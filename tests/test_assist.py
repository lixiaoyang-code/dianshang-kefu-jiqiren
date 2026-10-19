import time
from unittest.mock import patch
import unittest
import test_nets as fixtures


class AssistTests(unittest.TestCase):
    setUp = fixtures.NetsTests.setUp
    tearDown = fixtures.NetsTests.tearDown
    chat = fixtures.NetsTests.chat
    """沿用真实商品测试环境；检查新增行为和误承诺风险。"""
    def test_fit_then_unknown_then_continue(self):
        self.chat('802尺寸','answered')
        r=self.chat('90*190可以用吗','answered')
        self.assertIn('可以的亲',r['answer'])
        self.assertLess(len(r['answer']),60)
        self.chat('802防火报告','handoff')
        self.chat('802壁厚','answered')

    def test_fit_unknown_height(self):
        self.chat('803尺寸','answered')
        r=self.chat('90×190×120可以用吗','answered')
        self.assertNotIn('可以的亲',r['answer'])

    def test_fit_unknown_size(self):
        self.chat('802尺寸','answered')
        self.chat('100×200可以用吗','answered')

    def test_fit_question_does_not_hide_extra_promise(self):
        self.chat('802尺寸','answered')
        self.chat('90*190可以用吗，保证防火吗','handoff')

    def test_delivery_choice(self):
        r=self.chat('多久到货','answered')
        self.assertIn('显示',r['answer'])

    def test_non_jd_dispatch_not_arrival(self):
        r=self.chat('页面没有京东物流，多久发货','answered')
        self.assertIn('24小时发出',r['answer'])
        self.assertNotIn('24小时送达',r['answer'])

    def test_jd_estimate(self):
        r=self.chat('页面显示京东物流，多久到','answered')
        self.assertIn('一般',r['answer'])
        self.assertIn('下单页面',r['answer'])

    def test_expedite_not_fulfilled_claim(self):
        r=self.chat('今天可以发出吗','answered')
        self.assertIn('申请加急',r['answer'])
        self.assertNotIn('已安排',r['answer'])

    def test_unknown_no_customer_reply(self):
        r=self.chat('802保修几年','handoff')
        self.assertEqual(r['answer'],'')
        self.assertTrue(r['operator_note'])

    def test_error_does_not_latch(self):
        from app.main import app
        with patch.object(app.state.service.model,'select',side_effect=TimeoutError()):
            r=self.chat('802材质','error')
            self.assertFalse(r['send_to_customer'])
        self.chat('802材质','answered')

    def test_wait_once_after_25_seconds(self):
        from app.main import app
        r=self.chat('802保修几年','handoff');rid=r['debug']['request_id']
        url=f'/api/sessions/{self.sid}/waiting/{rid}'
        self.assertFalse(self.client.post(url).json()['send_to_customer'])
        app.state.service.sessions[self.sid].waiting[rid]['received_at']=time.perf_counter()-26
        reply=self.client.post(url).json()
        self.assertTrue(reply['send_to_customer'])
        self.assertIn('正在看',reply['answer'])
        self.assertFalse(self.client.post(url).json()['send_to_customer'])

    def test_human_handled_cancels_wait(self):
        r=self.chat('802保修几年','handoff');rid=r['debug']['request_id']
        self.client.post(f'/api/sessions/{self.sid}/events',json={'type':'handled'})
        self.assertFalse(self.client.post(f'/api/sessions/{self.sid}/waiting/{rid}').json()['send_to_customer'])

    def test_answer_cancels_previous_wait(self):
        r=self.chat('802保修几年','handoff');rid=r['debug']['request_id']
        self.chat('802壁厚','answered')
        self.assertFalse(self.client.post(f'/api/sessions/{self.sid}/waiting/{rid}').json()['send_to_customer'])

    def test_no_resume_control(self):
        html=self.client.get('/').text
        self.assertNotIn('id="resume"',html)
        self.assertNotIn('id="takeover"',html)
