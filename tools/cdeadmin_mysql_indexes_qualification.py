"""Native typed indexes, review identity, catalog discovery and API dispatch."""
import argparse
import hashlib
import json
from pathlib import Path
import secrets
import sys
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'web'), str(ROOT/'tools')]


def qualify(output):
    from cdeadmin_mysql_dump_verification_qualification import setup_application
    output = Path(output).resolve(); output.mkdir(parents=True, exist_ok=False)
    app = setup_application(output)
    from mysql_qualification_support import server, _root_connection
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_PROFILE, MYSQL_ADMINISTRATION, _create_client, _resources
    from pgadmin.cdeadmin.providers.mysql_family import mysql_indexes as indexes
    from pgadmin.cdeadmin.sdk import RelationalClientError
    paths = ['web/pgadmin/cdeadmin/providers/mysql_family/'+name for name in ('mysql_indexes.py', 'administration.py', 'provider.py', 'descriptor_contracts.py')]
    paths += ['web/pgadmin/cdeadmin/visual_admin/provider.py']
    paths += ['web/pgadmin/cdeadmin/ui_descriptors/mysql/'+name for name in ('forms/index.form.json', 'operations.json')]
    paths += [str(Path(__file__).relative_to(ROOT))]
    proof = {'complete': False, 'history_testing': 'ScratchBird history not run', 'interfaces': [],
        'source_sha256': {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    try:
        with server(output/'fixture') as (route, _container, owned):
            oracle = _root_connection('mysql', route['port']); oracle.autocommit = True; q = oracle.cursor()
            try:
                q.execute('CREATE DATABASE sr_osc')
                q.execute('CREATE TABLE sr_osc.t(id INT AUTO_INCREMENT PRIMARY KEY,word VARCHAR(100),body TEXT,doc JSON,g POINT NOT NULL SRID 4326)')
                q.execute("INSERT INTO sr_osc.t(word,body,doc,g) VALUES('Native word 雪','Native body words',JSON_OBJECT('tags',JSON_ARRAY(1,2)),ST_SRID(POINT(1,2),4326))")
                q.execute('CREATE TABLE sr_osc.pending(id INT PRIMARY KEY)')
                q.execute('CREATE TABLE sr_osc.myisam(word VARCHAR(100)) ENGINE=MyISAM')
                q.execute('CREATE TABLE sr_osc.memory(id INT) ENGINE=MEMORY')
                q.execute('SELECT @@GLOBAL.sql_mode'); original_mode = q.fetchone()[0]
                for pure in (True, False):
                    mode = original_mode if pure else 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'
                    q.execute('SET GLOBAL sql_mode=%s', (mode,))
                    client = _create_client(MYSQL_PROFILE, SimpleNamespace(acquire_secret=None), SimpleNamespace())
                    selected = {**route, 'database': 'sr_osc', 'use_pure': pure}
                    classes = []; connect = client._connect
                    def tracked(request):
                        handle = connect(request); classes.append(type(handle).__name__); return handle
                    client._connect = tracked
                    prefix = 'typed_'+str(int(pure))+'_'
                    def review(draft):
                        return client.plan_admin_operation({'resource_kind': 'index', 'operation_id': 'create', 'draft': draft, '_provider_route': selected})
                    def execute(draft):
                        return MYSQL_ADMINISTRATION.apply(client, review(draft))
                    def parts(name, table='t'):
                        q.execute('SELECT COLUMN_NAME,EXPRESSION,SUB_PART,COLLATION,INDEX_TYPE,IS_VISIBLE,INDEX_COMMENT '
                            'FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s ORDER BY SEQ_IN_INDEX', ('sr_osc', table, name))
                        return q.fetchall()
                    try:
                        name = prefix+'ordered'
                        planned = review({'name': name, 'table': ['sr_osc', 't'],
                            'columns': [{'name': 'word', 'prefix_length': 6, 'direction': 'DESC'}, {'name': 'id', 'direction': 'ASC'}],
                            'unique': True, 'method': 'BTREE', 'visible': False, 'comment': "quote' 雪", 'algorithm': 'INPLACE', 'lock': 'NONE'})
                        # Normal writes advance AUTO_INCREMENT between review
                        # and apply. They are not a structural DDL change.
                        q.execute("INSERT INTO sr_osc.t(word,body,doc,g) VALUES('Later word','Later body',JSON_OBJECT('tags',JSON_ARRAY(3)),ST_SRID(POINT(2,3),4326))")
                        oracle.autocommit = False; q.execute('SAVEPOINT index_guard'); q.execute('INSERT INTO sr_osc.pending VALUES(%s)', (int(pure)+1,))
                        applied = MYSQL_ADMINISTRATION.apply(client, planned)
                        assert applied['accepted'] and applied['index_observation']['native_acknowledged']
                        assert 'table_definition' not in applied['index_observation']['after']
                        q.execute('SELECT ROW_COUNT()'); assert q.fetchone() == (1,)
                        q.execute('ROLLBACK TO SAVEPOINT index_guard'); oracle.rollback(); oracle.autocommit = True
                        observed = parts(name)
                        assert observed[0][:4] == ('word', None, 6, 'D') and observed[1][:4] == ('id', None, None, 'A')
                        assert all(row[4:] == ('BTREE', 'NO', "quote' 雪") for row in observed)
                        cases = [
                            ('functional', 't', {'columns': [{'expression': 'lower(word)', 'direction': 'DESC'}]}),
                            ('literal', 't', {'columns': [{'expression': "CAST(CONCAT(word,'/*! literal') AS CHAR(32))"}]}),
                            ('array', 't', {'columns': [{'expression': "CAST(doc->'$.tags' AS UNSIGNED ARRAY)"}]}),
                            ('text', 't', {'columns': ['body'], 'index_kind': 'FULLTEXT', 'parser': 'ngram'}),
                            ('spatial', 't', {'columns': ['g'], 'index_kind': 'SPATIAL'}),
                            ('hash', 'memory', {'columns': ['id'], 'method': 'HASH'}),
                            ('block', 'myisam', {'columns': [{'name': 'word', 'prefix_length': 8}], 'key_block_size': '8', 'algorithm': 'COPY', 'lock': 'SHARED'}),
                            ('attributes', 't', {'columns': ['id'], 'secondary_engine_attribute': {'native': "quote' 雪"}}),
                        ]
                        failures = []
                        for suffix, table, values in cases:
                            try:
                                result = execute({'name': prefix+suffix, 'table': ['sr_osc', table], **values})
                                assert result['accepted'] and parts(prefix+suffix, table)
                            except Exception as error:
                                failures.append({'case': suffix, 'connector_pure': pure, 'type': type(error).__name__,
                                    'errno': getattr(error, 'errno', None), 'sqlstate': getattr(error, 'sqlstate', None),
                                    'native_dispatched': getattr(error, 'native_dispatched', None),
                                    'native_acknowledged': getattr(error, 'native_acknowledged', None)})
                        if failures:
                            proof['failures'] = failures
                            raise AssertionError(failures)
                        proof.setdefault('native_index_observations', []).append({'use_pure': pure,
                            'variants': {suffix: parts(prefix+suffix, table) for suffix, table, _values in cases}})
                        assert parts(prefix+'functional')[0][1] and parts(prefix+'functional')[0][3] == 'D'
                        assert parts(prefix+'array')[0][1] and parts(prefix+'text')[0][4] == 'FULLTEXT'
                        assert parts(prefix+'spatial')[0][4] == 'SPATIAL' and parts(prefix+'hash', 'memory')[0][4] == 'HASH'
                        handle = client._connect({'route': selected}); direct = handle.cursor()
                        try:
                            for table in ('t', 'myisam', 'memory'):
                                try:
                                    direct.execute('CREATE INDEX `'+prefix+'unsupported_attribute` ON sr_osc.`'+table+'` (`'+('word' if table!='memory' else 'id')+'`) ENGINE_ATTRIBUTE=%s', ('{"native":true}',))
                                except Exception as error: assert getattr(error, 'errno', None) == 3981
                                else: raise AssertionError('Unqualified primary-engine attribute support appeared')
                            for engine in ('InnoDB', 'MyISAM', 'MEMORY'):
                                try:
                                    direct.execute('CREATE TABLE sr_osc.`'+prefix+'unsupported_attribute` (id INT) ENGINE='+engine+' ENGINE_ATTRIBUTE=%s', ('{"native":true}',))
                                except Exception as error: assert getattr(error, 'errno', None) == 3981
                                else: raise AssertionError('Unqualified table engine-attribute support appeared')
                        finally: direct.close(); client._forget_and_close(handle)
                        handle = client._connect({'route': selected})
                        try:
                            resources = _resources(handle, {'route': selected}, MYSQL_PROFILE)
                            node = next(row for row in resources if row['resource_kind'] == 'index' and row['display_path'] == ['sr_osc', 't', name])
                            assert node['native']['definition_parts'] == [{'name': 'word', 'prefix_length': 6, 'direction': 'DESC'}, {'name': 'id', 'direction': 'ASC'}]
                            assert node['native']['index_kind'] == 'NORMAL' and node['native']['unique'] and node['native']['visible'] is False
                            functional = next(row for row in resources if row['resource_kind'] == 'index' and row['display_name'] == prefix+'functional')
                            assert functional['native']['definition_parts'][0]['expression']
                            spatial = next(row for row in resources if row['resource_kind'] == 'index' and row['display_name'] == prefix+'spatial')
                            assert spatial['native']['index_kind'] == 'SPATIAL'
                        finally: client._forget_and_close(handle)
                        stale_name = prefix+'stale'
                        stale = review({'name': stale_name, 'table': ['sr_osc', 't'], 'columns': ['id']})
                        q.execute('ALTER TABLE sr_osc.t ADD COLUMN `'+prefix+'changed` INT')
                        try: MYSQL_ADMINISTRATION.apply(client, stale)
                        except RelationalClientError as error: assert error.native_dispatched is False
                        else: raise AssertionError('Stale table definition was admitted')
                        assert not parts(stale_name)
                        try: execute({'name': prefix+'bad_parser', 'table': ['sr_osc', 't'], 'columns': ['body'], 'index_kind': 'FULLTEXT', 'parser': 'owned_missing_parser'})
                        except RelationalClientError as error:
                            assert error.native_dispatched and not error.native_acknowledged and error.errno >= 1000
                        else: raise AssertionError('Missing native parser was accepted')
                        assert not parts(prefix+'bad_parser')
                        loss_name = prefix+'lost_observation'; reviewed = review({'name': loss_name, 'table': ['sr_osc', 't'], 'columns': ['id']})
                        observe = indexes.observe; calls = 0
                        def lost(*args):
                            nonlocal calls
                            calls += 1
                            if calls == 2: raise OSError('Owned post-ack observation loss')
                            return observe(*args)
                        with patch.object(indexes, 'observe', lost):
                            try: MYSQL_ADMINISTRATION.apply(client, reviewed)
                            except RelationalClientError as error:
                                assert error.native_dispatched and error.native_acknowledged and error.automatic_retry is False
                            else: raise AssertionError('Lost observation hid the native ACK')
                        assert parts(loss_name)
                        expected = 'CharsetMySQLConnection' if pure else 'CharsetCMySQLConnection'
                        assert set(classes) == {expected}
                        proof['interfaces'].append({'native_connection_class': expected, 'complete': True,
                            'index_variants': ['ordered-unique-prefix-desc-invisible', *[row[0] for row in cases]],
                            'normal_writes_between_review_and_apply': True, 'pending_transaction_and_savepoint_preserved': True,
                            'native_catalog_key_parts_and_traits_verified': True, 'stale_definition_refused': True,
                            'native_missing_parser_error_preserved': True, 'post_ack_observation_loss_never_replayed': True,
                            'primary_engine_attributes_unavailable_in_three_release_engines': True})
                        for suffix, table in [('ordered', 't'), *[(row[0], row[1]) for row in cases], ('lost_observation', 't')]:
                            q.execute('ALTER TABLE sr_osc.`'+table+'` DROP INDEX `'+prefix+suffix+'`')
                    finally: client.close()
                q.execute('SET GLOBAL sql_mode=%s', (original_mode,))
                password = secrets.token_urlsafe(24); q.execute('ALTER USER CURRENT_USER() IDENTIFIED BY %s', (password,))
                proof['application'] = workspace(app, route, password, q)
                proof['complete'] = True
            finally: q.close(); oracle.close()
        proof['owned_server_stopped'] = owned['owned_server_stopped']
    finally: (output/'summary.json').write_text(json.dumps(proof, indent=2)+'\n')
    return proof


def workspace(app, route, password, oracle):
    from cdeadmin_mysql_online_ddl_qualification import registration
    results = []
    for pure in (True, False):
        _sid, _target, post = registration(app, route, password, not pure)
        name = 'api_typed_'+str(int(pure))
        planned = post('visual_admin_plan', {'resource_kind': 'index', 'operation_id': 'create',
            'draft': {'name': name, 'table': ['sr_osc', 't'], 'columns': [{'expression': 'lower(word)', 'direction': 'DESC'}], 'visible': False}})
        assert planned['state'] == 'ready' and planned['execution_available'], planned
        request = {key: planned[key] for key in ('plan_id', 'plan_digest')} | {'confirmed': True}
        result = post('visual_admin_apply', request)
        assert result['provider_result']['accepted']
        replay = post.raw('visual_admin_apply', request)
        assert replay.status_code != 200 or not replay.get_json().get('success')
        oracle.execute('SELECT EXPRESSION,COLLATION,IS_VISIBLE FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND INDEX_NAME=%s', ('sr_osc', 't', name))
        row = oracle.fetchone(); assert row[0] and row[1:] == ('D', 'NO')
        oracle.execute('ALTER TABLE sr_osc.t DROP INDEX `'+name+'`')
        results.append({'use_pure': pure, 'typed_plan_apply_and_native_effect': True, 'replay_refused': True})
    return {'complete': True, 'interfaces': results}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument('--output', required=True)
    args = parser.parse_args(); result = qualify(args.output); print(json.dumps({'complete': result['complete'], 'interfaces': len(result['interfaces'])}))
