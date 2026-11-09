from .product_labels import visible_products
"""资料管理与有来源的 RAG 建议；建议始终与客户自动回复分开。"""
from typing import Literal
from .product_labels import public_text

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from .faq_admin import check_origin
from .frontend import frontend_page
from .rag import RAGAssistant, RAGStore

router = APIRouter()


class SaveMaterial(BaseModel):
    revision: str = Field(max_length=128)
    document: dict


class AssistRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=100)
    message: str = Field(min_length=1, max_length=2000)
    product_id: str | None = None
    reception_type: Literal['presales', 'aftersales'] | None = None
    business_stage: Literal['presales', 'shipping', 'received', 'aftersales'] | None = None


@router.get('/materials')
def materials_page():
    return frontend_page('materials.html')


@router.get('/api/materials')
def materials(request: Request):
    doc, revision = RAGStore().read()
    return {'revision': revision, 'documents': doc['documents'],
            'products': [{'id': p['id'], 'name': p.get('display_name',p['name'])}
                         for p in visible_products(request.app.state.service.kb)]}


@router.post('/api/materials')
def save_material(body: SaveMaterial, request: Request):
    check_origin(request)
    svc = request.app.state.service
    try:
        row, revision = RAGStore().save(body.revision, body.document, list(svc.kb.products))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from None
    return {'document': row, 'revision': revision, 'message': '资料已保存，下次检索即生效。'}


@router.post('/api/rag/assist')
async def assist(body: AssistRequest, request: Request):
    check_origin(request)
    svc = request.app.state.service
    if body.session_id not in svc.sessions:
        raise HTTPException(404, '会话不存在或服务已重启，请新建会话。')
    if not body.message.strip():
        raise HTTPException(422, '问题不能为空。')
    if body.product_id is not None and body.product_id not in svc.kb.products:
        raise HTTPException(422, '请选择已有商品。')
    async with svc.locks[body.session_id]:
        session = svc.sessions[body.session_id]
        product = body.product_id or session.current_product_id
        reception = body.reception_type or session.reception_type
        stage = body.business_stage or session.business_stage
        history = list(session.history[-6:])
        promotion=session.last_promotion or {}
        promotion_context=promotion if (promotion.get('followup') and promotion.get('product_id')==product
            and promotion.get('reception')==reception and promotion.get('stage')==stage) else {}
    encoder = getattr(svc.semantic, 'encoder', None)
    rag = getattr(svc, '_rag_assistant', None)
    if rag is None or rag.kb is not svc.kb or rag.model is not svc.model or rag.encoder is not encoder:
        rag = svc._rag_assistant = RAGAssistant(svc.kb, svc.model, encoder=encoder)
    result = await rag.assist(body.message.strip(), product, reception, stage, history=history,promotion_context=promotion_context)
    # 资料建议不写入历史、不触发客户发送，也不自动新增或启用 FAQ。
    if result.get('suggestion'):result['suggestion'] = public_text(result['suggestion'])
    result['for_operator_only'] = True
    result['send_to_customer'] = False
    return svc.scrub(result)
