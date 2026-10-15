"""Qualify data paging across concurrent commits and lossless native values."""
import json
from decimal import Decimal
from types import SimpleNamespace
from pgadmin.cdeadmin.providers.firebird.provider import _create_client, _resources
from pgadmin.cdeadmin.providers.firebird.temporal_arrays import cursor as native_cursor
from pgadmin.cdeadmin.security.secrets import SecretLease
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_data_export import capture


def qualify(connection, route, password, destination=None, destination_route=None):
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE DATA_EXPORT_TEST (ID INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, BIG INT128, '
            'EXACT_VALUE NUMERIC(18,4), NOTE VARCHAR(40), BIN BLOB SUB_TYPE BINARY, '
            'TXT BLOB SUB_TYPE TEXT, ARR INTEGER[-1:1], APPROX DOUBLE PRECISION, CALC COMPUTED BY (ID + 1))')
    connection.commit()
    with native_cursor(connection) as cursor:
        for index in range(205):
            cursor.execute('INSERT INTO DATA_EXPORT_TEST (ID, BIG, EXACT_VALUE, NOTE, BIN, TXT, ARR, APPROX) OVERRIDING SYSTEM VALUE VALUES (?, ?, ?, ?, ?, ?, ?, ?)',
                (index, 2**100, Decimal('123.4500'), 'é;\r\n' if index else '',
                 bytes([0, 255, 10]), '' if index else None, [-1, 0, 1], -0.0))
    connection.commit()
    rows = _resources(connection, {})
    connection.rollback()
    model = build_export(rows, endpoint_id='owned', target_id='owned', generation='native',
                         resource_id='table:DATA_EXPORT_TEST', native_model=True)
    permissions = SimpleNamespace(require=lambda *_: True,
                                  acquire_secret=lambda *_: SecretLease(password))
    embedded = route.get('attachment_mode') == 'embedded'
    if embedded:
        from pgadmin.cdeadmin.providers.firebird.embedded_provider import PROFILE, ADMINISTRATION
        client = _create_client(permissions, attachment_mode='embedded', profile=PROFILE,
                                administration=ADMINISTRATION)
    else:
        client = _create_client(permissions, attachment_mode='network')
    credentials = {} if embedded else {'credential_reference_id': 'owned-export', 'principal_reference': 'owned-export'}
    scoped = {**route, **credentials,
              'transaction_access': 'READ', 'transaction_isolation': 'SNAPSHOT',
              'transaction_auto_commit': False, 'transaction_ignore_limbo': False}
    handles, actions, pages = {}, [], []

    class Host:
        def open_session(self, _server, _language, _target, *, session_purpose):
            assert session_purpose == 'firebird-data-export'
            handles['export'] = client.open_session({'route': scoped})
            return {'session_id': 'export'}

        def read_visual_admin_rows(self, _server, request):
            page = client.read_admin_rows({**request, '_provider_route': scoped,
                                          '_provider_session_handle': handles[request['session_id']]})
            pages.append(len(page['rows']))
            if len(pages) == 1:
                with connection.cursor() as cursor:
                    cursor.execute('INSERT INTO DATA_EXPORT_TEST (ID) OVERRIDING SYSTEM VALUE VALUES (1000)')
                connection.commit()
            return page

        def cancel_visual_admin_rows(self, _server, request):
            return client.cancel_admin_cursor(request)

        def transaction_action(self, _server, session, action, _target):
            actions.append(action)
            return client.control_transaction(handles[session], action)

        def close_session(self, _server, session, _target):
            client.close_session(handles.pop(session))

    try:
        result = capture(Host(), None, model, contents='both')
        document = json.loads(result['download_text'])
        from pgadmin.cdeadmin.workspace.firebird_data_ddn import read
        assert result['ddn'].get('snapshot'), result['ddn']
        assert json.loads(read(result['ddn']['download_text'])) == document
        table = document['tables'][0]
        assert result['row_count'] == 205 and pages == [200, 5], (result['row_count'], pages)
        assert actions == ['rollback'] and not handles
        for row in table['rows']:
            assert row['BIG'] == str(2**100)
            assert Decimal(row['EXACT_VALUE']) == Decimal('123.4500')
            assert row['BIN'] == {'encoding': 'base64', 'data': 'AP8K', 'byte_length': 3}
            assert row['ARR'] == [-1, 0, 1] and row['APPROX'] == '-0.0'
        assert table['rows'][0]['TXT'] is None and table['rows'][1]['TXT'] == ''
        assert table['rows'][0]['NOTE'] == '' and table['rows'][1]['NOTE'] == 'é;\r\n'
        exact = next(column for column in table['native_columns'] if column['name'] == 'EXACT_VALUE')
        assert int(exact['field_scale']) == -4
        array = next(column for column in table['columns'] if column['name'] == 'ARR')
        assert array['array_spec']
        with connection.cursor() as cursor:
            cursor.execute('SELECT COUNT(*) FROM DATA_EXPORT_TEST')
            assert cursor.fetchone() == (206,)
        connection.rollback()
        replay = None
        if destination is not None:
            from pgadmin.cdeadmin.providers.firebird.provider import ADMINISTRATION
            from pgadmin.cdeadmin.workspace.firebird_data_import import preview
            for statement in model['rows']['table:DATA_EXPORT_TEST']['native']['recreation_statements']:
                destination.execute_immediate(statement)
            destination.commit()
            destination_model = build_export(_resources(destination, {}), endpoint_id='destination',
                target_id='destination', generation='native-destination', native_model=True)
            destination.rollback()
            planned = preview(result['ddn']['download_text'], destination_model)
            assert planned['identity_requirements'] and all(op['override_identity'] for op in planned['operations'])
            write_route = {**destination_route, **credentials, 'transaction_access': 'WRITE',
                'transaction_isolation': 'SNAPSHOT', 'transaction_auto_commit': False}
            for outcome in ('rollback', 'commit'):
                handle = client.open_session({'route': write_route})
                try:
                    for operation in planned['operations']:
                        request = {'resource_kind': 'table', 'operation_id': 'insert',
                            '_provider_route': write_route, 'target_resource': planned['catalogs'][operation['table']]['resource'],
                            'draft': {'values': operation['values'], 'override_identity': operation['override_identity']}}
                        plan = ADMINISTRATION.plan(request)
                        ADMINISTRATION.apply(client, plan, connection=handle)
                    with destination.cursor() as probe:
                        probe.execute('SELECT COUNT(*) FROM DATA_EXPORT_TEST')
                        assert probe.fetchone() == (0,)
                    destination.rollback()
                    client.control_transaction(handle, outcome)
                finally:
                    client.close_session(handle)
                with destination.cursor() as probe:
                    probe.execute('SELECT COUNT(*) FROM DATA_EXPORT_TEST')
                    assert probe.fetchone() == ((0,) if outcome == 'rollback' else (205,))
                destination.rollback()
            with native_cursor(destination) as probe:
                probe.execute('SELECT ID, BIG, EXACT_VALUE, BIN, TXT, ARR, APPROX, CALC FROM DATA_EXPORT_TEST ORDER BY ID')
                imported = probe.fetchall()
                assert len(imported) == 205
                assert imported[0][0] == 0 and imported[-1][0] == 204
                assert all(value[1] == 2**100 and value[2] == Decimal('123.4500') and
                           value[3] == bytes([0, 255, 10]) and value[5] == [-1, 0, 1] and
                           value[7] == value[0] + 1 for value in imported)
            destination.rollback()
            replay = {'passed': True, 'rows': 205, 'identity_values_preserved': True,
                      'computed_values_not_inserted': True, 'rollback_then_commit_verified': True,
                      'independent_visibility_verified': True}
        return {'passed': True, 'rows': 205, 'pages': pages, 'concurrent_commit_excluded': True,
                'exact_numeric_blob_array_empty_null_and_negative_zero': True,
                'owned_snapshot_released': True, 'static_ddn_roundtrip_and_native_import': True, 'sha256': result['sha256'], 'native_import': replay}
    finally:
        for handle in handles.values(): client.close_session(handle)
        client.close()
