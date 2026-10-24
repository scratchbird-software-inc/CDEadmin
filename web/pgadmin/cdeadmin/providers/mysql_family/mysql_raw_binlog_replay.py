"""MySQL9.7 raw-log replay through native mysqlbinlog and mysql clients."""
from datetime import datetime,timezone
import json
import os
from pathlib import Path
import re
import shutil
import uuid

from . import mysql_raw_binlog_archives as archive
from .mysql_binlog_archives import BinlogArchiveError,rows,_json
from .mysql_clone import configure
from ...operations.fileio import private_directory,private_file
from ...sdk.tooling import ProviderToolGrant
from ...security import SecretLease


def options(value):
    allowed={'stop_mode','stop_file','stop_position','start_file','start_position','target_confirmation','timeout_seconds'}
    if not isinstance(value,dict) or set(value)-allowed:raise BinlogArchiveError('Select exact native raw replay options')
    mode=value.get('stop_mode','all');file=value.get('stop_file');offset=value.get('stop_position');timeout=value.get('timeout_seconds',3600)
    if not isinstance(mode,str) or mode not in {'all','before','after'}:raise BinlogArchiveError('Select all groups, stop before or stop after one native transaction group')
    if mode=='all':
        if file not in (None,'') or offset not in (None,''):raise BinlogArchiveError('Full raw replay takes no stop boundary')
        file=offset=None
    else:
        archive.options({'log_names':[file]})
        if not isinstance(offset,str) or not re.fullmatch(r'[1-9][0-9]{0,19}',offset) or not 4<=int(offset)<=18446744073709551615:
            raise BinlogArchiveError('Select an exact native transaction-start file position')
    start_file=value.get('start_file');start_position=value.get('start_position')
    if start_file is not None or start_position is not None:
        archive.options({'log_names':[start_file]})
        if not isinstance(start_position,str) or not re.fullmatch(r'[1-9][0-9]{0,19}',start_position) or not 4<=int(start_position)<=18446744073709551615:raise BinlogArchiveError('Select an exact native starting group position')
    confirmation=value.get('target_confirmation')
    try:
        if not isinstance(confirmation,str) or str(uuid.UUID(confirmation))!=confirmation:raise ValueError()
    except (ValueError,AttributeError):raise BinlogArchiveError('Confirm the exact native target UUID') from None
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):raise BinlogArchiveError('Select positive client runtime seconds or null for no deadline')
    return {'stop_mode':mode,'stop_file':file,'stop_position':offset,'start_file':start_file,'start_position':start_position,'target_confirmation':confirmation,'timeout_seconds':timeout}


def inventory(directory,*,selected=None,offset=0,limit=100,cancel=None):
    if type(offset) is not int or offset<0 or type(limit) is not int or not 1<=limit<=100:raise BinlogArchiveError('Invalid native transaction-group page')
    directory=Path(directory);metadata=_json(directory/'archive.json')
    if metadata.get('format')!='mysql-raw-binlog@9.7.0':raise BinlogArchiveError('Select a native MySQL raw archive')
    names=archive.options({'log_names':[row['name'] for row in metadata['logs']]})['log_names']
    start_file=selected.get('start_file') if selected else None
    if start_file is not None and start_file not in names:raise BinlogArchiveError('The selected start file is not in this archive')
    start_index=names.index(start_file) if start_file is not None else 0
    start_position=selected['start_position'] if start_file is not None else '4'
    start_key=(start_index,int(start_position));start_found=start_position=='4'
    stop_key=(names.index(selected['stop_file']),int(selected['stop_position'])) if selected and selected['stop_mode']!='all' and selected['stop_file'] in names else None
    count=0;page=[];first=before=after=None;anonymous=False;named=False;first_positions={};sizes={}
    for index,name in enumerate(names):
        with (directory/name).open('rb') as stream:
            size=os.fstat(stream.fileno()).st_size;sizes[index]=size
            if stream.read(4)!=b'\xfebin':raise BinlogArchiveError('Native raw input magic differs')
            while header:=stream.read(19):
                if cancel is not None and cancel.is_set():raise InterruptedError('Native transaction inspection cancelled')
                position=stream.tell()-19
                if len(header)!=19:raise BinlogArchiveError('Native raw event header is truncated')
                length=int.from_bytes(header[9:13],'little');kind=header[4]
                if length<19 or length>size-position:raise BinlogArchiveError('Native raw event is truncated')
                # Native9.7: GTID_LOG_EVENT33, ANONYMOUS_GTID34 and TAGGED42.
                # mysqlbinlog owns decoding their contents and transaction payloads.
                if kind in {33,34,42}:
                    group={'file':name,'file_index':index,'position':str(position),'event_type':kind,
                        'event_time_utc':datetime.fromtimestamp(int.from_bytes(header[:4],'little'),timezone.utc).isoformat(),
                        'time_scope':'native event-header seconds; not a commit-time recovery target'}
                    if first is None:first=group
                    if before is not None and after is None:after=group
                    if selected and name==selected.get('stop_file') and str(position)==selected.get('stop_position'):before=group
                    if offset<=count<offset+limit:page.append(group)
                    first_positions.setdefault(index,str(position))
                    key=(index,position)
                    if key==start_key:start_found=True
                    included=key>=start_key and (stop_key is None or key<stop_key or key==stop_key and selected['stop_mode']=='after')
                    count+=1
                    if included:anonymous=anonymous or kind==34;named=named or kind!=34
                stream.seek(position+length)
    if not start_found:raise BinlogArchiveError('The start position must be a native group start or file header')
    if stop_key is not None and start_key>stop_key:raise BinlogArchiveError('The native stop group precedes the selected start')
    if first is None:raise BinlogArchiveError('The selected raw range has no native transaction groups')
    if selected and selected['stop_mode']!='all' and before is None:raise BinlogArchiveError('Select a transaction-start boundary observed in this sealed archive')
    return {'log_names':names,'first_group':first,'start_boundary':{'file':names[start_index],'file_index':start_index,'position':start_position},
        'header_end_position':first_positions.get(start_index,str(sizes[start_index])),'stop_before':before,'stop_after':after,
        'anonymous_groups_present':anonymous,'named_groups_present':named,'groups':page,'offset':offset,'limit':limit,'total':count,'more':offset+limit<count}


def capture_target(connection):
    configure(connection)
    row=rows(connection,'SELECT VERSION() AS version,@@server_uuid AS server_uuid,@@server_id AS server_id,CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role,@@global.gtid_mode AS gtid_mode,@@global.gtid_executed AS gtid_executed,@@global.log_bin AS log_bin,@@global.local_infile AS local_infile')[0]
    if row['version'].split('-')[0]!='9.7.0':raise BinlogArchiveError('Select native MySQL9.7.0')
    if row['log_bin'] not in (1,True,'ON'):raise BinlogArchiveError('Raw recovery requires native target binary logging for dispatch-position observations')
    local=rows(connection,'SELECT LOCAL AS native_position FROM performance_schema.log_status')[0]['native_position']
    local=json.loads(local) if isinstance(local,str) else local
    if not isinstance(local,dict) or not isinstance(local.get('binary_log_file'),str) or type(local.get('binary_log_position')) is not int:
        raise BinlogArchiveError('Native target binary-log position is unavailable')
    return {'identity':{key:row[key] for key in ('version','server_uuid','server_id','authenticated_principal','active_role')},
        'state':{**{key:row[key] for key in ('gtid_mode','gtid_executed','log_bin','local_infile')},
            'binary_log_file':local['binary_log_file'],'binary_log_position':str(local['binary_log_position'])}}


def program_identity(client,route,workspace,*,cancel=None,progress=None):
    decoder=archive.program_identity(client,route,workspace,cancel=cancel,progress=progress)
    grant=ProviderToolGrant('mysql-client',str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),timeout_seconds=30)
    result=client._tool_runner.run(grant,['--no-defaults','--no-login-paths','--version'],cancel_signal=cancel,progress=progress)
    if result['return_code']!=0 or not re.search(r'\bVer 9\.7\.0\b',result['stdout']+' '+result['stderr']):raise BinlogArchiveError('Native raw recovery requires mysql9.7.0')
    return {'decoder':decoder,'client':{'tool_version':'9.7.0','executable_sha256':result['executable_sha256'],
        'execution_host':{key:result['execution_host'][key] for key in ('kind','platform')}},'execution_host':decoder['execution_host']}


def _grant(executable,route,workspace,timeout,*,durable_name=None):
    return ProviderToolGrant(executable,str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),
        timeout_seconds=timeout,allow_unbounded_runtime=timeout is None,durable_name=durable_name,guard_parent_death=durable_name is not None)


def previous_gtids(client,route,directory,observed,workspace,expected,*,cancel=None,progress=None):
    """Let the native decoder read PREVIOUS_GTIDS, including tagged SID formats."""
    workspace=Path(workspace);path=workspace/('native-header-'+uuid.uuid4().hex+'.sql');first=observed['first_group']
    header=workspace/('native-header-'+uuid.uuid4().hex+'.bin');remaining=int(observed['header_end_position'])
    with (Path(directory)/observed['start_boundary']['file']).open('rb') as incoming,header.open('xb') as outgoing:
        private_file(header)
        while remaining:
            if cancel is not None and cancel.is_set():raise InterruptedError('Native header staging cancelled')
            chunk=incoming.read(min(remaining,1024*1024))
            if not chunk:raise BinlogArchiveError('Native header changed during staging')
            outgoing.write(chunk);remaining-=len(chunk)
        outgoing.flush();os.fsync(outgoing.fileno())
    result=client._tool_runner.run(_grant('mysql-binlog',route,workspace,30),['--no-defaults','--no-login-paths',
        '--verify-binlog-checksum','--result-file='+str(path),'--',str(header)],
        cancel_signal=cancel,progress=progress)
    try:
        private_file(path)
        if result['return_code']!=0 or result['executable_sha256']!=expected['decoder']['executable_sha256']:
            raise BinlogArchiveError('The native decoder refused the raw starting GTID state')
        found=False;parts=[]
        with path.open('rb') as stream:
            for line in stream:
                if b'\tPrevious-GTIDs' in line:
                    if found:raise BinlogArchiveError('Native starting GTID observation is ambiguous')
                    found=True;continue
                if found:
                    if line.startswith(b'# at ') or not line.startswith(b'# '):break
                    value=line[2:].strip().decode('ascii')
                    if value!='[empty]':parts.append(value)
        if not found:raise BinlogArchiveError('Native starting GTID state is unavailable')
        return ''.join(parts)
    except BaseException as error:
        error.observation={key:value for key,value in result.items() if key not in {'stdout','stderr'}};raise
    finally:
        if result.get('process_observation',{}).get('cleanup_confirmed') is True:
            header.unlink(missing_ok=True);path.unlink(missing_ok=True)


def admission(connection,artifact,observed,previous,selected):
    target=capture_target(connection)
    if target['identity']['server_uuid']!=selected['target_confirmation']:raise BinlogArchiveError('The target does not match its confirmed native UUID')
    if target['identity']['server_uuid']==artifact['source_uuid']:raise BinlogArchiveError('Select a separate recovery target')
    mode=target['state']['gtid_mode']
    if observed['named_groups_present'] and observed['start_boundary']['position']!='4':raise BinlogArchiveError('Start named recovery at a closed-file header; native GTID filtering resumes within it')
    if mode=='ON' and observed['anonymous_groups_present']:raise BinlogArchiveError('A GTID-ON target cannot replay anonymous native transactions')
    if mode=='OFF' and observed['named_groups_present']:raise BinlogArchiveError('A GTID-OFF target cannot replay named native transactions')
    if mode not in {'ON','OFF','ON_PERMISSIVE','OFF_PERMISSIVE'}:raise BinlogArchiveError('The native target GTID mode is unavailable')
    if rows(connection,'SELECT GTID_SUBSET(%s,@@global.gtid_executed) AS valid',(previous,))[0]['valid']!=1:
        raise BinlogArchiveError('Restore and independently verify the base first; archived starting GTIDs are missing')
    return target


def delegate_credentials(client,route):
    from .mysql_binlog_archives import delegate_credentials as acquire
    delegated=[]
    def seal(view):
        values=json.loads(bytes(view));lines=['[client]']
        for name in ('password','password2','password3'):
            if name not in values:continue
            value=values[name]
            if not isinstance(value,str) or '\x00' in value:raise BinlogArchiveError('A native client factor credential cannot be represented')
            value=value.replace('\\','\\\\').replace('"','\\"').replace('\n','\\n').replace('\r','\\r')
            lines.append(('password1' if name=='password' else name)+'="'+value+'"')
        delegated.append(SecretLease(('\n'.join(lines)+'\n').encode('utf8')))
    with acquire(client,route) as lease:lease.use(seal)
    return delegated[0]


def _literal(value):
    if type(value) is bool:value=1 if value else 0
    return "CONVERT(X'"+str(value).encode('utf8').hex()+"' USING utf8mb4)"


def lock_name(target):return 'cdeadmin:binlog-load:'+target['server_uuid']


def guard(target,state,nonce):
    tests=[expr+' <=> '+_literal(value) for expr,value in [
        ('@@server_uuid',target['server_uuid']),('VERSION()',target['version']),('@@server_id',target['server_id']),
        ('CURRENT_USER()',target['authenticated_principal']),('CURRENT_ROLE()',target['active_role']),
        ('@@global.gtid_mode',state['gtid_mode']),('@@global.gtid_executed',state['gtid_executed']),
        ('@@global.local_infile',state['local_infile'])]]
    tests.extend(['(SELECT JSON_UNQUOTE(JSON_EXTRACT(LOCAL,\'$.binary_log_file\')) FROM performance_schema.log_status) <=> '+_literal(state['binary_log_file']),
        '(SELECT CAST(JSON_EXTRACT(LOCAL,\'$.binary_log_position\') AS CHAR) FROM performance_schema.log_status) <=> '+_literal(state['binary_log_position'])])
    marker='CDEADMIN_REPLAY_'+nonce+':'
    return ('SET @cdeadmin_raw_lock=GET_LOCK('+_literal(lock_name(target))+',0);\n'
        'SET @cdeadmin_raw_allowed=(@cdeadmin_raw_lock=1 AND '+' AND '.join('('+test+')' for test in tests)+');\n'
        'SELECT IF(@cdeadmin_raw_allowed,'+_literal(marker+'invoked')+','+_literal(marker+'refused')+');\n'
        'SET @cdeadmin_raw_guard=IF(@cdeadmin_raw_allowed,\'DO 0\',\'CDEADMIN_NATIVE_RAW_TARGET_CHANGED\');\n'
        'PREPARE cdeadmin_raw_guard FROM @cdeadmin_raw_guard;EXECUTE cdeadmin_raw_guard;DEALLOCATE PREPARE cdeadmin_raw_guard;\n')


def run_load(client,route,credentials,directory,target,state,selected,observed,workspace,expected_program,*,cancel=None,progress=None,boundary=lambda:None):
    directory=Path(directory);workspace=Path(workspace);dispatched=False;last=None
    try:
        directory.resolve().relative_to(workspace.resolve())
        program=program_identity(client,route,workspace,cancel=cancel,progress=progress)
        if program!=expected_program:raise BinlogArchiveError('Native raw replay executable or execution host changed')
        loads=workspace/'native-load';loads.mkdir(mode=0o700);private_directory(loads)
        decoded=workspace/'decoded.sql';sql=workspace/'replay.sql'
        stop=observed['stop_before' if selected['stop_mode']=='before' else 'stop_after'] if selected['stop_mode']!='all' else None
        start=observed['start_boundary'];end=len(observed['log_names']) if stop is None else stop['file_index']+1
        names=observed['log_names'][start['file_index']:end]
        args=['--no-defaults','--no-login-paths','--verify-binlog-checksum','--local-load='+str(loads),'--result-file='+str(decoded)]
        if start['position']!='4':args.append('--start-position='+start['position'])
        if state['gtid_executed']:args.append('--exclude-gtids='+state['gtid_executed'])
        if stop is not None:args.append('--stop-position='+stop['position'])
        result=client._tool_runner.run(_grant('mysql-binlog',route,workspace,selected['timeout_seconds'],durable_name='raw-replay-decoder'),
            [*args,'--',*[str(directory/name) for name in names]],cancel_signal=cancel,progress=progress)
        last={key:value for key,value in result.items() if key not in {'stdout','stderr'}};decoder=dict(last)
        if result['return_code']!=0 or result['executable_sha256']!=program['decoder']['executable_sha256']:raise BinlogArchiveError('The native decoder refused raw replay input')
        private_file(decoded);nonce=uuid.uuid4().hex;marker='CDEADMIN_REPLAY_'+nonce+':'
        with sql.open('xb') as stream:
            private_file(sql);stream.write(guard(target,state,nonce).encode('utf8'))
            with decoded.open('rb') as source:shutil.copyfileobj(source,stream,1024*1024)
            stream.write(('\nDELIMITER ;\nSELECT '+_literal(marker+'returned')+';\nSELECT RELEASE_LOCK('+_literal(lock_name(target))+');\n').encode('utf8'));stream.flush();os.fsync(stream.fileno())
        args=[*archive.connection_arguments(client,route),'--batch','--raw','--skip-column-names','--binary-mode','--skip-reconnect',
            '--local-infile=0','--load-data-local-dir='+str(loads)]
        # Decoder termination cannot establish termination of the next client.
        last=None
        boundary();dispatched=True
        result=credentials.use(lambda view:client._tool_runner.run(_grant('mysql-client',route,workspace,selected['timeout_seconds'],durable_name='raw-replay-client'),args,
            input_path=sql,secret_config=bytes(view),secret_argument='--defaults-file={path}',secret_argument_position=0,
            cancel_signal=cancel,progress=progress))
        last={key:value for key,value in result.items() if key not in {'stdout','stderr'}}
        if result['executable_sha256']!=program['client']['executable_sha256']:raise BinlogArchiveError('Native raw replay client changed during dispatch')
        markers=[line[len(marker):] for line in result['stdout'].splitlines() if line.startswith(marker)]
        control=None
        if markers==['refused']:control={'native_load_invoked':False,'native_load_returned':False,'stage':'checking_target'}
        elif markers in (['invoked'],['invoked','returned']):control={'native_load_invoked':True,'native_load_returned':markers[-1]=='returned','stage':'returned' if markers[-1]=='returned' else 'loading'}
        diagnostics=[{'native_code':int(code),'sqlstate':code_state} for code,code_state in re.findall(r'ERROR ([0-9]+) \(([A-Z0-9]{5})\)',result.get('stderr',''))]
        return {'control':control,'tool':{key:result[key] for key in ('executable_id','executable_sha256','execution_host','network_grant','return_code','process_observation')},
            'decoder':decoder,'native_diagnostics':diagnostics,'program':program,'automatic_retry':False,'data_recovery_verified':False}
    except BaseException as error:
        observed_error=getattr(error,'process_observation',None) or last
        if observed_error is not None:error.observation={key:value for key,value in observed_error.items() if key not in {'stdout','stderr'}}
        if not dispatched:error.control={'native_load_invoked':False,'native_load_returned':False,'stage':'native_client_preparation'};error.native_preparation_refused=True
        raise


def coverage(connection,target,before):
    after=capture_target(connection)
    delta=rows(connection,'SELECT GTID_SUBTRACT(@@global.gtid_executed,%s) AS added,GTID_SUBSET(%s,@@global.gtid_executed) AS baseline_preserved',
        (before['state']['gtid_executed'],before['state']['gtid_executed']))[0]
    return {'target_identity_unchanged':after['identity']==target,'after_native_state':after['state'],**delta,
        'scope':'native target log position and GTID observations; anonymous transaction attribution and recovered data are not verified'}
