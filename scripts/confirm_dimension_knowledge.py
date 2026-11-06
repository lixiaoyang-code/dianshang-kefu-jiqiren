"""按 2026-10-22 商家确认拆分尺寸意图，保留其他话术、图片和来源。

可重复执行。只更新本次确认的伸缩与组成知识；写入前备份所有变化文件。
"""
from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONFIRMED_AT = "2026-10-22"
PRODUCT_IDS = ("801", "802", "803", "804")

HEIGHT_PARTS = {
    "801": [
        "90厘米高度款：高度固定90厘米，不可伸缩。",
        "110厘米高度款：高度固定110厘米，不可伸缩。",
        "120厘米高度款：高度可以在65–120厘米之间调节哈～",
    ],
    "802": [
        "90厘米高度款：高度可以在80–100厘米之间调节哈～",
        "110厘米高度款：高度可以在100–115厘米之间调节哈～",
        "120厘米高度款：高度可以在110–120厘米之间调节哈～",
    ],
    "803": ["110厘米高度款：高度固定110厘米，不可伸缩。"],
    "804": [
        "90厘米高度款：高度可以在90–100厘米之间调节哈～",
        "110厘米高度款：高度可以在100–110厘米之间调节哈～",
        "120厘米高度款：高度可以在110–120厘米之间调节哈～",
    ],
}
LENGTH_WIDTH_ANSWERS = {
    "801": "亲亲，纯色款长190厘米、宽90厘米，长宽固定不可伸缩；如果需要调节长宽，这边推荐全伸缩款哈～",
    "802": "亲亲，全伸缩款长度可以在145–190厘米之间调节，宽度支持65–90厘米伸缩哈～选购参考帐纱本身的尺寸来挑就好。",
    "803": "亲亲，小狗款以长190厘米、宽90厘米为基准，长宽都可以±4厘米调节哈～",
    "804": "亲亲，免安装款长度可以在186–190厘米之间调节，宽度支持76–90厘米伸缩哈～",
}
STRUCTURE_ANSWER = "亲亲，四款都是支架＋遮光帘＋帐纱，帐纱套在最外层的哈～"
RANGES = {
    "801": {"length": [190, 190], "width": [90, 90], "height": {"90": [90, 90], "110": [110, 110], "120": [65, 120]}},
    "802": {"length": [145, 190], "width": [65, 90], "height": {"90": [80, 100], "110": [100, 115], "120": [110, 120]}},
    "803": {"length": [186, 194], "width": [86, 94], "height": {"110": [110, 110]}},
    "804": {"length": [186, 190], "width": [76, 90], "height": {"90": [90, 100], "110": [100, 110], "120": [110, 120]}},
}
SCENES = {
    "height_range": {
        "name": "高度能否调节、范围是多少？",
        "description": "只询问支架高度是否可调、最高最低和各高度款的范围；不回答长宽。90/110/120为高度款条件，不另建意图。",
        "question_variants": [
            "高度能否调节、范围是多少？", "支架高度可以调节多少？", "伸缩高度是多少？", "高度能调多少",
            "高度能伸缩吗", "高度可以调节吗", "高度是固定的吗", "高度可伸缩是什么意思", "最高多高", "最低能降到多少",
        ],
    },
    "length_width_range": {
        "name": "长宽能否调节、范围是多少？",
        "description": "询问支架长度或宽度是否可调及范围，包括单独问长度、宽度；不把高度范围或帐纱规格当成长宽伸缩范围。",
        "question_variants": [
            "长宽能否调节、范围是多少？", "长宽可以伸缩吗", "长宽可以伸缩嘛", "长宽能调吗", "长宽能调多少",
            "长宽固定吗", "长度可以调节吗", "长度能伸缩吗", "长度最短多少", "长度调节范围是多少",
            "宽度能伸缩吗", "宽度可以调节吗", "宽度能调多少", "宽度调节范围是多少",
        ],
    },
    "telescoping": {
        "name": "支架整体伸缩范围是多少？",
        "description": "客户未指定维度，询问支架整体或长宽高全部的调节范围；明确问长宽归长宽意图，明确问高度归高度意图。全伸缩选款推荐单独处理。",
        "question_variants": [
            "支架整体伸缩范围是多少？", "支架伸缩范围是多少？", "大小能调吗", "能不能调整长宽高", "支架可以伸缩吗",
            "伸缩范围", "全部伸缩范围是多少", "长宽高分别能调多少", "长宽高调节范围是多少",
        ],
    },
    "structure": {
        "name": "一套包括什么？帐纱套在哪层？",
        "description": "询问套装组成及帐纱、遮光帘、支架的层次：四款均含支架、遮光帘、帐纱，帐纱在最外层；材质、安装步骤、防蚊效果各有独立意图。",
        "question_variants": [
            "一套包括什么？帐纱套在哪层？", "一套包括什么", "这款包含什么", "都有什么组成", "一套有哪几部分", "是几件套",
            "包含帐纱吗", "有支架和遮光帘吗", "帐纱套在哪一层", "帐纱在里面还是外面", "蚊帐套在外面吗", "最外层是什么",
        ],
    },
}


def answer_parts(pid: str, intent: str) -> list[str]:
    if intent == "height_range":
        return list(HEIGHT_PARTS[pid])
    if intent == "length_width_range":
        return [LENGTH_WIDTH_ANSWERS[pid]]
    if intent == "structure":
        return [STRUCTURE_ANSWER]
    if intent == "telescoping":
        return ["\n".join(HEIGHT_PARTS[pid]), LENGTH_WIDTH_ANSWERS[pid]]
    raise ValueError(intent)


def confirmation_source(pid: str, intent: str) -> dict:
    return {
        "type": "user_confirmation",
        "date": CONFIRMED_AT,
        "reference": "本聊天：四款伸缩范围及套装组成确认",
        "excerpt": "\n\n".join(answer_parts(pid, intent)),
        "note": "本次确认优先于旧资源库中的冲突参数；旧来源保留用于追溯。",
    }


def with_confirmation(sources: list, pid: str, intent: str) -> list:
    result = copy.deepcopy(sources)
    source = confirmation_source(pid, intent)
    if source not in result:
        result.append(source)
    return result


def set_record(row: dict, pid: str, intent: str) -> None:
    previous=copy.deepcopy(row)
    scene = SCENES[intent]
    parts = answer_parts(pid, intent)
    row.update(
        intent=intent,
        scene_id=f"industry.{intent}",
        scene_name=scene["name"],
        scene_type="industry",
        question_variants=list(scene["question_variants"]),
        standard_answer="\n\n".join(parts),
        answer_parts=parts,
        fields=[intent],
        configured_scene=True,
        updated_at=CONFIRMED_AT,
    )
    # 仅移除会跨维度误触发的旧词；保留维护者其他精确关键词及条件。
    row["keywords"] = [word for word in row.get("keywords", []) if word != "伸缩"]
    row["sources"] = with_confirmation(row.get("sources", []), pid, intent)
    if {k:v for k,v in previous.items() if k!='updated_at'}=={k:v for k,v in row.items() if k!='updated_at'}:
        row['updated_at']=previous.get('updated_at',CONFIRMED_AT)


def migrate_faq(document: dict) -> dict:
    doc = copy.deepcopy(document)
    scenes = {scene["id"]: scene for scene in doc["scenes"]}
    for intent, definition in SCENES.items():
        key = f"industry.{intent}"
        scene = scenes.get(key, {})
        scene.update(id=key, type="industry", category="商品参数", configured=True, **copy.deepcopy(definition))
        scenes[key] = scene
    doc["scenes"] = list(scenes.values())
    rows = {row["id"]: row for row in doc["records"]}
    # 源表问法“高度可伸缩是什么意思”必须与纯色高度答案完全一致。
    source_intents = {"qa.801.C16": "height_range", "qa.802.C8": "telescoping"}
    for row in doc["records"]:
        pid = row.get("answer_product_id")
        intent = source_intents.get(row["id"], row.get("intent"))
        if pid in PRODUCT_IDS and intent in SCENES and (
            row["id"].startswith("product.") or row["id"] in source_intents
        ):
            set_record(row, pid, intent)
    # 原表问答保留检索与来源追溯，但同条件下以可维护的商品标准答案为准。
    # 避免维护者只改标准答案后，与旧导入副本产生同级冲突。
    for source_id, intent in source_intents.items():
        source_row = rows.get(source_id)
        if not source_row:
            continue
        source_row["priority"] = 0
        canonical = rows[f"product.{source_row['answer_product_id']}.{intent}"]
        source_row["canonical_answer_id"] = canonical["id"]
        canonical["priority"] = max(1, canonical.get("priority", 0))
        for source in source_row.get("sources", []):
            if source not in canonical["sources"]:
                canonical["sources"].append(copy.deepcopy(source))
    for pid in PRODUCT_IDS:
        for intent in ("length_width_range", "structure"):
            key = f"product.{pid}.{intent}"
            if key in rows:
                continue
            # 继承同款已确认条目的适用条件，不变更其他商品或售后策略。
            row = copy.deepcopy(rows[f"product.{pid}.height_range"])
            row.update(id=key, origin="user_confirmation", images=[], sources=[])
            set_record(row, pid, intent)
            rows[key] = row
            doc["records"].append(row)
    return doc


def migrate_products(document: dict) -> dict:
    doc = copy.deepcopy(document)
    for product in doc["products"]:
        pid = product["id"]
        if pid not in PRODUCT_IDS:
            continue
        product.setdefault("ranges", {}).update(copy.deepcopy(RANGES[pid]))
        for intent in SCENES:
            answer = "\n\n".join(answer_parts(pid, intent))
            product.setdefault("facts", {})[intent] = answer
            product.setdefault("short_replies", {})[intent] = answer
            product.setdefault("sources", {})[intent] = with_confirmation(product["sources"].get(intent, []), pid, intent)
            product.setdefault("field_updated_at", {})[intent] = CONFIRMED_AT
    return doc


def migrate_source_qa(document: dict) -> dict:
    doc = copy.deepcopy(document)
    intent_by_id = {"qa.801.C16": "height_range", "qa.802.C8": "telescoping"}
    for row in doc["records"]:
        intent = intent_by_id.get(row["id"])
        if not intent:
            continue
        pid = row["product_id"]
        row.update(
            fields=[intent],
            answer="\n\n".join(answer_parts(pid, intent)),
            answer_parts=answer_parts(pid, intent),
            reason="采用2026-10-22商家确认的范围；高度、长宽分开，旧表原文仅保留追溯",
            confirmed_at=CONFIRMED_AT,
        )
        row["confirmations"] = with_confirmation(row.get("confirmations", []), pid, intent)
    return doc


MIGRATIONS = {
    "faq.json": migrate_faq,
    "nets_801_804.json": migrate_products,
    "source_qa.json": migrate_source_qa,
}


def main() -> None:
    data = ROOT / "data"
    changes = []
    for filename, migrate in MIGRATIONS.items():
        target = data / filename
        old = target.read_bytes()
        result = migrate(json.loads(old))
        output = (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        if old != output:
            changes.append((target, old, output))
    if not changes:
        print("Dimension knowledge already confirmed; no changes.")
        return
    backups = data / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%dT%H%M%S%f")
    for target, old, _ in changes:
        (backups / f"{target.stem}-before-confirmed-dimensions-{stamp}.json").write_bytes(old)
    for target, _, output in changes:
        target.write_bytes(output)
        print(f"Updated {target.name}")


if __name__ == "__main__":
    main()
