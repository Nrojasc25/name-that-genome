# Five-class candidate model card

Status as of 2026-11-18: **research candidate; rejected by project release gates**. No API integration or clinical-use claim.

## Intended task and scope

Predict the frozen ClinVar germline classification among Benign, Likely benign, Uncertain, Likely pathogenic, and Pathogenic. These are source-label predictions, not patient disease probabilities or independently established clinical classifications. No disease ranking is implemented.

The source snapshot covers eight target genes (ACADM, ATP7B, CFTR, COL4A5, FBN1, GAA, PAH, PKHD1) and overlapping annotations, not all ClinVar. Release 2026-09-13 contains 28,388 retained normalized GRCh38 variants. Exact label filtering, exclusions, reference checks, and import-provenance limitations are described in the [data audit](reports/data_audit.md).

## Model and inputs

Selected candidate: unweighted XGBoost, depth 5, 250 trees, selected among eleven predefined candidates by training-only cross-validation. All 16,500 training rows were used for its final refit. Training-CV macro-F1 was 0.6403. See the [training manifest](reports/model_manifest.json) for artifact identity and checksums.

The 42-feature schema includes sequence-change measurements, fixed consequence indicators, legacy population frequencies and missingness, and reference-window GC. Labels, gene IDs, review status, and clinical conditions are excluded as inputs. Imputation is fitted on training rows only. The [feature dictionary](FEATURES.md) defines each input and its limitations. Current annotation inference requires a supported key in the frozen cache; arbitrary novel variants are unsupported.

## Calibration and decisions

Validation contains 3,536 variants, split evenly into temperature-fit and policy-selection subsets. Temperature scaling failed the predefined minimum log-loss improvement; active temperature is 1.0. Scores remain **uncalibrated**. Highest score determines the class, with ties resolved by canonical class order.

No tested confidence rule achieved both 50% coverage and 85% accuracy on the selection subset. Every prediction receives a separate low-confidence flag. This does not replace its label with Uncertain. The [frozen policy](reports/evaluation_policy.json) records all choices before test access.

## First held-out results

| Metric | Test | Gene challenge |
|---|---:|---:|
| Variants | 3,536 | 4,816 |
| Macro-F1 | 0.6417 | 0.6499 |
| Balanced accuracy | 0.6461 | 0.6538 |
| Likely pathogenic recall | 8.83% | 13.04% |
| Logistic baseline macro-F1 | 0.6246 | 0.6509 |
| Pathogenic-group → benign-group errors | 22/1,090 (2.02%) | 36/1,028 (3.50%) |
| Benign-group → pathogenic-group errors | 2/1,327 (0.15%) | 1/1,557 (0.06%) |
| Mean class ECE | 0.0106 | 0.0522 |

Severe-error groups combine definite and likely labels; denominators are the corresponding true group, excluding Uncertain. Their rates do not describe overall error frequency. Both partitions fail the minimum 40% per-class recall and maximum 2% pathogenic-to-benign error criteria. The challenge additionally fails the logistic comparison and ECE threshold; both fail confidence coverage and accuracy criteria. All predefined gates must pass for approval.

The test 95% macro-F1 bootstrap interval is 0.5937–0.6752, based on seven connected-gene components. The challenge interval is 0.6246–0.6737, resampling variants conditional on its single CFTR-connected component. It does not establish generalization across unseen genes. Neither interval includes model-selection uncertainty. See the [complete evaluation](reports/evaluation_report.md) and [JSON diagnostics](reports/evaluation_report.json) for class metrics, subgroup support, reliability bins, and error examples.

## Limitations and next experiment

Likely pathogenic is poorly separated from Uncertain and Pathogenic. ClinVar likely-versus-definite labels may depend on evidence absent from the current features. Calibration preserves class ordering and cannot fix that discrimination problem. Sparse legacy population annotations and strong population-feature reliance may encode ascertainment effects. Conservation, protein-level, and modern ancestry-specific annotation are not included. No temporal, genome-wide, demographic, patient-level, or prospective validation is claimed.

Warm cached lookup, imputation, model prediction, and temperature transformation measured p95 0.168 ms over 100 timed runs on macOS 15.7.4 arm64 with Python 3.12. This excludes startup, API, network annotation, and SHAP. Phase 6 now provides verified class-specific raw-margin SHAP explanations; see the [SHAP report](reports/shap_report.md). This does not change model release status.

The candidate should not be presented as an accepted release. Investigate class separation and source/feature coverage in a versioned follow-up experiment. Both holdouts were opened once on 2026-11-18; obtaining a new holdout or explicitly declaring a reused-test study is required for further evaluation claims. Do not lower gates after seeing these results.

## Reproducibility

The [ML README](README.md) documents commands, dependencies, tests, and report rendering. Calibration and evaluation artifacts stay locally under ignored `ml/artifacts/`; small reports and provenance are tracked. The [evaluation manifest](reports/evaluation_manifest.json), [render manifest](reports/render_manifest.json), and [completed access record](reports/evaluation_access.json) bind the frozen policy and saved predictions. Report rendering reads saved predictions without rescoring the model. Fifty ML tests passed; all four plots were visually reviewed.

## Explanation assessment

Interventional Tree SHAP uses 100 uniformly sampled training rows after training-only imputation. It explains raw class margins, not probabilities, causal mechanisms, or patient risk. All five class outputs passed additivity checks on 200 sampled previously evaluated variants. Full details and measured explanation latency are in the [SHAP report](reports/shap_report.md).

Grouped consequence features dominate global mean absolute attributions for every class. Population missingness is also influential: the 1000 Genomes missingness indicator is the second-largest group for Benign, Uncertain, and Likely pathogenic in this sample. This supports further investigation of annotation-availability dependence; it does not establish leakage or biological relevance. The model's poor Likely pathogenic recall remains unresolved. Correlation, constrained feature combinations, background choice, and the small equally weighted evaluation samples limit interpretation.
