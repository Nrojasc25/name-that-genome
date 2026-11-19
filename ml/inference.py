"""Bounded, single-worker inference for the frozen research candidate."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from importlib.metadata import version
import json
import logging
import os
from pathlib import Path
from threading import BoundedSemaphore
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger(__name__)
DISPLAY_NAMES = {
    'af_esp': 'Population frequency — ESP', 'af_exac': 'Population frequency — ExAC',
    'af_tgp': 'Population frequency — 1000 Genomes',
    'af_esp_missing': 'ESP frequency unavailable', 'af_exac_missing': 'ExAC frequency unavailable',
    'af_tgp_missing': '1000 Genomes frequency unavailable', 'context_gc_fraction': 'GC content near the variant',
    'phylop100way_snv': 'Conservation across 100 species', 'phylop100way_snv_missing': 'Conservation score unavailable',
}


class InferenceService:
    def __init__(self, root=ROOT):
        self.root = Path(root)
        self.executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='ntg-inference')
        self.capacity = BoundedSemaphore(4)
        self.reason = None
        self.cache = None
        self.enrichment = None
        self.results = OrderedDict()
        try:
            self.executor.submit(self._load).result()
        except FileNotFoundError:
            self.reason = 'model_missing'
        except Exception:
            LOGGER.exception('Candidate artifacts could not be loaded')
            self.reason = 'model_load_failed'

    def _load(self):
        if os.environ.get('NTG_MODEL_DIR'):
            return self._load_conservation(self.root / os.environ['NTG_MODEL_DIR'])
        from .dataset_io import digest
        from .explain import SavedExplainer
        from .annotate import AnnotationCache
        model = self.root / 'ml/artifacts/training-v1-final'
        explanations = self.root / 'ml/artifacts/shap-v1-final'
        evaluation = self.root / 'ml/artifacts/evaluation-v1'
        # Pin runtime artifacts to reviewed repository manifests, not a mutable local manifest alone.
        for actual, trusted in [(model/'model_manifest.json', 'model_manifest.json'),
                                (explanations/'shap_manifest.json', 'shap_manifest.json'),
                                (evaluation/'evaluation_policy.json', 'evaluation_policy.json')]:
            if digest(actual) != digest(self.root/'ml/reports'/trusted):
                raise ValueError('Unreviewed artifact manifest: ' + trusted)
        for package, required in [('xgboost','3.0.5'),('shap','0.48.0'),('numpy','2.2.6')]:
            if version(package) != required:
                raise ValueError('Incompatible package: ' + package)
        self.saved = SavedExplainer(model, explanations)
        self.model_manifest = json.loads((model/'model_manifest.json').read_text())
        self.policy = json.loads((evaluation/'evaluation_policy.json').read_text())
        if self.policy['input_fingerprints'] != self.saved.manifest['input_fingerprints']:
            raise ValueError('Model and evaluation provenance mismatch')
        self.cache = AnnotationCache(self.root/'ml/data/annotations-v1', expected_version=self.model_manifest['annotation_version'])
        self.identity = (digest(model/'model_manifest.json'), digest(explanations/'shap_manifest.json'), digest(evaluation/'evaluation_policy.json'), self.cache.manifest['annotation_version'])

    def _load_conservation(self, model):
        import numpy as np
        from xgboost import XGBClassifier
        from .annotate import AnnotationCache
        from .dataset_io import digest
        from .explain import ClassExplainer
        from .features import FEATURE_NAMES
        from .labels import CLASS_ORDER
        from .preprocessing import TrainingPreprocessor
        path = model / 'candidate_manifest.json'
        if digest(path) != digest(self.root/'ml/reports/conservation_candidate_manifest.json'):
            raise ValueError('Conservation candidate differs from the reviewed manifest')
        self.model_manifest = manifest = json.loads(path.read_text())
        names = list(FEATURE_NAMES) + ['phylop100way_snv', 'phylop100way_snv_missing']
        if not manifest['serving_compatible'] or manifest['feature_names'] != names or manifest['class_order'] != list(CLASS_ORDER):
            raise ValueError('Refit the candidate with the current conservation/SHAP contract')
        for package, required in [('xgboost','3.0.5'),('shap','0.48.0'),('numpy','2.2.6')]:
            if version(package) != required: raise ValueError('Incompatible package: ' + package)
        for name, checksum in manifest['outputs_sha256'].items():
            if digest(model/name) != checksum: raise ValueError('Candidate artifact checksum mismatch: ' + name)
        enrichment = self.root / os.environ.get('NTG_CONSERVATION_DIR', 'ml/data/conservation-all-v1')
        extra_manifest = json.loads((enrichment/'conservation_manifest.json').read_text())
        if extra_manifest['partition'] != 'all' or extra_manifest['training_manifest_sha256'] != manifest['enrichment_manifest_sha256']:
            raise ValueError('Extend the original training conservation cache before serving')
        if digest(enrichment/'features.json') != extra_manifest['features_sha256']:
            raise ValueError('Conservation cache checksum mismatch')
        self.enrichment = json.loads((enrichment/'features.json').read_text())
        self.enrichment_version = digest(enrichment/'conservation_manifest.json')
        self.conservation_median = json.loads((model/'conservation_preprocessor.json').read_text())['median']
        processor = TrainingPreprocessor.load(model/'base_preprocessor.json')
        fitted = XGBClassifier(n_jobs=2)
        fitted.load_model(model/'model.ubj')
        fitted.set_params(n_jobs=2)
        engine = ClassExplainer(fitted, names, np.load(model/'background.npy', allow_pickle=False),
                                model_version=manifest['model_version'], background_version=manifest['background_version'],
                                atol=manifest['shap_config']['additivity_atol'])
        self.saved = SimpleNamespace(processor=processor, columns=list(range(len(FEATURE_NAMES))), engine=engine,
                                     manifest={'config': manifest['shap_config']})
        # The new model has no validated confidence rule; do not reuse v1's policy.
        self.policy = {'calibration': {'temperature': 1.0, 'probability_kind': 'uncalibrated'}, 'confidence_rule': {'accepted': False}}
        self.cache = AnnotationCache(self.root/'ml/data/annotations-v1', expected_version=manifest['annotation_version'])
        self.identity = (digest(path), self.enrichment_version, self.cache.manifest['annotation_version'])

    def predict(self, records):
        if self.reason:
            return {'prediction': None, 'prediction_reason': self.reason}
        if not self.capacity.acquire(blocking=False):
            return {'prediction': None, 'prediction_reason': 'busy'}
        try:
            return self.executor.submit(self._predict, records).result()
        except Exception:
            LOGGER.exception('Candidate prediction failed')
            return {'prediction': None, 'prediction_reason': 'prediction_failed'}
        finally:
            self.capacity.release()

    def _predict(self, records):
        import numpy as np
        from .calibration import probabilities, standard_mask
        from .labels import CLASS_ORDER
        from .features import SCHEMA_VERSION
        start = time.perf_counter()
        matches = [r for r in records if r['assembly'] == 'GRCh38' and r['release_version'] == self.cache.manifest['clinvar_release']]
        if not matches:
            return {'prediction': None, 'prediction_reason': 'unsupported_source'}
        keys = {f"GRCh38:{r['chromosome']}:{r['position']}:{r['ref']}:{r['alt']}" for r in matches}
        if len(keys) != 1:
            return {'prediction': None, 'prediction_reason': 'ambiguous_source'}
        key = next(iter(keys))
        cache_key = (key, *self.identity)
        if cache_key in self.results:
            self.results.move_to_end(cache_key)
            result = deepcopy(self.results[cache_key])
            result['timings_ms'] = {'total': (time.perf_counter()-start)*1000, 'cache_hit': True}
            return result
        record = matches[0]
        ref, alt = record['ref'], record['alt']
        if not ref or not alt or set(ref+alt)-set('ACGT') or max(len(ref),len(alt)) > 50:
            return {'prediction': None, 'prediction_reason': 'unsupported_variant'}
        try:
            # Only exact normalized alleles in the frozen cache are supported. No live reannotation.
            raw = self.cache.features_for(key)
        except KeyError:
            return {'prediction': None, 'prediction_reason': 'annotation_missing'}
        except ValueError:
            return {'prediction': None, 'prediction_reason': 'features_invalid'}
        matrix = np.asarray(self.saved.processor.transform([raw]))[:, self.saved.columns]
        if self.enrichment is not None:
            if key not in self.enrichment:
                return {'prediction': None, 'prediction_reason': 'annotation_missing'}
            extra = self.enrichment[key]
            value = extra['phylop100way_snv']
            if (value is not None and not np.isfinite(value)) or extra['phylop100way_snv_missing'] != float(value is None):
                return {'prediction': None, 'prediction_reason': 'features_invalid'}
            matrix = np.column_stack([matrix, [[self.conservation_median if value is None else value, float(value is None)]]])
            raw.update(extra)
        feature_end = time.perf_counter()
        engine = self.saved.engine
        margins = engine.model.predict(matrix, output_margin=True)
        scores = probabilities(margins, self.policy['calibration']['temperature'])
        decision = str(CLASS_ORDER[int(scores[0].argmax())])
        prediction = {'schema_version': 2, 'model_name': self.model_manifest['model_name'],
                      'model_version': self.model_manifest['model_version'], 'feature_schema_version': self.model_manifest.get('feature_schema_version', SCHEMA_VERSION),
                      'annotation_version': ':'.join(self.identity[1:]) if self.enrichment is not None else self.cache.manifest['annotation_version'], 'dataset_version': self.model_manifest['dataset_version'],
                      'decision': decision, 'class_scores': dict(zip(CLASS_ORDER, map(float,scores[0]))),
                      'probability_kind': self.policy['calibration']['probability_kind'],
                      'confidence_status': 'standard' if standard_mask(scores,self.policy['confidence_rule'])[0] else 'low',
                      'release_status': 'research_candidate_rejected', 'explanation': None, 'explanation_status': 'failed',
                      'source_record_id': record['record_id'], 'normalized_variant_key': key}
        if self.enrichment is not None:
            prediction.update(confidence_status='not_assessed', release_status=None)
        prediction_end = time.perf_counter()
        try:
            values, base, explained = engine.explain(matrix)
            payload = engine.payload(raw, matrix[0], values[0], base, explained[0], target=decision,
                                     per_sign=self.saved.manifest['config']['display_per_sign'])
            def convert(group):
                return {'feature': DISPLAY_NAMES.get(group['feature'], group['feature']), 'value': None, 'contribution': group['contribution'], 'members': group['members']}
            prediction['explanation'] = {k: payload[k] for k in ['base_value','explained_value','output_space','output_target','model_version','background_version']}
            prediction['explanation'].update(features=[convert(g) for g in payload['features']],
                                              display_features=[convert(g) for g in payload['display_features']])
            prediction['explanation_status'] = 'available'
        except Exception:
            LOGGER.exception('SHAP failed; retaining valid model scores')
        end = time.perf_counter()
        result = {'prediction': prediction, 'prediction_reason': None,
                  'timings_ms': {'features': (feature_end-start)*1000, 'prediction': (prediction_end-feature_end)*1000,
                                 'explanation': (end-prediction_end)*1000, 'total': (end-start)*1000, 'cache_hit': False}}
        if prediction['explanation_status'] == 'available':
            self.results[cache_key] = deepcopy(result)
            if len(self.results) > 128:
                self.results.popitem(last=False)
        return result

    def close(self):
        if self.cache is not None:
            self.executor.submit(self.cache.close).result()
        self.executor.shutdown(wait=True)
