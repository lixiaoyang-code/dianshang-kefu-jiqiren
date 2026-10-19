import json
import unittest
from unittest.mock import patch,AsyncMock
import httpx
from app.config import Settings,ROOT
from app.model import Model
from app.knowledge import Knowledge
from app.intent_candidates import candidates_for

class IntentModelTests(unittest.IsolatedAsyncioTestCase):
    async def test_no_key_makes_no_network_call(self):
        with patch('httpx.AsyncClient.post',new=AsyncMock()) as post:
            answer,status=await Model(Settings(mode='auto',key='')).understand('test',[],[])
        self.assertIsNone(answer);self.assertEqual(status,'disabled');post.assert_not_called()

    async def test_valid_pointer_preserves_approved_reply(self):
        response=httpx.Response(200,request=httpx.Request('POST','https://example.com'),
            json={'choices':[{'message':{'content':json.dumps({'action':'answer','answer_id':'product.801.stability'})}}]})
        with patch('httpx.AsyncClient.post',new=AsyncMock(return_value=response)):
            answer,status=await Model(Settings(mode='api',key='fake')).understand('这个牢靠不',[],[{'id':'product.801.stability','answer':'批准原话'}])
        self.assertEqual(answer,'product.801.stability');self.assertEqual(status,'success')

    async def test_unknown_pointer_rejected(self):
        response=httpx.Response(200,request=httpx.Request('POST','https://example.com'),
            json={'choices':[{'message':{'content':'{"action":"answer","answer_id":"product.803.fake"}'}}]})
        with patch('httpx.AsyncClient.post',new=AsyncMock(return_value=response)):
            answer,status=await Model(Settings(mode='api',key='fake')).understand('test',[],[{'id':'product.801.stability'}])
        self.assertIsNone(answer);self.assertEqual(status,'invalid_answer_id')

    def test_candidates_do_not_mix_concrete_products(self):
        kb=Knowledge(ROOT/'data/nets_801_804.json')
        rows=candidates_for(kb,'这个牢靠不','801')
        for row in rows:
            if row.get('product_id') not in ('801',None):
                self.assertEqual(row.get('scope'), 'catalog')

    def test_unknown_guarantee_not_sent_to_intent_model(self):
        kb=Knowledge(ROOT/'data/nets_801_804.json')
        self.assertEqual(candidates_for(kb,'保证能挂50公斤吗','801'),[])
