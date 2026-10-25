"""Cold recovered-data deployment into a permanent, initially read-only unit."""
import base64
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

try:
    import _cdeadmin_physical_worker as physical
    import _cdeadmin_recovery_worker as recovery
    import _cdeadmin_native_installation as installation
except ModuleNotFoundError:
    from . import mysql_physical_worker as physical
    from . import mysql_recovery_worker as recovery
    from . import mysql_host_installation as installation

host=physical.host
Refused=physical.Refused


def options(value,*,host_paths=True):
    if not isinstance(value,dict) or set(value)!={'directory','service','bind_address','port','server_id'}:
        raise Refused('Select the permanent deployment directory, new systemd unit, listener and server ID')
    if not isinstance(value['directory'],str) or not value['directory'].startswith('/') or '\0' in value['directory'] or len(value['directory'])>4096:
        raise Refused('Select an absolute directory on the Linux deployment host')
    directory=physical.absolute(value['directory']) if host_paths else value['directory']
    if not isinstance(value.get('service'),str) or not re.fullmatch(r'[A-Za-z0-9@_.:\\-]+\.service',value['service']) or len(value['service'])>255:
        raise Refused('Select an exact new native systemd unit name')
    if not isinstance(value['bind_address'],str):raise Refused('Select the native listener address as text')
    try:ipaddress.ip_address(value['bind_address'])
    except (TypeError,ValueError):raise Refused('Select an explicit native IPv4 or IPv6 listener address') from None
    if (type(value['port']) is not int or not 1<=value['port']<=65535 or
            type(value['server_id']) is not int or not 1<=value['server_id']<=4294967295):
        raise Refused('Select the permanent native listener port and nonzero server ID')
    return {**value,'directory':str(directory)}


def cold_input(request):
    root=physical.root_directory(request['workspace'],physical.host_scope(request))
    directory=root/physical.job_id(request['input_job_id'])
    prior=physical.read_json(directory/'request.json');receipt=physical.read_json(directory/'result.json')
    if (prior.get('phase')!='recover' or prior.get('binding')!=request['binding'] or
            prior.get('workspace')!=str(root) or not receipt.get('sql_ready_observed') or
            not receipt.get('runtime_process') or not receipt.get('supervisor_process')):
        raise Refused('Select an originally observed managed recovery in this exact source and host workspace')
    if (directory/'retention-intent.json').exists():raise Refused('The recovered input has entered retention')
    # Original process births, rather than stale receipt states or numerical
    # PIDs, prove both writers ended. Unknown original outcomes stay unknown.
    if recovery.present(receipt['runtime_process']) or recovery.present(receipt['supervisor_process']):
        raise Refused('Stop the original recovered server and wait for its original supervisor to end before deployment')
    data=directory/'runtime-data'
    if not data.is_dir() or data.is_symlink():raise Refused('The original cold recovered data directory is unavailable')
    host.binding({'server_uuid':receipt['sql_identity']['server_uuid'],'hostname':request['binding']['hostname'],'datadir':str(data)})
    files=physical.manifest(data)
    if prior['reviewed'].get('external_paths') and not (directory/'runtime-external').is_dir():
        raise Refused('The original cold external-data directory is unavailable')
    external=physical.manifest(directory/'runtime-external') if prior['reviewed'].get('external_paths') else None
    logs=[];index=directory/'recovery-bin.index'
    if index.exists():
        with host.regular_stream(index) as stream:lines=stream.read(1048577)
        if len(lines)>1048576:raise Refused('The native recovered binary-log index exceeds its deployment bound')
        for line in lines.decode('utf8').splitlines():
            path=Path(line)
            if not path.is_absolute():path=directory/path
            if path.parent!=directory or not re.fullmatch(r'recovery-bin\.[0-9]{6,}',path.name):
                raise Refused('Native recovered binary logs escaped their original private directory')
            if path.name in {row['name'] for row in logs}:raise Refused('The native recovered log index contains duplicate files')
            logs.append({'name':path.name,'sha256':host.file_hash(path),'bytes':path.stat().st_size})
    return directory,prior,receipt,{'files':files,'external_files':external,'binary_logs':logs,
        'data_sha256':host.digest(files),'external_sha256':host.digest(external),'binary_log_index_sha256':host.file_hash(index) if index.exists() else None}


def inspection(request):
    if not sys.platform.startswith('linux'):raise Refused('Permanent recovered-service deployment requires Linux systemd')
    selected=options(request['deployment']);directory,prior,receipt,files=cold_input(request)
    target=Path(selected['directory']);root=Path(request['workspace'])
    if (target==Path(target.anchor) or target==Path.home().resolve() or target.exists() or
            target.is_relative_to(root) or root.is_relative_to(target) or
            target.is_relative_to(Path(request['binding']['datadir'])) or
            Path(request['binding']['datadir']).is_relative_to(target)):
        raise Refused('Select a new permanent directory separate from the original data and physical artifact workspace')
    parent=target.parent.resolve(strict=True);info=parent.stat()
    if not parent.is_dir():raise Refused('The permanent deployment parent directory is unavailable')
    programs={}
    for name in ('systemctl','systemd-analyze'):
        found=shutil.which(name)
        if found is None:raise Refused('Native systemd deployment tools are unavailable')
        path=Path(found).resolve(strict=True);programs[name]={'path':str(path),'sha256':host.file_hash(path)}
    unit=Path('/etc/systemd/system')/selected['service']
    if os.path.lexists(unit):raise Refused('The selected native service unit already exists')
    with tempfile.TemporaryDirectory(prefix='scratchrobin-recovery-deployment-') as temp:
        if installation.load_state(programs['systemctl'],selected['service'],temp,host.__dict__)!='not-found':
            raise Refused('Select a new native service without an existing systemd definition')
    mysqld=physical.executable(prior['mysqld'],'mysqld')
    if mysqld!=prior['reviewed']['mysqld']:raise Refused('The original recovered native MySQL executable changed')
    return {'source_job_id':prior['job_id'],'source_review_digest':prior['input_digest'],
        'recovered_uuid':receipt['sql_identity']['server_uuid'],'original_outcome_unchanged':True,
        'runtime_process':receipt['runtime_process'],'supervisor_process':receipt['supervisor_process'],
        'input':files,'selected':selected,'parent_identity':[info.st_dev,info.st_ino],
        'mysqld':mysqld,'python':{'path':str(Path(sys.executable).resolve()),'sha256':host.file_hash(Path(sys.executable).resolve())},
        'programs':programs,'unit_path':str(unit),'permanent':True,'initial_super_read_only':True,
        'event_scheduler':'OFF','replication_autostart':False,'automatic_upgrade':False,
        'data_acceptance_verified':False,'production_cutover_verified':False}


def copy_logs(source,target,logs):
    lines=[]
    for row in logs:
        original=source/row['name'];destination=target/row['name']
        if host.file_hash(original)!=row['sha256']:raise Refused('Native recovered binary-log bytes changed before deployment')
        shutil.copy2(original,destination)
        if host.file_hash(destination)!=row['sha256']:raise Refused('The deployed binary-log copy differs from the original')
        lines.append(str(destination))
    if logs:
        with (target/'recovery-bin.index').open('x',encoding='utf8') as stream:
            host.private_file(target/'recovery-bin.index');stream.write('\n'.join(lines)+'\n');stream.flush();os.fsync(stream.fileno())


def launch(directory,validate=False):
    directory=Path(directory);manifest=physical.read_json(directory/'deployment.json')
    executable=Path(manifest['program']['path'])
    if host.file_hash(executable)!=manifest['program']['sha256']:raise Refused('The deployed native MySQL executable changed')
    if manifest['aliases'] is not None:
        isolation=physical.paths_module().activate(directory,manifest['aliases'],directory=directory)
        host.save(directory/'filesystem-isolation.json',isolation)
    os.chdir(directory)
    os.execve(str(executable),[str(executable),*manifest['arguments'],*(['--validate-config'] if validate else [])],physical.native_environment(directory))


def execute(directory):
    directory=Path(directory);request=physical.read_json(directory/'request.json')
    value={'job_id':request['job_id'],'input_digest':request['input_digest'],'phase':'deploy',
        'state':'native_dispatch','native_may_have_dispatched':False,'automatic_retry':False,
        'process_termination_confirmed':False,'supervisor_finished':False,'credential_cleanup_confirmed':True,
        'production_cutover_verified':False,'data_acceptance_verified':False}
    def save():physical.finish(directory,value)
    executable=Path('/proc/self/exe').resolve(strict=True)
    value['supervisor_process']=recovery.birth(os.getpid(),{'path':str(executable),'sha256':host.file_hash(executable)})
    save()
    def admitted():
        if (directory/'cancel').exists():raise InterruptedError('Recovered deployment cancelled; its original target claim is retained')
    def copy_file(source,target):
        admitted()
        with host.regular_stream(Path(source)) as incoming,Path(target).open('xb') as outgoing:
            host.private_file(Path(target))
            while chunk:=incoming.read(2*1024*1024):admitted();outgoing.write(chunk)
            outgoing.flush();os.fsync(outgoing.fileno())
        return str(target)
    try:
        admitted()
        observed=inspection(request)
        if observed!=request['reviewed']:raise Refused('Recovered deployment inputs changed after review')
        source,prior,receipt,files=cold_input(request)
        target=Path(observed['selected']['directory']);parent=os.open(target.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:
            info=os.fstat(parent)
            if [info.st_dev,info.st_ino]!=observed['parent_identity']:raise Refused('The permanent deployment parent changed')
            # A durable, exclusive target claim survives failure at any later
            # copy/configuration/unit step. Another job cannot overwrite it.
            os.mkdir(target.name,mode=0o700,dir_fd=parent)
            host.save(target/'claim.json',{'job_id':request['job_id'],'input_digest':request['input_digest']})
            os.fsync(parent)
        finally:os.close(parent)
        value.update(native_may_have_dispatched=True,deployment_directory=str(target));save()
        data=target/'runtime-data';shutil.copytree(source/'runtime-data',data,copy_function=copy_file)
        if physical.manifest(data)!=files['files']:raise Refused('Permanent recovered data differs from its original cold snapshot')
        if files['external_files'] is not None:
            shutil.copytree(source/'runtime-external',data/'external-data',copy_function=copy_file)
            if physical.manifest(data/'external-data')!=files['external_files']:raise Refused('Permanent external data differs from its original cold snapshot')
        copy_logs(source,target,files['binary_logs'])
        admitted()
        args,aliases=recovery.runtime_arguments(prior,prior['reviewed'],target,data,deployment=observed['selected'])
        if cold_input(request)[3]!=files:raise Refused('The original recovered data changed during deployment copy')
        manifest={'job_id':request['job_id'],'input_digest':request['input_digest'],'program':observed['mysqld'],
            'arguments':args,'aliases':aliases,'recovered_uuid':observed['recovered_uuid'],
            'source_snapshot_sha256':files['data_sha256'],'source_external_sha256':files['external_sha256'],
            'selected':observed['selected'],'initial_super_read_only':True}
        host.save(target/'deployment.json',manifest)
        original=(directory/'supervisor.py').read_text();suffix='\nm.execute(sys.argv[1])\n'
        if not original.endswith(suffix):raise Refused('The independent deployment launcher source is unavailable')
        launcher=target/'native-service.py'
        source_text=original[:-len(suffix)]+"\nsys.modules['_cdeadmin_recovery_deployment'].launch(sys.argv[1],len(sys.argv)>2 and sys.argv[2]=='--validate-config')\n"
        with launcher.open('x',encoding='utf8') as stream:
            host.private_file(launcher);stream.write(source_text);stream.flush();os.fsync(stream.fileno())
        validation=host.process(Path(observed['python']['path']),['-u',str(launcher),str(target),'--validate-config'],directory,
            request['timeout_seconds'],guard_parent_death=True)
        value['configuration_validation']=validation;save()
        if validation['return_code']!=0 or validation.get('timed_out'):
            value.update(state='native_returned',return_code=validation['return_code'],native_reply_observed=True,process_termination_confirmed=True)
            return
        unit_path=Path(observed['unit_path']);unit_root=unit_path.parent.resolve(strict=True);info=unit_root.stat()
        command=[observed['python']['path'],'-u',str(launcher),str(target)]
        unit='[Unit]\nDescription=Recovered MySQL staged through ScratchRobin\nAfter=network.target\n[Service]\nType=simple\nExecStart=:'+ ' '.join(installation.argument(arg) for arg in command)+'\nTimeoutStopSec=90\nRestart=on-failure\n[Install]\nWantedBy=multi-user.target\n'
        plan={'selected_service':{'manager':'systemd','name':observed['selected']['service']},'path':str(unit_path),
            'parent_identity':[info.st_dev,info.st_ino],'unit_text':unit,'unit_sha256':hashlib.sha256(unit.encode()).hexdigest(),
            'manager':observed['programs']['systemctl'],'validator':observed['programs']['systemd-analyze']}
        host.save(directory/'deployment-plan.json',{'unit':plan,'command':command,'manifest_sha256':host.file_hash(target/'deployment.json'),
            'launcher_sha256':host.file_hash(launcher),'recovered_uuid':observed['recovered_uuid'],'program':observed['mysqld']})
        def current():
            if os.path.lexists(unit_path):raise Refused('Another native unit was installed during deployment')
            for item in (*observed['programs'].values(),observed['python'],observed['mysqld']):
                if host.file_hash(Path(item['path']))!=item['sha256']:raise Refused('A native deployment program changed before service publication')
            return plan
        def associated():return {'deployment_manifest_sha256':host.file_hash(target/'deployment.json'),
            'launcher_sha256':host.file_hash(launcher),'recovered_uuid':observed['recovered_uuid']}
        result={'installed':False,'native_result':{'return_code':None}}
        installed=installation.publish(plan,directory,request['timeout_seconds'],host.__dict__,result,current,associated)
        value['installation']=installed;save()
        native=installed['native_result']
        if installed.get('installed') and native.get('return_code')==0:
            admitted()
            # Starts a permanent read-only unit. Boot enablement, independent
            # recovered-data acceptance and writable activation stay explicit.
            started=host.process(Path(plan['manager']['path']),['--no-ask-password','--no-pager','--job-mode=fail','start','--',observed['selected']['service']],directory,request['timeout_seconds'],guard_parent_death=True)
            value['service_start']=started;native=started
        value.update(state='native_returned',return_code=native.get('return_code'),native_reply_observed=True,
            process_termination_confirmed=True,input_copy_detached=bool(installed.get('installed')),
            deployment_manifest_sha256=host.file_hash(target/'deployment.json'),launcher_sha256=host.file_hash(launcher))
    except BaseException as error:
        value.update(state='unknown' if value['native_may_have_dispatched'] else 'not_dispatched',
            error_type=type(error).__name__,error_message=str(error) if isinstance(error,Refused) else None,
            process_termination_confirmed=True)
    finally:
        value.update(supervisor_finished=True)
        request['database_credentials']=None;host.save(directory/'request.json',request);save()


def observe(directory,value):
    """Independent facts never supply a missing installation/start reply."""
    directory=Path(directory);request=physical.read_json(directory/'request.json')
    selected=request['reviewed']['selected'];target=Path(selected['directory'])
    facts={'original_outcome_unchanged':True,'observed':False,'permanent_native_process_verified':False,
        'source_input_copy_detached':False,'database_acceptance_verified':False,'production_cutover_verified':False}
    if value.get('supervisor_process'):
        try:facts['original_supervisor_live']=recovery.present(value['supervisor_process'])
        except (OSError,Refused):facts['original_supervisor_live']=None
    try:
        plan=physical.read_json(directory/'deployment-plan.json');unit=plan['unit']
        claim=physical.read_json(target/'claim.json')
        if claim!={'job_id':request['job_id'],'input_digest':request['input_digest']}:
            raise Refused('The permanent directory belongs to another deployment claim')
        manifest_hash=host.file_hash(target/'deployment.json')
        if manifest_hash!=plan['manifest_sha256']:
            activation=physical.read_json(target/'activation.json')
            if (activation.get('original_manifest_sha256')!=plan['manifest_sha256'] or
                    activation.get('manifest_sha256')!=manifest_hash or activation.get('deployment_job_id')!=request['job_id'] or
                    activation.get('deployment_digest')!=request['input_digest']):
                raise Refused('The recovered startup activation differs from its original deployment')
            facts['startup_activation']=activation
        if (host.file_hash(target/'native-service.py')!=plan['launcher_sha256'] or
                host.file_hash(Path(unit['path']))!=unit['unit_sha256']):
            raise Refused('The reviewed permanent deployment definition changed')
        digest=lambda v:hashlib.sha256(json.dumps(v,separators=(',',':')).encode()).hexdigest()
        previous={'service_binding_verified':True,'selected_service':unit['selected_service'],'unit':{'Id':selected['service']},
            'definition_files':{unit['path']:{'resolved_path':str(Path(unit['path']).resolve()),'sha256':unit['unit_sha256']}},
            'command_sha256':{'ExecStart':digest([[plan['command'][0],plan['command'],False]]),'ExecStop':digest([])}}
        service=host.native_services.inspect({'service':unit['selected_service'],'native_pid_file':str(target/'runtime.pid'),
            'previous_service_binding':previous},{'program':plan['program']},host.process,host.file_hash,host.regular_stream,Refused)
        facts.update(observed=True,service=service,manifest_sha256=manifest_hash,launcher_sha256=plan['launcher_sha256'],
            recovered_uuid=plan['recovered_uuid'],deployment_directory=str(target))
        process=service.get('native_process')
        if process:
            data=target/'runtime-data'
            host.binding({'server_uuid':plan['recovered_uuid'],'hostname':request['binding']['hostname'],'datadir':str(data)})
            wanted=(data/'mysql.ibd').stat();owns=False
            for descriptor in (Path('/proc')/str(process['pid'])/'fd').iterdir():
                try:current=descriptor.stat()
                except FileNotFoundError:continue
                if (current.st_dev,current.st_ino)==(wanted.st_dev,wanted.st_ino):owns=True;break
            if not owns:raise Refused('The permanent native process does not own this recovered dictionary')
            manifest=physical.read_json(target/'deployment.json')
            if manifest['aliases'] is not None:
                isolation=physical.read_json(target/'filesystem-isolation.json')
                facts['filesystem_isolation_observation']=physical.paths_module().observe(process['pid'],isolation)
                if facts['filesystem_isolation_observation'].get('native_filesystem_isolation_observed') is not True:
                    raise Refused('The permanent native filesystem view is unconfirmed')
            facts['permanent_native_process_verified']=True
    except (OSError,ValueError,KeyError) as error:
        facts.update(observed=False,error_type=type(error).__name__)
    return {**value,'deployment_observation':facts}


def activate_policy(directory,selected):
    """One durable, non-replaying startup-policy transition, separate from SQL."""
    directory=Path(directory);request=physical.read_json(directory/'request.json')
    if (not isinstance(selected,dict) or set(selected)!={'job_id','review_digest','event_scheduler','target_uuid'} or
            selected.get('event_scheduler') not in {'ON','OFF'}):
        raise Refused('Select the exact reviewed writable startup policy')
    physical.job_id(selected['job_id']);physical.job_id(selected['target_uuid'])
    if not re.fullmatch(r'[0-9a-f]{64}',selected['review_digest']):raise Refused('Select the exact cutover digest')
    original=physical.read_json(directory/'result.json');observed=observe(directory,original)['deployment_observation']
    if not observed.get('permanent_native_process_verified') or observed['recovered_uuid']!=selected['target_uuid']:
        raise Refused('The permanent recovered process is not independently bound')
    target=Path(request['deployment']['directory']);claim=target/'activation-claim.json'
    if claim.exists():
        if physical.read_json(claim)!=selected:raise Refused('Another cutover already claimed this recovered service')
        # Never repeat a missing original policy write.
        return {'automatic_retry':False,'original_claim_exists':True,
            'activation':physical.read_json(target/'activation.json') if (target/'activation.json').exists() else None}
    with claim.open('x',encoding='utf8') as stream:
        host.private_file(claim);json.dump(selected,stream);stream.flush();os.fsync(stream.fileno())
    manifest=physical.read_json(target/'deployment.json');before=host.file_hash(target/'deployment.json')
    manifest['arguments']=[arg for arg in manifest['arguments'] if arg.split('=',1)[0] not in
        {'--read-only','--super-read-only','--event-scheduler'}]+['--read-only=OFF','--super-read-only=OFF','--event-scheduler='+selected['event_scheduler']]
    manifest['startup_activation']=selected
    receipt={**selected,'deployment_job_id':request['job_id'],'deployment_digest':request['input_digest'],
        'original_manifest_sha256':before,'manifest_sha256':hashlib.sha256(json.dumps(manifest,ensure_ascii=True).encode()).hexdigest(),
        'startup_policy_committed':True,'live_sql_activation_observed':False,'automatic_retry':False}
    # Publish the expected new hash before replacing the manifest. Interruption
    # before replacement leaves the old read-only policy; after it is observable.
    host.save(target/'activation.json',receipt);host.save(target/'deployment.json',manifest)
    receipt['manifest_sha256']=host.file_hash(target/'deployment.json');host.save(target/'activation.json',receipt)
    return {'automatic_retry':False,'activation':receipt,'original_claim_exists':False}
