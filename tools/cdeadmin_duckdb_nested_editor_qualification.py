"""Capture native DuckDB container bindings for the real editor completion gate."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'web'),str(ROOT/'tools'),str(ROOT)]


def qualify(output):
    import duckdb
    from pgadmin.cdeadmin.providers.native_editor import metadata
    if duckdb.__version__!='1.5.2':raise ValueError('Select native DuckDB1.5.2')
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside the source checkout')
    output.mkdir(parents=True,exist_ok=False,mode=0o700)
    proof={'complete':False,'native_version':duckdb.__version__,'history_testing':'not run'}
    paths=['tools/cdeadmin_duckdb_nested_editor_qualification.py',
        'web/pgadmin/cdeadmin/providers/native_editor.py',
        'web/pgadmin/cdeadmin/providers/duckdb/editor_type_rules.py']+['web/pgadmin/static/js/cdeadmin_ui/editors/'+name for name in (
        'nativeCompletion.js','nativeScopes.js','nativeLexing.js','duckdbNestedTypes.js')]
    proof['source_sha256']={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}
    try:
        with duckdb.connect() as connection:
            connection.execute('CREATE TABLE one(items STRUCT("Field ü" BIGINT)[], fixed STRUCT("Field ü" BIGINT)[2], lookup MAP(VARCHAR,STRUCT("Field ü" BIGINT)), matrix STRUCT("Field ü" BIGINT)[][])')
            connection.execute('INSERT INTO one VALUES ([struct_pack("Field ü":=7)], [struct_pack("Field ü":=8),struct_pack("Field ü":=9)], map([\'key\'],[struct_pack("Field ü":=10)]), [[struct_pack("Field ü":=11)]])')
            connection.execute('CREATE VIEW tuple_values AS SELECT row(42::BIGINT,struct_pack("Field ü":=12::BIGINT),[struct_pack("Field ü":=13::BIGINT)]) AS "positional"')
            connection.execute('CREATE TABLE native_names("select" STRUCT("Field ü" BIGINT),array_extract STRUCT("Field ü" BIGINT)[],"value" STRUCT("Field ü" BIGINT))')
            connection.execute('INSERT INTO native_names VALUES(struct_pack("Field ü":=17),[struct_pack("Field ü":=18)],struct_pack("Field ü":=19))')
            connection.execute('CREATE TYPE user_pair AS STRUCT("Field ü" BIGINT)')
            connection.execute('CREATE TABLE union_tbl(u UNION(left_branch STRUCT("Field ü" BIGINT), right_branch VARCHAR))')
            connection.execute('INSERT INTO union_tbl VALUES (union_value(left_branch := struct_pack("Field ü" := 23)))')
            connection.execute('BEGIN');connection.execute('INSERT INTO one DEFAULT VALUES')
            observed=metadata(connection,'duckdb')
            cases=[]
            for marked in [
                'SELECT n.items[1].| FROM one n','SELECT n.fixed[1].| FROM one n',
                "SELECT n.lookup['key'].| FROM one n",'SELECT n.matrix[1][1].| FROM one n',
                'SELECT n.items[:][1].| FROM one n','SELECT n.fixed[1:2][1].| FROM one n',
                'SELECT items[1].| FROM one','WITH q AS (SELECT n.items[1] AS item FROM one n) SELECT q.item.| FROM q',
                'WITH q AS (SELECT n.lookup AS value FROM one n) SELECT q.value[\'key\'].| FROM q',
                'SELECT q.item.| FROM (SELECT n.fixed[1] AS item FROM one n) q',
                'SELECT n."positional"[2].| FROM tuple_values n',
                'SELECT n."positional"[3][1].| FROM tuple_values n',
                'WITH q AS (SELECT n."positional"[2] AS part FROM tuple_values n) SELECT q.part.| FROM q',
                'SELECT array_extract[1].| FROM native_names',
                'SELECT n.select.| FROM native_names n',
                'WITH q AS (SELECT n.select AS part FROM native_names n) SELECT q.part.| FROM q',
                'SELECT n.value.| FROM native_names n',
                'SELECT (n.items[1]).| FROM one n',
                'SELECT ((n.items)[1]).| FROM one n',
                'SELECT (((n.items)))[1].| FROM one n',
                'SELECT (n.fixed)[1].| FROM one n',
                "SELECT (n.lookup)['key'].| FROM one n",
                'SELECT ((n.matrix)[1])[1].| FROM one n',
                'SELECT (n.items[:])[1].| FROM one n',
                'SELECT (items[1]).| FROM one',
                'SELECT (/* receiver */ n.items[1]).| FROM one n',
                'WITH q AS (SELECT (n.items[1]) AS part FROM one n) SELECT q.part.| FROM q',
                'WITH q(part) AS (SELECT ((n.items))[1] FROM one n) SELECT (q.part).| FROM q',
                'WITH q(ignored,part) AS (SELECT typeof(n.items),((n.items))[1] FROM one n) SELECT q.part.| FROM q',
                'SELECT q.part.| FROM (SELECT ((n.fixed)[1]) AS part FROM one n) q',
                'SELECT (n."positional")[2].| FROM tuple_values n',
                'SELECT ((n."positional")[3])[1].| FROM tuple_values n',
                'WITH q(part) AS (SELECT (n."positional")[2] FROM tuple_values n) SELECT q.part.| FROM q',
            ] + [f'SELECT {name}(n.items[1]).| FROM one n WHERE n.items IS NOT NULL'
                 for name in ('min','max','first','last','any_value','arbitrary')] + [
                f'SELECT {name}(n.items[1])[1].| FROM one n WHERE n.items IS NOT NULL'
                for name in ('list','array_agg')] + [
                'SELECT max(n.items[1],2)[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT min(n.items[1],2)[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT main.max(n.items[1]).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT system.main.max(n.items[1]).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT (MAX(n.items[1])).| FROM one n WHERE n.items IS NOT NULL',
                'WITH q AS (SELECT max(n.items[1]) AS part FROM one n) SELECT q.part.| FROM q',
                'WITH q(part) AS (SELECT list(n.items[1]) FROM one n) SELECT q.part[1].| FROM q',
                'SELECT q.part.| FROM (SELECT first(n.items[1]) AS part FROM one n) q',
                'SELECT (max(n.items[1]) FILTER (WHERE n.items IS NOT NULL)).| FROM one n',
                'SELECT (max(n.items[1]) OVER ()).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT (list(n.items[1]) FILTER (WHERE true) OVER (PARTITION BY n.items))[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT (max(n.items[1],2) OVER w)[1].| FROM one n WHERE n.items IS NOT NULL WINDOW w AS ()',
                'SELECT (first(n.items[1]) OVER "window ü").| FROM one n WHERE n.items IS NOT NULL WINDOW "window ü" AS ()',
                'SELECT max(DISTINCT n.items[1]).| FROM one n',
                'SELECT (list(ALL n.items[1]) OVER (ORDER BY n.items ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW))[1].| FROM one n WHERE n.items IS NOT NULL',
                'WITH q AS (SELECT (max(n.items[1]) FILTER (WHERE true) OVER ()) AS part FROM one n WHERE n.items IS NOT NULL) SELECT q.part.| FROM q',
                'SELECT max(n.items[1] ORDER BY n.items).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT list(n.items[1] ORDER BY n.items DESC NULLS LAST)[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT arg_max(n.items[1], 1).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT arg_min(n.items[1], 1, 2)[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT max_by(n.items[1], 1).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT min_by(n.items[1], 1).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT list_extract(n.items, 1).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT list_element(n.items, 1).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT list_slice(n.items, 1, 1)[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT list_reverse(n.items)[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT list_distinct(n.items)[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT list_sort(n.items)[1].| FROM one n WHERE n.items IS NOT NULL',
                'SELECT flatten(n.matrix)[1].| FROM one n WHERE n.matrix IS NOT NULL',
                "SELECT map_extract(n.lookup, 'key')[1].| FROM one n WHERE n.lookup IS NOT NULL",
                "SELECT map_extract_value(n.lookup, 'key').| FROM one n WHERE n.lookup IS NOT NULL",
                'SELECT map_values(n.lookup)[1].| FROM one n WHERE n.lookup IS NOT NULL',
                'SELECT map_entries(n.lookup)[1]."value".| FROM one n WHERE n.lookup IS NOT NULL',
                'SELECT struct_pack(wrapped := n.items[1]).wrapped.| FROM one n WHERE n.items IS NOT NULL',
                'SELECT row(42, n.items[1])[2].| FROM one n WHERE n.items IS NOT NULL',
                "SELECT union_extract(u.u, 'left_branch').| FROM union_tbl u",
                'SELECT coalesce(n.items[1], n.fixed[1]).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT ifnull(n.items[1], n.fixed[1]).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT nullif(n.items[1], NULL).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT CAST(n.items[1] AS STRUCT("Field ü" BIGINT)).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT TRY_CAST(n.items[1] AS user_pair).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT (n.items[1]::user_pair).| FROM one n WHERE n.items IS NOT NULL',
                'SELECT (SELECT m.items[1] FROM one m WHERE m.items IS NOT NULL LIMIT 1).|',
                'SELECT (SELECT n.items[1]).| FROM one n WHERE n.items IS NOT NULL',
                'WITH q AS (SELECT (SELECT m.items[1] FROM one m WHERE m.items IS NOT NULL LIMIT 1) AS part) SELECT q.part.| FROM q',
            ]:
                sql=marked.replace('|','"Field ü"');query=connection.execute(sql)
                assert str(query.description[0][1])=='BIGINT'
                values=query.fetchall();assert values[0][0] is not None
                cases.append({'marked':marked,'native_sql':sql,'native_type':'BIGINT','native_values':values,
                    'expected':[{'label':'Field ü','apply':'"Field ü"','detail':'BIGINT'}]})
            assert connection.execute('SELECT count(*) FROM one').fetchone()[0]==2
            connection.execute('ROLLBACK')
            assert connection.execute('SELECT count(*) FROM one').fetchone()[0]==1
            (output/'native-editor-fixture.json').write_text(json.dumps({'metadata':observed,'cases':cases},ensure_ascii=False,indent=2)+'\n',encoding='utf8')
            proof.update(complete=True,native_cases=len(cases),pending_transaction_preserved=True,
                qualification_scope='native observed metadata and bound value expressions; pair with nativeCompletionScope Jest qualification')
    finally:(output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    qualify(parser.parse_args().evidence)
