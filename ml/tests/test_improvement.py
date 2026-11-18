import unittest
import tempfile
from pathlib import Path
import json
import numpy as np
from ml.improve import sample_weights, feature_collisions, select, extend_features
from ml.conservation import feature, windows, fetch


class ImprovementTests(unittest.TestCase):
    def test_fold_local_weights_and_multiplier(self):
        labels=np.array([0,0,1,2,3,4])
        weights=sample_weights(labels,{'balanced':True,'likely_pathogenic_weight':2})
        self.assertAlmostEqual(weights.mean(),1)
        self.assertAlmostEqual(weights[4]/weights[2],2)
        self.assertAlmostEqual(weights[2]/weights[0],2)
        with self.assertRaises(ValueError): sample_weights(labels,{'balanced':False,'likely_pathogenic_weight':0})

    def test_identical_features_with_conflicting_labels(self):
        result=feature_collisions(np.array([[1,0],[1,0],[1,0],[0,1]]),np.array([0,3,3,4]))
        self.assertEqual(result['distinct_vectors'],2)
        self.assertEqual(result['rows_in_conflicting_groups'],3)
        self.assertEqual(result['likely_pathogenic_rows_in_conflicting_groups'],2)
        self.assertEqual(result['empirical_maximum_deterministic_accuracy'],.75)

    def test_conservation_coordinates_and_missingness(self):
        key='GRCh38:12:101:A:G'
        self.assertEqual(feature(key,{('12',100):4.5})['phylop100way_snv'],4.5)
        self.assertIsNone(feature('GRCh38:12:101:AT:A',{('12',100):4.5})['phylop100way_snv'])
        self.assertEqual(windows([key]),[('12',100,101)])
        extra={'a':{'phylop100way_snv':2.,'phylop100way_snv_missing':0.},
               'b':{'phylop100way_snv':None,'phylop100way_snv_missing':1.},
               'c':{'phylop100way_snv':100.,'phylop100way_snv_missing':0.}}
        _,score,fill=extend_features(extra,['a'],['b','c'])
        self.assertEqual(fill,2.)
        self.assertEqual(score[0].tolist(),[2.,1.])
        self.assertEqual(score[1].tolist(),[100.,0.])

    def test_cached_conservation_rejects_wrong_region_or_truncation(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory=Path(temporary)
            path=directory/'12-100-101.json'
            response={'genome':'hg38','chrom':'chr12','start':100,'end':101,'track':'phyloP100way',
                      'phyloP100way':[],'itemsReturned':1}
            path.write_text(json.dumps(response))
            with self.assertRaisesRegex(ValueError,'Truncated'): fetch(('12',100,101),directory)
            response['itemsReturned']=0;response['genome']='hg19';path.write_text(json.dumps(response))
            with self.assertRaisesRegex(ValueError,'region/source'): fetch(('12',100,101),directory)

    def test_all_missing_enrichment_never_fits_score_rows(self):
        extra={'fit':{'phylop100way_snv':None,'phylop100way_snv_missing':1.},
               'score':{'phylop100way_snv':8.,'phylop100way_snv_missing':0.}}
        fit,score,fill=extend_features(extra,['fit'],['score'])
        self.assertEqual(fill,0.)
        self.assertEqual(fit.tolist(),[[0.,1.]])
        self.assertEqual(score.tolist(),[[8.,0.]])

    def test_no_selection_when_recall_or_severe_gate_fails(self):
        high={'candidate':{'id':'high'},'mean_fold_macro_f1':.9,'mean_fold_log_loss':.2,'discrimination_gates':{'recall':False}}
        self.assertIsNone(select([high]))
        eligible={'candidate':{'id':'eligible'},'mean_fold_macro_f1':.7,'mean_fold_log_loss':.3,'discrimination_gates':{'recall':True}}
        self.assertEqual(select([high,eligible])['candidate']['id'],'eligible')


if __name__=='__main__': unittest.main()
