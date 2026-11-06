"""按商家授权启用原声问答；生成可复核清单，迁移保留云端人工修改。"""
import copy, hashlib, json, re
from collections import Counter, defaultdict
from pathlib import Path
from app.faq import canonical
from app.faq_admin import FAQStore
from app.knowledge import Knowledge
from app.config import ROOT
from scripts.test_customer_voices import prepare

DATE='2026-11-06'
# 逐项核对发现的错配、未经验证的机理及依赖上文的回复。
HOLD_IDS={
 'draft_e42aab07b939','draft_420013c93eb6','draft_989b84f94215','draft_6edc9543bf51',
 'draft_8961870c0aca','draft_bfcd3f57182c','draft_c0f1dfeebdcd','draft_2dabfe2bd8a5',
 'draft_5dae0bb1f31b','draft_86cc537b17e5','draft_39ef2373afda','draft_06848fafc4df',
 'draft_7c27bc6c8437','draft_e0f47cea0d5a','draft_402ebbc357e9','draft_1fe1cdd1b1ee',
 'draft_b9fcc7870a9b','draft_4fb59a9c4d12','draft_8043edf93f49',
}


def digest(row):
    return hashlib.sha256(json.dumps(row,sort_keys=True,ensure_ascii=False).encode()).hexdigest()


def curate(row, document):
    r=copy.deepcopy(row);q=' / '.join(r.get('question_variants') or []);a=r.get('standard_answer') or ''
    pid=(r.get('product_ids') or [''])[0]
    reason=''
    if not a.strip():return r,'原资料没有文字答案，需要补充依据'
    if r['id'].split('.')[-1] in HOLD_IDS:return r,'逐项核对发现答非所问、参数冲突或未经验证的功能说明'
    # 对应问句与参考话术实际不相符，不能靠启用状态修复。
    if ('质保' in q and '七天无理由' in a and not re.search(r'质保.{0,8}(一年|年|月)',a)) or ('定时' in q and '风力多档' in a):
        return r,'问答不对应，需要重新提供答案'
    if re.search(r'颈椎病|反弓|椎间盘|富贵包|打呼|止鼾|孕妇|初生婴儿|宝宝可以|小宝宝|过敏体质|治疗|缓解颈椎|修复颈椎|促进血液循环',q+' '+a):
        return r,'涉及疗效或特殊人群，现有资料不足以支持承诺'
    if re.search(r'漏电|触电|跳闸|尿床|尿尿|溅上水|滴上水|弄湿|防摔|掉下床|掉床|掉下去|坠床|坐在横杆',q) or re.search(r'100斤|防止宝宝|具有防摔|防摔效果|防摔才是|主打的就是防摔',a):
        return r,'用电异常或儿童防坠问题，需要人工核实，禁止保证安全'
    if pid in ('plushblanket','nonwovenblanket') and re.search(r'机洗|水洗|甩干|洗衣机|烘干|防水|乳胶床垫|折叠使用|一直高温|高温一直',q):
        return r,'电热毯洗护或使用边界需按对应型号说明书核验'
    if pid=='heater' and re.search(r'面积|平方|平米|零下|室内温度|最高温度|多久能|要多久|热起来|升温度',q):
        return r,'适用面积、升温或温度数据在原表中不一致'
    if pid=='tietie' and re.search(r'密度|多少d|40d',q,re.I):return r,'同款原表出现35D和40D，需要确认型号'
    if pid=='cloudquilt' and re.search(r'几斤|四斤|4斤|6斤|8斤|10斤|3斤|重量有什么|冬天|秋天|怕冷|四季|空调睡|空调房',q.replace(' ','')):
        core=next(x for x in document['records'] if x['id']=='catalog.cloudquilt.weight_selection')
        r['standard_answer']=core['standard_answer'];r['boundaries']['requires_clarification']=True
        reason='原表斤数建议冲突，统一为尺寸、季节、室温追问'
    elif pid=='cloudquilt' and re.search(r'填充|含量|成分|大豆|赤豆|莱赛尔|莱塞尔|胶原蛋白',q+' '+a):
        return r,'原表填充成分有赤豆、大豆、胶原蛋白等冲突，需要核对水洗标'
    elif re.search(r'证书|报告|认证|甲醛|荧光|[7A]A级|母婴级|无毒|无害|消毒|杀菌|绝对安全|最高安全标准|国标',q+' '+a):
        return r,'检测、认证或消毒声明缺少对应可核验附件'
    elif re.search(r'\[链接\]|看看.{0,6}(图片|照片)|看下.{0,6}(图片|照片)|发教程|看一下哈|参考一下哈',a) and not r.get('images'):
        return r,'话术依赖图片、链接或教程，但此条没有绑定附件'
    elif re.search(r'可以预约|不想定时|通电后用定时|预约是|最长定时|会自动断电|过热|高温自动断电|恒温',q) and pid in ('plushblanket','nonwovenblanket'):
        return r,'定时、预约和保护功能原表存在不同型号或互相冲突的说明'
    elif pid in ('plushblanket','nonwovenblanket','heater') and re.search(r'耗电|度电|费电|多少电',q):
        if pid=='heater':a='亲亲，耗电量和档位、室温及使用时长有关。按原表高档2200W计算，持续满功率1小时约2.2度电；ECO会随温度调节，不能保证每小时固定0.5度电。具体以所选型号铭牌和实际使用为准哈～'
        elif pid=='plushblanket':a='亲亲，原表单人最高功率70W、双人最高160W；持续满功率10小时分别约0.7度、1.6度电。调温或间歇工作时实际耗电会变化，以具体型号铭牌为准哈～'
        else:a='亲亲，原表单人最高功率65W、双人最高140W；持续满功率10小时分别约0.65度、1.4度电。实际耗电随档位和控温变化，宿舍能否使用还需核对学校规定哈～'
        r['standard_answer']=a;reason='按原表功率重新计算耗电量，移除宿舍适用保证'
    elif re.search(r'运费险|超重|运费全包|包运费|免费退|承担运费',q):
        if '运费险' in q:
            a='亲亲，原表配置有赠送运费险，实际是否赠送请以下单页和订单保障为准哈～理赔额度按保单规则计算，超出部分需要另行核实。'
        elif re.search(r'退|试睡|试用|拆开|包装',q):
            a='亲亲，原表支持7天无理由退换；是否符合退换条件，以及运费险和超出部分费用，请以订单保障和商品状态为准。您可以提供订单信息，人工帮您核实哈～'
        else:a='亲亲，退回运费需结合订单保障、退货原因和保单额度核实，不能保证所有费用都由运费险承担；您发一下订单信息，人工帮您确认哈～'
        r['standard_answer']=a;reason='保留原表售后服务，去掉无限额运费承诺'
    elif re.search(r'7\s*天|七天|试睡|试用|退货|退换',q+' '+a):
        if not re.search(r'退|试睡|试用|拆开|包装',q):
            # 不把“机洗/密度”的答案改成售后话术；保留有依据的核心信息。
            if pid=='cloudquilt' and re.search(r'机洗|起球',q):return r,'原话术混有15000次机洗或免费退承诺，已有洗护主答案，需补充正确问法'
            return r,'原话术将商品问题与试用售后混答，需要拆分'
        r['standard_answer']='亲亲，原表支持7天无理由退换，具体适用条件请以订单服务承诺和商品状态为准哈～拆封或试用后的情况、取件方式及费用，请人工结合订单核实。'
        reason='保留原表7天服务，明确适用条件，不承诺无条件免费上门'
    elif re.search(r'包运费|承担运费|不花.{0,3}钱|没有任何风险|假一赔|免费换',a):
        return r,'商品话术混入费用或赔付承诺，需拆分后核实'
    elif re.search(r'已.{0,4}(安排|备注|处理)|给您.{0,4}(安排|备注|申请)|联系仓库|加急|优先发',a):
        a=re.sub(r'小妹.{0,8}给您.*','',a)
        if re.search(r'发|到|多久|加急',q):a='亲亲，您可以查看下单页或订单中的预计发货、送达时间；着急使用的话，请把订单信息发来，人工帮您核实能否加急，具体以仓库和物流实际进度为准哈～'
        elif re.search(r'优惠|便宜|价格',q):a='亲亲，具体到手价和优惠以您所选规格的下单页面为准哈～您可以发一下规格和页面截图，人工帮您核对有没有可用优惠。'
        else:return r,'参考话术依赖人工操作或订单承诺，需要核实后发送'
        r['standard_answer']=a;reason='改为人工可协助核实，不声称已执行订单操作'
    if not reason:
        a=r['standard_answer']
        a=re.sub(r'#E-[A-Za-z0-9]+','',a)
        a=a.replace('绝对','').replace('肯定没问题','正常使用并按洗护标保养').replace('最低价','当前活动价')
        r['standard_answer']=a
        reason='按商家授权启用原表明确问答'
    if len(canonical(q))<3:return r,'原声过短或依赖上文，不能独立建立自动答复'
    r['status']='active';r['answer_parts']=[r['standard_answer']]
    # 原声由谁记录是采集标签，不能拿它限制普通商品参数的答复阶段。
    if not re.search(r'退|换货|运费|质保|保修|试睡|试用|发货|送达|到货|送货|加急|优惠|价格|便宜|赠|送枕套|价保|国补|新款|出厂日期',q):
        r['conditions'].update(reception='all',stages=[])
        reason+='；通用商品信息适用售前后，不按记录人员限制'
    r['review_note']=reason;r['updated_at']=DATE;r['reviewed_source']='merchant_authorized_voice_import'
    for s in r.get('sources',[]):
        if s.get('type')=='merchant_resource_pending':s['type']='merchant_resource'
    return r,reason


# 只对原表明确标注且语义一致的意图补充问法，不用回答文本猜意图。
MAP={
 '咨询商品颜色':'colors','是什么颜色':'colors','有什么颜色':'colors',
 '咨询商品规格或尺寸':'specifications','询问商品尺寸':'specifications',
 '咨询商品如何清洁保养，是否易清洁|免清洗':'removable_washing','是否好清洗（清洁），如何清洗':'removable_washing',
 '是否能伸缩':'telescoping','询问商品承重范围':'load_capacity',
 '是否有安装教程':'easy_installation','是否有使用教程':'instructions',
 '询问商品几面遮光':'shade_sides','询问商品透光性':'light_blocking','是否分上下铺':'bunk_recommendation',
 '咨询店铺发货时间，通知发货':'shipping','咨询快递送达时间':'delivery_with_expedite',
 '咨询店铺发货快递':'delivery_choice','咨询能否或要求指定快递':'delivery_choice',
 '是否支持购买运费险（是否赠送运费险）':'freight_insurance',
 '咨询能否退货或退款':'common_returns_policy','咨询有无试用期及试用规则':'common_returns_policy',
 '买家要申请退款或退货':'common_return_request','咨询如何退货或退款':'common_return_request',
 '咨询如何换货':'common_exchange_request','反馈商家发错商品，如何处理':'common_damaged',
 '反馈商品破损或被打开过怎么办':'common_damaged','反馈商品收到发现少件或未全部发货':'common_damaged',
 '反馈工具配件缺少|错发|损坏，及如何处理':'common_damaged',
 '咨询商品物流信息':'common_tracking','咨询发货物流单号':'common_tracking','咨询商品是否发货，反馈未发货':'common_tracking',
 '咨询快递一直显示揽件中或等待揽件怎么办':'common_tracking','反馈查不到物流记录':'common_tracking','表示还没收到货':'common_tracking'
}


def plan(document, source):
    from app.scene_rules import normalize_document
    doc=normalize_document(document);updates=[];held=[]
    for old in doc['records']:
        if old['status']!='needs_review':continue
        new,reason=curate(old,doc)
        if new['status']=='active':updates.append({'before':digest(old),'row':new})
        else:held.append({'id':old['id'],'before':digest(old),'question':old['question_variants'][0] if old['question_variants'] else old['intent'],'reason':reason})
    # 相同问法、商品和条件下有多个不同答案时，保留已核准核心答案。
    core=[r for r in doc['records'] if r['status']=='active' and not r.get('canonical_answer_id')]
    index=defaultdict(list)
    for r in [*core,*(u['row'] for u in updates)]:
        for q in r['question_variants']:
            for pid in r.get('product_ids',[]) if r['scope']=='product' else ['store']:
                index[(pid,canonical(q),json.dumps(r['conditions'],sort_keys=True))].append(r)
    conflicts=set()
    for peers in index.values():
        if len({canonical(r['standard_answer']) for r in peers})<=1:continue
        existing=[r for r in peers if r in core]
        if existing:
            for r in peers:
                if r not in core:
                    if len({canonical(x['standard_answer']) for x in existing})==1:
                        r['standard_answer']=existing[0]['standard_answer']
                        r['answer_parts']=existing[0].get('answer_parts') or [r['standard_answer']]
                        r['review_note']+='；相同问法复用既有核准主答案'
                    else:conflicts.add(r['id'])
        else:conflicts.update(r['id'] for r in peers)
    selected=[]
    for u in updates:
        if u['row']['id'] in conflicts:held.append({'id':u['row']['id'],'before':u['before'],'question':u['row']['question_variants'][0],'reason':'相同商品、问法、条件存在不同答案，保留既有核准答案'})
        else:selected.append(u)
    variants=defaultdict(list);scenes={s['id']:s for s in doc['scenes']}
    for raw in source:
        if raw['domain']!='四款蚊帐':continue
        sid='industry.'+MAP.get(raw['source_intent'],'')
        if sid not in scenes:continue
        # 不把售后问题扩展到仅售前有效的商品答案。
        eligible=[r for r in core if r['scene_id']==sid and r['conditions']['reception'] in ('all',raw['reception'])]
        if not eligible:continue
        q=raw['question']
        if len(canonical(q))<3 or len(q)>300:continue
        if sid=='industry.common_damaged' and not re.search(r'破|损|坏|裂|漏|少|错发|发错|质量',q):continue
        if sid=='industry.common_tracking' and not re.search(r'物流|快递|运单|订单|货|发|到|收',q):continue
        if sid=='industry.common_returns_policy' and not re.search(r'退|退款|运费|试|拆',q):continue
        if canonical(q) not in {canonical(x) for x in scenes[sid]['question_variants']+variants[sid]}:
            if len(scenes[sid]['question_variants'])+len(variants[sid])<100:variants[sid].append(q)
    return {'date':DATE,'updates':selected,'variants':dict(variants),'held':held,
            'source_summary':{'total':len(source),'with_reference':sum(bool(r['reference_answer']) for r in source),
                'without_reference':sum(not r['reference_answer'] for r in source),
                'unknown_product':sum(r['domain']=='商品未确定' for r in source)}}


def apply(document, package):
    from app.scene_rules import normalize_document
    doc=normalize_document(document);applied=[];skipped=[]
    byid={r['id']:i for i,r in enumerate(doc['records'])}
    for u in package['updates']:
        rid=u['row']['id'];i=byid.get(rid)
        if i is None or digest(doc['records'][i])!=u['before']:
            skipped.append(rid);continue
        doc['records'][i]=copy.deepcopy(u['row']);applied.append(rid)
    for h in package['held']:
        i=byid.get(h['id'])
        if i is not None and digest(doc['records'][i])==h.get('before'):
            doc['records'][i]['review_note']=h['reason']
    for sid,questions in package['variants'].items():
        scene=next((s for s in doc['scenes'] if s['id']==sid),None)
        if not scene:continue
        scene['question_variants']=list(dict.fromkeys(scene['question_variants']+questions))[:100]
        for r in doc['records']:
            if r['scene_id']==sid:r['question_variants']=scene['question_variants'][:]
    return doc,{'activated':len(applied),'skipped_modified_or_already_applied':len(skipped)}


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--apply',type=Path);args=p.parse_args()
    store=FAQStore();doc,_=store.read()
    if args.apply:
        package=json.loads(args.apply.read_text(encoding='utf-8'))
    else:
        source=prepare(json.loads((ROOT/'logs/customer-voices/parsed-sheets.json').read_text(encoding='utf-8')))
        package=plan(doc,source)
        (ROOT/'logs/voice-activation-20261106.json').write_text(json.dumps(package,ensure_ascii=False,indent=2),encoding='utf-8')
    updated,counts=apply(doc,package)
    if updated!=doc:store.persist(updated,lambda d:Knowledge(faq_document=d))
    print(json.dumps({**counts,'held':len(package['held']),'added_variants':sum(map(len,package['variants'].values())),'source':package['source_summary']},ensure_ascii=False))
