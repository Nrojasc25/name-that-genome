# Phase 4 training comparison

Training-only cross-validation estimates used for selection; not final test performance.

| Candidate | CV macro-F1 | Fold SD | CV log loss |
|---|---:|---:|---:|
| xgb-deep | 0.6403 | 0.0052 | 0.6671 |
| xgb-shallow | 0.6399 | 0.0069 | 0.6682 |
| xgb-deep-balanced | 0.6350 | 0.0076 | 0.7250 |
| xgb-shallow-balanced | 0.6340 | 0.0085 | 0.7436 |
| logistic-c1 | 0.6283 | 0.0056 | 0.6706 |
| logistic-c01 | 0.6249 | 0.0046 | 0.6724 |
| logistic-c1-balanced | 0.6149 | 0.0075 | 0.7530 |
| logistic-c01-balanced | 0.6140 | 0.0091 | 0.7564 |
| xgb-deep-no-population | 0.5189 | 0.0097 | 0.7362 |
| xgb-deep-balanced-no-population | 0.5140 | 0.0053 | 0.8712 |
| dummy-prior | 0.1018 | 0.0012 | 1.4225 |

Selected: **xgb-deep**. Refit on 16,500 training rows only; probabilities remain uncalibrated.

## Selected candidate: pooled training out-of-fold class metrics

| Class | Precision | Recall | F1 | Support |
|---|---:|---:|---:|---:|
| benign | 0.8146 | 0.6357 | 0.7141 | 560 |
| likely_benign | 0.8701 | 0.9636 | 0.9145 | 5636 |
| uncertain | 0.6941 | 0.8877 | 0.7791 | 5218 |
| likely_pathogenic | 0.4661 | 0.0963 | 0.1596 | 2430 |
| pathogenic | 0.6364 | 0.6340 | 0.6352 | 2656 |

Fold variation is descriptive, not a confidence interval. The primary CV folds share genes; the reserved gene challenge is needed to assess unseen-gene generalization.
Class weights and medians are recomputed within each fit fold. Logistic scaling is inside each fold. Population ablations remove all three frequency values and their missingness indicators.
The frozen validation set, final test set, and gene challenge were not scored. Calibration, quality thresholds, final evaluation, and production/API integration remain future work.
Candidate selection is based only on the predeclared CV ranking; held-out outcomes were not used. Timing figures in JSON are batch timings on this machine, not a production latency guarantee.
