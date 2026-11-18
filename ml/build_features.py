"""Export raw allowlisted features and coverage reports; do not fit preprocessing here."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import tempfile

import pyarrow as pa
import pyarrow.parquet as pq

from .annotate import AnnotationCache, read_dataset
from .dataset_io import digest, write_json
from .features import CONFIG, CONFIG_PATH, FEATURE_DICTIONARY, FEATURE_NAMES, SCHEMA_VERSION
from .labels import CLASS_ORDER
from .preprocessing import validate_vector


def coverage(vectors, labels):
    report = {}
    for name in FEATURE_NAMES:
        by_class = {}
        for label in CLASS_ORDER:
            indices = [i for i, item in enumerate(labels) if item == label]
            observed = [vectors[i][name] for i in indices if vectors[i][name] is not None]
            by_class[str(label)] = {'total': len(indices), 'observed': len(observed), 'missing': len(indices) - len(observed),
                                    'zero': sum(value == 0 for value in observed)}
        values = [row[name] for row in vectors if row[name] is not None]
        report[name] = {'total': len(vectors), 'observed': len(values), 'missing': len(vectors) - len(values),
                        'minimum': min(values) if values else None, 'maximum': max(values) if values else None,
                        'by_class': by_class}
    return report


def build(dataset: Path, cache_directory: Path, output: Path):
    if output.exists():
        raise FileExistsError('Feature output exists; choose a fresh directory')
    dataset_manifest, variants = read_dataset(dataset)
    cache_manifest = json.loads((cache_directory / 'annotation_manifest.json').read_text())
    if cache_manifest['fingerprints']['dataset_variants_sha256'] != dataset_manifest['outputs_sha256']['variants.parquet']:
        raise ValueError('Cache was built for a different dataset')
    cache = AnnotationCache(cache_directory, expected_version=cache_manifest['annotation_version'])
    try:
        keys = [r['variant_key'] for r in variants]
        vectors = [cache.features_for(key) for key in keys]
    finally:
        cache.close()
    for vector in vectors:
        validate_vector(vector)
    # Labels are loaded only after vectors are built, and are used exclusively for coverage reporting.
    target_rows = pq.read_table(dataset / 'variants.parquet', columns=['variant_key', 'label']).to_pylist()
    target_map = {r['variant_key']: r['label'] for r in target_rows}
    labels = [target_map[key] for key in keys]
    report = {'variants': len(keys), 'features': len(FEATURE_NAMES), 'class_counts': dict(Counter(labels)),
              'schema_version': SCHEMA_VERSION, 'annotation_version': cache_manifest['annotation_version'],
              'feature_coverage': coverage(vectors, labels), 'preprocessing_fitted': False,
              'deferred_annotations': CONFIG['deferred_annotations']}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.features-', dir=output.parent) as temp:
        directory = Path(temp)
        schema = pa.schema([(name, pa.float64()) for name in FEATURE_NAMES])
        pq.write_table(pa.Table.from_pylist(vectors, schema=schema), directory / 'features.parquet', compression='zstd')
        pq.write_table(pa.table({'variant_key': pa.array(keys, type=pa.string())}), directory / 'feature_rows.parquet', compression='zstd')
        write_json(directory / 'feature_dictionary.json', FEATURE_DICTIONARY)
        write_json(directory / 'feature_coverage.json', report)
        lines = ['# Feature coverage - Phase 3', '', f'Prepared **{len(keys):,} variants** with **{len(FEATURE_NAMES)} fixed features**.', '',
                 'This is a raw feature matrix. No model, imputer, or scaler has been fitted on the full dataset.', '',
                 '## Population and reference-context availability', '', '| Feature | Observed | Missing |', '|---|---:|---:|']
        for name in [field.lower() for field in CONFIG['frequency_fields']] + ['context_gc_fraction']:
            item = report['feature_coverage'][name]
            lines.append(f"| {name} | {item['observed']} | {item['missing']} |")
        lines += ['', 'Detailed per-class counts for every feature are in feature_coverage.json. Zero is counted as observed, not missing.', '',
                  '## Supported annotation workflow', '',
                  'Consequence terms and legacy population fields come from the checksum-pinned NCBI ClinVar snapshot. The cache preserves all consequence terms with no transcript selected and no severity ranking. Reference GC context is computed from the pinned GRCh38 FASTA.', '',
                  'Study-specific versions, population coverage denominators, and ancestry breakdowns are absent from the source snapshot. Frequencies are not described as current gnomAD frequencies. Missing/invalid/conflicting values remain null, with explicit missingness indicators.', '',
                  'Conservation, transcript-specific protein changes, and modern population enrichment remain follow-up annotations, not fabricated columns. Missingness may itself be associated with ClinVar ascertainment; evaluate with/without population features during training.', '',
                  '## Leakage controls', '',
                  'Only the fixed feature schema is exported. Labels, IDs, genes, positions, conditions, review stars, and source classifications are absent from features.parquet. feature_rows.parquet provides a separate ordered key mapping. Targets remain in the Phase 2 dataset.', '',
                  'Preprocessing must be fitted separately for each training fold with explicit training keys, then reused unchanged for validation/test data and inference. The fixed consequence/substitution vocabulary is not learned from target labels.', '',
                  '## Inference support', '',
                  'AnnotationCache.features_for(normalized_key) runs the same function used in batch generation. An unknown key fails explicitly; the cache does not annotate new variants outside the frozen dataset. API model integration remains a later phase.']
        (directory / 'feature_coverage.md').write_text('\n'.join(lines) + '\n')
        manifest = {'schema_version': SCHEMA_VERSION, 'annotation_version': cache_manifest['annotation_version'],
                    'dataset_version': dataset_manifest['dataset_version'], 'dataset_variants_sha256': dataset_manifest['outputs_sha256']['variants.parquet'],
                    'annotation_cache_sha256': cache_manifest['cache_sha256'], 'feature_config_sha256': digest(CONFIG_PATH),
                    'feature_names': list(FEATURE_NAMES), 'rows': len(keys), 'preprocessing_fitted': False,
                    'row_alignment': 'features.parquet row i matches feature_rows.parquet row i; never sort one independently.',
                    'created_at_utc': datetime.now(timezone.utc).isoformat(),
                    'code_sha256': {name: digest(Path(__file__).with_name(name)) for name in ['features.py', 'annotate.py', 'preprocessing.py', 'build_features.py']},
                    'outputs_sha256': {p.name: digest(p) for p in sorted(directory.iterdir())},
                    'build_command': ['python', '-m', 'ml.build_features', '--dataset', str(dataset), '--cache', str(cache_directory), '--output', str(output)]}
        write_json(directory / 'feature_manifest.json', manifest)
        directory.replace(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--cache', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    manifest = build(args.dataset, args.cache, args.output)
    print(f"Exported {manifest['rows']} rows and {len(manifest['feature_names'])} features; preprocessing not fitted.")


if __name__ == '__main__':
    main()
