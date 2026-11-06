"""新增可维护的肯定互动 FAQ；重复执行不覆盖维护者修改。"""
import copy
import json
from datetime import datetime
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VARIANTS=['好的','好哒','好滴','明白了','知道了','了解了','收到','嗯嗯','好','OK']


def migrate(document):
    doc=copy.deepcopy(document)
    scene_id='industry.affirmation'
    if not any(s['id']==scene_id for s in doc['scenes']):
        doc['scenes'].append({'id':scene_id,'name':'肯定／已了解','type':'industry','category':'聊天互动',
            'question_variants':VARIANTS,'configured':True,
            'description':'仅识别独立的肯定、已了解回应；带有后续问题时处理实际问题，带问号或质疑不当作肯定。不表示选择商品或执行订单操作。'})
    if not any(r['id']=='store.affirmation' for r in doc['records']):
        doc['records'].append({'id':'store.affirmation','intent':'affirmation','scene_id':scene_id,
            'scene_name':'肯定／已了解','scene_type':'industry','category':'聊天互动',
            'question_variants':VARIANTS,'standard_answer':'💗','answer_parts':['💗'],
            'scope':'store','product_ids':[],'answer_product_id':None,'fields':['affirmation'],
            'status':'active','configured_scene':True,'origin':'user_confirmation','images':[],
            'conditions':{'reception':'presales','stages':['presales'],'valid_from':None,'valid_until':None},
            'keywords':[],'keyword_mode':'any','priority':0,'updated_at':'2026-10-22',
            'sources':[{'type':'user_confirmation','date':'2026-10-22','excerpt':'表示肯定的可以回复一个💗'}],
            'boundaries':{'no_extra_promises':True,'no_order_operations':True,'unsupported':'operator_only_no_customer_reply'}})
    return doc


if __name__=='__main__':
    path=ROOT/'data/faq.json'
    document=json.loads(path.read_text(encoding='utf-8'))
    updated=migrate(document)
    if updated!=document:
        backup=path.parent/'backups';backup.mkdir(exist_ok=True)
        (backup/f'faq-before-affirmation-{datetime.now():%Y%m%d-%H%M%S-%f}.json').write_bytes(path.read_bytes())
        path.write_text(json.dumps(updated,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print('Added affirmation FAQ')
    else: print('Already configured')
