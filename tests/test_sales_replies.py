import unittest
from app.main import app
import test_nets as fixtures

class SalesReplyTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def select(self,pid):
        self.sid=self.client.post('/api/sessions').json()['session_id']
        self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})

    def test_sound_for_all_four(self):
        for pid in ['801','802','803','804']:
            self.select(pid)
            r=self.chat('隔音吗','answered')
            for value in ['600g','轻微','耳塞']:self.assertIn(value,r['answer'])
            self.assertEqual(r['answer'],app.state.service.kb.products[pid]['short_replies']['sound_insulation'])

    def test_stability_all_four(self):
        for pid in ['801','802','803','804']:
            self.select(pid)
            r=self.chat('支架稳吗','answered')
            for value in ['稳固','10斤']:self.assertIn(value,r['answer'])
            self.assertTrue(r['images'])

    def test_stable_and_material_source_question(self):
        self.select('801')
        r=self.chat('支架结实吗，什么材质的','answered')
        self.assertIn('10斤',r['answer'])

    def test_sound_repeat_not_sent(self):
        self.select('803')
        self.chat('隔音吗','answered')
        self.chat('能隔音吗','duplicate')

    def test_load_promise_does_not_get_generic_yes(self):
        self.select('803')
        self.chat('支架稳吗，能挂两桶水10斤吗','handoff')
