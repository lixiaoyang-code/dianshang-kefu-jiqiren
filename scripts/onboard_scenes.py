"""新增通用人工协作场景，并绑定脱敏真实拓展问法。"""
import json,re,copy
from app.config import ROOT
from app.faq import canonical
from app.faq_admin import FAQStore
from app.common_intents import EXTRA
from scripts.test_customer_voices import redact
from scripts.onboard_catalog import record

DEFINITIONS={
 'missing_accessories':('配件缺少／配件不齐','亲亲，您缺的是哪一件配件呢？请保留包装，并拍一下已收到的配件，通过订单联系人工核对。是否需要补发及具体安排，要核实后确认哈～'),
 'change_address':('修改收货地址／信息','亲亲，修改收货信息需要结合订单和发货状态核实。请通过平台订单联系人工处理，暂时无法在这里直接改地址哈～'),
 'refund_progress':('退款进度／到账查询','亲亲，请先在订单售后详情查看退款状态和原支付渠道的记录。具体进度或到账时间需要人工结合订单核实，这里暂时无法直接查询哈～'),
 'cancel_order':('取消订单／拍错规格','亲亲，请先查看订单当前状态；如需取消或改规格，请通过平台订单联系人工核实。这里暂时不能代您取消、修改或拦截订单哈～'),
 'parcel_reject':('拒收／拒签包裹','亲亲，您是准备拒收，还是已经拒收了呢？是否需要申请售后、运费如何处理，都需要结合订单与原因核实，请先通过订单联系人工哈～'),
 'invoice':('发票／开票咨询','亲亲，开票方式、票种和抬头要求需要结合店铺及订单核实，您可以先查看订单开票入口，或联系人工确认哈～'),
 'promotion_policy':('有优惠吗，可以便宜点吗？','亲亲，具体到手价、折扣和优惠券以您所选规格的下单页面为准哈～您可以发一下页面截图，人工帮您核对可用优惠。'),
 'gift_policy':('有赠品吗，可以送什么？','亲亲，具体赠品和赠送条件以您所选商品页面的活动说明为准哈～您可以发一下商品或活动截图，人工核实后再为您确认，不先承诺额外赠送哦～'),
 'price_protection':('保价／差价处理','亲亲，保价是否适用、申请期限和差价金额，都需要结合平台活动规则与订单核实，请先查看订单保价入口或联系人工确认哈～'),
 'manual_service':('请求人工客服','亲亲，收到您的人工服务需求了。当前是测试工作台，尚未接通真实客服转接，请通过店铺订单联系人工；这里不会显示为已经转接成功。'),
 'tracking_abnormal':('物流异常／签收未收到','亲亲，您可以先核对订单物流最新节点和签收信息。如果显示签收却未收到、丢件或派送异常，请通过订单联系人工与承运方核实，暂时不能直接认定丢件或承诺赔付。'),
 'reshipment':('补发申请／补发进度','亲亲，您是想申请补发，还是查询已申请的补发进度呢？需要人工核对缺少的配件、处理记录及发货安排，这里暂时不能直接登记或确认已经补发哈～'),
 'purchase_payment':('付款失败／支付帮助','亲亲，页面有什么报错提示呢？您可以先核对订单状态和支付页面；涉及扣款或重复支付时，请通过平台订单联系人工核实，不需要在这里提供支付密码或验证码。'),
}

def build(doc,source):
    document=copy.deepcopy(doc)
    seen={canonical(q) for s in doc['scenes'] for q in s['question_variants']}
    samples={k:[] for k in EXTRA}
    for sheet in source:
        h={re.sub(r'\d','',k):v for k,v in sheet['rows'][0].items()};qc=next((k for k,v in h.items() if v=='客户原声'),None)
        for raw in sheet['rows'][1:]:
            q=redact(next((v for k,v in raw.items() if re.sub(r'\d','',k)==qc),''))
            matches=[key for key,pattern in EXTRA.items() if re.search(pattern,q)]
            if len(matches)==1 and 1<len(q)<=120 and canonical(q) not in seen:
                key=matches[0]
                if q not in samples[key]:samples[key].append(q)
    records=[]
    for key,(title,answer) in DEFINITIONS.items():
        sid='industry.common_'+key
        if any(s['id']==sid for s in document['scenes']):continue
        variants=[title,*samples[key][:90]]
        r=record('none',key,title,variants,answer)
        r.update(id='store.common_'+key,scene_id=sid,scope='store',product_ids=[],answer_product_id=None,
                 category='通用售前售后',origin='general_reception_template')
        r['sources']=[{'type':'workflow_template','date':'2026-11-05','excerpt':'依据用户原声整理人工协作接待；不代表已执行订单操作，不承诺活动、费用或时效。'}]
        document['scenes'].append({'id':sid,'name':title,'type':'industry','category':r['category'],
            'question_variants':variants,'configured':True,'description':'识别需求并接待，具体订单处理须人工核实。'})
        document['records'].append(r);records.append(r)
    return document,records

if __name__=='__main__':
    source=json.loads((ROOT/'logs/customer-voices/parsed-sheets.json').read_text(encoding='utf-8'))
    store=FAQStore();doc,_=store.read();updated,records=build(doc,source)
    if doc!=updated:store.persist(updated,lambda d:None)
    package=ROOT/'logs/catalog-onboarding-package.json';value=json.loads(package.read_text(encoding='utf-8'))
    value['records']+=records;package.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({'new_scenes':len(records),'real_variants':sum(len(r['question_variants'])-1 for r in records)},ensure_ascii=False))
