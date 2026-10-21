"""Unconfirmed C escaping borrows only a verified, retained native C peer."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from mysql.connector.constants import ServerFlag

from test_mysql_session_variables import setup
from pgadmin.cdeadmin.providers.mysql_family.mysql_session_variables import ObserverUnavailable
from pgadmin.cdeadmin.providers.mysql_family.mysql_values import bound_source, MySQLParameterAdmissionError


def native_peer(mode):
    source, observer, _connect, peer, query = setup()
    query.fetchall.return_value = [(key, mode if key == 'sql_mode' else value) for key, value in query.fetchall.return_value]
    peer._cmysql.st_server_status.return_value = ServerFlag.STATUS_NO_BACKSLASH_ESCAPES if 'NO_BACKSLASH_ESCAPES' in mode else 0
    peer.prepare_for_mysql.return_value = [b"'native opaque literal'"]
    return source, observer, peer, query


@pytest.mark.parametrize('mode', ['', 'ANSI_QUOTES', 'NO_BACKSLASH_ESCAPES', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'])
def test_same_driver_converts_on_the_private_peer_with_observed_charset_and_mode(mode):
    source, observer, peer, _query = native_peer(mode)
    values = [b'opaque\x00\xff']
    assert observer.native_literals(values, mode) == [b"'native opaque literal'"]
    peer.prepare_for_mysql.assert_called_once_with(values)
    peer.set_charset_collation.assert_called_once_with('latin1')
    assert peer.sql_mode == mode
    source.cursor.assert_not_called(); observer.close()


@pytest.mark.parametrize('fault', ['mode_changed', 'private_ack', 'conversion'])
def test_private_context_or_conversion_failure_never_invokes_original_or_reconnects_in_worker(fault):
    source, observer, peer, _query = native_peer('NO_BACKSLASH_ESCAPES')
    if fault == 'private_ack': peer._cmysql.st_server_status.return_value = 0
    if fault == 'conversion': peer.prepare_for_mysql.side_effect = OSError('owned private native failure')
    with pytest.raises((ObserverUnavailable, OSError)):
        observer.native_literals([b'private'], '' if fault == 'mode_changed' else 'NO_BACKSLASH_ESCAPES')
    source.cursor.assert_not_called(); peer.close.assert_called_once()
    assert observer.needs_connection_refresh and observer.connection is None


def test_bound_source_uses_peer_literals_when_original_C_status_is_unconfirmed(monkeypatch):
    source, observer, peer, _query = native_peer('NO_BACKSLASH_ESCAPES')
    source._cmysql = SimpleNamespace(st_server_status=lambda: 0)
    source.prepare_for_mysql = Mock(side_effect=AssertionError('Unconfirmed converter must not run'))
    source.charset = 'latin1'; source.python_charset = 'latin1'
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.mysql_values.observed_language', lambda _source: ('9.7.0', 'NO_BACKSLASH_ESCAPES'))
    assert bound_source(source, Mock(), 'SELECT %s', ['value']) == b"SELECT 'native opaque literal'"
    source.prepare_for_mysql.assert_not_called(); source.cursor.assert_not_called()
    peer.prepare_for_mysql.assert_called_once(); observer.close()


def test_bound_source_retains_local_refusal_if_private_C_context_cannot_be_confirmed(monkeypatch):
    source, observer, peer, _query = native_peer('NO_BACKSLASH_ESCAPES')
    source._cmysql = SimpleNamespace(st_server_status=lambda: 0)
    source.prepare_for_mysql = Mock(side_effect=AssertionError('Original converter must not run'))
    source.charset = 'latin1'; source.python_charset = 'latin1'
    peer._cmysql.st_server_status.return_value = 0
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mysql_family.mysql_values.observed_language', lambda _source: ('9.7.0', 'NO_BACKSLASH_ESCAPES'))
    with pytest.raises(MySQLParameterAdmissionError) as error: bound_source(source, Mock(), 'SELECT %s', ['value'])
    assert error.value.original_diagnostics_preserved and not error.value.original_session_identity_unconfirmed
    source.prepare_for_mysql.assert_not_called(); source.cursor.assert_not_called()
