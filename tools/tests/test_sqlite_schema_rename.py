"""Native rename design generation, DDN roundtrip, owned review and effects."""
from contextlib import closing
from dataclasses import dataclass
import json
import sqlite3
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from pgadmin.cdeadmin.operations.store import JsonOperationStore
from pgadmin.cdeadmin.providers.sqlite.provider import SQLiteProvider,_create_client
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.service import ProviderWorkspaceService,ProviderWorkspaceError


@pytest.mark.parametrize('kind',['table','column','chain'])
@pytest.mark.parametrize('failure',[None,'stale','postimage','ambiguous','collision','busy','lost_commit','existing_fk'])
def test_native_rename_design_and_review_preserve_data_and_rewrite_dependencies(tmp_path,kind,failure):
    @dataclass(frozen=True)
    class Context:
        endpoint_id:str='endpoint'
        profile_id:str='sqlite-native'
    path=tmp_path/'native.sqlite'
    with closing(sqlite3.connect(path)) as connection:
        connection.executescript('''
            PRAGMA foreign_keys=ON;
            CREATE TABLE parent(id INTEGER PRIMARY KEY AUTOINCREMENT,note TEXT UNIQUE,other TEXT);
            CREATE TABLE child(id INTEGER PRIMARY KEY,parent_id INTEGER REFERENCES parent(id));
            CREATE TABLE audit(note TEXT);
            CREATE INDEX by_note ON parent(note DESC);
            CREATE VIEW projection AS SELECT id,note FROM parent;
            CREATE TRIGGER parent_touch AFTER UPDATE ON parent BEGIN INSERT INTO audit VALUES(new.note); END;
            CREATE TRIGGER child_touch AFTER INSERT ON child BEGIN UPDATE parent SET note=note WHERE id=new.parent_id; END;
            INSERT INTO parent VALUES(9007199254740993,'雪','kept');
            INSERT INTO parent(id,note) VALUES(9007199254740999,'high');
            DELETE FROM parent WHERE id=9007199254740999;
            INSERT INTO child VALUES(1,9007199254740993);
            DELETE FROM audit;
        ''')
        if failure=='ambiguous':connection.execute('CREATE VIEW ambiguous_reference AS SELECT note FROM parent JOIN child')
        connection.commit()
        if failure=='existing_fk':
            connection.execute('PRAGMA foreign_keys=OFF');connection.execute('INSERT INTO child VALUES(2,9999999)');connection.commit()
        original=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
    provider=SQLiteProvider(Context(),SimpleNamespace(require=Mock()),_create_client())
    route={'database':str(path),'filesystem_root':str(tmp_path),'timeout':.05}
    try:
        captured=provider.capture_catalog(route,include_system=False)
        baseline=json.dumps(build_export(captured['resources'],endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite')['snapshot'])
        renames=([{'kind':'table','table':'parent','to':'renamed:雪'}] if kind=='table' else
            [{'kind':'column','table':'parent','from':'note','to':'renamed:雪'}] if kind=='column' else
            [{'kind':'table','table':'parent','to':'renamed:雪'}, {'kind':'column','table':'renamed:雪','from':'note','to':'body:雪'}])
        if failure=='collision':renames=[{'kind':'table','table':'parent','to':'child'}]
        if failure=='ambiguous':renames=[{'kind':'column','table':'parent','from':'note','to':'parent_id'}]
        service=object.__new__(ProviderWorkspaceService);service.endpoint_service=Mock()
        service.endpoint_service.workspace.return_value=(Context(),{'route':route},None)
        service.endpoint_service.provider_registry.resolve.return_value=SimpleNamespace(instance=provider)
        service.operation_bus=SimpleNamespace(store=JsonOperationStore(tmp_path/'operations.json'))
        service.resource_service=Mock();service._principal_id=lambda _server:'owner'
        generated_request={'database_target_id':'file','baseline':baseline,'renames':renames}
        if failure in {'collision','ambiguous'}:
            with pytest.raises(ProviderWorkspaceError,match='Native SQLite rename refused'):
                service.sqlite_schema_rename_design('owned',generated_request)
            with closing(sqlite3.connect(path)) as connection:
                assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
            return
        generated=service.sqlite_schema_rename_design('owned',generated_request)
        documents={**generated_request,'desired':json.dumps(generated['snapshot'])}
        displayed=service.sqlite_schema_plan('owned',documents)
        assert displayed['ready_for_review'],displayed
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
            assert connection.execute('SELECT * FROM audit').fetchall()==[]
        reviewed=service.sqlite_schema_application('owned','sqlite_schema_review',{**documents,'execution_sha256':displayed['execution_sha256']})
        request={'database_target_id':'file',**{key:reviewed[key] for key in ('review_id','review_digest')},'confirmed':True}
        if failure=='stale':
            with closing(sqlite3.connect(path)) as connection:
                connection.execute('CREATE VIEW appeared AS SELECT note FROM parent');connection.commit()
                original=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        if failure=='busy':
            writer=sqlite3.connect(path)
            try:
                writer.execute("INSERT INTO audit VALUES('pending')");writer.execute('SAVEPOINT retained')
                result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
                assert writer.in_transaction and writer.execute('SELECT * FROM audit').fetchall()==[('pending',)]
                writer.execute('ROLLBACK TO retained');writer.rollback()
            finally:writer.close()
        elif failure=='lost_commit':
            connect=provider.client._connect
            class LostCommit:
                def __init__(self,connection):self.connection=connection
                def __getattr__(self,name):return getattr(self.connection,name)
                def commit(self):
                    self.connection.commit();raise ConnectionError('Owned loss after actual native commit')
            provider.client._connect=Mock(side_effect=lambda payload:LostCommit(connect(payload)))
            result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        elif failure=='postimage':
            # Change a post-dispatch observation while preserving the actual
            # engine execution. The complete native rename must roll back.
            from pgadmin.cdeadmin.workspace import sqlite_rename
            actual=sqlite_rename.model
            def altered(connection,baseline):
                value=actual(connection,baseline)
                owned=any(row[1]=='main' and row[2]==str(path) for row in connection.execute('PRAGMA database_list'))
                if owned and (connection.execute('SELECT name FROM sqlite_schema WHERE name=?',('renamed:雪',)).fetchone() or kind=='column' and any(row[1]=='renamed:雪' for row in connection.execute('PRAGMA table_xinfo(parent)'))):
                    value['rows']={identity:row for identity,row in value['rows'].items() if row['kind']!='view'}
                return value
            with pytest.MonkeyPatch.context() as patch:
                patch.setattr(sqlite_rename,'model',altered)
                result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        else:result=service.sqlite_schema_application('owned','sqlite_schema_apply',request)
        expected='not_dispatched' if failure in {'stale','busy'} else 'unknown_outcome' if failure=='lost_commit' else 'rolled_back' if failure=='postimage' else 'committed'
        assert result['state']==expected,result
        provider.client._connect=Mock(side_effect=AssertionError('native rename review was replayed'))
        assert service.sqlite_schema_application('owned','sqlite_schema_apply',request)['state']==expected
        provider.client._connect.assert_not_called()
        with closing(sqlite3.connect(path)) as connection:
            assert connection.execute('SELECT * FROM audit').fetchall()==[]
            violations=connection.execute('PRAGMA foreign_key_check').fetchall()
            if failure=='existing_fk':assert violations==[('child',2,'parent' if kind=='column' else 'renamed:雪',0)]
            else:assert violations==[]
            if failure in {'stale','busy','postimage'}:
                assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
                assert connection.execute('SELECT * FROM parent').fetchall()==[(9007199254740993,'雪','kept')]
            else:
                if failure!='lost_commit':assert result['outcome']['rediscovery_verified']
                table='parent' if kind=='column' else 'renamed:雪'
                column='note' if kind=='table' else 'renamed:雪' if kind=='column' else 'body:雪'
                assert connection.execute('SELECT rowid,* FROM "'+table+'"').fetchall()==[(9007199254740993,9007199254740993,'雪','kept')]
                assert connection.execute('SELECT * FROM projection').fetchall()==[(9007199254740993,'雪')]
                assert connection.execute('SELECT seq FROM sqlite_sequence WHERE name=?',(table,)).fetchone()==(9007199254740999,)
                connection.execute('UPDATE "'+table+'" SET "'+column+'"=\'updated\'')
                assert connection.execute('SELECT * FROM audit').fetchall()==[('updated',)]
                assert connection.execute('PRAGMA foreign_key_list(child)').fetchone()[2]==table
                assert connection.execute('PRAGMA index_xinfo(by_note)').fetchone()[2]==column
    finally:provider.close()
