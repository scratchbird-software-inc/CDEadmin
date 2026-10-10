"""Explicit dialect routing must not silently select another language."""
from types import SimpleNamespace

import pytest
import test_cdeadmin_clickhouse_provider  # noqa: F401
from pgadmin.cdeadmin.providers.influxdb.client import InfluxDBClient, InfluxDBClientError
from pgadmin.cdeadmin.providers.opensearch_sql_ppl.client import (
    OpenSearchSQLPPLClient, OpenSearchSQLPPLClientError,
)

CASES = [
    (InfluxDBClient, InfluxDBClientError, 'influxdb3-sql', 'influxql', 'sql'),
    (InfluxDBClient, InfluxDBClientError, 'influxdb3-influxql', 'sql', 'influxql'),
    (OpenSearchSQLPPLClient, OpenSearchSQLPPLClientError, 'opensearch-sql', 'ppl', 'sql'),
    (OpenSearchSQLPPLClient, OpenSearchSQLPPLClientError, 'opensearch-ppl', 'sql', 'ppl'),
]

@pytest.mark.parametrize('client,error,profile,default,expected', CASES)
def test_explicit_language_overrides_opposite_route_default(client, error, profile, default, expected):
    assert client._language(profile, default) == expected
    assert client._language(profile.upper(), default) == expected

@pytest.mark.parametrize('client,error,profile,default,expected', CASES)
@pytest.mark.parametrize('invalid', ['postgresql-sql', 'sql-garbage', 'fake-ppl', 'other-influxql', ' sql ', False, 0, {}, []])
def test_unrelated_or_malformed_language_rejected(client, error, profile, default, expected, invalid):
    with pytest.raises(error, match='query language'):
        client._language(invalid, default)

@pytest.mark.parametrize('client,error,legacy', [
    (InfluxDBClient, InfluxDBClientError, 'influxdb3-sql-influxql'),
    (OpenSearchSQLPPLClient, OpenSearchSQLPPLClientError, 'opensearch-sql-ppl'),
])
def test_legacy_combined_profile_is_explicit_compatibility(client, error, legacy):
    assert client._language(legacy, 'sql') == 'sql'
    assert client._language(None, 'sql') == 'sql'
    with pytest.raises(error, match='default'):
        client._language(legacy, 'unrelated')

@pytest.mark.parametrize('profile,default,endpoint', [
    ('influxdb3-sql', 'influxql', '/api/v3/query_sql'),
    ('influxdb3-influxql', 'sql', '/api/v3/query_influxql'),
])
def test_influx_native_endpoint_follows_explicit_language(profile, default, endpoint):
    client = InfluxDBClient()
    calls = []
    client._request = lambda route, path, **kw: (
        calls.append(path) or SimpleNamespace(json=lambda: []))
    client._query({'query_language': default, 'database': 'db'}, 'source', profile)
    assert calls == [endpoint]

@pytest.mark.parametrize('profile,default,endpoint', [
    ('opensearch-sql', 'ppl', '/_plugins/_sql'),
    ('opensearch-ppl', 'sql', '/_plugins/_ppl'),
])
def test_opensearch_native_endpoint_follows_explicit_language(profile, default, endpoint):
    client = OpenSearchSQLPPLClient()
    calls = []
    client._request = lambda route, path, **kw: (
        calls.append(path) or SimpleNamespace(json=lambda: {'schema': [], 'datarows': []}))
    client._query({'query_language': default, 'fetch_size': 100}, 'source', profile)
    assert calls == [endpoint]
