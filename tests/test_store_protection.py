import json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from app.config import ROOT,Settings
from app.knowledge import Knowledge
from app.model import Model
from app.service import Service
from app.rag import RAGAssistant
from app.common_intents import store_policy,select
from app.product_labels import HIDDEN_PRODUCTS
from scripts.add_store_protection import migrate,INSURANCE

class ProtectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_visible_products_and_unselected_use_maintainable_faq(self):
        doc=migrate(json.loads((ROOT/'data/faq.json').read_text(encoding='utf-8')))
        self.assertEqual(migrate(doc),doc)
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{'SEMANTIC_MODE':'off'}):
            svc=Service(Knowledge(faq_document=doc),Model(Settings(mode='mock',key='')),Path(t))
            try:
                for pid in [None,*[p for p in svc.kb.products if p not in HIDDEN_PRODUCTS]]:
                    for reception,stage in [('presales','presales'),('aftersales','aftersales')]:
                        for q in ['有运费险吗','运费险有吗','可以试用吗','可以试睡吗']:
                            r=await svc.chat(svc.create().session_id,q,pid,reception,stage)
                            self.assertTrue(r['send_to_customer'],(pid,q,r))
                            self.assertIn('运费险' if '险' in q else '试用',r['answer'])
                            self.assertEqual(r['debug']['model'],'not_called')
                for q in ['有运费险吗','可以试用吗']:
                    r=await RAGAssistant(svc.kb,svc.model).assist(q,'plushblanket')
                    self.assertEqual(r['retrieval_method'],'faq_reference')
                for row in svc.kb.faq.records:
                    if row['scene_id']=='industry.common_trial_policy':row['status']='disabled'
                r=await svc.chat(svc.create().session_id,'可以试用吗','plushblanket')
                self.assertFalse(r['send_to_customer'])
            finally:
                for h in svc.logger.handlers:h.close()

    def test_claims_duration_disputes_and_order_operations_are_not_generic_policies(self):
        for q in ['运费险赔多少','运费险怎么理赔','运费险没到账','可以试用30天吗','试用后怎么退款','帮我退货','试用多久','电热毯功率多少']:
            self.assertIsNone(store_policy(q),q)
        for q in ['电热毯有运费险吗','所有商品都有运费险吗']:
            self.assertEqual(store_policy(q),'freight_insurance')
