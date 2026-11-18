# Phase 5 follow-up: feature enrichment and a new research candidate

The first improvement cycle is complete. **Phase 5 release approval is still outstanding.** A new conservation-enriched candidate passes the unchanged discrimination thresholds on training cross-validation; it has not passed an independent release evaluation or replaced the API model.

## What was wrong and what changed

The original 42 features compress 16,500 training variants into only 3,102 distinct vectors. Of those variants, 12,697 share their exact feature vector with variants carrying different labels. Increasing tree depth cannot distinguish identical inputs. This does not prove the original release criteria are mathematically impossible, but it motivates adding information rather than only changing weights.

An eleven-configuration study tested deeper trees and greater Likely pathogenic class weight. None passed all discrimination criteria. Raising that class's recall alone shifted errors into Pathogenic and Uncertain. See [v2 results](reports/v2_improvement_report.md).

The next study adds two experimental inputs: a UCSC 100-way phyloP score for SNVs and an explicit missingness indicator. The score is obtained by genomic coordinate, without using ClinVar classifications, review status, genes, or conditions. Indels and missing track values remain null. The existing training-fitted imputer is reused for original features; conservation medians are fitted separately within each CV fit fold.

The 100-way track was fetched through the [UCSC API](https://genome.ucsc.edu/goldenPath/help/api.html). GRCh38's 1-based variant position is converted to the API's 0-based half-open interval. Response files, requested intervals, source data/download times, code, and SHA-256 hashes are frozen in the [conservation manifest](reports/conservation_manifest.json). These are API track values; [UCSC documents precision differences between browser track values and original conservation downloads](https://genome.ucsc.edu/FAQ/FAQdownloads.html). No live requests occur during training, and these experimental features are not yet served by the application.

With these features, training rows contain 14,390 distinct vectors, and 2,182 rows remain in conflicting-vector groups. The optimistic deterministic accuracy ceiling on these exact training vectors rises from 79.04% to 95.07%. This is a feature-equivalence diagnostic, **not a forecast of unseen accuracy**.

## Training-only comparison

| Metric | Original candidate replay | Selected conservation candidate |
|---|---:|---:|
| Pooled OOF macro-F1 | 0.6405 | 0.6743 |
| Benign recall | 63.6% | 62.1% |
| Likely benign recall | 96.4% | 94.2% |
| Uncertain recall | 88.8% | 80.1% |
| Likely pathogenic recall | 9.6% | 40.4% |
| Pathogenic recall | 63.4% | 54.0% |
| True P/LP predicted B/LB | 2.26% | 1.63% |

Recall improved for the weakest class at a cost to several others. The selected candidate uses depth 8, 500 trees, and a 1.5× training weight for Likely pathogenic. Both the 1.5× and 2× depth-8 conservation candidates meet the existing pooled discrimination criteria; the predefined ranking picks the stronger mean-fold macro-F1 among eligible candidates. The highest macro-F1 overall (0.6908, depth 5 / 1.5×) was **not** selected because its Likely pathogenic recall remained below 40%.

See [v3 results](reports/v3_improvement_report.md) and [full per-class/fold diagnostics](reports/v3_improvement_report.json). The original baseline replay matches every historical training OOF prediction exactly. Neither study loads validation, test, or gene-challenge labels. Study design was informed by previous Phase 5 failures, so these are development/selection estimates, not independent release evidence. Passing a 40% pooled recall threshold by a small margin is not evidence that it will pass on a new dataset.

## Saved candidate and safeguards

The selected model was refitted on all 16,500 training rows and saved to `ml/artifacts/conservation-candidate-v3/`. Reloaded predictions match the original fitted model on 512 deterministic probe rows. The artifact includes the original-feature preprocessor, conservation median/missingness specification, 44-column schema, class order, training-key digest, environment lock, and study/source fingerprints. See the [candidate manifest](reports/conservation_candidate_manifest.json).

It is explicitly **uncalibrated**, **not approved**, and **not compatible with the current 42-feature serving pipeline**. Existing API artifacts, SHAP background, calibration policy, release thresholds, and consumed-test ledger are unchanged. Do not point the API at this model or copy it over `training-v1-final`.

## Remaining work before Phase 5 can pass

1. Freeze an independent evaluation cohort that excludes all prior variant keys (and account for related alleles/loci and gene overlap). No unused independent cohort is currently present locally. A different shuffle of the old variants does not make a new holdout. If old test sets are used for development comparisons, label them explicitly as reused and do not claim fresh validation.
2. Extend the conservation cache/feature contract to the validation and future evaluation cohorts with consistent missingness semantics. The current cache and experimental matrix deliberately contain training rows only. Avoid making annotation availability depend on partition membership.
3. Freeze the candidate and validation protocol. Assess calibration and confidence coverage/accuracy on validation data; do not deploy a confidence threshold chosen from training OOF scores.
4. Evaluate the frozen complete predictor against **all** existing gates, including per-class recalls, both severe-error directions, baselines, calibration, confidence, latency, and the gene challenge. Report failures without lowering thresholds.
5. If approved, implement the versioned 44-feature serving adapter, regenerate SHAP background/explanations against that exact model and preprocessing, and rerun Phase 7 integration checks. Existing saved results must retain their original versions.

The classifier still targets ClinVar's five labels; conservation does not supply all evidence used to distinguish likely from definite labels. The current eight-gene scope, sparse legacy population fields, and training CV's shared genes/loci remain limitations. Broader protein/transcript annotation or data expansion may still be necessary.

## Reproduce the development studies

Existing output directories are immutable. These commands document completed runs; choose new versioned destinations for intentional repetitions.

```bash
# Original-feature training-only study.
.venv/bin/python -m ml.improve --dataset ml/data/clinvar-five-class-v1-rebuild --features ml/data/features-v1 --splits ml/data/splits-v1 --baseline ml/artifacts/training-v1-final --output ml/artifacts/improvement-v2

# Download public training-only conservation annotations; requires network.
.venv/bin/python -m ml.conservation --splits ml/data/splits-v1 --output ml/data/conservation-training-v1

# Enriched training-only study.
.venv/bin/python -m ml.improve --dataset ml/data/clinvar-five-class-v1-rebuild --features ml/data/features-v1 --splits ml/data/splits-v1 --baseline ml/artifacts/training-v1-final --enrichment ml/data/conservation-training-v1 --config ml/config/conservation_study.json --output ml/artifacts/improvement-v3-conservation

# Train selected eligible candidate; preserves the active API model.
.venv/bin/python -m ml.refit_candidate --dataset ml/data/clinvar-five-class-v1-rebuild --features ml/data/features-v1 --splits ml/data/splits-v1 --study ml/artifacts/improvement-v3-conservation --enrichment ml/data/conservation-training-v1 --output ml/artifacts/conservation-candidate-v3

.venv/bin/python -m unittest discover -s ml/tests -v
```

No additional Python packages were installed for these studies. The downloader allows two concurrent requests, validates response regions and truncation, and retains completed responses so an interrupted download can resume. A completed cache refuses overwrite. Historical raw responses must be retained for exact reproduction because a live track can change.

## Verification

All 66 ML/backend tests passed. Tests cover fold-local class weights and conservation imputation, absent values, coordinate conversion, mismatched/truncated annotation responses, feature collisions, and refusing selection when a discrimination gate fails. The refit verified persisted-model prediction parity on 512 training probe rows. Study/candidate checksums and unchanged original model, policy, evaluation report, SHAP manifest, and access ledger were verified.
