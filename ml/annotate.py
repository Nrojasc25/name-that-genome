"""Build a versioned local annotation cache from frozen NCBI annotations and GRCh38."""

import argparse
from collections import Counter, defaultdict
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import sqlite3
import tempfile

import pyarrow.parquet as pq
import pysam

from .dataset_io import digest, source_connection, write_json
from .features import CONFIG, CONFIG_PATH, SCHEMA_VERSION, build_features

VARIANT_COLUMNS = ['variant_key', 'assembly', 'chromosome', 'position', 'ref', 'alt', 'source_record_ids']


def read_dataset(directory: Path):
    manifest = json.loads((directory / 'dataset_manifest.json').read_text())
    if digest(directory / 'variants.parquet') != manifest['outputs_sha256']['variants.parquet']:
        raise ValueError('Dataset variants checksum mismatch')
    rows = pq.read_table(directory / 'variants.parquet', columns=VARIANT_COLUMNS).to_pylist()
    if len(rows) != manifest['output_variants'] or len({r['variant_key'] for r in rows}) != len(rows):
        raise ValueError('Dataset row count or key uniqueness failed')
    return manifest, rows


def parse_frequency(values: list) -> tuple[float | None, str]:
    observed = []
    for raw in values:
        if raw is None or (isinstance(raw, str) and raw.strip() in ('', '.')):
            continue
        if isinstance(raw, bool) or not isinstance(raw, (int, float, str)):
            return None, 'invalid'
        try:
            value = float(raw)
        except (ValueError, OverflowError):
            return None, 'invalid'
        if not math.isfinite(value) or not 0 <= value <= 1:
            return None, 'invalid'
        observed.append(value)
    if not observed:
        return None, 'missing'
    if len(set(observed)) != 1:
        return None, 'conflicting'
    return observed[0], 'observed'


def annotate_variant(variant, source_records, consequences, fasta):
    ids = variant['source_record_ids']
    if not ids or any(identifier not in source_records for identifier in ids):
        raise ValueError('Variant source linkage is incomplete')
    chrom = 'chrM' if variant['chromosome'] == 'MT' else 'chr' + variant['chromosome']
    if chrom not in fasta.references:
        raise ValueError('Reference chromosome missing')
    start = variant['position'] - 1
    if start < 0 or fasta.fetch(chrom, start, start + len(variant['ref'])).upper() != variant['ref']:
        raise ValueError('Variant reference does not match cached reference genome')
    radius = CONFIG['context_radius']
    context = None
    context_status = 'boundary'
    if start >= radius and start + radius + 1 <= fasta.get_reference_length(chrom):
        sequence = fasta.fetch(chrom, start - radius, start + radius + 1).upper()
        if set(sequence) <= set('ACGT'):
            context = (sequence.count('G') + sequence.count('C')) / len(sequence)
            context_status = 'observed'
        else:
            context_status = 'ambiguous'
    frequencies, status = {}, {}
    for field in CONFIG['frequency_fields']:
        frequencies[field], status[field] = parse_frequency([source_records[i].get(field) for i in ids])
    annotation = {'variant_key': variant['variant_key'],
                  'consequences': sorted({term for i in ids for term in consequences.get(i, [])}),
                  'frequencies': frequencies, 'frequency_status': status,
                  'context_gc_fraction': context, 'context_status': context_status}
    build_features(variant, annotation)  # Validate the shared single-variant path before caching.
    return annotation


def build_cache(dataset: Path, database: Path, reference: Path, output: Path):
    if output.exists():
        raise FileExistsError('Annotation output exists; choose a new version/directory')
    manifest, variants = read_dataset(dataset)
    if digest(database) != manifest['source_database_sha256']:
        raise ValueError('ClinVar source snapshot checksum mismatch')
    if digest(reference) != manifest['reference']['fasta_sha256'] or digest(Path(str(reference) + '.fai')) != manifest['reference']['fai_sha256']:
        raise ValueError('Reference checksum mismatch')
    release_id = manifest['release']['id']
    source_records, consequences = {}, defaultdict(list)
    required = {i for variant in variants for i in variant['source_record_ids']}
    with source_connection(database) as source:
        for row in source.execute('SELECT id, raw_info FROM clinvar_record WHERE release_id=?', (release_id,)):
            if row['id'] in required:
                raw = json.loads(row['raw_info'])
                # Copy only population fields. Clinical labels and metadata never enter cache payloads.
                source_records[row['id']] = {field: raw.get(field) for field in CONFIG['frequency_fields']}
        for row in source.execute('SELECT c.record_id,c.term FROM record_consequence c JOIN clinvar_record r ON r.id=c.record_id WHERE r.release_id=? ORDER BY c.record_id,c.term', (release_id,)):
            if row['record_id'] in required:
                consequences[row['record_id']].append(row['term'])
    fingerprints = {'dataset_variants_sha256': manifest['outputs_sha256']['variants.parquet'],
                    'source_database_sha256': manifest['source_database_sha256'],
                    'reference_sha256': manifest['reference']['fasta_sha256'],
                    'feature_config_sha256': digest(CONFIG_PATH),
                    'annotation_code_sha256': digest(Path(__file__)),
                    'features_code_sha256': digest(Path(__file__).with_name('features.py'))}
    version = hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest()
    cache_manifest = {'annotation_version': version, 'schema_version': SCHEMA_VERSION,
                      'workflow': CONFIG['annotation_workflow'], 'fingerprints': fingerprints,
                      'dataset_version': manifest['dataset_version'], 'clinvar_release': manifest['release']['version'],
                      'transcript_policy': CONFIG['transcript_policy'],
                      'population_source_note': 'GO-ESP, ExAC, and 1000 Genomes fields frozen in ClinVar; original study versions and ancestry/coverage denominators are not available in this snapshot.',
                      'context_radius': CONFIG['context_radius'], 'reference_source': manifest['reference']['source_url'],
                      'deferred_annotations': CONFIG['deferred_annotations'],
                      'created_at_utc': datetime.now(timezone.utc).isoformat(), 'variants': len(variants)}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.annotate-', dir=output.parent) as temp:
        directory = Path(temp)
        statuses = {field: Counter() for field in CONFIG['frequency_fields']}
        context_statuses = Counter()
        with closing(sqlite3.connect(directory / 'annotations.sqlite')) as connection, connection, pysam.FastaFile(str(reference)) as fasta:
            connection.execute('CREATE TABLE annotation(variant_key TEXT PRIMARY KEY, variant_json TEXT NOT NULL, annotation_json TEXT NOT NULL)')
            for variant in sorted(variants, key=lambda r: r['variant_key']):
                annotation = annotate_variant(variant, source_records, consequences, fasta)
                for field in CONFIG['frequency_fields']:
                    statuses[field][annotation['frequency_status'][field]] += 1
                context_statuses[annotation['context_status']] += 1
                minimal = {key: variant[key] for key in VARIANT_COLUMNS if key != 'source_record_ids'}
                connection.execute('INSERT INTO annotation VALUES(?,?,?)', (variant['variant_key'], json.dumps(minimal, sort_keys=True), json.dumps(annotation, sort_keys=True)))
        if digest(database) != manifest['source_database_sha256']:
            raise ValueError('Source snapshot changed during annotation')
        cache_manifest['frequency_status_counts'] = {k: dict(v) for k, v in statuses.items()}
        cache_manifest['context_status_counts'] = dict(context_statuses)
        cache_manifest['cache_sha256'] = digest(directory / 'annotations.sqlite')
        write_json(directory / 'annotation_manifest.json', cache_manifest)
        directory.replace(output)
    return cache_manifest


class AnnotationCache:
    """Open once at service startup; fail closed on wrong version or modified content."""

    def __init__(self, directory: Path, *, expected_version: str):
        self.manifest = json.loads((directory / 'annotation_manifest.json').read_text())
        if self.manifest['annotation_version'] != expected_version or self.manifest['schema_version'] != SCHEMA_VERSION:
            raise ValueError('Annotation version/schema mismatch')
        fingerprints = self.manifest['fingerprints']
        if hashlib.sha256(json.dumps(fingerprints, sort_keys=True).encode()).hexdigest() != expected_version:
            raise ValueError('Annotation fingerprints disagree with version')
        if fingerprints['feature_config_sha256'] != digest(CONFIG_PATH) or fingerprints['features_code_sha256'] != digest(Path(__file__).with_name('features.py')):
            raise ValueError('Feature implementation does not match annotation artifact')
        path = directory / 'annotations.sqlite'
        if digest(path) != self.manifest['cache_sha256']:
            raise ValueError('Annotation cache checksum mismatch')
        self.connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
        self.connection.execute('PRAGMA query_only=ON')

    def features_for(self, variant_key: str):
        row = self.connection.execute('SELECT variant_json,annotation_json FROM annotation WHERE variant_key=?', (variant_key,)).fetchone()
        if row is None:
            raise KeyError('Variant has no annotation in this pinned cache')
        return build_features(json.loads(row[0]), json.loads(row[1]))

    def close(self):
        self.connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--database', type=Path, default=Path('backend/data/variants.sqlite'))
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = build_cache(args.dataset, args.database, args.reference, args.output)
    print(json.dumps({k: result[k] for k in ['annotation_version', 'variants', 'frequency_status_counts']}, indent=2))


if __name__ == '__main__':
    main()
