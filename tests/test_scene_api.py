import unittest
import test_faq_admin as fixtures


class SceneAPITests(unittest.TestCase):
    setUp=fixtures.FAQAdminTests.setUp
    tearDown=fixtures.FAQAdminTests.tearDown
    snapshot=fixtures.FAQAdminTests.snapshot
    save=fixtures.FAQAdminTests.save

    def scene(self,type='industry',variants=None):
        body={'revision':self.snapshot()['revision'],'scene':{'name':'赠品测试场景',
              'type':type,'question_variants':variants or ['有没有测试赠品','可以送测试赠品吗'],'category':'优惠赠品'}}
        r=self.client.post('/api/scenes',json=body)
        self.assertEqual(r.status_code,200,r.text)
        return r.json()['scene']

    def answer(self,scene,pid='801',answer='测试标准答案',conditions=None,**extras):
        row={'scene_id':scene['id'],'standard_answer':answer,'scope':'product',
             'product_ids':[pid],'answer_product_id':pid,'status':'active','images':[],
             'conditions':conditions or {},'keywords':[],**extras}
        r=self.save(row);self.assertEqual(r.status_code,200,r.text)
        return r.json()['record']

    def ask(self,text,pid='801',reception='presales',stage='presales'):
        sid=self.client.post('/api/sessions').json()['session_id']
        return self.client.post('/api/chat',json={'session_id':sid,'product_id':pid,
            'message':text,'reception_type':reception,'business_stage':stage}).json()

    def test_grouped_list_keeps_answers_and_variants(self):
        scene=self.scene();self.answer(scene);self.answer(scene,'803','另一个商品的测试答案')
        grouped=self.client.get('/api/scenes').json()['scenes']
        selected=next(s for s in grouped if s['id']==scene['id'])
        self.assertEqual(len(selected['answers']),2)
        self.assertEqual(selected['type'],'industry')
        self.assertEqual(self.ask('可以送测试赠品吗')['answer'],'测试标准答案')
        self.assertEqual(self.ask('可以送测试赠品吗','803')['answer'],'另一个商品的测试答案')
        self.assertFalse(self.ask('可以送测试赠品吗','804')['send_to_customer'])

    def test_stage_and_reception_actually_select_different_answers(self):
        scene=self.scene()
        self.answer(scene,answer='售前测试答案',conditions={'reception':'presales','stages':['presales']})
        self.answer(scene,answer='售后测试答案',conditions={'reception':'aftersales','stages':['aftersales']})
        self.assertEqual(self.ask('有没有测试赠品')['answer'],'售前测试答案')
        self.assertEqual(self.ask('有没有测试赠品',reception='aftersales',stage='aftersales')['answer'],'售后测试答案')
        self.assertFalse(self.ask('有没有测试赠品',stage='shipping')['send_to_customer'])

    def test_keywords_do_not_bypass_conditions(self):
        scene=self.scene('special')
        self.answer(scene,answer='售后关键词测试答案',keywords=['补送','礼品'],keyword_mode='all',
                    conditions={'reception':'aftersales','stages':['received']})
        self.assertEqual(self.ask('需要补送礼品',reception='aftersales',stage='received')['answer'],'售后关键词测试答案')
        self.assertFalse(self.ask('需要补送礼品')['send_to_customer'])

    def test_priority_and_expired_custom_fall_back(self):
        base=self.scene();self.answer(base,answer='行业测试答案')
        special=self.scene('special');self.answer(special,answer='特殊测试答案')
        custom=self.scene('custom');self.answer(custom,answer='过期测试答案',conditions={'valid_until':'2020-01-01T00:00:00+08:00'})
        self.assertEqual(self.ask('有没有测试赠品')['answer'],'特殊测试答案')
        current=self.scene('custom');self.answer(current,answer='自定义测试答案')
        self.assertEqual(self.ask('有没有测试赠品')['answer'],'自定义测试答案')

    def test_duplicate_condition_conflict_is_not_auto_answered(self):
        scene=self.scene();self.answer(scene,answer='测试答案A');self.answer(scene,answer='测试答案B')
        result=self.ask('有没有测试赠品')
        self.assertFalse(result['send_to_customer']);self.assertEqual(result['debug']['reason'],'scene_ambiguous')

    def test_scene_edit_updates_shared_questions(self):
        scene=self.scene();self.answer(scene)
        scene.update(name='新场景名',question_variants=['新原声测试'],type='special')
        r=self.client.post('/api/scenes',json={'revision':self.snapshot()['revision'],'scene':scene})
        self.assertEqual(r.status_code,200)
        self.assertEqual(self.ask('新原声测试')['answer'],'测试标准答案')

    def test_invalid_time_and_reception_are_rejected(self):
        scene=self.scene();row={'scene_id':scene['id'],'standard_answer':'测试',
             'scope':'product','product_ids':['801'],'status':'active','images':[],
             'conditions':{'valid_from':'2030-01-01','valid_until':'2020-01-01'}}
        self.assertEqual(self.save(row).status_code,422)
        sid=self.client.post('/api/sessions').json()['session_id']
        self.assertEqual(self.client.post('/api/chat',json={'session_id':sid,'message':'测试','business_stage':'unknown'}).status_code,422)

    def test_clear_product_does_not_keep_old_binding(self):
        sid=self.client.post('/api/sessions').json()['session_id']
        url=f'/api/sessions/{sid}/events'
        self.client.post(url,json={'type':'customer_select','product_id':'801'})
        r=self.client.post(url,json={'type':'customer_select','product_id':None}).json()
        self.assertIsNone(r['current_product_id']);self.assertFalse(r['product_confirmed'])

    def test_raw_keywords_survive_question_normalization(self):
        scene=self.scene('special',variants=['用于识别顶棚的问题'])
        self.answer(scene,answer='已批准的顶棚测试答案',keywords=['顶棚'])
        self.assertEqual(self.ask('顶棚怎么样')['answer'],'已批准的顶棚测试答案')

    def test_unknown_product_code_does_not_reuse_bound_product(self):
        scene=self.scene();self.answer(scene,keywords=['测试赠品'])
        result=self.ask('805有没有测试赠品')
        self.assertEqual(result['debug']['reason'],'unknown_product_code')

    def test_editing_size_scene_does_not_replace_computed_fit_reply(self):
        scene=next(s for s in self.client.get('/api/scenes').json()['scenes'] if s['id']=='industry.specifications')
        row=scene['answers'][0]
        self.assertEqual(self.save(row).status_code,200)
        sid=self.client.post('/api/sessions').json()['session_id']
        self.client.post('/api/chat',json={'session_id':sid,'product_id':'802','message':'802尺寸'})
        r=self.client.post('/api/chat',json={'session_id':sid,'message':'90*190可以用吗'}).json()
        self.assertEqual(r['status'],'answered');self.assertIn('可以的',r['answer'])
