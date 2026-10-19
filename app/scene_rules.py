"""场景负责识别问题，答案负责商品、状态和时间条件。"""
import copy
import re
from datetime import datetime, timezone, timedelta

SCENE_TYPES = {'industry':0, 'special':1, 'custom':2}
STAGES = ('presales','shipping','received','aftersales')
CHINA = timezone(timedelta(hours=8))
TITLES = {'specifications':'商品尺寸','telescoping':'伸缩范围','stability':'支架稳固 / 承重',
 'pole_sales':'支架介绍','pole_material':'支架材质','pole_diameter':'支架粗细','pole_wall':'支架壁厚',
 'sound_insulation':'隔音效果','roof':'顶棚材质','coating':'涂层咨询','doors':'开门方式',
 'shade_sides':'四面 / 五面','bottom':'底部设计','charging_port':'充电走线','power_strip':'排插与充电',
 'washing':'清洗方式','removable_washing':'拆卸清洗','easy_installation':'安装方法',
 'instructions':'使用说明','colors':'可选颜色','weight':'商品重量','material':'商品材质',
 'packaging':'包装规格','storage':'收纳设计','formaldehyde_script':'甲醛咨询',
 'reference_price':'参考价格','price_objection':'价格疑虑','bunk_recommendation':'上下铺推荐',
 'catalog_recommendation':'免安装款推荐','best_recommendation':'小狗款推荐',
 'delivery_summary':'物流与发货','delivery_with_expedite':'送达与加急','expedite':'加急发货',
 'freight_insurance':'运费险','shipping':'发货时效','arrival':'到货时效','freight':'运费政策',
 'after_sales':'售后政策','quality':'商品质量','selling_points':'商品卖点','scenarios':'适用场景',
 'appearance':'实物外观','inner_color':'内外颜色','custom_size':'尺寸定制',
 'jd_delivery':'京东物流','delivery_choice':'物流方式','courier':'普通快递'}


def normalize_document(document):
    doc=copy.deepcopy(document)
    doc['schema_version']='2.0'
    scenes={s['id']:copy.deepcopy(s) for s in doc.get('scenes',[])}
    for row in doc.get('records',[]):
        key=row.get('scene_id') or 'industry.'+row['intent']
        row.setdefault('scene_id',key)
        row.setdefault('scene_type','industry')
        row.setdefault('scene_name',TITLES.get(row['intent'],row['intent']))
        row.setdefault('conditions',{})
        row['conditions']={'reception':'all','stages':[],'valid_from':None,'valid_until':None,**row['conditions']}
        row.setdefault('keywords',[]);row.setdefault('keyword_mode','any');row.setdefault('priority',0)
        row.setdefault('configured_scene',False)
        if key not in scenes:
            scenes[key]={'id':key,'name':row['scene_name'],'type':row['scene_type'],
                         'question_variants':[],'category':row.get('category','商品咨询')}
        scene=scenes[key]
        if 'scenes' not in document or not any(s['id']==key for s in document['scenes']):
            scene['question_variants']=list(dict.fromkeys([*scene['question_variants'],*row['question_variants']]))
        row['scene_type'],row['scene_name']=scene['type'],scene['name']
    doc['scenes']=list(scenes.values())
    return doc


def parse_time(value):
    if not value: return None
    dt=datetime.fromisoformat(value.replace('Z','+00:00'))
    return dt if dt.tzinfo else dt.replace(tzinfo=CHINA)


def row_eligible(row,pid,reception='presales',stage='presales',now=None):
    if row.get('status')!='active':return False
    if row.get('scope')=='product' and pid not in row.get('product_ids',[]):return False
    c=row.get('conditions',{})
    if c.get('reception','all') not in ('all',reception):return False
    if c.get('stages') and stage not in c['stages']:return False
    moment=now or datetime.now(CHINA)
    if moment.tzinfo is None:moment=moment.replace(tzinfo=CHINA)
    start,end=parse_time(c.get('valid_from')),parse_time(c.get('valid_until'))
    return (start is None or moment>=start) and (end is None or moment<=end)


def rank(row):
    c=row.get('conditions',{})
    # 类型优先，其次手动优先级；相同时选限制更明确的答案。
    specificity=(int(row.get('scope')=='product'),-len(row.get('product_ids',[])) if row.get('scope')=='product' else 0,
                 int(c.get('reception','all')!='all'),int(bool(c.get('stages'))),
                 -len(c.get('stages',[])),int(bool(c.get('valid_from') or c.get('valid_until'))))
    return (SCENE_TYPES.get(row.get('scene_type','industry'),0),row.get('priority',0),
            int(bool(row.get('configured_scene'))),*specificity)


def managed(row):
    c=row.get('conditions',{})
    return bool(row.get('configured_scene') or row.get('scene_type','industry')!='industry' or
                row.get('keywords') or row.get('priority') or c.get('reception','all')!='all' or
                c.get('stages') or c.get('valid_from') or c.get('valid_until'))


def keyword_match(row,text):
    words=row.get('keywords',[])
    if not words:return False
    checks=[w.lower() in text.lower() for w in words]
    return all(checks) if row.get('keyword_mode','any')=='all' else any(checks)
