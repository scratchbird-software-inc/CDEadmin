from copy import deepcopy
import json
from unittest.mock import Mock
import pytest

from pgadmin.cdeadmin.workspace.mariadb_data_import import (MariaDBDataApplications, bound, plan_digest)
from pgadmin.cdeadmin.providers.mariadb_data_application import apply_import
from pgadmin.cdeadmin.workspace.firebird_schema_plan import digest


def plan():
    result = {'format': 'scratchrobin.mariadb.data-import-plan@1', 'ready_for_review': True, 'row_count': 1,
        'rows': [['18446744073709551615']], 'columns': ['id'], 'database': 'db', 'table': 't`é',
        'server_uid': 'uuid', 'storage_engine': 'InnoDB', 'catalog_sql_mode': '',
        'sql_mode': 'NO_AUTO_VALUE_ON_ZERO', 'native_definition_sha256': digest('native ddl'),
        'native_columns': [{'column_name': 'id', 'column_type': 'bigint unsigned', 'is_nullable': 'NO',
                            'extra': '', 'generation_expression': '', 'character_set_name': None, 'collation_name': None, 'srs_id': None}]}
    result['execution_sha256'] = plan_digest(result)
    return result


def test_typed_binary_and_native_charset_checks_preserve_exact_bytes():
    column = {'column_type': 'varbinary(10)'}
    assert bound({'encoding': 'base64', 'data': 'AP8=', 'byte_length': 2}, column) == ('%s', [b'\x00\xff'])
    with pytest.raises(Exception):
        bound({'encoding': 'base64', 'data': 'AP8=', 'byte_length': 1}, column)
    with pytest.raises(ValueError):
        bound({'encoding': 'base64', 'data': 'AP8=', 'native_charset': 'utf8mb4);DROP'}, {'column_type': 'text', 'character_set_name': 'utf8mb4'})


def test_vector_binary_binding_preserves_float32_bits_and_refuses_nonfinite():
    import base64
    import struct
    raw = struct.pack('<fff', -0.0, 0.1, 3)
    transport = lambda value: {'encoding': 'base64', 'data': base64.b64encode(value).decode(), 'byte_length': len(value)}
    assert bound(transport(raw), {'column_type': 'vector(3)'}) == ('CAST(%s AS BINARY)', [raw])
    with pytest.raises(ValueError):
        bound(transport(raw), {'column_type': 'vector(2)'})
    with pytest.raises(ValueError):
        bound(transport(struct.pack('<f', float('nan'))), {'column_type': 'vector(1)'})


def test_data_review_is_owner_bound_hides_values_and_repeated_unknown_never_replays(tmp_path):
    applications = MariaDBDataApplications(tmp_path / 'data.json')
    receipt = applications.review(plan(), 1, 'endpoint-db')
    assert '18446744073709551615' not in json.dumps(receipt)
    request = {'review_id': receipt['review_id'], 'review_digest': receipt['review_digest'], 'confirmed': True}
    callback = Mock(return_value={'state': 'unknown_outcome'})
    assert applications.apply(request, 1, 'endpoint-db', callback)['state'] == 'unknown_outcome'
    restarted = MariaDBDataApplications(tmp_path / 'data.json')
    assert restarted.apply(request, 1, 'endpoint-db', callback)['state'] == 'unknown_outcome'
    callback.assert_called_once()
    assert '18446744073709551615' not in (tmp_path / 'data.json').read_text()
    with pytest.raises(ValueError):
        restarted.get(receipt['review_id'], 2, 'endpoint-db')
    changed = deepcopy(plan()); changed['rows'][0][0] = 'different'
    with pytest.raises(ValueError):
        applications.review(changed, 1, 'endpoint-db')


def test_lost_native_commit_reply_keeps_unknown_even_if_rollback_returns(monkeypatch):
    selected = plan()
    cursor = Mock(rowcount=1)
    cursor.fetchone.side_effect = [('12.2.2', 'uuid', 'db'), ('t', 'native ddl')]
    connection = Mock(server_status=0)
    connection.cursor.return_value = cursor
    connection.commit.side_effect = OSError('lost acknowledgement')
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mariadb_data_application.native_layout', lambda *_: selected['native_columns'])
    monkeypatch.setattr('pgadmin.cdeadmin.providers.mariadb_data_application.verify', lambda *_: {'verified': True})
    result = apply_import(connection, {'plan': selected})
    assert result['state'] == 'unknown_outcome' and result['acknowledged_rows'] == 1
    connection.commit.assert_called_once()
    connection.rollback.assert_called_once()
    assert sum(call.args[0].startswith('INSERT INTO') for call in cursor.execute.call_args_list) == 1
