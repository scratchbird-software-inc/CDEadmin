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
