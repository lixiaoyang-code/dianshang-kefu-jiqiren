"""新品使用绑定到自身的FAQ，不经过床帘专用尺寸和营销规则。"""
import asyncio
import re
from .faq import canonical


def question_key(text, product):
    """Only remove product labels and courtesy particles; never infer a new intent."""
    for token in sorted({product['id'], product['name'], product['model'], *product['aliases']}, key=len, reverse=True):
        text = re.sub(re.escape(token), '', text, flags=re.I)
    text = canonical(text)
    text = re.sub(r'^(?:亲亲|亲|您好|你好|请问|这个|这款)+', '', text)
    return re.sub(r'(?:吗|嘛|呢|呀|啊|哈)+$', '', text)


async def answer(service, query, pid, reception, stage, history):
    kb=service.kb;p=kb.products[pid]
    text=query
    for token in sorted([pid,p['name'],p['model'],*p['aliases']],key=len,reverse=True):text=text.replace(token,'')
    scoped=[r for r in kb.faq.records if r.get('scope')=='product' and pid in r.get('product_ids',[])]
    # Keep the original full question as well as the product-free query. Personal
    # phrases often include the product name; stripping only the query lost them.
    choice=kb.faq.resolve(query,pid,reception,stage,aliases=[text])
    relevant=[r for r in scoped if r['scene_id'] in choice.get('scene_ids',[])]
    if not relevant:
        key=question_key(query,p)
        own_scenes={r['scene_id'] for r in scoped if not r.get('deleted_at')}
        aliases=[q for scene in kb.faq.scenes if scene['id'] in own_scenes
                 for q in scene['question_variants'] if key and question_key(q,p)==key]
        if aliases:
            choice=kb.faq.resolve(query,pid,reception,stage,aliases=[text,*aliases])
            relevant=[r for r in scoped if r['scene_id'] in choice.get('scene_ids',[])]
    if relevant:
        choice=kb.faq.select(relevant,pid,reception,stage)
        if choice['status']=='matched':
            row=choice['row']
            return row,{'retrieval':{'method':'scene_faq','status':'matched','hits':[kb.faq.candidate(row)]}},'catalog_faq'
        return None,{'scene_selection':{'status':choice['status'],'scene_ids':sorted({r['scene_id'] for r in relevant})}},'catalog_'+choice['status']
    # 缺少对应核准资料时，不用相似的材质/规格答案解释疗效或用电安全。
    if re.search(r'颈椎|治疗|治病|缓解|孕妇|婴儿|宝宝|儿童|安全|漏电|机洗|水洗|能洗|功率|耗电|度电|防摔|坠床|赔|免费|退款|质保|证书|认证',text):
        return None,{},'catalog_review_required'
    if service.semantic:
        doc,debug=await asyncio.to_thread(service.semantic.search,text,pid,reception,stage)
        if doc and doc['id'] in {r['id'] for r in scoped}:
            original=next(r for r in scoped if r['id']==doc['id'])
            selected=kb.faq.select(kb.faq.related_rows(original),pid,reception,stage)
            if selected['status']=='matched':
                row=selected['row']
                return row,{'semantic':debug,'retrieval':{'method':'semantic_onnx','status':'matched','hits':[kb.faq.candidate(row)]}},'catalog_semantic'
        info={'semantic':debug}
    else:info={}
    return None,info,'catalog_knowledge_missing'
