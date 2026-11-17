"""Native MariaDB SHUTDOWN, separating acknowledgement from process exit."""
from collections.abc import Mapping
from copy import deepcopy
from datetime import datetime, timezone
import time

from ...sdk import RelationalClientError
from .mariadb_server_diagnostics import target_uid, environment, form as diagnostic_form
from .mysql_engine_diagnostics import observer_route, release

OPERATIONS = {'shutdown_server': ('Shut down server', 'SHUTDOWN')}
KEY = 'mariadb_shutdown'


def form(operation):
    return diagnostic_form(operation)


def compile_operation(operation, draft, target):
    if operation not in OPERATIONS or not isinstance(draft, Mapping):
        raise RelationalClientError('Select native MariaDB shutdown')
    uid = target_uid(target)
    if set(draft) != {'service_disruption_confirmed', 'confirmation'}:
        raise RelationalClientError('Confirm only the typed native shutdown fields')
    if draft['service_disruption_confirmed'] is not True or draft['confirmation'] != target['display_name']:
        raise RelationalClientError('Confirm service interruption and the exact native server')
    return {'statements': [{'source': 'SHUTDOWN', 'parameters': ()}],
        KEY: {'operation': operation, 'draft': deepcopy(dict(draft)), 'target': deepcopy(dict(target)), 'server_uid': uid},
        'warnings': [
            'SHUTDOWN interrupts this server and all its clients. Native SHUTDOWN privilege is required; embedded shutdown is unsupported.',
            'A dedicated connection issues one native SHUTDOWN. There is no automatic reconnect, retry, host service action or restart.',
            'The review expires after 60 seconds and compares native uptime progression. This is an observation fence, not an atomic process-generation reservation.',
            'A native OK acknowledges the shutdown request only. Connection closure and independently observed process exit are separate outcomes. Process exit is not inferred from an unreachable socket.',
            'Other sessions own their transactions; this operation does not report committing or rolling back their work.',
        ]}


def uptime(cursor):
    cursor.execute("SHOW GLOBAL STATUS LIKE 'Uptime'")
    rows = cursor.fetchmany(2)
    if len(rows) != 1 or rows[0][0] != 'Uptime' or not str(rows[0][1]).isdecimal():
        raise RelationalClientError('Native server uptime is unavailable for shutdown review')
    return int(rows[0][1])


def bind_review(client, planned):
    payload = planned['provider_payload']; intent = payload['compiled'][KEY]
    handle = client._connect({'route': observer_route(payload)}); cursor = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); identity = environment(cursor)
        if identity['server_uid'] != intent['server_uid']:
            raise RelationalClientError('The native shutdown server differs from the selected target')
        review = {'execution_identity': identity, 'uptime_seconds': uptime(cursor), 'review_clock': time.monotonic()}
        intent['review'] = review
        planned['command_preview'].update(native_execution_identity=identity,
            native_uptime_seconds=review['uptime_seconds'], review_expires_in_seconds=60)
        return planned
    finally:
        if not release(client, handle, cursor)['connection_released']:
            raise RelationalClientError('Shutdown review connection release is unconfirmed')


def apply(client, request, connection=None):
    if connection is not None:
        raise RelationalClientError('Shutdown requires an independently owned native connection')
    payload = request['provider_payload']; compiled = payload['compiled']; intent = compiled[KEY]
    checked = deepcopy(compiled); review = checked[KEY].pop('review', None)
    if not isinstance(review, Mapping) or compile_operation(intent['operation'], intent['draft'], intent['target']) != checked:
        raise RelationalClientError('Review the exact native shutdown before dispatch')
    age = time.monotonic() - review['review_clock']
    if not 0 <= age <= 60:
        raise RelationalClientError('Native shutdown review expired; review the server again')
    handle = client._connect({'route': observer_route(payload)}); cursor = None
    dispatched = acknowledged = False; result = failure = None
    try:
        handle.autocommit = True; cursor = handle.cursor(); identity = environment(cursor)
        observed_uptime = uptime(cursor)
        age = time.monotonic() - review['review_clock']
        if (identity != review['execution_identity'] or not 0 <= age <= 60
                or abs(observed_uptime - review['uptime_seconds'] - age) > 2):
            raise RelationalClientError('Native shutdown identity or uptime changed after review')
        dispatched = True; cursor.execute('SHUTDOWN')
        acknowledged = True
        result = dict(accepted=True, commit_requested=False, rollback_requested=False,
            native_implicit_commit=False, staged_in_provider_session=False, automatic_retry=False,
            transaction_finality_interpreted_by_common_code=False,
            shutdown=dict(native_dispatched=True, native_acknowledged=True,
                native_completion='shutdown-request-acknowledged', process_exit='not-observed',
                host_service_control=False, restart_requested=False, execution_identity=identity,
                atomic_process_generation_reservation=False, observed_at=datetime.now(timezone.utc).isoformat()))
        return result
    except Exception as error:
        failure = error if isinstance(error, RelationalClientError) else RelationalClientError(
            'Native MariaDB shutdown failed (' + type(error).__name__ + ')')
        failure.errno = getattr(error, 'errno', None); failure.sqlstate = getattr(error, 'sqlstate', None)
        failure.native_dispatched = dispatched; failure.native_acknowledged = acknowledged
        failure.automatic_retry = False
        failure.process_exit = 'not-observed'
        failure.native_completion = 'unconfirmed-after-dispatch' if dispatched and failure.errno not in (1045, 1227) else 'refused'
        failure.native_status_codes = (failure.errno,) if type(failure.errno) is int else ()
        raise failure from None
    finally:
        cleanup = release(client, handle, cursor)
        if result is not None: result['connection_release'] = cleanup
        elif failure is not None: failure.connection_release = cleanup
