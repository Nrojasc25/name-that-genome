# Name That Genome

A web application that analyzes genetic variants and uses machine learning to identify potential rare genetic diseases.

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
you do not need to activate it. It starts both servers in the same terminal.
Open http://localhost:5173 and press Ctrl+C to stop both servers. Stop any
previously started servers before using this command. If either server exits,
the launcher shuts down the other one as well.
