"""Native AST scopes and isolated CLI admission for FTS dependencies."""
from contextlib import closing
import sqlite3

import pytest

from pgadmin.cdeadmin.workspace.sqlite_native_rebind import rewrite, program


def fixture(connection, source):
    rows = [
        {'kind': 'table', 'name': 'owner', 'native': {'ddl': 'CREATE TABLE owner(id INTEGER PRIMARY KEY,body,tag)'}},
        {'kind': 'fts-table', 'name': 'search', 'native': {'ddl': "CREATE VIRTUAL TABLE search USING fts5(body,tag,content='owner')"}},
        {'kind': 'view', 'name': 'projection', 'native': {'ddl': source}}]
    for row in rows: connection.execute(row['native']['ddl'])
    return rows


@pytest.mark.parametrize('source,expected',[
    ("CREATE VIEW projection AS SELECT s.body, s.tag, 'body search' AS literal FROM search('native') AS s",
     "CREATE VIEW projection AS SELECT s.\"text:雪\", s.tag, 'body search' AS literal FROM \"found:雪\"('native') AS s"),
    ("CREATE VIEW projection AS WITH search(body) AS (VALUES('unchanged')) SELECT body FROM search",
     "CREATE VIEW projection AS WITH search(body) AS (VALUES('unchanged')) SELECT body FROM search"),
    ("CREATE VIEW projection(body) AS SELECT body FROM search('native') WHERE body LIKE '%body%'",
     "CREATE VIEW projection(body) AS SELECT \"text:雪\" FROM \"found:雪\"('native') WHERE \"text:雪\" LIKE '%body%'"),
    ("CREATE VIEW projection AS SELECT search.body FROM search('native') AS search",
     "CREATE VIEW projection AS SELECT search.\"text:雪\" FROM \"found:雪\"('native') AS search"),
])
def test_native_ast_preserves_unbound_names_and_aliases(source,expected):
    with closing(sqlite3.connect(':memory:')) as connection:
        rows=fixture(connection,source)
        before=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()
        changes,runtime=rewrite(connection,rows,[
            {'kind':'column','table':'owner','from':'body','to':'intermediate'},
            {'kind':'column','table':'owner','from':'intermediate','to':'text:雪'},
            {'kind':'table','table':'search','to':'intermediate_search'},
            {'kind':'table','table':'intermediate_search','to':'found:雪'}],
            [{'source_name':'search','column_renames':[
                {'from':'body','to':'intermediate'},{'from':'intermediate','to':'text:雪'},
                {'from':'search','to':'intermediate_search'},{'from':'intermediate_search','to':'found:雪'}]}])
        assert changes[0][1]==expected
        assert runtime['version']==sqlite3.sqlite_version and len(runtime['sha256'])==64
        assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
        # Internal test functions have never been enabled in the caller.
        with pytest.raises(sqlite3.OperationalError,match='no such function'):
            connection.execute("SELECT sqlite_rename_column(NULL,NULL,NULL,NULL,NULL,0,NULL,1,0)")


def test_native_schema_comments_and_quoted_newlines_cannot_become_shell_commands(tmp_path):
    marker=tmp_path/'must-not-exist'
    source=("CREATE VIEW projection AS SELECT s.body, 'quoted\n.system touch "+str(marker)+
            "\n' AS literal /* comment\n.system touch "+str(marker)+"\n.nonce invalid\n*/ FROM search('native') AS s;")
    with closing(sqlite3.connect(':memory:')) as connection:
        rows=fixture(connection,source)
        changes,_runtime=rewrite(connection,rows,[{'kind':'column','table':'owner','from':'body','to':'text'}],
            [{'source_name':'search','column_renames':[{'from':'body','to':'text'}]}])
        assert changes[0][1]==source.replace('s.body','s."text"')
    assert not marker.exists()


def test_explicit_missing_native_binary_does_not_fall_back(monkeypatch,tmp_path):
    monkeypatch.setenv('CDEADMIN_SQLITE_BINARY',str(tmp_path/'absent'))
    with pytest.raises(ValueError,match='unavailable'):program()


def test_unqualified_native_runtime_is_refused_before_returning_definitions(monkeypatch):
    from pgadmin.cdeadmin.workspace import sqlite_native_rebind
    # Lost/corrupt subprocess replies must never become reviewed definitions.
    monkeypatch.setattr(sqlite_native_rebind,'observe_process',lambda *_args,**_kwargs:{
        'return_code':0,'cleanup_confirmed':True,'stdout_bytes':100,
        'stdout':b'[{"probe":-1,"rewritten":"old","version":"3.53.0","source_id":"wrong"}]'})
    with closing(sqlite3.connect(':memory:')) as connection:
        rows=fixture(connection,"CREATE VIEW projection AS SELECT body FROM search('native')")
        with pytest.raises(ValueError,match='unqualified reply'):
            rewrite(connection,rows,[{'kind':'column','table':'owner','from':'body','to':'text'}],
                [{'source_name':'search','column_renames':[{'from':'body','to':'text'}]}])


def test_native_span_probe_can_use_an_independent_empty_schema_without_changing_source_sql():
    sources=[
        {'kind':'table','name':'owner','native':{'ddl':'CREATE TABLE owner(tag,body)'}},
        {'kind':'view','name':'mapped','native':{'ddl':'CREATE VIEW mapped(doc,tag,body) AS SELECT s.rowid AS doc,s.* FROM owner AS s'}},
        {'kind':'trigger','name':'inserted','native':{'ddl':'CREATE TRIGGER inserted INSTEAD OF INSERT ON mapped BEGIN INSERT INTO owner(rowid,tag,body) VALUES(new.doc,new.tag,new.body); END'}}]
    private=[
        {'kind':'table','name':'owner','native':{'ddl':'CREATE TABLE owner(tag,body,rowid INTEGER PRIMARY KEY)'}},
        {'kind':'view','name':'mapped','native':{'ddl':'CREATE VIEW mapped(doc,tag,body) AS SELECT NULL,NULL,NULL WHERE 0'}}]
    with closing(sqlite3.connect(':memory:')) as connection:
        for row in sources:connection.execute(row['native']['ddl'])
        before=connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall();edits={}
        result,_runtime=rewrite(connection,sources,[],[],schema_declarations=private,
            native_targets=[('column','owner',2,'oid')],edits_out=edits)
        assert result[0][1]=='CREATE VIEW mapped(doc,tag,body) AS SELECT s."oid" AS doc,s.* FROM owner AS s'
        assert 'INSERT INTO owner("oid",tag,body)' in result[1][1]
        assert edits[('view','mapped')] and edits[('trigger','inserted')]
        assert connection.execute('SELECT name,sql FROM sqlite_schema ORDER BY name').fetchall()==before
