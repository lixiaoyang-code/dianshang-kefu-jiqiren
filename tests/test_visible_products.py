import unittest
from fastapi.testclient import TestClient
from app.main import app
from app.product_labels import public_text
from app.rag import RAGAssistant

class VisibleProductsTests(unittest.TestCase):
    def test_one_blanket_in_all_choices_without_deleting_archived_knowledge(self):
        with TestClient(app) as client:
            for route in ['/api/products','/api/faq','/api/scenes','/api/materials']:
                value=client.get(route).json()
                products=value if isinstance(value,list) else value['products']
                self.assertNotIn('nonwovenblanket',[p['id'] for p in products],route)
                self.assertEqual([p['id'] for p in products if p['name']=='电热毯'],['plushblanket'],route)
            kb=app.state.service.kb
            self.assertIn('nonwovenblanket',kb.products)
            self.assertTrue(any('nonwovenblanket' in r['product_ids'] for r in kb.faq.records))
            self.assertEqual(kb.mentions('电热毯'),['plushblanket'])
            self.assertEqual(kb.mentions('无纺布电热毯的参数'),['nonwovenblanket'])
            rag=RAGAssistant(kb,app.state.service.model)
            targets,_=rag._scope('电热毯怎么选','plushblanket')
            self.assertNotIn('nonwovenblanket',targets)
            self.assertEqual(public_text('电热毯-1／长毛绒电热毯／plushblanket'),'电热毯／电热毯／电热毯')
