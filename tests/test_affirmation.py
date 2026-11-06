import copy
import unittest
from unittest.mock import AsyncMock, patch
import test_nets as fixtures
import test_faq_admin as admin_fixtures
from app.main import app
from app.intent_candidates import candidates_for
from scripts.add_acknowledgement import migrate


class AffirmationTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def fresh(self,pid=None):
        self.sid=self.client.post('/api/sessions').json()['session_id']
        if pid:self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})

    def test_pure_acknowledgement_without_product_sends_one_heart(self):
        with patch.object(app.state.service.model,'understand',new=AsyncMock(side_effect=AssertionError('no model'))) as model:
            for text in ['好的','好哒','明白了','知道了','了解了','收到','嗯嗯','OK','好的！']:
                with self.subTest(text=text):
                    self.fresh()
                    result=self.chat(text,'answered')
                    self.assertEqual(result['answer'],'💗')
                    self.assertEqual(result['answer_parts'],['💗'])
                    self.assertEqual(result['images'],[])
                    self.assertEqual(result['debug']['analysis']['intents'][0]['id'],'industry.affirmation')
                    self.assertIsNone(result['session']['current_product_id'])
            model.assert_not_awaited()

    def test_acknowledgement_never_switches_product(self):
        for pid in ['801','802','803','804']:
            with self.subTest(product=pid):
                self.fresh(pid)
                result=self.chat('好的','answered')
                self.assertEqual(result['session']['current_product_id'],pid)
                self.assertEqual(result['answer'],'💗')

    def test_existing_repeat_policy_and_memory_reset_apply(self):
        self.chat('好的','answered')
        self.chat('好哒','duplicate')
        self.client.post(f'/api/sessions/{self.sid}/reset',json={'mode':'memory'})
        self.assertEqual(self.chat('明白了','answered')['answer'],'💗')

    def test_following_question_takes_priority_over_positive_prefix(self):
        self.fresh('802')
        self.chat('110高款高度能调多少','answered')
        result=self.chat('好的，那宽度能调多少？','answered')
        self.assertEqual(result['debug']['analysis']['intents'][0]['id'],'industry.length_width_range')
        self.assertIn('65–90',result['answer'])
        self.assertNotEqual(result['answer'],'💗')

    def test_question_marks_are_not_confirmed_affirmation(self):
        result=self.chat('好的？','handoff')
        self.assertEqual(result['debug']['reason'],'affirmation_uncertain')
        self.assertEqual(result['debug']['analysis']['intents'],[])
        self.assertEqual(result['answer'],'')

    def test_substantive_or_unknown_requests_never_retrieve_heart(self):
        for text in ['好的，但是你刚才不是这么说的','好的，那能养熊猫吗','好的你帮我换成蓝色']:
            with self.subTest(text=text):
                self.fresh('801')
                result=self.client.post('/api/chat',json={'session_id':self.sid,'message':text}).json()
                self.assertNotEqual(result['answer'],'💗')
                self.assertNotIn('store.affirmation',[h.get('id') for h in (result['debug'].get('retrieval') or {}).get('hits',[])])
                self.assertNotIn('store.affirmation',[r['id'] for r in candidates_for(app.state.service.kb,text,'801')])

    def test_disabled_acknowledgement_cannot_fall_back(self):
        row=next(r for r in app.state.service.kb.faq.records if r['id']=='store.affirmation')
        row['status']='disabled'
        self.chat('好的','handoff')

    def test_migration_preserves_maintainers_answer_and_is_idempotent(self):
        import json
        from app.config import ROOT
        doc=json.loads((ROOT/'data/faq.json').read_text(encoding='utf-8'))
        row=next(r for r in doc['records'] if r['id']=='store.affirmation')
        row['standard_answer']='维护者回复';row['answer_parts']=['维护者回复']
        self.assertEqual(migrate(doc),doc)
        self.assertEqual(migrate(migrate(doc)),doc)


class AffirmationMaintenanceTests(unittest.TestCase):
    setUp=admin_fixtures.FAQAdminTests.setUp
    tearDown=admin_fixtures.FAQAdminTests.tearDown
    snapshot=admin_fixtures.FAQAdminTests.snapshot
    save=admin_fixtures.FAQAdminTests.save

    def test_approved_reply_is_editable_knowledge(self):
        row=copy.deepcopy(next(r for r in self.snapshot()['records'] if r['id']=='store.affirmation'))
        row.update(standard_answer='👌',answer_parts=['👌'])
        self.assertEqual(self.save(row).status_code,200)
        sid=self.client.post('/api/sessions').json()['session_id']
        result=self.client.post('/api/chat',json={'session_id':sid,'message':'好的'}).json()
        self.assertEqual(result['answer'],'👌')
        self.assertEqual(result['debug']['editable_answer_ids'],['store.affirmation'])
