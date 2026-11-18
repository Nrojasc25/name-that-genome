# Name That Genome

A research web application that predicts five-class variant labels and explains model outputs with SHAP, alongside separate ClinVar reference annotations. The current candidate has not passed its performance gates and does not diagnose or rank diseases.

## Tech Stack

- React + TypeScript
- Vite
- Python
- Machine Learning
- ClinVar / GRCh38

## Team

University of Florida — Senior Project, Fall 2026

## Run locally

After the one-time setup in `backend/README.md` and `npm install` inside
`frontend/`, run this from the repository root:

```bash
python3 dev.py
```

On Windows, use `py dev.py`. The launcher uses the backend's `.venv` automatically;
On Mac, use `python3 dev.py`
you do not need to activate it. It starts both servers in the same terminal.
Open http://localhost:5173 and press Ctrl+C to stop both servers. Stop any
previously started servers before using this command. If either server exits,
the launcher shuts down the other one as well.


## Local model testing

Phase 7 connects the locally built candidate artifacts. Install inference dependencies with `.venv/bin/python -m pip install -r ml/requirements-inference.txt`; see [ML setup and status](ml/README.md) for artifact prerequisites. Restart `dev.py`, sign in, and submit ClinVar ID `614`, `729975`, `2828440`, `703089`, or `102871`. Guest demo screens still use fixed samples. Existing saved analyses keep their original outputs; submit a new analysis to see the connected model. Missing artifacts produce an explicit unavailable state.

The model remains uncalibrated and low confidence. Next: revisit feature/training weaknesses and Phase 5 gates, with fresh evaluation data reserved before tuning.
