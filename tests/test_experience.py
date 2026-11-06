import tempfile,unittest
from pathlib import Path
from unittest.mock import patch,AsyncMock
from fastapi.testclient import TestClient
from app.main import app
from app.config import Settings
from app.knowledge import Knowledge
from app.service import Service
from app.model import Model
from app.deployment import DeploymentSettings
from app.rag import RAGAssistant
from app.replies import WAITING_REPLY


class PublicExperienceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.env=patch.dict('os.environ',{'SEMANTIC_MODE':'off'});self.env.start()
        self.service=Service(Knowledge(),Model(Settings(mode='mock',key='')),Path(self.temp.name))
        self.settings=DeploymentSettings(mode='demo',admin_username='owner',admin_password='test-password-123456',
            session_secret='test-secret-at-least-thirty-two-characters',allowed_hosts=('demo.test',))
        self.mock_settings=patch('app.main.DeploymentSettings.from_env',return_value=self.settings);self.mock_settings.start()
        self.mock_service=patch('app.main.Service',return_value=self.service);self.mock_service.start()
        self.client=TestClient(app,base_url='https://demo.test');self.client.__enter__()
    def tearDown(self):
        self.client.__exit__(None,None,None);self.mock_service.stop();self.mock_settings.stop();self.env.stop();self.temp.cleanup()

    def test_public_workflow_and_aggregate_are_accessible_but_real_knowledge_and_rows_are_private(self):
        for path in ['/experience/knowledge','/experience/statistics']:
            self.assertEqual(self.client.get(path).status_code,200)
        for path in ['/api/faq','/api/scenes','/api/materials','/api/statistics','/api/statistics/review',
                     '/api/statistics/processing','/consultations']:
            self.assertEqual(self.client.get(path).status_code,401)
        fake={'counts':{'total':1},'rates':{'response':100},'trend':[],
              'scope':'test','accuracy_note':'test','records':[{'question':'PRIVATE_SENTINEL','answer':'PRIVATE_ANSWER'}],
              'record_total':1,'page':1,'reasons':[{'reason':'PRIVATE_REASON'}]}
        with patch.object(self.service.statistics,'snapshot',return_value=fake):
            result=self.client.get('/api/experience/statistics')
        self.assertEqual(result.status_code,200)
        self.assertEqual(set(result.json()),{'counts','rates','trend','scope','accuracy_note'})
        self.assertNotIn('PRIVATE',result.text)
        self.assertEqual(self.client.post('/api/experience/statistics').status_code,405)

    def test_workflow_script_uses_local_storage_and_never_reads_or_writes_formal_faq(self):
        from app.config import ROOT
        js=(ROOT/'static/knowledge-demo.js').read_text(encoding='utf-8')
        self.assertIn('localStorage.setItem',js)
        for path in ['/api/faq','/api/scenes','/api/materials']:self.assertNotIn(path,js)


class HoldingSuggestionTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_evidence_provides_safe_reply_without_model_or_saving(self):
        rag=RAGAssistant(Knowledge(),Model(Settings(mode='mock',key='')))
        with patch.object(rag,'_retrieve',return_value=([],'keyword')),patch.object(rag,'_generate',new=AsyncMock(side_effect=AssertionError('no model'))) as generate:
            r=await rag.assist('这款能养熊猫吗','cloudquilt')
        self.assertEqual(r['suggestion'],WAITING_REPLY)
        self.assertEqual(r['sources'],[]);self.assertFalse(r['can_save_faq'])
        self.assertEqual(r['suggestion_kind'],'holding');self.assertIn('资料',r['operator_advice'])
        generate.assert_not_awaited()
