"""Native event commit/rollback, reconnect and release qualification."""
import time
import uuid


def qualify(connection, client, route, *, disconnect=False):
    from pgadmin.cdeadmin.providers.firebird.events import EventSubscriptions
    events = EventSubscriptions()
    event = 'SR_EVENT_' + uuid.uuid4().hex[:12]
    opened = []
    def connect():
        handle = client.open_session({'route': route})
        opened.append(handle)
        return handle
    def await_state(identity, predicate, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = events.action('owner', 'route', identity)
            if predicate(value): return value
            if value['state'] in {'failed', 'cleanup-unknown'}:
                raise AssertionError(value)
            time.sleep(.05)
        raise AssertionError('Event observation timed out: ' + str(value))
    identity = events.start('owner', 'route', [event], connect, client.close_session)['subscription_id']
    try:
        await_state(identity, lambda item: item['state'] == 'listening')
        with connection.cursor() as cursor:
            cursor.execute("EXECUTE BLOCK AS BEGIN POST_EVENT '" + event + "'; END")
        connection.rollback()
        time.sleep(.4)
        assert events.action('owner', 'route', identity)['counts'][event] == '0'
        with connection.cursor() as cursor:
            cursor.execute("EXECUTE BLOCK AS BEGIN POST_EVENT '" + event + "'; POST_EVENT '" + event + "'; END")
        connection.commit()
        observed = await_state(identity, lambda item: int(item['counts'][event]) >= 2)
        assert observed['counts'][event] == '2'
        assert not opened[0].main_transaction.is_active(), 'Monitor retained an MGA snapshot'
    finally:
        stopped = events.action('owner', 'route', identity, stop=True)
        assert stopped['cleanup_confirmed'], stopped
    second = events.start('owner', 'route', [event], connect, client.close_session)['subscription_id']
    try:
        fresh = await_state(second, lambda item: item['state'] == 'listening')
        assert fresh['counts'][event] == '0' and second != identity
        with events.items[second].lock:
            events.items[second].lease = time.monotonic() - 121
        assert events.items[second].done.wait(5)
        expired = events.items[second].snapshot()
        assert expired['state'] == 'expired' and expired['cleanup_confirmed']
    finally:
        events.action('owner', 'route', second, stop=True)
    failure = None
    if disconnect:
        third = events.start('owner', 'route', [event], connect, client.close_session)['subscription_id']
        try:
            await_state(third, lambda item: item['state'] == 'listening')
            attachment_id = opened[-1].info.id
            with connection.cursor() as cursor:
                cursor.execute('DELETE FROM MON$ATTACHMENTS WHERE MON$ATTACHMENT_ID = ?', (attachment_id,))
            connection.commit()
            assert events.items[third].done.wait(20), 'Disconnected monitor did not finish'
            failure = events.action('owner', 'route', third)
            assert failure['delivery_gap'] and failure['state'] in {'failed', 'cleanup-unknown'}, failure
            assert failure['counts'][event] == '0'
        finally:
            events.action('owner', 'route', third, stop=True)
    events.close()
    return {'passed': True,
            'disconnect': failure, 'committed_event_count': '2', 'rollback_not_delivered': True,
            'reconnect_new_interval': True, 'idle_expiry_released': True,
            'no_retained_monitor_transaction': True, 'stop_released': True}
