"""Native, privately supervised MySQL recovery instances on their backup host."""
import configparser
import json
import os
from pathlib import Path
import re
import shutil
import signal
import socket
import subprocess
import sys
import time

try:
    import _cdeadmin_physical_worker as physical
except ModuleNotFoundError:
    from . import mysql_physical_worker as physical

host = physical.host
Refused = physical.Refused


def successful(value):
    return (value.get('return_code') == 0 and not value.get('error_type') and
        value.get('supervisor_finished') is True and value.get('credential_cleanup_confirmed') is True and
        value.get('process_termination_confirmed') is True)


def configuration(path, *, keyring=False):
    """Consume only admitted native geometry, never arbitrary server options."""
    text = physical.metadata(path)
    # XtraBackup can emit an observed option after its original command-line
    # value. Native MySQL applies the last occurrence; duplicate output is valid.
    parser = configparser.ConfigParser(interpolation=None, strict=False)
    parser.read_string(text)
    if parser.sections() != ['mysqld'] or parser.defaults():
        raise Refused('Recovery requires the admitted native backup configuration')
    values = dict(parser['mysqld'])
    paths = {'datadir', 'tmpdir', 'innodb_data_home_dir', 'innodb_log_group_home_dir',
        'innodb_undo_directory', 'innodb_buffer_pool_filename', 'innodb_directories'}
    numeric = {'innodb_page_size', 'innodb_redo_log_capacity', 'innodb_log_block_size',
        'innodb_undo_tablespaces', 'server_id'}
    enumerated = {'innodb_checksum_algorithm', 'innodb_flush_method'}
    metadata = {'server_uuid', 'master_key_id'}
    encryption = {'innodb_redo_log_encrypt', 'innodb_undo_log_encrypt'}
    allowed = paths | numeric | enumerated | metadata | encryption | {'innodb_data_file_path','innodb_log_checksums'}
    if set(values) - allowed:
        raise Refused('Native backup configuration needs additional recovery option admission: ' + ', '.join(sorted(set(values)-allowed)))
    if 'server_uuid' in values: physical.job_id(values['server_uuid'])
    if not re.fullmatch('[0-9]+',values.get('master_key_id','0')) or int(values.get('master_key_id','0'))>18446744073709551615:
        raise Refused('Native recovery master-key identity is unavailable')
    if any(values[key] not in {'0','1','ON','OFF','true','false'} for key in encryption & values.keys()):
        raise Refused('Native recovery encryption setting is not an admitted boolean')
    if not keyring and (values.get('master_key_id','0') != '0' or any(values[key] not in {'0','OFF'} for key in encryption & values.keys())):
        raise Refused('Encrypted native recovery requires separately admitted keyring provisioning')
    for key in numeric & values.keys():
        if not re.fullmatch(r'[0-9]+', values[key]):
            raise Refused('Native recovery geometry is not an admitted integer: '+key)
    if values.get('innodb_log_checksums','ON') not in {'ON','OFF','0','1','true','false'}:
        raise Refused('Native log checksum option is not an admitted boolean')
    for key in enumerated & values.keys():
        if not re.fullmatch(r'[A-Za-z0-9_]+', values[key]):
            raise Refused('Native recovery geometry is not an admitted enumeration')
    if 'innodb_data_file_path' in values:
        # Native basename/size/autoextend syntax; absolute/external system-file
        # paths need their own mapping and cannot escape the new data directory.
        for item in values['innodb_data_file_path'].split(';'):
            if not re.fullmatch(r'[A-Za-z0-9_.-]+:[0-9]+[KMG]?(?::autoextend(?::max:[0-9]+[KMG]?)?)?', item) or item.split(':')[0] in {'.', '..'}:
                raise Refused('Native system tablespaces need separately admitted recovery path mapping')
    return {key: value for key,value in values.items() if key not in paths | metadata | {'server_id', 'innodb_log_block_size', 'innodb_undo_tablespaces', 'innodb_log_checksums'}}


def check_listener_port(port):
    with socket.socket() as listener:
        # Match native MySQL's Linux listener admission after a completed
        # connection leaves TIME_WAIT. A live listening socket still refuses.
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        try:listener.bind(('127.0.0.1',port))
        except OSError:raise Refused('Selected recovery loopback TCP port is already occupied') from None


def tls_files(request):
    selected=request.get('recovery_tls')
    if selected is None:return None
    if not request.get('recovery_port') or not isinstance(selected,dict) or set(selected)!={'ssl_ca','ssl_cert','ssl_key'}:
        raise Refused('Native recovery TLS requires its own loopback listener and host CA/certificate/key')
    result={}
    for name,value in selected.items():
        path=physical.absolute(value)
        with host.regular_stream(path) as stream:data=stream.read(131073)
        if not data or len(data)>131072:raise Refused('Native recovery TLS material exceeds its bound')
        result[name]={'path':str(path),'sha256':physical.hashlib.sha256(data).hexdigest()}
    return result


def inspection(request):
    if not sys.platform.startswith('linux') or not hasattr(os, 'pidfd_open') or not hasattr(signal, 'pidfd_send_signal'):
        raise Refused('Managed recovery requires a native Linux host with process descriptor control')
    import pwd
    binding = physical.host_scope(request)
    root = physical.root_directory(request['workspace'], binding)
    if type(request.get('timeout_seconds')) is not int or not 1 <= request['timeout_seconds'] <= 604800:
        raise Refused('Select a bounded recovery-instance lifetime')
    if type(request.get('memory_bytes')) is not int or not 67108864 <= request['memory_bytes'] <= 17179869184:
        raise Refused('Select bounded native recovery buffer memory')
    if request.get('recovery_gtid_mode') not in {'OFF', 'OFF_PERMISSIVE', 'ON_PERMISSIVE', 'ON'}:
        raise Refused('Select the native recovery GTID mode explicitly')
    port = request.get('recovery_port',0)
    if type(port) is not int or port != 0 and not 1024 <= port <= 65535 or port and port == request['sql_port']:
        raise Refused('Select a separate native recovery loopback TCP port or no TCP listener')
    if type(request.get('recovery_local_infile',False)) is not bool:raise Refused('Select trusted recovery checksum input explicitly')
    if port:check_listener_port(port)
    tls=tls_files(request)
    if 'ssl_cert' in request.get('sql_tls_policy',{}).get('files',{}) and tls is None:
        raise Refused('Provision native recovery server TLS and a loopback port for the delegated certificate profile')
    mode=request.get('recovery_mode','read_only')
    if mode not in {'read_only','replay'}:raise Refused('Select a native recovery startup mode')
    replay=mode=='replay';server_id=request.get('recovery_server_id')
    if replay and (not port or type(server_id) is not int or not 1<=server_id<=4294967295):
        raise Refused('Native writable recovery requires an explicit loopback TCP listener and server ID')
    if not replay and server_id is not None:raise Refused('Read-only recovery does not accept a replay server ID')
    source = root / physical.job_id(request['input_job_id'])
    if (source/'retention-intent.json').exists():raise Refused('Physical input has entered reviewed retention')
    receipt = physical.read_json(source / 'result.json')
    if not successful(receipt) or not receipt.get('restored_files') or receipt.get('phase') != 'copy_back':
        raise Refused('Select a completed, verified isolated copy-back as the recovery base')
    files = physical.manifest(source / 'artifact')
    if files != receipt['restored_files']['files']:
        raise Refused('The isolated copy-back bytes changed before recovery admission')
    prior = physical.read_json(source / 'request.json')
    if prior.get('phase') != 'copy_back' or prior.get('binding') != request['binding'] or prior.get('workspace') != str(root):
        raise Refused('The native copy-back belongs to another source or host workspace')
    prepared = root / physical.job_id(prior['input_job_id'])
    base = physical.read_json(prepared / 'result.json')
    if not successful(base) or not base.get('artifact', {}).get('prepared'):
        raise Refused('The original prepared artifact configuration is unavailable')
    config = prepared / 'artifact' / 'backup-my.cnf'
    config_hash = host.file_hash(config)
    if not any(item['path'] == 'backup-my.cnf' and item['sha256'] == config_hash for item in base['artifact']['files']):
        raise Refused('The native backup configuration changed after preparation')
    material=physical.keyring_module().audit(source/'artifact')
    keyring=physical.keyring_module().inspect(request,material)
    external=physical.paths_module().admission(request,base['artifact'].get('external_tablespaces',[]))
    # The UUID is assigned after review. All accepted job identities have the
    # same length, so the socket pathname bound is known before dispatch.
    if len(os.fsencode(str(root / ('0' * 36) / 'runtime.sock'))) > 100:
        raise Refused('Select a shorter private workspace for the native Unix socket')
    account = pwd.getpwuid(os.geteuid())
    return {'host': binding, 'workspace': str(root), 'mysql': physical.executable(request['mysql'], 'mysql'),
        'mysqld': physical.executable(request['mysqld'], 'mysqld'),
        'os_account': {'uid': os.geteuid(), 'gid': os.getegid(), 'name': account.pw_name},
        'input': {'job_id': request['input_job_id'], 'manifest_sha256': host.digest(files), 'file_count': len(files)},
        'configuration': configuration(config,keyring=keyring is not None), 'configuration_sha256': config_hash,
        **({'keyring':keyring} if keyring is not None else {}),
        **({'external_paths':external} if external is not None else {}),
        'transport': 'loopback-tcp-and-private-unix-socket' if port else 'private-unix-socket-only', 'recovery_port':port, 'automatic_upgrade': False,
        'replication_autostart': False, 'group_replication_autostart': False, 'event_scheduler': 'DISABLED', 'super_read_only': not replay,
        'recovery_local_infile':request.get('recovery_local_infile',False),
        **({'recovery_tls':tls} if tls is not None else {}),
        'recovery_mode':mode,'binary_logging':replay,'recovery_server_id':server_id,
        'recovery_gtid_mode': request['recovery_gtid_mode'], 'maximum_lifetime_seconds': request['timeout_seconds']}


def birth(pid, program):
    path = Path('/proc') / str(pid)
    fields = (path / 'stat').read_text().rpartition(')')[2].split()
    with host.regular_stream(path/'exe') as stream:
        info=os.fstat(stream.fileno());checksum=physical.hashlib.sha256()
        while data:=stream.read(1024*1024):checksum.update(data)
    if checksum.hexdigest() != program['sha256']:
        raise Refused('The native recovery process executable differs from its review')
    current=(path/'stat').read_text().rpartition(')')[2].split()
    if current[19]!=fields[19] or current[0]=='Z':
        raise FileNotFoundError('Original native process ended during observation')
    image=(path/'exe').stat()
    if (image.st_dev,image.st_ino)!=(info.st_dev,info.st_ino):
        raise Refused('The native recovery process changed its executing image during observation')
    return {'pid': pid, 'start_ticks': fields[19], 'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'executable': program, 'uid': path.stat().st_uid,
        'executable_file':{'device':str(info.st_dev),'inode':str(info.st_ino)}}


def present(value):
    """False proves the original birth ended; uncertainty never authorizes a signal."""
    if value['boot_id'] != Path('/proc/sys/kernel/random/boot_id').read_text().strip(): return False
    path = Path('/proc') / str(value['pid'])
    try:
        fields = (path / 'stat').read_text().rpartition(')')[2].split()
        if fields[19] != value['start_ticks'] or fields[0] == 'Z': return False
        current=birth(value['pid'],value['executable'])
        if (any(current[key]!=value[key] for key in ('pid','start_ticks','boot_id','executable','uid')) or
                'executable_file' in value and current['executable_file']!=value['executable_file']):
            raise Refused('Original recovery process association is uncertain')
        return True
    except FileNotFoundError: return False


def stop(value, selected_signal=signal.SIGTERM):
    # A pidfd binds the signal to this original process even if its numeric PID
    # is reused between observation and signal delivery.
    try: descriptor = os.pidfd_open(value['pid'])
    except ProcessLookupError: return False
    try:
        if not present(value): return False
        signal.pidfd_send_signal(descriptor, selected_signal)
        return True
    finally: os.close(descriptor)


def observe(directory, value, action):
    value = dict(value)
    if action == 'cancel':
        host.save(directory/'cancel', {'requested_at':time.time(),'input_digest':value['input_digest']})
    if value.get('supervisor_process'):
        try: value['supervisor_process_live'] = present(value['supervisor_process'])
        except (OSError, Refused): value['supervisor_process_live'] = None
    process = value.get('runtime_process')
    if process:
        try:
            live = present(process)
            value['runtime_process_live'] = live
            if live and value.get('filesystem_isolation'):
                try:value['filesystem_isolation_observation']=physical.paths_module().observe(process['pid'],value['filesystem_isolation'])
                except (OSError,Refused) as error:
                    value['filesystem_isolation_observation']={'native_filesystem_isolation_observed':False,'error_type':type(error).__name__}
            value['process_presence_observed_at'] = time.time()
            if not live:
                value['process_termination_confirmed'] = True
            if action == 'cancel' and live:
                request = {'state':'dispatching','requested_at':time.time(),'signal':'SIGTERM','process':process}
                host.save(directory/'stop-request.json',request)
                request.update(state='observed',signal_delivered=stop(process),observed_at=time.time())
                host.save(directory/'stop-request.json',request)
        except (OSError, Refused):
            value['runtime_process_live'] = None
            value['process_presence_unknown'] = True
    value['recovery_running_verified'] = bool(value.get('sql_ready_observed') and value.get('runtime_process_live') is True and
        value.get('credential_cleanup_confirmed') is True and not value.get('error_type') and
        (not value.get('filesystem_isolation') or value.get('filesystem_isolation_observation',{}).get('native_filesystem_isolation_observed') is True))
    if value.get('supervisor_process_live') is False and not value.get('supervisor_finished'):
        value['supervisor_control_unavailable'] = True
        value['native_exit_reply_unknown'] = True
    if (directory/'cancel').exists(): value['stop_requested'] = True
    if (directory/'stop-request.json').exists(): value['stop_request'] = physical.read_json(directory/'stop-request.json')
    return value


def sql_ready(request, observed, directory, option_file, data):
    query = "SELECT JSON_OBJECT('version',VERSION(),'server_uuid',@@server_uuid,'datadir',@@datadir,'socket',@@socket," \
        "'skip_networking',@@skip_networking,'port',@@port,'bind_address',CAST(@@bind_address AS CHAR CHARACTER SET utf8mb4),'skip_replica_start',@@skip_replica_start,'super_read_only',@@super_read_only,'read_only',@@read_only,'event_scheduler',@@event_scheduler," \
        "'local_infile',@@global.local_infile,'gtid_mode',@@gtid_mode,'gtid_executed',@@gtid_executed,'gtid_purged',@@gtid_purged,'log_bin',@@log_bin,'server_id',@@server_id," \
        "'log_bin_basename',CAST(@@log_bin_basename AS CHAR CHARACTER SET utf8mb4),'log_bin_index',CAST(@@log_bin_index AS CHAR CHARACTER SET utf8mb4),'log_replica_updates',@@log_replica_updates,'binlog_format',CAST(@@binlog_format AS CHAR CHARACTER SET utf8mb4)," \
        "'group_replication_autostart',CAST((SELECT VARIABLE_VALUE FROM performance_schema.global_variables WHERE VARIABLE_NAME='group_replication_start_on_boot') AS CHAR CHARACTER SET utf8mb4)," \
        "'authenticated_principal',CURRENT_USER()," \
        "'active_role',CAST(CURRENT_ROLE() AS CHAR CHARACTER SET utf8mb4)" + (
        ",'native_keyring_component',CAST((SELECT STATUS_VALUE FROM performance_schema.keyring_component_status WHERE STATUS_KEY='Component_name') AS CHAR CHARACTER SET utf8mb4),"
        "'native_keyring_data_file',CAST((SELECT STATUS_VALUE FROM performance_schema.keyring_component_status WHERE STATUS_KEY='Data_file') AS CHAR CHARACTER SET utf8mb4),"
        "'innodb_redo_log_encrypt',@@innodb_redo_log_encrypt,'innodb_undo_log_encrypt',@@innodb_undo_log_encrypt,'binlog_encryption',@@binlog_encryption"
        if observed.get('keyring') else '') + ')'
    route=(['--host=127.0.0.1','--protocol=tcp','--port='+str(request['recovery_port'])] if observed.get('recovery_tls') else
        ['--host=localhost','--protocol=socket','--socket='+str(directory/'runtime.sock')])
    result = subprocess.run([observed['mysql']['path'], '--defaults-file='+str(option_file), *route,
        '--batch', '--raw', '--skip-column-names', '--default-character-set=utf8mb4', '--execute='+query],
        cwd=directory, env=physical.native_environment(directory), capture_output=True, timeout=5, check=False)
    if result.returncode:
        error = re.search(rb'ERROR ([0-9]+)', result.stderr)
        errno = error.group(1).decode('ascii') if error else 'unavailable'
        if errno in {'2002','2003'}: return None
        raise Refused('Native recovered SQL authentication/inspection failed; native errno '+errno)
    value = json.loads(result.stdout.decode('utf8'))
    expected = request['source_identity']
    parser = configparser.ConfigParser(); parser.read_string(physical.metadata(data/'auto.cnf')); uuid = parser['auto']['server-uuid']
    physical.job_id(uuid)
    replay=request.get('recovery_mode','read_only')=='replay'
    if (value.get('server_uuid') != uuid or uuid == expected['server_uuid'] or
            value.get('version') != expected['version'] or
            value.get('authenticated_principal') != expected['authenticated_principal'] or value.get('active_role') != expected['active_role'] or
            physical.absolute(value['datadir']) != (physical.absolute(observed['external_paths']['original_datadir']) if observed.get('external_paths') else data) or physical.absolute(value['socket']) != directory/'runtime.sock' or
            value.get('skip_networking') != (0 if request.get('recovery_port') else 1) or value.get('skip_replica_start') != 1 or value.get('super_read_only') != (0 if replay else 1) or value.get('read_only') != (0 if replay else 1) or
            value.get('local_infile') != int(request.get('recovery_local_infile',False)) or
            value.get('event_scheduler') != 'DISABLED' or value.get('log_bin') != (1 if replay else 0) or value.get('gtid_mode') != request['recovery_gtid_mode']):
        raise Refused('Native recovered SQL identity or isolation differs from the reviewed instance')
    if replay and (value.get('server_id')!=request['recovery_server_id'] or value.get('log_replica_updates')!=1 or value.get('binlog_format')!='ROW' or
            physical.absolute(value['log_bin_basename'])!=directory/'recovery-bin' or physical.absolute(value['log_bin_index'])!=directory/'recovery-bin.index'):
        raise Refused('Native writable recovery binary-log configuration differs from its review')
    if request.get('recovery_port') and (value.get('port') != request['recovery_port'] or value.get('bind_address') != '127.0.0.1'):
        raise Refused('Native recovery TCP listener differs from its reviewed loopback address')
    if value.get('group_replication_autostart') not in {None,'OFF'}:
        raise Refused('Native recovered Group Replication autostart is not disabled')
    if observed.get('keyring'):
        context=observed['keyring']
        if (value.get('native_keyring_component')!='component_keyring_file' or
                physical.absolute(value['native_keyring_data_file'])!=data/physical.keyring_module().DIRECTORY/'keyring' or
                any(value.get(option)!=int(context['encryption'][key]) for option,key in
                    [('innodb_redo_log_encrypt','redo'),('innodb_undo_log_encrypt','undo'),('binlog_encryption','binlog')])):
            raise Refused('Native recovered keyring or encryption policy differs from the private reviewed instance')
    return value


def execute(directory):
    directory = Path(directory); request = physical.read_json(directory/'request.json')
    value = {'job_id':request['job_id'], 'input_digest':request['input_digest'], 'phase':'recover', 'state':'native_dispatch',
        'automatic_retry':False, 'native_may_have_dispatched':False, 'process_termination_confirmed':False,
        'credential_cleanup_confirmed':False, 'supervisor_finished':False, 'started_at':time.time()}
    child = option_file = None
    executable = Path('/proc/self/exe').resolve(strict=True)
    value['supervisor_process'] = birth(os.getpid(), {'path':str(executable),'sha256':host.file_hash(executable)})
    def save(): physical.finish(directory,value)
    def clean():
        physical.clean_client_options(directory)
        request['database_credentials'] = None; host.save(directory/'request.json',request)
        value['credential_cleanup_confirmed'] = True
    try:
        observed = inspection(request)
        if observed != request['reviewed']: raise Refused('Native recovery inputs changed after review')
        original = Path(observed['workspace'])/request['input_job_id']/'artifact'; data = directory/'runtime-data'
        shutil.copytree(original,data)
        if host.digest(physical.manifest(data)) != observed['input']['manifest_sha256']:
            raise Refused('Staged recovery bytes differ from the immutable copy-back')
        (data/'auto.cnf').unlink(missing_ok=True)  # Native startup assigns a distinct target UUID.
        args = ['--no-defaults', '--persisted-globals-load=OFF', '--upgrade=NONE', '--datadir='+str(data),
            '--socket='+str(directory/'runtime.sock'), '--pid-file='+str(directory/'runtime.pid'),
            '--log-error='+str(directory/'native-error.log'),
            '--user='+observed['os_account']['name'], '--mysqlx=OFF', '--skip-replica-start',
            '--loose-group-replication-start-on-boot=OFF',
            '--local-infile='+('ON' if request.get('recovery_local_infile',False) else 'OFF'),
            '--event-scheduler=DISABLED', '--gtid-mode='+request['recovery_gtid_mode'],
            '--enforce-gtid-consistency=ON', '--innodb-buffer-pool-size='+str(request['memory_bytes']),
            '--tmpdir='+str(directory), '--innodb-data-home-dir='+str(data), '--innodb-undo-directory='+str(data)]
        args += ['--'+key.replace('_','-')+'='+val for key,val in sorted(observed['configuration'].items())]
        for name,selected in observed.get('recovery_tls',{}).items():
            target=directory/('recovery-'+name+'.pem')
            with host.regular_stream(Path(selected['path'])) as stream:tls_data=stream.read(131073)
            if physical.hashlib.sha256(tls_data).hexdigest()!=selected['sha256']:raise Refused('Native recovery TLS files changed after review')
            with target.open('xb') as stream:host.private_file(target);stream.write(tls_data)
            args.append('--'+name.replace('_','-')+'='+str(target))
        args += (['--read-only=OFF','--super-read-only=OFF','--log-bin='+str(directory/'recovery-bin'),
            '--log-bin-index='+str(directory/'recovery-bin.index'),'--server-id='+str(request['recovery_server_id']),
            '--log-replica-updates=ON','--binlog-format=ROW','--binlog-encryption=OFF'] if request.get('recovery_mode','read_only')=='replay'
            else ['--super-read-only=ON','--skip-log-bin'])
        if observed.get('keyring'):args+=physical.keyring_module().runtime(directory,data,observed['keyring'])
        aliases=None
        if observed.get('external_paths'):
            aliases,native_paths=physical.paths_module().runtime(directory,data,observed['external_paths'])
            args+=native_paths
        args += ['--bind-address=127.0.0.1','--port='+str(request['recovery_port'])] if request.get('recovery_port') else ['--skip-networking']
        if (directory/'cancel').exists(): raise InterruptedError('Recovery cancelled before native dispatch')
        option_file = physical.client_options(request,directory)
        if aliases is not None:
            value['filesystem_isolation']=physical.paths_module().activate(Path(observed['workspace']),aliases,directory=directory)
            save()
        value['native_may_have_dispatched'] = True; save()
        with (directory/'stdout').open('xb') as stdout, (directory/'stderr').open('xb') as stderr:
            host.private_file(directory/'stdout'); host.private_file(directory/'stderr')
            child = subprocess.Popen([observed['mysqld']['path'],*args],stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr,
                cwd=directory,env=physical.native_environment(directory),start_new_session=True)
            value['runtime_process'] = birth(child.pid,observed['mysqld']); save()
            deadline = time.monotonic()+request['timeout_seconds']; ready_deadline = min(deadline,time.monotonic()+90)
            while child.poll() is None:
                if (directory/'cancel').exists() or time.monotonic() >= deadline:
                    value.update(stop_requested=(directory/'cancel').exists(), lifetime_expired=time.monotonic()>=deadline)
                    stop(value['runtime_process'])
                    try: child.wait(timeout=30)
                    except subprocess.TimeoutExpired:
                        value['forced_termination'] = stop(value['runtime_process'],signal.SIGKILL); child.wait(timeout=15)
                    break
                if not value.get('sql_ready_observed'):
                    ready = sql_ready(request,observed,directory,option_file,data)
                    if ready:
                        clean(); value.update(state='recovery_running',sql_ready_observed=True,sql_identity=ready,
                            sql_ready_at=time.time(),data_directory=observed['external_paths']['original_datadir'] if aliases is not None else str(data),
                            physical_data_directory=str(data),socket=str(directory/'runtime.sock'))
                        save()
                    elif time.monotonic() >= ready_deadline:
                        raise Refused('Native recovered SQL readiness was not observed before its startup deadline')
                time.sleep(.2)
        value.update(state='native_returned',return_code=child.returncode,native_reply_observed=True,
            process_termination_confirmed=True,finished_at=time.time())
        if not value.get('sql_ready_observed'): value['error_type'] = 'NativeRecoveryNotReady'
        save()
        if host.digest(physical.manifest(original)) != observed['input']['manifest_sha256']:
            raise Refused('Original copy-back bytes changed while recovery was running')
    except BaseException as error:
        if child is not None and child.poll() is None:
            try: child.terminate(); child.wait(timeout=30)
            except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=15)
        value.update(state='native_returned' if child is not None and child.poll() is not None else 'unknown' if value['native_may_have_dispatched'] else 'not_dispatched',
            error_type=type(error).__name__,error_message=str(error) if isinstance(error,(Refused,InterruptedError)) else None,
            process_termination_confirmed=child is None or child.poll() is not None)
        if child is not None and child.poll() is not None: value.update(return_code=child.returncode,native_reply_observed=True)
    finally:
        try: clean()
        except Exception as error: value['credential_cleanup_error_type'] = type(error).__name__
        if child is None or child.poll() is not None:
            try:
                for name in ('ssl_ca','ssl_cert','ssl_key'):(directory/('recovery-'+name+'.pem')).unlink(missing_ok=True)
            except OSError as error:value['server_tls_cleanup_error_type']=type(error).__name__
        value.update(supervisor_finished=True,supervisor_finished_at=time.time()); save()
