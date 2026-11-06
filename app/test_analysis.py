"""仅供训练工作台的诊断，不生成或发送客户话术。"""
from urllib.parse import urlencode
from .faq import canonical
from .scene_rules import row_eligible, parse_time, CHINA
from datetime import datetime

METHODS = {
    'scene_faq':'标准问法 / 关键词规则', 'faq_exact':'标准问法匹配',
    'semantic_onnx':'语义向量检索', 'llm_intent_selection':'大模型辅助意图选择',
    'source_qa':'资源库问答匹配', 'bounded_intent':'业务规则识别',
    'approved_reply':'已核准话术规则', 'catalog':'跨款推荐规则',
    'exact_net_dimensions':'尺寸计算规则',
    'faq_field':'FAQ 字段匹配', 'scope_filter':'接待范围过滤',
    'dimension_context':'相邻尺寸对话纠错',
}
REASONS = {
    'presales_scope':'当前蚊帐知识仅适用于售前接待及售前业务状态；请切换测试条件，或维护适用于当前状态的新答案。',
    'scene_ineligible':'已识别客户意图，但没有符合当前商品、状态、有效期和启用条件的答案。',
    'scene_ambiguous':'当前条件下有多条冲突答案，需要检查优先级或适用条件。',
    'scene_multi_question':'多个问题的答案条件不一致，需要分别核实。',
    'faq_not_active':'命中知识未启用或不符合当前条件。',
    'product_unconfirmed':'尚未确认商品，无法选择商品专属答案。',
    'product_conflict':'问题涉及不同商品，需要确认咨询对象。',
    'ambiguous_reference':'指代涉及多个商品，尚不能确认咨询对象。',
    'unknown_product_code':'未找到客户提到的商品编号。',
    'insufficient_evidence':'没有找到可可靠回答的有效知识；请检查意图、问法或补充答案。',
    'manual_or_unsupported_request':'问题触发人工核实边界，未自动发送商品答复。',
    'answer_validation_failed':'回答未通过证据校验，未发送给客户。',
    'system_failure':'系统处理失败，请查看错误类型或重试；这不等同于知识缺失。',
    'height_variant_missing':'已识别高度咨询，但核准答案缺少这个高度规格；未套用其他规格参数。',
    'dimension_repair_exhausted':'客户已连续纠正尺寸答复，请人工核对原问题、意图与答案，不再重复普通招呼。',
    'affirmation_uncertain':'这句带有疑问，未当作肯定回应，请核实上一轮答复。',
}


def analyze(kb, message, debug, status):
    retrieval = debug.get('retrieval') or {}
    by_id = {r['id']:r for r in kb.faq.records}
    scene_map = {s['id']:s for s in kb.faq.scenes}
    hit_ids = [h.get('id') for h in retrieval.get('hits', [])]
    rows = [by_id[i] for i in hit_ids if i in by_id]
    scene_ids = list(dict.fromkeys([*debug.get('scene_selection', {}).get('scene_ids', []),
                                  *[r['scene_id'] for r in rows]]))
    if debug.get('scene_selection', {}).get('scene_id'):
        scene_ids.append(debug['scene_selection']['scene_id'])
    # 只把真实规则命中或实际选中答案关联为已识别意图，不能把最高相似候选当结论。
    scenes = [scene_map[i] for i in dict.fromkeys(scene_ids) if i in scene_map]
    if not scenes:
        queries = {canonical(message)}
        product = kb.products.get(debug.get('current_product_id'))
        if product:
            text = message
            for token in sorted([product['id'],product['name'],*product['aliases']],key=len,reverse=True):
                text=text.replace(token,'')
            queries.add(canonical(text))
        scenes = [s for s in kb.faq.scenes if queries.intersection(canonical(q) for q in s['question_variants'])]
    if debug.get('reason')=='affirmation_uncertain':scenes=[]
    method = retrieval.get('method') or ('scene_faq' if debug.get('scene_selection',{}).get('scene_ids') else None)
    reason = debug.get('reason')
    failure = debug.get('error') or (debug.get('intent_model') or {}).get('error')
    if status == 'error':
        outcome = REASONS['system_failure']
    elif status == 'duplicate':
        outcome = '已命中有效答案；同一商品的同一客户意图已回复，本次未重复发送。'
    elif status == 'answered':
        outcome = '已选择有效答案并发送。'
    else:
        outcome = REASONS.get(reason) or '本条未发送客户答复，请检查知识和触发条件。'
    candidates = []
    for item in (debug.get('semantic') or {}).get('candidates', []):
        row = by_id.get(item.get('id'))
        if row:
            scene = scene_map.get(row['scene_id'], {})
            candidates.append({'id':row['scene_id'],'name':scene.get('name', row['scene_name']),
                               'score':item.get('score'),'matched_question':item.get('matched_question')})
    queries=canonical_queries(message,kb,debug)
    matched = next((q for s in scenes for q in s['question_variants'] if canonical(q) in queries),None)
    if method == 'semantic_onnx':
        matched = next((c.get('matched_question') for c in candidates if c['id'] in {s['id'] for s in scenes}),None)
    # 候选多个不代表已识别出多个独立问题，界面必须保留不确定性。
    state = 'matched' if len(scenes)==1 else 'ambiguous' if scenes else 'unrecognized'
    scene_id = scenes[0]['id'] if len(scenes)==1 else None
    params = {'scene':scene_id} if scene_id else {}
    if rows and len(scenes)==1:params['answer']=rows[0]['id']
    result = {'status':state,'intents':[{'id':s['id'],'name':s['name']} for s in scenes],
            'method':METHODS.get(method, '业务边界规则' if reason=='manual_or_unsupported_request'
                                 else '业务字段检索' if retrieval else '未匹配到有效知识'),
            'semantic_status':(debug.get('semantic') or {}).get('status'),
            'intent_model_status':(debug.get('intent_model') or {}).get('status'),
            'matched_question':matched,'outcome':outcome,'reason_code':reason,'error_type':failure,
            'candidates':candidates[:5], 'dedicated_classifier':False,
            'model_used':debug.get('model')=='api_intent_success' or bool(debug.get('intent_model')),
            'knowledge_url':'/knowledge'+('?' + urlencode(params) if params else '')}
    result['assistant'] = assistant_summary(kb, debug, status, scenes, candidates, failure)
    return result


def assistant_summary(kb, debug, status, scenes, candidates, failure):
    """仅依据本次检索与配置给训练建议；不生成新的商品事实或自动创建知识。"""
    reason = debug.get('reason')
    semantic = debug.get('semantic') or {}
    title, badge, tone, summary, advice, action = (
        '意图待确认', '需核实', 'warning', '没有找到可靠匹配，暂不能判断是缺少问法还是答案。',
        '先查找已有意图；确实没有时，再新建待完善条目。', 'review')
    if status == 'error':
        title, badge, tone = '系统异常', '请求失败', 'error'
        summary, advice, action = '处理失败，不能据此判断知识缺失。', '查看依据中的错误类型，恢复服务后重新测试。', 'retry'
    elif status == 'duplicate':
        title, badge, tone = '已回答过', '重复拦截', 'neutral'
        summary, advice, action = '本条已有有效答案，同类回复未重复发送。', '无需新增知识；独立测试时可先清除记忆。', 'view'
    elif status == 'answered':
        title, badge, tone = '已匹配知识', '已回复', 'success'
        summary, advice, action = '已选中有效答案并回复。', '答复符合预期即可保留；需要调整时修改原答案。', 'answer'
        if any(s['id']=='industry.affirmation' for s in scenes):
            title, summary, advice = '肯定／已了解', '已按互动知识回复。', '可在知识库维护问法、回复和适用接待状态。'
    elif scenes and not any(row['scene_id'] in {s['id'] for s in scenes} for row in kb.faq.records):
        title, badge = '缺少条件答案', '待补充'
        summary, advice, action = '已识别客户意图，该意图下还没有答案。', '补充标准答案并绑定商品与接待状态，确认后启用。', 'answer'
    elif reason in ('scene_ambiguous', 'scene_multi_question'):
        title, badge = '答案存在冲突', '待处理'
        summary, advice, action = '当前条件下无法确定唯一答案。', '检查答案内容、优先级及适用条件。', 'answer'
    elif reason in ('scene_ineligible', 'faq_not_active', 'presales_scope'):
        title, badge = '答案条件不符', '未回复'
        summary, advice, action = '现有答案不适用于本次测试条件，或尚未启用。', '核对商品、接待状态、有效期和启用状态。', 'answer' if scenes else 'review'
    elif reason in ('product_unconfirmed', 'product_conflict', 'ambiguous_reference', 'unknown_product_code', 'invalid_product'):
        title, badge = '需要确认商品', '待确认'
        summary, advice, action = '商品信息不足或存在冲突，无法选择专属答案。', '在左侧确认咨询商品后重新测试。', 'retry'
    elif reason in ('manual_or_unsupported_request', 'human_latched', 'answer_validation_failed', 'dimension_repair_exhausted', 'affirmation_uncertain'):
        title, badge = '需要人工核实', '人工处理'
        summary, advice, action = '问题触发人工边界，暂不自动答复。', '人工确认事实；可复用且边界明确的答案再纳入知识库。', 'review'
        if reason=='dimension_repair_exhausted':
            summary, advice = '客户连续纠正尺寸问题，需要人工核对。', '检查上一轮的长宽或高度意图，避免继续答非所问。'
            action='view'
        if reason=='affirmation_uncertain':
            summary, advice, action = '这句带有疑问，未按肯定回复。', '核实上一轮答复和客户想确认的内容。', 'view'
    elif reason=='height_variant_missing':
        title, badge = '缺少该高度规格', '待补充'
        summary, advice, action = '已有尺寸意图，但没有可核准的该规格答案。', '补充这个高度款的资料，不套用其他规格。', 'answer'
    elif status == 'clarify':
        title, badge, tone = '需要补充信息', '已追问', 'neutral'
        summary, advice, action = '已向客户追问必要信息。', '补充信息后继续测试，无需立即新建知识。', 'view'
    elif scenes:
        title, badge = '已识别意图', '答案待核实'
        summary, advice, action = '已找到客户意图，但没有可靠可用的答复。', '检查该意图的条件答案，确认后补充或修改。', 'answer'
    elif semantic.get('status') == 'guard_rejected':
        title, badge = '触发匹配边界', '待核实'
        summary, advice = '本条触发检索边界，未采用向量候选。', '先检查已有相关意图，确认归属后补充问法。'
    elif semantic.get('status') == 'low_confidence':
        title, badge = '匹配不够确定', '待核实'
        summary, advice = '候选相似度或候选分差不足，未自动采用。', '核实候选意图；同一意图可补充原话，避免重复建库。'
    if status not in ('answered', 'duplicate', 'error') and failure:
        summary += '辅助模型调用也未成功。'
    # 依据展示真实配置，候选仅供核实，不据此声称问题已经识别。
    selected_ids = {s['id'] for s in scenes}
    evidence_ids = selected_ids or {c['id'] for c in candidates}
    conditions = debug.get('conditions') or {}
    pid, reception, stage = debug.get('current_product_id'), conditions.get('reception', 'presales'), conditions.get('stage', 'presales')
    evidence = []
    now = datetime.now(CHINA)
    for row in kb.faq.records:
        if row['scene_id'] not in evidence_ids:
            continue
        exclusions = []
        if row.get('status') != 'active': exclusions.append('未启用' if row.get('status') == 'disabled' else '待核实 / 人工处理')
        if row.get('scope') == 'product' and pid not in row.get('product_ids', []): exclusions.append('商品不符')
        c = row.get('conditions', {})
        if c.get('reception', 'all') not in ('all', reception): exclusions.append('接待类型不符')
        if c.get('stages') and stage not in c['stages']: exclusions.append('业务状态不符')
        start, end = parse_time(c.get('valid_from')), parse_time(c.get('valid_until'))
        if (start and now < start) or (end and now > end): exclusions.append('不在有效期')
        evidence.append({'id':row['id'], 'scene_id':row['scene_id'], 'scene_name':row['scene_name'],
                         'text':row.get('standard_answer', ''), 'sources':row.get('sources', []),
                         'eligible':row_eligible(row, pid, reception, stage), 'exclusions':exclusions,
                         'candidate_only':not bool(selected_ids)})
    # 优先显示本次商品的可用资料，仍保留被条件排除的记录供排查。
    hit_ids = {h.get('id') for h in (debug.get('retrieval') or {}).get('hits', [])}
    candidate_rank = {c['id']:index for index,c in reversed(list(enumerate(candidates)))}
    evidence.sort(key=lambda e:(e['id'] not in hit_ids, not e['eligible'], candidate_rank.get(e['scene_id'],0), e['id']))
    distinct, seen = [], set()
    for item in evidence:
        signature=(item['scene_id'], item['text'], tuple(item['exclusions']))
        if signature not in seen:
            seen.add(signature)
            distinct.append(item)
    return {'title':title, 'badge':badge, 'tone':tone, 'summary':summary, 'advice':advice,
            'action':action, 'evidence':distinct[:6], 'evidence_count':len(distinct)}


def canonical_queries(message,kb,debug):
    texts={canonical(message)}
    product=kb.products.get(debug.get('current_product_id'))
    if product:
        for token in sorted([product['id'],product['name'],*product['aliases']],key=len,reverse=True):
            message=message.replace(token,'')
        texts.add(canonical(message))
    return texts
