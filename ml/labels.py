"""Exact ClinVar germline label eligibility; no model or dataset filtering side effects."""

from dataclasses import asdict, dataclass
from enum import StrEnum
import json
from pathlib import Path
import re


class VariantClass(StrEnum):
    BENIGN = "benign"
    LIKELY_BENIGN = "likely_benign"
    UNCERTAIN = "uncertain"
    LIKELY_PATHOGENIC = "likely_pathogenic"
    PATHOGENIC = "pathogenic"


CLASS_ORDER = tuple(VariantClass)
POLICY = json.loads((Path(__file__).parent / "config" / "labels.json").read_text())
if POLICY["class_order"] != list(CLASS_ORDER):
    raise ValueError("Label policy class order disagrees with the shared enum")
POLICY_VERSION = POLICY["policy_version"]


@dataclass(frozen=True)
class LabelDecision:
    label: VariantClass | None
    class_id: int | None
    exclusion_reason: str | None
    policy_version: str = POLICY_VERSION

    def to_dict(self) -> dict:
        return asdict(self)


def normalize_label(value: str) -> str:
    """Normalize case, whitespace, and ClinVar VCF underscore-encoded spaces only."""
    return re.sub(r"\s*/\s*", "/", " ".join(value.replace("_", " ").casefold().split()))


def classify_label(classification: str | None, review_stars: int | None,
                   classification_type: str = "germline") -> LabelDecision:
    """Return a single exact training label or a deterministic first exclusion reason.

    Assembly/allele eligibility and duplicate conflicts are dataset-stage checks.
    This function never infers a label from a substring or from model confidence.
    """
    def excluded(reason: str) -> LabelDecision:
        return LabelDecision(None, None, reason)

    if classification_type != POLICY["classification_type"]:
        return excluded("non_germline_classification")
    if classification is not None and not isinstance(classification, str):
        return excluded("invalid_classification")
    normalized = normalize_label(classification or "")
    if normalized in POLICY["missing_labels"]:
        return excluded("missing_classification")
    if normalized in POLICY["conflicting_labels"]:
        return excluded("conflicting_classification")
    if normalized in POLICY["combined_labels"]:
        return excluded("combined_classification")
    label = POLICY["exact_labels"].get(normalized)
    if label is None:
        return excluded("unsupported_classification")
    if type(review_stars) is not int or not 0 <= review_stars <= 4:
        return excluded("invalid_review_stars")
    if review_stars < POLICY["minimum_review_stars"]:
        return excluded("insufficient_review_stars")
    label = VariantClass(label)
    return LabelDecision(label, CLASS_ORDER.index(label), None)
