"""本地神经网络句向量检索，答案仍为知识库原文。"""
import os
import re
import hashlib
import json
import threading
from .config import ROOT
from .scene_rules import row_eligible

SEEDS={
 'stability':['杆子牢不牢','会不会塌','支撑结不结实','支架会晃吗'],
 'sound_insulation':['室友说话能挡住吗','能减轻外面的声音吗','吵不吵'],
 'washing':['能丢洗衣机洗吗','清洁怎么处理','洗涤方式'],
 'pole_material':['杆子是铁的还是塑料的','骨架用什么做的'],
 'pole_diameter':['杆子粗细是多少'],
 'colors':['有哪几种配色','有什么颜色可选'],
 'charging_port':['手机充电怎么走线','电源线怎么穿进去'],
 'storage':['手机放哪里','里面有小袋子吗'],
 'bottom':['下面有没有底','底下封不封住'],
 'shade_sides':['四面五面区别','背面有帘子吗'],
 'roof':['顶上是什么面料'],
 'telescoping':['大小能调吗','能不能调整长宽高'],
 'instructions':['装起来麻不麻烦','安装费不费劲'],
 'coating':['遮光帘有没有涂层'],
 'specifications':['这款多大的'],
}
_MODEL=None
_CACHE={}
_LOCK=threading.Lock()

class Encoder:
    def __init__(self):
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np=np
        options=ort.SessionOptions();options.intra_op_num_threads=2
        self.session=ort.InferenceSession(str(ROOT/'models/minilm/model.onnx'),options,providers=['CPUExecutionProvider'])
        self.tokenizer=Tokenizer.from_file(str(ROOT/'models/minilm/tokenizer.json'))
        self.tokenizer.enable_truncation(max_length=128)
        self.tokenizer.enable_padding(pad_id=1,pad_token='<pad>')

    def encode(self,texts):
        np=self.np;result=[]
        for start in range(0,len(texts),16):
            encoded=self.tokenizer.encode_batch(texts[start:start+16])
            values={'input_ids':np.array([e.ids for e in encoded],dtype=np.int64),
                    'attention_mask':np.array([e.attention_mask for e in encoded],dtype=np.int64),
                    'token_type_ids':np.array([e.type_ids for e in encoded],dtype=np.int64)}
            inputs={v.name:values[v.name] for v in self.session.get_inputs()}
            tokens=self.session.run(None,inputs)[0]
            mask=values['attention_mask'][...,None]
            pooled=(tokens*mask).sum(axis=1)/np.maximum(mask.sum(axis=1),1)
            pooled/=np.maximum(np.linalg.norm(pooled,axis=1,keepdims=True),1e-9)
            result.extend(pooled.tolist())
        return np.array(result,dtype=np.float32)

class SemanticRetriever:
    def __init__(self,kb,encoder):
        self.kb=kb;self.encoder=encoder;self.docs=[];self.texts=[];self.owners=[]
        self.threshold=float(os.getenv('SEMANTIC_MIN_SCORE','0.68'))
        self.margin=float(os.getenv('SEMANTIC_MIN_MARGIN','0.07'))
        self.top_k=int(os.getenv('SEMANTIC_TOP_K','5'))
        for pid,p in kb.products.items():
            for field,seeds in SEEDS.items():
                if field not in p['facts'] or (field=='telescoping' and pid=='801'):
                    continue
                answer=p.get('short_replies',{}).get(field) or p['facts'][field]
                # 指定话术直接保留；其余使用现有固定短答，不让检索器写话术。
                if not answer.startswith(('亲','稳固','有的')):answer='亲亲，'+answer.rstrip('。')+'～'
                doc={'id':f'product.{pid}.{field}','product_id':pid,'field':field,'answer':answer,'sources':p.get('sources',{}).get(field,[])}
                configured=next((r for r in kb.faq.records if r['id']==doc['id']),None)
                if configured and configured['status']!='active': continue
                idx=len(self.docs);self.docs.append(doc)
                aliases=[a for r in kb.qa_records if r['product_id']==pid and r['status']=='active' and r['fields']==[field] for a in r['aliases']]
                faq = next((r for r in kb.faq.records if r['id']==doc['id']), None)
                if faq:
                    doc.update(answer=faq['standard_answer'], images=faq['images'])
                    aliases += faq['question_variants']
                for text in list(dict.fromkeys([*seeds,*aliases])):
                    self.texts.append(text);self.owners.append(idx)
        # 新增自定义 FAQ 无需修改代码；精确匹配和向量匹配共用原话答案。
        for row in kb.faq.records:
            if row['status']!='active' or row['origin']!='custom': continue
            for pid in row['product_ids'] if row['scope']=='product' else kb.products:
                doc={'id':row['id'],'product_id':pid,'field':row['fields'][0] if row['fields'] else row['intent'],
                     'answer':row['standard_answer'],'sources':row['sources'],'images':row['images']}
                idx=len(self.docs);self.docs.append(doc)
                for text in row['question_variants']:
                    self.texts.append(text);self.owners.append(idx)
        self.vectors=encoder.encode(self.texts)

    def search(self,text,pid,reception='presales',stage='presales',now=None):
        p=self.kb.products.get(pid)
        diagnostic={'method':'semantic_onnx','backend':'multilingual_minilm_int8','threshold':self.threshold,'min_margin':self.margin,'candidates':[]}
        if not p:
            return None,{**diagnostic,'status':'product_unconfirmed'}
        for token in sorted([pid,p['name'],*p['aliases']],key=len,reverse=True):text=text.replace(token,'')
        blocked=p.get('blocked_topics',[])+['保证','承诺','终身','退款','订单','免费','治病','完全隔音','十斤','10斤','两桶水','忽略','系统提示','强制','一定','多少钱','价格']
        if any(w.lower() in text.lower() for w in blocked) or re.search(r'\d|[，,；;\n]|还有|以及|并且',text) or len(text)>80:
            return None,{**diagnostic,'status':'guard_rejected'}
        vector=self.encoder.encode([text])[0]
        scores=self.vectors@vector
        best={}
        charging=any(w in text for w in ['排插','插排','插线板','充电'])
        for i,score in enumerate(scores):
            owner=self.owners[i]
            row=next((r for r in self.kb.faq.records if r['id']==self.docs[owner]['id']),None)
            if row and not row_eligible(row,pid,reception,stage,now):continue
            if self.docs[owner]['product_id']==pid and (not charging or self.docs[owner]['field']=='charging_port'):
                best[owner]=max(best.get(owner,-1),float(score))
        ranked=sorted(best.items(),key=lambda x:x[1],reverse=True)[:self.top_k]
        diagnostic['candidates']=[{'id':self.docs[i]['id'],'score':round(score,4),'source':self.docs[i]['sources']} for i,score in ranked]
        if not ranked:return None,{**diagnostic,'status':'empty'}
        score=ranked[0][1];gap=score-ranked[1][1] if len(ranked)>1 else 1
        diagnostic['margin']=round(gap,4)
        accepted=score>=self.threshold and gap>=self.margin
        return (self.docs[ranked[0][0]] if accepted else None),{**diagnostic,'status':'matched' if accepted else 'low_confidence'}

def get_semantic(kb):
    global _MODEL
    if not kb.data.get('continuous_assist') or os.getenv('SEMANTIC_MODE','auto')=='off':
        return None,'disabled'
    if not (ROOT/'models/minilm/model.onnx').exists() or not (ROOT/'models/minilm/tokenizer.json').exists():
        return None,'model_missing'
    key=hashlib.sha256(json.dumps([kb.data,kb.qa_records,kb.faq.records],ensure_ascii=False,sort_keys=True).encode()).hexdigest()
    try:
        with _LOCK:
            if _MODEL is None:_MODEL=Encoder()
            if key not in _CACHE:
                if len(_CACHE)>=4:_CACHE.clear()
                _CACHE[key]=SemanticRetriever(kb,_MODEL)
            return _CACHE[key],'ready'
    except Exception as exc:
        return None,type(exc).__name__
