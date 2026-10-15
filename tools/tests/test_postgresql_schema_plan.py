"""Three-way native DDN metadata changes preserve concurrent work."""
from copy import deepcopy
import pytest
from pgadmin.cdeadmin.workspace.postgresql_schema_plan import build_plan

IDENTITY = 'postgresql:pg_class:16384'


def documents():
    doc = {'provenance': {'mapping': 'scratchrobin.postgresql.catalog@1', 'endpoint_id': 'endpoint',
        'database_target_id': 'postgresql-database:42', 'generation': 'g'}, 'rows': {
        IDENTITY: {'resource_id': IDENTITY, 'kind': 'table', 'path': ['db', 'public', 'Mixed " name'],
            'name': 'Mixed " name', 'system': 'false', 'native': {'catalog': 'pg_class', 'oid': 16384,
                'comment': 'before', 'sql_identity': 'public."Mixed "" name"',
                'catalog_row': {'relname': 'Mixed " name', 'relowner': 10}}}}}
    return tuple(deepcopy(doc) for _ in range(3))


def test_comment_plan_quotes_literals_and_preserves_live_other_fields():
    baseline, desired, live = documents()
    desired['rows'][IDENTITY]['native']['comment'] = "é\\'; DROP TABLE x; --"
    live['rows'][IDENTITY]['native']['catalog_row']['relowner'] = 11
    plan = build_plan(baseline, desired, live)
    assert plan['ready_for_review'] and not plan['application_supported']
    statement = plan['operations'][0]['statement']
    from pglast import parse_sql, ast
    parsed = parse_sql(statement)
    assert len(parsed) == 1 and isinstance(parsed[0].stmt, ast.CommentStmt)
    assert parsed[0].stmt.comment == desired['rows'][IDENTITY]['native']['comment']
    assert live['rows'][IDENTITY]['native']['catalog_row']['relowner'] == 11


def test_conflicting_comments_block_but_converged_comments_do_not_reapply():
    baseline, desired, live = documents()
    desired['rows'][IDENTITY]['native']['comment'] = 'desired'
    live['rows'][IDENTITY]['native']['comment'] = 'someone else'
    assert not build_plan(baseline, desired, live)['ready_for_review']
    live['rows'][IDENTITY]['native']['comment'] = 'desired'
    plan = build_plan(baseline, desired, live)
    assert plan['counts']['converged'] == 1 and not plan['operations']


def test_missing_row_or_removed_property_never_implies_drop():
    baseline, desired, live = documents()
    del desired['rows'][IDENTITY]['native']['comment']
    assert not build_plan(baseline, desired, live)['ready_for_review']
    desired['rows'].clear()
    plan = build_plan(baseline, desired, live)
    assert not plan['ready_for_review'] and not plan['operations']


@pytest.mark.parametrize('value', [None, ''])
def test_explicit_empty_comment_generates_native_null(value):
    baseline, desired, live = documents()
    desired['rows'][IDENTITY]['native']['comment'] = value
    assert build_plan(baseline, desired, live)['operations'][0]['statement'].endswith(' IS NULL')


def test_native_identity_edit_is_not_executable_imported_sql():
    baseline, desired, live = documents()
    desired['rows'][IDENTITY]['native']['comment'] = 'desired'
    desired['rows'][IDENTITY]['native']['sql_identity'] = 'other; DROP TABLE x; --'
    plan = build_plan(baseline, desired, live)
    assert not plan['ready_for_review'] and not plan['operations']


def test_unmodified_live_change_is_preserved():
    baseline, desired, live = documents()
    live['rows'][IDENTITY]['native']['comment'] = 'new live comment'
    plan = build_plan(baseline, desired, live)
    assert plan['counts']['preserved_live_changes'] == 1 and not plan['operations']


def test_database_and_engine_provenance_cannot_be_relabelled():
    baseline, desired, live = documents()
    desired['provenance']['database_target_id'] = 'postgresql-database:43'
    with pytest.raises(ValueError, match='different endpoint or database'):
        build_plan(baseline, desired, live)


def test_noncomment_change_is_explicitly_blocked():
    baseline, desired, live = documents()
    desired['rows'][IDENTITY]['native']['catalog_row']['relowner'] = 12
    plan = build_plan(baseline, desired, live)
    assert 'catalog_row' in plan['blockers'][0]['reason']
    assert not plan['ready_for_review']


def test_domain_constraint_uses_domain_grammar_and_live_parent_identity():
    baseline, desired, live = documents()
    identity = 'postgresql:pg_constraint:17000'
    for doc in (baseline, desired, live):
        doc['rows'][identity] = {'kind': 'constraint', 'path': ['db', 'public', 'check'],
            'name': 'check', 'system': 'false', 'native': {'catalog': 'pg_constraint', 'oid': 17000,
                'sql_identity': '"on on" on public.domain_name', 'comment': None,
                'catalog_row': {'contypid': 17001, 'conname': 'on on'}}}
    live['rows']['postgresql:pg_type:17001'] = {'native': {'sql_identity': 'public."domain name"'}}
    desired['rows'][identity]['native']['comment'] = 'domain constraint'
    result = build_plan(baseline, desired, live)
    assert result['ready_for_review']
    assert '"on on" ON DOMAIN public."domain name"' in result['operations'][0]['statement']


def column_documents():
    before, desired, live = documents()
    for doc in (before, desired, live):
        doc['rows'][IDENTITY]['native']['children'] = {'pg_attribute': [
            {'attrelid': '16384', 'attnum': 1, 'attname': 'Odd " column', 'comment': 'before', 'attnotnull': False},
            {'attrelid': '16384', 'attnum': 2, 'attname': 'second', 'comment': None, 'attnotnull': False}]}
    return before, desired, live


def test_column_comment_preserves_live_properties_and_combines_with_table_comment():
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['comment'] = 'new table comment'
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['comment'] = "column\\'comment"
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attnotnull'] = True
    plan = build_plan(before, desired, live)
    assert plan['ready_for_review'] and len(plan['operations']) == 2
    column = next(op for op in plan['operations'] if op['kind'] == 'column')
    assert column['resource_id'] == 'postgresql:pg_attribute:16384:1'
    assert 'public."Mixed "" name"."Odd "" column"' in column['statement']
    assert live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attnotnull'] is True


def test_column_conflict_and_rename_are_not_silently_overwritten():
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['comment'] = 'wanted'
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['comment'] = 'independent'
    assert 'independently' in build_plan(before, desired, live)['blockers'][0]['reason']
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['comment'] = 'before'
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attname'] = 'renamed'
    assert 'identity changed' in build_plan(before, desired, live)['blockers'][0]['reason']


def test_column_change_converges_and_explicit_null_clears_comment():
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['comment'] = None
    plan = build_plan(before, desired, live)
    assert plan['ready_for_review'] and plan['operations'][0]['statement'].endswith(' IS NULL')
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['comment'] = None
    plan = build_plan(before, desired, live)
    assert not plan['operations'] and plan['counts']['converged'] == 1


def test_column_metadata_edits_and_omissions_remain_blocked():
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['atttypid'] = 23
    assert not build_plan(before, desired, live)['ready_for_review']
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'].pop()
    assert not build_plan(before, desired, live)['ready_for_review']


def test_native_attribute_reordering_is_not_a_comment_change():
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'].reverse()
    assert not build_plan(before, desired, live)['ready_for_review']


def test_column_nullability_diff_and_convergence_preserve_identity():
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attnotnull'] = True
    plan = build_plan(before, desired, live)
    assert plan['ready_for_review'], plan['blockers']
    assert plan['operations'][0]['statement'].endswith('SET NOT NULL')
    assert plan['operations'][0]['operation'] == 'set_nullability'
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attnotnull'] = True
    plan = build_plan(before, desired, live)
    assert not plan['operations'] and plan['counts']['converged'] == 1


@pytest.mark.parametrize('value', ['false', None, 0])
def test_column_nullability_rejects_nonboolean(value):
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attnotnull'] = value
    assert not build_plan(before, desired, live)['ready_for_review']


def test_inherited_column_nullability_is_not_silently_changed():
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attnotnull'] = True
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attinhcount'] = 1
    assert not build_plan(before, desired, live)['ready_for_review']


def test_column_rename_keeps_identity_and_orders_combined_changes():
    before, desired, live = column_documents()
    wanted = desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]
    wanted.update(attname=' New " ü ', attnotnull=True, comment='renamed')
    plan = build_plan(before, desired, live)
    assert plan['ready_for_review'], plan['blockers']
    assert len(plan['operations']) == 3
    rename, nullable, comment = plan['operations']
    assert rename['operation'] == 'rename_column'
    assert all(op['resource_id'] == 'postgresql:pg_attribute:16384:1' for op in plan['operations'])
    assert '" New "" ü "' in nullable['statement'] and '" New "" ü "' in comment['statement']
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0].update(wanted)
    converged = build_plan(before, desired, live)
    assert converged['ready_for_review'] and not converged['operations']
    assert converged['counts']['converged'] == 3


@pytest.mark.parametrize('name', ['', 'x\x00y', 'ü' * 32, 'second'])
def test_column_rename_rejects_invalid_or_occupied_names(name):
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attname'] = name
    assert not build_plan(before, desired, live)['ready_for_review']


def test_column_rename_refuses_concurrent_rename_and_inheritance():
    before, desired, live = column_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attname'] = 'wanted'
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['attname'] = 'independent'
    assert not build_plan(before, desired, live)['ready_for_review']
    live = deepcopy(before)
    live['rows'][IDENTITY]['native']['catalog_row']['relhassubclass'] = True
    assert not build_plan(before, desired, live)['ready_for_review']


def test_relation_rename_preserves_oid_and_converges_after_native_rediscovery():
    before, desired, live = documents()
    for document in (before, desired, live):
        document['rows'][IDENTITY]['native']['schema'] = 'public'
    desired['rows'][IDENTITY]['native']['catalog_row']['relname'] = ' Renamed " ü '
    plan = build_plan(before, desired, live)
    assert plan['application_supported'], plan['blockers']
    operation = plan['operations'][0]
    assert operation['operation'] == 'rename_relation'
    assert operation['resource_id'] == IDENTITY and operation['lock_target']['oid'] == 16384
    live['rows'][IDENTITY]['native']['catalog_row']['relname'] = ' Renamed " ü '
    live['rows'][IDENTITY]['path'][-1] = ' Renamed " ü '
    live['rows'][IDENTITY]['name'] = ' Renamed " ü '
    live['rows'][IDENTITY]['native']['sql_identity'] = 'public." Renamed "" ü "'
    converged = build_plan(before, desired, live)
    assert not converged['blockers'] and not converged['operations'] and converged['counts']['converged']==1


@pytest.mark.parametrize('failure',['concurrent','destination','inheritance','mixed','overlength'])
def test_relation_rename_refuses_conflicts_and_unsupported_combinations(failure):
    before, desired, live = documents()
    for document in (before, desired, live):
        document['rows'][IDENTITY]['native']['schema'] = 'public'
    desired['rows'][IDENTITY]['native']['catalog_row']['relname'] = 'wanted'
    if failure == 'concurrent':
        live['rows'][IDENTITY]['native']['catalog_row']['relname'] = 'independent'
        live['rows'][IDENTITY]['path'][-1] = 'independent'
    elif failure == 'destination':
        other=deepcopy(live['rows'][IDENTITY]);other['native']['catalog_row']['relname']='wanted'
        live['rows']['postgresql:pg_class:99999']=other
    elif failure == 'inheritance':
        live['rows'][IDENTITY]['native']['catalog_row']['relhassubclass']=True
    elif failure == 'mixed':
        desired['rows'][IDENTITY]['native']['comment']='mixed change'
    else:
        desired['rows'][IDENTITY]['native']['catalog_row']['relname']='ü'*32
    assert not build_plan(before, desired, live)['ready_for_review']


def test_column_default_set_drop_and_concurrent_change_preserve_native_identity():
    before, desired, live = column_documents()
    for document in (before,desired,live):
        document['rows'][IDENTITY]['native']['schema']='public'
        document['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['default_expression']=None
    wanted=desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]
    wanted['default_expression']='42'
    plan=build_plan(before,desired,live)
    assert plan['application_supported'],plan['blockers']
    assert plan['operations'][0]['operation']=='set_default'
    assert plan['operations'][0]['statement'].endswith(' SET DEFAULT 42')
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['default_expression']='43'
    assert not build_plan(before,desired,live)['ready_for_review']
    live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['default_expression']='42'
    assert not build_plan(before,desired,live)['operations']
    before=deepcopy(live);desired=deepcopy(live)
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['default_expression']=None
    assert build_plan(before,desired,live)['operations'][0]['statement'].endswith(' DROP DEFAULT')


@pytest.mark.parametrize('failure',['identity','generated','inheritance','missing','injection'])
def test_default_changes_refuse_ambiguous_or_nonordinary_columns(failure):
    before,desired,live=column_documents()
    for document in (before,desired,live):
        document['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['default_expression']=None
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['default_expression']='42'
    column=live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]
    if failure=='identity':column['attidentity']='a'
    elif failure=='generated':column['attgenerated']='s'
    elif failure=='inheritance':column['attinhcount']=1
    elif failure=='missing':del before['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['default_expression']
    else:desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['default_expression']='1); DROP TABLE x;--'
    assert not build_plan(before,desired,live)['ready_for_review']


def test_column_type_change_uses_native_type_and_detects_concurrent_changes():
    before, desired, live = column_documents()
    for document in (before, desired, live):
        document['rows'][IDENTITY]['native']['schema']='public'
        document['rows'][IDENTITY]['native']['children']['pg_attribute'][0].update(formatted_type='integer',atttypid=23,atttypmod=-1)
    wanted=desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]
    wanted['formatted_type']='numeric(20, 4)'
    plan=build_plan(before,desired,live)
    assert plan['application_supported'],plan['blockers']
    assert plan['operations'][0]['operation']=='set_type'
    assert 'numeric' in plan['operations'][0]['statement'].lower()
    current=live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]
    current['atttypid']=999
    assert not build_plan(before,desired,live)['ready_for_review']
    current.update(formatted_type='numeric(20, 4)',atttypid=1700)
    assert not build_plan(before,desired,live)['operations']


@pytest.mark.parametrize('failure',['identity','generated','inherited','partition','injection'])
def test_column_type_refuses_unadmitted_or_injected_changes(failure):
    before,desired,live=column_documents()
    for document in (before,desired,live):
        document['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['formatted_type']='integer'
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['formatted_type']='bigint'
    current=live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]
    if failure=='identity':current['attidentity']='a'
    elif failure=='generated':current['attgenerated']='s'
    elif failure=='inherited':current['attinhcount']=1
    elif failure=='partition':live['rows'][IDENTITY]['native']['catalog_row']['relispartition']=True
    else:desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['formatted_type']='integer; DROP TABLE x'
    assert not build_plan(before,desired,live)['ready_for_review']


def test_explicit_relation_drop_preserves_identity_and_converges_only_original_oid():
    before,desired,live=documents()
    for document in (before,desired,live):document['rows'][IDENTITY]['native']['schema']='public'
    desired['rows'][IDENTITY]['native']['drop']=True
    plan=build_plan(before,desired,live)
    assert plan['application_supported'],plan['blockers']
    assert plan['operations'][0]['operation']=='drop_relation'
    assert plan['operations'][0]['statement'].endswith(' RESTRICT')
    replacement=live['rows'].pop(IDENTITY)
    replacement['native']['oid']=17000
    live['rows']['postgresql:pg_class:17000']=replacement
    result=build_plan(before,desired,live)
    assert result['ready_for_review'] and not result['operations']
    assert result['counts']['converged']==1


@pytest.mark.parametrize('failure',['false','system','changed','mixed','inheritance'])
def test_relation_drop_refuses_implicit_or_unreviewed_changes(failure):
    before,desired,live=documents()
    for document in (before,desired,live):document['rows'][IDENTITY]['native']['schema']='public'
    desired['rows'][IDENTITY]['native']['drop']=True
    if failure=='false':desired['rows'][IDENTITY]['native']['drop']=False
    elif failure=='system':live['rows'][IDENTITY]['system']='true'
    elif failure=='changed':live['rows'][IDENTITY]['native']['comment']='another owner changed it'
    elif failure=='mixed':desired['rows'][IDENTITY]['native']['comment']='new comment'
    else:
        for document in (before,desired,live):document['rows'][IDENTITY]['native']['catalog_row']['relhassubclass']=True
    assert not build_plan(before,desired,live)['ready_for_review']


def owned_documents(kind):
    catalog, owner_field, name_field, keyword = {
        'trigger': ('pg_trigger', 'tgrelid', 'tgname', 'TRIGGER'),
        'rule': ('pg_rewrite', 'ev_class', 'rulename', 'RULE'),
        'policy': ('pg_policy', 'polrelid', 'polname', 'POLICY'),
    }[kind]
    baseline = documents()[0]
    baseline['rows'][IDENTITY]['native']['schema'] = 'public'
    child_id = 'postgresql:' + catalog + ':17001'
    baseline['rows'][child_id] = {'resource_id': child_id, 'kind': kind,
        'name': 'quoted " child', 'system': 'false', 'path': ['db', 'public', 'quoted " child'],
        'native': {'catalog': catalog, 'oid': 17001, 'schema': 'public', 'comment': None,
            'sql_identity': '"quoted "" child" ON public."Mixed "" name"',
            'catalog_row': {owner_field: 16384, name_field: 'quoted " child'}}}
    return child_id, tuple(deepcopy(baseline) for _ in range(3)), keyword


@pytest.mark.parametrize('kind', ['trigger', 'rule', 'policy'])
def test_table_owned_drop_locks_exact_owner_and_preserves_replacement(kind):
    identity, (baseline, desired, live), keyword = owned_documents(kind)
    desired['rows'][identity]['native']['drop'] = True
    plan = build_plan(baseline, desired, live)
    assert plan['application_supported'], plan['blockers']
    operation = plan['operations'][0]
    assert operation['lock_target']['oid'] == 16384
    assert operation['statement'] == 'DROP ' + keyword + ' "quoted "" child" ON "public"."Mixed "" name" RESTRICT'
    assert operation['operation'] == 'drop_table_owned'
    old = live['rows'].pop(identity)
    old['native']['oid'] = 17002
    old['resource_id'] = identity.rsplit(':', 1)[0] + ':17002'
    live['rows'][old['resource_id']] = old
    converged = build_plan(baseline, desired, live)
    assert converged['ready_for_review'] and not converged['operations']
    assert converged['counts']['converged'] == 1


@pytest.mark.parametrize('kind', ['trigger', 'rule', 'policy'])
def test_table_owned_comment_admits_exact_parent_and_refuses_native_drift(kind):
    identity, (baseline, desired, live), _ = owned_documents(kind)
    desired['rows'][identity]['native']['comment'] = 'Reviewed comment'
    plan = build_plan(baseline, desired, live)
    assert plan['application_supported'], plan['blockers']
    assert plan['operations'][0]['lock_target']['oid'] == 16384
    live['rows'][identity]['native']['comment'] = 'Independent comment'
    assert build_plan(baseline, desired, live)['blockers']


@pytest.mark.parametrize('failure', ['parent_missing', 'partition', 'constraint', 'internal', 'changed_child'])
def test_table_owned_drop_refuses_unqualified_ownership_or_changes(failure):
    identity, (baseline, desired, live), _ = owned_documents('trigger')
    desired['rows'][identity]['native']['drop'] = True
    if failure == 'parent_missing': del live['rows'][IDENTITY]
    if failure == 'partition': live['rows'][IDENTITY]['native']['catalog_row']['relispartition'] = True
    if failure == 'constraint':
        for document in (baseline, desired, live):
            document['rows'][identity]['native']['catalog_row']['tgconstraint'] = 999
    if failure == 'internal':
        for document in (baseline, desired, live):
            document['rows'][identity]['native']['catalog_row']['tgisinternal'] = True
    if failure == 'changed_child': live['rows'][identity]['native']['comment'] = 'changed'
    plan = build_plan(baseline, desired, live)
    assert plan['blockers'] and not plan['application_supported']


@pytest.mark.parametrize('kind,name_field', [('trigger','tgname'),('rule','rulename'),('policy','polname')])
def test_table_owned_rename_preserves_oid_other_properties_and_converges(kind, name_field):
    identity,(baseline,desired,live),keyword=owned_documents(kind)
    wanted=' renamed " ü '
    desired['rows'][identity]['native']['catalog_row'][name_field]=wanted
    live['rows'][identity]['native']['comment']='independent comment'
    plan=build_plan(baseline,desired,live)
    assert plan['application_supported'],plan['blockers']
    operation=plan['operations'][0]
    assert operation['statement']=='ALTER '+keyword+' "quoted "" child" ON "public"."Mixed "" name" RENAME TO " renamed "" ü "'
    assert operation['resource_id']==identity and operation['lock_target']['oid']==16384
    live['rows'][identity]['native']['catalog_row'][name_field]=wanted
    plan=build_plan(baseline,desired,live)
    assert plan['counts']['converged']==1 and not plan['operations'] and not plan['blockers']


@pytest.mark.parametrize('failure', ['changed_definition','changed_owner','changed_name','collision','oversized'])
def test_table_owned_rename_refuses_ambiguous_or_unreviewed_change(failure):
    identity,(baseline,desired,live),_=owned_documents('policy')
    desired['rows'][identity]['native']['catalog_row']['polname']='new'
    if failure=='changed_definition':desired['rows'][identity]['native']['catalog_row']['using_sql']='false'
    if failure=='changed_owner':live['rows'][identity]['native']['catalog_row']['polrelid']=999
    if failure=='changed_name':live['rows'][identity]['native']['catalog_row']['polname']='someone else'
    if failure=='oversized':desired['rows'][identity]['native']['catalog_row']['polname']='é'*32
    if failure=='collision':
        other=deepcopy(live['rows'][identity]);other['native']['oid']=17002
        other['native']['catalog_row']['polname']='new'
        live['rows']['postgresql:pg_policy:17002']=other
    plan=build_plan(baseline,desired,live)
    assert plan['blockers'] and not plan['application_supported']


@pytest.mark.parametrize('kind,field', [('trigger', 'tgenabled'), ('rule', 'ev_enabled')])
@pytest.mark.parametrize('state,clause', [('O', 'ENABLE'), ('D', 'DISABLE'),
    ('R', 'ENABLE REPLICA'), ('A', 'ENABLE ALWAYS')])
def test_table_owned_activation_native_states_lock_parent_and_converge(kind, field, state, clause):
    identity, (baseline, desired, live), keyword = owned_documents(kind)
    for document in (baseline, desired, live):
        document['rows'][identity]['native']['catalog_row'][field] = 'D' if state == 'O' else 'O'
    desired['rows'][identity]['native']['catalog_row'][field] = state
    plan = build_plan(baseline, desired, live)
    assert plan['application_supported'], plan['blockers']
    operation = plan['operations'][0]
    assert operation['statement'] == ('ALTER TABLE ONLY "public"."Mixed "" name" ' +
        clause + ' ' + keyword + ' "quoted "" child"')
    assert operation['lock_target']['oid'] == 16384 and operation['resource_id'] == identity
    live['rows'][identity]['native']['catalog_row'][field] = state
    plan = build_plan(baseline, desired, live)
    assert not plan['blockers'] and not plan['operations'] and plan['counts']['converged'] == 1


@pytest.mark.parametrize('failure', ['mixed', 'definition', 'concurrent', 'owner',
    'internal', 'constraint', 'partition', 'missing', 'unknown', 'malformed'])
def test_table_owned_activation_rejects_unreviewed_or_unsupported_state(failure):
    identity, (baseline, desired, live), _ = owned_documents('trigger')
    for document in (baseline, desired, live):
        document['rows'][identity]['native']['catalog_row']['tgenabled'] = 'O'
    desired['rows'][identity]['native']['catalog_row']['tgenabled'] = 'D'
    if failure == 'mixed': desired['rows'][identity]['native']['comment'] = 'also changed'
    if failure == 'definition': live['rows'][identity]['native']['catalog_row']['tgfoid'] = 999
    if failure == 'concurrent': live['rows'][identity]['native']['catalog_row']['tgenabled'] = 'R'
    if failure == 'owner': live['rows'][identity]['native']['catalog_row']['tgrelid'] = 999
    if failure in ('internal', 'constraint'):
        for document in (baseline, desired, live):
            document['rows'][identity]['native']['catalog_row'][
                'tgisinternal' if failure == 'internal' else 'tgconstraint'] = True if failure == 'internal' else 999
    if failure == 'partition': live['rows'][IDENTITY]['native']['catalog_row']['relispartition'] = True
    if failure == 'missing': live['rows'].pop(identity)
    if failure == 'unknown': desired['rows'][identity]['native']['catalog_row']['tgenabled'] = 'ALL'
    if failure == 'malformed': desired['rows'][identity]['native']['catalog_row']['tgenabled'] = []
    plan = build_plan(baseline, desired, live)
    assert plan['blockers'] and not plan['application_supported']


def security_documents():
    result = documents()
    for document in result:
        native = document['rows'][IDENTITY]['native']
        native['schema'] = 'public'
        native['catalog_row'].update(relrowsecurity=False, relforcerowsecurity=False)
    return result


@pytest.mark.parametrize('field,desired_value,clause', [
    ('relrowsecurity', True, 'ENABLE'), ('relrowsecurity', False, 'DISABLE'),
    ('relforcerowsecurity', True, 'FORCE'), ('relforcerowsecurity', False, 'NO FORCE')])
def test_row_security_switches_compile_exact_native_flags(field, desired_value, clause):
    baseline, desired, live = security_documents()
    for document in (baseline, desired, live):
        document['rows'][IDENTITY]['native']['catalog_row'][field] = not desired_value
    desired['rows'][IDENTITY]['native']['catalog_row'][field] = desired_value
    plan = build_plan(baseline, desired, live)
    assert plan['application_supported'], plan['blockers']
    operation = plan['operations'][0]
    assert operation['statement'] == 'ALTER TABLE ONLY "public"."Mixed "" name" ' + clause + ' ROW LEVEL SECURITY'
    assert operation['lock_target']['oid'] == 16384 and operation['field'] == field
    live['rows'][IDENTITY]['native']['catalog_row'][field] = desired_value
    plan = build_plan(baseline, desired, live)
    assert not plan['operations'] and not plan['blockers'] and plan['counts']['converged'] == 1


def test_row_security_switches_handle_partial_convergence():
    baseline, desired, live = security_documents()
    desired['rows'][IDENTITY]['native']['catalog_row'].update(relrowsecurity=True, relforcerowsecurity=True)
    live['rows'][IDENTITY]['native']['catalog_row']['relrowsecurity'] = True
    plan = build_plan(baseline, desired, live)
    assert plan['application_supported'] and plan['counts']['converged'] == 1
    assert len(plan['operations']) == 1 and plan['operations'][0]['field'] == 'relforcerowsecurity'


@pytest.mark.parametrize('failure', ['missing', 'oid', 'mixed', 'owner', 'comment',
    'other_flag', 'partition', 'inheritance', 'foreign', 'not_boolean'])
def test_row_security_switches_reject_unreviewed_changes(failure):
    baseline, desired, live = security_documents()
    desired['rows'][IDENTITY]['native']['catalog_row']['relrowsecurity'] = True
    if failure == 'missing': live['rows'].pop(IDENTITY)
    if failure == 'oid': live['rows'][IDENTITY]['native']['oid'] = 999
    if failure == 'mixed': desired['rows'][IDENTITY]['native']['comment'] = 'changed'
    if failure == 'owner': live['rows'][IDENTITY]['native']['catalog_row']['relowner'] = 999
    if failure == 'comment': live['rows'][IDENTITY]['native']['comment'] = 'changed'
    if failure == 'other_flag': live['rows'][IDENTITY]['native']['catalog_row']['relforcerowsecurity'] = True
    if failure == 'partition': live['rows'][IDENTITY]['native']['catalog_row']['relispartition'] = True
    if failure == 'inheritance': live['rows'][IDENTITY]['native']['children'] = {'pg_inherits': [{'inhparent': 999}]}
    if failure == 'foreign':
        for document in (baseline, desired, live): document['rows'][IDENTITY]['kind'] = 'foreign-table'
    if failure == 'not_boolean': desired['rows'][IDENTITY]['native']['catalog_row']['relrowsecurity'] = 1
    plan = build_plan(baseline, desired, live)
    assert plan['blockers'] and not plan['application_supported']


def column_drop_documents():
    docs = column_documents()
    for doc in docs:
        doc['rows'][IDENTITY]['native']['schema'] = 'public'
    docs[1]['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['drop'] = True
    return docs


def test_explicit_column_drop_is_locked_restrict_and_converges_without_replay():
    before, desired, live = column_drop_documents()
    plan = build_plan(before, desired, live)
    assert plan['application_supported'], plan['blockers']
    operation = plan['operations'][0]
    assert operation['operation'] == 'drop_column'
    assert operation['lock_target']['oid'] == 16384
    assert operation['statement'].endswith('DROP COLUMN "Odd "" column" RESTRICT')
    live['rows'][IDENTITY]['native']['children']['pg_attribute'].pop(0)
    plan = build_plan(before, desired, live)
    assert not plan['operations'] and not plan['blockers'] and plan['counts']['converged'] == 1


@pytest.mark.parametrize('change', ['renamed', 'replaced', 'default', 'inherited', 'partition', 'mixed', 'false'])
def test_column_drop_refuses_concurrent_changes_and_unsupported_scope(change):
    before, desired, live = column_drop_documents()
    attribute = live['rows'][IDENTITY]['native']['children']['pg_attribute'][0]
    if change == 'renamed': attribute['attname'] = 'new-name'
    elif change == 'replaced': attribute['attnum'] = 3
    elif change == 'default': attribute['default_expression'] = '42'
    elif change == 'inherited': attribute['attinhcount'] = 1
    elif change == 'partition': live['rows'][IDENTITY]['native']['catalog_row']['relispartition'] = True
    elif change == 'mixed': desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['comment'] = 'mixed'
    elif change == 'false': desired['rows'][IDENTITY]['native']['children']['pg_attribute'][0]['drop'] = False
    assert not build_plan(before, desired, live)['ready_for_review']


def test_column_omission_does_not_create_drop_intent():
    before, desired, live = column_drop_documents()
    desired['rows'][IDENTITY]['native']['children']['pg_attribute'].pop(0)
    plan = build_plan(before, desired, live)
    assert not plan['ready_for_review'] and not plan['operations']


def addition_documents():
    import uuid
    docs = column_documents()
    for doc in docs:
        doc['rows'][IDENTITY]['native']['schema'] = 'public'
    docs[1]['rows'][IDENTITY]['native']['add_columns'] = [
        {'resource_id': 'postgresql:new:' + str(uuid.uuid4()),
         'definition': {'name': 'new " column', 'data_type': 'numeric(12,2)', 'default': '12.34', 'nullable': False}}]
    return docs


def test_column_addition_uses_new_identity_and_parent_lock():
    before, desired, live = addition_documents()
    plan = build_plan(before, desired, live)
    assert plan['application_supported'], plan['blockers']
    operation = plan['operations'][0]
    assert operation['operation'] == 'add_column' and operation['parent_resource_id'] == IDENTITY
    assert operation['lock_target']['oid'] == 16384
    assert 'ADD COLUMN "new "" column" numeric(12, 2) DEFAULT (12.34) NOT NULL' in operation['statement']


@pytest.mark.parametrize('change', ['exists', 'repeated', 'invalid_id', 'native_id', 'mixed', 'drift', 'inherited', 'empty', 'sql'])
def test_column_addition_rejects_ambiguous_drafts_and_parent_changes(change):
    before, desired, live = addition_documents()
    native = desired['rows'][IDENTITY]['native']
    draft = native['add_columns'][0]
    if change == 'exists': draft['definition']['name'] = 'second'
    elif change == 'repeated': native['add_columns'].append(deepcopy(draft))
    elif change == 'invalid_id': draft['resource_id'] = 'postgresql:new:not-a-uuid'
    elif change == 'native_id': draft['resource_id'] = 'postgresql:pg_attribute:16384:3'
    elif change == 'mixed': native['comment'] = 'another change'
    elif change == 'drift': live['rows'][IDENTITY]['native']['comment'] = 'concurrent'
    elif change == 'inherited':
        for doc in (before, desired, live):doc['rows'][IDENTITY]['native']['catalog_row']['relhassubclass'] = True
    elif change == 'empty': native['add_columns'] = []
    elif change == 'sql': draft['definition']['data_type'] = 'integer); DROP TABLE t; --'
    assert not build_plan(before, desired, live)['ready_for_review']
