import json,tempfile,unittest
from pathlib import Path
from unittest.mock import Mock,patch
from app.common_intents import identify
from app.intents import purchase_confirmation
from app.config import ROOT,Settings
from app.knowledge import Knowledge
from app.model import Model
from app.service import Service
from app.rag import RAGAssistant
from scripts.add_purchase_confirmation import migrate,SID

class PurchaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_pure_statements_use_editable_faq_without_semantic_search(self):
        doc=migrate(json.loads((ROOT/'data/faq.json').read_text(encoding='utf-8')))
        self.assertEqual(migrate(doc),doc)
        with tempfile.TemporaryDirectory() as t,patch.dict('os.environ',{'SEMANTIC_MODE':'off'}):
            svc=Service(Knowledge(faq_document=doc),Model(Settings(mode='mock',key='')),Path(t))
            svc.semantic=Mock();svc.semantic.search.side_effect=AssertionError('purchase must not retrieve parameters')
            try:
                for pid in ['801','plushblanket','cloudquilt']:
                    for q in ['好的 我现在拍','好的，我现在拍','我拍了','那我就买了','现在下单','我现在就拍','已经付款了']:
                        r=await svc.chat(svc.create().session_id,q,pid)
                        self.assertEqual(r['answer'],'好的亲亲💗，有问题随时找我～',q)
                        self.assertEqual(r['debug']['analysis']['intents'][0]['id'],SID)
                        self.assertEqual(r['debug']['model'],'not_called')
                rag=await RAGAssistant(svc.kb,svc.model).assist('好的 我现在拍','plushblanket')
                self.assertEqual(rag['retrieval_method'],'faq_reference')
                row=next(r for r in svc.kb.faq.records if r['scene_id']==SID);row['status']='disabled'
                r=await svc.chat(svc.create().session_id,'我现在拍','plushblanket')
                self.assertFalse(r['send_to_customer'])
                svc.semantic.search.assert_not_called()
            finally:
                for h in svc.logger.handlers:h.close()

    def test_questions_conditions_and_photo_actions_are_not_acknowledgements(self):
        for q in ['优惠我就买','便宜点我马上下单','我现在拍什么时候发货','好的，能机洗吗','我拍了没收到',
                  '我没拍','我不买了','我现在拍吗？','我现在拍照','我拍张照片','我想买','那12档多少钱']:
            self.assertFalse(purchase_confirmation(q),q)
            self.assertNotEqual(identify(q),'purchase_confirmation',q)
        self.assertEqual(identify('优惠我就买'),'price_negotiation')

    def test_no_scene_does_not_fall_through_to_product_search(self):
        from app.common_intents import select
        kb=Knowledge();kb.faq.scenes=[s for s in kb.faq.scenes if s['id']!=SID]
        self.assertEqual(select(kb,'好的 我现在拍','plushblanket','presales','presales')['status'],'ineligible')
