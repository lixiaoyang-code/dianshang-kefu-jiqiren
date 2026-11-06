"""明确尺寸问法与相邻轮纠错；只选择可维护 FAQ，不在规则里存商品参数。"""
import re

SCENES = {'height': 'industry.height_range', 'length_width': 'industry.length_width_range',
          'all': 'industry.telescoping', 'structure': 'industry.structure',
          'specifications': 'industry.specifications'}
DIMENSION_SCENES = set(SCENES.values())


def request(text, product=None, previous=None):
    plain = text.strip()
    if product:
        for token in sorted([product['id'], product['name'], *product['aliases']], key=len, reverse=True):
            plain = plain.replace(token, '')
    plain = plain.strip(' ，,。！？?!～~')
    if (len(plain) > 100 or any(word in plain for word in (
            '保证', '一定', '必须', '绝对', '忽略', '系统提示', '退款', '订单', '投诉',
            '赠品', '价格', '便宜', '赔偿', '物流', '发货', '材质', '洗', '遮光率', '承重',
            '免费', '充电', '置物', '防蚊', '透气', '安装', '保修', '机洗', '甲醛'))):
        return None
    if re.fullmatch(r'(?:有没有|有)?长宽高都(?:可以|能)?伸缩的(?:款式)?(?:有吗)?', plain):
        return None  # 跨款推荐仍走已有推荐 FAQ，不要求先确认当前商品。
    if re.fullmatch(r'(?:支架|杆子)多宽', plain):
        return None  # 杆子粗细与整个支架宽度需要先消歧。
    # 单独问号在尺寸对话后表示需要重看上轮；孤立问号仍走普通互动。
    if not plain and re.fullmatch(r'[？?\s]+', text) and previous:
        return {**previous, 'repair': True}
    if not covered(plain):return None
    structure = any(word in plain for word in ('组成', '包含什么', '包含哪些', '包括什么', '几部分',
        '几件套', '套在外', '套最外', '最外层', '外面是帐纱', '外面是蚊帐', '帐纱套', '蚊帐套', '帐纱在', '蚊帐在'))
    structure = structure or bool(re.search(r'(?:帐纱|蚊帐).{0,6}(?:外面|里面|外层|内层)', plain))
    if structure:
        return {'kind': 'structure', 'heights': [], 'repair': False}
    correction = bool(re.search(r'我(?:问|说)(?:的)?(?:是)?|不是.*是|问错了|答错了|没问|说的是|要问', plain))
    axis_text=re.sub(r'不是(?:问)?(?:高度|长宽|长度|宽度)(?:而)?(?:是)?','',plain) if correction else plain
    height = bool(re.search(r'高度|多高|高低|升降|高款|最高|最低|高(?:可以|能)|\d+\s*(?:cm|厘米)?\s*高', axis_text, re.I))
    horizontal = any(word in axis_text for word in ('长宽', '长度', '宽度', '多长', '多宽', '长能', '宽能')) or bool(re.search(r'(?:长|宽)(?:可以|可不|支持)',axis_text))
    adjust = any(word in plain for word in ('伸缩', '调节', '可调', '能调', '可以调', '固定', '升降', '最高', '最低', '最短', '最长', '最宽', '最窄', '调到'))
    if re.search(r'长宽高|长、宽、高', plain): height = horizontal = True
    if correction and previous and previous['kind'] != 'structure':
        adjust = adjust or previous['kind'] != 'specifications'
    if previous and previous['kind'] in ('height','length_width','all') and re.fullmatch(
            r'(?:那|那么)?(?:长宽|长度|宽度|高度)(?:呢|的呢|怎么样)?', plain):
        adjust = True
    if not adjust:
        # “110高呢”只在同一尺寸问答紧接着出现时继承调节这个属性。
        followup = previous and re.fullmatch(r'(?:那|那么)?\s*(?:90|110|120)\s*(?:cm|厘米)?\s*(?:高度款|高款|高|厘米)?\s*(?:呢|的呢|怎么样)?', plain, re.I)
        if followup and previous['kind'] in ('height', 'all'):
            height, adjust = True, True
        elif not (height or horizontal) or not any(word in plain for word in ('多少', '多高', '多长', '多宽', '尺寸')):
            return None
    if not adjust:
        return {'kind': 'specifications', 'heights': [], 'repair': correction}
    if height and horizontal: kind = 'all'
    elif height: kind = 'height'
    elif horizontal: kind = 'length_width'
    elif any(word in plain for word in ('伸缩', '调节范围', '调节量')): kind = 'all'
    else: return None
    # 不把单独的80宽、190长当作高度款；只有明确高度修饰才选择规格。
    heights = [int(value) for value in re.findall(r'(\d{2,3})\s*(?:cm|厘米)?\s*(?:高度款|高度|高款|高)', plain, re.I)]
    for group in re.findall(r'(\d{2,3}(?:\s*(?:/|和|、|与)\s*\d{2,3})+)\s*(?:cm|厘米)?\s*(?:高度款|高度|高款|高)',plain,re.I):
        heights=[int(n) for n in re.findall(r'\d+',group)]+heights
    if not heights and previous and re.fullmatch(r'(?:那|那么)?\s*(90|110|120)\s*(?:cm|厘米)?\s*(?:呢|的呢|怎么样)?', plain, re.I):
        heights = [int(re.search(r'\d+', plain).group())]
    return {'kind': kind, 'heights': list(dict.fromkeys(heights)), 'repair': correction}


def covered(text):
    """完整覆盖才进入快捷路由，陌生附带问题留给原有完整性检查。"""
    remainder=text.lower()
    vocabulary=('我问的是','我说的是','我问的','我说的','不是','而是','问错了','答错了','没问','说的是','要问',
        '能不能','可以不可以','可不可以','是不是','能否','是否','不可以','不支持','不可','不能','可以','支持',
        '长宽高','长宽','长度','宽度','高度款','高度','高款','高低','升降','最小','最大','最高','最低','最长','最短','最宽','最窄',
        '伸缩','调节','调整','可调','能调','固定','范围','多少','多高','多长','多宽','多大','尺寸','规格','款式','款',
        '怎么','什么','怎样','意思','请问','我想知道','想知道','告诉我','亲亲','亲','你好','支架','杆子','帐纱','蚊帐','床帘','遮光帘',
        '包含','包括','哪些','几个','几部分','几件套','一套','套装','组成','东西','最外层','外层','内层','外面','里面','外边','里边',
        '套在','套','在哪一层','哪一层','哪层','在哪里','哪里','里面还是外面','还是',
        '全部','整体','分别','之间','厘米','毫米','cm','那么','那个','这个','这款','那款','咱家','你家','你们','还有','以及','并且',
        '我','问','说','的是','是','的','能','不','有','没有','都','还','又','到','在','了','吗','嘛','呢','呀','啊','哈','么','那','怎么样','和','与','高','长','宽')
    for token in sorted(vocabulary,key=len,reverse=True):remainder=remainder.replace(token,'')
    return not re.sub(r'[\d\s，,。？！?!；;：:、/×*x\-—–+±~～（）()]+','',remainder)


def select(kb, plan, pid, reception, stage):
    scene = SCENES[plan['kind']]
    rows = [row for row in kb.faq.records if row['scene_id'] == scene]
    choice = kb.faq.select(rows, pid, reception, stage)
    if choice['status'] != 'matched':
        return {**choice, 'scene_id': scene}
    row = choice['row']
    parts = row.get('answer_parts') or [row['standard_answer']]
    # 编辑后的单段仍可按显式换行识别高度子项；找不到明确段落就留人工，不能用旧数字回填。
    if plan['kind'] == 'height' and plan['heights']:
        fragments = [line.strip() for part in parts for line in part.splitlines() if line.strip()]
        scoped = []
        for value in plan['heights']:
            matches = [line for line in fragments if re.search(rf'(?<!\d){value}\s*(?:厘米|cm)?\s*(?:高度款|高款|高)', line, re.I)]
            if not matches:
                # 单一固定高度可保留明确“固定110厘米”的整段。
                matches = [part for part in parts if re.search(rf'(?:固定|高度(?:固定)?(?:为|是)?)\s*{value}\s*(?:厘米|cm)', part, re.I)]
            if not matches:
                return {'status': 'ineligible', 'row': row, 'scene_id': scene, 'reason': 'height_variant_missing'}
            scoped.extend(matches)
        parts = list(dict.fromkeys(scoped))
    return {**choice, 'parts': parts, 'answer': '\n\n'.join(parts), 'scene_id': scene}
