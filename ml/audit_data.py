"""Inventory a selected ClinVar release without training or modifying source records."""

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

from .dataset_io import DEFAULT_CONFIG, DEFAULT_DATABASE, digest, load_source, write_json
from .labels import CLASS_ORDER, classify_label


def counts(rows, field):
    return dict(sorted(Counter(str(r.get(field)) for r in rows).items()))


def class_counts(rows):
    result = dict.fromkeys(map(str, CLASS_ORDER), 0)
    for row in rows:
        if row.get('label') is not None:
            result[str(row['label'])] += 1
    return result


def group_counts(rows, field):
    result = defaultdict(lambda: dict.fromkeys(map(str, CLASS_ORDER), 0))
    for row in rows:
        if row.get('label') is not None:
            for group in row[field] or ['(missing)']:
                result[group][str(row['label'])] += 1
    return dict(sorted(result.items()))


def summarize(release, rows, inventory):
    labeled = [{**r, 'label': classify_label(r['germline_classification'], 4).label} for r in rows]
    eligible = [r for r in labeled if classify_label(r['germline_classification'], r['review_stars']).label is not None]
    annotations = {key: sum(r['raw_info'].get(key) not in (None, '', '.') for r in rows)
                   for key in ['AF_ESP', 'AF_EXAC', 'AF_TGP', 'MC', 'GENEINFO', 'CLNHGVS']}
    return {
        'release': {k: v for k, v in release.items() if k != 'details'},
        'selected_genes_from_import_metadata': release['details'].get('imported_genes'),
        'inventory': inventory, 'records': len(rows),
        'stored_coordinate_keys': len({(r['assembly'], r['chromosome'], r['position'], r['ref'], r['alt']) for r in rows}),
        'coordinate_note': 'Stored source coordinates; canonical normalized counts require the reference-backed build.',
        'raw_labels': counts(rows, 'germline_classification'), 'review_stars': counts(rows, 'review_stars'),
        'review_status': counts(rows, 'review_status'), 'variant_types': counts(rows, 'variant_type'),
        'assemblies': counts(rows, 'assembly'), 'chromosomes': counts(rows, 'chromosome'),
        'source_normalization': counts(rows, 'normalization'),
        'exact_class_counts_before_review_filter': class_counts(labeled),
        'class_counts_after_label_policy': class_counts(eligible),
        'class_by_gene_before_review': group_counts(labeled, 'genes'),
        'class_by_consequence_before_review': group_counts(labeled, 'consequences'),
        'missingness': {
            'genes': sum(not r['genes'] for r in rows),
            'consequences': sum(not r['consequences'] for r in rows),
            'condition_links': sum(not r['condition_count'] for r in rows),
            'classification': sum(r['germline_classification'] is None for r in rows),
            'review_stars': sum(r['review_stars'] is None for r in rows),
        },
        'raw_annotation_presence': annotations,
        'annotation_note': 'Presence is not validation, numeric parsing, or independent annotation evidence.',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=DEFAULT_DATABASE)
    parser.add_argument('--config', type=Path, default=DEFAULT_CONFIG)
    parser.add_argument('--output', type=Path, default=Path('ml/reports/source_audit.json'))
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    before = digest(args.database)
    release, rows, inventory = load_source(args.database, config)
    result = summarize(release, rows, inventory)
    if digest(args.database) != before:
        raise ValueError('Source changed while auditing')
    result['source_database_sha256'] = before
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, result)
    print(f"Audited {len(rows)} records from release {release['version']}: {args.output}")


if __name__ == '__main__':
    main()
