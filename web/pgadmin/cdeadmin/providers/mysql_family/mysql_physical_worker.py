"""Standalone, private host-side XtraBackup jobs; native utilities own recovery."""
import configparser
import base64
import hashlib
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import signal
import socket
import stat
import subprocess
import sys
import time
import uuid

try:
    import _cdeadmin_native_worker as host
except ModuleNotFoundError:
    from . import mysql_host_worker as host

Refused = host.Refused
VERSION = '9.7.1-rc1'
REVISION = 'b1c9c34183de95316d8889ea3d4cb31e31ffddc5'
MAX_FILES = 200000
MAX_OUTPUT = 128 * 1024
RAW_READER_PATCH = '40abc6e5ca994a84bfc65db8dd30c92b53a09c372d42163b7ae284d9a051c761'
UNDO_READER_PATCH = 'dd79a7fc860b0bf063c8eb3f8d5bc49f331cc33c02bc3d1297d53fa867e4a610'
SYSTEM_READER_PATCH = '058bee13fabb4d64f844a68ad47c00631f1d8d946a72d6135af41e45288eaa1c'


def recovery_module():
    try:
        import _cdeadmin_recovery_worker as recovery
    except ModuleNotFoundError:
        from . import mysql_recovery_worker as recovery
    return recovery


def keyring_module():
    try:
        import _cdeadmin_keyring_worker as keyring
    except ModuleNotFoundError:
        from . import mysql_physical_keyring as keyring
    return keyring


def paths_module():
    try:
        import _cdeadmin_physical_paths as paths
    except ModuleNotFoundError:
        from . import mysql_physical_paths as paths
    return paths


def geometry_module():
    try:
        import _cdeadmin_physical_geometry as geometry
    except ModuleNotFoundError:
        from . import mysql_physical_geometry as geometry
    return geometry


def public(value):
    if isinstance(value, list): return [public(item) for item in value]
    if isinstance(value, dict):
        return {**{key: public(item) for key, item in value.items() if key != 'files'},
            **({'file_count': len(value['files'])} if isinstance(value.get('files'), list) else {})}
    return value


def absolute(value):
    path = Path(host.text(value))
    if not path.is_absolute() or path.is_symlink():
        raise Refused('Select an absolute native path without a symbolic link')
    return path.resolve()


def root_directory(value, binding):
    root = absolute(value)
    data = absolute(binding['datadir'])
    if root in {Path(root.anchor), Path.home().resolve()} or root.is_relative_to(data) or data.is_relative_to(root):
        raise Refused('Physical recovery workspace must be separate from the active data directory and its ancestors')
    if root.exists():
        info = root.stat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077:
            raise Refused('Physical workspace must be private to the authenticated OS account')
    return root


def job_id(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise Refused('Select an exact native physical job identity')
    return value


def host_scope(request, *, live=False):
    if live: return host.binding(request['binding'])
    binding = request['binding']
    if not isinstance(binding, dict) or set(binding) != {'server_uuid', 'hostname', 'datadir'}:
        raise Refused('Select the original physical source binding')
    job_id(binding['server_uuid'])
    if binding['hostname'] != socket.gethostname():
        raise Refused('The authenticated SSH host differs from this physical artifact host')
    return {'server_uuid': binding['server_uuid'], 'hostname': binding['hostname'],
        'datadir': str(absolute(binding['datadir'])), 'platform': sys.platform,
        'python_version': list(sys.version_info[:3]), 'execution_host_kind': 'database-server-ssh-host',
        'source_identity_scope': 'recorded_backup_source; live source not required'}


def read_json(path):
    with host.regular_stream(path) as stream:
        value = stream.read(32 * 1024 * 1024 + 1)
    if len(value) > 32 * 1024 * 1024:
        raise Refused('Native physical receipt exceeds its observation bound')
    return json.loads(value)


def metadata(path, maximum=1024 * 1024):
    with host.regular_stream(path) as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise Refused('Native physical metadata exceeds its observation bound')
    return value.decode('utf8')


def properties(path):
    result = {}
    for line in metadata(path).splitlines():
        if not line.strip():
            continue
        key, separator, value = line.partition('=')
        if not separator or key.strip() in result:
            raise Refused('Native physical metadata has invalid or duplicate fields')
        result[key.strip()] = value.strip()
    return result


def manifest(directory):
    directory = absolute(str(directory))
    files = []
    for parent, dirs, names in os.walk(directory, followlinks=False):
        for name in dirs:
            if (Path(parent) / name).is_symlink():
                raise Refused('Physical artifact directories cannot contain symbolic links')
        for name in names:
            path = Path(parent) / name
            if path.is_symlink() or not stat.S_ISREG(path.lstat().st_mode):
                raise Refused('Physical artifacts must contain only regular files')
            before = path.stat()
            checksum = host.file_hash(path)
            after = path.stat()
            if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino):
                raise Refused('Physical artifact changed during observation')
            files.append({'path': str(path.relative_to(directory)), 'bytes': str(after.st_size), 'sha256': checksum})
            if len(files) > MAX_FILES:
                raise Refused('Physical artifact exceeds its file observation bound')
    return sorted(files, key=lambda item: item['path'])


def merge_members(directory,files):
    """Use MySQL9.7's DD child-name interpretation, not filesystem traversal.

    myisammrg_parent_open_callback extracts the final db/table components and
    the server opens those children through its own table cache. Preserve the
    native metadata bytes, including old absolute/relative path prefixes.
    """
    available={item['path'] for item in files};result=[]
    for item in files:
        selected=Path(item['path'])
        if selected.suffix.casefold()!='.mrg':continue
        if len(selected.parts)!=2:raise Refused('Native MERGE metadata requires a database/table identity')
        for member in metadata(directory/selected).splitlines():
            if not member or member.startswith('#'):continue
            if ('\0' in member or '\\' in member or member.endswith('/') or len(member.encode('utf8'))>510):
                raise Refused('Native MERGE child identity is incompatible')
            parts=Path(member).parts
            child=selected.parent/member if len(parts)==1 else Path(*parts[-2:])
            if len(child.parts)!=2 or any(part in {'/','.', '..'} for part in child.parts):
                raise Refused('Native MERGE child database/table identity is unavailable')
            name=str(child)
            if not {name+'.MYD',name+'.MYI'}<=available:
                raise Refused('Native MERGE member MyISAM payload is missing from this complete backup')
            result.append({'metadata_file':item['path'],'native_member':member,'table_file_identity':name})
            if len(result)>MAX_FILES:raise Refused('Native MERGE member inventory exceeds its bound')
    return result


def artifact(directory, *, prepared=None):
    checkpoint = properties(directory / 'xtrabackup_checkpoints')
    info = properties(directory / 'xtrabackup_info')
    tablespaces = paths_module().tablespaces(directory)
    if (info.get('server_version') != '9.7.0' or info.get('tool_version') != VERSION or
            info.get('partial') != 'N' or info.get('incremental') not in ({'Y'} if checkpoint.get('backup_type')=='incremental' else {'N','Y'} if checkpoint.get('backup_type') in {'log-applied','full-prepared'} else {'N'}) or
            info.get('compressed') != 'N' or info.get('encrypted') != 'N' or
            checkpoint.get('backup_type') not in {'full-backuped', 'log-applied', 'full-prepared', 'incremental'}):
        raise Refused('Select an admitted complete, uncompressed MySQL9.7.0 physical artifact')
    if prepared is not None and (checkpoint['backup_type'] == 'full-prepared') != prepared:
        raise Refused('Physical artifact preparation state differs from its selected operation')
    for key in ('from_lsn', 'to_lsn', 'last_lsn'):
        if not re.fullmatch(r'[0-9]+', checkpoint.get(key, '')):
            raise Refused('Native physical LSN metadata is unavailable')
    low,high,last = (int(checkpoint[key]) for key in ('from_lsn','to_lsn','last_lsn'))
    if not 0 <= low <= high <= last <= 18446744073709551615 or checkpoint['backup_type'] != 'incremental' and low != 0:
        raise Refused('Native physical checkpoint LSN range is invalid')
    files = manifest(directory)
    members=merge_members(directory,files)
    # Existing receipts already seal ordinary relative member metadata. Add
    # derived identities for the newly admitted forms without invalidating
    # immutable receipts produced by previous adapters for the ordinary forms.
    special_members=any(Path(row['native_member']).is_absolute() or
        posixpath.normpath(str(Path(row['metadata_file']).parent/row['native_member'])).split('/')[0]=='..' for row in members)
    keyring=keyring_module().audit(directory)
    storage=geometry_module().audit(directory)
    return {'format': 'xtrabackup-9.7-incremental' if checkpoint['backup_type'] == 'incremental' else 'xtrabackup-9.7-full', 'checkpoint': checkpoint,
        'backup_uuid': info['uuid'], 'server_version': info['server_version'],
        'tool_version': info['tool_version'], 'binlog_info': metadata(directory / 'xtrabackup_binlog_info'),
        'files': files, 'manifest_sha256': host.digest(files), 'total_bytes': str(sum(int(item['bytes']) for item in files)),
        'prepared': checkpoint['backup_type'] == 'full-prepared', 'database_recovery_verified': False,
        **({'redo_only':True} if checkpoint['backup_type']=='log-applied' else {}),
        **({'native_incremental_info':True} if info['incremental']=='Y' and checkpoint['backup_type']!='incremental' else {}),
        **({'keyring':keyring} if keyring is not None else {}),
        **({'storage_geometry':storage} if storage is not None else {}),
        **({'merge_members':members} if special_members else {}),
        **({'external_tablespaces':tablespaces['external_tablespaces']} if tablespaces['external_tablespaces'] else {})}


def executable(path, kind):
    path = absolute(path)
    if path.name != kind or not os.access(path, os.X_OK):
        raise Refused('Select the native ' + kind + ' executable')
    value = subprocess.run([str(path), '--no-defaults', '--version'], capture_output=True, timeout=15,
        env={**os.environ, 'LC_ALL': 'C'}, check=False)
    output = (value.stdout + value.stderr).decode('utf8', errors='replace')
    pattern = r'xtrabackup version 9\.7\.1-rc1\b.*revision id: b1c9c341' if kind == 'xtrabackup' else r'\b(?:Ver|Distrib)\s+9\.7\.0\b'
    if value.returncode or not re.search(pattern, output):
        raise Refused('The selected native ' + kind + ' does not match the admitted version/revision')
    return {'path': str(path), 'sha256': host.file_hash(path), 'version_output': output.strip()}


def raw_storage_backend(executable,*,optional=False):
    """Bind the source-qualified reader and its private native dependencies."""
    root=Path(executable['path']).parent.parent
    try:
        if optional and not (root/'PROVENANCE.json').exists():return None
        if (root/'PROVENANCE.json').is_symlink():raise Refused('Select the original native package provenance')
        value=read_json(root/'PROVENANCE.json')
        system_numbered=isinstance(value,dict) and value.get('patch_sha256')==SYSTEM_READER_PATCH
        numbered=isinstance(value,dict) and value.get('patch_sha256') in {UNDO_READER_PATCH,SYSTEM_READER_PATCH}
        patch=SYSTEM_READER_PATCH if system_numbered else UNDO_READER_PATCH if numbered else RAW_READER_PATCH
        capabilities=['raw-system-files-v1']+(['undo-numbers-v1'] if numbered else [])+(['system-file-numbers-v1'] if system_numbered else [])
        if (not isinstance(value,dict) or value.get('schema')!='scratchrobin.native-backup-build.v1' or value.get('upstream_revision')!=REVISION or
                value.get('patch_sha256')!=patch or value.get('binary_sha256')!=executable['sha256'] or
                value.get('research_candidate_only') is not False or value.get('capabilities')!=capabilities):
            raise Refused('Native system files require the separately qualified native backup dependency')
        qualification=value.get('qualification',{})
        if (not isinstance(qualification,dict) or qualification.get('binary_sha256')!=executable['sha256'] or
                qualification.get('qualified_extents')!=['fixed','autoextended'] or qualification.get('multiple_system_files') is not True):
            raise Refused('Qualify fixed, autoextended and multiple native raw system files before admission')
        if numbered and qualification.get('duplicate_undo_paths') is not True:
            raise Refused('Qualify native duplicate undo paths before admitting numbered backup names')
        if system_numbered and qualification.get('duplicate_system_paths') is not True:
            raise Refused('Qualify native system-file collisions before admitting ordinal backup names')
        files=value['package_files']
        if (not isinstance(files,dict) or len(files)>128 or files.get('bin/xtrabackup')!=executable['sha256'] or
                files.get('native-raw.patch')!=patch):
            raise Refused('Native raw-reader package identity is unavailable')
        for name,checksum in files.items():
            path=Path(name)
            if (not isinstance(checksum,str) or not re.fullmatch('[a-f0-9]{64}',checksum) or path.is_absolute() or
                    any(part in {'','.', '..'} for part in name.split('/')) or
                    not absolute(str(root/path)).is_relative_to(root) or host.file_hash(absolute(str(root/path)))!=checksum):
                raise Refused('Native raw-reader package bytes changed')
        libraries=value['libraries']
        if not isinstance(libraries,dict) or not libraries or any(files.get('lib/'+name)!=checksum for name,checksum in libraries.items()):
            raise Refused('Native raw-reader dependencies are unavailable')
        return {'format':'raw-system-files-v1','manifest_sha256':host.file_hash(root/'PROVENANCE.json'),
            'patch_sha256':patch,'binary_sha256':executable['sha256'],'libraries':libraries,
            **({'undo_naming':geometry_module().UNDO_NAMING} if numbered else {}),
            **({'system_naming':geometry_module().SYSTEM_NAMING} if system_numbered else {})}
    except (OSError,ValueError,KeyError,TypeError):
        raise Refused('Native system files require the separately qualified native backup dependency') from None


def input_artifact(request, root, selected):
    source=root/job_id(selected)
    if (source/'retention-intent.json').exists():raise Refused('Physical input has entered reviewed retention')
    original=read_json(source/'request.json');receipt=read_json(source/'result.json')
    if (original.get('job_id')!=selected or original.get('binding')!=request['binding'] or absolute(original.get('workspace'))!=root or
            original.get('input_digest')!=receipt.get('input_digest') or receipt.get('state')!='native_returned' or
            receipt.get('return_code')!=0 or receipt.get('error_type') or not receipt.get('artifact') or
            receipt.get('process_termination_confirmed') is not True or receipt.get('credential_cleanup_confirmed') is not True):
        raise Refused('Select a completed verified physical input from this original source and host workspace')
    verified=artifact(source/'artifact')
    if verified!=receipt['artifact']:raise Refused('Physical input bytes changed after native publication')
    chain=receipt.get('lineage')
    if chain is None and original.get('phase')=='backup' and not original.get('input_job_id'):
        chain={'base_job_id':selected,'incremental_job_ids':[]}
    if not isinstance(chain,dict) or set(chain)!={'base_job_id','incremental_job_ids'} or not isinstance(chain['incremental_job_ids'],list) or len(chain['incremental_job_ids'])>128:
        raise Refused('Original native incremental lineage is unavailable or exceeds its bound')
    ids=[job_id(chain['base_job_id']),*[job_id(value) for value in chain['incremental_job_ids']]]
    if len(set(ids))!=len(ids):raise Refused('Native incremental lineage contains a repeated input')
    if original['phase'] in {'backup','incremental'} and ids[-1]!=selected:raise Refused('Native backup lineage tip differs from its original job')
    return {'job_id':selected,'artifact':public(verified),'lineage':chain}


def inspection(request):
    if request['phase'] == 'recover': return recovery_module().inspection(request)
    if not sys.platform.startswith('linux'):
        raise Refused('The admitted XtraBackup backend requires a native Linux database host')
    phase=request['phase']
    binding = host_scope(request, live=phase in {'backup','incremental'})
    root = root_directory(request['workspace'], binding)
    observed = {'host': binding, 'workspace': str(root), 'xtrabackup': executable(request['executable'], 'xtrabackup'),
        'release_status': 'RC1', 'source_revision': REVISION}
    for name, low, high in [('parallel', 1, 64), ('memory_bytes', 67108864, 17179869184), ('timeout_seconds', 1, 604800)]:
        if type(request.get(name)) is not int or not low <= request[name] <= high:
            raise Refused('Select bounded native physical ' + name)
    if phase in {'backup','incremental'}:
        observed['mysql'] = executable(request['mysql'], 'mysql')
        if type(request.get('sql_port')) is not int or not 1 <= request['sql_port'] <= 65535:
            raise Refused('Select the source TCP port reachable from the database host')
        host.text(request['sql_host'])
    if phase=='backup':
        if request.get('input_job_id') is not None:raise Refused('A full backup has no input')
    elif phase in {'incremental','prepare','prepare_redo','copy_back'}:
        source=input_artifact(request,root,request['input_job_id']);observed['input']=source
        checkpoint=source['artifact']['checkpoint']['backup_type']
        if phase=='incremental' and checkpoint not in {'full-backuped','incremental'}:
            raise Refused('Base an incremental on an immutable raw full or incremental backup')
        if phase=='incremental' and len(source['lineage']['incremental_job_ids'])>=128:
            raise Refused('Native incremental chain exceeds128 increments')
        if phase=='copy_back' and checkpoint!='full-prepared':raise Refused('Finalize native preparation before copy-back')
        if phase in {'prepare','prepare_redo'} and checkpoint not in {'full-backuped','log-applied'}:
            raise Refused('Prepare a full or redo-only base; raw incremental files are not a complete data directory')
        delta=request.get('incremental_job_id')
        if delta is not None:
            if phase!='prepare_redo' or checkpoint!='log-applied':raise Refused('Apply an incremental only to a separately retained redo-only base')
            increment=input_artifact(request,root,delta);observed['incremental_input']=increment
            lineage=increment['lineage']
            if (increment['artifact']['checkpoint']['backup_type']!='incremental' or not lineage['incremental_job_ids'] or
                    lineage['incremental_job_ids'][-1]!=delta or
                    source['lineage']!={'base_job_id':lineage['base_job_id'],'incremental_job_ids':lineage['incremental_job_ids'][:-1]} or
                    source['artifact']['checkpoint']['to_lsn']!=increment['artifact']['checkpoint']['from_lsn']):
                raise Refused('Select the exact next contiguous native incremental from this full-backup lineage')
        elif phase=='prepare_redo' and checkpoint=='log-applied':
            raise Refused('Select the next incremental or finalize this redo-only copy')
    else:raise Refused('Select a native full/incremental backup, preparation or isolated copy-back')
    if phase!='prepare_redo' and request.get('incremental_job_id') is not None:raise Refused('An additional incremental input applies only to redo-only preparation')
    snapshot=observed.get('incremental_input',observed.get('input',{})).get('artifact',{}).get('keyring')
    keyring=keyring_module().inspect(request,snapshot)
    if keyring is not None:observed['keyring']=keyring
    entries=observed.get('incremental_input',observed.get('input',{})).get('artifact',{}).get('external_tablespaces',[])
    storage=observed.get('incremental_input',observed.get('input',{})).get('artifact',{}).get('storage_geometry')
    system_naming_required=False
    if phase in {'backup','incremental'}:
        try:storage=geometry_module().from_source(request,filesystem=True)
        except geometry_module().SystemNamingRequired:storage=None;system_naming_required=True
        except geometry_module().ResolutionRequired:storage=None
    source_specification=(request.get('source_storage') or {}).get('variables',{}).get('innodb_data_file_path') if phase in {'backup','incremental'} else geometry_module().configuration(root/request['input_job_id']/'artifact').get('innodb_data_file_path')
    specification=geometry_module().system_spec(source_specification,allow_duplicate_names=True) if source_specification is not None else []
    required=system_naming_required or len(specification)>1 or any(row.get('raw_mode') for row in specification) or storage is not None and (storage.get('undo_naming') is not None or storage.get('system_naming') is not None)
    explicit_undo=phase in {'backup','incremental'} and any(row.get('file_type')=='UNDO LOG' and
        (row.get('undo_number',0)>2 or row.get('tablespace_name') not in {'innodb_undo_001','innodb_undo_002'})
        for row in (request.get('source_storage') or {}).get('files',[]))
    backend=raw_storage_backend(observed['xtrabackup']) if required else raw_storage_backend(observed['xtrabackup'],optional=True) if explicit_undo else None
    if phase in {'backup','incremental'} and any(row.get('raw_mode') for row in specification) and backend['patch_sha256']==RAW_READER_PATCH:
        raise Refused('Select the current qualified native backup dependency for parallel raw-system reads')
    if storage is not None and storage.get('system_naming') is not None and (backend or {}).get('system_naming')!=storage['system_naming']:
        raise Refused('Select the qualified ordinal system-file backup dependency for this retained layout')
    if backend is not None:observed['raw_storage_backend']=backend
    if phase in {'backup','incremental'}:
        storage=geometry_module().from_source(request,filesystem=True,undo_naming=backend.get('undo_naming') if backend else None,system_naming=backend.get('system_naming') if backend else None)
    external=paths_module().admission(request,entries,storage=storage)
    if external is not None:
        observed['external_paths']=external
    if phase in {'prepare','prepare_redo','copy_back'}:
        for selected in [request['input_job_id'],*([request['incremental_job_id']] if request.get('incremental_job_id') else [])]:
            selected_directory=root/selected/'artifact'
            recovery_module().configuration(selected_directory/'backup-my.cnf',keyring=keyring is not None,
                original_datadir=request['binding']['datadir'],mapped_storage=geometry_module().audit(selected_directory))
    return observed


def native_environment(directory):
    return {'PATH': '/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin',
        'LC_ALL': 'C', 'HOME': str(directory), 'TMPDIR': str(directory)}


def client_options(request, directory, *, transition_key=None):
    credentials = request['database_credentials']
    if not isinstance(credentials, dict) or not {'user', 'password'} <= set(credentials) or set(credentials)-{'user','password','tls'}:
        raise Refused('Delegate the selected single-factor native database credential explicitly')
    def quote(value):
        if not isinstance(value, str) or '\x00' in value:
            raise Refused('Native client option text is invalid')
        return '"' + value.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t') + '"'
    settings = {'ssl-mode': 'REQUIRED'}
    tls = credentials.get('tls')
    if tls is not None:
        if (not isinstance(tls,dict) or set(tls)!={'policy','files'} or
                tls['policy']!=request.get('sql_tls_policy') or not isinstance(tls['files'],dict)):
            raise Refused('Native TLS delegation differs from its exact reviewed policy')
        policy=tls['policy']
        if (not isinstance(policy,dict) or set(policy)!={'options','files'} or not isinstance(policy['options'],dict) or
                set(policy['options'])-{'ssl-mode','ssl-cipher','tls-version','tls-ciphersuites'} or
                policy['options'].get('ssl-mode') not in {'REQUIRED','VERIFY_CA','VERIFY_IDENTITY'} or
                not isinstance(policy['files'],dict) or set(policy['files'])!=set(tls['files']) or
                set(tls['files'])-{'ssl_ca','ssl_cert','ssl_key'}):
            raise Refused('Native TLS delegation contains an unadmitted option or file')
        settings=dict(policy['options'])
        for name,encoded in tls['files'].items():
            if not isinstance(encoded,str) or len(encoded)>174764:raise Refused('Native TLS file exceeds its bound')
            data=base64.b64decode(encoded,validate=True)
            if not data or len(data)>131072 or hashlib.sha256(data).hexdigest()!=policy['files'][name]:
                raise Refused('Native TLS file differs from its original reviewed bytes')
            target=directory/('client-'+name+'.pem')
            with target.open('xb') as stream:
                host.private_file(target);stream.write(data)
            settings[name.replace('_','-')]=str(target)
    elif request.get('sql_tls_policy') is not None:
        raise Refused('Delegate the reviewed native TLS files and verification policy explicitly')
    if any(not isinstance(value,str) or len(value)>4096 for value in settings.values()):
        raise Refused('Native TLS option exceeds its bound')
    path = directory / 'client.cnf'
    with path.open('x', encoding='utf8') as stream:
        host.private_file(path)
        stream.write('[client]\nuser=' + quote(credentials['user']) + '\npassword=' + quote(credentials['password']) +
            '\nhost=' + quote(request['sql_host']) + '\nport=' + str(request['sql_port']) + '\nprotocol=tcp\n' +
            ''.join(key+'='+quote(value)+'\n' for key,value in settings.items()))
        if transition_key is not None:
            if not re.fullmatch('[0-9a-f]{64}',transition_key):raise Refused('Native transition key is invalid')
            stream.write('[xtrabackup]\ntransition-key='+quote(transition_key)+'\n')
    return path


def clean_client_options(directory):
    for name in ('client.cnf','client-ssl_ca.pem','client-ssl_cert.pem','client-ssl_key.pem'):
        (directory/name).unlink(missing_ok=True)


def identity(request, observed, option_file, directory):
    # CURRENT_ROLE has a binary string type. Native JSON otherwise represents
    # it as an opaque base64 value, rather than the session's actual role text.
    source = "SELECT JSON_OBJECT('version',VERSION(),'server_uuid',@@server_uuid,'datadir',@@datadir,'authenticated_principal',CURRENT_USER(),'active_role',CAST(CURRENT_ROLE() AS CHAR CHARACTER SET utf8mb4))"
    response = subprocess.run([observed['mysql']['path'], '--defaults-file=' + str(option_file), '--batch', '--raw',
        '--skip-column-names', '--default-character-set=utf8mb4', '--execute=' + source],
        capture_output=True, timeout=15, cwd=directory, env=native_environment(directory), check=False)
    if response.returncode:
        raise Refused('Native source authentication or identity inspection failed')
    value = json.loads(response.stdout.decode('utf8'))
    expected = request['source_identity']
    differences = [key for key in ('version', 'server_uuid', 'authenticated_principal', 'active_role') if value.get(key) != expected.get(key)]
    if absolute(value['datadir']) != absolute(request['binding']['datadir']): differences.append('datadir')
    if differences:
        error = Refused('The native backup SQL peer differs from the reviewed source identity: ' + ', '.join(differences))
        error.observed_identity = value
        raise error
    return value


def finish(directory, value):
    host.save(directory / 'result.json', value)


def execute(directory):
    """Detached supervisor. It survives loss of the web worker or SSH reply."""
    directory = Path(directory)
    request = read_json(directory / 'request.json')
    if request['phase'] == 'recover': return recovery_module().execute(directory)
    value = {'state': 'native_dispatch', 'job_id': request['job_id'], 'input_digest': request['input_digest'],
        'automatic_retry': False, 'native_may_have_dispatched': False, 'process_termination_confirmed': False,
        'credential_cleanup_confirmed': False, 'supervisor_finished': False, 'started_at': time.time()}
    child = option_file = staged_increment = native_config = staged_copy_back = None
    try:
        observed = inspection(request)
        if observed != request['reviewed']:
            raise Refused('Native physical source, utility or artifact changed after review')
        phase = request['phase']; target = directory / 'artifact'
        if phase in {'backup','incremental'}:
            if observed.get('keyring'):
                prior=Path(observed['workspace'])/request['input_job_id']/'artifact' if phase=='incremental' else None
                transition=keyring_module().backup_key(directory,prior)
                option_file=client_options(request,directory,transition_key=transition)
            else:option_file = client_options(request, directory)
            value['sql_identity'] = identity(request, observed, option_file, directory)
            args = ['--defaults-file=' + str(option_file), '--backup', '--datadir=' + observed['host']['datadir'],
                '--target-dir=' + str(target), '--parallel=' + str(request['parallel'])]
            args+=geometry_module().backup_arguments(observed.get('external_paths',{}).get('storage'))
            if phase=='incremental':args.append('--incremental-basedir='+str(Path(observed['workspace'])/request['input_job_id']/'artifact'))
        else:
            original = Path(observed['workspace']) / request['input_job_id'] / 'artifact'
            if phase in {'prepare','prepare_redo'}:
                # Prepare mutates a private derived copy; the original base and
                # its dependency boundary remain immutable and independently usable.
                shutil.copytree(original, target)
                if public(artifact(target, prepared=False)) != observed['input']['artifact']:
                    raise Refused('Staged physical bytes differ from the selected immutable base')
                args = ['--no-defaults', '--prepare', '--target-dir=' + str(target), '--use-memory=' + str(request['memory_bytes'])]
                if phase=='prepare_redo':args.append('--apply-log-only')
                if observed.get('incremental_input'):
                    staged_increment=directory/'delta-input'
                    shutil.copytree(Path(observed['workspace'])/request['incremental_job_id']/'artifact',staged_increment)
                    if public(artifact(staged_increment))!=observed['incremental_input']['artifact']:raise Refused('Staged incremental differs from its immutable input')
                    args.append('--incremental-dir='+str(staged_increment))
                storage=geometry_module().stage_prepare(directory,target,staged_increment)
                args+=geometry_module().prepare_arguments(target,storage)
                if observed.get('keyring'):
                    material=keyring_module().apply_snapshot(target,staged_increment)
                    keys=(staged_increment if staged_increment is not None else target)/'xtrabackup_keys'
                    if material is not None and keys.is_file():
                        option_file=keyring_module().native_options(directory,keyring_module().read_key(target/keyring_module().DIRECTORY))
                        native_config=keyring_module().prepare_options(target,option_file)
                        args[0]='--defaults-file='+str(option_file)
                    keyring_module().stage_prepare_material(directory,target)
            else:
                target.mkdir(mode=0o700)
                copy_input=original
                if observed.get('external_paths'):
                    staged_copy_back,_plan=paths_module().stage_copy_back(directory,original,target,observed['input']['artifact'],observed['external_paths'])
                    copy_input=staged_copy_back
                args = ['--no-defaults', '--copy-back', '--target-dir=' + str(copy_input), '--datadir=' + str(target),
                    '--innodb-data-home-dir=' + str(target), '--innodb-undo-directory=' + str(target),
                    '--innodb-log-group-home-dir=' + str(target)]
                args+=geometry_module().copy_back_arguments(directory,target,observed['input']['artifact'].get('storage_geometry'),observed.get('external_paths'))
        if observed.get('keyring'):args.append('--xtrabackup-plugin-dir='+observed['keyring']['xtrabackup_plugin_dir'])
        if (directory / 'cancel').exists():
            raise InterruptedError('Cancelled before native dispatch')
        value.update(native_may_have_dispatched=True, phase=phase)
        finish(directory, value)
        with (directory / 'stdout').open('xb') as stdout, (directory / 'stderr').open('xb') as stderr:
            host.private_file(directory / 'stdout'); host.private_file(directory / 'stderr')
            child = subprocess.Popen([observed['xtrabackup']['path'], *args], stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, cwd=directory, env=native_environment(directory), start_new_session=True)
            value['native_pid'] = child.pid
            finish(directory, value)
            deadline = time.monotonic() + request['timeout_seconds']
            while child.poll() is None:
                if (directory / 'cancel').exists() or time.monotonic() > deadline:
                    value['cancel_requested'] = (directory / 'cancel').exists()
                    value['timeout_reached'] = time.monotonic() > deadline
                    os.killpg(child.pid, signal.SIGTERM)
                    try: child.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=15)
                    break
                time.sleep(.1)
        value.update(state='native_returned', return_code=child.returncode,
            process_termination_confirmed=True, native_reply_observed=True, finished_at=time.time())
        # Native completion is a fact before hashing/metadata/cleanup can fail.
        finish(directory, value)
        if native_config is not None:
            keyring_module().restore_prepare_options(target,native_config);native_config=None
        if phase in {'prepare','prepare_redo'}:
            keyring_module().restore_prepare_material(directory,target)
            geometry_module().restore_prepare(directory,target)
        if child.returncode == 0:
            if phase in {'backup','incremental'}:geometry_module().capture(request,target,reviewed=observed.get('external_paths',{}).get('storage'))
            if phase in {'backup','incremental'} and observed.get('keyring'):
                keyring_module().capture(directory,target,observed['keyring'])
            if phase == 'copy_back':
                geometry_module().finish_copy_back(directory,original,target,observed['input']['artifact'].get('storage_geometry'),observed.get('external_paths'))
                keyring_module().copied_snapshot(original,target)
                copied = manifest(target)
                value['restored_files'] = {'files': copied, 'manifest_sha256': host.digest(copied),
                    'total_bytes': str(sum(int(item['bytes']) for item in copied)), 'database_started': False,
                    'data_directory': str(target), 'database_recovery_verified': False}
            else:
                value['artifact'] = artifact(target, prepared=phase == 'prepare')
                if value['artifact'].get('external_tablespaces') and request.get('isolate_external_paths') is not True:
                    raise Refused('Native external files were not admitted for this backup; verified publication withheld')
                if phase=='prepare_redo' and not value['artifact'].get('redo_only'):raise Refused('Native preparation did not retain its redo-only state')
            if phase!='backup':
                if input_artifact(request,Path(observed['workspace']),request['input_job_id'])!=observed['input']:
                    raise Refused('Original physical input changed during the native operation')
                if observed.get('incremental_input') and input_artifact(request,Path(observed['workspace']),request['incremental_job_id'])!=observed['incremental_input']:
                    raise Refused('Original incremental input changed during the native operation')
            lineage=({'base_job_id':request['job_id'],'incremental_job_ids':[]} if phase=='backup' else observed.get('incremental_input',observed['input'])['lineage'])
            if phase=='incremental':lineage={**lineage,'incremental_job_ids':[*lineage['incremental_job_ids'],request['job_id']]}
            value['lineage']=lineage
    except BaseException as error:
        if child is not None and child.poll() is None:
            try: os.killpg(child.pid, signal.SIGKILL); child.wait(timeout=15)
            except (ProcessLookupError, subprocess.TimeoutExpired): pass
        value.update(state=value['state'] if value.get('native_reply_observed') else 'unknown' if value['native_may_have_dispatched'] else 'not_dispatched',
            error_type=type(error).__name__, error_message=str(error) if isinstance(error, (Refused, InterruptedError)) else None,
            process_termination_confirmed=child is None or child.poll() is not None)
        if getattr(error, 'observed_identity', None) is not None:
            value['observed_sql_identity'] = error.observed_identity
    finally:
        # Invocation secrets are never part of a public receipt or retained
        # executable. A later observer can distinguish an incomplete cleanup.
        if request['phase'] in {'prepare','prepare_redo'} and (child is None or child.poll() is not None):
            try:geometry_module().restore_prepare(directory,directory/'artifact')
            except Exception as error:value['storage_restore_error_type']=type(error).__name__
        try:
            if native_config is not None:keyring_module().restore_prepare_options(target,native_config)
            if request['phase'] in {'prepare','prepare_redo'}:keyring_module().restore_prepare_material(directory,directory/'artifact')
            clean_client_options(directory)
            keyring_module().cleanup(directory,material_retained=value.get('native_may_have_dispatched') is True)
            if staged_increment is not None and staged_increment.exists() and (child is None or child.poll() is not None):shutil.rmtree(staged_increment)
            if staged_copy_back is not None and staged_copy_back.exists() and (child is None or child.poll() is not None):shutil.rmtree(staged_copy_back)
            if request.get('keyring'):
                value['native_key_material_retained']=(directory/keyring_module().TRANSITION).exists() or (directory/'artifact'/keyring_module().DIRECTORY).is_dir()
            request['database_credentials'] = None
            host.save(directory / 'request.json', request)
            value['credential_cleanup_confirmed'] = True
        except Exception as error:
            value['credential_cleanup_error_type'] = type(error).__name__
        value.update(supervisor_finished=True, supervisor_finished_at=time.time())
        finish(directory, value)


def dispatch(request, launch_source=None):
    if isinstance(request,dict) and (request.get('action')=='start' or str(request.get('action','')).startswith('retention_')):
        try:
            import _cdeadmin_physical_retention_worker as retention
        except ModuleNotFoundError:
            from . import mysql_physical_retention_worker as retention
        if request.get('schema')!='cdeadmin.mysql-physical.v1':raise Refused('Select the native physical host protocol')
        root=root_directory(request['workspace'],host_scope(request))
        with retention.admission(root):
            if request['action'].startswith('retention_'):
                return retention.dispatch(request,root,root/job_id(request['job_id']))
            return _dispatch(request,launch_source)
    return _dispatch(request,launch_source)


def _dispatch(request, launch_source=None):
    if not isinstance(request, dict) or request.get('schema') != 'cdeadmin.mysql-physical.v1':
        raise Refused('Select the native physical host protocol')
    action = request.get('action')
    if action == 'inspect':
        return inspection(request)
    binding = host_scope(request)
    root = root_directory(request['workspace'], binding)
    selected = job_id(request['job_id']); directory = root / selected
    if action in {'status', 'cancel', 'output'}:
        if not directory.is_dir() or directory.is_symlink():
            return {'state': 'unknown', 'remote_receipt_available': False, 'automatic_retry': False}
        record = read_json(directory / 'result.json')
        if record.get('input_digest') != request['input_digest']:
            raise Refused('Physical receipt belongs to another reviewed input')
        if request['phase'] == 'recover' and action in {'status', 'cancel'}:
            return public(recovery_module().observe(directory, record, action))
        if action == 'cancel' and not record.get('process_termination_confirmed'):
            with (directory / 'cancel').open('ab') as stream: host.private_file(directory / 'cancel')
        if action == 'output':
            record = {'job_id': selected, 'input_digest': request['input_digest'], 'outputs': {}}
            for name in ('stdout', 'stderr', *(['native-error.log'] if request['phase'] == 'recover' else [])):
                path = directory / name
                if path.exists():
                    with host.regular_stream(path) as stream:
                        stream.seek(max(0, path.stat().st_size - MAX_OUTPUT))
                        record['outputs'][name] = stream.read(MAX_OUTPUT).decode('utf8', errors='replace')
        return public(record)
    if action != 'start' or launch_source is None:
        raise Refused('Native physical action is unavailable')
    if directory.exists():
        return dispatch({**request, 'action': 'status'})
    observed = inspection(request)
    if observed != request.get('reviewed'):
        raise Refused('Native physical inputs changed after review')
    root.mkdir(parents=True, exist_ok=True, mode=0o700); host.private_directory(root)
    directory.mkdir(mode=0o700); host.private_directory(directory)
    # This exclusive durable claim prevents retries, including a killed SSH
    # worker between claim and child launch. Missing admission stays unknown.
    finish(directory, {'state': 'claimed', 'job_id': selected, 'input_digest': request['input_digest'],
        'automatic_retry': False, 'process_termination_confirmed': False, 'credential_cleanup_confirmed': False})
    host.save(directory / 'request.json', request)
    path = directory / 'supervisor.py'
    with path.open('x', encoding='utf8') as stream:
        host.private_file(path); stream.write(launch_source)
        stream.flush(); os.fsync(stream.fileno())
    try:
        subprocess.Popen([sys.executable, '-u', str(path), str(directory)], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True,
            cwd=directory, env=native_environment(directory))
    except BaseException:
        request['database_credentials'] = None
        host.save(directory / 'request.json', request)
        finish(directory, {'state': 'not_dispatched', 'job_id': selected, 'input_digest': request['input_digest'],
            'automatic_retry': False, 'process_termination_confirmed': True, 'credential_cleanup_confirmed': True,
            'native_may_have_dispatched': False, 'supervisor_finished': True, 'error_type': 'supervisor_launch_failed'})
        raise
    return {'state': 'admitted', 'job_id': selected, 'input_digest': request['input_digest'],
        'automatic_retry': False, 'process_termination_confirmed': False}
