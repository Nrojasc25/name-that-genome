"""Read stored ClinVar records from the project's SQLite database."""

import sqlite3
from contextlib import closing
from pathlib import Path


# Resolve the database relative to this file, regardless of the terminal folder.
DATABASE_PATH = Path(__file__).resolve().parent / "data" / "variants.sqlite"


def get_connection() -> sqlite3.Connection:
    """Open the existing database for reading and return rows with named fields."""
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found at {DATABASE_PATH}. "
            "Download variants.sqlite using the link in backend/README.md."
        )

    connection = sqlite3.connect(DATABASE_PATH.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def get_variant(variation_id: int) -> dict | None:
    """Return a stored variant and its source records, or None if not found."""
    # closing() closes the database connection when the lookup finishes.
    with closing(get_connection()) as connection:
        variant = connection.execute(
            """
            SELECT id AS variant_id, clinvar_variation_id, clinvar_allele_id
            FROM variant
            WHERE clinvar_variation_id = ?
            """,
            (variation_id,),
        ).fetchone()

        if variant is None:
            return None

        records = connection.execute(
            """
            SELECT r.id AS record_id, r.release_id, s.version AS release_version,
                   l.assembly, l.chromosome, l.position, l.ref, l.alt,
                   r.variant_type,
                   r.germline_classification AS clinvar_classification,
                   r.review_status, r.review_stars
            FROM clinvar_record AS r
            JOIN source_release AS s ON s.id = r.release_id
            JOIN variant_locus AS l ON l.id = r.locus_id
            WHERE r.variant_id = ?
            ORDER BY s.version DESC, r.id
            """,
            (variant["variant_id"],),
        ).fetchall()

        result = dict(variant)
        result["source_records"] = []

        for row in records:
            record = dict(row)
            record["genes"] = [
                gene["gene_symbol"]
                for gene in connection.execute(
                    "SELECT gene_symbol FROM record_gene WHERE record_id = ? ORDER BY gene_symbol",
                    (record["record_id"],),
                )
            ]
            record["consequences"] = [
                consequence["term"]
                for consequence in connection.execute(
                    "SELECT term FROM record_consequence WHERE record_id = ? ORDER BY term",
                    (record["record_id"],),
                )
            ]
            result["source_records"].append(record)

        return result
