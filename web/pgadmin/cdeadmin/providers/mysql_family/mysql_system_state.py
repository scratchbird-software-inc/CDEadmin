"""Exact, read-only checks of selected native MySQL 9.7 system tables.

This is a checkpoint comparison, never a system-table importer. Native runtime
state, hidden dictionary tables and host configuration have separate coverage.
"""
import hashlib
import json
import re
from pathlib import Path

from .mysql_binlog_archives import BinlogArchiveError
from .mysql_dump_verification import quote, document
from ...sdk.relational import RelationalClientError
from ...operations.fileio import private_file

FILE = '@.scratchrobin-system-state.json'
FORMAT = 'mysql-system-table-checkpoint-v1'
# Public SQL tables created by the pinned Community system-table bootstrap.
# Logs, replication positions and engine statistics deliberately have no equality
# assertion: those are changing runtime state with separate native semantics.
TABLES = frozenset('''user db default_roles role_edges global_grants password_history
func plugin component servers tables_priv columns_priv procs_priv proxies_priv
help_topic help_category help_relation help_keyword time_zone_name time_zone
time_zone_transition time_zone_transition_type time_zone_leap_second
server_cost engine_cost'''.split())
HEX = re.compile(r'[0-9a-f]{64}\Z')


def selection(value):
    if (not isinstance(value,list) or not value or len(value)>len(TABLES) or
            any(not isinstance(name,str) or name not in TABLES for name in value) or len(set(value))!=len(value)):
        raise BinlogArchiveError('Select distinct supported native system-table checkpoints')
    return sorted(value)


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()


def capture(connection, tables, *, cancel=None):
    """Stream server-generated row digests, preserving NULL, bytes and duplicates."""
    selected=selection(tables);cursor=connection.cursor();result=[];original_zone=None
    try:
        cursor.execute('SELECT @@session.time_zone');original_zone=cursor.fetchone()[0]
        cursor.execute("SET SESSION time_zone='+00:00'")
        cursor.execute('SELECT VERSION(),@@server_uuid')
        version,server_uuid=cursor.fetchone()
        if version.split('-')[0]!='9.7.0':raise BinlogArchiveError('Native system checkpoints require MySQL9.7.0')
        for table in selected:
            if cancel is not None and cancel.is_set():raise InterruptedError('System checkpoint cancelled')
            cursor.execute('SELECT COLUMN_NAME,COLUMN_TYPE,IS_NULLABLE,COLLATION_NAME,EXTRA,GENERATION_EXPRESSION '
                'FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s ORDER BY ORDINAL_POSITION',('mysql',table))
            columns=[list(row) for row in cursor.fetchall()]
            if not columns:raise BinlogArchiveError('Native system-table column visibility is unavailable: '+table)
            cursor.execute('SHOW CREATE TABLE mysql.'+quote(table));definition=cursor.fetchone()[1]
            # HEX of native binary casts keeps numeric digits, text encoding,
            # embedded zero bytes and SQL NULL distinct inside the JSON array.
            expression=','.join('HEX(CAST('+quote(row[0])+' AS BINARY))' for row in columns)
            cursor.execute('SELECT SHA2(CAST(JSON_ARRAY('+expression+') AS CHAR CHARACTER SET utf8mb4),256) AS row_digest '
                'FROM mysql.'+quote(table)+' ORDER BY row_digest')
            fingerprint=hashlib.sha256();count=0
            while True:
                batch=cursor.fetchmany(512)
                if not batch:break
                for row in batch:
                    if not isinstance(row[0],str) or HEX.fullmatch(row[0]) is None:
                        raise BinlogArchiveError('Native system-table row digest is unavailable')
                    fingerprint.update(row[0].encode('ascii')+b'\n');count+=1
                if cancel is not None and cancel.is_set():raise InterruptedError('System checkpoint cancelled')
            result.append({'table':table,'columns_sha256':digest(columns),
                'definition_sha256':hashlib.sha256(definition.encode('utf8')).hexdigest(),
                'rows':str(count),'rows_sha256':fingerprint.hexdigest()})
        return {'format':FORMAT,'source_uuid':server_uuid,'version':version.split('-')[0],'tables':result}
    finally:
        try:
            if original_zone is not None:cursor.execute('SET SESSION time_zone=%s',(original_zone,))
        finally:cursor.close()


def validate(value, source_uuid):
    if (not isinstance(value,dict) or set(value)!={'format','source_uuid','version','tables'} or
            value['format']!=FORMAT or value['source_uuid']!=source_uuid or value['version']!='9.7.0' or
            not isinstance(value['tables'],list) or any(not isinstance(row,dict) for row in value['tables'])):
        raise BinlogArchiveError('Original native system checkpoint identity differs')
    names=selection([row.get('table') for row in value['tables'] if isinstance(row,dict)])
    if names!=[row.get('table') for row in value['tables']]:raise BinlogArchiveError('Native system checkpoint coverage differs')
    for row in value['tables']:
        if (set(row)!={'table','columns_sha256','definition_sha256','rows','rows_sha256'} or
                not isinstance(row['rows'],str) or re.fullmatch(r'0|[1-9][0-9]*',row['rows']) is None or
                any(not isinstance(row[key],str) or HEX.fullmatch(row[key]) is None for key in ('columns_sha256','definition_sha256','rows_sha256'))):
            raise BinlogArchiveError('Native system checkpoint facts are unavailable')
    return value


def save(directory, value):
    path=Path(directory)/FILE
    with path.open('x',encoding='utf8') as stream:
        private_file(path);json.dump(validate(value,value['source_uuid']),stream,sort_keys=True,separators=(',',':'));stream.write('\n')


def read(directory, source_uuid):
    path=Path(directory)/FILE
    if path.is_symlink() or not path.is_file():raise BinlogArchiveError('Original native system checkpoint is unavailable')
    try:value=document(path)
    except RelationalClientError:raise BinlogArchiveError('Original native system checkpoint metadata is unavailable') from None
    return validate(value,source_uuid)


def compare(expected, observed):
    validate(expected,expected['source_uuid']);validate(observed,observed['source_uuid'])
    left={row['table']:row for row in expected['tables']};right={row['table']:row for row in observed['tables']}
    differences=[{'table':name,'expected':left.get(name),'observed':right.get(name)}
        for name in sorted(left.keys()|right.keys()) if left.get(name)!=right.get(name)]
    return {'requested':True,'matched':not differences,'tables':sorted(left),'differences':differences,
        'expected_source_uuid':expected['source_uuid'],'observed_target_uuid':observed['source_uuid'],
        'scope':'Exact selected native system-table definitions, column metadata, full row counts and row-multiset digests; no import or runtime/host readiness assertion'}
