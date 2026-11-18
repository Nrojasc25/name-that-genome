"""Build a frozen, reference-validated five-class dataset from a pinned ClinVar snapshot."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq
import pysam

from .audit_data import class_counts, group_counts, summarize
from .dataset_io import DEFAULT_CONFIG, DEFAULT_DATABASE, digest, load_source, write_json
from .labels import CLASS_ORDER, POLICY_VERSION
from .normalize import NORMALIZER_VERSION, prepare_rows, select_rows

STR = pa.string()
STRINGS = pa.list_(STR)
INTS = pa.list_(pa.int64())
VARIANT_SCHEMA = pa.schema([
    ('variant_key', STR), ('assembly', STR), ('chromosome', STR), ('position', pa.int64()),
    ('ref', STR), ('alt', STR), ('variant_type', STR), ('genes', STRINGS), ('consequences', STRINGS),
    ('label', STR), ('class_id', pa.int8()), ('representative_record_id', STR),
    ('source_record_ids', STRINGS), ('clinvar_variation_ids', INTS), ('clinvar_allele_ids', INTS),
])
EXCLUSION_SCHEMA = pa.schema([
    ('record_id', STR), ('clinvar_variation_id', pa.int64()), ('original_assembly', STR),
    ('original_chromosome', STR), ('original_position', pa.int64()), ('original_ref', STR), ('original_alt', STR),
    ('variant_key', STR), ('source_classification', STR), ('label', STR),
    ('exclusion_reason', STR), ('label_reason', STR), ('sequence_reason', STR), ('reference_reason', STR),
])
MEMBERSHIP_SCHEMA = pa.schema([
    ('record_id', STR), ('variant_key', STR), ('disposition', STR), ('representative_record_id', STR),
    ('source_classification', STR), ('review_stars', pa.int8()), ('original_chromosome', STR),
    ('original_position', pa.int64()), ('original_ref', STR), ('original_alt', STR),
])


def table(rows, schema, path):
    pq.write_table(pa.Table.from_pylist(rows, schema=schema), path, compression='zstd')


def stage(name, rows):
    return {'name': name, 'records': len(rows), 'class_counts': class_counts(rows)}


def render_report(audit, manifest):
    lines = ['# ClinVar dataset audit', '', f"Release: **{manifest['release']['version']}** | Dataset: **{manifest['dataset_version']}**", '',
             'This report describes real source records and the reference-backed build. It is not model evaluation.', '',
             '## Scope', '', f"Imported target genes: {', '.join(audit['selected_genes_from_import_metadata'] or [])}.",
             'Other overlapping genes appear in annotations. This is an eight-target-gene subset, not all ClinVar or a genome-wide benchmark.', '',
             '## Filter stages', '', '| Stage | Records | Benign | Likely benign | Uncertain | Likely pathogenic | Pathogenic |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for item in audit['stages']:
        lines.append('| ' + ' | '.join([item['name'], str(item['records']), *[str(item['class_counts'][str(k)]) for k in CLASS_ORDER]]) + ' |')
    lines += ['', 'Stages are cumulative. Early counts include source rows; the final row counts unique canonical variants. Exact-label counts before review omit unsupported labels from class columns.', '',
              '## Exclusions (one final reason per source record)', '', '| Reason | Records |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in audit['exclusion_counts'].items()]
    lines += ['', 'Row-level reports also retain independent label, sequence, and reference reasons. Duplicate-label disagreements quarantine the entire normalized group.', '',
              '## Reference validation and duplicates', '']
    lines += [f'- {k}: {v}' for k, v in audit['normalization'].items()]
    lines += [f"- Reference problems across all checked rows: {json.dumps(audit['reference_issues'], sort_keys=True)}",
              f"- Source database SHA-256: `{manifest['source_database_sha256']}`",
              f"- FASTA SHA-256: `{manifest['reference']['fasta_sha256']}`",
              f"- Normalizer: {NORMALIZER_VERSION}.", '',
              '## Annotation coverage', '', '| Field | Missing source records |', '|---|---:|']
    lines += [f'| {k} | {v} |' for k, v in audit['missingness'].items()]
    lines += ['', 'Complete class-by-gene and class-by-consequence counts, raw label strings, review status, and raw annotation presence are in data_audit.json. Annotation presence does not imply a validated feature.', '',
              '## Gates and limitations', '']
    lines += [f'- {k}: {v}' for k, v in manifest['gates'].items()]
    lines += ['', 'A minimum of 100 unique variants per class is a planning feasibility check, not proof of usable gene-held-out splits, statistical power, or future model performance.',
              'Variants outside simple SNVs and indels of 1-49 bases are excluded. Multiallelic and complex records are not decomposed because per-allele labels are not established.',
              'No training/test split is made here. Review stars, source classifications, identifiers, gene identity, and clinical conditions must not become default predictor features.', '',
              '## Provenance gaps', '']
    lines += [f'- {gap}' for gap in manifest['provenance_gaps']]
    return '\n'.join(lines) + '\n'


def build(database: Path, fasta: Path, reference_manifest: Path, output: Path, config_path: Path = DEFAULT_CONFIG):
    config = json.loads(config_path.read_text())
    reference = json.loads(reference_manifest.read_text())
    if output.exists():
        raise FileExistsError('Output already exists; use a new directory to preserve frozen artifacts')
    if reference['assembly'] != config['assembly'] or reference['source_url'] != config['reference']['url']:
        raise ValueError('Reference identity does not match configured reference')
    if reference['compressed_md5'] != config['reference']['compressed_md5']:
        raise ValueError('Reference checksum metadata does not match configuration')
    for path, key in [(fasta, 'fasta_sha256'), (Path(str(fasta) + '.fai'), 'fai_sha256')]:
        if digest(path) != reference[key]:
            raise ValueError(f'Reference checksum mismatch: {key}')
    database_sha = digest(database)
    if config.get('source_database_sha256') and database_sha != config['source_database_sha256']:
        raise ValueError('Database does not match the pinned snapshot checksum')
    release, source, inventory = load_source(database, config)
    audit = summarize(release, source, inventory)
    rows = prepare_rows(source, fasta, config)
    selected, excluded, normalization = select_rows(rows)
    labeled = [r for r in rows if not r['label_reason']]
    supported = [r for r in labeled if not r['sequence_reason']]
    checked = [r for r in supported if not r['reference_reason']]
    audit.update(stages=[
        {'name': 'source (exact labels before review)', 'records': len(rows), 'class_counts': audit['exact_class_counts_before_review_filter']},
        stage('label/review eligible', labeled), stage('supported sequence after normalization', supported),
        stage('reference validated', checked), stage('deduplicated, no label conflicts', selected),
    ], normalization=normalization,
        reference_issues=dict(sorted(Counter(r['reference_reason'] for r in rows if r['reference_reason']).items())),
        exclusion_counts=dict(sorted(Counter(r['exclusion_reason'] for r in excluded).items())),
        final_class_by_gene=group_counts(selected, 'genes'),
        final_class_by_consequence=group_counts(selected, 'consequences'),
        final_missingness={'genes': sum(not r['genes'] for r in selected), 'consequences': sum(not r['consequences'] for r in selected)},
        class_counts_review_stars_at_least_two=class_counts([r for r in selected if r['review_stars'] >= 2]))
    variants = [{
        'variant_key': r['normalized_key'], 'assembly': config['assembly'], 'chromosome': r['canonical_chromosome'],
        'position': r['normalized_position'], 'ref': r['normalized_ref'], 'alt': r['normalized_alt'],
        'variant_type': r['normalized_type'], 'genes': r['genes'], 'consequences': r['consequences'],
        'label': str(r['label']), 'class_id': r['class_id'], 'representative_record_id': r['id'],
        'source_record_ids': r['source_record_ids'], 'clinvar_variation_ids': r['clinvar_variation_ids'], 'clinvar_allele_ids': r['clinvar_allele_ids'],
    } for r in selected]
    rejected = [{
        'record_id': r['id'], 'clinvar_variation_id': r['clinvar_variation_id'], 'original_assembly': r['assembly'],
        'original_chromosome': r['chromosome'], 'original_position': r['position'], 'original_ref': r['ref'], 'original_alt': r['alt'],
        'variant_key': r['normalized_key'], 'source_classification': r['germline_classification'],
        **{key: r[key] for key in ['label', 'exclusion_reason', 'label_reason', 'sequence_reason', 'reference_reason']},
    } for r in excluded]
    representatives = {r['normalized_key']: r['id'] for r in selected}
    excluded_ids = {r['id'] for r in excluded}
    members = [{
        'record_id': r['id'], 'variant_key': r['normalized_key'], 'disposition': 'excluded' if r['id'] in excluded_ids else 'included',
        'representative_record_id': representatives.get(r['normalized_key']), 'source_classification': r['germline_classification'],
        'review_stars': r['review_stars'], 'original_chromosome': r['chromosome'], 'original_position': r['position'],
        'original_ref': r['ref'], 'original_alt': r['alt'],
    } for r in rows]
    minimum_ok = all(v >= config['minimum_examples_per_class'] for v in class_counts(selected).values())
    manifest = {
        'dataset_version': config['dataset_version'], 'schema_version': 1,
        'build_status': 'ready_for_feature_development' if minimum_ok else 'insufficient_class_support',
        'created_at_utc': datetime.now(timezone.utc).isoformat(),
        'source_database_sha256': database_sha, 'snapshot_url': config['snapshot_url'],
        'release': release, 'reference': reference, 'label_policy_version': POLICY_VERSION,
        'label_policy_sha256': digest(Path(__file__).parent / 'config/labels.json'),
        'class_order': list(CLASS_ORDER), 'config': config, 'config_sha256': digest(config_path),
        'normalizer': NORMALIZER_VERSION,
        'environment': {'python': platform.python_version(), 'pysam': pysam.__version__, 'pyarrow': pa.__version__},
        'build_command': ['python', '-m', 'ml.build_dataset', '--database', str(database), '--reference', str(fasta),
                          '--reference-manifest', str(reference_manifest), '--config', str(config_path), '--output', str(output)],
        'source_code_sha256': {p.name: digest(p) for p in sorted(Path(__file__).parent.glob('*.py'))},
        'input_records': len(rows), 'output_variants': len(selected), 'excluded_records': len(excluded),
        'class_counts': class_counts(selected),
        'feature_candidate_columns': ['variant_type', 'ref', 'alt', 'consequences'],
        'non_feature_columns': ['variant_key', 'assembly', 'chromosome', 'position', 'genes', 'label', 'class_id',
                                'representative_record_id', 'source_record_ids', 'clinvar_variation_ids', 'clinvar_allele_ids'],
        'gates': {'reference_validation_complete': True, 'unique_canonical_keys': len({r['normalized_key'] for r in selected}) == len(selected),
                  'input_accounting_complete': len(selected) + len(excluded) == len(rows),
                  'minimum_examples_per_class': config['minimum_examples_per_class'], 'class_support_gate_passed': minimum_ok, 'source_unchanged': True},
        'provenance_gaps': [
            'The upstream VCF SHA-256 is asserted by imported metadata; the original VCF was not independently downloaded or verified in this build.',
            'The original database import code and original download timestamp are unavailable. imported_at is retained as import metadata, not a download date.',
            'Reproduction starts from the published SQLite snapshot, validated by SHA-256; exact upstream VCF-to-SQLite reconstruction is not established.',
        ],
    }
    if digest(database) != database_sha:
        raise ValueError('Source database changed during build')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.dataset-build-', dir=output.parent) as temp:
        directory = Path(temp)
        table(variants, VARIANT_SCHEMA, directory / 'variants.parquet')
        table(rejected, EXCLUSION_SCHEMA, directory / 'exclusions.parquet')
        table(members, MEMBERSHIP_SCHEMA, directory / 'source_membership.parquet')
        write_json(directory / 'data_audit.json', audit)
        (directory / 'data_audit.md').write_text(render_report(audit, manifest))
        manifest['outputs_sha256'] = {p.name: digest(p) for p in sorted(directory.iterdir())}
        write_json(directory / 'dataset_manifest.json', manifest)
        # A failed build never leaves a success manifest in the requested output directory.
        directory.replace(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--reference', type=Path, required=True)
    parser.add_argument('--reference-manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.database, args.reference, args.reference_manifest, args.output, args.config)
    print(json.dumps({key: manifest[key] for key in ['build_status', 'input_records', 'output_variants', 'excluded_records', 'class_counts']}, indent=2))


if __name__ == '__main__':
    main()
