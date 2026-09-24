"""Offline safety and routing tests; never installs or starts engines."""
import contextlib
import io
from pathlib import Path
import runpy
import shlex
import tempfile
import unittest
from unittest.mock import patch

import manage
import remote


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='cdeadmin-setup-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.python = self.root / '.venv/bin/python'
        self.python.parent.mkdir(parents=True)
        self.python.touch()
        (self.root / 'web').mkdir()
        (self.root / 'web/config_local.py').touch()
        for name, value in [('ROOT', self.root), ('PYTHON', self.python),
                            ('DEMO', self.root / 'tools' /
                             'reference_engine_demos')]:
            self.enterContext(patch.object(manage, name, value))
        self.enterContext(patch.object(manage.platform, 'system',
                                       return_value='Linux'))
        self.enterContext(patch.object(manage.platform, 'machine',
                                       return_value='x86_64'))
        self.enterContext(contextlib.redirect_stdout(io.StringIO()))
        self.enterContext(contextlib.redirect_stderr(io.StringIO()))

    def test_existing_configuration_is_preserved(self):
        target = self.root / 'web/config_local.py'
        target.write_text('private setting')
        with self.assertRaises(FileExistsError):
            manage.configure()
        self.assertEqual(target.read_text(), 'private setting')

    def test_template_paths_and_security(self):
        target = self.root / 'web/config_local.py'
        target.unlink()
        source = self.root / 'tools/development/config_local.example.py'
        source.parent.mkdir(parents=True)
        source.write_text(Path(__file__).with_name(
            'config_local.example.py').read_text())
        manage.configure()
        settings = runpy.run_path(str(target))
        self.assertEqual(target.stat().st_mode & 0o777, 0o600)
        expected = str(self.root / '.devstate/application')
        self.assertEqual(settings['DATA_DIR'], expected)
        for name in ('LOG_FILE', 'SQLITE_PATH', 'SESSION_DB_PATH',
                     'STORAGE_DIR',
                     'KERBEROS_CCACHE_DIR', 'AZURE_CREDENTIAL_CACHE_DIR',
                     'CDEADMIN_OPERATION_STORE_PATH'):
            self.assertTrue(settings[name].startswith(expected + '/'), name)
        self.assertTrue(settings['MASTER_PASSWORD_REQUIRED'])
        self.assertFalse(settings['DEBUG'])
        self.assertEqual(settings['DEFAULT_SERVER'], '127.0.0.1')

    def test_lifecycle_and_client_arguments(self):
        for action in ('list', 'status', 'start', 'stop', 'seed', 'verify',
                       'prepare', 'clients', 'register'):
            with self.subTest(action=action), \
                    patch.object(manage, 'run') as run:
                arguments = ['--user', 'developer@example.com', '--dry-run'] \
                    if action == 'register' else ['postgresql']
                manage.main([action, *arguments])
                script = {'clients': 'bootstrap.py',
                          'register': 'register_demo_profiles.py'}.get(
                              action, 'demo_estate.py')
                expected = [self.python, manage.DEMO / script]
                if action not in ('clients', 'register'):
                    expected.append(action)
                run.assert_called_once_with([*expected, *arguments])

    def test_application_commands(self):
        for action, tail in [('init', ['web/setup.py', 'setup-db']),
                             ('run', ['web/CDEadmin.py'])]:
            with self.subTest(action=action), \
                    patch.object(manage, 'run') as run:
                manage.main([action])
                run.assert_called_once_with(
                    [self.python, self.root / tail[0], *tail[1:]])

    def test_configuration_required(self):
        (self.root / 'web/config_local.py').unlink()
        for action in ('run', 'init', 'register'):
            with self.subTest(action=action), \
                    patch.object(manage, 'run') as run:
                with self.assertRaises(SystemExit):
                    manage.main([action])
                run.assert_not_called()

    def test_missing_venv_blocks_application(self):
        self.python.unlink()
        with patch.object(manage, 'run') as run:
            with self.assertRaises(SystemExit):
                manage.main(['start', 'postgresql'])
            run.assert_not_called()

    def test_incomplete_venv_is_not_overwritten(self):
        self.python.unlink()
        with patch.object(manage, 'run') as run:
            with self.assertRaises(SystemExit):
                manage.main(['python'])
            run.assert_not_called()

    def test_python_combines_requirements_and_checks_conflicts(self):
        with patch.object(manage, 'run') as run:
            manage.main(['python'])
        self.assertEqual(run.call_args_list[0].args[0], [
            self.python, '-m', 'pip', 'install', '-r',
            self.root / 'requirements.txt', '-r',
            manage.DEMO / 'requirements.txt'])
        self.assertEqual(run.call_args_list[1].args[0],
                         [self.python, '-m', 'pip', 'check'])

    def test_frontend_preserves_lockfile(self):
        with patch.object(manage, 'run') as run:
            manage.main(['frontend'])
        self.assertEqual(run.call_args_list[0].args,
                         (['corepack', 'yarn', 'install', '--immutable'],
                          self.root / 'web'))
        self.assertEqual(run.call_args_list[1].args[0],
                         ['corepack', 'yarn', 'webpacker'])
        self.assertEqual(run.call_args_list[1].args[2]['NODE_ENV'],
                         'production')

    def test_native_non_linux_is_rejected(self):
        with patch.object(manage.platform, 'system', return_value='Darwin'), \
                patch.object(manage, 'run') as run:
            with self.assertRaises(SystemExit):
                manage.main(['python'])
            run.assert_not_called()

    def doctor(self, values, env=None):
        from subprocess import CompletedProcess
        with patch.object(manage.shutil, 'which', return_value='/bin/tool'), \
                patch.dict(manage.os.environ, env or {}, clear=True), \
                patch.object(manage.subprocess, 'run', side_effect=[
                    CompletedProcess([], 0, value) for value in values]):
            return manage.doctor()

    def test_doctor_pass(self):
        self.assertEqual(self.doctor([
            'unix:///var/run/docker.sock', 'linux/x86_64', 'Compose v2',
            'v22.22.3', 'go version go1.25.5 linux/amd64']), 0)

    def test_doctor_rejects_remote_daemon_and_old_versions(self):
        defaults = ['unix:///var/run/docker.sock', 'linux/x86_64',
                    'Compose v2', 'v22.22.3',
                    'go version go1.25.5 linux/amd64']
        for index, replacement in [(0, 'ssh://remote'), (1, 'linux/aarch64'),
                                   (3, 'v20.0.0'), (4, 'go version go1.25.4'),
                                   (4, 'unparseable')]:
            with self.subTest(replacement=replacement):
                values = list(defaults)
                values[index] = replacement
                self.assertEqual(self.doctor(values), 1)
        self.assertEqual(self.doctor(
            defaults, {'DOCKER_HOST': 'tcp://remote'}), 1)

    def test_doctor_collects_all_missing_tools(self):
        with patch.object(manage.shutil, 'which', return_value=None), \
                patch.object(manage.subprocess, 'run',
                             side_effect=FileNotFoundError) as run:
            self.assertEqual(manage.doctor(), 1)
            self.assertEqual(run.call_count, 5)

    def test_remote_quotes_arguments(self):
        args = ['register', '--user', 'a; echo test@example.com']
        result = remote.command('dev@vm', '/home/dev/my project', args)
        self.assertEqual(result[:3], ['ssh', '-t', 'dev@vm'])
        self.assertEqual(shlex.split(result[3]), [
            'bash', '/home/dev/my project/tools/development/dev.sh', *args])

    def test_remote_rejects_options_and_relative_paths(self):
        for host, path in [('-oProxyCommand=bad', '/repo'),
                           ('vm', 'relative')]:
            with self.assertRaises(ValueError):
                remote.command(host, path, ['doctor'])


if __name__ == '__main__':
    unittest.main()
