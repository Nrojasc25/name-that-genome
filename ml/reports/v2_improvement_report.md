# Phase 5 model-improvement study

Post-v1-failure development study; training OOF used for selection, not unbiased release evidence. No new calibration/confidence policy or deployment.

Training rows: 16,500. Baseline replay matches the original OOF predictions exactly.
Selected candidate: **none — no candidate passes discrimination gates**. Release approved: **no**.

| Candidate | Macro-F1 | Benign recall | Likely benign recall | Uncertain recall | Likely pathogenic recall | Pathogenic recall | P/LP → B/LB | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| baseline-replay | 0.6405 | 0.636 | 0.964 | 0.888 | 0.096 | 0.634 | 2.261% | False |
| depth3-lp2 | 0.6361 | 0.595 | 0.966 | 0.877 | 0.297 | 0.348 | 2.281% | False |
| depth5-lp2 | 0.6350 | 0.650 | 0.963 | 0.863 | 0.333 | 0.304 | 2.261% | False |
| depth5-lp4 | 0.5372 | 0.661 | 0.961 | 0.374 | 0.822 | 0.066 | 2.241% | False |
| depth5-lp8 | 0.4781 | 0.629 | 0.959 | 0.183 | 0.927 | 0.037 | 2.241% | False |
| depth5-balanced-lp2 | 0.5698 | 0.786 | 0.935 | 0.353 | 0.733 | 0.262 | 2.340% | False |
| depth5-balanced-lp4 | 0.4781 | 0.784 | 0.933 | 0.166 | 0.915 | 0.064 | 2.300% | False |
| depth8-lp2 | 0.6328 | 0.641 | 0.955 | 0.843 | 0.308 | 0.356 | 2.340% | False |
| depth8-lp4 | 0.5450 | 0.641 | 0.954 | 0.390 | 0.777 | 0.111 | 2.261% | False |
| depth8-balanced-lp2 | 0.5628 | 0.732 | 0.925 | 0.335 | 0.700 | 0.308 | 2.320% | False |
| depth3-balanced-lp2 | 0.5442 | 0.789 | 0.927 | 0.291 | 0.777 | 0.223 | 2.320% | False |

## Feature sufficiency

3,102 distinct feature vectors among 16,500 training variants. 12,697 rows belong to identical-vector groups with conflicting labels; 2,183 are Likely pathogenic.
Optimistic empirical deterministic accuracy ceiling on these training vectors: 79.04%.
Training-only feature-equivalence diagnostic after training imputation. Maximum accuracy is an optimistic empirical ceiling for a deterministic classifier on these exact rows/features, not a held-out performance bound. Different variants can share features without sharing biology.

## Decision

Fresh independent holdout and validation policy required before promotion; if none eligible, improve feature/data coverage before further tuning.
Acceptance thresholds and the active API model are unchanged. Increasing Likely pathogenic training weight is not calibration and cannot be assumed to improve all classes. See JSON for every class, fold, severe-error direction, distribution metric, and failed gate. Confidence/calibration/latency gates have not been reassessed in this study.
