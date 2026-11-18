# Phase 5 model-improvement study

Post-v1-failure development study; training OOF used for selection, not unbiased release evidence. No new calibration/confidence policy or deployment.

Training rows: 16,500. Baseline replay matches the original OOF predictions exactly.
Selected candidate: **conservation-depth8-lp1.5**. Release approved: **no**.

| Candidate | Macro-F1 | Benign recall | Likely benign recall | Uncertain recall | Likely pathogenic recall | Pathogenic recall | P/LP → B/LB | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline-replay | 0.6405 | 0.636 | 0.964 | 0.888 | 0.096 | 0.634 | 2.261% | False |
| conservation-depth5-lp1 | 0.6847 | 0.641 | 0.952 | 0.869 | 0.260 | 0.645 | 1.612% | False |
| conservation-depth5-lp1.5 | 0.6908 | 0.641 | 0.951 | 0.828 | 0.390 | 0.570 | 1.593% | False |
| conservation-depth5-lp2 | 0.6687 | 0.634 | 0.951 | 0.779 | 0.579 | 0.348 | 1.573% | False |
| conservation-depth8-lp1 | 0.6756 | 0.627 | 0.940 | 0.844 | 0.300 | 0.614 | 1.612% | False |
| conservation-depth8-lp1.5 | 0.6743 | 0.621 | 0.942 | 0.801 | 0.404 | 0.540 | 1.632% | True |
| conservation-depth8-lp2 | 0.6632 | 0.625 | 0.940 | 0.771 | 0.514 | 0.410 | 1.671% | True |

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
