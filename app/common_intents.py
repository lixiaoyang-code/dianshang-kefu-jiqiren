"""通用接待只选择已维护的 FAQ；不查询订单、不生成店铺承诺。"""
import re
from .faq import canonical
from .scene_rules import requires_scene_selection
from .intents import affirmation_state, affirmation_variants

INTERACTIONS = {'greeting', 'thanks', 'goodbye'}
EXTRA = {
 'missing_accessories':r'没有(?:风扇杆|杆子|配件)|少配件|配件不齐|缺配件|缺少配件',
 'change_address':r'改.{0,4}(?:地址|收货人|电话)|地址.{0,4}(?:错|修改)|收货信息.{0,4}修改',
 'refund_progress':r'退款.{0,6}(?:到.?账|进度|没到|未到|多久|什么时候)|(?:钱|款).{0,4}退到哪',
 'cancel_order':r'取消订单|撤销订单|拍错了|下错单',
 'parcel_reject':r'拒收|拒签',
 'invoice':r'发票|开票|抬头|税号',
 'promotion_policy':r'赠品|送.{0,4}(?:篮|枕套|礼品)|优惠|折扣|便宜.{0,4}(?:吗|点|些|不)|满减',
 'price_protection':r'保价|价保|退差价|降价了|补差价',
 'manual_service':r'转人工|找人工|人工客服|真人客服',
 'tracking_abnormal':r'丢件|丢了|物流异常|显示签收|签收.{0,6}没收到|派送失败|投递失败',
 'reshipment':r'补发|重新寄|重新发货|补寄',
 'purchase_payment':r'付不了款|支付失败|付款失败|不能付款|怎么付款|如何付款',
}
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


def identify(text, stage='presales'):
    q = canonical(text)
    for intent in INTERACTIONS:
        if q in {canonical(v) for v in VARIANTS[intent]}:
            return intent
    # 招呼之后有实际问题，不能只回招呼。
    q = re.sub(r'^(?:你好呀|你好|您好|哈喽|hello|hi|亲亲|亲)(?:请问)?', '', q, flags=re.I)
    if re.search(r'投诉|赔偿|起诉|报警', q):
        return None
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


def select(kb, text, pid, reception, stage):
    # 店铺通用肯定回复先于新品检索，但仍使用知识库条件和停用配置。
    intent = 'affirmation' if affirmation_state(text,affirmation_variants(kb))=='confirmed' else identify(text, stage)
    if not intent:
        return None
    scene_id = 'industry.affirmation' if intent=='affirmation' else 'industry.common_' + intent
    direct=kb.faq.resolve(text,pid,reception,stage)
    other={sid for sid in direct.get('scene_ids',[]) if sid!=scene_id and not sid.startswith('industry.common_')}
    if any(requires_scene_selection(r) for r in kb.faq.records if r['scene_id'] in other
           and (r.get('scope')!='product' or pid in r.get('product_ids',[])
                or r.get('origin')!='catalog_onboarding')):
        return None  # 真实问法已绑定其他场景时，交回正常条件/优先级选择。
    scene = next((s for s in kb.faq.scenes if s['id'] == scene_id), None)
    if not scene:
        return None
    # 使用场景标准问题走正常优先级，保留自定义/特殊场景与商品条件覆盖。
    result = direct if intent=='affirmation' else kb.faq.resolve(scene['name'], pid, reception, stage)
    return {**result, 'scene_id': scene_id}


def interaction_allowed(scene_id, text, stage='presales'):
    name = scene_id.removeprefix('industry.common_')
    # 售后工作流问法里的“杆子/尺寸”不能抢占商品参数意图。
    if name in EXTRA or name in VARIANTS:return identify(text,stage)==name
    return True
