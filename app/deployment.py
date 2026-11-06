"""Small single-process demo boundary. Local development remains unrestricted.

This is a browser demo, not a token-authenticated third-party API. TLS is
terminated by the included Caddy service; all visitor sessions are owned by a
signed, HttpOnly cookie. Quotas count accepted chat/RAG requests, not tokens.
"""
import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookies import SimpleCookie, CookieError

from fastapi import Request
from starlette.responses import JSONResponse


COOKIE = 'presales_demo'
PUBLIC_API = {'/api/health', '/api/products', '/api/sessions', '/api/chat', '/api/rag/assist', '/api/experience/statistics'}
SESSION_PATH = re.compile(r'^/api/sessions/([^/]+)(?:/.*)?$')


@dataclass(frozen=True)
class DeploymentSettings:
    mode: str = 'local'
    admin_username: str = ''
    admin_password: str = ''
    session_secret: str = ''
    cookie_secure: bool = True
    requests_per_minute: int = 60
    chat_per_minute: int = 20
    daily_requests: int = 500
    concurrent_requests: int = 3
    max_sessions: int = 200
    sessions_per_visitor: int = 10
    session_ttl_seconds: int = 3600
    allowed_hosts: tuple = ()

    @classmethod
    def from_env(cls):
        value = cls(
            mode=os.getenv('APP_MODE', 'local').strip().lower(),
            admin_username=os.getenv('ADMIN_USERNAME', ''),
            admin_password=os.getenv('ADMIN_PASSWORD', ''),
            session_secret=os.getenv('SESSION_SECRET', ''),
            cookie_secure=os.getenv('COOKIE_SECURE', 'true').lower() == 'true',
            requests_per_minute=int(os.getenv('DEMO_REQUESTS_PER_MINUTE', '60')),
            chat_per_minute=int(os.getenv('DEMO_CHAT_PER_MINUTE', '20')),
            daily_requests=int(os.getenv('DEMO_DAILY_REQUESTS', '500')),
            concurrent_requests=int(os.getenv('DEMO_CONCURRENT_REQUESTS', '3')),
            max_sessions=int(os.getenv('DEMO_MAX_SESSIONS', '200')),
            sessions_per_visitor=int(os.getenv('DEMO_SESSIONS_PER_VISITOR', '10')),
            session_ttl_seconds=int(os.getenv('DEMO_SESSION_TTL_SECONDS', '3600')),
            allowed_hosts=tuple(h.strip().lower() for h in os.getenv('ALLOWED_HOSTS', '').split(',') if h.strip()))
        value.validate()
        return value

    def validate(self):
        if self.mode not in ('local', 'demo'):
            raise RuntimeError('APP_MODE 必须为 local 或 demo。')
        if self.mode == 'demo':
            if not self.admin_username or len(self.admin_password) < 16 or len(self.session_secret) < 32:
                raise RuntimeError('公网模式需要管理员账号、至少16字符的密码及至少32字符的 SESSION_SECRET。')
            if any('replace' in v.lower() or 'change-me' in v.lower() for v in (self.admin_password, self.session_secret)):
                raise RuntimeError('请先替换公网配置中的示例密码和 SESSION_SECRET。')
            if not self.allowed_hosts or '*' in self.allowed_hosts:
                raise RuntimeError('公网模式必须设置明确的 ALLOWED_HOSTS 域名。')
            if not all(v > 0 for v in (self.requests_per_minute, self.chat_per_minute, self.daily_requests,
                                      self.concurrent_requests, self.max_sessions, self.sessions_per_visitor,
                                      self.session_ttl_seconds)):
                raise RuntimeError('公网模式的限额必须为正整数。')


class DemoRuntime:
    def __init__(self, settings):
        self.settings = settings
        self.lock = threading.RLock()
        self.sessions = {}  # sid -> {owner, touched}; not persisted intentionally.
        self.active_sessions = {}
        self.pending_creates = {}
        self.buckets = {}
        self.active = 0
        self.daily_day = ''
        self.daily_count = 0

    def own(self, sid, owner):
        with self.lock:
            self.sessions[sid] = {'owner': owner, 'touched': time.monotonic()}

    def prune(self, service):
        now = time.monotonic()
        with self.lock:
            expired = [sid for sid, value in self.sessions.items()
                       if now - value['touched'] > self.settings.session_ttl_seconds
                       and not self.active_sessions.get(sid)]
            for sid in expired:
                self.sessions.pop(sid, None)
                service.sessions.pop(sid, None)
                service.locks.pop(sid, None)
            self.buckets = {key: value for key, value in self.buckets.items() if now - value[0] < 60}

    def rate(self, key, maximum):
        now = time.monotonic()
        with self.lock:
            started, count = self.buckets.get(key, (now, 0))
            if now - started >= 60:
                started, count = now, 0
            # A bounded table prevents random cookies from growing memory forever.
            if key not in self.buckets and len(self.buckets) >= 10000:
                return False
            self.buckets[key] = (started, count + 1)
            return count < maximum

    def reserve(self):
        with self.lock:
            day = datetime.now(timezone.utc).date().isoformat()
            if day != self.daily_day:
                self.daily_day, self.daily_count = day, 0
            if self.daily_count >= self.settings.daily_requests:
                return '体验版今日请求额度已用完，请稍后再试。'
            if self.active >= self.settings.concurrent_requests:
                return '目前体验人数较多，请稍后再试。'
            self.daily_count += 1
            self.active += 1
            return None


def is_demo_admin(request: Request):
    settings = getattr(request.app.state, 'deployment', DeploymentSettings())
    return settings.mode != 'demo' or bool(getattr(request.state, 'demo_admin', False))


def public_request(request: Request):
    return not is_demo_admin(request)


def deployment_status(request: Request):
    settings = getattr(request.app.state, 'deployment', DeploymentSettings())
    return {'mode': settings.mode, 'public_demo': settings.mode == 'demo', 'can_manage': is_demo_admin(request)}


def register_session(request: Request, sid):
    runtime = getattr(request.app.state, 'demo_runtime', None)
    if runtime is not None:
        runtime.own(sid, request.state.demo_owner)


def admin_credentials(header, settings):
    if not header.lower().startswith('basic '):
        return False
    try:
        username, password = base64.b64decode(header.split(' ', 1)[1], validate=True).decode('utf-8').split(':', 1)
        # Both comparisons run even when the username is incorrect.
        name_ok = hmac.compare_digest(username.encode(), settings.admin_username.encode())
        password_ok = hmac.compare_digest(password.encode(), settings.admin_password.encode())
        return name_ok and password_ok
    except (ValueError, UnicodeError):
        return False


def visitor_cookie(header, settings):
    now = int(time.time())
    value = ''
    try:
        cookies = SimpleCookie()
        cookies.load(header)
        value = cookies[COOKIE].value if COOKIE in cookies else ''
        owner, expires, signature = value.split('.')
        raw = f'{owner}.{expires}'
        valid = (len(owner) == 48 and re.fullmatch('[a-f0-9]{48}', owner)
                 and now < int(expires) <= now + 86400
                 and hmac.compare_digest(signature, hmac.new(settings.session_secret.encode(), raw.encode(), hashlib.sha256).hexdigest()))
        if valid:
            return owner, value, False
    except (ValueError, KeyError, CookieError):
        pass
    owner = secrets.token_hex(24)
    raw = f'{owner}.{now + 86400}'
    return owner, raw + '.' + hmac.new(settings.session_secret.encode(), raw.encode(), hashlib.sha256).hexdigest(), True


class DemoAccessMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        application = scope['app']
        settings = getattr(application.state, 'deployment', DeploymentSettings())
        if settings.mode != 'demo':
            return await self.app(scope, receive, send)
        runtime = application.state.demo_runtime
        request = Request(scope)
        path = scope['path'].rstrip('/') or '/'
        method = scope['method']
        host = request.url.hostname or ''
        if host.lower() not in settings.allowed_hosts:
            return await JSONResponse({'detail': '访问域名不在允许列表。'}, status_code=400)(scope, receive, send)
        owner, cookie, new_cookie = visitor_cookie(request.headers.get('cookie', ''), settings)
        admin = admin_credentials(request.headers.get('authorization', ''), settings)
        scope.setdefault('state', {}).update(demo_owner=owner, demo_admin=admin)
        client = (scope.get('client') or ('unknown', 0))[0]
        ip = hashlib.sha256(str(client).encode()).hexdigest()[:24]
        runtime.prune(application.state.service)

        async def wrapped_send(message):
            if message['type'] == 'http.response.start':
                headers = list(message.get('headers', []))
                headers += [(b'cache-control', b'no-store'), (b'x-content-type-options', b'nosniff'),
                            (b'x-frame-options', b'DENY'), (b'referrer-policy', b'same-origin'),
                            (b'x-robots-tag', b'noindex, nofollow'),
                            (b'content-security-policy', b"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'")]
                if new_cookie:
                    cookie_header = f'{COOKIE}={cookie}; Path=/; Max-Age=86400; HttpOnly; SameSite=Lax'
                    if settings.cookie_secure:
                        cookie_header += '; Secure'
                    headers.append((b'set-cookie', cookie_header.encode('ascii')))
                message = {**message, 'headers': headers}
            await send(message)

        async def reject(status, detail, headers=None):
            return await JSONResponse({'detail': detail}, status_code=status, headers=headers)(scope, receive, wrapped_send)

        if path in ('/docs', '/redoc', '/openapi.json') or path.startswith('/docs/'):
            return await reject(404, '体验版不开放接口文档。')
        needs_admin = (path in ('/knowledge', '/materials', '/statistics', '/consultations', '/admin') or
                       path.startswith('/static/') and path.endswith('.html') or
                       path.startswith('/api/') and path not in PUBLIC_API and not SESSION_PATH.fullmatch(path))
        if needs_admin and not admin:
            if not runtime.rate(('login', ip), 30):
                return await reject(429, '登录尝试过多，请稍后再试。', {'Retry-After': '60'})
            return await reject(401, '请使用管理员账号登录。', {'WWW-Authenticate': 'Basic realm="Presales Admin", charset="UTF-8"'})
        if method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            expected = f'{request.url.scheme}://{request.url.netloc}'
            if origin and origin.rstrip('/') != expected:
                return await reject(403, '请在本站页面操作。')
            if request.headers.get('sec-fetch-site') == 'cross-site':
                return await reject(403, '不允许跨站请求。')
        if path.startswith('/api/') and path != '/api/health':
            if not runtime.rate(('api', ip), settings.requests_per_minute):
                return await reject(429, '操作过于频繁，请稍后再试。', {'Retry-After': '60'})

        # Bound and replay JSON bodies before routing; do not consume the stream
        # through BaseHTTPMiddleware, which can otherwise starve the endpoint.
        body = b''
        if method not in ('GET', 'HEAD', 'OPTIONS'):
            maximum = 1_048_576 if admin else 16_384
            more = True
            while more:
                message = await receive()
                if message['type'] == 'http.disconnect':
                    return
                body += message.get('body', b'')
                if len(body) > maximum:
                    return await reject(413, '请求内容过长。')
                more = message.get('more_body', False)
        consumed = False

        async def replay():
            nonlocal consumed
            if not consumed:
                consumed = True
                return {'type': 'http.request', 'body': body, 'more_body': False}
            return await receive()

        sid = None
        match = SESSION_PATH.fullmatch(path)
        if match:
            sid = match.group(1)
        elif path in ('/api/chat', '/api/rag/assist') and method == 'POST':
            try:
                parsed = json.loads(body)
                sid = parsed.get('session_id') if isinstance(parsed, dict) else None
            except (ValueError, UnicodeError):
                return await reject(422, '请求格式不正确。')
            if not isinstance(sid, str) or not sid:
                return await reject(422, '请提供有效的会话。')
        if sid:
            with runtime.lock:
                owned = runtime.sessions.get(sid)
                allowed = bool(owned and (owned['owner'] == owner or admin))
                if allowed:
                    owned['touched'] = time.monotonic()
                    runtime.active_sessions[sid] = runtime.active_sessions.get(sid, 0) + 1
            if not allowed:
                return await reject(404, '会话不存在或已过期，请新建会话。')

        reserved = False
        create_reserved = False
        try:
            if path == '/api/sessions' and method == 'POST':
                with runtime.lock:
                    count = sum(1 for value in runtime.sessions.values() if value['owner'] == owner) + runtime.pending_creates.get(owner, 0)
                    full = (len(runtime.sessions) + sum(runtime.pending_creates.values()) >= settings.max_sessions
                            or count >= settings.sessions_per_visitor)
                    if not full:
                        runtime.pending_creates[owner] = runtime.pending_creates.get(owner, 0) + 1
                        create_reserved = True
                if full:
                    return await reject(429, '体验会话已达上限，请使用现有会话，或稍后重试。')
                if not runtime.rate(('create', ip), 10):
                    return await reject(429, '新建会话过于频繁，请稍后再试。', {'Retry-After': '60'})
            if path in ('/api/chat', '/api/rag/assist') and method == 'POST':
                if not runtime.rate(('chat', ip), settings.chat_per_minute):
                    return await reject(429, '提问过于频繁，请稍后再试。', {'Retry-After': '60'})
                problem = runtime.reserve()
                if problem:
                    return await reject(429, problem, {'Retry-After': '60'})
                reserved = True
            return await self.app(scope, replay, wrapped_send)
        finally:
            with runtime.lock:
                if reserved:
                    runtime.active -= 1
                if create_reserved:
                    remaining = runtime.pending_creates.get(owner, 1) - 1
                    if remaining:
                        runtime.pending_creates[owner] = remaining
                    else:
                        runtime.pending_creates.pop(owner, None)
                if sid:
                    remaining = runtime.active_sessions.get(sid, 1) - 1
                    if remaining:
                        runtime.active_sessions[sid] = remaining
                    else:
                        runtime.active_sessions.pop(sid, None)
