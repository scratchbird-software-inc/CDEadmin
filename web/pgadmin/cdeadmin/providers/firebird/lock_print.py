"""Host-qualified Firebird 5.0.4 fb_lock_print structured diagnostic adapter.

Inspects native shared-memory lock tables on an authorized application host
without publishing raw lock keys or ASLR pointers into default MON$ metrics.
"""
from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import socket
import stat
import subprocess
import sys

from ...sdk.relational import RelationalClientError
from .local_services import admit_service_route, file_identity

MAX_OUTPUT_BYTES = 2 * 1024 * 1024
MAX_MANIFEST_BYTES = 1024 * 1024
STRIPPED_ENV_KEYS = ('ISC_PASSWORD', 'ISC_USER', 'ISC_DATABASE', 'ISC_ROLE')
ALLOWED_OPTION_KEYS = frozenset({
    'owners', 'locks', 'requests', 'history', 'waiting_only', 'pending_only',
    'consistent_mutex', 'series', 'interactive_seconds', 'interactive_interval',
    'interactive_counters', 'include_raw_lock_keys',
    'sensitive_lock_data_confirmed', 'confirmation', 'timeout_seconds',
})


def descriptor():
    return {
        'schema': 'scratchrobin.firebird.lock-print-api@1',
        'utility': 'fb_lock_print',
        'engine_version': '5.0.4',
        'supported_platforms': ['linux'],
        'published_as_default_metric': False,
        'requires_permissions': ['administer', 'maintenance_admin'],
        'options': {
            'owners': {'type': 'boolean', 'default': True},
            'locks': {'type': 'boolean', 'default': True},
            'requests': {'type': 'boolean', 'default': False, 'requires': 'owners'},
            'history': {'type': 'boolean', 'default': False},
            'waiting_only': {'type': 'boolean', 'default': True, 'requires': 'owners'},
            'pending_only': {'type': 'boolean', 'default': False, 'requires_any': ['owners', 'locks']},
            'consistent_mutex': {'type': 'boolean', 'default': True},
            'series': {'type': 'integer', 'minimum': 0, 'maximum': 32767, 'nullable': True, 'requires': 'locks'},
            'interactive_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 30, 'nullable': True},
            'interactive_interval': {'type': 'integer', 'minimum': 1, 'maximum': 10, 'nullable': True},
            'interactive_counters': {'type': 'string', 'allowed_chars': 'aotw', 'default': 'aotw'},
            'include_raw_lock_keys': {'type': 'boolean', 'default': False},
            'sensitive_lock_data_confirmed': {'type': 'boolean', 'default': False},
            'confirmation': {'type': 'string', 'default': ''},
            'timeout_seconds': {'type': 'integer', 'minimum': 1, 'maximum': 60, 'default': 15},
        },
        'notes': (
            'Executes Firebird 5.0.4 fb_lock_print against an operator-authorized '
            'application-host database lock table. Raw lock keys and AST pointers '
            'are redacted unless explicitly confirmed for this one-shot review.'
        ),
    }


def _bool_field(draft, name, default):
    val = draft.get(name, default)
    if type(val) is not bool:
        raise ValueError(f'{name} must be a boolean')
    return val


def normalize_options(draft, database_name=''):
    if not isinstance(draft, Mapping):
        raise ValueError('Lock-print options must be an object')
    unknown = sorted(set(draft) - ALLOWED_OPTION_KEYS)
    if unknown:
        raise ValueError('Unknown lock-print options: ' + ', '.join(unknown))

    timeout = draft.get('timeout_seconds', 15)
    if type(timeout) is not int or not 1 <= timeout <= 60:
        raise ValueError('timeout_seconds must be an integer between 1 and 60')

    interactive_seconds = draft.get('interactive_seconds')
    interactive_interval = draft.get('interactive_interval')
    counters = draft.get('interactive_counters', 'aotw')
    if not isinstance(counters, str) or not counters or any(c not in 'aotw' for c in counters) or len(set(counters)) != len(counters):
        raise ValueError('interactive_counters must combine distinct characters from a, o, t, w')

    include_raw = _bool_field(draft, 'include_raw_lock_keys', False)
    sensitive_ok = _bool_field(draft, 'sensitive_lock_data_confirmed', False)
    confirmation = draft.get('confirmation', '')
    if not isinstance(confirmation, str) or any(ch in confirmation for ch in ('\0', '\r', '\n')):
        raise ValueError('confirmation must be single-line text')
    if include_raw:
        if not sensitive_ok or (database_name and confirmation != database_name):
            raise ValueError('Confirm sensitive lock-key exposure with the exact database filename')

    if interactive_seconds is not None:
        if type(interactive_seconds) is not int or not 1 <= interactive_seconds <= 30:
            raise ValueError('interactive_seconds must be an integer between 1 and 30')
        if interactive_interval is None:
            interactive_interval = 1
        if type(interactive_interval) is not int or not 1 <= interactive_interval <= 10 or interactive_interval > interactive_seconds:
            raise ValueError('interactive_interval must be an integer between 1 and min(10, interactive_seconds)')
        if timeout <= interactive_seconds:
            raise ValueError('timeout_seconds must exceed interactive_seconds')
        for forbidden in ('owners', 'locks', 'requests', 'history', 'waiting_only', 'pending_only', 'consistent_mutex', 'series'):
            if forbidden in draft and draft[forbidden] not in (False, None):
                raise ValueError(f'{forbidden} cannot be combined with interactive counter sampling')
        return {
            'mode': 'interactive',
            'owners': False,
            'locks': False,
            'requests': False,
            'history': False,
            'waiting_only': False,
            'pending_only': False,
            'consistent_mutex': False,
            'series': None,
            'interactive_seconds': interactive_seconds,
            'interactive_interval': interactive_interval,
            'interactive_counters': counters,
            'include_raw_lock_keys': include_raw,
            'sensitive_lock_data_confirmed': sensitive_ok,
            'confirmation': confirmation,
            'timeout_seconds': timeout,
        }

    if interactive_interval is not None:
        raise ValueError('interactive_interval requires interactive_seconds')

    owners = _bool_field(draft, 'owners', True)
    locks = _bool_field(draft, 'locks', True)
    requests = _bool_field(draft, 'requests', False)
    history = _bool_field(draft, 'history', False)
    waiting_only = _bool_field(draft, 'waiting_only', owners)
    pending_only = _bool_field(draft, 'pending_only', False)
    consistent_mutex = _bool_field(draft, 'consistent_mutex', True)
    series = draft.get('series')

    if requests and not owners:
        raise ValueError('requests (-r) requires owners (-o)')
    if waiting_only and not owners:
        raise ValueError('waiting_only (-w) requires owners (-o)')
    if pending_only and not (owners or locks):
        raise ValueError('pending_only (-n) requires owners (-o) or locks (-l)')
    if series is not None:
        if type(series) is not int or not 0 <= series <= 32767:
            raise ValueError('series (-s) must be an integer between 0 and 32767')
        if not locks:
            raise ValueError('series (-s) requires locks (-l)')

    return {
        'mode': 'snapshot',
        'owners': owners,
        'locks': locks,
        'requests': requests,
        'history': history,
        'waiting_only': waiting_only,
        'pending_only': pending_only,
        'consistent_mutex': consistent_mutex,
        'series': series,
        'interactive_seconds': None,
        'interactive_interval': None,
        'interactive_counters': counters,
        'include_raw_lock_keys': include_raw,
        'sensitive_lock_data_confirmed': sensitive_ok,
        'confirmation': confirmation,
        'timeout_seconds': timeout,
    }


def build_cli_arguments(database_path, options):
    args = ['-d', database_path]
    if options['mode'] == 'interactive':
        args.extend([
            '-i' + options['interactive_counters'],
            str(options['interactive_seconds']),
            str(options['interactive_interval']),
        ])
        return args
    if options['consistent_mutex']:
        args.append('-c')
    if options['owners']:
        args.append('-o')
    if options['locks']:
        args.append('-l')
    if options['requests']:
        args.append('-r')
    if options['history']:
        args.append('-h')
    if options['waiting_only']:
        args.append('-w')
    if options['pending_only']:
        args.append('-n')
    if options['series'] is not None:
        args.extend(['-s', str(options['series'])])
    return args


def _file_sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def _verify_binary(binary_candidate):
    if not isinstance(binary_candidate, str) or not binary_candidate.strip() or '\0' in binary_candidate:
        raise ValueError('Configure an absolute Firebird 5.0.4 fb_lock_print binary path')
    raw = Path(binary_candidate)
    if not raw.is_absolute():
        raise ValueError('fb_lock_print binary path must be absolute')
    resolved = raw.resolve(strict=True)
    info = resolved.stat()
    if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
        raise ValueError('fb_lock_print binary must be an executable regular file')
    runtime_root = resolved.parent.parent
    fbclient = runtime_root / 'lib/libfbclient.so.5.0.4'
    if not fbclient.is_file():
        raise ValueError('fb_lock_print runtime must provide Firebird 5.0.4 libfbclient.so.5.0.4')
    return resolved, runtime_root, _file_sha256(resolved)


def _load_network_grant(endpoint_id, database_path):
    manifest_path = os.environ.get('CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST') or ''
    if not manifest_path:
        raise ValueError(
            'fb_lock_print inspects shared-memory lock tables on the Firebird host; '
            'remote TCP registrations without CDEADMIN_FIREBIRD_HOST_TOOLS_MANIFEST are unavailable'
        )
    mpath = Path(manifest_path)
    if not mpath.is_absolute() or mpath.resolve(strict=True) != mpath:
        raise ValueError('Firebird host-tools manifest must be a canonical absolute file')
    raw = mpath.read_bytes()
    if len(raw) > MAX_MANIFEST_BYTES:
        raise ValueError('Firebird host-tools manifest exceeds its size budget')
    doc = json.loads(raw)
    if (not isinstance(doc, dict) or doc.get('format') != 'scratchrobin.firebird.host-tools@1'
            or not isinstance(doc.get('grants'), list)):
        raise ValueError('Invalid Firebird host-tools manifest format')
    matches = [g for g in doc['grants'] if isinstance(g, dict) and g.get('endpoint_id') == endpoint_id]
    if len(matches) != 1:
        raise ValueError('No matching application-host Firebird grant for this endpoint')
    grant = matches[0]
    from .host_runtime_grant import ALLOWED_GRANT_KEYS
    if set(grant) - ALLOWED_GRANT_KEYS:
        raise ValueError('Firebird host grant contains unexpected fields')
    allowed_dbs = grant.get('databases')
    if not isinstance(allowed_dbs, list) or database_path not in allowed_dbs:
        raise ValueError('Database is not granted in the Firebird application-host manifest')
    db_file = Path(database_path)
    if not db_file.is_absolute() or db_file.resolve(strict=True) != db_file or not db_file.is_file():
        raise ValueError('Granted local Firebird database file is unavailable')
    rt_root = Path(grant['firebird_runtime_root']).resolve(strict=True)
    lock_dir = Path(grant['firebird_lock_directory']).resolve(strict=True)
    if not rt_root.is_dir() or not lock_dir.is_dir():
        raise ValueError('Granted Firebird runtime or lock directory is unavailable')
    st = db_file.stat()
    return {
        'database': str(db_file),
        'database_identity': {'device': str(st.st_dev), 'inode': str(st.st_ino)},
        'firebird_runtime_root': str(rt_root),
        'firebird_lock_directory': str(lock_dir),
        'manifest_sha256': hashlib.sha256(raw).hexdigest(),
    }


def resolve_host_scope(endpoint_id, route):
    if sys.platform != 'linux':
        raise ValueError('fb_lock_print host diagnostics are currently qualified on Linux only')
    boot_id = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
    if not boot_id:
        raise ValueError('Application host boot identity is unavailable')

    explicit_bin = os.environ.get('CDEADMIN_FIREBIRD_LOCK_PRINT_BINARY') or ''
    if route.get('attachment_mode') == 'embedded':
        try:
            admitted = admit_service_route(route)
            ident = file_identity(admitted)
        except RelationalClientError as error:
            raise ValueError(str(error)) from error
        fb_env = os.environ.get('FIREBIRD') or ''
        lock_env = os.environ.get('FIREBIRD_LOCK') or ''
        bin_candidate = explicit_bin or (str(Path(fb_env) / 'bin/fb_lock_print') if fb_env else '')
        binary, binary_rt, bin_sha = _verify_binary(bin_candidate)
        fb_root = str(Path(fb_env).resolve(strict=True)) if fb_env and Path(fb_env).exists() else str(binary_rt)
        lock_dir = str(Path(lock_env).resolve(strict=True)) if lock_env and Path(lock_env).is_dir() else ''
        return {
            'attachment_mode': 'embedded',
            'platform': 'linux',
            'boot_id': boot_id,
            'hostname': socket.gethostname(),
            'engine_version': '5.0.4',
            'binary_path': str(binary),
            'binary_sha256': bin_sha,
            'library_directory': str(binary_rt / 'lib'),
            'firebird_runtime_root': fb_root,
            'firebird_lock_directory': lock_dir,
            'database': ident['path'],
            'database_identity': {'device': ident['device'], 'inode': ident['inode']},
            'grant_manifest_sha256': None,
        }

    granted = _load_network_grant(endpoint_id, route.get('database'))
    bin_candidate = explicit_bin or str(Path(granted['firebird_runtime_root']) / 'bin/fb_lock_print')
    binary, binary_rt, bin_sha = _verify_binary(bin_candidate)
    return {
        'attachment_mode': 'same_host_granted_network',
        'platform': 'linux',
        'boot_id': boot_id,
        'hostname': socket.gethostname(),
        'engine_version': '5.0.4',
        'binary_path': str(binary),
        'binary_sha256': bin_sha,
        'library_directory': str(binary_rt / 'lib'),
        'firebird_runtime_root': granted['firebird_runtime_root'],
        'firebird_lock_directory': granted['firebird_lock_directory'],
        'database': granted['database'],
        'database_identity': granted['database_identity'],
        'grant_manifest_sha256': granted['manifest_sha256'],
    }


_INT_RE = {
    'version': re.compile(r'Version:\s*(\d+)'),
    'creation_timestamp': re.compile(r'Creation timestamp:\s*([^\r\n]+)'),
    'active_owner': re.compile(r'Active owner:\s*(\d+)'),
    'length_bytes': re.compile(r'Length:\s*(\d+)'),
    'used_bytes': re.compile(r'Used:\s*(\d+)'),
    'enqueues': re.compile(r'Enqs:\s*(\d+)'),
    'converts': re.compile(r'Converts:\s*(\d+)'),
    'rejects': re.compile(r'Rejects:\s*(\d+)'),
    'blocks': re.compile(r'Blocks:\s*(\d+)'),
    'deadlock_scans': re.compile(r'Deadlock scans:\s*(\d+)'),
    'deadlocks': re.compile(r'Deadlocks:\s*(\d+)'),
    'scan_interval': re.compile(r'Scan interval:\s*(\d+)'),
    'acquires': re.compile(r'Acquires:\s*(\d+)'),
    'acquire_blocks': re.compile(r'Acquire blocks:\s*(\d+)'),
    'spin_count': re.compile(r'Spin count:\s*(\d+)'),
    'mutex_wait_percent': re.compile(r'Mutex wait:\s*([0-9.]+)%'),
    'hash_slots': re.compile(r'Hash slots:\s*(\d+)'),
    'owners_count': re.compile(r'Owners\s*\((\d+)\):'),
}


def _sanitize_raw_text(text, include_raw_keys):
    sanitized = re.sub(r'AST:\s*\S+,\s*argument:\s*\S+', 'AST: [redacted], argument: [redacted]', text)
    if not include_raw_keys:
        sanitized = re.sub(r'(Key:\s*)([^,\r\n]+)', r'\1[redacted]', sanitized)
    return sanitized


def parse_lock_print_output(stdout, stderr='', *, include_raw_keys=False):
    if 'Unable to access lock table' in stdout or 'sh_mem_length_mapped is 0' in stderr:
        return {
            'lock_table_state': 'unmapped_no_active_attachments',
            'header': None,
            'owners': [],
            'locks': [],
            'requests': [],
            'interactive_samples': [],
            'interactive_average': None,
        }

    # Interactive mode parser
    lines = [ln.rstrip('\r') for ln in stdout.splitlines()]
    if any('acquire/s' in ln and 'enqueue/s' in ln for ln in lines):
        columns = []
        samples = []
        average = None
        for ln in lines:
            stripped = ln.strip()
            if not stripped:
                continue
            if 'acquire/s' in stripped and 'enqueue/s' in stripped:
                parts = stripped.split()
                columns = parts[1:] if ':' in parts[0] else parts
                continue
            if stripped.startswith('Average:') and columns:
                vals = stripped[len('Average:'):].split()
                if len(vals) == len(columns):
                    average = {col: int(v) for col, v in zip(columns, vals) if v.lstrip('-').isdigit()}
                continue
            parts = stripped.split()
            if columns and len(parts) == len(columns) + 1 and ':' in parts[0]:
                metrics = {col: int(v) for col, v in zip(columns, parts[1:]) if v.lstrip('-').isdigit()}
                samples.append({'time': parts[0], 'metrics': metrics})
        return {
            'lock_table_state': 'interactive_sampled',
            'header': None,
            'owners': [],
            'locks': [],
            'requests': [],
            'interactive_samples': samples,
            'interactive_average': average,
        }

    header = None
    owners = []
    locks = []
    requests = []

    blocks = re.split(r'\n(?=[A-Z_]+ BLOCK\b)', stdout)
    for block in blocks:
        bstrip = block.strip()
        if not bstrip:
            continue
        if bstrip.startswith('LOCK_HEADER BLOCK'):
            header = {}
            for key, pattern in _INT_RE.items():
                m = pattern.search(bstrip)
                if m:
                    raw_val = m.group(1).strip()
                    if key == 'creation_timestamp':
                        header[key] = raw_val
                    elif key == 'mutex_wait_percent':
                        header[key] = float(raw_val)
                    else:
                        header[key] = int(raw_val)
        elif bstrip.startswith('OWNER BLOCK'):
            m_off = re.match(r'OWNER BLOCK\s+(\d+)', bstrip)
            offset = int(m_off.group(1)) if m_off else None
            m_id = re.search(r'Owner id:\s*(\d+),\s*Type:\s*(\d+)', bstrip)
            m_pid = re.search(r'Process id:\s*(\d+)\s*\(([^)]+)\),\s*Thread id:\s*(\d+)', bstrip)
            m_flags = re.search(r'Flags:\s*(0x[0-9a-fA-F]+)', bstrip)
            m_req = re.search(r'Requests\s*\((\d+)\):', bstrip)
            m_pend = re.search(r'Pending\s*\((\d+)\):', bstrip)
            waits_on = []
            for wm in re.finditer(r'(\d+)\s+waits on\s*(nothing\.|\r?\n\s*(\d+))', bstrip):
                if wm.group(1) == str(offset) and wm.group(3):
                    waits_on.append(int(wm.group(3)))
            if not waits_on and re.search(rf'\b{offset}\s+waits on\s*\n\s*(\d+)', bstrip):
                for extra in re.findall(r'^\s+(\d+)\s+waits on', bstrip, flags=re.M):
                    if int(extra) != offset and int(extra) not in waits_on:
                        waits_on.append(int(extra))
            owners.append({
                'offset': offset,
                'owner_id': str(m_id.group(1)) if m_id else None,
                'owner_type': int(m_id.group(2)) if m_id else None,
                'pid': int(m_pid.group(1)) if m_pid else None,
                'process_state': m_pid.group(2).strip() if m_pid else None,
                'thread_id': int(m_pid.group(3)) if m_pid else None,
                'flags': m_flags.group(1) if m_flags else None,
                'requests_count': int(m_req.group(1)) if m_req else 0,
                'pending_count': int(m_pend.group(1)) if m_pend else 0,
                'waits_on_offsets': waits_on,
                'is_waiting': bool(waits_on or (m_pend and int(m_pend.group(1)) > 0)),
            })
        elif bstrip.startswith('LOCK BLOCK'):
            m_off = re.match(r'LOCK BLOCK\s+(\d+)', bstrip)
            m_meta = re.search(
                r'Series:\s*(\d+),\s*State:\s*(\d+),\s*Size:\s*(\d+),\s*Length:\s*(\d+),\s*Data:\s*(\d+)',
                bstrip,
            )
            m_key = re.search(r'Key:\s*([^,\r\n]+),\s*Flags:\s*(0x[0-9a-fA-F]+),\s*Pending request count:\s*(\d+)', bstrip)
            lock_reqs = []
            for rm in re.finditer(
                r'Request\s+(\d+),\s*Owner:\s*(\d+),\s*State:\s*(\d+)\s*\((\d+)\),\s*Flags:\s*(0x[0-9a-fA-F]+)',
                bstrip,
            ):
                lock_reqs.append({
                    'request_offset': int(rm.group(1)),
                    'owner_offset': int(rm.group(2)),
                    'granted_state': int(rm.group(3)),
                    'requested_state': int(rm.group(4)),
                    'flags': rm.group(5),
                })
            locks.append({
                'offset': int(m_off.group(1)) if m_off else None,
                'series': int(m_meta.group(1)) if m_meta else None,
                'state': int(m_meta.group(2)) if m_meta else None,
                'size': int(m_meta.group(3)) if m_meta else None,
                'key_length': int(m_meta.group(4)) if m_meta else None,
                'key': (m_key.group(1).strip() if include_raw_keys else '[redacted]') if m_key else None,
                'key_redacted': not include_raw_keys,
                'flags': m_key.group(2) if m_key else None,
                'pending_request_count': int(m_key.group(3)) if m_key else 0,
                'requests': lock_reqs,
            })
        elif bstrip.startswith('REQUEST BLOCK'):
            m_off = re.match(r'REQUEST BLOCK\s+(\d+)', bstrip)
            m_meta = re.search(
                r'Owner:\s*(\d+),\s*Lock:\s*(\d+),\s*State:\s*(\d+),\s*Mode:\s*(\d+),\s*Flags:\s*(0x[0-9a-fA-F]+)',
                bstrip,
            )
            requests.append({
                'offset': int(m_off.group(1)) if m_off else None,
                'owner_offset': int(m_meta.group(1)) if m_meta else None,
                'lock_offset': int(m_meta.group(2)) if m_meta else None,
                'state': int(m_meta.group(3)) if m_meta else None,
                'mode': int(m_meta.group(4)) if m_meta else None,
                'flags': m_meta.group(5) if m_meta else None,
                'ast_pointers_redacted': True,
            })

    return {
        'lock_table_state': 'active',
        'header': header,
        'owners': owners,
        'locks': locks,
        'requests': requests,
        'interactive_samples': [],
        'interactive_average': None,
    }


def _read_bounded_pipe(stream, limit):
    chunks = []
    total = 0
    truncated = False
    while True:
        chunk = stream.read(65536)
        if not chunk:
            break
        if total < limit:
            keep = chunk[:limit - total]
            chunks.append(keep)
            total += len(keep)
            if len(keep) < len(chunk):
                truncated = True
        else:
            truncated = True
    return b''.join(chunks).decode('utf-8', errors='replace'), truncated


def execute_lock_print(scope, options):
    current_boot = Path('/proc/sys/kernel/random/boot_id').read_text(encoding='utf-8').strip()
    if current_boot != scope['boot_id']:
        return {
            'state': 'rejected',
            'native_dispatched': False,
            'reason': 'Application host boot identity changed since review',
        }
    db_path = Path(scope['database'])
    if not db_path.is_file() or db_path.resolve(strict=True) != db_path:
        return {
            'state': 'rejected',
            'native_dispatched': False,
            'reason': 'Reviewed database file is no longer available at its canonical path',
        }
    st = db_path.stat()
    if {'device': str(st.st_dev), 'inode': str(st.st_ino)} != scope['database_identity']:
        return {
            'state': 'rejected',
            'native_dispatched': False,
            'reason': 'Database file inode changed since review; refresh and review again',
        }
    binary_path = Path(scope['binary_path'])
    if not binary_path.is_file() or _file_sha256(binary_path) != scope['binary_sha256']:
        return {
            'state': 'rejected',
            'native_dispatched': False,
            'reason': 'fb_lock_print binary changed since review',
        }

    cli_args = [str(binary_path), *build_cli_arguments(scope['database'], options)]
    env = {k: v for k, v in os.environ.items() if k not in STRIPPED_ENV_KEYS}
    env['FIREBIRD'] = scope['firebird_runtime_root']
    if scope['firebird_lock_directory']:
        env['FIREBIRD_LOCK'] = scope['firebird_lock_directory']
    lib_dir = scope['library_directory']
    env['LD_LIBRARY_PATH'] = f"{lib_dir}:{env['LD_LIBRARY_PATH']}" if env.get('LD_LIBRARY_PATH') else lib_dir

    started_at = datetime.now(timezone.utc).isoformat()
    proc = subprocess.Popen(
        cli_args,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
        shell=False,
        start_new_session=True,
    )
    timed_out = False
    process_cleaned_up = False
    try:
        raw_out, raw_err = proc.communicate(timeout=options['timeout_seconds'])
        process_cleaned_up = True
    except subprocess.TimeoutExpired:
        timed_out = True
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        raw_out, raw_err = proc.communicate(timeout=5)
        process_cleaned_up = proc.poll() is not None

    completed_at = datetime.now(timezone.utc).isoformat()
    out_truncated = len(raw_out) > MAX_OUTPUT_BYTES
    err_truncated = len(raw_err) > 65536
    stdout_text = raw_out[:MAX_OUTPUT_BYTES].decode('utf-8', errors='replace')
    stderr_text = raw_err[:65536].decode('utf-8', errors='replace')

    if timed_out:
        return {
            'state': 'timed_out',
            'native_dispatched': True,
            'timed_out': True,
            'process_cleaned_up': process_cleaned_up,
            'return_code': proc.returncode,
            'started_at': started_at,
            'completed_at': completed_at,
            'published_as_default_metric': False,
            'output_truncated': out_truncated or err_truncated,
        }

    if proc.returncode != 0:
        return {
            'state': 'native_error',
            'native_dispatched': True,
            'timed_out': False,
            'process_cleaned_up': process_cleaned_up,
            'return_code': proc.returncode,
            'stderr': _sanitize_raw_text(stderr_text, False)[:4096],
            'started_at': started_at,
            'completed_at': completed_at,
            'published_as_default_metric': False,
            'output_truncated': out_truncated or err_truncated,
        }

    include_raw = bool(options.get('include_raw_lock_keys'))
    parsed = parse_lock_print_output(stdout_text, stderr_text, include_raw_keys=include_raw)
    return {
        'state': 'completed',
        'native_dispatched': True,
        'timed_out': False,
        'process_cleaned_up': process_cleaned_up,
        'return_code': 0,
        'started_at': started_at,
        'completed_at': completed_at,
        'source_authority': {
            'utility': 'fb_lock_print',
            'engine_version': scope['engine_version'],
            'hostname': scope['hostname'],
            'attachment_mode': scope['attachment_mode'],
            'database': scope['database'],
            'database_identity': scope['database_identity'],
            'binary_sha256': scope['binary_sha256'],
        },
        'published_as_default_metric': False,
        'output_truncated': out_truncated or err_truncated,
        'parsed': parsed,
        'sanitized_text': _sanitize_raw_text(stdout_text, include_raw)[:65536],
    }
