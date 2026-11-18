"""Bounded training-only cross-validation; validation/test/challenge data remain unscored."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import platform
import tempfile
import time
import warnings

import joblib
import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from sklearn.dummy import DummyClassifier
from sklearn.exceptions import ConvergenceWarning
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import balanced_accuracy_score, classification_report, confusion_matrix, f1_score, log_loss
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.utils.class_weight import compute_sample_weight
from threadpoolctl import threadpool_limits, threadpool_info
from xgboost import XGBClassifier

from .dataset_io import digest, write_json
from .features import FEATURE_NAMES, CONFIG_PATH as FEATURE_CONFIG_PATH
from .labels import CLASS_ORDER
from .preprocessing import TrainingPreprocessor
from .split_data import CONFIG_PATH


CLASS_IDS = np.arange(len(CLASS_ORDER))


def selected_columns(candidate):
    return [i for i, name in enumerate(FEATURE_NAMES) if candidate['population_features'] or not name.startswith(('af_esp', 'af_exac', 'af_tgp'))]


def make_model(candidate, seed):
    algorithm = candidate['algorithm']
    if algorithm == 'dummy':
        return DummyClassifier(strategy='prior', random_state=seed)
    if algorithm == 'logistic':
        return Pipeline([('scale', StandardScaler()), ('classifier', LogisticRegression(C=candidate['C'], solver='lbfgs', max_iter=2500, random_state=seed))])
    if algorithm == 'xgboost':
        return XGBClassifier(objective='multi:softprob', num_class=5, eval_metric='mlogloss',
                             tree_method='hist', n_jobs=2, random_state=seed,
                             learning_rate=0.08, subsample=1.0, colsample_bytree=1.0,
                             max_depth=candidate['max_depth'], n_estimators=candidate['n_estimators'])
    raise ValueError('Unknown algorithm')


def fit_model(model, candidate, matrix, labels):
    weights = compute_sample_weight('balanced', labels) if candidate['weighted'] else None
    # Scaling and class weights see only this fold's fit rows.
    with warnings.catch_warnings():
        warnings.simplefilter('error', ConvergenceWarning)
        if candidate['algorithm'] == 'logistic':
            model.fit(matrix, labels, classifier__sample_weight=weights)
        else:
            model.fit(matrix, labels, sample_weight=weights)
    if not np.array_equal(model.classes_, CLASS_IDS):
        raise ValueError('Model class order differs from the saved canonical order')
    return model


def metrics(labels, probabilities):
    probabilities = np.asarray(probabilities, dtype=float)
    if probabilities.shape != (len(labels), 5) or not np.isfinite(probabilities).all():
        raise ValueError('Invalid five-class probabilities')
    if (probabilities < 0).any() or (probabilities > 1).any() or not np.allclose(probabilities.sum(axis=1), 1, atol=1e-6, rtol=0):
        raise ValueError('Invalid probability normalization')
    # Float32 softmax can differ from one by ~1e-7. Normalize only validated
    # roundoff for float64 metric routines; this is not probability calibration.
    probabilities = probabilities / probabilities.sum(axis=1, keepdims=True)
    decisions = probabilities.argmax(axis=1)
    return {'macro_f1': float(f1_score(labels, decisions, labels=CLASS_IDS, average='macro', zero_division=0)),
            'balanced_accuracy': float(balanced_accuracy_score(labels, decisions)),
            'log_loss': float(log_loss(labels, probabilities, labels=CLASS_IDS)),
            'confusion_matrix': confusion_matrix(labels, decisions, labels=CLASS_IDS).tolist(),
            'per_class': classification_report(labels, decisions, labels=CLASS_IDS, target_names=list(CLASS_ORDER), zero_division=0, output_dict=True)}


def select_candidate(experiments):
    usable = [item for item in experiments if item['status'] == 'complete']
    if not usable:
        raise ValueError('No candidate completed all CV folds')
    return min(usable, key=lambda item: (-item['cv_mean_macro_f1'], item['cv_mean_log_loss'], item['candidate']['id']))


def read_training_inputs(dataset: Path, features: Path, splits: Path, config):
    dataset_manifest = json.loads((dataset / 'dataset_manifest.json').read_text())
    feature_manifest = json.loads((features / 'feature_manifest.json').read_text())
    split_manifest = json.loads((splits / 'split_manifest.json').read_text())
    if feature_manifest['feature_config_sha256'] != digest(FEATURE_CONFIG_PATH):
        raise ValueError('Feature configuration differs from the exported matrix')
    if dataset_manifest['class_order'] != list(CLASS_ORDER) or split_manifest['class_order'] != list(CLASS_ORDER):
        raise ValueError('Dataset/split class order mismatch')
    if feature_manifest['feature_names'] != list(FEATURE_NAMES):
        raise ValueError('Feature order mismatch')
    checksum = dataset_manifest['outputs_sha256']['variants.parquet']
    if digest(dataset / 'variants.parquet') != checksum:
        raise ValueError('Dataset checksum mismatch')
    if feature_manifest['dataset_variants_sha256'] != checksum or split_manifest['dataset_variants_sha256'] != checksum:
        raise ValueError('Features/splits belong to another dataset')
    if split_manifest['config'] != config:
        raise ValueError('Training protocol differs from frozen split protocol; do not tune after viewing holdouts')
    for name in ['features.parquet', 'feature_rows.parquet']:
        if digest(features / name) != feature_manifest['outputs_sha256'][name]:
            raise ValueError('Feature file checksum mismatch')
    if digest(splits / 'membership.parquet') != split_manifest['outputs_sha256']['membership.parquet']:
        raise ValueError('Split membership checksum mismatch')
    memberships = pq.read_table(splits / 'membership.parquet').to_pylist()
    all_keys = [r['variant_key'] for r in memberships]
    if len(all_keys) != len(set(all_keys)):
        raise ValueError('Variant appears in multiple partitions')
    training = {r['variant_key']: r for r in memberships if r['partition'] == 'train'}
    if not training:
        raise ValueError('No training records')
    # Projection/filter means held-out labels are not loaded by training code.
    targets = pq.read_table(dataset / 'variants.parquet', columns=['variant_key', 'label'],
                            filters=[('variant_key', 'in', list(training))]).to_pylist()
    targets = {r['variant_key']: CLASS_ORDER.index(r['label']) for r in targets}
    row_keys = pq.read_table(features / 'feature_rows.parquet')['variant_key'].to_pylist()
    if len(row_keys) != len(set(row_keys)) or set(row_keys) != set(all_keys):
        raise ValueError('Feature row mapping and split keys differ')
    indices = [i for i, key in enumerate(row_keys) if key in training]
    matrix = pq.read_table(features / 'features.parquet')
    if matrix.column_names != list(FEATURE_NAMES) or matrix.num_rows != len(row_keys):
        raise ValueError('Feature matrix and row mapping differ')
    vectors = dict(zip([row_keys[i] for i in indices], matrix.take(pa.array(indices)).to_pylist(), strict=True))
    keys = sorted(training)
    if set(targets) != set(keys):
        raise ValueError('Training targets incomplete')
    fold_ids = {key: training[key]['cv_fold'] for key in keys}
    if set(fold_ids.values()) != set(range(config['cv_folds'])):
        raise ValueError('Invalid training CV fold assignments')
    return vectors, targets, fold_ids, {'dataset': dataset_manifest, 'features': feature_manifest, 'splits': split_manifest}


def environment_lock():
    # Full installed environment is recorded so dependency resolution is reproducible.
    return sorted(f"{dist.metadata['Name']}=={dist.version}" for dist in importlib.metadata.distributions() if dist.metadata['Name'])


def run(dataset: Path, features: Path, splits: Path, output: Path, config_path: Path = CONFIG_PATH):
    if output.exists():
        raise FileExistsError('Training output already exists; use a new run directory')
    config = json.loads(config_path.read_text())
    vectors, targets, fold_ids, inputs = read_training_inputs(dataset, features, splits, config)
    keys = sorted(vectors)
    annotation_version = inputs['features']['annotation_version']
    prepared = []
    for fold in range(config['cv_folds']):
        fit_keys = [k for k in keys if fold_ids[k] != fold]
        score_keys = [k for k in keys if fold_ids[k] == fold]
        if not score_keys or set(fit_keys) & set(score_keys):
            raise ValueError('Invalid CV split')
        fit_y, score_y = np.array([targets[k] for k in fit_keys]), np.array([targets[k] for k in score_keys])
        if set(fit_y) != set(CLASS_IDS) or set(score_y) != set(CLASS_IDS):
            raise ValueError('CV fold missing a class')
        processor = TrainingPreprocessor.fit(vectors, training_keys=fit_keys, annotation_version=annotation_version)
        prepared.append({'fold': fold, 'preprocessor': processor, 'fit_keys': fit_keys, 'score_keys': score_keys,
                         'fit_x': np.array(processor.transform([vectors[k] for k in fit_keys])),
                         'score_x': np.array(processor.transform([vectors[k] for k in score_keys])), 'fit_y': fit_y, 'score_y': score_y})
    experiments, predictions = [], {}
    with threadpool_limits(limits=2):
        for candidate in config['candidates']:
            print('Training candidate:', candidate['id'], flush=True)
            columns = selected_columns(candidate)
            folds, oof = [], {}
            for fold in prepared:
                model = make_model(candidate, config['seed'] + fold['fold'])
                start = time.perf_counter()
                fit_model(model, candidate, fold['fit_x'][:, columns], fold['fit_y'])
                fit_seconds = time.perf_counter() - start
                start = time.perf_counter()
                probabilities = model.predict_proba(fold['score_x'][:, columns])
                inference_seconds = time.perf_counter() - start
                scores = metrics(fold['score_y'], probabilities)
                folds.append({'fold': fold['fold'], **scores, 'fit_seconds': fit_seconds,
                              'batch_prediction_ms_per_row': inference_seconds * 1000 / len(probabilities),
                              'training_count': len(fold['fit_keys']), 'scored_count': len(fold['score_keys']),
                              'preprocessor_training_keys_sha256': fold['preprocessor'].artifact['training_keys_sha256'],
                              'training_class_counts': {str(CLASS_ORDER[c]): int(np.sum(fold['fit_y'] == c)) for c in CLASS_IDS}})
                oof.update(zip(fold['score_keys'], probabilities.tolist(), strict=True))
            if set(oof) != set(keys):
                raise ValueError('OOF predictions must cover training rows exactly once')
            overall = metrics(np.array([targets[k] for k in keys]), [oof[k] for k in keys])
            result = {'candidate': candidate, 'status': 'complete', 'folds': folds,
                      'cv_mean_macro_f1': float(np.mean([r['macro_f1'] for r in folds])),
                      'cv_std_macro_f1': float(np.std([r['macro_f1'] for r in folds])),
                      'cv_mean_log_loss': float(np.mean([r['log_loss'] for r in folds])),
                      'oof_metrics': overall}
            experiments.append(result)
            predictions[candidate['id']] = oof
            print(f"  CV macro-F1={result['cv_mean_macro_f1']:.4f}, log loss={result['cv_mean_log_loss']:.4f}", flush=True)
        selected = select_candidate(experiments)
        candidate = selected['candidate']
        processor = TrainingPreprocessor.fit(vectors, training_keys=keys, annotation_version=annotation_version)
        full_x = np.array(processor.transform([vectors[k] for k in keys]))[:, selected_columns(candidate)]
        full_y = np.array([targets[k] for k in keys])
        model = fit_model(make_model(candidate, config['seed']), candidate, full_x, full_y)
        check_predictions = model.predict_proba(full_x[:32])
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.training-', dir=output.parent) as temp:
        directory = Path(temp)
        processor.save(directory / 'preprocessor.json')
        for fold in prepared:
            fold['preprocessor'].save(directory / f"fold-{fold['fold']}-preprocessor.json")
        if candidate['algorithm'] == 'xgboost':
            model_name = 'model.ubj'
            model.save_model(directory / model_name)
            loaded = XGBClassifier()
            loaded.load_model(directory / model_name)
        else:
            model_name = 'model.joblib'
            joblib.dump(model, directory / model_name)
            loaded = joblib.load(directory / model_name)
        if not np.array_equal(check_predictions, loaded.predict_proba(full_x[:32])):
            raise ValueError('Saved/reloaded model changed predictions')
        oof_rows = [{'candidate_id': candidate_id, 'variant_key': key, 'cv_fold': fold_ids[key], 'target_class_id': targets[key], 'class_scores': values}
                    for candidate_id, records in predictions.items() for key, values in sorted(records.items())]
        pq.write_table(pa.Table.from_pylist(oof_rows), directory / 'training_oof.parquet', compression='zstd')
        report = {'selected_candidate': candidate['id'], 'selection_rule': config['selection'], 'training_rows': len(keys),
                  'class_order': list(CLASS_ORDER), 'experiments': experiments,
                  'held_out_predictions_generated': False, 'scores_are': 'Training-only cross-validation estimates used for selection; not final test performance.'}
        write_json(directory / 'training_report.json', report)
        lines = ['# Phase 4 training comparison', '', report['scores_are'], '',
                 '| Candidate | CV macro-F1 | Fold SD | CV log loss |', '|---|---:|---:|---:|']
        for item in sorted(experiments, key=lambda e: -e['cv_mean_macro_f1']):
            lines.append(f"| {item['candidate']['id']} | {item['cv_mean_macro_f1']:.4f} | {item['cv_std_macro_f1']:.4f} | {item['cv_mean_log_loss']:.4f} |")
        lines += ['', f"Selected: **{candidate['id']}**. Refit on {len(keys):,} training rows only; probabilities remain uncalibrated.", '',
                  '## Selected candidate: pooled training out-of-fold class metrics', '', '| Class | Precision | Recall | F1 | Support |', '|---|---:|---:|---:|---:|']
        for label in CLASS_ORDER:
            row = selected['oof_metrics']['per_class'][label]
            lines.append(f"| {label} | {row['precision']:.4f} | {row['recall']:.4f} | {row['f1-score']:.4f} | {int(row['support'])} |")
        lines += ['', 'Fold variation is descriptive, not a confidence interval. The primary CV folds share genes; the reserved gene challenge is needed to assess unseen-gene generalization.',
                  'Class weights and medians are recomputed within each fit fold. Logistic scaling is inside each fold. Population ablations remove all three frequency values and their missingness indicators.',
                  'The frozen validation set, final test set, and gene challenge were not scored. Calibration, quality thresholds, final evaluation, and production/API integration remain future work.',
                  'Candidate selection is based only on the predeclared CV ranking; held-out outcomes were not used. Timing figures in JSON are batch timings on this machine, not a production latency guarantee.']
        (directory / 'training_report.md').write_text('\n'.join(lines) + '\n')
        (directory / 'environment-lock.txt').write_text('\n'.join(environment_lock()) + '\n')
        manifest = {'model_version': config['experiment_version'], 'model_name': candidate['id'], 'model_file': model_name,
                    'candidate': candidate, 'probability_kind': 'uncalibrated', 'class_order': list(CLASS_ORDER),
                    'feature_names': list(FEATURE_NAMES), 'selected_feature_indices': selected_columns(candidate),
                    'selected_feature_names': [FEATURE_NAMES[i] for i in selected_columns(candidate)],
                    'annotation_version': annotation_version, 'feature_schema_version': inputs['features']['schema_version'],
                    'dataset_version': inputs['dataset']['dataset_version'], 'split_id': inputs['splits']['split_id'],
                    'training_keys_sha256': processor.artifact['training_keys_sha256'], 'training_count': len(keys),
                    'feature_manifest_sha256': digest(features / 'feature_manifest.json'), 'config': config,
                    'created_at_utc': datetime.now(timezone.utc).isoformat(), 'platform': platform.platform(),
                    'training_threads': 2, 'native_runtimes': [{k: runtime.get(k) for k in ['internal_api','version','prefix']} for runtime in threadpool_info()],
                    'code_sha256': {name: digest(Path(__file__).with_name(name)) for name in ['train.py','split_data.py','features.py','preprocessing.py']},
                    'build_command': ['python','-m','ml.train','--dataset',str(dataset),'--features',str(features),'--splits',str(splits),'--output',str(output),'--config',str(config_path)],
                    'outputs_sha256': {p.name: digest(p) for p in sorted(directory.iterdir())},
                    'release_status': 'candidate_only_not_evaluated_on_holdouts'}
        write_json(directory / 'model_manifest.json', manifest)
        directory.replace(output)
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ['dataset','features','splits','output']:
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--config', type=Path, default=CONFIG_PATH)
    args = parser.parse_args()
    result = run(args.dataset,args.features,args.splits,args.output,args.config)
    print('Saved candidate:', result['model_name'])


if __name__ == '__main__':
    main()
