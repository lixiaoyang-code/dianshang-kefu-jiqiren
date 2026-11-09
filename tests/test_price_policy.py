import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch
from app.knowledge import Knowledge
from app.config import Settings
from app.model import Model
from app.service import Service
from app.rag import RAGAssistant
from app.common_intents import select
from app.product_labels import HIDDEN_PRODUCTS

ANSWER='亲亲，现在价格已经很优惠了哦～'

def knowledge():
    kb=Knowledge()
    row=copy.deepcopy(next(r for r in kb.faq.records if r['id']=='store.common_promotion_policy'))
    row.update(standard_answer=ANSWER,answer_parts=[ANSWER],conditions={'reception':'all','stages':[]})
    scene=copy.deepcopy(next(s for s in kb.faq.scenes if s['id']==row['scene_id']))
    kb.faq.records=[row];kb.faq.scenes=[scene]
    return kb

class PricePolicyTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_products_get_same_short_faq_and_followups_keep_handoff(self):
        with patch.dict('os.environ',{'SEMANTIC_MODE':'off'}),tempfile.TemporaryDirectory() as folder:
            svc=Service(knowledge(),Model(Settings(mode='mock',key='')),Path(folder))
            try:
                for pid in svc.kb.products:
                    if pid in HIDDEN_PRODUCTS:continue
                    sid=svc.create().session_id
                    first=await svc.chat(sid,'有优惠吗',pid)
                    self.assertEqual(first['answer'],ANSWER,pid)
                    for question in ['有优惠吗','还能再少点吗','优惠我就买','最低多少钱']:
                        reply=await svc.chat(sid,question,pid)
                        self.assertFalse(reply['send_to_customer'])
                        self.assertEqual(reply['debug']['reason'],'price_followup')
                sid=svc.create().session_id
                await svc.chat(sid,'有优惠吗','801')
                switched=await svc.chat(sid,'有优惠吗','802')
                self.assertNotEqual(switched['debug']['reason'],'price_followup')
            finally:
                for h in svc.logger.handlers:h.close()

    def test_custom_priority_and_conditions_override_default_pending_does_not(self):
        kb=knowledge();custom=copy.deepcopy(kb.faq.records[0]);custom.update(id='test.offer',scene_id='custom.offer',scene_type='custom',
            standard_answer='本次活动有已核准的专属优惠。',scope='product',product_ids=['801'],priority=10)
        scene=copy.deepcopy(kb.faq.scenes[0]);scene.update(id='custom.offer',type='custom');kb.faq.scenes.append(scene);kb.faq.records.append(custom)
        self.assertEqual(select(kb,'有优惠吗','801','presales','presales')['row']['id'],'test.offer')
        self.assertEqual(select(kb,'有优惠吗','802','presales','presales')['row']['standard_answer'],ANSWER)
        custom['status']='needs_review'
        self.assertEqual(select(kb,'有优惠吗','801','presales','presales')['row']['standard_answer'],ANSWER)

    async def test_rag_uses_faq_without_expanding_and_followup_advises_handoff(self):
        rag=RAGAssistant(knowledge(),Model(Settings(mode='mock',key='')))
        rag._generate=AsyncMock(side_effect=AssertionError('price FAQ must not invoke a model'))
        first=await rag.assist('有优惠吗','latexpillow')
        self.assertEqual(first['suggestion'],ANSWER)
        self.assertEqual(first['retrieval_method'],'faq_reference')
        followup=await rag.assist('还能再少点吗','latexpillow',promotion_context={'intent':'promotion_policy'})
        self.assertEqual(followup['status'],'manual_boundary')
        self.assertIn('人工接管',followup['operator_advice'])
        self.assertFalse(followup['can_save_faq'])
        rag._generate.assert_not_awaited()
