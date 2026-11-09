"""Conservative suggestions for empty product drafts covered by an active answer."""
from .scene_rules import parse_time, STAGES


def _covers(active,draft):
    if active.get('scope')!='product' or draft.get('scope')!='product':return False
    products=set(draft.get('product_ids',[]))
    if not products or not products.issubset(active.get('product_ids',[])):return False
    if active.get('keywords') or draft.get('keywords'):return False
    if active.get('priority',0)<draft.get('priority',0):return False
    a,d=active.get('conditions',{}),draft.get('conditions',{})
    if a.get('reception','all') not in ('all',d.get('reception','all')):return False
    if not set(d.get('stages') or STAGES).issubset(a.get('stages') or STAGES):return False
    start,end=parse_time(a.get('valid_from')),parse_time(a.get('valid_until'))
    draft_start,draft_end=parse_time(d.get('valid_from')),parse_time(d.get('valid_until'))
    if start and (not draft_start or start>draft_start):return False
    if end and (not draft_end or end<draft_end):return False
    return True


def covered_drafts(document):
    rows=[r for r in document['records'] if not r.get('deleted_at') and not r.get('canonical_answer_id')]
    active={}
    for row in rows:
        if row.get('status')=='active' and (row.get('standard_answer') or '').strip():
            active.setdefault(row['scene_id'],[]).append(row)
    result=[]
    for draft in rows:
        if (draft.get('status')!='needs_review' or (draft.get('standard_answer') or '').strip()
                or any(str(p or '').strip() for p in (draft.get('answer_parts') or [])) or draft.get('images')):continue
        owner=next((a for a in active.get(draft['scene_id'],[]) if _covers(a,draft)),None)
        if owner:result.append({'id':draft['id'],'scene_id':draft['scene_id'],'covered_by':owner['id']})
    return result
