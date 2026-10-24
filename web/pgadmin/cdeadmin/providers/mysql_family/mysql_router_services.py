"""Native Linux Router service definition, association and original outcomes."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile


def modules():
    import sys
    if '_cdeadmin_native_installation' in sys.modules:
        return sys.modules['_cdeadmin_native_installation'],sys.modules['_cdeadmin_native_services']
    from . import mysql_host_installation,mysql_host_services
    return mysql_host_installation,mysql_host_services


def stable(value):
    return {key:value[key] for key in ('directory','directory_identity','configuration_path','configuration_sha256','native_router_ids')}


def runtime(request,router):
    native=router.host_module();options=router.selected(request);binding=request.get('deployment_binding')
    if not isinstance(binding,dict):raise router.Refused('Select the original native Router deployment receipt')
    observed=binding['observation'];program=Path(options['executable']).resolve(strict=True)
    if str(program)!=observed['program']['path'] or native.file_hash(program)!=observed['program']['sha256']:
        raise router.Refused('The original native Router executable changed')
    deployment=router.deployment(options['directory'])
    if stable(deployment)!=binding['deployment']:raise router.Refused('The original native Router deployment or configuration changed')
    selected=options.get('service')
    if (not isinstance(selected,dict) or set(selected)!={'manager','name'} or selected['manager']!='systemd' or
            not isinstance(selected['name'],str) or len(selected['name'])>255 or not re.fullmatch(r'[A-Za-z0-9@_.:\\-]+\.service',selected['name'])):
        raise router.Refused('Select the exact native Router systemd service')
    pid=str(Path(deployment['directory'])/'run'/'scratchrobin-router.pid')
    result={'program':observed['program'],'host':observed['host'],'deployment':stable(deployment),'native_pid_file':pid,
        'configuration_acceptance_scope':'native Router startup; systemd validation checks only the unit',
        'sql_readiness_observed':False}
    if options['operation']=='install_service':result['installation']=plan(request,result,router)
    else:
        _installation,services=modules()
        current=services.inspect({'service':selected,'native_pid_file':pid,'previous_service_binding':binding.get('service')},
            result,native.process,native.file_hash,native.regular_stream,router.Refused)
        previous=binding.get('service')
        if (not isinstance(previous,dict) or previous.get('selected_service')!=selected or
                any(current[key]!=previous.get(key) for key in ('definition_files','command_sha256'))):
            raise router.Refused('The bound native Router service definition changed')
        result['service']=current
    return result


def plan(request,observed,router):
    import pwd
    native=router.host_module();installation,_services=modules();options=request['options'];selected=options['service']
    try:user=pwd.getpwnam(options['user'])
    except KeyError:raise router.Refused('The selected native Router operating-system user does not exist') from None
    programs={}
    for command in ('systemctl','systemd-analyze'):
        path=shutil.which(command)
        if path is None:raise router.Refused('Native systemd installation tools are unavailable')
        path=Path(path).resolve(strict=True);programs[command]={'path':str(path),'sha256':native.file_hash(path)}
    root=Path('/etc/systemd/system').resolve(strict=True);info=root.stat();path=root/selected['name']
    if os.path.lexists(path):raise router.Refused('An existing native Router service unit is never replaced')
    host={'process':native.process,'Refused':router.Refused}
    with tempfile.TemporaryDirectory(prefix='scratchrobin-router-service-') as temporary:
        state=installation.load_state(programs['systemctl'],selected['name'],temporary,host)
    if state!='not-found':raise router.Refused('The selected native Router service already has a systemd definition')
    directory=observed['deployment']['directory']
    args=[observed['program']['path'],'--config='+observed['deployment']['configuration_path'],
        '--pid-file='+observed['native_pid_file'],'--user='+options['user']]
    unit='[Unit]\nDescription=MySQL Router managed through ScratchRobin\nAfter=network.target\n[Service]\nType=simple\nWorkingDirectory='+installation.working_directory(directory)+'\nEnvironment='+installation.argument('HOME='+directory)+'\nExecStart=:'+ ' '.join(installation.argument(value) for value in args)+'\nTimeoutStopSec=90\nRestart=on-failure\n[Install]\nWantedBy=multi-user.target\n'
    return {'selected_service':selected,'path':str(path),'parent_identity':[info.st_dev,info.st_ino],
        'unit_text':unit,'unit_sha256':hashlib.sha256(unit.encode()).hexdigest(),'native_arguments':args,
        'native_user':{'name':options['user'],'uid':user.pw_uid,'gid':user.pw_gid},'manager':programs['systemctl'],
        'validator':programs['systemd-analyze'],'load_state':state,'native_pid_file':observed['native_pid_file'],
        'automatic_start':False,'automatic_enable':False}


def association(request,observed,router):
    native=router.host_module();_installation,services=modules();plan=observed['installation']
    digest=lambda value:hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
    previous={'service_binding_verified':True,'selected_service':plan['selected_service'],'unit':{'Id':plan['selected_service']['name']},
        'definition_files':{plan['path']:{'resolved_path':plan['path'],'sha256':plan['unit_sha256']}},
        'command_sha256':{'ExecStart':digest([[observed['program']['path'],plan['native_arguments'],False]]),'ExecStop':digest([])}}
    return services.inspect({'service':plan['selected_service'],'native_pid_file':observed['native_pid_file'],'previous_service_binding':previous},
        observed,native.process,native.file_hash,native.regular_stream,router.Refused)


def execute(request,observed,directory,sources,result,router):
    """Every native command retains its original independent guardian receipt."""
    native=router.host_module();tools=router.sdk(directory,sources);installation,services=modules();count=0
    def run(executable,arguments,workspace,timeout):
        nonlocal count
        index=count;count+=1;checksum=native.file_hash(executable)
        def progress(event):
            if event.get('durable_tool'):
                result.setdefault('native_commands',[]).append({'index':index,'executable_sha256':checksum,'durable_tool':event['durable_tool']})
                native.save(directory/'result.json',result)
        outcome=tools.run([str(executable),*arguments],workspace=directory,environment=native.environment(executable,directory),
            timeout=timeout,capture_limit=65536,name='router-service-'+str(index),progress=progress,guard_parent_death=True)
        value={key:item for key,item in outcome.items() if key not in {'stdout','stderr'}}
        value['outputs']={name:{'base64':base64.b64encode(outcome[name]).decode()} for name in ('stdout','stderr')}
        return value
    host={key:getattr(native,key) for key in ('save','private_file')};host.update(process=run,Refused=router.Refused)
    operation=request['options']['operation'];timeout=request['options']['timeout_seconds']
    if operation=='install_service':
        initial={'installed':False,'configuration_validation':None,'configuration_acceptance_scope':observed['configuration_acceptance_scope'],
            'restart_issued':False,'enable_issued':False,'sql_readiness_observed':False,'automatic_retry':False}
        outcome=installation.publish(observed['installation'],directory,timeout,host,initial,
            lambda:runtime(request,router)['installation'],lambda:association(request,observed,router))
        result.update(service_installation_result=outcome,result=outcome.get('native_result'))
    else:
        outcome=services.execute(operation,observed['service'],directory,timeout,run,router.Refused)
        result['result']=outcome
        try:result['service_after']=runtime(request,router)['service']
        except Exception as error:result['service_after_error_type']=type(error).__name__
    result['state']='native_process_returned' if result.get('result') else 'unknown'
    native.save(directory/'result.json',result)
    return result


def observe(result,directory,router,request):
    native=router.host_module();tools=router.sdk(directory,expected=result['sdk_sha256']);facts=[]
    for command in result.get('native_commands',[]):
        facts.append({'index':command['index'],**tools.observe(directory,command['durable_tool'],command['executable_sha256'])})
    answer={**result,'native_command_observations':facts,'original_native_result_unchanged':True}
    phase=directory/'service-installation.json'
    if phase.is_file():answer['service_installation_phase_observation']=json.loads(phase.read_text())
    try:
        answer['current_service_observation']=association(request,result['observation'],router) if result['operation']=='install_service' else runtime(request,router)['service']
    except Exception as error:answer['current_service_observation_error_type']=type(error).__name__
    return answer
