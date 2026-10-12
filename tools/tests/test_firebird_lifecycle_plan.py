from copy import deepcopy
import pytest
from tools.tests.test_firebird_column_plan import catalog as column_catalog
from tools.tests.test_firebird_domain_plan import catalog as original_domain_catalog, domain
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan
from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications


def catalog(**kwargs):
    result = column_catalog(**kwargs)
    for row in result['rows'].values(): row['system'] = 'false'
    return result


def domain_catalog(*rows):
    result = original_domain_catalog(*rows)
    for row in result['rows'].values(): row['system'] = 'false'
    return result


def intent(base, identity, name):
    desired = deepcopy(base)
    row = desired['rows'][identity]
    row['native']['lifecycle'] = {'operation': 'rename', 'confirmation': row['name'], 'new_name': name}
    return desired


@pytest.mark.parametrize('kind', ['column', 'domain'])
def test_explicit_rename_preserves_review_instruction_and_exact_identity(kind, tmp_path):
    base = catalog() if kind == 'column' else domain_catalog(domain())
    base['rows']['database:database']['native']['catalog_observations'].append({'section': 'object privileges', 'available': True})
    identity = 'column:T:C' if kind == 'column' else 'domain:D"ü'
    desired = intent(base, identity, 'renamed " ü')
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    operation, = plan['operations']
    assert operation['operation'] == 'rename'
    assert operation['after']['name'] == 'renamed " ü'
    assert operation['statements'] == []
    assert operation['deferred_statements'][0].endswith('TO "renamed "" ü"')
    assert operation['native_preconditions'][operation['result_resource_id']] is None
    # Saving a review must not turn the explicit transition into a no-op.
    store = SchemaApplications(tmp_path / 'reviews.json')
    for document in (base, desired):
        document['rows']['database:database']['native'].update(guid='guid', file_id='file')
    plan = build_plan(base, desired, base)
    review = store.review(plan, base, desired, 'owner', 'binding', 'db')
    checked = []
    def apply(record):
        checked.append(build_plan(record['baseline'], record['desired'], base))
        return {'state': 'not_executed'}
    store.apply({'review_id': review['review_id'], 'review_digest': review['review_digest'],
                 'confirmed': True}, 'owner', 'binding', apply)
    assert checked[0]['execution_sha256'] == plan['execution_sha256']


@pytest.mark.parametrize('change', ['confirmation', 'extra', 'property', 'live', 'destination', 'system', 'kind'])
def test_rename_refuses_ambiguous_or_changed_identity(change):
    base = catalog(); desired = intent(base, 'column:T:C', 'NEW'); live = deepcopy(base)
    row = desired['rows']['column:T:C']
    if change == 'confirmation': row['native']['lifecycle']['confirmation'] = 'wrong'
    elif change == 'extra': row['native']['lifecycle']['cascade'] = True
    elif change == 'property': row['native']['description'] = 'different'
    elif change == 'live': live['rows']['column:T:C']['native']['description'] = 'concurrent'
    elif change == 'destination': live['rows']['column:T:NEW'] = deepcopy(row)
    elif change == 'system':
        for value in (base, desired, live): value['rows']['column:T:C']['system'] = 'true'
    elif change == 'kind':
        desired = intent(base, 'table:T', 'NEW')
    plan = build_plan(base, desired, live)
    assert plan['status'] == 'blocked' and plan['script'] is None


def test_column_grants_are_explicitly_remapped_and_guarded():
    base = catalog()
    base['rows']['database:database']['native']['catalog_observations'].append({'section': 'object privileges', 'available': True})
    base['rows']['privilege:grant'] = {'resource_id': 'privilege:grant', 'kind': 'privilege',
        'name': 'grant', 'path': ['grant'], 'system': 'false', 'native': {
            'grantee': 'WRITER', 'grantor': 'SYSDBA', 'grant_option': 1, 'user_type': 8,
            'object_type': 0, 'object_name': 'T', 'field': 'C', 'privilege': 'U'}}
    plan = build_plan(base, intent(base, 'column:T:C', 'NEW'), base)
    assert plan['status'] == 'review-ready', plan['blockers']
    operation, = plan['operations']
    assert operation['rename_statement_index'] == 1
    assert operation['deferred_statements'] == [
        'REVOKE UPDATE ("C") ON TABLE "T" FROM USER "WRITER" GRANTED BY USER "SYSDBA"',
        'ALTER TABLE "T" ALTER COLUMN "C" TO "NEW"',
        'GRANT UPDATE ("NEW") ON TABLE "T" TO USER "WRITER" WITH GRANT OPTION GRANTED BY USER "SYSDBA"']
    assert 'privilege:grant' in operation['native_preconditions']


def test_explicit_drop_orders_dependents_and_exposes_implicit_children():
    base = catalog(domain='D"ü')
    base['rows'].update({key: row for key, row in domain_catalog(domain())['rows'].items() if row['kind'] == 'domain'})
    desired = deepcopy(base)
    for identity in ('table:T', 'domain:D"ü'):
        row = desired['rows'][identity]
        row['native']['lifecycle'] = {'operation': 'drop', 'confirmation': row['name']}
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert [item['resource_id'] for item in plan['operations']] == ['table:T', 'domain:D"ü']
    assert plan['operations'][0]['implicit_child_removals'] == ['column:T:C']
    assert plan['operations'][0]['deferred_statements'] == ['DROP TABLE "T"']
    assert all(item['after'] is None for item in plan['operations'])
    del desired['rows']['column:T:C']
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_drop_confirmation_and_property_drift_are_not_implicit_consent():
    base = catalog(); desired = deepcopy(base)
    desired['rows']['column:T:C']['native']['lifecycle'] = {'operation': 'drop', 'confirmation': 'C'}
    assert build_plan(base, desired, base)['status'] == 'review-ready'
    live = deepcopy(base); live['rows']['column:T:C']['native']['description'] = 'changed'
    assert build_plan(base, desired, live)['status'] == 'blocked'
    desired['rows']['column:T:C']['native']['lifecycle']['confirmation'] = 'T'
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_explicit_domain_type_conversion_preserves_properties_and_guards():
    base = domain_catalog(domain(field_sub_type=0, field_scale=0, dimensions=0, field_length=4))
    desired = deepcopy(base)
    row = desired['rows']['domain:D"ü']
    row['native'].update(field_type=16, field_length=8, lifecycle={'operation': 'type', 'confirmation': row['name']})
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    operation, = plan['operations']
    assert operation['operation'] == 'alter_type'
    assert operation['statements'] == ['ALTER DOMAIN "D""ü" TYPE BIGINT']
    assert operation['after']['creation_type']['sql'] == 'BIGINT'
    row['native']['description'] = 'unrelated'
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_column_domain_rebinding_validates_expanded_facts():
    base = catalog()
    base['rows']['column:T:C']['native']['privileges'] = [{'grantee': 'WRITER', 'privilege': 'U'}]
    base['rows'].update({key: row for key, row in domain_catalog(domain(
        field_sub_type=0, field_scale=0, dimensions=0))['rows'].items() if row['kind'] == 'domain'})
    desired = deepcopy(base)
    native = desired['rows']['column:T:C']['native']
    native.update(domain='D"ü', domain_not_null=None, lifecycle={'operation': 'bind_domain', 'confirmation': 'C'})
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'] == ['ALTER TABLE "T" ALTER COLUMN "C" TYPE "D""ü"']
    native['privileges'] = []
    assert build_plan(base, desired, base)['status'] == 'blocked'
    native['privileges'] = deepcopy(base['rows']['column:T:C']['native']['privileges'])
    native['field_type'] = 16
    assert build_plan(base, desired, base)['status'] == 'blocked'
