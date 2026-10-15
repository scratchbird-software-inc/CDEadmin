"""Native server registrations; no remote connection or library installation."""
from ..sdk.relational import RelationalClientError
from . import mysql_program_objects
from .mysql_tablespaces import identifier

OPERATIONS = {
    'server-link': frozenset({'create', 'alter', 'drop'}),
    'loadable-function': frozenset({'create', 'drop'}),
}
OPTIONS = {
    'host': 'HOST', 'database': 'DATABASE', 'username': 'USER',
    'password': 'PASSWORD', 'port': 'PORT', 'socket': 'SOCKET', 'owner': 'OWNER',
}


def compile_operation(kind, operation, draft, target):
    if operation not in OPERATIONS.get(kind, ()) or not isinstance(draft, dict):
        raise RelationalClientError('Native MariaDB server operation is unavailable')
    if kind == 'loadable-function':
        if operation != 'create' and (target or {}).get('resource_kind') != kind:
            raise RelationalClientError('Exact native loadable function identity is required')
        native = (target or {}).get('native') or (target or {}).get(
            'extensions', {}).get('mariadb', {}).get('native', {})
        # Share only the qualified common UDF grammar, never MySQL libraries.
        return mysql_program_objects.compile_operation(kind, operation, draft,
                                                       {**(target or {}), 'native': native})
    create = operation == 'create'
    allowed = ({'name', 'wrapper'} | set(OPTIONS)) if create else {'confirmation'}
    if operation == 'alter':
        allowed |= set(OPTIONS) | {'change_' + key for key in OPTIONS}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown native MariaDB server option')
    path = [draft.get('name')] if create else (target or {}).get('display_path', [])
    if not isinstance(path, list) or len(path) != 1 or (
            not create and (target or {}).get('resource_kind') != 'server-link'):
        raise RelationalClientError('Exact native remote server identity is required')
    qualified = identifier(path[0])
    if operation == 'drop':
        return {'source': 'DROP SERVER ' + qualified, 'parameters': ()}
    values, parameters = [], []
    for key, native in OPTIONS.items():
        change = draft.get('change_' + key, False)
        if not create and type(change) is not bool:
            raise RelationalClientError('Native option selection must be Boolean')
        if not create and not change:
            continue
        value = draft.get(key, 3306 if key == 'port' else '')
        if key == 'port':
            if type(value) is not int or not 0 <= value <= 65535:
                raise RelationalClientError('Native remote port must be 0–65535')
        else:
            value = mysql_program_objects.text(value, 'Remote ' + key, 1024)
        values.append(native + ' %s')
        parameters.append(value)
    if not values:
        raise RelationalClientError('Select at least one remote server option to change')
    prefix = 'CREATE SERVER ' if create else 'ALTER SERVER '
    if create:
        prefix += qualified + ' FOREIGN DATA WRAPPER ' + identifier(draft.get('wrapper'))
    else:
        prefix += qualified
    return {'source': prefix + ' OPTIONS (' + ', '.join(values) + ')',
            'parameters': tuple(parameters)}


def form(kind, operation, field):
    if kind == 'loadable-function':
        value = mysql_program_objects.form(kind, operation, field)
        return {**value, 'form_id': 'mariadb.' + kind + '.' + operation,
                'form_key': 'mariadb-native-loadable-function-operation',
                'title': operation.title() + ' native MariaDB loadable function'}
    create = operation == 'create'
    fields = [field('name', 'Native server name', 'text', True),
              field('wrapper', 'Foreign data wrapper', 'text', True,
                    default='mysql')] if create else []
    if operation != 'drop':
        for key in OPTIONS:
            label = 'Remote ' + key
            if not create:
                fields.append(field('change_' + key, 'Change ' + label.lower(),
                                    'boolean', default=False))
            control = 'password' if key == 'password' else 'number' if key == 'port' else 'text'
            value = field(key, label, control, default=3306 if key == 'port' else '')
            if key == 'port':
                value.update(minimum=0, maximum=65535)
            if key == 'password':
                value['sensitive'] = True
            if not create:
                value['visible_when'] = {'field_id': 'change_' + key, 'equals': True}
            fields.append(value)
    if not create:
        fields.append(field('confirmation', 'Confirmation', 'text', True))
    return {'form_id': 'mariadb.server-link.' + operation,
            'form_key': 'mariadb-native-server-link-operation',
            'title': operation.title() + ' native MariaDB remote server', 'fields': fields}
