import copy
import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

from app.config import ROOT, Settings
from app.knowledge import Knowledge
from app.model import Model
from app.rag import RAGAssistant, RAGStore
from app.scene_rules import CHINA


class RAGStoreTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'materials.json'
        self.path.write_bytes((ROOT / 'data/rag_documents.json').read_bytes())
        self.store = RAGStore(self.path)

    def tearDown(self):
        self.folder.cleanup()

    def test_versioned_update_backs_up_and_preserves_other_records(self):
        doc, revision = self.store.read()
        before = self.path.read_bytes()
        row = copy.deepcopy(doc['documents'][0])
        row['content'] = '商家重新确认的测试资料。'
        saved, next_revision = self.store.save(revision, row, ['801', '802', '803', '804'])
        self.assertEqual(saved['id'], row['id'])
        self.assertNotEqual(revision, next_revision)
        self.assertEqual(next((self.path.parent / 'backups').glob('rag-*.json')).read_bytes(), before)
        after, _ = self.store.read()
        self.assertEqual(after['documents'][1:], doc['documents'][1:])
        with self.assertRaises(HTTPException) as caught:
            self.store.save(revision, row, ['801'])
        self.assertEqual(caught.exception.status_code, 409)

    def test_invalid_material_does_not_replace_original(self):
        doc, revision = self.store.read()
        before = self.path.read_bytes()
        for changes in [{'source': ''}, {'product_ids': ['999']}, {'status': 'approved'},
                        {'date': 'yesterday'}, {'conditions': {'valid_from': '2028-01-01', 'valid_until': '2027-01-01'}}]:
            with self.subTest(changes=changes):
                row = {**doc['documents'][0], **changes}
                with self.assertRaises(HTTPException) as caught:
                    self.store.save(revision, row, ['801', '802', '803', '804'])
                self.assertEqual(caught.exception.status_code, 422)
                self.assertEqual(self.path.read_bytes(), before)

    def test_new_material_defaults_to_review_and_presales(self):
        _, revision = self.store.read()
        row, _ = self.store.save(revision, {'title': '新资料', 'content': '待商家确认的内容。', 'source': '人工录入', 'product_ids': ['801']}, ['801'])
        self.assertEqual(row['status'], 'needs_review')
        self.assertEqual(row['conditions']['reception'], 'presales')
        self.assertEqual(row['conditions']['stages'], ['presales'])
        self.assertEqual(row['date'], datetime.now(CHINA).date().isoformat())


class RAGTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.path = Path(self.folder.name) / 'materials.json'
        self.path.write_bytes((ROOT / 'data/rag_documents.json').read_bytes())
        self.store = RAGStore(self.path)
        self.kb = Knowledge()
        self.model = Model(Settings(mode='mock', key=''))
        self.rag = RAGAssistant(self.kb, self.model, store=self.store, supplement_faq=False)

    def tearDown(self):
        self.folder.cleanup()

    async def test_combined_question_retrieves_multiple_confirmed_passages(self):
        result = await self.rag.assist('全伸缩款110高高度和长宽调节范围是多少？', '801')
        self.assertEqual(result['status'], 'extractive')
        self.assertEqual(result['generation_status'], 'disabled')
        self.assertTrue(result['for_operator_only'])
        self.assertFalse(result['can_save_faq'])
        self.assertEqual({s['document_id'] for s in result['sources']}, {'material.802.height', 'material.802.length_width'})
        self.assertFalse(result['missing_info'])
        self.assertTrue(all(s['product_ids'] == ['802'] for s in result['sources']))

    async def test_explicit_comparison_can_use_two_products(self):
        result = await self.rag.assist('纯色款和全伸缩款的高度、长宽调节有什么区别？', '801')
        self.assertEqual(len(result['sources']), 4)
        self.assertEqual({tuple(s['product_ids']) for s in result['sources']}, {('801',), ('802',)})

    async def test_product_name_does_not_add_an_unasked_installation_topic(self):
        self.rag.supplement_faq = True
        result = await self.rag.assist('全伸缩款和免安装款的长宽调节范围分别是多少？', '801')
        self.assertEqual(result['proposed_intent'], '长宽调节')
        self.assertEqual({s['document_id'] for s in result['sources']}, {'material.802.length_width', 'material.804.length_width'})
        self.assertFalse(result['missing_info'])
        self.assertEqual(result['status'], 'extractive')
        self.assertEqual(result['generation_status'], 'disabled')

    async def test_product_name_noise_is_removed_from_materials_and_faq_variants(self):
        doc, revision = self.store.read()
        row = next(r for r in doc['documents'] if r['id'] == 'material.804.length_width')
        row['topics'] = []
        self.store.save(revision, row, ['801', '802', '803', '804'])
        faq = copy.deepcopy(self.kb.faq.records[0])
        faq.update(id='custom.804.width', intent='custom_width', scene_id='custom.width', scene_name='免安装款宽度是多少？',
                   fields=[], question_variants=['免安装款宽度是多少？'], product_ids=['804'], status='active',
                   standard_answer='免安装款宽度76–90厘米。', sources=[{'type': 'user_confirmation', 'date': '2026-10-22'}])
        self.kb.faq.records = [faq]
        self.rag.supplement_faq = True
        rows, _ = self.rag._documents({'804'}, 'presales', 'presales', datetime.now(CHINA))
        relevant = [r for r in rows if r['document_id'] in ('material.804.length_width', 'faq.custom.804.width')]
        self.assertEqual(len(relevant), 2)
        self.assertTrue(all(r['topics'] == ['length_width'] for r in relevant))

    async def test_real_installation_question_remains_an_installation_topic(self):
        result = await self.rag.assist('免安装款怎么安装？', '801')
        self.assertEqual(result['proposed_intent'], '安装方法')
        self.assertEqual(result['status'], 'no_evidence')
        self.assertEqual(result['missing_info'], ['安装方法'])

    async def test_single_product_never_reads_other_product_passages(self):
        result = await self.rag.assist('高度和长宽能调多少？', '804')
        self.assertEqual({s['document_id'] for s in result['sources']}, {'material.804.height', 'material.804.length_width'})

    async def test_no_product_requires_confirmation_but_common_structure_does_not(self):
        result = await self.rag.assist('高度能调多少？')
        self.assertEqual(result['status'], 'product_required')
        self.assertFalse(result['sources'])
        common = await self.rag.assist('一套包括什么？帐纱在外面吗？')
        self.assertEqual(common['sources'][0]['document_id'], 'material.common.structure')

    async def test_expired_disabled_and_other_stages_are_not_evidence(self):
        doc, _ = self.store.read()
        for row in doc['documents']:
            if row['id'].endswith('.height'):
                row['conditions']['valid_until'] = '2026-01-01'
            else:
                row['status'] = 'needs_review'
        self.path.write_text(json.dumps(doc), encoding='utf-8')
        result = await self.rag.assist('高度和长宽能调多少', '801', now=datetime(2026, 11, 2, tzinfo=CHINA))
        self.assertEqual(result['status'], 'no_evidence')
        self.assertFalse(result['sources'])
        # Active but only presales documents remain unavailable to aftersales.
        self.path.write_bytes((ROOT / 'data/rag_documents.json').read_bytes())
        result = await self.rag.assist('高度能调多少', '801', reception='aftersales', stage='aftersales')
        self.assertEqual(result['status'], 'no_evidence')

    async def test_unknown_topic_does_not_fall_back_to_unrelated_top_hit(self):
        with patch.object(self.rag, '_generate', new=AsyncMock(side_effect=AssertionError('no generation'))):
            result = await self.rag.assist('甲醛检测结果怎样？', '801')
        self.assertEqual(result['status'], 'no_evidence')
        self.assertFalse(result['sources'])

    async def test_partial_evidence_lists_missing_topic(self):
        result = await self.rag.assist('高度能调多少，有甲醛检测吗？', '802')
        self.assertEqual(result['status'], 'partial')
        self.assertIn('面料与检测', result['missing_info'])
        self.assertFalse(result['can_save_faq'])
        self.assertTrue(all('height' in s['document_id'] for s in result['sources']))

    async def test_manual_operations_never_call_generation(self):
        with patch.object(self.rag, '_generate', new=AsyncMock(side_effect=AssertionError('no generation'))):
            result = await self.rag.assist('帮我退款并赔偿', '801')
        self.assertEqual(result['status'], 'manual_boundary')
        self.assertFalse(result['sources'])

    async def test_unknown_product_does_not_use_the_current_product(self):
        result = await self.rag.assist('805款高度能调多少？', '801')
        self.assertEqual(result['status'], 'product_required')
        self.assertFalse(result['sources'])

    async def test_hybrid_encoder_is_reused_until_documents_change(self):
        class Encoder:
            def __init__(self):
                self.calls = []
            def encode(self, texts):
                self.calls.append(len(texts))
                return [[1., 0.] for _ in texts]
        encoder = Encoder()
        self.rag.encoder = encoder
        first = await self.rag.assist('高度范围是多少？', '802')
        self.assertEqual(first['retrieval_method'], 'hybrid')
        await self.rag.assist('长宽范围是多少？', '802')
        self.assertEqual(len(encoder.calls), 3)
        self.assertGreater(encoder.calls[0], 1)
        doc, revision = self.store.read()
        row = next(r for r in doc['documents'] if r['id'] == 'material.802.height')
        row['content'] += '这是新的审核备注。'
        self.store.save(revision, row, ['801', '802', '803', '804'])
        await self.rag.assist('高度范围是多少？', '802')
        self.assertEqual(len(encoder.calls), 5)

    async def call_model(self, output, question='全伸缩款的高度和长宽范围是多少？', pid='802'):
        self.model.settings.mode = 'api'
        self.model.settings.key = 'test-only-not-real'
        client = AsyncMock()
        client.post.return_value = httpx.Response(200, request=httpx.Request('POST', 'https://example.invalid'), json={
            'choices': [{'message': {'content': json.dumps(output, ensure_ascii=False)}}]})
        client.__aenter__.return_value = client
        with patch('app.rag.httpx.AsyncClient', return_value=client):
            result = await self.rag.assist(question, pid)
        return result, client.post.call_args.kwargs['json']

    async def test_real_generation_path_uses_only_retrieved_passages_and_validates_citations(self):
        result, body = await self.call_model({'answer': '全伸缩款长度145–190厘米、宽度65–90厘米；110厘米高度款可调100–115厘米。',
            'citations': ['material.802.height#p1', 'material.802.length_width#p1'], 'missing_info': []})
        self.assertEqual(result['status'], 'generated')
        self.assertEqual(result['generation_status'], 'generated')
        self.assertTrue(result['can_save_faq'])
        self.assertTrue(result['requires_review'])
        prompt = json.loads(body['messages'][1]['content'])
        self.assertEqual(len(prompt['materials']), 2)
        self.assertNotIn('source', prompt['materials'][0])
        self.assertNotIn('test-only-not-real', json.dumps(body))

    async def test_unretrieved_citation_falls_back_to_excerpts(self):
        result, _ = await self.call_model({'answer': '无法核实', 'citations': ['material.999#p1'], 'missing_info': []})
        self.assertEqual(result['generation_status'], 'invalid_citations')
        self.assertEqual(result['status'], 'extractive')
        self.assertFalse(result['can_save_faq'])
        self.assertTrue(result['suggestion'].startswith('资料摘录：'))

    async def test_product_name_does_not_reject_valid_generated_width_advice(self):
        result, _ = await self.call_model({'answer': '免安装款长度186–190厘米、宽度76–90厘米，均可调节。',
            'citations': ['material.804.length_width#p1'], 'missing_info': []}, '免安装款长宽调节范围是多少？', '804')
        self.assertEqual(result['status'], 'generated')
        self.assertEqual(result['generation_status'], 'generated')
        self.assertFalse(result['missing_info'])

    async def test_model_omitting_one_requested_source_cannot_mark_complete_faq(self):
        result, _ = await self.call_model({'answer': '全伸缩款长度145–190厘米，宽度65–90厘米。',
            'citations': ['material.802.length_width#p1'], 'missing_info': []})
        self.assertEqual(result['status'], 'partial')
        self.assertFalse(result['can_save_faq'])
        self.assertIn('高度调节', result['missing_info'])

    async def test_new_numeric_claim_and_recombined_range_are_rejected(self):
        for answer, reason in [('高度可调999厘米。', 'unsupported_numbers'), ('长度可以调145–115厘米。', 'unsupported_ranges')]:
            with self.subTest(answer=answer):
                result, _ = await self.call_model({'answer': answer, 'citations': ['material.802.height#p1', 'material.802.length_width#p1'], 'missing_info': []})
                self.assertEqual(result['generation_status'], reason)
                self.assertNotEqual(result['status'], 'generated')

    async def test_timeout_remains_distinct_from_missing_knowledge(self):
        self.model.settings.mode = 'api'
        self.model.settings.key = 'test-only-not-real'
        client = AsyncMock()
        client.__aenter__.return_value = client
        client.post.side_effect = httpx.ReadTimeout('test timeout')
        with patch('app.rag.httpx.AsyncClient', return_value=client):
            result = await self.rag.assist('高度能调多少？', '802')
        self.assertEqual(result['generation_status'], 'timeout')
        self.assertEqual(result['status'], 'extractive')
        self.assertTrue(result['sources'])

    async def test_faq_supplement_respects_status_and_never_reintroduces_old_dimensions(self):
        self.rag.supplement_faq = True
        result = await self.rag.assist('支架承重稳固吗', '801')
        self.assertTrue(result['sources'])
        self.assertTrue(all(s['origin'] == 'faq' for s in result['sources']))
        for row in self.kb.faq.records:
            row['status'] = 'needs_review'
        result = await self.rag.assist('支架承重稳固吗', '801')
        self.assertFalse(result['sources'])
        dims = await self.rag.assist('高度和长宽范围是多少', '801')
        self.assertTrue(all(s['origin'] == 'material' for s in dims['sources']))
