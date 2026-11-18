"""Verify frozen artifacts and read labels only for explicitly requested partitions."""

import json
from pathlib import Path
import time
import platform

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from xgboost import XGBClassifier

from .annotate import AnnotationCache
from .dataset_io import digest
from .features import FEATURE_NAMES, CONFIG_PATH
from .labels import CLASS_ORDER
from .preprocessing import TrainingPreprocessor


class EvaluationInputs:
    def __init__(self, dataset: Path, features: Path, splits: Path, model: Path):
        self.dataset, self.features, self.splits, self.model_path = dataset, features, splits, model
        self.dataset_manifest = json.loads((dataset / 'dataset_manifest.json').read_text())
        self.feature_manifest = json.loads((features / 'feature_manifest.json').read_text())
        self.split_manifest = json.loads((splits / 'split_manifest.json').read_text())
        self.model_manifest = json.loads((model / 'model_manifest.json').read_text())
        for directory, manifest, files in [
            (dataset,self.dataset_manifest,['variants.parquet','source_membership.parquet']),
            (features,self.feature_manifest,['features.parquet','feature_rows.parquet']),
            (splits,self.split_manifest,['membership.parquet']),
            (model,self.model_manifest,[self.model_manifest['model_file'],'preprocessor.json','training_report.json'])]:
            for name in files:
                if digest(directory / name) != manifest['outputs_sha256'][name]:
                    raise ValueError('Artifact checksum mismatch: ' + name)
        checksum = self.dataset_manifest['outputs_sha256']['variants.parquet']
        if self.split_manifest['dataset_variants_sha256'] != checksum or self.feature_manifest['dataset_variants_sha256'] != checksum:
            raise ValueError('Dataset/feature/split mismatch')
        if self.model_manifest['split_id'] != self.split_manifest['split_id'] or self.model_manifest['feature_manifest_sha256'] != digest(features / 'feature_manifest.json'):
            raise ValueError('Model does not match frozen split/features')
        if self.feature_manifest['feature_config_sha256'] != digest(CONFIG_PATH) or self.feature_manifest['feature_names'] != list(FEATURE_NAMES):
            raise ValueError('Feature schema/configuration mismatch')
        if self.model_manifest['class_order'] != list(CLASS_ORDER):
            raise ValueError('Class order mismatch')
        if self.model_manifest['candidate']['algorithm'] != 'xgboost':
            raise ValueError('This temperature workflow supports the selected XGBoost candidate only')
        self.model = XGBClassifier(n_jobs=2)
        self.model.load_model(model / self.model_manifest['model_file'])
        self.model.set_params(n_jobs=2)
        self.processor = TrainingPreprocessor.load(model / 'preprocessor.json')
        if self.processor.artifact['annotation_version'] != self.feature_manifest['annotation_version']:
            raise ValueError('Preprocessor annotation mismatch')
        self.columns = self.model_manifest['selected_feature_indices']
        self.memberships = pq.read_table(splits / 'membership.parquet').to_pylist()
        self.membership = {r['variant_key']:r for r in self.memberships}
        keys = pq.read_table(features / 'feature_rows.parquet')['variant_key'].to_pylist()
        self.raw = pq.read_table(features / 'features.parquet')
        if len(keys) != len(set(keys)) or len(self.membership) != len(self.memberships) or set(keys) != set(self.membership):
            raise ValueError('Nonunique or inconsistent membership keys')
        if self.raw.num_rows != len(keys) or self.raw.column_names != list(FEATURE_NAMES):
            raise ValueError('Feature rows misaligned')
        self.indices = {k:i for i,k in enumerate(keys)}
        self.fingerprints = {'dataset_variants_sha256':checksum,'feature_manifest_sha256':digest(features / 'feature_manifest.json'),
                             'split_manifest_sha256':digest(splits / 'split_manifest.json'), 'model_manifest_sha256':digest(model / 'model_manifest.json')}

    def load_partition(self, partition):
        if partition not in {'train','validation','test','gene_challenge'}:
            raise ValueError('Unknown partition')
        keys = sorted(k for k,r in self.membership.items() if r['partition'] == partition)
        if not keys:
            raise ValueError('Empty partition')
        records = pq.read_table(self.dataset / 'variants.parquet', filters=[('variant_key','in',keys)]).to_pylist()
        by_key = {r['variant_key']:r for r in records}
        if set(by_key) != set(keys):
            raise ValueError('Partition labels incomplete')
        metadata = [by_key[k] for k in keys]
        labels = np.array([CLASS_ORDER.index(r['label']) for r in metadata])
        raw = self.raw.take(pa.array([self.indices[k] for k in keys])).to_pylist()
        full = np.array(self.processor.transform(raw))
        return {'keys':keys,'labels':labels,'metadata':metadata,'raw':raw,'full_matrix':full,'matrix':full[:,self.columns],
                'groups':[self.membership[k]['gene_group'] or k for k in keys]}

    def logits(self, partition):
        return self.model.predict(partition['matrix'], output_margin=True)

    def review_stars(self, metadata):
        ids = [r['representative_record_id'] for r in metadata]
        records = pq.read_table(self.dataset / 'source_membership.parquet',columns=['record_id','review_stars'],filters=[('record_id','in',ids)]).to_pylist()
        mapping = {r['record_id']:r['review_stars'] for r in records}
        return [mapping[i] for i in ids]

    def measure_latency(self, cache_path, keys, temperature, config):
        from .calibration import probabilities
        cache = AnnotationCache(cache_path, expected_version=self.feature_manifest['annotation_version'])
        timings = []
        try:
            for i in range(config['latency_warmup'] + config['latency_repeats']):
                start = time.perf_counter()
                raw = cache.features_for(keys[i % len(keys)])
                matrix = np.array(self.processor.transform([raw]))[:,self.columns]
                probabilities(self.model.predict(matrix,output_margin=True),temperature)
                duration = (time.perf_counter() - start) * 1000
                if i >= config['latency_warmup']:
                    timings.append(duration)
        finally:
            cache.close()
        return {'p50_ms':float(np.percentile(timings,50)),'p95_ms':float(np.percentile(timings,95)),
                'samples':len(timings),'platform':platform.platform(),'machine_label':config['latency_machine'],
                'scope':'Warm single-variant cache lookup + imputation + XGBoost + temperature; excludes startup, network, API and SHAP.'}
