"""模型只能选择已启用的回复，不能生成新的商品事实。"""
import re

def candidates_for(kb,question,pid,reception='presales',stage='presales',now=None):
    product=kb.products.get(pid)
    text=question
    if product:
        for token in sorted([pid,product['name'],*product['aliases']],key=len,reverse=True):text=text.replace(token,'')
    forbidden=(product or {}).get('blocked_topics',[])+['保证','一定','忽略','系统提示','退款','订单','保修','赠品','多少钱','价格']
    if any(word in text for word in forbidden) or re.search(r'\d|[，,；;\n]|还有|并且|以及',text):return []
    if kb.faq.records:
        return [kb.faq.candidate(r) for r in kb.faq.eligible(pid,reception,stage,now)]
    result=[]
    if product:
        for field,answer in product.get('short_replies',{}).items():
            if answer and field in product['facts']:
                result.append({'id':f'product.{pid}.{field}','question_topic':field,'answer':answer,
                               'product_id':pid,'sources':product.get('sources',{}).get(field,[])})
        for row in kb.qa_records:
            if row['product_id']==pid and row['status']=='active' and row['answer']:
                result.append({'id':row['id'],'question_topic':row['question'],'answer':row['answer'],
                               'product_id':pid,'fields':row['fields'],'source':row['source']})
    for target,field in [('804','catalog_recommendation'),('803','best_recommendation')]:
        p=kb.products.get(target,{})
        if field in p.get('short_replies',{}) and target!=pid:
            result.append({'id':f'product.{target}.{field}','question_topic':'其他款型推荐',
                           'answer':p['short_replies'][field],'product_id':target})
    for field in ['delivery_summary','freight_insurance','expedite']:
        value=kb.data['store']['facts'].get(field)
        if value:result.append({'id':f'store.{field}','question_topic':field,'answer':value})
    return result
