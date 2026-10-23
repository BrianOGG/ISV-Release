import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from patch_windows_launcher import ADAPTER, patch


class WindowsLauncherAdapterTests(unittest.TestCase):
    def test_keeps_venv_context_and_uses_direct_interpreter(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td).resolve()
            original = root / 'venv/Scripts/python.exe'
            base = root / 'python/python.exe'
            for path in (original, base):
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            state = SimpleNamespace(platform='win32', prefix=str(root/'venv'),
                                    base_prefix=str(root/'python'), executable=str(original),
                                    _base_executable=str(base))
            environment = {'ECAI_PORTABLE_ROOT': str(root)}
            scope = {'sys': state, 'os': SimpleNamespace(environ=environment), 'Path': Path}
            exec(ADAPTER, scope)
            scope['configure_windows_child_python']()
            self.assertEqual(state.executable, str(base))
            self.assertEqual(environment['__PYVENV_LAUNCHER__'], str(original))
            self.assertEqual(state.prefix, str(root/'venv'))
            state._base_executable = str(original)
            with self.assertRaisesRegex(RuntimeError, 'WINDOWS_PORTABLE_CONTEXT_INVALID'):
                scope['configure_windows_child_python']()

    def test_macos_does_not_require_or_change_portable_context(self):
        state = SimpleNamespace(platform='darwin', executable='/example/python')
        scope = {'sys': state}
        exec(ADAPTER, scope)
        scope['configure_windows_child_python']()
        self.assertEqual(state.executable, '/example/python')

    def test_public_launcher_contract_drift_is_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td)/'launcher.py'
            path.write_text('pass\n')
            with self.assertRaisesRegex(ValueError, 'PUBLIC_LAUNCHER_PATCH_CONTRACT_CHANGED'):
                patch(path)


if __name__ == '__main__':
    unittest.main()
