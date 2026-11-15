"""Load the verified native component without initializing SQLite.

This module must remain outside pgadmin and must not import sqlite3: native
host startup policies run before the application/configuration databases open.
"""
import atexit
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
import sysconfig
import tempfile
import threading

_LOCK=threading.RLock()
_COMPONENT=None
_SQLITE_EXTENSION=None
_FILE_IO=None


def file_io():
    """Reuse the host file/ACL implementation without importing the app."""
    global _FILE_IO
    if _FILE_IO is None:
        path=Path(__file__).resolve().parent/'pgadmin/cdeadmin/operations/fileio.py'
        spec=importlib.util.spec_from_file_location('_scratchrobin_startup_fileio',path)
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        _FILE_IO=module
    return _FILE_IO


def installed_library():
    name='_cdeadmin_dbconfig'+sysconfig.get_config_var('EXT_SUFFIX')
    candidates=[Path(prefix)/directory/name for prefix in dict.fromkeys((sys.prefix,sys.base_prefix)) for directory in ('lib','bin','DLLs')]
    candidates.append(Path(__file__).resolve().parent/'pgadmin/cdeadmin/native'/name)
    return next((str(path)for path in candidates if path.is_file() and Path(str(path)+'.json').is_file()),'')


def _preload_interpreter_extension():
    global _SQLITE_EXTENSION
    if _SQLITE_EXTENSION is not None:return
    spec=importlib.util.find_spec('_sqlite3')
    if spec is None or not spec.origin or not Path(spec.origin).is_file():
        raise RuntimeError('The native SQLite component requires the interpreter shared extension')
    # Loading the interpreter's binary resolves its usual SQLite dependency,
    # but does not invoke PyInit__sqlite3 or initialize SQLite. This prevents
    # the early helper load from selecting another system SQLite by accident.
    _SQLITE_EXTENSION=ctypes.PyDLL(spec.origin)


class Component:
    def __init__(self,module,program,directory):
        self.module,self.program,self.directory=module,program,directory
        self.leases=0;self.shutting_down=False

    def retain(self):
        with _LOCK:
            if self.shutting_down:raise RuntimeError('Native configuration runtime is shutting down')
            self.leases+=1

    def release(self):
        with _LOCK:
            if self.leases<=0:raise RuntimeError('Native component ownership is unbalanced')
            self.leases-=1


def load(filename):
    global _COMPONENT
    with _LOCK:
        path=Path(filename).resolve(strict=True);metadata=Path(str(path)+'.json')
        if not path.is_file() or path.stat().st_size>64*1024*1024 or metadata.stat().st_size>65536:
            raise RuntimeError('Native configuration helper/provenance is unavailable')
        proof=json.loads(metadata.read_text(encoding='utf8'))
        if (not isinstance(proof,dict) or proof.get('adapter_abi')!=1 or proof.get('native_configuration_revision')!=1 or
                proof.get('minimum_runtime')!='3.35.0' or proof.get('python_soabi')!=sysconfig.get_config_var('SOABI') or
                str(proof.get('python_version','')).split('.')[:2]!=[str(sys.version_info.major),str(sys.version_info.minor)]):
            raise RuntimeError('Native configuration helper ABI/interpreter is not admitted')
        digest=hashlib.sha256(path.read_bytes()).hexdigest()
        if digest!=proof.get('library_sha256'):raise RuntimeError('Native helper differs from its provenance')
        if _COMPONENT is not None:
            if digest!=_COMPONENT.program['library_sha256']:raise RuntimeError('Restart before changing the loaded native configuration helper')
            return _COMPONENT
        _preload_interpreter_extension()
        directory=Path(tempfile.mkdtemp(prefix='scratchrobin-sqlite-config-'));file_io().private_directory(directory)
        target=directory/path.name;loaded=False
        try:
            with path.open('rb')as source,target.open('xb')as output:
                file_io().private_file(target);hashed=hashlib.sha256()
                while block:=source.read(1048576):output.write(block);hashed.update(block)
                output.flush();os.fsync(output.fileno())
            if hashed.hexdigest()!=digest:raise RuntimeError('Native helper changed during immutable capture')
            spec=importlib.util.spec_from_file_location('_cdeadmin_dbconfig',target)
            module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);loaded=True
            identity=module.identity()
            floor=json.loads((Path(__file__).resolve().parent/'pgadmin/cdeadmin/ui_descriptors/sqlite/capabilities.json').read_text())['version_range']['minimum']
            if (identity.get('adapter_abi')!=1 or identity.get('native_configuration_revision')!=1 or
                    tuple(map(int,identity['sqlite_version'].split('.')))<tuple(map(int,floor.split('.')))):
                raise RuntimeError('Native helper runtime is outside the declared SQLite range')
        except BaseException:
            if not loaded:shutil.rmtree(directory,ignore_errors=True)
            raise
        program={**proof,**identity,'library_sha256':digest,'scope':'application-host/original-native-handle'}
        _COMPONENT=Component(module,program,directory)
        return _COMPONENT


def _cleanup():
    with _LOCK:
        if _COMPONENT is None or _COMPONENT.leases!=0:return
        _COMPONENT.shutting_down=True
        # No owned/pending handles remain. Remove our auto-extension callback
        # before disposing its captured runtime file at process shutdown.
        if _COMPONENT.module.stop_capture():shutil.rmtree(_COMPONENT.directory,ignore_errors=True)


atexit.register(_cleanup)
