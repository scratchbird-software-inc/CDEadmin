"""Native context admission and unresolved transaction cleanup boundaries."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from psycopg.pq import TransactionStatus

from pgadmin.cdeadmin.providers.postgresql import editor_context


@pytest.mark.parametrize('status', [TransactionStatus.INERROR, TransactionStatus.ACTIVE, TransactionStatus.UNKNOWN])
def test_unavailable_transaction_never_runs_queries_or_repairs_user_state(monkeypatch, status):
    native = Mock()
    native.info = SimpleNamespace(transaction_status=status, server_version=180003,
        user='login', parameter_status=lambda _: 'UTF8')
    state = SimpleNamespace(connection=SimpleNamespace(conn=native), uncertain=False)
    cursor = Mock(side_effect=AssertionError('No native query allowed'))
    monkeypatch.setattr(editor_context, 'Cursor', cursor)
    result = editor_context.observe(state)
    assert not result['observation']['available']
    assert result['effective_principal'] is None and result['standard_conforming_strings'] is None
    assert state.uncertain is (status == TransactionStatus.UNKNOWN)
    cursor.assert_not_called()
    native.rollback.assert_not_called()


def test_failed_cleanup_quarantines_session_without_exposing_native_diagnostics(monkeypatch):
    native = Mock()
    native.info = SimpleNamespace(transaction_status=TransactionStatus.IDLE,
        server_version=180003, user='login', parameter_status=lambda _: 'UTF8')
    native.rollback.side_effect = OSError('private native diagnostic')
    state = SimpleNamespace(connection=SimpleNamespace(conn=native), uncertain=False)
    cursor = Mock()
    cursor.fetchone.return_value = ('login', 'login', 'login', 'none', 'public', ['pg_catalog','public'], 'on', 'safe_encoding')
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(editor_context, 'Cursor', lambda *_args, **_kw: cursor)
    with pytest.raises(RuntimeError, match='cleanup is unconfirmed') as error:
        editor_context.observe(state)
    assert 'private' not in str(error.value) and state.uncertain
