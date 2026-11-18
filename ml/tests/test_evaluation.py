"""Calibration semantics and one-time holdout access, using synthetic data only."""

import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import numpy as np

from ml.calibration import (acceptance, choose_calibration, choose_confidence, confidence_summary,
                            fit_temperature, probabilities, standard_mask, summarize)
from ml.dataset_io import write_json
from ml.evaluate import CONFIG_PATH, calibrate, render, score_holdouts
from ml.evaluation_reports import bootstrap
from ml.features import FEATURE_NAMES
from ml.labels import CLASS_ORDER


class FakeInputs:
    """Deterministic synthetic predictions for exercising orchestration and access guards."""
    def __init__(self, root):
        self.splits=root/'splits';self.splits.mkdir()
        self.model_path=root/'model';self.model_path.mkdir()
        self.fingerprints={'synthetic':'only'}
        self.model_manifest={'model_name':'synthetic','model_version':'test','config':{'seed':1}}
        self.calls=[]
        candidate={'id':'logistic','algorithm':'logistic','C':1.0,'weighted':False,'population_features':True}
        write_json(self.model_path/'training_report.json',{'experiments':[{'candidate':candidate,'cv_mean_macro_f1':0.5,'cv_mean_log_loss':1.0}]})

    def load_partition(self,name):
        self.calls.append(name)
        labels=np.tile(np.arange(5),20)
        matrix=np.zeros((100,len(FEATURE_NAMES)))
        matrix[:,0]=labels
        metadata=[{'variant_key':f'{name}-{i}','label':str(CLASS_ORDER[label]),'variant_type':'snv','consequences':['missense_variant'],
                   'clinvar_variation_ids':[i+1],'representative_record_id':str(i)} for i,label in enumerate(labels)]
        return {'keys':[r['variant_key'] for r in metadata],'labels':labels,'matrix':matrix,'full_matrix':matrix,
                'metadata':metadata,'raw':[dict.fromkeys(FEATURE_NAMES,0.0) for _ in labels],
                'groups':['ONE' if name=='gene_challenge' else f'group{i%3}' for i in range(100)]}

    def logits(self,part):
        logits=np.zeros((len(part['labels']),5))
        logits[np.arange(len(logits)),part['matrix'][:,0].astype(int)]=1.5
        return logits

    def measure_latency(self,*args): return {'p95_ms':1.0,'scope':'synthetic test'}
    def review_stars(self,metadata): return [2]*len(metadata)


class EvaluationTest(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.config=json.loads(CONFIG_PATH.read_text());self.config['bootstrap_replicates']=5
        self.config_path=self.root/'protocol.json';write_json(self.config_path,self.config)
        self.y=np.tile(np.arange(5),10)
        self.logits=np.eye(5)[self.y]*2

    def test_temperature_is_normalized_preserves_decisions_and_does_not_fix_weak_class(self):
        original=probabilities(self.logits)
        scaled=probabilities(self.logits,2.0)
        np.testing.assert_allclose(scaled.sum(axis=1),1)
        np.testing.assert_array_equal(original.argmax(axis=1),scaled.argmax(axis=1))
        for temperature in [0,-1,float('nan')]:
            with self.assertRaises(ValueError): probabilities(self.logits,temperature)
        tied=probabilities(np.zeros((1,5)))
        self.assertEqual(tied.argmax(axis=1)[0],0)

    def test_temperature_fit_and_separate_selection_rejection(self):
        temperature=fit_temperature(self.logits,self.y,[0.25,4])
        self.assertLess(temperature,1)
        result=choose_calibration(self.logits,self.y,1.0,self.config)
        self.assertFalse(result['accepted'])
        self.assertEqual(result['probability_kind'],'uncalibrated')
        with self.assertRaises(ValueError):fit_temperature(self.logits[:4],self.y[:4],[0.25,4])

    def test_confidence_does_not_relabel_uncertain_or_other_classes(self):
        p=probabilities(self.logits)
        rule=choose_confidence(self.y,p,self.config['confidence_selection'])
        self.assertTrue(rule['accepted'])
        before=p.argmax(axis=1).copy()
        standard_mask(p,rule)
        np.testing.assert_array_equal(before,p.argmax(axis=1))
        rejected=choose_confidence(self.y,np.full((50,5),0.2),self.config['confidence_selection'])
        self.assertFalse(rejected['accepted'])
        result=confidence_summary(self.y,p,rejected)
        self.assertEqual(result['standard_count'],0)
        self.assertIsNone(result['standard_accuracy'])

    def test_severe_errors_use_separate_conditional_denominators(self):
        labels=np.array([0,1,2,3,4])
        p=np.eye(5)[[4,1,0,0,4]]
        result=summarize(labels,p)
        self.assertEqual(result['severe_confusion']['benign_to_pathogenic']['rate'],0.5)
        self.assertEqual(result['severe_confusion']['pathogenic_to_benign']['rate'],0.5)
        self.assertEqual(result['severe_confusion']['pathogenic_to_benign']['denominator'],2)
        self.assertEqual(len(result['one_vs_rest_average_precision']),5)
        self.assertAlmostEqual(result['multiclass_brier'],1.2)

    def test_missing_class_bootstrap_is_explicit_and_repeatable(self):
        p=probabilities(self.logits)
        first=bootstrap(self.y,p,['ONE']*50,self.config)
        second=bootstrap(self.y,p,['ONE']*50,self.config)
        self.assertEqual(first,second)
        self.assertIn('conditional',first['method'])
        self.assertEqual(first['connected_gene_components'],1)

    def test_weak_recall_cannot_pass_acceptance(self):
        p=np.full((50,5),0.05);p[:,1]=0.8
        result=summarize(self.y,p)
        confidence=confidence_summary(self.y,p,{'accepted':False})
        gates=acceptance(result,result,result,result,confidence,{'p95_ms':1},self.config)
        self.assertFalse(gates['recall_likely_pathogenic'])
        self.assertFalse(all(gates.values()))

    @patch('ml.evaluate.render_plots')
    def test_validation_freeze_first_access_and_report_rerender(self,plots):
        inputs=FakeInputs(self.root)
        policy_dir=self.root/'policy'
        policy=calibrate(inputs,None,policy_dir,self.config_path)
        self.assertEqual(inputs.calls,['validation','train'])
        self.assertFalse((inputs.splits/'evaluation_access.json').exists())
        self.assertNotEqual(policy['selection_partitions']['fit_keys_sha256'],policy['selection_partitions']['selection_keys_sha256'])
        output=self.root/'final'
        report=score_holdouts(inputs,policy_dir,output,self.config_path)
        self.assertEqual(inputs.calls,['validation','train','test','gene_challenge'])
        self.assertEqual(set(report['partitions']),{'test','gene_challenge'})
        self.assertEqual(report,render(output))
        self.assertEqual(inputs.calls,['validation','train','test','gene_challenge'])
        with self.assertRaises(FileExistsError):score_holdouts(inputs,policy_dir,self.root/'sneaky-retry',self.config_path)
        self.assertEqual(inputs.calls,['validation','train','test','gene_challenge'])
        with self.assertRaises(ValueError):calibrate(inputs,None,self.root/'new-policy',self.config_path)
        with (output/'heldout_predictions.json').open('a') as stream:stream.write(' ')
        with self.assertRaises(ValueError):render(output)

    def test_protocol_edit_is_rejected_before_any_holdout_access(self):
        inputs=FakeInputs(self.root);policy_dir=self.root/'policy'
        calibrate(inputs,None,policy_dir,self.config_path)
        changed=copy.deepcopy(self.config);changed['acceptance']['minimum_recall_each_class']=0
        write_json(self.config_path,changed)
        with self.assertRaises(ValueError):score_holdouts(inputs,policy_dir,self.root/'final',self.config_path)
        self.assertEqual(inputs.calls,['validation','train'])
        self.assertFalse((inputs.splits/'evaluation_access.json').exists())


if __name__=='__main__':unittest.main()
