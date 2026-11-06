"""Public demo boundary: no network calls and no changes to the real knowledge."""
import asyncio
import os
import time
import unittest
import uuid
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

import httpx
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from app.deployment import (COOKIE, DeploymentSettings, DemoAccessMiddleware, DemoRuntime,
                            deployment_status, register_session)


SETTINGS = DeploymentSettings(mode='demo', admin_username='owner', admin_password='test-password-123456789',
                              session_secret='test-secret-at-least-thirty-two-characters', allowed_hosts=('demo.test',))
AUTH = ('owner', 'test-password-123456789')


def demo_app(settings=SETTINGS):
    app = FastAPI()
    app.state.deployment = settings
    app.state.demo_runtime = DemoRuntime(settings) if settings.mode == 'demo' else None
    app.state.service = SimpleNamespace(sessions={}, locks={})
    app.state.called = 0
    app.add_middleware(DemoAccessMiddleware)

    @app.get('/api/health')
    def health(request: Request):
        return {'status': 'ok', 'deployment': deployment_status(request)}

    @app.post('/api/sessions')
    def create(request: Request):
        sid = str(uuid.uuid4())
        app.state.service.sessions[sid] = object()
        app.state.service.locks[sid] = object()
        register_session(request, sid)
        return {'session_id': sid}

    async def accept(request: Request):
        app.state.called += 1
        return {'ok': True, 'received': await request.json()}

    for path in ['/api/chat', '/api/rag/assist', '/api/sessions/{sid}/events',
                 '/api/sessions/{sid}/reset', '/api/sessions/{sid}/waiting/{rid}']:
        app.add_api_route(path, accept, methods=['POST'])
    for path in ['/knowledge', '/materials', '/statistics', '/api/statistics', '/api/statistics/review', '/api/faq', '/api/scenes', '/api/materials',
                 '/static/knowledge.html', '/api/future-admin-route']:
        app.add_api_route(path, lambda: {'admin': True}, methods=['GET', 'POST'])
    return app


class DemoSecurityTests(unittest.TestCase):
    def setUp(self):
        self.app = demo_app()
        self.client = TestClient(self.app, base_url='https://demo.test')

    def session(self, client=None):
        response = (client or self.client).post('/api/sessions')
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()['session_id']

    def limits(self, **kwargs):
        self.app.state.deployment = replace(SETTINGS, **kwargs)
        self.app.state.demo_runtime.settings = self.app.state.deployment

    def test_local_mode_preserves_current_access(self):
        with TestClient(demo_app(DeploymentSettings())) as client:
            self.assertEqual(client.get('/api/faq').status_code, 200)
            self.assertEqual(client.get('/docs').status_code, 200)
            self.assertEqual(client.get('/api/health').json()['deployment'],
                             {'mode': 'local', 'public_demo': False, 'can_manage': True})

    def test_demo_configuration_fails_closed(self):
        with patch.dict(os.environ, {'APP_MODE': 'demo', 'ADMIN_USERNAME': '', 'ADMIN_PASSWORD': '', 'SESSION_SECRET': ''}):
            with self.assertRaises(RuntimeError):
                DeploymentSettings.from_env()
        for changed in [{'allowed_hosts': ()}, {'allowed_hosts': ('*',)}, {'daily_requests': 0},
                        {'admin_password': 'replace-with-a-strong-password'}]:
            with self.subTest(changed=changed), self.assertRaises(RuntimeError):
                replace(SETTINGS, **changed).validate()

    def test_management_get_and_post_require_admin_including_new_routes(self):
        for path in ['/knowledge', '/materials', '/statistics', '/api/statistics', '/api/statistics/review', '/api/faq', '/api/scenes', '/api/materials',
                     '/static/knowledge.html', '/api/future-admin-route']:
            for method in ('get', 'post'):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path)
                    self.assertEqual(response.status_code, 401)
                    self.assertIn('Basic', response.headers['www-authenticate'])

    def test_admin_credentials_and_health_role(self):
        self.assertFalse(self.client.get('/api/health').json()['deployment']['can_manage'])
        self.assertEqual(self.client.get('/api/faq', auth=('owner', 'incorrect')).status_code, 401)
        self.assertEqual(self.client.get('/api/faq', auth=AUTH).status_code, 200)
        self.assertTrue(self.client.get('/api/health', auth=AUTH).json()['deployment']['can_manage'])

    def test_cookie_is_secure_http_only_and_not_in_response_body(self):
        response = self.client.post('/api/sessions')
        header = response.headers['set-cookie']
        self.assertIn('Secure', header)
        self.assertIn('HttpOnly', header)
        self.assertIn('SameSite=Lax', header)
        self.assertNotIn(SETTINGS.session_secret, header + response.text)
        self.assertNotIn('demo_owner', response.text)

    def test_cross_device_session_access_is_denied(self):
        sid = self.session()
        other = TestClient(self.app, base_url='https://demo.test')
        for path in ['/api/chat', '/api/rag/assist', f'/api/sessions/{sid}/events',
                     f'/api/sessions/{sid}/reset', f'/api/sessions/{sid}/waiting/old']:
            with self.subTest(path=path):
                response = other.post(path, json={'session_id': sid, 'message': '好的'})
                self.assertEqual(response.status_code, 404)
        self.assertEqual(self.app.state.called, 0)
        response = self.client.post('/api/chat', json={'session_id': sid, 'message': '好的'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['received']['message'], '好的')

    def test_tampered_cookie_cannot_claim_session(self):
        sid = self.session()
        cookie = self.client.cookies.get(COOKIE)
        self.client.cookies.clear()
        self.client.cookies.set(COOKIE, cookie[:-1] + ('0' if cookie[-1] != '0' else '1'))
        self.assertEqual(self.client.post('/api/chat', json={'session_id': sid}).status_code, 404)

    def test_cross_origin_posts_are_denied_even_with_admin(self):
        for headers in [{'Origin': 'https://evil.test'}, {'Sec-Fetch-Site': 'cross-site'}]:
            response = self.client.post('/api/faq', json={}, auth=AUTH, headers=headers)
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post('/api/faq', json={}, auth=AUTH,
                                         headers={'Origin': 'https://demo.test'}).status_code, 200)

    def test_docs_are_closed_even_for_admin_and_hosts_are_validated(self):
        for path in ['/docs', '/docs/', '/openapi.json', '/redoc']:
            self.assertEqual(self.client.get(path, auth=AUTH).status_code, 404)
        self.assertEqual(self.client.get('/api/health', headers={'Host': 'attacker.test'}).status_code, 400)

    def test_body_limit_and_required_session_validation(self):
        sid = self.session()
        self.assertEqual(self.client.post('/api/chat', content='x' * 20000).status_code, 413)
        for payload in [[], {}, {'session_id': []}, {'session_id': ''}]:
            self.assertEqual(self.client.post('/api/chat', json=payload).status_code, 422)
        self.assertEqual(self.client.post('/api/chat', content='{broken').status_code, 422)
        self.assertEqual(self.client.post('/api/chat', json={'session_id': sid}).status_code, 200)

    def test_chat_and_rag_share_daily_budget(self):
        self.limits(daily_requests=1)
        sid = self.session()
        self.assertEqual(self.client.post('/api/chat', json={'session_id': sid}).status_code, 200)
        response = self.client.post('/api/rag/assist', json={'session_id': sid})
        self.assertEqual(response.status_code, 429)
        self.assertIn('今日', response.json()['detail'])

    def test_ip_rate_limit_cannot_be_evaded_by_new_cookie(self):
        self.limits(requests_per_minute=2)
        sid = self.session()
        self.assertEqual(self.client.post('/api/chat', json={'session_id': sid}).status_code, 200)
        self.client.cookies.clear()
        self.assertEqual(self.client.post('/api/sessions').status_code, 429)

    def test_expired_sessions_are_removed_without_removing_active_work(self):
        runtime = self.app.state.demo_runtime
        sid = self.session()
        runtime.sessions[sid]['touched'] = time.monotonic() - SETTINGS.session_ttl_seconds - 1
        runtime.active_sessions[sid] = 1
        self.client.get('/api/health')
        self.assertIn(sid, runtime.sessions)
        runtime.active_sessions.pop(sid)
        self.client.get('/api/health')
        self.assertNotIn(sid, runtime.sessions)
        self.assertNotIn(sid, self.app.state.service.sessions)
        self.assertEqual(self.client.post('/api/chat', json={'session_id': sid}).status_code, 404)

    def test_total_and_visitor_session_limits(self):
        self.limits(sessions_per_visitor=1)
        self.session()
        self.assertEqual(self.client.post('/api/sessions').status_code, 429)
        self.assertEqual(self.app.state.demo_runtime.pending_creates, {})
        self.limits(max_sessions=1)
        other = TestClient(self.app, base_url='https://demo.test')
        self.assertEqual(other.post('/api/sessions').status_code, 429)


class DemoConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_shared_concurrency_limit_releases_on_completion(self):
        app = demo_app(replace(SETTINGS, concurrent_requests=1))
        started, finish = asyncio.Event(), asyncio.Event()

        @app.post('/api/rag/assist')
        async def delayed(request: Request):
            started.set()
            await finish.wait()
            return {'ok': True}

        # The existing route uses the same path; replace its endpoint in place.
        app.router.routes[:] = [route for route in app.routes if route.path != '/api/rag/assist' or route.endpoint == delayed]
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url='https://demo.test') as client:
            sid = (await client.post('/api/sessions')).json()['session_id']
            first = asyncio.create_task(client.post('/api/rag/assist', json={'session_id': sid}))
            await asyncio.wait_for(started.wait(), 2)
            blocked = await client.post('/api/chat', json={'session_id': sid})
            self.assertEqual(blocked.status_code, 429)
            finish.set()
            self.assertEqual((await first).status_code, 200)
            self.assertEqual(app.state.demo_runtime.active, 0)
            self.assertEqual(app.state.demo_runtime.active_sessions, {})
            self.assertEqual((await client.post('/api/chat', json={'session_id': sid})).status_code, 200)
