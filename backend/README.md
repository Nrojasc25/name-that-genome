# Name That Genome - Backend

This folder holds the project's ClinVar database and will contain the Python backend for accessing variant records and connecting the website to the model.

The model's task is to classify a genetic variant as benign or pathogenic. The database contains ClinVar's existing classifications. These are separate from predictions our model will make.

## Current status

The populated SQLite database is available for local use. The simplified database connection code and FastAPI endpoints have not been added yet, so there is no API server to start at this stage.

## Dataset

- **Source:** [ClinVar GRCh38 snapshot, September 13, 2026](https://ftp.ncbi.nlm.nih.gov/pub/clinvar/vcf_GRCh38/clinvar_20260913.vcf.gz).
- **Genes:** ACADM, ATP7B, CFTR, COL4A5, FBN1, GAA, PAH, and PKHD1.
- **Local file:** `backend/data/variants.sqlite`, relative to the repository root.

| Group | Records |
|---|---:|
| All stored variants | 36,065 |
| Candidate training variants | 20,996 |
| Benign / likely benign candidates | 10,765 |
| Pathogenic / likely pathogenic candidates | 10,231 |

The two label counts make up the candidate group. Other records, including uncertain and conflicting classifications, are retained for reference and are excluded from that group.

Candidates were selected using clear germline classifications, qualifying review status, and small sequence changes. They still need reference checks, gene and transcript annotation, final feature selection, and train/validation/test splits before training.

The database also stores coordinates, reported genes, review information, basic features, and the source and selection metadata.

## Local setup

1. Create `data/` inside this `backend/` folder if it does not exist.
2. Download [variants.sqlite](https://github.com/Nrojasc25/name-that-genome/releases/download/clinvar-data-v1/variants.sqlite) and place it in `backend/data/`.
3. Keep the database excluded from Git. Anyone running the backend locally needs a copy of the same prepared database. Cloning the repository alone will not download it.

## Next backend work

- Add `database.py` to connect to SQLite and look up stored variants using Python's built-in `sqlite3` module.
- Add `main.py` with a FastAPI endpoint that accepts a ClinVar variation ID and returns the stored variant details.
- Add a small `requirements.txt` and startup instructions when the API is implemented.
- Connect model predictions and SHAP explanations once those components are ready.

The first endpoint will return stored ClinVar information. Model inference is a later step.
