"""Native MariaDB recipe syntax must not inherit incompatible MySQL expressions."""
import pytest
from tools.tests.test_mysql_test_data import model as mysql_model, recipe as mysql_recipe
from pgadmin.cdeadmin.workspace.mariadb_test_data import generate, template, FORMAT
from pgadmin.cdeadmin.workspace.mysql_test_data import literal


def model():
    value = mysql_model();value['provenance']['mapping'] = 'scratchrobin.mariadb.catalog@1'
    return value


def test_native_maria_recipe_supports_exact_types_parent_allocation_and_native_json_vector():
    value = mysql_recipe([{'table': 'parent', 'count': 2, 'columns': {'id': {'kind': 'default'},
        'value': {'kind': 'constant', 'value': {'type': 'json', 'value': '{"n":9007199254740993}'}}}},
        {'table': 'child', 'count': 2, 'columns': {'id': {'kind': 'returned', 'table': 'parent', 'column': 'id'},
        'value': {'kind': 'constant', 'value': {'type': 'vector', 'value': '[1,2]'}}}}])
    value['format'] = FORMAT
    result = generate(model(), value)
    assert result['format'] == template(model())['format'] == FORMAT
    assert result['source'] == generate(model(), value)['source']
    assert 'VEC_FromText(' in result['source'] and 'CAST(' not in result['source']
    assert 'STRING_TO_VECTOR' not in result['source'] and not result['executed']
    assert 'DO LAST_INSERT_ID(0)' in result['source']
    for unsupported in ('START TRANSACTION;', 'COMMIT;', 'ROLLBACK;', 'FOREIGN_KEY_CHECKS', 'NEXT VALUE FOR'):
        assert unsupported not in result['source']
    assert not template(model())['tables'][0]['columns'][2]['insertable']
    assert literal({'type': 'decimal', 'value': '12345678901234567890.12345678901234567890'}, engine='mariadb') == '12345678901234567890.12345678901234567890'


def test_native_maria_rejects_cross_engine_recipe_catalog_and_scope():
    base = mysql_recipe([{'table': 'parent', 'count': 1, 'columns': {}}]);base['format'] = FORMAT
    for altered in ({**base, 'format': 'scratchrobin.mysql.test-data@1'}, {**base, 'scope': {'endpoint_id': 'foreign', 'database_target_id': 'db'}}):
        with pytest.raises(ValueError):generate(model(), altered)
    with pytest.raises(ValueError):generate(mysql_model(), base)
    with pytest.raises(ValueError):literal({'type': 'json', 'value': '{"x":NaN}'}, engine='mariadb')
