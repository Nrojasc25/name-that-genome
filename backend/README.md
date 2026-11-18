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

## Start both servers together

After setup, run `python3 dev.py` from the repository root (`py dev.py` on Windows).
This starts the backend and frontend in one terminal without activating the virtual
environment manually. Open http://localhost:5173. Press Ctrl+C to stop both.
Stop any existing dev servers first.

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

Phase 7 connects the frozen research candidate when the local artifacts are installed. New supported analyses return five uncalibrated scores, a low-confidence flag, and a selected-class raw-margin SHAP explanation. The candidate has failed its release criteria; it is not an approved clinical model.

Install inference dependencies from the repository root with `.venv/bin/python -m pip install -r ml/requirements-inference.txt`. The local service expects `ml/artifacts/training-v1-final/`, `ml/artifacts/shap-v1-final/`, `ml/artifacts/evaluation-v1/evaluation_policy.json`, and `ml/data/annotations-v1/`. See the [ML README](../ml/README.md) for build instructions. Artifacts remain ignored and are not downloaded automatically.

Startup checks reviewed manifest hashes, model/background/cache checksums, schema/class order, provenance, and pinned NumPy/XGBoost/SHAP versions. Missing or invalid artifacts leave lookup/history usable and produce a structured `prediction_reason`. One inference worker owns the SQLite annotation connection; at most four requests may be active/queued. A 128-entry LRU stores successful outputs keyed by normalized variant plus model, explanation, policy, and annotation identities.

Only the pinned GRCh38 release and exact normalized sequence alleles in the cache are supported. No new normalization or live annotation is attempted. The full source-record list is searched for the supported release rather than blindly predicting from the first record. Classification, conditions, genes, and review status are not inputs to prediction.

Unavailable reasons: `model_missing`, `model_load_failed`, `unsupported_source`, `ambiguous_source`, `unsupported_variant`, `annotation_missing`, `features_invalid`, `busy`, or `prediction_failed`. Unknown lookup IDs still return HTTP 404; invalid lookup syntax returns HTTP 422. `timings_ms` records lookup, features, prediction, explanation, and total inference time, or a cache-hit time.

If SHAP fails, valid scores are retained with `explanation: null` and `explanation_status: failed`. Failed explanation results are not memoized, so a new analysis can retry. History always reads the stored snapshot without recomputing it.

### Five-class prediction (schema version 2)

| Prediction field | Contents |
|---|---|
| `schema_version` | Required literal `2` |
| `model_name`, `model_version` | Nonempty model identification |
| `feature_schema_version`, `annotation_version`, `dataset_version` | Nonempty provenance versions |
| `decision` | `benign`, `likely_benign`, `uncertain`, `likely_pathogenic`, or `pathogenic` |
| `class_scores` | Exactly those five keys; finite numeric values in [0, 1], summing to 1 within 1e-6 |
| `probability_kind` | `calibrated` or `uncalibrated`; display uncalibrated values as scores |
| `confidence_status` | `not_assessed`, `low`, or `standard`; independent of the Uncertain class |
| `explanation` | Null or a class-specific SHAP explanation |

The decision is the maximum-scoring class. Exact ties choose the first class in the order shown above. Do not infer a category from five arbitrary intervals of a binary score. A predicted Uncertain label and low model confidence are distinct.

An explanation contains `base_value`, `explained_value`, `output_space` (`probability`, `log_odds`, or `raw_score`), a required `output_target` using the five-class enum, and `features`. Each feature has `feature`, `value` (string, number, boolean, or null), and finite `contribution`.

Positive contributions increase the named target's output in the stated output space; negative contributions decrease it. Raw multiclass margins must not be described as calibrated probabilities. SHAP computation and full/display additivity checks are implemented. New explanations include `model_version`, `background_version`, `display_features`, and group `members` retaining original and imputed values. New predictions include `release_status: research_candidate_rejected`, `explanation_status`, `source_record_id`, and `normalized_variant_key`. These fields are optional/defaulted when reading older version 2 snapshots; existing JSON is not migrated.

### Legacy saved results

Unversioned and version 1 predictions remain readable with their original three-choice `decision`, `pathogenic_probability`, model fields, probability kind, and optional pathogenic SHAP explanation. API serialization supplies `schema_version: 1`; stored JSON is not changed. Missing five-class probabilities are never fabricated. Version 2 payloads cannot fall back to legacy parsing when invalid.

See [ML implementation plan and Phase 1 instructions](../ml/README.md) and the explicitly synthetic examples in `ml/tests/fixtures/predictions.json`.
