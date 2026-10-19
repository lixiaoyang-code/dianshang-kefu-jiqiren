import unittest
import test_nets as fixtures
from app.main import app

class CatalogFeedbackTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def select(self,pid):
        self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})

    def test_load_question(self):
        self.select('801')
        r=self.chat('承重怎么样','answered')
        self.assertIn('10斤',r['answer'])
        self.assertEqual(r['images'][0]['id'],'pole-load-user')

    def test_cross_catalog_recommend_no_binding_change(self):
        self.select('801')
        r=self.chat('有全伸缩支架吗','answered')
        self.assertIn('全伸缩款',r['answer'])
        self.assertEqual(r['session']['current_product_id'],'801')
        self.chat('有全伸缩款吗','duplicate')
        self.assertEqual(app.state.service.sessions[self.sid].current_product_id,'801')

    def test_catalog_with_current_product_prefix(self):
        self.select('801');r=self.chat('纯色款有全伸缩的支架吗','answered')
        self.assertEqual(r['session']['current_product_id'],'801')

    def test_explicit_customer_switch_still_works(self):
        self.select('801');r=self.chat('我换成全伸缩款，尺寸','answered')
        self.assertEqual(r['session']['current_product_id'],'802')

    def test_generic_pole_question(self):
        self.select('801');self.assertIn('碳素钢',self.chat('什么支架','answered')['answer'])

    def test_coating_exact_script(self):
        self.select('801');r=self.chat('有涂层吗','answered')
        self.assertEqual(r['answer'],app.state.service.kb.products['801']['short_replies']['coating'])

    def test_dog_expensive_exact_script(self):
        self.select('803');r=self.chat('为什么这么贵','answered')
        self.assertIn('最稳固',r['answer']);self.assertIn('22毫米',r['answer'])

    def test_no_install_how_with_chosen_image(self):
        self.select('804');r=self.chat('怎么安装？','answered')
        self.assertIn('很方便',r['answer'])
        self.assertEqual(r['images'][0]['id'],'no-install-steps-user')
        self.assertEqual(self.client.get(r['images'][0]['url']).status_code,200)

    def test_reference_prices_not_all_sku(self):
        for pid,amount in [('801',260),('802',280),('803',388),('804',316)]:
            self.select(pid);r=self.chat('多少钱','answered')
            self.assertIn(str(amount),r['answer']);self.assertIn('约',r['answer'])
            if pid=='801':self.assertIn('120高五面款',r['answer'])
