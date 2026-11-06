"""从私有原声整理目录和待审核FAQ；仅启用逐项整理的基础资料。"""
import copy, hashlib, json, re
from pathlib import Path
from app.config import ROOT
from app.faq_admin import FAQStore
from scripts.test_customer_voices import redact

PRODUCTS=[('tietie','贴贴枕','枕头'),('cloudquilt','云朵被','被子'),('plushblanket','长毛绒电热毯','电热毯'),
          ('heater','立式取暖器','取暖器'),('nonwovenblanket','无纺布电热毯','电热毯'),
          ('latexpillow','云感乳胶枕','枕头'),('601','601防摔蚊帐','家用蚊帐')]
# 以下只保留原表的基础规格和结构，去掉疗效、认证和绝对保证。
CORE={
'tietie':[
 ('dimensions','贴贴枕尺寸与高度',['多大尺寸','枕头尺寸','中高低买哪个，成人用','高度有哪几款'],
  '亲亲，贴贴枕长60厘米、宽40厘米；低枕6–8厘米，中枕8–10厘米，高枕10–12厘米。选择高度还要结合平时的睡姿和习惯哈～'),
 ('material','贴贴枕填充材质',['什么材质','填充是什么','是记忆棉吗'],'亲亲，贴贴枕的填充物是记忆棉哈～'),
 ('care','贴贴枕清洁方式',['能不能水洗','枕芯可以洗吗','怎么清洗'],'亲亲，枕套可以水洗；枕芯有污渍时用湿毛巾蘸温和清洁剂轻擦，吸干水分后通风阴干。具体以收到的洗护标识为准哈～')],
'cloudquilt':[
 ('dimensions','云朵被尺寸选择',['1.35的床，买多少米合适','1.35米床怎么选'], '亲亲，原表对1.35米床单人盖的建议是150×200厘米。双人共用或喜欢宽松一些，需要再结合使用人数和习惯选择哈～'),
 ('cover','云朵被是否包含被套',['带被套嘛','带被套吗','这个需要套被套吗'],'亲亲，云朵被不带被套，可以自行搭配被套使用哈～'),
 ('care','云朵被清洗方法',['能机洗吗','可以水洗吗','清洗的方式','怎么洗'],'亲亲，原表说明支持水洗、机洗，建议轻柔模式、中性洗涤剂、低速脱水，阴凉晾干；不要暴晒或干洗，清洗前再核对洗护标和洗衣机容量哈～'),
 ('material','云朵被填充成分',['填充物是什么','这一款被子里面是什么绒','这里面是啥'],'亲亲，原表标注填充配方为5%赤豆纤维、5%莱赛尔和90%中空纤维；完整成分名称请再核对实物水洗标哈～')],
'plushblanket':[
 ('thickness','长毛绒电热毯厚度',['厚度多少','有多厚','毯子厚度'],'亲亲，原表标注长毛绒电热毯厚度约12毫米，实物可能存在测量差异哈～'),
 ('zones','长毛绒电热毯左右温区',['怎么分左右电热','是躺下来左手为左，还是人面对床那边为左'],'亲亲，原表的左右温区按人躺下后的视角区分：左手侧是左温区，右手侧是右温区。具体按您收到型号的控制器标识核对哈～')],
'heater':[
 ('identify','取暖器型号核对',['这是什么取暖器','取暖器怎么选型号'],'亲亲，当前接入的是立式取暖器。不同型号的功率和适用面积需要核对，您可以提供商品型号或参数标签，人工再帮您确认哈～')],
'nonwovenblanket':[
 ('control','无纺布电热毯单控双控区别',['单控和双控的区别是','单控双控有什么区别'],'亲亲，原表说明单控由一个开关控制整张毯子，双控可分别调节左右温区。选购时请核对具体规格页的控制方式哈～'),
 ('selection','无纺布电热毯选规格',['标准1.8米床，应该买哪款，没看懂','应该选多大的电热毯'],'亲亲，选购时先核对床的宽度，再对照当前商品页的规格选项；具体铺放方式和尺寸还要按对应型号说明书确认哈～')],
'latexpillow':[
 ('dimensions','云感乳胶枕尺寸高度',['什么尺寸','枕头高度怎么选','长宽是多少'],'亲亲，云感乳胶枕长60厘米、宽40厘米；中枕高8–10厘米，高枕高10–12厘米。建议结合平时睡姿和习惯选择哈～'),
 ('pillowcase','乳胶枕搭配枕套',['正常枕套能否使用','枕套尺寸怎么选'],'亲亲，这款枕头长60厘米、宽40厘米，搭配枕套时请对照这个尺寸核实，较大的枕套可能会宽松一些哈～')],
'601':[
 ('height','601蚊帐高度',['蚊帐高度有低一些的吗','高度多少','可以调高度吗'],'亲亲，601蚊帐原表标注为固定170厘米高度，不能按801或802款的伸缩范围来选择哈～'),
 ('bottom','601床笠全底区别',['床笠款和全底款是什么区别','床笠和全底区别'],'亲亲，全底款底部也有网纱，可以把床单铺在蚊帐里面；床笠款底部镂空没有网纱，可以先铺好床单再安装。两种结构不等于防坠落保证哈～'),
 ('material','601蚊帐材质',['什么材质','帐纱材质','支架材质'],'亲亲，原表标注601款帐纱为聚酯纤维，支架为六棱碳素钢；具体以对应型号参数标识为准哈～')]
}

def record(pid,key,title,questions,answer,status='active',sources=None):
    sid='industry.catalog_'+key;rid=f'catalog.{pid}.{key}'
    return {'id':rid,'intent':key,'scene_id':sid,'scene_name':title,'scene_type':'industry','category':'新品商品咨询',
        'question_variants':list(dict.fromkeys([title,*questions]))[:100],'standard_answer':answer,'answer_parts':[answer] if answer else [],
        'scope':'product','product_ids':[pid],'answer_product_id':pid,'fields':[],'status':status,'configured_scene':True,
        'origin':'catalog_onboarding','images':[],'keywords':[],'keyword_mode':'any','priority':0,'updated_at':'2026-11-05',
        'conditions':{'reception':'all','stages':[],'valid_from':None,'valid_until':None},
        'sources':sources or [{'type':'merchant_resource','file':'机器人专项原声收集配置.xlsx','sheet':'小智冬季品配置（售前）','date':'2026-11-05','excerpt':'从商家提供原表整理基础资料，去掉额外承诺；具体规格核对实物标识。'}],
        'boundaries':{'no_extra_promises':True,'no_order_operations':True,'unsupported':'operator_only_no_customer_reply'}}

def build(source):
    products=[];records=[]
    for pid,name,category in PRODUCTS:
        products.append({'id':pid,'model':pid,'name':name,'aliases':[name], 'category':category,'routing':'catalog',
            'updated_at':'2026-11-05','facts':{},'short_replies':{},'sources':{},'blocked_topics':[],
            'onboarding_status':'基础资料已接入；其他资料待审核'})
        for key,title,q,a in CORE[pid]:
            # 不同产品可共享意图；统一用不带商品名称的稳定意图名。
            title={'dimensions':'商品尺寸与高度','material':'商品材质与填充','care':'清洁与洗护','height':'商品高度是否可调',
                   'bottom':'底部结构区别','pillowcase':'枕套搭配','cover':'是否包含被套','zones':'左右温区区分',
                   'control':'单控与双控区别','selection':'规格如何选择','thickness':'商品厚度','identify':'商品型号核对'}[key]
            records.append(record(pid,key,title,q,a))
    names={name:pid for pid,name,_ in PRODUCTS};grouped={}
    sheet=next(s for s in source if s['name']=='小智冬季品配置（售前）')
    for raw in sheet['rows'][1:]:
        d={re.sub(r'\d','',k):v for k,v in raw.items()};pid=names.get(d.get('D',''))
        q,a=redact(d.get('C','')),redact(d.get('E',''))
        if not pid or not q or not a:continue
        core=next((r for r in records if r['product_ids']==[pid] and q in r['question_variants']),None)
        if core:continue
        digest=hashlib.sha256((pid+a).encode()).hexdigest()[:12]
        item=grouped.setdefault((pid,digest),{'questions':[],'answer':a,'sources':[]})
        if q not in item['questions']:item['questions'].append(q)
        item['sources'].append({'type':'merchant_resource_pending','file':'机器人专项原声收集配置.xlsx','sheet':sheet['name'],
            'cell':next((k for k in raw if k.startswith('C')),''),'date':'2026-11-05'})
    for (pid,digest),g in grouped.items():
        key='draft_'+digest
        r=record(pid,key,g['questions'][0][:180],g['questions'],g['answer'][:12000],'needs_review',g['sources'][:10])
        r['review_note']='原表参考话术，未核验：可能涉及型号冲突、疗效、安全、费用或额外承诺；审核前不能自动回复或供RAG引用。'
        records.append(r)
    return products,records

def merge(doc,records):
    doc=copy.deepcopy(doc)
    for r in records:
        if not any(s['id']==r['scene_id'] for s in doc['scenes']):
            doc['scenes'].append({'id':r['scene_id'],'name':r['scene_name'],'type':'industry','category':r['category'],
                'question_variants':r['question_variants'][:],'configured':True,'description':'按商品和触发条件选择已审核答案；待核实条目不自动启用。'})
        else:
            scene=next(s for s in doc['scenes'] if s['id']==r['scene_id'])
            scene['question_variants']=list(dict.fromkeys(scene['question_variants']+r['question_variants']))[:100]
        if not any(x['id']==r['id'] for x in doc['records']):doc['records'].append(r)
    return doc

if __name__=='__main__':
    source=json.loads((ROOT/'logs/customer-voices/parsed-sheets.json').read_text(encoding='utf-8'))
    products,records=build(source)
    # 独立目录，不改四款蚊帐的既有参数。
    (ROOT/'data/catalog_products.json').write_text(json.dumps({'products':products},ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    package=ROOT/'logs/catalog-onboarding-package.json';package.write_text(json.dumps({'records':records},ensure_ascii=False),encoding='utf-8')
    store=FAQStore();doc,_=store.read();updated=merge(doc,records)
    if doc!=updated:store.persist(updated,lambda d:None)
    print(json.dumps({'products':len(products),'active':sum(r['status']=='active' for r in records),'needs_review':sum(r['status']=='needs_review' for r in records)},ensure_ascii=False))
