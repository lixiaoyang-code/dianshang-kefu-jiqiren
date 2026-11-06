import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from app.scene_rules import CHINA
from app.statistics import StatisticsStore
import test_nets as fixtures


def event(key,status='answered',scene='industry.height',dated=True):
    return {'status':status,'send_to_customer':status in ('answered','clarify'),
            'answer':'测试答复' if status in ('answered','clarify') else '',
            'session':{'session_id':'session'},'debug':{
                'request_id':key,'question':'测试问题','current_product_id':'801',
                'occurred_at':datetime.now(CHINA).isoformat() if dated else None,
                'conditions':{'reception':'presales','stage':'presales'},'reason':'test_reason','elapsed_ms':12,
                'analysis':{'status':'matched' if status=='answered' else 'unrecognized',
                            'intents':[{'id':scene,'name':'测试意图'}] if status=='answered' else []}}}


class StatisticsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.folder=Path(self.temp.name)
        self.store=StatisticsStore(self.folder)

    def tearDown(self):self.temp.cleanup()

    def test_rates_exclude_interactions_duplicates_rag_and_waiting(self):
        for key,status in [('a','answered'),('b','answered'),('c','suppressed'),('d','clarify'),('e','error'),('f','duplicate')]:
            self.store.record(event(key,status))
        self.store.record(event('g',scene='industry.common_greeting'))
        self.store.record({'suggestion':'RAG','send_to_customer':False})
        self.store.record({'event':'waiting','answer':'请稍等'})
        self.store.review('a','correct');self.store.review('b','partial')
        v=self.store.snapshot()
        self.assertEqual(v['counts']['total'],5)
        self.assertEqual(v['rates'],{'response':40.0,'handoff':20.0,'intent':40.0,'accuracy':50.0,'review_coverage':100.0})
        self.assertEqual(v['counts']['duplicates'],1)
        self.assertEqual(v['counts']['errors'],1)
        self.assertEqual(self.store.snapshot(include_interactions=True)['counts']['total'],6)

    def test_import_is_idempotent_and_keeps_review_after_restart(self):
        row=event('old',dated=False)
        (self.folder/'events.jsonl').write_text(json.dumps(row)+'\nmalformed\n'+json.dumps(row)+'\n',encoding='utf-8')
        other=StatisticsStore(self.folder)
        self.assertEqual(other.snapshot()['counts']['total'],0)
        self.assertEqual(other.snapshot(days=0)['counts']['unknown_time'],1)
        other.review('old','correct')
        reopened=StatisticsStore(self.folder)
        self.assertEqual(reopened.snapshot(days=0)['counts']['total'],1)
        self.assertEqual(reopened.snapshot(days=0)['rates']['accuracy'],100.0)

    def test_accuracy_unknown_until_review_and_clear_is_reversible(self):
        self.store.record(event('a'));self.assertIsNone(self.store.snapshot()['rates']['accuracy'])
        self.store.review('a','incorrect');self.assertEqual(self.store.snapshot()['rates']['accuracy'],0)
        self.store.review('a',None);self.assertIsNone(self.store.snapshot()['rates']['accuracy'])
        self.store.record(event('b','clarify'))
        self.assertEqual(self.store.review('b','correct'),'not_answered')
        self.assertEqual(self.store.review('missing','correct'),'missing')

    def test_manual_reception_answer_can_count_both_without_counting_error_as_handoff(self):
        self.store.record(event('a',scene='industry.common_return_request'))
        v=self.store.snapshot()
        self.assertEqual(v['rates']['response'],100)
        self.assertEqual(v['rates']['handoff'],100)
        self.assertEqual(self.store.snapshot(product='802')['counts']['total'],0)
        self.assertEqual(self.store.snapshot(outcome='manual')['record_total'],1)

    def test_pending_processing_survives_restart_without_changing_metrics(self):
        for key,status in [('a','suppressed'),('b','error'),('c','clarify'),('d','answered'),('e','duplicate')]:
            self.store.record(event(key,status))
        before=self.store.snapshot()['rates']
        self.assertEqual(self.store.snapshot(outcome='pending')['record_total'],2)
        self.assertEqual(self.store.process('a',True,'补充问法后复测通过'),'saved')
        restarted=StatisticsStore(self.folder)
        self.assertEqual(restarted.snapshot(outcome='pending')['record_total'],1)
        done=restarted.snapshot(outcome='handled')['records'][0]
        self.assertEqual(done['processing_note'],'补充问法后复测通过')
        self.assertEqual(restarted.snapshot()['rates'],before)
        self.assertEqual(restarted.process('d',True),'not_pending')
        self.assertEqual(restarted.process('missing',True),'missing')
        self.assertEqual(restarted.process('a',False),'saved')
        self.assertEqual(restarted.snapshot(outcome='pending')['record_total'],2)


class StatisticsAPITests(unittest.TestCase):
    setUp=fixtures.NetsTests.setUp
    tearDown=fixtures.NetsTests.tearDown

    def test_unanswered_consultation_can_be_closed_and_reopened(self):
        self.assertEqual(self.client.get('/consultations').status_code,200)
        r=self.client.post('/api/chat',json={'session_id':self.sid,'message':'能拿去养熊猫吗','product_id':'801'}).json()
        rid=r['debug']['request_id']
        queue=self.client.get('/api/statistics?outcome=pending').json()
        self.assertIn(rid,[r['id'] for r in queue['records']])
        self.assertEqual(self.client.post('/api/statistics/processing',json={'request_id':rid,'handled':True}).status_code,200)
        self.assertEqual(self.client.get('/api/statistics?outcome=handled').json()['record_total'],1)
        self.client.post('/api/statistics/processing',json={'request_id':rid,'handled':False})
        self.assertEqual(self.client.get('/api/statistics?outcome=pending').json()['record_total'],1)

    def test_chat_persists_diagnostics_and_review_updates_dashboard(self):
        r=self.client.post('/api/chat',json={'session_id':self.sid,'message':'长宽可以伸缩吗','product_id':'801'}).json()
        rid=r['debug']['request_id']
        self.assertEqual(self.client.get('/statistics').status_code,200)
        for days in (0,1,7,30):
            self.assertEqual(self.client.get('/api/statistics?days='+str(days)).status_code,200)
        v=self.client.get('/api/statistics').json()
        self.assertEqual(v['counts']['responded'],1)
        self.assertIsNone(v['rates']['accuracy'])
        self.assertEqual(self.client.post('/api/statistics/review',json={'request_id':rid,'verdict':'correct'}).status_code,200)
        self.assertEqual(self.client.get('/api/statistics').json()['rates']['accuracy'],100)
        self.client.post(f'/api/sessions/{self.sid}/reset',json={'mode':'memory'})
        self.assertEqual(self.client.get('/api/statistics').json()['counts']['total'],1)
        self.assertEqual(self.client.post('/api/statistics/review',json={'request_id':rid,'verdict':'made-up'}).status_code,422)
        self.assertEqual(self.client.get('/api/statistics?days=-1').status_code,422)
