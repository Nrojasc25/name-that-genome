"""HTTP access to the project's stored ClinVar variants."""

from typing import Annotated

from fastapi import FastAPI, HTTPException, Path

from .database import get_variant


app = FastAPI(title="Name That Genome API", version="0.1.0")


@app.get("/variants/clinvar/{variation_id}")
def read_variant(
    variation_id: Annotated[int, Path(gt=0, le=2**63 - 1)],
) -> dict:
    """Look up a ClinVar variation ID in the local dataset."""
    try:
        variant = get_variant(variation_id)
    except FileNotFoundError as error:
        raise HTTPException(
            status_code=503, detail="The variant database is not available."
        ) from error

    if variant is None:
        raise HTTPException(status_code=404, detail="Variant not found in this dataset.")

    return variant
