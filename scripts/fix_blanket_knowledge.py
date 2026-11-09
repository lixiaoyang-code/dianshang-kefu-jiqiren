"""Retire nonwoven knowledge and repair existing plush FAQ entry points.

Reads the current persistent files at apply time. Never replaces cloud knowledge
with a development copy, and never converts nonwoven-only facts into plush facts.
"""
import copy
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

RETIRED = 'nonwovenblanket'
MARKER = 'retire_nonwoven_20261108'
VARIANTS = {
    'industry.catalog_draft_b37f9850a485': [
        '电热毯有几个档位？', '有几个档位', '几个档位', '有多少档位', '多少个档位',
        '有几档', '几档', '有多少档', '一共几档', '档位'],
    'industry.personal_blanket_warranty': [
        '质保多久', '保修多久', '质保多长时间', '保修多长时间', '有质保吗', '有保修吗',
        '质保几年', '质保政策', '保修政策', '电热毯质保多久'],
    'industry.catalog_draft_858deb6d3ede': ['多重', '有多重', '重量多少', '几斤重', '电热毯多重'],
    'industry.personal_cable': ['电源线多长', '电线多长', '线有多长', '电源线长度'],
    'industry.personal_power': ['最大功率多少', '功率多大', '额定功率多少'],
    'industry.personal_blanket_wash': ['怎么洗', '能机洗吗', '可以机洗吗', '能水洗吗'],
}


def migrate(document, materials, stamp=None):
    doc, rag = copy.deepcopy(document), copy.deepcopy(materials)
    stamp = stamp or datetime.now(timezone.utc).isoformat()
    changes = {'qa_retired': [], 'materials_removed': [], 'shared_unbound': [],
               'variants_added': {}, 'updated': [], 'scenes_retired': []}
    for row in doc['records']:
        pids = row.get('product_ids', [])
        if RETIRED not in pids or row.get('deleted_at'):
            continue
        if set(pids) == {RETIRED}:
            row.update(status='disabled', deleted_at=stamp, deleted_by=MARKER, updated_at=stamp)
            changes['qa_retired'].append(row['id'])
        else:
            row['product_ids'] = [p for p in pids if p != RETIRED]
            if row.get('answer_product_id') == RETIRED:
                row['answer_product_id'] = row['product_ids'][0]
            row['updated_at'] = stamp
            changes['shared_unbound'].append(row['id'])
    for row in rag['documents']:
        pids = row.get('product_ids', [])
        if RETIRED not in pids:
            continue
        if set(pids) == {RETIRED}:
            changes['materials_removed'].append(row['id'])
        else:
            row['product_ids'] = [p for p in pids if p != RETIRED]
            row['updated_at'] = stamp
            changes['shared_unbound'].append(row['id'])
    # The full original file is backed up before apply; retired material cards
    # disappear from the working library rather than lingering as disabled items.
    rag['documents'] = [r for r in rag['documents'] if r['id'] not in changes['materials_removed']]
    scenes = {s['id']: s for s in doc['scenes']}
    for sid, variants in VARIANTS.items():
        scene = scenes.get(sid)
        if not scene or scene.get('deleted_at'):
            continue
        old = scene.get('question_variants', [])
        new = list(dict.fromkeys([*old, *variants]))
        if new != old:
            scene['question_variants'] = new
            changes['variants_added'][sid] = len(new) - len(old)
            for row in doc['records']:
                if row['scene_id'] == sid and not row.get('deleted_at'):
                    row.update(question_variants=new, updated_at=stamp)
    # "档位" asks for the count; detailed temperature remains a separate intent.
    temp_scene = scenes.get('industry.catalog_draft_17812ec8bdc1')
    if temp_scene and '档位' in temp_scene.get('question_variants', []):
        temp_scene['question_variants'].remove('档位')
        for row in doc['records']:
            if row['scene_id'] == temp_scene['id']:
                row['question_variants'] = temp_scene['question_variants'][:]
        changes['updated'].append(temp_scene['id'])
    # This approved 3C answer was attached to an insurance question during import.
    cert = next((r for r in doc['records'] if r['id'] == 'personal.blanket_3c.95'
                 and not r.get('deleted_at')), None)
    if cert and cert['scene_id'] != 'industry.plushblanket_3c':
        sid = 'industry.plushblanket_3c'
        qs = ['电热毯有3C认证吗？', '有3C认证吗', 'CCC证书有吗']
        scene = {'id': sid, 'name': qs[0], 'type': 'industry', 'category': '商品参数',
                 'question_variants': qs, 'configured': True,
                 'description': '仅识别3C认证；不回答保险承保或产品疗效。'}
        if sid not in scenes:
            doc['scenes'].append(scene)
        cert.update(scene_id=sid, scene_name=qs[0], question_variants=qs, updated_at=stamp)
        changes['updated'].append(cert['id'])
    # Stop recommending a product that has been retired; no conversion of its facts.
    recommendation = next((r for r in doc['records']
                           if r['id'] == 'catalog.plushblanket.draft_da309b79ffc8'
                           and not r.get('deleted_at')), None)
    if recommendation and '无纺布' in recommendation['standard_answer']:
        answer = '亲亲，目前提供的是长毛绒面料电热毯哦～'
        recommendation.update(standard_answer=answer, answer_parts=[answer], updated_at=stamp)
        changes['updated'].append(recommendation['id'])
    # Two plush sources disagree on temperature (30-58 vs around 50). Retain only
    # their common confirmed fact here; keep the detailed original for audit/backup.
    temperature = next((r for r in rag['documents']
                        if r['id'] == 'personal.material.temperature.99'), None)
    if temperature and temperature['status'] == 'active' and '58' in temperature['content']:
        temperature.update(title='电热毯有几个档位？',
                           content='亲亲，这款电热毯支持12档调节；具体温度请以控制器说明和实际使用环境为准。',
                           updated_at=stamp)
        changes['updated'].append(temperature['id'])
    retired_scenes = {r['scene_id'] for r in doc['records'] if r.get('deleted_by') == MARKER}
    for scene in doc['scenes']:
        if scene['id'] in retired_scenes and not scene.get('deleted_at') and not any(
                r['scene_id'] == scene['id'] and not r.get('deleted_at') for r in doc['records']):
            scene.update(deleted_at=stamp, deleted_by=MARKER)
            changes['scenes_retired'].append(scene['id'])
    return doc, rag, changes


def apply():
    from app.faq_admin import FAQStore
    from app.knowledge import Knowledge
    from app.rag import RAGStore, _validate_document
    store, rs = FAQStore(), RAGStore()
    before, _ = store.read()
    materials, _ = rs.read()
    after, rag, changes = migrate(before, materials)
    kb = Knowledge(faq_document=after)
    for r in rag['documents']:
        _validate_document(r, kb.products, previous=r)
    originals = {store.path: store.path.read_bytes(), rs.path: rs.path.read_bytes()}
    backup = store.path.parent / 'backups' / ('blanket-retirement-' + uuid.uuid4().hex)
    backup.mkdir(parents=True)
    for path, raw in originals.items():
        (backup / path.name).write_bytes(raw)
    try:
        if after != before:
            store.persist(after, lambda d: Knowledge(faq_document=d))
        if rag != materials:
            temp = rs.path.with_name('.blanket-' + uuid.uuid4().hex + '.tmp')
            temp.write_text(json.dumps(rag, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            os.replace(temp, rs.path)
    except Exception:
        for path, raw in originals.items():
            temp = path.with_name('.rollback-' + uuid.uuid4().hex + '.tmp')
            temp.write_bytes(raw)
            os.replace(temp, path)
        raise
    (backup / 'changes.json').write_text(json.dumps(changes, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'backup': str(backup), **{k: len(v) for k, v in changes.items()}}, ensure_ascii=False))


if __name__ == '__main__':
    apply()
