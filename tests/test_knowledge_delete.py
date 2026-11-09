import copy
import json
import unittest
import test_faq_admin as fixtures
from app.main import app


class KnowledgeDeleteTests(unittest.TestCase):
    setUp=fixtures.FAQAdminTests.setUp
    tearDown=fixtures.FAQAdminTests.tearDown
    snapshot=fixtures.FAQAdminTests.snapshot
    stability=fixtures.FAQAdminTests.stability
    save=fixtures.FAQAdminTests.save
    chat=fixtures.FAQAdminTests.chat

    def delete(self,rid,target='faq',revision=None,confirmed=True,**kwargs):
        return self.client.post('/api/'+target+'/delete',json={
            'id':rid,'revision':revision or self.snapshot()['revision'],'confirmed':confirmed},**kwargs)

    def test_requires_confirmation_current_revision_and_same_origin(self):
        row=self.stability();before=self.path.read_bytes();rev=self.snapshot()['revision']
        self.assertEqual(self.delete(row['id'],confirmed=False).status_code,422)
        self.assertEqual(self.delete(row['id'],headers={'Origin':'https://unrelated.example'}).status_code,403)
        self.assertEqual(self.path.read_bytes(),before)
        self.assertEqual(self.save(row).status_code,200)
        updated=self.path.read_bytes()
        self.assertEqual(self.delete(row['id'],revision=rev).status_code,409)
        self.assertEqual(self.path.read_bytes(),updated)

    def test_answer_delete_removes_aliases_and_blocks_legacy_reply(self):
        row=self.stability();before=self.path.read_bytes();others={r['id']:copy.deepcopy(r) for r in self.snapshot()['records']}
        result=self.delete(row['id']);self.assertEqual(result.status_code,200,result.text)
        ids=set(result.json()['deleted_ids']);self.assertIn(row['id'],ids)
        self.assertFalse(ids & {r['id'] for r in self.snapshot()['records']})
        disk=json.loads(self.path.read_text(encoding='utf-8'))
        self.assertTrue(all(r.get('deleted_at') and r['status']=='disabled' for r in disk['records'] if r['id'] in ids))
        for r in self.snapshot()['records']:self.assertEqual(r,others[r['id']])
        self.assertFalse(self.chat('支架稳吗')['send_to_customer'])
        self.assertEqual(self.save(row).status_code,409)
        self.assertIn(before,[p.read_bytes() for p in (self.path.parent/'backups').glob('*.json')])
        self.assertEqual(self.delete(row['id']).status_code,404)

    def test_scene_delete_cascades_but_preserves_other_scenes(self):
        sid=self.stability()['scene_id']
        before=self.client.get('/api/scenes').json()
        result=self.delete(sid,'scenes');self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(result.json()['deleted_scene_id'],sid)
        after=self.client.get('/api/scenes').json()
        self.assertNotIn(sid,[s['id'] for s in after['scenes']])
        self.assertEqual(after['scenes'],[s for s in before['scenes'] if s['id']!=sid])
        self.assertNotIn(sid,[s['id'] for s in app.state.service.kb.faq.scenes])
        self.assertFalse(self.chat('支架稳吗')['send_to_customer'])
