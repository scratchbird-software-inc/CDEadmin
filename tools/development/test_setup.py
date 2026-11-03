"""Offline safety and routing tests; never installs or starts engines."""
import contextlib
import io
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
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
        self.environment_version = self.enterContext(patch.object(
            manage.subprocess, 'run', return_value=subprocess.CompletedProcess(
                [], 0, f'{sys.version_info.major} {sys.version_info.minor}\n')))
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

    def test_mismatched_venv_blocks_application_before_dispatch(self):
        self.environment_version.return_value.stdout = '3 13\n'
        with patch.object(manage, 'run') as run:
            with self.assertRaises(SystemExit):
                manage.main(['run'])
            run.assert_not_called()

    def test_incomplete_venv_is_not_overwritten(self):
        self.python.unlink()
        with patch.object(manage, 'run') as run:
            with self.assertRaises(SystemExit):
                manage.main(['python'])
            run.assert_not_called()

    def test_python_combines_requirements_and_checks_conflicts(self):
        order = []
        with patch.object(manage, 'run', side_effect=lambda args, *rest: order.append(args)) as run, \
                patch.object(manage, 'mariadb_driver', side_effect=lambda: order.append('mariadb')):
            manage.main(['python'])
        self.assertEqual(order, [
            [self.python, '-m', 'pip', 'install', '-r',
             self.root / 'requirements.txt', '-r',
             manage.DEMO / 'requirements.txt', '-r',
             self.root / 'web/regression/requirements.txt', manage.TEST_PYTEST],
            [self.python, '-B', '-m', 'tools.cdeadmin_install_mysql_driver',
             '--receipt', self.root / '.devstate/mysql-driver.json'],
            # The patched wheel replaces the stock pin before conflicts are checked.
            'mariadb',
            [self.python, '-m', 'pip', 'check']])
        self.assertEqual(run.call_count, 3)

    def test_patched_mariadb_wheel_is_built_outside_the_repository_and_installed(self):
        import native_assets
        archive = self.root / 'mariadb-1.1.14.tar.gz'
        commands = []
        def build(args, *rest):
            commands.append(args)
            if '--output' in args:
                output = Path(args[args.index('--output') + 1])
                self.assertFalse(output.exists())
                self.assertNotIn(Path(manage.__file__).resolve().parents[2], output.parents)
                (output / 'wheels').mkdir(parents=True)
                (output / 'wheels/mariadb-1.1.14-cp314-cp314-linux_x86_64.whl').touch()
        with patch.object(native_assets, 'download', return_value=archive) as download, \
                patch.object(manage, 'run', side_effect=build):
            manage.mariadb_driver()
        download.assert_called_once_with('mariadb-python')
        self.assertEqual(commands[0][:6], [self.python, '-B', '-m', 'tools.cdeadmin_build_mariadb_driver',
                                           '--archive', archive])
        self.assertEqual(commands[1][:5], [self.python, '-m', 'pip', 'install', '--no-deps'])
        self.assertEqual(commands[1][5:6], ['--force-reinstall'])
        self.assertEqual(Path(commands[1][6]).name, 'mariadb-1.1.14-cp314-cp314-linux_x86_64.whl')

    def test_missing_patched_mariadb_wheel_is_refused(self):
        import native_assets
        with patch.object(native_assets, 'download', return_value=self.root / 'archive'), \
                patch.object(manage, 'run') as run:
            with self.assertRaises(RuntimeError):
                manage.mariadb_driver()
        self.assertEqual(run.call_count, 1)

    def interpreter_paths(self):
        tracked = self.root / 'tracked'
        (tracked / 'lib').mkdir(parents=True)
        (tracked / 'lib/libsqlite3.so.3.53.0').write_bytes(b'tracked library')
        (tracked / 'lib/libsqlite3.so.0').symlink_to('libsqlite3.so.3.53.0')
        native = self.root / '.native'
        self.enterContext(patch.object(manage, 'TRACKED_SQLITE', tracked))
        self.enterContext(patch.object(manage, 'NATIVE', native))
        return tracked, native

    def test_interpreter_links_the_tracked_sqlite_and_reads_it_back(self):
        import native_assets
        tracked, native = self.interpreter_paths()
        source = native / 'python-source/Python-3.14.8'
        source.mkdir(parents=True)
        (source / 'configure').touch()
        self.enterContext(patch.dict(manage.os.environ, {'LD_LIBRARY_PATH': '/elsewhere'}))
        def installed(args, *rest):
            if args == ['make', 'install']: (native / 'python').mkdir()
        with patch.object(manage, 'run', side_effect=installed) as run, \
                patch.object(native_assets, 'download') as download:
            manage.interpreter()
        download.assert_not_called()
        configure, make, install, check = [call.args for call in run.call_args_list]
        self.assertEqual(configure[0], [source / 'configure', f'--prefix={native / "python"}',
                                        '--with-ensurepip=install', '--enable-loadable-sqlite-extensions',
                                        '--enable-optimizations', '--with-lto'])
        environment = configure[2]
        self.assertNotIn('LD_LIBRARY_PATH', environment)
        self.assertEqual(environment['LIBSQLITE3_LIBS'], f'-L{tracked}/lib -lsqlite3')
        self.assertEqual(environment['LDFLAGS'], f'-Wl,-rpath,{tracked}/lib')
        self.assertEqual(install[0], ['make', 'install'])
        # The build is accepted only after the new interpreter reports the
        # tracked file, its version and every option the helpers require.
        self.assertEqual(check[0][0], native / 'python/bin/python3.14')
        self.assertEqual(check[0][4:], [tracked / 'lib/libsqlite3.so.0', '--enable-optimizations', '--with-lto',
                                        *manage.SQLITE_OPTIONS])
        self.assertIn('CONFIG_ARGS', check[0][3])
        self.assertIn('"3.53.0"', check[0][3])
        import hashlib, json
        marker = json.loads((native / 'python/.cdeadmin-complete').read_text())
        self.assertEqual(marker['sqlite_sha256'], hashlib.sha256(b'tracked library').hexdigest())
        self.assertEqual(marker['optimizations'], ['--enable-optimizations', '--with-lto'])
        with patch.object(manage, 'run') as again:
            manage.interpreter()
        again.assert_not_called()

    def test_interpreter_is_not_rebuilt_or_replaced(self):
        tracked, native = self.interpreter_paths()
        (native / 'python').mkdir(parents=True)
        with patch.object(manage, 'run') as run:
            with self.assertRaises(RuntimeError):
                manage.interpreter()
        run.assert_not_called()
        marker = native / 'python/.cdeadmin-complete'
        marker.write_text('other inputs')
        with patch.object(manage, 'run') as run:
            with self.assertRaises(RuntimeError):
                manage.interpreter()
        run.assert_not_called()

    def test_setup_stages_do_not_inherit_the_engine_library_path(self):
        # Setup stages use the interpreter's own libraries. MySQL Shell's
        # private OpenSSL, whose CA path is another host's, is on no path.
        probe = self.root / 'python'
        probe.write_text('#!/bin/sh\nprintf "%s" "${LD_LIBRARY_PATH:-}"\n')
        probe.chmod(0o700)
        launcher = Path(__file__).with_name('dev.sh')
        environment = {key: value for key, value in manage.os.environ.items()
                       if key not in ('LD_LIBRARY_PATH', 'VIRTUAL_ENV')}
        environment['SCRATCHROBIN_PYTHON'] = str(probe)
        def library_path(action):
            # setUp replaces subprocess.run, which check_output would use.
            with subprocess.Popen(['bash', str(launcher), action], env=environment,
                                  stdout=subprocess.PIPE, text=True) as process:
                output = process.communicate(timeout=60)[0]
            self.assertEqual(process.returncode, 0)
            return output
        for action in ('interpreter', 'python'):
            self.assertNotIn('reference_engine_demos/runtime', library_path(action), action)
        engine = library_path('status')
        self.assertIn('runtime/foundationdb/lib', engine)
        self.assertNotIn('runtime/mysql', engine)

    def test_interpreter_builds_the_tracked_sqlite_when_absent(self):
        tracked, native = self.interpreter_paths()
        (tracked / 'lib/libsqlite3.so.0').unlink()
        with patch.object(manage, 'run') as run:
            with self.assertRaises(FileNotFoundError):
                manage.interpreter()
        run.assert_called_once_with([sys.executable, manage.DEMO / 'sqlite_tracked.py',
                                     '--version', '3.53.0'])

    def test_frontend_refreshes_ddn_and_preserves_lockfile(self):
        with patch.object(manage, 'run') as run:
            manage.main(['frontend'])
        self.assertEqual(run.call_args_list[0].args[0],
                         [sys.executable, self.root / 'tools/refresh_ddn.py'])
        self.assertEqual(run.call_args_list[1].args,
                         (['corepack', 'yarn', 'install', '--immutable'],
                          self.root / 'web'))
        self.assertEqual(run.call_args_list[2].args[0],
                         ['corepack', 'yarn', 'webpacker'])
        self.assertEqual(run.call_args_list[2].args[2]['NODE_ENV'],
                         'production')

    def test_ddn_refreshes_snapshot(self):
        with patch.object(manage, 'run') as run:
            manage.main(['ddn'])
        run.assert_called_once_with(
            [sys.executable, self.root / 'tools/refresh_ddn.py'])

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
