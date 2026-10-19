import unittest
import test_nets as fixtures

class SalesFeedbackRound3Tests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def select(self,pid='801'):
        self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})

    def test_pole_reply_has_sales_and_facts(self):
        self.select();r=self.chat('什么支架','answered')
        for text in ['碳素钢','0.38','稳固']:self.assertIn(text,r['answer'])

    def test_dog_price_polished(self):
        self.select('803');r=self.chat('小狗款为什么这么贵','answered')
        for text in ['联名','22毫米','最稳固']:self.assertIn(text,r['answer'])

    def test_no_install_cross_catalog_keeps_product_correct_image(self):
        self.select();r=self.chat('有免安装的款式吗','answered')
        self.assertEqual(r['session']['current_product_id'],'801')
        self.assertIn('免安装款',r['answer'])
        self.assertEqual(r['images'][0]['id'],'no-install-steps-user')
        self.assertTrue(r['debug']['retrieval']['hits'][0]['id'].startswith('product.804.'))

    def test_best_recommendation_and_image(self):
        self.select();r=self.chat('你们最好的是哪一款','answered')
        self.assertIn('小狗联名款',r['answer'])
        self.assertEqual(r['session']['current_product_id'],'801')
        self.assertTrue(all(a['id'].startswith('803-') for a in r['images']))

    def test_freight_insurance_no_product_needed(self):
        self.assertIn('有运费险',self.chat('运费险有吗','answered')['answer'])
        self.chat('有运费险吗','duplicate')

    def test_arrival_and_expedite(self):
        r=self.chat('多久能到','answered')
        for text in ['京东物流','24小时发出','48小时','加急']:self.assertIn(text,r['answer'])
        self.assertNotIn('已加急',r['answer'])

    def test_catalog_no_binding_no_selection(self):
        r=self.chat('有免安装款吗','answered')
        self.assertIsNone(r['session']['current_product_id'])
        self.assertTrue(r['images'])
