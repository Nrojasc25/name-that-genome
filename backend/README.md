# Name That Genome - Backend

This folder holds the project's ClinVar database and will contain the Python backend for accessing variant records and connecting the website to the model.

The model's task is to classify a genetic variant as benign or pathogenic. The database contains ClinVar's existing classifications. These are separate from predictions our model will make.

## Current status

The populated SQLite database supports variant lookups through `database.py`. A FastAPI endpoint in `main.py` returns the same stored information as JSON. Model inference and SHAP explanations are still upcoming.

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

## Run the API

Use Python 3.11 or newer. Run these commands from the repository root (`name-that-genome/`).

Create a virtual environment:

```sh
python -m venv .venv
```

On Windows PowerShell:

```powershell
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload
```

On macOS/Linux:

```sh
.venv/bin/python -m pip install -r backend/requirements.txt
.venv/bin/python -m uvicorn backend.main:app --reload
```

Open <http://127.0.0.1:8000/variants/clinvar/576> for an example lookup, or <http://127.0.0.1:8000/docs> to try the endpoint interactively. Keep the server terminal open, use Ctrl+C to stop it.

The endpoint returns 200 for a stored variant, 404 for an unknown ID, 422 for an invalid ID, and 503 if the database file is missing. The classification in a successful response is ClinVar's stored label. Each source record retains its release version and all reported genes.

## Next backend work

- Agree on the frontend's input and response format, then connect it to the lookup endpoint.
- Connect model predictions and SHAP explanations once those components are ready.

The current endpoint returns stored ClinVar information. Model inference is a later step.
