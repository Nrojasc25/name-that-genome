# Phase 5 model-improvement study

Post-v1-failure development study; training OOF used for selection, not unbiased release evidence. No new calibration/confidence policy or deployment.

Training rows: 16,500. Baseline replay matches the original OOF predictions exactly.
Selected candidate: **none — no candidate passes discrimination gates**. Release approved: **no**.

| Candidate | Accuracy | Macro-F1 | Benign recall | Likely benign recall | Uncertain recall | Likely pathogenic recall | Pathogenic recall | P/LP → B/LB | Eligible |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| baseline-replay | 0.7477 | 0.6405 | 0.636 | 0.964 | 0.888 | 0.096 | 0.634 | 2.261% | False |
| conservation-replay | 0.7424 | 0.6743 | 0.621 | 0.942 | 0.801 | 0.404 | 0.540 | 1.632% | False |
| population-depth5-lp1.0 | 0.7919 | 0.7263 | 0.732 | 0.947 | 0.897 | 0.320 | 0.702 | 0.924% | False |
| population-depth5-lp1.5 | 0.7884 | 0.7314 | 0.743 | 0.947 | 0.880 | 0.423 | 0.615 | 0.826% | False |
| population-depth5-lp2.0 | 0.7752 | 0.7212 | 0.738 | 0.947 | 0.857 | 0.516 | 0.495 | 0.885% | False |
| population-depth8-lp1.0 | 0.7854 | 0.7219 | 0.729 | 0.944 | 0.887 | 0.349 | 0.660 | 0.963% | False |
| population-depth8-lp1.5 | 0.7785 | 0.7191 | 0.738 | 0.943 | 0.874 | 0.403 | 0.595 | 0.944% | False |
| population-depth8-lp2.0 | 0.7727 | 0.7159 | 0.739 | 0.941 | 0.866 | 0.439 | 0.544 | 1.042% | False |

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

## Population-frequency experiment

Population-enabled candidates add eight gnomAD v4.1.1 columns: overall/ancestry-group maximum frequencies and missingness indicators for exomes and genomes. Exact PASS SNV matches only; absent values are not measured zeros. No external pathogenicity predictions are used.
