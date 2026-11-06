"""部署时原子追加知识，保留云端维护者修改；运行前停止应用。"""
import json,os,sys,uuid
from datetime import datetime
from app.config import ROOT
from app.knowledge import Knowledge
from app.faq_admin import FAQStore
from scripts.onboard_catalog import merge


def activate(products_path,package_path):
    products=json.loads(products_path.read_text(encoding='utf-8'))['products']
    rows=json.loads(package_path.read_text(encoding='utf-8'))['records']
    target=ROOT/'data/catalog_products.json'
    value=json.loads(target.read_text(encoding='utf-8')) if target.exists() else {'products':[]}
    ids={p['id'] for p in value['products']}
    for p in products:
        if p['id'] not in ids:value['products'].append(p);ids.add(p['id'])
    backup=target.parent/'backups';backup.mkdir(exist_ok=True)
    if target.exists():(backup/f'catalog-before-{datetime.now():%Y%m%d-%H%M%S}.json').write_bytes(target.read_bytes())
    temp=target.with_name('.catalog-'+uuid.uuid4().hex+'.tmp')
    temp.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');os.replace(temp,target)
    store=FAQStore();doc,_=store.read();updated=merge(doc,rows)
    if updated!=doc:store.persist(updated,lambda d:Knowledge(faq_document=d))
    kb=Knowledge();print(json.dumps({'products':len(kb.products),'records':len(kb.faq.records),
        'new_active':sum(r['status']=='active' for r in rows),'new_review':sum(r['status']=='needs_review' for r in rows)}))

if __name__=='__main__':
    from pathlib import Path
    activate(Path(sys.argv[1]),Path(sys.argv[2]))
