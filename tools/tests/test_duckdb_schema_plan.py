"""DuckDB DDN previews require explicit identity, grammar and three-way state."""

from copy import deepcopy

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import _resource_id
from pgadmin.cdeadmin.workspace.duckdb_schema_plan import plan


def row(kind, path, *, ddl=None, change=None):
    name = path[-1]
    native = {'system_object': False, 'catalog_metadata': {}}
    if ddl is not None: native['ddl'] = ddl
    if change is not None: native['duckdb_change'] = change
    return {'resource_id': _resource_id(kind, path[:-1], name), 'kind': kind,
        'name': name, 'path': path, 'system': 'false', 'native': native}


def model(*rows, endpoint='owned', target='file'):
    root = row('database', ['file'])
    return {'provenance': {'mapping': 'scratchrobin.duckdb.catalog@1',
        'endpoint_id': endpoint, 'database_target_id': target},
        'rows': {item['resource_id']: item for item in (root, *rows)}}


def test_create_plan_is_qualified_parsed_and_never_executes():
    pytest.importorskip('duckdb')
    addition = row('table', ['file', 'main', 'facts'],
        ddl='CREATE TABLE "file"."main"."facts" ("x" INTEGER)')
    result = plan(model(), model(addition), model())
    assert result['ready_for_review'] and result['application_supported']
    assert result['operations'][0]['operation'] == 'create'
    assert result['operations'][0]['source'] == addition['native']['ddl']
    assert not result['executed'] and result['native_grammar_validated']


def test_missing_row_does_not_drop_and_explicit_drop_is_separate():
    existing = row('table', ['file', 'main', 'facts'],
        ddl='CREATE TABLE "file"."main"."facts" ("x" INTEGER)')
    ignored = plan(model(existing), model(), model(existing))
    assert ignored['operations'] == [] and ignored['ignored'][0]['resource_id'] == existing['resource_id']
    drop = deepcopy(existing)
    drop['native']['duckdb_change'] = {'action': 'drop', 'confirmation': 'facts'}
    result = plan(model(existing), model(drop), model(existing))
    assert result['operations'][0]['source'] == 'DROP TABLE "file"."main"."facts" RESTRICT'


def test_stale_live_definition_and_foreign_scope_are_refused():
    before = row('view', ['file', 'main', 'report'],
        ddl='CREATE VIEW "file"."main"."report" AS SELECT 1')
    desired = deepcopy(before)
    desired['native'].update(ddl='CREATE OR REPLACE VIEW "file"."main"."report" AS SELECT 2',
        duckdb_change={'action': 'replace'})
    current = deepcopy(before)
    current['native']['ddl'] = 'CREATE VIEW "file"."main"."report" AS SELECT 3'
    result = plan(model(before), model(desired), model(current))
    assert result['conflicts'] and not result['operations']
    assert plan(model(before), model(desired), model(before))['operations'][0]['operation'] == 'replace'
    with pytest.raises(ValueError, match='another endpoint'):
        plan(model(before, endpoint='foreign'), model(desired), model(before))


@pytest.mark.parametrize('source', [
    'CREATE TABLE "other"."main"."facts" (x INTEGER)',
    'CREATE TABLE "file"."main"."facts" (',
    'CREATE TABLE "file"."main"."facts" (x INTEGER); DROP TABLE "file"."main"."facts"',
])
def test_unqualified_invalid_or_multiple_ddl_is_a_blocker(source):
    addition = row('table', ['file', 'main', 'facts'], ddl=source)
    result = plan(model(), model(addition), model())
    assert result['blockers'] and not result['ready_for_review']
    assert not result['operations']


def test_index_preview_binds_local_name_and_qualified_parent():
    pytest.importorskip('duckdb')
    table = row('table', ['file', 'main', 'facts'],
        ddl='CREATE TABLE "file"."main"."facts" ("x" INTEGER)')
    index = row('index', ['file', 'main', 'facts', 'facts_x'],
        ddl='CREATE INDEX "facts_x" ON "file"."main"."facts"("x")')
    created = plan(model(table), model(table, index), model(table))
    assert created['application_supported'] and created['operations'][0]['kind'] == 'index'
    assert created['operations'][0]['source'] == index['native']['ddl']
    omitted_parent = plan(model(), model(index), model())
    assert omitted_parent['blockers']
    for source in (
            'CREATE INDEX "wrong" ON "file"."main"."facts"("x")',
            'CREATE INDEX "facts_x" ON "main"."facts"("x")',
            index['native']['ddl'] + '; DROP TABLE "file"."main"."facts"'):
        edited = deepcopy(index)
        edited['native']['ddl'] = source
        assert plan(model(table), model(table, edited), model(table))['blockers']
    deleted = deepcopy(index)
    deleted['native']['duckdb_change'] = {'action': 'drop', 'confirmation': 'facts_x'}
    dropped = plan(model(table, index), model(table, deleted), model(table, index))
    assert dropped['application_supported']
    assert dropped['operations'][0]['source'] == 'DROP INDEX "file"."main"."facts_x" RESTRICT'


def test_column_add_and_explicit_drop_use_qualified_parent():
    pytest.importorskip('duckdb')
    table = row('table', ['file', 'main', 'facts'])
    column = row('column', ['file', 'main', 'facts', 'amount'])
    column['native']['catalog_metadata'] = {
        'data_type': 'DECIMAL(18,2)', 'nullable': True, 'default': '0'}
    result = plan(model(table), model(table, column), model(table))
    assert result['application_supported']
    assert result['operations'][0]['source'] == (
        'ALTER TABLE "file"."main"."facts" ADD COLUMN "amount" DECIMAL(18,2) DEFAULT 0')
    assert plan(model(), model(column), model())['blockers']
    for changes in ({'nullable': False}, {'comment': 'not yet admitted'},
                    {'data_type': 'INTEGER DEFAULT 5'}, {'data_type': 'INTEGER; DROP TABLE facts'}):
        edited = deepcopy(column)
        edited['native']['catalog_metadata'].update(changes)
        assert plan(model(table), model(table, edited), model(table))['blockers']
    removed = deepcopy(column)
    removed['native']['duckdb_change'] = {'action': 'drop', 'confirmation': 'amount'}
    drop = plan(model(table, column), model(table, removed), model(table, column))
    assert drop['application_supported']
    assert drop['operations'][0]['source'] == (
        'ALTER TABLE "file"."main"."facts" DROP COLUMN "amount" RESTRICT')
