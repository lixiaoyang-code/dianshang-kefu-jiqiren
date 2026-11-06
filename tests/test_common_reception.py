import copy
import unittest
from unittest.mock import AsyncMock, patch
import test_nets as fixtures
from app.main import app
from app.rag import RAGAssistant
from app.common_intents import identify
from app.intent_candidates import candidates_for
from scripts.add_common_intents import migrate


class CommonReceptionTests(unittest.TestCase):
    setUp = fixtures.NetsTests.setUp
    tearDown = fixtures.NetsTests.tearDown

    def test_generic_discount_uses_store_faq_despite_other_product_variants(self):
        svc=app.state.service
        with patch.object(svc.model,'understand',new=AsyncMock(side_effect=AssertionError('FAQ needs no generation'))):
            for pid in ['801','802','803','804']:
                sid=self.client.post('/api/sessions').json()['session_id']
                r=self.client.post('/api/chat',json={'session_id':sid,'product_id':pid,'message':'有优惠吗'}).json()
                self.assertEqual(r['status'],'answered',r)
                self.assertEqual(r['debug']['retrieval']['method'],'scene_faq')
                self.assertIn('页面',r['answer']);self.assertNotIn('已经',r['answer'])

    def test_disabled_promotion_faq_is_not_replaced_by_a_foreign_product(self):
        row=next(r for r in app.state.service.kb.faq.records if r['id']=='store.common_promotion_policy')
        row['status']='disabled'
        sid=self.client.post('/api/sessions').json()['session_id']
        r=self.client.post('/api/chat',json={'session_id':sid,'product_id':'801','message':'有优惠吗'}).json()
        self.assertFalse(r['send_to_customer'],r)

    def ask(self, text, reception='presales', stage='presales'):
        sid=self.client.post('/api/sessions').json()['session_id']
        return self.client.post('/api/chat',json={'session_id':sid,'message':text,
            'reception_type':reception,'business_stage':stage}).json()

    def test_greeting_without_product_in_all_reception_states(self):
        with patch.object(app.state.service.model,'understand',new=AsyncMock(side_effect=AssertionError('no model'))):
            for reception,stage in [('presales','presales'),('aftersales','shipping'),('aftersales','received'),('aftersales','aftersales')]:
                for text in ['你好','您好！','哈喽','在吗？','客服在吗','hello']:
                    r=self.ask(text,reception,stage)
                    self.assertTrue(r['send_to_customer'],r)
                    self.assertEqual(r['debug']['analysis']['intents'][0]['id'],'industry.common_greeting')
                    self.assertIsNone(r['session']['current_product_id'])

    def test_greeting_followed_by_actual_question_does_not_swallow_it(self):
        r=self.ask('你好，多久发货？')
        self.assertTrue(r['send_to_customer'],r)
        self.assertNotIn('industry.common_greeting',[s['id'] for s in r['debug']['analysis']['intents']])
        self.assertIn('24',r['answer'])

    def test_tracking_after_shipping_never_promises_presale_arrival(self):
        for text in ['我的快递到哪了','多久能到','物流','催一下物流']:
            r=self.ask(text,'aftersales','shipping')
            self.assertTrue(r['send_to_customer'],r)
            self.assertIn('核实',r['answer'])
            self.assertNotIn('次日',r['answer'])
            self.assertEqual(r['debug']['analysis']['intents'][0]['id'],'industry.common_tracking')

    def test_returns_are_reception_not_policy_or_operation_promises(self):
        for text in ['可以退换货吗','支持七天无理由吗','退货运费谁出','我要退货','帮我退款','我要换货','收到破损了']:
            r=self.ask(text,'aftersales','received')
            self.assertTrue(r['send_to_customer'],r)
            self.assertIn('核实',r['answer'])
            for forbidden in ['已经退款','已申请','七天无理由退货','免费退','全额赔偿']:
                self.assertNotIn(forbidden,r['answer'])

    def test_common_faq_disable_and_edit_take_effect(self):
        row=next(r for r in app.state.service.kb.faq.records if r['id']=='store.common_greeting')
        row['standard_answer']='维护过的招呼';row['answer_parts']=['维护过的招呼']
        self.assertEqual(self.ask('你好')['answer'],'维护过的招呼')
        row['status']='disabled'
        self.assertFalse(self.ask('你好')['send_to_customer'])

    def test_interaction_candidates_cannot_answer_unrelated_questions(self):
        ids={r['id'] for r in candidates_for(app.state.service.kb,'这个有多重','801')}
        self.assertNotIn('store.common_greeting',ids)
        self.assertNotIn('store.common_thanks',ids)
        self.assertIsNone(identify('你好，物流和退换货都说一下'))
        self.assertIsNone(identify('我要投诉并要求赔偿'))

    def test_migration_preserves_existing_content(self):
        doc={'scenes':copy.deepcopy(app.state.service.kb.faq.scenes),'records':copy.deepcopy(app.state.service.kb.faq.records)}
        doc['records'][-1]['standard_answer']='维护内容'
        self.assertEqual(migrate(doc),doc)

    def test_rag_shows_maintained_reference_without_inventing_policy(self):
        assistant=RAGAssistant(app.state.service.kb,app.state.service.model)
        import asyncio
        for text in ['你好','我要退货','我的快递到哪了']:
            result=asyncio.run(assistant.assist(text,reception='aftersales',stage='received'))
            self.assertTrue(result['suggestion'])
            self.assertEqual(result['retrieval_method'],'faq_reference')
            self.assertEqual(result['generation_status'],'not_called')
            self.assertEqual(len(result['sources']),1)
            self.assertTrue(result['for_operator_only'])
            self.assertFalse(result['can_save_faq'])
