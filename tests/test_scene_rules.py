"""场景识别后再筛答案：覆盖商品、接待、订单阶段、时间与优先级。"""
import copy
import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.config import ROOT, Settings
from app.faq import FAQ
from app.intent_candidates import candidates_for
from app.knowledge import Knowledge
from app.model import Model
from app.scene_rules import normalize_document, rank, row_eligible
from app.service import Service


CHINA = timezone(timedelta(hours=8))
NOW = datetime(2026, 10, 20, 12, 0, tzinfo=CHINA)


def answer(identifier='gift.801', **updates):
    row = {
        'id': identifier, 'intent': 'gift', 'category': '优惠赠品',
        'scope': 'product', 'product_ids': ['801'], 'status': 'active',
        'question_variants': ['有没有赠品', '可以送赠品吗'],
        'standard_answer': '亲，这款赠送收纳袋哈～',
        'answer_product_id': '801', 'images': [], 'fields': ['gift'],
        'sources': ['test:approved'], 'boundaries': [],
    }
    row.update(updates)
    return row


class SceneRulesTests(unittest.TestCase):
    def test_legacy_normalization_groups_same_intent_and_merges_variants(self):
        first = answer()
        second = answer('gift.802', product_ids=['802'], question_variants=['送东西吗'])
        doc = normalize_document({'records': [first, second]})
        self.assertEqual(len(doc['scenes']), 1)
        self.assertEqual({r['scene_id'] for r in doc['records']}, {'industry.gift'})
        self.assertEqual(set(doc['scenes'][0]['question_variants']),
                         {'有没有赠品', '可以送赠品吗', '送东西吗'})
        self.assertTrue(all(r['scene_type'] == 'industry' for r in doc['records']))

    def test_normalization_does_not_mutate_original_data(self):
        doc = {'records': [answer()]}
        original = copy.deepcopy(doc)
        normalize_document(doc)
        self.assertEqual(doc, original)

    def test_legacy_default_is_all_receptions_stages_and_times(self):
        row = normalize_document({'records': [answer()]})['records'][0]
        self.assertEqual(row['conditions'], {
            'reception': 'all', 'stages': [], 'valid_from': None, 'valid_until': None})
        for reception in ('presales', 'aftersales'):
            for stage in ('presales', 'shipping', 'received', 'aftersales'):
                with self.subTest(reception=reception, stage=stage):
                    self.assertTrue(row_eligible(row, '801', reception, stage, NOW))

    def test_one_scene_has_product_specific_answers(self):
        faq = FAQ([answer(), answer('gift.802', product_ids=['802'],
                                   standard_answer='亲，这款送挂钩哈～')])
        for pid, expected in [('801', '收纳袋'), ('802', '挂钩')]:
            with self.subTest(pid=pid):
                result = faq.resolve('可以送赠品吗？', pid, now=NOW)
                self.assertEqual(result['status'], 'matched')
                self.assertIn(expected, result['row']['standard_answer'])
        self.assertEqual(faq.resolve('有没有赠品', '803', now=NOW)['status'], 'ineligible')

    def test_scene_variant_can_select_another_product_answer(self):
        # 问法属于场景，不要求每个商品答案重复录入同一个问法。
        faq = FAQ([answer(), answer('gift.802', product_ids=['802'],
                                   question_variants=['这款带礼物吗'])])
        result = faq.resolve('这款带礼物吗', '801', now=NOW)
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['row']['id'], 'gift.801')

    def test_missing_product_cannot_take_a_product_answer(self):
        self.assertEqual(FAQ([answer()]).resolve('有没有赠品', None, now=NOW)['status'],
                         'ineligible')

    def test_store_and_catalog_answers_are_not_bound_to_current_product(self):
        for scope in ('store', 'catalog'):
            with self.subTest(scope=scope):
                faq = FAQ([answer(scope=scope, product_ids=[], answer_product_id='804')])
                result = faq.resolve('有没有赠品', '801', now=NOW)
                self.assertEqual(result['status'], 'matched')
                self.assertEqual(result['row']['answer_product_id'], '804')

    def test_each_order_stage_selects_its_own_answer(self):
        stages = ('presales', 'shipping', 'received', 'aftersales')
        rows = [answer('gift.' + stage, standard_answer='答复-' + stage,
                       conditions={'stages': [stage]}) for stage in stages]
        faq = FAQ(rows)
        for stage in stages:
            with self.subTest(stage=stage):
                result = faq.resolve('有没有赠品', '801', stage=stage, now=NOW)
                self.assertEqual(result['status'], 'matched')
                self.assertEqual(result['row']['standard_answer'], '答复-' + stage)

    def test_reception_is_separate_from_order_stage(self):
        faq = FAQ([answer(conditions={'reception': 'aftersales', 'stages': ['shipping']})])
        self.assertEqual(faq.resolve('有没有赠品', '801', reception='presales',
                                     stage='shipping', now=NOW)['status'], 'ineligible')
        self.assertEqual(faq.resolve('有没有赠品', '801', reception='aftersales',
                                     stage='shipping', now=NOW)['status'], 'matched')
        self.assertEqual(faq.resolve('有没有赠品', '801', reception='aftersales',
                                     stage='received', now=NOW)['status'], 'ineligible')

    def test_disabled_answers_are_ineligible(self):
        for status in ('disabled', 'needs_review', 'manual_policy'):
            with self.subTest(status=status):
                self.assertFalse(row_eligible(answer(status=status), '801', now=NOW))

    def test_time_window_includes_exact_start_and_end(self):
        row = answer(conditions={'valid_from': '2026-10-20T12:00:00+08:00',
                                 'valid_until': '2026-10-20T13:00:00+08:00'})
        for at, expected in [(NOW - timedelta(microseconds=1), False), (NOW, True),
                             (NOW + timedelta(hours=1), True),
                             (NOW + timedelta(hours=1, microseconds=1), False)]:
            with self.subTest(at=at):
                self.assertEqual(row_eligible(row, '801', now=at), expected)

    def test_naive_editor_times_mean_china_time(self):
        row = answer(conditions={'valid_from': '2026-10-20T12:00',
                                 'valid_until': '2026-10-20T13:00'})
        self.assertTrue(row_eligible(row, '801', now=NOW))
        self.assertFalse(row_eligible(row, '801', now=NOW - timedelta(seconds=1)))
        self.assertTrue(row_eligible(row, '801', now=datetime(2026, 10, 20, 12, 30)))

    def test_timezone_offsets_and_utc_z_represent_same_instant(self):
        row = answer(conditions={'valid_from': '2026-10-20T04:00:00Z',
                                 'valid_until': '2026-10-20T05:00:00+00:00'})
        self.assertTrue(row_eligible(row, '801', now=NOW))
        self.assertFalse(row_eligible(row, '801', now=NOW - timedelta(seconds=1)))

    def test_custom_has_priority_over_special_and_industry(self):
        rows = [answer(layer, scene_id=layer + '.gift', scene_type=layer,
                       standard_answer=layer, priority=999 if layer == 'industry' else 0)
                for layer in ('industry', 'special', 'custom')]
        result = FAQ(rows).resolve('有没有赠品', '801', now=NOW)
        self.assertEqual(result['row']['standard_answer'], 'custom')
        result = FAQ(rows[:2]).resolve('有没有赠品', '801', now=NOW)
        self.assertEqual(result['row']['standard_answer'], 'special')

    def test_expired_custom_falls_back_to_eligible_industry(self):
        rows = [answer('normal', standard_answer='常规赠品'),
                answer('event', scene_id='custom.gift', scene_type='custom',
                       standard_answer='活动赠品', conditions={
                           'valid_until': '2026-10-19T23:59:59+08:00'})]
        result = FAQ(rows).resolve('有没有赠品', '801', now=NOW)
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['row']['id'], 'normal')

    def test_wrong_product_custom_does_not_override_eligible_industry(self):
        rows = [answer('normal'), answer('event', scene_id='custom.gift', scene_type='custom',
                                        product_ids=['802'], standard_answer='别款活动赠品')]
        self.assertEqual(FAQ(rows).resolve('有没有赠品', '801', now=NOW)['row']['id'], 'normal')

    def test_manual_priority_is_within_layer(self):
        rows = [answer('low', priority=1),
                answer('high', priority=2, standard_answer='高优先级答复')]
        self.assertGreater(rank(rows[1]), rank(rows[0]))
        self.assertEqual(FAQ(rows).resolve('有没有赠品', '801', now=NOW)['row']['id'], 'high')

    def test_more_specific_product_and_stage_answers_win_ties(self):
        rows = [answer('store', scope='store', product_ids=[], standard_answer='通用'),
                answer('many', product_ids=['801', '802'], standard_answer='两款'),
                answer('one', standard_answer='当前款'),
                answer('stage', standard_answer='售前当前款', conditions={'stages': ['presales']})]
        self.assertEqual(FAQ(rows).resolve('有没有赠品', '801', now=NOW)['row']['id'], 'stage')

    def test_conflicting_equal_rank_answers_are_ambiguous(self):
        faq = FAQ([answer('one'), answer('two', standard_answer='不同答案')])
        result = faq.resolve('有没有赠品', '801', now=NOW)
        self.assertEqual(result['status'], 'ambiguous')
        self.assertIsNone(result['row'])

    def test_equal_rank_same_text_different_images_are_ambiguous(self):
        faq = FAQ([answer('one', images=[{'id': 'one'}]),
                   answer('two', images=[{'id': 'two'}])])
        self.assertEqual(faq.resolve('有没有赠品', '801', now=NOW)['status'], 'ambiguous')

    def test_identical_equal_rank_answers_need_not_be_ambiguous(self):
        self.assertEqual(FAQ([answer('one'), answer('two')]).resolve(
            '有没有赠品', '801', now=NOW)['status'], 'matched')

    def test_keywords_any_are_an_additional_matching_path(self):
        faq = FAQ([answer(keywords=['赠品', '礼物'], keyword_mode='any')])
        self.assertEqual(faq.resolve('下单有礼物给我吗', '801', now=NOW)['status'], 'matched')
        self.assertEqual(faq.resolve('好安装吗', '801', now=NOW)['status'], 'no_match')

    def test_keywords_all_require_every_word(self):
        faq = FAQ([answer(keywords=['活动', '赠品'], keyword_mode='all')])
        self.assertEqual(faq.resolve('现在的活动赠品是什么', '801', now=NOW)['status'], 'matched')
        self.assertEqual(faq.resolve('现在活动开始了吗', '801', now=NOW)['status'], 'no_match')

    def test_exact_scene_question_does_not_need_keywords(self):
        faq = FAQ([answer(keywords=['限时', '活动'], keyword_mode='all')])
        self.assertEqual(faq.resolve('有没有赠品', '801', now=NOW)['status'], 'matched')

    def test_keyword_hit_cannot_bypass_product_stage_or_time(self):
        faq = FAQ([answer(keywords=['礼物'], conditions={
            'reception': 'aftersales', 'stages': ['received'],
            'valid_from': '2026-10-20T12:00:00+08:00',
            'valid_until': '2026-10-20T13:00:00+08:00'})])
        cases = [('802', 'aftersales', 'received', NOW),
                 ('801', 'presales', 'received', NOW),
                 ('801', 'aftersales', 'shipping', NOW),
                 ('801', 'aftersales', 'received', NOW + timedelta(days=1))]
        for pid, reception, stage, moment in cases:
            with self.subTest(pid=pid, reception=reception, stage=stage, time=moment):
                self.assertEqual(faq.resolve('给礼物不', pid, reception, stage, moment)['status'],
                                 'ineligible')

    def test_model_candidate_rows_only_include_eligible_answers(self):
        rows = [answer('eligible'), answer('wrong_product', product_ids=['802']),
                answer('wrong_reception', conditions={'reception': 'aftersales'}),
                answer('wrong_stage', conditions={'stages': ['received']}),
                answer('expired', conditions={'valid_until': '2026-10-19T23:00:00+08:00'}),
                answer('disabled', status='needs_review')]
        faq = FAQ(rows)
        candidates = [FAQ.candidate(row) for row in faq.eligible(
            '801', reception='presales', stage='presales', now=NOW)]
        self.assertEqual([c['id'] for c in candidates], ['eligible'])

    def test_actual_model_candidate_builder_applies_context_conditions(self):
        rows = [answer('eligible', conditions={'reception': 'aftersales',
                                              'stages': ['received']}),
                answer('wrong_product', product_ids=['802']),
                answer('wrong_reception', conditions={'reception': 'presales'}),
                answer('wrong_stage', conditions={'stages': ['presales']}),
                answer('expired', conditions={'valid_until': '2026-10-19T23:00:00+08:00'}),
                answer('inactive', status='needs_review')]
        kb = SimpleNamespace(products={'801': {'name': '纯色款', 'aliases': [],
                                               'blocked_topics': []}}, faq=FAQ(rows))
        candidates = candidates_for(kb, '这个牢靠不', '801',
                                    reception='aftersales', stage='received', now=NOW)
        self.assertEqual([c['id'] for c in candidates], ['eligible'])

    def test_explicit_scene_metadata_groups_multiple_answer_rows(self):
        scenes = [{'id': 'gift.main', 'name': '有没有赠品', 'type': 'special',
                   'category': '优惠', 'question_variants': ['下单送什么']}]
        faq = FAQ([answer(scene_id='gift.main'), answer('gift.802', scene_id='gift.main',
                                                      product_ids=['802'])], scenes)
        result = faq.resolve('下单送什么', '802', now=NOW)
        self.assertEqual(result['status'], 'matched')
        self.assertEqual(result['row']['scene_type'], 'special')
        self.assertEqual(result['row']['scene_name'], '有没有赠品')


class SceneRecommendationRegressionTests(unittest.IsolatedAsyncioTestCase):
    async def test_finish_keeps_explicit_scene_choice_when_only_another_variant_overlaps(self):
        document = normalize_document(json.loads((ROOT / 'data/faq.json').read_text(encoding='utf-8')))
        document['scenes'] += [
            {'id': 'custom.alpha', 'name': '精确场景甲', 'type': 'custom', 'category': '测试',
             'question_variants': ['测试唯一甲', '测试交集乙']},
            {'id': 'custom.beta', 'name': '场景乙', 'type': 'custom', 'category': '测试',
             'question_variants': ['测试交集乙']},
        ]
        document['records'] += [
            answer('custom.alpha.answer', scene_id='custom.alpha', configured_scene=True,
                   question_variants=['测试唯一甲', '测试交集乙'], standard_answer='客户问题甲的答案'),
            answer('custom.beta.answer', scene_id='custom.beta', configured_scene=True, priority=10,
                   question_variants=['测试交集乙'], standard_answer='仅问题乙适用的答案'),
        ]
        kb = Knowledge(faq_document=document)
        with tempfile.TemporaryDirectory() as folder:
            with patch('app.service.get_semantic', return_value=(None, 'disabled')):
                service = Service(kb, Model(Settings(mode='mock', key='')), Path(folder))
            try:
                session = service.create()
                result = await service.chat(session.session_id, '测试唯一甲', selected='801')
                self.assertEqual(result['debug']['retrieval']['method'], 'scene_faq')
                self.assertEqual(result['answer'], '客户问题甲的答案')
                self.assertEqual(result['debug']['retrieval']['hits'][0]['id'], 'custom.alpha.answer')
            finally:
                for handler in list(service.logger.handlers):
                    service.logger.removeHandler(handler)
                    handler.close()

    async def test_configuring_product_dimensions_does_not_block_cross_product_recommendations(self):
        # 商品尺寸答案只允许售后触发，不应阻止独立的全伸缩款目录推荐。
        document = json.loads((ROOT / 'data/faq.json').read_text(encoding='utf-8'))
        for row in document['records']:
            if row['intent'] == 'telescoping':
                row.update(configured_scene=True, conditions={'stages': ['aftersales']})
        kb = Knowledge(faq_document=document)
        with tempfile.TemporaryDirectory() as folder:
            with patch('app.service.get_semantic', return_value=(None, 'disabled')):
                service = Service(kb, Model(Settings(mode='mock', key='')), Path(folder))
            try:
                for question in ('有全伸缩的支架吗', '有80宽的杆子吗', '80*190可以用吗'):
                    with self.subTest(question=question):
                        session = service.create()
                        session.current_product_id = '801'
                        session.product_confirmed = True
                        result = await service.chat(session.session_id, question)
                        self.assertEqual(result['status'], 'answered')
                        self.assertIn('推荐全伸缩款', result['answer'])
                        self.assertEqual(result['session']['current_product_id'], '801')
                        self.assertEqual(result['debug']['retrieval']['hits'][0]['id'],
                                         'catalog.full_stretch')
            finally:
                for handler in list(service.logger.handlers):
                    service.logger.removeHandler(handler)
                    handler.close()


if __name__ == '__main__':
    unittest.main()
