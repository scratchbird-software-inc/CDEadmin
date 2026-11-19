"""XA controls for retained MySQL and MariaDB editor sessions."""

from uuid import uuid4

from ...sdk import RelationalClientError
from .mysql_session_variables import invalidate
from .mysql_xa import xid_source


def describe(client, handle, observation):
    key = id(handle)
    branch = client._surface_xa.get(key)
    if branch:
        if key in client._uncertain_sessions:
            branch['state'] = 'unknown'
        observation['xa_state'] = branch['state']
        observation['prepared_transaction_id'] = branch['gid']
        if branch['state'] != 'active':
            observation['prepare_state'] = branch['state']
    return observation


def control(client, handle, action, engine):
    key = id(handle)
    branch = client._surface_xa.get(key)
    if branch and action not in {'commit', 'rollback', 'prepare'}:
        raise RelationalClientError('Resolve the managed XA transaction first')
    if action == 'prepare' and branch and branch['state'] != 'active':
        raise RelationalClientError('Only an active XA transaction can be prepared')
    if not branch and action not in {'start_xa', 'prepare'}:
        return False
    if action == 'start_xa':
        state = client._describe_idle_transaction(handle)
        if branch or state.get('in_transaction') is not False or not state.get('status_current'):
            raise RelationalClientError(f'An idle {engine} session is required to start XA')
        gid = f'scratchrobin_{uuid4().hex}'
        branch = {'gid': gid, 'state': 'starting'}
        client._surface_xa[key] = branch
    elif not branch:
        raise RelationalClientError('Start an XA transaction before preparing it')

    gid = branch['gid']
    xid = xid_source({'gtrid_hex': gid.encode('ascii').hex(), 'bqual_hex': '', 'format_id': '1'})
    cursor = None
    try:
        cursor = handle.cursor()
        if action == 'start_xa':
            cursor.execute('XA START ' + xid)
            branch['state'] = 'active'
        else:
            active = branch['state'] == 'active'
            if active:
                cursor.execute('XA END ' + xid)
            if action == 'prepare':
                cursor.execute('XA PREPARE ' + xid)
                branch['state'] = 'prepared'
            else:
                suffix = ' ONE PHASE' if active and action == 'commit' else ''
                cursor.execute(('XA COMMIT ' if action == 'commit' else 'XA ROLLBACK ') + xid + suffix)
                client._surface_xa.pop(key)
    except Exception:
        branch['state'] = 'unknown'
        client._uncertain_sessions.add(key)
        raise RelationalClientError(
            f'{engine} XA outcome is unconfirmed for {gid}; inspect prepared XA before taking further action'
        ) from None
    finally:
        if engine == 'MySQL':
            invalidate(handle)
        if cursor is not None:
            cursor.close()
    client._executions.sessions.status_unknown.discard(key)
    return True


def release(client, handle):
    key = id(handle)
    branch = client._surface_xa.get(key)
    if branch and branch['state'] != 'unknown' and key not in client._uncertain_sessions:
        raise RelationalClientError('Resolve the managed XA transaction before closing')
    client._surface_xa.pop(key, None)
