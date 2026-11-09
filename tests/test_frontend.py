import copy
import hashlib
import re
import shutil
import subprocess
import unittest
from fastapi.testclient import TestClient
from app.config import ROOT
from app.main import app


class FrontendTests(unittest.TestCase):
    def test_resuming_session_retains_product_and_history_without_replaying(self):
        with TestClient(app) as client:
            sid=client.post('/api/sessions').json()['session_id']
            client.post(f'/api/sessions/{sid}/events',json={'type':'customer_select','product_id':'801'})
            client.post('/api/chat',json={'session_id':sid,'message':'你好','product_id':'801'})
            before=copy.deepcopy(app.state.service.sessions[sid].history)
            value=client.get(f'/api/sessions/{sid}').json()
            self.assertEqual(value['session_id'],sid)
            self.assertEqual(value['current_product_id'],'801')
            self.assertEqual(app.state.service.sessions[sid].history,before)
            self.assertEqual(client.get('/api/sessions/missing').status_code,404)

    def test_pages_reference_current_assets_and_disable_stale_cache(self):
        with TestClient(app) as client:
            for route in ['/','/knowledge','/materials']:
                response=client.get(route)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.headers['cache-control'],'no-store')
                assets=re.findall(r'/static/([\w.-]+\.(?:js|css))\?v=([a-f0-9]+)',response.text)
                self.assertEqual(len(assets),{'/':11,'/knowledge':10,'/materials':9}[route])
                for name,version in assets:
                    self.assertEqual(version,hashlib.sha256((ROOT/'static'/name).read_bytes()).hexdigest()[:12])
                    asset=client.get(f'/static/{name}?v={version}')
                    self.assertEqual(asset.status_code,200)
                    self.assertEqual(asset.headers['cache-control'],'no-store')
                    self.assertEqual(asset.content,(ROOT/'static'/name).read_bytes())

    @unittest.skipUnless(shutil.which('node'),'需要 Node.js 运行前端交互回归')
    def test_frontend_bootstrap_and_selection(self):
        result=subprocess.run(['node',str(ROOT/'tests/frontend.test.cjs')],cwd=ROOT,
                              capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)

    @unittest.skipUnless(shutil.which('node'),'需要 Node.js 运行资料维护回归')
    def test_materials_editor(self):
        result=subprocess.run(['node',str(ROOT/'tests/materials.test.cjs')],cwd=ROOT,
                              capture_output=True,text=True,encoding='utf-8',timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
