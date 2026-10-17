"""Native structured constructors, actual module queries and transaction scope."""
from contextlib import closing
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import ADMINISTRATION, _create_client
from pgadmin.cdeadmin.providers.sqlite.virtual_tables import MODULES
from pgadmin.cdeadmin.sdk import RelationalClientError
from pgadmin.cdeadmin.visual_admin import ProviderVisualAdministration


CASES = [
    ('fts3', ['body'], {'tokenizer': {'name': 'unicode61', 'arguments': ['remove_diacritics=2']}}),
    ('fts4', ['body', 'label'], {'tokenizer': {'name': 'unicode61', 'arguments': ['remove_diacritics=2']},
                               'prefix': [2, 3], 'order': 'DESC', 'matchinfo': 'fts3', 'notindexed': ['label']}),
    ('fts5', ['body', {'name': 'label', 'unindexed': True}], {
        'tokenizer': {'name': 'unicode61', 'arguments': ['remove_diacritics', '2']},
        'prefix': [2, 3], 'columnsize': 1, 'detail': 'full', 'tokendata': 1, 'locale': 1}),
    ('rtree', ['id', 'x0', 'x1'], {'auxiliary_columns': ['label']}),
    ('rtree_i32', ['id', 'x0', 'x1'], {'auxiliary_columns': ['label']}),
    ('geopoly', ['label'], {}),
    ('geopoly', [], {}),
    ('fts4aux', [], {'table': 'base4'}),
    ('fts5vocab', [], {'table': 'base5', 'mode': 'row'}),
    ('fts5vocab', [], {'database': 'main', 'table': 'base5', 'mode': 'col'}),
    ('fts5vocab', [], {'table': 'base5', 'mode': 'instance'}),
    ('fts3tokenize', [], {'tokenizer': {'name': 'unicode61', 'arguments': ['remove_diacritics=2']}}),
    ('dbstat', [], {'database': 'main'}),
    ('dbstat', [], {}),
]


def seed(path):
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript("CREATE TABLE pending(value); CREATE TABLE owner(id INTEGER PRIMARY KEY,body TEXT); "
            "INSERT INTO owner VALUES(9,'native token'); CREATE VIRTUAL TABLE base4 USING fts4(body); "
            "INSERT INTO base4 VALUES('native token'); CREATE VIRTUAL TABLE base5 USING fts5(body); "
            "INSERT INTO base5 VALUES('native token');")
        connection.commit()


def request(tmp_path, module, columns, options, *, parent='main'):
    return {'resource_kind': 'fts-table' if module in {'fts3', 'fts4', 'fts5'} else 'virtual-table',
            'operation_id': 'create', '_provider_route': {'database': str(tmp_path / 'live.sqlite'),
                'filesystem_root': str(tmp_path), 'timeout': .05},
            'draft': {'name': 'created:雪', 'parent': parent, 'module': module,
                      'columns': columns, 'module_options': options}}


@pytest.mark.parametrize('module,columns,options', CASES)
def test_structured_native_creation_real_queries_and_catalog(tmp_path, module, columns, options):
    path = tmp_path / 'live.sqlite'; seed(path)
    wanted = request(tmp_path, module, columns, options)
    assert ADMINISTRATION.validate(wanted)['errors'] == []
    planned = ADMINISTRATION.plan(wanted); client = _create_client()
    try:
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute("SELECT count(*) FROM sqlite_schema WHERE name='created:雪'").fetchone() == (0,)
        result = ADMINISTRATION.apply(client, planned)
        assert result['native_outcome'] == 'committed' and result['native_virtual_table']['columns']
        assert ADMINISTRATION.validate_operation_post_state(client, {**planned, 'provider_result': result})['confirmed']
        with closing(sqlite3.connect(path)) as observer:
            table = '"created:雪"'
            if module in {'fts3', 'fts4', 'fts5'}:
                observer.execute('INSERT INTO ' + table + '(rowid,body) VALUES(9007199254740993,\'native café\')')
                assert observer.execute('SELECT rowid,body FROM ' + table + ' WHERE ' + table + " MATCH 'cafe'").fetchall() == [(9007199254740993, 'native café')]
            elif module in {'rtree', 'rtree_i32'}:
                observer.execute('INSERT INTO ' + table + " VALUES(1,0,1,'native')")
                assert observer.execute('SELECT label FROM ' + table + ' WHERE x0<=0 AND x1>=0').fetchall() == [('native',)]
            elif module == 'geopoly':
                observer.execute('INSERT INTO ' + table + '(_shape) VALUES(geopoly_blob(?))', ('[[0,0],[1,0],[1,1],[0,0]]',))
                assert observer.execute('SELECT count(*) FROM ' + table + ' WHERE geopoly_area(_shape)>0').fetchone() == (1,)
            elif module == 'fts4aux':
                assert observer.execute('SELECT occurrences FROM ' + table + " WHERE term='native' AND col='*'").fetchall() == [(1,)]
            elif module == 'fts5vocab':
                assert observer.execute('SELECT term FROM ' + table + " WHERE term='native'").fetchall() == [('native',)]
            elif module == 'fts3tokenize':
                assert observer.execute('SELECT token FROM ' + table + " WHERE input='Native café'").fetchall() == [('native',), ('cafe',)]
            else:
                assert observer.execute('SELECT count(*) FROM ' + table).fetchone()[0] > 0
    finally:
        client.close()


@pytest.mark.parametrize('module,options', [
    ('fts4', {'content': 'owner', 'languageid': 'language'}),
    ('fts5', {'content': 'owner', 'content_rowid': 'id'}),
    ('fts5', {'content': '', 'contentless_delete': 1, 'contentless_unindexed': 1}),
])
def test_external_and_contentless_native_constructors(tmp_path, module, options):
    path = tmp_path / 'live.sqlite'; seed(path); client = _create_client()
    try:
        result = ADMINISTRATION.apply(client, ADMINISTRATION.plan(request(tmp_path, module, ['body'], options)))
        assert result['native_outcome'] == 'committed'
        with closing(sqlite3.connect(path)) as observer:
            if options['content']:
                if module == 'fts4':
                    observer.execute('ALTER TABLE owner ADD COLUMN language INTEGER DEFAULT 0')
                observer.execute('INSERT INTO "created:雪"("created:雪") VALUES(\'rebuild\')')
            else:
                observer.execute('INSERT INTO "created:雪"(rowid,body) VALUES(9,\'native token\')')
            assert observer.execute('SELECT rowid FROM "created:雪" WHERE "created:雪" MATCH \'native\'').fetchall() == [(9,)]
    finally:
        client.close()


@pytest.mark.parametrize('schema,module,columns,options', [
    ('temp', 'fts4aux', [], {'database': 'main', 'table': 'base4'}),
    ('temp', 'fts5vocab', [], {'database': 'main', 'table': 'base5', 'mode': 'row'}),
    ('attached', 'fts5', ['body'], {}),
])
def test_retained_session_creation_preserves_pending_work_and_attached_scope(tmp_path, schema, module, columns, options):
    path = tmp_path / 'live.sqlite'; seed(path); client = _create_client()
    wanted = request(tmp_path, module, columns, options, parent=schema)
    try:
        handle = client._connect({'route': wanted['_provider_route']})
        handle.execute('ATTACH ? AS attached', (str(tmp_path / 'attached.sqlite'),))
        handle.execute('INSERT INTO pending VALUES(42)'); handle.execute('SAVEPOINT caller')
        result = ADMINISTRATION.apply(client, ADMINISTRATION.plan(wanted), connection=handle)
        assert result['native_outcome'] == 'staged' and handle.in_transaction
        assert ADMINISTRATION.validate_operation_post_state(client, {
            **ADMINISTRATION.plan(wanted), 'provider_result': result, '_provider_session_handle': handle})['confirmed']
        if module in {'fts4aux', 'fts5vocab'}:
            assert handle.execute('SELECT term FROM temp."created:雪" WHERE term=\'native\'').fetchall()
        else:
            handle.execute('INSERT INTO attached."created:雪" VALUES(\'native token\')')
            assert handle.execute('SELECT body FROM attached."created:雪"').fetchall() == [('native token',)]
        handle.execute('ROLLBACK TO caller')
        assert handle.execute('SELECT * FROM pending').fetchall() == [(42,)]
        assert not handle.execute('SELECT name FROM ' + schema + '.sqlite_schema WHERE name=\'created:雪\'').fetchall()
        handle.rollback()
    finally:
        client.close()


@pytest.mark.parametrize('failure', ['native', 'denied', 'postimage', 'lost_commit', 'stale', 'busy'])
def test_creation_refusal_atomicity_and_commit_uncertainty(tmp_path, failure):
    path = tmp_path / 'live.sqlite'; seed(path); client = _create_client()
    wanted = request(tmp_path, 'fts5', ['body'], {'detail': 'invalid'} if failure == 'native' else {})
    planned = ADMINISTRATION.plan(wanted); connect = client._connect
    writer = None
    try:
        if failure == 'stale':
            with closing(sqlite3.connect(path)) as observer:
                observer.execute('CREATE TABLE "created:雪"(sentinel)'); observer.commit()
        if failure == 'busy':
            writer = sqlite3.connect(path); writer.execute('INSERT INTO pending VALUES(99)')
        if failure in {'denied', 'postimage', 'lost_commit'}:
            class Injected:
                def __init__(self, native):
                    self.native = native
                    if failure == 'denied':
                        native.set_authorizer(lambda code, *_: sqlite3.SQLITE_DENY if code == sqlite3.SQLITE_CREATE_VTABLE else sqlite3.SQLITE_OK)
                def __getattr__(self, key): return getattr(self.native, key)
                def execute(self, source, *args):
                    result = self.native.execute(source, *args)
                    if failure == 'postimage' and source.startswith('PRAGMA '):
                        self.native.execute('SELECT * FROM missing_native_relation')
                    return result
                def commit(self):
                    self.native.commit()
                    if failure == 'lost_commit': raise ConnectionError('Native commit succeeded; reply lost')
            client._connect = lambda payload: Injected(connect(payload))
        with pytest.raises(RelationalClientError) as error:
            ADMINISTRATION.apply(client, planned)
        assert error.value.native_outcome == ('unknown_outcome' if failure == 'lost_commit' else 'rolled_back')
        if writer:
            assert writer.in_transaction and writer.execute('SELECT * FROM pending').fetchall() == [(99,)]
            writer.rollback()
        with closing(sqlite3.connect(path)) as observer:
            actual = observer.execute("SELECT type,sql FROM sqlite_schema WHERE name='created:雪'").fetchall()
            assert bool(actual) == (failure in {'lost_commit', 'stale'})
            if failure == 'stale': assert 'sentinel' in actual[0][1]
    finally:
        if writer: writer.close()
        client.close()


def test_native_fts4_compression_callbacks_and_caller_owned_refusal(tmp_path):
    path = tmp_path / 'live.sqlite'; seed(path); client = _create_client()
    wanted = request(tmp_path, 'fts4', ['body'], {'compress': 'pack', 'uncompress': 'unpack'})
    try:
        handle = client._connect({'route': wanted['_provider_route']})
        handle.create_function('pack', 1, lambda value: value.encode('utf-8'))
        handle.create_function('unpack', 1, lambda value: value.decode('utf-8'))
        result = ADMINISTRATION.apply(client, ADMINISTRATION.plan(wanted), connection=handle)
        assert result['native_outcome'] == 'staged' and handle.in_transaction
        handle.execute('INSERT INTO "created:雪" VALUES(\'native café\')')
        assert handle.execute('SELECT typeof(c0body) FROM "created:雪_content"').fetchone() == ('blob',)
        assert handle.execute('SELECT body FROM "created:雪" WHERE "created:雪" MATCH \'native\'').fetchall() == [('native café',)]
        handle.execute('INSERT INTO pending VALUES(42)'); handle.execute('SAVEPOINT retained')
        refused = request(tmp_path, 'fts5', ['body'], {'detail': 'invalid'})
        refused['draft']['name'] = 'refused'
        with pytest.raises(RelationalClientError):
            ADMINISTRATION.apply(client, ADMINISTRATION.plan(refused), connection=handle)
        handle.execute('ROLLBACK TO retained')
        assert handle.in_transaction and handle.execute('SELECT * FROM pending').fetchall() == [(42,)]
        handle.rollback()
        assert not handle.execute("SELECT name FROM sqlite_schema WHERE name='created:雪'").fetchall()
    finally:
        client.close()


def test_fresh_native_post_state_detects_replacement_and_unknown_receipt(tmp_path):
    path = tmp_path / 'live.sqlite'; seed(path); client = _create_client()
    planned = ADMINISTRATION.plan(request(tmp_path, 'fts5', ['body'], {}))
    try:
        result = ADMINISTRATION.apply(client, planned)
        with closing(sqlite3.connect(path)) as observer:
            observer.execute('DROP TABLE "created:雪"'); observer.execute('CREATE VIRTUAL TABLE "created:雪" USING fts5(other)'); observer.commit()
        assert not ADMINISTRATION.validate_operation_post_state(client, {**planned, 'provider_result': result})['confirmed']
        assert not ADMINISTRATION.validate_operation_post_state(client, planned)['confirmed']
    finally:
        client.close()


@pytest.mark.parametrize('when', ['planning', 'application'])
def test_creation_permission_is_checked_again_before_native_dispatch(tmp_path, when):
    path = tmp_path / 'live.sqlite'; seed(path); client = _create_client()
    class Permissions:
        denied = when == 'planning'
        def allows(self, _permission, _scope='resource'): return not self.denied
        def require(self, _permission, _scope='resource'):
            if self.denied: raise PermissionError('Owned native permission refusal')
    permissions = Permissions()
    context = SimpleNamespace(endpoint_id='owned', mode='embedded_sqlite', runtime_verification_state='verified',
        verified_runtime_family='sqlite', declared_runtime_family='sqlite',
        effective_permissions=frozenset({'data_read', 'data_write', 'administer', 'filesystem'}))
    visual = ProviderVisualAdministration(context, permissions, 'sqlite', '3.53.0', client)
    wanted = request(tmp_path, 'fts5', ['body'], {})
    try:
        if when == 'planning':
            with pytest.raises(PermissionError): visual.plan(wanted)
        else:
            planned = visual.plan(wanted)
            permissions.denied = True
            client._connect = Mock(side_effect=AssertionError('Native dispatch after permission revocation'))
            with pytest.raises(PermissionError):
                visual.apply({'plan_id': planned['plan_id'], 'plan_digest': planned['plan_digest'], 'confirmed': True})
            client._connect.assert_not_called()
        with closing(sqlite3.connect(path)) as observer:
            assert not observer.execute("SELECT name FROM sqlite_schema WHERE name='created:雪'").fetchall()
    finally:
        client.close()


def test_constructor_form_and_typed_admission(tmp_path):
    form = ADMINISTRATION._form('virtual-table', 'create')
    assert {item['value'] for item in next(field for field in form['fields'] if field['field_id'] == 'module')['options']} == set(MODULES)
    for module, columns, options in [
        ('fts3', ['body'], {'content': 'owner'}),
        ('fts5', ['body'], {'raw_sql': 'DROP TABLE owner'}),
        ('fts5', [{'name': 'body', 'unindexed': 'yes'}], {}),
        ('fts5', ['body'], {'prefix': [True]}),
        ('fts4aux', [], {'database': 'attached', 'table': 'base4'}),
        ('fts5vocab', ['arbitrary'], {'table': 'base5'}),
        ('sqlite_dbpage', [], {}),
    ]:
        wanted = request(tmp_path, module, columns, options)
        assert ADMINISTRATION.validate(wanted)['errors']
        with pytest.raises(RelationalClientError): ADMINISTRATION.plan(wanted)


def test_no_private_connection_temp_success_and_quoted_input_cannot_add_sql(tmp_path):
    path = tmp_path / 'live.sqlite'; seed(path); client = _create_client()
    try:
        planned = ADMINISTRATION.plan(request(tmp_path, 'fts5', ['body'], {}, parent='temp'))
        with pytest.raises(RelationalClientError, match='retained session'):
            ADMINISTRATION.apply(client, planned)
        wanted = request(tmp_path, 'fts5', ['body); DROP TABLE owner; --'],
                         {'content': "owner'); DROP TABLE pending; --"})
        result = ADMINISTRATION.apply(client, ADMINISTRATION.plan(wanted))
        assert result['native_virtual_table']['columns'][0]['name'] == 'body); DROP TABLE owner; --'
        with closing(sqlite3.connect(path)) as observer:
            assert observer.execute('SELECT count(*) FROM owner').fetchone() == (1,)
            assert observer.execute('SELECT count(*) FROM pending').fetchone() == (0,)
    finally:
        client.close()
