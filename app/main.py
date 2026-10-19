from dataclasses import asdict
from contextlib import asynccontextmanager
from typing import Literal
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.exceptions import RequestValidationError
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from .config import ROOT
from .service import Service
from .faq_admin import router as faq_router

@asynccontextmanager
async def lifespan(app):
    app.state.service = Service()
    yield
    for h in app.state.service.logger.handlers:
        h.close()

app = FastAPI(title='售前 AI 工作台 V0.2', lifespan=lifespan)
app.include_router(faq_router)
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')

class Chat(BaseModel):
    session_id: str
    message: str = Field(min_length=1, max_length=2000)
    product_id: str | None = None
    reception_type: Literal['presales','aftersales'] | None = None
    business_stage: Literal['presales','shipping','received','aftersales'] | None = None

class Event(BaseModel):
    type: Literal['agent_card', 'customer_select', 'takeover', 'resume', 'handled']
    product_id: str | None = None

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
    return FileResponse(ROOT / 'static/index.html')

@app.get('/api/health')
def health():
    settings=service().model.settings
    return {'status': 'ok', 'mode': 'mock' if settings.mock else 'api', 'version': '0.2.0',
            'semantic':service().semantic_status,
            'intent_model':'pending_key' if not settings.key else 'disabled' if settings.mock or not settings.intent_enabled else 'configured'}

@app.get('/api/products')
def products():
    return [{'id': p['id'], 'name': p['name'], 'model': p['model'], 'link':p.get('link'), 'image_refs':p.get('image_refs',[])} for p in service().kb.products.values()]

@app.post('/api/sessions')
def create():
    try:
        return asdict(service().create())
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
    s = session(sid)
    async with service().locks[sid]:
        if body.type in ('agent_card', 'customer_select'):
            if body.type=='customer_select' and body.product_id is None:
                s.current_product_id=None;s.product_confirmed=False;s.pending_question=None
                return asdict(s)
            if body.product_id not in service().kb.products:
                raise HTTPException(400, '商品不存在。')
            if body.type == 'agent_card':
                s.recent_product_ids = ([body.product_id] + [p for p in s.recent_product_ids if p != body.product_id])[:5]
            else:
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
