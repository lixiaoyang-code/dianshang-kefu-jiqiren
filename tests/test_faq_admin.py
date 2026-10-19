import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.config import ROOT
from app.main import app
from app.faq_admin import FAQStore


class FAQAdminTests(unittest.TestCase):
    def setUp(self):
        self.folder=tempfile.TemporaryDirectory()
        self.path=Path(self.folder.name)/'faq.json'
        self.path.write_bytes((ROOT/'data/faq.json').read_bytes())
        self.env=patch.dict('os.environ',{'MODEL_MODE':'mock','SEMANTIC_MODE':'off'})
        self.store=patch('app.faq_admin.FAQStore',lambda:FAQStore(self.path))
        self.env.start();self.store.start()
        self.client=TestClient(app);self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None,None,None);self.store.stop();self.env.stop();self.folder.cleanup()

    def snapshot(self):return self.client.get('/api/faq').json()

    def save(self,row,revision=None,**kwargs):
        return self.client.post('/api/faq',json={'revision':revision or self.snapshot()['revision'],'record':row},**kwargs)

    def stability(self):return next(copy.deepcopy(r) for r in self.snapshot()['records'] if r['id']=='product.801.stability')

    def chat(self,message):
        sid=self.client.post('/api/sessions').json()['session_id']
        return self.client.post('/api/chat',json={'session_id':sid,'product_id':'801','message':message}).json()

    def test_page_and_complete_data(self):
        self.assertEqual(self.client.get('/knowledge').status_code,200)
        d=self.snapshot();self.assertEqual(len(d['records']),207);self.assertEqual(len(d['products']),4)
        self.assertNotIn('MODEL_API_KEY',json.dumps(d))

    def test_update_persists_backs_up_and_applies_without_restart(self):
        original=self.path.read_bytes();row=self.stability();row['standard_answer']='已批准的测试话术'
        self.assertEqual(self.save(row).status_code,200)
        self.assertEqual(json.loads(self.path.read_text(encoding='utf-8'))['records'][next(i for i,r in enumerate(self.snapshot()['records']) if r['id']==row['id'])]['standard_answer'],row['standard_answer'])
        self.assertEqual(next((self.path.parent/'backups').glob('*.json')).read_bytes(),original)
        self.assertEqual(self.chat('支架稳吗')['answer'],row['standard_answer'])

    def test_stale_revision_rejected_without_overwriting(self):
        revision=self.snapshot()['revision'];row=self.stability();row['standard_answer']='第一次修改'
        self.assertEqual(self.save(row,revision).status_code,200)
        row['standard_answer']='过期修改';self.assertEqual(self.save(row,revision).status_code,409)

    def test_invalid_answer_does_not_change_file(self):
        row=self.stability();row['standard_answer']='';original=self.path.read_bytes()
        self.assertEqual(self.save(row).status_code,422);self.assertEqual(self.path.read_bytes(),original)

    def test_disabled_legacy_rule_does_not_answer(self):
        row=self.stability();row['status']='disabled';self.assertEqual(self.save(row).status_code,200)
        self.assertFalse(self.chat('支架稳吗')['send_to_customer'])

    def test_new_faq_can_reply_and_filters_product(self):
        row=dict(intent='新增测试',category='商品咨询',question_variants=['测试新增独特问题'],standard_answer='批准的新增回答',scope='product',product_ids=['801'],answer_product_id='801',status='active',images=[])
        r=self.save(row);self.assertEqual(r.status_code,200);self.assertTrue(r.json()['record']['id'].startswith('faq.'))
        self.assertEqual(self.chat('测试新增独特问题')['answer'],'批准的新增回答')
        self.assertIsNone(app.state.service.kb.faq.match('测试新增独特问题','803'))

    def test_image_path_and_origin_protection(self):
        row=self.stability();row['images']=[{'url':'/static/images/../../.env'}]
        self.assertEqual(self.save(row).status_code,422)
        self.assertEqual(self.save(self.stability(),headers={'Origin':'https://unrelated.example'}).status_code,403)

    def test_source_preserved_and_product_binding_editable(self):
        row=self.stability();row['scope']='product';row['product_ids']=['803'];row['answer_product_id']='803';row['sources']=[]
        result=self.save(row).json()['record']
        self.assertEqual(result['scope'],'product');self.assertEqual(result['product_ids'],['803'])
        self.assertTrue(result['sources'])
