"""PostgreSQL row-security policy create/alter/drop compile to exact native
statements (M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.policies import (
    expression, facts, form,
)

NATIVE = {'schema': 'service', 'name': 'visible rows', 'comment': None,
          'catalog_row': {'polname': 'visible rows', 'polrelid': '16393',
                          'polcmd': 'r', 'polpermissive': True,
                          'roles_sql': ['public'],
                          'using_sql': '(owner = CURRENT_USER)',
                          'check_sql': None},
          'policy_facts': {'schema': 'service', 'table': 'assets'}}
RELATIONS = {16393: ('service', 'assets')}


def compile_policy(operation, draft, native=None):
    native = dict(NATIVE if native is None else native)
    native['policy_facts'] = facts(native, RELATIONS)
    return compile_native_admin({
        'resource_kind': 'row-policy', 'operation_id': operation,
        'draft': {**draft, **({} if operation == 'create' else {
            'schema': native['policy_facts']['schema'],
            'table': native['policy_facts']['table']})},
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(operation, draft, native=None):
    return compile_policy(operation, draft, native)['statement'].split(';\n')


def test_facts_resolve_the_table_and_decode_the_command():
    assert facts(NATIVE, RELATIONS) == {
        'name': 'visible rows', 'schema': 'service', 'table': 'assets',
        'type': 'PERMISSIVE', 'event': 'SELECT', 'roles': ['public'],
        'using': '(owner = CURRENT_USER)', 'withcheck': None,
        'description': None}
    assert facts(NATIVE)['table'] is None


def test_expressions_are_admitted_by_the_parser_only():
    assert expression(' owner = CURRENT_USER ', 'USING') == \
        'owner = CURRENT_USER'
    assert expression('(SELECT count(*) FROM t) > 0', 'USING')
    for bad in ('1); DROP TABLE t; --', 'a) OR (b', 'x /* y */', '',
                '(a', 'a +'):
        with pytest.raises(PostgreSQLNativeAdminError):
            expression(bad, 'USING')


def test_create_with_every_clause():
    from pglast import parse_sql
    text = compile_policy('create', {
        'name': 'own rows', 'schema': 'Mixed schema', 'table': 'assets',
        'type': 'restrictive', 'event': 'update',
        'policyowner': 'app_owner, public',
        'using': 'owner = CURRENT_USER', 'withcheck': 'asset_id > 0',
        'description': "it's"})['statement']
    assert text.split(';\n') == [
        'CREATE POLICY "own rows" ON "Mixed schema"."assets" AS RESTRICTIVE '
        'FOR UPDATE TO "app_owner", PUBLIC USING (owner = CURRENT_USER) '
        'WITH CHECK (asset_id > 0)',
        'COMMENT ON POLICY "own rows" ON "Mixed schema"."assets" IS '
        "'it''s'"]
    assert len(parse_sql(text)) == 2


@pytest.mark.parametrize('draft, message', [
    ({'event': 'INSERT', 'using': 'true'}, 'no USING'),
    ({'event': 'SELECT', 'withcheck': 'true'}, 'no WITH CHECK'),
    ({'type': 'sometimes'}, 'PERMISSIVE or RESTRICTIVE'),
    ({'event': 'MERGE'}, 'one of'),
    ({'policyowner': [1]}, 'role'),
])
def test_create_refusals(draft, message):
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_policy('create', {'name': 'p', 'schema': 's', 'table': 't',
                                  **draft})


def test_alter_changes_only_what_differs_and_keeps_as_and_for():
    assert statements('alter', {
        'name': 'visible rows', 'policyowner': '',
        'using': '(owner = CURRENT_USER)', 'withcheck': None,
        'description': 'who sees what'}) == [
        'COMMENT ON POLICY "visible rows" ON "service"."assets" IS '
        "'who sees what'"]
    assert statements('alter', {
        'name': 'mine', 'policyowner': 'app_owner',
        'using': 'owner = CURRENT_USER AND NOT archived',
        'description': ''}) == [
        'ALTER POLICY "visible rows" ON "service"."assets" TO "app_owner" '
        'USING (owner = CURRENT_USER AND NOT archived)',
        'ALTER POLICY "visible rows" ON "service"."assets" RENAME TO "mine"']
    with pytest.raises(PostgreSQLNativeAdminError, match='fixed'):
        compile_policy('alter', {'event': 'ALL'})
    with pytest.raises(PostgreSQLNativeAdminError, match='removed in place'):
        compile_policy('alter', {'using': ''})
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_policy('alter', {'name': 'visible rows'})


def test_drop_needs_the_typed_name():
    assert statements('drop', {'confirmation': 'visible rows'}) == [
        'DROP POLICY "visible rows" ON "service"."assets"']
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_policy('drop', {'confirmation': 'other'})


def test_forms_and_catalog_route():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in form('create', field)['fields']}
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    assert set(create) == {'name', 'schema', 'table', 'type', 'event',
                           'policyowner', 'using', 'withcheck', 'description'}
    assert set(alter) == {'name', 'policyowner', 'using', 'withcheck',
                          'description'}
    assert alter['using']['initial_value_path'] == ['policy_facts', 'using']
    assert create['type']['default'] == 'PERMISSIVE'
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    policy = next(item for item in catalog['objects']
                  if item['resource_kind'] == 'row-policy')
    assert {op['operation_id']: op['execution_route']
            for op in policy['operations']} == {
        'create': 'provider-native', 'alter': 'provider-native',
        'drop': 'provider-native', 'inspect': 'legacy-preserved'}
