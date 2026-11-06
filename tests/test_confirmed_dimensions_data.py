import copy
import json
from pathlib import Path
import unittest

from scripts.confirm_dimension_knowledge import (
    CONFIRMED_AT,
    HEIGHT_PARTS,
    LENGTH_WIDTH_ANSWERS,
    MIGRATIONS,
    RANGES,
    STRUCTURE_ANSWER,
    migrate_faq,
)


ROOT = Path(__file__).resolve().parents[1]


def read_data(name):
    return json.loads((ROOT / "data" / name).read_text(encoding="utf-8"))


class ConfirmedDimensionDataTests(unittest.TestCase):
    def setUp(self):
        self.faq = read_data("faq.json")
        self.rows = {row["id"]: row for row in self.faq["records"]}
        self.products = {product["id"]: product for product in read_data("nets_801_804.json")["products"]}

    def test_known_ranges_and_fixed_heights_are_explicit(self):
        for pid, ranges in RANGES.items():
            with self.subTest(product=pid):
                self.assertEqual(self.products[pid]["ranges"], ranges)
                answer = self.rows[f"product.{pid}.height_range"]
                self.assertEqual(answer["answer_parts"], HEIGHT_PARTS[pid])
                self.assertNotIn("长", answer["standard_answer"])
                self.assertNotIn("宽", answer["standard_answer"])
                self.assertEqual(answer["fields"], ["height_range"])
        self.assertIn("不可伸缩", self.rows["product.801.height_range"]["answer_parts"][0])
        self.assertIn("不可伸缩", self.rows["product.801.height_range"]["answer_parts"][1])
        self.assertIn("高度固定110厘米", self.rows["product.803.height_range"]["standard_answer"])

    def test_length_width_answers_do_not_borrow_height(self):
        for pid, answer in LENGTH_WIDTH_ANSWERS.items():
            with self.subTest(product=pid):
                row = self.rows[f"product.{pid}.length_width_range"]
                self.assertEqual(row["standard_answer"], answer)
                self.assertEqual(row["fields"], ["length_width_range"])
                self.assertNotIn("高度", answer)
        self.assertIn("长宽固定不可伸缩", LENGTH_WIDTH_ANSWERS["801"])
        self.assertIn("全伸缩款", LENGTH_WIDTH_ANSWERS["801"])
        self.assertIn("±4", LENGTH_WIDTH_ANSWERS["803"])

    def test_complete_ranges_have_separate_height_and_length_width_parts(self):
        for pid in self.products:
            row = self.rows[f"product.{pid}.telescoping"]
            self.assertEqual(len(row["answer_parts"]), 2)
            self.assertEqual(row["answer_parts"][0], "\n".join(HEIGHT_PARTS[pid]))
            self.assertEqual(row["answer_parts"][1], LENGTH_WIDTH_ANSWERS[pid])
            self.assertNotIn("伸缩", row["keywords"])
        for row in self.rows.values():
            if row.get("answer_parts"):
                self.assertEqual(row["standard_answer"], "\n\n".join(row["answer_parts"]))

    def test_structure_is_confirmed_for_every_product(self):
        for pid in self.products:
            row = self.rows[f"product.{pid}.structure"]
            self.assertEqual(row["standard_answer"], STRUCTURE_ANSWER)
            self.assertEqual(row["product_ids"], [pid])
            self.assertEqual(row["conditions"]["reception"], "presales")
            self.assertEqual(row["conditions"]["stages"], ["presales"])
            self.assertIn("支架＋遮光帘＋帐纱", row["standard_answer"])
            self.assertIn("最外层", row["standard_answer"])
            self.assertEqual(self.products[pid]["facts"]["structure"], STRUCTURE_ANSWER)

    def test_old_source_answers_are_synced_without_erasing_originals(self):
        sources = {row["id"]: row for row in read_data("source_qa.json")["records"]}
        self.assertEqual(len(sources), 110)
        for source_id, product_id, intent in (("qa.801.C16", "801", "height_range"), ("qa.802.C8", "802", "telescoping")):
            original = sources[source_id]
            canonical = self.rows[f"product.{product_id}.{intent}"]
            compiled = self.rows[source_id]
            self.assertEqual(compiled["standard_answer"], canonical["standard_answer"])
            self.assertEqual(compiled["answer_parts"], canonical["answer_parts"])
            self.assertEqual(original["answer"], canonical["standard_answer"])
            self.assertEqual(original["fields"], [intent])
            self.assertTrue(original["original_answer"])
            self.assertEqual(original["confirmed_at"], CONFIRMED_AT)
            self.assertEqual(compiled["priority"], 0)
            self.assertGreaterEqual(canonical["priority"], 1)
            self.assertGreater(canonical["priority"], compiled["priority"])
            self.assertTrue(all(source in canonical["sources"] for source in compiled["sources"]))

    def test_scene_boundaries_and_origins_are_explicit(self):
        scenes = {scene["id"]: scene for scene in self.faq["scenes"]}
        generic = scenes["industry.telescoping"]
        self.assertNotIn("高度可伸缩是什么意思", generic["question_variants"])
        self.assertIn("高度可伸缩是什么意思", scenes["industry.height_range"]["question_variants"])
        self.assertIn("长宽可以伸缩嘛", scenes["industry.length_width_range"]["question_variants"])
        for pid in self.products:
            for intent in ("height_range", "length_width_range", "telescoping", "structure"):
                row = self.rows[f"product.{pid}.{intent}"]
                self.assertTrue(any(source.get("date") == CONFIRMED_AT for source in row["sources"]))

    def test_migration_is_idempotent_for_all_files(self):
        for filename, migrate in MIGRATIONS.items():
            with self.subTest(file=filename):
                doc = read_data(filename)
                self.assertEqual(migrate(doc), doc)
                self.assertEqual(migrate(migrate(doc)), doc)
        doc=read_data('faq.json')
        row=next(r for r in doc['records'] if r['id']=='product.802.telescoping')
        row['updated_at']='2026-10-22T12:00:00+00:00'
        self.assertEqual(migrate_faq(doc),doc)

    def test_migration_does_not_rewrite_unrelated_answers_or_images(self):
        before = copy.deepcopy(self.faq)
        untouched = self.rows["product.801.material"]
        marker = next(row for row in before["records"] if row["id"] == untouched["id"])
        marker["standard_answer"] = "维护者自己的材质答复"
        marker["images"] = [{"id": "manual-image", "url": "/static/images/manual.png"}]
        marker["conditions"]["valid_until"] = "2026-12-31"
        result = migrate_faq(before)
        self.assertEqual(marker, next(row for row in result["records"] if row["id"] == marker["id"]))

    def test_existing_higher_canonical_priority_is_preserved(self):
        before = copy.deepcopy(self.faq)
        canonical = next(row for row in before["records"] if row["id"] == "product.801.height_range")
        canonical["priority"] = 200
        result = migrate_faq(before)
        rows = {row["id"]: row for row in result["records"]}
        self.assertEqual(rows["product.801.height_range"]["priority"], 200)
        self.assertEqual(rows["qa.801.C16"]["priority"], 0)


if __name__ == "__main__":
    unittest.main()
