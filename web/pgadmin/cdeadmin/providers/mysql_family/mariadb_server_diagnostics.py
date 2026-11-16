"""Reviewed MariaDB native diagnostics on independently owned connections."""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import json
import re

from ...sdk import RelationalClientError
from .mysql_engine_diagnostics import engine_state, bounded_result, observer_route, release

OPERATIONS = {
    'inspect_engine_status': ('Inspect engine status', 'STATUS'),
    'inspect_engine_logs': ('Inspect engine logs', 'LOGS'),
    'inspect_engine_mutex': ('Inspect engine mutex diagnostics', 'MUTEX'),
}
KEY = 'mariadb_server_diagnostic'


def target_uid(target):
    if not isinstance(target, Mapping) or target.get('resource_kind') != 'server':
        raise RelationalClientError('Select an observed native MariaDB server')
    native = target.get('native')
    if native is None:
        extensions = target.get('extensions')
        engine = extensions.get('mariadb') if isinstance(extensions, Mapping) else None
        native = engine.get('native') if isinstance(engine, Mapping) else None
    if not isinstance(native, Mapping):
        raise RelationalClientError('Observe the native MariaDB server_uid before review')
    uid = native.get('server_uid')
    if not isinstance(uid, str) or not re.fullmatch(r'[A-Za-z0-9+/]{27}=', uid):
        raise RelationalClientError('Observe the native MariaDB server_uid before review')
    plain = (target.get('resource_id') == 'server:MariaDB' and target.get('display_path') == ['MariaDB']
             and target.get('display_name') == 'MariaDB')
    exchanged = (target.get('resource_id') == 'mariadb-server:' + json.dumps([uid, 'server'], separators=(',', ':'))
                 and target.get('display_path') == [uid] and target.get('display_name') == 'MariaDB ' + uid)
    if not plain and not exchanged:
        raise RelationalClientError('The native MariaDB server address differs')
    return uid


def environment(cursor):
    cursor.execute('SELECT VERSION(),@@server_uid,CURRENT_USER(),USER(),CURRENT_ROLE(),@@sql_mode')
    row = cursor.fetchone()
    if row is None or str(row[0]).split('-')[0] != '12.2.2':
        raise RelationalClientError('The native MariaDB12.2.2 reference interface is required')
    return dict(zip(('version', 'server_uid', 'effective_principal', 'authenticated_session', 'active_role', 'sql_mode'), row))


def form(operation):
    from ...ui_descriptors import UIDescriptorService
    from .descriptor_contracts import field_contract
    row = next(value for value in UIDescriptorService().engine('mariadb')['operations']
               if value['operation_id'] == operation and value['resource_kind'] == 'server')
    return {'form_id': 'mariadb.server.' + operation, 'title': row['title'],
            'fields': [field_contract(value) for value in row['fields']]}


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a typed native MariaDB diagnostic')
    uid = target_uid(target)
    if set(draft) - {'engine', 'engine_scope', 'private_data_confirmed', 'confirmation'}:
        raise RelationalClientError('Select only typed native engine diagnostic fields')
    if draft.get('private_data_confirmed') is not True or draft.get('confirmation') != target['display_name']:
        raise RelationalClientError('Confirm private diagnostic access and the exact native server')
    scope = draft.get('engine_scope', 'ENGINE')
    name = draft.get('engine')
    if scope == 'ALL':
        if name not in (None, ''):
            raise RelationalClientError('Omit the engine name for native ALL scope')
        selection = 'ALL'
    elif scope == 'ENGINE':
        if not isinstance(name, str) or not name or len(name) > 64 or '\0' in name:
            raise RelationalClientError('Select one installed native storage engine')
        selection = '`' + name.replace('`', '``') + '`'
    else:
        raise RelationalClientError('Select native ENGINE or ALL scope')
    return {'statements': [{'source': 'SHOW ENGINE ' + selection + ' ' + OPERATIONS[operation][1], 'parameters': ()}],
        KEY: {'operation': operation, 'draft': deepcopy(dict(draft)), 'target': deepcopy(dict(target)),
              'server_uid': uid, 'engine_scope': scope},
        'warnings': [
            'Private native diagnostics can include other sessions SQL, transaction details and server paths.',
            'Native PROCESS authority applies to STATUS/MUTEX; FILE authority applies to LOGS. Current native privileges remain authoritative.',
            'This owns a fresh observer connection. It does not inspect or change original-session transaction/diagnostic state or write monitoring history.',
            'Single-engine output is bounded to 256 rows/1 MiB; ALL output to 4096 rows/8 MiB. Empty native output does not prove a handler is implemented.',
            'No automatic reconnect/replay. Native acknowledgement, complete output and connection release are separate observations.',
        ]}


def bind_review(client, planned):
    payload = planned['provider_payload']
    intent = payload['compiled'][KEY]
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        observed = environment(cursor)
        if observed['server_uid'] != intent['server_uid']:
            raise RelationalClientError('The native MariaDB server differs from the selected target')
        selected = engine_state(cursor, intent['draft'].get('engine'), intent['engine_scope'])
        intent['review'] = {'execution_identity': observed, 'engine': selected}
        planned['command_preview'].update(native_execution_identity=observed, native_engine=selected)
        return planned
    finally:
        cleanup = release(client, handle, cursor)
        if not cleanup['connection_released']:
            raise RelationalClientError('Native diagnostic review connection release is unconfirmed')


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Native MariaDB diagnostics require a dedicated observer')
    payload = request['provider_payload']
    compiled = payload['compiled']
    intent = compiled[KEY]
    checked = deepcopy(compiled)
    review = checked[KEY].pop('review', None)
    if not isinstance(review, Mapping) or compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Review the exact native MariaDB diagnostic before dispatch')
    handle = client._connect({'route': observer_route(payload)})
    cursor = None
    dispatched = acknowledged = False
    result = failure = None
    try:
        handle.autocommit = True
        cursor = handle.cursor()
        identity = environment(cursor)
        selected = engine_state(cursor, intent['draft'].get('engine'), intent['engine_scope'])
        if identity != review['execution_identity'] or selected != review['engine']:
            raise RelationalClientError('Native MariaDB server, principal, role or engine changed after review')
        dispatched = True
        cursor.execute(compiled['statements'][0]['source'])
        rows = bounded_result(cursor, intent['engine_scope'] == 'ALL')
        acknowledged = rows['complete']
        result = {'accepted': True, 'commit_requested': False, 'rollback_requested': False,
            'native_implicit_commit': False, 'staged_in_provider_session': False, 'automatic_retry': False,
            'transaction_finality_interpreted_by_common_code': False,
            'engine_diagnostic': {**rows, 'operation': intent['operation'], 'engine': selected,
                'execution_identity': identity, 'native_dispatched': True, 'native_acknowledged': acknowledged,
                'native_completion': 'acknowledged' if acknowledged else 'unconfirmed-output-truncated',
                'connection': 'dedicated-observer', 'private_content': True,
                'observed_at': datetime.now(timezone.utc).isoformat()}}
        return result
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            'Native MariaDB engine diagnostic failed (' + type(error).__name__ + ')')
        failure.native_dispatched = dispatched
        failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        failure.errno = getattr(error, 'errno', None)
        failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        cleanup = release(client, handle, cursor)
        if result is not None:
            result['connection_release'] = cleanup
        elif failure is not None:
            failure.connection_release = cleanup
