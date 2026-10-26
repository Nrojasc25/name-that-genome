"""Read ClinVar records from variants.sqlite."""

import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path


DATABASE_PATH = Path(__file__).resolve().parent / "data" / "variants.sqlite"


def get_connection() -> sqlite3.Connection:
    """Open the ClinVar database read-only."""
    if not DATABASE_PATH.is_file():
        raise FileNotFoundError(
            f"Database not found at {DATABASE_PATH}. "
            "Download variants.sqlite using the link in backend/README.md."
        )

    connection = sqlite3.connect(DATABASE_PATH.as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    return connection


def get_variant(variation_id: int) -> dict | None:
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
                   r.variant_type, json_extract(r.raw_info, '$.CLNHGVS') AS hgvs,
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
            record["conditions"] = [
                {"name": condition["name"], "identifiers": json.loads(condition["identifiers"])}
                for condition in connection.execute(
                    "SELECT name, identifiers FROM condition_link WHERE record_id = ? ORDER BY ordinal",
                    (record["record_id"],),
                )
            ]
            result["source_records"].append(record)

        return result


def find_variant(query: str) -> dict | None:
    """Match a ClinVar ID or stored GRCh38 genomic HGVS."""
    query = query.strip()

    if re.fullmatch(r"[0-9]+", query):
        variation_id = int(query)
        if not 0 < variation_id <= 2**63 - 1:
            raise ValueError("Enter a positive ClinVar variation ID.")
        return get_variant(variation_id)

    if not re.fullmatch(r"NC_[0-9]+\.[0-9]+:g\.[^\s]+", query):
        raise ValueError(
            "Enter a ClinVar ID, such as 576, or a full GRCh38 genomic HGVS, "
            "such as NC_000012.12:g.102840399C>T. "
            "Short coding expressions such as c.76A>T are not supported."
        )

    with closing(get_connection()) as connection:
        matches = connection.execute(
            """
            SELECT DISTINCT v.clinvar_variation_id
            FROM clinvar_record AS r
            JOIN variant AS v ON v.id = r.variant_id
            JOIN variant_locus AS l ON l.id = r.locus_id
            WHERE l.assembly = 'GRCh38'
              AND json_extract(r.raw_info, '$.CLNHGVS') = ?
            LIMIT 2
            """,
            (query,),
        ).fetchall()

    if len(matches) > 1:
        raise ValueError("More than one variant matches. Use its ClinVar ID instead.")
    if not matches:
        return None
    return get_variant(matches[0][0])
