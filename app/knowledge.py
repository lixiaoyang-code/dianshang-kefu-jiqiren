import json
import re
import os
from .config import ROOT
from .faq import FAQ

FIELDS = {
    'sound_insulation': ('隔音', '噪音'),
    'stability': ('支架稳', '支架牢固', '支架结实'),
    'roof': ('顶部', '防尘顶', '防尘布'),
    'pole_material': ('支架材质',),
    'doors': ('开门', '几开门', '三开', '单开'),
    'shade_sides': ('四面', '五面', '靠墙遮光'),
    'bottom': ('底部', '全底', '回底', '半包'),
    'charging_port': ('充电口', '充电线'),
    'storage': ('收纳袋', '置物袋'),
    'telescoping': ('伸缩', '调节范围', '调节量'),
    'washing': ('机洗', '清洗', '怎么洗'),
    'packaging': ('包装尺寸', '外包装'),
    'pole_diameter': ('直径', '多粗'),
    'pole_wall': ('壁厚', '管壁厚度'),
    'coating': ('涂层',),
    'colors': ('颜色', '蓝色', '米色', '灰色', '米白色', '粉色', '紫色'),
    'material': ('材质', '材料', '什么做'),
    'specifications': ('规格', '容量', '尺寸', '多大'),
    'weight': ('重量', '多重'),
    'model': ('型号', 'sku'),
    'features': ('功能', '能干什么'),
    'instructions': ('怎么用', '使用方法', '使用说明', '如何使用'),
    'precautions': ('注意事项', '注意什么'),
    'selling_points': ('卖点', '优点', '优势'),
    'scenarios': ('适合', '场景'),
    'shipping': ('发货', '多久发货', '什么时候发货', '多久发', '什么时候发'),
    'arrival': ('到货', '送达', '收到', '能到', '到达'),
    'freight': ('运费', '包邮'),
    'after_sales': ('售后', '退换规则'),
    'quality': ('质量', '耐用', '靠谱吗'),
}
STORE_FIELDS = {'shipping', 'arrival', 'freight', 'after_sales'}

class Knowledge:
    def __init__(self, path=None, faq_document=None):
        self.data = json.loads((path or ROOT / os.getenv('KNOWLEDGE_FILE', 'data/nets_801_804.json')).read_text(encoding='utf-8'))
        self.products = {p['id']: p for p in self.data['products']}
        if len(self.products) != len(self.data['products']):
            raise ValueError('duplicate product id')
        self.qa_records = []
        self.faq = FAQ([])
        if self.data.get('continuous_assist'):
            self.qa_records = json.loads((ROOT / 'data/source_qa.json').read_text(encoding='utf-8'))['records']
            faq_path = ROOT / 'data/faq.json'
            if faq_document is not None or faq_path.exists():
                document = faq_document if faq_document is not None else json.loads(faq_path.read_text(encoding='utf-8'))
                self.faq = FAQ(document['records'],document.get('scenes'))
                for row in self.faq.records:
                    parts = row['id'].split('.')
                    if row['status'] != 'active': continue
                    if len(parts)==3 and parts[0]=='product' and parts[1] in self.products:
                        p = self.products[parts[1]]
                        p.setdefault('short_replies', {})[parts[2]] = row['standard_answer']
                        p.setdefault('answer_images', {})[parts[2]] = row['images']
                    elif len(parts)==2 and parts[0]=='store':
                        self.data['store']['facts'][parts[1]] = row['standard_answer']
                # 原始表格问答仍保留用于溯源；运行时以统一 FAQ 的审核状态和答案为准。
                by_id = {r['id']: r for r in self.faq.records}
                self.qa_records = [{**r, 'question': by_id[r['id']]['question_variants'][0],
                    'aliases': by_id[r['id']]['question_variants'][1:],
                    'answer': by_id[r['id']]['standard_answer'], 'status': by_id[r['id']]['status']}
                    if r['id'] in by_id else r for r in self.qa_records]

    def match_qa(self, text, product_id):
        product = self.products.get(product_id)
        if not product:
            return None
        def canonical(value):
            for name in sorted([product['name'],product_id,*product['aliases']],key=len,reverse=True):
                value=value.replace(name,'')
            value=re.sub(r'[\s，。？！?！～~、：:]', '', value)
            value=re.sub(r'^(亲亲|亲|请问)', '',value)
            return re.sub(r'(吗|嘛|呢)$','',value)
        query=canonical(text)
        matches=[r for r in self.qa_records if r['product_id']==product_id and
                 query and query in [canonical(a) for a in [r['question'],*r['aliases']]]]
        return next((r for r in matches if r['status']=='active'), matches[0] if matches else None)

    def mentions(self, text):
        return [pid for pid, p in self.products.items() if any(
            (re.search(r'(?<![A-Za-z0-9])' + re.escape(token) + r'(?![A-Za-z0-9])', text, re.I)
             if token == pid or token == p['model'] else token.lower() in text.lower())
            for token in [pid, p['name'], p['model'], *p['aliases']])]

    def retrieve(self, text, product_id):
        """确定性字段检索：分句检查覆盖范围，未覆盖的分句不让模型补全。"""
        hits, missing, unknown = {}, [], []
        # 伸缩尺寸问的是调节范围，不代表完整产品尺寸或包装尺寸。
        text = text.replace('伸缩尺寸', '伸缩范围')
        product=self.products.get(product_id)
        if product:
            for name in sorted([product['name'],product_id,*product['aliases']],key=len,reverse=True):
                text=text.replace(name,'')
            text=re.sub(r'^(?:我)?(?:想)?(?:换成|改问|咨询)', '',text)
        blocked = [t for t in self.products.get(product_id, {}).get('blocked_topics', []) if t.lower() in text.lower()]
        if blocked:
            return {'status':'insufficient', 'hits':[], 'missing_fields':[], 'unknown_clauses':[],
                    'blocked_topics':blocked, 'reason':'source_needs_review'}
        clauses = [s.strip() for s in re.split(r'[，,。？！?!；;\n]|还有|以及|并且', text) if s.strip()]
        for clause in clauses:
            fields = [f for f, words in FIELDS.items() if any(w in clause.lower() for w in words)]
            if 'roof' in fields or 'pole_material' in fields:
                fields = [f for f in fields if f != 'material']
            # 包装尺寸不能当作产品尺寸；外包装重量由包装条目回答。
            if 'packaging' in fields:
                fields = [f for f in fields if f not in ('specifications', 'weight')]
            if fields:
                # 保守白名单：已知属性旁夹带的陌生要求也不能被悄悄忽略。
                remainder = clause.lower()
                tokens = [w for words in FIELDS.values() for w in words]
                tokens += [v.lower() for p in self.products.values() for v in [p['id'], p['name'], p['model'], *p['aliases']]]
                tokens += ['请问', '告诉我', '我想知道', '咨询', '刚才那个', '什么时候', '正常情况下', '这个', '那个', '这款', '那款', '商品', '产品', '什么', '多少', '怎样', '怎么样', '如何', '小时', '天内', '小时内', '支架', '蚊帐', '床帘', '长宽高', '范围', '区别', '是否', '几个', '几面', '带不带', '带', '能不能', '全部', '高度款', '高度', '高款', '高', 'cm', '厘米']
                for token in sorted(tokens, key=len, reverse=True):
                    remainder = remainder.replace(token, '')
                remainder = re.sub(r'[\d\s的是什么有多大吗呢啊呀和与及、能会在内后前不就可以也还好了一下我想要买它您你们店到？?]+', '', remainder)
                if remainder:
                    unknown.append(clause)
            if not fields:
                # 单独出现商品名称/确认词不算一个待答问题。
                remainder = clause
                for p in self.products.values():
                    for token in [p['id'], p['name'], p['model'], *p['aliases']]:
                        remainder = remainder.replace(token, '')
                if remainder.strip(' 我问的是这款那个这个好的嗯呢和与、 ') :
                    unknown.append(clause)
            for field in fields:
                is_store = field in STORE_FIELDS
                owner = self.data['store'] if is_store else self.products.get(product_id, {})
                value = owner.get('facts', {}).get(field)
                if field == 'model' and not value and owner.get('model'):
                    value = owner['model']
                if not value:
                    missing.append(field)
                    continue
                source = f"store.{field}" if is_store else f"product.{product_id}.{field}"
                hits[source] = {'id': source, 'field': field, 'text': value,
                                'product_id': None if is_store else product_id,
                                'kind': 'store_rule' if is_store else ('verified_selling_point' if field == 'selling_points' else 'product_fact'),
                                'updated_at': owner.get('field_updated_at', {}).get(field, owner['updated_at']),
                                'sources': owner.get('sources', {}).get(field, [])}
        return {'status': 'insufficient' if missing or unknown or not hits else 'matched',
                'hits': list(hits.values()), 'missing_fields': sorted(set(missing)), 'unknown_clauses': unknown}
