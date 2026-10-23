"""MySQL9.7 native replay admission and control-script observations.

Native GTID coverage, utility return, process finality and data recovery are
separate facts. This module never infers rollback from local cancellation.
"""
import json
import os
from pathlib import Path
import re
import uuid

from .mysql_binlog_archives import (
    BinlogArchiveError,CREDENTIAL_FILE,connection_options,program_identity,rows)
from .mysql_clone import configure
from ...operations.fileio import private_file
from ...sdk.tooling import ProviderToolGrant


def options(value):
    if not isinstance(value,dict) or set(value)-{'stop_mode','stop_gtid','target_confirmation','timeout_seconds'}:
        raise BinlogArchiveError('Select exact native replay options')
    mode=value.get('stop_mode','all');gtid=value.get('stop_gtid');confirmation=value.get('target_confirmation')
    if not isinstance(mode,str) or mode not in {'all','before','after'}:raise BinlogArchiveError('Select all transactions, stop before or stop after one native GTID')
    if mode=='all':
        if gtid is not None and gtid!='':raise BinlogArchiveError('A full archive load does not take a stop GTID')
        gtid=None
    else:
        if not isinstance(gtid,str) or len(gtid)>128:raise BinlogArchiveError('Select one exact native GTID')
        parts=gtid.split(':')
        try:
            if len(parts) not in {2,3} or str(uuid.UUID(parts[0]))!=parts[0] or not re.fullmatch('[1-9][0-9]{0,18}',parts[-1]) or int(parts[-1])>9223372036854775807:raise ValueError()
            if len(parts)==3 and not re.fullmatch('[A-Za-z_][A-Za-z_0-9]{0,31}',parts[1]):raise ValueError()
        except (ValueError,AttributeError):raise BinlogArchiveError('Select one canonical native UUID, optional tag and positive transaction number') from None
    try:
        if not isinstance(confirmation,str) or str(uuid.UUID(confirmation))!=confirmation:raise ValueError()
    except (ValueError,AttributeError):raise BinlogArchiveError('Confirm the exact target server UUID') from None
    timeout=value.get('timeout_seconds',3600)
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):raise BinlogArchiveError('Select positive client runtime seconds or null for no deadline')
    return {'stop_mode':mode,'stop_gtid':gtid,'target_confirmation':confirmation,'timeout_seconds':timeout}


def capture_target(connection):
    configure(connection)
    row=rows(connection,'SELECT VERSION() AS version,@@server_uuid AS server_uuid,CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role,@@global.gtid_mode AS gtid_mode,@@global.gtid_executed AS gtid_executed,@@global.gtid_purged AS gtid_purged')[0]
    if row['version'].split('-')[0]!='9.7.0':raise BinlogArchiveError('Select a native MySQL9.7.0 replay target')
    return {'identity':{key:row[key] for key in ('version','server_uuid','authenticated_principal','active_role')},
        'state':{key:row[key] for key in ('gtid_mode','gtid_executed','gtid_purged')}}


def admission(connection,artifact,selected):
    target=capture_target(connection)
    if target['identity']['server_uuid']!=selected['target_confirmation']:
        raise BinlogArchiveError('The selected target does not match the confirmed native server UUID')
    if artifact['source_uuid']==target['identity']['server_uuid']:
        raise BinlogArchiveError('Select a separate recovery target; the archive source is not a replay destination')
    if target['state']['gtid_mode'] not in {'ON','ON_PERMISSIVE'}:raise BinlogArchiveError('Native replay requires target GTID mode ON or ON_PERMISSIVE')
    start=artifact.get('start_from',{}).get('gtidExecuted');archived=artifact.get('gtid_set')
    if not isinstance(start,str) or not isinstance(archived,str):raise BinlogArchiveError('The sealed archive lacks a native GTID boundary')
    if rows(connection,'SELECT GTID_SUBSET(%s,@@global.gtid_executed) AS valid',(start,))[0]['valid']!=1:
        raise BinlogArchiveError('Restore and verify the target base before loading this archive; its starting GTIDs are missing')
    stop=selected['stop_gtid']
    if stop is not None:
        result=rows(connection,'SELECT GTID_SUBSET(%s,%s) AS archived,GTID_SUBSET(%s,@@global.gtid_executed) AS present',(stop,archived,stop))[0]
        if result['archived']!=1 or result['present']!=0:
            raise BinlogArchiveError('The stop GTID must be in this archive and not already present on the target')
    return target


def coverage(connection,artifact,selected,before):
    after=capture_target(connection)
    observed=rows(connection,'SELECT GTID_SUBTRACT(@@global.gtid_executed,%s) AS added,GTID_SUBSET(%s,@@global.gtid_executed) AS baseline_preserved,GTID_SUBSET(%s,@@global.gtid_executed) AS all_archive_gtids_present',
        (before['state']['gtid_executed'],before['state']['gtid_executed'],artifact['gtid_set']))[0]
    observed['only_archived_gtids_added']=rows(connection,'SELECT GTID_SUBSET(%s,%s) AS valid',(observed['added'],artifact['gtid_set']))[0]['valid']==1
    observed['stop_gtid_present']=None if selected['stop_gtid'] is None else rows(connection,
        'SELECT GTID_SUBSET(%s,@@global.gtid_executed) AS present',(selected['stop_gtid'],))[0]['present']==1
    observed['target_identity_unchanged']=after['identity']==before['identity']
    observed['scope']='native_gtid_presence_and_delta; not data-integrity verification or attribution of concurrent work'
    return observed


def script(directory,target,before_gtids,selected,nonce):
    expected=[target[key] for key in ('server_uuid','version','authenticated_principal','active_role')]
    native={'showProgress':False,'ignoreVersion':False,'ignoreGtidGap':False}
    if selected['stop_mode']!='all':native['stopBefore' if selected['stop_mode']=='before' else 'stopAfter']=selected['stop_gtid']
    marker='CDEADMIN_REPLAY_'+nonce+':'
    lock_name='cdeadmin:binlog-load:'+target['server_uuid']
    return ('let invoked=false;let stage="connecting";let replayLock=false;\ntry {\n'
        'shell.connect(target);stage="checking_target";\n'
        'const session=shell.getSession();const observed=session.runSql("SELECT @@server_uuid,VERSION(),CURRENT_USER(),CURRENT_ROLE()").fetchOne();\n'
        'if(!'+json.dumps(expected,separators=(',',':'))+'.every((value,index)=>value===observed[index]))throw new Error("Replay target identity changed");\n'
        'if(session.runSql("SELECT GET_LOCK(?,0)",'+json.dumps([lock_name])+').fetchOne()[0]!==1)throw new Error("Another native replay holds this target");replayLock=true;\n'
        'const lineage=session.runSql("SELECT GTID_SUBSET(?,@@global.gtid_executed),GTID_SUBSET(@@global.gtid_executed,?)",'+json.dumps([before_gtids,before_gtids])+').fetchOne();\n'
        'if(lineage[0]!==1 || lineage[1]!==1)throw new Error("Replay target changed after review");\n'
        'stage="loading";invoked=true;util.loadBinlogs('+json.dumps(str(directory))+','+json.dumps(native,separators=(',',':'))+');\n'
        'stage="returned";print('+json.dumps(marker)+'+JSON.stringify({native_load_invoked:invoked,native_load_returned:true,stage:stage}));\n'
        '} catch(error) {print('+json.dumps(marker)+'+JSON.stringify({native_load_invoked:invoked,native_load_returned:false,stage:stage,error_code:Number.isInteger(error.code)?error.code:null}));throw error;}\n'
        'finally {if(replayLock)shell.getSession().runSql("SELECT RELEASE_LOCK(?)",'+json.dumps([lock_name])+');}\n')


def run_load(client,route,credentials,artifact_directory,target,before_gtids,selected,workspace,expected_program,*,cancel=None,progress=None):
    workspace,artifact_directory=Path(workspace),Path(artifact_directory)
    try:
        reservation=None
        if route.get('mysql_recovery_binding'):
            from .mysql_recovery_bridge import UTILITY_KEY,require_replay_utility
            require_replay_utility(route,family='shell');reservation=route[UTILITY_KEY].bridge.listener
        try:artifact_directory.resolve().relative_to(workspace.resolve())
        except ValueError:raise BinlogArchiveError('Replay input escapes its execution-host filesystem grant') from None
        program=program_identity(client,route,workspace,cancel=cancel,progress=progress)
        if program!=expected_program:raise BinlogArchiveError('Native replay executable or execution host changed')
        nonce=uuid.uuid4().hex;marker='CDEADMIN_REPLAY_'+nonce+':'
        source=('const authentication=JSON.parse(os.loadTextFile(os.getenv('+json.dumps(CREDENTIAL_FILE)+')));\n'
            'const target='+json.dumps(connection_options(client,route),ensure_ascii=True)+';\n'
            'for(const name of Object.keys(authentication))target[name]=authentication[name];\n'+
            script(artifact_directory,target,before_gtids,selected,nonce))
        path=workspace/'replay.js'
        with path.open('x',encoding='utf8') as stream:
            private_file(path);stream.write(source);stream.flush();os.fsync(stream.fileno())
        grant=ProviderToolGrant('mysql-shell',str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),
            timeout_seconds=selected['timeout_seconds'],allow_unbounded_runtime=selected['timeout_seconds'] is None,
            secret_environment_names=(CREDENTIAL_FILE,),durable_name='shell-replay-client')
    except BaseException as error:
        error.control={'native_load_invoked':False,'native_load_returned':False,'stage':'native_client_preparation'}
        error.native_preparation_refused=True;raise
    def control_from(result):
        control=None
        for line in result.get('stdout','').splitlines():
            if line.startswith(marker):
                if control is not None:raise BinlogArchiveError('Native replay control observation is ambiguous')
                try:control=json.loads(line[len(marker):])
                except ValueError:raise BinlogArchiveError('Native replay control observation is invalid') from None
                if not isinstance(control,dict) or type(control.get('native_load_invoked')) is not bool or type(control.get('native_load_returned')) is not bool or control.get('stage') not in {'connecting','checking_target','loading','returned'}:
                    raise BinlogArchiveError('Native replay control observation is invalid')
                if control['native_load_returned'] and (not control['native_load_invoked'] or control['stage']!='returned'):
                    raise BinlogArchiveError('Native replay control observation is inconsistent')
        return control
    try:
        result=credentials.use(lambda view:client._tool_runner.run(grant,['--no-defaults','--js','--log-level=none','--file='+str(path)],
            secret_config=bytes(view),secret_argument=None,secret_environment_name=CREDENTIAL_FILE,secret_suffix='.json',
            cancel_signal=cancel,progress=progress,reservation_socket=reservation))
    except BaseException as error:
        observed=getattr(error,'process_observation',None)
        if observed is not None:
            error.observation={key:value for key,value in observed.items() if key not in {'stdout','stderr'}}
            try:error.control=control_from(observed)
            except BinlogArchiveError:error.control=None
        raise
    try:control=control_from(result)
    except BinlogArchiveError as error:
        error.observation={key:value for key,value in result.items() if key not in {'stdout','stderr'}};raise
    return {'control':control,'tool':{key:result[key] for key in ('executable_id','executable_sha256','execution_host','network_grant','return_code','process_observation')},
        'program':program,'automatic_retry':False,'data_recovery_verified':False}
