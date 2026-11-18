# Phase 4 frozen splits

Reserve one whole connected gene component closest to 15% with sufficient class support, then apply 70/15/15 to remaining variants. Selection uses counts only, before fitting.

| Partition | Variants | Benign | Likely benign | Uncertain | Likely pathogenic | Pathogenic |
|---|---:|---:|---:|---:|---:|---:|
| train | 16500 | 560 | 5636 | 5218 | 2430 | 2656 |
| validation | 3536 | 120 | 1208 | 1118 | 521 | 569 |
| test | 3536 | 120 | 1207 | 1119 | 521 | 569 |
| gene_challenge | 4816 | 63 | 1494 | 2231 | 299 | 729 |

Challenge genes (including overlapping annotations): CFTR, CFTR-AS1, CFTR-AS2, LOC111674463, LOC111674464, LOC111674467, LOC111674468, LOC111674472, LOC111674474, LOC111674475, LOC111674477, LOC113219471, LOC113219472, LOC113633874, LOC113633875, LOC113633876, LOC113633877, LOC113664106, LOC126860160

Canonical variant overlap: 0. Gene overlap between challenge and other partitions: 0.
Within the primary split, genes may overlap by design. The separate challenge measures unseen-gene generalization.
Validation, test, and gene-challenge predictions are not generated during Phase 4. The validation set is reserved for Phase 5 calibration/quality rules.
Unavailable: only one source release is available in this dataset.
