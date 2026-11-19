"""Own a retained MySQL-family row read while its native cancel is armed."""
from contextlib import contextmanager, nullcontext

from ...sdk import RelationalClientError


@contextmanager
def _borrow(client, handle, execution):
    owner = client._executions
    key = id(handle)
    with owner.lock:
        owner.require_idle(handle)
        client._require_usable_session(handle)
        if owner.closing or key not in client._session_requests:
            raise RelationalClientError('Native row-read session is unavailable')
        if execution is not None:
            identity = owner.sessions.get(handle)
            route_request = client._session_requests[key]
        owner.grid_reads.add(key)
    try:
        scope = execution.cancellable_row_read(
            lambda: owner.kill_query(handle, route_request, identity)
        ) if execution is not None else nullcontext()
        with scope:
            yield
    except Exception:
        with owner.lock:
            owner.sessions.status_unknown.add(key)
        raise
    finally:
        with owner.lock:
            owner.grid_reads.discard(key)


def read(provider, request, fallback):
    if not isinstance(request, dict) or not request.get('session_id'):
        return fallback(request)
    payload = dict(request)
    execution = payload.pop('_row_read_execution', None)
    context = provider._visual_admin_session_context(payload)
    if execution is not None:
        context['_row_read_checkpoint'] = execution.check_stop
    with _borrow(provider.client, context['session_handle'], execution):
        try:
            page = provider._visual_admin.read_rows(payload, context)
            if execution is not None:
                execution.check_stop()
            return page
        except Exception:
            if execution is not None:
                try:
                    execution.check_stop()
                except RuntimeError:
                    provider.client._administration().invalidate_row_session(context['session_id'])
                    provider._visual_admin.invalidate_session_plans(context['session_id'])
                    raise
            raise
