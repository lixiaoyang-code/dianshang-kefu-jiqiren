"""分开遮光效果与帘子结构，补充已遇到的全伸缩推荐原话；不改商家话术。"""
import copy
import json
from datetime import datetime
from pathlib import Path


def migrate(document):
    doc=copy.deepcopy(document)
    scenes={s['id']:s for s in doc['scenes']}
    key='industry.light_blocking'
    moved=[r for r in doc['records'] if r['standard_answer']=='可以遮光的亲，也能遮挡隐私哈～']
    variants=['可以遮光吗？','能遮住光吗','能遮光吗','遮光效果怎么样','遮光效果好吗','遮光好吗','遮光吗']
    variants += [q for r in moved for q in r['question_variants']]
    variants=list(dict.fromkeys(variants))
    scenes[key]={**scenes.get(key,{}),'id':key,'name':'可以遮光吗？','type':'industry','category':'购买疑虑',
        'description':'询问是否遮光、能否遮挡隐私；四面五面的帘子结构差异单独回答。','question_variants':variants}
    for row in moved:
        row.update(scene_id=key,scene_name=scenes[key]['name'],intent='light_blocking',configured_scene=True,
                   question_variants=variants)
    def canonical(text):
        return ''.join(c for c in text if c not in '，。？！?！～~、：: \n')
    light={canonical(v) for v in variants}
    for scene in scenes.values():
        if scene['id']=='industry.shade_sides':
            scene['question_variants']=[q for q in scene['question_variants'] if canonical(q) not in light]
    for row in doc['records']:
        if row['scene_id']=='industry.shade_sides':
            row['question_variants']=[q for q in row['question_variants'] if canonical(q) not in light]
        if row['id']=='catalog.full_stretch':
            for q in ['有全伸缩的支架吗','有没有全伸缩的支架']:
                if q not in row['question_variants']:row['question_variants'].append(q)
                scene=scenes[row['scene_id']]
                if q not in scene['question_variants']:scene['question_variants'].append(q)
    doc['scenes']=list(scenes.values())
    return doc

if __name__=='__main__':
    path=Path(__file__).resolve().parents[1]/'data/faq.json'
    raw=path.read_bytes();doc=migrate(json.loads(raw))
    output=(json.dumps(doc,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    if output!=raw:
        backups=path.parent/'backups';backups.mkdir(exist_ok=True)
        (backups/f'faq-before-routing-{datetime.now():%Y%m%dT%H%M%S}.json').write_bytes(raw)
        path.write_bytes(output)
    print(len(doc['scenes']),len(doc['records']))
