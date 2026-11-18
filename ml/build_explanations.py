"""Build versioned SHAP diagnostics on saved evaluation rows, without model tuning."""

import argparse
from collections import Counter
import json
import os
from pathlib import Path
import platform
import tempfile
import time

import numpy as np
import shap
from threadpoolctl import threadpool_limits

from .dataset_io import digest, write_json
from .evaluation_data import EvaluationInputs
from .explain import ClassExplainer, SavedExplainer, group_name
from .features import FEATURE_NAMES
from .labels import CLASS_ORDER
from .train import environment_lock

CONFIG_PATH = Path(__file__).parent / 'config/shap.json'


def sample_training(training, size, seed):
    if not 1 <= size <= min(100, len(training['keys'])):
        raise ValueError('Background requires 1–100 training rows')
    indices = np.sort(np.random.default_rng(seed).choice(len(training['keys']), size, replace=False))
    return indices


def plots(report, examples, output):
    os.environ.setdefault('MPLCONFIGDIR', str(Path(tempfile.gettempdir()) / 'ntg-matplotlib'))
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), layout='constrained')
    for c, ax in zip(CLASS_ORDER, axes.flat):
        groups = report['global_mean_absolute_grouped_shap'][c]
        names = sorted(groups, key=groups.get, reverse=True)[:10][::-1]
        ax.barh(names, [groups[n] for n in names], color='#276782')
        ax.set(title=c.replace('_', ' ').title(), xlabel='Mean |group contribution| (raw score)')
        ax.tick_params(axis='y', labelsize=8)
    axes.flat[-1].axis('off')
    axes.flat[-1].text(0, .8, f"{report['count']} sampled evaluation variants\nEqual partition sampling; not population weighted.\n\nDescribes model behavior, not biology.\nSigned members are summed before\nabsolute group importance is averaged.\nMissingness remains separately visible.", va='top')
    fig.suptitle('Five-class SHAP — rejected research candidate')
    fig.savefig(output / 'shap_global.png', dpi=150)
    plt.close(fig)
    fig, axes = plt.subplots(2, 3, figsize=(15, 9), layout='constrained')
    for example, ax in zip(examples, axes.flat):
        payload = example['explanation']
        groups = payload['display_features'][::-1]
        values = [g['contribution'] for g in groups]
        ax.barh([g['feature'] for g in groups], values, color=['#206b99' if v >= 0 else '#bb641c' for v in values])
        ax.axvline(0, color='gray', linewidth=.7)
        ax.tick_params(axis='y', labelsize=8)
        ax.set_title(payload['output_target'].replace('_', ' ').title() + f"\nBase {payload['base_value']:.3f} + contributions = {payload['explained_value']:.3f}", fontsize=10, pad=10)
        ax.set_xlabel('Signed contribution to raw class score')
    axes.flat[-1].axis('off')
    axes.flat[-1].text(0, .8, 'One deterministic example per target class.\nTargets are explicit; the model need not\npredict that class for the example.\n\nPositive: increases this class raw score.\nNegative: decreases this class raw score.\n\nOther features preserves the full sum.\nContributions do not sum to probability.', va='top')
    fig.suptitle('Local class-specific explanations — example IDs in shap_examples.json')
    fig.savefig(output / 'shap_local.png', dpi=150)
    plt.close(fig)


def build(inputs, evaluation, cache_path, output, config_path=CONFIG_PATH):
    if output.exists():
        raise FileExistsError('Explanation output exists; preserve it and use a new version directory')
    config = json.loads(config_path.read_text())
    if config['output_space'] != 'raw_score' or config['feature_perturbation'] != 'interventional':
        raise ValueError('Only interventional raw-margin explanations are supported')
    evaluation_manifest = json.loads((evaluation / 'evaluation_manifest.json').read_text())
    for file, field in [('heldout_predictions.json', 'predictions_sha256'), ('evaluation_policy.json', 'policy_sha256')]:
        if digest(evaluation / file) != evaluation_manifest[field]:
            raise ValueError('Evaluation artifact checksum mismatch')
    policy = json.loads((evaluation / 'evaluation_policy.json').read_text())
    if policy['input_fingerprints'] != inputs.fingerprints:
        raise ValueError('Explanations and evaluation use different artifacts')
    training = inputs.load_partition('train')
    indices = sample_training(training, config['background_size'], config['seed'])
    background = training['matrix'][indices]
    background_keys = [training['keys'][i] for i in indices]
    if any(inputs.membership[k]['partition'] != 'train' for k in background_keys):
        raise ValueError('Background leakage')
    records = json.loads((evaluation / 'heldout_predictions.json').read_text())
    chosen = []
    rng = np.random.default_rng(config['seed'])
    for partition in ['test', 'gene_challenge']:
        rows = sorted((r for r in records if r['partition'] == partition), key=lambda r: r['variant_key'])
        ids = np.sort(rng.choice(len(rows), min(len(rows), config['evaluation_rows_per_partition']), replace=False))
        chosen.extend(rows[i] for i in ids)
    if set(background_keys) & {r['variant_key'] for r in chosen}:
        raise ValueError('Evaluation/background overlap')
    names = [FEATURE_NAMES[i] for i in inputs.columns]
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.shap-', dir=output.parent) as temporary, threadpool_limits(limits=2):
        directory = Path(temporary)
        np.save(directory / 'background.npy', background, allow_pickle=False)
        write_json(directory / 'background_membership.json', background_keys)
        version = config['version'] + '-' + digest(directory / 'background.npy')[:12]
        engine = ClassExplainer(inputs.model, names, background, model_version=inputs.model_manifest['model_version'],
                                background_version=version, atol=config['additivity_atol'])
        raw = [r['raw_features'] for r in chosen]
        matrix = np.asarray(inputs.processor.transform(raw))[:, inputs.columns]
        values, base, margins = engine.explain(matrix)
        # Verifies the explained model is the one previously scored; no new accuracy estimate.
        from .calibration import probabilities
        if not np.allclose(probabilities(margins), [r['raw_scores'] for r in chosen], atol=1e-6, rtol=0):
            raise ValueError('Explained outputs disagree with saved evaluation scores')
        payloads = [[engine.payload(raw[i], matrix[i], values[i], base, margins[i], target=c,
                                    per_sign=config['display_per_sign']) for c in CLASS_ORDER] for i in range(len(chosen))]
        examples = []
        for c, name in enumerate(CLASS_ORDER):
            # Choose first sampled row with this reference label; no high-confidence cherry-picking.
            i = next((i for i, r in enumerate(chosen) if r['label_id'] == c), 0)
            examples.append({'variant_key': chosen[i]['variant_key'], 'partition': chosen[i]['partition'],
                             'reference_label': str(CLASS_ORDER[chosen[i]['label_id']]),
                             'decision': chosen[i]['decision'], 'explanation': payloads[i][c]})
        global_values = {}
        for c, name in enumerate(CLASS_ORDER):
            global_values[str(name)] = {g: float(np.mean(np.abs(values[:, [i for i, n in enumerate(names) if group_name(n) == g], c].sum(axis=1))))
                                        for g in sorted({group_name(n) for n in names})}
        np.savez_compressed(directory / 'shap_values.npz', values=values, base_values=base, margins=margins, matrix=matrix)
        write_json(directory / 'evaluation_membership.json', [{'variant_key': r['variant_key'], 'partition': r['partition']} for r in chosen])
        write_json(directory / 'shap_examples.json', examples)
        manifest = {'background_version': version, 'config': config, 'config_sha256': digest(config_path),
                    'class_order': list(CLASS_ORDER), 'feature_names': names, 'input_fingerprints': inputs.fingerprints,
                    'evaluation_manifest_sha256': digest(evaluation / 'evaluation_manifest.json'),
                    'sampling': 'Uniform without replacement from sorted training rows, preserving natural distribution in expectation; no class balancing.',
                    'background_count': len(indices), 'background_class_counts': dict(Counter(str(CLASS_ORDER[training['labels'][i]]) for i in indices)),
                    'background_representation': 'Training-imputed selected features; no new preprocessing fit.',
                    'shap_version': shap.__version__, 'model_version': inputs.model_manifest['model_version'],
                    'code_sha256': {n: digest(Path(__file__).with_name(n)) for n in ['explain.py', 'build_explanations.py']},
                    'outputs_sha256': {p.name: digest(p) for p in directory.iterdir()}}
        write_json(directory / 'shap_manifest.json', manifest)
        # Exercise the persisted single-variant path, including annotation compatibility.
        saved = SavedExplainer(inputs.model_path, directory)
        from .annotate import AnnotationCache
        timings = []
        cache = AnnotationCache(cache_path, expected_version=inputs.feature_manifest['annotation_version'])
        try:
            for i in range(config['latency_warmup'] + config['latency_repeats']):
                key = chosen[i % len(chosen)]['variant_key']
                start = time.perf_counter()
                result = saved.explain_from_cache(cache, key)
                elapsed = (time.perf_counter() - start) * 1000
                expected = payloads[i % len(chosen)][CLASS_ORDER.index(result['output_target'])]
                if result != expected:
                    raise ValueError('Saved single-variant and batch explanations disagree')
                if i >= config['latency_warmup']:
                    timings.append(elapsed)
        finally:
            cache.close()
        p95 = float(np.percentile(timings, 95))
        report = {'status': 'explanations_verified_model_still_rejected', 'count': len(chosen),
                  'partition_counts': dict(Counter(r['partition'] for r in chosen)), 'class_order': list(CLASS_ORDER),
                  'max_additivity_error': float(np.max(np.abs(values.sum(axis=1) + base - margins))),
                  'additivity_atol': config['additivity_atol'], 'single_batch_reload_parity': True,
                  'global_mean_absolute_grouped_shap': global_values,
                  'latency': {'p95_ms': p95, 'samples': len(timings), 'platform': platform.platform(),
                              'budget_ms': config['warm_explanation_p95_budget_ms'], 'passes': p95 <= config['warm_explanation_p95_budget_ms'],
                              'scope': 'Warm cache lookup, imputation, all-class SHAP, raw prediction, validation, and selected-class payload; excludes startup, network, API.'},
                  'interpretation': 'Diagnostics on previously evaluated holdouts, not a new untouched test or model acceptance. Raw margins, not calibrated probabilities. Noncausal attributions; correlated and constrained features can share attribution.'}
        write_json(directory / 'shap_report.json', report)
        plots(report, examples, directory)
        (directory / 'environment-lock.txt').write_text('\n'.join(environment_lock()) + '\n')
        manifest['outputs_sha256'] = {p.name: digest(p) for p in directory.iterdir() if p.name != 'shap_manifest.json'}
        write_json(directory / 'shap_manifest.json', manifest)
        directory.replace(output)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['dataset', 'features', 'splits', 'model', 'evaluation', 'cache', 'output']:
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--config', type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    inputs = EvaluationInputs(args.dataset, args.features, args.splits, args.model)
    report = build(inputs, args.evaluation, args.cache, args.output, args.config)
    print(json.dumps({k: report[k] for k in ['status', 'count', 'max_additivity_error', 'latency']}, indent=2))


if __name__ == '__main__':
    main()
