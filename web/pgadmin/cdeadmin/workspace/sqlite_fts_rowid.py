"""Native empty-schema observation of external FTS content row identity."""
import sqlite3

from .sqlite_fts_rebind import equal,quote
from ..providers.sqlite.provider import PROFILE
from .firebird_schema_plan import digest


def fingerprint(connection,table,column):
    # Disable Python's statement cache on this owned connection. A cached
    # EXPLAIN can otherwise describe the pre-ALTER program. NOT INDEXED keeps
    # ordinary storage-column identities independent of covering-index choice.
    rows=connection.execute('EXPLAIN SELECT '+quote(column)+' FROM '+quote(table)+' NOT INDEXED').fetchall()
    # Transaction records the current schema cookie/generation. Those counters
    # change after ALTER; expression, cursor and result instructions must match.
    return tuple((op,p1,p2,0 if op=='Transaction' else p3,None if op=='Transaction' else p4,p5)
        for _address,op,p1,p2,p3,p4,p5,_comment in rows)


def mapping(baseline,content,renames,*,before_name='rowid',after_name='rowid'):
    owners=[row for row in baseline['rows'].values() if row['kind']=='table' and
        row['path'][0]=='main' and row['system']=='false' and equal(row['name'],content)]
    if not owners:return None
    if len(owners)!=1:raise ValueError('Native FTS content owner is ambiguous')
    owner=owners[0];connection=sqlite3.connect(':memory:',cached_statements=0)
    try:
        # Before/after fingerprints come from this one runtime, so any
        # admitted version is comparable; record which one answered.
        runtime=sqlite3.sqlite_version
        if not PROFILE.accepts_runtime_version(runtime):
            raise ValueError(
                'Native FTS row identity requires an admitted SQLite runtime')
        connection.setconfig(sqlite3.SQLITE_DBCONFIG_DQS_DML,False)
        connection.execute(owner['native']['ddl']);before=fingerprint(connection,owner['name'],before_name);current=owner['name']
        for item in renames:
            if not equal(item['table'],current):continue
            source='ALTER TABLE '+quote(current)+' RENAME '
            if item['kind']=='table':
                connection.execute(source+'TO '+quote(item['to']));current=item['to']
            else:connection.execute(source+'COLUMN '+quote(item['from'])+' TO '+quote(item['to']))
        after=fingerprint(connection,current,after_name)
        result={'owner':current,'changed':before!=after,'expression':after_name,
                'authority':'sqlite-'+runtime+'-native-content-select-bytecode',
                'before_sha256':digest(before),'after_sha256':digest(after)}
        if before==after:return result
        candidates=[row[1] for row in connection.execute('PRAGMA table_xinfo('+quote(current)+')')]+['rowid','oid','_rowid_']
        for name in dict.fromkeys(candidates):
            try:observed=fingerprint(connection,current,name)
            except sqlite3.Error:continue
            if observed==before:return {**result,'expression':name}
        raise ValueError('The original native FTS row identity is no longer expressible in the renamed content table')
    except sqlite3.Error as error:
        raise ValueError('Native FTS row identity observation refused: '+str(error)) from None
    finally:connection.close()
