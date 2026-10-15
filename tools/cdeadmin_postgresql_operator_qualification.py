"""Native operator administration through retained provider plans and owned sessions."""
import uuid
import psycopg
from psycopg import sql


def qualify(provider, route, password, server, receipt):
    from pgadmin.utils.driver import get_driver
    from pgadmin.utils.crypto import encrypt
    from pgadmin.utils.master_password import get_crypt_key
    present, key = get_crypt_key()
    assert present
    manager = get_driver('psycopg3').connection_manager(server.id)
    status, _ = manager.connection().connect(password=encrypt(password, key))
    assert status
    schemas = ['sr_operator_' + uuid.uuid4().hex for _ in range(2)]
    role = 'sr_operator_owner_' + uuid.uuid4().hex
    created, role_created = [], False
    try:
        with psycopg.connect(host=route['host'], port=route['port'], user=route['user'], password=password,
                dbname=route.get('database', 'postgres'), autocommit=True,
                **route.get('connection_params', {})) as observer:
            try:
                oid = int(observer.execute('SELECT oid FROM pg_database WHERE datname=current_database()').fetchone()[0])
                for schema in schemas:
                    observer.execute(sql.SQL('CREATE SCHEMA {}').format(sql.Identifier(schema)))
                    created.append(schema)
                observer.execute(sql.SQL('CREATE ROLE {} NOLOGIN').format(sql.Identifier(role)))
                role_created = True
                target = {'schema': schemas[0], 'name': '===', 'left_type': 'integer', 'right_type': 'integer'}
                def action(operation, draft):
                    plan = provider.plan_admin_operation({'resource_kind': 'operator', 'operation_id': operation,
                        'draft': draft, '_provider_route': {'server_id': server.id, 'database_id': oid},
                        'target_resource': {'extensions': {'postgresql': {'native': dict(target)}}}})
                    result = provider.apply_admin_operation(plan)
                    assert result['transaction_outcome'] == 'committed' and result['release_status'] == 'confirmed'
                    return result
                observer.execute(sql.SQL('CREATE OPERATOR {}.!== (FUNCTION=pg_catalog.int4ne,LEFTARG=integer,RIGHTARG=integer)').format(sql.Identifier(schemas[0])))
                action('create', {**target, 'function': 'pg_catalog.int4eq', 'options': {
                    'commutator': schemas[0]+'.===', 'negator': schemas[0]+'.!==',
                    'restrict': 'pg_catalog.eqsel', 'join': 'pg_catalog.eqjoinsel', 'hashes': True, 'merges': True}})
                # A same-symbol different overload must survive alterations and DROP.
                observer.execute(sql.SQL('CREATE OPERATOR {}.=== (FUNCTION=pg_catalog.texteq,LEFTARG=text,RIGHTARG=text)').format(sql.Identifier(schemas[0])))
                original = int(action('inspect', {})['result']['rows'][0]['oid'])
                assert observer.execute(sql.SQL('SELECT 7 OPERATOR({}.===) 7').format(sql.Identifier(schemas[0]))).fetchone()[0] is True
                action('alter', {'action': 'options', 'options': {'restrict': None, 'join': None}})
                row = action('inspect', {})['result']['rows'][0]
                assert int(row['oid']) == original and row['oprrest'] == '-' and row['oprjoin'] == '-'
                action('alter', {'action': 'comment', 'value': 'operator comment'})
                assert action('inspect', {})['result']['rows'][0]['comment'] == 'operator comment'
                action('alter', {'action': 'schema', 'value': schemas[1]})
                target['schema'] = schemas[1]
                action('alter', {'action': 'owner', 'value': role})
                assert observer.execute('SELECT pg_get_userbyid(oprowner) FROM pg_operator WHERE oid=%s',(original,)).fetchone()[0] == role
                action('drop', {'confirmation': '==='})
                assert action('inspect', {})['result']['rows'] == []
                assert observer.execute(sql.SQL("SELECT 'a'::text OPERATOR({}.===) 'a'::text").format(sql.Identifier(schemas[0]))).fetchone()[0] is True
                target.update(schema=schemas[0], name='@#', left_type=None)
                action('create', {**target, 'function': 'pg_catalog.int4abs'})
                assert int(observer.execute(sql.SQL('SELECT OPERATOR({}.@#) (-7)').format(sql.Identifier(schemas[0]))).fetchone()[0]) == 7
                assert len(action('inspect', {})['result']['rows']) == 1
                action('drop', {'confirmation': '@#'})
                receipt['checks'].append('native-operator-create-prefix-binary-overload-options-comment-move-owner-drop')
            finally:
                for schema in reversed(created):
                    observer.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                if role_created:
                    observer.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
    finally:
        manager.release()
