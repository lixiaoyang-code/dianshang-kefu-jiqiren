from dataclasses import asdict
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import ROOT
from .service import Service, Session
from .faq_admin import router as faq_router
from .rag_routes import router as rag_router
from .statistics_routes import router as statistics_router
from .frontend import frontend_page
from .experience import router as experience_router
from .product_links import validate_link
from .deployment import (DeploymentSettings, DemoRuntime, DemoAccessMiddleware,
                         deployment_status, register_session)

@asynccontextmanager
async def lifespan(app):
    app.state.deployment = DeploymentSettings.from_env()
    app.state.demo_runtime = DemoRuntime(app.state.deployment) if app.state.deployment.mode == 'demo' else None
    app.state.service = Service()
    yield
    for h in app.state.service.logger.handlers:
        h.close()

app = FastAPI(title='售前 AI 工作台 V0.2', lifespan=lifespan)
app.add_middleware(DemoAccessMiddleware)
app.include_router(faq_router)
app.include_router(rag_router)
app.include_router(statistics_router)
app.include_router(experience_router)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

@app.middleware('http')
async def fresh_frontend_assets(request,call_next):
    response=await call_next(request)
    if request.url.path.startswith('/static/') and request.url.path.endswith(('.css','.js')):
        response.headers['Cache-Control']='no-store'
    return response

class Chat(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    product_id: str | None = None
    reception_type: Literal['presales','aftersales'] | None = None
    business_stage: Literal['presales','shipping','received','aftersales'] | None = None

class Event(BaseModel):
    type: Literal['agent_card', 'customer_select', 'customer_link', 'takeover', 'resume', 'handled']
    product_id: str | None = None
    url: str | None = Field(default=None,max_length=2000)


class ResetSession(BaseModel):
    mode: Literal['memory', 'test'] = 'memory'
    reception_type: Literal['presales','aftersales'] | None = None
    business_stage: Literal['presales','shipping','received','aftersales'] | None = None

def service():
    return app.state.service

def session(sid):
    if sid not in service().sessions:
        raise HTTPException(404, '会话不存在或服务已重启，请新建会话。')
    return service().sessions[sid]

@app.exception_handler(RequestValidationError)
async def invalid_request(request, exc):
    return JSONResponse(status_code=422, content={'status': 'error', 'answer': '请求格式不正确，请检查消息和事件参数。'})

@app.get('/')
def index():
    return frontend_page('index.html')

@app.get('/api/health')
def health(request: Request):
    settings=service().model.settings
    return {'status': 'ok', 'mode': 'mock' if settings.mock else 'api', 'version': '0.2.0',
            'deployment':deployment_status(request),
            'semantic':service().semantic_status,
            'dedicated_intent_classifier':False,
            'intent_model':'pending_key' if not settings.key else 'disabled' if settings.mock or not settings.intent_enabled else 'configured'}

@app.get('/api/products')
def products():
    return [{'id': p['id'], 'name': p['name'], 'model': p['model'], 'category':p.get('category','宿舍床帘'),
             'onboarding_status':p.get('onboarding_status'), 'link':p.get('link'), 'image_refs':p.get('image_refs',[])} for p in service().kb.products.values()]

@app.get('/admin')
def admin_entry():
    return RedirectResponse('/', status_code=303)

@app.post('/api/sessions')
def create(request: Request):
    try:
        value = service().create()
        register_session(request, value.session_id)
        return asdict(value)
    except RuntimeError:
        raise HTTPException(503, '本地会话数量达到上限，请重启服务。')

@app.post('/api/chat')
async def chat(body: Chat):
    session(body.session_id)
    if not body.message.strip():
        raise HTTPException(422, '消息不能为空。')
    return await service().chat(body.session_id, body.message.strip(), body.product_id,
                                body.reception_type,body.business_stage)

@app.post('/api/sessions/{sid}/events')
async def event(sid: str, body: Event):
    session(sid)
    async with service().locks[sid]:
        s=session(sid)
        if body.type=='customer_link':
            url=validate_link(body.url) if body.url and body.url.strip() else None
            if body.product_id is not None and body.product_id not in service().kb.products:
                raise HTTPException(400,'关联的商品不存在，请重新选择。')
            if url is None and body.product_id is None:
                raise HTTPException(422,'请选择商品，或填写商品网址。')
            s.last_dimension=None;s.pending_question=None;s.pending_topic=None
            s.waiting.clear();s.answered_keys=[]
            s.current_product_id=body.product_id;s.product_confirmed=body.product_id is not None
            s.product_links=([{'url':url,'product_id':body.product_id}]+s.product_links)[:20]
            payload=service().scrub({'event':{'type':body.type,'url':url,'product_id':body.product_id},'session':sid})
            service().logger.info(__import__('json').dumps(payload,ensure_ascii=False))
            return {'session':asdict(s),'link':s.product_links[0],
                    'message':'已关联商品，后续问题按这款回答。' if body.product_id else '已收到商品链接，请先确认对应商品后继续咨询。',
                    'status':'linked' if body.product_id else 'product_required'}
        if body.type in ('agent_card', 'customer_select'):
            if body.type=='customer_select' and body.product_id is None:
                s.current_product_id=None;s.product_confirmed=False;s.pending_question=None
                s.last_dimension=None
                return asdict(s)
            if body.product_id not in service().kb.products:
                raise HTTPException(400, '商品不存在。')
            if body.type == 'agent_card':
                s.recent_product_ids = ([body.product_id] + [p for p in s.recent_product_ids if p != body.product_id])[:5]
            else:
                if s.current_product_id!=body.product_id:s.last_dimension=None
                s.current_product_id, s.product_confirmed = body.product_id, True
        else:
            s.needs_human = body.type == 'takeover'
            s.waiting.clear()
        service().logger.info(__import__('json').dumps({'event': body.model_dump(), 'session': sid}, ensure_ascii=False))
        return asdict(s)

@app.post('/api/sessions/{sid}/waiting/{request_id}')
async def waiting(sid: str, request_id: str):
    session(sid)
    return await service().waiting_reply(sid,request_id)


@app.post('/api/sessions/{sid}/reset')
async def reset_session(sid: str, body: ResetSession):
    session(sid)
    async with service().locks[sid]:
        previous=session(sid)
        # 保留条件的清除，与回到初始条件的重置分开，旧等待任务随会话状态一起失效。
        fresh=Session(sid)
        if body.mode=='memory':
            fresh.current_product_id=previous.current_product_id
            fresh.product_confirmed=previous.product_confirmed
            fresh.reception_type=body.reception_type or previous.reception_type
            fresh.business_stage=body.business_stage or previous.business_stage
        service().sessions[sid]=fresh
        service().logger.info(__import__('json').dumps({'event':'reset_session','mode':body.mode,'session':sid}))
        return asdict(fresh)
