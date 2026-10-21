"""Reviewed native SHUTDOWN/RESTART requests on independently owned handles."""
from collections.abc import Mapping
from copy import deepcopy

from ...sdk import RelationalClientError
from .mysql_instance import environment, target_uuid

OPERATIONS = {
    'shutdown_server': ('Shut down native MySQL server', 'SHUTDOWN'),
    'restart_server': ('Restart native MySQL server', 'RESTART'),
}


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select a native MySQL server control request')
    uuid = target_uuid(target)
    if (set(draft) != {'confirmation', 'disconnect_all_clients'} or
            draft.get('confirmation') != target['display_name'] or
            draft.get('disconnect_all_clients') is not True):
        raise RelationalClientError('Confirm the exact native server and disconnection of all its clients')
    return {'statements': [{'source': OPERATIONS[operation][1], 'parameters': ()}],
        'mysql_server_control': {'operation': operation, 'server_uuid': uuid,
            'draft': dict(draft), 'target': deepcopy(dict(target))},
        'warnings': ['This server-wide request disconnects clients. Native MySQL owns shutdown, rollback of unfinished transactions and subsequent recovery.',
            'RESTART requires a native service or process supervisor. MySQL decides whether this server is managed and whether the current account has SHUTDOWN authority.',
            'A native acknowledgement confirms the request only. It does not establish process termination, a new process generation or readiness. Connection loss alone is an unknown outcome; this request is never automatically replayed.',
            'SHUTDOWN does not start the server again. Use the configured database host service to start a stopped instance.']}


def form(operation, field):
    return {'form_id': 'mysql.server.'+operation, 'title': OPERATIONS[operation][0],
        'fields': [field('disconnect_all_clients', 'Disconnect all clients on this native server', 'boolean', True, default=False),
            field('confirmation', 'Exact server name', 'text', True)]}


def instance(cursor):
    cursor.execute('SELECT @@hostname,@@port,@@datadir,@@pid_file')
    row = cursor.fetchone()
    if (not row or len(row) != 4 or type(row[1]) is not int or not 1 <= row[1] <= 65535 or
            any(not isinstance(row[i], str) or not row[i] for i in (0, 2, 3))):
        raise RelationalClientError('The native MySQL instance address is unavailable')
    return dict(zip(('hostname', 'port', 'datadir', 'pid_file'), row))


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled']['mysql_server_control']
    handle = client._connect({'route': payload['route']}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); actor = environment(cursor)
        if actor['server_uuid'] != intent['server_uuid']:
            raise RelationalClientError('The selected native server differs from the control request')
        observed = instance(cursor)
        intent['review'] = {'execution_identity': actor, 'instance': observed}
        planned['command_preview'].update(native_execution_identity=actor, native_server_instance=observed,
            native_acknowledgement_scope='request_only')
        return planned
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Native server control requires an independently owned connection')
    payload = request['provider_payload']; compiled = payload['compiled']; intent = compiled['mysql_server_control']
    checked = deepcopy(compiled); review = checked['mysql_server_control'].pop('review', None)
    if not isinstance(review, Mapping) or compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Review the exact native MySQL server control request before dispatch')
    handle = client._connect({'route': payload['route']}); cursor = None
    dispatched = acknowledged = False
    try:
        handle.autocommit = True; cursor = handle.cursor(); actor = environment(cursor)
        if actor != review['execution_identity'] or instance(cursor) != review['instance']:
            raise RelationalClientError('The native server control identity changed since review')
        dispatched = True
        cursor.execute(compiled['statements'][0]['source'])
        acknowledged = True
        return {'accepted': True, 'native_implicit_commit': intent['operation'] == 'restart_server',
            'catalog_refresh_deferred': True,
            'commit_requested': False, 'rollback_requested': False, 'staged_in_provider_session': False,
            'automatic_retry': False, 'driver_observation_only': True,
            'transaction_finality_interpreted_by_common_code': False,
            'server_control_observation': {'operation': intent['operation'], 'native_acknowledged': True,
                'acknowledgement_scope': 'request_only', 'execution_identity': actor,
                'instance': review['instance'], 'server_termination_observed': False,
                'new_process_generation_observed': False, 'server_readiness_observed': False}}
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError('Native MySQL server control request failed ('+type(error).__name__+')')
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged
        failure.automatic_retry = False; failure.errno = getattr(error, 'errno', None)
        failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        if cursor is not None: client._safe_close(cursor)
        client._forget_and_close(handle)
