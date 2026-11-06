import unittest
import json
import re
import test_nets as fixtures
from app.config import ROOT
from app.main import app
from app.scene_rules import row_eligible


class SourceQATests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def test_each_compiled_source_entry_routes(self):
        records=json.loads((ROOT/'data/source_qa.json').read_text(encoding='utf8'))['records']
        self.assertEqual(len(records),110)
        self.assertEqual(len({row['id'] for row in records}),110)
        by_id={row['id']:row for row in app.state.service.kb.faq.records}
        self.assertTrue({row['id'] for row in records}.issubset(by_id))

        def signature(text):
            # 仅忽略称呼与标点；数字、单位、否定词、材质等商品事实仍逐字校验。
            text=re.sub(r'^(?:亲亲|亲)[，,\s]*','',text.strip())
            return re.sub(r'[\s，,。？！?！～~、：:；;]','',text)

        for row in records:
            with self.subTest(source=row['id']):
                expected=by_id[row['id']]
                pid=row['product_id']
                self.sid=self.client.post('/api/sessions').json()['session_id']
                self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})
                active=row_eligible(expected,pid,'presales','presales')
                response=self.chat(row['question'],'answered' if active else 'handoff')
                self.assertEqual(response['session']['current_product_id'],pid)
                if not active:
                    self.assertFalse(response['send_to_customer'])
                    self.assertTrue(response['operator_note'])
                    continue

                # 维护者可以配置不同意图的答案，验证业务含义和证据，不绑定某条旧路由。
                intents={item['id'] for item in response['debug']['analysis']['intents']}
                self.assertIn(expected['scene_id'],intents)
                hits=(response['debug']['retrieval'] or {}).get('hits',[])
                self.assertTrue(hits)
                selected=[]
                for hit in hits:
                    self.assertIn(hit['id'],by_id)
                    chosen=by_id[hit['id']]
                    self.assertEqual(chosen['scene_id'],expected['scene_id'])
                    self.assertTrue(row_eligible(chosen,pid,'presales','presales'))
                    if chosen['scope']=='product':self.assertIn(pid,chosen['product_ids'])
                    if expected['fields']:
                        self.assertTrue(set(expected['fields']).intersection(chosen['fields']))
                    selected.append(chosen)
                approved='；'.join(chosen['standard_answer'].rstrip('。') for chosen in selected)
                self.assertEqual(signature(response['answer']),signature(approved))

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
