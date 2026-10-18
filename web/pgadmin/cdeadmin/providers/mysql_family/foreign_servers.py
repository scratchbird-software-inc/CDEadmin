"""Reviewed MySQL foreign-server definitions, independent of FEDERATED loading."""
from collections.abc import Mapping
from copy import deepcopy
import json
import secrets

from ...sdk import RelationalClientError
from .spatial_reference_systems import identity, number

KIND = 'server-link'
OPERATIONS = frozenset({'create', 'alter', 'drop'})
FIELDS = ('server_name', 'host', 'db', 'username', 'port', 'socket', 'wrapper', 'owner')
SELECT = 'SELECT Server_name,Host,Db,Username,Port,Socket,Wrapper,Owner FROM mysql.servers'
OPTIONS = {'host': ('HOST', 'Host', 'host'), 'database': ('DATABASE', 'Database', 'db'),
    'username': ('USER', 'User', 'username'), 'password': ('PASSWORD', 'Password', None),
    'port': ('PORT', 'Exact native port', 'port'), 'socket': ('SOCKET', 'Socket', 'socket'),
    'owner': ('OWNER', 'Owner', 'owner')}


def text(value, label):
    if not isinstance(value, str) or '\x00' in value:
        raise RelationalClientError(label + ' requires native text without NUL')
    return value


def address(name):
    parts = [KIND, name]
    return ('mysql-resource:' + json.dumps(parts, ensure_ascii=False, separators=(',', ':'))
            if ':' in name else KIND + ':' + name)


def normalized(row):
    value = {key: row.get(key) for key in FIELDS} if isinstance(row, Mapping) else dict(zip(FIELDS, row))
    value['port'] = str(value['port'])
    return value


def native(target):
    value = (target or {}).get('native')
    if value is None:
        value = ((target or {}).get('extensions') or {}).get('mysql', {}).get('native')
    if not isinstance(value, Mapping):
        raise RelationalClientError('Native MySQL foreign-server identity is unavailable')
    if isinstance(value.get('catalog_row'), Mapping):
        value = value['catalog_row']
    return value


def compile_operation(operation, draft, target=None):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Native MySQL foreign-server operation is unavailable')
    allowed = ({'name', 'wrapper'} if operation == 'create' else {'confirmation'})
    if operation != 'drop':
        allowed |= set(OPTIONS) | {'include_' + key for key in OPTIONS}
    else:
        allowed |= {'if_exists'}
    if set(draft) - allowed:
        raise RelationalClientError('Unknown native foreign-server option')
    old = None if operation == 'create' else native(target)
    name = text(draft.get('name') if old is None else old.get('server_name'), 'Server name')
    if not name or len(name) > 64:
        raise RelationalClientError('Foreign-server names require 1 to 64 characters')
    if old is not None and ((target or {}).get('resource_kind') != KIND or
            target.get('resource_id') != address(name) or target.get('display_path') != [name] or
            target.get('display_name') != name or draft.get('confirmation') != name):
        raise RelationalClientError('Confirm the exact native foreign-server resource address')
    quoted = '`' + name.replace('`', '``') + '`'
    parameters = []
    if operation == 'drop':
        if_exists = draft.get('if_exists', False)
        if type(if_exists) is not bool:
            raise RelationalClientError('IF EXISTS must be boolean')
        source = 'DROP SERVER ' + ('IF EXISTS ' if if_exists else '') + quoted
    else:
        if operation == 'create':
            wrapper = text(draft.get('wrapper'), 'Foreign data wrapper')
            if not wrapper:
                raise RelationalClientError('Specify a native foreign data wrapper')
            source = 'CREATE SERVER ' + quoted + ' FOREIGN DATA WRAPPER %s'
            parameters.append(wrapper)
        else:
            source = 'ALTER SERVER ' + quoted
        options = []
        for key, (keyword, label, _column) in OPTIONS.items():
            selected = draft.get('include_' + key, False)
            if type(selected) is not bool:
                raise RelationalClientError('Select foreign-server options explicitly')
            if selected:
                if key == 'port':
                    # mysql.servers stores a signed INT; keep the exact value
                    # independently of browser numeric conversion.
                    options.append('PORT ' + str(number(draft.get(key), label, 2147483647)))
                else:
                    options.append(keyword + ' %s')
                    parameters.append(text(draft.get(key), label))
            elif key in draft:
                raise RelationalClientError('Select foreign-server options explicitly')
        if not options:
            raise RelationalClientError('Select at least one native foreign-server option')
        source += ' OPTIONS (' + ', '.join(options) + ')'
    return {'statements': [{'source': source, 'parameters': tuple(parameters)}],
        'mysql_foreign_server': {'operation': operation, 'name': name, 'draft': dict(draft),
            'target': deepcopy(target), 'baseline': normalized(old) if old is not None else None},
        'warnings': ['Native MySQL DDL uses an independent connection. The definition does not verify a remote connection or enable FEDERATED.']}


def form(operation, field):
    fields = []
    if operation == 'create':
        fields.extend([field('name', 'Foreign server name', 'text', True),
            field('wrapper', 'Foreign data wrapper', 'text', True, default='mysql')])
    if operation != 'drop':
        for key, (_keyword, label, column) in OPTIONS.items():
            fields.append(field('include_' + key, 'Specify ' + label.lower(), 'boolean',
                default=(operation == 'create' and key == 'host')))
            value = field(key, label, 'password' if key == 'password' else 'text',
                sensitive=key == 'password')
            value.update(visible_when={'field_id': 'include_' + key, 'equals': True}, submit_unchanged=True)
            if column and operation == 'alter':
                value['initial_value_path'] = [column]
            fields.append(value)
    if operation != 'create':
        fields.append(field('confirmation', 'Exact foreign server name', 'text', True))
    if operation == 'drop':
        fields.append(field('if_exists', 'IF EXISTS', 'boolean', default=False))
    return {'form_id': 'mysql.server-link.' + operation,
        'title': operation.title() + ' native MySQL foreign server', 'fields': fields}


def current(cursor, name):
    # Binary comparison prevents a case-insensitive comparison from selecting
    # a differently addressed dictionary row.
    cursor.execute(SELECT + ' WHERE CAST(Server_name AS BINARY)=CAST(%s AS BINARY)', (name,))
    row = cursor.fetchone()
    return normalized(row) if row else None


def credential_stamp(cursor, name, nonce):
    # A per-review nonce protects a private credential comparison. Neither the
    # password nor its digest is exposed through catalog, preview or receipt.
    cursor.execute('SELECT SHA2(CONCAT(%s,Password),256) FROM mysql.servers '
        'WHERE CAST(Server_name AS BINARY)=CAST(%s AS BINARY)', (nonce, name))
    row = cursor.fetchone()
    return row[0] if row else None


def bind_review(client, planned):
    payload = planned['provider_payload'];intent = payload['compiled']['mysql_foreign_server']
    handle = client._connect({'route': payload['route']});cursor = None
    try:
        cursor = handle.cursor()
        observed = identity(cursor)
        before = current(cursor, intent['name'])
        if before != intent['baseline']:
            raise RelationalClientError('Native foreign-server definition changed before review')
        nonce = secrets.token_hex(32)
        intent['review'] = {'execution_identity': observed, 'credential_nonce': nonce,
            'credential_stamp': credential_stamp(cursor, intent['name'], nonce)}
        planned['command_preview']['native_execution_identity'] = dict(observed)
        return planned
    finally:
        if cursor is not None:
            client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('MySQL foreign-server DDL requires an independently owned connection')
    payload = request.get('provider_payload') or {};compiled = payload['compiled']
    intent = compiled['mysql_foreign_server'];checked = deepcopy(compiled)
    review = checked['mysql_foreign_server'].pop('review', None)
    if compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Reviewed foreign-server operation changed')
    if not isinstance(review, Mapping):
        raise RelationalClientError('Review the native MySQL instance and principal before dispatch')
    handle = client._connect({'route': payload['route']});cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True;handle.raise_on_warnings = False;handle.get_warnings = True
        cursor = handle.cursor();observed = identity(cursor)
        expected_uuid = native(intent['target']).get('server_uuid') if intent['target'] else None
        if observed != review['execution_identity'] or expected_uuid is not None and observed['server_uuid'] != expected_uuid:
            raise RelationalClientError('MySQL foreign-server execution identity changed')
        before = current(cursor, intent['name'])
        if before != intent['baseline'] or credential_stamp(cursor, intent['name'], review['credential_nonce']) != review['credential_stamp']:
            raise RelationalClientError('Native foreign-server definition or credential changed since review')
        statement = compiled['statements'][0];dispatched = True
        cursor.execute(statement['source'], statement['parameters'] or None);acknowledged = True
        warnings = [{'level': level, 'code': code, 'message': message}
            for level, code, message in (cursor.warnings or ())]
        after = current(cursor, intent['name'])
        return {'accepted': True, 'commit_requested': False, 'rollback_requested': False,
            'staged_in_provider_session': False, 'native_implicit_commit': True,
            'driver_observation_only': True, 'transaction_finality_interpreted_by_common_code': False,
            'native_warnings': warnings, 'foreign_server_observation': {
                'native_acknowledged': True, 'before': before, 'after': after,
                'execution_identity': observed}, 'automatic_retry': False}
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            'Native MySQL foreign-server operation failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched;failure.native_acknowledged = acknowledged
        failure.errno = getattr(error, 'errno', None);failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        failure.automatic_retry = False
        raise failure from None
    finally:
        if cursor is not None:
            client._safe_close(cursor)
        client._forget_and_close(handle)
