"""Strict provider route validators admit the endpoint service's envelope
(owner direction 2026-11-11: one registration path for every engine)."""
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

from pgadmin.cdeadmin.transports.route_envelope import (  # noqa: E402
    ROUTE_ENVELOPE_KEYS, unknown_route_keys,
)

ENVELOPE = {'route_id': 'r7', 'host': '127.0.0.1', 'port': 1, 'user': 'u', 'database': 'd',
            'database_target_id': 3, 'connection_timeout': 10, 'credential_kind': 'database_password',
            'credential_kinds': ['database_password'], 'credential_references': {}}


def test_envelope_keys_are_never_unknown():
    assert unknown_route_keys(ENVELOPE, frozenset()) == []
    assert unknown_route_keys({**ENVELOPE, 'bogus': 1}, frozenset({'x'})) == ['bogus']
    assert 'database_target_id' in ROUTE_ENVELOPE_KEYS


@pytest.mark.parametrize('module, attribute', [
    ('pgadmin.cdeadmin.providers.redis.client', 'RedisClient'),
    ('pgadmin.cdeadmin.providers.mongodb.client', 'MongoDBClient'),
    ('pgadmin.cdeadmin.providers.neo4j.client', 'Neo4jClient'),
    ('pgadmin.cdeadmin.providers.clickhouse.client', 'ClickHouseClient'),
    ('pgadmin.cdeadmin.providers.xtdb.client', 'XTDBClient'),
    ('pgadmin.cdeadmin.providers.cql_native', 'CassandraClient'),
])
def test_strict_clients_admit_the_envelope(module, attribute):
    import importlib
    client = getattr(importlib.import_module(module), attribute)
    route = {'host': '127.0.0.1', 'port': 1, **{k: v for k, v in ENVELOPE.items() if k not in ('host', 'port')}}
    validate = getattr(client, '_route')
    try:
        validate({'route': route}) if isinstance(validate, staticmethod) or not hasattr(validate, '__self__') else validate({'route': route})
    except Exception as exc:  # a validator may refuse other things; never the envelope
        assert 'unknown fields' not in str(exc), (module, exc)


def test_http_normaliser_admits_the_envelope():
    from pgadmin.cdeadmin.transports.analytics_http import normalize_http_route
    # The credential kind must agree with the authentication kind, as always;
    # the envelope's bookkeeping keys are what must not be refused.
    envelope = {k: v for k, v in ENVELOPE.items() if k not in ('credential_kind', 'credential_kinds')}
    route = normalize_http_route({'route': {**envelope, 'host': '127.0.0.1', 'port': 9200}}, default_port=9200)
    assert route['host'] == '127.0.0.1'
