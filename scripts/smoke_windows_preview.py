"""Test final Skill installation from a hash-verified cached final runtime."""
import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import urllib.request
import zipfile


def smoke(project, version, output):
    output = Path(output).resolve()
    with tempfile.TemporaryDirectory(prefix='win-preview-final-') as td:
        root = Path(td)
        skill = root/'skill'
        skill.mkdir()
        with zipfile.ZipFile(output/(project+'-portable-win-skill-'+version+'.zip')) as zip:
            zip.extractall(skill)
        conf = dict(line.split('=', 1) for line in
                    (skill/'assets/portable-windows-x64.conf').read_text().splitlines() if line)
        archive = output/(project+'-portable-windows-x64-'+version+'.tar.gz')
        h = hashlib.file_digest(archive.open('rb'), 'sha256').hexdigest()
        if h != conf['PORTABLE_SHA256']:
            raise RuntimeError('FINAL_ARCHIVE_HASH_MISMATCH')
        install = root/'安装目录 with spaces'
        cache = install/'portable'
        cache.mkdir(parents=True)
        shutil.copyfile(archive, cache/(h+'.tar.gz'))
        env = os.environ.copy()
        env.pop('ECAI_PORTABLE_ROOT', None)
        env.pop('__PYVENV_LAUNCHER__', None)
        env['KOL_DATA_DIR' if project == 'kol-selection' else 'E2E_DATA_DIR'] = str(root/'app-data')
        # Seed a historical, UTF-8 fixture with an incompatible task shape.
        # The compiled service must start, leave this file unchanged, and keep
        # normal API access. This is intentionally *not* a real user's task.
        legacy_file = None
        legacy_hash = None
        if project == 'kol-selection':
            legacy = root / 'app-data' / 'workflows' / ('a' * 32)
            legacy.mkdir(parents=True)
            legacy_file = legacy / 'task.json'
            legacy_file.write_text(json.dumps({
                'id': 'a' * 32, 'schema_version': 1, 'synthetic': True,
                'created_at': '2026-10-23T10:00:00Z',
                'config': {'name': '中文旧演示任务', 'targets': []},
                'modules': {},
            }, ensure_ascii=False), encoding='utf-8')
            with legacy_file.open('rb') as handle:
                legacy_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
        def call(action):
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass',
                '-File', str(skill/'scripts/setup.ps1'), '-Action', action, '-InstallDir', str(install),
                '-Port', str(port)], env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180)
            if result.returncode:
                if action == 'install' and project == 'kol-selection':
                    installed_python = cache/h/conf['PORTABLE_PYTHON']
                    node = next((cache/h/'python').rglob('node.exe'), None)
                    print('FINAL_BROWSER_NODE_EXISTS='+str(bool(node and node.is_file())).lower(), flush=True)
                    print('FINAL_BROWSER_NODE_PATH_OVER_260='+str(bool(node and len(str(node))>=260)).lower(), flush=True)
                    print('FINAL_BROWSER_CHROME_COUNT='+str(len(list((cache/h/'browsers').rglob('chrome.exe')))), flush=True)
                    diag = root/'app-data/logs/diagnostics.jsonl'
                    if diag.is_file():
                        for row in diag.read_text(encoding='utf-8').splitlines()[-3:]:
                            item = json.loads(row)
                            kind = item.get('error_type', '')
                            if re.fullmatch('[A-Za-z_]+', kind):
                                print('FINAL_BROWSER_ERROR_TYPE='+kind, flush=True)
                            number = item.get('winerror')
                            if isinstance(number, int):
                                print('FINAL_BROWSER_WINERROR='+str(number), flush=True)
                codes = re.findall(rb'\bPORTABLE_[A-Z_]+\b', result.stdout + result.stderr)
                code = codes[-1].decode('ascii') if codes else 'NO_PUBLIC_CODE'
                raise RuntimeError('FINAL_SKILL_'+action.upper()+'_FAILED_'+code)
            print('FINAL_SKILL_'+action.upper()+'_OK', flush=True)
        call('prepare')
        call('install')
        call('install')
        bundle = cache/h
        if (bundle/'ecai_launcher.py').read_bytes() != (skill/'scripts/ecai_launcher.py').read_bytes():
            raise RuntimeError('FINAL_LAUNCHER_WAS_OVERWRITTEN')
        call('version')
        call('doctor')
        started = False
        try:
            call('start')
            started = True
            call('status')
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with opener.open('http://127.0.0.1:'+str(port)+'/', timeout=15) as response:
                if response.status != 200 or b'<html' not in response.read(50000).lower():
                    raise RuntimeError('FINAL_SKILL_WEB_FAILED')
            print('FINAL_SKILL_WEB_OK', flush=True)
            if project == 'kol-selection':
                base = 'http://127.0.0.1:' + str(port)
                def json_endpoint(url):
                    with opener.open(base + url, timeout=60) as response:
                        if response.status != 200 or 'json' not in response.headers.get('content-type', ''):
                            raise RuntimeError('FINAL_WORKFLOW_API_NOT_JSON')
                        return json.load(response)
                rows = json_endpoint('/api/workflows')
                if (not isinstance(rows, list) or len(rows) != 1
                        or rows[0].get('archived_demo') is not True
                        or len(rows[0]['config']['targets']) != 23):
                    raise RuntimeError('FINAL_WORKFLOW_DEMO_NOT_READY')
                demo_id = rows[0]['id']
                single = json_endpoint('/api/workflows/' + demo_id)
                if single.get('id') != demo_id:
                    raise RuntimeError('FINAL_WORKFLOW_DEMO_DETAIL_FAILED')
                if len(json_endpoint('/api/workflows')) != 1:
                    raise RuntimeError('FINAL_WORKFLOW_DEMO_RELOAD_FAILED')
                with opener.open(base + '/api/workflows/' + demo_id
                                 + '/modules/screening/download/report.html', timeout=60) as response:
                    if response.status != 200 or b'<html' not in response.read(100000).lower():
                        raise RuntimeError('FINAL_WORKFLOW_DEMO_REPORT_FAILED')
                if not legacy_file.is_file():
                    raise RuntimeError('FINAL_WORKFLOW_LEGACY_DATA_MISSING')
                with legacy_file.open('rb') as handle:
                    new_hash = hashlib.file_digest(handle, 'sha256').hexdigest()
                if new_hash != legacy_hash:
                    raise RuntimeError('FINAL_WORKFLOW_LEGACY_DATA_MODIFIED')
                diag = root / 'app-data' / 'logs' / 'workflow-diagnostics.jsonl'
                if not diag.is_file() or 'workflow.legacy_task_skipped' not in diag.read_text(encoding='utf-8'):
                    raise RuntimeError('FINAL_WORKFLOW_LEGACY_NOT_QUARANTINED')
                print('FINAL_WINDOWS_WORKFLOW_UTF8_DEMO_AND_LEGACY_PASSED', flush=True)
        finally:
            if started:
                call('stop')
                call('stop')
        print('FINAL_WINDOWS_PREVIEW_INSTALL_PASSED', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('project', 'version', 'output'):
        p.add_argument('--'+name, required=True)
    a = p.parse_args()
    smoke(a.project, a.version, a.output)
