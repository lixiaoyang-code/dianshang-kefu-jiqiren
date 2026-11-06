"""售前范围必须覆盖老规则、字段检索和问答，不能只改变管理页面的勾选。"""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

import test_nets as fixtures
from app.config import ROOT
from app.main import app
from app.scene_rules import managed, requires_scene_selection
from scripts.set_presales_scope import apply, migrate


class PresalesMigrationTests(unittest.TestCase):
    def test_product_answers_stay_presales_and_common_templates_are_shared(self):
        document=json.loads((ROOT/'data/faq.json').read_text(encoding='utf-8'))
        self.assertGreater(len(document['records']),200)
        for row in document['records']:
            with self.subTest(answer=row['id']):
                if row['id'].startswith('store.common_') or row['id']=='store.affirmation':
                    self.assertEqual(row['conditions']['reception'],'all')
                    self.assertEqual(row['conditions']['stages'],[])
                    continue
                if row.get('origin')=='catalog_onboarding':continue
                self.assertEqual(row['conditions']['reception'],'presales')
                self.assertEqual(row['conditions']['stages'],['presales'])

    def test_migration_preserves_everything_except_scope(self):
        original={'scenes':[{'id':'intent'}],'records':[{
            'id':'answer','status':'needs_review','standard_answer':'商家原话',
            'images':[{'url':'/static/image.png'}],'sources':['original-cell'],
            'conditions':{'reception':'all','stages':[],
                          'valid_from':'2026-01-01','valid_until':'2027-01-01'},
            'priority':21,'keywords':['拓展关键词']}]}
        result=migrate(original)
        self.assertEqual(result,migrate(result))
        self.assertEqual(original['records'][0]['conditions']['reception'],'all')
        expected=copy.deepcopy(original)
        expected['records'][0]['conditions'].update(reception='presales',stages=['presales'])
        self.assertEqual(result,expected)

    def test_apply_backs_up_exact_original_and_is_idempotent(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'faq.json'
            original=b'{"records":[{"id":"test","conditions":{"reception":"all"}}]}'
            path.write_bytes(original)
            backup,count=apply(path)
            self.assertEqual(count,1)
            self.assertEqual(backup.read_bytes(),original)
            self.assertIsNone(apply(path)[0])
            self.assertEqual(len(list((path.parent/'backups').iterdir())),1)

    def test_migration_keeps_priorities_even_if_reference_answers_differ(self):
        core={'id':'product.801.material','scene_id':'industry.material',
              'scope':'product','product_ids':['801'],'status':'active',
              'standard_answer':'核准话术','images':[],'priority':0}
        source={**core,'id':'qa.801.material','origin':'source_qa',
                'standard_answer':'原表不同话术'}
        unrelated={**core,'id':'product.802.material','product_ids':['802']}
        manual={**core,'id':'product.801.other','priority':14}
        inactive={**core,'id':'product.801.inactive','status':'needs_review'}
        result=migrate({'records':[core,source,unrelated,manual,inactive]})
        self.assertEqual([r['priority'] for r in result['records']],[0,0,0,14,0])
        self.assertEqual(core['priority'],0)

    def test_baseline_scope_does_not_create_new_selection_conflicts(self):
        row={'conditions':{'reception':'presales','stages':['presales']},
             'configured_scene':False,'scene_type':'industry'}
        self.assertTrue(managed(row))
        self.assertFalse(requires_scene_selection(row))
        for update in ({'configured_scene':True},{'keywords':['支架']},
                       {'priority':1},{'scene_type':'custom'}):
            self.assertTrue(requires_scene_selection({**row,**update}))
        self.assertTrue(requires_scene_selection({**row,'conditions':{
            **row['conditions'],'valid_until':'2030-01-01'}}))


class PresalesServiceScopeTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown

    def ask(self,message,reception='presales',stage='presales',pid='801'):
        sid=self.client.post('/api/sessions').json()['session_id']
        result=self.client.post('/api/chat',json={'session_id':sid,'message':message,
            'product_id':pid,'reception_type':reception,'business_stage':stage})
        self.assertEqual(result.status_code,200,result.text)
        return result.json()

    def test_legacy_answer_paths_cannot_bypass_reception_or_stage(self):
        # 包含核准话术、精确源问答、跨款推荐、物流、尺寸计算与字段检索。
        questions=['支架什么材质','支架稳固吗','有全伸缩的支架吗','有免安装的吗',
                   '今天能发吗','90*190可以用吗','四面五面',
                   '开门','材质','有涂层吗','伸缩高度是多少？']
        invalid=[('aftersales','presales'),('presales','shipping'),
                 ('presales','received'),('presales','aftersales'),('aftersales','aftersales')]
        service=app.state.service
        with patch.object(service.model,'select',new=AsyncMock()) as selector, \
             patch.object(service.model,'understand',new=AsyncMock()) as understander:
            for reception,stage in invalid:
                for question in questions:
                    with self.subTest(reception=reception,stage=stage,question=question):
                        result=self.ask(question,reception,stage)
                        self.assertFalse(result['send_to_customer'],result)
                        self.assertEqual(result['answer'],'')
                        self.assertEqual(result['status'],'suppressed')
                        self.assertTrue(result['operator_note'])
                        self.assertIn(result['debug']['reason'],('presales_scope','scene_ineligible'))
            selector.assert_not_awaited()
            understander.assert_not_awaited()

    def test_out_of_scope_guard_does_not_queue_customer_waiting_reply(self):
        for question in ['架子摇不摇呀','伸缩高度是多少？']:
            with self.subTest(question=question):
                result=self.ask(question,stage='received')
                self.assertIn(result['debug']['reason'],('presales_scope','scene_ineligible'))
                self.assertFalse(result['session']['waiting'])
                self.assertTrue(result['debug']['analysis']['outcome'])

    def test_future_explicit_aftersales_answer_can_still_match(self):
        service=app.state.service
        row=copy.deepcopy(next(r for r in service.kb.faq.records if r['id']=='product.801.stability'))
        row.update(id='test.aftersales.stability',standard_answer='已审核的售后检查支架话术',
                   configured_scene=True,conditions={'reception':'aftersales','stages':['aftersales']})
        service.kb.faq.records.append(row)
        result=self.ask('支架稳吗',reception='aftersales',stage='aftersales')
        self.assertEqual(result['status'],'answered',result)
        self.assertEqual(result['answer'],'已审核的售后检查支架话术')
        self.assertEqual(result['debug']['retrieval']['method'],'scene_faq')

    def test_presales_still_answers_existing_approved_questions(self):
        for question in ['承重怎么样','什么支架','多久能到','伸缩高度是多少？']:
            with self.subTest(question=question):
                result=self.ask(question)
                self.assertEqual(result['status'],'answered',result)
                self.assertTrue(result['send_to_customer'])


if __name__=='__main__':
    unittest.main()
