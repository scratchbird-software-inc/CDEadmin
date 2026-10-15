"""Explicit DDN creations preserve native identities and ordering."""
from copy import deepcopy
import uuid
import pytest
from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan


def documents():
    current = {'provenance': {'mapping': 'scratchrobin.postgresql.catalog@1', 'endpoint_id': 'one',
        'database_target_id': 'postgresql-database:42', 'generation': 'g'}, 'rows': {}}
    return deepcopy(current), deepcopy(current), current


def add(document, kind, **draft):
    identity = 'postgresql:new:' + str(uuid.uuid4())
    document['rows'][identity] = {'resource_id': identity, 'name': draft['name'], 'kind': kind,
        'system': 'false', 'path': ['db', draft.get('schema', ''), draft['name']],
        'native': {'system_object': False, 'create': draft}}
    return identity


def test_creation_order_and_exact_types_names_and_integer_values():
    before, desired, current = documents()
    schema = add(desired, 'schema', name='Odd schema')
    enum = add(desired, 'type', schema='Odd schema', name='Mood', labels=['', ' spaced ', "a'b"])
    table = add(desired, 'table', schema='Odd schema', name='Mixed " table', depends_on=[enum], columns=[
        {'name': 'id', 'data_type': 'bigint', 'nullable': False},
        {'name': 'state', 'data_type': '"Odd schema"."Mood"'},
        {'name': 'amount', 'data_type': 'double precision'}],
        keys=[{'kind': 'PRIMARY KEY', 'name': 'Key', 'columns': ['id']}])
    sequence = add(desired, 'sequence', schema='Odd schema', name='seq', start='9223372036854775799')
    plan = build_plan(before, desired, current)
    assert plan['ready_for_review'] and plan['application_supported']
    ids = [op['resource_id'] for op in plan['operations']]
    assert ids.index(schema) < ids.index(enum) < ids.index(table)
    assert ids.index(schema) < ids.index(sequence)
    assert '9223372036854775799' in next(op['statement'] for op in plan['operations'] if op['resource_id'] == sequence)
    assert '"Mixed "" table"' in next(op['statement'] for op in plan['operations'] if op['resource_id'] == table)


def test_unknown_fields_never_silently_disappear():
    before, desired, current = documents()
    add(desired, 'table', name='t', schema='public', columns=[], partition_by='unknown')
    plan = build_plan(before, desired, current)
    assert not plan['ready_for_review'] and not plan['operations']


def test_creation_does_not_claim_captured_oid():
    before, desired, current = documents()
    identity = add(desired, 'schema', name='new')
    desired['rows'][identity]['native']['oid'] = 42
    assert not build_plan(before, desired, current)['ready_for_review']


def test_cycles_missing_schema_and_missing_dependencies_block():
    before, desired, current = documents()
    one = add(desired, 'schema', name='one')
    two = add(desired, 'schema', name='two', depends_on=[one])
    desired['rows'][one]['native']['create']['depends_on'] = [two]
    assert 'cycle' in build_plan(before, desired, current)['blockers'][0]['reason']
    desired['rows'][one]['native']['create']['depends_on'] = ['missing']
    assert 'unavailable' in build_plan(before, desired, current)['blockers'][0]['reason']
    desired['rows'].clear()
    add(desired, 'table', name='t', schema='missing', columns=[])
    assert 'schema is unavailable' in build_plan(before, desired, current)['blockers'][0]['reason']


def test_duplicate_drafts_and_native_name_collisions_block():
    before, desired, current = documents()
    add(desired, 'schema', name='same')
    add(desired, 'schema', name='same')
    assert not build_plan(before, desired, current)['ready_for_review']
    desired['rows'].pop(next(iter(desired['rows'])))
    current['rows']['postgresql:pg_namespace:42'] = {'name': 'same', 'kind': 'schema', 'native': {'catalog': 'pg_namespace'}}
    assert 'already occupies' in build_plan(before, desired, current)['blockers'][0]['reason']


@pytest.mark.parametrize('columns', [[{'name': 'x', 'data_type': 'int', 'nullable': 'false'}],
    [{'name': 'x', 'data_type': 'int'}, {'name': 'x', 'data_type': 'text'}],
    [{'name': 'x', 'data_type': 'integer); DROP TABLE other; --'}]])
def test_invalid_column_drafts_are_blocked(columns):
    before, desired, current = documents()
    add(desired, 'schema', name='public')
    add(desired, 'table', name='t', schema='public', columns=columns)
    assert not build_plan(before, desired, current)['ready_for_review']


def test_defaults_generation_identity_and_foreign_key_order():
    before, desired, current = documents()
    add(desired, 'schema', name='public')
    parent = add(desired, 'table', schema='public', name='parent', columns=[
        {'name': 'id', 'data_type': 'bigint', 'identity': 'ALWAYS'}],
        keys=[{'kind': 'PRIMARY KEY', 'name': 'pk', 'columns': ['id']}])
    child = add(desired, 'table', schema='public', name='child', depends_on=[parent], columns=[
        {'name': 'id', 'data_type': 'bigint'},
        {'name': 'amount', 'data_type': 'numeric(12,2)', 'default': '2 + 3'},
        {'name': 'total', 'data_type': 'numeric', 'generated': {'expression': 'amount * 2', 'storage': 'STORED'}}],
        keys=[{'name': 'positive', 'kind': 'CHECK', 'expression': 'amount >= 0'},
              {'name': 'fk', 'kind': 'FOREIGN KEY', 'columns': ['id'],
               'references': {'schema': 'public', 'table': 'parent', 'columns': ['id']},
               'deferrable': True, 'initially_deferred': True, 'on_delete': 'CASCADE'}])
    plan = build_plan(before, desired, current)
    assert plan['ready_for_review'], plan['blockers']
    statements = [op['statement'] for op in plan['operations']]
    assert 'GENERATED ALWAYS AS IDENTITY' in statements[1]
    assert 'DEFERRABLE INITIALLY DEFERRED' in statements[2]
    desired['rows'][child]['native']['create']['depends_on'] = []
    assert not build_plan(before, desired, current)['ready_for_review']


@pytest.mark.parametrize('properties', [
    {'default': '1); DROP TABLE t; SELECT (1'},
    {'default': '1) FROM pg_class --'},
    {'default': '1', 'identity': 'ALWAYS'},
    {'identity': 'ALWAYS', 'nullable': True},
    {'generated': {'expression': '1', 'storage': 'UNKNOWN'}},
])
def test_invalid_expression_or_incompatible_column_options(properties):
    before, desired, current = documents()
    add(desired, 'schema', name='public')
    add(desired, 'table', schema='public', name='t', columns=[{'name': 'x', 'data_type': 'int', **properties}])
    assert not build_plan(before, desired, current)['ready_for_review']


@pytest.mark.parametrize('key', [
    {'kind': 'CHECK', 'expression': 'x > 0', 'deferrable': True},
    {'kind': 'UNIQUE', 'columns': ['x'], 'initially_deferred': True},
    {'kind': 'FOREIGN KEY', 'columns': ['x'], 'references': {'schema': 'public', 'table': 't', 'columns': ['x','y']}},
])
def test_invalid_constraint_options(key):
    before, desired, current = documents()
    add(desired, 'schema', name='public')
    add(desired, 'table', schema='public', name='t', columns=[{'name': 'x', 'data_type': 'int'}], keys=[{'name': 'key', **key}])
    assert not build_plan(before, desired, current)['ready_for_review']


def test_domain_and_native_view_properties():
    before, desired, current = documents()
    add(desired, 'schema', name='public')
    domain = add(desired, 'domain', schema='public', name='positive', data_type='numeric(12,2)',
        default='1', nullable=False, checks=[{'name': 'positive', 'expression': 'VALUE > 0'}])
    view = add(desired, 'view', schema='public', name='v', query='SELECT 1 AS value', columns=['amount'],
        security_barrier=True, security_invoker=True)
    materialized = add(desired, 'materialized-view', schema='public', name='m', query='SELECT 2', with_data=False)
    plan = build_plan(before, desired, current)
    assert plan['ready_for_review'], plan['blockers']
    sql = {op['resource_id']: op['statement'] for op in plan['operations']}
    assert 'NOT NULL CONSTRAINT "positive" CHECK' in sql[domain]
    assert 'security_barrier=true, security_invoker=true' in sql[view]
    assert sql[materialized].endswith('WITH NO DATA')


@pytest.mark.parametrize('kind,properties', [
    ('view', {'query': 'SELECT 1; DROP TABLE t'}),
    ('view', {'query': 'SELECT 1 INTO t'}),
    ('view', {'query': 'DELETE FROM t RETURNING *'}),
    ('view', {'query': 'SELECT 1', 'with_data': True}),
    ('materialized-view', {'query': 'SELECT 1', 'security_invoker': True}),
    ('domain', {'data_type': 'int', 'nullable': 'false'}),
    ('domain', {'data_type': 'int', 'checks': [{'name': 'c', 'expression': 'VALUE > 0'}, {'name': 'c', 'expression': 'VALUE < 10'}]}),
])
def test_invalid_view_domain_drafts(kind, properties):
    before, desired, current = documents()
    add(desired, 'schema', name='public')
    add(desired, kind, schema='public', name='x', **properties)
    assert not build_plan(before, desired, current)['ready_for_review']


def test_application_only_admits_wholly_new_schema_creation_batches():
    before, desired, current = documents()
    current['rows']['postgresql:pg_namespace:42'] = {'name': 'public', 'kind': 'schema',
        'native': {'catalog': 'pg_namespace', 'schema': 'public'}}
    add(desired, 'table', schema='public', name='existing_scope', columns=[])
    plan = build_plan(before, desired, current)
    assert plan['ready_for_review'] and not plan['application_supported']
    desired['rows'].clear()
    schema = add(desired, 'schema', name='new_scope', depends_on=['postgresql:pg_namespace:42'])
    assert not build_plan(before, desired, current)['application_supported']
    desired['rows'][schema]['native']['create']['depends_on'] = []
    add(desired, 'table', schema='new_scope', name='new_table', columns=[])
    assert build_plan(before, desired, current)['application_supported']


def test_index_dependency_expression_and_native_namespace():
    before, desired, current = documents()
    add(desired, 'schema', name='scope')
    table = add(desired, 'table', schema='scope', name='t', columns=[{'name': 'value', 'data_type': 'text'}])
    index = add(desired, 'index', schema='scope', name='idx', table='t', depends_on=[table],
        unique=True, keys=[{'expression': 'lower(value)', 'order': 'DESC', 'nulls': 'LAST',
            'collation': {'schema': 'pg_catalog', 'name': 'C'},
            'opclass': {'schema': 'pg_catalog', 'name': 'text_ops'}}],
        include=['value'], nulls_distinct=False, predicate='value IS NOT NULL')
    plan = build_plan(before, desired, current)
    assert plan['application_supported'], plan['blockers']
    assert [op['resource_id'] for op in plan['operations']].index(table) < [op['resource_id'] for op in plan['operations']].index(index)
    statement = plan['operations'][-1]['statement']
    assert 'CREATE UNIQUE INDEX "idx" ON "scope"."t"' in statement
    assert 'NULLS NOT DISTINCT WHERE' in statement
    desired['rows'][index]['native']['create']['depends_on'] = []
    assert not build_plan(before, desired, current)['ready_for_review']
    desired['rows'][index]['native']['create']['depends_on'] = [table]
    desired['rows'][index]['native']['create']['name'] = 't'
    desired['rows'][index]['name'] = 't'
    assert not build_plan(before, desired, current)['ready_for_review']


@pytest.mark.parametrize('properties', [
    {'keys': []}, {'keys': [{'column': 'x', 'expression': 'x'}]},
    {'keys': [{'expression': '1); DROP TABLE t; SELECT (1'}]},
    {'keys': [{'column': 'x', 'order': 'SIDEWAYS'}]},
    {'keys': [{'column': 'x', 'opclass': 'text_ops'}]},
    {'concurrently': True}, {'unique': 'false'}, {'nulls_distinct': False},
    {'include': ['x', 'x']}, {'predicate': 'x) FROM pg_class --'},
])
def test_invalid_index_options_are_blockers(properties):
    before, desired, current = documents()
    add(desired, 'schema', name='scope')
    add(desired, 'index', **{'schema': 'scope', 'name': 'idx', 'table': 't', 'keys': [{'column': 'x'}], **properties})
    assert not build_plan(before, desired, current)['ready_for_review']


def test_composite_and_range_types_preserve_native_properties():
    before, desired, current = documents()
    add(desired, 'schema', name='scope')
    composite = add(desired, 'type', schema='scope', name='Pair', type_kind='COMPOSITE', attributes=[
        {'name': 'label', 'data_type': 'text', 'collation': {'schema': 'pg_catalog', 'name': 'C'}},
        {'name': 'value', 'data_type': 'numeric(12,2)'}])
    interval = add(desired, 'type', schema='scope', name='Span', type_kind='RANGE', subtype='double precision',
        subtype_diff={'schema': 'pg_catalog', 'name': 'float8mi'})
    plan = build_plan(before, desired, current)
    assert plan['application_supported'], plan['blockers']
    sql = {op['resource_id']: op['statement'] for op in plan['operations']}
    assert 'COLLATE "pg_catalog"."C"' in sql[composite]
    assert 'SUBTYPE_DIFF = "pg_catalog"."float8mi"' in sql[interval]
    add(desired, 'sequence', schema='scope', name='Pair')
    assert not build_plan(before, desired, current)['ready_for_review']


@pytest.mark.parametrize('properties', [
    {'type_kind': 'COMPOSITE', 'attributes': [{'name': 'x', 'data_type': 'int', 'default': '1'}]},
    {'type_kind': 'COMPOSITE', 'attributes': [{'name': 'x', 'data_type': 'int'}]*2},
    {'type_kind': 'COMPOSITE', 'attributes': [], 'labels': []},
    {'type_kind': 'RANGE', 'subtype': 'int', 'canonical': 'unsafe'},
    {'type_kind': 'RANGE', 'subtype': 'int); DROP TABLE t'},
    {'type_kind': 'RANGE', 'subtype': 'int', 'subtype_diff': 'float8mi'},
    {'type_kind': 'BASE'}, {'type_kind': {}},
])
def test_invalid_type_variants_block(properties):
    before, desired, current = documents()
    add(desired, 'schema', name='scope')
    add(desired, 'type', schema='scope', name='T', **properties)
    assert not build_plan(before, desired, current)['ready_for_review']


def test_native_routine_drafts_preserve_definitions_and_overload_signatures():
    before, desired, live = documents()
    add(desired, 'schema', name='routines')
    definitions = [
        ('function', 'echo', "CREATE FUNCTION routines.echo(value integer DEFAULT 1) RETURNS integer LANGUAGE SQL IMMUTABLE AS $$ SELECT value + 1 $$"),
        ('function', 'echo', "CREATE FUNCTION routines.echo(value text) RETURNS text LANGUAGE SQL STRICT AS $$ SELECT value $$"),
        ('procedure', 'bump', "CREATE PROCEDURE routines.bump(INOUT value integer) LANGUAGE plpgsql AS $$ BEGIN value := value + 1; END $$"),
    ]
    for kind, name, definition in definitions:
        add(desired, kind, schema='routines', name=name, definition=definition)
    plan = build_plan(before, desired, live)
    assert plan['application_supported'], plan['blockers']
    routines = plan['operations'][1:]
    assert {op['statement'] for op in routines} == {definition for _, _, definition in definitions}
    assert len({op['routine_signature'] for op in routines}) == 3
    assert all(op['routine_signature'].startswith('"routines".') for op in routines)


@pytest.mark.parametrize('definition', [
    'CREATE FUNCTION wrong.echo() RETURNS integer LANGUAGE SQL AS $$ SELECT 1 $$',
    'CREATE OR REPLACE FUNCTION routines.echo() RETURNS integer LANGUAGE SQL AS $$ SELECT 1 $$',
    'CREATE PROCEDURE routines.echo() LANGUAGE SQL AS $$ SELECT 1 $$',
    'CREATE FUNCTION routines.echo() RETURNS integer LANGUAGE SQL AS $$ SELECT 1 $$; DROP SCHEMA public CASCADE',
])
def test_routine_definition_cannot_retarget_replace_or_add_statements(definition):
    before, desired, live = documents()
    add(desired, 'schema', name='routines')
    add(desired, 'function', schema='routines', name='echo', definition=definition)
    assert not build_plan(before, desired, live)['ready_for_review']


@pytest.mark.parametrize('kind,name,definition,signature', [
    ('function','echo', 'CREATE FUNCTION routines.echo(IN value integer, OUT result text) LANGUAGE SQL AS $$ SELECT value::text $$', 'integer'),
    ('window-function','rnum', "CREATE FUNCTION routines.rnum() RETURNS bigint LANGUAGE internal WINDOW AS 'window_row_number'", ''),
    ('aggregate','total', 'CREATE AGGREGATE routines.total(integer) (SFUNC=int4pl, STYPE=integer, INITCOND=0)', 'integer'),
    ('aggregate','total', 'CREATE AGGREGATE routines.total(*) (SFUNC=int8inc, STYPE=bigint, INITCOND=0)', ''),
])
def test_all_native_routine_kinds_have_resolvable_input_signatures(kind, name, definition, signature):
    before, desired, live = documents()
    add(desired, 'schema', name='routines')
    add(desired, kind, schema='routines', name=name, definition=definition)
    plan = build_plan(before, desired, live)
    assert plan['application_supported'], plan['blockers']
    assert plan['operations'][1]['routine_signature'] == f'"routines"."{name}"({signature})'


def test_existing_schema_creation_requires_exact_user_namespace_guard():
    before, desired, live = documents()
    live['rows']['postgresql:pg_namespace:17000'] = {'name':'scope', 'kind':'schema', 'system':'false',
        'native': {'catalog':'pg_namespace','oid':17000,'schema':'scope','catalog_row':{'nspname':'scope'}}}
    add(desired, 'table', schema='scope', name='t', columns=[])
    plan = build_plan(before, desired, live)
    assert plan['application_supported'], plan['blockers']
    assert plan['operations'][0]['schema_guard']['oid'] == 17000
    replaced = deepcopy(live)
    schema = replaced['rows'].pop('postgresql:pg_namespace:17000')
    schema['native']['oid'] = 17001
    replaced['rows']['postgresql:pg_namespace:17001'] = schema
    assert build_plan(before, desired, replaced)['execution_sha256'] != plan['execution_sha256']
    live['rows']['postgresql:pg_namespace:17000']['system'] = 'true'
    assert not build_plan(before, desired, live)['application_supported']


def test_created_namespace_guard_refuses_same_name_different_oid():
    from pgadmin.cdeadmin.providers.postgresql.schema_application import _check_created_scope
    operation = {'schema_guard': {'oid': 17000}}
    row = {'native': {'catalog':'pg_class','catalog_row':{'relnamespace':17001}}}
    with pytest.raises(ValueError, match='different schema identity'):
        _check_created_scope(operation, row)
    row['native']['catalog_row']['relnamespace'] = 17000
    _check_created_scope(operation, row)


NATIVE_DEFINITIONS = {
    'collation': 'CREATE COLLATION public.native FROM pg_catalog."C"',
    'conversion': "CREATE CONVERSION public.native FOR 'UTF8' TO 'LATIN1' FROM pg_catalog.utf8_to_iso8859_1",
    'text-search-configuration': 'CREATE TEXT SEARCH CONFIGURATION public.native (COPY=pg_catalog.simple)',
    'text-search-dictionary': 'CREATE TEXT SEARCH DICTIONARY public.native (TEMPLATE=pg_catalog.simple)',
    'text-search-template': 'CREATE TEXT SEARCH TEMPLATE public.native (LEXIZE=pg_catalog.dsimple_lexize)',
    'text-search-parser': 'CREATE TEXT SEARCH PARSER public.native (START=pg_catalog.prsd_start, GETTOKEN=pg_catalog.prsd_nexttoken, END=pg_catalog.prsd_end, LEXTYPES=pg_catalog.prsd_lextype)',
}


@pytest.mark.parametrize('kind,definition',NATIVE_DEFINITIONS.items())
def test_named_native_definitions_retain_options_and_exact_kind_scope(kind,definition):
    before, desired, current = documents()
    add(desired,'schema',name='public')
    add(desired,kind,schema='public',name='native',definition=definition)
    plan=build_plan(before,desired,current)
    assert plan['application_supported'],plan['blockers']
    assert plan['operations'][-1]['statement']==definition
    for wrong in (definition+'; SELECT 1', definition.replace('public.native','other.native'), 'CREATE TABLE public.native(id integer)'):
        altered=deepcopy(desired)
        next(row for row in altered['rows'].values() if row['kind']==kind)['native']['create']['definition']=wrong
        assert not build_plan(before,altered,current)['ready_for_review']


def test_named_definition_namespaces_are_distinct_but_native_collisions_refused():
    before,desired,current=documents()
    add(desired,'schema',name='public')
    for kind in ('collation','conversion'):
        add(desired,kind,schema='public',name='native',definition=NATIVE_DEFINITIONS[kind])
    assert build_plan(before,desired,current)['application_supported']
    current['rows']['postgresql:pg_collation:88']={'name':'native','kind':'collation',
        'native':{'catalog':'pg_collation','oid':88,'schema':'public'}}
    assert not build_plan(before,desired,current)['ready_for_review']


def test_partition_definitions_keep_native_bounds_and_declared_parent_order():
    before,desired,current=documents()
    add(desired,'schema',name='scope')
    parent=add(desired,'partitioned-table',schema='scope',name='parent',definition='CREATE TABLE scope.parent(id integer) PARTITION BY RANGE (id)')
    child=add(desired,'table',schema='scope',name='child',depends_on=[parent],definition='CREATE TABLE scope.child PARTITION OF scope.parent FOR VALUES FROM (0) TO (10)')
    plan=build_plan(before,desired,current)
    assert plan['application_supported'],plan['blockers']
    ids=[operation['resource_id'] for operation in plan['operations']]
    assert ids.index(parent)<ids.index(child)
    desired['rows'][child]['native']['create']['depends_on']=[]
    assert not build_plan(before,desired,current)['ready_for_review']


@pytest.mark.parametrize('definition',[
    'CREATE TABLE scope.parent(id integer)',
    'CREATE TABLE other.parent(id integer) PARTITION BY HASH (id)',
    'CREATE TEMP TABLE scope.parent(id integer) PARTITION BY LIST (id)',
    'CREATE TABLE IF NOT EXISTS scope.parent(id integer) PARTITION BY RANGE (id)',
    'CREATE TABLE scope.parent(id integer) PARTITION BY HASH (id); SELECT 1',
])
def test_partition_drafts_refuse_wrong_identity_kind_persistence_or_extra_sql(definition):
    before,desired,current=documents();add(desired,'schema',name='scope')
    add(desired,'partitioned-table',schema='scope',name='parent',definition=definition)
    assert not build_plan(before,desired,current)['ready_for_review']


def test_partition_existing_parent_is_not_silently_attached():
    before,desired,current=documents();add(desired,'schema',name='scope')
    add(desired,'table',schema='scope',name='child',definition='CREATE TABLE scope.child PARTITION OF scope.parent DEFAULT')
    assert not build_plan(before,desired,current)['ready_for_review']


def existing_partition_fixture():
    before, desired, current = documents()
    current['rows']['postgresql:pg_namespace:17000'] = {'name':'scope','kind':'schema','system':'false',
        'native':{'catalog':'pg_namespace','oid':17000,'schema':'scope','catalog_row':{'nspname':'scope'}}}
    parent = 'postgresql:pg_class:17001'
    current['rows'][parent] = {'name':'parent','kind':'partitioned-table','system':'false',
        'native':{'catalog':'pg_class','oid':17001,'schema':'scope','catalog_row':{'relname':'parent'}}}
    child = add(desired,'table',schema='scope',name='child',depends_on=[parent],
        definition='CREATE TABLE scope.child PARTITION OF scope.parent FOR VALUES FROM (0) TO (10)')
    return before, desired, current, parent, child


def test_existing_partition_parent_is_locked_and_fingerprinted():
    before, desired, current, parent, child = existing_partition_fixture()
    plan = build_plan(before, desired, current)
    assert plan['application_supported'], plan['blockers']
    operation = plan['operations'][0]
    assert operation['parent_guard']['resource_id'] == parent
    assert operation['lock_target'] == {'oid':17001,'schema':'scope','name':'parent'}
    changed = deepcopy(current)
    changed['rows'][parent]['native']['comment'] = 'changed since review'
    assert build_plan(before, desired, changed)['execution_sha256'] != plan['execution_sha256']
    replaced = changed['rows'].pop(parent)
    replaced['native']['oid'] = 17002
    changed['rows']['postgresql:pg_class:17002'] = replaced
    assert not build_plan(before, desired, changed)['application_supported']
    desired['rows'][child]['native']['create']['depends_on'] = []
    assert not build_plan(before, desired, current)['application_supported']


def test_existing_partition_lock_cannot_bypass_unrelated_dependency_admission():
    before, desired, current, parent, child = existing_partition_fixture()
    desired['rows'][child]['native']['create']['depends_on'].append('postgresql:pg_namespace:17000')
    assert not build_plan(before, desired, current)['application_supported']


def test_created_partition_must_have_exact_parent_oid():
    from pgadmin.cdeadmin.providers.postgresql.schema_application import _check_created_scope
    operation = {'parent_guard':{'oid':17001}}
    row = {'native':{'oid':17002,'children':{'pg_inherits':[{'inhparent':17001,'inhrelid':17002}]}}}
    _check_created_scope(operation, row)
    row['native']['children']['pg_inherits'][0]['inhparent'] = 17003
    with pytest.raises(ValueError, match='different parent identity'):
        _check_created_scope(operation, row)


def test_mixed_creation_and_locked_relation_alteration_is_admitted():
    from tools.tests.test_postgresql_schema_apply import documents as altered_documents
    before,desired=altered_documents()
    add(desired,'schema',name='new_schema')
    table=add(desired,'table',schema='new_schema',name='created',columns=[])
    plan=build_plan(before,desired,before)
    assert plan['application_supported'],plan['blockers']
    assert [op.get('operation') for op in plan['operations']]==['create','create',None]
    assert plan['operations'][1]['resource_id']==table
    desired['rows'][table]['native']['create']['depends_on']=['postgresql:pg_class:16384']
    assert not build_plan(before,desired,before)['application_supported']


def test_existing_routine_name_does_not_block_a_new_overload():
    before, desired, live = documents()
    live['rows']['postgresql:pg_namespace:17000']={'name':'scope','kind':'schema','system':'false',
        'native':{'catalog':'pg_namespace','oid':17000,'schema':'scope','catalog_row':{'nspname':'scope'}}}
    live['rows']['postgresql:pg_proc:17001']={'name':'echo','kind':'function','system':'false',
        'native':{'catalog':'pg_proc','oid':17001,'schema':'scope','catalog_row':{'proname':'echo'}}}
    identity=add(desired,'function',schema='scope',name='echo',
        definition='CREATE FUNCTION scope.echo(value text) RETURNS text LANGUAGE SQL AS $$ SELECT value $$')
    plan=build_plan(before,desired,live)
    assert plan['application_supported'],plan['blockers']
    assert plan['operations'][0]['routine_signature']=='scope.echo(text)' or plan['operations'][0]['routine_signature']=='"scope"."echo"(text)'
    desired['rows'][identity]['native']['create']['definition']='CREATE OR REPLACE FUNCTION scope.echo(value text) RETURNS text LANGUAGE SQL AS $$ SELECT value $$'
    assert not build_plan(before,desired,live)['application_supported']


TABLE_DEFINITIONS = {
    'trigger': 'CREATE TRIGGER same BEFORE INSERT ON scope.parent FOR EACH ROW EXECUTE FUNCTION scope.change()',
    'policy': 'CREATE POLICY same ON scope.parent FOR SELECT USING (value > 0)',
    'rule': 'CREATE RULE same AS ON DELETE TO scope.parent DO INSTEAD NOTHING',
}


@pytest.mark.parametrize('kind,definition',TABLE_DEFINITIONS.items())
def test_table_owned_definition_requires_exact_parent_and_orders_new_table(kind,definition):
    before,desired,current=documents();add(desired,'schema',name='scope')
    parent=add(desired,'table',schema='scope',name='parent',columns=[{'name':'value','data_type':'integer'}])
    child=add(desired,kind,schema='scope',name='same',table='parent',definition=definition,depends_on=[parent])
    plan=build_plan(before,desired,current)
    assert plan['application_supported'],plan['blockers']
    ids=[op['resource_id'] for op in plan['operations']]
    assert ids.index(parent)<ids.index(child)
    desired['rows'][child]['native']['create']['depends_on']=[]
    assert not build_plan(before,desired,current)['ready_for_review']
    desired['rows'][child]['native']['create']['depends_on']=[parent]
    desired['rows'][child]['native']['create']['table']='other'
    assert not build_plan(before,desired,current)['ready_for_review']


@pytest.mark.parametrize('kind,definition',TABLE_DEFINITIONS.items())
def test_existing_table_owned_definition_is_guarded_and_names_are_table_scoped(kind,definition):
    before,desired,current,parent,child=existing_partition_fixture()
    desired['rows'].clear()
    current['rows'][parent]['kind']='table'
    first=add(desired,kind,schema='scope',name='same',table='parent',definition=definition,depends_on=[parent])
    second_parent='postgresql:pg_class:17003'
    current['rows'][second_parent]=deepcopy(current['rows'][parent])
    current['rows'][second_parent]['name']='other'
    current['rows'][second_parent]['native'].update(oid=17003,catalog_row={'relname':'other'})
    add(desired,kind,schema='scope',name='same',table='other',definition=definition.replace('scope.parent','scope.other'),depends_on=[second_parent])
    plan=build_plan(before,desired,current)
    assert plan['application_supported'],plan['blockers']
    assert {op['owner_guard']['oid'] for op in plan['operations']}=={17001,17003}
    current['rows'][parent]['native']['catalog_row']['relispartition']=True
    assert not build_plan(before,desired,current)['application_supported']


def test_index_parameters_preserve_native_structure_and_quote_values():
    from pgadmin.cdeadmin.workspace.postgresql_creation import index_definition
    from pglast import parse_sql
    statement = index_definition('idx', 'scope', {'table': 't', 'method': 'brin',
        'keys': [{'column': 'x', 'opclass': {'schema': 'pg_catalog', 'name': 'int8_minmax_multi_ops'},
                  'opclass_parameters': {'values_per_range': 32}}],
        'storage_parameters': {'pages_per_range': 16, 'autosummarize': True}})
    node = parse_sql(statement)[0].stmt
    assert len(node.indexParams[0].opclassopts) == 1
    assert {item.defname for item in node.options} == {'pages_per_range', 'autosummarize'}
    adversarial = index_definition('idx', 'scope', {'table': 't', 'keys': [{'column': 'x'}],
        'storage_parameters': {'fillfactor': "80'); DROP TABLE t; --\\"}})
    assert len(parse_sql(adversarial)) == 1


@pytest.mark.parametrize('properties', [
    {'storage_parameters': {}}, {'storage_parameters': {'fillfactor': None}},
    {'storage_parameters': {'fillfactor': 80.5}},
    {'storage_parameters': {'fillfactor': 'x' * 4097}},
    {'storage_parameters': {'fillfactor': 'x\x00'}},
    {'keys': [{'column': 'x', 'opclass_parameters': {'values_per_range': 32}}]},
])
def test_invalid_index_parameter_shapes_are_blockers(properties):
    before, desired, current = documents()
    add(desired, 'schema', name='scope')
    add(desired, 'index', **{'schema': 'scope', 'name': 'idx', 'table': 't', 'keys': [{'column': 'x'}], **properties})
    assert not build_plan(before, desired, current)['ready_for_review']


def test_index_parameter_rendering_survives_durable_review_key_sorting():
    import json
    from pgadmin.cdeadmin.workspace.postgresql_creation import index_definition
    draft = {'table': 't', 'method': 'brin', 'keys': [{'column': 'x',
        'opclass': {'schema': 'pg_catalog', 'name': 'int8_bloom_ops'},
        'opclass_parameters': {'n_distinct_per_range': 1000, 'false_positive_rate': '0.01'}}],
        'storage_parameters': {'pages_per_range': 16, 'autosummarize': True}}
    assert index_definition('idx', 'scope', draft) == index_definition(
        'idx', 'scope', json.loads(json.dumps(draft, sort_keys=True)))
