import {MariaSQL, MySQL, PostgreSQL, SQLite, StandardSQL} from '@codemirror/lang-sql';
import {sqlLanguageConfig, sqlLanguageProfile} from '../../../pgadmin/static/js/cdeadmin_ui/editors/sqlLanguageProfiles';

describe('shared SQL language profile descriptors', () => {
  test.each([
    ['mariadb-sql', MariaSQL], ['mysql-sql', MySQL], ['tidb-sql', MySQL],
    ['vitess-sql', MySQL], ['dolt-sql', MySQL], ['postgresql-sql', PostgreSQL],
    ['cockroachdb-sql', PostgreSQL], ['ysql', PostgreSQL], ['xtdb-sql', PostgreSQL],
    ['xtdb-sql-2.1', PostgreSQL], ['sqlite-sql', SQLite], ['unknown', StandardSQL],
  ])('%s preserves its native CodeMirror dialect', (name, dialect) => {
    expect(sqlLanguageConfig(sqlLanguageProfile(name)).dialect).toBe(dialect);
  });
  test('native warning metadata follows the selected language before an engine fallback', () => {
    expect(sqlLanguageProfile('firebird-sql').native_transaction_close_warning).toBe(true);
    expect(sqlLanguageProfile('', 'firebird-embedded').native_transaction_close_warning).toBe(true);
    expect(sqlLanguageProfile('sqlite-sql', 'firebird').native_transaction_close_warning).toBe(false);
  });
  test('native syntax builders retain their independent resource-aware configuration', () => {
    expect(sqlLanguageConfig(sqlLanguageProfile('firebird-sql'), {}, 3).dialect).toBeTruthy();
    expect(sqlLanguageConfig(sqlLanguageProfile('duckdb-sql')).upperCaseKeywords).toBe(true);
  });
});
