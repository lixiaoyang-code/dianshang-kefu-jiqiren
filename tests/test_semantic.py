import unittest
from unittest.mock import patch
import test_nets as fixtures
from app.config import ROOT
from app.knowledge import Knowledge
from app.semantic import get_semantic
from app.main import app

@unittest.skipUnless((ROOT/'models/minilm/model.onnx').exists(), '需要先下载本地向量模型')
class SemanticTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def test_real_vector_paraphrase(self):
        r=self.chat('小狗联名款杆子容易倒吗','answered')
        self.assertEqual(r['debug']['retrieval']['method'],'semantic_onnx')
        self.assertIn('10斤',r['answer'])
        self.assertEqual(r['answer'],app.state.service.kb.products['803']['short_replies']['stability'])

    def test_product_filter(self):
        s=app.state.service.semantic
        for pid in ['801','802','803','804']:
            doc,trace=s.search('骨架是啥做成的',pid)
            self.assertEqual(doc['product_id'],pid)
            self.assertTrue(all(c['id'].startswith('product.'+pid+'.') for c in trace['candidates']))

    def test_unknown_product_no_retrieval(self):
        doc,trace=app.state.service.semantic.search('杆子容易倒吗',None)
        self.assertIsNone(doc)
        self.assertEqual(trace['status'],'product_unconfirmed')

    def test_unknown_question_and_close_candidates(self):
        for q in ['你吃饭了吗','能开增值税发票吗','架子撑得住不']:
            doc,trace=app.state.service.semantic.search(q,'803')
            self.assertIsNone(doc)
            self.assertEqual(trace['status'],'low_confidence')

    def test_sensitive_and_multi_question_guards(self):
        for q in ['保证支架不会塌','杆子牢不牢，能治失眠吗','能挂10斤吗','这种有没有甲醛']:
            doc,trace=app.state.service.semantic.search(q,'803')
            self.assertIsNone(doc)
            self.assertEqual(trace['status'],'guard_rejected')

    def test_no_new_washing_fact_for_other_product(self):
        doc,trace=app.state.service.semantic.search('能塞进洗衣机里面清洗不','801')
        self.assertTrue(doc is None or doc['field']!='washing')

    def test_synonym_reply_dedup(self):
        self.chat('小狗联名款支架稳吗','answered')
        r=self.chat('杆子容易倒吗','duplicate')
        self.assertFalse(r['send_to_customer'])

    def test_off_and_missing_model_fallback(self):
        with patch.dict('os.environ',{'SEMANTIC_MODE':'off'}):
            semantic,status=get_semantic(Knowledge())
        self.assertIsNone(semantic);self.assertEqual(status,'disabled')
        with patch('pathlib.Path.exists',return_value=False):
            semantic,status=get_semantic(Knowledge())
        self.assertIsNone(semantic);self.assertEqual(status,'model_missing')
