"""通用接待只选择已维护的 FAQ；不查询订单、不生成店铺承诺。"""
import re
from .faq import canonical
from .scene_rules import requires_scene_selection
from .intents import affirmation_state, affirmation_variants, purchase_confirmation
from .product_labels import NAMES, REPLACEMENTS


def store_policy(text):
    q=canonical(text).strip(',')
    for name in sorted(set(NAMES.values())|set(REPLACEMENTS),key=len,reverse=True):q=q.replace(name.lower(),'')
    q=re.sub(r'^(?:你好|您好|亲亲|亲|请问|我|这款|这个|你家|你们家|你们|咱家|全店|全部商品|所有商品|商品|产品)+','',q)
    if re.fullmatch(r'(?:都)?(?:有|有没有|带|带不带|送|赠送|包含|提供|是否有|支持)?(?:运费险|退货险)(?:有吗|吗|嘛|么|呢|不)?',q):return 'freight_insurance'
    if re.fullmatch(r'(?:都)?(?:支持|可以|能|可不可以|能不能|是否支持|有没有|有)?(?:试用|试睡)(?:可以吗|支持吗|吗|嘛|么|呢|不)?',q):return 'trial_policy'
    return None

INTERACTIONS = {'greeting', 'thanks', 'goodbye', 'purchase_confirmation'}
EXTRA = {
 'missing_accessories':r'没有(?:风扇杆|杆子|配件)|少配件|配件不齐|缺配件|缺少配件',
 'change_address':r'改.{0,4}(?:地址|收货人|电话)|地址.{0,4}(?:错|修改)|收货信息.{0,4}修改',
 'refund_progress':r'退款.{0,6}(?:到.?账|进度|没到|未到|多久|什么时候)|(?:钱|款).{0,4}退到哪',
 'cancel_order':r'取消订单|撤销订单|拍错了|下错单',
 'parcel_reject':r'拒收|拒签',
 'invoice':r'发票|开票|抬头|税号',
 'promotion_policy':r'优惠|折扣|打折|优惠券|满减|便宜.{0,4}(?:吗|点|些|不)',
 'gift_policy':r'赠品|赠送|礼品|礼物|送.{0,6}(?:篮|枕套|东西|什么)|(?:篮子|置物篮|挂篮).{0,6}(?:没|未)',
 'price_protection':r'保价|价保|退差价|降价了|补差价',
 'manual_service':r'转人工|找人工|人工客服|真人客服',
 'tracking_abnormal':r'丢件|丢了|物流异常|显示签收|签收.{0,6}没收到|派送失败|投递失败',
 'reshipment':r'补发|重新寄|重新发货|补寄',
 'purchase_payment':r'付不了款|支付失败|付款失败|不能付款|怎么付款|如何付款',
}


def promotion_kind(text,previous=None):
    """价格和赠品独立识别；售后履约不能由售前赠品话术接管。"""
    q=canonical(text)
    price=bool(re.search(EXTRA['promotion_policy'],q))
    gift=bool(re.search(EXTRA['gift_policy'],q))
    if price and gift:return 'mixed'
    if gift:
        if re.search(r'物流|快递|查不到|什么时候.{0,4}寄',q):return 'tracking'
        if re.search(r'没送|未送|没收到|未收到|没.{0,4}寄|没有寄|只.{0,3}(?:拿|收到)|漏发|少发',q):return 'damaged'
        if re.search(r'挂那|挂哪|怎么用|如何用',q):return 'gift_usage'
        return 'gift_policy'
    if price and re.search(r'(?:优惠|便宜|折扣).{0,18}(?:就|立刻|马上|立即|才|再).{0,4}(?:买|拍|下单|付款)',q):
        return 'price_negotiation'
    if previous and previous.get('intent') in ('promotion_policy','price_negotiation'):
        if re.search(r'(?:再|还能|还可以).{0,4}(?:便宜|优惠|少点|少一点|少一些|给点|让点|低点)|最低(?:价|多少|能)|(?:能|可以)少多少|再让点|再低点',q):
            return 'price_negotiation'
    return 'promotion_policy' if price else None
VARIANTS = {
    'greeting': ['你好', '您好', '哈喽', 'hello', 'hi', '在吗', '有人吗', '客服在吗', '亲在吗', '早上好', '晚上好', '你好呀'],
    'thanks': ['谢谢', '谢谢你', '谢谢啦', '感谢', '多谢', '辛苦了', '好的谢谢', '好哒谢谢', '谢谢亲'],
    'goodbye': ['再见', '拜拜', '晚安', '回头聊', '谢谢拜拜', '谢谢再见', '没有其他问题了', '没问题了', '先这样吧', '就这样吧'],
    'tracking': ['查一下物流', '我的快递到哪了', '包裹到哪里了', '物流怎么不更新', '已经发货了吗', '我的订单什么时候到', '催一下物流'],
    'returns_policy': ['可以退换货吗', '退换货规则是什么', '支持七天无理由吗', '拆开了可以退吗', '退货运费谁出', '退货地址是什么'],
    'return_request': ['我要退货', '我想退货', '怎么申请退货', '帮我退款', '退款多久到账', '取消订单'],
    'exchange_request': ['我要换货', '我想换货', '怎么换货', '换个尺寸', '换个颜色'],
    'damaged': ['收到破损了', '收到少件了', '发错货了', '商品有质量问题', '配件少了'],
}


def identify(text, stage='presales',previous=None):
    q = canonical(text)
    if purchase_confirmation(text):return 'purchase_confirmation'
    for intent in INTERACTIONS - {'purchase_confirmation'}:
        if q in {canonical(v) for v in VARIANTS[intent]}:
            return intent
    # 招呼之后有实际问题，不能只回招呼。
    q = re.sub(r'^(?:你好呀|你好|您好|哈喽|hello|hi|亲亲|亲)(?:请问)?', '', q, flags=re.I)
    if re.search(r'投诉|赔偿|起诉|报警', q):
        return None
    policy=store_policy(q)
    if policy:return policy
    promotion=promotion_kind(q,previous)
    if promotion in ('mixed','gift_usage'):return None
    if promotion in ('tracking','damaged'):return promotion
    if promotion=='price_negotiation':return promotion
    if len(q)<=100 and not re.search(r'还有|以及|并且',q):
        extra=[k for k,pattern in EXTRA.items() if re.search(pattern,q)]
        if len(extra)==1:return extra[0]
        if len(extra)>1:return None
    groups = []
    if re.search(r'退换|退货|退回|退款|无理由|取消订单', q):
        groups.append('return_request' if re.search(r'我要退|我想退|申请退|帮我退|退款|取消订单', q) else 'returns_policy')
    if re.search(r'换货|换个尺寸|换个颜色', q) and '退换' not in q:
        groups.append('exchange_request')
    if re.search(r'破损|少件|少了|漏发|发错|质量问题|坏了', q):
        groups.append('damaged')
    logistics = bool(re.search(r'物流|快递|包裹|发货|到货|多久到|多久能到|几天能到|什么时候到', q))
    if logistics:
        if groups:
            return None
        if stage != 'presales' or re.search(r'我的|订单|查|到哪|到哪里|不更新|催|已经|还没|未收到', q):
            return 'tracking'
    return groups[0] if len(groups) == 1 else None


def select(kb, text, pid, reception, stage,previous=None):
    # 店铺通用肯定回复先于新品检索，但仍使用知识库条件和停用配置。
    intent = 'affirmation' if affirmation_state(text,affirmation_variants(kb))=='confirmed' else identify(text, stage,previous)
    if not intent:
        return None
    scene_id = ('industry.affirmation' if intent=='affirmation' else 'industry.freight_insurance'
                if intent=='freight_insurance' else 'industry.common_' + intent)
    direct=kb.faq.resolve(text,pid,reception,stage)
    if intent in ('freight_insurance','trial_policy'):
        ids=set(direct.get('scene_ids',[]))|{scene_id}
        scene=next((s for s in kb.faq.scenes if s['id']==scene_id),None)
        if scene:ids.update(kb.faq.resolve(scene['name'],pid,reception,stage).get('scene_ids',[]))
        # Existing scheduled/custom policy answers keep their normal ranking.
        result=kb.faq.select([r for r in kb.faq.records if r['scene_id'] in ids],pid,reception,stage)
        return {**result,'scene_id':scene_id,'scene_ids':sorted(ids)}
    if intent in ('promotion_policy','price_negotiation'):
        # A later bargaining turn needs a person, even when it repeats the same wording.
        if previous and previous.get('intent') in ('promotion_policy','price_negotiation'):
            return {'status':'manual_required','row':None,'scene_id':scene_id,
                    'scene_ids':[scene_id],'reason':'price_followup'}
        ids=set(direct.get('scene_ids',[]))|{scene_id}
        scene=next((s for s in kb.faq.scenes if s['id']==scene_id),None)
        if scene:ids.update(kb.faq.resolve(scene['name'],pid,reception,stage).get('scene_ids',[]))
        # Normal FAQ ranking handles active product answers, scheduled/custom overrides;
        # unrelated or pending answers must not prevent the store fallback.
        result=kb.faq.select([r for r in kb.faq.records if r['scene_id'] in ids],pid,reception,stage)
        return {**result,'scene_id':scene_id,'scene_ids':sorted(ids)}
    other={sid for sid in direct.get('scene_ids',[]) if sid!=scene_id and not sid.startswith('industry.common_')}
    if any(requires_scene_selection(r) for r in kb.faq.records if r['scene_id'] in other
           and (r.get('scope')!='product' or pid in r.get('product_ids',[])
                or r.get('origin')!='catalog_onboarding')):
        return None  # 真实问法已绑定其他场景时，交回正常条件/优先级选择。
    scene = next((s for s in kb.faq.scenes if s['id'] == scene_id), None)
    if not scene:
        if intent=='purchase_confirmation':return {'status':'ineligible','row':None,'scene_id':scene_id}
        return None
    # 使用场景标准问题走正常优先级，保留自定义/特殊场景与商品条件覆盖。
    result = direct if intent=='affirmation' else kb.faq.resolve(scene['name'], pid, reception, stage)
    return {**result, 'scene_id': scene_id}


def interaction_allowed(scene_id, text, stage='presales'):
    if scene_id=='industry.freight_insurance':return store_policy(text)=='freight_insurance'
    if scene_id=='industry.common_trial_policy':return store_policy(text)=='trial_policy'
    name = scene_id.removeprefix('industry.common_')
    # 售后工作流问法里的“杆子/尺寸”不能抢占商品参数意图。
    if name in EXTRA or name in VARIANTS or name in ('price_negotiation','purchase_confirmation'):return identify(text,stage)==name
    return True
