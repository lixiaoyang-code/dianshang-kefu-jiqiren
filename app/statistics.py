"""从诊断结果持久化统计；人工评价与命中结果分开保存。"""
import json
import sqlite3
from contextlib import contextmanager
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from .scene_rules import CHINA
from .common_intents import EXTRA

INTERACTIONS = {'industry.affirmation', 'industry.common_greeting', 'industry.common_thanks', 'industry.common_goodbye', 'industry.common_purchase_confirmation'}
MANUAL_SCENES = {'industry.common_' + v for v in ('tracking', 'returns_policy', 'return_request', 'exchange_request', 'damaged')}
MANUAL_SCENES.update('industry.common_'+v for v in EXTRA)


class StatisticsStore:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.path = self.folder / 'statistics.sqlite3'
        self.folder.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.execute('''CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY, occurred_at TEXT, session_id TEXT, product_id TEXT,
                reception TEXT, stage TEXT, question TEXT, answer TEXT, status TEXT,
                recognized INTEGER, responded INTEGER, manual INTEGER, interaction INTEGER,
                reason TEXT, intent TEXT, method TEXT, elapsed REAL,
                review TEXT, reviewed_at TEXT)''')
            db.execute('''CREATE TABLE IF NOT EXISTS processing (
                request_id TEXT PRIMARY KEY, handled_at TEXT, note TEXT)''')
        self.import_logs()

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path, timeout=5)
        try:
            with db:yield db
        finally:db.close()

    def import_logs(self):
        # request_id 去重；无时间的旧日志不虚构日期，也不统计事件/等待提示/RAG。
        with self.connect() as db:
            for path in sorted(self.folder.glob('events.jsonl*')):
                if not path.is_file():continue
                with path.open(encoding='utf-8', errors='replace') as stream:
                    for line in stream:
                        try:self.record(json.loads(line), db)
                        except (ValueError, TypeError, AttributeError):continue

    def record(self, result, connection=None):
        debug = result.get('debug') or {}
        request_id = debug.get('request_id')
        question = debug.get('question')
        if not request_id or not isinstance(question, str):return
        analysis = debug.get('analysis') or {}
        scenes = analysis.get('intents') or []
        ids = {s.get('id') for s in scenes}
        status = result.get('status', '')
        session = result.get('session') or {}
        conditions = debug.get('conditions') or {}
        row = (request_id, debug.get('occurred_at'), session.get('session_id'), debug.get('current_product_id'),
               conditions.get('reception'), conditions.get('stage'), question[:2000], (result.get('answer') or '')[:12000], status,
               int(analysis.get('status') == 'matched'), int(status == 'answered' and bool(result.get('send_to_customer'))),
               int(status in ('suppressed', 'handoff') or bool(ids & MANUAL_SCENES)),
               int(bool(ids & INTERACTIONS)), debug.get('reason') or '',
               ' / '.join(s.get('name','') for s in scenes), (debug.get('retrieval') or {}).get('method',''),
               float(debug.get('elapsed_ms') or 0))
        sql='INSERT OR IGNORE INTO messages VALUES (' + ','.join('?' for _ in row) + ',NULL,NULL)'
        if connection is not None:connection.execute(sql,row)
        else:
            with self.connect() as db:db.execute(sql,row)

    def review(self, request_id, verdict):
        with self.connect() as db:
            row = db.execute('SELECT responded FROM messages WHERE id=?', (request_id,)).fetchone()
            if row is None:return 'missing'
            if not row[0]:return 'not_answered'
            db.execute('UPDATE messages SET review=?, reviewed_at=? WHERE id=?',
                       (verdict, datetime.now(CHINA).isoformat(), request_id))
        return 'saved'

    def process(self, request_id, handled, note=''):
        with self.connect() as db:
            row=db.execute('SELECT status,responded FROM messages WHERE id=?',(request_id,)).fetchone()
            if row is None:return 'missing'
            if row[1] or row[0] not in ('suppressed','handoff','error'):return 'not_pending'
            if handled:
                db.execute('INSERT OR REPLACE INTO processing VALUES (?,?,?)',
                           (request_id,datetime.now(CHINA).isoformat(),note.strip()[:500]))
            else:db.execute('DELETE FROM processing WHERE request_id=?',(request_id,))
        return 'saved'

    def snapshot(self, days=7, product='', include_interactions=False, outcome='', page=1):
        clauses, args = [], []
        if days:
            since=(datetime.now(CHINA).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=days-1)).isoformat()
            clauses.append('occurred_at>=?');args.append(since)
        if product:clauses.append('product_id=?');args.append(product)
        if not include_interactions:clauses.append('interaction=0')
        where=' WHERE '+' AND '.join(clauses) if clauses else ''
        with self.connect() as db:
            db.row_factory=sqlite3.Row
            rows=[dict(r) for r in db.execute('SELECT * FROM messages'+where+' ORDER BY occurred_at DESC, rowid DESC',args)]
            handled={r['request_id']:dict(r) for r in db.execute('SELECT * FROM processing')}
        for r in rows:
            r['handled_at']=handled.get(r['id'],{}).get('handled_at')
            r['processing_note']=handled.get(r['id'],{}).get('note','')
            r['pending']=bool(not r['responded'] and r['status'] in ('suppressed','handoff','error') and not r['handled_at'])
        valid=[r for r in rows if r['status']!='duplicate']
        total=len(valid)
        reviewed=[r for r in valid if r['responded'] and r['review']]
        rate=lambda n,d:round(100*n/d,1) if d else None
        reviewed_correct=sum(r['review']=='correct' for r in reviewed)
        counts={'total':total, 'all_records':len(rows), 'duplicates':len(rows)-total,
                'responded':sum(r['responded'] for r in valid),'recognized':sum(r['recognized'] for r in valid),
                'manual':sum(r['manual'] for r in valid),'errors':sum(r['status']=='error' for r in valid),
                'clarifications':sum(r['status']=='clarify' for r in valid),'reviewed':len(reviewed),
                'correct':reviewed_correct,'partial':sum(r['review']=='partial' for r in reviewed),
                'incorrect':sum(r['review']=='incorrect' for r in reviewed),
                'unknown_time':sum(not r['occurred_at'] for r in rows),
                'pending':sum(r['pending'] for r in rows),'handled':sum(bool(r['handled_at']) for r in rows)}
        rates={'response':rate(counts['responded'],total),'handoff':rate(counts['manual'],total),
               'intent':rate(counts['recognized'],total),'accuracy':rate(reviewed_correct,len(reviewed)),
               'review_coverage':rate(len(reviewed),counts['responded'])}
        previous_rates={}
        if days:
            previous_start=datetime.now(CHINA).replace(hour=0,minute=0,second=0,microsecond=0)-timedelta(days=days*2-1)
            previous_end=previous_start+timedelta(days=days)
            previous_clauses=['occurred_at>=?','occurred_at<?'];previous_args=[previous_start.isoformat(),previous_end.isoformat()]
            if product:previous_clauses.append('product_id=?');previous_args.append(product)
            if not include_interactions:previous_clauses.append('interaction=0')
            with self.connect() as db:
                prev=[dict(r) for r in db.execute('SELECT * FROM messages WHERE '+' AND '.join(previous_clauses),previous_args)]
            prev=[r for r in prev if r['status']!='duplicate']
            previous_rates={'response':rate(sum(r['responded'] for r in prev),len(prev)),
                            'handoff':rate(sum(r['manual'] for r in prev),len(prev)),
                            'intent':rate(sum(r['recognized'] for r in prev),len(prev))}
        trend={}
        for r in valid:
            if not r['occurred_at']:continue
            day=r['occurred_at'][:10]
            v=trend.setdefault(day,{'day':day,'total':0,'responded':0,'manual':0})
            v['total']+=1;v['responded']+=r['responded'];v['manual']+=r['manual']
        reasons=Counter(r['reason'] for r in valid if r['manual'] or r['status']=='error')
        filtered=[r for r in rows if not outcome or (outcome=='manual' and r['manual']) or
                  (outcome=='unreviewed' and r['responded'] and not r['review']) or
                  (outcome=='error' and r['status']=='error') or
                  (outcome=='pending' and r['pending']) or (outcome=='handled' and r['handled_at'])]
        start=(page-1)*30
        return {'counts':counts,'rates':rates,'trend':sorted(trend.values(),key=lambda x:x['day'])[-31:],
                'reasons':[{'reason':k,'count':v} for k,v in reasons.most_common(8)],
                'records':filtered[start:start+30], 'record_total':len(filtered),'page':page,
                'scope':'按客户消息统计；排除重复抑制，默认排除问候等互动。转人工指系统判定需人工处理，非实际接管。',
                'previous_rates':previous_rates,
                'accuracy_note':'准确率仅基于已人工评价的业务答复；部分正确不计为正确。RAG和等待提示不计应答。'}
