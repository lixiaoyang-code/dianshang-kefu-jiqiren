"""用户最新批准的问法优先于旧问答和语义近似匹配。"""
import re
from .replies import FLEX_RECOMMENDATION

def catalog_reply(text,data=None):
    """跨款推荐是目录咨询，不把候选商品绑定为当前咨询商品。"""
    plain=re.sub(r'[\s？?！!，,。～~]', '',text)
    if re.fullmatch(r'(?:纯色款|小狗联名款|免安装款|80[1-4])?(?:有|有没有)(?:全伸缩(?:的)?(?:支架|款|款式)?|长宽高都(?:能|可以)?伸缩的(?:支架|款|款式)?)(?:吗|嘛)?',plain):
        return 'answered',FLEX_RECOMMENDATION,'catalog.full_stretch'
    if data:
        products={p['id']:p for p in data['products']}
        if re.fullmatch(r'(?:有|有没有)(?:免安装|不用安装)(?:的)?(?:款式|款|蚊帐)?(?:吗|嘛)?',plain):
            return 'answered',products['804']['short_replies']['catalog_recommendation'],'product.804.catalog_recommendation'
        if re.fullmatch(r'(?:你们)?(?:最好(?:的)?(?:是)?哪(?:一)?款|哪(?:一)?款最好|推荐最好(?:的)?(?:一)?款)',plain):
            return 'answered',products['803']['short_replies']['best_recommendation'],'product.803.best_recommendation'
        if re.fullmatch(r'(?:运费险有|有运费险|有没有运费险)(?:吗|嘛)?',plain):
            return 'answered',data['store']['facts']['freight_insurance'],'store.freight_insurance'
        if re.fullmatch(r'(?:多久|几天)(?:能|可以)?(?:到|收到|送到|送达)(?:货)?',plain):
            return 'answered',data['store']['facts']['delivery_with_expedite'],'store.delivery_with_expedite'
    return None

def approved_reply(text, product, data):
    plain=text.strip()
    if product:
        for name in sorted([product['name'],product['id'],*product['aliases']],key=len,reverse=True):
            plain=plain.replace(name,'')
    plain=re.sub(r'[\s？?！!，,。～~]', '',plain).strip('的')
    if re.fullmatch(r'(?:有|有没有)?80(?:厘米|cm)?宽(?:的)?(?:杆子|支架|款式)?(?:吗|嘛)?',plain):
        return 'answered',FLEX_RECOMMENDATION,'catalog.full_stretch'
    if not product:
        return None
    pid=product['id'];replies=product['short_replies']
    if re.fullmatch(r'(?:支架)?承重(?:怎么样|如何|多少|是多少|好吗)?',plain):
        return 'answered',replies['stability'],f'product.{pid}.stability'
    if re.fullmatch(r'什么支架|(?:支架|杆子)(?:是|用)?(?:什么|啥)(?:材质|材料)?',plain):
        return 'answered',replies['pole_sales'],f'product.{pid}.pole_sales'
    if re.fullmatch(r'(?:有|有没有|有无)(?:涂层)(?:吗|嘛)?',plain):
        return 'answered',replies['coating'],f'product.{pid}.coating'
    if re.fullmatch(r'为什么(?:这么|那么|会这么)?贵|怎么(?:这么|那么)贵|为什么贵这么多',plain) and pid=='803':
        return 'answered',replies['price_objection'],f'product.{pid}.price_objection'
    if re.fullmatch(r'(?:怎么|如何)安装|安装(?:步骤|方法)',plain):
        return 'answered',replies['easy_installation'],f'product.{pid}.easy_installation'
    if re.fullmatch(r'(?:价格|多少钱|什么价|什么价格|多少元|折后多少钱|折扣后多少钱)',plain):
        return 'answered',replies['reference_price'],f'product.{pid}.reference_price'
    if re.fullmatch(r'(?:我)?(?:睡|在|是)?(?:上铺|下铺|上下铺)(?:怎么选|如何选|选哪个|选哪款|选哪款好|选什么|用哪款|适合哪款)',plain):
        if pid=='801':
            return 'answered',replies['bunk_recommendation'],f'product.{pid}.bunk_recommendation'
        return None
    if re.fullmatch(r'(?:支架|杆子)?(?:稳|稳固|牢固|结实)(?:吗|不稳|不牢固)?(?:会不会(?:晃|慌|晃动))?|会不会(?:晃|慌|晃动)',plain):
        return 'answered',replies['stability'],f'product.{pid}.stability'
    if re.fullmatch(r'(?:排插|插排|插线板)(?:呢|可以过吗|能过吗|可以放进来吗|放得进吗|能放进来吗|能穿过去吗)?|(?:那我|我)?(?:怎么|如何)充电(?:呢|呀)?',plain):
        return 'answered',replies['power_strip'],f'product.{pid}.power_strip'
    if re.fullmatch(r'(?:安装|装起来)(?:麻烦|难|难不难|麻不麻烦)(?:吗|嘛)?',plain):
        return 'answered',replies['easy_installation'],f'product.{pid}.easy_installation'
    if re.fullmatch(r'(?:可以|能)?(?:拆卸|拆下来|拆洗|拆卸清洗)(?:清洗|洗)?(?:吗|嘛)?',plain):
        return 'answered',replies['removable_washing'],f'product.{pid}.removable_washing'
    if re.fullmatch(r'(?:有|有没有|含|含不含|是否含有|会有)?甲醛(?:吗|嘛)?|甲醛(?:含量|问题)',plain):
        return 'answered',replies['formaldehyde_script'],f'product.{pid}.formaldehyde_script'
    return None
