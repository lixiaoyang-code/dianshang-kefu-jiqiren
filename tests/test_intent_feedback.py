import copy
import unittest
from unittest.mock import patch
import test_nets as fixtures
from app.main import app
from app.test_analysis import analyze
from app.knowledge import Knowledge
from app.faq_admin import FAQStore, SaveScene
from scripts.update_customer_intents import migrate


class IntentFeedbackTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def select(self,pid='801'):
        self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})

    def test_height_question_has_intent_and_direct_edit_link(self):
        self.select()
        r=self.chat('伸缩高度是多少？','answered')
        a=r['debug']['analysis']
        self.assertEqual(a['status'],'matched')
        self.assertEqual(a['intents'][0]['id'],'industry.height_range')
        self.assertIn('65',r['answer'])
        self.assertIn('scene=industry.height_range',a['knowledge_url'])
        self.assertIn('answer=product.801.height_range',a['knowledge_url'])
        self.assertFalse(a['dedicated_classifier'])

    def test_load_and_stability_are_separate_not_duplicate(self):
        self.select()
        stable=self.chat('支架稳吗','answered')
        load=self.chat('承重多少','answered')
        self.assertEqual(stable['debug']['analysis']['intents'][0]['id'],'industry.stability')
        self.assertEqual(load['debug']['analysis']['intents'][0]['id'],'industry.load_capacity')
        self.chat('能挂多重','duplicate')

    def test_unrecognized_always_has_operator_feedback(self):
        self.select()
        r=self.chat('能不能把月亮摘下来','handoff')
        a=r['debug']['analysis']
        self.assertEqual(a['status'],'unrecognized')
        self.assertTrue(a['outcome']);self.assertTrue(a['knowledge_url'])
        self.assertEqual(r['answer'],'')

    def test_disabled_answer_is_distinct_from_unrecognized(self):
        self.select()
        for row in app.state.service.kb.faq.records:
            if row['scene_id']=='industry.height_range':row['status']='disabled'
        r=self.chat('伸缩高度是多少？','handoff')
        a=r['debug']['analysis']
        self.assertEqual(a['status'],'matched')
        self.assertEqual(a['reason_code'],'scene_ineligible')
        self.assertIn('启用条件',a['outcome'])

    def test_failure_is_not_reported_as_missing_knowledge(self):
        self.select()
        with patch.object(app.state.service.kb,'mentions',side_effect=TimeoutError()):
            r=self.chat('伸缩高度是多少？','error')
        a=r['debug']['analysis']
        self.assertEqual(a['error_type'],'TimeoutError')
        self.assertIn('不等同于知识缺失',a['outcome'])

    def test_ambiguous_conditions_no_customer_answer(self):
        self.select()
        row=next(r for r in app.state.service.kb.faq.records if r['id']=='product.801.height_range')
        conflicting=copy.deepcopy(row);conflicting.update(id='conflicting-height',standard_answer='冲突答案')
        app.state.service.kb.faq.records.append(conflicting)
        r=self.chat('伸缩高度是多少？','handoff')
        self.assertEqual(r['debug']['analysis']['reason_code'],'scene_ambiguous')
        self.assertIn('冲突',r['debug']['analysis']['outcome'])

    def test_migration_idempotent_preserves_approved_answers_and_images(self):
        import json
        from app.config import ROOT
        doc=json.loads((ROOT/'data/faq.json').read_text(encoding='utf-8'))
        result=migrate(doc)
        self.assertEqual(result,migrate(result))
        before={r['id']:r for r in doc['records']}
        for row in result['records']:
            if row['id'] in before:
                self.assertEqual(row['standard_answer'],before[row['id']]['standard_answer'])
                self.assertEqual(row['images'],before[row['id']]['images'])

    def test_classifier_status_explicit(self):
        self.assertFalse(self.client.get('/api/health').json()['dedicated_intent_classifier'])

    def test_semantic_candidate_is_not_confirmed_intent(self):
        a=analyze(app.state.service.kb,'陌生的问题',{'current_product_id':'801',
            'reason':'insufficient_evidence','semantic':{'status':'low_confidence','candidates':[
                {'id':'product.801.stability','score':0.9,'matched_question':'支架稳吗'}]}},'suppressed')
        self.assertEqual(a['status'],'unrecognized')
        self.assertEqual(a['intents'],[])
        self.assertEqual(a['candidates'][0]['id'],'industry.stability')
        helper=a['assistant']
        self.assertEqual(helper['title'],'匹配不够确定')
        self.assertNotIn('缺少答案',helper['summary'])
        self.assertTrue(helper['evidence'])
        self.assertTrue(all(item['candidate_only'] for item in helper['evidence']))

    def test_helper_evidence_and_action_follow_actual_answer(self):
        self.select()
        r=self.chat('伸缩高度是多少？','answered')
        helper=r['debug']['analysis']['assistant']
        self.assertEqual(helper['action'],'answer')
        self.assertEqual(helper['badge'],'已回复')
        evidence=helper['evidence'][0]
        self.assertEqual(evidence['id'],'product.801.height_range')
        self.assertIn('65',evidence['text'])
        self.assertFalse(evidence['candidate_only'])
        self.assertTrue(evidence['eligible'])

    def test_helper_shows_exact_condition_exclusions(self):
        self.select()
        for row in app.state.service.kb.faq.records:
            if row['scene_id']=='industry.height_range':row['status']='disabled'
        r=self.chat('伸缩高度是多少？','handoff')
        helper=r['debug']['analysis']['assistant']
        self.assertEqual(helper['title'],'答案条件不符')
        evidence=next(e for e in helper['evidence'] if e['id']=='product.801.height_range')
        self.assertEqual(evidence['exclusions'],['未启用'])

    def test_helper_keeps_model_failure_separate_from_missing_knowledge(self):
        a=analyze(app.state.service.kb,'一个陌生问题',{'current_product_id':'801',
            'reason':'insufficient_evidence','intent_model':{'status':'failed','error':'ConnectError'},
            'semantic':{'status':'guard_rejected'}},'suppressed')
        self.assertEqual(a['assistant']['title'],'触发匹配边界')
        self.assertIn('辅助模型调用也未成功',a['assistant']['summary'])
        self.assertEqual(a['error_type'],'ConnectError')


class IntentMetadataTests(unittest.TestCase):
    def test_description_and_expansions_persist_without_changing_answers(self):
        import tempfile,json
        from pathlib import Path
        from app.config import ROOT
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'faq.json';path.write_bytes((ROOT/'data/faq.json').read_bytes())
            store=FAQStore(path);doc,revision=store.read()
            scene=copy.deepcopy(next(s for s in doc['scenes'] if s['id']=='industry.height_range'))
            scene.update(description='只回答高度，不把长宽当高度。')
            scene['question_variants'].append('最低能调到多高呀')
            saved,_,_=store.save_scene(SaveScene(revision=revision,scene=scene),lambda doc:doc)
            result,_=store.read()
            self.assertEqual(saved['description'],scene['description'])
            self.assertIn('最低能调到多高呀',saved['question_variants'])
            self.assertEqual(next(s for s in result['scenes'] if s['id']==scene['id'])['description'],scene['description'])
            old={r['id']:r for r in doc['records']}
            for row in result['records']:
                self.assertEqual(row['standard_answer'],old[row['id']]['standard_answer'])
                self.assertEqual(row['images'],old[row['id']]['images'])
