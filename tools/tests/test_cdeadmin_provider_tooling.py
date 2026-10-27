##########################################################################
#
# CDEadmin - Multi-engine Database Administration
#
# Copyright (C) 2013 - 2026, The pgAdmin Development Team
# This software is released under the PostgreSQL Licence
#
##########################################################################

"""Provider-owned external tool authority tests."""

from __future__ import annotations

import sys
import os
import tempfile
import threading
import unittest
from pathlib import Path
from types import ModuleType


ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / 'web'
if str(WEB) not in sys.path:
    sys.path.insert(0, str(WEB))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(WEB / 'pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.sdk.tooling import (  # noqa: E402
    ProviderToolError,
    ProviderToolGrant,
    ProviderToolRunner,
    tool_environment,
)


class ProviderToolRunnerTests(unittest.TestCase):

    def test_native_service_file_is_granted_by_environment_and_never_added_to_arguments(self):
        with tempfile.TemporaryDirectory(prefix='sr-tool-service-file-') as workspace:
            result = ProviderToolRunner({'python':sys.executable}).run(
                ProviderToolGrant('python',workspace,'127.0.0.1',5432,secret_environment_names=('PGSERVICEFILE',)),
                ['-c','import os,sys,pathlib;assert len(sys.argv)==1;print(pathlib.Path(os.environ["PGSERVICEFILE"]).read_text(),end="")'],
                secret_config=b'private-service-canary',secret_argument=None,
                secret_environment_name='PGSERVICEFILE',redact_values=('private-service-canary',))
            self.assertEqual(0,result['return_code'])
            self.assertEqual('[redacted]',result['stdout'])
            self.assertEqual([],list(Path(workspace).iterdir()))

    def test_live_process_environment_is_isolated_and_host_is_explicit(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(prefix='sr-tool-environment-') as workspace:
            runner = ProviderToolRunner({'python':sys.executable})
            grant = ProviderToolGrant('python', workspace, '127.0.0.1', 5432)
            with patch.dict(os.environ, {'PGPASSWORD':'private-environment-canary'}):
                result = runner.run(grant, ['-c', 'import os;print(os.environ.get("PGPASSWORD"));print(os.environ.get("USERPROFILE") if os.name=="nt" else os.environ["HOME"])'])
            self.assertEqual(0, result['return_code'])
            self.assertEqual(['None', workspace], result['stdout'].splitlines())
            self.assertEqual('application-host', result['execution_host']['kind'])
            self.assertFalse(result['remote_finality_inferred'])

    def test_both_streams_are_drained_bounded_and_secret_crossing_limit_is_redacted(self):
        with tempfile.TemporaryDirectory(prefix='sr-tool-output-') as workspace:
            runner = ProviderToolRunner({'python':sys.executable})
            grant = ProviderToolGrant('python', workspace, '127.0.0.1', 5432, max_output_bytes=1024)
            secret = 'leakcanary-never-export'
            code = 'import os;os.write(1,b"a"*1018+b"leakcanary-never-export"+b"z"*2000000);os.write(2,b"e"*2000000)'
            observations = []
            result = runner.run(grant, ['-c',code], redact_values=(secret,), progress=observations.append)
            self.assertEqual(0, result['return_code'])
            self.assertLessEqual(len(result['stdout'].encode()),1024)
            self.assertLessEqual(len(result['stderr'].encode()),1024)
            self.assertNotIn('leakca', result['stdout'])
            self.assertTrue(result['stdout_truncated'] and result['stderr_truncated'])
            self.assertGreaterEqual(result['process_observation']['stdout_bytes'],2000000)
            self.assertGreaterEqual(result['process_observation']['stderr_bytes'],2000000)
            self.assertNotIn(secret,repr(observations))

    def test_cancel_before_dispatch_never_starts_the_tool(self):
        with tempfile.TemporaryDirectory(prefix='sr-tool-pre-cancel-') as workspace:
            signal = threading.Event(); signal.set()
            result = ProviderToolRunner({'python':sys.executable}).run(
                ProviderToolGrant('python',workspace,'127.0.0.1',5432),
                ['-c','from pathlib import Path;Path("must-not-exist").write_text("executed")'],cancel_signal=signal)
            self.assertFalse(result['process_observation']['started'])
            self.assertTrue(result['process_observation']['cancel_requested'])
            self.assertIsNone(result['return_code'])
            self.assertFalse((Path(workspace)/'must-not-exist').exists())

    def test_cancellation_stops_owned_descendants_without_inferring_remote_rollback(self):
        import json
        import psutil
        with tempfile.TemporaryDirectory(prefix='sr-tool-cancel-') as workspace:
            signal = threading.Event()
            def progress(event):
                if event['stdout_bytes']:signal.set()
            code = ('import subprocess,sys,time,json,psutil;'
                    'p=subprocess.Popen([sys.executable,"-c","import time;time.sleep(30)"],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);'
                    'print(json.dumps({"pid":p.pid,"created":psutil.Process(p.pid).create_time()}),flush=True);time.sleep(30)')
            result = ProviderToolRunner({'python':sys.executable}).run(
                ProviderToolGrant('python',workspace,'127.0.0.1',5432,timeout_seconds=10),['-c',code],
                cancel_signal=signal,progress=progress)
            self.assertTrue(result['process_observation']['cancel_requested'])
            self.assertTrue(result['process_observation']['cleanup_confirmed'])
            self.assertFalse(result['remote_finality_inferred'])
            child = json.loads(result['stdout'])
            try:
                process = psutil.Process(child['pid'])
                if process.create_time()==child['created']:
                    self.assertIn(process.status(),{psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD})
            except psutil.NoSuchProcess:
                pass

    def test_timeout_preserves_process_observation_and_scrubs_credentials(self):
        with tempfile.TemporaryDirectory(prefix='sr-tool-timeout-') as workspace:
            runner = ProviderToolRunner({'python':sys.executable})
            with self.assertRaisesRegex(ProviderToolError,'timed out') as failure:
                runner.run(ProviderToolGrant('python',workspace,'127.0.0.1',5432,timeout_seconds=1),
                    ['-c','import time;time.sleep(30)'],secret_config=b'private-timeout-canary',
                    redact_values=('private-timeout-canary',))
            result = failure.exception.process_observation
            self.assertTrue(result['process_observation']['timed_out'])
            self.assertTrue(result['process_observation']['cleanup_confirmed'])
            self.assertFalse(result['remote_finality_inferred'])
            self.assertEqual([],list(Path(workspace).iterdir()))

    def test_progress_observer_failure_does_not_hide_native_process_result(self):
        with tempfile.TemporaryDirectory(prefix='sr-tool-progress-failure-') as workspace:
            def failure(_event):raise RuntimeError('private-progress-canary')
            result = ProviderToolRunner({'python':sys.executable}).run(
                ProviderToolGrant('python',workspace,'127.0.0.1',5432),
                ['-c','import time;time.sleep(.4);print("complete")'],progress=failure)
            self.assertEqual(0,result['return_code'])
            self.assertEqual('RuntimeError',result['process_observation']['progress_delivery_error_type'])
            self.assertNotIn('private-progress-canary',repr(result))

    def test_output_supervision_failure_stops_process_and_preserves_unknown_remote_outcome(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory(prefix='sr-tool-start-failure-') as workspace:
            with patch('pgadmin.cdeadmin.sdk.tool_process.threading.Thread.start',side_effect=RuntimeError('private-startup-canary')):
                with self.assertRaisesRegex(ProviderToolError,'output supervision') as failure:
                    ProviderToolRunner({'python':sys.executable}).run(
                        ProviderToolGrant('python',workspace,'127.0.0.1',5432),['-c','import time;time.sleep(30)'])
            result = failure.exception.process_observation
            self.assertTrue(result['process_observation']['cleanup_confirmed'])
            self.assertIsNotNone(result['return_code'])
            self.assertFalse(result['remote_finality_inferred'])
            self.assertNotIn('private-startup-canary',repr(result))

    def test_windows_environment_uses_native_paths_without_inheriting_settings_or_secrets(self):
        result = tool_environment(r'C:\Vendor tools\pg_basebackup.exe', r'D:\owned artifact', platform='win32', inherited={
            'SystemRoot':r'C:\Windows', 'PGPASSWORD':'private', 'PATH':'untrusted', 'MYSQL_HOME':'private-settings'})
        self.assertEqual(r'C:\Vendor tools;C:\Windows\System32;C:\Windows', result['PATH'])
        self.assertEqual(r'C:\Windows', result['SYSTEMROOT'])
        self.assertEqual(r'D:\owned artifact', result['USERPROFILE'])
        self.assertNotIn('PGPASSWORD', result)
        self.assertNotIn('MYSQL_HOME', result)
        self.assertNotIn('/usr/bin', result['PATH'])
        with self.assertRaisesRegex(ProviderToolError, 'SystemRoot'):
            tool_environment(r'C:\tools\pg_basebackup.exe', r'D:\owned', platform='win32', inherited={})

    def test_posix_native_tool_environment_contains_its_allowlisted_directory_and_owned_settings(self):
        result = tool_environment('/opt/vendor tools/pg_basebackup', '/owned artifact', platform='darwin', inherited={
            'PGPASSWORD':'private', 'LD_PRELOAD':'private', 'HOME':'/other-user'})
        self.assertTrue(result['PATH'].startswith('/opt/vendor tools' + os.pathsep))
        self.assertEqual('/owned artifact', result['HOME'])
        self.assertEqual('C', result['LC_ALL'])
        self.assertNotIn('PGPASSWORD', result)
        self.assertNotIn('LD_PRELOAD', result)

    def test_secret_file_is_private_redacted_and_removed(self):
        with tempfile.TemporaryDirectory(
            prefix='cdeadmin-provider-tool-test-'
        ) as workspace:
            secret = 'credential-canary-never-export'
            runner = ProviderToolRunner({'python': sys.executable})
            grant = ProviderToolGrant(
                executable_id='python', workspace=workspace,
                endpoint_host='127.0.0.1', endpoint_port=27017,
            )
            result = runner.run(
                grant, [
                    '-c',
                    'import pathlib,sys;print('
                    'pathlib.Path(sys.argv[1]).read_text(),end="")',
                ], secret_config=secret.encode('utf-8'),
                secret_argument='{path}', secret_suffix='.secret',
                redact_values=(secret,),
            )
            self.assertEqual(0, result['return_code'])
            self.assertEqual('[redacted]', result['stdout'])
            self.assertNotIn(secret, repr(result))
            self.assertEqual([], list(Path(workspace).iterdir()))
            self.assertTrue(result['local_process_observation_only'])
            self.assertFalse(result['remote_finality_inferred'])

    def test_grants_and_arguments_fail_closed(self):
        with self.assertRaisesRegex(ProviderToolError, 'over-broad'):
            ProviderToolGrant(
                executable_id='python', workspace=Path(tempfile.gettempdir()).anchor,
                endpoint_host='127.0.0.1', endpoint_port=27017,
            )
        with tempfile.TemporaryDirectory(
            prefix='cdeadmin-provider-tool-test-'
        ) as workspace:
            grant = ProviderToolGrant(
                executable_id='missing', workspace=workspace,
                endpoint_host='127.0.0.1', endpoint_port=27017,
            )
            runner = ProviderToolRunner({'missing': '/absent/cdeadmin-tool'})
            with self.assertRaisesRegex(ProviderToolError, 'unavailable'):
                runner.run(grant, [])

    def test_secret_environment_requires_an_explicit_name_grant(self):
        with tempfile.TemporaryDirectory(
            prefix='cdeadmin-provider-tool-test-'
        ) as workspace:
            runner = ProviderToolRunner({'python': sys.executable})
            grant = ProviderToolGrant(
                executable_id='python', workspace=workspace,
                endpoint_host='127.0.0.1', endpoint_port=7687,
                secret_environment_names=('NEO4J_PASSWORD',),
            )
            secret = 'environment-canary-never-export'
            result = runner.run(
                grant, [
                    '-c', 'import os;print(os.environ["NEO4J_PASSWORD"])',
                ], secret_environment={'NEO4J_PASSWORD': secret},
                redact_values=(secret,),
            )
            self.assertEqual('[redacted]' + os.linesep, result['stdout'])
            with self.assertRaisesRegex(ProviderToolError, 'not granted'):
                runner.run(
                    grant, ['-c', 'pass'],
                    secret_environment={'UNGRANTED_SECRET': secret},
                )

    def test_streamed_input_and_leading_secret_argument_are_constrained(self):
        with tempfile.TemporaryDirectory(
            prefix='cdeadmin-provider-tool-stream-test-'
        ) as workspace:
            root = Path(workspace)
            input_path = root / 'restore.sql'
            input_path.write_bytes(b'SELECT 1;\n')
            runner = ProviderToolRunner({'python': sys.executable})
            grant = ProviderToolGrant(
                executable_id='python', workspace=workspace,
                endpoint_host='127.0.0.1', endpoint_port=3306,
            )
            result = runner.run(
                grant, [
                    '-c',
                    'import pathlib,sys;print(pathlib.Path('
                    'sys.argv[1]).read_text(),end="");'
                    'print(sys.stdin.read(),end="")',
                ], input_path=input_path, secret_config=b'private-config',
                secret_argument='{path}', secret_suffix='.cnf',
                secret_argument_position=2,
                redact_values=('private-config',),
            )
            self.assertEqual('[redacted]SELECT 1;' + os.linesep, result['stdout'])
            self.assertEqual([input_path], list(root.iterdir()))
            with tempfile.NamedTemporaryFile() as outside:
                with self.assertRaisesRegex(ProviderToolError, 'escapes'):
                    runner.run(grant, ['-c', 'pass'], input_path=outside.name)
            with self.assertRaisesRegex(ProviderToolError, 'conflicts'):
                runner.run(
                    grant, ['-c', 'pass'], input_bytes=b'x',
                    input_path=input_path,
                )

    def test_split_secret_option_is_inserted_without_shell_parsing(self):
        with tempfile.TemporaryDirectory(
            prefix='cdeadmin-provider-tool-split-secret-'
        ) as workspace:
            runner = ProviderToolRunner({'python': sys.executable})
            grant = ProviderToolGrant(
                executable_id='python', workspace=workspace,
                endpoint_host='127.0.0.1', endpoint_port=7199,
            )
            result = runner.run(
                grant, [
                    '-c',
                    'import pathlib,sys;print(sys.argv[1]);print('
                    'pathlib.Path(sys.argv[2]).read_text(),end="")',
                ],
                secret_config=b'private-password-file',
                secret_argument=('-pwf', '{path}'),
                secret_argument_position=2,
                redact_values=('private-password-file',),
            )
            self.assertEqual(0, result['return_code'])
            self.assertEqual('-pwf' + os.linesep + '[redacted]', result['stdout'])
            self.assertEqual([], list(Path(workspace).iterdir()))


if __name__ == '__main__':
    unittest.main()


def test_unbounded_native_process_requires_explicit_authority_and_remains_cancellable(tmp_path):
    import threading
    import sys
    from pgadmin.cdeadmin.sdk.tooling import ProviderToolError,ProviderToolGrant,ProviderToolRunner
    with __import__('pytest').raises(ProviderToolError):
        ProviderToolGrant('python',str(tmp_path),'localhost',5432,timeout_seconds=None)
    signal=threading.Event()
    runner=ProviderToolRunner({'python':sys.executable})
    grant=ProviderToolGrant('python',str(tmp_path),'localhost',5432,timeout_seconds=None,allow_unbounded_runtime=True)
    result=runner.run(grant,['-c','import time;time.sleep(30)'],cancel_signal=signal,progress=lambda _event:signal.set())
    assert result['process_observation']['cancel_requested'] and not result['process_observation']['timed_out']
    assert result['process_observation']['cleanup_confirmed']
