"""Observe inferred labels through native ordinary/FTS view dependency chains."""
from contextlib import closing
import sqlite3

import pytest

from pgadmin.cdeadmin.providers.sqlite.provider import _resources,_resource_id
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.sqlite_rename import generate,schema,model


@pytest.mark.parametrize('fts',[False,True])
@pytest.mark.parametrize('projection',['s.body','s.*',"s.body||' literal body'",'upper(s.body)'])
def test_native_inferred_view_names_follow_actual_projection_ordinals(fts,projection):
    quote=lambda value:'"'+value.replace('"','""')+'"'
    with closing(sqlite3.connect(':memory:')) as connection:
        connection.execute('CREATE TABLE owner(body TEXT)')
        connection.execute("INSERT INTO owner VALUES('native token')")
        if fts:
            connection.execute("CREATE VIRTUAL TABLE search USING fts5(body,content='owner')")
            connection.execute("INSERT INTO search(search) VALUES('rebuild')")
        source="search('native')" if fts else 'owner'
        connection.execute('CREATE VIEW first AS SELECT '+projection+' FROM '+source+' AS s')
        label=connection.execute('PRAGMA table_xinfo(first)').fetchone()[1]
        connection.execute('CREATE VIEW second AS SELECT '+quote(label)+' FROM first')
        connection.execute('CREATE VIEW third AS SELECT '+quote(label)+' FROM second')
        connection.execute('CREATE VIEW boundary(stable) AS SELECT '+quote(label)+' FROM third')
        expected=connection.execute('SELECT * FROM boundary').fetchall();connection.commit()
        baseline=build_export(_resources(connection,{}),endpoint_id='endpoint',target_id='file',generation='g',engine='sqlite',native_model=True)
        original=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        desired,_,stages=generate(baseline,[{'kind':'column','table':'owner','from':'body','to':'renamed:雪'}],
            [_resource_id('fts-table',['main'],'search')] if fts else [])
        assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==original
        connection.execute('BEGIN IMMEDIATE')
        for stage in stages:connection.execute(stage)
        assert schema(model(connection,baseline))==schema(desired)
        assert connection.execute('SELECT * FROM boundary').fetchall()==expected
        assert connection.execute('PRAGMA table_xinfo(boundary)').fetchone()[1]=='stable'
        assert connection.execute('SELECT * FROM owner').fetchall()==[('native token',)]
        connection.commit()


@pytest.mark.parametrize('kind',['view','trigger'])
def test_final_dependency_preparation_does_not_reuse_a_stale_explain_program(kind):
    from pgadmin.cdeadmin.workspace.sqlite_schema_apply import _validate_dependencies
    with closing(sqlite3.connect(':memory:')) as connection:
        connection.execute('CREATE TABLE owner(body)')
        if kind=='view':
            connection.execute('CREATE VIEW retained AS SELECT body FROM owner')
            observed={'retained':{'resource_kind':'view','display_name':'retained','native':{}}}
            changed='CREATE VIEW retained AS SELECT missing FROM owner'
        else:
            connection.execute('CREATE TRIGGER retained AFTER INSERT ON owner BEGIN SELECT body FROM owner; END')
            observed={'retained':{'resource_kind':'trigger','display_name':'retained','display_path':['main','owner','retained'],'native':{}}}
            changed='CREATE TRIGGER retained AFTER INSERT ON owner BEGIN SELECT missing FROM owner; END'
        _validate_dependencies(connection,observed)
        connection.execute('DROP '+kind+' retained');connection.execute(changed)
        with pytest.raises(sqlite3.Error,match='missing'):_validate_dependencies(connection,observed)
