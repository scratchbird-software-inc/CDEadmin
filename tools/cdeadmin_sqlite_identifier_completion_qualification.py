"""Native SQLite3.53 identifier roles, retained work and real insertion fixtures."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT),str(ROOT/'web'),str(ROOT/'tools')]
import config  # noqa: F401,E402


def qualify(output):
    from tools.cdeadmin_native_editor_gate import provider
    output=Path(output).resolve()
    if output==ROOT or ROOT in output.parents:raise ValueError('Evidence belongs outside source')
    output.mkdir(parents=True,exist_ok=False)
    paths=['web/pgadmin/cdeadmin/providers/native_editor.py','web/pgadmin/cdeadmin/providers/sqlite/identifier_keywords.py',
        'web/pgadmin/static/js/cdeadmin_ui/editors/nativeLexing.js','web/pgadmin/static/js/cdeadmin_ui/editors/nativeScopes.js']
    paths.append(str(Path(__file__).relative_to(ROOT)))
    proof={'complete':False,'history_testing':'not run','source_sha256':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in paths}}
    instance=None
    try:
        assert sqlite3.sqlite_version=='3.53.0'
        path=output/'native.sqlite';instance,route=provider('sqlite',{'database':str(path),'filesystem_root':str(output)})
        session=instance.open_session({'route':route});handle=instance._sessions[session['session_id']].handle
        handle.execute('CREATE TABLE "key"(key INTEGER PRIMARY KEY,filter INTEGER,over INTEGER,window INTEGER,current_date TEXT,n INTEGER,"ſelect" INTEGER) WITHOUT ROWID')
        handle.execute("INSERT INTO \"key\" VALUES(1,2,3,4,'owned column',6,7)")
        for name,value in [('offset',8),('ſelect',9),('lateral',10)]:
            handle.execute('CREATE TABLE "'+name+'"(value INTEGER PRIMARY KEY) WITHOUT ROWID');handle.execute('INSERT INTO "'+name+'" VALUES(?)',(value,))
        handle.execute('CREATE INDEX idx_key ON "key"(key)');handle.execute('CREATE TABLE pending(v INTEGER)')
        handle.execute('INSERT INTO pending VALUES(1)');handle.commit();handle.execute('BEGIN');handle.execute('INSERT INTO pending VALUES(2)')
        calls=[]
        handle.create_function('sqlite_version',0,lambda:calls.append('sqlite_version') or 'overridden')
        handle.create_function('current_date',0,lambda:calls.append('current_date') or 'observed date')
        observed=instance.complete({'session_id':session['session_id']})['editor_context']
        assert not calls and observed['context']['version']=='3.53.0' and observed['context']['keyword_observation_complete']
        roles=observed['context']['identifier_keyword_roles']
        assert 'KEY' in roles['nm'] and 'LEFT' in roles['nm'] and 'LEFT' not in roles['ids']
        assert 'INDEXED' in roles['nm'] and 'INDEXED' not in roles['ids'] and 'SELECT' not in roles['nm']
        assert 'CURRENT_DATE' in roles['nm'] and 'CURRENT_DATE' not in roles['bare']
        assert 'CURRENT_DATE' not in roles['qualifier']
        cases=[]
        for marked in [
            'SELECT t.| FROM main.key t','SELECT key.| FROM main.key',
            'SELECT filter.| FROM main.key filter',
            'WITH q AS (SELECT t.* FROM main.key t) SELECT q.| FROM q',
            'WITH q AS (SELECT t.key AS filter FROM main.key t) SELECT q.| FROM q',
            'WITH with AS (SELECT t.key FROM main.key t) SELECT with.| FROM with',
            'SELECT left.| FROM main.key AS left',
            'SELECT "current_date".| FROM main.key AS current_date',
            'SELECT u.| FROM main.key t LEFT JOIN main.key u ON 1=1',
            'SELECT u.| FROM main.offset t JOIN main.key u ON 1=1',
            'SELECT key.| FROM main.key INDEXED BY idx_key',
            "SELECT 'named alias'.| FROM 'key' AS 'named alias'",
            "SELECT 'key'.'ke|' FROM 'key'",
            'WITH q AS (SELECT current_date FROM main.key) SELECT q.| FROM q',
            "WITH q AS (SELECT n'quoted alias' FROM main.key) SELECT q.| FROM q",
            'SELECT t.| FROM ſelect t','SELECT t.| FROM lateral t',
            'SELECT t.| FROM main.key t WINDOW w AS ()',
            'WITH q AS (SELECT sum(t.key) OVER w AS value FROM main.key t WINDOW w AS ()) SELECT q.| FROM q',
            'WITH q AS (SELECT sum(t.key) FILTER(WHERE t.key>0) OVER() AS value FROM main.key t) SELECT q.| FROM q',
        ]:
            # The quoted partial member needs a full native source for its
            # result oracle; all other cases use the native star projection.
            oracle=marked.replace("'ke|'",'*').replace('|','*')
            native=handle.execute(oracle);names=[column[0] for column in native.description];assert len(native.fetchall())==1
            quoted=lambda name:("'"+name.replace("'","''")+"'") if "'ke|'" in marked else '"'+name.replace('"','""')+'"'
            expected=[{'label':quoted(name) if "'ke|'" in marked else name,'apply':quoted(name),'type':'property'} for name in names]
            inserted=[]
            for option in expected:
                source=marked.replace("'ke|'",option['apply']) if "'ke|'" in marked else marked.replace('|',option['apply'])
                query=handle.execute(source);assert len(query.description)==1;assert len(query.fetchall())==1;inserted.append(source)
            cases.append({'marked':marked,'expected':expected,'native_inserted_sql':inserted})
        negative=['SELECT indexed.| FROM main.key indexed','SELECT t.| FROM main.select t',
            'SELECT current_date.| FROM main.key AS current_date']
        for marked in negative:
            try:handle.execute(marked.replace('|','*'))
            except sqlite3.OperationalError:pass
            else:raise AssertionError('Invalid native identifier context was accepted')
        assert handle.in_transaction and handle.execute('SELECT count(*) FROM pending').fetchone()[0]==2
        with sqlite3.connect(path) as observer:assert observer.execute('SELECT count(*) FROM pending').fetchone()[0]==1
        handle.rollback();assert handle.execute('SELECT count(*) FROM pending').fetchone()[0]==1
        (output/'native-editor-fixture.json').write_text(json.dumps({'engine':'sqlite','metadata':observed,'cases':cases,'negative_cases':negative},ensure_ascii=False,indent=2)+'\n')
        proof.update(complete=True,native_cases=len(cases),negative_cases=len(negative),
            compiled_keyword_count=len(observed['context']['keywords'].split()),metadata_executed_no_user_functions=True,pending_work_preserved=True)
    finally:
        if instance is not None:instance.client.close()
        (output/'summary.json').write_text(json.dumps(proof,indent=2)+'\n')
    return proof


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--evidence',type=Path,required=True)
    args=parser.parse_args();qualify(args.evidence)
