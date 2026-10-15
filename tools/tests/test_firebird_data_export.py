"""One export-owned snapshot, complete pages and cleanup on every outcome."""
import json
from unittest.mock import Mock
import pytest
from tools.cdeadmin_firebird_admin_mapping_gate import _create_client  # noqa: F401
from pgadmin.cdeadmin.workspace import firebird_data_export as export
from tools.tests.test_firebird_test_data_session import service


def model():
    return {'provenance': {'database_target_id': 'target', 'generation': 'g'},
            'rows': {'table:T': {'resource_id': 'table:T', 'name': 'T', 'path': ['T'],
                'kind': 'table', 'system': 'false', 'native': {
                    'relation_type': 0, 'columns': [{'name': 'A', 'position': 0}]}}}}


def owner(pages):
    result = Mock()
    result.open_session.return_value = {'session_id': 'owned-read'}
    result.read_visual_admin_rows.side_effect = pages
    return result


def page(value, continuation=None):
    return {'columns': [{'name': 'A', 'input_kind': 'integer'}],
            'rows': [{'values': {'A': value}, 'identity_token': 'DO-NOT-EXPORT'}],
            'continuation': continuation, 'complete': continuation is None}


def test_all_pages_one_snapshot_and_exact_values_without_session_handles():
    value = owner([page('170141183460469231731687303715884105727', 'next'), page(None)])
    result = export.capture(value, 'server', model(), contents='both')
    saved = json.loads(result['download_text'])
    assert result['row_count'] == 2 and result['table_count'] == 1
    assert saved['tables'][0]['rows'] == [{'A': '170141183460469231731687303715884105727'}, {'A': None}]
    assert 'DO-NOT-EXPORT' not in result['download_text']
    assert 'metadata' in saved
    value.open_session.assert_called_once_with('server', 'firebird-sql', 'target', session_purpose='firebird-data-export')
    assert all(call.args[1]['session_id'] == 'owned-read' for call in value.read_visual_admin_rows.call_args_list)
    value.transaction_action.assert_called_once_with('server', 'owned-read', 'rollback', 'target')
    value.close_session.assert_called_once_with('server', 'owned-read', 'target')


def test_limits_never_publish_truncated_output_and_cancel_retained_cursor(monkeypatch):
    value = owner([page('too big', 'next')]); monkeypatch.setattr(export, 'MAX_ROWS', 0)
    with pytest.raises(ValueError, match='limit'): export.capture(value, 'server', model())
    value.cancel_visual_admin_rows.assert_called_once()
    assert value.cancel_visual_admin_rows.call_args.args[1]['continuation'] == 'next'
    value.transaction_action.assert_called_once()
    value.close_session.assert_called_once()


def test_read_failure_or_cleanup_failure_cannot_report_success():
    value = owner([RuntimeError('read failed')])
    with pytest.raises(RuntimeError, match='read failed'): export.capture(value, 'server', model())
    value.transaction_action.assert_called_once(); value.close_session.assert_called_once()
    value = owner([page(1)]); value.transaction_action.side_effect = RuntimeError('rollback unconfirmed')
    with pytest.raises(RuntimeError, match='rollback unconfirmed'): export.capture(value, 'server', model())
    value.close_session.assert_called_once()


def test_external_tables_and_catalog_drift_refused():
    document = model(); document['rows']['table:T']['native']['relation_type'] = 2
    value = owner([])
    with pytest.raises(ValueError, match='external'): export.capture(value, 'server', document)
    value.open_session.assert_not_called()
    value = owner([{'columns': [{'name': 'CHANGED'}], 'rows': [], 'continuation': None}])
    with pytest.raises(ValueError, match='shape changed'): export.capture(value, 'server', model())
    value.close_session.assert_called_once()


def test_export_session_cannot_inherit_user_autocommit_or_write_mode():
    value, endpoint = service()
    endpoint['route']['transaction_access'] = 'WRITE'
    value.open_session('server', 'firebird-sql', 'target', session_purpose='firebird-data-export')
    route = value.studio_service.open_session.call_args.args[1]['route']
    assert route['transaction_access'] == 'READ' and route['transaction_auto_commit'] is False
    assert route['transaction_isolation'] == 'SNAPSHOT'
    assert endpoint['route']['transaction_access'] == 'WRITE'


@pytest.mark.parametrize('metadata_at', ['table', 'page'])
def test_empty_table_metadata_limit_stops_before_reading_more_tables(monkeypatch, metadata_at):
    document = model()
    document['rows']['table:U'] = {**document['rows']['table:T'], 'resource_id': 'table:U', 'name': 'U'}
    empty = {'columns': [{'name': 'A', 'input_kind': 'integer'}], 'rows': [], 'complete': True}
    if metadata_at == 'table':
        document['rows']['table:T']['native']['columns'][0]['type_sql'] = 'X' * 4096
    else:
        empty['columns'][0]['type_sql'] = 'X' * 4096
    value = owner([empty, empty])
    monkeypatch.setattr(export, 'MAX_BYTES', 2048)
    with pytest.raises(ValueError, match='8 MiB limit'):
        export.capture(value, 'server', document)
    assert value.read_visual_admin_rows.call_count == (0 if metadata_at == 'table' else 1)
    value.transaction_action.assert_called_once()
    value.close_session.assert_called_once()


def test_slow_final_page_cannot_publish_after_the_capture_deadline(monkeypatch):
    clock = [0]
    monkeypatch.setattr(export.time, 'monotonic', lambda: clock[0])
    value = owner([])
    def finish_page(*_):
        clock[0] = export.MAX_SECONDS + 1
        return page(42)
    value.read_visual_admin_rows.side_effect = finish_page
    with pytest.raises(ValueError, match='time limit'):
        export.capture(value, 'server', model())
    value.read_visual_admin_rows.assert_called_once()
    value.transaction_action.assert_called_once()
    value.close_session.assert_called_once()
