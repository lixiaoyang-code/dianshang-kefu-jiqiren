from .product_labels import visible_products
"""本地 FAQ 管理：校验、版本冲突保护、备份和原子保存。"""
import copy
import hashlib
import json
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import FileResponse, RedirectResponse
from pydantic import BaseModel, Field
from .config import ROOT
from .knowledge import Knowledge
from .semantic import get_semantic
from .scene_rules import normalize_document, SCENE_TYPES, STAGES, parse_time
from .frontend import frontend_page
from .draft_coverage import covered_drafts

router = APIRouter()
WRITE_LOCK = threading.Lock()


class SaveFAQ(BaseModel):
    revision: str
    record: dict

class SaveScene(BaseModel):
    revision: str
    scene: dict


class DeleteKnowledge(BaseModel):
    revision: str
    id: str = Field(min_length=1, max_length=200)
    confirmed: bool = False


class CleanupDrafts(BaseModel):
    revision: str
    scene_id: str = Field(min_length=1,max_length=200)
    ids: list[str] = Field(min_length=1,max_length=200)
    confirmed: bool = False


class FAQStore:
    def __init__(self, path=None):
        self.path = path or ROOT/'data/faq.json'
        self.timings = {}

    def read(self):
        raw = self.path.read_bytes()
        return normalize_document(json.loads(raw)), hashlib.sha256(raw).hexdigest()

    def persist(self, doc, prepare):
        start=time.perf_counter()
        prepared=prepare(doc)
        self.timings['prepare']=time.perf_counter()-start
        start=time.perf_counter()
        backups=self.path.parent/'backups';backups.mkdir(exist_ok=True)
        (backups/f'faq-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.json').write_bytes(self.path.read_bytes())
        raw=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        temp=self.path.with_name('.faq-'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_bytes(raw)
            os.replace(temp,self.path)
        finally:temp.unlink(missing_ok=True)
        revision=hashlib.sha256(raw).hexdigest()
        self.timings['write']=time.perf_counter()-start
        return revision,prepared

    def save_scene(self,payload,prepare):
        with WRITE_LOCK:
            doc,revision=self.read()
            if payload.revision!=revision:raise HTTPException(409,'资料已更新，请刷新后保存。')
            value=payload.scene
            name=value.get('name','')
            variants=value.get('question_variants',[])
            if not isinstance(name,str) or not name.strip() or len(name)>200:
                raise HTTPException(422,'请填写场景名称，最多200字。')
            if value.get('type') not in SCENE_TYPES:raise HTTPException(422,'无效的场景分类。')
            if not isinstance(variants,list) or not variants or len(variants)>100 or not all(isinstance(v,str) and v.strip() and len(v)<=2000 for v in variants):
                raise HTTPException(422,'场景至少需要一个问法，最多100个。')
            previous=next((s for s in doc['scenes'] if s['id']==value.get('id')),None)
            if previous and previous.get('deleted_at'):raise HTTPException(409,'该意图已删除，请刷新列表。')
            scene={'id':previous['id'] if previous else 'scene.'+uuid.uuid4().hex,
                   'name':name.strip(),'type':value['type'],'category':value.get('category') or '商品咨询',
                   'question_variants':list(dict.fromkeys([name.strip(),*(v.strip() for v in variants)])), 'configured':True}
            description=value.get('description', (previous or {}).get('description',''))
            if not isinstance(description,str) or len(description)>2000:
                raise HTTPException(422,'意图描述最多2000字。')
            scene['description']=description.strip()
            if len(scene['question_variants'])>100:
                raise HTTPException(422,'标准问题和拓展问法合计最多100个。')
            doc['scenes']=[s for s in doc['scenes'] if s['id']!=scene['id']]+[scene]
            for row in doc['records']:
                if row['scene_id']==scene['id']:
                    row.update(scene_name=scene['name'],scene_type=scene['type'],
                               question_variants=scene['question_variants'],configured_scene=True)
            revision,prepared=self.persist(doc,prepare)
            return scene,revision,prepared

    def save(self, payload, product_ids, prepare):
        start=time.perf_counter()
        with WRITE_LOCK:
            self.timings['lock']=time.perf_counter()-start
            start=time.perf_counter()
            doc, revision = self.read()
            self.timings['read']=time.perf_counter()-start
            if payload.revision != revision:
                raise HTTPException(409, '资料已被其他页面更新，请刷新后再保存。')
            row = copy.deepcopy(payload.record)
            previous = next((r for r in doc['records'] if r['id']==row.get('id')), None)
            if previous and previous.get('deleted_at'):raise HTTPException(409,'该答案已删除，请刷新列表。')
            if previous and previous.get('canonical_answer_id'):
                raise HTTPException(422,'这是来源引用，请编辑对应的商品主答案。')
            if previous:
                # 来源与旧字段 ID 保留；商品和状态条件可在页面维护。
                row = {**previous, **{k:row[k] for k in ('intent','question_variants',
                    'standard_answer','answer_parts','category','status','images','scope','product_ids','answer_product_id',
                    'scene_id','conditions','keywords','keyword_mode','priority') if k in row}}
            else:
                row.update(id='faq.'+uuid.uuid4().hex, origin='custom', fields=[], sources=[],
                    boundaries={'unsupported':'operator_only_no_customer_reply', 'no_extra_promises':True})
                row.setdefault('images', [])
                row.setdefault('answer_product_id', None)
            scene=next((s for s in doc['scenes'] if s['id']==row.get('scene_id')),None)
            if 'scene_id' in payload.record and not scene:raise HTTPException(422,'场景不存在，请先保存场景。')
            if scene:
                row.setdefault('intent',scene['name'])
                row.setdefault('category',scene['category'])
                row.setdefault('question_variants',scene['question_variants'])
                row.update(scene_type=scene['type'],scene_name=scene['name'])
            row['configured_scene']=True
            conditions=row.get('conditions',{})
            if not isinstance(conditions,dict):raise HTTPException(422,'触发条件格式不正确。')
            conditions={'reception':'all','stages':[],'valid_from':None,'valid_until':None,**conditions}
            if conditions['reception'] not in ('all','presales','aftersales') or not isinstance(conditions['stages'],list) or any(s not in STAGES for s in conditions['stages']):
                raise HTTPException(422,'接待类型或业务状态不正确。')
            try:
                start,end=parse_time(conditions['valid_from']),parse_time(conditions['valid_until'])
                if start and end and start>end:raise ValueError()
            except (ValueError,TypeError,AttributeError):raise HTTPException(422,'有效时间格式不正确，结束不能早于开始。')
            row['conditions']=conditions
            keywords=row.get('keywords',[])
            if not isinstance(keywords,list) or len(keywords)>100 or not all(isinstance(k,str) and k.strip() and len(k)<=100 for k in keywords):
                raise HTTPException(422,'关键词最多100个，每个最多100字。')
            row['keywords']=list(dict.fromkeys(k.strip() for k in keywords))
            row.setdefault('keyword_mode','any');row.setdefault('priority',0)
            if row['keyword_mode'] not in ('any','all') or type(row['priority']) is not int or not 0<=row['priority']<=1000:
                raise HTTPException(422,'关键词模式或优先级不正确。')
            for key in ('intent','category','standard_answer'):
                if not isinstance(row.get(key),str):
                    raise HTTPException(422,'场景名称、分类和答案必须是文字。')
            # 一条回复内的换行原样保留；分条发送只由显式的 answer_parts 配置决定。
            if 'answer_parts' in payload.record:
                parts=payload.record['answer_parts']
                if (not isinstance(parts,list) or len(parts)>8 or
                    not all(isinstance(part,str) and part.strip() and len(part)<=4000 for part in parts)):
                    raise HTTPException(422,'回复最多分8条，每条填写1至4000字。')
                parts=[part.strip() for part in parts]
                if parts and row['standard_answer'].strip()!='\n\n'.join(parts):
                    raise HTTPException(422,'标准答案与分条回复不一致，请刷新后重试。')
                if parts:row['standard_answer']='\n\n'.join(parts)
                row['answer_parts']=parts or ([row['standard_answer']] if row['standard_answer'].strip() else [])
            elif not previous or row['standard_answer']!=previous.get('standard_answer'):
                # 兼容旧版单文本编辑器，不能保留已过期的分段答案。
                row['answer_parts']=[row['standard_answer']] if row['standard_answer'].strip() else []
            row['intent'] = row['intent'].strip()
            if not row['intent'] or len(row['intent'])>200 or len(row['standard_answer'])>12000:
                raise HTTPException(422,'请填写场景名称，答案不能超过12000字。')
            variants = row.get('question_variants')
            if not isinstance(variants,list) or not all(isinstance(v,str) for v in variants):
                raise HTTPException(422,'问法格式不正确。')
            row['question_variants'] = list(dict.fromkeys(v.strip() for v in variants if v.strip()))
            if not row['question_variants'] or len(variants)>100 or any(len(v)>2000 for v in variants):
                raise HTTPException(422,'至少填写一个问法，最多100个问法。')
            if row.get('status') not in ('active','needs_review','manual_policy','disabled'):
                raise HTTPException(422,'无效的启用状态。')
            if row['status']=='active' and not row['standard_answer'].strip():
                raise HTTPException(422,'启用的问答必须填写标准答案。')
            if row.get('scope') not in ('product','store','catalog'):
                raise HTTPException(422,'请选择商品专属、店铺通用或跨款推荐。')
            owners = row.get('product_ids', [])
            if not isinstance(owners,list) or any(p not in product_ids for p in owners):
                raise HTTPException(422,'商品范围不正确。')
            if row['scope']=='product' and not owners:
                raise HTTPException(422,'商品专属问答至少选择一款商品。')
            if row.get('answer_product_id') not in [None,*product_ids]:
                raise HTTPException(422,'推荐商品不正确。')
            if row['scope']=='product' and row.get('answer_product_id') is None:
                row['answer_product_id'] = owners[0]
            images = row.get('images', [])
            if not isinstance(images,list) or len(images)>12:
                raise HTTPException(422,'图片格式不正确，最多12张。')
            for asset in images:
                url = asset.get('url','') if isinstance(asset,dict) else ''
                if not url.startswith('/static/images/') or '?' in url or '#' in url:
                    raise HTTPException(422,'只能关联本地图片库中的图片。')
                target=(ROOT/url.lstrip('/')).resolve()
                if not target.is_relative_to((ROOT/'static/images').resolve()) or not target.is_file():
                    raise HTTPException(422,'关联图片不存在。')
            row['updated_at']=datetime.now(timezone.utc).isoformat()
            if previous:
                doc['records']=[row if r['id']==row['id'] else r for r in doc['records']]
            else: doc['records'].append(row)
            revision,prepared=self.persist(doc,prepare)
            return row,revision,prepared

    def delete(self,payload,target,prepare):
        with WRITE_LOCK:
            if not payload.confirmed:raise HTTPException(422,'请确认删除后再提交。')
            doc,revision=self.read()
            if payload.revision!=revision:raise HTTPException(409,'资料已更新，请刷新后再删除。')
            collection=doc['scenes'] if target=='scene' else doc['records']
            item=next((r for r in collection if r['id']==payload.id and not r.get('deleted_at')),None)
            if item is None:raise HTTPException(404,'条目不存在或已删除。')
            if target=='answer' and item.get('canonical_answer_id'):
                raise HTTPException(422,'这是来源引用，请删除对应的商品主答案。')
            ids={r['id'] for r in doc['records'] if r['scene_id']==payload.id} if target=='scene' else {payload.id}
            # 一并移除主答案的来源副本，避免旧问答在主答案删除后重新被启用。
            while True:
                related={r['id'] for r in doc['records'] if r.get('canonical_answer_id') in ids}
                if related.issubset(ids):break
                ids.update(related)
            when=datetime.now(timezone.utc).isoformat()
            for row in doc['records']:
                if row['id'] in ids:row.update(status='disabled',deleted_at=when,updated_at=when)
            if target=='scene':item['deleted_at']=when
            revision,prepared=self.persist(doc,prepare)
            return sorted(ids),revision,prepared

    def cleanup_covered(self,payload,prepare):
        with WRITE_LOCK:
            if not payload.confirmed:raise HTTPException(422,'请确认清理范围后再提交。')
            doc,revision=self.read()
            if payload.revision!=revision:raise HTTPException(409,'资料已更新，请刷新后重新核对清理范围。')
            candidates={r['id']:r for r in covered_drafts(doc) if r['scene_id']==payload.scene_id}
            ids=set(payload.ids)
            if not ids.issubset(candidates):raise HTTPException(409,'部分草稿已有内容或条件发生变化，未执行清理，请刷新核对。')
            while True:
                related={r['id'] for r in doc['records'] if r.get('canonical_answer_id') in ids}
                if related.issubset(ids):break
                ids.update(related)
            when=datetime.now(timezone.utc).isoformat()
            for row in doc['records']:
                if row['id'] in ids:
                    row.update(status='disabled',deleted_at=when,updated_at=when,deleted_reason='covered_empty_draft')
                    if row['id'] in candidates:row['covered_by']=candidates[row['id']]['covered_by']
            revision,prepared=self.persist(doc,prepare)
            return sorted(ids),revision,prepared


@router.get('/knowledge')
def knowledge_page(request:Request):
    if request.query_params.get('status')=='needs_review' and not any(k in request.query_params for k in ('scene','test','answer')):
        return RedirectResponse('/review',status_code=303)
    return frontend_page('knowledge.html',view='embedded' if request.query_params.get('embed')=='1' else None)


@router.get('/review')
def review_page():
    return frontend_page('knowledge.html',view='review')


@router.get('/api/faq')
def list_faq(request: Request):
    doc,revision=FAQStore().read()
    svc=request.app.state.service
    return {'revision':revision,'records':[r for r in doc['records'] if not r.get('deleted_at')],
        'products':[{'id':p['id'],'name':p.get('display_name',p['name'])} for p in visible_products(svc.kb)]}

@router.get('/api/scenes')
def list_scenes(request: Request):
    doc,revision=FAQStore().read()
    scenes=[{**s,'answers':[r for r in doc['records'] if r['scene_id']==s['id'] and not r.get('canonical_answer_id') and not r.get('deleted_at')]} for s in doc['scenes'] if not s.get('deleted_at')]
    return {'revision':revision,'scenes':scenes,'covered_drafts':covered_drafts(doc),
            'products':[{'id':p['id'],'name':p.get('display_name',p['name'])} for p in visible_products(request.app.state.service.kb)]}


def activate(doc,svc,timings=None):
    start=time.perf_counter()
    kb=Knowledge(faq_document=doc)
    if timings is not None:timings['knowledge']=time.perf_counter()-start
    start=time.perf_counter()
    semantic,status=get_semantic(kb)
    if timings is not None:timings['semantic']=time.perf_counter()-start
    return kb,semantic,status


def apply_prepared(svc,prepared):
    svc.kb,svc.semantic,svc.semantic_status=prepared
    for session in svc.sessions.values():session.answered_keys.clear()


def check_origin(request):
    origin=request.headers.get('origin')
    if origin and origin.rstrip('/')!=str(request.base_url).rstrip('/'):
        raise HTTPException(403,'请在本地工作台页面保存资料。')


@router.post('/api/scenes')
def save_scene(body:SaveScene,request:Request):
    check_origin(request);svc=request.app.state.service
    scene,revision,prepared=FAQStore().save_scene(body,lambda doc:activate(doc,svc))
    apply_prepared(svc,prepared)
    return {'scene':scene,'revision':revision,'message':'场景已保存。'}


@router.post('/api/faq')
def save_faq(body: SaveFAQ, request: Request, response: Response):
    start=time.perf_counter()
    check_origin(request)
    svc=request.app.state.service
    store=FAQStore()
    def prepare(doc):return activate(doc,svc,store.timings)
    row,revision,prepared=store.save(body,list(svc.kb.products),prepare)
    apply_prepared(svc,prepared)
    covered=covered_drafts({'records':svc.kb.faq.records})
    store.timings['total']=time.perf_counter()-start
    timings={key:round(value*1000,2) for key,value in store.timings.items()}
    request_id=uuid.uuid4().hex
    response.headers['Server-Timing']=', '.join(f'{key};dur={value}' for key,value in timings.items())
    response.headers['X-Save-Request-ID']=request_id
    # Only timing metadata: never log the submitted answer, credentials or personal data.
    svc.logger.info(json.dumps({'event':'faq_save','request_id':request_id,'timings_ms':timings,
                               'semantic':svc.semantic_status}))
    return {'record':row,'revision':revision,'message':'已保存并应用到客服机器人。',
            'semantic':svc.semantic_status,'covered_drafts':covered,'timings_ms':timings,'request_id':request_id}


def delete_knowledge(body,request,target):
    check_origin(request);svc=request.app.state.service
    ids,revision,prepared=FAQStore().delete(body,target,lambda doc:activate(doc,svc))
    apply_prepared(svc,prepared)
    return {'deleted_ids':ids,'deleted_scene_id':body.id if target=='scene' else None,
            'revision':revision,'covered_drafts':covered_drafts({'records':svc.kb.faq.records}),
            'message':'意图及其条件答案已删除。' if target=='scene' else '答案已删除。'}


@router.post('/api/faq/delete')
def delete_answer(body:DeleteKnowledge,request:Request):
    return delete_knowledge(body,request,'answer')


@router.post('/api/scenes/delete')
def delete_scene(body:DeleteKnowledge,request:Request):
    return delete_knowledge(body,request,'scene')


@router.post('/api/faq/cleanup-covered')
def cleanup_covered(body:CleanupDrafts,request:Request):
    check_origin(request);svc=request.app.state.service
    ids,revision,prepared=FAQStore().cleanup_covered(body,lambda doc:activate(doc,svc))
    apply_prepared(svc,prepared)
    return {'deleted_ids':ids,'revision':revision,'covered_drafts':covered_drafts({'records':svc.kb.faq.records}),
            'message':f'已清理 {len(set(body.ids))} 条已被覆盖的空白草稿，启用答案保留。'}
