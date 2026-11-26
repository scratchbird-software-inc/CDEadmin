"""Native refusal reasons (Decision 22): codes, the per-engine catalog, the contract and the reasons store."""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
for entry in (str(ROOT / 'web'), str(ROOT / 'tools'), str(ROOT / 'tools/tests')):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from pgadmin.cdeadmin.providers.postgresql import refusal_codes  # noqa: E402
from test_ui_descriptor_operations_postgresql import compile_maintenance  # noqa: E402
from pgadmin.cdeadmin.providers.postgresql.native_admin import PostgreSQLNativeAdminError  # noqa: E402
from pgadmin.cdeadmin.visual_admin import VisualAdminValidationError  # noqa: E402
from pgadmin.cdeadmin.visual_admin.refusal_log import RefusalReasons  # noqa: E402
from pgadmin.cdeadmin.visual_admin.refusals import response  # noqa: E402

DESCRIPTORS = ROOT / 'web/pgadmin/cdeadmin/ui_descriptors'


def catalog(engine):
    path = DESCRIPTORS / engine / 'refusals.json'
    return {row['code']: row['message'] for row in json.loads(path.read_text(encoding='utf-8'))['refusals']}


# --- the vocabulary and its text ------------------------------------------------------------------

def test_every_registered_code_has_catalog_text_and_no_other_text_exists():
    assert set(catalog('postgresql')) == set(refusal_codes.CODES)


def test_a_known_static_message_carries_its_code_and_field_and_an_unknown_one_none():
    error = PostgreSQLNativeAdminError('drop confirmation does not match object name')
    assert (error.refusal_code, error.refusal_field) == ('confirmation_mismatch', 'confirmation')
    other = PostgreSQLNativeAdminError('Columns must be a list of column names')
    assert (other.refusal_code, other.refusal_field) == (None, None)


def test_an_explicit_code_must_be_registered():
    ok = PostgreSQLNativeAdminError('anything', 'database_not_chosen', 'database')
    assert (ok.refusal_code, ok.refusal_field) == ('database_not_chosen', 'database')
    with pytest.raises(ValueError, match='unregistered'):
        PostgreSQLNativeAdminError('anything', 'made_up_code')


def test_the_three_refusals_seen_in_the_click_through_carry_a_reason():
    role = {'name': 'r1'}
    with pytest.raises(PostgreSQLNativeAdminError) as missing:
        compile_maintenance('role', 'drop-owned', role, {'confirmation': 'r1'})
    assert (missing.value.refusal_code, missing.value.refusal_field) == ('database_not_chosen', 'database')
    with pytest.raises(PostgreSQLNativeAdminError) as mismatch:
        compile_maintenance('role', 'drop-owned', role, {
            'database': 'postgresql:pg_database:16384', 'confirmation': 'other'})
    assert (mismatch.value.refusal_code, mismatch.value.refusal_field) == ('confirmation_mismatch', 'confirmation')
    from pgadmin.cdeadmin.providers.postgresql.cluster import _password_clauses
    with pytest.raises(PostgreSQLNativeAdminError) as password:
        _password_clauses({'rolpassword': 'Example-Pass-1!'})
    assert (password.value.refusal_code, password.value.refusal_field) == ('password_not_carried', 'rolpassword')


def test_the_provider_error_keeps_the_reason_the_compiler_gave():
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProviderError
    source = PostgreSQLNativeAdminError('choose the database the operation runs in')
    wrapped = PostgreSQLProviderError.refusing(source)
    assert str(wrapped) == str(source)
    assert (wrapped.refusal_code, wrapped.refusal_field) == ('database_not_chosen', 'database')
    assert PostgreSQLProviderError.refusing(ValueError('x')).refusal_code is None


# --- the contract ---------------------------------------------------------------------------------

def refusal(*errors, message='secret-canary typed-by-the-user'):
    return VisualAdminValidationError(message, list(errors))


def test_a_catalogued_code_carries_the_catalog_sentence_and_the_field_and_the_reference():
    error = refusal({'field_id': 'database', 'code': 'database_not_chosen'})
    value = response(error, '0123456789abcdef', catalog('postgresql'))
    entry = value['data']['refusal']['errors'][0]
    assert entry == {'field_id': 'database', 'code': 'database_not_chosen',
                     'message': catalog('postgresql')['database_not_chosen']}
    assert value['data']['refusal']['reference'] == '0123456789abcdef'
    assert value['status'] == 422 and value['data']['refusal']['native_dispatched'] is False


def test_an_uncatalogued_code_keeps_the_generic_sentence_and_no_message():
    value = response(refusal({'field_id': None, 'code': 'native_review_refused'}), None, catalog('postgresql'))
    assert value['data']['refusal']['errors'] == [{'field_id': None, 'code': 'native_review_refused'}]
    assert 'reference' not in value['data']['refusal']
    assert 'refused before dispatch' in value['errormsg']


def test_nothing_the_exception_or_the_draft_says_reaches_the_response():
    error = refusal({'field_id': 'database', 'code': 'database_not_chosen', 'message': 'secret-canary',
                     'value': 'secret-canary'})
    value = response(error, '0123456789abcdef', catalog('postgresql'))
    assert 'secret-canary' not in json.dumps(value)
    # a catalog entry that is not text, and a malformed reference, are ignored
    odd = response(error, 'not-a-reference', {'database_not_chosen': {'x': 'secret-canary'}})
    assert 'message' not in odd['data']['refusal']['errors'][0] and 'reference' not in odd['data']['refusal']
    assert 'secret-canary' not in json.dumps(odd)


def test_a_field_id_that_is_not_an_identifier_is_dropped_and_a_message_is_bounded():
    value = response(refusal({'field_id': 'a b; DROP', 'code': 'x y'}), None, {'invalid_field': 'z' * 900})
    entry = value['data']['refusal']['errors'][0]
    assert entry['field_id'] is None and entry['code'] == 'invalid_field' and len(entry['message']) == 300


# --- the reasons store ----------------------------------------------------------------------------

def test_a_reason_is_kept_under_its_reference_and_only_for_its_endpoint():
    store = RefusalReasons()
    reference = store.record(endpoint_id='e1', user_id=7, operation='role/drop-owned', message='boom', codes=['c'])
    assert len(reference) == 16
    entry = store.read(reference, 'e1')
    assert entry['message'] == 'boom' and entry['codes'] == ['c'] and entry['user_id'] == 7
    assert store.read(reference, 'e2') is None
    assert store.read('0' * 16, 'e1') is None and store.read(None, 'e1') is None and store.read('../x', 'e1') is None


def test_the_store_expires_and_is_bounded():
    now = [1000.0]
    store = RefusalReasons(limit=2, ttl=60, clock=lambda: now[0])
    first = store.record(endpoint_id='e', user_id=1, operation='o', message='m', codes=[])
    second = store.record(endpoint_id='e', user_id=1, operation='o', message='m', codes=[])
    third = store.record(endpoint_id='e', user_id=1, operation='o', message='m', codes=[])
    assert store.read(first, 'e') is None and store.read(second, 'e') and store.read(third, 'e')
    now[0] += 61
    assert store.read(second, 'e') is None and store.read(third, 'e') is None


# --- who may read a reason ------------------------------------------------------------------------

def test_a_reason_is_read_only_by_someone_allowed_and_only_on_its_own_endpoint(monkeypatch):
    from pgadmin.cdeadmin.visual_admin import refusal_log
    store = RefusalReasons()
    monkeypatch.setattr(refusal_log, '_STORE', store)
    reference = store.record(endpoint_id='e1', user_id=7, operation='role/drop-owned',
                             message='raw provider text with a name', codes=['database_not_chosen'])
    status, body = refusal_log.lookup(reference, 'e1', allowed=True)
    assert status == 200 and body['data']['message'] == 'raw provider text with a name'
    assert set(body['data']) == {'reference', 'operation', 'codes', 'message', 'time'}  # no user id, no endpoint id
    # not allowed: refused before the store is consulted, the same for a real and an invented reference
    assert refusal_log.lookup(reference, 'e1', allowed=False)[0] == 403
    assert refusal_log.lookup('0' * 16, 'e1', allowed=False)[0] == 403
    # allowed, but another endpoint, an unknown reference or none: one answer for all three
    assert refusal_log.lookup(reference, 'e2', allowed=True)[0] == 404
    assert refusal_log.lookup('0' * 16, 'e1', allowed=True)[0] == 404
    assert refusal_log.lookup(None, 'e1', allowed=True)[0] == 404


def test_the_postgresql_probe_says_yes_only_for_a_connected_superuser():
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider

    class Connection:
        def __init__(self, connected, rows, status=True):
            self._connected, self.rows, self.status = connected, rows, status

        def connected(self):
            return self._connected

        def execute_dict(self, sql, *_):
            assert 'rolsuper' in sql and 'session_user' in sql
            return self.status, {'rows': self.rows}

    def probe(connection):
        provider = object.__new__(PostgreSQLProvider)
        provider._driver = type('Driver', (), {'connection_manager': lambda self, sid: type(
            'Manager', (), {'connection': lambda self: connection})()})()
        return provider.is_native_administrator({'_provider_route': {'server_id': 1}})

    assert probe(Connection(True, [{'rolsuper': True}])) is True
    assert probe(Connection(True, [{'rolsuper': False}])) is False
    assert probe(Connection(False, [{'rolsuper': True}])) is False
    assert probe(Connection(True, [])) is False
    assert probe(Connection(True, [{'rolsuper': True}], status=False)) is False
    assert PostgreSQLProvider.is_native_administrator(object.__new__(PostgreSQLProvider), {}) is False


def test_the_permission_exists_and_is_registered():
    from pgadmin.tools.user_management.PgAdminPermissions import AllPermissionTypes
    assert AllPermissionTypes.refusal_view_reasons == 'refusal.view_reasons'
    assert 'refusal.view_reasons' in AllPermissionTypes.list()
