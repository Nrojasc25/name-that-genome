"""Feature semantics, leakage resistance, cache integrity, and train-only preprocessing."""

import unittest

import pyarrow.parquet as pq

from ml.annotate import AnnotationCache, annotate_variant, build_cache, parse_frequency
from ml.build_dataset import build as build_dataset
from ml.build_features import build as export_features
from ml.features import FEATURE_NAMES, build_features
from ml.preprocessing import TrainingPreprocessor
from ml.tests import test_dataset


class FeaturesTest(unittest.TestCase):
    def setUp(self):
        test_dataset.DatasetTest.setUp(self)
        self.variant = {'variant_key': 'GRCh38:1:7:G:T', 'assembly': 'GRCh38', 'chromosome': '1', 'position': 7, 'ref': 'G', 'alt': 'T', 'source_record_ids': ['r']}
        self.annotation = {'variant_key': self.variant['variant_key'], 'consequences': ['missense_variant'],
                           'frequencies': {'AF_ESP': 0.0, 'AF_EXAC': None, 'AF_TGP': 0.1}, 'context_gc_fraction': 0.5}

    def test_features_have_fixed_order_and_no_clinical_columns(self):
        row = build_features(self.variant, self.annotation)
        self.assertEqual(tuple(row), FEATURE_NAMES)
        for forbidden in ['label','class_id','position','chromosome','genes','review_stars','conditions','variant_key']:
            self.assertNotIn(forbidden, row)
        self.assertEqual(row['substitution_C_to_A'], 1)
        self.assertEqual(row['consequence_missense_variant'], 1)

    def test_label_and_review_mutations_cannot_change_features(self):
        expected = build_features(self.variant, self.annotation)
        for label in ['Benign','Pathogenic','Likely pathogenic','Uncertain significance']:
            variant = {**self.variant, 'label': label, 'review_stars': 4, 'genes': ['SECRET'], 'conditions': ['DISEASE']}
            annotation = {**self.annotation, 'clinvar_classification': label, 'class_id': 4}
            self.assertEqual(expected, build_features(variant, annotation))

    def test_zero_is_not_missing(self):
        row = build_features(self.variant, self.annotation)
        self.assertEqual((row['af_esp'], row['af_esp_missing']), (0.0, 0.0))
        self.assertEqual((row['af_exac'], row['af_exac_missing']), (None, 1.0))

    def test_frequency_validation_and_duplicates(self):
        self.assertEqual(parse_frequency(['0',None,'.']), (0.0, 'observed'))
        self.assertEqual(parse_frequency(['0.2','0.20']), (0.2, 'observed'))
        self.assertEqual(parse_frequency(['0.2','0.3']), (None, 'conflicting'))
        self.assertEqual(parse_frequency([None,'.','']), (None, 'missing'))
        for value in ['nan','inf','-1','1.5','0.1,0.2',True,[],{}]:
            with self.subTest(value=value):
                self.assertEqual(parse_frequency([value]), (None, 'invalid'))

    def test_unknown_consequences_do_not_change_schema(self):
        annotation = {**self.annotation, 'consequences': ['future_term']}
        row = build_features(self.variant, annotation)
        self.assertEqual(row['consequence_other'], 1)
        self.assertEqual(row['consequence_missing'], 0)
        annotation['consequences'] = []
        self.assertEqual(build_features(self.variant, annotation)['consequence_missing'], 1)

    def test_indels_and_nonapplicable_substitution(self):
        variant = {**self.variant, 'ref':'G', 'alt':'GA', 'variant_key':'GRCh38:1:7:G:GA'}
        annotation = {**self.annotation, 'variant_key':variant['variant_key']}
        row = build_features(variant, annotation)
        self.assertEqual(row['length_change'],1)
        self.assertEqual(row['is_insertion'],1)
        self.assertEqual(sum(v for k,v in row.items() if k.startswith('substitution_')),0)

    def test_reference_context_boundary_and_observed(self):
        import pysam
        with pysam.FastaFile(str(self.fasta)) as fasta:
            annotation = annotate_variant(self.variant, {'r':{}}, {}, fasta)
            self.assertIsNone(annotation['context_gc_fraction'])
            self.assertEqual(annotation['context_status'],'boundary')
            variant = {**self.variant,'position':30,'ref':'A','alt':'T','variant_key':'GRCh38:1:30:A:T'}
            annotation = annotate_variant(variant, {'r':{}}, {}, fasta)
            self.assertEqual(annotation['context_gc_fraction'], 0)
            self.assertEqual(annotation['context_status'],'observed')

    def test_bad_identity_or_values_fail_closed(self):
        with self.assertRaises(ValueError):
            build_features({**self.variant,'position':8}, self.annotation)
        with self.assertRaises(ValueError):
            build_features(self.variant, {**self.annotation,'context_gc_fraction':float('nan')})

    def test_imputer_only_uses_explicit_training_rows(self):
        base = build_features(self.variant,self.annotation)
        first = {**base,'af_exac':0.1,'af_exac_missing':0}
        second = {**base,'af_exac':0.3,'af_exac_missing':0}
        heldout = {**base,'af_exac':1.0,'af_exac_missing':0}
        model = TrainingPreprocessor.fit({'train1':first,'train2':second,'heldout':heldout},training_keys=['train1','train2'],annotation_version='synthetic')
        self.assertAlmostEqual(model.artifact['fill_values']['af_exac'],0.2)
        self.assertEqual(model.artifact['training_count'],2)
        self.assertIn('af_exac_missing', model.artifact['feature_names'])
        path = self.root/'preprocessor.json';model.save(path)
        self.assertEqual(model.transform([base]),TrainingPreprocessor.load(path).transform([base]))
        self.assertAlmostEqual(model.transform([base])[0][FEATURE_NAMES.index('af_exac')],0.2)

    def test_imputer_rejects_extra_columns_and_missing_training_keys(self):
        base = build_features(self.variant,self.annotation)
        with self.assertRaises(ValueError):
            TrainingPreprocessor.fit({'x':{**base,'label':1}},training_keys=['x'],annotation_version='synthetic')
        for keys in [[],['x','x'],['missing']]:
            with self.assertRaises(ValueError):
                TrainingPreprocessor.fit({'x':base},training_keys=keys,annotation_version='synthetic')
        model=TrainingPreprocessor.fit({'x':base},training_keys=['x'],annotation_version='synthetic')
        self.assertEqual(model.artifact['fill_values']['af_exac'],0)
        self.assertIn('af_exac',model.artifact['all_missing_training_features'])

    def test_full_cache_batch_single_parity_and_reproducibility(self):
        database = test_dataset.DatasetTest.make_database(self)
        dataset = self.root/'dataset'
        build_dataset(database,self.fasta,self.reference_manifest,dataset,self.config_path)
        manifests=[]
        for number in [1,2]:
            cache_dir=self.root/f'cache{number}'
            manifest=build_cache(dataset,database,self.fasta,cache_dir)
            manifests.append(manifest)
            output=self.root/f'features{number}'
            feature_manifest=export_features(dataset,cache_dir,output)
            keys=pq.read_table(output/'feature_rows.parquet')['variant_key'].to_pylist()
            matrix=pq.read_table(output/'features.parquet').to_pylist()
            cache=AnnotationCache(cache_dir,expected_version=manifest['annotation_version'])
            try:
                self.assertEqual(matrix,[cache.features_for(key) for key in keys])
                with self.assertRaises(KeyError): cache.features_for('unknown')
                model=TrainingPreprocessor.fit(dict(zip(keys,matrix)),training_keys=keys[:2],annotation_version=manifest['annotation_version'])
                self.assertEqual(model.transform([matrix[0]])[0],model.transform_from_cache(cache,keys[0]))
                model.artifact['annotation_version']='wrong'
                with self.assertRaises(ValueError): model.transform_from_cache(cache,keys[0])
            finally:
                cache.close()
            self.assertFalse(feature_manifest['preprocessing_fitted'])
        self.assertEqual(manifests[0]['annotation_version'],manifests[1]['annotation_version'])
        self.assertEqual(manifests[0]['cache_sha256'],manifests[1]['cache_sha256'])
        with self.assertRaises(ValueError):
            AnnotationCache(self.root/'cache1',expected_version='wrong')
        with (self.root/'cache1'/'annotations.sqlite').open('ab') as stream: stream.write(b'corrupted')
        with self.assertRaises(ValueError):
            AnnotationCache(self.root/'cache1',expected_version=manifests[0]['annotation_version'])


if __name__=='__main__':
    unittest.main()
