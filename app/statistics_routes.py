from typing import Literal
from fastapi import APIRouter, Request, Query, HTTPException
from pydantic import BaseModel, Field
from .faq_admin import check_origin
from .frontend import frontend_page

router=APIRouter()


class Review(BaseModel):
    request_id: str = Field(min_length=1,max_length=100)
    verdict: Literal['correct','partial','incorrect'] | None = None


class Processing(BaseModel):
    request_id: str = Field(min_length=1,max_length=100)
    handled: bool
    note: str = Field(default='',max_length=500)


@router.get('/statistics')
@router.get('/consultations')
def page():return frontend_page('statistics.html')


@router.get('/api/statistics')
def statistics(request:Request, days:int=Query(7,ge=0,le=30), product:str=Query('',max_length=100),
               include_interactions:bool=False, outcome:Literal['','manual','unreviewed','error','pending','handled']='', page:int=Query(1,ge=1)):
    svc=request.app.state.service
    result=svc.statistics.snapshot(days,product,include_interactions,outcome,page)
    for row in result['records']:
        row['intents']=[{'id':s['id'],'name':s['name']} for s in svc.kb.faq.scenes
                        if s['name']==row['intent'] or s['name'] in row['intent'].split(' / ')]
    return result


@router.post('/api/statistics/review')
def review(body:Review,request:Request):
    check_origin(request)
    result=request.app.state.service.statistics.review(body.request_id,body.verdict)
    if result=='missing':raise HTTPException(404,'未找到这条诊断记录。')
    if result=='not_answered':raise HTTPException(422,'只评价已发送的业务答复。')
    return {'status':'saved'}


@router.post('/api/statistics/processing')
def process(body:Processing,request:Request):
    check_origin(request)
    result=request.app.state.service.statistics.process(body.request_id,body.handled,body.note)
    if result=='missing':raise HTTPException(404,'未找到这条咨询记录。')
    if result=='not_pending':raise HTTPException(422,'仅处理未回答或系统异常的咨询。')
    return {'status':'saved'}
