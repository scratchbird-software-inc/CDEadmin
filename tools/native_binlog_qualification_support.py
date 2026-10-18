"""Owned native binlog processes waiting on a fixture socket, never a DB."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import psutil


@contextmanager
def waiting_binlog(directory,decoder,family,*,orphan=False):
    directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));listener.listen();listener.settimeout(10)
        arguments=[str(decoder),'--no-defaults',*(['--no-login-paths'] if family=='mysql' else []),
            '--host=127.0.0.1','--port='+str(listener.getsockname()[1]),'--user=owned',
            '--read-from-remote-server','--raw','--stop-never',
            ('--connection-server-id=' if family=='mysql' else '--stop-never-slave-server-id=')+'4000000199',
            '--result-file='+str(directory)+os.sep,'--','native.000001']
        process=child=connection=None
        try:
            with (directory/'fixture-tool.log').open('wb') as log:
                if orphan:
                    identity=directory/'fixture-process.json'
                    program=('import json,pathlib,psutil,subprocess,sys; '
                        'p=subprocess.Popen(sys.argv[2:],close_fds=True); '
                        'pathlib.Path(sys.argv[1]).write_text(json.dumps({"pid":p.pid,"created":psutil.Process(p.pid).create_time()}))')
                    subprocess.run([sys.executable,'-c',program,str(identity),*arguments],cwd=directory,
                        stdout=log,stderr=log,check=True,timeout=10)
                    value=json.loads(identity.read_text());process=psutil.Process(value['pid'])
                    assert process.create_time()==value['created']
                else:
                    child=subprocess.Popen(arguments,cwd=directory,stdout=log,stderr=log)
                    process=psutil.Process(child.pid)
                connection,_address=listener.accept()
                yield process
        finally:
            if process is not None:
                try:
                    if process.is_running() and process.status()!=psutil.STATUS_ZOMBIE:
                        process.kill();process.wait(timeout=5)
                except psutil.NoSuchProcess:pass
                except psutil.TimeoutExpired:assert process.status()==psutil.STATUS_ZOMBIE
            if child is not None:child.wait(timeout=5)
            if connection is not None:connection.close()
