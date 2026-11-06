"""幂等新增通用接待模板，不覆盖现有维护内容或编造售后政策。"""
import copy
import json
from app.common_intents import VARIANTS
from app.config import ROOT
from app.faq_admin import FAQStore

ANSWERS = {
    'greeting': ('问候／咨询开场', '亲亲，您好呀～请问想了解商品，还是需要处理订单问题呢？'),
    'thanks': ('感谢回应', '不客气呀亲亲💗 有问题随时来问～'),
    'goodbye': ('结束对话', '好的亲亲，祝您生活愉快💗'),
    'tracking': ('查询／催促订单物流', '亲亲，您可以先在订单详情里查看最新物流～如果进度没有更新或迟迟未收到，请通过平台订单联系人工客服核实。'),
    'returns_policy': ('咨询退换货条件与费用', '亲亲，退换条件、运费和寄回地址需要结合订单页面及商品情况核实，暂时不能直接承诺。您是想退货还是换货呢？'),
    'return_request': ('申请退货／退款', '亲亲，您是还没收到货，还是已经收到后想退货呢？具体退款或退货处理需要人工结合订单核实，请先通过平台订单联系人工客服。'),
    'exchange_request': ('申请换货', '亲亲，您想换尺寸、颜色，还是商品有问题呢？换货条件和库存需要人工结合订单核实，请先别自行寄回哦～'),
    'damaged': ('破损／漏发／错发反馈', '亲亲，给您添麻烦了。方便保留包装，并拍一下问题位置或收到的配件吗？请通过平台订单联系人工客服核实处理。'),
}


def migrate(document):
    doc = copy.deepcopy(document)
    for intent, (title, answer) in ANSWERS.items():
        sid, rid = 'industry.common_' + intent, 'store.common_' + intent
        category = '聊天互动' if intent in ('greeting', 'thanks', 'goodbye') else '物流' if intent == 'tracking' else '售后服务'
        variants = [title, *VARIANTS[intent]]
        if not any(s['id'] == sid for s in doc['scenes']):
            doc['scenes'].append({'id': sid, 'name': title, 'type': 'industry', 'category': category,
                'question_variants': variants, 'configured': True,
                'description': '通用接待模板；不代表已查询、提交或完成任何订单操作。不承诺退款、赔付或到货。'})
        if not any(r['id'] == rid for r in doc['records']):
            doc['records'].append({'id': rid, 'intent': 'common_' + intent, 'scene_id': sid,
                'scene_name': title, 'scene_type': 'industry', 'category': category,
                'question_variants': variants, 'standard_answer': answer, 'answer_parts': [answer],
                'scope': 'store', 'product_ids': [], 'answer_product_id': None, 'fields': [],
                'status': 'active', 'configured_scene': True, 'origin': 'general_reception_template',
                'images': [], 'keywords': [], 'keyword_mode': 'any', 'priority': 0,
                'conditions': {'reception': 'all', 'stages': [], 'valid_from': None, 'valid_until': None},
                'updated_at': '2026-11-04', 'sources': [{'type': 'workflow_template', 'date': '2026-11-04',
                    'excerpt': '按用户要求补充通用问候、物流和退换货接待；未确认的具体店铺规则须人工核实。'}],
                'boundaries': {'no_extra_promises': True, 'no_order_operations': True,
                    'unsupported': 'operator_only_no_customer_reply'}})
    return doc


if __name__ == '__main__':
    store = FAQStore()
    doc, _ = store.read()
    updated = migrate(doc)
    if updated != doc:
        store.persist(updated, lambda value: None)
        print('Added general reception FAQ without replacing existing answers')
    else:
        print('Already configured')
