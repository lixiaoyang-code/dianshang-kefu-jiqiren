import copy
import json
import unittest
import test_faq_admin as fixtures
from app.draft_coverage import covered_drafts


class DraftCoverageTests(unittest.TestCase):
    def rows(self):
        base=dict(scene_id='test',scope='product',product_ids=['801','802','803','804'],
                  priority=0,keywords=[],images=[],conditions={'reception':'presales','stages':['presales'],'valid_from':None,'valid_until':None})
        active={**copy.deepcopy(base),'id':'active','status':'active','standard_answer':'四款共用的核准话术'}
        draft={**copy.deepcopy(base),'id':'draft','status':'needs_review','product_ids':['804'],'standard_answer':None,'answer_parts':None}
        return active,draft

    def test_empty_null_draft_is_covered_but_content_is_preserved(self):
        active,draft=self.rows()
        self.assertEqual(covered_drafts({'records':[active,draft]}),[{'id':'draft','scene_id':'test','covered_by':'active'}])
        for field,value in [('standard_answer','另一份待核对话术'),('answer_parts',['保留的内容']),('images',[{'url':'/static/images/evidence.png'}]),('keywords',['定向触发']),('priority',1),('scene_id','other')]:
            with self.subTest(field=field):
                changed={**draft,field:value}
                self.assertEqual(covered_drafts({'records':[active,changed]}),[])

    def test_full_product_reception_stage_and_time_coverage_required(self):
        active,draft=self.rows()
        for changed in [dict(active,product_ids=['801']),
                        dict(active,conditions={'reception':'aftersales','stages':[]}),
                        dict(draft,conditions={'reception':'all','stages':[]})]:
            rows=[changed,draft] if changed.get('id')=='active' else [active,changed]
            self.assertEqual(covered_drafts({'records':rows}),[])
        active['conditions']['valid_until']='2026-11-08T00:00:00+08:00'
        self.assertEqual(covered_drafts({'records':[active,draft]}),[])
        draft['conditions']['valid_until']='2026-11-07T00:00:00+08:00'
        self.assertEqual(len(covered_drafts({'records':[active,draft]})),1)


class CoveredCleanupAPITests(unittest.TestCase):
    setUp=fixtures.FAQAdminTests.setUp
    tearDown=fixtures.FAQAdminTests.tearDown
    snapshot=fixtures.FAQAdminTests.snapshot
    stability=fixtures.FAQAdminTests.stability

    def seed(self):
        doc=json.loads(self.path.read_text(encoding='utf-8'));sid='test.coverage'
        scene=dict(id=sid,name='覆盖清理验收',type='industry',category='测试',question_variants=['覆盖清理验收'])
        source=self.stability();source.update(id='coverage.active',scene_id=sid,scene_name=scene['name'],
            question_variants=scene['question_variants'],product_ids=['801','802','803','804'],
            standard_answer='保持的核准答案',answer_parts=['保持的核准答案'],images=[],keywords=[],priority=0)
        doc['scenes'].append(scene);doc['records'].append(source)
        for i,pid in enumerate(['803','804']):doc['records'].append({**copy.deepcopy(source),'id':f'coverage.draft{i}',
            'status':'needs_review','product_ids':[pid],'standard_answer':None,'answer_parts':[]})
        self.path.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
        return sid,source

    def test_cleanup_needs_confirmation_and_preserves_active_answer(self):
        sid,source=self.seed();data=self.client.get('/api/scenes').json()
        candidates=[r for r in data['covered_drafts'] if r['scene_id']==sid]
        self.assertEqual(len(candidates),2)
        body=dict(revision=data['revision'],scene_id=sid,ids=[r['id'] for r in candidates],confirmed=False)
        before=self.path.read_bytes()
        self.assertEqual(self.client.post('/api/faq/cleanup-covered',json=body).status_code,422)
        self.assertEqual(self.path.read_bytes(),before)
        body['confirmed']=True
        result=self.client.post('/api/faq/cleanup-covered',json=body)
        self.assertEqual(result.status_code,200,result.text)
        self.assertEqual(next(r for r in self.snapshot()['records'] if r['id']==source['id']),source)
        disk=json.loads(self.path.read_text(encoding='utf-8'))
        for row in disk['records']:
            if row['id'] in body['ids']:
                self.assertEqual(row['deleted_reason'],'covered_empty_draft');self.assertEqual(row['covered_by'],source['id'])
        self.assertIn(before,[p.read_bytes() for p in (self.path.parent/'backups').glob('*.json')])

    def test_cleanup_cannot_delete_content_or_use_stale_revision(self):
        sid,source=self.seed();revision=self.snapshot()['revision'];before=self.path.read_bytes()
        body=dict(revision=revision,scene_id=sid,ids=[source['id']],confirmed=True)
        self.assertEqual(self.client.post('/api/faq/cleanup-covered',json=body).status_code,409)
        self.assertEqual(self.path.read_bytes(),before)
        body.update(revision='stale',ids=['coverage.draft0'])
        self.assertEqual(self.client.post('/api/faq/cleanup-covered',json=body).status_code,409)

    def test_review_is_a_separate_task_page_and_old_bookmark_redirects(self):
        page=self.client.get('/review');self.assertEqual(page.status_code,200)
        self.assertIn('data-knowledge-view="review"',page.text)
        self.assertIn('id="review-tasks"',page.text)
        self.assertIn('href="/review" id="review-nav" aria-current="page"',page.text)
        old=self.client.get('/knowledge?status=needs_review',follow_redirects=False)
        self.assertEqual(old.status_code,303);self.assertEqual(old.headers['location'],'/review')
