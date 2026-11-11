"""PostgreSQL domain and type create/alter/drop compile to exact native
statements (M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.types import (
    domain_facts, domain_form, type_facts, type_form,
)

DOMAIN = {'schema': 'service', 'name': 'code', 'oid': 56385,
          'comment': 'codes',
          'catalog_row': {'typname': 'code', 'typtype': 'd',
                          'typnotnull': True,
                          'typdefault': "'x'::character varying"}}
CONSTRAINTS = {56385: [
    {'name': 'code_not_null', 'definition': 'NOT NULL',
     'catalog_row': {'convalidated': True}},
    {'name': 'code_check',
     'definition': "CHECK (((VALUE)::text <> ''::text)) NOT VALID",
     'catalog_row': {'convalidated': False}}]}
ENUM = {'schema': 'service', 'name': 'mood', 'oid': 56389, 'comment': None,
        'catalog_row': {'typname': 'mood', 'typtype': 'e', 'typrelid': '0'},
        'children': {'pg_enum': [
            {'enumlabel': 'ok', 'enumsortorder': 2},
            {'enumlabel': 'sad', 'enumsortorder': 1}]}}
COMPOSITE = {'schema': 'service', 'name': 'addr', 'oid': 56396,
             'comment': None,
             'catalog_row': {'typname': 'addr', 'typtype': 'c',
                             'typrelid': '56395'}}
ATTRIBUTES = {56395: [{'attname': 'street', 'formatted_type': 'text'},
                      {'attname': 'zip', 'formatted_type':
                       'character varying(10)'},
                      {'attname': 'old', 'formatted_type': 'text',
                       'attisdropped': True}]}


def compile_kind(kind, operation, draft, native):
    native = dict(native)
    if kind == 'domain':
        native['domain_facts'] = domain_facts(native, CONSTRAINTS)
    else:
        native['type_facts'] = type_facts(native, ATTRIBUTES)
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft, native=None):
    native = native or (DOMAIN if kind == 'domain' else ENUM)
    return compile_kind(kind, operation, draft, native)['statement'].split(
        ';\n')


def test_domain_facts_list_their_check_constraints():
    facts = domain_facts(DOMAIN, CONSTRAINTS)
    assert facts['constraints'] == [{
        'conname': 'code_check', 'consrc': "((VALUE)::text <> ''::text)",
        'convalidated': False}]
    assert (facts['typnotnull'], facts['typdefault'], facts['basensp']) == (
        True, "'x'::character varying", 'service')


def test_type_facts_order_enum_values_and_skip_dropped_attributes():
    assert type_facts(ENUM)['enum'] == [{'label': 'sad'}, {'label': 'ok'}]
    assert type_facts(COMPOSITE, ATTRIBUTES)['composite'] == [
        {'member_name': 'street', 'type': 'text'},
        {'member_name': 'zip', 'type': 'character varying(10)'}]
    assert type_facts(COMPOSITE)['kind'] == 'composite'


def test_domain_create_with_every_clause():
    from pglast import parse_sql
    text = compile_kind('domain', 'create', {
        'name': 'pos code', 'basensp': 'Mixed schema',
        'basetype': 'character varying(10)', 'collname': '"C"',
        'typdefault': "'x'", 'typnotnull': True, 'owner': 'app_owner',
        'description': "it's",
        'constraints': [{'conname': 'not blank', 'consrc': "VALUE <> ''",
                         'convalidated': False},
                        {'consrc': 'length(VALUE) < 10'}]}, DOMAIN)[
        'statement']
    assert text.split(';\n') == [
        # The parser spells the admitted type canonically.
        'CREATE DOMAIN "Mixed schema"."pos code" AS varchar(10) '
        "COLLATE \"C\" DEFAULT 'x' NOT NULL",
        'ALTER DOMAIN "Mixed schema"."pos code" OWNER TO "app_owner"',
        'ALTER DOMAIN "Mixed schema"."pos code" ADD CONSTRAINT "not blank" '
        "CHECK (VALUE <> '') NOT VALID",
        'ALTER DOMAIN "Mixed schema"."pos code" ADD CHECK '
        '(length(VALUE) < 10)',
        'COMMENT ON DOMAIN "Mixed schema"."pos code" IS \'it\'\'s\'']
    assert len(parse_sql(text)) == 5


def test_domain_alter_emits_only_differences():
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('domain', 'alter', {
            'name': 'code', 'basensp': 'service', 'typnotnull': True,
            'typdefault': "'x'::character varying", 'description': 'codes'},
            DOMAIN)
    assert statements('domain', 'alter', {
        'name': 'ticket_code', 'basensp': 'archive', 'typnotnull': False,
        'typdefault': '', 'owner': 'dba', 'description': '',
        'drop_constraints': [{'conname': 'code_check'}],
        'validate_constraints': [{'conname': 'later'}],
        'add_constraints': [{'conname': 'later', 'consrc': 'VALUE <> \'z\'',
                             'convalidated': False}]}) == [
        'ALTER DOMAIN "service"."code" RENAME TO "ticket_code"',
        'ALTER DOMAIN "service"."ticket_code" DROP NOT NULL',
        'ALTER DOMAIN "service"."ticket_code" DROP DEFAULT',
        'ALTER DOMAIN "service"."ticket_code" OWNER TO "dba"',
        'ALTER DOMAIN "service"."ticket_code" DROP CONSTRAINT "code_check"',
        'ALTER DOMAIN "service"."ticket_code" VALIDATE CONSTRAINT "later"',
        'ALTER DOMAIN "service"."ticket_code" ADD CONSTRAINT "later" CHECK '
        "(VALUE <> 'z') NOT VALID",
        'COMMENT ON DOMAIN "service"."ticket_code" IS NULL',
        'ALTER DOMAIN "service"."ticket_code" SET SCHEMA "archive"']


def test_domain_drop_needs_the_typed_name():
    assert statements('domain', 'drop', {'confirmation': 'code',
                                         'cascade': True}) == [
        'DROP DOMAIN "service"."code" CASCADE']
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_kind('domain', 'drop', {'confirmation': 'x'}, DOMAIN)


def test_type_create_for_each_kind():
    from pglast import parse_sql
    enum = compile_kind('type', 'create', {
        'name': 'mood', 'schema': 'service', 'typtype': 'e',
        'enum': [{'label': 'sad'}, {'label': "it's"}],
        'typeowner': 'app_owner', 'description': 'how'}, ENUM)['statement']
    assert enum.split(';\n') == [
        'CREATE TYPE "service"."mood" AS ENUM (\'sad\', \'it\'\'s\')',
        'ALTER TYPE "service"."mood" OWNER TO "app_owner"',
        'COMMENT ON TYPE "service"."mood" IS \'how\'']
    composite = compile_kind('type', 'create', {
        'name': 'addr', 'schema': 'service', 'typtype': 'c',
        'composite': [{'member_name': 'street', 'type': 'text'},
                      {'member_name': 'zip', 'type': 'varchar(10)',
                       'collation': '"C"'}]}, ENUM)['statement']
    assert composite == ('CREATE TYPE "service"."addr" AS ("street" text, '
                         '"zip" varchar(10) COLLATE "C")')
    range_type = compile_kind('type', 'create', {
        'name': 'floatrange', 'schema': 'service', 'typtype': 'r',
        'typname': 'float8', 'rngsubdiff': 'float8mi',
        'rngmultirangetype': 'floatmulti'}, ENUM)['statement']
    assert range_type == ('CREATE TYPE "service"."floatrange" AS RANGE '
                          '(SUBTYPE = float8, SUBTYPE_DIFF = float8mi, '
                          'MULTIRANGE_TYPE_NAME = floatmulti)')
    for text in (enum, composite, range_type):
        assert len(parse_sql(text)) >= 1


@pytest.mark.parametrize('draft, message', [
    ({'typtype': 'b'}, 'external and shell'),
    ({'typtype': 'c', 'composite': []}, 'at least one member'),
    ({'typtype': 'e', 'enum': [{'label': 'a'}, {'label': 'a'}]}, 'repeats'),
    ({'typtype': 'c', 'composite': [{'member_name': 'x',
                                     'type': 'text; DROP'}]}, 'type'),
    ({'typtype': 'r', 'typname': 'float8', 'rngsubdiff': 'f(); --'},
     'catalog reference'),
])
def test_type_create_refusals(draft, message):
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_kind('type', 'create', {'name': 't', 'schema': 's', **draft},
                     ENUM)


def test_enum_alter_adds_and_renames_values_in_order():
    assert statements('type', 'alter', {
        'name': 'feeling', 'description': 'x',
        'rename_values': [{'from': 'ok', 'to': 'fine'}],
        'add_values': [{'label': 'great', 'after': 'fine'},
                       {'label': 'awful', 'before': 'sad'}]}) == [
        "ALTER TYPE \"service\".\"mood\" RENAME VALUE 'ok' TO 'fine'",
        "ALTER TYPE \"service\".\"mood\" ADD VALUE 'great' AFTER 'fine'",
        "ALTER TYPE \"service\".\"mood\" ADD VALUE 'awful' BEFORE 'sad'",
        'COMMENT ON TYPE "service"."mood" IS \'x\'',
        'ALTER TYPE "service"."mood" RENAME TO "feeling"']
    with pytest.raises(PostgreSQLNativeAdminError, match='already has'):
        compile_kind('type', 'alter', {'add_values': [{'label': 'sad'}]},
                     ENUM)
    with pytest.raises(PostgreSQLNativeAdminError, match='no value'):
        compile_kind('type', 'alter', {'rename_values': [
            {'from': 'nope', 'to': 'x'}]}, ENUM)
    with pytest.raises(PostgreSQLNativeAdminError, match='only an enum'):
        compile_kind('type', 'alter', {'add_values': [{'label': 'x'}]},
                     COMPOSITE)


def test_composite_alter_changes_attributes():
    assert statements('type', 'alter', {
        'schema': 'archive',
        'drop_attributes': [{'member_name': 'zip'}],
        'rename_attributes': [{'member_name': 'street', 'to': 'road'}],
        'alter_attributes': [{'member_name': 'road', 'type': 'varchar(80)'}],
        'add_attributes': [{'member_name': 'city', 'type': 'text'}]},
        COMPOSITE) == [
        'ALTER TYPE "service"."addr" DROP ATTRIBUTE "zip"',
        'ALTER TYPE "service"."addr" RENAME ATTRIBUTE "street" TO "road"',
        'ALTER TYPE "service"."addr" ALTER ATTRIBUTE "road" SET DATA TYPE '
        'varchar(80)',
        'ALTER TYPE "service"."addr" ADD ATTRIBUTE "city" text',
        'ALTER TYPE "service"."addr" SET SCHEMA "archive"']
    with pytest.raises(PostgreSQLNativeAdminError, match='no attribute'):
        compile_kind('type', 'alter', {'drop_attributes': [
            {'member_name': 'nope'}]}, COMPOSITE)
    with pytest.raises(PostgreSQLNativeAdminError, match='only a composite'):
        compile_kind('type', 'alter', {'drop_attributes': [
            {'member_name': 'x'}]}, ENUM)


def test_type_drop_and_forms_and_routes():
    assert statements('type', 'drop', {'confirmation': 'mood'}) == [
        'DROP TYPE "service"."mood" RESTRICT']

    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in type_form('create', field)['fields']}
    assert create['typtype']['default'] == 'e'
    assert create['enum']['visible_when'] == {'field_id': 'typtype',
                                              'equals': 'e'}
    alter = {f['field_id']: f for f in domain_form('alter', field)['fields']}
    assert alter['typdefault']['initial_value_path'] == [
        'domain_facts', 'typdefault']
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    for kind in ('domain', 'type'):
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes == {
            'create': 'provider-native', 'alter': 'provider-native',
            'drop': 'provider-native', 'inspect': 'legacy-preserved'}, kind
