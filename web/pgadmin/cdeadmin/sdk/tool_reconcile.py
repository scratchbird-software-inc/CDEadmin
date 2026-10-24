"""Independent cleanup after a qualified native client's guardian has ended.

Only opted-in clients which do not daemonize belong to this policy. The original
receipt and database outcome are immutable; kernel/process facts live separately.
"""
import json
import os
from pathlib import Path
import stat
import signal
import hashlib

import psutil

from ..operations.fileio import exclusive_file_lock

POLICY = 'linux-parent-death-kill-v1'
LEGACY_CLIENTS={'mysql-instance-backup','mysql-instance-restore','mysql-instance-acceptance','shell-replay-client','raw-replay-decoder','raw-replay-client'}


def document(path):
    if path.is_symlink() or path.stat().st_size > 1048576:
        raise ValueError('Native reconciliation metadata changed')
    return json.loads(path.read_text())


def fingerprint(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as stream:
        while chunk:=stream.read(1048576):digest.update(chunk)
    return digest.hexdigest()


def legacy_anchor(root,intent,reference,current_host,write):
    """Bind an older invocation to a living original client before observing end."""
    path=root/'session-witness.json'
    if path.exists():
        witness=document(path)
        if (witness.get('nonce')!=reference['nonce'] or witness.get('request_sha256')!=reference['request_sha256'] or
                witness.get('executable_sha256')!=intent['executable_sha256']):
            raise ValueError('Original legacy client witness changed')
        return witness
    started=document(root/'started.json');progress=document(root/'progress.json')
    if (started.get('nonce')!=reference['nonce'] or started.get('request_sha256')!=reference['request_sha256'] or
            progress.get('nonce')!=reference['nonce']):raise ValueError('Original legacy client metadata changed')
    observed=progress['observation'];pid=observed['pid']
    if type(pid) is not int or pid<1:raise ValueError('Original legacy process is unavailable')
    process=psutil.Process(pid)
    if (process.create_time()!=observed['process_create_time'] or process.uids().real!=os.geteuid() or
            process.uids().effective!=os.geteuid() or process.cmdline()!=intent['command'] or
            os.getsid(pid)!=started['guardian_pid'] or fingerprint(Path('/proc')/str(pid)/'exe')!=intent['executable_sha256']):
        raise ValueError('Original legacy native client identity changed')
    witness={'nonce':reference['nonce'],'request_sha256':reference['request_sha256'],
        'executable_sha256':intent['executable_sha256'],'pid':pid,'process_create_time':observed['process_create_time'],
        'guardian_pid':started['guardian_pid'],'host':current_host,'credential_file_identity':None}
    credential=intent.get('credential_file')
    if credential is not None:
        candidate=Path(credential)
        if candidate.parent.resolve()!=Path(intent['workspace']).resolve() or candidate.is_symlink():
            raise ValueError('Original legacy credential scope changed')
        if candidate.exists():
            info=candidate.stat()
            if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.geteuid():
                raise ValueError('Original legacy credential ownership changed')
            witness['credential_file_identity']={'device':info.st_dev,'inode':info.st_ino,'bytes':str(info.st_size),'sha256':fingerprint(candidate)}
    write(path,witness)
    return witness


def stop_legacy_client(intent,witness,live):
    """Signal only the original sole client, through its current kernel handle."""
    if len(live)!=1 or live[0]['pid']!=witness['pid']:return False
    descriptor=os.pidfd_open(witness['pid'])
    try:
        process=psutil.Process(witness['pid'])
        if (process.create_time()!=witness['process_create_time'] or process.cmdline()!=intent['command'] or
                os.getsid(process.pid)!=witness['guardian_pid'] or process.uids().effective!=os.geteuid() or
                fingerprint(Path('/proc')/str(process.pid)/'exe')!=intent['executable_sha256']):
            raise ValueError('Original legacy native client changed before stop')
        signal.pidfd_send_signal(descriptor,signal.SIGKILL)
        return True
    finally:os.close(descriptor)


def erase(path, workspace, expected, *, wipe=False):
    """Remove only this invocation's original regular, private file."""
    path=Path(path)
    if path.parent.resolve()!=workspace.resolve() or path.is_symlink():
        raise ValueError('Native cleanup scope changed')
    try:descriptor=os.open(path,(os.O_RDWR if wipe else os.O_RDONLY)|os.O_NOFOLLOW)
    except FileNotFoundError:return True
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.geteuid():
            raise ValueError('Native private file ownership changed')
        if expected is None:raise ValueError('Original native private cleanup identity is unavailable')
        digest=hashlib.sha256()
        with os.fdopen(os.dup(descriptor),'rb') as stream:
            while data:=stream.read(1048576):digest.update(data)
        if str(info.st_size)!=str(expected['bytes']) or digest.hexdigest()!=expected['sha256']:
            raise ValueError('Native private cleanup bytes changed')
        if 'device' in expected and (info.st_dev,info.st_ino)!=(expected['device'],expected['inode']):
            raise ValueError('Native private cleanup identity changed')
        if wipe:
            os.lseek(descriptor,0,os.SEEK_SET)
            remaining=info.st_size
            while remaining:
                sent=os.write(descriptor,b'\0'*min(65536,remaining));remaining-=sent
            os.fsync(descriptor)
        current=path.stat(follow_symlinks=False)
        if (current.st_dev,current.st_ino)!=(info.st_dev,info.st_ino):
            raise ValueError('Native cleanup path changed')
        path.unlink()
        parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(parent)
        finally:os.close(parent)
        return not path.exists()
    finally:os.close(descriptor)


def reconcile(root,intent,reference,current_host,write,*,cancel=False):
    result={'available':False,'native_process_termination_confirmed':False,
        'native_outcome_inferred':False,'automatic_retry':False}
    legacy=intent.get('kernel_policy') is None and reference['name'] in LEGACY_CLIENTS
    if intent.get('kernel_policy')!=POLICY and not legacy:
        return {**result,'reason':'original_kernel_policy_unavailable'}
    original=intent['host'];boot=original.get('linux_boot_id')
    if (not boot and not legacy) or not current_host.get('linux_boot_id'):
        return {**result,'reason':'kernel_boot_identity_unavailable'}
    root=Path(root);workspace=Path(intent['workspace'])
    if root.resolve().parent!=workspace.resolve() or root.stat().st_uid!=os.geteuid():
        raise ValueError('Original native execution-host ownership changed')
    rebooted=bool(boot and boot!=current_host['linux_boot_id'])
    if not legacy and not rebooted and original.get('pid_namespace')!=current_host.get('pid_namespace'):
        return {**result,'reason':'original_process_namespace_unavailable'}
    # A read-only observer must not race the helper's first nonblocking lock.
    if not cancel and not (root/'started.json').exists():
        return {**result,'available':True,'reason':'original_guardian_admission_unconfirmed'}
    lock=root/'guardian.lock'
    if lock.is_symlink():raise ValueError('Native guardian lock changed')
    descriptor=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        info=os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1 or info.st_uid!=os.geteuid():
            raise ValueError('Native guardian lock ownership changed')
        try:
            with exclusive_file_lock(descriptor,blocking=False):
                result.update(available=True,guardian_lock_independently_free=True,kernel_boot_changed=rebooted)
                marker=root/'started.json'
                if not marker.exists():
                    if not cancel or (root/'result.json').exists() or (root/'progress.json').exists():
                        return {**result,'reason':'original_guardian_admission_unconfirmed'}
                    # The original helper refuses any second admission once this
                    # durable marker exists, including a delayed first launch.
                    write(marker,{'nonce':intent['nonce'],'request_sha256':reference['request_sha256'],
                        'guardian_pid':None,'native_start_revoked':True})
                started=document(marker)
                if started.get('nonce')!=intent['nonce'] or started.get('request_sha256')!=reference['request_sha256']:
                    raise ValueError('Native guardian admission belongs to another invocation')
                witness=None
                if legacy:
                    try:witness=legacy_anchor(root,intent,reference,current_host,write)
                    except (OSError,ValueError,KeyError,psutil.Error):return {**result,'reason':'original_legacy_native_identity_unavailable'}
                    original=witness['host'];rebooted=original['linux_boot_id']!=current_host['linux_boot_id']
                    if not rebooted and original['pid_namespace']!=current_host['pid_namespace']:
                        return {**result,'reason':'original_process_namespace_unavailable'}
                    result.update(legacy_session_independently_anchored=True,kernel_boot_changed=rebooted)
                revoked=started.get('native_start_revoked') is True
                if revoked:
                    if started.get('guardian_pid') is not None:raise ValueError('Native revocation identity changed')
                    live=[]
                elif rebooted:live=[]
                else:
                    sid=started.get('guardian_pid')
                    if type(sid) is not int or sid<1:raise ValueError('Original native guardian session is unavailable')
                    live=[]
                    for index,pid in enumerate(psutil.pids()):
                        if index>=200000:return {**result,'reason':'native_process_scan_incomplete'}
                        try:
                            if os.getsid(pid)!=sid:continue
                            process=psutil.Process(pid)
                            if process.status() not in {psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD}:
                                live.append({'pid':pid,'process_create_time':process.create_time()})
                        except (ProcessLookupError,psutil.NoSuchProcess):continue
                        except (OSError,psutil.Error):return {**result,'reason':'native_process_scan_denied'}
                result.update(original_session_live_processes=live,native_start_revoked=revoked)
                if live:
                    if legacy and cancel:
                        try:result['legacy_native_cancellation_requested']=stop_legacy_client(intent,witness,live)
                        except (OSError,ValueError,psutil.Error):result['legacy_native_cancellation_requested']=False
                    return {**result,'reason':'original_native_session_still_present'}
                result['native_process_termination_confirmed']=True
                credential=intent.get('credential_file');selected=intent.get('input_file')
                result.update(credential_file_cleanup_confirmed=credential is None,input_file_cleanup_confirmed=selected is None)
                for label,path,parent,expected,wipe in (
                    ('credential_file',credential,workspace,intent.get('credential_file_identity') or (witness or {}).get('credential_file_identity'),True),
                    ('input_file',selected.get('path') if selected else None,root,selected,False)):
                    if path is None:continue
                    try:
                        result[label+'_cleanup_confirmed']=erase(path,parent,expected,wipe=wipe)
                    except (OSError,ValueError,KeyError) as error:result[label+'_cleanup_error_type']=type(error).__name__
                result.update(nonce=intent['nonce'],request_sha256=reference['request_sha256'])
                write(root/'reconciliation.json',result)
                return result
        except BlockingIOError:return {**result,'reason':'original_guardian_still_owns_invocation'}
    finally:os.close(descriptor)
