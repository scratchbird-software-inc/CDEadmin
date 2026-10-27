"""Native aggregate admission cannot infer a user macro's result type."""
import duckdb
import pytest

from pgadmin.cdeadmin.providers.duckdb.editor_type_rules import aggregate_type_rules
from pgadmin.cdeadmin.providers.native_editor import metadata


def test_native_catalog_admits_qualified_core_shapes_and_shadowing_removes_only_affected_rule():
    with duckdb.connect() as connection:
        connection.execute('CREATE TABLE one(value STRUCT("Field ü" BIGINT))')
        connection.execute('INSERT INTO one VALUES(struct_pack("Field ü":=7))')
        connection.execute('BEGIN')
        connection.execute('INSERT INTO one VALUES(struct_pack("Field ü":=8))')
        first = metadata(connection, 'duckdb')
        rules = first['context']['aggregate_type_rules']
        assert set(rules) == {'min','max','first','last','any_value','arbitrary','list','array_agg'}
        for name, rule in rules.items():
            result = connection.sql('SELECT ' + name + '(value) FROM one').types[0]
            assert result.id == ('list' if rule['argument'] == 'list' else 'struct')
        connection.execute('CREATE MACRO max(x) AS 42')
        assert connection.sql('SELECT max(value) FROM one').types[0].id == 'integer'
        changed = metadata(connection, 'duckdb')
        assert 'max' not in changed['context']['aggregate_type_rules']
        assert set(changed['context']['aggregate_type_rules']) == set(rules) - {'max'}
        assert changed['context']['context_revision'] != first['context']['context_revision']
        connection.execute('ROLLBACK')
        assert connection.execute('SELECT count(*) FROM one').fetchone()[0] == 1
        assert metadata(connection,'duckdb')['context']['aggregate_type_rules'] == rules


@pytest.mark.parametrize('version,truncated', [('v1.5.3', False), ('v1.5.2', True)])
def test_other_versions_and_incomplete_function_inventory_cannot_admit_rules(version,truncated):
    rows=[('system','main','max','aggregate',['arg'],['ANY'],'ANY',True)]
    assert aggregate_type_rules(version, rows, truncated) == {}


@pytest.mark.parametrize('replacement', [
    ('system','main','max','aggregate',['arg'],['ANY'],'VARCHAR',True),
    ('system','main','max','aggregate',['arg'],['ANY'],'ANY',False),
    ('system','main','max','macro',['arg'],['ANY'],'ANY',True),
    ('owned','main','max','aggregate',['arg'],['ANY'],'ANY',True),
])
def test_changed_core_signature_or_origin_is_not_a_native_shape_rule(replacement):
    assert aggregate_type_rules('v1.5.2',[replacement],False) == {}
