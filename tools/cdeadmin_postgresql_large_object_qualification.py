"""Owned native large-object CRUD, sparse offsets, ACLs and isolation proof."""
import base64
import hashlib
import secrets


def qualify(provider, route, password, server, receipt):
    import psycopg
    from psycopg import sql
    from psycopg.rows import tuple_row
    from psycopg.types.string import ByteaLoader
    from pgadmin.utils.driver import get_driver
    from pgadmin.utils.crypto import encrypt
    from pgadmin.utils.master_password import get_crypt_key
    present, key = get_crypt_key()
    assert present
    manager = get_driver('psycopg3').connection_manager(server.id)
    status, _ = manager.connection().connect(password=encrypt(password, key))
    assert status
    connection = psycopg.connect(host=route['host'], port=route['port'], user=route['user'],
        password=password, dbname=route['database'], autocommit=True, row_factory=tuple_row,
        **route.get('connection_params', {}))
    connection.adapters.register_loader(17, ByteaLoader)
    oid, lost_oid, role_created = None, None, False
    role, role_password = 'sr_lo_' + secrets.token_hex(8), secrets.token_urlsafe(32)
    try:
        database_oid = int(connection.execute('SELECT oid FROM pg_catalog.pg_database WHERE datname=current_database()').fetchone()[0])
        def execute(operation, draft=None):
            plan = provider.plan_admin_operation({'resource_kind': 'large-object', 'operation_id': operation,
                'draft': draft or {}, '_provider_route': {'server_id': server.id, 'database_id': database_oid},
                'target_resource': {'extensions': {'postgresql': {'native': {'oid': oid}}}}})
            return provider.apply_admin_operation({'provider_payload': plan['provider_payload']})
        initial_sessions = set(provider._sessions)
        data = bytes(range(256)) * 4096
        created = execute('create', {'large_object_data_base64': base64.b64encode(data).decode('ascii')})
        oid = int(created['result']['rows'][0]['oid'])
        assert set(provider._sessions) == initial_sessions
        assert bytes(connection.execute('SELECT lo_get(%s::oid)', (oid,)).fetchone()[0]) == data
        row = execute('read', {'offset': '1048500', 'length': '100'})['result']['rows'][0]
        assert base64.b64decode(row['data_base64'], validate=True) == data[1048500:1048600]
        assert row['sha256'] == hashlib.sha256(data[1048500:1048600]).hexdigest()
        from unittest.mock import patch
        from pgadmin.utils.driver.psycopg3.connection import Connection
        from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProviderError
        original_read = Connection.execute_dict
        def wrong_verification(connection, statement, *args, **kwargs):
            status, result = original_read(connection, statement, *args, **kwargs)
            if ' AS observed_sha256' in statement and status:
                result['rows'][0]['observed_sha256'] = 'mismatched'
            return status, result
        with patch.object(Connection, 'execute_dict', wrong_verification):
            try:
                execute('write', {'offset': '0', 'large_object_data_base64': 'AP8='})
            except PostgreSQLProviderError as error:
                assert 'verification failed before commit' in str(error)
            else:
                raise AssertionError('Large-object checksum mismatch committed')
        assert bytes(connection.execute('SELECT lo_get(%s::oid)', (oid,)).fetchone()[0]) == data
        # Large objects are sparse: this exercises the 64-bit interfaces without
        # allocating or transferring a multi-gigabyte fixture.
        offset = 2**31 + 17
        written = execute('write', {'offset': str(offset), 'large_object_data_base64': 'AP8='})
        assert written['result']['rows'][0]['observed_sha256'] == hashlib.sha256(b'\x00\xff').hexdigest()
        native = connection.execute('SELECT lo_get(%s::oid,%s::bigint,4)', (oid, offset - 2)).fetchone()[0]
        assert bytes(native) == b'\0\0\0\xff'
        execute('truncate', {'length': '128', 'confirmation': str(oid)})
        assert bytes(connection.execute('SELECT lo_get(%s::oid)', (oid,)).fetchone()[0]) == data[:128]
        execute('alter', {'action': 'comment', 'value': "🔥 OID\\'comment"})
        assert execute('inspect')['result']['rows'][0]['comment'] == "🔥 OID\\'comment"
        connection.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {}').format(sql.Identifier(role), sql.Literal(role_password)))
        role_created = True
        limited = psycopg.connect(host=route['host'], port=route['port'], user=role,
            password=role_password, dbname=route['database'], autocommit=True,
            row_factory=tuple_row, **route.get('connection_params', {}))
        limited.adapters.register_loader(17, ByteaLoader)
        try:
            execute('grant', {'role': role, 'privileges': ['SELECT']})
            assert bytes(limited.execute('SELECT lo_get(%s::oid)', (oid,)).fetchone()[0]) == data[:128]
            execute('revoke', {'role': role, 'privileges': ['SELECT']})
            try:
                limited.execute('SELECT lo_get(%s::oid)', (oid,))
            except psycopg.errors.InsufficientPrivilege:
                pass
            else:
                raise AssertionError('Large-object read privilege was not revoked')
        finally:
            limited.close()
        execute('alter', {'action': 'owner', 'value': role})
        assert execute('inspect')['result']['rows'][0]['owner'] == role
        execute('alter', {'action': 'owner', 'value': route['user']})
        execute('drop', {'confirmation': str(oid)})
        assert connection.execute('SELECT oid FROM pg_largeobject_metadata WHERE oid=%s', (oid,)).fetchone() is None
        assert set(provider._sessions) == initial_sessions
        oid = None
        receipt['checks'].append('native-large-object-file-chunks-sparse-64-bit-offsets-truncate-owner-comment-grant-revoke-drop-and-independent-visibility')
        import pgadmin.cdeadmin.providers.postgresql.provider as implementation
        original_control, commits = implementation.native_control, []
        def lose_commit(connection, command):
            result = original_control(connection, command)
            if command == 'COMMIT':
                commits.append(command)
                raise OSError('Owned commit-reply fault')
            return result
        while lost_oid is None or connection.execute('SELECT oid FROM pg_largeobject_metadata WHERE oid=%s', (lost_oid,)).fetchone() is not None:
            lost_oid = 1_000_000_000 + secrets.randbelow(1_000_000_000)
        with patch.object(implementation, 'native_control', lose_commit):
            try:
                execute('create', {'oid': str(lost_oid), 'large_object_data_base64': 'AP8='})
            except PostgreSQLProviderError as error:
                assert 'commit outcome is unknown; do not replay' in str(error)
            else:
                raise AssertionError('Lost large-object COMMIT reply was reported confirmed')
        assert commits == ['COMMIT']
        assert bytes(connection.execute('SELECT lo_get(%s::oid)', (lost_oid,)).fetchone()[0]) == b'\0\xff'
        assert set(provider._sessions) == initial_sessions
        receipt['checks'].append('native-large-object-write-verification-refusal-rolls-back-and-lost-create-commit-reply-is-unknown-without-automatic-retry')
    finally:
        if oid is not None:
            connection.execute('SELECT lo_unlink(%s::oid)', (oid,))
        if lost_oid is not None and connection.execute('SELECT oid FROM pg_largeobject_metadata WHERE oid=%s', (lost_oid,)).fetchone() is not None:
            connection.execute('SELECT lo_unlink(%s::oid)', (lost_oid,))
        if role_created:
            connection.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
        connection.close()
        manager.release()
