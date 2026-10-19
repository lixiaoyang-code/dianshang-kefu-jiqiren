"""本地 FAQ 管理：校验、版本冲突保护、备份和原子保存。"""
import copy
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field
from .config import ROOT
from .knowledge import Knowledge
from .semantic import get_semantic
from .scene_rules import normalize_document, SCENE_TYPES, STAGES, parse_time

router = APIRouter()
WRITE_LOCK = threading.Lock()


class SaveFAQ(BaseModel):
    revision: str
    record: dict

class SaveScene(BaseModel):
    revision: str
    scene: dict


class FAQStore:
    def __init__(self, path=None):
        self.path = path or ROOT/'data/faq.json'

    def read(self):
        raw = self.path.read_bytes()
        return normalize_document(json.loads(raw)), hashlib.sha256(raw).hexdigest()

    def persist(self, doc, prepare):
        prepared=prepare(doc)
        backups=self.path.parent/'backups';backups.mkdir(exist_ok=True)
        (backups/f'faq-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.json').write_bytes(self.path.read_bytes())
        raw=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
        temp=self.path.with_name('.faq-'+uuid.uuid4().hex+'.tmp')
        try:
            temp.write_bytes(raw)
            os.replace(temp,self.path)
        finally:temp.unlink(missing_ok=True)
        return hashlib.sha256(raw).hexdigest(),prepared

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
            scene={'id':previous['id'] if previous else 'scene.'+uuid.uuid4().hex,
                   'name':name.strip(),'type':value['type'],'category':value.get('category') or '商品咨询',
                   'question_variants':list(dict.fromkeys(v.strip() for v in variants)), 'configured':True}
            doc['scenes']=[s for s in doc['scenes'] if s['id']!=scene['id']]+[scene]
            for row in doc['records']:
                if row['scene_id']==scene['id']:
                    row.update(scene_name=scene['name'],scene_type=scene['type'],
                               question_variants=scene['question_variants'],configured_scene=True)
            revision,prepared=self.persist(doc,prepare)
            return scene,revision,prepared

    def save(self, payload, product_ids, prepare):
        with WRITE_LOCK:
            doc, revision = self.read()
            if payload.revision != revision:
                raise HTTPException(409, '资料已被其他页面更新，请刷新后再保存。')
            row = copy.deepcopy(payload.record)
            previous = next((r for r in doc['records'] if r['id']==row.get('id')), None)
            if previous:
                # 来源与旧字段 ID 保留；商品和状态条件可在页面维护。
                row = {**previous, **{k:row[k] for k in ('intent','question_variants',
                    'standard_answer','category','status','images','scope','product_ids','answer_product_id',
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


@router.get('/knowledge')
def knowledge_page():
    return FileResponse(ROOT/'static/knowledge.html')


@router.get('/api/faq')
def list_faq(request: Request):
    doc,revision=FAQStore().read()
    svc=request.app.state.service
    return {'revision':revision,'records':doc['records'],
        'products':[{'id':p['id'],'name':p['name']} for p in svc.kb.products.values()]}

@router.get('/api/scenes')
def list_scenes(request: Request):
    doc,revision=FAQStore().read()
    scenes=[{**s,'answers':[r for r in doc['records'] if r['scene_id']==s['id']]} for s in doc['scenes']]
    return {'revision':revision,'scenes':scenes,
            'products':[{'id':p['id'],'name':p['name']} for p in request.app.state.service.kb.products.values()]}


def activate(doc,svc):
    kb=Knowledge(faq_document=doc)
    semantic,status=get_semantic(kb)
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
def save_faq(body: SaveFAQ, request: Request):
    check_origin(request)
    svc=request.app.state.service
    def prepare(doc):return activate(doc,svc)
    row,revision,prepared=FAQStore().save(body,list(svc.kb.products),prepare)
    apply_prepared(svc,prepared)
    return {'record':row,'revision':revision,'message':'已保存并应用到客服机器人。',
            'semantic':svc.semantic_status}
