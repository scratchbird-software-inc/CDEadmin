"""Native event commit/rollback, reconnect and release qualification."""
import time
import uuid


def qualify(connection, client, route):
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
    return {'passed': True, 'committed_event_count': '2', 'rollback_not_delivered': True,
            'reconnect_new_interval': True, 'idle_expiry_released': True,
            'no_retained_monitor_transaction': True, 'stop_released': True}
