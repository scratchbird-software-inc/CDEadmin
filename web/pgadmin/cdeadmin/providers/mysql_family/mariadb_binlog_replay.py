"""MariaDB12.2 native GTID-aware replay of sealed, closed binary logs.

Read the native GTID/GTID_LIST headers for admission and transaction boundaries;
MariaDB's own decoder remains responsible for SQL, compression and row events.
"""
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import uuid

from . import mariadb_binlog_archives as archive
from .mysql_binlog_archives import BinlogArchiveError,rows
from ...operations.fileio import private_directory,private_file
from ...sdk.tooling import ProviderToolGrant


def gtids(value):
    if not isinstance(value,str) or len(value)>1024*1024:raise BinlogArchiveError('Invalid native MariaDB GTID position')
    result={}
    if not value:return result
    for item in value.split(','):
        if not re.fullmatch(r'(0|[1-9][0-9]*)-(0|[1-9][0-9]*)-(0|[1-9][0-9]*)',item):raise BinlogArchiveError('Select canonical MariaDB domain-server-sequence GTIDs')
        domain,server,sequence=map(int,item.split('-'))
        if domain>4294967295 or server>4294967295 or sequence>18446744073709551615 or domain in result:
            raise BinlogArchiveError('MariaDB GTIDs require one native unsigned position per domain')
        result[domain]=(server,sequence)
    return result


def position(value):return ','.join(f'{domain}-{server}-{sequence}' for domain,(server,sequence) in sorted(value.items()))


def options(value):
    if not isinstance(value,dict) or set(value)-{'stop_mode','stop_gtid','target_confirmation','timeout_seconds'}:raise BinlogArchiveError('Select exact native replay options')
    mode=value.get('stop_mode','all');stop=value.get('stop_gtid');confirmation=value.get('target_confirmation');timeout=value.get('timeout_seconds',3600)
    if not isinstance(mode,str) or mode not in {'all','before','after'}:raise BinlogArchiveError('Select all transactions, stop before or stop after one native GTID')
    if mode=='all':
        if stop not in (None,''):raise BinlogArchiveError('A full archive replay takes no stop GTID')
        stop=None
    elif not isinstance(stop,str) or len(gtids(stop))!=1:raise BinlogArchiveError('Select one native MariaDB stop GTID')
    if not isinstance(confirmation,str) or not re.fullmatch(r'[A-Za-z0-9+/]{27}=',confirmation):raise BinlogArchiveError('Confirm the exact native target server_uid')
    if timeout is not None and (type(timeout) is not int or not 1<=timeout<=2147483647):raise BinlogArchiveError('Select positive client runtime seconds or null for no deadline')
    return {'stop_mode':mode,'stop_gtid':stop,'target_confirmation':confirmation,'timeout_seconds':timeout}


def capture_target(connection):
    if rows(connection,'SELECT @@in_transaction AS active')[0]['active']:raise BinlogArchiveError('Replay requires an independently owned idle connection')
    connection.autocommit=True
    row=rows(connection,'SELECT VERSION() AS version,@@server_uid AS server_uid,@@server_id AS server_id,CURRENT_USER() AS authenticated_principal,CURRENT_ROLE() AS active_role,@@global.log_bin AS log_bin,@@global.gtid_strict_mode AS gtid_strict_mode,@@global.gtid_current_pos AS gtid_current_pos,@@global.gtid_binlog_pos AS gtid_binlog_pos,@@global.gtid_slave_pos AS gtid_slave_pos')[0]
    if row['version'].split('-')[0]!='12.2.2' or 'MariaDB' not in row['version']:raise BinlogArchiveError('Select native MariaDB12.2.2')
    combined={}
    for key in ('gtid_current_pos','gtid_binlog_pos','gtid_slave_pos'):
        for domain,(server,seq) in gtids(row[key]).items():
            previous=combined.get(domain)
            if previous is not None and previous[1]==seq and previous[0]!=server:
                raise BinlogArchiveError('Native target GTID stores disagree on domain lineage')
            if previous is None or previous[1]<seq:combined[domain]=(server,seq)
    row['replay_gtid_pos']=position(combined)
    return {'identity':{key:row[key] for key in ('version','server_uid','server_id','authenticated_principal','active_role')},
        'state':{key:row[key] for key in ('log_bin','gtid_strict_mode','gtid_current_pos','gtid_binlog_pos','gtid_slave_pos','replay_gtid_pos')}}


def inventory(directory,artifact,*,wanted=(),stop=None,cancel=None):
    """Bounded header scan; layouts are from native12.2 sql/log_event.h/.cc."""
    # Manifest ordering is lexical; execution ordering comes from the sealed
    # native inventory, which need not have lexically increasing basenames.
    from .mysql_binlog_archives import _json
    names=[row['name'] for row in _json(Path(directory)/'archive.json')['logs']]
    wanted=set(wanted);matched=set();initial=None;current={};count=0;boundary=None;after=None
    for index,name in enumerate(names):
        with (Path(directory)/name).open('rb') as stream:
            if stream.read(4)!=b'\xfebin':raise BinlogArchiveError('Native binary-log magic differs')
            saw_list=False
            while True:
                if cancel is not None and cancel.is_set():raise InterruptedError('Native replay inspection cancelled')
                offset=stream.tell();header=stream.read(19)
                if not header:break
                if len(header)!=19:raise BinlogArchiveError('Native binary-log header is truncated')
                length=int.from_bytes(header[9:13],'little');kind=header[4]
                if length<19:raise BinlogArchiveError('Native binary-log event length is invalid')
                end=offset+length
                if kind==163:
                    raw=stream.read(4)
                    if len(raw)!=4:raise BinlogArchiveError('Native GTID list is truncated')
                    size=struct.unpack('<I',raw)[0]&0xfffffff
                    if size*16>length-23:raise BinlogArchiveError('Native GTID list length differs')
                    observed={}
                    for _ in range(size):
                        data=stream.read(16)
                        if len(data)!=16:raise BinlogArchiveError('Native GTID list is truncated')
                        domain,server,seq=struct.unpack('<IIQ',data)
                        if domain in observed:raise BinlogArchiveError('Native GTID list repeats a domain')
                        observed[domain]=(server,seq)
                    if initial is None:initial=dict(observed);current=dict(observed)
                    elif observed!=current:raise BinlogArchiveError('Native archived log range has a GTID gap or changed lineage')
                    saw_list=True
                elif kind==162:
                    if not saw_list:raise BinlogArchiveError('Native GTID event precedes its file state')
                    raw=stream.read(13)
                    if len(raw)!=13:raise BinlogArchiveError('Native GTID event is truncated')
                    seq,domain,_flags=struct.unpack('<QIB',raw);server=int.from_bytes(header[5:9],'little')
                    if seq<=current.get(domain,(0,0))[1]:raise BinlogArchiveError('Native archive GTID sequences are not strictly increasing')
                    exact=f'{domain}-{server}-{seq}'
                    if boundary is not None and after is None:after={'file_index':index,'position':offset}
                    if exact==stop:boundary={'file_index':index,'position':offset}
                    if exact in wanted:matched.add(exact)
                    current[domain]=(server,seq);count+=1
                stream.seek(end)
            if not saw_list:raise BinlogArchiveError('Native archived file has no GTID list')
    if initial is None:raise BinlogArchiveError('Native replay input has no GTID state')
    if stop is not None and boundary is None:raise BinlogArchiveError('The stop GTID is not an archived native transaction')
    return {'start_gtid_pos':position(initial),'end_gtid_pos':position(current),'gtid_events':str(count),'log_names':names,
        'matched_gtids':sorted(matched),'stop_before':boundary,'stop_after':after}


def admission(connection,artifact,selected,observed):
    target=capture_target(connection)
    if target['identity']['server_uid']!=selected['target_confirmation']:raise BinlogArchiveError('The target does not match the confirmed native server_uid')
    if target['identity']['server_uid']==artifact['source_uid']:raise BinlogArchiveError('Select a separate recovery target')
    if target['state']['log_bin'] not in (True,1,'ON') or target['state']['gtid_strict_mode'] not in (True,1,'ON'):
        raise BinlogArchiveError('Native replay requires target binary logging and GTID strict mode')
    base=gtids(observed['start_gtid_pos']);end=gtids(observed['end_gtid_pos']);present=gtids(target['state']['replay_gtid_pos'])
    for domain,(server,seq) in base.items():
        actual=present.get(domain)
        if actual is None or actual[1]<seq or actual[1]==seq and actual[0]!=server:raise BinlogArchiveError('Restore and verify the target base first; archive starting GTIDs are missing or differ')
    for domain,(server,seq) in present.items():
        if domain not in end or (server,seq)==base.get(domain):continue
        if f'{domain}-{server}-{seq}' not in observed['matched_gtids']:raise BinlogArchiveError('The target GTID lineage is not in this archive')
    if selected['stop_gtid'] is not None:
        domain,(server,seq)=next(iter(gtids(selected['stop_gtid']).items()))
        if present.get(domain,(0,0))[1]>=seq:raise BinlogArchiveError('The stop GTID is already present or behind the native target')
    return target


def program_identity(client,route,workspace,*,cancel=None,progress=None):
    decoder=archive.program_identity(client,route,workspace,cancel=cancel,progress=progress)
    grant=ProviderToolGrant('mariadb-client',str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),timeout_seconds=30)
    result=client._tool_runner.run(grant,['--no-defaults','--version'],cancel_signal=cancel,progress=progress)
    if result['return_code']!=0 or not re.search(r'\b12\.2\.2-MariaDB\b',result['stdout']+' '+result['stderr']):raise BinlogArchiveError('Native replay requires mariadb client12.2.2')
    return {'decoder':decoder,'client':{'executable_sha256':result['executable_sha256'],'tool_version':'12.2.2-MariaDB',
        'execution_host':{key:result['execution_host'][key] for key in ('kind','platform')}},'execution_host':decoder['execution_host']}


def lock_name(target):return 'cdeadmin:mariadb-replay:'+hashlib.sha256(target['server_uid'].encode('ascii')).hexdigest()[:40]


def _literal(value):
    if value is None:return 'NULL'
    if type(value) is bool:return '1' if value else '0'
    if type(value) is int:return str(value)
    return "CONVERT(X'"+str(value).encode('utf8').hex()+"' USING utf8mb4)"


def guard(target,before,nonce):
    comparisons=['NOT ('+expr+' <=> '+_literal(value)+')' for expr,value in [
        ('@@server_uid',target['server_uid']),('VERSION()',target['version']),('@@server_id',target['server_id']),
        ('CURRENT_USER()',target['authenticated_principal']),('CURRENT_ROLE()',target['active_role']),
        *[('@@global.'+name,before[name]) for name in ('gtid_current_pos','gtid_binlog_pos','gtid_slave_pos','log_bin','gtid_strict_mode')]]]
    return ('DELIMITER //\nBEGIN NOT ATOMIC\nDECLARE EXIT HANDLER FOR SQLEXCEPTION BEGIN SELECT '+_literal('CDEADMIN_REPLAY_'+nonce+':refused')+'; RESIGNAL; END;\n'
        'IF GET_LOCK('+_literal(lock_name(target))+',0) IS NOT TRUE THEN SIGNAL SQLSTATE \'45000\' SET MESSAGE_TEXT=\'Another native replay holds this target\'; END IF;\n'
        'IF '+ ' OR '.join(comparisons)+' THEN SIGNAL SQLSTATE \'45000\' SET MESSAGE_TEXT=\'Native replay target changed\'; END IF;\n'
        'SELECT '+_literal('CDEADMIN_REPLAY_'+nonce+':invoked')+';\nEND//\nDELIMITER ;\n')


def run_load(client,route,credentials,directory,target,before,selected,observed,workspace,expected_program,*,cancel=None,progress=None,boundary=lambda:None):
    workspace=Path(workspace);directory=Path(directory);last=None;dispatched=False
    try:
        directory.resolve().relative_to(workspace.resolve())
        program=program_identity(client,route,workspace,cancel=cancel,progress=progress)
        if program!=expected_program:raise BinlogArchiveError('Native replay executable or execution host changed')
        loads=workspace/'native-load';loads.mkdir(mode=0o700);private_directory(loads)
        decoded=workspace/'decoded.sql';private_file_workspace=workspace/'replay.sql'
        grant=ProviderToolGrant('mariadb-binlog',str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),
            timeout_seconds=selected['timeout_seconds'],allow_unbounded_runtime=selected['timeout_seconds'] is None)
        names=observed['log_names'];stop=observed['stop_before' if selected['stop_mode']=='before' else 'stop_after'] if selected['stop_mode']!='all' else None
        if stop is not None:names=names[:stop['file_index']+1]
        arguments=['--no-defaults','--verify-binlog-checksum','--gtid-strict-mode','--local-load='+str(loads),'--result-file='+str(decoded)]
        archived_domains=gtids(observed['end_gtid_pos'])
        native_start=position({domain:value for domain,value in gtids(before['replay_gtid_pos']).items() if domain in archived_domains})
        if native_start:arguments.append('--start-position='+native_start)
        if stop is not None:arguments.append('--stop-position='+str(stop['position']))
        result=client._tool_runner.run(grant,[*arguments,'--',*[str(directory/name) for name in names]],cancel_signal=cancel,progress=progress)
        last={key:value for key,value in result.items() if key not in {'stdout','stderr'}};decoder_observation=dict(last)
        if result['return_code']!=0 or result['executable_sha256']!=program['decoder']['executable_sha256']:
            raise BinlogArchiveError('Native MariaDB decoder refused the archived GTID range')
        private_file(decoded);nonce=uuid.uuid4().hex;marker='CDEADMIN_REPLAY_'+nonce+':'
        with private_file_workspace.open('xb') as stream:
            private_file(private_file_workspace);stream.write(guard(target,before,nonce).encode('utf8'))
            with decoded.open('rb') as source:shutil.copyfileobj(source,stream,1024*1024)
            stream.write(('\nDELIMITER ;\nSELECT '+_literal(marker+'returned')+';\nSELECT RELEASE_LOCK('+_literal(lock_name(target))+');\n').encode('utf8'));stream.flush();os.fsync(stream.fileno())
        arguments=client._connection_arguments({**route,'host':route.get('host') or 'localhost'}, {'compress_connection':bool(route.get('compress'))})
        arguments=[item for item in arguments if not item.startswith('--default-character-set=')]
        arguments.extend(['--default-character-set=utf8mb4','--batch','--raw','--skip-column-names','--skip-reconnect','--binary-mode','--skip-print-query-on-error','--skip-auto-rehash'])
        grant=ProviderToolGrant('mariadb-client',str(workspace),str(route.get('host') or 'localhost'),int(route.get('port',3306)),
            timeout_seconds=selected['timeout_seconds'],allow_unbounded_runtime=selected['timeout_seconds'] is None)
        boundary();dispatched=True
        result=credentials.use(lambda view:client._tool_runner.run(grant,arguments,input_path=private_file_workspace,
            secret_config=bytes(view),secret_argument='--defaults-file={path}',secret_argument_position=0,cancel_signal=cancel,progress=progress))
        last={key:value for key,value in result.items() if key not in {'stdout','stderr'}}
        if result['executable_sha256']!=program['client']['executable_sha256']:raise BinlogArchiveError('Native replay client changed during dispatch')
        markers=[line[len(marker):] for line in result['stdout'].splitlines() if line.startswith(marker)]
        control=None
        if markers==['refused']:control={'native_load_invoked':False,'native_load_returned':False,'stage':'checking_target'}
        elif markers in (['invoked'],['invoked','returned']):control={'native_load_invoked':True,'native_load_returned':markers[-1]=='returned','stage':'returned' if markers[-1]=='returned' else 'loading'}
        diagnostics=[{'native_code':int(code),'sqlstate':state} for code,state in re.findall(r'ERROR ([0-9]+) \(([A-Z0-9]{5})\)',result.get('stderr',''))]
        return {'native_diagnostics':diagnostics,'control':control,'tool':{key:result[key] for key in ('executable_id','executable_sha256','execution_host','network_grant','return_code','process_observation')},
            'decoder':decoder_observation,'program':program,'automatic_retry':False,'data_recovery_verified':False}
    except BaseException as error:
        observation=getattr(error,'process_observation',None) or last
        if observation is not None:error.observation={key:value for key,value in observation.items() if key not in {'stdout','stderr'}}
        if not dispatched:error.control={'native_load_invoked':False,'native_load_returned':False,'stage':'native_client_preparation'};error.native_preparation_refused=True
        raise


def coverage(connection,target,before,archived,selected):
    after=capture_target(connection);previous=gtids(before['state']['replay_gtid_pos']);present=gtids(after['state']['replay_gtid_pos']);end=gtids(archived['end_gtid_pos'])
    preserves=all(domain in present and present[domain][1]>=seq and (present[domain][1]!=seq or present[domain][0]==server) for domain,(server,seq) in previous.items())
    covered=all(domain in present and present[domain][1]>=seq for domain,(_server,seq) in end.items())
    stop=gtids(selected['stop_gtid']) if selected['stop_gtid'] else None
    return {'before_native_gtid_stores':{key:before['state'][key] for key in ('gtid_current_pos','gtid_binlog_pos','gtid_slave_pos')},
        'after_native_gtid_stores':{key:after['state'][key] for key in ('gtid_current_pos','gtid_binlog_pos','gtid_slave_pos')},
        'before_replay_gtid_pos':before['state']['replay_gtid_pos'],'after_replay_gtid_pos':after['state']['replay_gtid_pos'],
        'baseline_sequences_preserved':preserves,'all_archive_domain_sequences_present':covered,
        'stop_domain_sequence_present':None if stop is None else all(present.get(domain,(0,0))[1]>=seq for domain,(_server,seq) in stop.items()),
        'target_identity_unchanged':after['identity']==target,
        'scope':'native_domain_sequence_presence; not exact transaction attribution, data verification or production cutover'}
