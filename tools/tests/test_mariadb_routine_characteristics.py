"""MariaDB procedure/function create carries native routine characteristics."""
import json
from pathlib import Path

import pytest

from pgadmin.cdeadmin.providers.mysql_family.provider import MARIADB_ADMINISTRATION, MYSQL_ADMINISTRATION
from pgadmin.cdeadmin.sdk.relational import RelationalClientError

ROUTE = {'host': 'mariadb.example', 'route_id': 'mariadb-routines', 'database': 'inventory'}


def plan(kind, draft):
    return MARIADB_ADMINISTRATION.plan({'resource_kind': kind, 'operation_id': 'create', 'target_resource': None,
                                        'draft': draft, '_provider_route': ROUTE})['command_preview']['statements']


def test_function_declares_the_selected_characteristics_after_returns():
    statements = plan('function', {'name': 'f', 'parent': 'inventory', 'parameters': [{'name': 'a', 'type': 'INT'}],
                                   'returns': 'INT', 'body': 'RETURN a + 1', 'deterministic': 'DETERMINISTIC',
                                   'data_access': 'NO SQL', 'sql_security': 'INVOKER'})
    assert [item['source'] for item in statements] == [
        'CREATE FUNCTION `inventory`.`f` (`a` INT) RETURNS INT DETERMINISTIC NO SQL SQL SECURITY INVOKER RETURN a + 1']


def test_procedure_takes_characteristics_and_unset_ones_are_omitted():
    statements = plan('procedure', {'name': 'p', 'parent': 'inventory', 'parameters': [],
                                    'body': 'BEGIN SELECT 1; END', 'data_access': 'READS SQL DATA'})
    assert statements[0]['source'] == 'CREATE PROCEDURE `inventory`.`p` () READS SQL DATA BEGIN SELECT 1; END'
    statements = plan('procedure', {'name': 'p', 'parent': 'inventory', 'parameters': [], 'body': 'BEGIN SELECT 1; END',
                                    'deterministic': ''})
    assert statements[0]['source'] == 'CREATE PROCEDURE `inventory`.`p` () BEGIN SELECT 1; END'


@pytest.mark.parametrize('key, value', [('deterministic', 'DETERMINISTIC RETURN 1;'), ('deterministic', True),
                                        ('data_access', 'reads sql data'), ('sql_security', 'OWNER')])
def test_only_admitted_characteristic_values_are_rendered(key, value):
    with pytest.raises(RelationalClientError):
        plan('function', {'name': 'f', 'parent': 'inventory', 'parameters': [], 'returns': 'INT',
                          'body': 'RETURN 1', key: value})


def test_provider_and_descriptor_forms_offer_the_same_characteristics():
    descriptor = json.loads((Path(__file__).resolve().parents[2] /
                             'web/pgadmin/cdeadmin/ui_descriptors/mariadb/forms/routine.form.json').read_text())
    offered = {field['field_id']: [option['value'] for option in field['options']]
               for field in descriptor['fields'] if field['field_id'] in {'deterministic', 'data_access', 'sql_security'}}
    for kind in ('procedure', 'function'):
        form = MARIADB_ADMINISTRATION._form(kind, 'create')
        provider = {field['field_id']: [option['value'] for option in field['options']]
                    for field in form['fields'] if field['field_id'] in offered}
        assert provider == offered
    assert 'deterministic' not in {field['field_id'] for field in MARIADB_ADMINISTRATION._form('package', 'create')['fields']}
    assert MYSQL_ADMINISTRATION.dialect.routine_characteristics == {}
