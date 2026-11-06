"""所有工作台页面共用的导航，不依赖各页布局或字体规则。"""
import re

PATHS = {
    'chat': 'M4 5h16v11H9l-5 4V5Z M8 9h8 M8 12h5',
    'knowledge': 'M4 4h16v16H4Z M4 9h16 M8 9v11',
    'consultations': 'M7 3h10v3h3v15H4V6h3 M8 11h8 M8 15h6',
    'materials': 'M3 6h7l2 2h9v12H3Z',
    'statistics': 'M4 20V11h4v9 M10 20V4h4v16 M16 20V8h4v12',
}


def icon(name):
    return f'<svg class="pac-nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="{PATHS[name]}"/></svg>'


def shell(html, filename):
    chat = filename == 'index.html'
    public = filename.endswith('-demo.html')
    entries = [('chat', '/', '咨询测试', ''),
               ('knowledge', '/knowledge', '知识库', 'knowledge-nav'),
               ('knowledge', '/experience/knowledge', '知识库体验', 'experience-nav'),
               ('consultations', '/consultations', '咨询记录', 'consultations-nav' if chat else 'consultations-link'),
               ('materials', '/materials', '资料库', 'materials-nav'),
               ('statistics', '/experience/statistics' if public or chat else '/statistics', '数据看板', 'statistics-nav' if chat else 'statistics-link')]
    selected = {'index.html': '/', 'knowledge.html': '/knowledge', 'materials.html': '/materials',
                'statistics.html': '/statistics', 'knowledge-demo.html': '/experience/knowledge',
                'statistics-demo.html': '/experience/statistics'}.get(filename)
    links = []
    for name, href, label, identity in entries:
        hidden = (href in ('/knowledge', '/consultations', '/materials') if chat else
                  (href in ('/knowledge', '/consultations', '/materials') if public else href == '/experience/knowledge'))
        links.append(f'<a href="{href}"' + (f' id="{identity}"' if identity else '') +
                     (' hidden' if hidden else '') + (' aria-current="page"' if href == selected else '') +
                     f'>{icon(name)}<span>{label}</span></a>')
    header = '<header class="pac-shell"><a class="pac-brand" href="/" aria-label="PAC 客服工作台"><img src="/static/pac-logo.svg" alt="PAC" width="52" height="52"><span>客服工作台</span></a><nav aria-label="工作台导航">' + ''.join(links) + '</nav>'
    header += '<div class="pac-account account-entry"><span id="access-label" class="access-label">' + ('访客体验' if public or chat else '管理员模式') + '</span>'
    header += '<a id="admin-entry" href="' + ('/admin' if public or chat else '/knowledge') + '">' + ('管理员登录 ↗' if public or chat else '管理后台 ↗') + '</a><span id="mode" role="status">' + ('连接中' if chat else 'PAC · 客服工作台') + '</span></div></header>'
    html = re.sub(r'<header>.*?</header>', lambda _: header, html, count=1, flags=re.S)
    html = html.replace('</head>', '<link rel="stylesheet" href="/static/shell.css"><link rel="icon" type="image/svg+xml" href="/static/pac-logo.svg"></head>')
    html = re.sub(r'<body([^>]*)>', lambda m: '<body' + m[1] + ' data-pac-shell="' + ('chat' if chat else 'page') + '">', html, count=1)
    return html
