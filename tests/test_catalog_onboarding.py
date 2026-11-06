import asyncio,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app.config import Settings,ROOT
from app.knowledge import Knowledge
from app.service import Service
from app.model import Model
from app.rag import RAGAssistant
from app.common_intents import identify
from scripts.onboard_catalog import merge


class CatalogOnboardingTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.env=patch.dict('os.environ',{'SEMANTIC_MODE':'off'});self.env.start()
        self.svc=Service(Knowledge(),Model(Settings(mode='mock',key='')),Path(self.temp.name))
    def tearDown(self):
        for h in self.svc.logger.handlers:h.close()
        self.env.stop();self.temp.cleanup()
    async def ask(self,pid,q,reception='presales',stage='presales'):
        s=self.svc.create();return await self.svc.chat(s.session_id,q,pid,reception,stage)

    async def test_seven_products_have_independent_answers(self):
        self.assertEqual(len(self.svc.kb.products),11)
        for pid,q,expected in [('tietie','什么材质','记忆棉'),('cloudquilt','能机洗吗','轻柔'),
            ('plushblanket','厚度多少','12毫米'),('heater','取暖器怎么选型号','型号'),
            ('nonwovenblanket','单控和双控的区别是','左右'),('latexpillow','什么尺寸','60厘米'),('601','高度多少','170')]:
            r=await self.ask(pid,q);self.assertTrue(r['send_to_customer'],r);self.assertIn(expected,r['answer'])
            self.assertNotIn('store.expedite',[h['id'] for h in r['debug']['retrieval']['hits']])

    async def test_new_product_never_uses_old_pole_or_dimensions(self):
        for pid,q in [('tietie','承重怎么样'),('heater','长宽可以伸缩吗'),('cloudquilt','支架什么材质')]:
            r=await self.ask(pid,q);self.assertFalse(r['send_to_customer'],r)
            self.assertNotIn('10斤',r['answer'])

    async def test_imported_static_facts_do_not_inherit_collector_reception(self):
        for reception,stage in [('presales','presales'),('aftersales','aftersales')]:
            for pid,q,expected in [('heater','这个有多重','3.7'),('plushblanket','插电吗','插电')]:
                r=await self.ask(pid,q,reception,stage)
                self.assertTrue(r['send_to_customer'],r)
                self.assertIn(expected,r['answer'])

    async def test_shared_interactions_work_for_catalog_products_without_model(self):
        from unittest.mock import AsyncMock
        with patch.object(self.svc.model,'understand',new=AsyncMock(side_effect=AssertionError('no model'))):
            for pid in ['801','cloudquilt','tietie']:
                for q in ['好的','好的，谢谢','谢谢，拜拜','没有其他问题了']:
                    r=await self.ask(pid,q,'aftersales','aftersales')
                    self.assertTrue(r['send_to_customer'],r)
                    self.assertEqual(r['session']['current_product_id'],pid)
                    if q=='好的':self.assertEqual(r['answer'],'💗')

    async def test_quilt_weight_asks_conditions_and_is_not_a_weight_promise(self):
        for q in ['几斤合适','买几斤合适','好的，几斤合适']:
            r=await self.ask('cloudquilt',q)
            self.assertEqual(r['status'],'clarify',r)
            self.assertTrue(r['send_to_customer']);self.assertIn('室温',r['answer'])
            self.assertNotRegex(r['answer'],r'\d+\s*斤')
            self.assertEqual(r['debug']['editable_answer_ids'],['catalog.cloudquilt.weight_selection'])

    async def test_stopped_shared_answer_is_not_bypassed_by_catalog(self):
        row=next(r for r in self.svc.kb.faq.records if r['id']=='store.affirmation')
        row['status']='disabled'
        self.assertFalse((await self.ask('cloudquilt','好的'))['send_to_customer'])

    def test_feedback_migration_keeps_pending_references_and_is_idempotent(self):
        from scripts.fix_closing_and_quilt import migrate
        d=json.loads((ROOT/'data/faq.json').read_text(encoding='utf-8'))
        before=[r for r in d['records'] if r['status']=='needs_review']
        updated=migrate(d)
        self.assertEqual(before,[r for r in updated['records'] if r['status']=='needs_review'])
        self.assertEqual(migrate(updated),updated)

    async def test_unspecified_best_product_asks_category(self):
        r=await self.ask(None,'你们最好的是哪款')
        self.assertEqual(r['status'],'clarify');self.assertIn('品类',r['answer'])
        r=await self.ask('801','你们最好的是哪款')
        self.assertIn('小狗',r['answer'])

    async def test_sensitive_pending_reference_never_auto_answers(self):
        for pid,q in [('latexpillow','颈椎不舒服这款可以用吗'),('heater','这个能带多少平方'),('nonwovenblanket','有没有3c认证')]:
            r=await self.ask(pid,q);self.assertFalse(r['send_to_customer'],r)
            self.assertTrue(r['debug']['reason'].startswith('catalog_'))

    async def test_aftersales_product_fact_is_scoped_and_editable(self):
        r=await self.ask('601','高度多少','aftersales','aftersales')
        self.assertIn('170',r['answer']);self.assertEqual(r['debug']['editable_answer_ids'],['catalog.601.height'])
        row=next(r for r in self.svc.kb.faq.records if r['id']=='catalog.601.height');row['status']='disabled'
        self.assertFalse((await self.ask('601','高度多少'))['send_to_customer'])

    async def test_rag_uses_active_own_product_faq_and_not_pending_promises(self):
        rag=RAGAssistant(self.svc.kb,self.svc.model)
        r=await rag.assist('贴贴枕什么材质','tietie')
        self.assertTrue(r['sources'],r)
        self.assertTrue(all(not s.get('product_ids') or 'tietie' in s['product_ids'] for s in r['sources']))
        self.assertNotIn('缓解酸痛',r['suggestion'])

    async def test_new_general_scenes_work_in_aftersales_without_order_operations(self):
        for q,intent in [('没有风扇杆','missing_accessories'),('请帮我改地址','change_address'),('退款多久到账','refund_progress'),
            ('能开发票吗','invoice'),('我要转人工','manual_service')]:
            self.assertEqual(identify(q,'aftersales'),intent)
            r=await self.ask('801',q,'aftersales','aftersales')
            self.assertTrue(r['send_to_customer'],r)
            self.assertNotIn('已帮您修改',r['answer']);self.assertNotIn('已经退款',r['answer'])

    def test_onboarding_merge_preserves_maintainer_answers(self):
        d={'scenes':[{'id':'industry.catalog_material','question_variants':['材质']}],
           'records':[{'id':'catalog.tietie.material','standard_answer':'维护者编辑'}]}
        incoming=next(r for r in self.svc.kb.faq.records if r['id']=='catalog.tietie.material')
        self.assertEqual(merge(d,[incoming])['records'][0]['standard_answer'],'维护者编辑')
