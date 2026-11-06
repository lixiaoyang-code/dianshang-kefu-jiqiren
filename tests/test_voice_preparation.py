import unittest
from scripts.test_customer_voices import prepare,redact


class VoicePreparationTests(unittest.TestCase):
    def test_person_rule_wins_over_sheet_name_and_missing_person_uses_sheet(self):
        values=prepare([{'name':'售前表','rows':[{'A1':'人员','B1':'客户原声','C1':'产品名称'},
            {'A2':'李晓洋','B2':'长宽可以调吗','C2':'801'},
            {'A3':'其他人','B3':'可以退吗','C3':'801,802'},
            {'B4':'你好'}]}])
        self.assertEqual(values[0]['reception'],'presales');self.assertEqual(values[0]['selected_product'],'801')
        self.assertEqual(values[1]['reception'],'aftersales');self.assertTrue(values[1]['classification_conflict'])
        self.assertIsNone(values[1]['selected_product'])
        self.assertEqual(values[2]['classification_basis'],'无人员：按表名推断')
        self.assertEqual(values[2]['domain'],'商品未确定')

    def test_unconnected_product_never_borrows_801_and_contacts_are_redacted(self):
        v=prepare([{'name':'冬季品','rows':[{'A1':'人员','B1':'客户原声','C1':'产品名称'},
            {'A2':'黄伟龙','B2':'能机洗吗 联系13812345678','C2':'电热毯'}]}])[0]
        self.assertIsNone(v['selected_product']);self.assertEqual(v['domain'],'未接入商品')
        self.assertNotIn('13812345678',v['question']);self.assertIn('[手机号]',v['question'])
        self.assertNotIn('ark-abcdef',redact('ark-abcdef'))
