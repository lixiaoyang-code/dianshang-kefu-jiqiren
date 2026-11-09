import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from app.common_intents import identify
from app.config import ROOT,Settings
from app.knowledge import Knowledge
from app.model import Model
from app.service import Service,Session
from scripts.add_negotiation_intent import migrate,SID


class NegotiationMemoryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.env=patch.dict('os.environ',{'SEMANTIC_MODE':'off'});self.env.start()
        self.temp=tempfile.TemporaryDirectory()
        original=json.loads((ROOT/'data/faq.json').read_text(encoding='utf-8'))
        doc=migrate(original)
        self.assertEqual(doc,migrate(doc))
        self.assertEqual(doc['records'][:len(original['records'])],[
            {**r,'question_variants':next(s['question_variants'] for s in doc['scenes'] if s['id']==r['scene_id'])}
            if any(identify(q)=='price_negotiation' for q in r['question_variants']) else r for r in original['records']])
        self.svc=Service(Knowledge(faq_document=doc),Model(Settings(mode='mock',key='')),Path(self.temp.name))

    def tearDown(self):
        for h in self.svc.logger.handlers:h.close()
        self.temp.cleanup();self.env.stop()

    async def test_discount_then_conditional_purchase_hands_off(self):
        sid=self.svc.create().session_id
        first=await self.svc.chat(sid,'有优惠吗','801')
        second=await self.svc.chat(sid,'优惠我就买','801')
        self.assertEqual(first['status'],'answered',first)
        self.assertFalse(second['send_to_customer'])
        self.assertEqual(second['debug']['reason'],'price_followup')
        self.assertEqual(second['debug']['analysis']['intents'][0]['id'],SID)
        repeated=await self.svc.chat(sid,'优惠我就买','801')
        self.assertEqual(repeated['debug']['reason'],'price_followup')

    async def test_elliptical_bargaining_uses_adjacent_discount_context(self):
        sid=self.svc.create().session_id
        await self.svc.chat(sid,'有优惠吗','801')
        reply=await self.svc.chat(sid,'还能再少点吗','801')
        self.assertFalse(reply['send_to_customer'])
        self.assertEqual(reply['debug']['reason'],'price_followup')
        self.assertEqual(reply['debug']['analysis']['intents'][0]['id'],SID)
        self.assertEqual(reply['debug']['conversation_context']['previous_intent'],'promotion_policy')
        self.assertIsNone(identify('还能再少点吗'))

    async def test_product_switch_reset_and_unrelated_question_clear_context(self):
        for operation in ('switch','reset','unrelated'):
            sid=self.svc.create().session_id
            await self.svc.chat(sid,'有优惠吗','801')
            if operation=='reset':self.svc.sessions[sid]=Session(sid,current_product_id='801',product_confirmed=True)
            if operation=='unrelated':await self.svc.chat(sid,'你好','801')
            reply=await self.svc.chat(sid,'还能再少点吗','802' if operation=='switch' else '801')
            self.assertNotIn('conversation_context',reply['debug'],operation)
            self.assertIsNone(self.svc.sessions[sid].last_promotion)

    def test_purchase_confirmation_and_gift_request_are_not_price_negotiation(self):
        self.assertNotEqual(identify('我已经买了还有优惠吗'),'price_negotiation')
        self.assertNotEqual(identify('那我就买了'),'price_negotiation')
        self.assertEqual(identify('送个篮子我就买'),'gift_policy')
