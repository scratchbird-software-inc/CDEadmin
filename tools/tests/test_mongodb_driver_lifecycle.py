"""MongoDB retained workers, exact BSON and cleanup regression checks."""
import json
import threading
import time
from types import SimpleNamespace

import pytest
import test_cdeadmin_mongodb_provider  # noqa: F401
from pgadmin.cdeadmin.providers.mongodb.driver import (
    MongoDBDriver, MongoDBDriverBackend)
from pgadmin.cdeadmin.providers.mongodb.provider import PROFILE
from pgadmin.cdeadmin.providers.native_distributed import NativeResult


class Backend:
    def __init__(self):
        self.threads = []
        self.fail_close = False

    def touch(self):
        self.threads.append(threading.get_ident())

    def open_session(self, request):
        self.touch()
        return object()

    def describe_transaction(self, handle):
        self.touch()
        return {}

    def iterate(self, handle, command, parameters):
        self.touch()
        if command.get('error'):
            raise TimeoutError('credential must not be exposed')
        yield NativeResult('document', 'documents', [{'_id': 1}], {}, {})

    def control_transaction(self, handle, action):
        self.touch()

    def close_session(self, handle, unknown):
        self.touch()
        if self.fail_close:
            raise RuntimeError('cleanup')

    def close(self):
        pass


def observe(client, token):
    for _ in range(100):
        value = client.describe_result(token)
        if value['complete']:
            return value
        time.sleep(.001)
    raise AssertionError('No terminal observation')


def test_worker_ownership_busy_and_retryable_cleanup():
    backend = Backend()
    client = MongoDBDriver(PROFILE, backend, {})
    owner = client.open_session({})
    token = client.execute(owner, {'source': '{}'})
    with pytest.raises(Exception, match='active'):
        client.control_transaction(owner, 'begin')
    observe(client, token)
    client.control_transaction(owner, 'begin')
    backend.fail_close = True
    with pytest.raises(Exception, match='cleanup'):
        client.close_session(owner)
    assert owner in client._sessions
    backend.fail_close = False
    client.close_session(owner)
    assert len(set(backend.threads)) == 1


def test_unknown_result_is_redacted_and_not_replayed():
    backend = Backend()
    client = MongoDBDriver(PROFILE, backend, {})
    owner = client.open_session({})
    token = client.execute(owner, {'source': '{"error":true}'})
    value = observe(client, token)
    assert value['payload']['outcome_unknown']
    assert 'credential' not in json.dumps(value)
    with pytest.raises(Exception, match='unknown'):
        client.execute(owner, {'source': '{}'})
    client.close()


def test_cursor_cleanup_failure_retains_native_owner():
    backend = MongoDBDriverBackend()
    cursor = SimpleNamespace(close=lambda: None)
    backend._pending_cursors.append(cursor)
    backend.close()
    assert not backend._pending_cursors
