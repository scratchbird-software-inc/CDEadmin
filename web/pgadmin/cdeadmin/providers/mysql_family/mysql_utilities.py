"""Managed MySQL 9.7.0 offline storage and benchmark host utilities.

Covers the five audited MySQL 9.7.0 utility gaps:
- MY-AUDIT-UTILITY-MYISAMCHK (``run_myisamchk``)
- MY-AUDIT-UTILITY-MYISAMPACK (``run_myisampack``)
- MY-AUDIT-UTILITY-INNOCHECKSUM (``run_innochecksum``)
- MY-AUDIT-UTILITY-IBD2SDI (``run_ibd2sdi``)
- MY-AUDIT-UTILITY-MYSQLSLAP (``run_mysqlslap``)
"""
from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json
import re
import socket
import uuid

from ...sdk import RelationalClientError, RelationalCredentialError
from ...security import SecretLease
from .mysql_engine_diagnostics import observer_route, release
from .mysql_instance import target_uuid
from .utility_host_worker import (
    UtilityHostError,
    format_defaults_file,
    open_host_session,
    resolve_posix_subpath,
    validate_identifier,
    validate_posix_root,
)

KEY = 'mysql_utility'

OPERATIONS = {
    'run_myisamchk': 'Check or repair offline MyISAM table files',
    'run_myisampack': 'Compress offline MyISAM table files',
    'run_innochecksum': 'Inspect or rewrite offline InnoDB page checksums',
    'run_ibd2sdi': 'Extract offline InnoDB tablespace SDI metadata',
    'run_mysqlslap': 'Run concurrency load benchmark',
}

READS = frozenset()
DESTRUCTIVE = frozenset({'run_myisampack'})

PROVENANCE = {
    'myisamchk': {
        'audit_id': 'MY-AUDIT-UTILITY-MYISAMCHK',
        'native_utility': 'myisamchk',
        'native_implementation_source': 'storage/myisam/myisamchk.cc',
        'source_sha256': '6902dc60ffd5c516db6b1452283e3711ebf5bd405342b2176057f5efbb1fdbfe',
    },
    'myisampack': {
        'audit_id': 'MY-AUDIT-UTILITY-MYISAMPACK',
        'native_utility': 'myisampack',
        'native_implementation_source': 'storage/myisam/myisampack.cc',
        'source_sha256': 'e5405e527d9d50eff4649946f741116de14af763124de5183222962ea14dbabe',
    },
    'innochecksum': {
        'audit_id': 'MY-AUDIT-UTILITY-INNOCHECKSUM',
        'native_utility': 'innochecksum',
        'native_implementation_source': 'utilities/innochecksum.cc',
        'source_sha256': 'b930a905d7cb5ac75d93c480a42efef73bd5b360c7a7764ae032b6de6074aa79',
    },
    'ibd2sdi': {
        'audit_id': 'MY-AUDIT-UTILITY-IBD2SDI',
        'native_utility': 'ibd2sdi',
        'native_implementation_source': 'utilities/ibd2sdi.cc',
        'source_sha256': '1a2ae1ab2994980f560f366566fb324f186e7b02b6a66ec061ed2889fd581a70',
    },
    'mysqlslap': {
        'audit_id': 'MY-AUDIT-UTILITY-MYSQLSLAP',
        'native_utility': 'mysqlslap',
        'native_implementation_source': 'client/mysqlslap.cc',
        'source_sha256': 'f6b6d4d8363255cdaaf461935483b89a1b1489db0c98e1f0658cc21a56f3046d',
    },
}

OPERATION_BINARY = {
    'run_myisamchk': 'myisamchk',
    'run_myisampack': 'myisampack',
    'run_innochecksum': 'innochecksum',
    'run_ibd2sdi': 'ibd2sdi',
    'run_mysqlslap': 'mysqlslap',
}

HOST_FIELDS = frozenset({
    'execution_host_kind', 'executable_path', 'datadir', 'workspace',
    'pid_file', 'socket_path', 'container_name', 'docker_context',
    'ssh_host', 'ssh_port', 'ssh_username', 'ssh_host_key',
    'ssh_auth_mode', 'ssh_password', 'ssh_private_key', 'ssh_python',
    'timeout_seconds', 'confirmation',
})

SENSITIVE_HOST_KEYS = ('ssh_password', 'ssh_private_key')
SYSTEM_SCHEMAS = frozenset({
    'mysql', 'information_schema', 'performance_schema', 'sys', 'mtr', 'ndbinfo', 'test',
})
FORBIDDEN_BENCHMARK_SQL_RE = re.compile(
    r'\b(drop\s+database|drop\s+schema|create\s+database|create\s+schema|'
    r'grant\s+|revoke\s+|create\s+user|alter\s+user|drop\s+user|'
    r'shutdown\b|restart\b|set\s+global|set\s+persist|'
    r'reset\s+master|reset\s+binary|purge\s+binary|'
    r'install\s+plugin|uninstall\s+plugin|install\s+component|uninstall\s+component|'
    r'load\s+data|into\s+outfile|into\s+dumpfile)\b',
    re.I,
)
SCRATCH_SCHEMA_RE = re.compile(r'^(cdeadmin_slap_|mysqlslap)[A-Za-z0-9_]{0,48}$')

_SSH_SECRET_LEASES: dict[str, SecretLease] = {}


def _store_ssh_secrets(secrets_dict: dict) -> str | None:
    if not secrets_dict:
        return None
    lease_id = 'ssh-lease-' + uuid.uuid4().hex
    _SSH_SECRET_LEASES[lease_id] = SecretLease(json.dumps(secrets_dict).encode('utf-8'))
    return lease_id


def _peek_ssh_secrets(lease_id: str | None) -> dict:
    if not lease_id:
        return {}
    lease = _SSH_SECRET_LEASES.get(lease_id)
    if lease is None:
        raise RelationalCredentialError('SSH execution-host credential lease expired or is unavailable')
    return lease.use(lambda view: json.loads(bytes(view).decode('utf-8')))


def _release_ssh_secrets(lease_id: str | None) -> None:
    if not lease_id:
        return
    lease = _SSH_SECRET_LEASES.pop(lease_id, None)
    if lease is not None:
        lease.close()


def _parse_host_spec(draft: Mapping, *, require_datadir: bool) -> tuple[dict, dict]:
    kind = draft.get('execution_host_kind', 'local')
    if kind not in {'local', 'container', 'ssh'}:
        raise RelationalClientError('Select local, container, or ssh execution_host_kind')
    workspace = draft.get('workspace')
    if not isinstance(workspace, str) or not workspace.strip():
        raise RelationalClientError('Select a private execution-host workspace path')
    try:
        workspace = validate_posix_root(workspace.strip(), 'workspace')
    except UtilityHostError as exc:
        raise RelationalClientError(str(exc)) from None

    datadir_raw = draft.get('datadir')
    datadir = None
    if require_datadir or (isinstance(datadir_raw, str) and datadir_raw.strip()):
        if not isinstance(datadir_raw, str) or not datadir_raw.strip():
            raise RelationalClientError('Select the offline database data directory path')
        try:
            datadir = validate_posix_root(datadir_raw.strip(), 'datadir')
        except UtilityHostError as exc:
            raise RelationalClientError(str(exc)) from None

    timeout = draft.get('timeout_seconds', 120)
    if type(timeout) is not int or not 1 <= timeout <= 3600:
        raise RelationalClientError('Select timeout_seconds as an integer from 1 through 3600')

    exec_path = draft.get('executable_path')
    if exec_path is not None and exec_path != '':
        if not isinstance(exec_path, str) or '\x00' in exec_path or len(exec_path) > 1024:
            raise RelationalClientError('Invalid executable_path')
        exec_path = exec_path.strip()
    else:
        exec_path = None

    spec = {
        'execution_host_kind': kind,
        'workspace': workspace,
        'datadir': datadir,
        'executable_path': exec_path,
        'pid_file': (draft.get('pid_file') or '').strip() or None,
        'socket_path': (draft.get('socket_path') or '').strip() or None,
        'timeout_seconds': timeout,
    }
    ssh_secrets = {}
    if kind == 'container':
        cname = (draft.get('container_name') or '').strip()
        if not cname or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', cname):
            raise RelationalClientError('Select the admitted execution container_name')
        spec['container_name'] = cname
        dctx = (draft.get('docker_context') or '').strip()
        if dctx:
            if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,63}', dctx):
                raise RelationalClientError('Select a valid docker_context')
            spec['docker_context'] = dctx
    elif kind == 'ssh':
        for req_key in ('ssh_host', 'ssh_username', 'ssh_host_key'):
            val = draft.get(req_key)
            if not isinstance(val, str) or not val.strip() or '\x00' in val:
                raise RelationalClientError(f'Supply {req_key} for SSH utility host execution')
            spec[req_key] = val.strip()
        ssh_port = draft.get('ssh_port', 22)
        if type(ssh_port) is not int or not 1 <= ssh_port <= 65535:
            raise RelationalClientError('Select a valid ssh_port (1..65535)')
        spec['ssh_port'] = ssh_port
        auth_mode = draft.get('ssh_auth_mode', 'password')
        if auth_mode not in {'password', 'private_key'}:
            raise RelationalClientError('Select password or private_key for ssh_auth_mode')
        spec['ssh_auth_mode'] = auth_mode
        spec['ssh_python'] = (draft.get('ssh_python') or '/usr/bin/python3').strip()
        if auth_mode == 'password':
            pw = draft.get('ssh_password')
            if not isinstance(pw, str) or not pw:
                raise RelationalClientError('Supply ssh_password for SSH password authentication')
            ssh_secrets['password'] = pw
        else:
            pk = draft.get('ssh_private_key')
            if not isinstance(pk, str) or not pk:
                raise RelationalClientError('Supply ssh_private_key for SSH public-key authentication')
            ssh_secrets['private_key'] = pk
    return spec, ssh_secrets


def _validate_benchmark_sql(sql_text: str, schema_name: str, field_label: str) -> str:
    if not isinstance(sql_text, str) or not sql_text.strip() or '\x00' in sql_text or len(sql_text) > 65536:
        raise RelationalClientError(f'Supply bounded non-empty SQL for {field_label}')
    if FORBIDDEN_BENCHMARK_SQL_RE.search(sql_text):
        raise RelationalClientError(
            f'{field_label} contains forbidden server-global, privilege, file, or schema-drop SQL'
        )
    # Refuse explicit cross-schema references `other_db`.`table` or other_db.table outside schema_name
    for m in re.finditer(r'(?:`([^`]+)`|([A-Za-z0-9_$]+))\s*\.\s*(?:`[^`]+`|[A-Za-z0-9_$]+)', sql_text):
        qualifier = (m.group(1) or m.group(2) or '').strip()
        if qualifier and qualifier.lower() not in {schema_name.lower(), 'new', 'old'}:
            raise RelationalClientError(
                f'{field_label} references schema {qualifier!r} outside isolated benchmark schema {schema_name!r}'
            )
    return sql_text.strip()


def compile_operation(operation: str, draft: Mapping, target: Mapping) -> dict:
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a typed MySQL native utility operation')
    server_uuid = target_uuid(target)
    if draft.get('confirmation') != target.get('display_name'):
        raise RelationalClientError('Confirm the selected MySQL server name')

    binary = OPERATION_BINARY[operation]
    prov = PROVENANCE[binary]
    public_draft = {k: deepcopy(v) for k, v in draft.items() if k not in SENSITIVE_HOST_KEYS}
    for sk in SENSITIVE_HOST_KEYS:
        if draft.get(sk):
            public_draft[sk + '_redacted'] = True

    if operation == 'run_myisamchk':
        allowed = HOST_FIELDS | {
            'database_name', 'table_name', 'mode',
            'include_information', 'quick', 'backup', 'destructive_confirmed',
        }
        if set(draft) - allowed:
            raise RelationalClientError('Unsupported field in run_myisamchk draft')
        host_spec, ssh_secrets = _parse_host_spec(draft, require_datadir=True)
        try:
            db_name = validate_identifier(draft.get('database_name'), 'database_name')
            tbl_name = validate_identifier(draft.get('table_name'), 'table_name')
        except UtilityHostError as exc:
            raise RelationalClientError(str(exc)) from None
        mode = draft.get('mode', 'check')
        mode_flags = {
            'check': ['--check'],
            'medium_check': ['--medium-check'],
            'extend_check': ['--extend-check'],
            'information': ['--check', '--information'],
            'recover': ['--recover'],
            'safe_recover': ['--safe-recover'],
            'sort_index': ['--sort-index'],
            'analyze': ['--analyze'],
        }
        if mode not in mode_flags:
            raise RelationalClientError('Select a valid myisamchk mode')
        mutating = mode in {'recover', 'safe_recover', 'sort_index', 'analyze'}
        include_info = bool(draft.get('include_information', False))
        quick = bool(draft.get('quick', False))
        backup = bool(draft.get('backup', mutating))
        destructive_confirmed = bool(draft.get('destructive_confirmed', False))
        if mutating and not destructive_confirmed:
            raise RelationalClientError('Confirm destructive_confirmed before offline MyISAM repair, index sort, or analyze')
        if quick and mode not in {'recover', 'safe_recover', 'check'}:
            raise RelationalClientError('--quick applies only to check or recover modes')
        cli_preview = list(mode_flags[mode])
        if include_info and '--information' not in cli_preview:
            cli_preview.append('--information')
        if quick:
            cli_preview.append('--quick')
        if backup and mutating:
            cli_preview.append('--backup')
        rel_myi = f'{db_name}/{tbl_name}.MYI'
        rel_myd = f'{db_name}/{tbl_name}.MYD'
        spec = {
            'database_name': db_name,
            'table_name': tbl_name,
            'mode': mode,
            'mutating': mutating,
            'backup': backup,
            'flags': cli_preview,
            'rel_myi': rel_myi,
            'rel_myd': rel_myd,
        }
        preview_cmd = f'myisamchk {" ".join(cli_preview)} --tmpdir=<private_workspace> <datadir>/{rel_myi}'

    elif operation == 'run_myisampack':
        allowed = HOST_FIELDS | {
            'database_name', 'table_name', 'dry_run_test',
            'backup', 'force', 'join_target_table', 'source_tables',
            'rebuild_indexes', 'destructive_confirmed',
        }
        if set(draft) - allowed:
            raise RelationalClientError('Unsupported field in run_myisampack draft')
        host_spec, ssh_secrets = _parse_host_spec(draft, require_datadir=True)
        try:
            db_name = validate_identifier(draft.get('database_name'), 'database_name')
            tbl_name = validate_identifier(draft.get('table_name'), 'table_name')
        except UtilityHostError as exc:
            raise RelationalClientError(str(exc)) from None
        dry_run = bool(draft.get('dry_run_test', False))
        backup = bool(draft.get('backup', True))
        force = bool(draft.get('force', False))
        rebuild_indexes = bool(draft.get('rebuild_indexes', True))
        destructive_confirmed = bool(draft.get('destructive_confirmed', False))
        if not dry_run and not destructive_confirmed:
            raise RelationalClientError('Confirm destructive_confirmed before offline MyISAM compression')
        join_target = (draft.get('join_target_table') or '').strip() or None
        extra_sources_raw = draft.get('source_tables') or []
        extra_sources = []
        if join_target is not None:
            try:
                join_target = validate_identifier(join_target, 'join_target_table')
                for item in extra_sources_raw:
                    val = item.get('value') if isinstance(item, Mapping) else item
                    extra_sources.append(validate_identifier(val, 'source_tables item'))
            except UtilityHostError as exc:
                raise RelationalClientError(str(exc)) from None
        elif extra_sources_raw:
            raise RelationalClientError('source_tables applies only when join_target_table is set')
        flags = ['--verbose']
        if dry_run:
            flags.append('--test')
        if backup and not dry_run:
            flags.append('--backup')
        if force:
            flags.append('--force')
        all_tables = [tbl_name, *[t for t in extra_sources if t != tbl_name]]
        spec = {
            'database_name': db_name,
            'table_name': tbl_name,
            'source_tables': all_tables,
            'join_target_table': join_target,
            'dry_run_test': dry_run,
            'mutating': not dry_run,
            'backup': backup,
            'force': force,
            'rebuild_indexes': rebuild_indexes and not dry_run,
            'flags': flags,
        }
        preview_cmd = f'myisampack {" ".join(flags)} <datadir>/{db_name}/{tbl_name}.MYI' + (
            f' && myisamchk -rq --sort-index --analyze <datadir>/{db_name}/{join_target or tbl_name}.MYI'
            if spec['rebuild_indexes'] else ''
        )

    elif operation == 'run_innochecksum':
        allowed = HOST_FIELDS | {
            'database_name', 'table_name', 'tablespace_scope', 'tablespace_relpath',
            'count_only', 'start_page', 'end_page', 'page_num',
            'strict_check', 'no_check', 'write_algorithm',
            'page_type_summary', 'enable_private_log', 'destructive_confirmed',
        }
        if set(draft) - allowed:
            raise RelationalClientError('Unsupported field in run_innochecksum draft')
        ts_scope = draft.get('tablespace_scope', 'datadir_table')
        if ts_scope not in {'datadir_table', 'workspace_staged'}:
            raise RelationalClientError('Select datadir_table or workspace_staged for tablespace_scope')
        host_spec, ssh_secrets = _parse_host_spec(draft, require_datadir=True)
        if ts_scope == 'datadir_table':
            try:
                db_name = validate_identifier(draft.get('database_name'), 'database_name')
                tbl_name = validate_identifier(draft.get('table_name'), 'table_name')
            except UtilityHostError as exc:
                raise RelationalClientError(str(exc)) from None
            rel_ibd = f'{db_name}/{tbl_name}.ibd'
        else:
            rel_raw = (draft.get('tablespace_relpath') or '').strip()
            if not rel_raw or not rel_raw.endswith('.ibd'):
                raise RelationalClientError('Select a relative .ibd file path inside the workspace')
            try:
                resolve_posix_subpath(host_spec['workspace'], rel_raw, 'tablespace_relpath')
            except UtilityHostError as exc:
                raise RelationalClientError(str(exc)) from None
            rel_ibd = rel_raw
            db_name = None
            tbl_name = None

        count_only = bool(draft.get('count_only', False))
        strict_check = draft.get('strict_check', 'crc32')
        if strict_check not in {'', 'crc32', 'innodb', 'none'}:
            raise RelationalClientError('Select crc32, innodb, or none for strict_check')
        write_alg = draft.get('write_algorithm', '')
        if write_alg not in {'', 'crc32', 'innodb', 'none'}:
            raise RelationalClientError('Select crc32, innodb, none, or empty for write_algorithm')
        no_check = bool(draft.get('no_check', False))
        if no_check and not write_alg:
            raise RelationalClientError('MySQL innochecksum --no-check requires an explicit --write checksum algorithm')
        if count_only and write_alg:
            raise RelationalClientError('Cannot combine --count with --write checksum rewrite')
        mutating = bool(write_alg)
        if mutating and not bool(draft.get('destructive_confirmed', False)):
            raise RelationalClientError('Confirm destructive_confirmed before rewriting InnoDB page checksums with --write')

        flags = []
        if count_only:
            flags.append('--count')
        for field_key, cli_flag in (('start_page', '--start-page'), ('end_page', '--end-page'), ('page_num', '--page')):
            val = draft.get(field_key)
            if val is not None and val != '':
                if type(val) is not int or val < 0:
                    raise RelationalClientError(f'{field_key} must be a non-negative integer')
                if count_only:
                    raise RelationalClientError(f'Cannot combine --count with {field_key}')
                flags.append(f'{cli_flag}={val}')
        if strict_check and not count_only and not no_check:
            flags.append(f'--strict-check={strict_check}')
        if no_check:
            flags.append('--no-check')
        if write_alg:
            flags.append(f'--write={write_alg}')
        if bool(draft.get('page_type_summary', False)) and not count_only:
            flags.append('--page-type-summary')
        enable_log = bool(draft.get('enable_private_log', True)) and not count_only
        spec = {
            'tablespace_scope': ts_scope,
            'database_name': db_name,
            'table_name': tbl_name,
            'rel_ibd': rel_ibd,
            'count_only': count_only,
            'strict_check': strict_check,
            'no_check': no_check,
            'write_algorithm': write_alg,
            'mutating': mutating,
            'enable_private_log': enable_log,
            'flags': flags,
        }
        preview_cmd = f'innochecksum {" ".join(flags)}' + (' --log=<private_log>' if enable_log else '') + f' <{ts_scope}>/{rel_ibd}'

    elif operation == 'run_ibd2sdi':
        allowed = HOST_FIELDS | {
            'database_name', 'table_name', 'tablespace_scope', 'tablespace_relpath',
            'sdi_type', 'sdi_id', 'skip_data', 'strict_check', 'no_check',
        }
        if set(draft) - allowed:
            raise RelationalClientError('Unsupported field in run_ibd2sdi draft')
        ts_scope = draft.get('tablespace_scope', 'datadir_table')
        if ts_scope not in {'datadir_table', 'workspace_staged'}:
            raise RelationalClientError('Select datadir_table or workspace_staged for tablespace_scope')
        host_spec, ssh_secrets = _parse_host_spec(draft, require_datadir=True)
        if ts_scope == 'datadir_table':
            try:
                db_name = validate_identifier(draft.get('database_name'), 'database_name')
                tbl_name = validate_identifier(draft.get('table_name'), 'table_name')
            except UtilityHostError as exc:
                raise RelationalClientError(str(exc)) from None
            rel_ibd = f'{db_name}/{tbl_name}.ibd'
        else:
            rel_raw = (draft.get('tablespace_relpath') or '').strip()
            if not rel_raw or not rel_raw.endswith('.ibd'):
                raise RelationalClientError('Select a relative .ibd file path inside the workspace')
            try:
                resolve_posix_subpath(host_spec['workspace'], rel_raw, 'tablespace_relpath')
            except UtilityHostError as exc:
                raise RelationalClientError(str(exc)) from None
            rel_ibd = rel_raw
            db_name = None
            tbl_name = None

        flags = []
        sdi_type = draft.get('sdi_type')
        if sdi_type is not None and sdi_type != '':
            if type(sdi_type) is not int or not 1 <= sdi_type <= 65535:
                raise RelationalClientError('sdi_type must be a positive integer')
            flags.append(f'--type={sdi_type}')
        sdi_id = (draft.get('sdi_id') or '').strip()
        if sdi_id:
            if not re.fullmatch(r'[0-9]{1,20}', sdi_id):
                raise RelationalClientError('sdi_id must be an unsigned 64-bit integer string')
            flags.append(f'--id={sdi_id}')
        if bool(draft.get('skip_data', False)):
            flags.append('--skip-data')
        no_check = bool(draft.get('no_check', False))
        strict_check = draft.get('strict_check', 'crc32')
        if strict_check not in {'crc32', 'innodb', 'none'}:
            raise RelationalClientError('Select crc32, innodb, or none for strict_check')
        if no_check:
            flags.append('--no-check')
        else:
            flags.append(f'--strict-check={strict_check}')
        spec = {
            'tablespace_scope': ts_scope,
            'database_name': db_name,
            'table_name': tbl_name,
            'rel_ibd': rel_ibd,
            'mutating': False,
            'flags': flags,
        }
        preview_cmd = f'ibd2sdi {" ".join(flags)} --dump-file=<private_sdi_json> <{ts_scope}>/{rel_ibd}'

    elif operation == 'run_mysqlslap':
        allowed = HOST_FIELDS | {
            'concurrency', 'iterations', 'number_of_queries',
            'workload_mode', 'auto_load_type', 'number_int_cols', 'number_char_cols',
            'benchmark_schema', 'create_sql', 'query_sql',
            'keep_benchmark_schema', 'isolated_scratch_confirmed',
        }
        if set(draft) - allowed:
            raise RelationalClientError('Unsupported field in run_mysqlslap draft')
        host_spec, ssh_secrets = _parse_host_spec(draft, require_datadir=False)
        if draft.get('isolated_scratch_confirmed') is not True:
            raise RelationalClientError('Confirm isolated_scratch_confirmed before running mysqlslap')
        schema_name = (draft.get('benchmark_schema') or 'cdeadmin_slap_scratch').strip()
        try:
            schema_name = validate_identifier(schema_name, 'benchmark_schema')
        except UtilityHostError as exc:
            raise RelationalClientError(str(exc)) from None
        if schema_name.lower() in SYSTEM_SCHEMAS or not SCRATCH_SCHEMA_RE.fullmatch(schema_name):
            raise RelationalClientError(
                'benchmark_schema must be a dedicated scratch schema prefixed with cdeadmin_slap_ or mysqlslap (never a system or production schema)'
            )
        concurrency_raw = str(draft.get('concurrency', '4')).strip()
        if not re.fullmatch(r'[0-9]+(,[0-9]+)*', concurrency_raw):
            raise RelationalClientError('concurrency must be a positive integer or comma-separated integers (e.g. "4" or "1,4,8")')
        levels = [int(x) for x in concurrency_raw.split(',')]
        if any(not 1 <= lv <= 256 for lv in levels):
            raise RelationalClientError('Each concurrency level must be between 1 and 256')
        iterations = draft.get('iterations', 2)
        if type(iterations) is not int or not 1 <= iterations <= 1000:
            raise RelationalClientError('iterations must be an integer between 1 and 1000')
        num_queries = draft.get('number_of_queries')
        if num_queries is not None and num_queries != '':
            if type(num_queries) is not int or not 1 <= num_queries <= 1000000:
                raise RelationalClientError('number_of_queries must be an integer between 1 and 1000000')
        else:
            num_queries = None

        wmode = draft.get('workload_mode', 'auto_generate')
        if wmode not in {'auto_generate', 'explicit_sql'}:
            raise RelationalClientError('Select auto_generate or explicit_sql for workload_mode')

        flags = [f'--concurrency={concurrency_raw}', f'--iterations={iterations}', f'--create-schema={schema_name}']
        create_sql = None
        query_sql = None
        if wmode == 'auto_generate':
            load_type = draft.get('auto_load_type', 'mixed')
            if load_type not in {'read', 'write', 'mixed', 'key', 'update'}:
                raise RelationalClientError('Select read, write, mixed, key, or update for auto_load_type')
            int_cols = draft.get('number_int_cols', 2)
            char_cols = draft.get('number_char_cols', 2)
            if type(int_cols) is not int or not 1 <= int_cols <= 64 or type(char_cols) is not int or not 1 <= char_cols <= 64:
                raise RelationalClientError('number_int_cols and number_char_cols must be integers from 1 through 64')
            flags.extend([
                '--auto-generate-sql',
                f'--auto-generate-sql-load-type={load_type}',
                f'--number-int-cols={int_cols}',
                f'--number-char-cols={char_cols}',
            ])
            if num_queries is not None:
                flags.append(f'--number-of-queries={num_queries}')
        else:
            query_sql = _validate_benchmark_sql(draft.get('query_sql', ''), schema_name, 'query_sql')
            if not query_sql.endswith(';'):
                query_sql += ';'
            raw_create = (draft.get('create_sql') or '').strip()
            if raw_create:
                create_sql = _validate_benchmark_sql(raw_create, schema_name, 'create_sql')
                if not create_sql.endswith(';'):
                    create_sql += ';'
            flags.append('--delimiter=;')
            if num_queries is not None:
                flags.append(f'--number-of-queries={num_queries}')

        keep_schema = bool(draft.get('keep_benchmark_schema', False))
        if keep_schema:
            flags.append('--no-drop')

        spec = {
            'benchmark_schema': schema_name,
            'concurrency_levels': levels,
            'iterations': iterations,
            'number_of_queries': num_queries,
            'workload_mode': wmode,
            'create_sql': create_sql,
            'query_sql': query_sql,
            'keep_benchmark_schema': keep_schema,
            'mutating': True,
            'flags': flags,
        }
        preview_cmd = f'mysqlslap --defaults-extra-file=<private_0600_cnf> {" ".join(flags)}'

    ssh_lease_id = _store_ssh_secrets(ssh_secrets)
    return {
        'statements': [{'source': f'/* native utility: {preview_cmd} */', 'parameters': ()}],
        KEY: {
            'operation': operation,
            'binary': binary,
            'provenance': prov,
            'server_uuid': server_uuid,
            'target': deepcopy(dict(target)),
            'public_draft': public_draft,
            'host_spec': host_spec,
            'spec': spec,
            'ssh_lease_id': ssh_lease_id,
        },
        'warnings': [
            f'Executes native MySQL 9.7.0 utility {binary} ({prov["native_implementation_source"]}) on the explicitly selected {host_spec["execution_host_kind"]} host.',
            'Offline utilities verify stopped mysqld, PID files, /proc open descriptors, and datadir/auto.cnf identity before and at dispatch.',
            'Credentials for benchmark runs use a temporary 0600 option file wiped immediately in finally; secrets never appear in argv or plans.',
        ],
    }


def form(operation: str) -> dict:
    from ..mysql_descriptor_contract import operation_entry
    entry = operation_entry('server', operation)
    if entry is None:
        raise RelationalClientError(f'Missing UI descriptor for MySQL operation {operation}')
    for f in entry['fields']:
        if f.get('control') == 'password':
            f['sensitive'] = True
    return entry


def _probe_sql_endpoint_stopped(client, payload: Mapping, expected_uuid: str) -> None:
    """Ensure the SQL endpoint is NOT actively serving expected_uuid before running an offline utility."""
    route = observer_route(payload)
    host = route.get('host')
    port = int(route.get('port', 3306))
    unix_sock = route.get('unix_socket')
    # Fast socket reachability test first
    reachable = False
    if unix_sock:
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(0.5)
        try:
            s.connect(str(unix_sock))
            reachable = True
        except OSError:
            pass
        finally:
            s.close()
    elif host:
        try:
            with socket.create_connection((str(host), port), timeout=0.6):
                reachable = True
        except OSError:
            pass
    if not reachable:
        return
    # Port answered: check if it is our MySQL server instance!
    handle = cursor = None
    online_msg = None
    try:
        handle = client._connect({'route': {**route, 'connection_timeout': 2, 'read_timeout': 2, 'write_timeout': 2}})
        cursor = handle.cursor()
        cursor.execute('SELECT @@server_uuid, VERSION()')
        row = cursor.fetchone()
        if row and str(row[0]).lower() == expected_uuid.lower():
            online_msg = (
                f'Refused offline MySQL utility: mysqld ({row[1]}) for server_uuid {expected_uuid} '
                'is currently online and accepting SQL connections'
            )
    except Exception:
        # If TCP port is forwarded (e.g. docker-proxy) while mysqld is stopped, host /proc check verifies datadir offline state.
        pass
    finally:
        if handle is not None:
            release(client, handle, cursor)
    if online_msg:
        raise RelationalClientError(online_msg)


def _acquire_db_password(client, route: Mapping, callback):
    references = dict(route.get('credential_references') or {})
    primary = route.get('credential_reference_id')
    if primary is not None:
        references.setdefault('database_password', primary)
    ref = references.get('database_password')
    if ref is not None:
        principal = route.get('principal_reference')
        if not isinstance(principal, str) or not principal.strip() or not callable(client.config.secret_acquirer):
            raise RelationalCredentialError('MySQL utility credential binding is unavailable')
        try:
            lease = client.config.secret_acquirer(str(ref), principal.strip(), 'provider_tool', 'database_password')
        except Exception:
            raise RelationalCredentialError('MySQL utility database credential lease is unavailable') from None
        with lease:
            return lease.use(lambda view: callback(bytes(view).decode('utf-8')))
    inline = route.get('password')
    return callback(str(inline) if inline is not None else '')


def _offline_target_paths(session, host_spec: dict, operation: str, spec: dict) -> dict[str, str]:
    datadir = host_spec['datadir']
    ws = host_spec['workspace']
    paths: dict[str, str] = {}
    if operation == 'run_myisamchk':
        paths['myi'] = session.resolve_contained_file(datadir, spec['rel_myi'], must_exist=True)
        paths['myd'] = session.resolve_contained_file(datadir, spec['rel_myd'], must_exist=True)
    elif operation == 'run_myisampack':
        db = spec['database_name']
        for idx, tname in enumerate(spec['source_tables']):
            paths[f'myi_{idx}'] = session.resolve_contained_file(datadir, f'{db}/{tname}.MYI', must_exist=True)
            paths[f'myd_{idx}'] = session.resolve_contained_file(datadir, f'{db}/{tname}.MYD', must_exist=True)
        if spec.get('join_target_table'):
            paths['join_myi'] = session.resolve_contained_file(datadir, f'{db}/{spec["join_target_table"]}.MYI', must_exist=False)
    elif operation in {'run_innochecksum', 'run_ibd2sdi'}:
        root = datadir if spec['tablespace_scope'] == 'datadir_table' else ws
        paths['ibd'] = session.resolve_contained_file(root, spec['rel_ibd'], must_exist=True)
    return paths


def parse_slap_output(stdout: str) -> dict:
    runs = []
    current: dict = {}
    for raw_line in stdout.splitlines():
        line = raw_line.strip()
        m_eng = re.search(r'Running for engine\s+(\S+)', line, re.I)
        if m_eng:
            if current:
                runs.append(current)
                current = {}
            current['storage_engine'] = m_eng.group(1)
        m_avg = re.search(r'Average number of seconds to run all queries:\s*([0-9.]+)', line, re.I)
        if m_avg:
            if 'average_seconds' in current:
                runs.append(current)
                current = {'storage_engine': current.get('storage_engine')}
            current['average_seconds'] = float(m_avg.group(1))
        m_min = re.search(r'Minimum number of seconds to run all queries:\s*([0-9.]+)', line, re.I)
        if m_min:
            current['minimum_seconds'] = float(m_min.group(1))
        m_max = re.search(r'Maximum number of seconds to run all queries:\s*([0-9.]+)', line, re.I)
        if m_max:
            current['maximum_seconds'] = float(m_max.group(1))
        m_cli = re.search(r'Number of clients running queries:\s*([0-9]+)', line, re.I)
        if m_cli:
            current['clients'] = int(m_cli.group(1))
        m_qpc = re.search(r'Average number of queries per client:\s*([0-9]+)', line, re.I)
        if m_qpc:
            current['queries_per_client'] = int(m_qpc.group(1))
    if current and ('average_seconds' in current or 'clients' in current):
        runs.append(current)
    primary = runs[-1] if runs else {}
    return {
        'run_count': len(runs),
        'runs': runs,
        'storage_engine': primary.get('storage_engine'),
        'average_seconds': primary.get('average_seconds'),
        'minimum_seconds': primary.get('minimum_seconds'),
        'maximum_seconds': primary.get('maximum_seconds'),
        'clients_per_run': primary.get('clients'),
        'queries_per_client': primary.get('queries_per_client'),
    }


def parse_sdi_json(raw_bytes: bytes) -> dict:
    text = raw_bytes.decode('utf-8', errors='replace').strip()
    if not text:
        return {'record_count': 0, 'objects': []}
    doc = json.loads(text)
    if not isinstance(doc, list):
        raise RelationalClientError('ibd2sdi output did not parse as a JSON array')
    objects = []
    sdi_version = None
    for entry in doc:
        if not isinstance(entry, list) or len(entry) != 2:
            if isinstance(entry, Mapping) and 'ibd2sdi' in entry:
                continue
            if isinstance(entry, Mapping):
                sdi_type = entry.get('type')
                sdi_id = entry.get('id')
                obj_wrap = entry.get('object') if isinstance(entry.get('object'), Mapping) else {}
            else:
                continue
        else:
            continue
        if sdi_version is None and isinstance(obj_wrap, Mapping):
            sdi_version = obj_wrap.get('sdi_version')
        dd_type = obj_wrap.get('dd_object_type')
        dd_obj = obj_wrap.get('dd_object') if isinstance(obj_wrap.get('dd_object'), Mapping) else {}
        cols = []
        for col in (dd_obj.get('columns') or [])[:256]:
            if isinstance(col, Mapping) and not col.get('hidden', 0) in {2, 3}:
                cols.append({
                    'name': col.get('name'),
                    'column_type_utf8': col.get('column_type_utf8'),
                    'is_nullable': col.get('is_nullable'),
                    'ordinal_position': col.get('ordinal_position'),
                })
        idxs = [
            idx.get('name')
            for idx in (dd_obj.get('indexes') or [])[:128]
            if isinstance(idx, Mapping) and idx.get('name')
        ]
        objects.append({
            'sdi_type': sdi_type,
            'sdi_id': str(sdi_id) if sdi_id is not None else None,
            'dd_object_type': dd_type,
            'name': dd_obj.get('name'),
            'engine': dd_obj.get('engine'),
            'row_format': dd_obj.get('row_format'),
            'columns': cols,
            'indexes': idxs,
        })
    return {
        'record_count': len(objects),
        'sdi_version': sdi_version,
        'objects': objects,
    }


def bind_review(client, planned: dict) -> dict:
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    operation = intent['operation']
    host_spec = intent['host_spec']
    spec = intent['spec']
    ssh_secrets = _peek_ssh_secrets(intent.get('ssh_lease_id'))

    session = None
    try:
        session = open_host_session(host_spec, ssh_secrets)
        exe_spec = host_spec.get('executable_path') or intent['binary']
        tool_info = session.inspect_binary(exe_spec, 'mysql', host_spec['workspace'])
        companion_tool = None
        if operation == 'run_myisampack' and spec.get('rebuild_indexes'):
            chk_spec = str(exe_spec).replace('myisampack', 'myisamchk') if host_spec.get('executable_path') else 'myisamchk'
            companion_tool = session.inspect_binary(chk_spec, 'mysql', host_spec['workspace'])

        if operation == 'run_mysqlslap':
            handle = client._connect({'route': observer_route(payload)})
            cursor = None
            try:
                handle.autocommit = True
                cursor = handle.cursor()
                cursor.execute('SELECT VERSION(), @@server_uuid, @@port, @@socket, CURRENT_USER()')
                row = cursor.fetchone()
                if row is None or str(row[0]).split('-')[0] != '9.7.0':
                    raise RelationalClientError('MySQL 9.7.0 server runtime is required for mysqlslap')
                obs_ver, obs_uuid, obs_port, obs_sock, obs_user = row
                if str(obs_uuid).lower() != intent['server_uuid'].lower():
                    raise RelationalClientError('Observed MySQL server_uuid differs from selected target')
                cursor.execute(
                    'SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s',
                    (spec['benchmark_schema'],),
                )
                existing_tables = int(cursor.fetchone()[0])
                if existing_tables > 0:
                    raise RelationalClientError(
                        f'Benchmark scratch schema {spec["benchmark_schema"]!r} already contains {existing_tables} table(s); '
                        'select an empty isolated scratch schema'
                    )
                review = {
                    'mode': 'online_benchmark',
                    'tool': tool_info,
                    'server_identity': {
                        'version': str(obs_ver),
                        'server_uuid': str(obs_uuid),
                        'server_port': int(obs_port),
                        'server_socket': str(obs_sock) if obs_sock else None,
                        'principal': str(obs_user),
                    },
                    'scratch_schema_verified_empty': True,
                }
            finally:
                cleanup = release(client, handle, cursor)
                if not cleanup['connection_released']:
                    raise RelationalClientError('Benchmark review observer connection release is unconfirmed')
        else:
            _probe_sql_endpoint_stopped(client, payload, intent['server_uuid'])
            dd_identity = session.observe_datadir_identity(host_spec['datadir'], 'mysql')
            if dd_identity.get('server_uuid') and dd_identity['server_uuid'].lower() != intent['server_uuid'].lower():
                raise RelationalClientError(
                    f'Execution-host datadir auto.cnf server-uuid ({dd_identity["server_uuid"]}) differs from target ({intent["server_uuid"]})'
                )
            target_paths = _offline_target_paths(session, host_spec, operation, spec)
            offline_state = session.verify_offline_state(
                host_spec['datadir'],
                [p for k, p in target_paths.items() if k != 'join_myi'],
                'mysql',
                pid_file=host_spec.get('pid_file'),
                socket_path=host_spec.get('socket_path'),
            )
            fingerprints = {k: session.file_fingerprint(p) for k, p in target_paths.items()}
            review = {
                'mode': 'offline_storage_utility',
                'tool': tool_info,
                'companion_tool': companion_tool,
                'datadir_identity': dd_identity,
                'offline_verification': offline_state,
                'target_paths': target_paths,
                'file_fingerprints': fingerprints,
            }

        intent['review'] = review
        planned['command_preview'].update(
            native_utility=intent['binary'],
            native_tool_version=tool_info['tool_version_identity'],
            native_executable_sha256=tool_info['executable_sha256'],
            execution_host_kind=tool_info['execution_host_kind'],
            provenance=intent['provenance'],
        )
        return planned
    except UtilityHostError as exc:
        raise RelationalClientError(str(exc)) from None
    finally:
        if session is not None:
            session.close()


def apply(client, request: Mapping, connection=None, *, cancel_signal=None, progress=None) -> dict:
    if connection is not None:
        raise RelationalClientError('MySQL host utilities do not execute inside a retained SQL session')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    review = intent.get('review')
    if not isinstance(review, Mapping):
        raise RelationalClientError('Review the exact MySQL utility plan before dispatch')

    operation = intent['operation']
    host_spec = intent['host_spec']
    spec = intent['spec']
    ssh_lease_id = intent.get('ssh_lease_id')
    ssh_secrets = _peek_ssh_secrets(ssh_lease_id)
    job_id = 'myutil-' + uuid.uuid4().hex[:16]

    session = None
    dispatched = False
    acknowledged = False
    cleanup_confirmed = False
    try:
        session = open_host_session(host_spec, ssh_secrets)
        exe_spec = host_spec.get('executable_path') or intent['binary']
        current_tool = session.inspect_binary(exe_spec, 'mysql', host_spec['workspace'])
        if current_tool['executable_sha256'] != review['tool']['executable_sha256']:
            raise RelationalClientError('Native MySQL utility binary changed after review; re-plan before dispatch')

        if operation == 'run_mysqlslap':
            route = observer_route(payload)
            handle = client._connect({'route': route})
            cursor = None
            try:
                handle.autocommit = True
                cursor = handle.cursor()
                cursor.execute('SELECT VERSION(), @@server_uuid, @@port, @@socket')
                row = cursor.fetchone()
                if not row or str(row[1]).lower() != intent['server_uuid'].lower():
                    raise RelationalClientError('MySQL server_uuid changed after benchmark review')
                cursor.execute(
                    'SELECT COUNT(*) FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s',
                    (spec['benchmark_schema'],),
                )
                if int(cursor.fetchone()[0]) > 0:
                    raise RelationalClientError(
                        f'Benchmark scratch schema {spec["benchmark_schema"]!r} gained tables after review; refusing execution'
                    )
            finally:
                release(client, handle, cursor)

            job_rel = f'jobs/{job_id}'
            session.prepare_job_dir(host_spec['workspace'], job_id)
            extra_args = list(spec['flags'])
            if spec['workload_mode'] == 'explicit_sql':
                q_abs = session.write_private_file(
                    host_spec['workspace'], f'{job_rel}/query.sql', spec['query_sql'].encode('utf-8')
                )
                extra_args.append(f'--query={q_abs}')
                if spec.get('create_sql'):
                    c_abs = session.write_private_file(
                        host_spec['workspace'], f'{job_rel}/create.sql', spec['create_sql'].encode('utf-8')
                    )
                    extra_args.append(f'--create={c_abs}')

            user = str(route.get('user') or route.get('username') or 'root')
            conn_args = [f'--user={user}']
            if host_spec['execution_host_kind'] == 'local':
                if route.get('unix_socket'):
                    conn_args.extend(['--protocol=socket', f'--socket={route["unix_socket"]}'])
                else:
                    conn_args.extend([
                        '--protocol=tcp',
                        f'--host={route.get("host", "127.0.0.1")}',
                        f'--port={int(route.get("port", 3306))}',
                    ])
            else:
                sock_override = host_spec.get('socket_path')
                if sock_override:
                    conn_args.extend(['--protocol=socket', f'--socket={sock_override}'])
                else:
                    srv_port = review['server_identity']['server_port']
                    conn_args.extend(['--protocol=tcp', '--host=127.0.0.1', f'--port={srv_port}'])

            full_args = [*conn_args, *extra_args]
            scratch_dropped = False
            obs = None
            try:
                def _run_with_secret(pw: str):
                    nonlocal dispatched
                    defaults_bytes = format_defaults_file(pw, user=user)
                    dispatched = True
                    return session.run_supervised(
                        current_tool['executable_path'],
                        full_args,
                        host_spec['workspace'],
                        host_spec['timeout_seconds'],
                        secret_defaults_bytes=defaults_bytes,
                        secret_arg_prefix='--defaults-extra-file=',
                        redact_values=(pw,),
                        cancel_signal=cancel_signal,
                    )

                obs = _acquire_db_password(client, route, _run_with_secret)
            finally:
                session.remove_private_file(host_spec['workspace'], f'{job_rel}/query.sql')
                session.remove_private_file(host_spec['workspace'], f'{job_rel}/create.sql')
                if not spec['keep_benchmark_schema']:
                    cleanup_conn = cleanup_cur = None
                    try:
                        cleanup_conn = client._connect({'route': route})
                        cleanup_conn.autocommit = True
                        cleanup_cur = cleanup_conn.cursor()
                        if obs is None or obs.get('cancelled') or obs.get('timed_out'):
                            try:
                                cleanup_cur.execute(
                                    'SELECT ID FROM information_schema.PROCESSLIST WHERE DB = %s AND ID <> CONNECTION_ID()',
                                    (spec['benchmark_schema'],),
                                )
                                for (tid,) in list(cleanup_cur.fetchall() or ()):
                                    try:
                                        cleanup_cur.execute(f'KILL {int(tid)}')
                                    except Exception:
                                        pass
                            except Exception:
                                pass
                        escaped_schema = spec['benchmark_schema'].replace('`', '``')
                        cleanup_cur.execute(f'DROP DATABASE IF EXISTS `{escaped_schema}`')
                        cleanup_cur.execute(
                            'SELECT COUNT(*) FROM information_schema.SCHEMATA WHERE SCHEMA_NAME = %s',
                            (spec['benchmark_schema'],),
                        )
                        scratch_dropped = int(cleanup_cur.fetchone()[0]) == 0
                    except Exception:
                        scratch_dropped = False
                    finally:
                        if cleanup_conn is not None:
                            release(client, cleanup_conn, cleanup_cur)

            cleanup_confirmed = bool(obs['cleanup_confirmed']) and (spec['keep_benchmark_schema'] or scratch_dropped)
            if obs['cancelled']:
                raise RelationalClientError(
                    f'mysqlslap benchmark cancelled; process_cleanup={obs["cleanup_confirmed"]}, scratch_schema_dropped={scratch_dropped}'
                )
            if obs['timed_out']:
                raise RelationalClientError(
                    f'mysqlslap benchmark timed out after {host_spec["timeout_seconds"]}s; process_cleanup={obs["cleanup_confirmed"]}, scratch_schema_dropped={scratch_dropped}'
                )
            if obs['return_code'] != 0:
                raise RelationalClientError(
                    f'mysqlslap failed with exit code {obs["return_code"]}: {obs["stderr"][:240]}'
                )
            parsed_metrics = parse_slap_output(obs['stdout'])
            acknowledged = True
            utility_result = {
                'operation': operation,
                'utility': 'mysqlslap',
                'provenance': intent['provenance'],
                'tool': current_tool,
                'benchmark_schema': spec['benchmark_schema'],
                'scratch_schema_cleaned_up': scratch_dropped if not spec['keep_benchmark_schema'] else False,
                'secret_passing_mode': 'private_0600_defaults_extra_file',
                'secret_file_wiped': obs['secret_file_wiped'],
                'metrics': parsed_metrics,
                'return_code': obs['return_code'],
                'cleanup_confirmed': cleanup_confirmed,
                'observed_at': datetime.now(timezone.utc).isoformat(),
            }

        else:
            # Offline storage utilities: re-verify stopped server & fingerprints right before dispatch!
            _probe_sql_endpoint_stopped(client, payload, intent['server_uuid'])
            dd_identity = session.observe_datadir_identity(host_spec['datadir'], 'mysql')
            if dd_identity.get('server_uuid') and dd_identity['server_uuid'].lower() != intent['server_uuid'].lower():
                raise RelationalClientError('Execution-host datadir server-uuid changed after review')
            target_paths = _offline_target_paths(session, host_spec, operation, spec)
            offline_now = session.verify_offline_state(
                host_spec['datadir'],
                [p for k, p in target_paths.items() if k != 'join_myi'],
                'mysql',
                pid_file=host_spec.get('pid_file'),
                socket_path=host_spec.get('socket_path'),
            )
            current_fps = {k: session.file_fingerprint(p) for k, p in target_paths.items()}
            if current_fps != review['file_fingerprints']:
                raise RelationalClientError('Target tablespace or MyISAM files changed after review; re-plan before dispatch')

            backup_receipt = None
            if spec.get('mutating'):
                backup_receipt = session.stage_private_backups(
                    host_spec['workspace'],
                    job_id,
                    {k: p for k, p in target_paths.items() if current_fps[k]['exists']},
                )

            job_dir = session.prepare_job_dir(host_spec['workspace'], job_id)
            job_rel = f'jobs/{job_id}'

            if operation == 'run_myisamchk':
                args = [*spec['flags'], f'--tmpdir={job_dir}', target_paths['myi'].removesuffix('.MYI')]
                dispatched = True
                obs = session.run_supervised(
                    current_tool['executable_path'], args, host_spec['workspace'],
                    host_spec['timeout_seconds'], cancel_signal=cancel_signal,
                )
                cleanup_confirmed = obs['cleanup_confirmed']
                if obs['cancelled'] or obs['timed_out']:
                    raise RelationalClientError('myisamchk interrupted by cancellation or timeout')
                after_fps = {k: session.file_fingerprint(p) for k, p in target_paths.items()}
                combined_out = obs['stdout'] + '\n' + obs['stderr']
                corrupted = obs['return_code'] != 0 or bool(re.search(r'\b(corrupt|error|crashed)\b', combined_out, re.I))
                if spec['mutating'] and obs['return_code'] != 0:
                    raise RelationalClientError(f'myisamchk {spec["mode"]} failed (exit {obs["return_code"]}): {combined_out[:240]}')
                if spec['mutating']:
                    session.sync_datadir_ownership(host_spec['datadir'], list(target_paths.values()))
                acknowledged = True
                utility_result = {
                    'operation': operation,
                    'utility': 'myisamchk',
                    'mode': spec['mode'],
                    'mutating': spec['mutating'],
                    'return_code': obs['return_code'],
                    'check_passed': obs['return_code'] == 0,
                    'corrupted_detected': corrupted if not spec['mutating'] else False,
                    'repaired': spec['mutating'] and obs['return_code'] == 0,
                    'output_summary': combined_out.strip()[:2048],
                    'before_files': current_fps,
                    'after_files': after_fps,
                    'backup_artifact': backup_receipt,
                    'offline_verification': offline_now,
                    'tool': current_tool,
                    'provenance': intent['provenance'],
                    'cleanup_confirmed': cleanup_confirmed,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                }

            elif operation == 'run_myisampack':
                args = [*spec['flags'], f'--tmpdir={job_dir}']
                if spec.get('join_target_table'):
                    args.append(f'--join={target_paths["join_myi"][:-4]}')
                args.extend(target_paths[f'myi_{i}'].removesuffix('.MYI') for i in range(len(spec['source_tables'])))
                dispatched = True
                obs = session.run_supervised(
                    current_tool['executable_path'], args, host_spec['workspace'],
                    host_spec['timeout_seconds'], cancel_signal=cancel_signal,
                )
                cleanup_confirmed = obs['cleanup_confirmed']
                if obs['cancelled'] or obs['timed_out'] or obs['return_code'] != 0:
                    raise RelationalClientError(
                        f'myisampack failed (exit {obs["return_code"]}): {(obs["stdout"] + " " + obs["stderr"]).strip()[:240]}'
                    )
                rebuild_obs = None
                packed_myi = target_paths['join_myi'] if spec.get('join_target_table') else target_paths['myi_0']
                if spec.get('rebuild_indexes'):
                    comp = review['companion_tool']
                    chk_now = session.inspect_binary(comp['executable_path'], 'mysql', host_spec['workspace'])
                    if chk_now['executable_sha256'] != comp['executable_sha256']:
                        raise RelationalClientError('Companion myisamchk binary changed before post-pack index rebuild')
                    rebuild_obs = session.run_supervised(
                        chk_now['executable_path'],
                        ['-rq', '--sort-index', '--analyze', f'--tmpdir={job_dir}', packed_myi.removesuffix('.MYI')],
                        host_spec['workspace'],
                        host_spec['timeout_seconds'],
                        cancel_signal=cancel_signal,
                    )
                    cleanup_confirmed = cleanup_confirmed and rebuild_obs['cleanup_confirmed']
                    if rebuild_obs['return_code'] != 0:
                        raise RelationalClientError(
                            f'Post-pack myisamchk -rq failed (exit {rebuild_obs["return_code"]}): {rebuild_obs["stderr"][:240]}'
                        )
                packed_myd = packed_myi[:-4] + '.MYD'
                if spec['mutating']:
                    session.sync_datadir_ownership(host_spec['datadir'], [packed_myi, packed_myd])
                after_myi_fp = session.file_fingerprint(packed_myi)
                after_myd_fp = session.file_fingerprint(packed_myd)
                before_myd_bytes = current_fps['myd_0']['size_bytes']
                after_myd_bytes = after_myd_fp['size_bytes']
                acknowledged = True
                utility_result = {
                    'operation': operation,
                    'utility': 'myisampack',
                    'dry_run_test': spec['dry_run_test'],
                    'mutating': spec['mutating'],
                    'return_code': obs['return_code'],
                    'before_myd_bytes': before_myd_bytes,
                    'after_myd_bytes': after_myd_bytes,
                    'bytes_saved': max(0, before_myd_bytes - after_myd_bytes),
                    'index_rebuild_executed': rebuild_obs is not None,
                    'index_rebuild_return_code': rebuild_obs['return_code'] if rebuild_obs else None,
                    'read_only_compressed_expected': not spec['dry_run_test'],
                    'output_summary': (obs['stdout'] + '\n' + obs['stderr']).strip()[:2048],
                    'before_files': current_fps,
                    'after_files': {'myi': after_myi_fp, 'myd': after_myd_fp},
                    'backup_artifact': backup_receipt,
                    'offline_verification': offline_now,
                    'tool': current_tool,
                    'provenance': intent['provenance'],
                    'cleanup_confirmed': cleanup_confirmed,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                }

            elif operation == 'run_innochecksum':
                args = list(spec['flags'])
                log_rel = f'{job_rel}/innochecksum.log'
                if spec.get('enable_private_log'):
                    args.append(f'--log={job_dir}/innochecksum.log')
                args.append(target_paths['ibd'])
                dispatched = True
                obs = session.run_supervised(
                    current_tool['executable_path'], args, host_spec['workspace'],
                    host_spec['timeout_seconds'], cancel_signal=cancel_signal,
                )
                cleanup_confirmed = obs['cleanup_confirmed']
                if obs['cancelled'] or obs['timed_out']:
                    raise RelationalClientError('innochecksum interrupted by cancellation or timeout')
                combined_out = (obs['stdout'] + '\n' + obs['stderr']).strip()
                if spec['mutating'] and obs['return_code'] != 0:
                    raise RelationalClientError(f'innochecksum --write failed (exit {obs["return_code"]}): {combined_out[:240]}')
                if spec['mutating'] and spec['tablespace_scope'] == 'datadir_table':
                    session.sync_datadir_ownership(host_spec['datadir'], [target_paths['ibd']])
                if spec['count_only'] and obs['return_code'] != 0:
                    raise RelationalClientError(f'innochecksum --count failed (exit {obs["return_code"]}): {combined_out[:240]}')
                m_pages = re.search(r'Number of pages:\s*([0-9]+)', combined_out, re.I)
                page_count = int(m_pages.group(1)) if m_pages else None
                log_summary = None
                if spec.get('enable_private_log'):
                    try:
                        log_data = session.read_private_file(host_spec['workspace'], log_rel, max_bytes=65536)
                        log_lines = log_data['content_bytes'].decode('utf-8', errors='replace').splitlines()
                        log_summary = {
                            'sha256': log_data['sha256'],
                            'size_bytes': log_data['size_bytes'],
                            'line_count': len(log_lines),
                            'preview_lines': [ln[:160] for ln in log_lines[:20]],
                        }
                    except UtilityHostError:
                        log_summary = None
                after_fp = session.file_fingerprint(target_paths['ibd'])
                acknowledged = True
                utility_result = {
                    'operation': operation,
                    'utility': 'innochecksum',
                    'return_code': obs['return_code'],
                    'page_count': page_count,
                    'checksum_valid': obs['return_code'] == 0,
                    'corruption_detected': obs['return_code'] != 0,
                    'rewrite_applied': spec['mutating'] and obs['return_code'] == 0,
                    'strict_check': spec['strict_check'],
                    'private_log_summary': log_summary,
                    'output_summary': combined_out[:2048],
                    'before_file': current_fps['ibd'],
                    'after_file': after_fp,
                    'backup_artifact': backup_receipt,
                    'offline_verification': offline_now,
                    'tool': current_tool,
                    'provenance': intent['provenance'],
                    'cleanup_confirmed': cleanup_confirmed,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                }

            elif operation == 'run_ibd2sdi':
                sdi_rel = f'{job_rel}/sdi.json'
                sdi_abs = f'{job_dir}/sdi.json'
                args = [*spec['flags'], f'--dump-file={sdi_abs}', target_paths['ibd']]
                dispatched = True
                obs = session.run_supervised(
                    current_tool['executable_path'], args, host_spec['workspace'],
                    host_spec['timeout_seconds'], cancel_signal=cancel_signal,
                )
                cleanup_confirmed = obs['cleanup_confirmed']
                if obs['cancelled'] or obs['timed_out'] or obs['return_code'] != 0:
                    raise RelationalClientError(
                        f'ibd2sdi failed (exit {obs["return_code"]}): {(obs["stdout"] + " " + obs["stderr"]).strip()[:240]}'
                    )
                artifact = session.read_private_file(host_spec['workspace'], sdi_rel)
                if artifact['truncated']:
                    raise RelationalClientError('ibd2sdi output exceeded bounded inspection limit')
                parsed_sdi = parse_sdi_json(artifact['content_bytes'])
                acknowledged = True
                utility_result = {
                    'operation': operation,
                    'utility': 'ibd2sdi',
                    'return_code': obs['return_code'],
                    'artifact': {
                        'relpath': sdi_rel,
                        'sha256': artifact['sha256'],
                        'size_bytes': artifact['size_bytes'],
                    },
                    'sdi_metadata': parsed_sdi,
                    'source_ibd': current_fps['ibd'],
                    'offline_verification': offline_now,
                    'tool': current_tool,
                    'provenance': intent['provenance'],
                    'cleanup_confirmed': cleanup_confirmed,
                    'observed_at': datetime.now(timezone.utc).isoformat(),
                }

        return {
            'accepted': True,
            'commit_requested': False,
            'rollback_requested': False,
            'native_implicit_commit': False,
            'staged_in_provider_session': False,
            'automatic_retry': False,
            'transaction_finality_interpreted_by_common_code': False,
            'native_dispatched': dispatched,
            'native_acknowledged': acknowledged,
            'mysql_utility': utility_result,
        }
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            f'MySQL native utility failed ({type(error).__name__}: {error})'
        )
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.cleanup_confirmed = cleanup_confirmed
        failure.automatic_retry = False
        raise failure from None
    finally:
        _release_ssh_secrets(ssh_lease_id)
        if session is not None:
            session.close()
