import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.catalog import answer
from app.config import Settings
from app.knowledge import Knowledge
from app.model import Model
from app.rag import RAGAssistant
from app.service import Service
from scripts.fix_blanket_knowledge import migrate


def fixture():
    pairs = [
        ('count', 'industry.catalog_draft_b37f9850a485', ['几个档位？'], '一共12档。', ['plushblanket'], 'active'),
        ('personal.blanket_warranty.75', 'industry.personal_blanket_warranty', ['电热毯质保多久？'],
         '一年内遥控器不亮、失灵等问题，符合质保条件可免费更换遥控器。', ['plushblanket', 'nonwovenblanket'], 'active'),
        ('cable', 'industry.personal_cable', ['电热毯电源线多长？'], '控制器线约1.8米。', ['plushblanket'], 'active'),
        ('wash', 'industry.personal_blanket_wash', ['电热毯可以机洗吗？'], '按洗护说明，先断电取下控制器。', ['plushblanket'], 'active'),
        ('old', 'industry.old', ['有几个档位？'], '6档。', ['nonwovenblanket'], 'active'),
        ('pending', 'industry.pending', ['电热毯可以甩干吗？'], '待核对洗护标识。', ['plushblanket'], 'needs_review'),
        ('personal.blanket_3c.95', 'industry.insurance', ['由保险公司承保吗？', '有3C认证吗'],
         '这款有3C认证。', ['plushblanket'], 'active'),
        ('pending_insurance', 'industry.insurance', ['由保险公司承保吗？'],
         '保险承保信息待核实。', ['plushblanket'], 'needs_review'),
        ('other', 'industry.other', ['云感被质保多久？'], '其他商品答案。', ['cloudquilt'], 'active'),
    ]
    scenes, records = [], []
    for rid, sid, qs, text, pids, status in pairs:
        scenes.append(dict(id=sid, name=qs[0], type='industry', category='商品参数', question_variants=qs[:]))
        records.append(dict(id=rid, intent='test', scene_id=sid, scene_name=qs[0], scene_type='industry',
                            scope='product', product_ids=pids, answer_product_id=pids[0], status=status,
                            standard_answer=text, answer_parts=[text], question_variants=qs[:],
                            fields=[], sources=[{'file': 'test'}], images=[], boundaries={},
                            conditions={'reception': 'presales', 'stages': ['presales']}))
    mats = {'documents': [dict(id='retired', title='旧电热毯', content='6档。', source='旧资料', status='active',
                               product_ids=['nonwovenblanket'], conditions={}),
                          dict(id='shared', title='质保', content='遥控器一年。', source='快捷短语', status='active',
                               product_ids=['nonwovenblanket', 'plushblanket'], conditions={})]}
    return {'scenes': scenes, 'records': records}, mats


class BlanketRetirementTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.original, self.materials = fixture()
        self.doc, self.rag, self.changes = migrate(self.original, self.materials, '2026-11-08T12:00:00+08:00')
        self.kb = Knowledge(faq_document=self.doc)
        self.svc = SimpleNamespace(kb=self.kb, semantic=None)

    async def test_short_and_full_questions_use_existing_plush_faq(self):
        for q, rid in [('有几个档位', 'count'), ('电热毯有几档', 'count'), ('档位', 'count'),
                       ('质保多久', 'personal.blanket_warranty.75'), ('电热毯质保多久', 'personal.blanket_warranty.75'),
                       ('保修多久', 'personal.blanket_warranty.75'), ('电热毯电源线多长', 'cable'),
                       ('电热毯可以机洗吗', 'wash')]:
            row, debug, reason = await answer(self.svc, q, 'plushblanket', 'presales', 'presales', [])
            self.assertIsNotNone(row, (q, reason))
            self.assertEqual(row['id'], rid, q)
            self.assertEqual(debug['retrieval']['method'], 'scene_faq')

    async def test_normalization_keeps_status_and_product_boundaries(self):
        for pid, q, reception, stage in [('plushblanket', '可以甩干吗', 'presales', 'presales'),
                                        ('plushblanket', '保修多久', 'aftersales', 'aftersales'),
                                        ('cloudquilt', '电源线多长', 'presales', 'presales')]:
            row, _, _ = await answer(self.svc, q, pid, reception, stage, [])
            self.assertIsNone(row, q)

    async def test_certification_answer_does_not_answer_insurance(self):
        row, _, _ = await answer(self.svc, '有3C认证吗', 'plushblanket', 'presales', 'presales', [])
        self.assertEqual(row['id'], 'personal.blanket_3c.95')
        row, _, _ = await answer(self.svc, '由保险公司承保吗？', 'plushblanket', 'presales', 'presales', [])
        self.assertIsNone(row)

    def test_retirement_is_recoverable_idempotent_and_preserves_other_products(self):
        old = next(r for r in self.doc['records'] if r['id'] == 'old')
        self.assertEqual(old['status'], 'disabled')
        self.assertTrue(old['deleted_at'])
        self.assertEqual(old['standard_answer'], '6档。')
        self.assertFalse(self.kb.faq.eligible('nonwovenblanket'))
        self.assertNotIn('retired', [r['id'] for r in self.rag['documents']])
        self.assertEqual(self.rag['documents'][0]['product_ids'], ['plushblanket'])
        self.assertEqual(self.doc['records'][-1], self.original['records'][-1])
        again = migrate(self.doc, self.rag)
        self.assertEqual(again[:2], (self.doc, self.rag))
        self.assertEqual(self.original, fixture()[0])

    async def test_retired_product_cannot_reply_or_supply_rag_sources(self):
        with tempfile.TemporaryDirectory() as temp, patch.dict('os.environ', {'SEMANTIC_MODE': 'off'}):
            svc = Service(self.kb, Model(Settings(mode='mock', key='')), Path(temp))
            try:
                for pid, q in [('nonwovenblanket', '几个档位'), ('plushblanket', '无纺布电热毯几档')]:
                    result = await svc.chat(svc.create().session_id, q, pid)
                    self.assertEqual(result['debug']['reason'], 'retired_product')
                    self.assertNotIn('6档', result['answer'])
                assistant = RAGAssistant(self.kb, svc.model)
                result = await assistant.assist('无纺布电热毯有几档', 'plushblanket')
                self.assertEqual(result['status'], 'product_required')
                self.assertFalse(result['sources'])
            finally:
                for handler in svc.logger.handlers:
                    handler.close()


if __name__ == '__main__':
    unittest.main()
