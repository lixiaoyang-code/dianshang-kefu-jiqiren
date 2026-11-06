"""公开体验只提供汇总指标；知识配置保存在访问者本机。"""
from fastapi import APIRouter,Request,Query
from .frontend import frontend_page

router=APIRouter()

@router.get('/experience/knowledge')
def knowledge_experience():return frontend_page('knowledge-demo.html')

@router.get('/experience/statistics')
def statistics_experience():return frontend_page('statistics-demo.html')

@router.get('/api/experience/statistics')
def aggregate_statistics(request:Request,days:int=Query(7,ge=0,le=30)):
    value=request.app.state.service.statistics.snapshot(days=days)
    # Deliberate allowlist: never expose questions, answers, request IDs or diagnostic rows.
    return {k:value[k] for k in ('counts','rates','trend','scope','accuracy_note')}
