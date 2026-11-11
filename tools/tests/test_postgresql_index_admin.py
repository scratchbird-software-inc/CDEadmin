"""PostgreSQL index create/alter/drop compile to exact native statements
(M4)."""
import pytest
from pgadmin.cdeadmin.providers.postgresql.native_admin import (
    compile_native_admin, PostgreSQLNativeAdminError,
)
from pgadmin.cdeadmin.providers.postgresql.indexes import facts, form

INDEX = {'schema': 'service', 'name': 'ix_orders', 'comment': None,
         'definition': 'CREATE UNIQUE INDEX ix_orders ON service.work_orders '
                       'USING btree (lower(status) COLLATE "C" '
                       'text_pattern_ops DESC NULLS FIRST, priority) INCLUDE '
                       "(technician) WITH (fillfactor='70') "
                       'WHERE (priority > 1)',
         'catalog_row': {'relname': 'ix_orders'}}


def compile_index(operation, draft, native=INDEX):
    native = dict(native, index_facts=facts(native))
    return compile_native_admin({
        'resource_kind': 'index', 'operation_id': operation, 'draft': draft,
        'target_resource': {'extensions': {'postgresql': {'native': native}}}})


def test_facts_read_the_definition_back_through_the_parser():
    current = facts(INDEX)
    assert current['definition_parsed'] and current['table'] == 'work_orders'
    assert (current['amname'], current['indisunique'], current['include'],
            current['indconstraint']) == ('btree', True, ['technician'],
                                          'priority > 1')
    assert current['columns'] == [
        {'colname': 'lower(status)', 'is_exp': True, 'collspcname': '"C"',
         'op_class': '"text_pattern_ops"', 'sort_order': 'DESC',
         'nulls': 'FIRST'},
        {'colname': 'priority', 'is_exp': False, 'collspcname': None,
         'op_class': None, 'sort_order': None, 'nulls': None}]
    assert current['storage_parameters'] == [{'name': 'fillfactor',
                                              'value': '70'}]
    assert facts({'definition': 'nope', 'catalog_row': {}})[
        'definition_parsed'] is False


def test_create_with_every_clause():
    from pglast import parse_sql
    compiled = compile_index('create', {
        'name': 'ix one', 'schema': 'Sch ema', 'table': 'orders',
        'amname': 'GIST', 'indisunique': True, 'indnullsnotdistinct': True,
        'indisonly': True,
        'columns': [{'colname': 'lower(email)', 'is_exp': True,
                     'collspcname': '"C"', 'op_class': 'text_pattern_ops',
                     'sort_order': 'desc', 'nulls': 'first'},
                    {'colname': 'status'}],
        'include': [{'colname': 'id'}, 'note'], 'fillfactor': 70,
        'storage_parameters': [{'name': 'buffering', 'value': 'on'}],
        'spcname': 'fast', 'indconstraint': "status <> 'x'",
        'description': "it's"})
    assert compiled['statement'].split(';\n') == [
        'CREATE UNIQUE INDEX "ix one" ON ONLY "Sch ema"."orders" USING gist '
        '((lower(email)) COLLATE "C" text_pattern_ops DESC NULLS FIRST, '
        '"status") INCLUDE ("id", "note") NULLS NOT DISTINCT WITH '
        '(fillfactor=70, buffering=on) TABLESPACE "fast" WHERE '
        "status <> 'x'",
        'COMMENT ON INDEX "Sch ema"."ix one" IS \'it\'\'s\'']
    assert 'autocommit' not in compiled
    assert len(parse_sql(compiled['statement'])) == 2
    concurrent = compile_index('create', {
        'name': 'i', 'schema': 's', 'table': 't', 'isconcurrent': True,
        'columns': [{'colname': 'c'}]})
    assert concurrent == {'statement': 'CREATE INDEX CONCURRENTLY "i" ON '
                                       '"s"."t" ("c")',
                          'read_only': False, 'autocommit': True}


@pytest.mark.parametrize('draft, message', [
    ({'columns': []}, 'at least one column'),
    ({'columns': [{'colname': 'a', 'sort_order': 'up'}]}, 'ASC or DESC'),
    ({'columns': [{'colname': 'a', 'nulls': 'middle'}]}, 'FIRST or LAST'),
    ({'columns': [{'colname': 'a); drop', 'is_exp': True}]}, 'unsafe'),
    ({'columns': [{'colname': 'a'}], 'amname': 'btree; drop'},
     'method name'),
    ({'columns': [{'colname': 'a'}], 'storage_parameters': [
        {'name': 'fillfactor', 'value': '70; drop'}]}, 'plain word'),
    ({'columns': [{'colname': 'a'}], 'isconcurrent': True,
      'description': 'x'}, 'runs alone'),
    ({'columns': [{'colname': 'a'}], 'indconstraint': 'a) or (b'},
     'unsafe'),
])
def test_create_refusals(draft, message):
    with pytest.raises(PostgreSQLNativeAdminError, match=message):
        compile_index('create', {'name': 'i', 'schema': 's', 'table': 't',
                                 **draft})


def test_alter_changes_what_can_change_in_place():
    current = facts(INDEX)
    assert compile_index('alter', {
        'name': 'ix_orders_v2', 'columns': current['columns'],
        'spcname': 'fast', 'fillfactor': 90,
        'storage_parameters': [{'name': 'deduplicate_items', 'value': False}],
        'reset_parameters': [{'name': 'buffering'}],
        'indisclustered': True, 'description': 'orders'})['statement'] == \
        '\n'.join([
            'ALTER INDEX "service"."ix_orders" RENAME TO "ix_orders_v2";',
            'ALTER INDEX "service"."ix_orders_v2" SET TABLESPACE "fast";',
            'ALTER INDEX "service"."ix_orders_v2" SET (fillfactor=90, '
            'deduplicate_items=off);',
            'ALTER INDEX "service"."ix_orders_v2" RESET (buffering);',
            'ALTER TABLE "service"."work_orders" CLUSTER ON "ix_orders_v2";',
            'COMMENT ON INDEX "service"."ix_orders_v2" IS \'orders\''])
    with pytest.raises(PostgreSQLNativeAdminError, match='nothing to change'):
        compile_index('alter', {'name': 'ix_orders', 'fillfactor': 70})
    with pytest.raises(PostgreSQLNativeAdminError, match='fixed once'):
        compile_index('alter', {'columns': [{'colname': 'other'}]})


def test_drop_plain_and_concurrent():
    assert compile_index('drop', {'confirmation': 'ix_orders',
                                  'cascade': True}) == {
        'statement': 'DROP INDEX "service"."ix_orders" CASCADE',
        'read_only': False}
    assert compile_index('drop', {'confirmation': 'ix_orders',
                                  'concurrently': True}) == {
        'statement': 'DROP INDEX CONCURRENTLY "service"."ix_orders"',
        'read_only': False, 'autocommit': True}
    with pytest.raises(PostgreSQLNativeAdminError, match='CASCADE'):
        compile_index('drop', {'confirmation': 'ix_orders',
                               'concurrently': True, 'cascade': True})
    with pytest.raises(PostgreSQLNativeAdminError, match='confirmation'):
        compile_index('drop', {'confirmation': 'x'})


def test_reindex_still_routes_to_maintenance_and_forms_follow_ids():
    compiled = compile_native_admin({
        'resource_kind': 'index', 'operation_id': 'reindex', 'draft': {},
        'target_resource': {'extensions': {'postgresql': {'native': {
            'schema': 's', 'name': 'i'}}}}})
    assert compiled['statement'] == 'REINDEX INDEX "s"."i"'

    def field(field_id, label, control='text', required=False, **extra):
        return {'field_id': field_id, 'label': label, 'control': control,
                'required': required, **extra}
    create = {f['field_id']: f for f in form('create', field)['fields']}
    alter = {f['field_id']: f for f in form('alter', field)['fields']}
    assert create['columns']['required'] and 'amname' in create
    assert alter['columns']['initial_value_path'] == ['index_facts',
                                                      'columns']
    from pgadmin.cdeadmin.providers.postgresql.preserved_surface import (
        adapt_catalog)
    catalog = adapt_catalog({'objects': []})
    index = next(item for item in catalog['objects']
                 if item['resource_kind'] == 'index')
    routes = {op['operation_id']: op['execution_route']
              for op in index['operations']}
    assert routes == {'create': 'provider-native', 'alter': 'provider-native',
                      'drop': 'provider-native',
                      'inspect': 'legacy-preserved',
                      'reindex': 'provider-native'}
