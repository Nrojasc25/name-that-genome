# Machine Learning

## Phase 2 status: implemented for the published eight-gene snapshot

The real ClinVar dataset has been audited, checked against GRCh38, normalized with pinned bcftools, and exported without changing the source database. The target genes recorded by the import are **ACADM, ATP7B, CFTR, COL4A5, FBN1, GAA, PAH, and PKHD1**. Overlapping gene annotations also occur. This dataset does not cover all ClinVar or establish genome-wide performance.

### Real build results

| Category | Retained unique variants |
|---|---:|
| Benign | 863 |
| Likely benign | 9,545 |
| Uncertain | 9,686 |
| Likely pathogenic | 3,771 |
| Pathogenic | 4,523 |
| **Total** | **28,388** |

Source: 36,065 records in release **2026-09-13**. Excluded: **7,677**, with one final reason per record plus independent label/sequence/reference reasons. The eligible sequence records matched the reference; normalization found no duplicate groups or representation changes in this snapshot. Synthetic tests verify that non-normalized indels and disagreements are handled correctly when present.

Read [the real dataset audit](reports/data_audit.md), [detailed audit counts](reports/data_audit.json), and [the frozen build manifest](reports/dataset_manifest.json). These are real-data reports, unlike the optional Phase 1 label-policy examples.

### Install offline data tools

From the repository root, after backend setup:

```bash
.venv/bin/python -m pip install -r ml/requirements.txt
```

The tested environment is Python 3.12 on macOS. Use a compatible Linux/WSL environment for the offline normalization workflow if native Windows dependencies are unavailable. ML dependencies are separate from the API's runtime requirements.

### Reproduce Phase 2 from a clean checkout

Obtain `backend/data/variants.sqlite` from the [published snapshot](https://github.com/Nrojasc25/name-that-genome/releases/download/clinvar-data-v1/variants.sqlite), following the backend README. `ml/config/dataset.json` pins its SHA-256, release ID/version, GRCh38 assembly, maximum indel length, and reference identity. A changed snapshot fails the build instead of silently selecting a new release.

```bash
# Audit the selected source; no reference download required for this inventory.
.venv/bin/python -m ml.audit_data

# About 938 MB compressed / 3 GB unpacked; stored outside Git.
mkdir -p ml/data/reference
curl --fail --location https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/hg38.fa.gz --output ml/data/reference/hg38.fa.gz
.venv/bin/python -m ml.prepare_reference ml/data/reference/hg38.fa.gz

# Uses the indexed FASTA and its verified checksum manifest.
.venv/bin/python -m ml.build_dataset --reference ml/data/reference/hg38.fa --reference-manifest ml/data/reference/hg38.manifest.json --output ml/data/clinvar-five-class-v1

# Includes Phase 1 and tiny synthetic FASTA/SQLite normalization tests.
.venv/bin/python -m unittest discover -s ml/tests -v
```

When known, supply `--download-date YYYY-MM-DD` to `ml.prepare_reference`; do not guess an earlier download date. Preparation verifies the pinned official compressed MD5 and records compressed/uncompressed SHA-256 plus the FASTA index checksum. The initial local download occurred November 17, 2026. Reuse an already prepared reference instead of unpacking it again. Both reference preparation and dataset building refuse to overwrite existing output; use a fresh output directory for comparison builds.

### Selection and normalization policy

- Read only the configured source release and its ClinVar germline classification field. Ignore existing binary-oriented `dataset_member`/model tables in the source database.
- Accept primary GRCh38 chromosome aliases (`1`/`chr1`, `X`/`chrX`, `MT`/`chrM`) explicitly. Do not guess RefSeq aliases or lift between assemblies.
- Validate A/C/G/T alleles, positive 1-based positions, contig bounds, and REF sequence. Exclude symbolic, ambiguous, multiallelic, and unsupported source types with reasons.
- Run **bcftools 1.23.1 through pysam 0.24.0**, with reference validation and left alignment. Never swap alleles to repair a mismatch. Accept normalized simple SNVs and insertions/deletions of **1-49 bases**; exclude complex substitutions and larger indels.
- Check normalized duplicate groups even when some members have ineligible labels. Quarantine label disagreements. For consistent eligible duplicates, choose highest review stars, then lowest ClinVar variation ID, then record ID; retain all source/ClinVar IDs for traceability.
- Emit one representative per canonical assembly/chromosome/position/ref/alt key. Every source row is accounted for as a representative or an exclusion, including duplicate rows.
- Require at least 100 unique examples in each class as an initial feasibility gate. This does not prove that a gene-held-out split is feasible or that any model will perform well.

The reference/normalization procedure follows the [UCSC reference distribution and checksums](https://hgdownload.soe.ucsc.edu/goldenPath/hg38/bigZips/) and [bcftools normalization documentation](https://samtools.github.io/bcftools/bcftools#norm).

### Output files

Large/intermediate files live in ignored `ml/data/`; compact reports live in `ml/reports/` for review.

| File | Purpose |
|---|---|
| `variants.parquet` | One row per validated canonical variant, five-class target, gene/consequence annotations, and source IDs. |
| `exclusions.parquet` | Every excluded source row, original allele, normalized key when available, and explicit reasons. |
| `source_membership.parquet` | Every source row, original coordinates/classification/review stars, disposition, and representative linkage. |
| `data_audit.json` / `.md` | Filter counts, coverage, raw labels, review status, per-class gene/consequence counts, reference results, and limitations. |
| `dataset_manifest.json` | Checksums, source/reference metadata, policy/configuration, package versions, code fingerprints, command, output hashes, and gates. |

`label`/`class_id` are targets. Gene identity, clinical/reference metadata, coordinates, and IDs are not default predictor features. The manifest lists candidate feature columns separately from non-feature columns. Phase 3 must build a specific feature matrix rather than train on every exported column. No account/history data is exported, and no training/test split or model training occurs in Phase 2.

### Provenance limitations

Reproducibility starts from the **published SQLite snapshot**, whose checksum is pinned. Its upstream VCF URL, checksum, import time, and gene selection are retained, but the upstream file was not independently verified in this build. The original import script and original download date are unavailable. Therefore, exact reconstruction from the upstream VCF alone remains unverified; the import timestamp is not represented as a download timestamp.

### Completed in Phase 2

- [x] Audit the real selected ClinVar release and annotation coverage.
- [x] Pin the source snapshot, label policy, release, reference, and normalizer.
- [x] Check REF alleles and normalize supported sequence variants.
- [x] Exclude unsupported records and quarantine duplicate-label disagreements.
- [x] Export typed Parquet tables, row-level traceability, manifests, and real reports.
- [x] Verify all five classes meet the initial sample-support gate.
- [x] Test normalization, exclusions, source protection, checksum rejection, and reproducibility.
- [ ] Independently recover/verify the original upstream VCF import provenance (recorded limitation).
- [ ] Phase 3: enrich annotations and implement the shared feature pipeline.

---

## Phase 1 status: implemented

The five-class contract and exact ClinVar label policy are implemented. No trained model is connected; new analyses still return `prediction_status: not_available` and `prediction: null`.

### Class order and policy

Stable class IDs are 0 = benign, 1 = likely_benign, 2 = uncertain, 3 = likely_pathogenic, 4 = pathogenic. `ml/config/labels.json` records policy version 1.0.0 and the explicit accepted labels. `ml/labels.py` is the shared Python enum and eligibility function.

Only exact eligible germline labels with integer review stars from 1 through 4 are included. Normalization accepts case changes, whitespace, and ClinVar VCF underscore-encoded spaces. Combined labels, conflicts, missing labels, unsupported terms, non-germline classifications, and insufficient/invalid review stars have explicit exclusion reasons. Unknown labels are never guessed. An exclusion reports the first failing rule: classification type, label validity/mapping, then review stars.

These are label eligibility checks only. Full-database counts, source freezing, allele normalization, duplicate resolution, and assembly/type filtering belong to Phase 2. No training eligibility is asserted for a variant solely because its label passes.

### Run checks and reproduce the example report

From the repository root after the backend environment setup:

```bash
.venv/bin/python -m unittest discover -s ml/tests -v
.venv/bin/python -m ml.label_report ml/tests/fixtures/label_examples.jsonl ml/reports/label_policy_examples.json
```

On Windows, replace `.venv/bin/python` with `.venv\Scripts\python.exe`.

The report uses **synthetic examples**, not counts from the ClinVar database. It contains per-class counts, exclusion counts, and a row-level reason for every excluded example. To apply the policy to another JSONL file, supply `classification`, `review_stars`, and optionally `record_id` and `classification_type` (defaults to `germline`; callers must identify other classification types explicitly).

### Versioned application contract

`backend/prediction.py` defines schema version 2. New predictions require all five `class_scores`, each finite and between 0 and 1, with a total within 1e-6 of one. `decision` must select the highest score; exact ties use the class order above. Model, dataset, annotation, and feature-schema versions are required. `confidence_status` is `not_assessed`, `low`, or `standard`; it is separate from the learned `uncertain` category.

SHAP explanations specify any of the five classes as `output_target`. Positive contributions increase that target's stated output, rather than always indicating greater pathogenicity. Additivity verification and actual SHAP computation are future implementation work.

Legacy unversioned/1 predictions retain their saved `pathogenic_probability`. Response parsing identifies them as version 1 without filling in nonexistent class scores or rewriting stored JSON. The frontend supports both contracts and uses class-specific explanation text. Synthetic response examples for all five classes live in `ml/tests/fixtures/predictions.json`; they are not real model outputs.

### Completed in Phase 1

- [x] Versioned label configuration and stable five-class enum/order.
- [x] Exact mapping and deterministic exclusion reasons.
- [x] Reproducible synthetic label-policy report.
- [x] Version 2 backend/frontend prediction contracts and five-score validation.
- [x] Legacy saved-result compatibility without invented scores.
- [x] Minimal results rendering for the new contract and class-specific SHAP targets.
- [x] Label, contract, and isolated SQLite history tests.
- [x] Full implementation plan copied below; original PDF remains the planning snapshot.
- [x] Phase 2: audit the actual ClinVar dataset and freeze the training source (see status above).

---

The full plan below retains the November 12, 2026 implementation sequence, with its status and final checklist updated after Phase 2. The original PDF remains the initial planning snapshot.

# Name That Genome - ML Implementation Plan

## Objective

Build and integrate a reproducible five-category genetic variant classifier using ClinVar labels and SHAP explanations. The application will accept a supported variant, create biological features, predict a category, explain that prediction, and save the result with its model and data versions.

The five user-facing categories are **Benign, Likely benign, Pathogenic, Likely pathogenic, and Uncertain**. This replaces the earlier binary-training proposal. Likely benign and likely pathogenic remain distinct training labels; uncertain significance is included as its own supervised class.

**Planning baseline:** November 12, 2026. The original foundation was established by repository inspection. Phase 1 label/contract and isolated history tests now pass, as do the frontend build and lint checks. Model training and full end-to-end inference testing remain future work.

## Target behavior

| Area | Required behavior |
| --- | --- |
| Input | ClinVar variation ID or exact stored GRCh38 genomic HGVS, matching current lookup support. |
| Prediction | One of the five categories and a score distribution covering all five. |
| Explanation | SHAP contributions for a named class and explicitly stated output space. |
| Disease context | ClinVar-associated conditions displayed as reference annotations. |
| Persistence | Save the original prediction, explanation, and provenance with the analysis. |
| Failure | Explain invalid, unsupported, missing-data, or unavailable-model states without inventing a category. |

## Scope and interpretation

The first model predicts ClinVar-style germline classification from available features. Its outputs estimate learned label membership; they are not a clinical determination or a patient's probability of disease. A VUS label reflects unresolved evidence, so its predictability must be measured rather than assumed.

Begin with supported single-nucleotide variants and small sequence-resolved insertions/deletions. Define and record the maximum indel size after the data audit. Structural variants, complex alleles, transcript-only HGVS, and patient-level diagnosis are outside the initial model's supported scope.

The existing disease-shortlist ambition remains a separate extension: a five-category classifier alone cannot rank diseases. Finish the classifier and reference-condition display first; disease ranking needs its own labels and validation.

---

# Existing foundation and proposed architecture

## Reuse the current application

| Existing source | Reuse | Required ML change |
| --- | --- | --- |
| backend/database.py | Read-only ClinVar lookup, coordinates, consequences, genes, and conditions. | Resolve a supported GRCh38 record deterministically and attach versioned features. |
| backend/main.py | Analysis endpoint and prediction hook. | Replace the empty hook; expand three decisions to five; revise scores and SHAP target. |
| backend/app_database.py | JSON analysis snapshots and user-owned history. | Store a schema version and complete prediction provenance. |
| frontend/src/lib/analysis.ts | Shared result types. | Add a strict five-class union and per-class scores. |
| frontend/src/pages/Results.tsx | Reference and prediction sections. | Render five categories, class-specific explanations, and quality states. |
| ml/README.md | Placeholder ML directory. | Add implementation, reproducibility instructions, and model documentation. |

## Proposed code organization

```text
ml/
  config/                 # label, feature, split, and training settings
  audit_data.py           # source inventory and quality report
  build_dataset.py        # release selection, normalization, labels
  annotate.py             # versioned external annotation/cache
  features.py             # shared training and inference transforms
  split_data.py            # frozen split manifests and overlap checks
  train.py                # baseline and five-class candidate training
  evaluate.py             # held-out metrics, calibration, error analysis
  explain.py              # class-specific SHAP adapter and checks
  inference.py            # artifact loading and one-variant prediction
  tests/                  # label, leakage, inference, explanation tests
  reports/                # small reviewable reports and model card
  artifacts/              # ignored local downloads; versioned externally
```

Training runs offline. The API loads an approved artifact bundle once at startup and runs inference through the same feature schema used in training. Annotation lookups should use a versioned local cache so results do not silently change with live external services.

**Exit criteria:** each module has a defined responsibility; API and frontend agree on the five-class contract; no model-training job runs inside an HTTP request.

---

# Phase 1 - Define five-class labels

## Canonical label map

Use this immutable model class order. Store it in every model artifact; never assume a library returns classes in this order without checking.

| ID | API key | Display name | Accepted primary ClinVar label |
| --- | --- | --- | --- |
| 0 | benign | Benign | Benign |
| 1 | likely_benign | Likely benign | Likely benign |
| 2 | uncertain | Uncertain | Uncertain significance |
| 3 | likely_pathogenic | Likely pathogenic | Likely pathogenic |
| 4 | pathogenic | Pathogenic | Pathogenic |

## Implement explicit inclusion rules

- Use germline classification only. Keep somatic clinical impact and oncogenicity out of this target. ClinVar documents these as distinct classification types [1].
- Normalize whitespace and documented input encoding, then use an explicit mapping. Do not use substring rules: “likely pathogenic” must not accidentally become “pathogenic.”
- Exclude combined labels such as “Benign/Likely benign” and “Pathogenic/Likely pathogenic” from the primary exact-five-class benchmark. They do not identify one exact class. Record them in the exclusion report for possible later partial-label research.
- Exclude conflicting classifications, missing labels, risk factors, drug response, association labels, and unsupported terms. Do not turn those into Uncertain.
- Begin with records with at least one review star and an eligible exact label. Report counts for every class and run a stricter review-status sensitivity analysis. Review stars guide filtering; they are not model features or probabilities [2].
- Select one normalized variant per frozen release. Resolve duplicate records deterministically; quarantine disagreements rather than choosing the most severe label.

## Separate two meanings of uncertainty

**Predicted Uncertain:** the classifier selects the class learned from eligible ClinVar uncertain-significance records.

**Low model confidence:** a separate quality flag derived from validation, such as a small top-two score margin. It must not silently overwrite another predicted class with Uncertain. Unsupported inputs receive no prediction, not a sixth biological class.

**Deliverables:** label configuration, exclusion-reason report, examples of every mapping, and tests covering exact, combined, conflicting, and missing labels. **Exit:** every included row maps to exactly one of five classes and every rejected row has an auditable reason.

---

# Phase 2 - Audit, freeze, and normalize ClinVar

## Work to implement

1. Open variants.sqlite read-only. Inventory source releases, tables, assembly values, label strings, review status, variant types, and annotation coverage. Count distinct normalized variants as well as records.
2. Produce per-class counts before and after every filter. Include class-by-gene and class-by-consequence summaries, missingness, duplicates, and unsupported sequence representations.
3. Select a specific ClinVar release and GRCh38 reference version. Record original source URLs, download date, checksum, import procedure, and label-policy version in a manifest. Do not equate the application's database download date with the ClinVar release date.
4. Validate chromosome naming, reference alleles, coordinates, and assembly. Normalize sequence-resolved alleles with a pinned tool and reference FASTA; left-align and trim indels consistently. Retain original identifiers for traceability.
5. Define how multi-allelic and complex records are handled. Split only when labels can be safely assigned to the individual allele; otherwise exclude with a reason.
6. Deduplicate by assembly, chromosome, normalized position, reference, and alternate allele. Keep alternate IDs linked to the same canonical key. Choose the release explicitly rather than relying on unverified lexical date sorting.
7. Export a training table and manifest with checksums. Keep labels, reference conditions, and provenance separate from the feature allowlist. Never export account or analysis-history data as training data.

## Dataset outputs

| Output | Contents |
| --- | --- |
| dataset_manifest.json | Source and reference versions, checksums, filters, class order, build command. |
| variants.parquet | Canonical variant keys, allowed annotations, target label, traceability fields. |
| exclusions.parquet | Rejected record keys and explicit reasons. |
| data_audit.md | Counts, coverage, duplicates, class balance, and unresolved data issues. |

Large tables and reference files belong in ignored local storage or a versioned artifact release, not ordinary Git commits. Commit the build scripts, configurations, small fixtures, and compact audit report.

**Exit criteria:** a clean environment can recreate the dataset from documented sources; reference alleles validate; no duplicated canonical keys remain; all five classes have enough independent examples for the planned splits. If a class is too small, revise scope or collect more eligible data before claiming five-class validation.

---

# Phase 3 - Build biological features

## Start with an explicit feature allowlist

| Feature group | Initial implementation | Follow-up enrichment |
| --- | --- | --- |
| Sequence change | Variant type, ref/alt lengths, length difference, SNV substitution type. | Local reference sequence context where justified. |
| Consequence | Versioned molecular-consequence indicators. | Consistent transcript, splice-region, and protein-change annotations. |
| Population evidence | Audit availability; preserve missingness. | Versioned population allele frequencies with population and coverage context. |
| Conservation | Audit availability; preserve missingness. | Selected conservation measurements with documented source and assembly. |
| Protein context | Only reliably available annotations. | Amino-acid change and physicochemical descriptors for relevant variants. |

## Annotation and preprocessing tasks

- Choose a pinned annotation workflow, such as Ensembl VEP, after checking supported assembly, cache availability, license, and storage requirements. Record its transcript-selection policy; do not choose a transcript using the target label.
- Preserve missing values and missingness indicators. An unavailable allele frequency is not a measured frequency of zero. Define separate handling for nonapplicable protein features.
- Fit imputers and categorical encoders on training folds only. Handle unseen categories deterministically. Persist the exact feature names, order, types, transformations, and schema version.
- Use one feature-builder entry point for training and API inference. Validate that identical normalized variants and source versions produce identical vectors.
- Keep ClinVar classification, conditions, review status/stars, submission metadata, dates, and record IDs outside the feature matrix. Coordinates are join keys by default, not prediction shortcuts.
- Keep gene identity out of the initial baseline. If later introduced, compare with and without it and report performance on unseen genes.
- Treat existing pathogenicity scores as optional later experiments. Audit their training-source overlap with ClinVar and compare performance without them to expose circularity.

## Deliverables and gate

Deliver the annotation cache builder, feature dictionary, missingness report, and transformation tests. Each dictionary entry must specify source, biological meaning, units, missing-value policy, and inference availability.

**Exit criteria:** no disallowed label-derived columns enter training; annotated coverage is reported for every class; a feature vector can be recreated independently of the target label; a test variant produces the same vector through batch and single-variant paths.

---

# Phase 4 - Split data and train five-class models

## Freeze evaluation partitions first

Use a proposed 70% training / 15% validation / 15% untouched test allocation, adjusted only before model selection if class support requires it. Stratify across the five classes while grouping all representations of the same normalized variant. Save the exact split membership and seed.

Perform hyperparameter search using grouped folds within the training partition. Use the validation partition for a fixed calibration procedure and confidence-rule selection. Keep final test labels out of tuning, preprocessing, resampling, and SHAP background selection.

Add a separate gene-held-out challenge set. Multi-gene variants require grouping connected gene sets or exclusion from that challenge; otherwise the same gene can leak across groups. If historical releases exist, add a temporal evaluation using variants first seen later, with labels and annotations frozen to the intended cutoff.

## Train in increasing complexity

1. **Dummy baseline:** class-prior or majority-class predictions. This reveals misleading overall accuracy caused by imbalance.
2. **Multinomial logistic regression:** a reproducible, regularized five-class baseline using the shared preprocessing pipeline.
3. **Gradient-boosted trees:** evaluate a multiclass XGBoost candidate with five output classes and a bounded parameter search. Pin compatible Python and package versions, especially the model/SHAP combination.
4. **Class imbalance:** compare weighted and unweighted training. Calculate weights inside training folds. Never balance validation/test data artificially; report their actual distribution.
5. **Selection:** choose using cross-validated macro-F1 and per-class behavior, with log loss and inference cost as additional criteria. Compare against both baselines before increasing model complexity.

Do not train a binary score and divide it into five arbitrary intervals. “Likely” categories must come from the five-class target. Do not treat numeric class IDs as a regression scale: uncertain significance is an evidence state, not a numerical midpoint of biological damage.

**Deliverables:** split manifests, overlap report, experiment table, training configuration, candidate model artifacts, environment lock, and random seeds.

**Exit criteria:** all five classes appear in evaluation with disclosed support; no canonical-variant overlap exists; training is repeatable; the selected candidate's improvements and limitations are documented. Do not relax the benchmark after seeing test results.

---

# Phase 5 - Evaluate, calibrate, and set quality rules

## Required evaluation report

| Evaluation | What it must show |
| --- | --- |
| Five-class confusion matrix | Raw counts and row-normalized values; adjacent and opposite-category mistakes. |
| Per-class precision, recall, F1 | Separate results and sample support for all five classes, including Uncertain. |
| Macro-F1 and balanced accuracy | Performance that does not hide weaker classes behind the largest class. |
| One-vs-rest PR-AUC | Class-specific discrimination with each class's prevalence stated. |
| Multiclass log loss / Brier score | Quality of the full five-class distribution. |
| Calibration plots | Per-class predicted membership versus observed label frequency. |
| Subgroup analysis | Variant type, consequence, missingness, review-status subset, and unseen genes. |

Estimate uncertainty in reported metrics using bootstrap resampling at the appropriate variant or gene group level. Inspect examples of benign-to-pathogenic and pathogenic-to-benign mistakes, VUS confusion, and likely-versus-definite confusion.

## Calibration and decision policy

Compare uncalibrated outputs with a validation-fitted multiclass calibration method, such as temperature scaling on logits. Preserve five nonnegative probabilities summing to one. Retain calibration only if the predefined validation assessment supports it.

The primary decision is the highest-scoring class. Define deterministic tie handling. Evaluate a separate low-confidence flag using top-class confidence or the top-two margin; choose the rule before final testing. The flag does not turn an otherwise selected label into Uncertain.

Set probability_kind to calibrated only for an artifact whose calibration was evaluated. Otherwise display model scores. Even calibrated label probabilities do not represent a patient's disease probability or establish a clinical “likely” threshold.

## Acceptance gate

Before final test evaluation, record numeric acceptance targets in the evaluation configuration: macro-F1 improvement over baseline, minimum per-class recall, acceptable severe-confusion rate, calibration criteria, and inference latency on a named machine. Set realistic targets after the training/validation audit, not by inventing performance numbers now.

**Exit criteria:** the untouched test report is generated once for the selected release candidate; failures are disclosed. If the model fails an acceptance target, revise and version the experiment with an honest test-reuse statement or obtain a new holdout. Ship no unsupported performance claim.

---

# Phase 6 - Implement class-specific SHAP

## Explanation contract

Use SHAP to explain a named model output. The default explanation targets the selected class; optionally allow the user to inspect another class. Replace the existing fixed pathogenic target with the same five-class enum used by the classifier.

Each explanation contains the target class, baseline, explained value, output space, feature values, and signed contributions. Include the model version and background-data version. A positive contribution increases that class's explained output; it does not always mean “more pathogenic.”

## Implementation sequence

1. Run a small compatibility experiment with the pinned multiclass tree model and SHAP version before building the UI. Verify class-index alignment, output dimensions, and unsupported settings.
2. Create and version a representative background sample from training data only. Record how it was sampled and which feature representation it uses.
3. Prefer TreeExplainer for a supported tree output. For multiclass models, raw outputs may be class margins/logits; label them raw_score rather than assuming binary log-odds [3].
4. For each of the five classes, test that baseline plus the full contribution sum reconstructs the same class output within a documented tolerance. Test shapes, finite values, sign direction, and class order on multiple examples.
5. If calibration is external to the tree, choose explicitly: explain the original class margin and label it clearly, or use a suitable explainer for the complete calibrated predictor. Tree explanations do not automatically explain a separate calibration transform.
6. Combine one-hot contributions into readable original feature groups by addition. Show the largest positive and negative effects and an “Other features” remainder so the visible values retain their total.
7. Generate a local waterfall/bar view and global per-class summary plots on evaluation data. Review surprising reliance on missingness or annotation artifacts before release.

## Frontend language

Example heading: “Features influencing the Likely pathogenic model output.” State the output space next to the plot. If displaying a calibrated probability with an explanation of the underlying margin, explicitly identify the two quantities; do not imply that margin contributions add to the probability.

SHAP describes model behavior relative to a background dataset, not a causal biological mechanism. Correlated features may share attribution.

**Exit criteria:** all five class explanations pass additivity and class-mapping checks, grouped displays preserve sums, and measured explanation latency fits the agreed application budget.

---

# Phase 7 - API, UI, and saved history

## Version the response contract

Replace the existing single pathogenic_probability field in the new schema with a class_scores map containing exactly benign, likely_benign, uncertain, likely_pathogenic, and pathogenic. Keep probability_kind to distinguish calibrated probabilities from uncalibrated model scores. Both distributions must be finite, nonnegative, and sum to one within tolerance.

Add decision, confidence_status, schema_version, model_name, model_version, feature_schema_version, annotation_version, and dataset_version. Explanations identify output_target using the five-class enum. Store the raw SHAP feature data required to reproduce the displayed chart.

## Backend implementation

- Implement ml/inference.py and connect backend/main.py's predict_variant hook. Load only trusted, checksum-verified artifacts once; validate class order, package compatibility, and feature schema at startup.
- Select the correct supported assembly/release record. Apply normalization and annotation using the artifact's versions. Keep this path consistent with offline evaluation.
- Distinguish an unknown variant, unsupported type, missing essential features, model load failure, and explanation failure. Preserve the existing not_available path with a structured reason; never return fabricated scores.
- If prediction succeeds but SHAP fails, retain the valid prediction with explanation=null and an explanation status. Do not fabricate contributions or silently describe a missing explanation as complete.
- Record latency for lookup, features, prediction, and explanation; cache by normalized variant plus all relevant versions. Bound memory use and concurrent explanation work.

## Frontend and history implementation

- Update the TypeScript types and results screen for all five labels and the complete class distribution. Explain Uncertain versus low model confidence in plain language.
- Render SHAP contributions with text labels, keyboard-accessible details, and signs; do not rely on color alone. Keep ClinVar conditions/classification in the reference section.
- Store new analysis payloads as snapshots. Add a version-aware reader for older three-decision payloads; never invent missing likely-class probabilities or recompute saved results silently.
- Update relevant README/API documentation and About-page wording to match what is implemented. Keep hardcoded demo results explicitly marked as examples.

**Exit criteria:** validated fixtures for every class render and round-trip through saved history; real supported inputs run through the integrated model; legacy results remain readable; missing-model and failed-explanation paths behave correctly.

---

# Delivery sequence and completion gates

## Proposed eight-week working schedule

This is a sequencing estimate, not a committed deadline. Annotation setup, class coverage, team capacity, and compute availability may extend it. Finish the evidence gates before moving a model toward release.

| Window | Deliver | Exit criteria |
| --- | --- | --- |
| Week 1 | Five-class contract, data audit, labels, source manifest. | Exact label policy reviewed; class counts and exclusions known. |
| Week 2 | Normalization, feature schema, annotation prototype. | Batch and single-variant features agree; coverage measured. |
| Week 3 | Frozen splits, dummy/logistic baselines. | No variant leakage; repeatable five-class baseline report. |
| Week 4 | Tree candidates and bounded tuning. | Candidate selected on training/validation evidence. |
| Week 5 | Calibration, quality rules, final test report. | Predefined evaluation targets assessed; limitations recorded. |
| Week 6 | Class-specific SHAP, global/local plots. | All-class additivity, mapping, and latency checks pass. |
| Week 7 | API integration, result UI, history compatibility. | Five-category end-to-end workflow and failure paths pass. |
| Week 8 | Artifact packaging, documentation, regression checks, demo. | Clean setup reproduces the release and saved analyses. |

## Required validation

Test label normalization, duplicate grouping, reference mismatches, train/test isolation, unknown categories, missing values, class ordering, score normalization, artifact load/reload, and per-class SHAP additivity. Include contract tests and integration tests for saved snapshots and access control around analyses.

Use synthetic fixtures to test that every UI label and failure state is handled. Use held-out real variants for model evaluation; do not force the model to produce every label merely to make a demo look complete. Run the frontend build/lint checks and relevant backend/ML tests before merging integration work.

## Definition of complete

The five-class model, reproducible data/feature pipeline, held-out evaluation, verified explanations, API integration, and history-compatible UI are implemented. A model card records scope, class counts, sources, package versions, metrics, failure cases, and intended use. A clean checkout can fetch verified artifacts and run the demo from documented commands.

Clinical deployment, disease-ranking validation, new-variant annotation outside the current database, and production hosting operations are separate milestones. They must not be described as completed by finishing this classifier.

---

# Risks, extension scope, and references

## Major risks and mitigations

| Risk | Planned mitigation |
| --- | --- |
| Definite versus likely labels depend on evidence absent from features. | Report exact-class confusion and limits; do not conceal weak classes by merging labels. |
| Uncertain is heterogeneous and can dominate counts. | Retain VUS as its own target; show per-class metrics and examine missingness shortcuts. |
| Annotation or ClinVar overlap leaks labels. | Enforce a feature allowlist, freeze source versions, audit external predictor provenance. |
| Duplicate variants or related genes inflate performance. | Normalize and group variants; add a correctly isolated gene-held-out evaluation. |
| Too few clean examples in a class. | Report support early; expand eligible data or narrow supported scope before training claims. |
| SHAP explains a different quantity than the UI implies. | Verify output space and class mapping; separate calibrated scores from raw-margin explanations. |
| Training and serving diverge. | Share transformations, pin artifacts, validate schema/checksums, test vector equivalence. |
| Data/model updates alter old analyses. | Save snapshots and versions; evaluate each new release separately. |

## Disease-shortlist extension

For the initial release, show only source-associated conditions and identifiers as ClinVar reference information. Do not rank these by a shared pathogenicity score or describe them as independently predicted diseases.

A future ranker needs a candidate-generation policy, normalized disease identifiers, variant-disease examples, treatment of missing associations, and held-out ranking metrics such as recall@k. Missing associations are not automatically negatives. Phenotype, inheritance, and zygosity may require new inputs. A disease explanation must target a disease-specific score, not reuse a five-class SHAP plot.

## Sources and planning basis

The attached Driver App Rewrite Plan was used for document structure: objective, sources, implementation phases, deliverables, exit criteria, timeline, risks, and completion criteria. Its Driver-app instructions are not requirements for this project.

[1] NCBI, Representation of classifications in ClinVar. Germline label semantics and aggregate classification rules. https://www.ncbi.nlm.nih.gov/clinvar/docs/clinsig/

[2] NCBI, Review status in ClinVar. Review-status interpretation and star levels. https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/

[3] SHAP, TreeExplainer API reference. Supported outputs, background data, and explanation behavior. https://shap.readthedocs.io/en/stable/generated/shap.TreeExplainer.html

Sources checked November 12, 2026. Model choice, split percentages, branch names, and schedule are project recommendations. Dependency compatibility and numeric acceptance targets must be verified during implementation.

---

# GitHub branch outline

## Proposed branches and ownership boundaries

Create short-lived branches from updated main after their dependencies merge. Open one focused PR per branch; split an oversized phase into smaller PRs. The names below are proposals, not branches created by this document.

| Branch | What belongs on it | Depends on |
| --- | --- | --- |
| docs/ml-plan | This plan, scope, milestones, acceptance checklist. | Current main |
| feat/ml-five-class-contract | Label enum, versioned API/TS types, five-score fixtures, legacy payload compatibility. | Plan |
| feat/ml-clinvar-dataset | Audit, source manifest, normalization, exact label rules, exclusions, dataset tests. | Plan + class enum |
| feat/ml-feature-pipeline | Annotation workflow/cache, feature dictionary, shared transforms, missingness tests. | Dataset |
| feat/ml-training | Frozen splits, overlap checks, dummy/logistic/tree models, experiment configs. | Features |
| feat/ml-evaluation | Metrics, calibration, confidence flags, error analysis, candidate model card. | Training |
| feat/ml-shap | Multiclass explainer, background manifest, additivity checks, grouped features. | Selected model + contract |
| feat/ml-api-inference | Startup loading, inference hook, provenance, failure states, snapshot integration. | Evaluation + SHAP + contract |
| feat/ml-results-ui | Five-label results, class distribution, SHAP chart, confidence copy, reference conditions. | Contract; final checks need API |
| test/ml-end-to-end | Workflow/regression tests, legacy history, failure paths, performance measurements. | API + UI |
| chore/ml-release | Dependency lock, verified artifact packaging, clean setup, final model card and demo docs. | End-to-end + accepted metrics |

## Merge and collaboration rules

The main dependency chain is dataset -> features -> training -> evaluation -> SHAP -> API -> end-to-end -> release. The response contract comes early so UI work can proceed against realistic fixtures while ML work continues. Final UI acceptance requires the real API.

Keep main runnable: merge the new contract with unavailable-model handling before inference is ready. Shared enum/schema changes belong to the contract PR. Keep raw datasets, model binaries, account data, caches, and credentials out of Git; use checksummed release artifacts for large outputs.

Each PR states its behavior change, dependencies, commands run, relevant evidence, and remaining limitations. Model PRs include data/split versions and measured results; explanation PRs include output-space and additivity evidence. Existing local branches are not renamed or deleted by this plan.

---

# Final checklist - completed and remaining

## Already present or completed

Existing application features below were identified by repository inspection. Phase 1 validation covers labels, score contracts, isolated SQLite history, frontend compilation, and lint; it does not establish accuracy of a future model.

- [x] React/TypeScript frontend and FastAPI backend are present.
- [x] dev.py provides a combined local development launcher.
- [x] A local variants.sqlite database is present; its ML suitability still needs auditing.
- [x] ClinVar ID and stored GRCh38 genomic HGVS lookup are implemented in backend/database.py.
- [x] Lookup returns reference coordinates, genes, consequences, classification, conditions, and source metadata.
- [x] Account/session handling and per-user JSON analysis history are implemented.
- [x] The analysis endpoint calls a dedicated predict_variant hook; the hook currently returns None.
- [x] Results UI separates ClinVar reference annotations from model output.
- [x] Version 2 prediction/SHAP schemas and minimal results UI support all five classes, with legacy snapshot compatibility.
- [x] Five required categories are confirmed by the user and documented in this plan.
- [x] Implementation phases, deliverables, validation gates, proposed GitHub branches, and this status checklist are documented.

## Remaining implementation checklist

- [x] Expand and version the API/frontend contract for five classes and legacy history.
- [x] Implement exact label rules, exclusion reasons, synthetic reports, and Phase 1 tests.
- [x] Audit and freeze the published ClinVar SQLite snapshot; validate normalization and exact label rules. Upstream import-provenance limitations are documented above.
- [ ] Build the annotation cache and shared feature pipeline; verify leakage exclusions.
- [ ] Freeze grouped splits and document class coverage and overlap checks.
- [ ] Train and compare dummy, multinomial, and tree candidates.
- [ ] Evaluate every class, calibrate if justified, and define confidence flags.
- [ ] Record numeric acceptance targets and complete the untouched test report.
- [ ] Implement and verify all five class-specific SHAP explanations.
- [ ] Package/version trusted artifacts and connect live API inference.
- [ ] Build five-category results, class-score display, and readable SHAP charts.
- [ ] Verify saved snapshots, old results, unsupported inputs, and failure states.
- [ ] Complete regression checks, latency measurement, model card, and clean setup demo.

**Current milestone:** Phase 2 implemented and validated for the published eight-gene snapshot. Next: Phase 3 annotation enrichment and feature engineering. No trained model, benchmark score, calibrated probability system, or live SHAP inference has been claimed as completed.
