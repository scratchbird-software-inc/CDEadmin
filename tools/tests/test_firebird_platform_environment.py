"""Portable workflow children can import the app without shell path setup."""
import os
import subprocess
import sys

import pytest

from tools.development import firebird_platform as runner


@pytest.mark.parametrize('inherited', [None, '/owned/adapter-module-path'])
def test_fresh_workflow_process_has_application_import_boundary(
        tmp_path, monkeypatch, inherited):
    if inherited is None:
        monkeypatch.delenv('PYTHONPATH', raising=False)
    else:
        monkeypatch.setenv('PYTHONPATH', inherited)
    monkeypatch.setattr(
        runner, 'binary_identity', lambda _: {'format': 'test'})
    observations = []

    def probe(args, *, env, log, timeout):
        # Exercise real imports in a fresh interpreter with exactly the
        # runner's child environment, without opening a native database.
        child = subprocess.run([
            sys.executable, '-c',
            'import config; '
            'import tools.cdeadmin_firebird_workflow_platform_gate; '
            'print(config.APP_NAME)'],
            cwd=runner.ROOT, env=env, check=True, capture_output=True,
            text=True, timeout=30)
        observations.append((args, env, child.stdout))

    monkeypatch.setattr(runner, 'command', probe)
    result = runner.run_mode(
        'network', {'attachment_mode': 'network'}, tmp_path,
        tmp_path / 'runtime', tmp_path, None, workflows=True, codecs=True)
    assert result['complete'] and len(observations) == 2
    assert observations[1][0][2] == (
        'tools.cdeadmin_firebird_workflow_platform_gate')
    for _, env, output in observations:
        paths = env['PYTHONPATH'].split(os.pathsep)
        assert paths[:2] == [str(runner.ROOT / 'web'), str(runner.ROOT)]
        assert output.strip() == 'CDEadmin'
        if inherited is not None:
            assert paths[-1] == inherited
