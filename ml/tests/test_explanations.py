import unittest
import tempfile
from pathlib import Path

import numpy as np
from xgboost import XGBClassifier

from ml.build_explanations import sample_training
from ml.explain import ClassExplainer, SavedExplainer, display_features, grouped_features
from ml.features import FEATURE_NAMES
from ml.preprocessing import TrainingPreprocessor
from ml.dataset_io import digest, write_json
from ml.labels import CLASS_ORDER


class ExplanationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        rng = np.random.default_rng(42)
        cls.x = rng.normal(size=(150, 4))
        y = np.argmax(np.column_stack([cls.x, -cls.x.sum(axis=1)]), axis=1)
        cls.model = XGBClassifier(n_estimators=10, max_depth=2, n_jobs=2, random_state=42,
                                  objective='multi:softprob', num_class=5)
        cls.model.fit(cls.x, y)
        cls.engine = ClassExplainer(cls.model, ['a','b','c','d'], cls.x[:50], model_version='test', background_version='train-test')

    def test_all_class_additivity_baseline_and_targets(self):
        x = self.x[100:110]
        values, base, margins = self.engine.explain(x)
        np.testing.assert_allclose(base, self.model.predict(self.x[:50], output_margin=True).mean(axis=0), atol=1e-5)
        np.testing.assert_allclose(values.sum(1) + base, margins, atol=1e-5)
        for i in range(len(x)):
            raw = dict(zip(['a','b','c','d'], x[i]))
            for c, name in enumerate(CLASS_ORDER):
                p = self.engine.payload(raw, x[i], values[i], base, margins[i], name, per_sign=1)
                self.assertEqual(p['output_target'], name)
                self.assertEqual(p['output_space'], 'raw_score')
                self.assertAlmostEqual(p['base_value'] + sum(g['contribution'] for g in p['display_features']), margins[i,c], places=5)
            p = self.engine.payload(raw, x[i], values[i], base, margins[i])
            self.assertEqual(p['output_target'], CLASS_ORDER[np.argmax(margins[i])])
        self.assertTrue(np.any(values > 0))
        self.assertTrue(np.any(values < 0))

    def test_signs_grouping_missing_values_and_remainder(self):
        names = ['substitution_C_to_A','substitution_C_to_G','af_exac','af_exac_missing','length_change']
        raw = dict(zip(names,[1,0,None,1,2]))
        groups = grouped_features(names,raw,[1,0,.1,1,2],[2,-.5,-1,.2,-.1])
        self.assertEqual(groups[0]['contribution'],1.5)
        missing = next(g for g in groups if g['feature']=='af_exac')['members'][0]
        self.assertIsNone(missing['value'])
        self.assertEqual(missing['model_value'],.1)
        visible = display_features(groups,1)
        self.assertEqual([g['feature'] for g in visible],['SNV substitution','af_exac','Other features'])
        self.assertAlmostEqual(sum(g['contribution'] for g in visible), .6)
        self.assertGreater(visible[0]['contribution'],0)
        self.assertLess(visible[1]['contribution'],0)

    def test_invalid_inputs_and_targets_fail(self):
        with self.assertRaises(ValueError): self.engine.explain([[np.nan]*4])
        with self.assertRaises(ValueError): self.engine.explain([[1,2]])
        with self.assertRaises(ValueError): display_features([],0)
        v,b,m = self.engine.explain(self.x[:1])
        with self.assertRaises(ValueError): self.engine.payload({},self.x[0],v[0],b,m[0],'disease')
        with self.assertRaises(ValueError): self.engine.payload(dict(zip(['a','b','c','d'],self.x[0])),self.x[0],v[0]+1,b,m[0])

    def test_saved_reload_and_checksum_rejection(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            model_dir = root / 'model'; model_dir.mkdir()
            explanation_dir = root / 'explanations'; explanation_dir.mkdir()
            vectors = {str(i): dict.fromkeys(FEATURE_NAMES, 0.0) for i in range(50)}
            for i in range(50):
                for j, name in enumerate(FEATURE_NAMES[:4]):
                    vectors[str(i)][name] = float(self.x[i,j])
            processor = TrainingPreprocessor.fit(vectors, training_keys=list(vectors), annotation_version='synthetic')
            processor.save(model_dir / 'preprocessor.json')
            x = np.asarray(processor.transform(list(vectors.values())))
            model = XGBClassifier(n_estimators=3, n_jobs=2, objective='multi:softprob', num_class=5)
            model.fit(x, np.tile(np.arange(5),10))
            model.save_model(model_dir / 'model.ubj')
            write_json(model_dir / 'model_manifest.json', {'class_order': list(CLASS_ORDER), 'model_file': 'model.ubj',
                'model_version': 'synthetic', 'selected_feature_indices': list(range(len(FEATURE_NAMES))),
                'outputs_sha256': {p.name: digest(p) for p in model_dir.iterdir()}})
            np.save(explanation_dir / 'background.npy', x[:10])
            write_json(explanation_dir / 'background_membership.json', list(vectors)[:10])
            write_json(explanation_dir / 'shap_manifest.json', {'class_order': list(CLASS_ORDER),
                'input_fingerprints': {'model_manifest_sha256': digest(model_dir / 'model_manifest.json')},
                'feature_names': list(FEATURE_NAMES), 'background_version': 'synthetic',
                'config': {'additivity_atol': 1e-4, 'display_per_sign': 3},
                'outputs_sha256': {p.name: digest(p) for p in explanation_dir.iterdir()}})
            original = ClassExplainer(model, FEATURE_NAMES, x[:10], model_version='synthetic', background_version='synthetic')
            loaded = SavedExplainer(model_dir, explanation_dir)
            for before, after in zip(original.explain(x[10:15]), loaded.engine.explain(x[10:15])):
                np.testing.assert_array_equal(before, after)
            with (explanation_dir / 'background.npy').open('ab') as stream:
                stream.write(b'corrupted')
            with self.assertRaisesRegex(ValueError, 'Background artifact checksum'):
                SavedExplainer(model_dir, explanation_dir)

    def test_training_sample_deterministic_unique_and_bounded(self):
        training = {'keys':[str(i) for i in range(200)]}
        a = sample_training(training,100,42)
        np.testing.assert_array_equal(a,sample_training(training,100,42))
        self.assertEqual(len(set(a)),100)
        with self.assertRaises(ValueError): sample_training(training,101,42)


if __name__ == '__main__':
    unittest.main()
