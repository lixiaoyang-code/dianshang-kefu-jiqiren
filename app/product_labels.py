"""Public product labels are independent of persistent knowledge bindings."""
NAMES = {
    '801': '纯色款', '802': '伸缩款', '803': '联名款', '804': '免安装款',
    'tietie': '记忆棉枕', 'cloudquilt': '云感被', 'plushblanket': '电热毯',
    'heater': '立式取暖器', 'nonwovenblanket': '电热毯-2',
    'latexpillow': '乳胶枕', '601': '防摔蚊帐',
}
HIDDEN_PRODUCTS = frozenset({'nonwovenblanket'})

def visible_products(kb):
    return [p for pid,p in kb.products.items() if pid not in HIDDEN_PRODUCTS]
REPLACEMENTS = {
    '全伸缩款': '伸缩款', '小狗联名款': '联名款', '小狗款': '联名款',
    '贴贴枕': '记忆棉枕', '云朵被': '云感被', '长毛绒电热毯': '电热毯',
    '电热毯-1':'电热毯', 'plushblanket':'电热毯',
    '无纺布电热毯': '电热毯-2', '云感乳胶枕': '乳胶枕', '601防摔蚊帐': '防摔蚊帐',
}


def public_text(text):
    for old, new in REPLACEMENTS.items():
        text = text.replace(old, new)
    return text


def public_reply(result):
    # Keep evidence, history, IDs and stored answers intact; only project outgoing wording.
    return {**result, 'answer': public_text(result.get('answer', '')),
            'answer_parts': [public_text(p) for p in result.get('answer_parts', [])]}
