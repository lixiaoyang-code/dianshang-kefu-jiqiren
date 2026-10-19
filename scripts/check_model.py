"""主动运行才调用真实接口；不打印密钥、请求头或异常正文。"""
import asyncio
import json
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.config import ROOT, Settings
from app.model import Model

async def main():
    settings=Settings()
    if settings.mock:
        print('Mock mode: no real API call.');return
    model=Model(settings)
    # 联网冒烟测试只用虚构数据，不导出实际知识库。
    candidates=[{'id':'demo.stability','question_topic':'stability','answer':'测试商品A的支架稳固。'},
                {'id':'demo.color','question_topic':'colors','answer':'测试商品A有绿色。'}]
    results=[]
    for question,pid,expected in [('架子撑得住不','801','stability'),
                                  ('你吃饭了吗','801',None)]:
        start=time.perf_counter()
        row={'question':question,'product_id':pid,'expected_intent':expected}
        try:
            answer_id,status=await model.understand(question,[],candidates)
            chosen=next((c for c in candidates if c['id']==answer_id),None)
            row.update(status=status,answer_id=answer_id,
                answer=chosen['answer'] if chosen else '',
                passed=(chosen is None and status=='skip') if expected is None else
                    chosen is not None and chosen['question_topic']==expected)
        except Exception as exc:
            row.update(status='failed',error_type=type(exc).__name__,passed=False)
        row['elapsed_ms']=round((time.perf_counter()-start)*1000)
        results.append(row)
    report={'model':settings.model,'provider':settings.provider,'data_scope':'synthetic_faq_only','cases':results,
            'passed':sum(r['passed'] for r in results),'total':len(results)}
    (ROOT/'docs/model_connection_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=True,indent=2))

if __name__=='__main__':asyncio.run(main())
