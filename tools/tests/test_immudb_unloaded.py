"""immudb while a database is unloaded (providers/immudb/provider.py).

Live, 1.11.0: /db/list, /db/list/v2, DATABASES() and /serverinfo all fail
"already closed" while any database is unloaded; /db/use answers per
database and /health still reports the version.
"""
import sys
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.providers.immudb import provider  # noqa: E402
from pgadmin.cdeadmin.sdk import RelationalClientError  # noqa: E402

CLOSED = RelationalClientError(
    "immudb REST request failed (HTTP 500) code=2 message='already closed'")
MISSING = RelationalClientError(
    "immudb REST request failed (HTTP 404) code=5 "
    "message=\"'gone' does not exist\"")


class Server:
    """The REST calls the fallback makes, answered as 1.11.0 did."""

    def __init__(self, unloaded=(), absent=(), metrics=None):
        self.unloaded, self.absent = set(unloaded), set(absent)
        self.metrics = metrics
        self.calls = []

    def bind(self):
        client = object.__new__(provider.ImmudbDBAPIClient)
        client._request = self.request
        client._login = lambda _route: 'token'
        client.rest_admin = lambda route, method, path, body=None: {
            'document': self.request(route, method, path, body)}

        def metrics(_route):
            if self.metrics is None:
                raise RelationalClientError('immudb metrics request failed')
            return set(self.metrics)
        client._metrics_databases = metrics
        return client

    def request(self, _route, method, path, body=None, token=None):
        self.calls.append(path)
        if path.startswith('/db/use/'):
            name = path.rsplit('/', 1)[1]
            if name in self.absent:
                raise MISSING
            if name in self.unloaded:
                raise CLOSED
            return {'token': 't'}
        if path in {'/db/list/v2', '/serverinfo'} and self.unloaded:
            raise CLOSED
        if path == '/db/list/v2':
            return {'databases': [{'name': 'defaultdb', 'loaded': True}]}
        if path == '/serverinfo':
            return {'version': '1.11.0', 'startedAt': 's'}
        if path == '/health':
            return {'status': True, 'version': '1.11.0-f07d3ac0'}
        raise AssertionError(path)


def test_the_native_list_is_used_while_every_database_is_loaded():
    client = Server().bind()
    assert client._database_records({}, 'defaultdb') == [
        {'name': 'defaultdb', 'loaded': True}]
    assert client._server_version({}) == ('1.11.0', 's')


def test_an_unloaded_database_is_listed_from_metrics_and_checked():
    server = Server(unloaded={'sales'}, absent={'gone'},
                    metrics={'defaultdb', 'sales', 'gone', 'systemdb'})
    records = server.bind()._database_records({}, 'defaultdb')
    assert [(item['name'], item['loaded']) for item in records] == [
        ('defaultdb', True), ('sales', False)]
    assert all('cannot list databases' in item['database_list_unread']
               for item in records)
    # systemdb is internal and is not checked.
    assert '/db/use/systemdb' not in server.calls


def test_without_metrics_only_the_connected_database_is_checked():
    records = Server(unloaded={'sales'}).bind()._database_records(
        {}, 'defaultdb')
    assert [item['name'] for item in records] == ['defaultdb']
    assert 'metrics endpoint could not be read' in records[0][
        'database_list_unread']


def test_the_version_comes_from_health_while_serverinfo_is_closed():
    assert Server(unloaded={'sales'}).bind()._server_version({}) == (
        '1.11.0', None)


def test_database_state_reads_loaded_unloaded_and_absent():
    client = Server(unloaded={'sales'}, absent={'gone'}).bind()
    assert client.database_state({}, 'defaultdb') is True
    assert client.database_state({}, 'sales') is False
    assert client.database_state({}, 'gone') is None


def test_other_failures_are_not_mistaken_for_an_unloaded_database():
    client = Server().bind()

    def broken(*_args, **_kwargs):
        raise RelationalClientError('immudb REST request failed (HTTP 403)')
    client._request = broken
    client.rest_admin = lambda *args, **kwargs: broken()
    with pytest.raises(RelationalClientError, match='403'):
        client._database_records({}, 'defaultdb')
    with pytest.raises(RelationalClientError, match='403'):
        client.database_state({}, 'defaultdb')


def test_metrics_names_come_from_db_labels():
    text = ('immudb_number_of_stored_entries{db="sales"} 3\n'
            'immudb_db_size_bytes{db="defaultdb"} 9\n'
            'go_info{version="go1.25.9"} 1\n')
    assert set(provider._METRICS_DATABASE.findall(text)) == {
        'sales', 'defaultdb'}


def test_a_database_that_cannot_be_checked_is_left_out_and_named():
    server = Server(unloaded={'sales'}, metrics={'defaultdb', 'private'})
    client = server.bind()
    request = server.request

    def refusing(route, method, path, body=None, token=None):
        if path == '/db/use/private':
            raise RelationalClientError(
                'immudb REST request failed (HTTP 403)')
        return request(route, method, path, body, token)
    client._request = refusing
    records = client._database_records({}, 'defaultdb')
    assert [item['name'] for item in records] == ['defaultdb']
    assert 'Not checked, so not shown: private' in records[0][
        'database_list_unread']
