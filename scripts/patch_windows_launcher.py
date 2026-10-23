"""Public portable-launcher adapter for Windows venv process identity.

CPython's redirector passes __PYVENV_LAUNCHER__ to the base interpreter.
Use that same context for child commands, avoiding the extra redirector PID.
No private Core modules or their identity checks are changed.
"""
from pathlib import Path

ADAPTER = '''
def configure_windows_child_python():
    if sys.platform != 'win32':
        return
    root = Path(os.environ['ECAI_PORTABLE_ROOT']).resolve()
    original = Path(sys.executable)
    base = Path(sys._base_executable)
    if (sys.prefix == sys.base_prefix or not original.is_absolute()
            or not original.is_file() or not base.is_absolute() or not base.is_file()
            or not original.resolve().is_relative_to((root / 'venv').resolve())
            or not base.resolve().is_relative_to((root / 'python').resolve())
            or Path(sys.prefix).resolve() != (root / 'venv').resolve()):
        raise RuntimeError('WINDOWS_PORTABLE_CONTEXT_INVALID')
    os.environ['__PYVENV_LAUNCHER__'] = str(original)
    sys.executable = str(base)

'''


def patch(path):
    path = Path(path)
    text = path.read_text(encoding='utf-8')
    marker = "if __name__ == '__main__':\n"
    if text.count(marker) != 1 or 'configure_windows_child_python' in text:
        raise ValueError('PUBLIC_LAUNCHER_PATCH_CONTRACT_CHANGED')
    text = text.replace(marker, ADAPTER + marker + '    configure_windows_child_python()\n')
    compile(text, str(path), 'exec')
    path.write_text(text, encoding='utf-8')
