import copy
import unittest
from types import SimpleNamespace
from app.common_intents import identify,select,interaction_allowed
from app.faq import FAQ
from scripts.split_promotion_intents import migrate,SID


class PromotionSplitTests(unittest.TestCase):
    def fixture(self):
        qs=['赠品／活动／优惠券','有优惠券吗','这个有赠品吗','不是说送置物篮吗为什么没送',
            '赠品物流查不到','请问送的篮子挂那里','优惠力度更大还送置物篮']
        row=dict(id='store.common_promotion_policy',intent='promotion_policy',scene_id=SID,
            scene_name=qs[0],scene_type='industry',category='通用售前售后',question_variants=qs,
            standard_answer='价格话术由商家维护',answer_parts=['价格话术由商家维护'],
            scope='store',product_ids=[],answer_product_id=None,status='active',fields=[],sources=[],images=[],
            boundaries={},configured_scene=True,conditions={'reception':'all','stages':['presales','aftersales']})
        scenes=[dict(id=SID,name=qs[0],type='industry',category=row['category'],question_variants=qs)]
        rows=[row]
        for key in ('damaged','tracking'):
            s=dict(id='industry.common_'+key,name=key,type='industry',category='售后',question_variants=[key])
            scenes.append(s)
            rows.append({**copy.deepcopy(row),'id':'store.common_'+key,'intent':key,'scene_id':s['id'],
                'scene_name':key,'question_variants':[key],'standard_answer':'售后核实','answer_parts':['售后核实']})
        return dict(scenes=scenes,records=rows)

    def test_classification_keeps_boundaries(self):
        for question in ['有优惠吗','可以便宜点吗','优惠券怎么领','有折扣吗']:
            self.assertEqual(identify(question),'promotion_policy')
            self.assertFalse(interaction_allowed('industry.common_gift_policy',question))
        for question in ['有赠品吗','送置物篮吗','可以送个小礼品吗','送什么东西']:
            self.assertEqual(identify(question),'gift_policy')
            self.assertFalse(interaction_allowed(SID,question))
        self.assertEqual(identify('不是说送置物篮吗为什么没送'),'damaged')
        self.assertEqual(identify('赠品物流查不到'),'tracking')
        self.assertIsNone(identify('优惠力度更大还送置物篮'))
        self.assertIsNone(identify('请问送的篮子挂那里'))
        self.assertIsNone(identify('有什么活动'))

    def test_migration_preserves_price_and_existing_conditions(self):
        before=self.fixture();after=migrate(before)
        old=before['records'][0];new=after['records'][0]
        for key in ('standard_answer','answer_parts','status','scope','product_ids','conditions','sources'):
            self.assertEqual(new[key],old[key],key)
        self.assertEqual(migrate(after),after)
        self.assertEqual(before,self.fixture())
        price=next(s for s in after['scenes'] if s['id']==SID)
        self.assertNotIn('这个有赠品吗',price['question_variants'])
        faq=FAQ(after['records'],after['scenes']);kb=SimpleNamespace(faq=faq)
        for pid in ['801','802','cloudquilt']:
            result=select(kb,'有优惠吗',pid,'presales','presales')
            self.assertEqual(result['row']['id'],'store.common_promotion_policy')
            result=select(kb,'这个有赠品吗',pid,'presales','presales')
            self.assertEqual(result['row']['id'],'store.common_gift_policy')
            self.assertNotEqual(result['row']['standard_answer'],new['standard_answer'])
        for text,key in [('不是说送置物篮吗为什么没送','damaged'),('赠品物流查不到','tracking')]:
            self.assertEqual(select(kb,text,'801','aftersales','aftersales')['row']['id'],'store.common_'+key)
        self.assertNotEqual(faq.resolve('请问送的篮子挂那里','801')['status'],'matched')

    def test_mixed_answer_is_not_silently_reused_for_price(self):
        doc=self.fixture();doc['records'][0]['standard_answer']='赠品和优惠以页面为准'
        with self.assertRaises(ValueError):migrate(doc)


if __name__=='__main__':unittest.main()
