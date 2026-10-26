# Name That Genome - Backend

## Setup

Use Python 3.12. Download [variants.sqlite](https://github.com/Nrojasc25/name-that-genome/releases/download/clinvar-data-v1/variants.sqlite) into `backend/data/`. The API creates `app.sqlite` for accounts and history.

First-time setup from the repository root on Windows:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r backend\requirements.txt
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --no-use-colors
```

On macOS/Linux, create the environment with `python3.12 -m venv .venv` and use `.venv/bin/python` for the remaining commands.

## Connection

- API: `http://localhost:8000`. Schemas and examples: [localhost:8000/docs](http://localhost:8000/docs).
- Frontend origins: `http://localhost:5173` and `http://127.0.0.1:5173`. Use the same hostname for the API.
- Include `credentials: "include"` on requests and `Content-Type: application/json` when sending JSON.

## Endpoints

| Endpoint | Request | Response |
|---|---|---|
| `POST /api/auth/register` | `first_name`, `last_name`, `email`, `password` | 201: User; signs in immediately |
| `POST /api/auth/login` | `email`, `password` | 200: User |
| `POST /api/auth/guest` | No body | 201: User |
| `GET /api/auth/me` | No body | 200: User; 401 without a session |
| `POST /api/auth/logout` | No body | 204: empty body |
| `POST /api/auth/password-reset` | `email` | 200: `message`, `delivery` |
| `POST /api/auth/password-reset/confirm` | `token`, `password` | 200: `message`; requires login again |
| `POST /api/analyses` | `{"variant":"576"}` | 201: Analysis |
| `GET /api/analyses/{id}` | Analysis ID | 200: Analysis |
| `GET /api/history?limit=4&offset=0` | Recent results | 200: History |
| `GET /api/history?limit=20&offset=0` | Paginated history | 200: History |

**User:** `{id, email, first_name, last_name, is_guest}`. Guest email is null. New passwords require 8-128 characters; send only `password`, not the confirmation field. Guest history does not transfer to an account.

**Errors:** `detail` is a message string or a list of validation entries with `msg` fields. Statuses: 400 invalid reset link, 401 login/session required, 403 origin rejected, 404 not found, 409 duplicate email, 422 invalid input, 503 database or reset delivery unavailable.

## Analysis and history

Accepted inputs: ClinVar ID (`576`) or an exact stored GRCh38 genomic HGVS (`NC_000012.12:g.102840399C>T`). Short `c.` expressions and transcript-level HGVS are unsupported.

| Analysis field | Contents |
|---|---|
| `id` | Saved analysis ID used to reopen a result |
| `created_at` | Unix timestamp in seconds |
| `input` | Submitted variant text |
| `variant` | `variant_id`, `clinvar_variation_id`, `clinvar_allele_id`, `source_records` |
| `prediction_status` | `not_available` or `available` |
| `prediction` | Null until the model is connected; otherwise the object below |

Use `variant.source_records[0]` for the newest source record:

| Fields | Contents |
|---|---|
| `hgvs`, `genes`, `consequences` | HGVS string or null; gene and consequence lists |
| `chromosome`, `position`, `ref`, `alt`, `assembly` | Coordinates and sequence change |
| `clinvar_classification`, `conditions` | Reference classification; condition objects with `name` and `identifiers` |
| `review_stars`, `review_status`, `release_version` | Review information and source version |

ClinVar classifications and conditions are reference data, not model predictions. No zygosity field is available.

**History:** `{items, total, limit, offset}`. Each item is an Analysis, newest first. `limit` accepts 1-100; `offset` starts at 0. Saved analyses retain their original results after model updates.

## Password reset

The response's `delivery` is `local` until email is configured. For local testing, open the `.eml` message in `backend/data/mail_outbox/` and follow its link.

The link opens `/forgot-password/new-password#token=...`. Read `token` from the URL fragment and send it with `password` to the confirmation endpoint. The link expires after 30 minutes and works once; a newer request replaces it.

## Prediction and SHAP

| Prediction field | Contents |
|---|---|
| `model_name`, `model_version` | Model identification |
| `decision` | `benign`, `pathogenic`, or `uncertain` |
| `pathogenic_probability` | 0-1 score for the pathogenic class |
| `probability_kind` | `calibrated` or `uncalibrated`; display uncalibrated values as scores |
| `explanation` | Null or a SHAP explanation |

An explanation contains `base_value`, `explained_value`, `output_space` (`probability`, `log_odds`, or `raw_score`), `output_target` (`pathogenic`), and `features`. Each feature has `feature`, `value` (string, number, boolean, or null), and `contribution`.

Positive contributions increase the pathogenic output in the stated output space; negative contributions decrease it.
