import copy
import threading
import unittest
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace

import numpy as np
from app.semantic import Encoder, SemanticRetriever


class CountingEncoder(Encoder):
    def __init__(self):
        self.np=np
        self._index_vectors=OrderedDict()
        self._index_lock=threading.Lock()
        self.calls=[]

    def encode(self,texts):
        self.calls.append(list(texts))
        return np.array([[len(text),1,2] for text in texts],dtype=np.float32).reshape(-1,3)


def knowledge(answer='steel',variants=None):
    row={'id':'faq.material','status':'active','scope':'product','product_ids':['801'],
         'fields':['material'],'intent':'material','standard_answer':answer,'sources':[],
         'images':[],'question_variants':variants or ['what material','what material','frame material']}
    return SimpleNamespace(products={'801':{'facts':{}}},qa_records=[],faq=SimpleNamespace(records=[row]))


class IndexCacheTests(unittest.TestCase):
    def test_duplicate_questions_encode_once_but_keep_index_alignment(self):
        encoder=CountingEncoder();index=SemanticRetriever(knowledge(),encoder)
        self.assertEqual(encoder.calls,[['what material','frame material']])
        self.assertEqual(index.vectors.shape,(3,3))
        self.assertEqual(index.owners,[0,0,0])
        np.testing.assert_array_equal(index.vectors[0],index.vectors[1])

    def test_answer_updates_use_fresh_metadata_and_reuse_vectors(self):
        encoder=CountingEncoder();before=SemanticRetriever(knowledge(),encoder)
        after=SemanticRetriever(knowledge('aluminium'),encoder)
        self.assertEqual(len(encoder.calls),1)
        self.assertEqual(before.docs[0]['answer'],'steel')
        self.assertEqual(after.docs[0]['answer'],'aluminium')
        kb=knowledge();kb.faq.records[0]['status']='disabled'
        self.assertEqual(SemanticRetriever(kb,encoder).docs,[])

    def test_only_new_questions_are_encoded_and_removed_ones_leave_index(self):
        encoder=CountingEncoder();SemanticRetriever(knowledge(),encoder)
        index=SemanticRetriever(knowledge(variants=['frame material','new question']),encoder)
        self.assertEqual(encoder.calls[-1],['new question'])
        self.assertEqual(index.texts,['frame material','new question'])
        self.assertEqual(index.vectors.shape,(2,3))

    def test_parallel_builds_do_not_duplicate_encoding(self):
        encoder=CountingEncoder()
        with ThreadPoolExecutor(max_workers=3) as pool:
            arrays=list(pool.map(lambda _:encoder.encode_index(['same question']),range(3)))
        self.assertEqual(encoder.calls,[['same question']])
        self.assertTrue(all(a.shape==(1,3) for a in arrays))
