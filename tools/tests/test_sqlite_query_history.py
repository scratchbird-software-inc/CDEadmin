"""SQLite SQL history is file-scoped and omits attachment paths."""

from types import SimpleNamespace
from unittest.mock import Mock

import config  # noqa: F401
import pytest
from sqlalchemy import create_engine

from pgadmin.model import QueryHistoryModel
from pgadmin.cdeadmin.workspace.query_history import (
    HistoryScope, QueryHistory)
from pgadmin.cdeadmin.workspace.service import (
    ProviderWorkspaceError, ProviderWorkspaceService)


SCOPE = HistoryScope(1, 2, 'file-a', 'sqlite-sql', 'sqlite')


def test_native_history_is_file_scoped_and_attach_source_is_omitted(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'history.db'))
    QueryHistoryModel.__table__.create(engine)
    history = QueryHistory(engine, QueryHistoryModel)
    try:
        history.configure(SCOPE, {'capture_source': True,
                                  'retention_days': 2, 'max_records': 3})
        history.record(SCOPE, 'SELECT 42')
        history.record(SCOPE, "ATTACH '/private/finance.sqlite' AS finance")
        current = history.read(SCOPE)
        assert current['scope']['engine_id'] == 'sqlite'
        assert current['entries'][0]['source'] is None
        assert current['entries'][1]['source'] == 'SELECT 42'
        assert not history.read(HistoryScope(1, 2, 'file-b',
                                             'sqlite-sql', 'sqlite'))['entries']
    finally:
        engine.dispose()


def test_history_requires_exact_registered_file():
    service = object.__new__(ProviderWorkspaceService)
    service._principal_id = Mock(return_value=1)
    service.endpoint_service = Mock()
    service.endpoint_service.workspace.return_value = (
        SimpleNamespace(profile_id='sqlite-native'),
        {'route': {'database': '/owned/file.sqlite'}}, None)
    service.endpoint_service.database_catalog.return_value = {
        'targets': [{'target_id': SCOPE.target,
                     'database': '/owned/file.sqlite'}]}
    server = SimpleNamespace(id=2, endpoint_profile=SimpleNamespace(
        profile_id='sqlite-native'))
    assert service._history_context(server, SCOPE.target, None) == SCOPE
    for target, dialect in ((None, None), ('other', None),
                            (SCOPE.target, 3)):
        with pytest.raises(ProviderWorkspaceError):
            service._history_context(server, target, dialect)
