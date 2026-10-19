"""统一 FAQ：保留标准答案，商品事实与跨款推荐分开筛选。"""
import re
from .scene_rules import normalize_document, row_eligible, rank, managed, keyword_match


def canonical(text):
    return re.sub(r'[\s，。？！?！～~、：:]', '', text).lower()


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
        return [r for r in self.records if row_eligible(r,pid,reception,stage,now)]

    def select(self, rows, pid, reception='presales', stage='presales', now=None):
        eligible=[r for r in rows if row_eligible(r,pid,reception,stage,now)]
        if not eligible:return {'status':'ineligible','row':None}
        highest=max(rank(r) for r in eligible)
        winners=[r for r in eligible if rank(r)==highest]
        signatures={(r['standard_answer'],str(r.get('images',[]))) for r in winners}
        if len(signatures)>1:return {'status':'ambiguous','row':None}
        return {'status':'matched','row':winners[0]}

    def resolve(self,text,pid,reception='presales',stage='presales',now=None,aliases=None):
        texts=[text,*(aliases or [])]
        queries={canonical(t) for t in texts if canonical(t)}
        scenes={s['id'] for s in self.scenes if queries.intersection(canonical(q) for q in s['question_variants'])}
        scenes.update(r['scene_id'] for r in self.records if any(keyword_match(r,t) for t in texts))
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
                'fields': row['fields'], 'sources': row['sources'],
                'images': row['images'], 'boundaries': row['boundaries'], 'scope': row['scope']}
