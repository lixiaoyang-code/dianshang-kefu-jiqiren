"""统一 FAQ：保留标准答案，商品事实与跨款推荐分开筛选。"""
import re
from .scene_rules import normalize_document, row_eligible, rank, managed, keyword_match, requires_scene_selection, SCENE_TYPES


def canonical(text):
    return re.sub(r'[\s，。？！?！～~、：:]', '', text).lower()


def answer_signature(text):
    # 来源问答与核准短答可能仅差称呼和标点；这不构成商品事实冲突。
    return canonical(re.sub(r'^(?:亲亲|亲)[，,\s]*', '', text.strip()))


class FAQ:
    def __init__(self, records, scenes=None):
        document={'records':records}
        if scenes is not None:document['scenes']=scenes
        document=normalize_document(document)
        self.records = document['records']
        self.scenes = document['scenes']
        seen = set()
        for row in self.records:
            if row['id'] in seen:
                raise ValueError('duplicate FAQ id')
            seen.add(row['id'])
            if row['scope'] not in ('product', 'store', 'catalog'):
                raise ValueError('invalid FAQ scope')
            if row['status'] == 'active' and not row['standard_answer'].strip():
                raise ValueError('active FAQ requires answer')
            if row['scope'] == 'product' and not row['product_ids']:
                raise ValueError('product FAQ requires product_ids')

    def eligible(self, pid, reception='presales', stage='presales', now=None):
        return [r for r in self.records if not r.get('canonical_answer_id') and row_eligible(r,pid,reception,stage,now)]

    def select(self, rows, pid, reception='presales', stage='presales', now=None):
        # 原表副本只保留来源，不能在主答案被停用后重新顶上旧内容。
        eligible=[r for r in rows if not r.get('canonical_answer_id') and row_eligible(r,pid,reception,stage,now)]
        if not eligible:return {'status':'ineligible','row':None}
        highest=max(rank(r) for r in eligible)
        winners=[r for r in eligible if rank(r)==highest]
        signatures={(answer_signature(r['standard_answer']),str(r.get('images',[]))) for r in winners}
        if len(signatures)>1:return {'status':'ambiguous','row':None}
        return {'status':'matched','row':winners[0]}

    def resolve(self,text,pid,reception='presales',stage='presales',now=None,aliases=None):
        texts=[text,*(aliases or [])]
        queries={canonical(t) for t in texts if canonical(t)}
        exact={s['id'] for s in self.scenes if queries.intersection(canonical(q) for q in s['question_variants'])}
        highest_exact=max((SCENE_TYPES.get(s['type'],0) for s in self.scenes if s['id'] in exact),default=-1)
        scenes=set(exact)
        for row in self.records:
            if row['scope']=='product' and pid not in row['product_ids']:continue
            # 已有标准问法时，同层的宽泛关键词不能吞掉更具体的客户意图。
            # 高层活动/特殊规则仍可覆盖基础意图，实际答案继续过滤所有条件。
            if (row['scene_id'] in exact or SCENE_TYPES.get(row.get('scene_type'),0)>highest_exact) and any(keyword_match(row,t) for t in texts):
                scenes.add(row['scene_id'])
        if not scenes:return {'status':'no_match','row':None,'managed':False}
        rows=[r for r in self.records if r['scene_id'] in scenes]
        result=self.select(rows,pid,reception,stage,now)
        return {**result,'managed':any(managed(r) for r in rows),'scene_ids':sorted(scenes)}

    def related_rows(self,row):
        """语义检索命中后，同问法的高优先级场景也参与条件选择。"""
        scene=next((s for s in self.scenes if s['id']==row['scene_id']),None)
        variants={canonical(q) for q in (scene or {}).get('question_variants',[])}
        related={s['id'] for s in self.scenes if s['id']==row['scene_id'] or
                 variants.intersection(canonical(q) for q in s['question_variants'])}
        return [r for r in self.records if r['scene_id'] in related]

    def from_evidence(self, hits, pid, reception='presales', stage='presales'):
        """字段检索已定位到 FAQ 时直接选核准答案，无需模型再批准一遍。"""
        by_id={r['id']:r for r in self.records}
        if not hits or any(h.get('id') not in by_id for h in hits):return None
        chosen=[]
        for hit in hits:
            row=by_id[hit['id']]
            peers=self.related_rows(row)
            if any(requires_scene_selection(r) for r in peers
                   if r.get('scope')!='product' or pid in r.get('product_ids',[])):
                result=self.select(peers,pid,reception,stage)
            else:
                result={'status':'matched','row':row} if row_eligible(row,pid,reception,stage) else {'status':'ineligible','row':None}
            if result['status']!='matched':
                return {**result,'scene_ids':[row['scene_id']]}
            if result['row']['id'] not in {r['id'] for r in chosen}:chosen.append(result['row'])
        return {'status':'matched','rows':chosen}

    def match(self, text, pid,reception='presales',stage='presales',now=None):
        matches = [r for r in self.eligible(pid,reception,stage,now) if canonical(text) in
                   [canonical(q) for q in r['question_variants']]]
        # 不同标准答案同时命中时不猜测。
        if len({r['standard_answer'] for r in matches}) != 1:
            return None
        return matches[0] if matches else None

    @staticmethod
    def candidate(row):
        return {'id': row['id'], 'question_topic': row['intent'],
                'question_variants': row['question_variants'],
                'answer': row['standard_answer'], 'product_id': row.get('answer_product_id'),
                'answer_parts': row.get('answer_parts') or [row['standard_answer']],
                'fields': row['fields'], 'sources': row['sources'],
                'images': row['images'], 'boundaries': row['boundaries'], 'scope': row['scope']}
