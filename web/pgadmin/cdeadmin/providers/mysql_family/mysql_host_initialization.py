"""Native Linux MySQL initialization before a SQL endpoint exists.

A detached, single-admission guardian owns the original process and log files.
Independent writer/session observations never manufacture its missing outcome.
"""
import base64
import configparser
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import sys
import time

SCOPE='mysql-initialization-host-v1'
LIMIT=512*1024


def kernel():
    return {'boot_id':Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'pid_namespace':os.readlink('/proc/self/ns/pid')}


def host_binding(value):
    if not sys.platform.startswith('linux'):raise ValueError('Native initialization requires the Linux host adapter')
    if not isinstance(value,dict) or value.get('scope')!=SCOPE:raise ValueError('Select an authenticated native initialization host')
    target=Path(value['datadir'])
    if not target.is_absolute():raise ValueError('Select an absolute native initialization data directory')
    parent=target.parent.resolve(strict=True);target=parent/target.name
    return {'scope':SCOPE,'hostname':socket.gethostname(),'datadir':str(target),'platform':sys.platform,
        'python_version':list(sys.version_info[:3]),**kernel()}


def facts(path):
    path=Path(path)
    if path.is_symlink():raise ValueError('Native initialization directory identity changed')
    if not path.exists():return {'exists':False}
    info=path.lstat()
    if not stat.S_ISDIR(info.st_mode):raise ValueError('Select a native data directory or an unused directory name')
    names=[]
    for child in path.iterdir():
        if len(names)>=10000:raise ValueError('Native directory observation exceeds its entry bound')
        names.append(child.name)
    return {'exists':True,'device':info.st_dev,'inode':info.st_ino,'mode':stat.S_IMODE(info.st_mode),
        'uid':info.st_uid,'gid':info.st_gid,'entries':sorted(names)}


def inspect(request,observed):
    selected=request.get('initialization')
    if (not isinstance(selected,dict) or set(selected)!={'datadir','user','secure'} or
            type(selected['secure']) is not bool or not isinstance(selected['user'],str) or
            not selected['user'] or '\0' in selected['user'] or len(selected['user'])>512):
        raise ValueError('Select exact native initialization directory, user and secure-password mode')
    target=Path(observed['host']['datadir'])
    if target==Path(target.anchor) or target==Path.home().resolve():
        raise ValueError('Select a bounded native initialization directory')
    before=facts(target)
    if any(not name.startswith('.') and name!='lost+found' for name in before.get('entries',[])):
        raise ValueError('The native initialization data directory contains existing data')
    parent=target.parent.stat()
    return {'datadir':str(target),'requested_datadir':selected['datadir'],'before':before,'parent_identity':[parent.st_dev,parent.st_ino],
        'user':selected['user'],'secure':selected['secure'],
        'native_instance_identity_before_initialization':None}


def fence_path(target):
    return target.parent/('.scratchrobin-mysql-init-'+hashlib.sha256(os.fsencode(target.name)).hexdigest()+'.json')


def read(path):
    if path.is_symlink() or path.stat().st_size>2*1024*1024:raise ValueError('Native initialization metadata changed')
    return json.loads(path.read_text())


def ticks(pid):
    return (Path('/proc')/str(pid)/'stat').read_text().rpartition(')')[2].split()[19]


def output(path):
    if not path.exists():return {'base64':'','total_bytes':'0','truncated':False,'sha256':hashlib.sha256(b'').hexdigest()}
    if path.is_symlink():raise ValueError('Native initialization output changed')
    digest=hashlib.sha256();kept=bytearray();size=0
    with path.open('rb') as stream:
        while chunk:=stream.read(65536):
            digest.update(chunk);size+=len(chunk);kept.extend(chunk[:max(0,LIMIT-len(kept))])
    return {'base64':base64.b64encode(kept).decode('ascii'),'total_bytes':str(size),'sha256':digest.hexdigest(),'truncated':size>len(kept)}


def release(intent,directory):
    path=fence_path(Path(intent['observed']['initialization_plan']['datadir']))
    if not path.exists():return
    value=read(path)
    if value!={'job_id':intent['request']['job_id'],'input_digest':intent['request']['input_digest'],
        'nonce':intent['nonce'],'workspace':intent['request']['workspace']}:
        raise ValueError('Another native initialization owns the directory claim')
    path.unlink()
    descriptor=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(descriptor)
    finally:os.close(descriptor)


def start(request,observed,directory,host,launch_source):
    if launch_source is None:raise host['Refused']('The native initialization guardian is unavailable')
    directory=Path(directory);target=Path(observed['initialization_plan']['datadir'])
    intent={'request':request,'observed':observed,'nonce':secrets.token_hex(16)}
    path=fence_path(target)
    descriptor=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(descriptor,'w') as stream:
        json.dump({'job_id':request['job_id'],'input_digest':request['input_digest'],'nonce':intent['nonce'],'workspace':request['workspace']},stream)
        stream.flush();os.fsync(stream.fileno())
    host['save'](directory/'initializer-request.json',intent)
    script=directory/'initializer-guardian.py'
    with script.open('x') as stream:
        host['private_file'](script);stream.write(launch_source);stream.flush();os.fsync(stream.fileno())
    try:
        subprocess.Popen([sys.executable,'-u',str(script),str(directory)],stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True,cwd=directory,
            env=host['environment'](Path(sys.executable),directory))
    except BaseException:
        release(intent,directory);raise
    deadline=time.monotonic()+request['timeout_seconds']+15
    while time.monotonic()<deadline:
        value=read(directory/'result.json')
        if value.get('state')=='native_process_returned':return value
        time.sleep(.05)
    return read(directory/'result.json')


def guardian(directory,host):
    import fcntl
    directory=Path(directory);intent=read(directory/'initializer-request.json');request=intent['request'];observed=intent['observed']
    with (directory/'initializer.lock').open('a+b') as lock:
        host['private_file'](directory/'initializer.lock')
        try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:return
        if (directory/'initializer-started.json').exists():return
        marker={'input_digest':request['input_digest'],'nonce':intent['nonce'],'guardian_pid':os.getpid(),
            'guardian_start_ticks':ticks(os.getpid()),'session_id':os.getsid(0),'kernel':kernel()}
        host['save'](directory/'initializer-started.json',marker)
        value=read(directory/'result.json');child=None;native=None
        try:
            current=host['inspect'](request,observed)
            if current!=observed:raise ValueError('Native initialization inputs changed before guardian dispatch')
            plan=observed['initialization_plan'];configuration=observed['configuration']
            defaults=['--defaults-file='+configuration['path']] if configuration else ['--no-defaults']
            arguments=[observed['program']['path'],*defaults,'--initialize=ON',
                '--initialize-insecure='+('OFF' if plan['secure'] else 'ON'),
                '--datadir='+plan['datadir'],'--user='+plan['user'],'--daemonize=OFF','--skip-log-error']
            environment=host['environment'](Path(observed['program']['path']),directory)
            # mysqld may drop to --user. The receipt directory remains private
            # to SSH authority; native temporary files use the engine's option
            # file/default location rather than that inaccessible directory.
            environment.pop('TMPDIR',None)
            working=Path(plan['datadir']).parent
            if configuration:
                working=Path(configuration['context']['working_directory']);environment['HOME']=configuration['context']['home_directory']
            started=time.time();cancelled=False;timed_out=False
            with (directory/'initializer.stdout').open('xb') as stdout,(directory/'initializer.stderr').open('xb') as stderr:
                host['private_file'](directory/'initializer.stdout');host['private_file'](directory/'initializer.stderr')
                child=subprocess.Popen(arguments,cwd=working,env=environment,stdin=subprocess.DEVNULL,stdout=stdout,stderr=stderr)
                try:process={'pid':child.pid,'start_ticks':ticks(child.pid),'session_id':marker['session_id']}
                except FileNotFoundError:process={'pid':child.pid,'start_ticks':None,'session_id':marker['session_id']}
                host['save'](directory/'initializer-process.json',process)
                while child.poll() is None:
                    cancel=directory/'initializer-cancel.json'
                    cancelled=cancel.exists() and read(cancel).get('nonce')==intent['nonce']
                    timed_out=time.time()-started>request['timeout_seconds']
                    if cancelled or timed_out:
                        child.terminate()
                        try:child.wait(timeout=5)
                        except subprocess.TimeoutExpired:child.kill();child.wait()
                        break
                    time.sleep(.05)
            native={'return_code':child.returncode,'timed_out':timed_out,'cancelled':cancelled,
                'native_process_termination_observed':True,'streams_closed':True,
                'outputs':{'stdout':output(directory/'initializer.stdout'),'stderr':output(directory/'initializer.stderr')}}
            target=Path(plan['datadir']);identity=None
            if child.returncode==0:
                parser=configparser.ConfigParser(interpolation=None)
                with (target/'auto.cnf').open() as stream:parser.read_file(stream)
                identity={'server_uuid':parser.get('auto','server-uuid'),'datadir':str(target),'version':observed['program']['version_output']}
            value.update(state='native_process_returned',result=native,
                initialization_result={'native_initialization_returned':child.returncode==0,'native_identity':identity,
                    'secure':plan['secure'],'native_user_option':plan['user'],'sql_readiness_observed':False,
                    'process_termination_confirmed':True,'automatic_retry':False})
        except BaseException as error:
            if child is not None and child.poll() is None:child.kill();child.wait()
            value.update(state='native_process_returned',result=native or {'return_code':None,'outputs':{
                'stdout':output(directory/'initializer.stdout'),'stderr':output(directory/'initializer.stderr')}},
                initialization_result={'native_initialization_returned':native is not None and native.get('return_code')==0,'native_identity':None,
                    'process_termination_confirmed':True,'sql_readiness_observed':False,'automatic_retry':False},
                error_type=type(error).__name__)
        host['save'](directory/'result.json',value)
        release(intent,directory)


def observe(directory,value,host,*,cancel=False,acknowledge=False):
    import fcntl
    import signal
    directory=Path(directory);intent=read(directory/'initializer-request.json')
    if intent['request']['input_digest']!=value['input_digest']:raise ValueError('Original initialization request differs')
    if cancel:host['save'](directory/'initializer-cancel.json',{'nonce':intent['nonce']})
    facts={'original_native_result_unchanged':True,'automatic_retry':False,'process_termination_confirmed':False}
    if value.get('state')=='native_process_returned' and (value.get('initialization_result') or {}).get('process_termination_confirmed'):
        facts['process_termination_confirmed']=True
    elif not (directory/'initializer-started.json').exists():facts['reason']='original_guardian_admission_unconfirmed'
    else:
        marker=read(directory/'initializer-started.json')
        if marker.get('nonce')!=intent['nonce'] or marker.get('input_digest')!=value['input_digest']:
            raise ValueError('Original initialization guardian identity differs')
        with (directory/'initializer.lock').open('a+b') as lock:
            try:fcntl.flock(lock.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:facts['reason']='original_guardian_still_active'
            else:
                current=kernel();old=marker['kernel']
                if current['boot_id']!=old['boot_id']:facts['process_termination_confirmed']=True
                elif current['pid_namespace']!=old['pid_namespace']:facts['reason']='original_process_namespace_unavailable'
                else:
                    live=[]
                    for name in os.listdir('/proc'):
                        if not name.isdigit():continue
                        try:
                            if os.getsid(int(name))==marker['session_id']:
                                state=(Path('/proc')/name/'stat').read_text().rpartition(')')[2].split()[0]
                                if state not in {'Z','X'}:live.append(int(name))
                        except (ProcessLookupError,FileNotFoundError):continue
                        except PermissionError:facts['reason']='original_process_scan_denied';break
                    else:
                        facts.update(original_session_live_processes=live,process_termination_confirmed=not live)
                        if cancel and live and (directory/'initializer-process.json').exists():
                            process=read(directory/'initializer-process.json');pid=process['pid']
                            try:
                                descriptor=os.pidfd_open(pid)
                                try:
                                    if process['start_ticks'] is not None and ticks(pid)==process['start_ticks'] and os.getsid(pid)==marker['session_id']:
                                        signal.pidfd_send_signal(descriptor,signal.SIGKILL);facts['original_native_cancellation_requested']=True
                                finally:os.close(descriptor)
                            except ProcessLookupError:pass
    if acknowledge:
        if not facts['process_termination_confirmed']:raise ValueError('Original initialization writers have not ended')
        release(intent,directory);facts['target_claim_released']=True
    return {**value,'initialization_reconciliation':facts}
