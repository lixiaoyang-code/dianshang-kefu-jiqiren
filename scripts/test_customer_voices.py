"""原声离线基线：隔离日志、脱敏、保留原始行号，不将表内话术当标准答案。"""
import argparse, asyncio, csv, json, re, time
from collections import Counter
from pathlib import Path
from app.config import Settings, ROOT
from app.knowledge import Knowledge
from app.model import Model
from app.service import Service

PRESALES={'黄伟龙','李凯迪','李志强','刘薇','李晓洋'}

def redact(text):
    text=str(text or '')
    text=re.sub(r'(?<!\d)1[3-9]\d{9}(?!\d)','[手机号]',text)
    text=re.sub(r'(?<!\d)\d{17}[\dXx](?!\d)','[证件号]',text)
    text=re.sub(r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}','[邮箱]',text)
    text=re.sub(r'https?://\S+','[链接]',text)
    text=re.sub(r'(?:sk-|ark-)[A-Za-z0-9_-]+','[密钥]',text)
    return text.strip()

def prepare(sheets):
    rows=[]
    catalog_path=ROOT/'data/catalog_products.json'
    catalog=json.loads(catalog_path.read_text(encoding='utf-8'))['products'] if catalog_path.exists() else []
    names={p['name']:p['id'] for p in catalog}
    for sheet in sheets:
        header={re.sub(r'\d','',k):v for k,v in sheet['rows'][0].items()}
        def col(name):return next((k for k,v in header.items() if v==name),None)
        for raw in sheet['rows'][1:]:
            d={re.sub(r'\d','',k):v for k,v in raw.items()}
            q=redact(d.get(col('客户原声'),''))
            if not q:continue
            person=d.get(col('人员'),'').strip()
            if person:
                reception='presales' if person in PRESALES else 'aftersales';basis='用户指定人员规则'
            elif '售前' in sheet['name']:
                reception='presales';basis='无人员：按表名推断'
            elif '售后' in sheet['name']:
                reception='aftersales';basis='无人员：按表名推断'
            else:
                reception='aftersales' if re.search(r'收到|退货|退款|破损|漏发|换货',q) else 'presales';basis='无人员：按内容推断，待核实'
            product=' '.join(d.get(col(k),'') for k in ['产品名称','产品名称1']).strip()
            owners=sorted(set(re.findall(r'(?<!\d)80[1-4](?!\d)',product)))
            explicit=sorted(set(re.findall(r'(?<!\d)80[1-4](?!\d)',q)))
            pid=explicit[0] if len(explicit)==1 else owners[0] if len(owners)==1 else None
            domain='四款蚊帐' if owners else '商品未确定' if not product else '未接入商品'
            if product in names:
                pid=names[product];owners=[pid];domain='新增商品'
            stage='presales' if reception=='presales' else 'aftersales'
            if reception=='aftersales' and re.search(r'未收货|发货中',d.get(col('收货状态'),'')):stage='shipping'
            elif reception=='aftersales' and re.search(r'已收货',d.get(col('收货状态'),'')):stage='received'
            rows.append({'source_sheet':sheet['name'],'source_row':int(re.search(r'\d+',next(iter(raw))).group()),
                'person':person or '未标注','classification_basis':basis,'reception':reception,'stage':stage,
                'product':product,'product_ids':owners,'selected_product':pid,'domain':domain,'question':q,
                'source_intent':d.get(col('匹配场景'),''),'reference_answer':redact(d.get(col('话术'),'')),
                'classification_conflict':bool(person and (('售前' in sheet['name'] and reception=='aftersales') or ('售后' in sheet['name'] and reception=='presales')))})
    return rows

class OfflineModel(Model):
    async def understand(self,*args):return None,'not_run_offline'
    async def select(self,*args):return {'action':'handoff','evidence_ids':[]},'not_run_offline'

async def evaluate(source,output):
    rows=prepare(json.loads(source.read_text(encoding='utf-8')))
    output.mkdir(parents=True,exist_ok=True)
    svc=Service(Knowledge(),OfflineModel(Settings(mode='api',key='',intent_enabled=False)),ROOT/'logs/customer-voices/evaluation-runtime')
    cache={};results=[];start=time.time()
    try:
        for i,row in enumerate(rows):
            key=(row['question'],row['selected_product'],row['reception'],row['stage'])
            if key not in cache:
                session=svc.create()
                r=await svc.chat(session.session_id,row['question'],row['selected_product'],row['reception'],row['stage'])
                a=r['debug'].get('analysis') or {}
                cache[key]={'status':r['status'],'answer':r['answer'],'responded':r['status']=='answered' and r['send_to_customer'],
                    'recognized':a.get('status')=='matched','identified_intent':' / '.join(v['name'] for v in a.get('intents',[])),
                    'reason':r['debug'].get('reason'),'method':(r['debug'].get('retrieval') or {}).get('method'),
                    'elapsed_ms':r['debug']['elapsed_ms'],'gold_accuracy':None}
                svc.sessions.pop(session.session_id,None);svc.locks.pop(session.session_id,None)
            results.append({**row,**cache[key]})
            if (i+1)%500==0:print(json.dumps({'processed':i+1,'total':len(rows),'unique_cases':len(cache)},ensure_ascii=False),flush=True)
    finally:
        for h in svc.logger.handlers:h.close()
    def cohort(values):
        n=len(values)
        return {'rows':n,'responded':sum(v['responded'] for v in values),'recognized':sum(v['recognized'] for v in values),
            'response_rate':round(100*sum(v['responded'] for v in values)/n,2) if n else None,
            'intent_rate':round(100*sum(v['recognized'] for v in values)/n,2) if n else None,
            'statuses':dict(Counter(v['status'] for v in values)),'reasons':dict(Counter(v['reason'] for v in values))}
    summary={'total':len(rows),'unique_cases':len(cache),'seconds':round(time.time()-start,1),'semantic':svc.semantic_status,
        'model':'未调用大模型；FAQ/规则/本地向量检索基线，不等同公网完整表现','accuracy':None,
        'accuracy_note':'参考意图与参考话术未经核验，不当作金标准；准确率待人工复核。',
        'overall':cohort(results),'receptions':{k:cohort([r for r in results if r['reception']==k]) for k in ['presales','aftersales']},
        'domains':{k:cohort([r for r in results if r['domain']==k]) for k in sorted({r['domain'] for r in rows})},
        'sheets':{k:cohort([r for r in results if r['source_sheet']==k]) for k in sorted({r['source_sheet'] for r in rows})},
        'classification_sources':dict(Counter(r['classification_basis'] for r in rows)),
        'classification_conflicts':sum(r['classification_conflict'] for r in rows)}
    (output/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'results.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in results),encoding='utf-8')
    fields=['source_sheet','source_row','person','classification_basis','classification_conflict','reception','stage','product','selected_product','domain','question','status','responded','recognized','identified_intent','reason','method','answer','source_intent','reference_answer']
    with (output/'逐条测试结果.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');writer.writeheader()
        for r in results:
            # 防止 CSV 被表格软件当公式执行。
            writer.writerow({k:("'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v) for k,v in r.items() if k in fields})
    print(json.dumps(summary,ensure_ascii=False),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT/'logs/customer-voices/parsed-sheets.json');p.add_argument('--output',type=Path,default=ROOT/'outputs/customer-voice-tests/2026-11-05');a=p.parse_args();asyncio.run(evaluate(a.source,a.output))
