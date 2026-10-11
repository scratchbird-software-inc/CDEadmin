from copy import deepcopy
import pytest
from tools.tests.test_firebird_schema_plan import document, obj
from pgadmin.cdeadmin.workspace.firebird_schema_plan import build_plan


def param(name='A', position=0, **changes):
    return {'name': name, 'position': position, 'mode': 'input', 'field_type': 8,
            'field_sub_type': 0, 'field_scale': 0, 'not_null': None, **changes}


def procedure(**changes):
    return obj('procedure', 'P', **{'parameters': [param(default_source='DEFAULT 2'),
        param('R', mode='output')], 'metadata_source': 'BEGIN R = A + 1; SUSPEND; END',
        'sql_security': None, 'entrypoint': None, 'engine_name': None, 'description': None, **changes})


def function(**changes):
    return obj('function', 'F', **{'parameters': [param('A', 1, return_value=False),
        param(None, 0, return_value=True)], 'metadata_source': 'BEGIN RETURN A + 1; END',
        'sql_security': None, 'entrypoint': None, 'engine_name': None, 'description': None,
        'deterministic': 1, **changes})


def catalog(*rows):
    result = document(list(rows))
    result['rows']['database:database']['native']['catalog_observations'] = [
        {'section': name, 'available': True} for name in ('procedure objects', 'function objects',
            'procedure parameters', 'function arguments')]
    return result


@pytest.mark.parametrize('factory,signature', [(procedure, 'CREATE PROCEDURE "P" ("A" INTEGER DEFAULT 2\n) RETURNS ("R" INTEGER)'),
    (function, 'CREATE FUNCTION "F" ("A" INTEGER) RETURNS INTEGER\nDETERMINISTIC')])
def test_native_creation_uses_structured_signature_and_whole_body(factory, signature):
    base = catalog(); desired = catalog(factory(ddl='DROP DATABASE'))
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert result['operations'][0]['statements'][0].startswith(signature + '\nAS\nBEGIN')
    assert 'DROP DATABASE' not in result['script']


def test_body_alter_preserves_signature_and_independent_live_comment():
    base = catalog(procedure()); desired = catalog(procedure(metadata_source='BEGIN R = A + 2; SUSPEND; END'))
    result = build_plan(base, desired, catalog(procedure(description='independent')))
    assert result['status'] == 'review-ready', result['blockers']
    operation = result['operations'][0]
    assert operation['statements'][0].startswith('ALTER PROCEDURE')
    assert 'RECREATE' not in result['script'] and 'DROP PROCEDURE' not in result['script']
    assert operation['after']['description'] == 'independent'
    assert build_plan(base, desired, desired)['status'] == 'no-op'


def test_parameter_comments_and_exact_named_domain_reference():
    native = {'field_type': 8, 'field_sub_type': 0, 'field_scale': 0}
    domain = obj('domain', 'D', **native)
    base = catalog(domain)
    wanted = catalog(domain, procedure(parameters=[param(domain='D', mechanism=1, description="owner's input")],
                                       metadata_source='BEGIN END'))
    plan = build_plan(base, wanted, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert '"A" TYPE OF "D"' in plan['script']
    assert 'COMMENT ON PROCEDURE PARAMETER "P"."A" IS \'owner\'\'s input\'' in plan['script']
    wanted['rows']['procedure:P']['native']['parameters'][0]['field_type'] = 16
    assert build_plan(base, wanted, base)['status'] == 'blocked'


@pytest.mark.parametrize('parameters', [[param(position=1)], [param(), param()],
    [param(default_source='DEFAULT 1; DROP TABLE T')], [param(field_type=999)],
    [param(mechanism=1)], [param(unrecognized_native_fact=True)]])
def test_invalid_parameter_signatures_refuse(parameters):
    base = catalog()
    assert build_plan(base, catalog(procedure(parameters=parameters)), base)['status'] == 'blocked'


def test_missing_return_packaged_member_and_conflicting_source_refuse():
    base = catalog()
    assert build_plan(base, catalog(function(parameters=[])), base)['status'] == 'blocked'
    assert build_plan(base, catalog(procedure(package='PKG')), base)['status'] == 'blocked'
    base = catalog(function())
    desired = catalog(function(metadata_source='BEGIN RETURN 2; END'))
    assert build_plan(base, desired, catalog(function(metadata_source='BEGIN RETURN 3; END')))['status'] == 'blocked'
    unavailable = deepcopy(base); unavailable['rows']['database:database']['native']['catalog_observations'] = []
    assert build_plan(base, desired, unavailable)['status'] == 'blocked'


def test_external_payload_is_quoted_and_security_is_not_synthesized():
    base = catalog()
    desired = catalog(procedure(parameters=[], engine_name='UDR', entrypoint='library!entry', metadata_source="payload ' text"))
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert plan['operations'][0]['statements'][0] == 'CREATE PROCEDURE "P"\nEXTERNAL NAME \'library!entry\' ENGINE "UDR"\nAS \'payload \'\' text\''
    desired['rows']['procedure:P']['native']['sql_security'] = 1
    assert build_plan(base, desired, base)['status'] == 'blocked'


def test_new_domain_signature_uses_projected_definition_and_native_ordering():
    base = catalog()
    domain = obj('domain', 'Z_DOMAIN', field_type=8, field_sub_type=0, field_scale=0,
                 dimensions=0, not_null=None, default_source=None, validation_source=None)
    desired = catalog(domain, procedure(parameters=[param(domain='Z_DOMAIN')], metadata_source='BEGIN END'))
    for value in (base, desired):
        value['rows']['database:database']['native']['catalog_observations'].append({'section': 'domain objects', 'available': True})
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    assert [item['resource_id'] for item in plan['operations']] == ['domain:Z_DOMAIN', 'procedure:P']


def test_type_of_existing_column_order_survives_saved_review_reduction(tmp_path):
    from tools.tests.test_firebird_column_plan import catalog as column_catalog
    from pgadmin.cdeadmin.workspace.firebird_schema_apply import SchemaApplications
    base = column_catalog()
    native = base['rows']['database:database']['native']
    native.update(guid='native-guid', file_id='native-file')
    native['catalog_observations'].extend([{'section': section, 'available': True}
                                          for section in ('procedure objects', 'procedure parameters')])
    desired = deepcopy(base)
    desired['rows']['procedure:P'] = catalog(procedure(parameters=[param(mechanism=1,
        relation_name='T', field_name='C')], metadata_source='BEGIN END'))['rows']['procedure:P']
    plan = build_plan(base, desired, base)
    assert plan['status'] == 'review-ready', plan['blockers']
    store = SchemaApplications(tmp_path / 'routine-review.json')
    review = store.review(plan, base, desired, 'owner', 'binding', 'db')
    def verify(record):
        replay = build_plan(record['baseline'], record['desired'], base)
        assert replay['execution_sha256'] == plan['execution_sha256']
        return {'state': 'not_executed'}
    result = store.apply({'review_id': review['review_id'], 'review_digest': review['review_digest'],
        'confirmed': True}, 'owner', 'binding', verify)
    assert result['state'] == 'not_executed', result


def test_mutual_new_routines_use_noncallable_signatures_and_final_bodies():
    base = catalog(); desired = catalog(function(), procedure())
    desired['rows']['function:F']['native']['creation_dependencies'] = ['procedure:P']
    desired['rows']['procedure:P']['native']['creation_dependencies'] = ['function:F']
    result = build_plan(base, desired, base)
    assert result['status'] == 'review-ready', result['blockers']
    assert all(item['signature_first'] for item in result['operations'])
    assert all('SCRATCHROBIN_INCOMPLETE_SCHEMA' in item['statements'][0] for item in result['operations'])
    assert all(item['deferred_statements'][0].startswith('ALTER ') for item in result['operations'])
    assert 'R = A + 1' in result['script'] and 'RETURN A + 1' in result['script']
    assert any('non-callable signatures' in warning for warning in result['warnings'])
    assert result['script'].startswith('-- Firebird') and 'SET AUTODDL OFF;' in result['script']
