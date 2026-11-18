# Feature coverage - Phase 3

Prepared **28,388 variants** with **42 fixed features**.

This is a raw feature matrix. No model, imputer, or scaler has been fitted on the full dataset.

## Population and reference-context availability

| Feature | Observed | Missing |
|---|---:|---:|
| af_esp | 946 | 27442 |
| af_exac | 3536 | 24852 |
| af_tgp | 1466 | 26922 |
| context_gc_fraction | 28388 | 0 |

Detailed per-class counts for every feature are in feature_coverage.json. Zero is counted as observed, not missing.

## Supported annotation workflow

Consequence terms and legacy population fields come from the checksum-pinned NCBI ClinVar snapshot. The cache preserves all consequence terms with no transcript selected and no severity ranking. Reference GC context is computed from the pinned GRCh38 FASTA.

Study-specific versions, population coverage denominators, and ancestry breakdowns are absent from the source snapshot. Frequencies are not described as current gnomAD frequencies. Missing/invalid/conflicting values remain null, with explicit missingness indicators.

Conservation, transcript-specific protein changes, and modern population enrichment remain follow-up annotations, not fabricated columns. Missingness may itself be associated with ClinVar ascertainment; evaluate with/without population features during training.

## Leakage controls

Only the fixed feature schema is exported. Labels, IDs, genes, positions, conditions, review stars, and source classifications are absent from features.parquet. feature_rows.parquet provides a separate ordered key mapping. Targets remain in the Phase 2 dataset.

Preprocessing must be fitted separately for each training fold with explicit training keys, then reused unchanged for validation/test data and inference. The fixed consequence/substitution vocabulary is not learned from target labels.

## Inference support

AnnotationCache.features_for(normalized_key) runs the same function used in batch generation. An unknown key fails explicitly; the cache does not annotate new variants outside the frozen dataset. API model integration remains a later phase.
