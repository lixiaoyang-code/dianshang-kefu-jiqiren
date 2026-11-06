import json
import tempfile
import unittest
from pathlib import Path

from scripts.remove_reply_brands import clean_text, migrate_faq, run


class ReplyBrandCleanupTests(unittest.TestCase):
    def test_brand_endorsement_is_removed_without_affirming_supplier(self):
        document = {'records': [{'id': 'supplier', 'status': 'active',
            'question_variants': ['原材料是巴斯夫的吗？'],
            'standard_answer': '是的，原料是巴斯夫 CosyPUR 慢回弹记忆棉。',
            'answer_parts': ['是的，原料是巴斯夫 CosyPUR 慢回弹记忆棉。'],
            'sources': [{'excerpt': '原料是巴斯夫 CosyPUR 慢回弹记忆棉。'}]}]}
        updated, changes = migrate_faq(document)
        row = updated['records'][0]
        self.assertEqual(row['status'], 'disabled')
        self.assertEqual(row['standard_answer'], '')
        self.assertEqual(row['answer_parts'], [])
        self.assertEqual(row['sources'], document['records'][0]['sources'])
        self.assertEqual(changes, [{'id': 'supplier', 'action': 'disabled'}])
        self.assertEqual(document['records'][0]['status'], 'active')

    def test_preserves_parameters_boundaries_parts_and_pending_status(self):
        answer = '半弦月取暖器高730MM左右，具体请以实物为准。'
        doc = {'records': [{'id': 'size', 'status': 'needs_review', 'question_variants': ['多高'],
                           'standard_answer': answer, 'answer_parts': [answer]}]}
        updated, _ = migrate_faq(doc)
        row = updated['records'][0]
        self.assertEqual(row['standard_answer'], '取暖器高730MM左右，具体请以实物为准。')
        self.assertEqual(row['answer_parts'], [row['standard_answer']])
        self.assertEqual(row['status'], 'needs_review')
        self.assertEqual(clean_text('注：以上数据为半弦月实验室在实验环境下测试温度，具体因使用环境不同会有差异。'),
                         '注：以上为实验环境下的参考温度，具体因使用环境不同会有差异。')
        self.assertEqual(clean_text('京东物流配送；非京东物流按页面为准。'), '京东物流配送；非京东物流按页面为准。')

    def test_atomic_migration_is_idempotent_and_keeps_source_history(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)
            original = {'records': [{'id': 'size', 'status': 'active', 'question_variants': ['多高'],
                'standard_answer': '半弦月取暖器高730MM左右。', 'answer_parts': ['半弦月取暖器高730MM左右。']}]}
            raw = json.dumps(original, ensure_ascii=False).encode()
            (path / 'faq.json').write_bytes(raw)
            source = {'records': [{'id': 'old', 'original_answer': '半弦月取暖器高730MM左右。',
                                    'answer': '半弦月取暖器高730MM左右。'}]}
            (path / 'source_qa.json').write_text(json.dumps(source), encoding='utf-8')
            first = run(path)
            self.assertEqual(len(first['faq.json']), 1)
            backup = next((path / 'backups').glob('*faq-*'))
            self.assertEqual(backup.read_bytes(), raw)
            self.assertTrue(all(not changes for changes in run(path).values()))
            updated_source = json.loads((path / 'source_qa.json').read_bytes())['records'][0]
            self.assertEqual(updated_source['original_answer'], source['records'][0]['original_answer'])
            self.assertNotIn('半弦月', updated_source['answer'])


if __name__ == '__main__':
    unittest.main()
