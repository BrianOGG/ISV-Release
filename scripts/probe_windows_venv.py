"""CI-only authenticated process identity probe; prints booleans, never tokens."""
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request


def probe(python, launcher, release, stage, project, environment):
    env = environment.copy()
    data = Path(stage) / 'identity-probe-data'
    data.mkdir()
    env['KOL_DATA_DIR' if project == 'kol-selection' else 'E2E_DATA_DIR'] = str(data)
    token = secrets.token_urlsafe(32)
    env['EC_AI_RUNTIME_TOKEN'] = token
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(stop=False):
        req = urllib.request.Request(
            'http://127.0.0.1:%d/api/runtime%s' % (port, '/stop' if stop else ''),
            headers={'Authorization': 'Bearer ' + token}, method='POST' if stop else 'GET')
        with opener.open(req, timeout=2) as response:
            return json.load(response)
    with (data / 'child.log').open('wb') as logfile:
        child = subprocess.Popen([str(python), '-I', str(launcher), '--release', str(release),
                                  'serve', '--port', str(port)], env=env, cwd=data,
                                 stdin=subprocess.DEVNULL, stdout=logfile, stderr=logfile,
                                 creationflags=subprocess.CREATE_NO_WINDOW)
        healthy = False
        try:
            for _ in range(30):
                try:
                    record = json.loads((data / 'runtime.json').read_text(encoding='utf-8'))
                    reply = request()
                    healthy = (record.get('token') == token and reply.get('app') == project
                               and reply.get('pid') == record.get('pid'))
                    if healthy:
                        print('WIN_PROBE_PID_MATCH=' + str(record['pid'] == child.pid).lower(), flush=True)
                        print('WIN_PROBE_TOKEN_MATCH=true', flush=True)
                        break
                except (OSError, ValueError):
                    pass
                if child.poll() is not None:
                    break
                time.sleep(1)
            print('WIN_PROBE_AUTHENTICATED_HEALTH=' + str(healthy).lower(), flush=True)
        finally:
            if healthy:
                request(stop=True)
            try:
                child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.terminate()
                child.wait(timeout=10)
        if not healthy:
            raise RuntimeError('WIN_IDENTITY_PROBE_NOT_HEALTHY')

