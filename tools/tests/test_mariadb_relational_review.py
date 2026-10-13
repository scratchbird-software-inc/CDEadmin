"""MariaDB graphical edits preserve native periods and engine identity."""
from copy import deepcopy
import json
import pytest
from tools.tests.test_mariadb_catalog import Connection
from pgadmin.cdeadmin.providers.mysql_family.mariadb_catalog import capture
from pgadmin.cdeadmin.workspace.firebird_catalog_export import build_export
from pgadmin.cdeadmin.workspace.firebird_catalog_import import read_catalog
from pgadmin.cdeadmin.workspace.firebird_relational_review import read_relations, handoff
from pgadmin.cdeadmin.workspace.mysql_relational_fields import datatype, merge_fields, rename_definition
from pgadmin.cdeadmin.workspace.mariadb_schema_plan import alteration


def fixture():
    native = capture(Connection(), 'demo')
    return build_export(native['resources'], endpoint_id='owned', target_id='demo',
                        generation=native['generation'], engine='mariadb')


def test_graphical_maria_type_edit_reaches_native_catalog_without_execution():
    result = fixture(); original = result['diagram']['snapshot']; desired = deepcopy(original)
    mapped = read_relations(original, engine='mariadb')
    table = next(row for row in mapped.values() if row['fields'])
    # Edit the public DDN field rather than its embedded native CREATE definition.
    for name, source in desired['files'].items():
        assert 'datatype:"bigint"' in source
        desired['files'][name] = source.replace('datatype:"bigint"', 'datatype:"UUID"')
    value = handoff(result['snapshot'], original, desired, engine='mariadb')
    before, after = [read_catalog(value[key], engine='mariadb') for key in ('baseline', 'desired')]
    identity = table['resource_id']
    assert '`id` bigint PRIMARY KEY' in before['rows'][identity]['native']['definition']
    assert '`id` UUID PRIMARY KEY' in after['rows'][identity]['native']['definition']
    assert value['changed_resource_ids'] == [identity] and not value['executed']
    assert '`id` bigint' in read_catalog(json.dumps(result['snapshot']), engine='mariadb')['rows'][identity]['native']['definition']


@pytest.mark.parametrize('native_type', ['UUID', 'INET4', 'INET6', 'NUMBER(20, 2)', 'RAW(16)'])
def test_maria_native_types_are_not_enabled_on_mysql(native_type):
    assert datatype(native_type, '', engine='mariadb') == native_type
    with pytest.raises(ValueError): datatype(native_type, '')


def test_renames_keep_application_period_indexes_and_literal_comments():
    before = {'name':'t', 'native':{'database':'demo', 'definition':
        "CREATE TABLE `t` (`begins` date, `ends` date, `note` varchar(40) COMMENT 'begins', "
        "PERIOD FOR `validity` (`begins`,`ends`), KEY `by_start` (`begins`)) ENGINE=InnoDB"}}
    native = rename_definition(before, deepcopy(before['native']), {'begins':'starts'}, '', engine='mariadb')
    assert "COMMENT 'begins'" in native['definition']
    assert 'PERIOD FOR `validity` (`starts`,`ends`)' in native['definition']
    sql = alteration(before, {'name':'t','native':native}, '')
    assert 'CHANGE COLUMN `begins` `starts` date FIRST' in sql
    assert 'DROP PERIOD FOR `validity`' in sql
    assert 'ADD PERIOD FOR `validity` (`starts`,`ends`)' in sql
    assert 'DROP INDEX' not in sql


def test_omitted_graphical_fields_keep_native_periods_and_generated_columns():
    before = {'uid':'t', 'name':'t', 'kind':'table', 'native':{'database':'demo', 'definition':
        'CREATE TABLE `t` (`id` int, `b` date, `e` date, PERIOD FOR `validity` (`b`,`e`))'},
        'fields':{'id':{'datatype':'int','_label':'id','_property_names':['uid','datatype']}}}
    desired = deepcopy(before); desired['fields'] = {}
    assert merge_fields(before, desired, '', engine='mariadb') == before['native']
