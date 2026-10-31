"""DDN runners start the real Node binary in a minimal environment.

Live, 2026-10-31: with Node behind an asdf shim, every runner failed with
"$HOME is not defined" (the runner environment carries no HOME), and the
callers reported it as an invalid document: about 800 tests failed.
"""
import os
import shutil
import stat
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))

from pgadmin.cdeadmin.workspace import ddn_source  # noqa: E402

REAL_NODE = shutil.which('node')
pytestmark = pytest.mark.skipif(REAL_NODE is None, reason='node is required')


@pytest.fixture()
def shim(tmp_path):
    # Like a version-manager shim: refuses to run without HOME.
    path = tmp_path / 'node-shim'
    path.write_text('#!/bin/sh\n'
                    'if [ -z "$HOME" ]; then\n'
                    "  echo '$HOME is not defined' >&2; exit 1\n"
                    'fi\n'
                    f'exec "{REAL_NODE}" "$@"\n')
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    ddn_source._NODE_PATHS.pop(str(path), None)
    return str(path)


def test_a_shim_resolves_to_the_binary_it_runs(shim):
    resolved = ddn_source.node_executable(shim)
    assert resolved != shim and os.path.isabs(resolved)
    assert os.access(resolved, os.X_OK)
    # Cached: the shim is asked once.
    assert ddn_source.node_executable(shim) is resolved


def test_the_runner_environment_stays_minimal(monkeypatch):
    monkeypatch.setenv('HOME', '/home/someone')
    monkeypatch.setenv('AWS_SECRET_ACCESS_KEY', 'x')
    assert set(ddn_source.runner_environment()) <= {
        'PATH', 'SYSTEMROOT', 'TMPDIR'}


def test_the_resolved_binary_runs_where_the_shim_cannot(shim):
    import subprocess
    # The shim itself fails in the runner environment...
    failed = subprocess.run([shim, '-e', '1'],
                            env=ddn_source.runner_environment(),
                            capture_output=True, text=True)
    assert failed.returncode == 1 and 'HOME' in failed.stderr
    # ...the resolved binary runs there.
    ran = subprocess.run([ddn_source.node_executable(shim), '-e',
                          'process.stdout.write("ok")'],
                         env=ddn_source.runner_environment(),
                         capture_output=True, text=True)
    assert ran.stdout == 'ok'


def test_an_unusable_node_is_returned_unchanged(tmp_path):
    missing = str(tmp_path / 'no-node')
    assert ddn_source.node_executable(missing) == missing
