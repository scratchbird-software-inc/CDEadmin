"""Offline regression checks for native setup failure and ownership boundaries."""
import contextlib
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))
import native
import native_assets
import native_fixtures


class NativeSetupTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))

    def test_ci_collects_later_failures_and_never_labels_them_passed(self):
        def stage(name, _):
            if name in ('python', 'verify'):
                raise RuntimeError('owned failure ' + name)
        with patch.object(native, 'stage', side_effect=stage) as selected, \
                patch.object(native.platform, 'platform', return_value='owned-test-platform'), \
                patch.object(native.subprocess, 'check_output', return_value='revision'):
            self.assertEqual(native.ci(self.root), 1)
        self.assertEqual(selected.call_count, 9)
        receipt = json.loads((self.root / 'receipt.json').read_text())
        self.assertFalse(receipt['complete'])
        self.assertEqual([s['stage'] for s in receipt['steps'] if s['status'] == 'failed'],
                         ['python', 'verify'])

    def test_configuration_is_preserved(self):
        (self.root / 'web').mkdir()
        target = self.root / 'web/config_local.py'
        target.write_text('private configuration', encoding='utf-8')
        with patch.object(native, 'ROOT', self.root):
            native.configure()
        self.assertEqual(target.read_text(), 'private configuration')

    def test_targeted_success_is_not_full_environment_acceptance(self):
        with patch.object(native, 'stage'), \
                patch.object(native.platform, 'platform', return_value='owned-test-platform'), \
                patch.object(native.subprocess, 'check_output', return_value='revision'):
            self.assertEqual(native.ci(self.root, ('doctor',)), 0)
        receipt = json.loads((self.root / 'receipt.json').read_text())
        self.assertTrue(receipt['complete'])
        self.assertFalse(receipt['full_environment_complete'])

    def test_windows_corepack_uses_node_without_a_command_shell(self):
        wrapper = self.root / 'Node With Spaces/corepack.CMD'
        cli = wrapper.parent / 'node_modules/corepack/dist/corepack.js'
        cli.parent.mkdir(parents=True)
        cli.touch()
        with patch.object(native.platform, 'system', return_value='Windows'), \
                patch.object(native.shutil, 'which', side_effect=lambda name, **_: str(wrapper) if name == 'corepack.cmd' else None), \
                patch.object(native.subprocess, 'run') as execute:
            native.command(['corepack', 'yarn', 'install', '--immutable'], cwd=self.root)
        self.assertEqual(execute.call_args.args[0],
                         ['node', str(cli), 'yarn', 'install', '--immutable'])
        self.assertNotIn('shell', execute.call_args.kwargs)

    def test_cached_download_is_rehashed(self):
        downloads = self.root / 'downloads'
        downloads.mkdir()
        (downloads / 'asset.zip').write_bytes(b'corrupt')
        expected = hashlib.sha256(b'expected').hexdigest()
        with patch.object(native_assets, 'STATE', self.root), \
                patch.dict(native_assets.ASSETS, {'owned': ('https://example.invalid/asset.zip', expected)}), \
                patch.object(native_assets.urllib.request, 'urlopen') as fetch:
            with self.assertRaisesRegex(RuntimeError, 'SHA-256'):
                native_assets.download('owned')
            fetch.assert_not_called()

    def test_crash_cleanup_refuses_a_reused_foreign_pid(self):
        import psutil
        marker = self.root / 'owned-process.json'
        marker.write_text(json.dumps({'pid': 12345,
                          'executable': str(self.root / 'owned-server'),
                          'argument': str(self.root / 'owned-data')}))
        process = unittest.mock.Mock()
        process.is_running.return_value = True
        process.exe.return_value = str(self.root / 'another-program')
        process.cmdline.return_value = [str(self.root / 'owned-data')]
        with patch.object(psutil, 'Process', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'outside the owned fixture'):
                native_fixtures.cleanup_crashed_fixture(self.root)
        process.kill.assert_not_called()
        process.children.assert_not_called()

    def test_source_modules_resolve_unambiguously_on_case_insensitive_hosts(self):
        groups = {}
        for path in (native.ROOT / 'web/pgadmin').rglob('*'):
            if path.suffix in ('.js', '.jsx', '.ts', '.tsx'):
                key = str(path.parent).casefold(), path.stem.casefold()
                groups.setdefault(key, []).append(str(path.relative_to(native.ROOT)))
        collisions = [paths for paths in groups.values() if len(paths) > 1]
        self.assertEqual(collisions, [], 'Extensionless imports collide on Windows/macOS')

    def test_host_changes_require_disposable_ci(self):
        with patch.dict(native.os.environ, {}, clear=True), \
                patch.object(native, 'environment', return_value={}), \
                patch.object(native, 'command') as execute:
            with self.assertRaisesRegex(RuntimeError, 'disposable CI'):
                native.stage('prerequisites', self.root)
            execute.assert_not_called()

    def test_native_clients_reject_linux_without_downloading(self):
        with patch.object(native_assets.platform, 'system', return_value='Linux'), \
                patch.object(native_assets, 'download') as fetch:
            with self.assertRaisesRegex(RuntimeError, 'Windows and macOS'):
                native_assets.clients(self.root, {})
            fetch.assert_not_called()

    def test_no_environment_secret_is_copied_to_generated_requirements(self):
        path = self.root / 'requirements.txt'
        with patch.dict(native.os.environ, {'OWNED_PASSWORD': 'never-store-this'}):
            native.requirements(path)
        self.assertNotIn('never-store-this', path.read_text())
        self.assertIn('tools/reference_engine_demos/requirements.txt', path.read_text())


if __name__ == '__main__':
    unittest.main()
