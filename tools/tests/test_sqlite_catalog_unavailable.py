"""Native unavailable relation facts remain distinct from an empty catalog."""
from contextlib import closing
from types import SimpleNamespace
from unittest.mock import Mock
import sqlite3

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client,_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export


@pytest.mark.parametrize('case',['authorizer','fts-module-error'])
def test_native_metadata_refusal_preserves_other_objects_and_caller_transaction(tmp_path,case):
    path=tmp_path/'observations.sqlite'
    with closing(sqlite3.connect(path)) as seed:
        seed.executescript('CREATE TABLE healthy(id INTEGER PRIMARY KEY,body TEXT); CREATE TABLE blocked(id INTEGER); INSERT INTO healthy VALUES(1,\'committed\');')
        if case=='fts-module-error':
            seed.execute('CREATE VIRTUAL TABLE bad_fts USING fts5(body)')
            seed.execute('UPDATE bad_fts_config SET v=999 WHERE k=\'version\'')
            seed.execute('CREATE VIEW bad_view AS SELECT * FROM bad_fts')
        seed.commit()
    caller=sqlite3.connect(path);caller.execute("INSERT INTO healthy VALUES(2,'pending')");caller.execute('SAVEPOINT retained')
    provider=SQLiteProvider(SimpleNamespace(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path)}
    if case=='authorizer':
        connect=provider.client._connect
        def guarded(payload):
            connection=connect(payload)
            connection.set_authorizer(lambda action,name,target,*_args:sqlite3.SQLITE_DENY if action==sqlite3.SQLITE_PRAGMA and name=='table_xinfo' and target=='blocked' else sqlite3.SQLITE_OK)
            return connection
        provider.client._connect=guarded
    try:
        captured=provider.capture_catalog(route,include_system=False);resources=captured['resources'];by_id={row['resource_id']:row for row in resources}
        assert captured['complete'] is False
        assert caller.in_transaction and caller.execute('SELECT count(*) FROM healthy').fetchone()==(2,)
        with closing(sqlite3.connect(path)) as observer:assert observer.execute('SELECT count(*) FROM healthy').fetchone()==(1,)
        healthy=by_id[_resource_id('table',['main'],'healthy')]
        assert healthy['native']['column_observation']['available'] and [item['name'] for item in healthy['native']['columns']]==['id','body']
        identity=_resource_id('table',['main'],'blocked') if case=='authorizer' else _resource_id('fts-table',['main'],'bad_fts')
        denied=by_id[identity]
        assert denied['native']['ddl'] and denied['native']['column_observation']['available'] is False
        assert denied['native']['column_observation']['native_error_code']==(sqlite3.SQLITE_AUTH if case=='authorizer' else sqlite3.SQLITE_ERROR)
        if case=='fts-module-error':
            assert denied['native']['module_observation']['registered_in_session'] is True
            assert denied['native']['fts_configuration']['native_format_version']==999
            assert denied['native']['fts_configuration']['restorable'] is False
            assert by_id[_resource_id('view',['main'],'bad_view')]['native']['view_binding_observation']['available'] is False
        exported=build_export(resources,endpoint_id='endpoint',target_id='file',generation=captured['generation'],engine='sqlite')
        assert exported['provenance']['coverage']=='partial'
        assert any(identity in observation.get('unavailable_resource_ids',[]) for observation in exported['provenance']['catalog_observations'])
        assert any('unavailable' in warning for warning in exported['provenance']['warnings'])
        caller.execute('ROLLBACK TO retained');caller.rollback()
    finally:provider.close();caller.close()
