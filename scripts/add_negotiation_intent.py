"""把附带购买意向的议价与普通优惠咨询分开，保留其他话术和条件。"""
import copy
import json
from datetime import datetime,timezone
from app.common_intents import promotion_kind
from app.faq_admin import FAQStore
from app.knowledge import Knowledge

SID='industry.common_price_negotiation'
TITLE='议价／优惠后购买'
ANSWER='亲亲，明白，您是想优惠一些再下单哈～具体优惠以所选规格的结算页面为准，您可以发一下页面价格，让客服帮您核对有没有可用优惠哦～'


def migrate(document):
    doc=copy.deepcopy(document)
    if any(s['id']==SID for s in doc['scenes']):return doc
    variants=['优惠我就买','给我优惠我就买','便宜点我就下单']
    for scene in doc['scenes']:
        if scene.get('deleted_at'):continue
        moved=[q for q in scene['question_variants'] if promotion_kind(q)=='price_negotiation']
        if not moved:continue
        variants.extend(moved)
        # 单独的商品议价场景保留原来的商品答案，避免改变商家维护的专属话术。
        if promotion_kind(scene['name'])=='price_negotiation':continue
        scene['question_variants']=[q for q in scene['question_variants'] if q not in moved]
        for row in doc['records']:
            if row['scene_id']==scene['id']:row['question_variants']=scene['question_variants']
    source=next(r for r in doc['records'] if r['id']=='store.common_promotion_policy')
    qs=list(dict.fromkeys([TITLE,*variants]))
    doc['scenes'].append(dict(id=SID,name=TITLE,type='industry',category='价格优惠',configured=True,
        description='客户提出议价，或明确表示优惠后购买；相邻优惠咨询后的省略追问可结合上下文识别，不代表已经购买。',question_variants=qs))
    row=copy.deepcopy(source)
    row.update(id='store.common_price_negotiation',intent='price_negotiation',scene_id=SID,scene_name=TITLE,
        category='价格优惠',question_variants=qs,standard_answer=ANSWER,answer_parts=[ANSWER],status='active',
        keywords=[],updated_at=datetime.now(timezone.utc).isoformat(),
        conditions={'reception':'all','stages':['presales'],'valid_from':None,'valid_until':None})
    doc['records'].append(row)
    return doc


if __name__=='__main__':
    store=FAQStore();before,_=store.read();after=migrate(before)
    if before!=after:store.persist(after,lambda doc:Knowledge(faq_document=doc))
    print(json.dumps({'changed':before!=after,'scenes_added':len(after['scenes'])-len(before['scenes'])}))
