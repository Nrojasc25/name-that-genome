# Phase 5 model-improvement study

Post-v1-failure development study; training OOF used for selection, not unbiased release evidence. No new calibration/confidence policy or deployment.

Training rows: 16,500. Baseline replay matches the original OOF predictions exactly.
Selected candidate: **none — no candidate passes discrimination gates**. Release approved: **no**.

| Candidate | Accuracy | Macro-F1 | Benign recall | Likely benign recall | Uncertain recall | Likely pathogenic recall | Pathogenic recall | P/LP → B/LB | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline-replay | 0.7477 | 0.6405 | 0.636 | 0.964 | 0.888 | 0.096 | 0.634 | 2.261% | False |
| conservation-replay | 0.7424 | 0.6743 | 0.621 | 0.942 | 0.801 | 0.404 | 0.540 | 1.632% | False |
| protein-depth5-lp1.0 | 0.7890 | 0.7130 | 0.675 | 0.946 | 0.894 | 0.323 | 0.701 | 1.081% | False |
| protein-depth5-lp1.5 | 0.7852 | 0.7175 | 0.680 | 0.944 | 0.876 | 0.427 | 0.621 | 1.140% | False |
| protein-depth8-lp1.0 | 0.7788 | 0.7052 | 0.668 | 0.939 | 0.878 | 0.357 | 0.654 | 1.199% | False |
| protein-depth8-lp1.5 | 0.7738 | 0.7047 | 0.675 | 0.941 | 0.869 | 0.403 | 0.591 | 1.180% | False |
| protein-depth12-lp1.0 | 0.7761 | 0.7019 | 0.666 | 0.938 | 0.878 | 0.358 | 0.640 | 1.081% | False |
| protein-depth12-lp1.5 | 0.7728 | 0.7040 | 0.686 | 0.936 | 0.873 | 0.397 | 0.591 | 1.121% | False |

## Feature sufficiency

3,102 distinct feature vectors among 16,500 training variants. 12,697 rows belong to identical-vector groups with conflicting labels; 2,183 are Likely pathogenic.
Optimistic empirical deterministic accuracy ceiling on these training vectors: 79.04%.
Training-only feature-equivalence diagnostic after training imputation. Maximum accuracy is an optimistic empirical ceiling for a deterministic classifier on these exact rows/features, not a held-out performance bound. Different variants can share features without sharing biology.

## Decision

Fresh independent holdout and validation policy required before promotion; if none eligible, improve feature/data coverage before further tuning.
Acceptance thresholds and the active API model are unchanged. Increasing Likely pathogenic training weight is not calibration and cannot be assumed to improve all classes. See JSON for every class, fold, severe-error direction, distribution metric, and failed gate. Confidence/calibration/latency gates have not been reassessed in this study.

## Conservation experiment

Extra features: SNV phyloP100way and its missingness indicator. Fold medians use fit rows only. Enriched vectors: 14,390; conflicting rows: 2,182; empirical deterministic accuracy ceiling: 95.07%.
Baseline replay uses the original 42 features; all other candidates use the two additional experimental columns. These columns are not deployed or claimed compatible with the existing serving schema.

## Transcript/protein experiment

Protein-enabled candidates add fixed transcript/splice geometry, amino-acid identities, and coding-change indicators. Conservation replay omits these new features. No class labels, identifiers, or external pathogenicity scores are predictor columns.
Accuracy is correct five-class argmax predictions divided by all training OOF rows, without filtering by confidence. These selection results cannot establish accuracy on the locked temporal cohort.
