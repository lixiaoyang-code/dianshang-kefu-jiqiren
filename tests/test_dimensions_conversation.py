"""尺寸按维度和规格回答，纠错不能丢失客户上一轮真正问的属性。"""
import copy
import re
import unittest
from unittest.mock import AsyncMock, patch

import test_nets as fixtures
import test_faq_admin as admin_fixtures
from app.main import app


def normalized(text):
    return re.sub(r'[\s，,。；;：:]', '', text).replace('—', '-').replace('–', '-').replace('～', '-').replace('至', '-').replace('到', '-')


class DimensionConversationTests(unittest.TestCase):
    setUp = fixtures.NetsTests.setUp
    tearDown = fixtures.NetsTests.tearDown
    chat = fixtures.NetsTests.chat

    def select(self, pid):
        response = self.client.post(f'/api/sessions/{self.sid}/events',
                                    json={'type': 'customer_select', 'product_id': pid})
        self.assertEqual(response.status_code, 200)

    def new_session(self, pid=None):
        self.sid = self.client.post('/api/sessions').json()['session_id']
        if pid:
            self.select(pid)

    def assert_intent(self, result, scene):
        self.assertEqual(result['debug']['analysis']['intents'][0]['id'], scene, result)

    def test_width_question_is_not_height_and_does_not_require_model(self):
        self.select('801')
        model = app.state.service.model
        with patch.object(model, 'select', new=AsyncMock(side_effect=ConnectionError())) as select, \
             patch.object(model, 'understand', new=AsyncMock(side_effect=ConnectionError())) as understand:
            result = self.chat('长宽可以伸缩嘛', 'answered')
        select.assert_not_awaited()
        understand.assert_not_awaited()
        self.assert_intent(result, 'industry.length_width_range')
        self.assertIn('固定', result['answer'])
        self.assertIn('190', result['answer'])
        self.assertIn('90', result['answer'])
        self.assertIn('全伸缩款', result['answer'])
        self.assertNotIn('65-120', normalized(result['answer']))
        self.assertEqual(result['session']['current_product_id'], '801')

    def test_801_height_boundaries_are_explicit(self):
        for height in [90, 110]:
            with self.subTest(height=height):
                self.new_session('801')
                result = self.chat(f'{height}高款高度可以伸缩吗？', 'answered')
                self.assert_intent(result, 'industry.height_range')
                self.assertRegex(result['answer'], r'不(?:可以|能|可)?(?:伸缩|调节)|固定')
                self.assertNotIn('65-120', normalized(result['answer']))
        self.new_session('801')
        result = self.chat('120高款高度能调多少？', 'answered')
        self.assert_intent(result, 'industry.height_range')
        self.assertIn('65-120', normalized(result['answer']))

    def test_stretch_and_foldaway_width_only_excludes_height(self):
        for pid, expected in [('802', ['145-190', '65-90']), ('804', ['186-190', '76-90'])]:
            with self.subTest(product=pid):
                self.new_session(pid)
                result = self.chat('长宽能伸缩多少？', 'answered')
                self.assert_intent(result, 'industry.length_width_range')
                text = normalized(result['answer'])
                for value in expected:
                    self.assertIn(value, text)
                self.assertNotIn('高度', result['answer'])
                self.assertNotIn('100-115', text)
                self.assertNotIn('110-120', text)

    def test_each_height_only_returns_its_range(self):
        cases = [('802', 90, '80-100'), ('802', 110, '100-115'), ('802', 120, '110-120'),
                 ('804', 90, '90-100'), ('804', 110, '100-110'), ('804', 120, '110-120')]
        for pid, height, expected in cases:
            with self.subTest(product=pid, height=height):
                self.new_session(pid)
                result = self.chat(f'{height}高款高度伸缩范围是多少？', 'answered')
                self.assert_intent(result, 'industry.height_range')
                text = normalized(result['answer'])
                self.assertIn(expected, text)
                self.assertNotIn('145-190', text)
                self.assertNotIn('186-190', text)
                for other_pid, _, other in cases:
                    if other_pid == pid and other != expected:
                        self.assertNotIn(other, text)

    def test_dog_height_is_fixed_and_width_is_adjustable(self):
        self.select('803')
        height = self.chat('高度可以伸缩吗？', 'answered')
        self.assert_intent(height, 'industry.height_range')
        self.assertIn('110', height['answer'])
        self.assertRegex(height['answer'], r'固定|不(?:能|可|可以)?(?:伸缩|调节)')
        self.assertNotIn('±4', height['answer'])
        width = self.chat('长宽可以伸缩吗？', 'answered')
        self.assert_intent(width, 'industry.length_width_range')
        self.assertIn('±4', width['answer'])
        self.assertNotIn('65-120', normalized(width['answer']))

    def test_generic_question_can_return_explicit_message_parts(self):
        self.select('802')
        result = self.chat('全部伸缩范围是多少？', 'answered')
        self.assert_intent(result, 'industry.telescoping')
        self.assertGreaterEqual(len(result['answer_parts']), 2)
        self.assertEqual(result['answer'], '\n\n'.join(result['answer_parts']))
        self.assertTrue(any('高度' in p for p in result['answer_parts']))
        self.assertTrue(any('145' in p and '65' in p for p in result['answer_parts']))

    def test_width_correction_keeps_telescope_attribute(self):
        self.select('801')
        self.chat('长宽可以伸缩嘛', 'answered')
        result = self.client.post('/api/chat', json={'session_id': self.sid, 'message': '我问的是长宽'}).json()
        self.assertIn(result['status'], ['answered', 'duplicate'], result)
        self.assert_intent(result, 'industry.length_width_range')
        if result['answer']:
            self.assertIn('固定', result['answer'])
            self.assertIn('全伸缩款', result['answer'])
            self.assertNotIn('高度', result['answer'])
        third = self.client.post('/api/chat', json={'session_id': self.sid, 'message': '？？？'}).json()
        self.assertNotIn('您想了解哪一点', third['answer'])
        self.assertNotIn('您想了解哪一点', third.get('operator_note') or '')
        if third['status'] in ['answered', 'duplicate']:
            self.assert_intent(third, 'industry.length_width_range')
        else:
            self.assertIn(third['status'], ['suppressed', 'clarify'], third)

    def test_standalone_question_marks_still_clarify(self):
        result = self.chat('？？？', 'clarify')
        self.assertTrue(result['answer'])

    def test_dimension_correction_uses_new_product_after_switch(self):
        self.select('801')
        self.chat('长宽可以伸缩嘛', 'answered')
        self.select('804')
        self.assertIsNone(app.state.service.sessions[self.sid].last_dimension)
        self.chat('？？？', 'clarify')
        result = self.chat('长宽可以伸缩嘛', 'answered')
        self.assertEqual(result['session']['current_product_id'], '804')
        self.assertIn('186-190', normalized(result['answer']))
        self.assertNotIn('145-190', normalized(result['answer']))
        self.assertNotIn('长宽固定', result['answer'])

    def test_short_height_followup_keeps_attribute_and_switches_specification(self):
        self.select('802')
        self.chat('90高款高度伸缩范围是多少？', 'answered')
        result = self.chat('那110高呢', 'answered')
        self.assert_intent(result, 'industry.height_range')
        self.assertIn('100-115', normalized(result['answer']))
        self.assertNotIn('80-100', normalized(result['answer']))

    def test_short_axis_followup_keeps_adjustment_attribute(self):
        for followup in ['那宽度呢', '那长度呢']:
            with self.subTest(followup=followup):
                self.new_session('802')
                self.chat('110高款高度能调多少？', 'answered')
                result = self.chat(followup, 'answered')
                self.assert_intent(result, 'industry.length_width_range')
                self.assertIn('145-190', normalized(result['answer']))
                self.assertIn('65-90', normalized(result['answer']))
                self.assertNotIn('高度', result['answer'])

    def test_negated_height_correction_changes_axis(self):
        self.select('801')
        self.chat('120高款高度能调多少？', 'answered')
        result = self.chat('不是高度是长宽', 'answered')
        self.assert_intent(result, 'industry.length_width_range')
        self.assertIn('固定', result['answer'])
        self.assertIn('全伸缩款', result['answer'])
        self.assertNotIn('65-120', normalized(result['answer']))

    def test_unknown_extra_requirement_is_not_silently_dropped(self):
        for question in ['长宽能伸缩吗，还能养熊猫吗', '长宽是多少，还能养熊猫吗',
                         '包含哪些东西，还能养熊猫吗']:
            with self.subTest(question=question):
                self.new_session('801')
                result = self.chat(question, 'handoff')
                self.assertEqual(result['answer'], '')
                self.assertFalse(result['send_to_customer'])

    def test_shortest_length_is_adjustment_not_net_specifications(self):
        self.select('802')
        result = self.chat('长度最短多少', 'answered')
        self.assert_intent(result, 'industry.length_width_range')
        self.assertIn('145', result['answer'])
        self.assertNotIn('高度', result['answer'])

    def test_compound_height_specifications_do_not_lose_first_value(self):
        for question in ['90和110高款高度能调多少？', '90、110高款高度伸缩范围是多少？']:
            with self.subTest(question=question):
                self.new_session('802')
                result = self.chat(question, 'answered')
                self.assert_intent(result, 'industry.height_range')
                text = normalized(result['answer'])
                self.assertIn('80-100', text)
                self.assertIn('100-115', text)
                self.assertNotIn('110-120', text)

    def test_unknown_height_specification_does_not_reuse_nearest_known_range(self):
        self.select('802')
        result = self.chat('100高款高度伸缩范围是多少？', 'handoff')
        self.assertEqual(result['answer'], '')
        self.assertEqual(result['debug']['reason'], 'height_variant_missing')

    def test_memory_and_test_reset_remove_correction_state(self):
        for mode in ['memory', 'test']:
            with self.subTest(mode=mode):
                self.new_session('801')
                self.chat('长宽可以伸缩嘛', 'answered')
                response = self.client.post(f'/api/sessions/{self.sid}/reset', json={'mode': mode})
                self.assertEqual(response.status_code, 200)
                result = self.chat('？？？', 'clarify')
                self.assertNotIn('全伸缩款', result['answer'])
                self.assertNotIn('固定', result['answer'])

    def test_unknown_dimensions_are_not_promised_to_fit(self):
        self.select('802')
        result = self.client.post('/api/chat', json={'session_id': self.sid, 'message': '床宽60厘米能用吗？'}).json()
        self.assertNotRegex(result['answer'], r'完全适用|都能用|肯定能用|可以的亲|放心用|能装下')

    def test_all_four_structure_answers_include_outer_mesh(self):
        for pid in ['801', '802', '803', '804']:
            with self.subTest(product=pid):
                self.new_session(pid)
                result = self.chat('包含哪些东西，帐纱套在哪里？', 'answered')
                self.assert_intent(result, 'industry.structure')
                for word in ['支架', '遮光帘', '帐纱', '最外']:
                    self.assertIn(word, result['answer'])

    def test_dimension_route_cannot_bypass_disabled_answer(self):
        self.select('801')
        for row in app.state.service.kb.faq.records:
            if row['scene_id'] == 'industry.length_width_range' and '801' in row['product_ids']:
                row['status'] = 'disabled'
        result = self.chat('长宽可以伸缩嘛', 'handoff')
        self.assertEqual(result['answer'], '')
        self.assertIn('ineligible', result['debug']['reason'])

    def test_dimension_route_cannot_bypass_presales_scope(self):
        self.select('801')
        result = self.client.post('/api/chat', json={'session_id': self.sid, 'message': '长宽可以伸缩嘛',
            'reception_type': 'aftersales', 'business_stage': 'received'}).json()
        self.assertFalse(result['send_to_customer'], result)
        self.assertEqual(result['answer'], '')


class DimensionAnswerMaintenanceTests(unittest.TestCase):
    setUp = admin_fixtures.FAQAdminTests.setUp
    tearDown = admin_fixtures.FAQAdminTests.tearDown
    snapshot = admin_fixtures.FAQAdminTests.snapshot
    save = admin_fixtures.FAQAdminTests.save

    def row(self, pid, scene):
        return next(copy.deepcopy(row) for row in self.snapshot()['records']
                    if row['scene_id'] == scene and row['product_ids'] == [pid])

    def ask(self, pid, text):
        sid = self.client.post('/api/sessions').json()['session_id']
        result = self.client.post('/api/chat', json={'session_id': sid, 'product_id': pid, 'message': text})
        self.assertEqual(result.status_code, 200)
        return result.json()

    def test_edited_height_values_are_not_replaced_by_old_product_ranges(self):
        row = self.row('802', 'industry.height_range')
        row.pop('answer_parts', None)  # 兼容旧版单文本编辑器。
        row['standard_answer'] = '亲亲，110厘米高度款，高度可调102—114厘米。'
        saved = self.save(row)
        self.assertEqual(saved.status_code, 200, saved.text)
        result = self.ask('802', '110高款高度伸缩范围是多少？')
        self.assertEqual(result['status'], 'answered', result)
        self.assertIn('102-114', normalized(result['answer']))
        self.assertNotIn('100-115', normalized(result['answer']))

    def test_editing_plain_answer_removes_stale_message_parts(self):
        row = self.row('801', 'industry.length_width_range')
        row.pop('answer_parts', None)
        row['standard_answer'] = '亲亲，长宽固定190×90厘米，需要调整长宽推荐全伸缩款哈。'
        saved = self.save(row)
        self.assertEqual(saved.status_code, 200, saved.text)
        result = self.ask('801', '长宽可以伸缩嘛')
        self.assertEqual(result['answer'], row['standard_answer'])
        self.assertEqual(result['answer_parts'], [row['standard_answer']])

    def test_multiline_and_multiple_messages_are_different(self):
        row = self.row('802', 'industry.telescoping')
        parts = ['亲亲，高度范围：\n90高款80—100厘米；110高款100—115厘米。',
                 '长145—190厘米，宽65—90厘米，可按帐纱尺寸选择哈。']
        row.update(answer_parts=parts, standard_answer='\n\n'.join(parts))
        saved = self.save(row)
        self.assertEqual(saved.status_code, 200, saved.text)
        result = self.ask('802', '全部伸缩范围是多少？')
        self.assertEqual(result['answer_parts'], parts)
        self.assertEqual(result['answer'], '\n\n'.join(parts))

    def test_inconsistent_parts_do_not_silently_overwrite_answer(self):
        row = self.row('802', 'industry.height_range')
        row.update(standard_answer='新高度答案', answer_parts=['未同步的旧答案'])
        original = self.path.read_bytes()
        self.assertEqual(self.save(row).status_code, 422)
        self.assertEqual(self.path.read_bytes(), original)
