"""商品级链接模拟：只记录明确关联，不抓取外站或推断 SKU。"""
from urllib.parse import urlsplit
from fastapi import HTTPException


def validate_link(value):
    if not isinstance(value,str):raise HTTPException(422,'请填写商品链接。')
    value=value.strip()
    if not value or len(value)>2000 or any(c.isspace() or ord(c)<32 for c in value) or '\\' in value:
        raise HTTPException(422,'商品链接格式不正确，请粘贴完整的 http 或 https 链接。')
    try:
        url=urlsplit(value)
        if url.scheme.lower() not in ('http','https') or not url.hostname or url.username is not None or url.password is not None:
            raise ValueError()
        url.port
    except ValueError:
        raise HTTPException(422,'请使用不带账号密码的 http 或 https 商品链接。')
    return value
