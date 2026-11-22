"""Typed constructor, ABI/runtime capability, shadow-storage and DDN reproduction adapters
for installed SQLite custom virtual modules (SQ-AUD-08).

No raw native-action or arbitrary SQL string is admitted: each supported source-available
loadable module has a typed option contract, eponymous-only table-valued functions are
explicitly distinguished from persistent CREATE VIRTUAL TABLE modules, and DDN / retained
reproduction checks live PRAGMA module_list availability and shadow storage authorizer events.
"""
from __future__ import annotations

from collections.abc import Mapping
import sqlite3

from pgadmin.cdeadmin.sdk import RelationalClientError
from .declarations import quote

# Eponymous-only modules cannot be instantiated via CREATE VIRTUAL TABLE.
EPONYMOUS_ONLY_MODULES = frozenset({
    'carray',
    'generate_series',
    'json_each',
    'json_tree',
    'pragma_module',
    'sqlite_dbpage',
    'sqlite_memstat',
    'sqlite_stmt',
    'stmt',
})

# Source-available loadable SQLite virtual modules with typed constructor contracts.
CUSTOM_CREATABLE_SPECS = {
    'csv': {
        'allowed_options': frozenset({'data', 'filename_ref', 'schema', 'columns_count', 'header', 'avin'}),
        'accepts_columns': False,
        'creates_shadow_tables': False,
        'read_only': True,
        'source_origin': 'ext/misc/csv.c',
    },
    'spellfix1': {
        'allowed_options': frozenset({'vocab_table', 'edit_cost_table', 'soundslike', 'langid'}),
        'accepts_columns': False,
        'creates_shadow_tables': True,
        'read_only': False,
        'source_origin': 'ext/misc/spellfix.c',
    },
    'fuzzer': {
        'allowed_options': frozenset({'rules_table'}),
        'accepts_columns': False,
        'creates_shadow_tables': False,
        'read_only': True,
        'source_origin': 'ext/misc/fuzzer.c',
    },
    'wholenumber': {
        'allowed_options': frozenset(),
        'accepts_columns': False,
        'creates_shadow_tables': False,
        'read_only': True,
        'source_origin': 'ext/misc/wholenumber.c',
    },
    'cde_kv_vtab': {
        'allowed_options': frozenset({'namespace_tag', 'read_only_mode', 'with_shadow'}),
        'accepts_columns': True,
        'creates_shadow_tables': True,
        'read_only': False,
        'source_origin': 'approved-native-extension:cde_kv_vtab',
    },
}


def _err(msg: str) -> None:
    raise RelationalClientError('SQLite custom virtual module: ' + msg)


def _lit(val: str) -> str:
    if not isinstance(val, str) or '\0' in val:
        _err('option text cannot contain NUL bytes')
    return "'" + val.replace("'", "''") + "'"


def _ident(val: str) -> str:
    if not isinstance(val, str) or not val or '\0' in val or len(val) > 1024:
        _err('identifier must contain 1 to 1024 non-NUL characters')
    return '"' + val.replace('"', '""') + '"'


def is_custom_creatable(module: object) -> bool:
    return isinstance(module, str) and module.lower() in CUSTOM_CREATABLE_SPECS


def is_eponymous_only(module: object) -> bool:
    return isinstance(module, str) and module.lower() in EPONYMOUS_ONLY_MODULES


def compile_custom_arguments(module: str, columns: list | None, options: Mapping) -> str:
    mod_lower = module.lower()
    if is_eponymous_only(mod_lower):
        _err(f'{module} is an eponymous-only table-valued module and does not support CREATE VIRTUAL TABLE')
    spec = CUSTOM_CREATABLE_SPECS.get(mod_lower)
    if spec is None:
        _err(f'module {module!r} has no typed native constructor adapter')
    if not isinstance(options, Mapping):
        _err('module_options must be an object')
    unknown = set(options) - spec['allowed_options']
    if unknown:
        _err(f'unknown options for {module}: ' + ', '.join(sorted(unknown)))
    cols = columns or []
    if not isinstance(cols, list):
        _err('columns must be a list')
    if cols and not spec['accepts_columns']:
        _err(f'{module} defines its own schema; leave columns empty')

    parts: list[str] = []
    if spec['accepts_columns']:
        for col in cols:
            parts.append(_ident(col))

    if mod_lower == 'csv':
        if 'filename_ref' in options:
            _err('csv filename= host path constructor is refused on shared connections; pass inline data= text')
        data = options.get('data')
        if not isinstance(data, str) or '\0' in data:
            _err('csv requires inline data string without NUL bytes')
        parts.append('data=' + _lit(data))
        if 'schema' in options:
            parts.append('schema=' + _lit(str(options['schema'])))
        if 'columns_count' in options:
            cnt = options['columns_count']
            if type(cnt) is not int or not 1 <= cnt <= 2000:
                _err('csv columns_count must be an integer between 1 and 2000')
            parts.append(f'columns={cnt}')
        if options.get('header') is True:
            parts.append('header')
    elif mod_lower == 'spellfix1':
        for key, opt_kw in (('vocab_table', 'vocab'), ('edit_cost_table', 'edit_cost_table'), ('soundslike', 'soundslike'), ('langid', 'langid')):
            if key in options:
                parts.append(f'{opt_kw}={_lit(str(options[key]))}')
    elif mod_lower == 'fuzzer':
        rules = options.get('rules_table')
        if not isinstance(rules, str) or not rules:
            _err('fuzzer requires rules_table identifier')
        parts.append(_ident(rules))
    elif mod_lower == 'cde_kv_vtab':
        if 'namespace_tag' in options:
            parts.append('namespace_tag=' + _lit(str(options['namespace_tag'])))
        if 'read_only_mode' in options:
            if not isinstance(options['read_only_mode'], bool):
                _err('read_only_mode must be boolean')
            parts.append(f'read_only_mode={1 if options["read_only_mode"] else 0}')
        if 'with_shadow' in options:
            if not isinstance(options['with_shadow'], bool):
                _err('with_shadow must be boolean')
            parts.append(f'with_shadow={1 if options["with_shadow"] else 0}')
    return ', '.join(parts)


def installed_modules(connection: sqlite3.Connection) -> set[str]:
    return {str(r[0]).lower() for r in connection.execute('PRAGMA module_list').fetchall()}


def inspect_module_capabilities(connection: sqlite3.Connection) -> dict:
    present = installed_modules(connection)
    custom = {}
    for name, spec in sorted(CUSTOM_CREATABLE_SPECS.items()):
        custom[name] = {
            'installed': name in present,
            'creatable': True,
            'eponymous_only': False,
            'read_only': spec['read_only'],
            'creates_shadow_tables': spec['creates_shadow_tables'],
            'allowed_options': sorted(spec['allowed_options']),
            'source_origin': spec['source_origin'],
        }
    eponymous = {
        name: {'installed': name in present, 'creatable': False, 'eponymous_only': True}
        for name in sorted(EPONYMOUS_ONLY_MODULES)
    }
    return {
        'installed_modules': sorted(present),
        'custom_creatable_modules': custom,
        'eponymous_only_modules': eponymous,
    }


def verify_reproducible_on_connection(connection: sqlite3.Connection, module_name: str) -> dict:
    mod_lower = module_name.lower()
    present = installed_modules(connection)
    if mod_lower not in present:
        raise ValueError(
            f'Custom virtual module {module_name!r} is not loaded in this SQLite connection; '
            'load the approved native extension before reproducing or migrating this object'
        )
    spec = CUSTOM_CREATABLE_SPECS.get(mod_lower)
    if spec is None:
        raise ValueError(
            f'Installed virtual module {module_name!r} has no atomic retained/DDN reproduction adapter'
        )
    return spec
