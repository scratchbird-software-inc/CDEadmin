"""Independent MariaDB package declaration/body lifecycle with explicit SQL mode."""
from ..sdk.relational import RelationalClientError

OPERATIONS = frozenset({'create_specification', 'replace_specification', 'create_body', 'replace_body', 'drop_body'})
TITLES = {'create_specification': 'Create package declaration', 'replace_specification': 'Replace package declaration',
    'create_body': 'Create package body', 'replace_body': 'Replace package body', 'drop_body': 'Drop package body'}


def identifier(value):
    if not isinstance(value, str) or not value or len(value) > 64 or '\x00' in value:
        raise RelationalClientError('Package/database name requires 1 to 64 characters without NUL')
    return '`' + value.replace('`', '``') + '`'


def compile_operation(operation, draft, target, safe_definition):
    if operation not in OPERATIONS or not isinstance(draft, dict):
        raise RelationalClientError('Invalid native MariaDB package operation')
    create = operation == 'create_specification'
    allowed = {'database', 'name', 'definition', 'sql_mode'} if create else {'confirmation'} | (
        set() if operation == 'drop_body' else {'definition', 'sql_mode'})
    if set(draft) - allowed:
        raise RelationalClientError('Unknown native MariaDB package option')
    path = [draft.get('database'), draft.get('name')] if create else (target or {}).get('display_path')
    if not isinstance(path, list) or len(path) != 2 or (not create and (target or {}).get('resource_kind') != 'package'):
        raise RelationalClientError('Exact native MariaDB package identity is required')
    try:
        qualified = '.'.join(identifier(part) for part in path)
    except ValueError as error:
        raise RelationalClientError(str(error)) from None
    if operation == 'drop_body':
        return [{'source': 'DROP PACKAGE BODY ' + qualified, 'parameters': ()}]
    definition = safe_definition(draft.get('definition'))
    if not definition or len(definition.encode('utf8')) > 1024 * 1024:
        raise RelationalClientError('Native package declaration/body requires text within 1 MiB')
    mode = draft.get('sql_mode', 'current' if create else 'stored')
    statements = []
    if mode == 'stored':
        native = (target or {}).get('native') or (target or {}).get('extensions', {}).get('mariadb', {}).get('native', {})
        part = 'package_body' if operation == 'replace_body' else 'package_specification'
        observations = native.get(part, {}).get('show_create', [])
        modes = {row.get('sql_mode') for row in observations if isinstance(row, dict) and isinstance(row.get('sql_mode'), str)}
        if len(modes) != 1:
            raise RelationalClientError('Stored native package SQL mode is unavailable; explicitly select current or Oracle mode')
        statements.append({'source': 'SET SESSION sql_mode=%s', 'parameters': (next(iter(modes)),)})
    elif mode == 'oracle':
        statements.append({'source': 'SET SESSION sql_mode=%s', 'parameters': ('ORACLE',)})
    elif mode != 'current':
        raise RelationalClientError('Select stored, current or Oracle package SQL mode')
    command = 'CREATE OR REPLACE' if operation.startswith('replace_') else 'CREATE'
    kind = 'PACKAGE BODY' if operation.endswith('_body') else 'PACKAGE'
    statements.append({'source': command + ' ' + kind + ' ' + qualified + ' ' + definition, 'parameters': ()})
    return statements


def form(operation, field):
    create = operation == 'create_specification'
    fields = [field('database', 'Database', 'text', True), field('name', 'Package name', 'text', True)] if create else []
    if operation != 'drop_body':
        fields += [field('sql_mode', 'Package SQL mode', 'select', True, default='current' if create else 'stored',
            options=('current', 'oracle') if create else ('stored', 'current', 'oracle')),
            field('definition', 'Declaration or body fragment', 'code', True,
                'Enter the fragment after the qualified package name, including END; native MariaDB validates grammar.')]
    if not create:fields.append(field('confirmation', 'Confirmation', 'text', True))
    return {'form_id': 'package.' + operation, 'title': TITLES[operation], 'fields': fields}
