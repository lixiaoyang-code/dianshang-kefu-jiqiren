"""Merge a reviewed personal phrase package without replacing active merchant answers."""
import copy,json,re,hashlib,os,uuid
from pathlib import Path
from datetime import datetime,timezone
from app.faq import canonical
from app.knowledge import Knowledge
from app.faq_admin import FAQStore
from app.rag import RAGStore,_validate_document

def clean(text):
    text=re.sub(r'#E-[A-Za-z0-9]+','',text or '')
    for brand in ['中国平安','平安','半弦月','拍米拉链']:text=text.replace(brand,'')
    return text.strip()

def merge(document,materials,package):
    doc,rag=copy.deepcopy(document),copy.deepcopy(materials)
    stats=dict(scenes_added=0,answers_added=0,active_answers_added=0,review_answers_added=0,existing_answers_preserved=0,variants_added=0,materials_added=0)
    report=[];now=datetime.now(timezone.utc).isoformat()
    for e in package:
        qs=list(dict.fromkeys(clean(q) for q in e['qs'] if clean(q)))
        ids=set(e['pids']);status='needs_review' if e['note'] else 'active'
        answer=clean(e['answer'])
        key=e['key'];sid=e.get('sid')
        scene=next((s for s in doc['scenes'] if s['id']==sid and not s.get('deleted_at')),None) if sid else None
        if not scene:
            norms={canonical(q) for q in qs}
            candidates=[s for s in doc['scenes'] if not s.get('deleted_at') and norms.intersection(canonical(q) for q in [s['name'],*s.get('question_variants',[])]) and any(r['scene_id']==s['id'] and ids.intersection(r.get('product_ids',[])) and not r.get('deleted_at') for r in doc['records'])]
            scene=next((s for s in candidates if canonical(s['name'])==canonical(e['title'])),candidates[0] if candidates else None)
        if not scene:
            sid='industry.personal_'+key
            scene=next((s for s in doc['scenes'] if s['id']==sid),None)
            if scene and scene.get('deleted_at'):report.append(dict(row=e['source_row'],action='skip_deleted',title=e['title']));continue
            if not scene:
                scene=dict(id=sid,name=e['title'],type='industry',category='产品使用' if any(w in e['title'] for w in ['洗','安装','断电','折叠','模式']) else '商品参数',question_variants=[],configured=True,description='仅识别“'+e['title']+'”这一问题，不将相邻的参数、售后政策等其他问题合并。')
                doc['scenes'].append(scene);stats['scenes_added']+=1
        sid=scene['id']
        before=scene.get('question_variants',[])
        scene['question_variants']=list(dict.fromkeys([*before,*qs]))[:100]
        stats['variants_added']+=len(scene['question_variants'])-len(before)
        for r in doc['records']:
            if r['scene_id']==sid and not r.get('deleted_at'):r['question_variants']=scene['question_variants']
        baseid='personal.'+key+'.'+str(e['source_row'])
        existing=[r for r in doc['records'] if r['scene_id']==sid and r.get('status')=='active' and not r.get('deleted_at') and not r.get('canonical_answer_id') and r.get('scope')=='product']
        covered={p for r in existing for p in r.get('product_ids',[])}
        missing=sorted(ids-covered) if status=='active' else sorted(ids)
        action='preserved_active' if status=='active' and not missing else 'added_'+status
        if not missing:stats['existing_answers_preserved']+=1
        if missing and not any(r['id']==baseid for r in doc['records']):
            row=dict(id=baseid,intent=key,scene_id=sid,scene_name=scene['name'],scene_type=scene['type'],category=scene['category'],scope='product',product_ids=missing,answer_product_id=missing[0],question_variants=scene['question_variants'],standard_answer=answer,answer_parts=[answer],status=status,images=[],fields=[],keywords=[],keyword_mode='any',priority=0,configured_scene=True,conditions={'reception':'presales','stages':['presales'],'valid_from':None,'valid_until':None},boundaries={'no_extra_promises':True,'unsupported':'operator_only_no_customer_reply'},sources=[e['source']],origin='personal_phrase_20261107',updated_at=now,review_note=e['note'])
            doc['records'].append(row);stats['answers_added']+=1;stats['active_answers_added' if status=='active' else 'review_answers_added']+=1
        mid='personal.material.'+key+'.'+str(e['source_row'])
        if not any(r['id']==mid for r in rag['documents']):
            value=dict(title=e['title'],content=answer,source='快捷短语(个人).csv · 数据行 '+str(e['source_row'])+' · '+e['source']['code']+('；待核对：'+e['note'] if e['note'] else ''),product_ids=sorted(ids),status=status,topics=[],conditions={'reception':'presales','stages':['presales'],'valid_from':None,'valid_until':None},date='2026-11-07')
            value=_validate_document(value,{p:True for p in ids});value['id']=mid
            rag['documents'].append(value);stats['materials_added']+=1
        report.append(dict(row=e['source_row'],title=e['title'],scene_id=sid,pids=e['pids'],status=status,action=action,note=e['note']))
    Knowledge(faq_document=doc)
    return doc,rag,stats,report

def apply(package_path):
    # Run with app stopped, using the persistent data volume; preserve current cloud edits.
    store=FAQStore();before,_=store.read();rs=RAGStore();materials,_=rs.read()
    after,rag,stats,report=merge(before,materials,json.loads(Path(package_path).read_text(encoding='utf-8')))
    # Validate both documents first and restore exact originals if either write fails.
    faq_bytes,rag_bytes=store.path.read_bytes(),rs.path.read_bytes()
    try:
        if before!=after:store.persist(after,lambda doc:Knowledge(faq_document=doc))
        if materials!=rag:
            folder=rs.path.parent/'backups';folder.mkdir(exist_ok=True)
            (folder/('rag-personal-'+uuid.uuid4().hex+'.json')).write_bytes(rag_bytes)
            temp=rs.path.with_name('.rag-personal-'+uuid.uuid4().hex+'.tmp')
            temp.write_text(json.dumps(rag,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,rs.path)
    except Exception:
        for path,original in [(store.path,faq_bytes),(rs.path,rag_bytes)]:
            temp=path.with_name('.rollback-'+uuid.uuid4().hex+'.tmp');temp.write_bytes(original);os.replace(temp,path)
        raise
    print(json.dumps(stats,ensure_ascii=False))
    return stats

if __name__=='__main__':
    import sys
    apply(sys.argv[1])
