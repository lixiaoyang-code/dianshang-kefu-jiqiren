import copy
import unittest
from unittest.mock import patch
from app.config import ROOT, Settings
from app.knowledge import Knowledge
from app.faq import FAQ
from app.model import Model
from app.intent_candidates import candidates_for


class FAQTests(unittest.TestCase):
    def setUp(self):
        self.kb = Knowledge(ROOT/'data/nets_801_804.json')

    def test_source_rows_preserved(self):
        rows=[r for r in self.kb.faq.records if r['origin']=='source_qa']
        self.assertEqual(len(rows),110)
        self.assertEqual(len({r['id'] for r in self.kb.faq.records}),len(self.kb.faq.records))

    def test_inactive_not_model_candidates(self):
        ids={r['id'] for r in candidates_for(self.kb,'这个牢靠不','801')}
        self.assertTrue(all(r['id'] not in ids for r in self.kb.faq.records if r['status']!='active'))

    def test_product_filter_and_catalog_available(self):
        rows=self.kb.faq.eligible('801')
        self.assertTrue(all(r['scope']!='product' or r['product_ids']==['801'] for r in rows))
        self.assertTrue(any(r['answer_product_id']=='804' and r['scope']=='catalog' for r in rows))
        self.assertTrue(all(r['scope']!='product' for r in self.kb.faq.eligible(None)))

    def test_exact_variant_and_original_answer(self):
        r=self.kb.faq.match('有80宽的杆子吗？','801')
        self.assertEqual(r['id'],'catalog.full_stretch')
        self.assertIn('全伸缩款',r['standard_answer'])

    def test_conflicting_answers_are_rejected(self):
        row=copy.deepcopy(self.kb.faq.records[0]);row.update(id='test.a',question_variants=['测试'],standard_answer='A')
        other=copy.deepcopy(row);other.update(id='test.b',standard_answer='B')
        self.assertIsNone(FAQ([row,other]).match('测试','801'))

    def test_custom_record_is_immediately_usable(self):
        row=copy.deepcopy(self.kb.faq.records[0]);row.update(id='faq.custom',question_variants=['新客户原话'],standard_answer='用户批准原话',origin='custom')
        self.assertEqual(FAQ([row]).match('新客户原话','801')['standard_answer'],'用户批准原话')

    def test_pictures_and_user_copy_preserved(self):
        row=next(r for r in self.kb.faq.records if r['id']=='product.804.easy_installation')
        self.assertEqual(row['standard_answer'],self.kb.products['804']['short_replies']['easy_installation'])
        self.assertTrue(row['images'])

    def test_volcano_request_is_json_and_nonthinking(self):
        body=Model(Settings(provider='volcengine',thinking=False)).payload([],100)
        self.assertEqual(body['thinking'],{'type':'disabled'})
        self.assertEqual(body['response_format'],{'type':'json_object'})
        self.assertNotIn('thinking',Model(Settings(provider='openai_compatible')).payload([],100))
