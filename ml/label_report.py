"""Apply the label policy to JSONL records; this is not a full ClinVar data audit."""

import argparse
from collections import Counter
import json
from pathlib import Path

from .labels import CLASS_ORDER, POLICY_VERSION, classify_label


def build_report(records: list[dict]) -> dict:
    counts = {label.value: 0 for label in CLASS_ORDER}
    exclusions = Counter()
    decisions = []
    for index, record in enumerate(records):
        result = classify_label(record.get("classification"), record.get("review_stars"),
                                record.get("classification_type", "germline"))
        if result.label is not None:
            counts[result.label.value] += 1
        else:
            exclusions[result.exclusion_reason] += 1
        decisions.append({"row": index + 1, "record_id": record.get("record_id"),
                          "classification": record.get("classification"),
                          "review_stars": record.get("review_stars"),
                          "classification_type": record.get("classification_type", "germline"),
                          **result.to_dict()})
    return {"policy_version": POLICY_VERSION, "total": len(records),
            "included": sum(counts.values()), "excluded": sum(exclusions.values()),
            "class_counts": counts, "exclusion_counts": dict(sorted(exclusions.items())),
            "records": decisions}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="JSONL: classification, review_stars, optional record_id/type")
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    records = [json.loads(line) for line in args.input.read_text().splitlines() if line.strip()]
    report = build_report(records)
    report["source"] = str(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")


if __name__ == "__main__":
    main()
