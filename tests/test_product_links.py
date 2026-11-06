import unittest
from unittest.mock import AsyncMock,patch
import test_nets as fixtures
from app.main import app


class ProductLinkTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown

    def link(self,url='https://item.example.com/803.html',pid=None):
        return self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_link','url':url,'product_id':pid})

    def test_explicit_product_wins_over_digits_in_url_without_model(self):
        svc=app.state.service
        before=svc.statistics.snapshot()['counts']['all_records']
        with patch.object(svc.model,'select',new=AsyncMock(side_effect=AssertionError('no model'))):
            result=self.link(pid='802');self.assertEqual(result.status_code,200)
            r=result.json();self.assertEqual(r['session']['current_product_id'],'802')
            self.assertTrue(r['session']['product_confirmed']);self.assertEqual(r['status'],'linked')
            self.assertEqual(r['link']['product_id'],'802')
        self.assertEqual(svc.statistics.snapshot()['counts']['all_records'],before)
        reply=self.client.post('/api/chat',json={'session_id':self.sid,'message':'长宽能调节吗'}).json()
        self.assertTrue(reply['send_to_customer'],reply);self.assertEqual(reply['session']['current_product_id'],'802')
        self.assertIn('145',reply['answer'])

    def test_unassociated_link_clears_old_product_and_dimension_context(self):
        s=app.state.service.sessions[self.sid];s.current_product_id='801';s.product_confirmed=True
        s.last_dimension={'product_id':'801'};s.waiting={'old':{}};s.answered_keys=['old']
        r=self.link().json()
        self.assertEqual(r['status'],'product_required');self.assertIsNone(r['session']['current_product_id'])
        self.assertFalse(r['session']['product_confirmed']);self.assertIsNone(r['session']['last_dimension'])
        self.assertEqual(r['session']['waiting'],{});self.assertEqual(r['session']['answered_keys'],[])

    def test_invalid_link_and_unknown_product_do_not_mutate_session(self):
        for value in ['javascript:alert(1)','file:///C:/secret','https://a:b@example.com/x','https://exa mple.com','https://example.com:bad/x','https://example.com\\x','/relative']:
            self.assertEqual(self.link(value,'801').status_code,422,value)
        self.assertEqual(self.link(pid='999').status_code,400)
        self.assertEqual(app.state.service.sessions[self.sid].product_links,[])
        self.assertIsNone(app.state.service.sessions[self.sid].current_product_id)

    def test_link_history_is_bounded_and_clear_memory_clears_links(self):
        for i in range(22):self.assertEqual(self.link(f'https://example.com/{i}','801').status_code,200)
        self.assertEqual(len(app.state.service.sessions[self.sid].product_links),20)
        self.client.post(f'/api/sessions/{self.sid}/reset',json={'mode':'memory'})
        self.assertEqual(app.state.service.sessions[self.sid].product_links,[])

    def test_product_card_without_url_associates_product(self):
        for value in [None, '', '   ']:
            response=self.link(value,'802')
            self.assertEqual(response.status_code,200)
            self.assertIsNone(response.json()['link']['url'])
            self.assertEqual(response.json()['session']['current_product_id'],'802')
        self.assertEqual(self.link('',None).status_code,422)
        self.assertEqual(app.state.service.sessions[self.sid].current_product_id,'802')
