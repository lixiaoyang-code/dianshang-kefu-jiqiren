import hashlib
import json
import unittest
import test_nets as fixtures
from app.config import ROOT

class SourceImageTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def test_full_catalog_and_selected_files(self):
        catalog=json.loads((ROOT/'data/image_catalog.json').read_text(encoding='utf8'))['images']
        self.assertEqual(len(catalog),167)
        active=[x for x in catalog if x['status']=='active']
        self.assertEqual(len(active),43)
        for x in active:
            f=ROOT / x['url'].lstrip('/')
            self.assertEqual(hashlib.sha256(f.read_bytes()).hexdigest(),x['sha256'])
            self.assertEqual(self.client.get(x['url']).status_code,200)

    def test_charge_and_door_images_product_scoped(self):
        for pid in ['801','802','803','804']:
            self.sid=self.client.post('/api/sessions').json()['session_id']
            self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})
            for query in ['排插可以过吗','这个开门']:
                r=self.chat(query,'answered')
                self.assertTrue(r['images'])
                self.assertTrue(all(a['id'].startswith(pid+'-') for a in r['images']))
                self.assertLessEqual(len(r['images']),2)

    def test_real_photo_source_question(self):
        r=self.chat('小狗联名款有实物图吗','answered')
        self.assertTrue(r['images'])
        self.assertTrue(all(i['id'].startswith('803-') for i in r['images']))

    def test_outdated_diameter_and_color_not_active(self):
        catalog=json.loads((ROOT/'data/image_catalog.json').read_text(encoding='utf8'))['images']
        for rid in ['803-20','801-09','804-33']:
            self.assertEqual(next(x for x in catalog if x['id']==rid)['status'],'superseded_or_conflict')

    def test_reference_scripts_do_not_activate_promotions(self):
        scripts=json.loads((ROOT/'data/source_sales_scripts.json').read_text(encoding='utf8'))['scripts']
        self.assertEqual(len(scripts),49)
        self.assertTrue(all(not s['auto_send'] for s in scripts))
        self.chat('小狗联名款现在送什么赠品','handoff')
