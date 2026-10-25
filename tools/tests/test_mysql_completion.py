"""Private completion preserves caller diagnostics and identifies partial scope."""
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.mysql_family.mysql_completion import complete
from pgadmin.cdeadmin.providers import native_editor
from pgadmin.cdeadmin.sdk.relational import RelationalClientError
from test_mysql_native_validation import owned


def catalog(mode='ANSI_QUOTES,NO_BACKSLASH_ESCAPES'):
    return {'context': {'version': '9.7.0', 'sql_mode': mode, 'active_role': '`default_role`@`%`',
        'character_set_client': 'utf8mb4', 'default_schema': 'odd`雪', 'context_revision': 'old'},
        'resources': [{'resource_kind': 'column', 'display_path': ['odd`雪','t','id']}],
        'observations': [{'section': 'columns', 'available': True}], 'visible_resource_count': 1,
        'complete': True, 'truncated': False}


def test_completion_reads_only_private_native_catalog_and_keeps_source_language_and_unconfirmed_overlays(monkeypatch):
    source, observer, _connect, peer, _query, client = owned()
    metadata = Mock(return_value=catalog());monkeypatch.setattr(native_editor,'metadata',metadata)
    try:
        result=complete(client,source)
        metadata.assert_called_once_with(peer,'mysql');source.cursor.assert_not_called()
        assert result['original_diagnostics_preserved'] and result['original_session_commands_sent']==0
        assert result['context']['character_set_client']=='latin1' and result['context']['active_role'] is None
        assert result['context']['metadata_peer_active_role']=='`default_role`@`%`'
        assert not result['complete'] and not result['original_session_catalog_binding_validated']
        assert result['observations'][-1]['available'] is False and result['context']['context_revision']!='old'
        assert not client._uncertain_sessions
    finally:observer.close()


@pytest.mark.parametrize('failure',['permission','transport','mode','identity'])
def test_private_completion_failure_never_queries_or_reconnects_source(monkeypatch,failure):
    source, observer, connect, peer, query, client=owned()
    metadata=Mock(return_value=catalog('' if failure=='mode' else 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'))
    monkeypatch.setattr(native_editor,'metadata',metadata)
    if failure=='identity':source.connection_id=13
    elif failure=='permission':
        from mysql.connector.errors import ProgrammingError
        query.execute.side_effect=ProgrammingError('source-bearing private denial',errno=1142)
    elif failure=='transport':metadata.side_effect=OSError('source-bearing private loss')
    with pytest.raises(RelationalClientError) as error:complete(client,source)
    assert 'source-bearing' not in str(error.value)
    source.cursor.assert_not_called()
    if failure=='identity':assert id(source) in client._uncertain_sessions and connect.call_count==0
    else:
        assert not client._uncertain_sessions and observer.needs_connection_refresh
        peer.close.assert_called_once();assert connect.call_count==1


@pytest.mark.parametrize('reason',['native-observation-denied','performance-schema-disabled',None])
def test_unadmitted_profile_never_substitutes_original_metadata_or_parser_queries(monkeypatch,reason):
    from pgadmin.cdeadmin.providers.mysql_family.mysql_native_validation import validate
    source=Mock();source._cdeadmin_session_variable_observer=None
    source._cdeadmin_session_variable_observer_status={'admitted':False,'reason':reason}
    metadata=Mock(return_value=catalog());monkeypatch.setattr(native_editor,'metadata',metadata)
    parser=Mock();monkeypatch.setattr(native_editor,'validate_mysql',parser)
    for operation in (lambda:complete(Mock(),source),lambda:validate(Mock(),source,'SELECT secret')):
        with pytest.raises(RelationalClientError,match='No original-session metadata command') as failure:operation()
        assert failure.value.original_session_commands_sent==0 and failure.value.original_diagnostics_preserved
        assert 'secret' not in str(failure.value)
    metadata.assert_not_called();parser.assert_not_called();source.cursor.assert_not_called()
