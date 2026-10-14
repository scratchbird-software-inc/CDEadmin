"""Native aggregate plans retain overloads, options and independent outcomes."""
import uuid
import json
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
    schemas = ['sr_aggregate_' + uuid.uuid4().hex for _ in range(2)]
    role = 'sr_aggregate_owner_' + uuid.uuid4().hex
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
                target = {'schema': schemas[0], 'name': 'sum', 'identity_arguments': 'integer'}
                def action(operation, draft):
                    plan = provider.plan_admin_operation({'resource_kind': 'aggregate', 'operation_id': operation,
                        'draft': draft, '_provider_route': {'server_id': server.id, 'database_id': oid},
                        'target_resource': {'extensions': {'postgresql': {'native': dict(target)}}}})
                    original = provider._ensure_native_connection
                    def nonstandard_connection(state):
                        original(state)
                        state.connection.conn.execute('SET standard_conforming_strings=off')
                        assert state.connection.conn.info.parameter_status('standard_conforming_strings') == 'off'
                    provider._ensure_native_connection = nonstandard_connection
                    try:
                        result = provider.apply_admin_operation(plan)
                    finally:
                        provider._ensure_native_connection = original
                    assert result['transaction_outcome'] == 'committed' and result['release_status'] == 'confirmed'
                    return result
                def definition(name, signature, options, replace=False):
                    return sql.SQL('CREATE {}AGGREGATE {}.{} ({}) ({})').format(
                        sql.SQL('OR REPLACE ' if replace else ''), sql.Identifier(schemas[0]),
                        sql.Identifier(name), sql.SQL(signature), sql.SQL(options)).as_string(observer)
                def identify(name):
                    row = observer.execute('SELECT p.oid,pg_get_function_identity_arguments(p.oid),(pg_identify_object(\'pg_proc\'::regclass,p.oid,0)).identity FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname=%s AND p.proname=%s AND p.prokind=\'a\' ORDER BY p.oid',(schemas[0],name)).fetchone()
                    target.update(name=name,schema=schemas[0],oid=int(row[0]),identity_arguments=row[1],sql_identity=row[2])
                def refresh_identity():
                    target['sql_identity']=observer.execute("SELECT (pg_identify_object('pg_proc'::regclass,%s,0)).identity",(target['oid'],)).fetchone()[0]
                options = "SFUNC=pg_catalog.int4pl,STYPE=integer,INITCOND='0',COMBINEFUNC=pg_catalog.int4pl,PARALLEL=SAFE,MSFUNC=pg_catalog.int4pl,MINVFUNC=pg_catalog.int4mi,MSTYPE=integer,MINITCOND='0'"
                action('create', {**target, 'definition': definition('sum','integer',options)})
                identify('sum');original=target['oid']
                observer.execute(sql.SQL('CREATE AGGREGATE {}.sum(bigint) (SFUNC=pg_catalog.int8pl,STYPE=bigint)').format(sql.Identifier(schemas[0])))
                values = observer.execute(sql.SQL('SELECT {}.sum(v) OVER (ORDER BY v ROWS 1 PRECEDING) FROM (VALUES(1),(2),(3)) q(v)').format(sql.Identifier(schemas[0]))).fetchall()
                assert [int(x[0]) for x in values] == [1,3,5]
                row = action('inspect', {})['result']['rows'][0]
                assert row['proparallel'] == 's'
                action('create', {**target, 'replace': True, 'definition': definition('sum','integer',"SFUNC=pg_catalog.int4pl,STYPE=integer,INITCOND='10'",True)})
                assert int(action('inspect', {})['result']['rows'][0]['oid']) == original
                assert int(observer.execute(sql.SQL('SELECT {}.sum(v) FROM (VALUES(1),(2),(3)) q(v)').format(sql.Identifier(schemas[0]))).fetchone()[0]) == 16
                action('alter', {'action':'comment','value':'aggregate comment'})
                assert action('inspect', {})['result']['rows'][0]['comment']=='aggregate comment'
                action('alter', {'action':'rename','value':'renamed sum'});target['name']='renamed sum';refresh_identity()
                action('alter', {'action':'schema','value':schemas[1]});target['schema']=schemas[1];refresh_identity()
                action('alter', {'action':'owner','value':role})
                assert observer.execute('SELECT pg_get_userbyid(proowner) FROM pg_proc WHERE oid=%s',(original,)).fetchone()[0]==role
                action('drop', {'confirmation':target['name']})
                assert action('inspect', {})['result']['rows']==[]
                assert int(observer.execute(sql.SQL('SELECT {}.sum(v::bigint) FROM (VALUES(1),(2),(3)) q(v)').format(sql.Identifier(schemas[0]))).fetchone()[0])==6
                variants=[('zero','*',"SFUNC=pg_catalog.int8inc,STYPE=bigint,INITCOND='0'",'zero(*)',3),
                          ('ordered','ORDER BY integer',"SFUNC=pg_catalog.int4pl,STYPE=integer,INITCOND='0'",'ordered() WITHIN GROUP (ORDER BY v)',6),
                          ('hypothetical','integer ORDER BY integer',"SFUNC=pg_catalog.int4pl,STYPE=integer,FINALFUNC=pg_catalog.int4pl,INITCOND='0',HYPOTHETICAL",'hypothetical(10) WITHIN GROUP (ORDER BY v)',16)]
                for name,signature,opts,expression,expected in variants:
                    action('create', {'schema':schemas[0],'name':name,'definition':definition(name,signature,opts)})
                    identify(name)
                    assert int(observer.execute(sql.SQL('SELECT {}.{} FROM (VALUES(1),(2),(3)) q(v)').format(sql.Identifier(schemas[0]),sql.SQL(expression))).fetchone()[0])==expected
                    assert len(action('inspect', {})['result']['rows'])==1
                    action('alter', {'action':'comment','value':name+' comment'})
                    action('drop', {'confirmation':name})
                # Exercise actual serialization/deserialization of internal state
                # through a partial/final parallel aggregate, not just its DDL.
                action('create', {'schema':schemas[0], 'name':'parallel_avg',
                    'definition':definition('parallel_avg','bigint',
                        'SFUNC=pg_catalog.int8_avg_accum,STYPE=internal,'
                        'FINALFUNC=pg_catalog.numeric_poly_avg,COMBINEFUNC=pg_catalog.int8_avg_combine,'
                        'SERIALFUNC=pg_catalog.int8_avg_serialize,DESERIALFUNC=pg_catalog.int8_avg_deserialize,PARALLEL=SAFE')})
                identify('parallel_avg')
                observer.execute(sql.SQL('CREATE TABLE {}.parallel_input AS SELECT generate_series(1,20000)::bigint AS value').format(sql.Identifier(schemas[0])))
                observer.execute(sql.SQL('ALTER TABLE {}.parallel_input SET (parallel_workers=2)').format(sql.Identifier(schemas[0])))
                observer.execute('SET max_parallel_workers_per_gather=2')
                observer.execute('SET min_parallel_table_scan_size=0')
                observer.execute('SET parallel_setup_cost=0')
                observer.execute('SET parallel_tuple_cost=0')
                query=sql.SQL('SELECT {}.parallel_avg(value) FROM {}.parallel_input').format(sql.Identifier(schemas[0]),sql.Identifier(schemas[0]))
                encoded=observer.execute(sql.SQL('EXPLAIN (ANALYZE,FORMAT JSON) ')+query).fetchone()[0]
                plan=(json.loads(encoded) if isinstance(encoded,str) else encoded)[0]['Plan']
                def nodes(node):
                    yield node
                    for child in node.get('Plans',[]): yield from nodes(child)
                actual=list(nodes(plan))
                assert any(n.get('Partial Mode')=='Partial' for n in actual)
                assert any(n.get('Partial Mode')=='Finalize' for n in actual)
                assert any(n.get('Workers Launched',0)>0 for n in actual)
                assert str(observer.execute(query).fetchone()[0]).rstrip('0')=='10000.5'
                action('drop', {'confirmation':'parallel_avg'})
                receipt['checks'].append('native-aggregate-internal-state-serial-deserial-parallel-workers-execution')
                observer.execute(sql.SQL("CREATE FUNCTION {}.variadic_step(bigint,VARIADIC integer[]) RETURNS bigint LANGUAGE SQL IMMUTABLE AS 'SELECT $1+COALESCE((SELECT sum(v) FROM unnest($2) q(v)),0)'").format(sql.Identifier(schemas[0])))
                action('create', {'schema':schemas[0], 'name':'variadic_sum',
                    'definition':definition('variadic_sum','VARIADIC integer[]',
                        'SFUNC='+schemas[0]+".variadic_step,STYPE=bigint,INITCOND='0'")})
                identify('variadic_sum')
                assert int(observer.execute(sql.SQL('SELECT {}.variadic_sum(v,v+1) FROM (VALUES(1),(2),(3)) q(v)').format(sql.Identifier(schemas[0]))).fetchone()[0])==15
                assert int(observer.execute(sql.SQL('SELECT {}.variadic_sum(VARIADIC ARRAY[v,v+1]) FROM (VALUES(1),(2),(3)) q(v)').format(sql.Identifier(schemas[0]))).fetchone()[0])==15
                action('alter', {'action':'comment','value':'variadic overload'})
                assert action('inspect', {})['result']['rows'][0]['comment']=='variadic overload'
                action('drop', {'confirmation':'variadic_sum'})
                receipt['checks'].append('native-aggregate-variadic-expanded-and-array-invocation-signature-comment-drop')
                action('create', {'schema':schemas[0], 'name':'literal', 'definition':definition('literal','text',
                    "SFUNC=pg_catalog.textcat,STYPE=text,INITCOND='\\'")})
                identify('literal')
                assert observer.execute(sql.SQL("SELECT {}.literal(v) FROM (VALUES('x')) q(v)").format(sql.Identifier(schemas[0]))).fetchone()[0]=='\\x'
                action('drop', {'confirmation':'literal'})
                observer.execute(sql.SQL('CREATE DOMAIN {}.custom AS integer').format(sql.Identifier(schemas[0])))
                observer.execute(sql.SQL("CREATE FUNCTION {}.step(integer,{}.custom) RETURNS integer LANGUAGE SQL IMMUTABLE AS 'SELECT $1+$2'").format(sql.Identifier(schemas[0]),sql.Identifier(schemas[0])))
                action('create', {'schema':schemas[0],'name':'custom_agg','definition':definition('custom_agg',schemas[0]+'.custom',
                    'SFUNC='+schemas[0]+".step,STYPE=integer,INITCOND='0'")})
                browse=manager.connection(did=oid)
                assert browse.connect()[0]
                assert browse.execute_void('SET search_path='+schemas[0]+',pg_catalog')[0]
                try:
                    schema_oid=int(observer.execute('SELECT oid FROM pg_namespace WHERE nspname=%s',(schemas[0],)).fetchone()[0])
                    rows=provider._catalog.read('aggregate', {'server_id':server.id,'database_id':oid,'schema_id':schema_oid})
                    resource=next(row for row in rows if row['name']=='custom_agg')
                    assert schemas[0]+'.custom' in resource['sql_identity']
                    target.clear();target.update(resource)
                    action('alter', {'action':'comment','value':'qualified custom type'})
                    action('drop', {'confirmation':'custom_agg'})
                finally:
                    browse.execute_void('RESET search_path')
                receipt['checks'].append('native-aggregate-qualified-custom-type-signature-across-independent-search-paths')
                receipt['checks'].append('native-admin-literal-policy-overrides-nonstandard-owned-connection-default')
                receipt['checks'].append('native-aggregate-create-moving-parallel-replace-overloads-owner-rename-schema-comment-drop')
                receipt['checks'].append('native-aggregate-zero-input-ordered-set-hypothetical-signatures-and-execution')
            finally:
                for schema in reversed(created):
                    observer.execute(sql.SQL('DROP SCHEMA {} CASCADE').format(sql.Identifier(schema)))
                if role_created:
                    observer.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
    finally:
        manager.release()
