"""来源副本不会在主答案停用或修改后重新生效。"""
import unittest
import test_nets as fixtures
import test_faq_admin as admin_fixtures
from app.main import app


class DimensionAliasTests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown
    chat=fixtures.NetsTests.chat

    def test_disabling_only_primary_prevents_old_source_fallback(self):
        for pid,field,question in [('801','height_range','高度可伸缩是什么意思'),('802','telescoping','支架可以伸缩吗')]:
            with self.subTest(product=pid):
                self.sid=self.client.post('/api/sessions').json()['session_id']
                self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'customer_select','product_id':pid})
                primary=next(r for r in app.state.service.kb.faq.records if r['id']==f'product.{pid}.{field}')
                primary['status']='disabled'
                result=self.chat(question,'handoff')
                self.assertEqual(result['answer_parts'],[])

    def test_source_references_are_not_duplicate_maintenance_cards(self):
        scenes=self.client.get('/api/scenes').json()['scenes']
        records=[r for s in scenes for r in s['answers']]
        self.assertFalse(any(r.get('canonical_answer_id') for r in records))
        self.assertTrue(any(r['id']=='product.801.height_range' for r in records))


class DimensionAliasSaveTests(unittest.TestCase):
    setUp=admin_fixtures.FAQAdminTests.setUp
    tearDown=admin_fixtures.FAQAdminTests.tearDown
    snapshot=admin_fixtures.FAQAdminTests.snapshot
    save=admin_fixtures.FAQAdminTests.save

    def test_source_patch_points_maintainer_to_primary_without_writing(self):
        row=next(r for r in self.snapshot()['records'] if r['id']=='qa.801.C16')
        before=self.path.read_bytes()
        response=self.save({'id':row['id'],'standard_answer':'来源不应独立覆盖'})
        self.assertEqual(response.status_code,422)
        self.assertIn('主答案',response.json()['detail'])
        self.assertEqual(self.path.read_bytes(),before)
