"""CHECK toggles retain table identity and exclude other constraint kinds."""
import pytest
from pgadmin.cdeadmin.providers.mysql_constraints import compile_operation
from pgadmin.cdeadmin.sdk.relational import RelationalClientError

TARGET = {'display_path': ['d`é', 't`é', 'c`é'], 'native': {'constraint_type': 'CHECK'}}


def test_check_enforcement_compiles_exact_native_target():
    for state in ('ENFORCED', 'NOT ENFORCED'):
        result = compile_operation('enforcement', {'enforcement': state}, TARGET)
        assert result == {'source': 'ALTER TABLE `d``é`.`t``é` ALTER CHECK `c``é` ' + state, 'parameters': ()}


@pytest.mark.parametrize('kind', ['PRIMARY KEY', 'UNIQUE', 'FOREIGN KEY', None])
def test_non_check_constraints_cannot_be_toggled(kind):
    with pytest.raises(RelationalClientError):
        compile_operation('enforcement', {'enforcement': 'NOT ENFORCED'}, {**TARGET, 'native': {'constraint_type': kind}})


@pytest.mark.parametrize('draft', [{}, {'enforcement': 'DISABLED'}, {'enforcement': 'ENFORCED; DROP TABLE t'}, {'enforcement': 'ENFORCED', 'cascade': True}])
def test_enforcement_refuses_unknown_states_and_options(draft):
    with pytest.raises(RelationalClientError):
        compile_operation('enforcement', draft, TARGET)


def test_mysql_check_catalog_publishes_targeted_confirmed_form():
    from pgadmin.cdeadmin.providers.mysql_family.provider import MYSQL_ADMINISTRATION, MARIADB_ADMINISTRATION
    from pgadmin.cdeadmin.visual_admin.catalog import catalog_for_engine
    catalog = MYSQL_ADMINISTRATION.catalog(catalog_for_engine('mysql'))
    row = next(r for r in catalog['objects'] if r['resource_kind'] == 'constraint')
    operation = next(r for r in row['operations'] if r['operation_id'] == 'enforcement')
    assert operation['target_required'] and operation['confirmation_required']
    assert operation['form']['fields'][0]['initial_value_path'] == ['enforcement']
    assert not MARIADB_ADMINISTRATION.supports('constraint', 'enforcement')
    request = {'resource_kind': 'constraint', 'operation_id': 'enforcement', 'target_resource': TARGET,
               'draft': {'enforcement': 'NOT ENFORCED'}}
    assert not MYSQL_ADMINISTRATION.validate(request)['errors']
    assert 'ALTER CHECK' in MYSQL_ADMINISTRATION._compile(request)['statements'][0]['source']
