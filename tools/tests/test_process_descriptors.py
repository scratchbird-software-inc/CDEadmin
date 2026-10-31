"""Process descriptors also work where the interpreter does not expose them.

Live, 2026-10-31: the standalone CPython 3.14 that uv installs has neither
os.pidfd_open nor signal.pidfd_send_signal, and every MySQL cancellation and
recovery stop raised AttributeError. The kernel calls are used instead.
"""
import os
import signal
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))

from pgadmin.cdeadmin.operations import fileio  # noqa: E402

pytestmark = pytest.mark.skipif(not sys.platform.startswith('linux'),
                                reason='process descriptors are Linux only')


@pytest.fixture(params=['interpreter', 'syscall'])
def path(request, monkeypatch):
    if request.param == 'syscall':
        monkeypatch.delattr(os, 'pidfd_open', raising=False)
        monkeypatch.delattr(signal, 'pidfd_send_signal', raising=False)
    elif not hasattr(os, 'pidfd_open'):
        pytest.skip('this interpreter has no os.pidfd_open')
    return request.param


def test_a_descriptor_signals_its_original_process(path):
    assert fileio.pidfd_available()
    child = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(60)'])
    descriptor = fileio.pidfd_open(child.pid)
    try:
        fileio.pidfd_send_signal(descriptor, signal.SIGKILL)
        assert child.wait(timeout=10) == -signal.SIGKILL
        # Reaped: the descriptor still names that process, never a PID reuse.
        with pytest.raises(ProcessLookupError):
            fileio.pidfd_send_signal(descriptor, signal.SIGKILL)
    finally:
        os.close(descriptor)
        if child.poll() is None:
            child.kill()


def test_a_missing_process_is_a_lookup_error(path):
    child = subprocess.Popen([sys.executable, '-c', 'pass'])
    child.wait(timeout=10)
    with pytest.raises(ProcessLookupError):
        fileio.pidfd_open(child.pid)


def test_shipped_workers_reach_the_helpers_without_the_package():
    # Remote hosts run these sources standalone, beside the shipped fileio.
    import types
    source = ROOT / 'web/pgadmin/cdeadmin/providers/mysql_family'
    shipped = types.ModuleType('_cdeadmin_native_fileio')
    exec((ROOT / 'web/pgadmin/cdeadmin/operations/fileio.py').read_text(),
         shipped.__dict__)
    saved = sys.modules.get('_cdeadmin_native_fileio')
    sys.modules['_cdeadmin_native_fileio'] = shipped
    try:
        module = types.ModuleType('_cdeadmin_native_initialization')
        exec((source / 'mysql_host_initialization.py').read_text(),
             module.__dict__)
        assert module.pidfd_open is shipped.pidfd_open
        assert module.pidfd_send_signal is shipped.pidfd_send_signal
    finally:
        if saved is None:
            sys.modules.pop('_cdeadmin_native_fileio')
        else:
            sys.modules['_cdeadmin_native_fileio'] = saved
