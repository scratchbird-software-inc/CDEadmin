// Shared descriptor loader for native SQL editor dialects and close warnings.
import {MariaSQL, MySQL, PostgreSQL, SQLDialect, SQLite, StandardSQL} from '@codemirror/lang-sql';
import declarations from '../../../../cdeadmin/ui_descriptors/language_profiles.json';
import {firebirdSQLConfig} from './firebirdSyntax';
import {duckdbSQLConfig} from './duckdbSyntax';

export function sqlLanguageProfile(languageProfile, engineId) {
  return declarations.profiles[languageProfile] ||
    declarations.profiles[String(engineId || '').toLowerCase()] ||
    {syntax_family: 'standard', native_transaction_close_warning: false};
}

const dialects = {mariadb: MariaSQL, mysql: MySQL, postgresql: PostgreSQL, sqlite: SQLite};
const builders = {
  firebird: (editor, dialect, resources) => firebirdSQLConfig(editor.keywords || '', dialect, resources, editor.reserved_words),
  duckdb: (editor, _dialect, resources) => duckdbSQLConfig(editor, resources),
};

export function sqlLanguageConfig(profile, editor = {}, dialect, resources = []) {
  const builder = builders[profile.syntax_family];
  if (builder) return builder(editor, dialect, resources);
  const native = dialects[profile.syntax_family] || StandardSQL;
  return {dialect: editor.keywords ? SQLDialect.define({
    ...native.spec, keywords: editor.keywords.toLowerCase(),
  }) : native};
}
