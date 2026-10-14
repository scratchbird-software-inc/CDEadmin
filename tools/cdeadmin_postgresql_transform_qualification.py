"""Real optional PL/Python transform proof, with owned native fixtures."""
from contextlib import contextmanager
import json
import uuid
from psycopg import sql


@contextmanager
def fixture(connection):
    if connection.execute("SELECT 1 FROM pg_transform t JOIN pg_language l ON l.oid=t.trflang "
                          "WHERE t.trftype='jsonb'::regtype AND l.lanname='plpython3u'").fetchone():
        raise ValueError('Existing jsonb/plpython3u transform is not an owned fixture')
    name = 'sr_transform_' + uuid.uuid4().hex
    language_created = False
    schema_created = False
    try:
        if not connection.execute("SELECT 1 FROM pg_language WHERE lanname='plpython3u'").fetchone():
            connection.execute('CREATE EXTENSION plpython3u')
            language_created = True
        connection.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(name)))
        schema_created = True
        for function, result, symbol in [('from_jsonb', 'internal', 'jsonb_to_plpython'),
                                         ('to_jsonb', 'jsonb', 'plpython_to_jsonb')]:
            connection.execute(sql.SQL('CREATE FUNCTION {}.{}(internal) RETURNS {} LANGUAGE C STRICT IMMUTABLE '
                'AS {}, {}').format(sql.Identifier(name), sql.Identifier(function), sql.SQL(result),
                                    sql.Literal('$libdir/jsonb_plpython3'), sql.Literal(symbol)))
        yield name
    finally:
        if schema_created:
            connection.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(name)))
        if language_created:
            # RESTRICT protects unrelated objects created concurrently.
            connection.execute('DROP EXTENSION plpython3u RESTRICT')


def roundtrip(connection, name):
    connection.execute(sql.SQL('CREATE FUNCTION {}.roundtrip(value jsonb) RETURNS jsonb '
        'LANGUAGE plpython3u TRANSFORM FOR TYPE jsonb AS {}').format(sql.Identifier(name),
        sql.Literal("assert isinstance(value, dict)\nvalue['native'] = True\nreturn value")))
    value = {'label': 'native ü', 'nested': {'array': [1, None, False]}}
    row = connection.execute(sql.SQL('SELECT {}.roundtrip(%s::jsonb)').format(sql.Identifier(name)),
                             (json.dumps(value),)).fetchone()[0]
    if isinstance(row, str):
        row = json.loads(row)
    assert row == {**value, 'native': True}
    connection.execute(sql.SQL('DROP FUNCTION {}.roundtrip(jsonb)').format(sql.Identifier(name)))


def qualify(provider, route, password, server, receipt):
    import psycopg
    from pgadmin.utils.driver import get_driver
    from pgadmin.utils.crypto import encrypt
    from pgadmin.utils.master_password import get_crypt_key
    present, key = get_crypt_key()
    assert present
    manager = get_driver('psycopg3').connection_manager(server.id)
    status, _ = manager.connection().connect(password=encrypt(password, key))
    assert status
    try:
        with psycopg.connect(host=route['host'], port=route['port'], user=route['user'], password=password,
                dbname=route.get('database', 'postgres'), autocommit=True,
                **route.get('connection_params', {})) as observer:
            oid = int(observer.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0])
            with fixture(observer) as name:
                def action(operation, draft):
                    plan = provider.plan_admin_operation({'resource_kind': 'transform', 'operation_id': operation,
                        'draft': draft, '_provider_route': {'server_id': server.id, 'database_id': oid},
                        'target_resource': {'extensions': {'postgresql': {'native': {
                            'data_type': 'jsonb', 'language': 'plpython3u'}}}}})
                    return provider.apply_admin_operation(plan)
                result = action('create', {'data_type': 'jsonb', 'language': 'plpython3u',
                    'from_sql': {'function': name+'.from_jsonb', 'argument_types': ['internal']},
                    'to_sql': {'function': name+'.to_jsonb', 'argument_types': ['internal']}})
                assert result['transaction_outcome'] == 'committed'
                inspected = action('inspect', {})['result']['rows']
                assert len(inspected) == 1 and inspected[0]['language'] == 'plpython3u'
                roundtrip(observer, name)
                result = action('drop', {'confirmation': 'jsonb / plpython3u'})
                assert result['transaction_outcome'] == 'committed'
                assert action('inspect', {})['result']['rows'] == []
                receipt['checks'].append('native-jsonb-plpython-transform-provider-create-inspect-bidirectional-use-drop')
    finally:
        manager.release()
