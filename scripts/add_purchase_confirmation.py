"""Add an editable purchase acknowledgement without changing merchant answers."""
import copy
SID='industry.common_purchase_confirmation'

def migrate(document):
    doc=copy.deepcopy(document)
    qs=['确认购买／准备下单','好的，我现在拍','好的 我现在拍','我现在拍','我拍了','我下单了','那我就买了','现在下单','已经付款了']
    if not any(s['id']==SID for s in doc['scenes']):
        doc['scenes'].append(dict(id=SID,name='确认购买／准备下单',type='industry',category='聊天互动',
            configured=True,question_variants=qs,description='仅处理明确购买或付款表态；议价、物流追问、订单异常及拍照片不属于此意图。'))
    if not any(r['scene_id']==SID for r in doc['records']):
        text='好的亲亲💗，有问题随时找我～'
        doc['records'].append(dict(id='store.common_purchase_confirmation',intent='purchase_confirmation',
            scene_id=SID,scene_name='确认购买／准备下单',scene_type='industry',category='聊天互动',
            scope='store',product_ids=[],answer_product_id=None,status='active',configured_scene=True,
            question_variants=qs,standard_answer=text,answer_parts=[text],fields=[],images=[],keywords=[],
            keyword_mode='any',priority=0,conditions={'reception':'all','stages':[]},
            sources=[{'type':'workflow_template','date':'2026-11-08','excerpt':'简短回应购买表态，不声称已收到订单、收款或安排发货。'}],
            boundaries={'no_order_operations':True},origin='general_reception_template'))
    return doc

if __name__=='__main__':
    from app.faq_admin import FAQStore
    from app.knowledge import Knowledge
    store=FAQStore();doc,_=store.read();new=migrate(doc)
    if new!=doc:store.persist(new,lambda d:Knowledge(faq_document=d))
    print('Purchase acknowledgement FAQ ready; existing answers preserved.')
