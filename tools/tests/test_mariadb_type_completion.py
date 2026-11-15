"""SQL type candidates must be spellings, not parser productions."""
import re
import pytest
import test_cdeadmin_relational_providers  # noqa: F401
from pgadmin.cdeadmin.providers.mysql_family.mariadb_types import candidates


def by_name(mode='', plugins=()):
    rows, observations = candidates('12.2.2-MariaDB', mode, plugins)
    return {row['name']: row for row in rows}, observations


def test_native_type_names_and_parameter_shapes_replace_grammar_symbols():
    rows, observations = by_name(plugins=[('uuid', 'ACTIVE'), ('inet4', 'ACTIVE'), ('inet6', 'ACTIVE')])
    assert {'BOOL', 'BOOLEAN', 'DATE', 'INT', 'INTEGER', 'DOUBLE PRECISION',
            'CHARACTER VARYING', 'ENUM', 'SET', 'UUID', 'INET4', 'INET6', 'VECTOR'} <= rows.keys()
    assert not any('_SYM' in name or 'opt_' in name or 'field_' in name for name in rows)
    assert all(re.fullmatch(r'[A-Z][A-Z0-9_]*(?: [A-Z][A-Z0-9_]*)*', name) for name in rows)
    assert rows['VECTOR']['syntax']['parameter_requirement'] == 'required'
    assert rows['VARCHAR']['syntax']['example_sql'] == 'VARCHAR(255)'
    assert rows['UUID']['syntax']['availability'] == 'active-native-plugin'
    assert all(row['available'] for row in observations)


def test_oracle_aliases_require_observed_oracle_mode():
    plain, _ = by_name()
    oracle, observations = by_name('ANSI_QUOTES,ORACLE,NO_BACKSLASH_ESCAPES')
    assert not {'NUMBER', 'VARCHAR2', 'RAW', 'CLOB'} & plain.keys()
    assert {'NUMBER', 'VARCHAR2', 'RAW', 'CLOB'} <= oracle.keys()
    assert observations[0]['oracle_mode']
    assert oracle['NUMBER']['syntax']['example_sql'] == 'NUMBER(10,2)'


def test_installed_plugin_admission_never_substitutes_static_availability():
    rows, observations = by_name(plugins=[('uuid', 'DISABLED'), ('inet4', 'ACTIVE'),
                                          ('test_shape', 'ACTIVE')])
    assert 'UUID' not in rows and 'INET6' not in rows and 'INET4' in rows
    assert 'TEST_SHAPE' not in rows
    assert observations[-1]['available'] is False
    assert observations[-1]['plugins'] == ['TEST_SHAPE']


@pytest.mark.parametrize('version', ['12.2.20', '12.2.1', '12.3.0', '', None])
def test_unqualified_runtime_never_borrows_reference_types(version):
    rows, observations = candidates(version, '', [('uuid', 'ACTIVE')])
    assert rows == [] and not observations[0]['available']


@pytest.mark.parametrize('denied', [False, True])
def test_metadata_exposes_sql_syntax_and_keeps_plugin_denial_incomplete(denied):
    from types import SimpleNamespace
    from pgadmin.cdeadmin.providers.native_editor import metadata
    class Denied(Exception):
        errno = 1142
    class Cursor:
        def execute(self, sql):
            if 'SELECT VERSION()' in sql:
                self.rows = [('12.2.2-MariaDB', 'owned', '', 'utf8mb4', 0)]
            elif 'SELECT CURRENT_USER()' in sql:
                self.rows = [('owner@localhost', None)]
            elif 'PLUGIN_TYPE=' in sql:
                if denied:
                    raise Denied('private native denial')
                self.rows = [('uuid', 'ACTIVE')]
            else:
                self.rows = []
        def fetchmany(self, limit):
            return self.rows[:limit]
        def close(self):
            pass
    result = metadata(SimpleNamespace(cursor=Cursor), 'mariadb')
    rows = {row['display_name']: row for row in result['resources']
            if row['resource_kind'] == 'type'}
    assert rows['DOUBLE PRECISION']['native_type_keyword']
    assert rows['DOUBLE PRECISION']['native_type_syntax']['example_sql'] == 'DOUBLE PRECISION(10,2)'
    assert 'YEAR' in rows and 'SQL_TSI_YEAR' in rows
    assert not any('_SYM' in name for name in rows)
    assert ('UUID' in rows) is not denied
    observation = next(row for row in result['observations'] if row['section'] == 'native-data-type-plugins')
    assert observation['available'] is not denied
    if denied:
        assert not result['complete'] and observation['error_code'] == 1142


def test_routine_local_plugins_are_distinct_from_unknown_column_grammars():
    rows, observations = by_name(plugins=[('sys_refcursor', 'ACTIVE'),
        ('associative_array', 'ACTIVE'), ('uuid', 'ACTIVE')])
    assert 'UUID' in rows and 'SYS_REFCURSOR' not in rows and 'ASSOCIATIVE_ARRAY' not in rows
    pending = next(row for row in observations if row['section'] == 'native-routine-type-contexts')
    assert pending['reason'] == 'routine-local-type-completion-unimplemented'
    assert pending['plugins'] == ['ASSOCIATIVE_ARRAY', 'SYS_REFCURSOR']
    assert not any(row['section'] == 'native-type-plugin-parameters' for row in observations)
