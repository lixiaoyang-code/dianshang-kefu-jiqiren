"""清除测试上下文不能只清空网页，还要清掉后台重复记录和等待任务。"""
import unittest
from unittest.mock import AsyncMock, patch
import test_nets as fixtures
from app.main import app


class SessionResetTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def reset(self,mode,**kwargs):
        response=self.client.post(f'/api/sessions/{self.sid}/reset',json={'mode':mode,**kwargs})
        self.assertEqual(response.status_code,200)
        return response.json()

    def test_clear_memory_keeps_conditions_and_removes_all_dialog_state(self):
        old=app.state.service.sessions[self.sid]
        old.current_product_id='802';old.product_confirmed=True
        old.reception_type='aftersales';old.business_stage='received'
        old.history=[{'role':'user','content':'旧问题'}];old.answered_keys=['old']
        old.recent_product_ids=['804'];old.pending_question='旧指代';old.pending_topic='旧主题'
        old.waiting={'old':{'received_at':0,'sent':False}};old.last_waiting_at=100;old.needs_human=True
        result=self.reset('memory')
        self.assertEqual(result['current_product_id'],'802')
        self.assertTrue(result['product_confirmed'])
        self.assertEqual(result['reception_type'],'aftersales')
        self.assertEqual(result['business_stage'],'received')
        for key in ['history','answered_keys','recent_product_ids']:self.assertEqual(result[key],[])
        self.assertEqual(result['waiting'],{})
        self.assertIsNone(result['pending_question']);self.assertIsNone(result['pending_topic'])
        self.assertFalse(result['needs_human']);self.assertEqual(result['last_waiting_at'],0)

    def test_clear_memory_uses_unsent_test_conditions(self):
        result=self.reset('memory',reception_type='aftersales',business_stage='shipping')
        self.assertEqual(result['reception_type'],'aftersales')
        self.assertEqual(result['business_stage'],'shipping')

    def test_reset_test_restores_initial_conditions(self):
        old=app.state.service.sessions[self.sid]
        old.current_product_id='803';old.product_confirmed=True
        old.reception_type='aftersales';old.business_stage='shipping'
        result=self.reset('test',reception_type='aftersales',business_stage='received')
        self.assertIsNone(result['current_product_id']);self.assertFalse(result['product_confirmed'])
        self.assertEqual(result['reception_type'],'presales');self.assertEqual(result['business_stage'],'presales')

    def test_after_memory_clear_answer_can_be_tested_again(self):
        self.chat('801支架稳吗','answered')
        self.chat('支架稳吗','duplicate')
        self.reset('memory')
        self.chat('支架稳吗','answered')

    def test_old_waiting_request_cannot_reply_after_reset(self):
        old=app.state.service.sessions[self.sid]
        old.waiting={'old-request':{'received_at':0,'sent':False}}
        self.reset('memory')
        result=self.client.post(f'/api/sessions/{self.sid}/waiting/old-request',json={}).json()
        self.assertFalse(result['send_to_customer'])

    def test_reset_validation_and_unknown_session(self):
        self.assertEqual(self.client.post(f'/api/sessions/{self.sid}/reset',json={'mode':'everything'}).status_code,422)
        self.assertEqual(self.client.post('/api/sessions/missing/reset',json={'mode':'memory'}).status_code,404)

    def test_approved_four_five_side_faq_does_not_require_model(self):
        with patch.object(app.state.service.model,'select',new=AsyncMock(side_effect=ConnectionError('unavailable'))) as select:
            result=self.chat('801四面和五面什么区别','answered')
        select.assert_not_awaited()
        self.assertIn('靠墙',result['answer'])
        self.assertEqual(result['debug']['model'],'not_called')

    def test_shading_and_four_five_sides_are_different_intents(self):
        for pid in ['801','802','803','804']:
            self.sid=self.client.post('/api/sessions').json()['session_id']
            first=self.chat(pid+'可以遮光吗','answered')
            second=self.chat('四面和五面有什么区别','answered')
            self.assertEqual(first['debug']['analysis']['intents'][0]['id'],'industry.light_blocking')
            self.assertIn('可以遮光',first['answer'])
            self.assertEqual(second['debug']['analysis']['intents'][0]['id'],'industry.shade_sides')
            self.assertIn('靠墙',second['answer'])


class SessionConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_queued_product_selection_reads_session_after_reset(self):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import Mock
        from app.main import reset_session, event, ResetSession, Event
        from app.service import Session
        original=app.state.service if hasattr(app.state,'service') else None
        sid='concurrent-test';lock=asyncio.Lock()
        store=SimpleNamespace(sessions={sid:Session(sid)},locks={sid:lock},
                              kb=SimpleNamespace(products={'804':{}}),logger=Mock())
        app.state.service=store
        try:
            await lock.acquire()
            clearing=asyncio.create_task(reset_session(sid,ResetSession(mode='test')))
            selecting=asyncio.create_task(event(sid,Event(type='customer_select',product_id='804')))
            await asyncio.sleep(0)
            lock.release()
            _,selected=await asyncio.gather(clearing,selecting)
            self.assertEqual(selected['current_product_id'],'804')
            self.assertEqual(store.sessions[sid].current_product_id,'804')
        finally:
            app.state.service=original
