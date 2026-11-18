"""Freeze canonical-variant splits and a separate connected-gene challenge before training."""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import tempfile

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.model_selection import StratifiedGroupKFold, train_test_split

from .dataset_io import digest, write_json
from .labels import CLASS_ORDER

CONFIG_PATH = Path(__file__).parent / 'config/training.json'


def connected_gene_groups(rows):
    parents = {}

    def root(gene):
        parents.setdefault(gene, gene)
        if parents[gene] != gene:
            parents[gene] = root(parents[gene])
        return parents[gene]

    for row in rows:
        for gene in row['genes']:
            a, b = root(gene), root(row['genes'][0])
            parents[max(a, b)] = min(a, b)
    members = defaultdict(set)
    for gene in parents:
        members[root(gene)].add(gene)
    names = {key: '|'.join(sorted(genes)) for key, genes in members.items()}
    return {r['variant_key']: names[root(r['genes'][0])] if r['genes'] else '' for r in rows}


def support(rows):
    counts = Counter(r['label'] for r in rows)
    return {str(label): counts[str(label)] for label in CLASS_ORDER}


def make_splits(rows, config):
    rows = sorted(rows, key=lambda r: r['variant_key'])
    keys = [r['variant_key'] for r in rows]
    if len(keys) != len(set(keys)):
        raise ValueError('Duplicate canonical variants; rebuild/deduplicate Phase 2 before splitting')
    if any(r['label'] not in CLASS_ORDER for r in rows):
        raise ValueError('Unknown class label')
    fractions = config['primary_split']
    if set(fractions) != {'train', 'validation', 'test'} or not np.isclose(sum(fractions.values()), 1):
        raise ValueError('Invalid primary split fractions')
    groups = connected_gene_groups(rows)
    by_group = defaultdict(list)
    for row in rows:
        by_group[groups[row['variant_key']]].append(row)
    total_counts = support(rows)
    eligible = []
    for group, candidates in by_group.items():
        counts = support(candidates)
        if group and min(counts.values()) >= config['gene_challenge_minimum_per_class'] and all(total_counts[k] - counts[k] >= config['minimum_primary_per_class'] for k in counts):
            distance = abs(len(candidates) / len(rows) - config['gene_challenge_target_fraction'])
            eligible.append((distance, group))
    if not eligible:
        raise ValueError('No connected gene group meets predeclared challenge support; revise protocol before training')
    held_group = min(eligible)[1]
    challenge = by_group[held_group]
    remaining = [r for r in rows if groups[r['variant_key']] != held_group]
    primary_indices = np.arange(len(remaining))
    labels = [r['label'] for r in remaining]
    training, held = train_test_split(primary_indices, test_size=fractions['validation'] + fractions['test'], stratify=labels, random_state=config['seed'])
    validation, testing = train_test_split(held, test_size=fractions['test'] / (fractions['test'] + fractions['validation']),
                                         stratify=[labels[i] for i in held], random_state=config['seed'] + 1)
    mapping = {r['variant_key']: {'variant_key': r['variant_key'], 'partition': 'gene_challenge', 'cv_fold': None, 'gene_group': groups[r['variant_key']]} for r in challenge}
    for partition, indices in [('train', training), ('validation', validation), ('test', testing)]:
        for i in indices:
            key = remaining[i]['variant_key']
            mapping[key] = {'variant_key': key, 'partition': partition, 'cv_fold': None, 'gene_group': groups[key]}
        if min(support([remaining[i] for i in indices]).values()) == 0:
            raise ValueError('A primary partition lacks a class')
    train_rows = sorted([remaining[i] for i in training], key=lambda r: r['variant_key'])
    folds = StratifiedGroupKFold(n_splits=config['cv_folds'], shuffle=True, random_state=config['seed'])
    for fold, (fit, score) in enumerate(folds.split(np.zeros(len(train_rows)), [r['label'] for r in train_rows], groups=[r['variant_key'] for r in train_rows])):
        if min(support([train_rows[i] for i in fit]).values()) == 0 or min(support([train_rows[i] for i in score]).values()) == 0:
            raise ValueError('A CV fold lacks a class')
        for i in score:
            mapping[train_rows[i]['variant_key']]['cv_fold'] = fold
    challenge_genes = {g for r in challenge for g in r['genes']}
    other_genes = {g for r in remaining for g in r['genes']}
    if challenge_genes & other_genes:
        raise ValueError('Gene challenge overlaps remaining genes')
    report = {'total': len(rows), 'partitions': {}, 'cv_folds': {}, 'challenge_genes': sorted(challenge_genes),
              'canonical_overlap': 0, 'challenge_gene_overlap': sorted(challenge_genes & other_genes),
              'connected_gene_groups': len([g for g in by_group if g]),
              'protocol': 'Reserve one whole connected gene component closest to 15% with sufficient class support, then apply 70/15/15 to remaining variants. Selection uses counts only, before fitting.',
              'temporal_evaluation': 'Unavailable: only one source release is available in this dataset.'}
    for partition in ['train', 'validation', 'test', 'gene_challenge']:
        subset = [r for r in rows if mapping[r['variant_key']]['partition'] == partition]
        report['partitions'][partition] = {'count': len(subset), 'class_counts': support(subset)}
    for fold in range(config['cv_folds']):
        subset = [r for r in train_rows if mapping[r['variant_key']]['cv_fold'] == fold]
        report['cv_folds'][str(fold)] = {'count': len(subset), 'class_counts': support(subset)}
    return [mapping[k] for k in keys], report


def freeze(dataset: Path, output: Path, config_path: Path = CONFIG_PATH):
    if output.exists():
        raise FileExistsError('Frozen split output exists; never overwrite it')
    config = json.loads(config_path.read_text())
    manifest = json.loads((dataset / 'dataset_manifest.json').read_text())
    if digest(dataset / 'variants.parquet') != manifest['outputs_sha256']['variants.parquet']:
        raise ValueError('Dataset checksum mismatch')
    rows = pq.read_table(dataset / 'variants.parquet', columns=['variant_key', 'label', 'genes']).to_pylist()
    membership, report = make_splits(rows, config)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.splits-', dir=output.parent) as temp:
        directory = Path(temp)
        schema = pa.schema([('variant_key', pa.string()), ('partition', pa.string()), ('cv_fold', pa.int16()), ('gene_group', pa.string())])
        pq.write_table(pa.Table.from_pylist(membership, schema=schema), directory / 'membership.parquet', compression='zstd')
        write_json(directory / 'split_report.json', report)
        lines = ['# Phase 4 frozen splits', '', report['protocol'], '', '| Partition | Variants | Benign | Likely benign | Uncertain | Likely pathogenic | Pathogenic |', '|---|---:|---:|---:|---:|---:|---:|']
        for name, item in report['partitions'].items():
            lines.append('| ' + ' | '.join([name, str(item['count']), *[str(item['class_counts'][str(k)]) for k in CLASS_ORDER]]) + ' |')
        lines += ['', 'Challenge genes (including overlapping annotations): ' + ', '.join(report['challenge_genes']), '',
                  'Canonical variant overlap: 0. Gene overlap between challenge and other partitions: 0.',
                  'Within the primary split, genes may overlap by design. The separate challenge measures unseen-gene generalization.',
                  'Validation, test, and gene-challenge predictions are not generated during Phase 4. The validation set is reserved for Phase 5 calibration/quality rules.',
                  report['temporal_evaluation']]
        (directory / 'split_report.md').write_text('\n'.join(lines) + '\n')
        result = {'schema_version': 1, 'config': config, 'config_sha256': digest(config_path), 'code_sha256': digest(Path(__file__)),
                  'dataset_version': manifest['dataset_version'], 'dataset_variants_sha256': manifest['outputs_sha256']['variants.parquet'],
                  'class_order': list(CLASS_ORDER), 'outputs_sha256': {p.name: digest(p) for p in sorted(directory.iterdir())}}
        result['split_id'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
        write_json(directory / 'split_manifest.json', result)
        directory.replace(output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--config', type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    print(freeze(args.dataset, args.output, args.config)['split_id'])


if __name__ == '__main__':
    main()
