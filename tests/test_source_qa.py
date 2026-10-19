import unittest
import json
import test_nets as fixtures
from app.config import ROOT


class SourceQATests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def test_each_compiled_source_entry_routes(self):
        records=json.loads((ROOT/'data/source_qa.json').read_text(encoding='utf8'))['records']
        self.assertEqual(len(records),110)
        for row in records:
            with self.subTest(source=row['id']):
                self.sid=self.client.post('/api/sessions').json()['session_id']
                self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':row['product_id']})
                response=self.chat(row['question'],'answered' if row['status']=='active' else 'handoff')
                if response['debug']['retrieval']['method']=='approved_reply':
                    self.assertEqual(row['answer'],response['answer'])
                    continue
                self.assertEqual(response['debug']['retrieval']['method'],'source_qa')
                selected_id=response['debug']['retrieval']['hits'][0]['id']
                selected=next(r for r in records if r['id']==selected_id)
                self.assertEqual(selected['question'],row['question'])
                self.assertEqual(selected['product_id'],row['product_id'])

    def test_public_names(self):
        products=self.client.get('/api/products').json()
        self.assertEqual({p['name'] for p in products},{'纯色款','全伸缩款','小狗联名款','免安装款'})
        r=self.chat('全伸缩款支架可以伸缩吗','answered')
        self.assertNotIn('802',r['answer'])
        self.assertIn('145',r['answer'])

    def test_old_pole_values_not_imported_as_reply(self):
        r=self.chat('纯色款加粗支架有啥区别','answered')
        self.assertIn('12 mm',r['answer'])
        self.assertNotIn('1cm',r['answer'])

    def test_original_active_qa_combined_features(self):
        r=self.chat('纯色款有充电口和置物袋吗','answered')
        self.assertIn('充电口',r['answer'])
        self.assertIn('收纳袋',r['answer'])

    def test_report_promises_remain_unanswered(self):
        self.chat('纯色款阻燃吗，有阻燃报告吗','handoff')

    def test_links_and_images_empty_until_provided(self):
        for p in self.client.get('/api/products').json():
            self.assertIsNone(p['link'])
            self.assertEqual(p['image_refs'][0]['id'],'pole-load-user')
