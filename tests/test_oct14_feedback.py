import unittest
import test_nets as fixtures
from app.main import app

class FeedbackTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def select(self,pid='801'):
        self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})

    def test_80_width_with_no_product(self):
        self.assertIn('全伸缩款',self.chat('有80宽的吗？','answered')['answer'])

    def test_80_width_rod(self):
        self.assertIn('全伸缩款',self.chat('有没有80宽的杆子','answered')['answer'])

    def test_pure_upper_and_lower_recommend_120(self):
        for query in ['我睡上铺怎么选','睡下铺选哪款好','上下铺怎么选']:
            self.sid=self.client.post('/api/sessions').json()['session_id'];self.select()
            r=self.chat(query,'answered')
            self.assertTrue(r['answer'].startswith('推荐120高度款'))
            self.assertTrue(r['answer'].endswith(app.state.service.kb.products['801']['facts']['bunk_recommendation']))

    def test_pure_range_does_not_overwrite_802(self):
        r=self.chat('全伸缩款伸缩范围','answered')
        self.assertIn('110–120',r['answer'])
        self.assertNotIn('65到120',r['answer'])

    def test_stability_image(self):
        self.select();r=self.chat('稳固吗？会不会慌？','answered')
        self.assertIn('10斤',r['answer']);self.assertTrue(r['images'])
        image=self.client.get(r['images'][0]['url'])
        self.assertEqual(image.status_code,200)
        self.assertTrue(image.headers['content-type'].startswith('image/'))

    def test_power_strip_not_stability_then_charge(self):
        self.select()
        r=self.chat('排插可以过吗','answered')
        self.assertIn('排插',r['answer']);self.assertNotIn('承重',r['answer']);self.assertTrue(all(a['id']!='pole-load-user' for a in r['images']))
        self.chat('那我怎么充电','duplicate')
        self.chat('稳固吗','answered')

    def test_power_strip_short_followup(self):
        self.select();self.assertIn('排插',self.chat('排插呢','answered')['answer'])

    def test_install_no_hassle(self):
        self.select();self.assertIn('不麻烦',self.chat('安装麻烦吗','answered')['answer'])

    def test_detach_wash_not_machine_wash(self):
        self.select();r=self.chat('可以拆卸清洗吗','answered')
        self.assertIn('可以拆卸清洗',r['answer']);self.assertNotIn('机洗',r['answer'])

    def test_formaldehyde_exact_user_script(self):
        self.select();r=self.chat('有没有甲醛','answered')
        self.assertEqual(r['answer'],app.state.service.kb.products['801']['short_replies']['formaldehyde_script'])

    def test_repeat_stability_no_repeat_image(self):
        self.select();self.chat('稳固吗','answered')
        r=self.chat('会不会晃','duplicate');self.assertEqual(r['images'],[])

    def test_semantic_power_strip_cannot_hit_stability(self):
        if not app.state.service.semantic:self.skipTest('本地模型未加载')
        doc,trace=app.state.service.semantic.search('排插从哪里塞进去','801')
        self.assertTrue(doc is None or doc['field']=='charging_port')
