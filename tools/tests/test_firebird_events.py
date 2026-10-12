import config  # Initialize application configuration before ORM imports.
import time
from unittest.mock import Mock, patch
import pytest
from pgadmin.cdeadmin.providers.firebird.events import EventSubscriptions, Subscription, names


@pytest.mark.parametrize('value', [[], ['a', 'a'], [''], ['\0'], ['a'*128], ['x']*16, 'name'])
def test_invalid_event_names(value):
    with pytest.raises(ValueError): names(value)


def test_counter_strings_keep_precision_and_scope_is_enforced():
    registry = EventSubscriptions()
    item = Subscription('owner', 'route', ('name',), counts={'name': 9007199254740993})
    registry.items[item.identity] = item
    assert registry.action('owner', 'route', item.identity)['counts']['name'] == '9007199254740993'
    for owner, binding in [('other', 'route'), ('owner', 'other')]:
        with pytest.raises(ValueError): registry.action(owner, binding, item.identity)


def test_native_failure_and_uncertain_cleanup_are_not_success():
    registry = EventSubscriptions()
    item = Subscription('owner', 'route', ('name',), counts={'name': 0})
    connection = Mock()
    connection.event_collector.return_value.begin.side_effect = RuntimeError('private native message')
    close = Mock(side_effect=RuntimeError('private cleanup message'))
    registry._run(item, lambda: connection, close)
    result = item.snapshot()
    assert result['state'] == 'cleanup-unknown' and result['delivery_gap']
    assert result['cleanup_confirmed'] is False and result['error_type'] == 'RuntimeError'
    assert 'private' not in str(result)
    close.assert_called_once_with(connection)


def test_expiry_releases_collector_and_attachment_without_user_transaction():
    registry = EventSubscriptions()
    item = Subscription('owner', 'route', ('name',), counts={'name': 0}, lease=time.monotonic()-121)
    connection = Mock(); close = Mock()
    with patch('pgadmin.cdeadmin.providers.firebird.events.heartbeat') as heartbeat:
        registry._run(item, lambda: connection, close)
    assert item.snapshot()['state'] == 'expired'
    assert item.cleanup_confirmed and item.gap
    heartbeat.assert_called_once_with(connection)
    connection.commit.assert_not_called(); connection.rollback.assert_not_called()
    connection.event_collector.return_value.close.assert_called_once()
    close.assert_called_once_with(connection)


def test_failed_open_has_no_fabricated_cleanup_and_shutdown_refuses_new_work():
    registry = EventSubscriptions()
    item = Subscription('owner', 'route', ('name',), counts={'name': 0})
    registry._run(item, Mock(side_effect=RuntimeError('unknown attach outcome')), Mock())
    assert item.state == 'cleanup-unknown' and not item.cleanup_confirmed
    registry.close()
    with pytest.raises(ValueError, match='shutting down'):
        registry.start('owner', 'route', ['EV'], Mock(), Mock())


def test_authentication_occurs_in_calling_context_before_worker_handoff():
    import threading
    registry = EventSubscriptions()
    caller = threading.get_ident()
    connection = Mock()
    observed = []
    def connect():
        observed.append(threading.get_ident())
        return connection
    with patch.object(registry, '_run') as worker:
        response = registry.start('owner', 'route', ['EV'], connect, Mock())
        deadline = time.monotonic() + 2
        while not worker.called and time.monotonic() < deadline:
            time.sleep(.01)
    assert observed == [caller]
    assert worker.call_args.args[1]() is connection
    registry.items[response['subscription_id']].done.set()
