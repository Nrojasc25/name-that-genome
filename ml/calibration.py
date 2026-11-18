"""Five-class calibration and confidence rules; never replace a predicted class."""

import numpy as np
from scipy.optimize import minimize_scalar
from scipy.special import softmax
from sklearn.metrics import average_precision_score, log_loss

from .labels import CLASS_ORDER
from .train import metrics


def probabilities(logits, temperature=1.0):
    values = np.asarray(logits, dtype=float)
    if values.ndim != 2 or values.shape[1] != 5 or not np.isfinite(values).all():
        raise ValueError('Expected finite five-class margins')
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError('Temperature must be positive and finite')
    return softmax(values / temperature, axis=1)


def fit_temperature(logits, labels, bounds):
    if len(logits) != len(labels) or set(labels) != set(range(5)):
        raise ValueError('Calibration fit requires aligned rows and all five classes')
    result = minimize_scalar(lambda t: log_loss(labels, probabilities(logits, t), labels=list(range(5))),
                             bounds=tuple(bounds), method='bounded', options={'xatol': 1e-8})
    if not result.success:
        raise ValueError('Temperature optimization failed')
    return float(result.x)


def reliability(labels, scores, bins=10):
    result = {}
    for c, name in enumerate(CLASS_ORDER):
        assignments = np.minimum((scores[:, c] * bins).astype(int), bins - 1)
        records = []
        for b in range(bins):
            mask = assignments == b
            count = int(mask.sum())
            records.append({'bin': b, 'count': count,
                            'mean_probability': float(scores[mask, c].mean()) if count else None,
                            'observed_fraction': float(np.mean(labels[mask] == c)) if count else None})
        ece = sum(r['count'] * abs(r['mean_probability'] - r['observed_fraction']) for r in records if r['count']) / len(labels)
        result[str(name)] = {'bins': records, 'ece': float(ece)}
    return result


def summarize(labels, scores, bins=10, include_curves=True):
    labels, scores = np.asarray(labels), np.asarray(scores, dtype=float)
    result = metrics(labels, scores)
    scores = scores / scores.sum(axis=1, keepdims=True)
    prediction = scores.argmax(axis=1)
    result['accuracy'] = float(np.mean(labels == prediction))
    result['multiclass_brier'] = float(np.mean(np.sum((scores - np.eye(5)[labels]) ** 2, axis=1)))
    matrix = np.asarray(result['confusion_matrix'])
    result['row_normalized_confusion_matrix'] = np.divide(matrix, matrix.sum(axis=1, keepdims=True),
                                                         out=np.zeros_like(matrix, dtype=float), where=matrix.sum(axis=1, keepdims=True) > 0).tolist()
    result['severe_confusion'] = {}
    for name, true_ids, predicted_ids in [('benign_to_pathogenic', [0,1], [3,4]), ('pathogenic_to_benign', [3,4], [0,1])]:
        mask = np.isin(labels, true_ids)
        count = int(np.sum(mask & np.isin(prediction, predicted_ids)))
        result['severe_confusion'][name] = {'count': count, 'denominator': int(mask.sum()), 'rate': count / int(mask.sum()) if mask.any() else None}
    if include_curves:
        result['reliability'] = reliability(labels, scores, bins)
        result['mean_class_ece'] = float(np.mean([v['ece'] for v in result['reliability'].values()]))
        result['one_vs_rest_average_precision'] = {str(name): {'average_precision': float(average_precision_score(labels == c, scores[:, c])) if (labels == c).any() else None,
                                                               'prevalence': float(np.mean(labels == c)), 'support': int(np.sum(labels == c))} for c,name in enumerate(CLASS_ORDER)}
        result['pr_auc_convention'] = 'Non-interpolated average precision (AP), not trapezoidal PR area.'
    return result


def choose_calibration(logits, labels, temperature, config):
    raw = summarize(labels, probabilities(logits), config['reliability_bins'])
    scaled = summarize(labels, probabilities(logits, temperature), config['reliability_bins'])
    rule = config['calibration_selection']
    checks = {'log_loss_improves': raw['log_loss'] - scaled['log_loss'] >= rule['minimum_log_loss_improvement'],
              'brier_nonworse': scaled['multiclass_brier'] <= raw['multiclass_brier'] + rule['maximum_brier_increase'],
              'ece_nonworse': scaled['mean_class_ece'] <= raw['mean_class_ece'] + rule['maximum_mean_class_ece_increase']}
    accepted = all(checks.values())
    return {'temperature': temperature if accepted else 1.0, 'fitted_temperature': temperature,
            'probability_kind': 'calibrated' if accepted else 'uncalibrated', 'accepted': accepted,
            'checks': checks, 'raw_metrics': raw, 'temperature_scaled_metrics': scaled}


def standard_mask(scores, rule):
    if not rule['accepted']:
        return np.zeros(len(scores), dtype=bool)
    ordered = np.sort(scores, axis=1)
    return (ordered[:, -1] >= rule['top_probability']) & (ordered[:, -1] - ordered[:, -2] >= rule['margin'])


def confidence_summary(labels, scores, rule):
    mask = standard_mask(scores, rule)
    return {'standard_count': int(mask.sum()), 'low_count': int((~mask).sum()), 'coverage': float(mask.mean()),
            'standard_accuracy': float(np.mean(np.asarray(labels)[mask] == scores[mask].argmax(axis=1))) if mask.any() else None,
            'class_standard_coverage': {str(name): float(mask[np.asarray(labels) == c].mean()) if (np.asarray(labels) == c).any() else None for c,name in enumerate(CLASS_ORDER)}}


def choose_confidence(labels, scores, config):
    candidates = []
    for top in config['top_probability_grid']:
        for margin in config['margin_grid']:
            rule = {'accepted': True, 'top_probability': top, 'margin': margin}
            summary = confidence_summary(labels, scores, rule)
            if summary['coverage'] >= config['minimum_standard_coverage'] and summary['standard_accuracy'] is not None and summary['standard_accuracy'] >= config['minimum_standard_accuracy']:
                candidates.append((summary['coverage'], top, margin, rule, summary))
    if not candidates:
        return {'accepted': False, 'top_probability': None, 'margin': None, 'reason': 'No validation rule meets coverage and accuracy targets; all predictions flagged low confidence.'}
    best = sorted(candidates, key=lambda row: (-row[0], row[1], row[2]))[0]
    return {**best[3], 'selection_metrics': best[4]}


def acceptance(selected, raw, dummy, logistic, confidence, latency, config):
    rule = config['acceptance']
    return {'macro_f1_floor': selected['macro_f1'] >= rule['minimum_macro_f1'],
            'improvement_over_dummy': selected['macro_f1'] - dummy['macro_f1'] >= rule['minimum_macro_f1_improvement_over_dummy'],
            'improvement_over_logistic': selected['macro_f1'] - logistic['macro_f1'] >= rule['minimum_macro_f1_improvement_over_logistic'],
            **{'recall_' + str(c): selected['per_class'][c]['recall'] >= rule['minimum_recall_each_class'] for c in CLASS_ORDER},
            **{name: details['rate'] is not None and details['rate'] <= rule['maximum_severe_confusion_each_direction'] for name,details in selected['severe_confusion'].items()},
            'mean_class_ece': selected['mean_class_ece'] <= rule['maximum_mean_class_ece'],
            'brier_nonworse_than_raw': selected['multiclass_brier'] <= raw['multiclass_brier'] + rule['maximum_brier_increase_over_raw'],
            'log_loss_nonworse_than_raw': selected['log_loss'] <= raw['log_loss'] + rule['maximum_log_loss_increase_over_raw'],
            'standard_coverage': confidence['coverage'] >= rule['minimum_standard_coverage'],
            'standard_accuracy': confidence['standard_accuracy'] is not None and confidence['standard_accuracy'] >= rule['minimum_standard_accuracy'],
            'warm_single_variant_latency': latency['p95_ms'] <= rule['maximum_warm_single_variant_p95_ms']}
