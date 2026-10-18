"""Native changeset application on an independent, owned file connection."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import stat

from ..embedded_route import contained_database,sqlite_arguments
from .driver import SQLiteConnection
from .session_api import SessionAPI,SessionAPIError

KINDS=('data','not_found','conflict','constraint','foreign_key')
CHOICES={'omit':0,'replace':1,'abort':2}
SWITCHES=('invert','ignore_noop','fk_no_action','foreign_keys','recursive_triggers','include_rebase')
DEFAULTS={**dict.fromkeys(SWITCHES,False),'foreign_keys':True,'table_name':None,'timeout_seconds':3600,
    'conflicts':dict.fromkeys(KINDS,'abort')}


def options(value):
    if not isinstance(value,dict) or set(value)-set(DEFAULTS):raise SessionAPIError('Select native changeset apply options')
    result={**deepcopy(DEFAULTS),**deepcopy(value)}
    if any(type(result[name]) is not bool for name in SWITCHES):raise SessionAPIError('Native changeset switches must be boolean')
    table=result['table_name'];timeout=result['timeout_seconds'];choices=result['conflicts']
    if table is not None and (not isinstance(table,str) or not table or '\x00' in table):raise SessionAPIError('Select an exact native table filter or all tables')
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):raise SessionAPIError('Select a positive apply duration or no deadline')
    if not isinstance(choices,dict) or set(choices)!=set(KINDS):raise SessionAPIError('Select a native response for every conflict kind')
    for kind,choice in choices.items():
        if not isinstance(choice,str) or choice not in CHOICES or choice=='replace' and kind not in {'data','conflict'}:
            raise SessionAPIError('Native replacement is valid only for DATA and CONFLICT')
    return result


def connect(route,library):
    path=contained_database(route)
    if path==':memory:':raise SessionAPIError('Independent changeset application requires a registered database file')
    if any(route.get(name) is True for name in ('read_only','uri_immutable','uri_nolock')) or route.get('uri_mode')=='ro':
        raise SessionAPIError('Native changeset application requires a writable, locking database route')
    info=Path(path).lstat()
    if not stat.S_ISREG(info.st_mode):raise SessionAPIError('Select an existing regular SQLite target file')
    arguments=sqlite_arguments({**route,'uri_mode':'rw','isolation_level':'autocommit'})
    connection=sqlite3.connect(**arguments,factory=SQLiteConnection)
    try:
        api=SessionAPI(connection,library)
        if api.program.get('native_session_revision',0)<2:raise SessionAPIError('The native SQLite helper lacks public changeset apply support')
        actual=[row[2] for row in connection.execute('PRAGMA database_list') if row[1]=='main']
        if actual!=[path]:raise SessionAPIError('Native apply connection resolved another database file')
        return connection,api
    except BaseException:connection.close();raise


def target_snapshot(connection,route):
    path=contained_database(route);info=Path(path).stat()
    schema=[list(row) for row in connection.execute('SELECT hex(type),hex(name),hex(tbl_name),typeof(sql),hex(sql) FROM main.sqlite_schema ORDER BY type,name')]
    return {'database':path,'file_identity':[str(info.st_dev),str(info.st_ino)],
        'schema_sha256':hashlib.sha256(json.dumps(schema,separators=(',',':')).encode('ascii')).hexdigest(),
        'schema_version':connection.execute('PRAGMA main.schema_version').fetchone()[0],
        'application_id':connection.execute('PRAGMA main.application_id').fetchone()[0],
        'user_version':connection.execute('PRAGMA main.user_version').fetchone()[0],
        'journal_mode':connection.execute('PRAGMA main.journal_mode').fetchone()[0]}


class ApplyFailure(SessionAPIError):
    def __init__(self,message,result=None,code=None):
        super().__init__(message,code);self.native_observations=result


def stage(connection,api,descriptor,selected,*,cancel_descriptor=-1,rebase_descriptor=-1,acknowledge=lambda value:None):
    """Leave successful changes in the caller's owned transaction for finality."""
    selected=options(selected)
    if not connection.in_transaction:raise SessionAPIError('Begin an owned apply transaction before staging native changes')
    for name in ('foreign_keys','recursive_triggers'):
        observed=bool(connection.execute('PRAGMA '+name).fetchone()[0])
        if observed!=selected[name]:raise SessionAPIError('Native apply connection settings differ from the reviewed switches')
    if selected['include_rebase']!=(rebase_descriptor>=0):raise SessionAPIError('Select the reviewed native rebase output destination')
    os.lseek(descriptor,0,os.SEEK_SET)
    inspected=api.call('inspect_selection',descriptor,cancel_descriptor,selected['table_name'])
    os.lseek(descriptor,0,os.SEEK_SET)
    flags=1 | (2 if selected['invert'] else 0) | (4 if selected['ignore_noop'] else 0) | (8 if selected['fk_no_action'] else 0)
    result=api.call('apply_file',descriptor,cancel_descriptor,flags,
        *(CHOICES[selected['conflicts'][kind]] for kind in KINDS),rebase_descriptor,selected['table_name'])
    acknowledge(result)
    code=result['native_apply_result_code'] or result['rebase_output_result_code']
    if code:raise ApplyFailure('Native changeset application did not complete',result,code)
    if result['native_changes_included']!=inspected['native_selected_record_count']:
        raise ApplyFailure('Native table compatibility skipped selected changes; the owned transaction must roll back',result)
    return {**result,'source_inspection':inspected,'data_finality':'staged-in-owned-transaction','commit_returned':False}
