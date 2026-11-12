"""PostgreSQL view and materialized view create/alter/drop compile to exact
native statements (M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.views import facts, form, query

VIEW = {'schema': 'service', 'name': 'open_work_orders', 'comment': None,
        'definition': ' SELECT w.id FROM service.work_orders w;',
        'catalog_row': {'relname': 'open_work_orders', 'relkind': 'v',
                        'reloptions': ['check_option=local',
                                       'security_barrier=true']}}
MVIEW = {'schema': 'service', 'name': 'workload', 'comment': 'per tech',
         'definition': 'SELECT technician, count(*) FROM service.work_orders '
                       'GROUP BY technician',
         'catalog_row': {'relname': 'workload', 'relkind': 'm',
                         'reloptions': ['fillfactor=70'],
                         'relispopulated': True}}


def compile_kind(kind, operation, draft, native):
    native = dict(native, view_facts=facts(native))
    return compile_native_admin({
        'resource_kind': kind, 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def statements(kind, operation, draft, native=None):
    native = native or (VIEW if kind == 'view' else MVIEW)
    return compile_kind(kind, operation, draft, native)['statement'].split(
        ';\n')


def test_facts_decode_the_options_and_trim_the_definition():
    view = facts(VIEW)
    assert (view['definition'], view['check_option'], view['security_barrier'],
            view['security_invoker']) == (
        'SELECT w.id FROM service.work_orders w', 'local', True, False)
    assert (facts(MVIEW)['fillfactor'], facts(MVIEW)['with_data']) == (
        70, True)


def test_query_is_one_select_by_the_parser():
    assert query(' SELECT 1 ; ') == 'SELECT 1'
    assert query('VALUES (1), (2)') == 'VALUES (1), (2)'
    for bad in ('SELECT 1; DROP TABLE t', 'DELETE FROM t', 'SELECT (1',
                'SELECT 1 -- x', '', 'TRUNCATE t'):
        with pytest.raises(PostgreSQLNativeAdminError):
            query(bad)


def test_view_create_with_options_owner_and_comment():
    from pglast import parse_sql
    text = compile_kind('view', 'create', {
        'name': 'mine', 'schema': 'Mixed schema',
        'definition': 'SELECT id FROM t WHERE owner = CURRENT_USER;',
        'check_option': 'cascaded', 'security_barrier': True,
        'security_invoker': True, 'owner': 'app_owner',
        'comment': "it's"}, VIEW)['statement']
    assert text.split(';\n') == [
        'CREATE VIEW "Mixed schema"."mine" WITH (check_option=cascaded, '
        'security_barrier=true, security_invoker=true) AS SELECT id FROM t '
        'WHERE owner = CURRENT_USER',
        'ALTER TABLE "Mixed schema"."mine" OWNER TO "app_owner"',
        'COMMENT ON VIEW "Mixed schema"."mine" IS \'it\'\'s\'']
    assert len(parse_sql(text)) == 3
    assert statements('view', 'create', {
        'name': 'v', 'schema': 's', 'definition': 'SELECT 1',
        'check_option': 'no', 'security_barrier': False,
        'security_invoker': False}) == ['CREATE VIEW "s"."v" AS SELECT 1']


def test_view_alter_replaces_or_sets_options():
    assert statements('view', 'alter', {
        'name': 'open_work_orders', 'schema': 'service',
        'definition': 'SELECT w.id FROM service.work_orders w',
        'check_option': 'no', 'security_barrier': False,
        'security_invoker': True, 'comment': 'open'}) == [
        'ALTER VIEW "service"."open_work_orders" SET (security_barrier=false,'
        ' security_invoker=true)',
        'ALTER VIEW "service"."open_work_orders" RESET (check_option)',
        'COMMENT ON VIEW "service"."open_work_orders" IS \'open\'']
    assert statements('view', 'alter', {
        'name': 'open', 'schema': 'archive', 'owner': 'dba',
        'definition': 'SELECT w.id, w.state FROM service.work_orders w',
        'check_option': None, 'security_barrier': None}) == [
        'ALTER VIEW "service"."open_work_orders" RENAME TO "open"',
        'ALTER VIEW "service"."open" SET SCHEMA "archive"',
        'ALTER TABLE "archive"."open" OWNER TO "dba"',
        'CREATE OR REPLACE VIEW "archive"."open" WITH (check_option=local, '
        'security_barrier=true) AS SELECT w.id, w.state FROM '
        'service.work_orders w']
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_kind('view', 'alter', {'name': 'open_work_orders'}, VIEW)
    with pytest.raises(PostgreSQLNativeAdminError, match='no, local'):
        compile_kind('view', 'alter', {'check_option': 'maybe'}, VIEW)


def test_materialized_view_create_and_alter():
    assert statements('materialized-view', 'create', {
        'name': 'load', 'schema': 's', 'definition': 'SELECT 1 AS n',
        'with_data': False, 'fillfactor': 80, 'spcname': 'fast',
        'amname': 'heap', 'owner': 'dba', 'comment': 'c'}) == [
        'CREATE MATERIALIZED VIEW "s"."load" USING "heap" WITH '
        '(fillfactor=80) TABLESPACE "fast" AS SELECT 1 AS n WITH NO DATA',
        'ALTER TABLE "s"."load" OWNER TO "dba"',
        'COMMENT ON MATERIALIZED VIEW "s"."load" IS \'c\'']
    assert statements('materialized-view', 'alter', {
        'name': 'workload', 'schema': 'service', 'spcname': 'fast',
        'fillfactor': 70, 'reset_fillfactor': True, 'comment': ''}) == [
        'ALTER MATERIALIZED VIEW "service"."workload" SET TABLESPACE "fast"',
        'ALTER MATERIALIZED VIEW "service"."workload" RESET (fillfactor)',
        'COMMENT ON MATERIALIZED VIEW "service"."workload" IS NULL']
    # A changed query drops and recreates, keeping the fill factor and the
    # populated state unless the draft says otherwise.
    assert statements('materialized-view', 'alter', {
        'definition': 'SELECT technician FROM service.work_orders',
        'fillfactor': 70, 'with_data': None}) == [
        'DROP MATERIALIZED VIEW "service"."workload"',
        'CREATE MATERIALIZED VIEW "service"."workload" WITH (fillfactor=70) '
        'AS SELECT technician FROM service.work_orders WITH DATA']
    with pytest.raises(PostgreSQLNativeAdminError, match='10 to 100'):
        compile_kind('materialized-view', 'alter', {'fillfactor': 5}, MVIEW)
    with pytest.raises(PostgreSQLNativeAdminError, match='access method'):
        compile_kind('materialized-view', 'create', {
            'name': 'm', 'schema': 's', 'definition': 'SELECT 1',
            'amname': 'heap; drop'}, MVIEW)


def test_drop_needs_the_typed_name():
    assert statements('view', 'drop', {'confirmation': 'open_work_orders',
                                       'cascade': True}) == [
        'DROP VIEW "service"."open_work_orders" CASCADE']
    assert statements('materialized-view', 'drop',
                      {'confirmation': 'workload'}) == [
        'DROP MATERIALIZED VIEW "service"."workload" RESTRICT']
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_kind('view', 'drop', {'confirmation': 'x'}, VIEW)


def test_forms_and_routes():
    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    view = {f['field_id']: f for f in form('view', 'alter', field)['fields']}
    assert view['check_option']['initial_value_path'] == [
        'view_facts', 'check_option']
    mview = {f['field_id']: f for f in form('materialized-view', 'create',
                                           field)['fields']}
    assert 'with_data' in mview and 'amname' in mview
    # Every family field id is admitted (owner direction 2026-11-11).
    import json, pathlib
    family = json.loads(pathlib.Path(
        'web/pgadmin/cdeadmin/ui_descriptors/postgresql/forms/'
        'view.form.json').read_text())
    for operation, served in (('alter', view), ('create', mview)):
        for item in family['fields']:
            if not item.get('modes') or operation in item['modes']:
                assert item['field_id'] in served, (operation, item['field_id'])
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    for kind in ('view', 'materialized-view'):
        resource = next(item for item in catalog['objects']
                        if item['resource_kind'] == kind)
        routes = {op['operation_id']: op['execution_route']
                  for op in resource['operations']}
        assert routes['create'] == routes['alter'] == routes['drop'] == \
            'provider-native', kind
        assert routes['inspect'] == 'legacy-preserved', kind
    assert routes['refresh'] == 'provider-native'


def test_privileges_labels_storage_and_dependencies():
    # Views: word privileges, a revoke and a label; dependencies refused.
    assert statements('view', 'alter', {
        'revoke': [{'grantee': 'public'}],
        'datacl': [{'grantee': 'reader', 'privileges': ['SELECT']}],
        'seclabels': [{'provider': 'selinux', 'label': 'x'}]}) == [
        'REVOKE ALL ON TABLE "service"."open_work_orders" FROM PUBLIC',
        'GRANT SELECT ON TABLE "service"."open_work_orders" TO "reader"',
        'SECURITY LABEL FOR "selinux" ON VIEW "service"."open_work_orders" '
        "IS 'x'"]
    with pytest.raises(PostgreSQLNativeAdminError, match='materialized'):
        compile_kind('view', 'alter', {'dependsonextensions': ['plpgsql']},
                     VIEW)
    # Materialized views: TOAST tuple target, autovacuum grids and an
    # extension dependency on create; the same again as a diff on alter.
    assert statements('materialized-view', 'create', {
        'name': 'm', 'schema': 's', 'definition': 'SELECT 1', 'fillfactor': 80,
        'toast_tuple_target': 256, 'autovacuum_enabled': 'f',
        'autovacuum_custom': True,
        'vacuum_table': [{'label': 'autovacuum_vacuum_threshold',
                          'value': 100}],
        'dependsonextensions': ['plpgsql']}) == [
        'CREATE MATERIALIZED VIEW "s"."m" WITH (fillfactor=80, '
        'toast_tuple_target=256, autovacuum_enabled=false, '
        'autovacuum_vacuum_threshold=100) AS SELECT 1 WITH DATA',
        'ALTER MATERIALIZED VIEW "s"."m" DEPENDS ON EXTENSION "plpgsql"']
    current = facts(MVIEW)
    assert (current['autovacuum_enabled'], current['autovacuum_custom'],
            current['toast_tuple_target']) == ('x', False, None)
    assert statements('materialized-view', 'alter', {
        'toast_tuple_target': 512, 'autovacuum_enabled': 't',
        'reset_fillfactor': True}) == [
        'ALTER MATERIALIZED VIEW "service"."workload" SET '
        '(toast_tuple_target=512, autovacuum_enabled=true)',
        'ALTER MATERIALIZED VIEW "service"."workload" RESET (fillfactor)']
    with pytest.raises(PostgreSQLNativeAdminError, match='not known'):
        compile_kind('materialized-view', 'alter', {'amname': 'heap2'},
                     MVIEW)
    known = dict(MVIEW, catalog_row=dict(MVIEW['catalog_row'],
                                         access_method_name='heap'))
    assert statements('materialized-view', 'alter', {'amname': 'heap2'},
                      known) == [
        'ALTER MATERIALIZED VIEW "service"."workload" SET ACCESS METHOD '
        '"heap2"']
    # A recreate keeps the current storage parameters under the changes.
    assert statements('materialized-view', 'alter', {
        'definition': 'SELECT 2', 'toast_tuple_target': 300})[1] == (
        'CREATE MATERIALIZED VIEW "service"."workload" WITH (fillfactor=70, '
        'toast_tuple_target=300) AS SELECT 2 WITH DATA')
