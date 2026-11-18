# Work toward greater than 90% accuracy

**The 90% target has not been achieved.** This round added transcript/protein and modern population-frequency features, ran two bounded training studies, and reserved a newer-release evaluation cohort. The best ordinary training out-of-fold accuracy was **79.19%**. No new model was approved, deployed, or claimed to perform at 90% on unseen data.

## Definition of the target

`config/accuracy_target.json` defines strictly greater than 0.90 ordinary accuracy: the number of correct five-class argmax predictions divided by **all eligible evaluation rows**. Scores are not filtered by confidence and classes are not merged. Accuracy is separate from macro-F1. The original per-class recall and severe-confusion requirements remain; calibration, confidence, latency, baselines, and gene challenge remain additional release requirements.

Training OOF scores are development/selection estimates. They do not establish the target on unseen data, especially after multiple experiments informed by previous results. No blind test was scored in this round.

## Locked new-release cohort

The public [NCBI ClinVar GRCh38 2026-11-15 release](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/) was downloaded and checked against its supplied MD5, with SHA-256 recorded locally. Before the new training studies, `ml.lock_cohort` froze all eligible variants within the original eight-gene scope after excluding:

- Every variant ID and allele ID present in the original source database, including previously excluded records.
- Overlapping original genomic reference spans/loci, regardless of alternate allele.
- Previously used normalized keys and overlapping normalized loci after reference validation and bcftools normalization.

The existing exact-label/review policy, GRCh38 reference checks, and sequence-type restrictions were retained. This is a temporal new-variant cohort in known genes, not an unseen-gene or prospective clinical cohort.

| Class | Reserved variants |
|---|---:|
| Benign | 1 |
| Likely benign | 94 |
| Uncertain | 175 |
| Likely pathogenic | 79 |
| Pathogenic | 66 |
| Total | 415 |

The cohort is **too small in several classes**, particularly Benign, to satisfy the predeclared 100-per-class support requirement. It must not support an unrestricted five-class acceptance claim. The row-level labels stay in ignored `ml/data/locked-temporal-v4/labels.sealed.json`, separate from the variant list; no prediction has been made on this cohort. Sealing is a workflow convention rather than encryption. Counts and eligibility were inspected during reservation, but row-level labels are not used by training. Training checks the locked manifest/content hashes before running. See [cohort provenance](reports/locked_temporal_cohort_manifest.json).

## Added information

### Transcript/protein study (v4)

`ml/protein_features.py` derives 50 fixed numeric features from UCSC's `ncbiRefSeqCurated` track and the pinned local GRCh38 FASTA: normalized coding position, geometric distance to an internal exon boundary, reference/alternate amino-acid indicators, synonymous/stop-gain/stop-loss flags, and explicit missingness indicators.

The transcript policy chooses an overlapping complete-CDS `NM_` transcript with the longest spliced coding sequence, then accession order. It does not choose by clinical label, annotation severity, or gene identifier and does not claim MANE/canonical status. Exons are spliced, minus strands reverse-complemented, and reference alleles verified before translating coding SNVs. Indels and unsuitable CDS/reference combinations retain missing coding features. Splice distance is not a splice-effect prediction. No protein-domain or biochemical-property features are claimed.

There are 16,491 training variants with a selected transcript and 10,770 with coding-SNV features. An Ensembl VEP request timed out; this experiment uses the frozen UCSC RefSeq source instead. The feature/schema/source manifest is [here](reports/protein_feature_manifest.json). [UCSC API documentation](https://genome.ucsc.edu/goldenPath/help/api.html) describes the annotation retrieval interface.

### Population-frequency study (v5)

`ml/population_features.py` adds eight columns from UCSC's [gnomAD v4.1.1 tracks](https://genome.ucsc.edu/cgi-bin/hgTrackUi?db=hg38&g=gnomadVariantsV4.1): overall and ancestry-group maximum AF for genomes and exomes, each with a missingness indicator. Only exact GRCh38 SNV allele matches with `FILTER=PASS`, finite frequencies in [0,1], and positive allele-number denominators are used. Indels remain unsupported by this experimental join.

The frozen training cache supplies overall exome frequencies for 6,602 rows and genome frequencies for 3,528 rows. Unmatched, failed-filter, conflicting, and unavailable values are missing—not evidence of absence from a population. Numeric missing fills are zero with an explicit missing flag; a measured zero has the flag unset. Other source fields, such as genes, consequence labels, IDs, and annotations, do not enter the numeric features. No CADD, REVEL, AlphaMissense, PolyPhen, SIFT, or other pathogenicity predictor is used. See [population provenance](reports/population_feature_manifest.json).

Raw responses are checksummed, retained under ignored `ml/data/`, and used offline for training. A versioned live annotation/serving pipeline has not yet been built for these experimental columns.

## Results and tradeoffs

All results below use the same 16,500 training rows and three frozen CV folds. Original-feature imputation and conservation median imputation fit only the fit rows of each fold. No validation/test/challenge labels were loaded by the training studies. The baseline replay matches historical OOF predictions exactly.

| Configuration | Ordinary accuracy | Macro-F1 | Likely pathogenic recall |
|---|---:|---:|---:|
| Original 42-feature candidate | 74.77% | 0.6405 | 9.6% |
| Previous selected conservation candidate | 74.24% | 0.6743 | 40.4% |
| Protein study's highest accuracy (depth 5, unweighted) | 78.90% | 0.7130 | 32.3% |
| Population study's highest accuracy (depth 5, unweighted) | 79.19% | 0.7263 | 32.0% |
| Population depth 5, Likely pathogenic weight 1.5× | 78.84% | 0.7314 | 42.3% |

The last configuration meets the original discrimination thresholds on these selection estimates, but misses the new accuracy requirement. The highest-accuracy configuration also fails Likely pathogenic recall. **No configuration passes the 90% selection requirement**, so none is selected or refitted for promotion. The improvements are useful evidence, not a finished 90%-accurate classifier.

Full fold/class/confusion results: [protein study](reports/v4_improvement_report.md), [population study](reports/v5_improvement_report.md), and [machine-readable goal status](reports/accuracy_goal_status.json). Weighting one class more heavily shifts mistakes elsewhere; the reports retain those tradeoffs. Calibration was not used as a way to claim improved class accuracy.

## What remains

A larger independent cohort with adequate support across all five classes is necessary for a credible acceptance test. Do not reshuffle old variants, filter to easy predictions, or merge labels to claim 90%. The 415 reserved variants can remain a future diagnostic cohort, but do not resolve the support limitation.

Further work needs a separately planned data-expansion and label-quality audit, including how much likely-versus-definite classification depends on clinical evidence absent from these features. Additional annotation may help, but this round does not establish that the chosen five-class task can reach 90% with the available inputs. No numeric outcome is guaranteed by further tuning.

Before any replacement model is used in the app, freeze and assess its calibration/confidence policy, evaluate it independently, implement its exact feature contract in serving, regenerate SHAP for that model, and rerun integration checks. The current API model, SHAP artifacts, old evaluation report, and consumed-test ledger remain unchanged.

## Reproduction and verification

The protocol files are `config/accuracy_target.json`, `config/protein_study.json`, and `config/population_study.json`. Completed output directories refuse overwrite. Downloads require network; model training reads frozen local files only.

```bash
.venv/bin/python -m ml.lock_cohort --vcf ml/data/clinvar-20261115/clinvar_20261115.vcf.gz --checksum ml/data/clinvar-20261115/clinvar_20261115.vcf.gz.md5 --old-database backend/data/variants.sqlite --old-dataset ml/data/clinvar-five-class-v1-rebuild --reference ml/data/reference/hg38.fa --output ml/data/locked-temporal-v4

.venv/bin/python -m ml.protein_features --splits ml/data/splits-v1 --reference ml/data/reference/hg38.fa --output ml/data/protein-training-v4
.venv/bin/python -m ml.population_features --splits ml/data/splits-v1 --output ml/data/population-training-v5

.venv/bin/python -m ml.improve --dataset ml/data/clinvar-five-class-v1-rebuild --features ml/data/features-v1 --splits ml/data/splits-v1 --baseline ml/artifacts/training-v1-final --enrichment ml/data/conservation-training-v1 --protein ml/data/protein-training-v4 --config ml/config/protein_study.json --output ml/artifacts/improvement-v4-protein

.venv/bin/python -m ml.improve --dataset ml/data/clinvar-five-class-v1-rebuild --features ml/data/features-v1 --splits ml/data/splits-v1 --baseline ml/artifacts/training-v1-final --enrichment ml/data/conservation-training-v1 --protein ml/data/protein-training-v4 --population ml/data/population-training-v5 --config ml/config/population_study.json --output ml/artifacts/improvement-v5-population

.venv/bin/python -m unittest discover -s ml/tests -v
```

73 tests passed, including positive/negative-strand codons, exon splicing, reference mismatches, explicit indel missingness, fixed transcript selection, reference-span overlap, exact review codes, population quality/allele matching, measured zero versus missing, and valid empty API responses. Source/study outputs, the sealed cohort, and unchanged live-model/evaluation artifacts were checksum-verified. No new Python packages were needed. The v5 artifact includes snapshots of the training/feature source files for reproducibility.
