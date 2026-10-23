"""Create final Windows preview assets from a successful native CI runtime."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import zipfile
from patch_windows_launcher import patch


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def package(project, version, archive, source, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    skill = Path(source)/project/'skills'/project
    tag = project+'-portable-win-'+version
    filename = project+'-portable-windows-x64-'+version+'.tar.gz'
    with tempfile.TemporaryDirectory(prefix='windows-preview-') as td:
        stage = Path(td)/'payload'
        stage.mkdir()
        with tarfile.open(archive, 'r:gz') as tar:
            tar.extractall(stage, filter='data')
        meta = json.loads((stage/'portable.json').read_text(encoding='utf-8'))
        if (meta.get('project') != project or meta.get('platform') != 'windows-x64'
                or meta.get('version') != version or meta.get('packages_preinstalled') is not True):
            raise ValueError('PREVIEW_RUNTIME_METADATA_MISMATCH')
        for name in ('identity-probe-data', 'test-kol-data', 'test-e2e-data', 'venv'):
            path = stage/name
            if path.exists():
                shutil.rmtree(path)
        launcher = stage/'ecai_launcher.py'
        shutil.copyfile(skill/'scripts/ecai_launcher.py', launcher)
        patch(launcher)
        meta['public_launcher_sha256'] = sha(launcher)
        meta['windows_venv_pid_adapter'] = True
        (stage/'portable.json').write_text(json.dumps(meta, indent=2)+'\n', encoding='utf-8')
        dest = output/filename
        with tarfile.open(dest, 'w:gz', compresslevel=3) as tar:
            tar.add(stage, arcname='.')
        config = '\n'.join((
            'PORTABLE_URL=https://github.com/BrianOGG/ISV-Release/releases/download/'+tag+'/'+filename,
            'PORTABLE_SHA256='+sha(dest), 'PORTABLE_VERSION='+version,
            'PORTABLE_PYTHON='+meta['python_executable'], ''))
        text = ('---\nname: '+project+'\ndescription: Windows x64 便携测试版安装与启动\n---\n\n'
                '# Windows x64 测试版\n\n'
                '已附带 Python 3.12.10、公开运行依赖、浏览器和编译核心。\n'
                '首次安装从同一 Release 下载完整运行时，无需自行配置 Python 或 pip。\n\n'
                '在解压后的目录执行：\n\n'
                '```powershell\npowershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Action install\n'
                'powershell -NoProfile -ExecutionPolicy Bypass -File scripts/setup.ps1 -Action start\n```\n\n'
                '同一入口支持 status、stop、doctor。打开启动输出中的本地工作台地址。\n'
                '此为测试候选，真实设备安装、平台登录和业务任务需要实测。\n')
        setup = (skill/'scripts/setup-portable.ps1').read_bytes()
        if not setup.startswith(b'\xef\xbb\xbf'):
            raise ValueError('PREVIEW_POWERSHELL_BOM_REQUIRED')
        marker = b'^([A-Z_]+)='
        if setup.count(marker) != 1:
            raise ValueError('PREVIEW_SETUP_PARSER_CONTRACT_CHANGED')
        setup = setup.replace(marker, b'^([A-Z][A-Z0-9_]*)=')
        extract_marker = b'        & tar.exe -xzf $Archive -C $Stage'
        # Win32 tar receives only ASCII relative arguments; PowerShell changes
        # the current directory through its Unicode-capable filesystem APIs.
        # This also avoids extending every archive entry with a long prefix.
        if setup.count(extract_marker) != 1:
            raise ValueError('PREVIEW_SETUP_EXTRACT_CONTRACT_CHANGED')
        setup = setup.replace(extract_marker, (
            '        Push-Location -LiteralPath $Cache\r\n'
            '        try {\r\n'
            '          & tar.exe -xzf ($Hash+\'.tar.gz\') -C (Split-Path -Path $Stage -Leaf)\r\n'
            '          $ExtractExit=$LASTEXITCODE\r\n'
            '        } finally { Pop-Location }\r\n'
            '        $LASTEXITCODE=$ExtractExit').encode('ascii'))
        entries = {'SKILL.md': text.encode('utf-8'), 'scripts/setup.ps1': setup,
                   'scripts/ecai_launcher.py': launcher.read_bytes(),
                   'assets/portable-windows-x64.conf': config.encode('ascii')}
        zipname = project+'-portable-win-skill-'+version+'.zip'
        with zipfile.ZipFile(output/zipname, 'w', compression=zipfile.ZIP_DEFLATED) as zip:
            for name, body in entries.items():
                zip.writestr(name, body)
    (output/'SHA256SUMS.txt').write_text(''.join(sha(p)+'  '+p.name+'\n'
         for p in sorted(output.iterdir()) if p.name != 'SHA256SUMS.txt'), encoding='ascii', newline='\n')
    print('WINDOWS_PREVIEW_ASSETS_READY', flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser()
    for name in ('project', 'version', 'archive', 'source', 'output'):
        p.add_argument('--'+name, required=True)
    a = p.parse_args()
    package(a.project, a.version, a.archive, a.source, a.output)
