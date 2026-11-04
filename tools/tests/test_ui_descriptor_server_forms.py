"""Server family forms round-trip (README step 8 for registration): a draft
entered through the server form's own fields -> servers-API payload ->
persisted route (the registration contract's own validator) -> a live session
on the engine -> edit pre-fill from the persisted route.

SQLite and DuckDB run on temporary files. MariaDB and Firebird need the same
``CDEADMIN_ROUNDTRIP_*`` settings as their family round trips and are skipped
otherwise. PostgreSQL registration is legacy_preserved (phase 5).
"""
import json
import os
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'web'))
sys.path.insert(0, str(ROOT / 'tools'))
if 'pgadmin' not in sys.modules:
    package = ModuleType('pgadmin')
    package.__path__ = [str(ROOT / 'web/pgadmin')]
    sys.modules['pgadmin'] = package

from pgadmin.cdeadmin.endpoints.profiles import registration_profile, registration_profiles  # noqa: E402
from ui_descriptor_roundtrip import (  # noqa: E402
    registration_data, registration_prefill, registration_route, resolved_form,
)

GENERIC = {'name', 'host', 'port', 'username', 'password', 'save_password', 'database', 'connect_now', 'comment',
           'bgcolor', 'fgcolor', 'tags', 'profile'}


def roundtrip(engine, profile_id, draft):
    form = resolved_form(engine, 'server')
    profile = registration_profile(profile_id)
    data = registration_data(form, draft)
    # every non-generic form field is a declared contract field or secret (nothing invented)
    declared = {f['field_id'] for sibling in registration_profiles() if sibling['engine_id'] == engine
                for f in sibling['connection_fields'] + sibling['secret_fields']}
    for tab in form['tabs']:
        for field in tab['fields']:
            assert field['field_id'] in GENERIC or field['field_id'] in declared, (engine, field['field_id'])
    route = registration_route(profile, data)
    prefill = registration_prefill(form, profile, route, data)
    for key, value in draft.items():
        if key in {'password', 'save_password'}:
            continue  # secrets never come back into the form
        actual = prefill.get(key)
        if isinstance(actual, list):  # grid rows carry the editor's row ids
            actual = [{k: v for k, v in row.items() if k != '_id'} if isinstance(row, dict) else row for row in actual]
        assert actual == value, (engine, key, actual, value)
    return form, profile, route


def test_sqlite_server_form(tmp_path):
    import sqlite3
    main = tmp_path / 'main.sqlite'
    other = tmp_path / 'other.sqlite'
    for path in (main, other):
        sqlite3.connect(path).close()
    draft = {'name': 'sqlite rt', 'database': str(main), 'uri_mode': 'default', 'timeout': 7,
             'attached_databases': [{'name': 'other', 'database': str(other)}], 'connect_now': True,
             'tags': [{'text': 'rt', 'color': '#ccc'}]}
    _form, _profile, route = roundtrip('sqlite', 'sqlite-native', draft)
    assert route['attached_databases'] == [{'name': 'other', 'database': str(other)}] and route['timeout'] == 7
    from pgadmin.cdeadmin.providers.sqlite.provider import _initialize_connection, _route_arguments
    # The client pins the admitted SQLite build (3.53.0); the route is proven through the provider's
    # own connect arguments and connection initializer (attachments), as the other SQLite suites do.
    arguments = _route_arguments(route)
    assert arguments['database'] == str(main) and arguments['timeout'] == 7
    connection = sqlite3.connect(**arguments)
    try:
        _initialize_connection(connection, route)
        assert 'other' in [row[1] for row in connection.execute('PRAGMA database_list')]
    finally:
        connection.close()


def test_duckdb_server_form(tmp_path):
    duckdb = pytest.importorskip('duckdb')
    main = tmp_path / 'main.duckdb'
    duckdb.connect(str(main)).close()
    draft = {'name': 'duckdb rt', 'database': str(main), 'read_only': False, 'config': {'threads': '2'},
             'attached_databases': [], 'connect_now': False}
    _form, _profile, route = roundtrip('duckdb', 'duckdb-native', draft)
    assert route['config'] == {'threads': '2'}
    from pgadmin.cdeadmin.providers.duckdb.provider import _create_client
    client = _create_client()
    try:
        identity = client.runtime_identity({'route': route})
        assert identity['engine_id'] == 'duckdb' and identity['version']
    finally:
        client.close()


@pytest.mark.skipif(not os.environ.get('CDEADMIN_ROUNDTRIP_MARIADB'), reason='CDEADMIN_ROUNDTRIP_MARIADB is not set')
def test_mariadb_server_form():
    settings = json.loads(os.environ['CDEADMIN_ROUNDTRIP_MARIADB'])
    draft = {'name': 'mariadb rt', 'host': settings['host'], 'port': int(settings['port']), 'username': settings['user'],
             'password': settings['password'], 'save_password': True, 'database': 'information_schema',
             'connection_timeout': 5, 'compress': True, 'ssl': False, 'autocommit': False, 'connect_now': True}
    _form, _profile, route = roundtrip('mariadb', 'mariadb-native', draft)
    assert route['compress'] is True and route['user'] == settings['user']
    from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_PROFILE, _create_client
    from pgadmin.cdeadmin.security.secrets import SecretLease
    client = _create_client(MARIADB_PROFILE, SimpleNamespace(acquire_secret=lambda *_args: SecretLease(settings['password'])),
                            SimpleNamespace(pool_namespace='ui-server-rt'))
    try:
        identity = client.runtime_identity({'route': {**route, 'credential_reference_id': 'rt', 'principal_reference': 'rt'}})
        assert identity['engine_id'] == 'mariadb' and identity['version']
    finally:
        client.close()


@pytest.mark.skipif(not os.environ.get('CDEADMIN_ROUNDTRIP_FIREBIRD'), reason='CDEADMIN_ROUNDTRIP_FIREBIRD is not set')
def test_firebird_network_server_form():
    pytest.importorskip('firebird.driver')
    settings = json.loads(os.environ['CDEADMIN_ROUNDTRIP_FIREBIRD'])
    draft = {'profile': 'firebird-native', 'name': 'firebird rt', 'host': settings['host'], 'port': int(settings['port']),
             'username': settings['user'], 'password': settings['password'], 'save_password': False,
             'auth_plugin_list': 'Srp256,Srp', 'trusted_auth': False, 'charset': 'UTF8', 'wire_crypt': 'Enabled',
             'transaction_isolation': 'SNAPSHOT', 'parallel_workers': 1, 'attachment_cache_pages': 128, 'connect_now': True}
    _form, _profile, route = roundtrip('firebird', 'firebird-native', draft)
    assert route['auth_plugin_list'] == 'Srp256,Srp' and route['host'] == settings['host']
    from pgadmin.cdeadmin.providers.firebird.provider import _create_client
    from pgadmin.cdeadmin.security.secrets import SecretLease
    client = _create_client(SimpleNamespace(acquire_secret=lambda *_args: SecretLease(settings['password'])))
    try:
        identity = client.runtime_identity({'route': {**route, 'credential_reference_id': 'rt', 'principal_reference': 'rt'}})
        assert identity['engine_id'] == 'firebird' and identity['version'].startswith('5.')
    finally:
        client.close()


def test_firebird_embedded_server_form_maps_to_its_contract(tmp_path):
    """The embedded profile shares the form behind the profile switch; its
    draft reaches the embedded contract (no live engine needed to prove the mapping)."""
    draft = {'profile': 'firebird-embedded', 'name': 'embedded rt', 'database': str(tmp_path / 'rt.fdb'),
             'user': 'SYSDBA', 'attachment_mode': 'embedded', 'filesystem_root': str(tmp_path), 'charset': 'UTF8', 'connect_now': False}
    _form, _profile, route = roundtrip('firebird', 'firebird-embedded', draft)
    assert route['attachment_mode'] == 'embedded' and route['user'] == 'SYSDBA' and route['database'].endswith('rt.fdb')


# Parity engines (owner direction 2026-10-30): each server form maps a draft onto its own
# registration contract, and, when its CDEADMIN_ROUNDTRIP_<ENGINE> settings are present (the
# same object its family round trip reads), the persisted route opens a live session.
PARITY = {
    'dolt': ('dolt-native', 'cdeadmin_demo', {
        'ssl_disabled': True, 'connection_timeout': 7, 'autocommit': True, 'time_zone': '+00:00',
        'conn_attrs': {'program_name': 'cdeadmin-rt'}, 'tls_versions': ['TLSv1.2', 'TLSv1.3']}),
    'tidb': ('tidb-native', 'cdeadmin_demo', {
        'ssl_disabled': True, 'connection_timeout': 7, 'autocommit': True, 'compress': True,
        'conn_attrs': {'program_name': 'cdeadmin-rt'}, 'tls_ciphersuites': [{'value': 'TLS_AES_128_GCM_SHA256'}]}),
    'vitess': ('vitess-native', 'test_keyspace', {
        'ssl_disabled': True, 'connection_timeout': 7, 'autocommit': True,
        'conn_attrs': {'program_name': 'cdeadmin-rt'}}),
    'cockroachdb': ('cockroachdb-native', 'cdeadmin_demo', {
        'sslmode': 'disable', 'application_name': 'cdeadmin-rt', 'connect_timeout': 7}),
    'yugabytedb': ('yugabytedb-native', 'cdeadmin_demo', {
        'sslmode': 'disable', 'application_name': 'cdeadmin-rt', 'connect_timeout': 7}),
    'immudb': ('immudb-native', 'cdeadmin_demo', {
        'sslmode': 'disable', 'application_name': 'cdeadmin-rt', 'connect_timeout': 7}),
    'xtdb': ('xtdb-native', 'xtdb', {
        'tls_mode': 'disable', 'application_name': 'cdeadmin-rt', 'transaction_mode': 'read-only'}),
}


def parity_draft(engine, settings=None):
    profile_id, database, extra = PARITY[engine]
    settings = settings or {'host': '127.0.0.1', 'port': 5000, 'user': 'rt'}
    draft = {'name': f'{engine} rt', 'host': settings['host'], 'port': int(settings['port']),
             'username': settings['user'], 'database': settings.get('database', database),
             'connect_now': True, **extra}
    if settings.get('password'):
        draft.update(password=settings['password'], save_password=False)
    if engine == 'immudb' and settings.get('web_port'):  # the native REST API on its own port
        draft['web_port'] = int(settings['web_port'])
    if engine == 'vitess' and settings.get('http_port'):  # vtgate's HTTP endpoint reports its identity
        draft['vtgate_http_port'] = int(settings['http_port'])
    if engine == 'yugabytedb':  # one form serves the YSQL and YCQL profiles
        draft['profile'] = profile_id
    return profile_id, draft


@pytest.mark.parametrize('engine', sorted(PARITY))
def test_parity_server_form_maps_to_its_contract(engine):
    profile_id, draft = parity_draft(engine)
    _form, _profile, route = roundtrip(engine, profile_id, draft)
    assert route['host'] == '127.0.0.1' and int(route['port']) == 5000
    for key, value in PARITY[engine][2].items():
        if isinstance(value, list) and value and isinstance(value[0], dict) and set(value[0]) == {'value'}:
            value = [row['value'] for row in value]  # a string-list grid's rows reach the route as strings
        assert route.get(key) == value, (engine, key, route.get(key))


def test_yugabytedb_server_form_serves_its_ycql_profile():
    draft = {'profile': 'yugabytedb-ycql', 'name': 'ycql rt', 'host': '127.0.0.1', 'port': 9042,
             'username': 'cassandra', 'keyspace': 'cdeadmin_demo', 'local_dc': 'datacenter1', 'connect_now': False}
    form, _profile, route = roundtrip('yugabytedb', 'yugabytedb-ycql', draft)
    assert route['keyspace'] == 'cdeadmin_demo' and route['local_dc'] == 'datacenter1'
    ysql_only = {field['field_id'] for tab in form['tabs'] for field in tab['fields']
                 if field.get('visible_when') == {'field': 'profile', 'equals': 'yugabytedb-native'}}
    assert 'sslmode' in ysql_only and 'keyspace' not in ysql_only


def live_identity(form_engine, profile_id, draft, module_name, password=None, passwordless=False):
    """Register the draft through the form, then open the persisted route with the provider."""
    import importlib
    import uuid
    from pgadmin.cdeadmin.security.secrets import SecretLease
    _form, profile_contract, route = roundtrip(form_engine, profile_id, draft)
    provider_module = importlib.import_module(f'pgadmin.cdeadmin.providers.{module_name}.provider')
    route = dict(route)
    # As the endpoint service does before every provider call (_route_and_reference): a profile
    # whose database target is another route key (YCQL keyspace) receives it under that key.
    target_key = (profile_contract.get('database_targeting') or {}).get('route_key', 'database')
    if target_key != 'database':
        database = route.pop('database', None)
        if target_key and database is not None:
            route[target_key] = database
    if password:
        route.update(credential_reference_id='rt', principal_reference='rt')
    elif passwordless:
        route['passwordless'] = True
    permissions = SimpleNamespace(acquire_secret=(lambda *_args: SecretLease(password.encode())) if password else None,
                                  require=lambda *_args: None)
    profile = provider_module.PROFILE
    namespace = f'ui-server-rt-{uuid.uuid4().hex[:6]}'
    context = SimpleNamespace(
        endpoint_id=str(uuid.uuid4()), session_namespace=namespace, pool_namespace=namespace,
        cache_namespace=namespace, provider_id=profile.provider_id, profile_id=profile.profile_id,
        profile_version=profile.exact_version, provider_version='0.2.0', mode='legacy_native',
        runtime_verification_state='unverified', verified_runtime_family=None, declared_runtime_family=None,
        target_adapter_id=None, effective_permissions=frozenset())
    provider = provider_module.create_provider(context, permissions)
    try:
        return provider.client.runtime_identity({'route': route})
    finally:
        close = getattr(provider, 'close', None) or getattr(provider.client, 'close', None)
        if close:
            close()


@pytest.mark.parametrize('engine', sorted(PARITY))
def test_parity_server_form_opens_a_live_session(engine):
    variable = f'CDEADMIN_ROUNDTRIP_{engine.upper()}'
    if not os.environ.get(variable):
        pytest.skip(f'{variable} is not set')
    settings = json.loads(os.environ[variable])
    profile_id, draft = parity_draft(engine, settings)
    identity = live_identity(engine, profile_id, draft, engine, settings.get('password'),
                             passwordless=engine in ('dolt', 'tidb', 'vitess'))
    assert identity['engine_id'] == engine and identity['version'], identity


@pytest.mark.skipif(not os.environ.get('CDEADMIN_ROUNDTRIP_YUGABYTEDB_YCQL'),
                    reason='CDEADMIN_ROUNDTRIP_YUGABYTEDB_YCQL is not set')
def test_yugabytedb_ycql_server_form_opens_a_live_session():
    settings = json.loads(os.environ['CDEADMIN_ROUNDTRIP_YUGABYTEDB_YCQL'])
    draft = {'profile': 'yugabytedb-ycql', 'name': 'ycql rt', 'host': settings['host'], 'port': int(settings['port']),
             'username': settings['user'], 'keyspace': settings['database'], 'local_dc': settings.get('local_dc', 'datacenter1'),
             'connect_now': True}
    if settings.get('password'):
        draft.update(auth_mode='password', password=settings['password'], save_password=False)
    if settings.get('version_api_port'):  # the master's HTTP endpoint reports the version
        draft['version_api_port'] = int(settings['version_api_port'])
    identity = live_identity('yugabytedb', 'yugabytedb-ycql', draft, 'yugabytedb_ycql', settings.get('password'))
    assert identity['engine_id'] == 'yugabytedb' and identity['protocol_id'] == 'cql' and identity['version'], identity

@pytest.mark.parametrize('engine', ['dolt', 'tidb', 'vitess'])
def test_mysql_wire_empty_typed_fields_leave_the_route_unset(engine):
    """An untouched Failover grid, TLS lists and attribute map send null (empty_as_null), so the
    route has no key, as with the legacy empty JSON field; the connector refuses an empty list."""
    from pgadmin.cdeadmin.endpoints.profiles import registration_profile
    from ui_descriptor_roundtrip import backend_draft
    profile_id, draft = parity_draft(engine)
    draft = {key: value for key, value in draft.items() if key not in ('conn_attrs', 'tls_versions', 'tls_ciphersuites')}
    form = resolved_form(engine, 'server')
    data = registration_data(form, draft)
    for key in ('failover', 'tls_versions', 'tls_ciphersuites', 'conn_attrs'):
        assert data.get(f'cde_route_{key}', None) is None, (engine, key, data.get(f'cde_route_{key}'))
    route = registration_route(registration_profile(profile_id), data)
    assert not {'failover', 'tls_versions', 'tls_ciphersuites', 'conn_attrs'} & set(route), sorted(route)
    offered = {field['field_id'] for tab in form['tabs'] for field in tab['fields']}
    assert 'conn_attrs' in offered and ('compress' in offered) == (engine == 'tidb'), sorted(offered)
    edit = backend_draft(form, {'failover': []}, mode='alter', baseline={'failover': [{'host': 'b', 'port': 3306}]})
    assert edit == {'cde_route_failover': None}
