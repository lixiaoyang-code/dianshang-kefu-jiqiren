"""一次性拆分价格优惠与赠品问法，保留答案、条件及来源；可重复执行。"""
import copy
import json
from datetime import datetime, timezone
from app.common_intents import promotion_kind
from app.faq_admin import FAQStore
from app.knowledge import Knowledge

SID='industry.common_promotion_policy'
GIFT_TITLE='有赠品吗，可以送什么？'
GIFT_ANSWER='亲亲，具体赠品和赠送条件以您所选商品页面的活动说明为准哈～您可以发一下商品或活动截图，人工核实后再为您确认，不先承诺额外赠送哦～'
PRICE_TITLE='有优惠吗，可以便宜点吗？'


def migrate(document):
    doc=copy.deepcopy(document)
    scene=next((s for s in doc['scenes'] if s['id']==SID),None)
    if not scene or scene.get('promotion_split_version')==1:return doc
    row=next(r for r in doc['records'] if r['id']=='store.common_promotion_policy')
    # 人工已经维护的价格话术保持不变；混合话术必须先单独核实。
    if promotion_kind(row['standard_answer']) in ('gift_policy','mixed'):
        raise ValueError('原答案仍混有赠品内容，请先核实价格话术后再拆分。')
    groups={key:[] for key in ('promotion_policy','gift_policy','damaged','tracking','gift_usage','mixed')}
    for q in dict.fromkeys([*scene['question_variants'],*row['question_variants']]):
        if q in (scene['name'],'赠品／活动／优惠券','赠品 / 活动 / 优惠券'):continue
        kind=promotion_kind(q)
        if kind=='price_negotiation':kind='promotion_policy'  # 后续独立迁移再拆分议价。
        if kind is None:
            # “送置物篮”“这些赠品没有了吗”等真实原话仍归赠品。
            kind='gift_policy' if any(w in q for w in ('赠品','礼品','置物篮','挂篮','篮子')) else 'mixed'
        groups[kind].append(q)
    def variants(title,items):return list(dict.fromkeys([title,*items]))
    scene.update(name=PRICE_TITLE,question_variants=variants(PRICE_TITLE,groups['promotion_policy']),
        description='询问价格折扣、优惠券、满减及能否便宜；不含赠品、赠品漏发、保价退差价。',promotion_split_version=1)
    row.update(scene_name=PRICE_TITLE,question_variants=scene['question_variants'])
    def add(key,title,questions,answer,status,description):
        if not questions and key!='gift_policy':return
        sid='industry.common_'+key
        if any(s['id']==sid for s in doc['scenes']):raise ValueError('目标意图已存在，需人工核对后合并：'+sid)
        qs=variants(title,questions)
        doc['scenes'].append(dict(id=sid,name=title,type='industry',category=row['category'],question_variants=qs,
            configured=True,description=description))
        new=copy.deepcopy(row)
        new.update(id='store.common_'+key,intent=key,scene_id=sid,scene_name=title,question_variants=qs,
            standard_answer=answer,answer_parts=[answer] if answer else [],status=status,
            updated_at=datetime.now(timezone.utc).isoformat())
        new['keywords']=[]
        if key=='gift_policy':new['conditions']={**new['conditions'],'reception':'all','stages':[]}
        doc['records'].append(new)
    add('gift_policy',GIFT_TITLE,groups['gift_policy'],GIFT_ANSWER,row['status'],
        '询问是否赠送、赠品内容、赠送条件或加赠；不含价格折扣、赠品物流、漏发和使用方法。')
    for key in ('damaged','tracking'):
        target=next(s for s in doc['scenes'] if s['id']=='industry.common_'+key)
        target['question_variants']=variants(target['name'],[*target['question_variants'],*groups[key]])
        for r in doc['records']:
            if r['scene_id']==target['id']:r['question_variants']=target['question_variants']
    add('gift_usage','赠品怎么使用、安装？',groups['gift_usage'],'','needs_review','赠品安装或使用方式，缺少确认资料时不自动回复。')
    add('promotion_mixed','同时咨询价格优惠和赠品',groups['mixed'],
        '客户同时询问价格优惠与赠品，请分别核实活动及订单后回复。','manual_policy','复合咨询，不能只回复价格或只回复赠品。')
    return doc


if __name__=='__main__':
    store=FAQStore();before,_=store.read();after=migrate(before)
    if before!=after:store.persist(after,lambda doc:Knowledge(faq_document=doc))
    print(json.dumps({'changed':before!=after,'scenes_added':len(after['scenes'])-len(before['scenes']),
        'answers_added':len(after['records'])-len(before['records'])},ensure_ascii=False))
