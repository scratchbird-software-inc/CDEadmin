"""Admission and unresolved-cleanup boundaries for retained-session capture."""
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from psycopg.pq import TransactionStatus
from pgadmin.cdeadmin.providers.postgresql import session_catalog
from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan


@pytest.mark.parametrize('status', [TransactionStatus.ACTIVE, TransactionStatus.INERROR, TransactionStatus.UNKNOWN])
def test_unhealthy_session_is_not_repaired(status):
    native = Mock()
    native.info.transaction_status = status
    state = SimpleNamespace(connection=SimpleNamespace(conn=native), uncertain=False)
    with pytest.raises(ValueError, match='resolve the existing transaction'):
        session_catalog.observe(state)
    native.rollback.assert_not_called()
    assert not state.uncertain


def test_unconfirmed_owned_cleanup_quarantines_session(monkeypatch):
    native = Mock()
    native.info.transaction_status = TransactionStatus.IDLE
    native.rollback.side_effect = OSError('private native detail')
    state = SimpleNamespace(connection=SimpleNamespace(conn=native), database_id=None, uncertain=False)
    cursor = Mock()
    cursor.fetchone.return_value = (42,)
    cursor.__enter__ = Mock(return_value=cursor)
    cursor.__exit__ = Mock(return_value=False)
    monkeypatch.setattr(session_catalog, 'Cursor', lambda *_args, **_kw: cursor)
    monkeypatch.setattr(session_catalog, 'capture', lambda *_args, **_kw: {'resources':[]})
    with pytest.raises(RuntimeError, match='cleanup is unconfirmed') as error:
        session_catalog.observe(state)
    assert 'private' not in str(error.value) and state.uncertain


@pytest.mark.parametrize('marker', ['provenance', 'native', 'temporary'])
def test_retained_observations_cannot_become_independent_migrations(marker):
    model = {'provenance': {'mapping':'scratchrobin.postgresql.catalog@1'}, 'rows':{}}
    if marker == 'provenance':model['provenance']['observation_scope'] = 'retained-session'
    else:model['rows']['temp'] = {'native':{'observation_scope':'retained-session'} if marker == 'native' else {'catalog_row':{'relpersistence':'t'}}}
    with pytest.raises(ValueError, match='Retained-session'):
        build_plan(model, model, model)
