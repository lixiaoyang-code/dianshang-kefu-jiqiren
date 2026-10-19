import unittest
import time
import test_nets as fixtures
from app.main import app


class CustomerPhraseTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def test_shipping_yes_continuation(self):
        self.chat('多久发货','answered')
        r=self.chat('有','handoff')
        self.assertEqual(r['answer'],'')
    def test_shipping_no_continuation(self):
        self.chat('多久发货','answered')
        self.chat('没有','handoff')
    def test_200_meters_typo(self):
        self.chat('803尺寸','answered')
        self.assertIn('200厘米',self.chat('200米的床可以用吗','clarify')['answer'])
    def test_upper_bunk(self):
        self.assertIn('三开',self.chat('我睡上铺选哪个？','clarify')['answer'])
    def test_width_followup(self):
        self.chat('803尺寸','answered');self.chat('80*190可以用吗？','answered')
        self.chat('宽度80长度190','duplicate')
    def test_wall_side(self):
        self.chat('803尺寸','answered')
        self.assertIn('不能打开',self.chat('靠墙侧可以打开吗','answered')['answer'])
    def test_803_colors(self):
        self.chat('803尺寸','answered')
        r=self.chat('有米色吗','answered')
        self.assertIn('粉色',r['answer']);self.assertNotIn('有米色',r['answer'])
    def test_machine_wash(self):
        self.chat('803尺寸','answered')
        self.assertIn('可以机洗',self.chat('能机洗吗','answered')['answer'])
    def test_tomorrow_arrival_not_promised(self):
        self.assertIn('时效',self.chat('明天能收到吗','answered')['answer'])
    def test_all_axis_recommendation(self):
        self.assertIn('全伸缩款',self.chat('有没有长宽高都可以伸缩的款式','answered')['answer'])

    def test_all_axis_customer_word_order(self):
        r=self.chat('长宽高都可以伸缩的有吗','answered')
        self.assertTrue(r['answer'].startswith('有的亲'))
        self.assertIn('全伸缩款',r['answer']);self.assertNotIn('802',r['answer'])
    def test_dog_alias_difference(self):
        r=self.chat('小狗款有什么区别','answered');self.assertIn('22毫米',r['answer'])
    def test_question_mark(self):
        self.chat('？','clarify')
    def test_shadow_not_guaranteed(self):
        self.chat('803尺寸','answered');self.chat('会有皮影戏吗','handoff')
    def test_shading(self):
        self.chat('803尺寸','answered');self.assertIn('遮光',self.chat('能遮住光吗','answered')['answer'])
    def test_pole_material_not_mesh(self):
        self.chat('803尺寸','answered')
        r=self.chat('支架什么材质','answered');self.assertIn('碳素钢',r['answer']);self.assertNotIn('聚酯',r['answer'])
    def test_roof(self):
        self.chat('803尺寸','answered')
        r=self.chat('顶棚是什么材质','answered');self.assertIn('覆膜',r['answer']);self.assertNotIn('零甲醛',r['answer'])
    def test_mosquito_questions(self):
        self.chat('803尺寸','answered')
        self.chat('防蚊吗','answered');self.chat('有蚊帐吗','duplicate')
    def test_courier(self):
        r=self.chat('物流','answered');self.assertIn('77仓',r['answer']);self.assertIn('48小时',r['answer'])
    def test_dog_width_ambiguity(self):
        self.chat('小狗款支架多宽','clarify')
    def test_dog_price_difference(self):
        self.assertIn('最粗',self.chat('小狗款为什么贵这么多','answered')['answer'])
    def test_waiting_cooldown(self):
        r=self.chat('803保修几年','handoff');rid=r['debug']['request_id']
        s=app.state.service.sessions[self.sid];s.last_waiting_at=time.perf_counter()
        s.waiting[rid]['received_at']=time.perf_counter()-26
        self.assertFalse(self.client.post(f'/api/sessions/{self.sid}/waiting/{rid}').json()['send_to_customer'])

    def test_logistics_similar_question_not_repeated(self):
        self.chat('多久发货','answered')
        r=self.chat('明天能收到吗','duplicate')
        self.assertFalse(r['send_to_customer'])
        self.assertEqual(r['session']['waiting'],{})

    def test_dedup_different_product_still_answers(self):
        self.chat('802材质','answered')
        self.chat('803材质','answered')

    def test_dedup_different_height_still_answers(self):
        a=self.chat('802 90cm高度伸缩范围','answered')
        b=self.chat('802 110cm高度伸缩范围','answered')
        self.assertNotEqual(a['answer'],b['answer'])

    def test_no_bed_size_interrogation(self):
        self.chat('803尺寸','answered')
        r=self.chat('80*190可以用吗','answered')
        self.assertIn('全伸缩款',r['answer'])
        self.assertNotIn('床板内尺寸',r['answer'])
