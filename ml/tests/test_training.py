"""Split isolation, training protocol, artifact persistence, and multiclass compatibility."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
import warnings

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq
from xgboost import XGBClassifier

from ml.dataset_io import digest, write_json
from ml.features import CONFIG_PATH as FEATURE_CONFIG_PATH, FEATURE_NAMES
from ml.labels import CLASS_ORDER
from ml.split_data import CONFIG_PATH, connected_gene_groups, freeze, make_splits
from ml.train import make_model, fit_model, metrics, read_training_inputs, run, select_candidate, selected_columns


class TrainingTest(unittest.TestCase):
    def setUp(self):
        self.config = json.loads(CONFIG_PATH.read_text())
        self.config['gene_challenge_minimum_per_class'] = 2
        self.config['minimum_primary_per_class'] = 10
        self.rows = [{'variant_key': f'GRCh38:1:{group * 1000 + c * 20 + n + 1}:A:T',
                      'genes': [f'GENE{group}'], 'label': str(label)}
                     for group in range(4) for c, label in enumerate(CLASS_ORDER) for n in range(12)]
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_connected_gene_groups_include_transitive_multigene_links(self):
        rows = [{'variant_key': 'a', 'genes': ['A','B']}, {'variant_key':'b','genes':['B','C']},
                {'variant_key':'c','genes':['D']}, {'variant_key':'d','genes':[]}]
        groups = connected_gene_groups(rows)
        self.assertEqual(groups['a'], groups['b'])
        self.assertNotEqual(groups['a'], groups['c'])
        self.assertEqual(groups['d'], '')

    def test_splits_repeat_without_variant_or_challenge_gene_overlap(self):
        membership, report = make_splits(self.rows,self.config)
        reversed_membership, other_report = make_splits(list(reversed(self.rows)),self.config)
        self.assertEqual(membership,reversed_membership)
        self.assertEqual(report,other_report)
        self.assertEqual(len(membership),len({r['variant_key'] for r in membership}))
        self.assertEqual(report['challenge_gene_overlap'],[])
        for counts in report['partitions'].values():
            self.assertGreater(min(counts['class_counts'].values()),0)
        for row in membership:
            self.assertEqual(row['cv_fold'] is not None,row['partition']=='train')

    def test_duplicate_variants_and_impossible_gene_challenge_fail(self):
        with self.assertRaises(ValueError): make_splits(self.rows+[self.rows[0]],self.config)
        rows = [{**r,'genes':['ONE_GENE']} for r in self.rows]
        with self.assertRaises(ValueError): make_splits(rows,self.config)

    def test_candidate_selection_is_predeclared_and_ignores_heldout_fields(self):
        examples = [dict(candidate={'id':'a'},status='complete',cv_mean_macro_f1=.4,cv_mean_log_loss=1.1,test_f1=1),
                    dict(candidate={'id':'b'},status='complete',cv_mean_macro_f1=.5,cv_mean_log_loss=1.2,test_f1=0)]
        self.assertEqual(select_candidate(examples)['candidate']['id'],'b')
        examples[0]['cv_mean_macro_f1']=.5
        self.assertEqual(select_candidate(examples)['candidate']['id'],'a')

    def test_population_ablation_removes_values_and_missing_flags(self):
        indices=selected_columns({'population_features':False})
        self.assertEqual(len(indices),len(FEATURE_NAMES)-6)
        self.assertFalse(any(FEATURE_NAMES[i].startswith('af_') for i in indices))

    def test_probabilities_and_logistic_fold_scaling(self):
        candidate={'algorithm':'logistic','C':1.0,'weighted':True}
        x=np.arange(300,dtype=float).reshape(50,6)
        y=np.tile(np.arange(5),10)
        model=fit_model(make_model(candidate,1),candidate,x,y)
        self.assertTrue(np.allclose(model.named_steps['scale'].mean_,x.mean(axis=0)))
        result=metrics(y,model.predict_proba(x))
        self.assertIn('macro_f1',result)
        with self.assertRaises(ValueError): metrics(y,np.ones((50,5)))

    def test_float32_roundoff_is_normalized_for_metrics_only(self):
        probabilities=np.full((5,5),np.float32(0.2)).astype(float)
        with warnings.catch_warnings():
            warnings.simplefilter('error',UserWarning)
            self.assertTrue(np.isfinite(metrics(np.arange(5),probabilities)['log_loss']))
        with self.assertRaises(ValueError): metrics(np.arange(5),probabilities * 1.00001)

    def test_multiclass_xgboost_shap_raw_additivity(self):
        import shap
        rng=np.random.default_rng(8)
        x=rng.normal(size=(50,6)); y=np.tile(np.arange(5),10)
        model=XGBClassifier(n_estimators=3,max_depth=2,num_class=5,objective='multi:softprob',n_jobs=2,random_state=8)
        model.fit(x,y)
        explainer=shap.TreeExplainer(model,model_output='raw')
        values=explainer.shap_values(x[:5])
        self.assertEqual(values.shape,(5,6,5))
        np.testing.assert_allclose(np.sum(values,axis=1)+np.asarray(explainer.expected_value),model.predict(x[:5],output_margin=True),atol=1e-5)

    def prepare_artifacts(self):
        dataset=self.root/'dataset';dataset.mkdir()
        features=self.root/'features';features.mkdir()
        self.config['candidates']=[{'id':'dummy','algorithm':'dummy','weighted':False,'population_features':True}]
        config_path=self.root/'config.json';write_json(config_path,self.config)
        pq.write_table(pa.Table.from_pylist(self.rows),dataset/'variants.parquet')
        checksum=digest(dataset/'variants.parquet')
        write_json(dataset/'dataset_manifest.json',{'dataset_version':'synthetic','class_order':list(CLASS_ORDER),'outputs_sha256':{'variants.parquet':checksum}})
        matrix=[dict.fromkeys(FEATURE_NAMES,0.0) for _ in self.rows]
        pq.write_table(pa.Table.from_pylist(matrix),features/'features.parquet')
        pq.write_table(pa.table({'variant_key':[r['variant_key'] for r in self.rows]}),features/'feature_rows.parquet')
        write_json(features/'feature_manifest.json',{'dataset_variants_sha256':checksum,'annotation_version':'synthetic','feature_config_sha256':digest(FEATURE_CONFIG_PATH),
                   'feature_names':list(FEATURE_NAMES),'schema_version':'1.0.0','outputs_sha256':{p.name:digest(p) for p in features.iterdir()}})
        splits=self.root/'splits';freeze(dataset,splits,config_path)
        return dataset,features,splits,config_path

    def test_training_loader_returns_only_training_rows_and_does_not_score_holdouts(self):
        dataset,features,splits,config=self.prepare_artifacts()
        vectors,targets,folds,_=read_training_inputs(dataset,features,splits,self.config)
        membership=pq.read_table(splits/'membership.parquet').to_pylist()
        train_keys={r['variant_key'] for r in membership if r['partition']=='train'}
        self.assertEqual(set(vectors),train_keys)
        self.assertEqual(set(targets),train_keys)
        self.assertEqual(set(folds),train_keys)
        output=self.root/'model'
        manifest=run(dataset,features,splits,output,config)
        self.assertEqual(manifest['training_count'],len(train_keys))
        oof=pq.read_table(output/'training_oof.parquet').to_pylist()
        self.assertEqual({r['variant_key'] for r in oof},train_keys)
        self.assertFalse(json.loads((output/'training_report.json').read_text())['held_out_predictions_generated'])
        self.assertEqual(json.loads((output/'preprocessor.json').read_text())['training_count'],len(train_keys))
        with self.assertRaises(FileExistsError): run(dataset,features,splits,output,config)

    def test_mismatched_feature_mapping_and_changed_protocol_fail(self):
        dataset,features,splits,config=self.prepare_artifacts()
        changed=copy.deepcopy(self.config);changed['seed']+=1
        with self.assertRaises(ValueError):read_training_inputs(dataset,features,splits,changed)
        with (features/'features.parquet').open('ab') as stream:stream.write(b'corruption')
        with self.assertRaises(ValueError):read_training_inputs(dataset,features,splits,self.config)


if __name__=='__main__':
    unittest.main()
