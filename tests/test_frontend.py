import hashlib
import re
import shutil
import subprocess
import unittest
from fastapi.testclient import TestClient
from app.config import ROOT
from app.main import app


class FrontendTests(unittest.TestCase):
    def test_pages_reference_current_assets_and_disable_stale_cache(self):
        with TestClient(app) as client:
            for route in ['/','/knowledge','/materials']:
                response=client.get(route)
                self.assertEqual(response.status_code,200)
                self.assertEqual(response.headers['cache-control'],'no-store')
                assets=re.findall(r'/static/([\w.-]+\.(?:js|css))\?v=([a-f0-9]+)',response.text)
                self.assertEqual(len(assets),{'/':6,'/knowledge':5,'/materials':4}[route])
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
