"""Allowlisted application-host PostgreSQL utilities, separate from SQL sessions."""
from pathlib import Path
import hashlib
import json
import os
import re
import socket
import stat
import sys

from ...sdk.tooling import ProviderToolGrant, ProviderToolRunner
from .continuity import ContinuityError
from .host_utilities import (
    EXTENDED_OPERATIONS,
    execute_extended,
    observe_extended,
    validate_extended_options,
)

OPERATIONS = {
    'host_pg_controldata': 'pg_controldata',
    'host_pg_walsummary': 'pg_walsummary',
    'host_pg_test_timing': 'pg_test_timing',
    'host_pg_test_fsync': 'pg_test_fsync',
    'host_pg_checksums': 'pg_checksums',
    **EXTENDED_OPERATIONS,
}
MAX_MANIFEST = 1024 * 1024


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def exact_path(value, directory=False):
    if not isinstance(value, str) or not value or '\0' in value:
        raise ContinuityError('Select an operator-granted native path')
    path = Path(value)
    if not path.is_absolute() or path.resolve(strict=True) != path or path.parent == path:
        raise ContinuityError('Native host paths must be exact absolute paths without symbolic links')
    info = path.stat()
    if not (stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode)):
        raise ContinuityError('Native host input has the wrong file type')
    return path


def identity(path, content=False):
    info = path.stat()
    result = {'device': str(info.st_dev), 'inode': str(info.st_ino), 'size': str(info.st_size),
              'mtime_ns': str(info.st_mtime_ns), 'ctime_ns': str(info.st_ctime_ns)}
    if content:
        h = hashlib.sha256()
        with path.open('rb') as source:
            while block := source.read(1024 * 1024):
                if source.tell() > info.st_size:
                    raise ContinuityError('Native input grew during bounded capture')
                h.update(block)
        if identity(path) != result:
            raise ContinuityError('Native input changed during capture')
        result['sha256'] = h.hexdigest()
    return result


def grants(filename, endpoint):
    if not filename:
        raise ContinuityError('Application-host utility grants are not configured')
    path = exact_path(filename)
    if path.stat().st_size > MAX_MANIFEST:
        raise ContinuityError('Native host grant manifest exceeds its size budget')
    with path.open('rb') as manifest:
        raw = manifest.read(MAX_MANIFEST + 1)
    if len(raw) > MAX_MANIFEST:
        raise ContinuityError('Native host manifest changed beyond its budget')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ContinuityError('Native host grant manifest is invalid') from None
    if not isinstance(value, dict) or set(value) != {'format', 'grants'} or value['format'] != 'scratchrobin.postgresql.host-tools@1' or not isinstance(value['grants'], list):
        raise ContinuityError('Select the versioned native host grant manifest')
    matches = [row for row in value['grants'] if isinstance(row, dict) and row.get('endpoint_id') == endpoint]
    allowed_grant_keys = {
        'endpoint_id', 'clusters', 'summary_files', 'benchmark_roots',
        'init_roots', 'archive_dirs', 'upgrade_pairs',
    }
    if len(matches) != 1 or set(matches[0]) - allowed_grant_keys:
        raise ContinuityError('Exactly one endpoint host grant is required')
    selected = matches[0]
    for kind in ('clusters', 'summary_files', 'benchmark_roots', 'init_roots', 'archive_dirs', 'upgrade_pairs'):
        entries = selected.get(kind, [])
        if not isinstance(entries, list) or len(entries) > 1000:
            raise ContinuityError('Native host grants exceed their inventory budget')
        ids = []
        for row in entries:
            if kind == 'upgrade_pairs':
                req_pair = {'id', 'old_bindir', 'new_bindir', 'old_datadir', 'new_datadir'}
                if not isinstance(row, dict) or set(row) != req_pair or not isinstance(row['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', row['id']) or any(not isinstance(row[k], str) or not row[k] for k in req_pair - {'id'}):
                    raise ContinuityError('Native upgrade pair grants require exact id and four binary/data paths')
                ids.append(row['id'])
                continue
            if not isinstance(row, dict) or not {'id', 'path'} <= set(row) or set(row) - ({'id', 'path', 'tablespaces'} if kind == 'clusters' else {'id', 'path'}) or not isinstance(row['id'], str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', row['id']):
                raise ContinuityError('Native host grants require bounded exact identities and paths')
            if kind == 'clusters':
                spaces = row.get('tablespaces', [])
                if not isinstance(spaces, list) or len(spaces) > 1000:
                    raise ContinuityError('Native tablespace grants exceed their inventory budget')
                space_ids = []
                for space in spaces:
                    if not isinstance(space, dict) or set(space) != {'oid', 'path'} or not isinstance(space['oid'], str) or not re.fullmatch('[1-9][0-9]{0,9}', space['oid']) or int(space['oid']) > 4294967295:
                        raise ContinuityError('Native tablespace grants require exact OID/path selections')
                    space_ids.append(space['oid'])
                if len(set(space_ids)) != len(space_ids):
                    raise ContinuityError('Native tablespace grants must be distinct')
            ids.append(row['id'])
        if len(set(ids)) != len(ids):
            raise ContinuityError('Native host grant identities must be distinct')
    return selected, hashlib.sha256(raw).hexdigest()


def options(operation, draft):
    if not isinstance(operation, str) or operation not in OPERATIONS or not isinstance(draft, dict):
        raise ContinuityError('Select a typed native host utility')
    if operation in EXTENDED_OPERATIONS:
        return validate_extended_options(operation, draft)
    allowed = ({'cluster_id', 'mode', 'filenode', 'progress', 'verbose', 'sync', 'sync_method', 'offline_quiescence_confirmed', 'checksum_change_confirmed', 'unsafe_no_sync_confirmed', 'confirmation', 'timeout_seconds'} if operation == 'host_pg_checksums' else
               {'scratch_id', 'seconds_per_test', 'confirmation', 'timeout_seconds'} if operation == 'host_pg_test_fsync' else
               {'duration_seconds', 'confirmation', 'timeout_seconds'} if operation == 'host_pg_test_timing' else
               {'summary_ids', 'individual', 'quiet', 'confirmation', 'timeout_seconds'}
               if operation == 'host_pg_walsummary' else {'cluster_id', 'confirmation', 'timeout_seconds'})
    if set(draft) - allowed:
        raise ContinuityError('Native utility draft contains unrelated fields')
    from copy import deepcopy
    result = deepcopy(draft)
    timeout = result.setdefault('timeout_seconds', 60)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise ContinuityError('Select a bounded native utility timeout of 1 through 3600 seconds')
    if operation == 'host_pg_test_fsync':
        seconds = result.setdefault('seconds_per_test', 1)
        if type(seconds) is not int or not 1 <= seconds <= 60 or not isinstance(result.get('scratch_id'), str):
            raise ContinuityError('Select an operator-granted scratch root and 1 through 60 seconds per native test')
        if result.get('confirmation') != socket.gethostname():
            raise ContinuityError('Confirm the application-host hostname')
        return result
    if operation == 'host_pg_test_timing':
        duration = result.setdefault('duration_seconds', 3)
        if type(duration) is not int or not 1 <= duration <= 60:
            raise ContinuityError('Native timer duration must be 1 through 60 seconds')
        if result.get('confirmation') != socket.gethostname():
            raise ContinuityError('Confirm the application-host hostname')
        return result
    if operation == 'host_pg_walsummary':
        ids = result.get('summary_ids')
        if not isinstance(ids, list) or not 1 <= len(ids) <= 100 or any(not isinstance(value, str) for value in ids) or len(set(ids)) != len(ids):
            raise ContinuityError('Select 1 through 100 distinct operator-granted WAL summary identities')
        for key in ('individual', 'quiet'):
            if type(result.setdefault(key, False)) is not bool:
                raise ContinuityError('Native summary switches must be Boolean')
        if result.get('confirmation') != 'WAL summaries':
            raise ContinuityError('Confirm WAL summaries before native file inspection')
        return result
    if operation == 'host_pg_checksums':
        mode = result.setdefault('mode', 'CHECK')
        if not isinstance(mode, str) or mode not in {'CHECK', 'ENABLE', 'DISABLE'}:
            raise ContinuityError('Select native checksum CHECK, ENABLE or DISABLE')
        for key, default in [('progress', True), ('verbose', False), ('sync', True), ('offline_quiescence_confirmed', False), ('checksum_change_confirmed', False), ('unsafe_no_sync_confirmed', False)]:
            if type(result.setdefault(key, default)) is not bool:
                raise ContinuityError('Native checksum switches require Boolean choices')
        if not result['offline_quiescence_confirmed']:
            raise ContinuityError('Confirm externally controlled offline cluster quiescence')
        if mode != 'CHECK' and not result['checksum_change_confirmed']:
            raise ContinuityError('Confirm native checksum metadata/page changes')
        if mode != 'CHECK' and not result['sync'] and not result['unsafe_no_sync_confirmed']:
            raise ContinuityError('Confirm native no-sync durability consequences')
        result.setdefault('sync_method', 'fsync')
        if not isinstance(result['sync_method'], str) or result['sync_method'] not in {'fsync', 'syncfs'}:
            raise ContinuityError('Select a native checksum sync method')
        if result['sync_method'] == 'syncfs' and sys.platform != 'linux':
            raise ContinuityError('syncfs is not admitted on this native host platform')
        filenode = result.setdefault('filenode', '')
        if not isinstance(filenode, str) or filenode and (mode != 'CHECK' or not re.fullmatch(r'0|[1-9][0-9]{0,9}', filenode) or int(filenode) > 2147483647):
            raise ContinuityError('Filenode selection requires native CHECK and exact decimal 0 through 2147483647')
    selected = result.get('cluster_id')
    if not isinstance(selected, str) or result.get('confirmation') != selected:
        raise ContinuityError('Confirm the exact operator-granted cluster identity')
    return result


class HostTools:
    def __init__(self, paths):
        self.paths = dict(paths)
        self.runner = ProviderToolRunner(self.paths)

    def invoke(self, name, workspace, arguments, timeout=60, cancel=None, progress=None, durable=False):
        grant = ProviderToolGrant(name, str(workspace), '127.0.0.1', 5432,
                                  timeout_seconds=timeout, max_output_bytes=1024 * 1024,
                                  durable_name='postgresql-host-tool' if durable else None,
                                  guard_parent_death=durable)
        return self.runner.run(grant, arguments, cancel_signal=cancel, progress=progress)

    def identify(self, name, workspace):
        if name not in set(OPERATIONS.values()) or not self.runner.available().get(name):
            raise ContinuityError('Selected native utility is not installed')
        observed = self.invoke(name, workspace, ['--version'], 15)
        text = observed['stdout'] + observed['stderr']
        match = re.search(r'\(PostgreSQL\)\s+(18\.\d+)\b', text)
        if observed['return_code'] or not match:
            raise ContinuityError('Native PostgreSQL 18 utilities are required for this host adapter')
        return {'name': name, 'version': match[1], 'version_text': text.strip(), 'executable_sha256': observed['executable_sha256'],
                'execution_host': {'kind': 'application-host', 'hostname': socket.gethostname(),
                                   'platform': sys.platform, 'process_uid': str(os.getuid()) if hasattr(os, 'getuid') else None}}

    def observe(self, operation, selected, grant, workspace):
        if operation in EXTENDED_OPERATIONS:
            return observe_extended(self, operation, selected, grant, workspace, exact_path, identity, parse_control)
        if operation == 'host_pg_test_fsync':
            entry = next((row for row in grant.get('benchmark_roots', []) if row['id'] == selected['scratch_id']), None)
            if entry is None:
                raise ContinuityError('Native fsync scratch root is not granted to this endpoint')
            root = exact_path(entry['path'], True)
            return {'hostname': socket.gethostname(), 'scratch_id': entry['id'], 'scratch_root': str(root),
                    'scratch_root_identity': identity(root), 'database_server_storage_performance_attested': False}
        if operation == 'host_pg_test_timing':
            return {'hostname': socket.gethostname(), 'platform': sys.platform, 'database_server_timing_attested': False}
        if operation == 'host_pg_walsummary':
            entries = {row['id']: row for row in grant.get('summary_files', [])}
            files = []; total = 0
            for key in selected['summary_ids']:
                if key not in entries:
                    raise ContinuityError('WAL summary is not granted to this endpoint')
                path = exact_path(entries[key]['path']); size = path.stat().st_size; total += size
                if size > 64 * 1024 * 1024 or total > 256 * 1024 * 1024:
                    raise ContinuityError('Native summary input exceeds its bounded snapshot budget')
                files.append({'id': key, 'path': str(path), 'identity': identity(path, True)})
            return {'summary_files': files, 'cluster_association_attested': False, 'native_format_validation_pending': True}
        cluster = next((row for row in grant.get('clusters', []) if row['id'] == selected['cluster_id']), None)
        if cluster is None:
            raise ContinuityError('Selected cluster is not granted to this endpoint')
        path = exact_path(cluster['path'], True)
        version_path = exact_path(str(path / 'PG_VERSION'))
        if version_path.stat().st_size > 32:
            raise ContinuityError('Native cluster version marker exceeds its budget')
        version = version_path.read_text().strip()
        if version != '18':
            raise ContinuityError('Granted cluster and native utility major versions differ')
        control = exact_path(str(path / 'global/pg_control'))
        if control.stat().st_size > 65536:
            raise ContinuityError('Native control file exceeds its observation budget')
        source = {'cluster_id': selected['cluster_id'], 'cluster_path': str(path), 'directory_identity': identity(path),
                'pg_version': version, 'control_identity': identity(control, True),
                'atomic_external_start_or_writer_fence': False}
        if operation == 'host_pg_checksums':
            if (path / 'postmaster.pid').exists() or (path / 'postmaster.pid').is_symlink():
                raise ContinuityError('Native checksum work requires an absent postmaster.pid and an externally stopped cluster')
            inspector = self.identify('pg_controldata', workspace)
            observed = self.invoke('pg_controldata', workspace, [str(path)], 15)
            fields = parse_control(observed['stdout'])
            if observed['return_code'] or observed['stdout_truncated'] or fields.get('Database cluster state') not in {'shut down', 'shut down in recovery'}:
                raise ContinuityError('Native checksum work requires a cleanly shut down cluster')
            source.update(control_fields_before=fields, control_inspector=inspector,
                          checksum_tree=checksum_tree(path, cluster.get('tablespaces', []), fields),
                          offline_quiescence_external_acknowledgement=True)
        return source

    def execute(self, operation, selected, source, workspace, cancel, progress, before_dispatch=None):
        if operation in EXTENDED_OPERATIONS:
            return execute_extended(self, operation, selected, source, workspace, cancel, progress, before_dispatch, parse_control)
        if operation == 'host_pg_checksums':
            arguments = ['--pgdata=' + source['cluster_path'], '--' + selected['mode'].lower()]
            if selected['filenode']:
                arguments.append('--filenode=' + selected['filenode'])
            if selected['progress']:
                arguments.append('--progress')
            if selected['verbose']:
                arguments.append('--verbose')
            arguments.append('--sync-method=' + selected['sync_method'])
            if not selected['sync']:
                arguments.append('--no-sync')
        elif operation == 'host_pg_test_fsync':
            import tempfile
            temporary = Path(tempfile.mkdtemp(prefix='scratchrobin-fsync-', dir=source['scratch_root']))
            register_temporary(temporary, workspace, before_dispatch)
            filename = temporary / 'native-fsync-test'
            arguments = ['--filename=' + str(filename), '--secs-per-test=' + str(selected['seconds_per_test'])]
        elif operation == 'host_pg_test_timing':
            arguments = ['--duration=' + str(selected['duration_seconds'])]
        elif operation == 'host_pg_walsummary':
            files = stage_summaries(source, workspace, cancel, before_dispatch)
            arguments = (['--individual'] if selected['individual'] else []) + (['--quiet'] if selected['quiet'] else []) + files
        else:
            arguments = [source['cluster_path']]
        if before_dispatch is not None:
            before_dispatch()
        result = self.invoke(OPERATIONS[operation], workspace, arguments,
                             selected['timeout_seconds'], cancel, progress, True)
        after = None
        if operation == 'host_pg_checksums':
            readback = self.invoke('pg_controldata', workspace, [source['cluster_path']], 15)
            after = {'native': readback, 'fields': parse_control(readback['stdout']),
                     'observed': readback['return_code'] == 0 and not readback['stdout_truncated']}
        verification = True
        if operation == 'host_pg_checksums':
            expected = '0' if selected['mode'] == 'DISABLE' else '1'
            verification = bool(after['observed'] and after['fields'].get('Database system identifier') == source['control_fields_before'].get('Database system identifier') and after['fields'].get('Data page checksum version') == expected)
        return {'verification_complete': verification, 'native': result, 'control_fields': parse_control(result['stdout']) if operation == 'host_pg_controldata' else None,
                'summary_input_count': len(source.get('summary_files', [])),
                'summary_quiet_requested': selected.get('quiet', False),
                'native_stdout_empty': not bool(result['stdout']),
                'sql_session_borrowed': False, 'commit_requested': False, 'rollback_requested': False,
                'native_success': result['return_code'] == 0,
                'report_complete': not result['stdout_truncated'] and not result['stderr_truncated'],
                'fsync_seconds_per_test': selected.get('seconds_per_test'),
                'cluster_mutation_requested': operation == 'host_pg_checksums' and selected['mode'] != 'CHECK',
                'checksum_control_readback': after, 'native_effect_rollback_available': False,
                'filenode_existence_attested': False,
                'operator_inspection_required_before_reuse': operation == 'host_pg_checksums' and (result['return_code'] != 0 or not verification),
                'atomic_live_snapshot_claimed': False}


def parse_control(text):
    return {left.strip(): right.strip() for line in text.splitlines() if ':' in line
            for left, right in [line.split(':', 1)]}


def stage_summaries(source, workspace, cancel, before_dispatch=None):
    root = Path(workspace) / 'native-summary-inputs'
    root.mkdir(mode=0o700)
    register_temporary(root, workspace, before_dispatch)
    paths = []
    for index, entry in enumerate(source['summary_files']):
        if cancel.is_set():
            raise InterruptedError('Summary snapshot cancelled before native inspection')
        path = exact_path(entry['path'])
        if identity(path, True) != entry['identity']:
            raise ContinuityError('Reviewed native summary changed before staging')
        target = root / (str(index) + '.summary')
        descriptor = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        h = hashlib.sha256(); size = 0
        with os.fdopen(descriptor, 'rb') as original, target.open('xb') as destination:
            os.chmod(target, 0o600)
            while block := original.read(1024 * 1024):
                if cancel.is_set():
                    raise InterruptedError('Summary snapshot cancelled')
                size += len(block)
                if size > int(entry['identity']['size']):
                    raise ContinuityError('Native summary grew during staging')
                h.update(block); destination.write(block)
            destination.flush(); os.fsync(destination.fileno())
        if size != int(entry['identity']['size']) or h.hexdigest() != entry['identity']['sha256'] or identity(path, True) != entry['identity']:
            raise ContinuityError('Native summary snapshot differs from the review')
        paths.append(str(target))
    return paths


def register_temporary(path, workspace, callback):
    from ...operations.fileio import publish_private_file, private_directory
    private_directory(path)
    marker = Path(workspace).name.encode('ascii')
    publish_private_file(path / '.scratchrobin-host-tool', marker)
    facts = identity(path)
    if callback is not None:
        callback({'path': str(path), 'device': facts['device'], 'inode': facts['inode'],
                  'marker_sha256': hashlib.sha256(marker).hexdigest()})


def checksum_tree(cluster, spaces, control):
    """Snapshot exactly admitted native scan roots; never follow arbitrary links."""
    entries = []; total = 0
    def walk(root, label):
        nonlocal total
        root = exact_path(str(root), True)
        stack = [(root, label)]
        while stack:
            directory, relative = stack.pop()
            entries.append([relative, identity(directory)])
            for item in sorted(directory.iterdir()):
                info = item.lstat(); key = relative + '/' + item.name
                if stat.S_ISLNK(info.st_mode):
                    raise ContinuityError('Unexpected symbolic link in native checksum scan roots')
                if stat.S_ISDIR(info.st_mode):
                    stack.append((item, key))
                elif stat.S_ISREG(info.st_mode) and info.st_nlink == 1:
                    entries.append([key, identity(item)]);total += info.st_size
                else:
                    raise ContinuityError('Native checksum files must be regular, unshared files')
                if len(entries) + len(stack) > 100000:
                    raise ContinuityError('Native checksum observation exceeds the 100000-entry budget')
    walk(cluster / 'global', 'global');walk(cluster / 'base', 'base')
    root = exact_path(str(cluster / 'pg_tblspc'), True)
    granted = {row['oid']: row['path'] for row in spaces}
    links = []
    for link in sorted(root.iterdir()):
        if link.name not in granted or not link.is_symlink():
            raise ContinuityError('Every external native tablespace requires an explicit operator OID/path grant')
        target = exact_path(granted[link.name], True)
        if link.resolve(strict=True) != target:
            raise ContinuityError('Native tablespace differs from its operator-granted path')
        version = 'PG_18_' + control['Catalog version number']
        walk(target / version, 'tablespace/' + link.name)
        info = link.lstat()
        links.append({'oid': link.name, 'target': str(target), 'device': str(info.st_dev), 'inode': str(info.st_ino)})
    return {'fingerprint': digest(sorted(entries)), 'entry_count': len(entries),
            'observed_file_bytes': str(total), 'tablespaces': links,
            'content_bytes_fully_hashed': False, 'atomic_external_writer_fence': False}
