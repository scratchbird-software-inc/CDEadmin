import {EditorState} from '@codemirror/state';
import {CompletionContext} from '@codemirror/autocomplete';
import {sql, schemaCompletionSource} from '@codemirror/lang-sql';
import {nativeSQLConfig, registerNativeCompletion} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeCompletion';
import {formatNative, nativeTokens} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeFormatting';
import {scopedSQLConfig} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeScopes';
import {diagnosticRanges} from '../../../pgadmin/static/js/cdeadmin_ui/editors/nativeDiagnostics';

function metadata(engine, modes='') {
  return {context: {engine, sql_mode: modes, default_schema: 'main', catalog: 'owned', schema: 'main', keywords: 'SELECT FROM WHERE AS'}, resources: [
    {resource_kind: 'table', display_path: ['main', 'odd.table']},
    {resource_kind: 'column', display_path: ['main', 'odd.table', 'odd`column']},
    {resource_kind: 'column', display_path: ['main', 'odd.table', 'second column']},
  ].map(item => ({...item, display_path: engine === 'duckdb' ? ['owned', ...item.display_path] : item.display_path}))};
}

test.each(['mysql', 'mariadb', 'sqlite'])('native %s completion resolves aliases and quotes exact identifiers', engine => {
  const config = nativeSQLConfig(metadata(engine));
  const quote = engine === 'sqlite' ? '"' : '`';
  const source = `SELECT * FROM ${quote}odd.table${quote} AS t WHERE t.`;
  const state = EditorState.create({doc: source, extensions: sql(config)});
  const result = schemaCompletionSource(config)(new CompletionContext(state, source.length, true));
  expect(result.options.some(option => option.label === 'second column' && option.apply === `${quote}second column${quote}`)).toBe(true);
  expect(result.options.find(option => option.label === 'odd`column').apply).toBe(engine === 'sqlite' ? '"odd`column"' : '`odd``column`');
});

test('MariaDB ANSI_QUOTES and NO_BACKSLASH_ESCAPES use the observed mode', () => {
  const config = nativeSQLConfig(metadata('mariadb', 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'));
  expect(config.dialect.spec.doubleQuotedStrings).toBe(false);
  expect(config.dialect.spec.backslashEscapes).toBe(false);
  expect(config.schema.main.children['odd\\.table'].self.apply).toBe('"odd.table"');
});

test.each(['mysql', 'mariadb', 'postgresql', 'duckdb', 'sqlite'])('%s CTE projection completion is scoped and quoted', engine => {
  const config = nativeSQLConfig(metadata(engine));
  const quote = ['mysql', 'mariadb'].includes(engine) ? '`' : '"';
  for (const projection of [`(${quote}odd x${quote}, y) AS (SELECT 1, 2)`,
    `AS (SELECT t.* FROM ${quote}odd.table${quote} t)`]) {
    const source = `WITH c ${projection} SELECT * FROM c WHERE c.`;
    const state = EditorState.create({doc: source, extensions: sql(config)});
    const scoped = scopedSQLConfig(config, state, source.length);
    const result = schemaCompletionSource(scoped)(new CompletionContext(state, source.length, true));
    expect(result.options.some(option => option.label === (projection.startsWith('(') ? 'odd x' : 'second column'))).toBe(true);
  }
  const source = 'WITH c(x) AS (SELECT 1) SELECT * FROM c; SELECT ';
  const state = EditorState.create({doc: source, extensions: sql(config)});
  expect(scopedSQLConfig(config, state, source.length).schema.c).toBeUndefined();
});

test('diagnostic ranges preserve Unicode and honest approximate positions', () => {
  const source = 'SELECT \'😀\';\nSELEC 1';
  expect(diagnosticRanges(source, [{offset: 12, severity: 'error'}])[0].from).toBe(source.indexOf('S', 1));
  expect(diagnosticRanges(source, [{offset: 14, position_exact: false, severity: 'error'}])[0])
    .toMatchObject({from: source.indexOf('SELEC', 1), to: source.length});
  expect(diagnosticRanges(source, [{offset: 1, severity: 'warning'}])).toEqual([]);
});

test.each(['mysql', 'mariadb', 'postgresql', 'duckdb', 'sqlite'])('formatting selects %s and preserves literals comments and identifiers', engine => {
  const source = 'select \'literal ; -- unchanged\' as "odd name" from t where id = 7 /* keep */';
  const context = {engine, sql_mode: 'ANSI_QUOTES,NO_BACKSLASH_ESCAPES'};
  const result = formatNative(source, context);
  expect(nativeTokens(result, context)).toEqual(nativeTokens(source, context));
  expect(result).toContain('\'literal ; -- unchanged\'');
  expect(result).toContain('/* keep */');
});

test('formatting preserves driver parameter markers and quoted PostgreSQL bodies', () => {
  const mysql = {engine: 'mysql', sql_mode: ''};
  expect(formatNative('select %s, %(name)s', mysql)).toContain('%(name)s');
  const postgres = {engine: 'postgresql'};
  const source = 'CREATE FUNCTION f() RETURNS text LANGUAGE sql AS $$ SELECT \'x; y\' $$';
  expect(nativeTokens(formatNative(source, postgres), postgres)).toEqual(nativeTokens(source, postgres));
});

test('MariaDB Oracle formatting preserves native quoting and comment boundaries', () => {
  const context = {engine: 'mariadb', sql_mode: 'ORACLE,ANSI_QUOTES'};
  const source = 'select \'it\'\' contains ; %s\' || \'text\' as "odd value" -- keep newline\nfrom dual';
  const formatted = formatNative(source, context);
  expect(nativeTokens(formatted, context)).toEqual(nativeTokens(source, context));
  expect(formatted).toContain('\'it\'\' contains ; %s\'');
  expect(formatted).toMatch(/-- keep newline\n/);
  expect(nativeSQLConfig(metadata('mariadb', 'ORACLE,ANSI_QUOTES')).dialect.spec.plsqlQuotingMechanism).toBe(false);
});

test('late native metadata cannot cross endpoint or document changes', async () => {
  let callback, resolve;
  const state = EditorState.create({doc: 'SELECT ', selection: {anchor: 7}, extensions: sql()});
  const editor = {state, registerAutocomplete: fn => {callback = fn;}};
  const settings = {active: true, blocked: false, scope: 'mysql:first', nativeProfile: 'mysql-sql',
    databaseTargetId: 'first', ensureSession: async () => 'retained', onMetadata: jest.fn(), onError: jest.fn(),
    post: jest.fn(() => new Promise(done => {resolve = done;}))};
  registerNativeCompletion(editor, () => settings);
  const available = jest.fn();
  const pending = callback(new CompletionContext(state, 7, true), available);
  await Promise.resolve();
  settings.scope = 'mysql:second';
  resolve({editor_context: metadata('mysql')});
  expect(await pending).toBeNull();
  expect(settings.onMetadata).not.toHaveBeenCalled();
  expect(available).toHaveBeenCalledTimes(1);
});
