"""本地页面资源按内容生成版本号，避免旧脚本与新页面混用。"""
import hashlib
import re
from fastapi.responses import HTMLResponse
from .config import ROOT
from .ui_shell import shell


def frontend_page(filename,view=None):
    folder=ROOT/'static'
    html=(folder/filename).read_text(encoding='utf-8')
    if view=='review':
        html=html.replace('<body>','<body data-knowledge-view="review">',1).replace('问答知识库 · 客服工作台','待审核 · 客服工作台',1)
    html=shell(html,'review.html' if view=='review' else filename)
    if view=='embedded':html=html.replace('<body','<body data-knowledge-embed="true"',1)
    def version(match):
        asset=match.group(1)
        digest=hashlib.sha256((folder/asset).read_bytes()).hexdigest()[:12]
        return f'="/static/{asset}?v={digest}"'
    html=re.sub(r'="/static/([\w.-]+\.(?:css|js))"',version,html)
    return HTMLResponse(html,headers={'Cache-Control':'no-store'})
