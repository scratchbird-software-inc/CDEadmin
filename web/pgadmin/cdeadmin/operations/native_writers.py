"""Inspect and stop only reviewed native executables in owned job workspaces."""
import hashlib
from pathlib import Path
import socket

import psutil


class NativeWriterError(ValueError):
    pass


def executable_hash(path):
    digest=hashlib.sha256()
    with Path(path).open('rb') as source:
        while data:=source.read(1048576):digest.update(data)
    return digest.hexdigest()


def inspect(scopes, *, hostname, started_at, expected=()):
    if hostname!=socket.gethostname():
        raise NativeWriterError('Inspect native writers on the application host recorded by this job')
    admitted={}
    for scope in scopes:
        directory=Path(scope['directory'])
        if (not directory.is_absolute() or not directory.is_dir() or directory.resolve()!=directory or
                directory.is_symlink() or getattr(directory.lstat(),'st_file_attributes',0)&0x400):
            raise NativeWriterError('An owned native writer workspace is unavailable')
        identities=scope['executables']
        if not identities:raise NativeWriterError('Reviewed native executable identities are unavailable')
        admitted[str(directory)]=dict(identities)
    expected_by_pid={}
    for item in expected:
        pid,created=item.get('pid'),item.get('process_create_time')
        if (pid is None)!=(created is None):raise NativeWriterError('Recorded native process creation identity is incomplete')
        if pid is not None:
            if type(pid) is not int or pid<=0 or isinstance(created,bool) or not isinstance(created,(int,float)):
                raise NativeWriterError('Recorded native process creation identity is invalid')
            if pid in expected_by_pid and expected_by_pid[pid]!=created:
                raise NativeWriterError('Recorded native process creation identities disagree')
            expected_by_pid[pid]=created
    candidates={};absent=set();refusals=[]
    for process in psutil.process_iter():
        try:
            created=process.create_time();expected_created=expected_by_pid.get(process.pid)
            reused=expected_created is not None and created!=expected_created
            if reused:absent.add(process.pid)
            if process.status() in {psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD}:
                if expected_created is not None:absent.add(process.pid)
                continue
            expected_process=expected_created is not None and not reused
            directory=str(Path(process.cwd()).resolve())
            if directory not in admitted:
                if expected_process:refusals.append('Recorded native process no longer belongs to an owned job workspace')
                continue
            if created<float(started_at)-1:
                if expected_process:refusals.append('Recorded native process predates this dispatch')
                continue
            digest=executable_hash(process.exe())
            tool=admitted[directory].get(digest)
            if tool is None:
                if expected_process:refusals.append('Recorded process does not match a reviewed native executable')
                continue
            if reused:
                # Never signal the new process, and never pretend its current
                # workspace is free of a possible writer.
                refusals.append('A reused process identity is now using this workspace; do not infer writer termination')
                continue
            candidates[process.pid]=(process,created,directory,digest,tool)
        except psutil.NoSuchProcess:
            if process.pid in expected_by_pid:absent.add(process.pid)
        except (psutil.Error,OSError):
            if process.pid in expected_by_pid:refusals.append('Recorded native process ownership could not be inspected')
    for pid,created in expected_by_pid.items():
        if pid in candidates or pid in absent:continue
        try:
            process=psutil.Process(pid)
            if process.create_time()!=created or process.status() in {psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD}:absent.add(pid)
            else:refusals.append('The recorded native writer was not admitted for reconciliation')
        except psutil.NoSuchProcess:absent.add(pid)
        except psutil.Error:refusals.append('Recorded native writer termination is unavailable')
    if refusals:raise NativeWriterError('; '.join(dict.fromkeys(refusals)))
    return candidates,sorted(absent)


def stop(candidates):
    stopped=[]
    for process,created,directory,digest,tool in candidates.values():
        try:
            if (process.create_time()!=created or str(Path(process.cwd()).resolve())!=directory or
                    executable_hash(process.exe())!=digest):
                raise NativeWriterError('Native process creation, workspace or executable identity changed')
            children=process.children(recursive=True)
            for child in reversed(children):
                try:child.terminate()
                except psutil.NoSuchProcess:pass
            try:process.terminate()
            except psutil.NoSuchProcess:pass
            _gone,alive=psutil.wait_procs([*children,process],timeout=3)
            for child in alive:
                try:child.kill()
                except psutil.NoSuchProcess:pass
            _gone,alive=psutil.wait_procs(alive,timeout=3)
            if any(item.is_running() and item.status() not in {psutil.STATUS_ZOMBIE,psutil.STATUS_DEAD} for item in alive):
                raise NativeWriterError('Owned native utility termination is unconfirmed')
            stopped.append({'pid':process.pid,'process_create_time':created,'tool':tool,'workspace':directory,'termination_confirmed':True})
        except psutil.NoSuchProcess:
            stopped.append({'pid':process.pid,'process_create_time':created,'tool':tool,'workspace':directory,'termination_confirmed':True,'already_absent':True})
        except (psutil.Error,OSError):raise NativeWriterError('Owned native utility termination could not be confirmed') from None
    return stopped
