# ClinVar dataset audit

Release: **2026-09-13** | Dataset: **clinvar-eight-gene-five-class-v1**

This report describes real source records and the reference-backed build. It is not model evaluation.

## Scope

Imported target genes: ACADM, ATP7B, CFTR, COL4A5, FBN1, GAA, PAH, PKHD1.
Other overlapping genes appear in annotations. This is an eight-target-gene subset, not all ClinVar or a genome-wide benchmark.

## Filter stages

| Stage | Records | Benign | Likely benign | Uncertain | Likely pathogenic | Pathogenic |
|---|---:|---:|---:|---:|---:|---:|
| source (exact labels before review) | 36065 | 907 | 9728 | 11082 | 4380 | 5028 |
| label/review eligible | 29177 | 906 | 9621 | 9823 | 4015 | 4812 |
| supported sequence after normalization | 28388 | 863 | 9545 | 9686 | 3771 | 4523 |
| reference validated | 28388 | 863 | 9545 | 9686 | 3771 | 4523 |
| deduplicated, no label conflicts | 28388 | 863 | 9545 | 9686 | 3771 | 4523 |

Stages are cumulative. Early counts include source rows; the final row counts unique canonical variants. Exact-label counts before review omit unsupported labels from class columns.

## Exclusions (one final reason per source record)

| Reason | Records |
|---|---:|
| combined_classification | 2038 |
| complex_sequence_change | 362 |
| conflicting_classification | 2366 |
| indel_exceeds_max_length | 75 |
| insufficient_review_stars | 1948 |
| missing_classification | 497 |
| symbolic_or_ambiguous_allele | 8 |
| unsupported_classification | 39 |
| unsupported_variant_type | 344 |

Row-level reports also retain independent label, sequence, and reference reasons. Duplicate-label disagreements quarantine the entire normalized group.

## Reference validation and duplicates

- normalized_unique_keys: 35618
- duplicate_groups: 0
- label_disagreement_groups: 0
- normalized_changed_records: 0
- Reference problems across all checked rows: {}
- Source database SHA-256: `14c0c14afc05f73e3e5ed417ab7fcdc0855a9e7b6e6a0d337d5bec54724b193d`
- FASTA SHA-256: `5be01555d98347fdb3714dc84c6f77c9d8bc774adcf32c6f7a8fa06f5baf5e51`
- Normalizer: bcftools 1.23.1 via pysam 0.24.0.

## Annotation coverage

| Field | Missing source records |
|---|---:|
| genes | 0 |
| consequences | 209 |
| condition_links | 371 |
| classification | 365 |
| review_stars | 365 |

Complete class-by-gene and class-by-consequence counts, raw label strings, review status, and raw annotation presence are in data_audit.json. Annotation presence does not imply a validated feature.

## Gates and limitations

- reference_validation_complete: True
- unique_canonical_keys: True
- input_accounting_complete: True
- minimum_examples_per_class: 100
- class_support_gate_passed: True
- source_unchanged: True

A minimum of 100 unique variants per class is a planning feasibility check, not proof of usable gene-held-out splits, statistical power, or future model performance.
Variants outside simple SNVs and indels of 1-49 bases are excluded. Multiallelic and complex records are not decomposed because per-allele labels are not established.
No training/test split is made here. Review stars, source classifications, identifiers, gene identity, and clinical conditions must not become default predictor features.

## Provenance gaps

- The upstream VCF SHA-256 is asserted by imported metadata; the original VCF was not independently downloaded or verified in this build.
- The original database import code and original download timestamp are unavailable. imported_at is retained as import metadata, not a download date.
- Reproduction starts from the published SQLite snapshot, validated by SHA-256; exact upstream VCF-to-SQLite reconstruction is not established.
