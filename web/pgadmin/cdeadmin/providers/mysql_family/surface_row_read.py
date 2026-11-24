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


def _enrich_mysql_family_comments(handle, payload, page):
    if not isinstance(page, dict) or not page.get('columns') or payload.get('continuation'):
        return
    target = payload.get('target_resource')
    if not isinstance(target, dict):
        return
    disp_path = list(target.get('display_path') or ())
    auth_path = list(target.get('authority_path') or ())
    table_name = str(target.get('display_name') or target.get('name') or (disp_path[-1] if disp_path else ''))
    schema_name = str(
        disp_path[-2]
        if len(disp_path) >= 2
        else (auth_path[-3] if len(auth_path) >= 3 else '')
    )
    if not table_name or not hasattr(handle, 'cursor'):
        return
    try:
        cur = handle.cursor()
        try:
            if not schema_name:
                cur.execute('SELECT DATABASE()')
                db_row = cur.fetchone()
                schema_name = str(db_row[0] or '') if db_row else ''
            if not schema_name:
                return
            cur.execute(
                "SELECT LEFT(COALESCE(TABLE_COMMENT, ''), 128) "
                'FROM information_schema.TABLES WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
                (schema_name, table_name),
            )
            t_row = cur.fetchone()
            if t_row and t_row[0]:
                page['table_comment'] = str(t_row[0])[:128]
            cur.execute(
                "SELECT COLUMN_NAME, LEFT(COALESCE(COLUMN_COMMENT, ''), 128) "
                'FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s',
                (schema_name, table_name),
            )
            col_comments = {
                str(r[0]): str(r[1])[:128]
                for r in (cur.fetchall() or ())
                if r and r[0] and r[1]
            }
            for col in page.get('columns', []):
                cname = col.get('name')
                if cname in col_comments and not col.get('comment'):
                    col['comment'] = col_comments[cname]
        finally:
            cur.close()
    except Exception:
        pass


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
            _enrich_mysql_family_comments(context['session_handle'], payload, page)
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
