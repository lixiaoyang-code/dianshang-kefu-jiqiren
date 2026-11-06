"""验证刚构建的镜像；临时容器仅监听本机，不使用真实模型密钥。"""
import json
import secrets
import subprocess
import time
import uuid

import httpx


def docker(*args):
    result = subprocess.run(['docker', *args], capture_output=True, text=True, encoding='utf-8', timeout=90)
    if result.returncode:
        raise RuntimeError('Docker 验证命令失败：' + result.stderr[-1000:])
    return result.stdout.strip()


def main():
    suffix = uuid.uuid4().hex[:12]
    name = 'presales-demo-check-' + suffix
    data, logs = name + '-data', name + '-logs'
    password, signature = secrets.token_hex(24), secrets.token_hex(32)
    made = False
    try:
        docker('run', '-d', '--rm', '--name', name, '-p', '127.0.0.1::8000', '--read-only',
               '--tmpfs', '/tmp:rw,size=64m', '--cap-drop=ALL', '--security-opt=no-new-privileges:true',
               '-v', data + ':/app/data', '-v', logs + ':/app/logs',
               '-e', 'APP_MODE=demo', '-e', 'MODEL_MODE=mock', '-e', 'ALLOWED_HOSTS=127.0.0.1',
               '-e', 'COOKIE_SECURE=false', '-e', 'ADMIN_USERNAME=smoke-owner',
               '-e', 'ADMIN_PASSWORD=' + password, '-e', 'SESSION_SECRET=' + signature,
               'presales-ai:demo-check')
        made = True
        port = docker('port', name, '8000/tcp').split(':')[-1]
        base = 'http://127.0.0.1:' + port
        with httpx.Client(base_url=base, timeout=30, trust_env=False) as client:
            deadline = time.monotonic() + 60
            while True:
                try:
                    health = client.get('/api/health')
                    if health.status_code == 200:
                        break
                except httpx.HTTPError:
                    pass
                if time.monotonic() >= deadline:
                    raise RuntimeError('镜像服务未在60秒内就绪。')
                time.sleep(.5)
            state = health.json()
            assert state['deployment'] == {'mode': 'demo', 'public_demo': True, 'can_manage': False}
            assert state['semantic'] == 'ready', state
            assert client.get('/knowledge').status_code == 401
            assert client.get('/api/materials').status_code == 401
            assert client.get('/docs').status_code == 404
            sid = client.post('/api/sessions', json={}).json()['session_id']
            answer = client.post('/api/chat', json={'session_id': sid, 'message': '好的'}).json()
            assert answer['answer'] == '💗', answer
            sources = client.post('/api/rag/assist', json={'session_id': sid, 'product_id': '802',
                'message': '全伸缩款和免安装款的长宽调节范围分别是多少？'}).json()
            assert sources['for_operator_only'] and not sources['send_to_customer']
            assert len(sources['sources']) == 2 and sources['generation_status'] == 'disabled', sources
            managed = client.get('/api/materials', auth=('smoke-owner', password))
            assert managed.status_code == 200 and len(managed.json()['documents']) == 9
            with httpx.Client(base_url=base, timeout=10, trust_env=False) as stranger:
                assert stranger.post(f'/api/sessions/{sid}/reset', json={'mode': 'memory'}).status_code == 404
        docker('exec', name, 'python', '-c',
               "import os,pathlib; assert os.getuid()!=0; assert not pathlib.Path('/app/.env').exists()")
        print(json.dumps({'status': 'passed', 'checks': [
            'Linux镜像启动', '只读根目录与非root用户', '模型就绪', 'FAQ回复', 'RAG真实检索与Mock标识',
            '管理员保护', '跨访客会话隔离', '知识数据与日志卷', '镜像不含本地.env']}, ensure_ascii=False))
    finally:
        if made:
            docker('stop', name)
        # 名称仅由本次随机ID产生，不触及既有服务或持久化知识。
        for volume in (data, logs):
            subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
