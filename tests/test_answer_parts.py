"""回复分段只修改临时知识库，不改项目中的商品资料。"""
import copy
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

from app.config import ROOT
from app.faq_admin import FAQStore, SaveFAQ


class AnswerPartsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.path=Path(self.temp.name)/'faq.json'
        self.path.write_bytes((ROOT/'data/faq.json').read_bytes())
        self.store=FAQStore(self.path)
        self.doc,self.revision=self.store.read()
        self.original=next(copy.deepcopy(row) for row in self.doc['records']
                           if row['id']=='product.801.stability')

    def tearDown(self):
        self.temp.cleanup()

    def save(self,record):
        return self.store.save(SaveFAQ(revision=self.revision,record=record),
                               ['801','802','803','804'],lambda doc:doc)

    def test_inline_patch_keeps_scope_images_status_and_sources(self):
        parts=['第一条：高度\n保留段内换行','第二条：长宽']
        row,self.revision,_=self.save({'id':self.original['id'],
                                     'standard_answer':'\n\n'.join(parts),
                                     'answer_parts':parts})
        self.assertEqual(row['answer_parts'],parts)
        self.assertEqual(row['standard_answer'],'\n\n'.join(parts))
        for key in ('status','product_ids','scope','images','sources','conditions','boundaries'):
            self.assertEqual(row.get(key),self.original.get(key),key)

    def test_legacy_single_text_edit_drops_stale_parts(self):
        row,self.revision,_=self.save({'id':self.original['id'],
                                     'standard_answer':'第一条\n\n第二条',
                                     'answer_parts':['第一条','第二条']})
        row,self.revision,_=self.save({'id':row['id'],'standard_answer':'旧页面修改的单条\n可换行'})
        self.assertEqual(row['answer_parts'],['旧页面修改的单条\n可换行'])

    def test_invalid_parts_never_change_document(self):
        for parts,answer in [(['第一条','第二条'],'不一致'),
                             (['有效',''],'有效\n\n'),
                             (['a']*9,'\n\n'.join(['a']*9)),
                             (['a'*4001],'a'*4001),
                             ('不是列表','不是列表'),
                             ([123],'123'),
                             (['a'*4000]*4,'\n\n'.join(['a'*4000]*4))]:
            with self.subTest(parts_type=type(parts).__name__,size=len(answer)):
                before=self.path.read_bytes()
                with self.assertRaises(HTTPException) as raised:
                    self.save({'id':self.original['id'],'standard_answer':answer,'answer_parts':parts})
                self.assertEqual(raised.exception.status_code,422)
                self.assertEqual(self.path.read_bytes(),before)

    def test_draft_keeps_draft_status_and_can_have_empty_answer(self):
        draft=copy.deepcopy(self.original)
        draft.update(status='needs_review',standard_answer='',answer_parts=[])
        row,self.revision,_=self.save(draft)
        self.assertEqual(row['status'],'needs_review')
        row,self.revision,_=self.save({'id':row['id'],'standard_answer':'待确认的完善答案',
                                     'answer_parts':['待确认的完善答案']})
        self.assertEqual(row['status'],'needs_review')


if __name__=='__main__':
    unittest.main()
