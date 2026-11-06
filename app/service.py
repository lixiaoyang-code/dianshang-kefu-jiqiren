import asyncio
import json
import logging
import re
import time
import uuid
import sqlite3
from datetime import datetime
from dataclasses import dataclass, field, asdict
from logging.handlers import RotatingFileHandler
from .config import ROOT, Settings
from .knowledge import Knowledge, FIELDS, STORE_FIELDS
from .model import Model
from .replies import compact_reply, fit_question, WAITING_REPLY, WAITING_DELAY_SECONDS, FLEX_RECOMMENDATION
from .intents import normalize_question, quick_reply, affirmation_variants, affirmation_state, strip_affirmation_prefix
from .semantic import get_semantic
from .approved_replies import approved_reply, catalog_reply
from .intent_candidates import candidates_for
from .scene_rules import row_eligible, requires_scene_selection
from .test_analysis import analyze
from .faq import canonical
from . import dimensions
from .common_intents import select as select_common
from .statistics import StatisticsStore
from .scene_rules import CHINA
from .catalog import answer as catalog_answer

@dataclass
class Session:
    session_id: str
    current_product_id: str | None = None
    product_confirmed: bool = False
    recent_product_ids: list = field(default_factory=list)
    history: list = field(default_factory=list)
    needs_human: bool = False
    pending_question: str | None = None
    waiting: dict = field(default_factory=dict)
    pending_topic: str | None = None
    last_waiting_at: float = 0
    answered_keys: list = field(default_factory=list)
    reception_type: str = 'presales'
    business_stage: str = 'presales'
    last_dimension: dict | None = None
    product_links: list = field(default_factory=list)

class Service:
    def __init__(self, knowledge=None, model=None, log_dir=None):
        self.kb = knowledge or Knowledge()
        self.model = model or Model(Settings())
        self.semantic,self.semantic_status=get_semantic(self.kb)
        self.sessions, self.locks = {}, {}
        folder = log_dir or ROOT / 'logs'
        folder.mkdir(parents=True, exist_ok=True)
        self.logger = logging.getLogger('presales.' + uuid.uuid4().hex)
        self.logger.setLevel(logging.INFO)
        self.logger.propagate = False
        handler = RotatingFileHandler(folder / 'events.jsonl', maxBytes=2_000_000, backupCount=3, encoding='utf-8')
        self.logger.addHandler(handler)
        self.statistics = StatisticsStore(folder)

    def create(self):
        if len(self.sessions) >= 1000:
            raise RuntimeError('session_capacity')
        sid = str(uuid.uuid4())
        self.sessions[sid] = Session(sid)
        self.locks[sid] = asyncio.Lock()
        return self.sessions[sid]

    def scrub(self, value):
        # 原始问题可能包含误粘贴的密钥；日志和调试响应统一脱敏。
        text = json.dumps(value, ensure_ascii=False)
        key = self.model.settings.key
        if key:
            text = text.replace(key, '[REDACTED]')
        text = re.sub(r'(?:sk-|ark-)[A-Za-z0-9_-]+', '[REDACTED]', text)
        return json.loads(text)

    async def chat(self, sid, message, selected=None,reception_type=None,business_stage=None):
        async with self.locks[sid]:
            s=self.sessions[sid]
            if reception_type is not None:s.reception_type=reception_type
            if business_stage is not None:s.business_stage=business_stage
            return await self._chat(sid, message, selected)

    async def _chat(self, sid, message, selected):
        start = time.perf_counter()
        s = self.sessions[sid]
        assist = self.kb.data.get('continuous_assist', False)
        debug = {'request_id': str(uuid.uuid4()), 'question': message, 'identification': {},
                 'retrieval': None, 'model': 'not_called', 'error': None,
                 'conditions':{'reception':s.reception_type,'stage':s.business_stage}}

        def finish(status, answer, reason):
            operator_note = None
            if assist and answer:
                hits=(debug.get('retrieval') or {}).get('hits',[])
                by_id={r['id']:r for r in self.kb.faq.records}
                for hit in hits:
                    row=by_id.get(hit.get('id'))
                    if row is None:continue
                    # 核准话术、尺寸、旧字段等所有路径都必须服从答案适用范围。
                    if not row_eligible(row,s.current_product_id,s.reception_type,s.business_stage):
                        status,answer,reason='suppressed','该答案当前不符合触发条件，请人工查看。','scene_ineligible'
                        break
                    if (debug.get('retrieval') or {}).get('method')=='exact_net_dimensions' and row['id']!='catalog.full_stretch':
                        # 尺寸适配由程序按帐纱参数计算，不能换成普通规格介绍。
                        if not row_eligible(row,s.current_product_id,s.reception_type,s.business_stage):
                            status,answer,reason='suppressed','尺寸答案不符合当前触发条件，请人工查看。','scene_ineligible'
                        continue
                    if (debug.get('retrieval') or {}).get('method')=='scene_faq':
                        # 已按本次原声选定场景，不再用其他共享问法扩大范围。
                        if not row_eligible(row,s.current_product_id,s.reception_type,s.business_stage):
                            status,answer,reason='suppressed','该答案当前不符合触发条件，请人工查看。','scene_ineligible'
                        continue
                    peers=self.kb.faq.related_rows(row)
                    if any(requires_scene_selection(r) for r in peers
                           if r.get('scope')!='product' or s.current_product_id in r.get('product_ids',[])):
                        choice=self.kb.faq.select(peers,s.current_product_id,s.reception_type,s.business_stage)
                        if choice['status']!='matched':
                            status,answer,reason='suppressed','该场景没有符合当前条件的唯一答案，请人工查看。','scene_'+choice['status']
                            debug['scene_selection']={'status':choice['status'],'scene_id':row['scene_id']}
                            break
                        chosen=choice['row']
                        if len(hits)==1:
                            if (debug.get('retrieval') or {}).get('method')!='faq_field' or chosen['id']!=row['id']:
                                answer=chosen['standard_answer']
                            hit.update(self.kb.faq.candidate(chosen))
                        elif chosen['id']!=row['id'] or not row_eligible(row,s.current_product_id,s.reception_type,s.business_stage):
                            status,answer,reason='suppressed','多问题的触发条件需要人工核实。','scene_multi_question'
                            break
                    elif row['status']!='active':
                        status,answer,reason='suppressed','该问答未启用或不符合当前条件，请人工查看。','faq_not_active'
                        break
            if assist and status == 'answered' and answer:
                # 按商品和实际答复去重，同义问法得到相同话术时不再发；
                # 不同高度参数/不同商品的答复仍正常输出。
                primary=debug.get('retrieval', {}).get('hits', [{}])[0].get('id','')
                scope = 'store' if primary.startswith('store.') else primary.split('.')[1] if primary.startswith('product.') else s.current_product_id
                row = by_id.get(primary)
                # 不同意图即便共用话术，也不能相互挡住（例如稳固性与承重）。
                intent_key = row['scene_id'] if row else primary
                key = str(scope) + ':' + intent_key + ':' + re.sub(r'[\s，。！？～~；、]', '', answer)
                if key in s.answered_keys and not debug.get('dimension_plan', {}).get('repair'):
                    status, answer = 'duplicate', ''
                    operator_note = '同类问题已回复，本次不重复发送'
                    debug['duplicate'] = True
                else:
                    s.answered_keys = (s.answered_keys + [key])[-50:]
            if assist and status in ('handoff', 'error'):
                operator_note = answer
                answer = ''
                s.needs_human = False
                s.waiting.clear()
                if s.reception_type=='presales' and s.business_stage=='presales':
                    s.waiting[debug['request_id']] = {'received_at': start, 'sent': False}
                status = 'error' if status == 'error' else 'suppressed'
            elif assist:
                s.needs_human = False
                s.waiting.clear()  # 已有新客户回复，旧等待话术不再发送。
            if assist and status == 'suppressed' and operator_note is None:
                operator_note = answer
                answer = ''
                s.waiting.clear()
                if s.reception_type=='presales' and s.business_stage=='presales' and reason!='presales_scope':
                    s.waiting[debug['request_id']] = {'received_at': start, 'sent': False}
            if status in ('handoff', 'error'):
                s.needs_human = not assist
            s.history.append({'role': 'user', 'content': message})
            if answer:
                s.history.append({'role': 'assistant', 'content': answer})
            s.history = s.history[-20:]
            plan=debug.get('dimension_plan')
            if plan and status in ('answered', 'duplicate'):
                previous=s.last_dimension or {}
                s.last_dimension={**plan,'product_id':s.current_product_id,
                    'reception':s.reception_type,'stage':s.business_stage,
                    'repair_count':previous.get('repair_count',0)+1 if plan.get('repair') else 0}
            else:
                s.last_dimension=None
            debug.update(current_product_id=s.current_product_id, reason=reason,
                         occurred_at=datetime.now(CHINA).isoformat(),
                         elapsed_ms=round((time.perf_counter() - start) * 1000, 2))
            debug['analysis'] = analyze(self.kb, message, debug, status)
            # 分段只是核准答案的展示方式；派生尺寸答复保留实际选中的子段。
            known={r['id']:r for r in self.kb.faq.records}
            source_rows=[known[h['id']] for h in (debug.get('retrieval') or {}).get('hits',[]) if h.get('id') in known]
            reply_parts=[]
            if answer:
                scoped=debug.pop('reply_parts',None)
                if scoped and '\n\n'.join(scoped)==answer:
                    reply_parts=scoped
                elif len(source_rows)==1 and answer==source_rows[0]['standard_answer']:
                    reply_parts=source_rows[0].get('answer_parts') or [answer]
                else:
                    reply_parts=[answer]
                answer='\n\n'.join(reply_parts)
            debug['editable_answer_ids']=[source_rows[0]['id']] if len(source_rows)==1 and answer and (
                answer==source_rows[0]['standard_answer'] or debug.get('dimension_plan')) else []
            images=[]
            product=self.kb.products.get(s.current_product_id)
            if answer:
                for hit in (debug.get('retrieval') or {}).get('hits',[]):
                    for asset in hit.get('images', []):
                        if asset not in images: images.append(asset)
                    owner=product or {}
                    if hit.get('id','').startswith('product.'):
                        owner=self.kb.products.get(hit['id'].split('.')[1],owner)
                    fields=hit.get('fields') or [hit.get('field') or hit.get('id','').split('.')[-1]]
                    for field_name in fields:
                        for asset in owner.get('answer_images',{}).get(field_name,[]):
                            if asset not in images:images.append(asset)
            debug['waiting_delay_ms']=WAITING_DELAY_SECONDS*1000
            result = self.scrub({'status': status, 'answer': answer, 'answer_parts':reply_parts, 'images':images[:2], 'send_to_customer': bool(answer), 'operator_note':operator_note, 'session': asdict(s), 'debug': debug})
            try:
                self.logger.info(json.dumps(result, ensure_ascii=False))
            except OSError:
                result['debug']['logging_error'] = 'log_write_failed'
            try:
                self.statistics.record(result)
            except (OSError, sqlite3.Error):
                result['debug']['statistics_error']='statistics_write_failed'
            return result

        try:
            if s.needs_human and not assist:
                return finish('handoff', '这段咨询已交给人工处理，客服可以查看消息；恢复 AI 后可继续自动回答。', 'human_latched')
            query = normalize_question(message) if assist else message
            if assist:
                ack_variants=affirmation_variants(self.kb)
                if affirmation_state(query,ack_variants)=='uncertain':
                    return finish('handoff','客户对上一轮答复表示疑问，请人工核实；未按肯定回复。','affirmation_uncertain')
                query=strip_affirmation_prefix(query,ack_variants)
            mentions = self.kb.mentions(query)
            debug['identification'] = {'mentions': mentions, 'selected': selected, 'candidates': s.recent_product_ids[:], 'basis': 'unresolved'}
            if selected and selected not in self.kb.products:
                return finish('clarify', '未找到这个商品，请重新选择商品。', 'invalid_product')
            candidate_pid=selected or (mentions[0] if len(mentions)==1 else s.current_product_id)
            previous=s.last_dimension
            if previous and (previous.get('product_id')!=candidate_pid or previous.get('reception')!=s.reception_type
                             or previous.get('stage')!=s.business_stage):previous=None
            dimension_plan=dimensions.request(query,self.kb.products.get(candidate_pid),previous) if assist else None
            if assist and any(code not in self.kb.products for code in re.findall(r'(?<![A-Za-z0-9])8\d{2}(?![A-Za-z0-9]|厘米|毫米|克)',message)):
                return finish('clarify','没有找到该商品编号，请从商品列表确认。','unknown_product_code')
            common = select_common(self.kb, query, candidate_pid, s.reception_type, s.business_stage) if assist else None
            if common:
                if selected or len(mentions)==1:
                    s.current_product_id, s.product_confirmed = candidate_pid, True
                debug['identification']['basis']='common_reception'
                debug['scene_selection']={k:v for k,v in common.items() if k!='row'}
                if common['status']=='matched':
                    row=common['row']
                    debug['retrieval']={'method':'scene_faq','status':'matched','hits':[self.kb.faq.candidate(row)]}
                    return finish('answered',row['standard_answer'],'common_reception')
                return finish('handoff','通用接待答案未启用或不符合当前条件，请人工核实。','scene_'+common['status'])
            if assist and self.kb.products.get(candidate_pid,{}).get('routing')=='catalog':
                if len(mentions)>1 or (selected and mentions and mentions!=[selected]):
                    return finish('clarify','涉及不同商品，请确认本次咨询的商品后再提问。','product_conflict')
                s.current_product_id,s.product_confirmed=candidate_pid,True
                row,info,reason=await catalog_answer(self,strip_affirmation_prefix(message,ack_variants),candidate_pid,s.reception_type,s.business_stage,s.history)
                debug.update(info);debug['identification']['basis']='catalog_product'
                if row:return finish('clarify' if row.get('boundaries',{}).get('requires_clarification') else 'answered',row['standard_answer'],reason)
                return finish('handoff','这款商品的对应资料待核实，请补充或审核该商品知识后再回复。',reason)
            if assist and len(mentions)<=1 and (not selected or not mentions or mentions==[selected]):
                candidate_pid=selected or (mentions[0] if mentions else s.current_product_id)
                scene_query=query
                original_query=message
                product=self.kb.products.get(candidate_pid)
                if product:
                    for token in sorted([product['id'],product['name'],*product['aliases']],key=len,reverse=True):
                        scene_query=scene_query.replace(token,'')
                        original_query=original_query.replace(token,'')
                choice=self.kb.faq.resolve(scene_query,candidate_pid,s.reception_type,s.business_stage,aliases=[original_query])
                explicit_codes=re.findall(r'(?<![A-Za-z0-9])8\d{2}(?![A-Za-z0-9]|厘米|毫米|克)',message)
                if any(code not in self.kb.products for code in explicit_codes):
                    choice={'status':'no_match','managed':False,'row':None}
                standard_question = any(canonical(t)==canonical(scene['name'])
                    for t in (scene_query,original_query) for scene in self.kb.faq.scenes
                    if scene['id'] in choice.get('scene_ids',[]))
                scoped_rows=[r for r in self.kb.faq.records if r['scene_id'] in choice.get('scene_ids',[])
                    and (r.get('scope')!='product' or candidate_pid in r.get('product_ids',[]))]
                explicit_conditions=any(requires_scene_selection(r) for r in scoped_rows)
                dimension_scope=bool(dimension_plan and set(choice.get('scene_ids',[])).issubset(dimensions.DIMENSION_SCENES)
                                     and (not choice.get('row') or choice['row'].get('scene_type','industry')=='industry'))
                if not dimension_scope and (explicit_conditions or (standard_question and choice['status']=='matched'
                        and not self.kb.match_qa(query,candidate_pid))):
                    if selected or mentions:
                        s.current_product_id,s.product_confirmed=candidate_pid,True
                    debug['identification']['basis']='scene_conditions'
                    debug['scene_selection']={k:v for k,v in choice.items() if k!='row'}
                    if choice['status']=='matched':
                        chosen=choice['row']
                        debug['retrieval']={'method':'scene_faq','status':'matched','hits':[self.kb.faq.candidate(chosen)]}
                        return finish('answered',chosen['standard_answer'],'scene_conditions_matched')
                    return finish('handoff','该场景没有符合当前条件的唯一答案，请人工查看。','scene_'+choice['status'])
            if assist and (s.reception_type!='presales' or s.business_stage!='presales'):
                # 未来显式配置的售后 FAQ 已在上面按意图/条件匹配；其余旧规则不能绕回售前话术。
                if selected or len(mentions)==1:
                    s.current_product_id=selected or mentions[0]
                    s.product_confirmed=True
                debug['identification']['basis']='outside_presales_scope'
                debug['retrieval']={'status':'out_of_scope','method':'scope_filter','hits':[]}
                return finish('suppressed','当前蚊帐知识仅适用于售前接待及售前业务状态；本条未发送客户答复。','presales_scope')
            if assist:
                catalog=catalog_reply(query,self.kb.data,candidate_pid)
                if catalog:
                    if selected:
                        s.current_product_id,s.product_confirmed=selected,True
                    status,reply,source=catalog
                    debug['identification']['basis']='catalog_recommendation_keep_binding'
                    owner=self.kb.products.get(source.split('.')[1],{}) if source.startswith('product.') else self.kb.data['store']
                    debug['retrieval']={'status':'matched','method':'catalog','hits':[{'id':source,'text':reply,'sources':owner.get('sources',{}).get(source.split('.')[-1],[])}]}
                    return finish(status,reply,'catalog_recommendation')
            if assist and len(mentions)>1 and not selected:
                comparison=self.kb.match_qa(query,s.current_product_id)
                if comparison and comparison['status']=='active' and not comparison['fields']:
                    debug['retrieval']={'status':'matched','method':'source_qa','hits':[{'id':comparison['id'],'source':comparison['source'],'text':comparison['answer']}]}
                    return finish('answered',comparison['answer'],'approved_comparison_qa')
            if len(mentions) > 1 or (selected and mentions and mentions != [selected]):
                s.pending_question = None
                return finish('clarify', '这条消息涉及不同商品，请明确本次要咨询哪一款，并重新发送问题。', 'product_conflict')
            # 未知明确编号不能退回旧商品。
            codes = re.findall(r'(?<![A-Za-z0-9])(?:P\d+|[A-Z]{2}-\d+)(?![A-Za-z0-9])', message, re.I)
            if any(pid.isdigit() for pid in self.kb.products):
                codes += re.findall(r'(?<![A-Za-z0-9])8\d{2}(?![A-Za-z0-9]|厘米|毫米|克)', message)
            valid = {v.lower() for p in self.kb.products.values() for v in (p['id'], p['model'])}
            if any(code.lower() not in valid for code in codes):
                return finish('clarify', '没有找到该商品编号，请从商品列表确认。', 'unknown_product_code')
            explicit = selected or (mentions[0] if mentions else None)
            if explicit:
                s.current_product_id, s.product_confirmed = explicit, True
                debug['identification']['basis'] = 'customer_selected' if selected else 'explicit_mention'
            elif any(w in message for w in ('那个', '那款', '刚才那个', '另一款', '新发的')):
                if len(set(s.recent_product_ids + ([s.current_product_id] if s.current_product_id else []))) > 1:
                    s.pending_question = message
                    return finish('clarify', '您说的是哪一款？请在左侧确认商品，我再按这款资料回答。', 'ambiguous_reference')
            if not explicit and s.product_confirmed:
                debug['identification']['basis'] = 'confirmed_session'
            if dimension_plan:
                if not s.product_confirmed:
                    return finish('clarify','请先在左侧确认咨询商品，我再按这款资料回答。','product_unconfirmed')
                debug['dimension_plan']=dimension_plan
                if dimension_plan.get('repair') and previous and previous.get('repair_count',0)>=1:
                    debug['scene_selection']={'status':'repair_required','scene_id':dimensions.SCENES[dimension_plan['kind']]}
                    debug['retrieval']={'method':'dimension_context','status':'repair_required','hits':[]}
                    return finish('handoff','客户连续纠正尺寸问题，请人工核对当前答复和意图归属。','dimension_repair_exhausted')
                choice=dimensions.select(self.kb,dimension_plan,s.current_product_id,s.reception_type,s.business_stage)
                debug['scene_selection']={'status':choice['status'],'scene_id':choice['scene_id']}
                if choice['status']!='matched':
                    return finish('handoff','对应尺寸或结构答案未启用、不符合条件，或缺少该高度款资料，请人工核实。',
                                  choice.get('reason') or 'scene_'+choice['status'])
                chosen=choice['row']
                debug['retrieval']={'method':'scene_faq','status':'matched','hits':[self.kb.faq.candidate(chosen)]}
                debug['reply_parts']=choice['parts']
                return finish('answered',choice['answer'],'dimension_context_repair' if dimension_plan.get('repair') else 'dimension_faq')
            if assist:
                approved=approved_reply(query,self.kb.products.get(s.current_product_id),self.kb.data)
                if approved:
                    status,reply,source=approved
                    p=self.kb.products.get(s.current_product_id,{})
                    debug['retrieval']={'status':'matched','method':'approved_reply','hits':[{'id':source,'text':reply,'sources':p.get('sources',{}).get(source.split('.')[-1],[])}]}
                    return finish(status,reply,'latest_user_approved_reply')
                qa=self.kb.match_qa(query,s.current_product_id)
                if qa:
                    debug['retrieval']={'status':'matched' if qa['status']=='active' else 'insufficient',
                        'method':'source_qa','hits':[{'id':qa['id'],'source':qa['source'],
                        'fields':qa['fields'],'text':qa['answer'], 'sources':{f:self.kb.products[s.current_product_id]['sources'].get(f,[]) for f in qa['fields']}}]}
                    return finish('answered' if qa['status']=='active' else 'suppressed',qa['answer'] or qa['reason'],'source_qa_'+qa['status'])
                faq = self.kb.faq.match(query, s.current_product_id,s.reception_type,s.business_stage)
                if faq:
                    hit = self.kb.faq.candidate(faq)
                    debug['retrieval'] = {'status':'matched','method':'faq_exact','hits':[hit]}
                    return finish('answered', faq['standard_answer'], 'approved_faq_match')
                quick=quick_reply(query,self.kb.products.get(s.current_product_id),self.kb.products,self.kb.data['store']['facts'],s)
                if quick:
                    status,reply,source=quick
                    debug['retrieval']={'status':'matched' if status!='suppressed' else 'insufficient','hits':[{'id':source}],'method':'bounded_intent'}
                    return finish(status,reply,'presales_intent')
            if assist and s.product_confirmed:
                product = self.kb.products[s.current_product_id]
                fit = fit_question(message, product)
                if fit:
                    evidence_product=self.kb.products['802'] if fit['text']==FLEX_RECOMMENDATION else product
                    field='telescoping' if fit['text']==FLEX_RECOMMENDATION else 'specifications'
                    source='catalog.full_stretch' if fit['text']==FLEX_RECOMMENDATION else f'product.{evidence_product["id"]}.{field}'
                    debug['retrieval'] = {'status':'matched','hits':[{'id':source,'text':evidence_product['facts'][field], 'sources':evidence_product['sources'][field]}], 'method':'exact_net_dimensions'}
                    return finish(fit['status'], fit['text'], 'net_dimension_match')
            if assist and any(w in message for w in ('今天发', '今天可以发', '今天能发', '加急', '急着用')):
                debug['retrieval']={'status':'matched','hits':[{'id':'store.expedite','text':self.kb.data['store']['facts']['expedite']}]}
                return finish('answered',self.kb.data['store']['facts']['expedite'],'expedite_request')
            if assist and any(w in message for w in ('京东物流','物流','发货','发出','多久到','送达','到货')) and not any(w in message for w in ('订单','查询','单号','保证','一定','必须')):
                rules=self.kb.data['store']['facts']
                negative=any(w in message for w in ('没有京东','没显示','不是京东','非京东'))
                field='delivery_summary'
                s.pending_topic = None
                debug['retrieval']={'status':'matched','hits':[{'id':f'store.{field}','text':rules[field]}]}
                return finish('answered',rules[field],'delivery_policy')
            if any(w in message for w in ('人工', '投诉', '退款', '订单', '物流', '库存', '优惠', '折扣', '保证', '承诺', '绝对', '一定', '百分百', '防水', '保温多久', '保修', '最低价')):
                return finish('handoff', '这项需求需要人工核实，我已标记人工接管，暂不作额外承诺。', 'manual_or_unsupported_request')
            question = query
            if explicit and s.pending_question:
                if not any(w in message for words in FIELDS.values() for w in words):
                    question = s.pending_question
                s.pending_question = None
            fields = [f for f, words in FIELDS.items() if any(w in question.lower() for w in words)]
            needs_product = any(f not in STORE_FIELDS for f in fields)
            if needs_product and not s.product_confirmed:
                s.pending_question = question
                return finish('clarify', '请先确认您咨询的商品。客服发送的卡片仅作候选，我不会自动认定是哪款。', 'product_unconfirmed')
            retrieval = self.kb.retrieve(question, s.current_product_id)
            debug['retrieval'] = retrieval
            if retrieval['status'] != 'matched':
                if assist and self.semantic and not retrieval.get('blocked_topics'):
                    doc,semantic_debug=await asyncio.to_thread(self.semantic.search,question,s.current_product_id,s.reception_type,s.business_stage)
                    debug['semantic']=semantic_debug
                    if doc:
                        debug['retrieval']={'method':'semantic_onnx','status':'matched','hits':[{'id':doc['id'],'text':doc['answer'],'sources':doc['sources'],'images':doc.get('images',[])}], 'candidates':semantic_debug['candidates']}
                        return finish('answered',doc['answer'],'semantic_evidence_match')
                elif assist:
                    debug['semantic']={'status':self.semantic_status}
                if assist and not self.model.settings.mock and self.model.settings.intent_enabled:
                    candidates=candidates_for(self.kb,question,s.current_product_id,s.reception_type,s.business_stage)
                    if candidates:
                        try:
                            answer_id,model_status=await self.model.understand(question,s.history,candidates)
                            debug['intent_model']={'status':model_status}
                            if answer_id:
                                chosen=next(c for c in candidates if c['id']==answer_id)
                                debug['retrieval']={'status':'matched','method':'llm_intent_selection','hits':[chosen]}
                                debug['model']='api_intent_success'
                                return finish('answered',chosen['answer'],'model_understood_approved_reply')
                        except Exception as exc:
                            debug['intent_model']={'status':'failed','error':type(exc).__name__}
                return finish('handoff', '现有资料不足以完整回答这个问题，我已标记人工核实，避免给您不准确的信息。', 'insufficient_evidence')
            if assist:
                verified=self.kb.faq.from_evidence(retrieval['hits'],s.current_product_id,
                                                    s.reception_type,s.business_stage)
                if verified:
                    if verified['status']!='matched':
                        debug['scene_selection']={k:v for k,v in verified.items() if k!='row'}
                        return finish('handoff','现有答案不符合条件或存在冲突，请在知识库核实。',
                                      'scene_'+verified['status'])
                    rows=verified['rows']
                    original_hits={hit['id']:hit for hit in retrieval['hits']}
                    debug['retrieval']={'status':'matched','method':'faq_field',
                                        'hits':[{**original_hits.get(row['id'],{}),
                                                 **self.kb.faq.candidate(row),
                                                 'text':row['standard_answer']} for row in rows]}
                    answer='；'.join(row['standard_answer'] for row in rows)
                    verified_hits=debug['retrieval']['hits']
                    if all('field' in h for h in verified_hits) and (
                            re.search(r'(90|110|120)\s*(?:cm|厘米)?\s*(?:高|高度)',question)
                            or {'roof','coating'}.issubset({h['field'] for h in verified_hits})):
                        answer=compact_reply(question,verified_hits,self.kb.products.get(s.current_product_id))
                    return finish('answered',answer,'approved_faq_fields')
            debug['model'] = 'calling'
            proposal, mode = await self.model.select(question, retrieval['hits'])
            debug['model'] = mode + '_success'
            expected = [h['id'] for h in retrieval['hits']]
            if not isinstance(proposal, dict) or proposal.get('action') != 'answer' or proposal.get('evidence_ids') != expected:
                return finish('handoff', '回答未通过资料校验，已转人工核实。', 'answer_validation_failed')
            # 模型文字不直接发送；事实由可信条目渲染，避免引用正确但内容编造。
            answer = '；'.join(h['text'].rstrip('。') for h in retrieval['hits']) + '。'
            if assist:
                answer = compact_reply(question,retrieval['hits'],self.kb.products.get(s.current_product_id))
            elif needs_product:
                answer = self.kb.products[s.current_product_id]['name'] + '：' + answer
            return finish('answered', answer, 'evidence_verified')
        except Exception as exc:
            debug['error'] = type(exc).__name__  # 不记录异常正文，可能含 URL、请求头或密钥。
            if debug['model'] == 'calling':
                debug['model'] = 'failed'
            return finish('error', '系统暂时无法完成回答，已标记人工接管，请客服及时处理这条咨询。', 'system_failure')

    async def waiting_reply(self, sid, request_id):
        async with self.locks[sid]:
            s=self.sessions[sid]
            item=s.waiting.get(request_id)
            if not item or item['sent'] or time.perf_counter()-item['received_at']<WAITING_DELAY_SECONDS:
                return {'send_to_customer':False,'answer':''}
            if s.last_waiting_at and time.perf_counter()-s.last_waiting_at<120:
                item['sent']=True
                return {'send_to_customer':False,'answer':''}
            item['sent']=True
            s.last_waiting_at=time.perf_counter()
            s.history.append({'role':'assistant','content':WAITING_REPLY})
            s.history=s.history[-20:]
            self.logger.info(json.dumps({'event':'waiting_reply','session_id':sid,'request_id':request_id,'answer':WAITING_REPLY},ensure_ascii=False))
            return {'send_to_customer':True,'answer':WAITING_REPLY}
