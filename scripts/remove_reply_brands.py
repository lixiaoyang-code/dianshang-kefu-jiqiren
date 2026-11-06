"""清理回复中的商品品牌。保留原始来源，品牌背书类回答停用而不改成泛泛的肯定。"""
from __future__ import annotations

import argparse
import copy
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path


PRODUCT_BRANDS = re.compile(r'半弦月|巴斯夫|BASF|CosyPUR|FlexiCoat[™®]?', re.I)
BRAND_ENDORSEMENT = re.compile(r'官方旗舰店|自主品牌|品牌\s*logo', re.I)
SUPPLIER_QUESTION = re.compile(r'巴斯夫|BASF|CosyPUR', re.I)


def clean_text(text):
    if not isinstance(text, str):
        return text
    if not (PRODUCT_BRANDS.search(text) or re.search(r'(?:中国)?平安(?:保险|安全责任险)', text)):
        return text
    # 不以“我们实验室”冒充原品牌的实验室；保留原有测试条件和误差说明。
    text = text.replace('以上数据为半弦月实验室在实验环境下测试温度', '以上为实验环境下的参考温度')
    text = text.replace('半弦月一直都注重产品和服务', '我们会为您提供产品售后服务')
    text = re.sub(r'中国平安保险|平安保险', '保险', text)
    text = text.replace('平安安全责任险', '产品安全责任险')
    text = PRODUCT_BRANDS.sub('', text)
    text = re.sub(r'[ \t]{2,}', ' ', text)
    return text.lstrip('.。 ').strip()


def migrate_faq(document):
    doc = copy.deepcopy(document)
    changed = []
    now = datetime.now(timezone.utc).isoformat()
    for row in doc['records']:
        answer = row.get('standard_answer') or ''
        parts = row.get('answer_parts') or []
        combined = '\n'.join([answer, *parts])
        if not (PRODUCT_BRANDS.search(combined) or BRAND_ENDORSEMENT.search(combined)
                or re.search(r'(?:中国)?平安(?:保险|安全责任险)', combined)):
            continue
        questions = ' '.join(row.get('question_variants') or [])
        # 删除品牌认证/原料供应商背书话术，防止删掉品牌词后变成无依据的“是的”。
        if BRAND_ENDORSEMENT.search(combined) or SUPPLIER_QUESTION.search(questions):
            row.update(status='disabled', standard_answer='', answer_parts=[])
            row['review_note'] = '已删除品牌背书类话术并停用；如需启用，请补充与当前商品相符的已核实答案。'
            action = 'disabled'
        else:
            row['standard_answer'] = clean_text(answer)
            row['answer_parts'] = [clean_text(part) for part in parts] if parts else ([row['standard_answer']] if answer else [])
            action = 'cleaned'
        row['updated_at'] = now
        changed.append({'id': row['id'], 'action': action})
    return doc, changed


def migrate_customer_fields(document, kind):
    """只清理会成为答复/资料的内容，原始问法、来源摘录与历史日志保留溯源。"""
    doc = copy.deepcopy(document)
    changed = []

    def field(obj, key, location):
        value = obj.get(key)
        if isinstance(value, str):
            cleaned = clean_text(value)
            if cleaned != value:
                obj[key] = cleaned
                changed.append(location + '/' + key)
        elif isinstance(value, dict):
            for nested in list(value):
                field(value, nested, location + '/' + key)

    if kind in ('nets', 'catalog'):
        for row in doc.get('products', []):
            for key in ('facts', 'short_replies'):
                field(row, key, row['id'])
        if kind == 'nets':
            for key in ('facts', 'short_replies'):
                field(doc.get('store', {}), key, 'store')
    elif kind == 'source':
        for row in doc.get('records', []):
            field(row, 'answer', row['id'])
    elif kind == 'rag':
        for row in doc.get('documents', []):
            field(row, 'content', row['id'])
    return doc, changed


def run(data_dir):
    report = {}
    for filename, kind in [('faq.json', 'faq'), ('nets_801_804.json', 'nets'),
                           ('catalog_products.json', 'catalog'), ('source_qa.json', 'source'),
                           ('rag_documents.json', 'rag')]:
        path = data_dir / filename
        if not path.exists():
            continue
        raw = path.read_bytes()
        document = json.loads(raw)
        updated, changes = migrate_faq(document) if kind == 'faq' else migrate_customer_fields(document, kind)
        report[filename] = changes
        if not changes:
            continue
        backup = data_dir / 'backups'
        backup.mkdir(exist_ok=True)
        (backup / f'brand-cleanup-{path.stem}-{datetime.now(timezone.utc):%Y%m%dT%H%M%S}-{uuid.uuid4().hex[:8]}.json').write_bytes(raw)
        temporary = path.with_name('.brand-' + uuid.uuid4().hex + '.tmp')
        try:
            temporary.write_text(json.dumps(updated, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'data')
    args = parser.parse_args()
    print(json.dumps(run(args.data_dir), ensure_ascii=False, indent=2))
