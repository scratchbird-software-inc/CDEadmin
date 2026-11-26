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


# --- every refusal is dealt with (Decision 22) -----------------------------------------------------

def test_every_refusal_in_the_provider_source_is_registered_or_matched_by_a_rule():
    """A new refusal that is neither fixed text in refusal_literals.json nor matched by a rule fails here."""
    import refusal_inventory
    assert refusal_inventory.main(['--check']) == 0, 'run: python3 tools/refusal_inventory.py --write'
    unmatched = [template for template in refusal_inventory.dynamic_templates()
                 if refusal_codes.describe(template.replace('{}', 'x')).code is None]
    assert unmatched == [], 'add a rule to refusal_codes.RULES for: ' + '; '.join(unmatched)
    literals = refusal_inventory.literals()
    assert all(refusal_codes.describe(text).explanation == text or refusal_codes.describe(text).code
               for text in literals)


def test_every_code_a_rule_can_give_has_catalog_text():
    given = {code for code, _pattern in refusal_codes.RULES} | {code for code, _field in refusal_codes.KNOWN_MESSAGES.values()}
    assert given <= set(catalog('postgresql')) and given <= refusal_codes.CODES
    assert 'rule_not_met' in catalog('postgresql')


def test_a_message_built_from_values_gets_the_sentence_for_its_rule_and_never_its_own_words():
    for message, code, field in (
            ('schema must not be empty', 'value_required', 'schema'),
            ('privileges must be a list of rows', 'list_expected', 'privileges'),
            ('name exceeds 63 bytes', 'too_long', 'name'),
            ('privilege rows must be a list of rows', 'list_expected', None),
            ('enum label hunter2 repeats', 'duplicate_value', None),
            ('Native postgres -C rejected postgresql.conf: password=hunter2', 'native_tool_rejected', None),
            ('PostgreSQL rejected ALTER ROLE x PASSWORD \'hunter2\': syntax', 'native_tool_rejected', None),
            ('Unsupported PostgreSQL configuration operation: hunter2', 'unsupported_here', None)):
        reason = refusal_codes.describe(message)
        assert (reason.code, reason.field_id, reason.explanation) == (code, field, None), message


def test_a_fixed_message_is_shown_as_it_stands_and_an_unknown_one_stays_generic():
    reason = refusal_codes.describe('a table has at most one primary key')
    assert (reason.code, reason.explanation) == ('rule_not_met', 'A table has at most one primary key.')
    assert refusal_codes.describe('something no compiler raises') == refusal_codes.Reason(None, None)
    # a known code keeps its catalog sentence rather than the message's own words
    assert refusal_codes.describe('drop confirmation does not match object name').explanation is None


def test_a_fixed_message_cannot_be_forged_by_a_built_one():
    """Only an exact match shows as it stands; a message that merely contains a registered text does not."""
    reason = refusal_codes.describe('a table has at most one primary key hunter2')
    assert reason.explanation is None


def test_the_response_shows_a_registered_text_and_still_never_an_entrys_own_message():
    error = refusal({'field_id': None, 'code': 'rule_not_met', 'explanation': 'a table has at most one primary key',
                     'message': 'secret-canary', 'value': 'secret-canary'})
    value = response(error, '0123456789abcdef', catalog('postgresql'))
    assert value['data']['refusal']['errors'][0]['message'] == 'a table has at most one primary key'
    assert 'secret-canary' not in json.dumps(value)
    # no explanation: the catalog's sentence for the code
    plain = response(refusal({'field_id': None, 'code': 'rule_not_met'}), None, catalog('postgresql'))
    assert plain['data']['refusal']['errors'][0]['message'] == catalog('postgresql')['rule_not_met']


def test_the_plan_funnel_gives_every_provider_refusal_a_reason():
    from pgadmin.cdeadmin.providers.postgresql.provider import PostgreSQLProvider, PostgreSQLProviderError

    class Planner:
        def __init__(self, error):
            self.error = error

        def plan(self, _request):
            raise self.error

    def refused(error):
        provider = object.__new__(PostgreSQLProvider)
        provider._visual_admin = Planner(error)
        with pytest.raises(VisualAdminValidationError) as caught:
            provider.plan_visual_admin({})
        return caught.value.errors[0]

    assert refused(PostgreSQLProviderError('a table has at most one primary key')) == {
        'field_id': None, 'code': 'rule_not_met', 'explanation': 'A table has at most one primary key.'}
    assert refused(PostgreSQLProviderError.refusing(PostgreSQLNativeAdminError('schema must not be empty'))) == {
        'field_id': 'schema', 'code': 'value_required'}
    assert refused(PostgreSQLProviderError('choose the database the operation runs in')) == {
        'field_id': 'database', 'code': 'database_not_chosen'}
    assert refused(PostgreSQLProviderError('never seen')) == {'field_id': None, 'code': 'native_review_refused'}


# --- the wording of the fixed messages ------------------------------------------------------------

def test_every_fixed_message_has_been_reviewed_exactly_once():
    """A new fixed message must be put in refusal_wording.json (text, code, or keep after review)."""
    import refusal_inventory
    words = refusal_codes.wording()
    registered = set(refusal_inventory.literals())
    groups = [set(words['text']), set(words['code']), set(words['keep'])]
    assert sum(len(group) for group in groups) == len(set().union(*groups)), 'a message is listed twice'
    unreviewed = sorted(registered - set().union(*groups))
    assert unreviewed == [], 'review the wording of: ' + '; '.join(unreviewed)
    stale = sorted(set().union(*groups) - registered)
    assert stale == [], 'no longer a refusal message: ' + '; '.join(stale)


def test_the_wording_is_sound():
    words = refusal_codes.wording()
    for message, replacement in words['text'].items():
        assert replacement and replacement != message, message
        assert len(replacement) <= refusal_codes.EXPLANATION_LIMIT, message
        assert replacement[0].isupper(), f'start with a capital: {replacement}'
        assert not any(internal in replacement for internal in ('pgAdmin', 'provider tree', 'inherited', 'native ')), replacement
    for message, entry in words['code'].items():
        assert entry['code'] in refusal_codes.CODES and entry['code'] in catalog('postgresql'), message
        assert set(entry) <= {'code', 'field'}, message


def test_a_reworded_message_shows_the_new_sentence_and_a_coded_one_the_catalog_sentence():
    reworded = refusal_codes.describe('attstorage must be one of p, m, e, x')
    assert (reworded.code, reworded.explanation) == (
        'rule_not_met', 'Storage must be p (plain), m (main), e (external) or x (extended).')
    coded = refusal_codes.describe('PostgreSQL provider is closed')
    assert (coded.code, coded.explanation) == ('provider_unavailable', None)
    fielded = refusal_codes.describe('Confirm the exact parameter name to reset')
    assert (fielded.code, fielded.field_id, fielded.explanation) == ('confirmation_mismatch', 'confirmation', None)
    kept = refusal_codes.describe('a table has at most one primary key')
    assert kept.explanation == 'A table has at most one primary key.'
    # a kept message already written as a sentence keeps its capital and its full stop
    assert refusal_codes.describe('A PostgreSQL row changed or is no longer writable. Refresh before retrying.').explanation == \
        'A PostgreSQL row changed or is no longer writable. Refresh before retrying.'
    assert refusal_codes.describe('ALL must be the only privilege').explanation == 'ALL must be the only privilege.'


def test_every_message_shown_as_it_stands_reads_as_a_sentence():
    import refusal_inventory
    words = refusal_codes.wording()
    for message in refusal_inventory.literals():
        shown = refusal_codes.describe(message).explanation
        if message in words['code'] or shown is None:
            continue
        assert shown[0].isupper() and shown[-1] in '.!?', shown


# --- the shared funnel keeps the real message, scrubbed (all actual-engine providers) ----------------------------

def _facade(planner, fields, draft):
    from types import SimpleNamespace
    from pgadmin.cdeadmin.visual_admin.provider import ProviderVisualAdministration

    class Facade(ProviderVisualAdministration):
        engine_id, profile_version = 'mysql', '9.7.0'
        context = SimpleNamespace(endpoint_id='e', mode='direct')
        permissions = SimpleNamespace(require=lambda *_: None)

        def __init__(self):
            pass

        def _operation(self, _payload):
            return {'resource_kind': 'user'}, {
                'operation_id': 'create', 'graphical_form_authority': 'engine-catalog', 'mutation_class': 'read',
                'confirmation_required': False, 'required_permissions': []}

        def _require_mutation(self, _mutation):
            pass

        def _operation_supported(self, *_):
            return True

        def validate(self, _payload, retain_sensitive=False):
            return {'valid': True, 'errors': [], 'draft': dict(draft)}

        def _operation_fields(self, _resource, _operation, _draft):
            return fields

        def _planner_callback(self):
            return planner

    return Facade()


def test_the_funnel_keeps_the_native_message_with_the_drafts_secrets_removed():
    from pgadmin.cdeadmin.sdk import RelationalClientError

    def planner(_request):
        raise RelationalClientError("Access denied for CREATE USER 'u'@'%' IDENTIFIED BY 'Other-Canary'; "
                                    "the value Secr3t-Canary was refused and PASSWORD('Third-Canary') too")
    facade = _facade(planner, [{'field_id': 'name'}, {'field_id': 'password', 'control': 'password'}],
                     {'name': 'u', 'password': 'Secr3t-Canary'})
    with pytest.raises(VisualAdminValidationError) as caught:
        facade.plan({'resource_kind': 'user', 'operation_id': 'create', 'draft': {}})
    message = str(caught.value)
    for canary in ('Secr3t-Canary', 'Other-Canary', 'Third-Canary'):
        assert canary not in message, canary
    assert 'Access denied for CREATE USER' in message and '<redacted>' in message
    assert caught.value.errors == [{'field_id': None, 'code': 'native_review_refused'}]
    # what the store keeps is that message, and the response still says none of it
    assert 'Canary' not in json.dumps(response(caught.value, '0123456789abcdef', {}))


def test_the_scrub_hides_short_values_only_where_quoted_and_nested_secrets_too():
    from pgadmin.cdeadmin.visual_admin.refusal_log import scrub, secret_values
    assert scrub("bad value 'ab' near abc", ['ab']) == "bad value '<redacted>' near abc"
    fields = [{'field_id': 'rows', 'sensitive': True}, {'field_id': 'name'}]
    assert sorted(secret_values(fields, {'rows': [{'p': 'one-secret'}, 'two-secret'], 'name': 'open'})) == ['one-secret', 'two-secret']
    assert scrub('nothing to hide', []) == 'nothing to hide'


def test_the_shared_funnel_gives_an_engine_that_describes_its_refusals_a_reason():
    from types import SimpleNamespace
    from pgadmin.cdeadmin.sdk.actual_engine import ActualEnginePilotProvider
    holder = SimpleNamespace(describe_refusal=lambda message: refusal_codes_reason(message))

    def refusal_codes_reason(message):
        from pgadmin.cdeadmin.visual_admin.refusal_vocabulary import Reason
        return Reason('value_required', 'name') if message == 'name must not be empty' else Reason(None, None)
    attach = ActualEnginePilotProvider._with_refusal_reason
    generic = VisualAdminValidationError('name must not be empty', [{'field_id': None, 'code': 'native_review_refused'}])
    improved = attach(holder, generic)
    assert improved.errors == [{'field_id': 'name', 'code': 'value_required'}] and str(improved) == 'name must not be empty'
    # an unknown message, a coded refusal and an engine with no hook all keep the refusal as it is
    other = VisualAdminValidationError('unknown', [{'field_id': None, 'code': 'native_review_refused'}])
    assert attach(holder, other) is other
    coded = VisualAdminValidationError('x', [{'field_id': 'a', 'code': 'unknown_fields'}])
    assert attach(holder, coded) is coded
    assert attach(SimpleNamespace(), generic) is generic


# --- the MySQL administrator probe ----------------------------------------------------------------------------

class _Cursor:
    def __init__(self, current, super_count):
        self.current, self.super_count, self.sql, self.params, self.closed = current, super_count, [], [], False

    def execute(self, sql, params=None):
        self.sql.append(sql)
        self.params.append(params)
        self.last = sql

    def fetchone(self):
        if 'CURRENT_USER' in self.last:
            return None if self.current is None else (self.current,)
        return (self.super_count,)

    def close(self):
        self.closed = True


def _probe(current, super_count):
    from pgadmin.cdeadmin.providers.mysql_family.provider import _administrator
    cursor = _Cursor(current, super_count)
    result = _administrator(type('Connection', (), {'cursor': lambda self: cursor})(), {})
    return result, cursor


def test_the_mysql_probe_says_yes_only_for_an_account_holding_super_and_names_it_exactly():
    result, cursor = _probe('admin@%', 1)
    assert result is True and cursor.closed
    assert cursor.params[1] == ("'admin'@'%'",)
    assert 'USER_PRIVILEGES' in cursor.sql[1] and "PRIVILEGE_TYPE = 'SUPER'" in cursor.sql[1]
    assert _probe('limited@localhost', 0)[0] is False
    # an account merely called root, with no SUPER, is not an administrator
    assert _probe('root@evil', 0)[0] is False
    # a quote in the name cannot change what is asked
    result, cursor = _probe("o'brien@%", 0)
    assert result is False and cursor.params[1] == ("'o''brien'@'%'",)
    # anything unclear answers no
    assert _probe(None, 1)[0] is False and _probe('nohost', 1)[0] is False and _probe('@h', 1)[0] is False


def test_the_mysql_provider_closes_the_probe_on_failure_and_exposes_the_vocabulary():
    from pgadmin.cdeadmin.providers.mysql_family.provider import MySQLPilotProvider

    class Broken:
        def describe_administrator(self, _request):
            raise RuntimeError('boom')
    provider = object.__new__(MySQLPilotProvider)
    provider.client = Broken()
    assert provider.is_native_administrator({'_provider_route': {}}) is False
    provider.client = type('Yes', (), {'describe_administrator': lambda self, request: True})()
    assert provider.is_native_administrator({'_provider_route': {}}) is True
    assert provider.is_native_administrator('not a mapping') is True  # a non-mapping is treated as an empty request
    from pgadmin.cdeadmin.providers.mysql_family import refusal_codes as mysql_codes
    assert hasattr(provider, 'describe_refusal') and mysql_codes.describe('no such message').code is None
