"""一次性迁移现有资料；已有 FAQ 时拒绝覆盖，日常直接编辑 FAQ。"""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.config import ROOT
from app.semantic import SEEDS
from app.knowledge import FIELDS
from app.replies import FLEX_RECOMMENDATION

path = ROOT / 'data/faq.json'
if path.exists():
    raise SystemExit('FAQ already exists; edit it directly instead of rebuilding.')
data = json.loads((ROOT/'data/nets_801_804.json').read_text(encoding='utf-8'))
source = json.loads((ROOT/'data/source_qa.json').read_text(encoding='utf-8'))
rows = []
def add(id, intent, variants, answer, scope, pid=None, fields=None, images=None,
        sources=None, status='active', origin='approved_product'):
    rows.append(dict(id=id, intent=intent, question_variants=list(dict.fromkeys(variants)),
        standard_answer=answer, scope=scope, product_ids=[pid] if scope=='product' else [],
        answer_product_id=pid, category='物流' if scope=='store' and
        ('delivery' in intent or 'shipping' in intent or intent=='expedite') else
        '选款推荐' if scope=='catalog' else '商品咨询', fields=fields or [],
        images=images or [], sources=sources or [], status=status, origin=origin,
        boundaries={'requires_confirmed_product':scope=='product', 'no_order_operations':True,
        'no_extra_promises':True, 'unsupported':'operator_only_no_customer_reply'},
        updated_at='2026-10-14'))

extra = {'stability':['承重怎么样','会不会晃','支架稳吗'],
    'pole_sales':['什么支架','支架是什么材质'],
    'power_strip':['排插呢','排插可以过吗','那我怎么充电'],
    'removable_washing':['可以拆卸清洗吗'], 'easy_installation':['怎么安装','安装麻烦吗'],
    'price_objection':['为什么这么贵'], 'bunk_recommendation':['我睡上铺怎么选','睡下铺选哪款好'],
    'formaldehyde_script':['有甲醛吗']}
for product in data['products']:
    pid = product['id']
    for field, answer in product['short_replies'].items():
        if not answer: continue
        scope = 'catalog' if field in ['catalog_recommendation','best_recommendation'] else 'product'
        variants = extra.get(field,[]) or SEEDS.get(field,[]) or list(FIELDS.get(field,[]))
        if scope=='catalog':
            variants = ['有没有免安装的款式','有免安装的吗'] if pid=='804' else ['你们最好的是哪款','哪款最好']
        add(f'product.{pid}.{field}',field,variants,answer,scope,pid,[field],
            product.get('answer_images',{}).get(field,[]),product.get('sources',{}).get(field,[]))
for r in source['records']:
    product = next(x for x in data['products'] if x['id']==r['product_id'])
    images = []
    for field in r['fields']:
        for image in product.get('answer_images',{}).get(field,[]):
            if image not in images: images.append(image)
    add(r['id'],r['fields'][0] if len(r['fields'])==1 else r['question'],
        [r['question'],*r['aliases']],r['answer'],'product',r['product_id'],r['fields'],images,
        [r['source']],r['status'],'source_qa')
store_variants = {'delivery_summary':['多久发货','物流','发货时效'],
    'delivery_with_expedite':['多久能到','几天能到'],
    'freight_insurance':['运费险有吗','有运费险吗'], 'expedite':['今天能发吗','可以加急吗']}
for field, answer in data['store']['facts'].items():
    add('store.'+field,field,store_variants.get(field,[]),answer,'store',
        sources=data['store'].get('sources',{}).get(field,[]),origin='approved_store')
add('catalog.full_stretch','全伸缩推荐',['有全伸缩支架吗','有80宽的杆子吗','长宽高都可以伸缩的有吗'],
    FLEX_RECOMMENDATION,'catalog','802',['telescoping'],origin='approved_catalog')
result = {'schema_version':'1.0','description':'801–804统一FAQ；active条目才自动回复。',
    'manual_boundaries':['纠纷','赔偿','投诉','情绪激烈','订单或退款操作'], 'records':rows}
path.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print('FAQ records:',len(rows),'active:',sum(r['status']=='active' for r in rows))
