"""Real artifact smoke tests plus API persistence and controlled failure tests."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from backend import app_database as store
from backend.database import get_variant
from backend.main import app
from backend.prediction import Prediction
from ml.inference import InferenceService, ROOT


@unittest.skipUnless((ROOT/'ml/artifacts/shap-v1-final/shap_manifest.json').exists(), 'Requires local candidate artifacts')
class InferenceIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = InferenceService()
        if cls.service.reason:
            raise AssertionError(cls.service.reason)

    @classmethod
    def tearDownClass(cls):
        cls.service.close()

    def test_real_five_reference_examples_and_label_invariance(self):
        for identifier in [729975,2828440,703089,102871,614]:
            records = get_variant(identifier)['source_records']
            result = self.service.predict(records)
            prediction = Prediction.model_validate(result['prediction'])
            self.assertEqual(prediction.confidence_status,'low')
            self.assertEqual(prediction.release_status,'research_candidate_rejected')
            self.assertEqual(prediction.explanation_status,'available')
            explanation = prediction.explanation
            self.assertEqual(explanation.output_target,prediction.decision)
            self.assertAlmostEqual(explanation.base_value+sum(f.contribution for f in explanation.display_features),explanation.explained_value,places=4)
            modified = deepcopy(records)
            for record in modified:
                record['clinvar_classification']='invented label'
                record['conditions']=[]
                record['genes']=['invented gene']
            # Remove memoized output to prove labels aren't used by computation.
            self.service.executor.submit(self.service.results.clear).result()
            second = self.service.predict(modified)
            self.assertEqual(result['prediction'],second['prediction'])

    def test_failure_paths_and_shap_failure_preserves_scores(self):
        records = get_variant(614)['source_records']
        changed = deepcopy(records)
        for row in changed: row['assembly']='GRCh37'
        self.assertEqual(self.service.predict(changed)['prediction_reason'],'unsupported_source')
        changed = deepcopy(records)
        for row in changed: row['alt']='<DEL>'
        self.assertEqual(self.service.predict(changed)['prediction_reason'],'unsupported_variant')
        changed = deepcopy(records)
        for row in changed: row['position']=1
        self.assertEqual(self.service.predict(changed)['prediction_reason'],'annotation_missing')
        self.service.executor.submit(self.service.results.clear).result()
        with patch.object(self.service.saved.engine,'explain',side_effect=RuntimeError('test failure')):
            with self.assertLogs('ml.inference',level='ERROR'):
                result=self.service.predict(records)
        self.assertIsNotNone(result['prediction'])
        self.assertIsNone(result['prediction']['explanation'])
        self.assertEqual(result['prediction']['explanation_status'],'failed')
        self.assertEqual(self.service.predict(records)['prediction']['explanation_status'],'available')

    def test_busy_capacity_is_bounded(self):
        for _ in range(4): self.service.capacity.acquire()
        try:
            self.assertEqual(self.service.predict([])['prediction_reason'], 'busy')
        finally:
            for _ in range(4): self.service.capacity.release()

    def test_api_snapshots_access_control_and_no_recomputation(self):
        with tempfile.TemporaryDirectory() as temp, patch.object(store,'DATABASE_PATH',Path(temp)/'accounts.sqlite'):
            # The class fixture owns shutdown; lifespan still exercises normal startup wiring.
            with patch('ml.inference.InferenceService',return_value=self.service), patch.object(self.service,'close'):
                with TestClient(app) as client:
                    self.assertEqual(client.post('/api/auth/guest').status_code,201)
                    response=client.post('/api/analyses',json={'variant':'614'})
                    self.assertEqual(response.status_code,201,response.text)
                    saved=response.json()
                    self.assertEqual(saved['prediction_status'],'available')
                    with patch.object(self.service,'predict',side_effect=AssertionError('History must not recompute')):
                        self.assertEqual(client.get('/api/analyses/'+saved['id']).json(),saved)
                        self.assertEqual(client.get('/api/history').json()['items'][0],saved)
                    client.post('/api/auth/guest')
                    self.assertEqual(client.get('/api/analyses/'+saved['id']).status_code,404)
                    self.assertEqual(client.post('/api/analyses',json={'variant':'invalid'}).status_code,422)


class MissingModelTests(unittest.TestCase):
    def test_missing_model_is_explicit(self):
        with tempfile.TemporaryDirectory() as temp:
            service=InferenceService(Path(temp))
            try:
                self.assertEqual(service.predict([]),{'prediction':None,'prediction_reason':'model_missing'})
            finally:
                service.close()
