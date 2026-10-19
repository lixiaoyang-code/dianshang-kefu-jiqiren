import re

WAITING_REPLY = '亲亲，让您久等啦，小妹这边正在看您的问题，稍等一下哈～'
FLEX_RECOMMENDATION = '有的亲，这边推荐全伸缩款，长宽高都能调节哈～'

def fit_question(text, product):
    """仅识别单一尺寸适配问句，不吞掉同句中的其他要求。"""
    clean = text
    for name in [product['name'], product['id'], product['model'], *product['aliases']]:
        clean = clean.replace(name, '')
    match = re.fullmatch(r'\s*(?:亲[亲]?\s*)?(\d{2,3})\s*[*×xX]\s*(\d{2,3})(?:\s*[*×xX]\s*(\d{2,3}))?\s*(?:cm|厘米)?\s*(?:的床|的床垫|的尺寸)?\s*(?:可以用吗|可以使用吗|能用吗|能装吗|可以吗|能使用吗)[？?。！!\s]*', clean)
    if not match:
        return None
    a,b,height = match.groups()
    if sorted([int(a),int(b)]) != [90,190]:
        return {'status':'answered', 'text':FLEX_RECOMMENDATION}
    if height and int(height) not in product['net_heights']:
        return {'status':'answered', 'text':FLEX_RECOMMENDATION}
    return {'status':'answered', 'text':'可以的亲，90×190和这款帐纱长宽对应。' + ('您需要多高的款呢？' if not height and len(product['net_heights']) > 1 else '')}

def compact_reply(question, hits, product):
    parts=[]
    for hit in hits:
        field=hit['field']
        if field=='coating' and any(h['field']=='roof' for h in hits):
            continue
        if field=='telescoping' and product and product.get('ranges'):
            ranges=product['ranges']
            height=re.search(r'(90|110|120)\s*(?:cm|厘米)?\s*(?:高|高度)', question)
            if height:
                low,high=ranges['height'][height.group(1)]
                parts.append(f'{height.group(1)}高款，高度可调{low}–{high}厘米')
            else:
                parts.append(product.get('short_replies',{}).get(field,hit['text']))
        elif product and field in product.get('short_replies',{}):
            parts.append(product['short_replies'][field])
        else:
            parts.append(hit['text'].rstrip('。'))
    return '亲，'+'；'.join(parts)+'。'
