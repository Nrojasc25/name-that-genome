import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from backend import app_database as store
from backend.main import AnalysisResponse, HistoryResponse, predict_variant
from backend.prediction import Prediction
from ml.label_report import build_report
from ml.labels import CLASS_ORDER, POLICY, classify_label

FIXTURES = Path(__file__).parent / "fixtures"


class LabelsTest(unittest.TestCase):
    def test_all_five_exact_labels_and_vcf_encoding(self):
        for raw, label in POLICY["exact_labels"].items():
            for text in [raw, raw.upper(), '  ' + raw.replace(' ', '  ') + '\t', raw.replace(' ', '_')]:
                with self.subTest(text=text):
                    result = classify_label(text, 1)
                    self.assertEqual(result.label, label)
                    self.assertEqual(result.class_id, CLASS_ORDER.index(label))
                    self.assertIsNone(result.exclusion_reason)

    def test_exclusion_fixtures(self):
        rows = [json.loads(line) for line in (FIXTURES / 'label_examples.jsonl').read_text().splitlines()]
        for row in rows:
            with self.subTest(row=row):
                result = classify_label(row['classification'], row['review_stars'], row.get('classification_type', 'germline'))
                self.assertEqual(result.exclusion_reason, row['expected_reason'])
                self.assertEqual(result.label, row.get('expected_label'))
        report = build_report(rows)
        self.assertEqual(report['total'], report['included'] + report['excluded'])
        self.assertEqual(report['included'], 5)
        self.assertEqual(set(report['class_counts']), set(CLASS_ORDER))
        self.assertTrue(all(x['exclusion_reason'] for x in report['records'] if x['label'] is None))

    def test_review_star_validation_and_threshold(self):
        for stars in [None, True, 1.5, '1', -1, 5]:
            self.assertEqual(classify_label('Pathogenic', stars).exclusion_reason, 'invalid_review_stars')
        self.assertEqual(classify_label('Pathogenic', 0).exclusion_reason, 'insufficient_review_stars')
        for stars in [1, 2, 3, 4]:
            self.assertEqual(classify_label('Pathogenic', stars).label, 'pathogenic')

    def test_no_substring_or_confidence_label_inference(self):
        for label in ['uncertain', 'low confidence', 'not pathogenic', 'pathogenic;benign', 'VUS', 'likely pathogenic, low penetrance']:
            self.assertEqual(classify_label(label, 3).exclusion_reason, 'unsupported_classification')
        self.assertEqual(classify_label(123, 1).exclusion_reason, 'invalid_classification')

    def test_frontend_canonical_order_matches(self):
        source = (Path(__file__).parents[2] / 'frontend/src/lib/analysis.ts').read_text()
        line = source.splitlines()[0]
        self.assertEqual(json.loads(line.split('= ', 1)[1].removesuffix(' as const').replace("'", '"')), list(CLASS_ORDER))


class ContractTest(unittest.TestCase):
    def setUp(self):
        self.fixtures = json.loads((FIXTURES / 'predictions.json').read_text())
        self.example = self.fixtures['five_class'][0]

    def analysis(self, prediction):
        return {'id': 'fixture', 'created_at': 1, 'input': '576', 'variant': {},
                'prediction_status': 'available' if prediction else 'not_available', 'prediction': prediction}

    def test_five_classes_round_trip(self):
        for prediction in self.fixtures['five_class']:
            with self.subTest(decision=prediction['decision']):
                parsed = Prediction.model_validate(prediction)
                self.assertEqual(parsed.model_dump(mode='json'), prediction)
                response = AnalysisResponse.model_validate(self.analysis(prediction))
                self.assertIsInstance(response.prediction, Prediction)

    def test_invalid_distributions_are_rejected_even_in_legacy_union(self):
        mutations = [
            lambda p: p['class_scores'].pop('uncertain'),
            lambda p: p['class_scores'].update(extra=0),
            lambda p: p['class_scores'].update(uncertain=-0.1),
            lambda p: p['class_scores'].update(uncertain=1.1),
            lambda p: p['class_scores'].update(uncertain=float('nan')),
            lambda p: p['class_scores'].update(uncertain=float('inf')),
            lambda p: p['class_scores'].update(uncertain=True),
            lambda p: p['class_scores'].update(uncertain='0.05'),
            lambda p: p['class_scores'].update(uncertain=0.5),
            lambda p: p.update(decision='likely_pathogenic'),
            lambda p: p.update(schema_version=3),
            lambda p: p.pop('schema_version'),
            lambda p: p['explanation'].update(output_target='disease'),
        ]
        for mutate in mutations:
            candidate = copy.deepcopy(self.example)
            mutate(candidate)
            with self.subTest(candidate=candidate), self.assertRaises(ValidationError):
                AnalysisResponse.model_validate(self.analysis(candidate))

    def test_tie_order_and_confidence_are_separate_from_uncertain(self):
        candidate = copy.deepcopy(self.example)
        candidate['class_scores'] = dict.fromkeys(CLASS_ORDER, 0.2)
        candidate['confidence_status'] = 'low'
        self.assertEqual(Prediction.model_validate(candidate).decision, 'benign')
        candidate['decision'] = 'uncertain'
        with self.assertRaises(ValidationError):
            Prediction.model_validate(candidate)

    def test_legacy_and_unavailable_history(self):
        legacy = self.fixtures['legacy']
        response = AnalysisResponse.model_validate(self.analysis(legacy)).model_dump(mode='json')
        self.assertEqual(response['prediction']['pathogenic_probability'], legacy['pathogenic_probability'])
        self.assertNotIn('class_scores', response['prediction'])
        self.assertEqual(response['prediction']['schema_version'], 1)
        self.assertIsNone(AnalysisResponse.model_validate(self.analysis(None)).prediction)
        self.assertIsNone(predict_variant({}))

    def test_saved_history_keeps_both_versions_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(store, 'DATABASE_PATH', Path(directory) / 'app.sqlite'):
            store.initialize_database()
            user = store.create_user(None, 'Test', '', None, guest=True)
            other = store.create_user(None, 'Other', '', None, guest=True)
            for prediction in [self.fixtures['legacy'], *self.fixtures['five_class'], None]:
                payload = self.analysis(prediction)
                payload.pop('id'); payload.pop('created_at')
                saved = store.save_analysis(user['id'], payload)
                read = store.get_analysis(user['id'], saved['id'])
                self.assertEqual(read['prediction'], prediction)
                AnalysisResponse.model_validate(read)
                self.assertIsNone(store.get_analysis(other['id'], saved['id']))
            history = HistoryResponse.model_validate(store.list_analyses(user['id'], 20, 0))
            self.assertEqual(history.total, 7)


if __name__ == '__main__':
    unittest.main()
