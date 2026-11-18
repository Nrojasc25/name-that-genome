"""Five-class raw-margin Tree SHAP with a persisted training-only background."""

import json
from pathlib import Path

import numpy as np
import shap
from xgboost import XGBClassifier

from .dataset_io import digest
from .features import FEATURE_NAMES
from .labels import CLASS_ORDER
from .preprocessing import TrainingPreprocessor


def group_name(name):
    if name.startswith('substitution_'):
        return 'SNV substitution'
    if name.startswith('consequence_') and name not in ('consequence_missing', 'consequence_other'):
        return 'Annotated consequences'
    if name in ('is_snv', 'is_insertion', 'is_deletion'):
        return 'Variant type'
    return name


def grouped_features(names, raw, transformed, contributions):
    """Add contributions; retain original and imputed inputs for every member."""
    groups = {}
    for name, value, contribution in zip(names, transformed, contributions, strict=True):
        group = groups.setdefault(group_name(name), {'feature': group_name(name), 'contribution': 0.0, 'members': []})
        group['contribution'] += float(contribution)
        group['members'].append({'feature': name, 'value': raw[name], 'model_value': float(value)})
    return list(groups.values())


def display_features(groups, per_sign=3):
    if not isinstance(per_sign, int) or per_sign < 1:
        raise ValueError('per_sign must be a positive integer')
    positives = sorted((g for g in groups if g['contribution'] > 0), key=lambda g: (-g['contribution'], g['feature']))[:per_sign]
    negatives = sorted((g for g in groups if g['contribution'] < 0), key=lambda g: (g['contribution'], g['feature']))[:per_sign]
    selected = positives + negatives
    names = {g['feature'] for g in selected}
    others = [g for g in groups if g['feature'] not in names]
    if others:
        selected.append({'feature': 'Other features', 'contribution': sum(g['contribution'] for g in others),
                         'members': [m for g in others for m in g['members']]})
    return selected


class ClassExplainer:
    def __init__(self, model, names, background, *, model_version, background_version, atol=1e-4):
        self.model, self.names = model, list(names)
        self.model_version, self.background_version, self.atol = model_version, background_version, atol
        background = np.asarray(background, dtype=float)
        if (background.ndim != 2 or background.shape[1] != len(names) or not len(background)
                or not np.isfinite(background).all() or len(set(names)) != len(names)):
            raise ValueError('Invalid background/schema')
        if not np.array_equal(model.classes_, np.arange(5)):
            raise ValueError('Expected canonical five-class indices')
        self.explainer = shap.TreeExplainer(model, data=background, model_output='raw',
                                          feature_perturbation='interventional', feature_names=self.names)
        # Avoid an implicit masker subsample changing the versioned background.
        if not np.array_equal(self.explainer.data, background):
            raise ValueError('SHAP changed the background; use at most 100 rows')

    def explain(self, matrix):
        matrix = np.asarray(matrix, dtype=float)
        if matrix.ndim != 2 or matrix.shape[1] != len(self.names) or not len(matrix) or not np.isfinite(matrix).all():
            raise ValueError('Invalid explanation matrix')
        values = np.asarray(self.explainer.shap_values(matrix, check_additivity=True))
        base = np.asarray(self.explainer.expected_value)
        margins = np.asarray(self.model.predict(matrix, output_margin=True))
        if values.shape != (len(matrix), len(self.names), 5) or base.shape != (5,) or margins.shape != (len(matrix), 5):
            raise ValueError('Unexpected multiclass SHAP shape')
        if not all(np.isfinite(x).all() for x in (values, base, margins)):
            raise ValueError('Nonfinite explanation')
        if not np.allclose(values.sum(axis=1) + base, margins, atol=self.atol, rtol=0):
            raise ValueError('SHAP does not reconstruct raw class margins')
        return values, base, margins

    def payload(self, raw, matrix_row, values, base, margins, target=None, per_sign=3):
        target = CLASS_ORDER[int(np.argmax(margins))] if target is None else target
        if target not in CLASS_ORDER:
            raise ValueError('Unknown output target')
        c = CLASS_ORDER.index(target)
        groups = grouped_features(self.names, raw, matrix_row, values[:, c])
        visible = display_features(groups, per_sign)
        if not np.isclose(base[c] + sum(g['contribution'] for g in visible), margins[c], atol=self.atol, rtol=0):
            raise ValueError('Displayed contributions do not reconstruct output')
        return {'output_target': str(target), 'output_space': 'raw_score', 'base_value': float(base[c]),
                'explained_value': float(margins[c]), 'model_version': self.model_version,
                'background_version': self.background_version, 'features': groups, 'display_features': visible,
                'interpretation': 'Positive contributions increase this class raw margin relative to the training background; they do not indicate disease risk or causation.'}


class SavedExplainer:
    """Load trusted local artifacts; explanations do not need target labels."""
    def __init__(self, model_directory: Path, explanation_directory: Path):
        self.manifest = json.loads((explanation_directory / 'shap_manifest.json').read_text())
        manifest = self.manifest
        model_manifest_path = model_directory / 'model_manifest.json'
        if digest(model_manifest_path) != manifest['input_fingerprints']['model_manifest_sha256']:
            raise ValueError('Model manifest mismatch')
        model_manifest = json.loads(model_manifest_path.read_text())
        if manifest['class_order'] != list(CLASS_ORDER) or model_manifest['class_order'] != list(CLASS_ORDER):
            raise ValueError('Class order mismatch')
        for name in [model_manifest['model_file'], 'preprocessor.json']:
            if digest(model_directory / name) != model_manifest['outputs_sha256'][name]:
                raise ValueError('Model artifact checksum mismatch')
        for name in ['background.npy', 'background_membership.json']:
            if digest(explanation_directory / name) != manifest['outputs_sha256'][name]:
                raise ValueError('Background artifact checksum mismatch')
        self.processor = TrainingPreprocessor.load(model_directory / 'preprocessor.json')
        self.columns = model_manifest['selected_feature_indices']
        names = [FEATURE_NAMES[i] for i in self.columns]
        if names != manifest['feature_names']:
            raise ValueError('Feature order mismatch')
        model = XGBClassifier(n_jobs=2)
        model.load_model(model_directory / model_manifest['model_file'])
        model.set_params(n_jobs=2)
        self.engine = ClassExplainer(model, names, np.load(explanation_directory / 'background.npy', allow_pickle=False),
                                    model_version=model_manifest['model_version'], background_version=manifest['background_version'],
                                    atol=manifest['config']['additivity_atol'])

    def explain_from_cache(self, cache, variant_key, target=None):
        if cache.manifest['annotation_version'] != self.processor.artifact['annotation_version']:
            raise ValueError('Annotation version mismatch')
        raw = cache.features_for(variant_key)
        matrix = np.asarray(self.processor.transform([raw]))[:, self.columns]
        values, base, margins = self.engine.explain(matrix)
        return self.engine.payload(raw, matrix[0], values[0], base, margins[0], target,
                                   self.manifest['config']['display_per_sign'])
