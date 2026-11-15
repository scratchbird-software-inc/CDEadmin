"""Installed completion uses native registries without leaking variable values."""
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family import mariadb_installed as subject


def test_native_installed_facts_and_protected_values_are_distinct():
    facts = []; queries = []
    def query(section, sql):
        queries.append(sql)
        return {
            'native-variable-metadata': [('OPTIMIZER_SWITCH', 'SESSION', 'FLAGSET', 'NO', None, None, None, 'mrr,default', 'Flags')],
            'native-loadable-functions': [('owned_udf', 2, 'function'), ('owned_aggregate', 0, 'aggregate')],
            'native-plugin-functions': [('uuid_v7', 'ACTIVE'), ('unloaded_function', 'INACTIVE')],
        }[section]
    def add(kind, path, detail, **metadata):
        facts.append({'kind': kind, 'path': path, **metadata})
    assert subject.discover(query, add)
    variable = facts[0]['native_variable']
    assert variable['scope'] == 'SESSION' and variable['data_type'] == 'FLAGSET'
    assert variable['enum_value_list'] == 'mrr,default'
    assert not variable['current_value_observed'] and not variable['default_value_observed']
    assert facts[1]['native_function']['return_type'] == 'INT_RESULT'
    assert facts[2]['native_function']['kind'] == 'aggregate'
    assert facts[3]['path'] == ['uuid_v7']
    assert len(facts) == 4 and all(not row['native_function']['invocation_verified'] for row in facts[1:])
    for sql in queries:
        assert all(token not in sql.upper() for token in ['SESSION_VALUE', 'GLOBAL_VALUE', 'DEFAULT_VALUE', 'GLOBAL_VALUE_PATH', 'SELECT *', ',DL'])
    assert 'performance_schema' not in ' '.join(queries)


@pytest.mark.parametrize('denied', ['native-variable-metadata', 'native-loadable-functions', 'native-plugin-functions'])
def test_denied_registry_is_incomplete_without_suppressing_other_native_sections(denied):
    from types import SimpleNamespace
    from pgadmin.cdeadmin.providers.native_editor import metadata
    class Denied(Exception):
        errno = 1142
    class Cursor:
        def execute(self, sql):
            sections = {subject.VARIABLES: ('native-variable-metadata', [('dynamic_var', 'GLOBAL', 'BIGINT', 'NO', '0', '100', '1', None, 'Metadata')]),
                subject.LOADABLE_FUNCTIONS: ('native-loadable-functions', [('owned_udf', 2, 'function')]),
                subject.PLUGIN_FUNCTIONS: ('native-plugin-functions', [('uuid_v7', 'ACTIVE')])}
            if sql in sections:
                section, self.rows = sections[sql]
                if section == denied:
                    raise Denied('private native refusal')
            elif 'SELECT VERSION()' in sql:
                self.rows = [('12.2.2-MariaDB', 'owned', '', 'utf8mb4', 0)]
            elif 'SELECT CURRENT_USER()' in sql:
                self.rows = [('owner@localhost', None)]
            else:
                self.rows = []
        def fetchmany(self, limit):
            return self.rows[:limit]
        def close(self):
            pass
    result = metadata(SimpleNamespace(cursor=Cursor), 'mariadb')
    observation = next(row for row in result['observations'] if row['section'] == denied)
    assert not result['complete'] and not observation['available'] and observation['error_code'] == 1142
    names = {row['display_name'] for row in result['resources']}
    for section, name in [('native-variable-metadata', 'dynamic_var'),
                          ('native-loadable-functions', 'owned_udf'),
                          ('native-plugin-functions', 'uuid_v7')]:
        assert (name in names) is (section != denied)
