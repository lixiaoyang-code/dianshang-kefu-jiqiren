"""补齐互动路由所需问法与选购追问，保留现有答案和待审核资料。"""
import copy
from app.common_intents import VARIANTS
from app.faq_admin import FAQStore
from app.knowledge import Knowledge
from scripts.onboard_catalog import record


def migrate(document):
    doc=copy.deepcopy(document)
    for key in ['thanks','goodbye']:
        sid='industry.common_'+key
        scene=next(s for s in doc['scenes'] if s['id']==sid)
        scene['question_variants']=list(dict.fromkeys(scene['question_variants']+VARIANTS[key]))
        for row in doc['records']:
            if row['scene_id']==sid:row['question_variants']=scene['question_variants'][:]
    ack=next(r for r in doc['records'] if r['id']=='store.affirmation')
    if ack.get('conditions',{}).get('reception')=='presales' and ack['conditions'].get('stages')==['presales']:
        ack['conditions'].update(reception='all',stages=[])
    rid='catalog.cloudquilt.weight_selection'
    if not any(r['id']==rid for r in doc['records']):
        row=record('cloudquilt','weight_selection','被子选几斤合适？',
            ['几斤合适','买几斤合适','几斤比较合适','推荐几斤','选多重合适','买几斤'],
            '亲亲，选几斤需要结合被子尺寸、使用季节和室温哈～您准备哪个季节盖、室温大概多少度？也请告诉我被子的尺寸和是否有暖气，先确认这些条件再选会更合适。')
        row['boundaries']['requires_clarification']=True
        row['sources']=[{'type':'workflow_template','date':'2026-11-05','excerpt':'根据客户反馈补充选购条件追问；具体斤数、温度对应表仍需商家审核，不使用待审核的推荐数值。'}]
        doc['records'].append(row)
        doc['scenes'].append({'id':row['scene_id'],'name':row['scene_name'],'type':'industry',
            'category':row['category'],'configured':True,'question_variants':row['question_variants'],
            'description':'客户未提供选购条件时先追问季节、室温、尺寸与暖气情况，不直接承诺具体斤数。'})
    return doc


if __name__=='__main__':
    store=FAQStore();doc,_=store.read();updated=migrate(doc)
    if updated!=doc:store.persist(updated,lambda d:Knowledge(faq_document=d))
    print('Applied closing and quilt clarification; pending reference answers remain pending.')
