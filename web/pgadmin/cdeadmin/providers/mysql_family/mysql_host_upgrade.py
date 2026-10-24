"""Reviewed native Linux service upgrade; MySQL owns dictionary migration."""
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
import base64
import uuid

SCOPE='mysql-upgrade-host-v1'


def preflight(request, observed, selected, host):
    refused=host['Refused'];connection=selected['check_connection'];secrets=request.get('upgrade_check_secret')
    if observed.get('configuration') is None:raise refused('Select the original native option file for complete upgrade preflight')
    allowed={'scheme','host','port','socket','user','ssl-mode','ssl-ca','ssl-cert','ssl-key','ssl-crl','ssl-capath','ssl-cipher','tls-version','tls-ciphersuites'}
    if (not isinstance(connection,dict) or set(connection)-allowed or connection.get('scheme','mysql')!='mysql' or
            not isinstance(connection.get('user'),str) or not connection['user'] or
            not isinstance(secrets,dict) or not secrets or set(secrets)-{'password','password2','password3'} or
            any(not isinstance(value,str) or len(value.encode('utf8'))>65536 for value in secrets.values())):
        raise refused('Supply an explicit native upgrade-check connection and private authentication factors')
    if connection.get('socket'):
        if not isinstance(connection['socket'],str) or not Path(connection['socket']).is_absolute():raise refused('Select the native absolute upgrade-check socket')
    elif connection.get('host') not in {'localhost','127.0.0.1','::1'} or type(connection.get('port')) is not int or not 1<=connection['port']<=65535:
        raise refused('Native upgrade checks must reach the original server directly on this SSH host')
    found=shutil.which(selected['shell_executable'])
    if found is None:raise refused('The selected native MySQL Shell is unavailable on this SSH host')
    program=Path(found).resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='scratchrobin-upgrade-check-') as temporary:
        directory=Path(temporary)
        version=host['process'](program,['--version'],directory,15,guard_parent_death=True)
        output=base64.b64decode(version.get('outputs',{}).get('stdout',{}).get('base64','')).decode('utf8')
        if version['return_code']!=0 or not re.search(r'\b9\.7\.0\b',output):raise refused('Select native MySQL Shell9.7.0 for upgrade checks')
        marker='CDEADMIN_UPGRADE_CHECK_'+uuid.uuid4().hex
        source='''import json,sys
p=json.loads(sys.stdin.read())
c=dict(p['connection'],**p['secret'])
s=mysql.get_classic_session(c)
try:r=list(s.run_sql('SELECT @@server_uuid,VERSION()').fetch_one())
finally:s.close()
if r[0]!=p['uuid'] or r[1].split('-')[0]!=p['version']:raise RuntimeError('Native upgrade-check source identity changed')
print(p['marker']+'BEGIN')
util.check_for_server_upgrade(c,{'targetVersion':'9.7.0','configPath':p['configuration'],'outputFormat':'JSON'})
print(p['marker']+'END')
'''
        script=directory/'check.py';script.write_text(source);host['private_file'](script)
        source_version=re.search(r'\bVer\s+(\d+\.\d+\.\d+)',observed['program']['version_output'])[1]
        payload=json.dumps({'connection':connection,'secret':secrets,'uuid':observed['host']['server_uuid'],
            'version':source_version,'configuration':observed['configuration']['path'],'marker':marker}).encode()
        result=host['process'](program,['--no-wizard','--py','--file='+str(script)],directory,request.get('timeout_seconds',120),
            guard_parent_death=True,input_bytes=payload)
        output=result.get('outputs',{}).get('stdout',{})
        if (result['return_code']!=0 or result.get('timed_out') or output.get('truncated') or
                result.get('private_input_closed') is not True or result.get('private_input_error_type')):
            raise refused('Native upgrade preflight did not return a complete authenticated report; the original service was not stopped')
        text=base64.b64decode(output.get('base64','')).decode('utf8')
        if text.count(marker+'BEGIN')!=1 or text.count(marker+'END')!=1:raise refused('Native upgrade-check report framing is unconfirmed')
        report=json.loads(text.split(marker+'BEGIN',1)[1].split(marker+'END',1)[0].strip())
        if (report.get('targetVersion')!='9.7.0' or not report.get('serverVersion','').startswith(source_version+' ') or
                any(type(report.get(key)) is not int or report[key]<0 for key in ('errorCount','warningCount','noticeCount'))):
            raise refused('Native upgrade-check identity or result counts are unconfirmed')
        return {'program':{'path':str(program),'sha256':host['file_hash'](program)},'report':report,
            'source_uuid':observed['host']['server_uuid'],'native_return_code':result['return_code'],
            'configuration_sha256':observed['configuration']['sha256'],'native_data_upgrade_dispatched':False}


def host_binding(value, host):
    """Host administration can inspect an old source before profile admission."""
    if not isinstance(value,dict) or set(value)!={'scope','datadir'} or value['scope']!=SCOPE:
        raise host['Refused']('Select the exact native upgrade source data directory')
    import configparser
    import socket
    directory=Path(host['text'](value['datadir'])).resolve(strict=True)
    if not Path(value['datadir']).is_absolute():raise host['Refused']('Select an absolute original native data directory')
    parsed=configparser.ConfigParser(interpolation=None)
    parsed.read_string(content(host,directory/'auto.cnf',65536).decode('utf8'))
    import uuid
    identity=parsed.get('auto','server-uuid',fallback=None)
    if str(uuid.UUID(identity))!=identity:raise host['Refused']('The original native filesystem UUID is unavailable')
    return host['binding']({'server_uuid':identity,'hostname':socket.gethostname(),'datadir':str(directory)})


def claim_path(datadir):
    directory=Path(datadir).resolve(strict=True)
    return directory.parent/('.'+directory.name+'.scratchrobin-upgrade.json')


def admitted(request, host):
    """Do not let another host operation race an admitted data upgrade."""
    path=claim_path(request['binding']['datadir'])
    if not os.path.lexists(path):return
    with host['regular_stream'](path) as stream:value=json.load(stream)
    if value.get('job_id')!=request.get('job_id') or value.get('input_digest')!=request.get('input_digest'):
        raise host['Refused']('An original native upgrade still owns this data directory; inspect its receipt')


def content(host, path, limit=1048576):
    with host['regular_stream'](Path(path)) as stream:
        value=stream.read(limit+1)
    if len(value)>limit:raise host['Refused']('Native upgrade metadata exceeds its bound')
    return value


def history(datadir, host):
    path=Path(datadir)/'mysql_upgrade_history'
    value=json.loads(content(host,path))
    if not isinstance(value,dict) or value.get('file_format')!='1' or not isinstance(value.get('upgrade_history'),list):
        raise host['Refused']('The original native upgrade history is unavailable')
    return value


def inspect(request, observed, host):
    refused=host['Refused'];selected=request['upgrade']
    if not sys.platform.startswith('linux'):raise refused('Native service upgrade requires Linux systemd')
    paths={'executable','configuration_file','basedir','user','source_datadir','source_pid_file','shell_executable'}
    if (not isinstance(selected,dict) or set(selected)!=paths|{'check_connection'} or
            any(not isinstance(selected[key],str) or not selected[key] or '\0' in selected[key] or len(selected[key])>32768 for key in paths)):
        raise refused('Select the native upgrade executable, option file, base directory and operating-system user')
    old=re.search(r'\bVer\s+(\d+)\.(\d+)\.(\d+)(?:\s|[-(])',observed['program']['version_output'])
    if not old or not ((int(old[1]),int(old[2]))==(8,4) or (int(old[1])==9 and int(old[2])<7)):
        raise refused('Select a native MySQL8.4 LTS or MySQL9 innovation source for this MySQL9.7 upgrade')
    service=observed.get('service') or {}
    if service.get('service_binding_verified') is not True or not service.get('native_process') or service['unit']['ActiveState']!='active':
        raise refused('Review the running original native MySQL service before upgrading')
    # There is no SQL-profile admission for the old server. Bind its actual
    # opened native dictionary file to the selected filesystem identity as
    # well as its executable, PID birth and systemd control group.
    dictionary=Path(observed['host']['datadir'])/'mysql.ibd';info=dictionary.stat()
    owned=False
    for path in (Path('/proc')/str(service['native_process']['pid'])/'fd').iterdir():
        try:current=path.stat()
        except FileNotFoundError:continue
        if (current.st_dev,current.st_ino)==(info.st_dev,info.st_ino):owned=True;break
    if not owned:raise refused('The original native MySQL process does not own this data dictionary file')
    candidate_request={key:value for key,value in request.items() if key not in {'upgrade','service','previous_service_binding'}}
    candidate_request.update(executable=selected['executable'],configuration_file=selected['configuration_file'])
    candidate=host['inspect'](candidate_request)
    basedir=Path(selected['basedir']).resolve(strict=True)
    if not basedir.is_dir():raise refused('Select the installed candidate MySQL base directory')
    import pwd
    try:user=pwd.getpwnam(selected['user'])
    except KeyError:raise refused('The selected native MySQL operating-system user does not exist') from None
    validator=shutil.which('systemd-analyze')
    if validator is None:raise refused('Native systemd unit validation is unavailable')
    validator=Path(validator).resolve(strict=True)
    name=service['unit']['Id'];root=Path('/etc/systemd/system').resolve(strict=True);parent=root/(name+'.d')
    if parent.is_symlink() or parent.exists() and not parent.is_dir():raise refused('The native upgrade drop-in directory changed')
    path=parent/'90-scratchrobin-native-upgrade.conf'
    if os.path.lexists(path):raise refused('The selected native upgrade drop-in already exists; inspect the original upgrade')
    from_name='_cdeadmin_native_installation'
    if from_name in sys.modules:installation=sys.modules[from_name]
    else:
        from . import mysql_host_installation as installation
    arguments=[candidate['program']['path'],'--defaults-file='+candidate['configuration']['path'],
        '--basedir='+str(basedir),'--datadir='+observed['host']['datadir'],
        '--pid-file='+request['native_pid_file'],'--user='+selected['user'],'--daemonize=OFF','--upgrade=AUTO']
    dropin='[Service]\nExecStart=\nExecStart=:'+' '.join(installation.argument(value) for value in arguments)+'\n'
    info=parent.stat() if parent.exists() else None
    return {'candidate':candidate,'native_arguments':arguments,'dropin_path':str(path),
        'dropin_text':dropin,'dropin_sha256':hashlib.sha256(dropin.encode()).hexdigest(),
        'parent_identity':[info.st_dev,info.st_ino] if info else None,
        'native_user':{'name':selected['user'],'uid':user.pw_uid,'gid':user.pw_gid},
        'validator':{'path':str(validator),'sha256':host['file_hash'](validator)},
        'native_history_before':history(observed['host']['datadir'],host),'preflight':preflight(request,observed,selected,host),
        'original_native_process':service['native_process'],'automatic_downgrade':False,
        'scope':'Native configuration/unit validation and explicit service replacement; SQL readiness and recovered-data acceptance remain separate'}


def process_ended(original):
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    if boot!=original['boot_id']:return True
    path=Path('/proc')/str(original['pid'])/'stat'
    try:fields=path.read_text().rpartition(')')[2].split()
    except FileNotFoundError:return True
    return fields[19]!=original['start_ticks'] or fields[0] in {'Z','X'}


def execute(request, observed, directory, timeout, host):
    path=Path(directory)/'upgrade.lock'
    descriptor=os.open(path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        # The inline SSH dispatcher owns all upgrade steps. Reconciliation
        # cannot release its data-directory claim while those steps can run.
        import fcntl
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        fields=Path('/proc/self/stat').read_text().rpartition(')')[2].split()
        host['save'](Path(directory)/'upgrade-dispatcher.json',{
            'policy':'linux-parent-death-manager-clients-v1','job_id':request['job_id'],'input_digest':request['input_digest'],
            'pid':os.getpid(),'start_ticks':fields[19],'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip()})
        value=perform(request,observed,directory,timeout,host)
        value['dispatcher_steps_ended']=True
        host['save'](Path(directory)/'upgrade-phase.json',value)
        return value
    finally:os.close(descriptor)


def perform(request, observed, directory, timeout, host):
    refused=host['Refused'];plan=observed['upgrade_plan'];directory=Path(directory)
    value={'stage':'before_native_validation','automatic_retry':False,'automatic_downgrade':False,
        'service_start_requested':False,'sql_readiness_observed':False}
    def save():host['save'](directory/'upgrade-phase.json',value)
    def guarded(executable,arguments,workspace,deadline):
        return host['process'](executable,arguments,workspace,deadline,guard_parent_death=True)
    save()
    if plan['preflight']['report']['errorCount']:
        value.update(stage='native_preflight_refused',native_result={'return_code':plan['preflight']['native_return_code'],
            'native_process_termination_observed':True},native_data_upgrade_dispatched=False)
        save();return value
    check=host['process'](Path(plan['candidate']['program']['path']),plan['native_arguments'][1:]+['--validate-config'],
        directory,timeout,configuration_context=plan['candidate']['configuration']['context'])
    value.update(configuration_validation=check,native_result=check);save()
    if check['return_code']!=0 or check.get('timed_out'):return value
    validation=directory/request['service']['name']
    with validation.open('xb') as stream:
        host['private_file'](validation);stream.write(('[Service]\nType=simple\n'+plan['dropin_text']).encode());stream.flush();os.fsync(stream.fileno())
    check=guarded(Path(plan['validator']['path']),['verify',str(validation)],directory,timeout)
    value.update(unit_validation=check,native_result=check);save()
    if check['return_code']!=0 or check.get('timed_out'):return value
    if host['inspect'](request)!=observed:raise refused('Native upgrade inputs changed after validation; prepare another review')
    claim=claim_path(observed['host']['datadir'])
    with claim.open('x') as stream:
        host['private_file'](claim);json.dump({'job_id':request['job_id'],'input_digest':request['input_digest']},stream);stream.flush();os.fsync(stream.fileno())
    value['stage']='original_service_stop_admitted';save()
    services=host['native_services']
    stopped=services.execute('service_stop',observed['service'],directory,timeout,guarded,refused)
    value.update(original_service_stop=stopped,native_result=stopped);save()
    if stopped['return_code']!=0 or stopped.get('timed_out'):return value
    original_ended=process_ended(plan['original_native_process'])
    current=services.inspect({**request,'previous_service_binding':observed['service']},observed,
        host['process'],host['file_hash'],host['regular_stream'],refused)
    if not original_ended or current['native_process'] is not None or current['unit']['ActiveState'] not in {'inactive','failed'}:
        raise refused('The original native MySQL service has not independently stopped')
    value.update(original_native_process_termination_confirmed=True,stage='original_service_stopped');save()
    # Recheck candidate files after shutdown. The native datadir identity and
    # original upgrade history are retained; no filesystem rollback is invented.
    candidate=host['inspect']({key:val for key,val in {**request,
        'executable':plan['candidate']['program']['path'],
        'configuration_file':plan['candidate']['configuration']['path']}.items()
        if key not in {'upgrade','service','previous_service_binding'}})
    if candidate!=plan['candidate']:raise refused('Native upgrade candidate or configuration changed after shutdown')
    target=Path(plan['dropin_path']);parent=target.parent
    if plan['parent_identity'] is None:
        parent.mkdir(mode=0o755)
    else:
        info=parent.stat()
        if parent.is_symlink() or [info.st_dev,info.st_ino]!=plan['parent_identity']:raise refused('Native upgrade drop-in parent changed')
    value['stage']='upgrade_dropin_publication_admitted';save()
    with target.open('xb') as stream:
        stream.write(plan['dropin_text'].encode());stream.flush();os.fsync(stream.fileno())
    descriptor=os.open(parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)
    value.update(dropin_installed=True,stage='native_manager_reload_admitted');save()
    manager=Path(observed['service']['manager_programs']['systemctl']['path'])
    reloaded=guarded(manager,['daemon-reload'],directory,timeout)
    value.update(manager_reload=reloaded,native_result=reloaded);save()
    if reloaded['return_code']!=0 or reloaded.get('timed_out'):return value
    value.update(stage='candidate_service_start_admitted',service_start_requested=True);save()
    started=guarded(manager,['--no-ask-password','--no-pager','--job-mode=fail','start','--',request['service']['name']],directory,timeout)
    value.update(candidate_service_start=started,native_result=started,stage='native_manager_requests_returned');save()
    return value


def observe(directory, value, host, *, acknowledge=False):
    directory=Path(directory);request=value['upgrade_request'];observed=value['observation'];plan=observed['upgrade_plan']
    phase_path=directory/'upgrade-phase.json'
    later={'original_native_result_unchanged':True,'sql_readiness_observed':False}
    if phase_path.exists():later['phase']=json.loads(content(host,phase_path))
    dispatcher=directory/'upgrade-dispatcher.json'
    if dispatcher.exists():
        original=json.loads(content(host,dispatcher))
        if (original.get('policy')!='linux-parent-death-manager-clients-v1' or
                any(original.get(key)!=request[key] for key in ('job_id','input_digest'))):
            raise host['Refused']('The original native upgrade dispatcher identity changed')
        later['original_dispatcher_end_confirmed']=process_ended(original)
    try:
        target=Path(plan['dropin_path']);present=os.path.lexists(target)
        later['dropin_matches_review']=host['file_hash'](target)==plan['dropin_sha256'] if present else False
        later['original_native_process_termination_confirmed']=process_ended(plan['original_native_process'])
        prior=observed['service']
        if present:
            if not later['dropin_matches_review']:raise host['Refused']('The original native upgrade drop-in changed')
            candidate=plan['candidate']
            # Bind an inactive/failed candidate to the exact original unit and
            # reviewed typed drop-in, without inventing a successful startup.
            association={**prior,'definition_files':{**prior['definition_files'],str(target):{
                'resolved_path':str(target.resolve(strict=True)),'sha256':plan['dropin_sha256']}},
                'command_sha256':{**prior['command_sha256'],'ExecStart':hashlib.sha256(json.dumps([
                    [candidate['program']['path'],plan['native_arguments'],False]],separators=(',',':')).encode()).hexdigest()}}
        else:
            if (later.get('phase') or {}).get('dropin_installed'):raise host['Refused']('The original published native upgrade drop-in is missing')
            candidate=observed;association=prior
            later['native_upgrade_write_not_dispatched']=True
        later['native_service']=host['native_services'].inspect({**request,'previous_service_binding':association},candidate,
            host['process'],host['file_hash'],host['regular_stream'],host['Refused'])
        later['native_upgrade_history']=history(observed['host']['datadir'],host)
        later['observed']=True
    except Exception as error:later.update(observed=False,error_type=type(error).__name__)
    if acknowledge:
        descriptor=os.open(directory/'upgrade.lock',os.O_RDWR|os.O_NOFOLLOW)
        try:
            import fcntl
            try:fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:raise host['Refused']('The original upgrade dispatcher can still execute native steps') from None
            original=plan['original_native_process']
            rebooted=Path('/proc/sys/kernel/random/boot_id').read_text().strip()!=original['boot_id']
            if ((later.get('phase') or {}).get('dispatcher_steps_ended') is not True and not rebooted and
                    later.get('original_dispatcher_end_confirmed') is not True):
                raise host['Refused']('Original native upgrade execution has not independently ended')
            if (later.get('observed') is not True or not (later.get('original_native_process_termination_confirmed') is True or
                    later.get('native_upgrade_write_not_dispatched') is True) or
                    later['native_service']['unit']['ActiveState'] not in {'active','inactive','failed'}):
                raise host['Refused']('Observe the original process end and current native upgrade target before acknowledgement')
            versions=later.get('native_upgrade_history',{}).get('upgrade_history',[])
            if (later.get('dropin_matches_review') and later['native_service']['unit']['ActiveState']=='active' and
                    (not versions or not isinstance(versions[-1].get('version'),str) or
                     versions[-1]['version'].split('-')[0]!='9.7.0')):
                raise host['Refused']('The candidate is still starting or its native upgrade completion is unconfirmed')
            claim=claim_path(observed['host']['datadir'])
            if claim.exists():
                admitted(request,host);claim.unlink()
                parent=os.open(claim.parent,os.O_RDONLY|os.O_DIRECTORY)
                try:os.fsync(parent)
                finally:os.close(parent)
            later['data_directory_claim_released']=True
        finally:os.close(descriptor)
    return {**value,'upgrade_reconciliation':later}
