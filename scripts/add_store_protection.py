"""Merchant-confirmed insurance and trial policies for every current product."""
import copy
from app.faq import canonical

INSURANCE='亲亲，咱家在售商品都有运费险哈～'
TRIAL='可以试用的哈亲亲～具体试用期限和退换条件以下单页服务说明为准。'

def migrate(document):
    doc=copy.deepcopy(document)
    trial=next((r['standard_answer'] for r in doc['records'] if not r.get('deleted_at') and
        r['status']=='active' and r['scope']=='store' and canonical(r.get('scene_name',''))=='支持七天无理由试用吗'),TRIAL)
    for sid,title,qs,rid,answer in [
        ('industry.freight_insurance','有运费险吗？',['有运费险吗','运费险有吗','有没有运费险','带运费险吗','有退货险吗'],'store.freight_insurance',INSURANCE),
        ('industry.common_trial_policy','可以试用吗？',['可以试用吗','支持试用吗','能试用吗','可以试睡吗','试用可以吗'],'store.common_trial_policy',trial)]:
        scene=next((s for s in doc['scenes'] if s['id']==sid),None)
        if scene is None:
            scene=dict(id=sid,name=title,type='industry',category='通用售前售后',configured=True,question_variants=[title,*qs])
            doc['scenes'].append(scene)
        else:scene['question_variants']=list(dict.fromkeys([*scene['question_variants'],title,*qs]))
        row=next((r for r in doc['records'] if r['id']==rid),None)
        if row is None:
            row=dict(id=rid,intent='freight_insurance' if sid=='industry.freight_insurance' else 'trial_policy',
                scene_id=sid,scene_name=scene['name'],scene_type=scene['type'],category='通用售前售后',scope='store',product_ids=[],
                answer_product_id=None,fields=[],images=[],sources=[],keywords=[],keyword_mode='any',priority=0,
                boundaries={'no_order_operations':True},origin='general_reception_template')
            doc['records'].append(row)
        row.update(status='active',scope='store',product_ids=[],configured_scene=True,standard_answer=answer,
            answer_parts=[answer],question_variants=scene['question_variants'][:],conditions={'reception':'all','stages':[]},
            sources=[{'type':'merchant_confirmation','date':'2026-11-08','excerpt':'所有在售商品都有运费险，且支持试用；期限及细则沿用已核准政策。'}])
    # Reconcile older simple insurance answers with the latest store-wide policy.
    for r in doc['records']:
        if not r.get('deleted_at') and r['status']=='active' and canonical(r.get('scene_name','')) in ('有运费险吗','运费险有吗','有没有运费险'):
            r.update(standard_answer=INSURANCE,answer_parts=[INSURANCE])
    return doc

if __name__=='__main__':
    from app.faq_admin import FAQStore
    from app.knowledge import Knowledge
    store=FAQStore();doc,_=store.read();new=migrate(doc)
    if new!=doc:store.persist(new,lambda d:Knowledge(faq_document=d))
    print('Store insurance and trial policies applied; product catalogue unchanged.')
