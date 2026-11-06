"""本地页面资源按内容生成版本号，避免旧脚本与新页面混用。"""
import hashlib
import re
from fastapi.responses import HTMLResponse
from .config import ROOT
from .ui_shell import shell


def frontend_page(filename):
    folder=ROOT/'static'
    html=shell((folder/filename).read_text(encoding='utf-8'), filename)
    def version(match):
        asset=match.group(1)
        digest=hashlib.sha256((folder/asset).read_bytes()).hexdigest()[:12]
        return f'="/static/{asset}?v={digest}"'
    html=re.sub(r'="/static/([\w.-]+\.(?:css|js))"',version,html)
    return HTMLResponse(html,headers={'Cache-Control':'no-store'})
