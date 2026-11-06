"""Windows 桌面启动器：使用现有环境启动服务，再打开浏览器。无额外依赖。"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
LOGS = ROOT / 'logs'
HIDDEN = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def healthy(port):
    try:
        # localhost 不经过系统代理；启动过程不需要联网。
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f'http://127.0.0.1:{port}/api/health', timeout=2) as response:
            value = json.load(response)
        return value.get('status') == 'ok' and all(k in value for k in ('version', 'mode', 'semantic'))
    except (OSError, ValueError):
        return False


def port_in_use(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.6):
            return True
    except OSError:
        return False


def find_python():
    candidates = [Path(sys.executable).with_name('python.exe'),
                  ROOT / '.venv/Scripts/python.exe',
                  Path(sys.base_prefix) / 'python.exe']
    available = shutil.which('python')
    if available:
        candidates.append(Path(available))
    imports = 'import fastapi, uvicorn'
    if (ROOT / 'models/minilm/model.onnx').exists():
        imports += ', onnxruntime, tokenizers, numpy'
    for candidate in dict.fromkeys(candidates):
        if not candidate.is_file():
            continue
        try:
            probe = subprocess.run([str(candidate), '-c', imports], cwd=ROOT,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   creationflags=HIDDEN, timeout=15)
            if probe.returncode == 0:
                return str(candidate)
        except (OSError, subprocess.TimeoutExpired):
            continue
    raise RuntimeError('没有找到完整的 Python 环境，请按项目 README 安装依赖。')


def ensure_service(port):
    if healthy(port):
        return 'reused'
    if port_in_use(port):
        raise RuntimeError(f'端口 {port} 已被其他程序占用，或者原服务没有正常响应，请检查本地服务。')
    python = find_python()
    prefix = LOGS / f'desktop-{port}-{time.strftime("%Y%m%d-%H%M%S")}'
    with Path(str(prefix) + '.stdout.log').open('ab') as output, \
            Path(str(prefix) + '.stderr.log').open('ab') as errors:
        server = subprocess.Popen([python, '-m', 'uvicorn', 'app.main:app',
                                   '--app-dir', str(ROOT), '--host', '127.0.0.1', '--port', str(port)],
                                  cwd=ROOT, stdin=subprocess.DEVNULL, stdout=output,
                                  stderr=errors, creationflags=HIDDEN, close_fds=True)
    (LOGS / f'service-{port}.pid').write_text(str(server.pid), encoding='ascii')
    if port == 8002:
        (LOGS / 'knowledge-server.pid').write_text(str(server.pid), encoding='ascii')
    deadline = time.monotonic() + 45
    while not healthy(port):
        if server.poll() is not None:
            raise RuntimeError('服务启动失败，请查看项目 logs 文件夹中的 desktop 日志。')
        if time.monotonic() > deadline:
            raise RuntimeError('服务启动较慢，请稍等后再次双击。如仍无法打开，请查看 logs 文件夹。')
        time.sleep(0.35)
    return 'started'


def launch(port, open_browser=True):
    import msvcrt
    LOGS.mkdir(exist_ok=True)
    # 文件锁随启动器退出释放，连续双击也不会并发创建两个服务。
    with (LOGS / f'launcher-{port}.lock').open('a+b') as lock:
        lock.seek(0, 2)
        if lock.tell() == 0:
            lock.write(b'0')
            lock.flush()
        deadline = time.monotonic() + 60
        while True:
            try:
                lock.seek(0)
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise RuntimeError('启动器仍在准备服务，请稍后再双击。')
                time.sleep(0.25)
        try:
            state = ensure_service(port)
        finally:
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_UNLCK, 1)
    url = f'http://127.0.0.1:{port}/'
    with (LOGS / 'launcher.log').open('a', encoding='utf-8') as record:
        record.write(f'{time.strftime("%Y-%m-%d %H:%M:%S")} {state} {url}\n')
    if open_browser:
        webbrowser.open(url, new=2)
    return state, url


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8002)
    parser.add_argument('--no-browser', action='store_true')
    options = parser.parse_args()
    try:
        if not 1024 <= options.port <= 65535:
            raise RuntimeError('端口需要在1024到65535之间。')
        state, url = launch(options.port, not options.no_browser)
        if sys.stdout:
            print(f'READY {state} {url}')
    except Exception as error:
        # 仅展示启动器可控的错误，不记录密钥或环境变量。
        message = str(error) if isinstance(error, RuntimeError) else '启动遇到问题，请检查项目目录和 Python 环境。'
        if options.no_browser:
            if sys.stderr:
                print(message, file=sys.stderr)
        else:
            ctypes.windll.user32.MessageBoxW(None, message, '电商客服机器人 · 启动提示', 0x40)
        sys.exit(1)
