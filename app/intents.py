"""轻量售前意图：只处理明确问法；答案引用当前商品事实或已确认店铺规则。"""
import re
from .replies import FLEX_RECOMMENDATION


def normalize_question(text):
    text = text.strip().replace('顶棚', '顶部').replace('小狗款', '线条小狗')
    text = text.replace('能机洗吗', '可以机洗吗')
    return text


def quick_reply(text, product, products, store, session):
    q=text.strip('？?。！! ～~')
    if session.pending_topic == 'delivery':
        if q in ('有','是','是的','有的','显示','显示了','有京东物流'):
            session.pending_topic=None
            return 'answered',store['jd_delivery'],'store.jd_delivery'
        if q in ('没有','没','不是','没有显示','没显示'):
            session.pending_topic=None
            return 'answered',store['shipping'],'store.shipping'
        # 客户已转问其他内容时，不让之后孤立的“有”误接旧物流追问。
        session.pending_topic=None
    if q in ('？','?','', '在吗','人呢'):
        return 'clarify','亲亲，小妹在呢～您想了解哪一点呀？','conversation.greeting'
    if re.fullmatch(r'(?:请问)?200米的床(?:可以用吗|能用吗)',q):
        return 'clarify','亲亲，您是说200厘米、也就是2米长的床吗？','conversation.dimension_unit'
    if re.fullmatch(r'(?:我)?(?:睡|是|在)?上铺(?:选哪个|选哪款|用哪款|选什么)',q):
        return 'clarify','亲亲，上铺侧面进出选三开款哈～床上可用高度大概多少呢？','product.doors'
    if re.fullmatch(r'(?:有没有|有)?长宽高都(?:可以|能)?伸缩的(?:款式)?(?:有吗)?',q):
        return 'answered',FLEX_RECOMMENDATION,'catalog.full_stretch'
    if re.fullmatch(r'(?:明天|今天)(?:能|可以)?(?:收到|到|送到)(?:吗)?',q):
        return 'answered',store['delivery_summary'],'store.delivery_summary'
    if re.fullmatch(r'(?:什么|哪个|发什么|用什么)?(?:物流|快递)(?:发货)?',q):
        return 'answered',store['delivery_summary'],'store.delivery_summary'
    if product is None:
        return None
    pid=product['id']
    plain=q
    for name in [product['name'],*product['aliases'],pid]:
        plain=plain.replace(name,'')
    plain=plain.strip(' 的')
    if re.fullmatch(r'(?:能|可以)?隔音(?:吗|效果怎么样|效果好吗)?|(?:担心|怕)噪音',plain):
        return 'answered',product['short_replies']['sound_insulation'],f'product.{pid}.sound_insulation'
    if re.fullmatch(r'支架(?:很)?(?:稳|稳固|牢固|结实)(?:吗|不稳|不牢固)?',plain):
        return 'answered',product['short_replies']['stability'],f'product.{pid}.stability'
    if re.fullmatch(r'靠墙(?:那|这)?(?:侧|一侧|边|面)?(?:可以|能)?打开(?:吗)?',plain):
        return 'answered','亲亲，靠墙那侧不能打开哦，三开款可以从床头、床尾和正面进出～',f'product.{pid}.doors'
    if re.fullmatch(r'(?:会)?(?:有|出现)?皮影戏(?:吗)?',plain):
        return 'suppressed','透影效果缺少已确认依据，请客服核实',f'product.{pid}.shade_review'
    if re.fullmatch(r'(?:能|可以)?遮住光(?:吗)?|遮光(?:吗)?',plain):
        return 'answered','可以遮光的亲，也能遮挡隐私哈～',f'product.{pid}.shade_sides'
    if re.fullmatch(r'防蚊(?:吗)?|有蚊帐(?:吗)?',plain):
        return 'answered','有防蚊帐纱的亲，铺好床垫、拉好拉链使用就好啦～',f'product.{pid}.bottom'
    if re.fullmatch(r'支架(?:是)?什么材质',plain):
        value=product['facts'].get('pole_material')
        return ('answered',product['short_replies'].get('pole_sales','亲亲，'+value+'～'),f'product.{pid}.pole_material') if value else ('suppressed','支架材质待确认，不用帐纱材质代答',f'product.{pid}.pole_material')
    if re.fullmatch(r'支架多宽',plain):
        return 'clarify','亲亲，您问杆子粗细还是整个支架宽度呀？',f'product.{pid}.pole_diameter'
    if re.fullmatch(r'为什么贵这么多|有什么区别',plain) and pid=='803':
        return 'answered','亲亲，这款是线条小狗联名，22毫米支架是这四款里最粗的，长宽可±4厘米调节～',f'product.{pid}.pole_diameter'
    if re.fullmatch(r'宽度\s*\d+\s*长度\s*\d+',plain):
        session.pending_topic=None
        return 'answered',FLEX_RECOMMENDATION,'catalog.full_stretch'
    return None
