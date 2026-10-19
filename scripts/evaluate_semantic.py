"""独立问法评测；不把这些问题写入索引样例。"""
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from app.config import ROOT
from app.knowledge import Knowledge
from app.semantic import get_semantic

cases=[
 ('杆子容易倒吗','stability'),('能塞进洗衣机里面清洗不','washing'),
 ('插头的线从哪里走','charging_port'),('骨架是啥做成的','pole_material'),
 ('手机有没有地方收着','storage'),('外头说话声音能减小点不','sound_insulation'),
 ('用滚筒洗衣机清洁行不行','washing'),('架子撑得住不',None),
 ('背后的光能挡住不',None),('每天用会不会散架',None),
 ('你吃饭了吗',None),('能开增值税发票吗',None),
 ('可以治疗失眠吗',None),('能挂10斤吗',None),('保证不会倒吗',None),
]
retriever,status=get_semantic(Knowledge())
if not retriever:raise SystemExit('semantic unavailable: '+status)
results=[]
for query,expected in cases:
 start=time.perf_counter();doc,trace=retriever.search(query,'803')
 actual=doc['field'] if doc else None
 results.append({'question':query,'expected':expected,'actual':actual,'passed':actual==expected,
                 'elapsed_ms':round((time.perf_counter()-start)*1000,2),'trace':trace})
report={'backend':status,'model':'paraphrase-multilingual-MiniLM-L12-v2 int8 ONNX',
        'cases':len(results),'passed':sum(r['passed'] for r in results),'results':results,
        'note':'7条期待命中；3条保守阈值拒答观察；5条无关/禁止问题。不是总体准确率。'}
(ROOT/'docs/semantic_evaluation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf8')
print(json.dumps({k:v for k,v in report.items() if k!='results'},ensure_ascii=False))
