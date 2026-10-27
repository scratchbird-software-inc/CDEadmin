"""Fixture setup/teardown cannot target application source or an unrelated PID."""
import json
import os
from unittest.mock import Mock

import pytest

from tools import cdeadmin_mysql_service_fixture as fixture


def test_guest_setup_refuses_source_repository_before_download_or_process(monkeypatch):
    download = Mock(); monkeypatch.setattr(fixture, 'download', download)
    with pytest.raises(ValueError, match='outside the source'): fixture.prepare(fixture.ROOT / 'forbidden-fixture')
    download.assert_not_called()


def test_guest_stop_refuses_unowned_record_before_any_control_socket(tmp_path, monkeypatch):
    (tmp_path / 'connection.json').write_text(json.dumps({'owned_fixture': False}))
    control = Mock(); monkeypatch.setattr(fixture.socket, 'socket', control)
    with pytest.raises(ValueError, match='exact owned directory'): fixture.stop(tmp_path)
    control.assert_not_called()


@pytest.mark.skipif(not os.path.exists('/proc/self/cmdline'), reason='Linux fixture process ownership boundary')
def test_guest_stop_refuses_current_unrelated_process_without_sending_qmp(tmp_path, monkeypatch):
    (tmp_path / 'connection.json').write_text(json.dumps({'owned_fixture': True,
        'private_key': str(tmp_path / 'ssh-key'), 'pid': os.getpid()}))
    control = Mock(); monkeypatch.setattr(fixture.socket, 'socket', control)
    with pytest.raises(ValueError, match='no longer belongs'): fixture.stop(tmp_path)
    control.assert_not_called()
