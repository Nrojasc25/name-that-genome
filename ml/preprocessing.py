"""Train-partition-only imputation, persisted with feature order and training-key digest."""

import hashlib
import json
import math
from pathlib import Path
import statistics

from .dataset_io import write_json, digest
from .features import CONFIG_PATH, FEATURE_NAMES, NULLABLE_FEATURES, SCHEMA_VERSION


def validate_vector(vector):
    if set(vector) != set(FEATURE_NAMES):
        raise ValueError('Feature schema mismatch; labels and extra columns are forbidden')
    for name in FEATURE_NAMES:
        value = vector[name]
        if value is None:
            if name not in NULLABLE_FEATURES:
                raise ValueError('Unexpected missing value in ' + name)
        elif isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise ValueError('Features must be finite numeric values or supported nulls')


class TrainingPreprocessor:
    """Fixed vocabulary needs no fit; medians are fitted on explicitly named training rows."""

    def __init__(self, artifact: dict):
        if artifact['schema_version'] != SCHEMA_VERSION or artifact['feature_names'] != list(FEATURE_NAMES):
            raise ValueError('Preprocessor feature schema mismatch')
        if artifact['feature_config_sha256'] != digest(CONFIG_PATH):
            raise ValueError('Preprocessor feature configuration mismatch')
        if set(artifact['fill_values']) != set(NULLABLE_FEATURES):
            raise ValueError('Preprocessor missing imputation parameters')
        for value in artifact['fill_values'].values():
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 1:
                raise ValueError('Invalid preprocessor fill value')
        self.artifact = artifact

    @classmethod
    def fit(cls, vectors: dict[str, dict], *, training_keys: list[str], annotation_version: str):
        if not annotation_version:
            raise ValueError("An annotation version is required")
        if not training_keys or len(training_keys) != len(set(training_keys)):
            raise ValueError('Provide a nonempty, unique list of training-partition keys')
        if set(training_keys) - vectors.keys():
            raise ValueError('A training key has no feature vector')
        rows = [vectors[key] for key in sorted(training_keys)]
        for row in rows:
            validate_vector(row)
        fills, all_missing = {}, []
        for name in NULLABLE_FEATURES:
            observed = [row[name] for row in rows if row[name] is not None]
            fills[name] = float(statistics.median(observed)) if observed else 0.0
            if not observed:
                all_missing.append(name)
        return cls({'annotation_version': annotation_version, 'schema_version': SCHEMA_VERSION, 'feature_names': list(FEATURE_NAMES),
                    'feature_config_sha256': digest(CONFIG_PATH), 'fill_values': fills,
                    'all_missing_training_features': all_missing, 'training_count': len(training_keys),
                    'training_keys_sha256': hashlib.sha256('\n'.join(sorted(training_keys)).encode()).hexdigest(),
                    'all_missing_policy': 'Fill with zero and preserve explicit missingness indicator; no held-out values used.'})

    def transform(self, vectors: list[dict]) -> list[list[float]]:
        output = []
        for row in vectors:
            validate_vector(row)
            output.append([float(self.artifact['fill_values'][name] if row[name] is None else row[name]) for name in FEATURE_NAMES])
        return output

    def transform_from_cache(self, cache, variant_key: str) -> list[float]:
        if cache.manifest['annotation_version'] != self.artifact['annotation_version']:
            raise ValueError('Preprocessor was fitted with a different annotation version')
        return self.transform([cache.features_for(variant_key)])[0]

    def save(self, path: Path):
        write_json(path, self.artifact)

    @classmethod
    def load(cls, path: Path):
        return cls(json.loads(path.read_text()))
