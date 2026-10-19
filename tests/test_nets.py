import tempfile
import unittest
from pathlib import Path
from fastapi.testclient import TestClient
from app.main import app
from app.config import ROOT, Settings
from app.model import Model
from app.knowledge import Knowledge
from app.service import Service

class NetsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.client = TestClient(app)
        self.client.__enter__()
        for h in app.state.service.logger.handlers:
            h.close()
        app.state.service = Service(Knowledge(ROOT / 'data/nets_801_804.json'),
                                    Model(Settings(mode='mock', key='')), Path(self.temp.name))
        self.sid = self.client.post('/api/sessions').json()['session_id']

    def tearDown(self):
        self.client.__exit__(None,None,None)
        self.temp.cleanup()

    def chat(self, message, status):
        r = self.client.post('/api/chat', json={'session_id':self.sid,'message':message})
        self.assertEqual(r.status_code,200)
        d = r.json()
        self.assertEqual(d['status'], 'suppressed' if status == 'handoff' else status, d)
        if d['status'] in ('suppressed','error','duplicate'):
            self.assertEqual(d['answer'],'')
            self.assertFalse(d['send_to_customer'])
            self.assertFalse(d['session']['needs_human'])
        else:
            self.assertTrue(d['answer'])
        return d

    def test_only_four_products(self):
        self.assertEqual({p['id'] for p in self.client.get('/api/products').json()}, {'801','802','803','804'})
    def test_material(self):
        self.assertIn('聚酯纤维',self.chat('801材质是什么','answered')['answer'])
    def test_801_doors(self):
        self.assertIn('单开门',self.chat('801开门','answered')['answer'])
    def test_802_doors(self):
        self.assertIn('单开门',self.chat('802开门','answered')['answer'])
    def test_803_doors_different(self):
        self.assertIn('全系列均为三开门',self.chat('803开门','answered')['answer'])
    def test_804_doors(self):
        self.assertIn('90 cm',self.chat('804开门','answered')['answer'])
    def test_telescope_802(self):
        self.assertIn('145–190',self.chat('802伸缩范围','answered')['answer'])
    def test_telescope_803(self):
        r=self.chat('803伸缩范围','answered');self.assertIn('±4',r['answer']);self.assertNotIn('145',r['answer'])
    def test_telescope_801_conflict(self):
        self.assertIn('65–120',self.chat('801伸缩范围','answered')['answer'])
    def test_telescope_804_confirmed(self):
        self.assertIn('186–190',self.chat('804伸缩范围','answered')['answer'])
    def test_packaging_802(self):
        r=self.chat('802包装尺寸','answered');self.assertIn('95×15×15',r['answer']);self.assertEqual(len(r['debug']['retrieval']['hits']),1)
    def test_packaging_801_conflict(self):
        self.chat('801包装尺寸','handoff')
    def test_packaging_804_conflict(self):
        self.chat('804包装尺寸','handoff')
    def test_curtain_coating_confirmed(self):
        self.assertIn('无涂层',self.chat('803有涂层吗','answered')['answer'])
    def test_no_demo_shipping(self):
        r=self.chat('什么时候发货','answered');self.assertIn('京东物流',r['answer'])
    def test_no_promotion(self):
        self.chat('803赠送什么','handoff')
    def test_no_formaldehyde_promise(self):
        self.assertIn('A类母婴级证书',self.chat('802有甲醛吗','answered')['answer'])
    def test_card_keeps_803(self):
        self.chat('803开门','answered')
        self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'agent_card','product_id':'801'})
        r=self.chat('这个开门','duplicate');self.assertEqual(r['session']['current_product_id'],'803')
    def test_switch_by_alias(self):
        self.chat('801开门','answered');r=self.chat('线条小狗开门','answered');self.assertEqual(r['session']['current_product_id'],'803')
    def test_multi_products(self):
        self.chat('801和803有什么区别','clarify')
    def test_numeric_boundary(self):
        kb=app.state.service.kb;self.assertEqual(kb.mentions('1801材质'),[]);self.assertEqual(kb.mentions('8010'),[])
    def test_unknown_number_does_not_reuse(self):
        self.chat('801开门','answered');self.chat('805开门','clarify')
    def test_sources(self):
        r=self.chat('803开门','answered');h=r['debug']['retrieval']['hits'][0]
        self.assertEqual(h['sources'][0]['cell'],'C6');self.assertEqual(h['sources'][0]['sheet'],'宿舍床帘-线条小狗联名803')
    def test_washing(self):
        self.assertIn('自然风干',self.chat('802可以机洗吗','answered')['answer'])
    def test_shade_sides(self):
        self.assertIn('靠墙',self.chat('804四面和五面区别','answered')['answer'])
    def test_charging(self):
        self.assertIn('预留充电口',self.chat('803有充电口吗','answered')['answer'])
    def test_unconfirmed_product(self):
        self.chat('这个开门','clarify')
    def test_missing_803_size(self):
        self.assertIn('90×190×110', self.chat('803尺寸','answered')['answer'])
    def test_803_pole_diameter(self):
        self.assertIn('22 mm',self.chat('803支架多粗','answered')['answer'])

    def test_confirmed_diameters_all_products(self):
        for pid, diameter in [('801',12),('802',16),('803',22),('804',16)]:
            with self.subTest(product=pid):
                r=self.chat(f'{pid}支架直径','answered')
                self.assertIn(f'{diameter} mm',r['answer'])
                self.assertNotIn('壁厚',r['answer'])
                h=r['debug']['retrieval']['hits'][0]
                self.assertEqual(h['sources'][0]['type'],'user_confirmation')
                self.assertEqual(h['updated_at'],'2026-10-13')

    def test_wall_thickness_separate_from_diameter(self):
        for pid in ['801','802','803','804']:
            r=self.chat(f'{pid}壁厚','answered')
            self.assertIn('0.38 mm',r['answer'])
            self.assertNotIn('直径',r['answer'])

    def test_802_new_heights_replace_old(self):
        answer=self.chat('802伸缩尺寸','answered')['answer']
        for expected in ['80–100','100–115','110–120','145–190','65–90']:
            self.assertIn(expected,answer)
        self.assertNotIn('70–',answer)

    def test_804_ranges(self):
        answer=self.chat('804伸缩尺寸','answered')['answer']
        for expected in ['186–190','76–90','90–100','100–110','110–120']:
            self.assertIn(expected,answer)

    def test_current_colors(self):
        for pid in ['802','804']:
            r=self.chat(f'{pid}颜色','answered')
            self.assertIn('仅蓝色',r['answer'])

    def test_discontinued_color_question(self):
        self.assertIn('仅蓝色',self.chat('802有米色吗','answered')['answer'])

    def test_top_is_not_uncoated_claim(self):
        r=self.chat('803顶部有涂层吗','answered')
        self.assertIn('覆膜',r['answer'])
        self.assertNotIn('无涂层',r['answer'])

    def test_certificate_not_inferred_from_coating(self):
        self.chat('802无涂层所以安全有证书吗','handoff')

    def test_old_values_not_retrieved(self):
        r=self.chat('803直径和壁厚','answered')
        self.assertIn('22 mm',r['answer'])
        self.assertIn('0.38 mm',r['answer'])
        self.assertNotIn('21 mm',r['answer'])
        self.assertNotIn('0.31',r['answer'])
    def test_no_unverified_marketing_in_facts(self):
        for p in app.state.service.kb.products.values():
            for text in p['facts'].values():
                self.assertFalse(any(t in text for t in ['0甲醛','无毒','100%','仅限今天','最好','绝对']))
