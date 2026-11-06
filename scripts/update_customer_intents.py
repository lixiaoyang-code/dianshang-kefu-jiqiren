"""整理现有蚊帐意图，保留话术、图片、来源和触发条件；可重复运行。"""
import copy
import json
import re
import sys
from datetime import datetime
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT

NAMES={
'specifications':'这款蚊帐是什么尺寸？','doors':'蚊帐怎么开门？','shade_sides':'四面和五面有什么区别？',
'coating':'遮光帘有涂层吗？','material':'蚊帐和床帘是什么材质？','pole_diameter':'支架直径是多少？',
'pole_wall':'支架壁厚是多少？','roof':'顶棚是什么材质？','sound_insulation':'床帘可以隔音吗？',
'stability':'支架稳固吗？会不会晃？','bunk_recommendation':'上铺和下铺怎么选？',
'power_strip':'排插能放进来吗？怎么充电？','easy_installation':'怎么安装？安装麻烦吗？',
'removable_washing':'可以拆卸清洗吗？','formaldehyde_script':'产品有甲醛吗？','instructions':'怎么使用和安装？',
'appearance':'有实物图片吗？','reference_price':'这款大概多少钱？','pole_sales':'这是什么支架？',
'pole_material':'支架是什么材质？','colors':'有哪些颜色？','washing':'可以机洗吗？',
'price_objection':'这款为什么贵？','best_recommendation':'你们最好的是哪一款？',
'catalog_recommendation':'有没有免安装的款式？','bottom':'蚊帐底部是什么设计？',
'charging_port':'电源线怎么穿？','inner_color':'内外颜色一样吗？','telescoping':'支架伸缩范围是多少？',
'delivery_summary':'多久发货和送达？','delivery_with_expedite':'多久能到？可以加急吗？',
'expedite':'今天能发吗？可以加急吗？','freight_insurance':'有运费险吗？',
'shipping':'多久发货？','arrival':'多久能收到？','freight':'运费怎么算？','after_sales':'售后规则是什么？',
'quality':'商品质量怎么样？','selling_points':'这款有什么优点？','scenarios':'适合什么场景？',
'full_stretch':'有没有长宽高都能伸缩的款式？',
'全伸缩推荐':'有没有长宽高都能伸缩的款式？','卖点':'这款有哪些卖点？',
'不确定高度':'不确定床铺高度，应该怎么选？','不确定宽度':'不确定床铺宽度，应该怎么选？',
'加粗':'有加粗支架吗？','尺寸定制':'可以定制尺寸吗？','收纳设计':'有收纳袋吗？',
'学校不让装':'学校不允许安装，怎么办？',
'学校有支架':'学校自带支架，可以使用吗？','赠送置物架':'有赠送置物架吗？',
'针对没货的参考话术':'这款缺货了怎么办？','无法使用微信支付':'为什么不能用微信支付？',
'京东物流':'是否由京东物流配送？','物流方式':'发什么快递？','普通快递':'普通快递多久能到？',
}

def migrate(doc):
    doc=copy.deepcopy(doc)
    for scene in doc['scenes']:
        if scene['type']!='industry' or scene.get('configured'):continue
        topic=scene['id'].removeprefix('industry.')
        short_name=scene['name'].splitlines()[0].split('/')[0].strip('？?：: ')
        scene['name']=NAMES.get(topic,NAMES.get(short_name,short_name))
        if len(scene['name'])>100:scene['name']=scene['name'][:100]
        if not scene['name'].endswith(('？','?')):scene['name']+='？'
        # 原始表中整段多行问法保留，同时拆出单条真实问法。
        variants=[scene['name'],*scene['question_variants']]
        variants += [v.strip() for q in scene['question_variants'] for v in q.splitlines() if v.strip()]
        scene['question_variants']=list(dict.fromkeys(variants))
    stability=next(s for s in doc['scenes'] if s['id']=='industry.stability')
    stability['description']='询问支架是否稳固、是否晃动。承重数值归到“支架承重多少”。'
    stability['question_variants']=[q for q in stability['question_variants'] if '承重' not in q]
    for q in ['稳固吗','会不会晃','支架稳吗','支架结实吗','架子会摇吗']:
        if q not in stability['question_variants']:stability['question_variants'].append(q)
    load_id='industry.load_capacity'
    if not any(s['id']==load_id for s in doc['scenes']):
        doc['scenes'].append({'id':load_id,'type':'industry','name':'支架承重多少？','category':stability['category'],
            'description':'询问支架可承受的重量，不等同于所有条件下的稳定性。',
            'question_variants':['支架承重多少？','承重怎么样','承重多少','能挂多重','能承受几斤','支架能承重多少']})
    by_id={r['id']:r for r in doc['records']}
    for row in list(doc['records']):
        if row['scene_id']!='industry.stability':continue
        if row['id'].startswith('product.'):
            new_id=row['id'].removesuffix('stability')+'load_capacity'
            if new_id not in by_id:
                clone=copy.deepcopy(row);clone.update(id=new_id,intent='load_capacity',scene_id=load_id,origin='custom')
                doc['records'].append(clone)
        elif row['question_variants'] and all('承重' in q for q in row['question_variants']):
            row['scene_id']=load_id;row['intent']='load_capacity'
    height_id='industry.height_range'
    if not any(s['id']==height_id for s in doc['scenes']):
        doc['scenes'].append({'id':height_id,'type':'industry','name':'支架高度可以调节多少？','category':'商品参数',
            'description':'询问高度伸缩范围；不同高度款分别回答，不能把长宽范围当高度。',
            'question_variants':['支架高度可以调节多少？','伸缩高度是多少？','高度能调多少','最高多高','最低能降到多少']})
        for row in list(doc['records']):
            if row['id'] in [f'product.{p}.telescoping' for p in ['801','802','803','804']]:
                clone=copy.deepcopy(row);clone.update(id=row['id'].removesuffix('telescoping')+'height_range',intent='height_range',scene_id=height_id,origin='custom')
                doc['records'].append(clone)
    scenes={s['id']:s for s in doc['scenes']}
    for row in doc['records']:
        scene=scenes[row['scene_id']]
        row.update(scene_name=scene['name'],scene_type=scene['type'])
        if row['scene_id'] in ('industry.load_capacity','industry.height_range'):
            row['question_variants']=scene['question_variants'];row['configured_scene']=True
        elif row['scene_id']=='industry.stability':
            row['question_variants']=[q for q in row['question_variants'] if '承重' not in q]
    return doc

if __name__=='__main__':
    target=ROOT/'data/faq.json';old=target.read_bytes();doc=migrate(json.loads(old))
    raw=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if raw!=old:
        backup=target.parent/'backups';backup.mkdir(exist_ok=True)
        (backup/f'faq-before-intents-{datetime.now():%Y%m%dT%H%M%S}.json').write_bytes(old)
        target.write_bytes(raw)
    print('Customer intents:',len(doc['scenes']),'Answers:',len(doc['records']))
