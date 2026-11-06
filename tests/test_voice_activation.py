import copy
import unittest
from scripts.import_voice_answers import curate,apply,digest
from scripts.onboard_catalog import record


class VoiceActivationTests(unittest.TestCase):
    def test_no_unsafe_washing_or_medical_claim_is_enabled(self):
        for pid,q,a in [('plushblanket','尿床会漏电吗','不会，擦干就可以'),
                        ('tietie','颈椎病能用吗','七天有效'),
                        ('nonwovenblanket','可以机洗吗','直接丢洗衣机')]:
            r=record(pid,'test',q,[q],a,'needs_review')
            self.assertEqual(curate(r,{'records':[]})[0]['status'],'needs_review')

    def test_power_math_and_no_unlimited_freight_promise(self):
        r=record('plushblanket','test','耗电多少',['耗电多少'],'双人160W十小时1度','needs_review')
        fixed,_=curate(r,{'records':[]})
        self.assertEqual(fixed['status'],'active');self.assertIn('1.6度',fixed['standard_answer'])
        r=record('tietie','insurance','运费险全包吗',['运费险全包吗'],'超重也全包','needs_review')
        fixed,_=curate(r,{'records':[]});self.assertIn('超出部分',fixed['standard_answer'])

    def test_migration_preserves_manual_edits_and_is_idempotent(self):
        r=record('601','test','几开门',['几开门'],'U型三开门','needs_review')
        n=copy.deepcopy(r);n['status']='active'
        d={'records':[r],'scenes':[]};package={'updates':[{'before':digest(r),'row':n}],'variants':{},'held':[]}
        updated,c=apply(d,package);self.assertEqual(c['activated'],1)
        again,c=apply(updated,package);self.assertEqual(c['activated'],0);self.assertEqual(again,updated)
        edited=copy.deepcopy(d);edited['records'][0]['standard_answer']='云端手工改过'
        kept,c=apply(edited,package);self.assertEqual(c['activated'],0)
        self.assertEqual(kept['records'][0]['standard_answer'],'云端手工改过')
