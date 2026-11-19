"""Reviewed Firebird 5.0.4 native plugin and external-engine (UDR) deployment.

Inspects installed binaries in plugins/ and plugins/udr/, verifies ELF64
architecture and Firebird entrypoint symbols (firebird_plugin / firebird_udr_plugin),
enforces OS and debug/sample classifications, and stages/removes source-available
plugins and UDR modules without emulating missing closed-source plugins.
"""
from collections.abc import Mapping
import hashlib
import os
from pathlib import Path
import re
import stat
import struct
import sys

from ...operations.fileio import exclusive_file_lock
from .host_runtime_grant import file_sha256, verify_same_host

CORE_PROTECTED_MODULES = frozenset({
    'Engine13', 'Srp', 'Legacy_Auth', 'Legacy_UserManager',
    'ChaCha', 'Default_Profiler', 'fbtrace', 'udr_engine',
})
CORE_PROTECTED_UDR = frozenset({'udf_compat'})
NON_PRODUCTION_MODULES = frozenset({
    'Auth_Debug', 'fbSampleDbCrypt', 'fbSampleKeyHolder', 'udrcpp_example',
})
_MODULE_NAME_RE = re.compile(r'^[A-Za-z0-9_\-]{1,64}$')
_ALIAS_NAME_RE = re.compile(r'^[A-Za-z0-9_.\-\u0080-\uffff]{1,64}$')


def descriptor():
    return {
        'schema': 'scratchrobin.firebird.plugin-deployment-api@1',
        'engine_version': '5.0.4',
        'supported_platforms': ['linux'],
        'requires_permissions': ['administer', 'maintenance_admin'],
        'actions': ['describe', 'inspect', 'review', 'apply', 'get', 'list'],
        'operations': [
            'deploy_udr_module', 'remove_udr_module',
            'deploy_plugin', 'remove_plugin',
        ],
        'platform_constraints': {
            'Win_Sspi': {
                'supported_on_host': sys.platform == 'win32',
                'reason': 'Windows SSPI authentication plugin requires a Windows host; never transferred from Linux.',
            },
            'Auth_Debug': {
                'production_admitted': False,
                'reason': 'Debug authentication plugin is non-production only.',
            },
            'sample_crypt_plugins': {
                'production_admitted': False,
                'reason': 'fbSampleDbCrypt and fbSampleKeyHolder are non-secure Firebird SDK examples.',
            },
        },
        'closed_source_emulation': False,
    }


def inspect_elf_shared_object(path):
    """Verify Linux ELF64 shared object header and extract exported dynamic symbols."""
    target = Path(path)
    if target.is_symlink() or not target.is_file():
        return {'valid_elf_dso': False, 'reason': 'Not a regular non-symlink file'}
    raw = target.read_bytes()
    if len(raw) < 64 or raw[:4] != b'\x7fELF':
        return {'valid_elf_dso': False, 'reason': 'Missing ELF magic header'}
    ei_class, ei_data = raw[4], raw[5]
    if ei_class != 2 or ei_data != 1:
        return {'valid_elf_dso': False, 'reason': 'Expected 64-bit little-endian ELF'}
    e_type, e_machine = struct.unpack_from('<HH', raw, 16)
    e_shoff = struct.unpack_from('<Q', raw, 40)[0]
    e_shentsize, e_shnum = struct.unpack_from('<HH', raw, 58)
    expected_machine = 62 if os.uname().machine == 'x86_64' else (183 if os.uname().machine == 'aarch64' else e_machine)
    if e_type != 3:
        return {'valid_elf_dso': False, 'reason': f'ELF e_type={e_type} is not ET_DYN shared object'}
    if e_machine != expected_machine:
        return {
            'valid_elf_dso': False,
            'reason': f'ELF architecture mismatch (e_machine={e_machine}, expected={expected_machine})',
        }

    exported = set()
    if e_shoff and e_shentsize >= 64 and e_shoff + e_shentsize * e_shnum <= len(raw):
        sections = []
        for idx in range(e_shnum):
            base = e_shoff + idx * e_shentsize
            sh_type, _flags, _addr, sh_offset, sh_size, sh_link, _info, _align, sh_entsize = (
                struct.unpack_from('<IQQQQIIQQ', raw, base + 4)
            )
            sections.append((sh_type, sh_offset, sh_size, sh_link, sh_entsize))
        for sh_type, sh_offset, sh_size, sh_link, sh_entsize in sections:
            # SHT_DYNSYM == 11
            if sh_type == 11 and sh_entsize >= 24 and 0 <= sh_link < len(sections):
                str_type, str_off, str_size, _, _ = sections[sh_link]
                if str_type == 3 and str_off + str_size <= len(raw) and sh_offset + sh_size <= len(raw):
                    dynstr = raw[str_off:str_off + str_size]
                    count = sh_size // sh_entsize
                    for sidx in range(count):
                        sbase = sh_offset + sidx * sh_entsize
                        st_name, st_info, _other, st_shndx = struct.unpack_from('<IBBH', raw, sbase)
                        bind = st_info >> 4
                        # STB_GLOBAL (1) or STB_WEAK (2), defined section (st_shndx != 0)
                        if st_shndx != 0 and bind in (1, 2) and st_name < len(dynstr):
                            end = dynstr.find(b'\x00', st_name)
                            if end > st_name:
                                sym = dynstr[st_name:end].decode('ascii', errors='ignore')
                                if sym in {'firebird_plugin', 'firebird_udr_plugin'}:
                                    exported.add(sym)

    return {
        'valid_elf_dso': True,
        'architecture': os.uname().machine,
        'size_bytes': len(raw),
        'sha256': hashlib.sha256(raw).hexdigest(),
        'exports_firebird_plugin': 'firebird_plugin' in exported,
        'exports_firebird_udr_plugin': 'firebird_udr_plugin' in exported,
    }


def _scan_so_directory(directory, kind):
    base = Path(directory)
    items = []
    if not base.is_dir():
        return items
    for entry in sorted(base.iterdir(), key=lambda p: p.name):
        if entry.is_dir() or not entry.name.endswith('.so'):
            continue
        mod_name = entry.name[3:-3] if entry.name.startswith('lib') else entry.name[:-3]
        elf = inspect_elf_shared_object(entry)
        classification = (
            'core_protected' if (
                mod_name in CORE_PROTECTED_MODULES or (kind == 'udr' and mod_name in CORE_PROTECTED_UDR)
            ) else 'debug_or_sample_non_production' if mod_name in NON_PRODUCTION_MODULES
            else 'deployed_extension'
        )
        items.append({
            'filename': entry.name,
            'module_name': mod_name,
            'kind': kind,
            'classification': classification,
            'production_safe': mod_name not in NON_PRODUCTION_MODULES,
            **elf,
        })
    return items


def _query_udr_dependents(client, route):
    if client is None or route is None or not route.get('database'):
        return None
    conn = client._connect({'route': route})
    try:
        cur = conn.cursor()
        try:
            dependents = []
            for kind, sql in (
                ('function', "SELECT TRIM(TRAILING FROM RDB$FUNCTION_NAME), TRIM(TRAILING FROM RDB$ENTRYPOINT) FROM RDB$FUNCTIONS WHERE TRIM(TRAILING FROM RDB$ENGINE_NAME) = 'UDR' AND COALESCE(RDB$SYSTEM_FLAG, 0) = 0"),
                ('procedure', "SELECT TRIM(TRAILING FROM RDB$PROCEDURE_NAME), TRIM(TRAILING FROM RDB$ENTRYPOINT) FROM RDB$PROCEDURES WHERE TRIM(TRAILING FROM RDB$ENGINE_NAME) = 'UDR' AND COALESCE(RDB$SYSTEM_FLAG, 0) = 0"),
                ('trigger', "SELECT TRIM(TRAILING FROM RDB$TRIGGER_NAME), TRIM(TRAILING FROM RDB$ENTRYPOINT) FROM RDB$TRIGGERS WHERE TRIM(TRAILING FROM RDB$ENGINE_NAME) = 'UDR' AND COALESCE(RDB$SYSTEM_FLAG, 0) = 0"),
            ):
                cur.execute(sql)
                for obj_name, entrypoint in cur.fetchall():
                    ep = str(entrypoint or '').strip()
                    module_part = ep.split('!', 1)[0].strip() if '!' in ep else ep
                    dependents.append({
                        'object_kind': kind,
                        'object_name': obj_name,
                        'entrypoint': ep,
                        'udr_module': module_part,
                    })
            return dependents
        finally:
            cur.close()
            conn.rollback()
    finally:
        client._forget_and_close(conn)


def inspect_plugin_environment(host_scope, client=None, route=None):
    rt = Path(host_scope['firebird_runtime_root'])
    plugins_dir = rt / 'plugins'
    udr_dir = plugins_dir / 'udr'
    core_plugins = _scan_so_directory(plugins_dir, 'plugin')
    udr_modules = _scan_so_directory(udr_dir, 'udr')
    installed_udr_names = {m['module_name'] for m in udr_modules if m.get('valid_elf_dso')}

    plugins_conf = rt / 'plugins.conf'
    udr_conf = plugins_dir / 'udr_engine.conf'
    dependents = []
    if client is not None and route is not None:
        try:
            dependents = _query_udr_dependents(client, route) or []
            for dep in dependents:
                dep['module_binary_installed'] = dep['udr_module'] in installed_udr_names
        except Exception:
            dependents = []

    return {
        'schema': 'scratchrobin.firebird.plugin-inventory@1',
        'runtime_root': str(rt),
        'platform': sys.platform,
        'staging_directory': host_scope.get('staging_directory'),
        'plugins_conf_sha256': file_sha256(plugins_conf) if plugins_conf.is_file() else '',
        'udr_engine_conf_present': udr_conf.is_file(),
        'plugins': core_plugins,
        'udr_modules': udr_modules,
        'database_udr_dependents': dependents,
        'unavailable_platform_plugins': [
            {
                'plugin_name': 'Win_Sspi',
                'installed': False,
                'supported_on_current_os': False,
                'reason': 'Windows SSPI plugin is unavailable on Linux.',
            },
        ] if sys.platform != 'win32' else [],
    }


def _resolve_staged_file(staging_dir, filename, expected_sha256):
    if not staging_dir:
        raise ValueError('No admitted staging_directory is configured for plugin/UDR deployment')
    if not isinstance(filename, str) or '/' in filename or '\\' in filename or '..' in filename:
        raise ValueError('Staged filename must be a plain basename inside staging_directory')
    sroot = Path(staging_dir).resolve(strict=True)
    candidate = sroot / filename
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f'Staged artifact {filename!r} is missing or is a symlink')
    actual_sha = file_sha256(candidate)
    if not isinstance(expected_sha256, str) or actual_sha != expected_sha256.lower():
        raise ValueError('Staged artifact SHA-256 does not match expected_source_sha256')
    return candidate, actual_sha


def prepare_plugin_review(host_scope, request, client=None, route=None):
    if not isinstance(request, Mapping):
        raise ValueError('Plugin deployment request must be an object')
    operation = request.get('operation')
    if operation not in {'deploy_udr_module', 'remove_udr_module', 'deploy_plugin', 'remove_plugin'}:
        raise ValueError('Unknown plugin deployment operation')
    module_name = request.get('module_name', '')
    if not isinstance(module_name, str) or not _MODULE_NAME_RE.match(module_name):
        raise ValueError('module_name must contain 1..64 ASCII letters, digits, underscores or hyphens')

    rt = Path(host_scope['firebird_runtime_root'])
    if (rt / 'plugins').is_symlink() or ((rt / 'plugins/udr').exists() and (rt / 'plugins/udr').is_symlink()):
        raise ValueError('Runtime plugins directory cannot be a symlink when deploying or removing binaries')
    is_udr = operation.endswith('_udr_module')
    dest_dir = (rt / 'plugins/udr') if is_udr else (rt / 'plugins')
    dest_file = dest_dir / f'lib{module_name}.so'

    if operation in {'deploy_udr_module', 'deploy_plugin'}:
        if not is_udr and module_name in CORE_PROTECTED_MODULES:
            raise ValueError(f'Core Firebird plugin {module_name!r} cannot be overwritten via plugin deployment')
        if is_udr and module_name in CORE_PROTECTED_UDR:
            raise ValueError(f'Core compatibility UDR {module_name!r} cannot be overwritten')
        staged_name = request.get('staged_filename') or f'lib{module_name}.so'
        staged_path, sha = _resolve_staged_file(
            host_scope.get('staging_directory'),
            staged_name,
            request.get('expected_source_sha256', ''),
        )
        elf = inspect_elf_shared_object(staged_path)
        if not elf.get('valid_elf_dso'):
            raise ValueError('Invalid shared library: ' + elf.get('reason', 'invalid ELF'))
        req_symbol = 'exports_firebird_udr_plugin' if is_udr else 'exports_firebird_plugin'
        if not elf.get(req_symbol):
            expected_sym = 'firebird_udr_plugin' if is_udr else 'firebird_plugin'
            raise ValueError(f'Shared library does not export required symbol {expected_sym}()')
        if dest_file.exists() and request.get('replace_existing') is not True:
            raise ValueError(f'{dest_file.name} already exists; set replace_existing=true to upgrade it')

        config_staged = None
        config_sha = None
        if not is_udr and request.get('staged_config_filename'):
            cfg_path, config_sha = _resolve_staged_file(
                host_scope.get('staging_directory'),
                request['staged_config_filename'],
                request.get('expected_config_sha256', ''),
            )
            config_staged = str(cfg_path)

        plugin_alias = request.get('plugin_alias')
        if plugin_alias is not None:
            if is_udr or not isinstance(plugin_alias, str) or not _ALIAS_NAME_RE.match(plugin_alias):
                raise ValueError('plugin_alias is valid only for deploy_plugin with a safe identifier')

        return {
            'scope': host_scope,
            'operation': operation,
            'module_name': module_name,
            'staged_path': str(staged_path),
            'expected_source_sha256': sha,
            'staged_config_path': config_staged,
            'expected_config_sha256': config_sha,
            'plugin_alias': plugin_alias,
            'destination_path': str(dest_file),
            'existing_sha256': file_sha256(dest_file) if dest_file.is_file() else None,
            'non_production_warning': module_name in NON_PRODUCTION_MODULES,
        }

    # Removal operations
    if not is_udr and module_name in CORE_PROTECTED_MODULES:
        raise ValueError(f'Core Firebird plugin {module_name!r} cannot be removed')
    if is_udr and module_name in CORE_PROTECTED_UDR:
        raise ValueError(f'Core UDR module {module_name!r} cannot be removed')
    if request.get('confirmation') != module_name:
        raise ValueError('Confirm the exact module_name to remove')
    if not dest_file.is_file() or dest_file.is_symlink():
        raise ValueError(f'Installed binary {dest_file.name} was not found')
    dependents = []
    if is_udr and client is not None and route is not None:
        all_deps = _query_udr_dependents(client, route) or []
        dependents = [d for d in all_deps if d['udr_module'] == module_name]
        if dependents and request.get('force_remove_with_dependents') is not True:
            names = ', '.join(f"{d['object_kind']}:{d['object_name']}" for d in dependents)
            raise ValueError(
                f'Active SQL UDR objects depend on {module_name!r} ({names}); '
                'drop those routines first or set force_remove_with_dependents=true'
            )
    return {
        'scope': host_scope,
        'operation': operation,
        'module_name': module_name,
        'destination_path': str(dest_file),
        'expected_installed_sha256': file_sha256(dest_file),
        'remove_plugin_alias': request.get('plugin_alias'),
        'dependents_acknowledged': dependents,
    }


def apply_plugin_operation(record):
    payload = record['payload']
    host_scope = payload['scope']
    verify_same_host(host_scope)
    rt = Path(host_scope['firebird_runtime_root'])
    dest_file = Path(payload['destination_path'])
    op = payload['operation']
    lock_fd = os.open(str(rt / '.cdeadmin_plugin_deploy.lock'), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        with exclusive_file_lock(lock_fd):
            backup_dir = rt / '.cdeadmin_backups' / record['review_id']
            backup_dir.mkdir(parents=True, exist_ok=True)

            if op in {'deploy_udr_module', 'deploy_plugin'}:
                staged_path = Path(payload['staged_path'])
                if staged_path.is_symlink() or not staged_path.is_file():
                    return {'state': 'rejected', 'native_dispatched': False, 'reason': 'Staged binary disappeared'}
                if file_sha256(staged_path) != payload['expected_source_sha256']:
                    return {'state': 'rejected', 'native_dispatched': False, 'reason': 'Staged binary SHA-256 changed since review'}
                current_sha = file_sha256(dest_file) if dest_file.is_file() else None
                if current_sha != payload['existing_sha256']:
                    return {'state': 'rejected', 'native_dispatched': False, 'reason': 'Destination binary changed since review'}
                if dest_file.is_file():
                    (backup_dir / dest_file.name).write_bytes(dest_file.read_bytes())
                dest_file.parent.mkdir(parents=True, exist_ok=True)
                tmp_so = dest_file.with_suffix('.so.staging')
                tmp_so.write_bytes(staged_path.read_bytes())
                os.chmod(tmp_so, 0o755)
                os.replace(tmp_so, dest_file)

                cfg_installed = None
                if payload.get('staged_config_path'):
                    cpath = Path(payload['staged_config_path'])
                    if not cpath.is_file() or file_sha256(cpath) != payload['expected_config_sha256']:
                        return {'state': 'rejected', 'native_dispatched': False, 'reason': 'Staged plugin config changed'}
                    dest_cfg = rt / 'plugins' / f"{payload['module_name']}.conf"
                    tmp_cfg = dest_cfg.with_suffix('.conf.staging')
                    tmp_cfg.write_bytes(cpath.read_bytes())
                    os.chmod(tmp_cfg, 0o644)
                    os.replace(tmp_cfg, dest_cfg)
                    cfg_installed = str(dest_cfg)

                alias = payload.get('plugin_alias')
                if alias:
                    pconf = rt / 'plugins.conf'
                    existing_text = pconf.read_text(encoding='utf-8') if pconf.is_file() else ''
                    if pconf.is_file():
                        (backup_dir / 'plugins.conf.bak').write_bytes(pconf.read_bytes())
                    mod = payload['module_name']
                    block_lines = [
                        f'\n# ScratchRobin managed plugin {alias}',
                        f'Plugin = {alias} {{',
                        f'  RegisterName = {mod}',
                        f'  Module = $(dir_plugins)/{mod}',
                    ]
                    if cfg_installed:
                        block_lines.append(f'  ConfigFile = $(dir_plugins)/{mod}.conf')
                    block_lines.append('}\n')
                    tmp_pc = pconf.with_suffix('.conf.staging')
                    tmp_pc.write_text(existing_text + '\n'.join(block_lines), encoding='utf-8')
                    os.replace(tmp_pc, pconf)

                return {
                    'state': 'deployed',
                    'native_dispatched': True,
                    'operation': op,
                    'module_name': payload['module_name'],
                    'installed_path': str(dest_file),
                    'installed_sha256': file_sha256(dest_file),
                    'config_installed_path': cfg_installed,
                    'plugin_alias_registered': alias,
                    'restart_recommended': not op.endswith('_udr_module'),
                }

            # remove_udr_module / remove_plugin
            if not dest_file.is_file() or file_sha256(dest_file) != payload['expected_installed_sha256']:
                return {
                    'state': 'rejected',
                    'native_dispatched': False,
                    'reason': 'Installed binary changed or was already removed since review',
                }
            backup_copy = backup_dir / dest_file.name
            backup_copy.write_bytes(dest_file.read_bytes())
            os.chmod(backup_copy, 0o600)
            dest_file.unlink()
            return {
                'state': 'removed',
                'native_dispatched': True,
                'operation': op,
                'module_name': payload['module_name'],
                'removed_path': str(dest_file),
                'backup_path': str(backup_copy),
                'restart_recommended': True,
            }
    finally:
        os.close(lock_fd)
