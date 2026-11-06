import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import test_nets as fixtures
from app.config import ROOT
from app.main import app


class RAGRouteTests(unittest.TestCase):
    def setUp(self):
        self.rag_folder = tempfile.TemporaryDirectory()
        self.rag_path = Path(self.rag_folder.name) / 'rag_documents.json'
        self.rag_path.write_bytes((ROOT / 'data/rag_documents.json').read_bytes())
        self.rag_env = patch.dict('os.environ', {'RAG_DOCUMENTS_FILE': str(self.rag_path)})
        self.rag_env.start()
        fixtures.NetsTests.setUp(self)

    def tearDown(self):
        fixtures.NetsTests.tearDown(self)
        self.rag_env.stop()
        self.rag_folder.cleanup()

    def test_rag_is_operator_only_and_does_not_change_chat_memory(self):
        session = app.state.service.sessions[self.sid]
        before = copy.deepcopy(session)
        result = self.client.post('/api/rag/assist', json={
            'session_id': self.sid, 'message': '全伸缩款的长度和宽度能调多少？', 'product_id': '802'})
        self.assertEqual(result.status_code, 200, result.text)
        data = result.json()
        self.assertTrue(data['for_operator_only'])
        self.assertFalse(data['send_to_customer'])
        self.assertTrue(data['sources'])
        self.assertNotEqual(data['generation_status'], 'success')
        self.assertEqual(session, before)

    def test_material_editor_and_revision_guard(self):
        self.assertEqual(self.client.get('/materials').status_code, 200)
        snapshot = self.client.get('/api/materials').json()
        row = copy.deepcopy(snapshot['documents'][0])
        row['content'] = '已核准的资料维护测试，不应修改客户回复。'
        payload = {'revision': snapshot['revision'], 'document': row}
        result = self.client.post('/api/materials', json=payload)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertEqual(result.json()['document']['content'], row['content'])
        self.assertEqual(self.client.post('/api/materials', json=payload).status_code, 409)
        self.assertTrue(list((self.rag_path.parent / 'backups').glob('*.json')))

    def test_invalid_session_product_message_and_origin_rejected(self):
        for payload, code in [
            ({'session_id': 'missing', 'message': '长度'}, 404),
            ({'session_id': self.sid, 'message': '长度', 'product_id': '999'}, 422),
            ({'session_id': self.sid, 'message': '   '}, 422)]:
            with self.subTest(payload=payload):
                self.assertEqual(self.client.post('/api/rag/assist', json=payload).status_code, code)
        result = self.client.post('/api/rag/assist', json={'session_id': self.sid, 'message': '长度'},
                                  headers={'Origin': 'https://other.example'})
        self.assertEqual(result.status_code, 403)

    def test_unknown_question_does_not_fabricate_facts_or_publish_faq(self):
        before = (ROOT / 'data/faq.json').read_bytes()
        data = self.client.post('/api/rag/assist', json={
            'session_id': self.sid, 'message': '能养一只熊猫吗？', 'product_id': '801'}).json()
        self.assertFalse(data['send_to_customer'])
        self.assertFalse(data['can_save_faq'])
        self.assertEqual(before, (ROOT / 'data/faq.json').read_bytes())
        self.assertNotIn('MODEL_API_KEY', json.dumps(data))
