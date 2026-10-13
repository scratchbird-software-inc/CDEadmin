"""DuckDB DDN previews require explicit identity, grammar and three-way state."""

from copy import deepcopy

import pytest

import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.duckdb.provider import _resource_id
from pgadmin.cdeadmin.workspace.duckdb_schema_plan import plan, view_query_tokens


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


@pytest.mark.parametrize('action', ['create', 'drop', 'set-default', 'rename'])
def test_view_columns_cannot_be_reviewed_as_table_column_mutations(action):
    pytest.importorskip('duckdb')
    view = row('view', ['file', 'main', 'projected'],
        ddl='CREATE VIEW "file"."main"."projected" AS SELECT 1 AS value')
    column = row('column', ['file', 'main', 'projected', 'value'])
    column['native']['catalog_metadata'] = {
        'data_type': 'INTEGER', 'nullable': True, 'default': None}
    baseline = model(view, column)
    desired = deepcopy(baseline)
    if action == 'create':
        added = row('column', ['file', 'main', 'projected', 'extra'])
        added['native']['catalog_metadata'] = {'data_type': 'INTEGER', 'nullable': True}
        desired['rows'][added['resource_id']] = added
    elif action == 'rename':
        renamed = row('column', ['file', 'main', 'projected', 'renamed'],
            change={'action': 'rename', 'from_resource_id': column['resource_id'],
                'confirmation': 'value'})
        renamed['native']['catalog_metadata'] = deepcopy(column['native']['catalog_metadata'])
        desired['rows'][renamed['resource_id']] = renamed
    else:
        changed = desired['rows'][column['resource_id']]['native']
        if action == 'drop':
            changed['duckdb_change'] = {'action': 'drop', 'confirmation': 'value'}
        else:
            changed['duckdb_change'] = {'action': 'set-default'}
            changed['catalog_metadata']['default'] = '2'
    result = plan(baseline, desired, baseline)
    assert not result['application_supported']
    assert any('table' in item['reason'] for item in result['blockers'])


def test_view_postcommit_body_comparison_ignores_header_and_terminal_separator():
    pytest.importorskip('duckdb')
    submitted = 'CREATE OR REPLACE VIEW "file"."main"."report" AS SELECT 2 AS x'
    observed = 'CREATE VIEW report AS SELECT 2 AS x;'
    wrong = 'CREATE VIEW report AS SELECT 3 AS x;'
    assert view_query_tokens(submitted) == view_query_tokens(observed)
    assert view_query_tokens(submitted) != view_query_tokens(wrong)
    assert view_query_tokens(
        'CREATE OR REPLACE VIEW "file"."main"."report" (renamed) AS SELECT 2 AS x'
    ) != view_query_tokens(observed)


def test_missing_row_does_not_drop_and_explicit_drop_is_separate():
    existing = row('table', ['file', 'main', 'facts'],
        ddl='CREATE TABLE "file"."main"."facts" ("x" INTEGER)')
    ignored = plan(model(existing), model(), model(existing))
    assert ignored['operations'] == [] and ignored['ignored'][0]['resource_id'] == existing['resource_id']
    drop = deepcopy(existing)
    drop['native']['duckdb_change'] = {'action': 'drop', 'confirmation': 'facts'}
    result = plan(model(existing), model(drop), model(existing))
    assert result['operations'][0]['source'] == 'DROP TABLE "file"."main"."facts" RESTRICT'


@pytest.mark.parametrize('field,value', [
    ('kind', 'view'),
    ('path', ['file', 'other', 'facts']),
    ('name', 'renamed'),
    ('system', 'true'),
    ('resource_id', 'duckdb:forged'),
])
def test_unchanged_row_identity_tampering_blocks_other_native_operations(field, value):
    existing = row('table', ['file', 'main', 'facts'],
        ddl='CREATE TABLE "file"."main"."facts" (x INTEGER)')
    addition = row('view', ['file', 'main', 'report'],
        ddl='CREATE VIEW "file"."main"."report" AS SELECT 1 AS x')
    baseline = model(existing)
    desired = deepcopy(baseline)
    desired['rows'][existing['resource_id']][field] = value
    desired['rows'][addition['resource_id']] = addition
    result = plan(baseline, desired, baseline)
    assert not result['application_supported']
    assert any('identity changed' in item['reason'] for item in result['blockers'])


def test_sequence_ownership_is_not_admitted_as_durable_design_change():
    table = row('table', ['file', 'main', 'owner_table'],
        ddl='CREATE TABLE "file"."main"."owner_table" (x INTEGER)')
    sequence = row('sequence', ['file', 'main', 'owned_seq'],
        ddl='CREATE SEQUENCE "file"."main"."owned_seq"')
    baseline = model(table, sequence)
    desired = deepcopy(baseline)
    changed = desired['rows'][sequence['resource_id']]['native']
    changed['catalog_metadata']['owner_table'] = ['file', 'main', 'owner_table']
    changed['duckdb_change'] = {'action': 'set-owner',
        'owner_table': ['file', 'main', 'owner_table'],
        'drop_with_table_confirmed': True}
    preview = plan(baseline, desired, baseline)
    assert not preview['application_supported']
    assert preview['operations'] == [] and preview['blockers']


def test_whole_table_replacement_cannot_silently_replace_data_and_dependents():
    original = row('table', ['file', 'main', 'facts'],
        ddl='CREATE TABLE "file"."main"."facts" (id INTEGER)')
    baseline = model(original)
    desired = deepcopy(baseline)
    changed = desired['rows'][original['resource_id']]['native']
    changed['ddl'] = 'CREATE OR REPLACE TABLE "file"."main"."facts" (id VARCHAR)'
    changed['duckdb_change'] = {'action': 'replace-table',
        'data_loss_confirmed': True}
    preview = plan(baseline, desired, baseline)
    assert not preview['application_supported']
    assert preview['operations'] == [] and preview['blockers']


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
    commented = deepcopy(before)
    commented['native']['catalog_metadata']['comment'] = 'preserve'
    commented_desired = deepcopy(desired)
    commented_desired['native']['catalog_metadata']['comment'] = 'preserve'
    assert 'discard native comment' in plan(
        model(commented), model(commented_desired), model(commented))['blockers'][0]['reason']
    with pytest.raises(ValueError, match='another endpoint'):
        plan(model(before, endpoint='foreign'), model(desired), model(before))


@pytest.mark.parametrize('kind,parent,old,new,statement', [
    ('table', ['file', 'main'], 'facts', 'renamed',
     'ALTER TABLE "file"."main"."facts" RENAME TO "renamed"'),
    ('view', ['file', 'main'], 'facts', 'renamed',
     'ALTER VIEW "file"."main"."facts" RENAME TO "renamed"'),
    ('column', ['file', 'main', 'facts'], 'value', 'amount',
     'ALTER TABLE "file"."main"."facts" RENAME COLUMN "value" TO "amount"'),
])
def test_exact_native_rename_binds_old_and_new_identity(kind, parent, old, new, statement):
    pytest.importorskip('duckdb')
    before = row(kind, [*parent, old])
    after = deepcopy(before)
    after.update(name=new, path=[*parent, new],
                 resource_id=_resource_id(kind, parent, new))
    after['native']['duckdb_change'] = {'action': 'rename',
        'from_resource_id': before['resource_id'], 'confirmation': old}
    parents = [row('table', parent)] if kind == 'column' else []
    baseline, desired = model(before, *parents), model(after, *parents)
    result = plan(baseline, desired, baseline)
    assert result['application_supported'], result['blockers']
    assert result['operations'][0]['source'] == statement
    assert result['operations'][0]['source_resource_id'] == before['resource_id']
    assert result['operations'][0]['resource_id'] == after['resource_id']
    wrong = deepcopy(after)
    wrong['native']['duckdb_change']['confirmation'] = new
    assert plan(baseline, model(wrong, *parents), baseline)['blockers']
    changed = deepcopy(after)
    changed['native']['catalog_metadata']['comment'] = 'other edit'
    assert plan(baseline, model(changed, *parents), baseline)['blockers']
    occupied = plan(baseline, desired, model(before, row(kind, [*parent, new]), *parents))
    assert occupied['blockers'] and not occupied['application_supported']
    stale = deepcopy(before)
    stale['native']['catalog_metadata']['comment'] = 'changed'
    assert plan(baseline, desired, model(stale, *parents))['conflicts']


@pytest.mark.parametrize('kind,path,target', [
    ('table', ['file', 'main', 'facts'], '"file"."main"."facts"'),
    ('view', ['file', 'main', 'facts'], '"file"."main"."facts"'),
    ('column', ['file', 'main', 'facts', 'value'], '"file"."main"."facts"."value"'),
    ('sequence', ['file', 'main', 'facts'], '"file"."main"."facts"'),
    ('type', ['file', 'main', 'facts'], '"file"."main"."facts"'),
    ('macro', ['file', 'main', 'facts'], '"file"."main"."facts"'),
    ('index', ['file', 'main', 'facts', 'facts_ix'], '"file"."main"."facts_ix"'),
])
def test_isolated_native_comment_uses_exact_target_and_escaped_literal(kind, path, target):
    pytest.importorskip('duckdb')
    before = row(kind, path)
    before['native']['catalog_metadata']['comment'] = None
    after = deepcopy(before)
    after['native']['catalog_metadata']['comment'] = "owner's note"
    after['native']['duckdb_change'] = {'action': 'set-comment'}
    result = plan(model(before), model(after), model(before))
    assert result['application_supported'], result['blockers']
    assert result['operations'][0]['source'] == (
        f"COMMENT ON {kind.upper()} {target} IS 'owner''s note'")
    assert result['operations'][0]['postcondition'] == {'comment': "owner's note"}
    after['native']['catalog_metadata']['tags'] = {'other': 'edit'}
    assert plan(model(before), model(after), model(before))['blockers']
    after['native']['catalog_metadata'].pop('tags')
    after['native']['catalog_metadata']['comment'] = "a'; DROP TABLE facts; --"
    safe = plan(model(before), model(after), model(before))
    assert safe['application_supported']
    assert safe['operations'][0]['source'].count("DROP TABLE facts") == 1


def test_schema_comment_is_blocked_by_native_version():
    before = row('schema', ['file', 'main'])
    after = deepcopy(before)
    after['native']['catalog_metadata']['comment'] = 'unsupported'
    after['native']['duckdb_change'] = {'action': 'set-comment'}
    assert plan(model(before), model(after), model(before))['blockers']


def test_native_batch_orders_parent_creation_and_added_column_before_index():
    pytest.importorskip('duckdb')
    schema = row('schema', ['file', 'design'], ddl='CREATE SCHEMA "file"."design"')
    table = row('table', ['file', 'design', 'facts'],
        ddl='CREATE TABLE "file"."design"."facts" ("x" INTEGER)')
    index = row('index', ['file', 'design', 'facts', 'facts_x'],
        ddl='CREATE INDEX "facts_x" ON "file"."design"."facts"("x")')
    result = plan(model(), model(index, table, schema), model())
    assert result['application_supported'], result['blockers']
    assert [item['kind'] for item in result['operations']] == ['schema', 'table', 'index']
    existing = row('table', ['file', 'main', 'old'])
    column = row('column', ['file', 'main', 'old', 'value'])
    column['native']['catalog_metadata'] = {'data_type': 'INTEGER', 'nullable': True}
    new_index = row('index', ['file', 'main', 'old', 'old_value_ix'],
        ddl='CREATE INDEX "old_value_ix" ON "file"."main"."old"("value")')
    added = plan(model(existing), model(existing, new_index, column), model(existing))
    assert added['application_supported'], added['blockers']
    assert [item['kind'] for item in added['operations']] == ['column', 'index']
    with_column = plan(model(), model(schema, table, row('column',
        ['file', 'design', 'facts', 'x'])), model())
    assert with_column['blockers']


def test_primary_key_addition_requires_explicit_observed_columns_and_no_other_edit():
    pytest.importorskip('duckdb')
    before = row('table', ['file', 'main', 'facts'])
    before['native']['catalog_metadata']['has_primary_key'] = False
    before['native']['columns'] = [{'name': 'id'}, {'name': 'region'}]
    after = deepcopy(before)
    after['native']['duckdb_change'] = {'action': 'add-primary-key',
        'columns': ['id', 'region']}
    result = plan(model(before), model(after), model(before))
    assert result['application_supported'], result['blockers']
    assert result['operations'][0]['source'] == (
        'ALTER TABLE "file"."main"."facts" ADD PRIMARY KEY ("id", "region")')
    assert result['operations'][0]['postcondition'] == {
        'primary_key_columns': ['id', 'region']}
    after['native']['duckdb_change']['columns'] = ['id', 'missing']
    assert plan(model(before), model(after), model(before))['blockers']
    after['native']['duckdb_change']['columns'] = ['id', 'id']
    assert plan(model(before), model(after), model(before))['blockers']
    after['native']['duckdb_change']['columns'] = ['id']
    after['native']['catalog_metadata']['comment'] = 'combined'
    assert plan(model(before), model(after), model(before))['blockers']


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


def test_column_default_and_nullability_edits_are_one_field_each():
    pytest.importorskip('duckdb')
    table = row('table', ['file', 'main', 'facts'])
    existing = row('column', ['file', 'main', 'facts', 'amount'])
    existing['native']['catalog_metadata'] = {
        'data_type': 'INTEGER', 'nullable': True, 'default': None}
    changed = deepcopy(existing)
    changed['native']['catalog_metadata']['default'] = '7'
    changed['native']['duckdb_change'] = {'action': 'set-default'}
    result = plan(model(table, existing), model(table, changed), model(table, existing))
    assert result['application_supported']
    assert result['operations'][0]['source'] == (
        'ALTER TABLE "file"."main"."facts" ALTER COLUMN "amount" SET DEFAULT 7')
    changed['native']['catalog_metadata']['nullable'] = False
    assert plan(model(table, existing), model(table, changed), model(table, existing))['blockers']
    changed = deepcopy(existing)
    changed['native']['catalog_metadata']['nullable'] = False
    changed['native']['duckdb_change'] = {'action': 'set-nullable'}
    result = plan(model(table, existing), model(table, changed), model(table, existing))
    assert result['operations'][0]['source'] == (
        'ALTER TABLE "file"."main"."facts" ALTER COLUMN "amount" SET NOT NULL')


def test_column_type_change_requires_isolated_native_intent_and_one_statement():
    pytest.importorskip('duckdb')
    table = row('table', ['file', 'main', 'facts'])
    existing = row('column', ['file', 'main', 'facts', 'amount'])
    existing['native']['catalog_metadata'] = {
        'data_type': 'VARCHAR', 'data_type_id': 12,
        'nullable': True, 'default': None,
    }
    changed = deepcopy(existing)
    changed['native']['catalog_metadata'].update(
        data_type='INTEGER', data_type_id=13)
    changed['native']['duckdb_change'] = {
        'action': 'set-type', 'using': '"amount"::INTEGER',
    }
    result = plan(model(table, existing), model(table, changed),
                  model(table, existing))
    assert result['application_supported'], result['blockers']
    assert result['operations'][0]['source'] == (
        'ALTER TABLE "file"."main"."facts" ALTER COLUMN "amount" '
        'TYPE INTEGER USING "amount"::INTEGER')
    assert result['operations'][0]['postcondition'] == {'data_type': 'INTEGER'}
    changed['native']['catalog_metadata']['nullable'] = False
    assert plan(model(table, existing), model(table, changed),
                model(table, existing))['blockers']
    changed['native']['catalog_metadata']['nullable'] = True
    for unsafe in ('INTEGER; DROP TABLE facts', 'INTEGER USING 1',
                   'INTEGER -- hidden'):
        changed['native']['catalog_metadata']['data_type'] = unsafe
        assert plan(model(table, existing), model(table, changed),
                    model(table, existing))['blockers']
    changed['native']['catalog_metadata']['data_type'] = 'INTEGER'
    changed['native']['duckdb_change']['using'] = '1; DROP TABLE facts'
    assert plan(model(table, existing), model(table, changed),
                model(table, existing))['blockers']


def test_native_enum_extension_is_append_only_and_warns_about_existing_columns():
    pytest.importorskip('duckdb')
    existing = row('type', ['file', 'main', 'mood'])
    existing['native']['catalog_metadata'] = {
        'logical_type': 'ENUM', 'labels': ['ok', 'bad'], 'comment': None}
    changed = deepcopy(existing)
    changed['native']['catalog_metadata']['labels'] = ['ok', 'bad', "it's good"]
    changed['native']['duckdb_change'] = {'action': 'extend-enum'}
    result = plan(model(existing), model(changed), model(existing))
    assert result['application_supported'], result['blockers']
    assert result['operations'][0]['source'] == (
        'CREATE OR REPLACE TYPE "file"."main"."mood" '
        "AS ENUM ('ok', 'bad', 'it''s good')")
    assert result['operations'][0]['postcondition'] == {
        'labels': ['ok', 'bad', "it's good"]}
    assert any('existing typed columns' in warning for warning in result['warnings'])
    for labels in (['ok'], ['bad', 'ok', "it's good"],
                   ['ok', 'bad', 'bad']):
        changed['native']['catalog_metadata']['labels'] = labels
        assert plan(model(existing), model(changed), model(existing))['blockers']
    changed['native']['catalog_metadata']['labels'] = ['ok', 'bad', 'great']
    changed['native']['catalog_metadata']['comment'] = 'other edit'
    assert plan(model(existing), model(changed), model(existing))['blockers']
    commented = deepcopy(existing)
    commented['native']['catalog_metadata']['comment'] = 'preserve'
    changed['native']['catalog_metadata']['comment'] = 'preserve'
    assert 'discard native comment' in plan(
        model(commented), model(changed), model(commented))['blockers'][0]['reason']


def test_scalar_macro_definition_replacement_rejects_other_edits():
    pytest.importorskip('duckdb')
    existing = row('macro', ['file', 'main', 'plusone'])
    overload = {'catalog_metadata': {'function_type': 'macro', 'varargs': None},
                'parameters': [{'name': 'x', 'data_type': None}],
                'definition': '(x + 1)'}
    existing['native'].update(
        definition='(x + 1)', parameters=deepcopy(overload['parameters']),
        overloads=[overload], overload_count=1)
    changed = deepcopy(existing)
    changed['native']['definition'] = '(x + 2)'
    changed['native']['overloads'][0]['definition'] = '(x + 2)'
    changed['native']['duckdb_change'] = {
        'action': 'replace-definition', 'parameters_without_defaults_confirmed': True}
    result = plan(model(existing), model(changed), model(existing))
    assert result['application_supported'], result['blockers']
    assert result['operations'][0]['source'] == (
        'CREATE OR REPLACE MACRO "file"."main"."plusone"("x") AS (x + 2)')
    assert result['operations'][0]['postcondition'] == {'definition': '(x + 2)'}
    unconfirmed = deepcopy(changed)
    unconfirmed['native']['duckdb_change'] = {'action': 'replace-definition'}
    assert 'no parameter defaults' in plan(
        model(existing), model(unconfirmed), model(existing))['blockers'][0]['reason']
    commented = deepcopy(existing)
    commented['native']['catalog_metadata']['comment'] = 'preserve this'
    commented_desired = deepcopy(changed)
    commented_desired['native']['catalog_metadata']['comment'] = 'preserve this'
    assert 'discard existing native comment or tags' in plan(
        model(commented), model(commented_desired), model(commented))['blockers'][0]['reason']
    tagged = deepcopy(existing)
    tagged['native']['catalog_metadata']['tags'] = {'owner': 'user'}
    tagged_desired = deepcopy(changed)
    tagged_desired['native']['catalog_metadata']['tags'] = {'owner': 'user'}
    assert 'discard existing native comment or tags' in plan(
        model(tagged), model(tagged_desired), model(tagged))['blockers'][0]['reason']
    changed['native']['parameters'].append({'name': 'y', 'data_type': None})
    assert plan(model(existing), model(changed), model(existing))['blockers']
    changed = deepcopy(existing)
    changed['native']['definition'] = '(x + 2)'
    changed['native']['overloads'][0]['definition'] = '(x + 2)'
    changed['native']['overloads'][0]['catalog_metadata']['function_type'] = 'table_macro'
    changed['native']['duckdb_change'] = {
        'action': 'replace-definition', 'parameters_without_defaults_confirmed': True}
    assert plan(model(existing), model(changed), model(existing))['blockers']


def test_table_macro_definition_replacement_preserves_native_kind():
    pytest.importorskip('duckdb')
    existing = row('macro', ['file', 'main', 'rows_for'])
    overload = {'catalog_metadata': {'function_type': 'table_macro', 'varargs': None},
                'parameters': [{'name': 'x', 'data_type': None}],
                'definition': 'SELECT (x + 1) AS "value"'}
    existing['native'].update(
        definition=overload['definition'], parameters=deepcopy(overload['parameters']),
        overloads=[overload], overload_count=1)
    changed = deepcopy(existing)
    changed['native']['definition'] = 'SELECT (x + 2) AS "value"'
    changed['native']['overloads'][0]['definition'] = changed['native']['definition']
    changed['native']['duckdb_change'] = {
        'action': 'replace-definition', 'parameters_without_defaults_confirmed': True}
    result = plan(model(existing), model(changed), model(existing))
    assert result['application_supported'], result['blockers']
    assert result['operations'][0]['source'] == (
        'CREATE OR REPLACE MACRO "file"."main"."rows_for"("x") '
        'AS TABLE SELECT (x + 2) AS "value"')
    assert result['operations'][0]['postcondition'] == {
        'definition': 'SELECT (x + 2) AS "value"'}
    changed['native']['overloads'][0]['catalog_metadata']['function_type'] = 'macro'
    assert plan(model(existing), model(changed), model(existing))['blockers']
