"""Reviewed creation of a native Linux systemd unit for an observed MySQL."""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import sys
import tempfile


def argument(value):
    if not isinstance(value,str) or '\0' in value:raise ValueError('Native service arguments must be exact text')
    escaped=value.replace('\\','\\\\').replace('"','\\"').replace('%','%%')
    for char,code in (('\n','\\n'),('\r','\\r'),('\t','\\t')):escaped=escaped.replace(char,code)
    return '"'+escaped+'"'


def working_directory(value):
    # WorkingDirectory uses unit_path_printf directly, unlike ExecStart's
    # quoted/C-unescaped word parser (systemd load-fragment.c).
    if value!=value.strip() or any(char in value for char in '\r\n\0') or value.endswith('\\'):
        raise ValueError('The native systemd working-directory field cannot represent this path exactly')
    return value.replace('%','%%')


def execute_native(plan,arguments,directory,host):
    return host['process'](Path(plan['manager']['path']),arguments,Path(directory),30)


def load_state(manager,name,directory,host):
    result=execute_native({'manager':manager},['--system','--no-pager','show','--property=LoadState','--value','--',name],directory,host)
    text=base64.b64decode(result['outputs'].get('stdout',{}).get('base64','')).decode('utf8').strip()
    if result['return_code']!=0 or result.get('timed_out') or text not in {'not-found','loaded','masked','error','bad-setting','merged','stub'}:
        raise host['Refused']('The native systemd unit load state is unavailable')
    return text


def inspect(request,observed,host):
    refused=host['Refused'];selected=request.get('service');installation=request.get('service_installation')
    if not sys.platform.startswith('linux'):raise refused('Service installation requires the native Linux systemd host')
    if (not isinstance(selected,dict) or set(selected)!={'manager','name'} or selected['manager']!='systemd' or
            not isinstance(selected['name'],str) or len(selected['name'])>255 or not re.fullmatch(r'[A-Za-z0-9@_.:\\-]+\.service',selected['name'])):
        raise refused('Select the exact new native MySQL service unit name')
    if not isinstance(installation,dict) or set(installation)!={'user'} or not isinstance(installation['user'],str) or not installation['user']:
        raise refused('Select the native MySQL user option for this new service')
    import pwd
    try:user=pwd.getpwnam(installation['user'])
    except KeyError:raise refused('The selected native MySQL operating-system user does not exist') from None
    programs={}
    for command in ('systemctl','systemd-analyze'):
        found=shutil.which(command)
        if found is None:raise refused('The native systemd installation tools are unavailable')
        path=Path(found).resolve(strict=True);programs[command]={'path':str(path),'sha256':host['file_hash'](path)}
    root=Path('/etc/systemd/system');parent=root.resolve(strict=True);info=parent.stat()
    path=parent/selected['name']
    if os.path.lexists(path):raise refused('Select a new native MySQL service; an existing unit file is never replaced')
    with tempfile.TemporaryDirectory(prefix='scratchrobin-systemd-install-inspect-') as temporary:
        state=load_state(programs['systemctl'],selected['name'],temporary,host)
    if state!='not-found':raise refused('The selected native service already has a systemd definition')
    configuration=observed['configuration']
    defaults=['--defaults-file='+configuration['path']] if configuration else ['--no-defaults']
    pid=request.get('native_pid_file')
    if not isinstance(pid,str) or not Path(pid).is_absolute() or '\0' in pid:raise refused('Select the native MySQL PID filename')
    args=[observed['program']['path'],*defaults,'--datadir='+observed['host']['datadir'],
        '--pid-file='+pid,'--user='+installation['user'],'--daemonize=OFF']
    # A new unit has a directly observed mysqld entry point. No shell wrapper,
    # guessed package manager, automatic server start or readiness assertion.
    context=configuration['context'] if configuration else {'working_directory':str(Path(observed['host']['datadir']).parent),'home_directory':str(Path(observed['host']['datadir']).parent)}
    try:working=working_directory(context['working_directory'])
    except ValueError as error:raise refused(str(error)) from None
    unit='[Unit]\nDescription=MySQL managed through ScratchRobin\nAfter=network.target\n[Service]\nType=simple\nWorkingDirectory='+working+'\nEnvironment='+argument('HOME='+context['home_directory'])+'\nExecStart=:'+ ' '.join(argument(value) for value in args)+'\nTimeoutStopSec=90\nRestart=on-failure\n[Install]\nWantedBy=multi-user.target\n'
    return {'selected_service':dict(selected),'path':str(path),'parent_identity':[info.st_dev,info.st_ino],
        'unit_text':unit,'unit_sha256':hashlib.sha256(unit.encode('utf8')).hexdigest(),
        'native_arguments':args,'native_user':{'name':installation['user'],'uid':user.pw_uid,'gid':user.pw_gid},
        'manager':programs['systemctl'],'validator':programs['systemd-analyze'],
        'load_state':state,'native_pid_file':pid,'automatic_start':False,'automatic_enable':False}


def execute(request,observed,directory,timeout,host):
    plan=observed['service_installation'];directory=Path(directory);path=Path(plan['path'])
    configuration=host['process'](Path(observed['program']['path']),plan['native_arguments'][1:]+['--validate-config'],directory,timeout,
        configuration_context=observed['configuration']['context'] if observed['configuration'] else None)
    result={'installed':False,'configuration_validation':configuration,'native_result':configuration,'native_result_scope':'mysqld_configuration_validation',
        'restart_issued':False,'enable_issued':False,'sql_readiness_observed':False,'automatic_retry':False}
    host['save'](directory/'service-installation.json',result)
    if configuration['return_code']!=0 or configuration.get('timed_out'):return result
    candidate=directory/path.name
    with candidate.open('xb') as stream:
        host['private_file'](candidate);stream.write(plan['unit_text'].encode('utf8'));stream.flush();os.fsync(stream.fileno())
    validation=host['process'](Path(plan['validator']['path']),['verify',str(candidate)],directory,timeout)
    result.update(validation=validation,native_result=validation,native_result_scope='systemd_unit_validation')
    host['save'](directory/'service-installation.json',result)
    if validation['return_code']!=0 or validation.get('timed_out'):return result
    if inspect(request,observed,host)!=plan:raise host['Refused']('Native unit installation inputs changed after validation')
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    temporary=None
    try:
        info=os.fstat(parent)
        if [info.st_dev,info.st_ino]!=plan['parent_identity']:raise host['Refused']('Native service installation directory changed')
        with tempfile.NamedTemporaryFile(dir=path.parent,prefix='.scratchrobin-unit-',delete=False) as stream:
            temporary=Path(stream.name);os.fchmod(stream.fileno(),0o644)
            stream.write(plan['unit_text'].encode('utf8'));stream.flush();os.fsync(stream.fileno())
        # linkat is exclusive: a competing installer or new symlink cannot be
        # overwritten between preflight and publication of this exact inode.
        os.link(temporary.name,path.name,src_dir_fd=parent,dst_dir_fd=parent,follow_symlinks=False)
        os.fsync(parent)
        info=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        result.update(installed=True,installed_identity={'device':info.st_dev,'inode':info.st_ino,
            'sha256':plan['unit_sha256'],'mode':stat.S_IMODE(info.st_mode)},daemon_reload_dispatched=False)
        host['save'](directory/'service-installation.json',result)
    finally:
        if temporary is not None:
            try:os.unlink(temporary.name,dir_fd=parent)
            except FileNotFoundError:pass
        os.close(parent)
    result['daemon_reload_dispatched']=True;host['save'](directory/'service-installation.json',result)
    result['daemon_reload']=host['process'](Path(plan['manager']['path']),['--system','--no-ask-password','daemon-reload'],directory,timeout)
    result['native_result']=result['daemon_reload']
    result['native_result_scope']='systemd_daemon_reload'
    host['save'](directory/'service-installation.json',result)
    if result['daemon_reload']['return_code']==0:
        try:result['installed_service_binding']=association(request,observed,directory,host)
        except Exception as error:result['association_error_type']=type(error).__name__
        host['save'](directory/'service-installation.json',result)
    return result


def association(request,observed,directory,host):
    plan=observed['service_installation']
    digest=lambda value:hashlib.sha256(json.dumps(value,separators=(',',':')).encode()).hexdigest()
    previous={'service_binding_verified':True,'selected_service':plan['selected_service'],
        'unit':{'Id':plan['selected_service']['name']},
        'definition_files':{plan['path']:{'resolved_path':plan['path'],'sha256':plan['unit_sha256']}},
        'command_sha256':{'ExecStart':digest([[observed['program']['path'],plan['native_arguments'],False]]),'ExecStop':digest([])}}
    value=host['native_services'].inspect({**request,'previous_service_binding':previous},observed,
        host['process'],host['file_hash'],host['regular_stream'],host['Refused'])
    value['source_association']='installed_native_unit_for_observed_datadir'
    return value


def observe(directory,value,host):
    # The private phase receipt can survive loss of the outer SSH dispatcher.
    # Its file facts do not supply a missing daemon-reload return code.
    directory=Path(directory);path=directory/'service-installation.json'
    phase=json.loads(path.read_text()) if path.is_file() else None
    plan=value['observation']['service_installation'];target=Path(plan['path'])
    facts={'original_native_result_unchanged':True,'phase_receipt':phase,'unit_file_observed':False}
    try:
        with host['regular_stream'](target) as stream:
            data=stream.read(1024*1024+1);info=os.fstat(stream.fileno())
        facts.update(unit_file_observed=True,current_sha256=hashlib.sha256(data).hexdigest(),
            matches_installed_unit=len(data)<=1024*1024 and hashlib.sha256(data).hexdigest()==plan['unit_sha256'],
            current_identity={'device':info.st_dev,'inode':info.st_ino})
    except FileNotFoundError:facts['unit_file_missing']=True
    facts['load_state']=load_state(plan['manager'],plan['selected_service']['name'],directory,host)
    if facts.get('matches_installed_unit') and facts['load_state']=='loaded':
        try:facts['service']=association({'service':plan['selected_service'],'native_pid_file':plan['native_pid_file']},value['observation'],directory,host)
        except Exception as error:facts['association_error_type']=type(error).__name__
    return {**value,'service_installation_reconciliation':facts}
