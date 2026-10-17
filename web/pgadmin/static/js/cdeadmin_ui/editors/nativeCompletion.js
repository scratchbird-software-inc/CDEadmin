import {SQLDialect, MySQL, MariaSQL, PostgreSQL, SQLite, StandardSQL, sql, keywordCompletionSource} from '@codemirror/lang-sql';
import {EditorState} from '@codemirror/state';
import {CompletionContext} from '@codemirror/autocomplete';
import {firebirdSQLConfig} from './firebirdSyntax';
import {scopedSQLConfig, nativeSchemaCompletion} from './nativeScopes';

const key = name => name.replaceAll('.', '\\.');

export function nativeSQLConfig(metadata) {
  const context = metadata.context;
  const engine = context.engine;
  if (engine === 'firebird') return {...firebirdSQLConfig(context.keywords, context.sql_dialect,
    metadata.resources.map(item => ({...item, package_name: ['function', 'procedure'].includes(item.resource_kind) &&
      item.display_path.length === 2 ? item.display_path[0] : undefined})), context.reserved_words),
  nativeEngine: engine, nativeLanguageContext: context, nativeIdentifierQuote: context.sql_dialect === 1 ? '' : '"'};
  const modes = new Set((context.sql_mode || '').split(','));
  const mysql = ['mysql', 'mariadb'].includes(engine);
  const base = engine === 'mysql' ? MySQL : engine === 'mariadb' ? MariaSQL : engine === 'postgresql' ? PostgreSQL : engine === 'sqlite' ? SQLite : StandardSQL;
  const quote = mysql && !modes.has('ANSI_QUOTES') ? '`' : '"';
  const quoted = name => quote + name.replaceAll(quote, quote + quote) + quote;
  const schema = Object.create(null);
  const ensure = (path, kind, detail='') => {
    let branch = schema, entry;
    for (const [index, name] of path.entries()) {
      entry = branch[key(name)] ||= {self: {label: name, apply: quoted(name), type: 'namespace'}, children: Object.create(null)};
      if (index === path.length - 1) {
        entry.self.type = kind;
        if (detail && !entry.self.detail?.split(' / ').includes(detail))
          entry.self.detail = [entry.self.detail, detail].filter(Boolean).join(' / ');
      }
      branch = entry.children;
    }
    return entry;
  };
  for (const item of metadata.resources || []) {
    const path = item.display_path;
    if (!Array.isArray(path) || !path.length || path.some(name => typeof name !== 'string' || !name)) continue;
    const kind = item.resource_kind;
    const entry = ensure(path, kind === 'column' ? 'property' :
      ['function', 'procedure', 'package', 'package body'].includes(kind) ? 'function' :
        ['table', 'view', 'type', 'domain', 'collation'].includes(kind) ? 'type' : 'namespace', item.detail);
    if (item.hidden_from_star) entry.self.nativeHiddenFromStar = true;
    if (path.length === 1 && ['function', 'type'].includes(kind) && /^[A-Za-z_][A-Za-z_0-9]*$/.test(path[0]))
      entry.self.apply = path[0];
    if (engine === 'duckdb' && kind === 'function' && path[0] === 'system') {
      const builtin = ensure([path.at(-1)], 'function', item.detail);
      builtin.self.apply = /^[A-Za-z_][A-Za-z_0-9]*$/.test(path.at(-1)) ? path.at(-1) : quoted(path.at(-1));
    }
  }
  if (engine === 'duckdb') {
    const catalog = schema[key(context.catalog)]?.children;
    for (const [name, entry] of Object.entries(catalog || {})) schema[name] ||= entry;
  }
  return {dialect: SQLDialect.define({...base.spec, keywords: (context.keywords || base.spec.keywords || '').toLowerCase(),
    ...(mysql ? {backslashEscapes: !modes.has('NO_BACKSLASH_ESCAPES'), doubleQuotedStrings: !modes.has('ANSI_QUOTES'),
      identifierQuotes: modes.has('ANSI_QUOTES') ? '`"' : '`', plsqlQuotingMechanism: false} : {}),
    ...(engine === 'postgresql' ? {backslashEscapes: context.standard_conforming_strings === 'off'} : {}),
    ...(engine === 'duckdb' ? {identifierQuotes: '"', doubleDollarQuotedStrings: true, backslashEscapes: false} : {})}),
  schema, nativeEngine: engine, nativeIdentifierQuote: quote,
  nativeLanguageContext: context,
  nativeRelationCaseSensitive: mysql && context.lower_case_table_names === 0,
  defaultSchema: (engine === 'duckdb' ? context.schema : context.default_schema) || undefined, upperCaseKeywords: true};
}

export function nativeCompletionContext(metadata, context) {
  const base = nativeSQLConfig(metadata);
  // The response can report a mode changed by an earlier statement. Parse the
  // current source with that mode before resolving aliases or CTE projections.
  // Updating React metadata alone leaves this request using the old token tree.
  const state = EditorState.create({doc: context.state.doc, selection: context.state.selection, extensions: sql(base)});
  const observed = new CompletionContext(state, context.pos, context.explicit);
  return {context: observed, config: scopedSQLConfig(base, state, context.pos)};
}

export function registerNativeCompletion(editor, current) {
  editor.registerAutocomplete(async (context, available) => {
    const initial = {...current()}, source = context.state.doc.toString();
    const applicable = () => {
      const latest = current();
      return latest.active && !latest.blocked && latest.scope === initial.scope &&
        latest.post === initial.post && !context.aborted && editor.state.doc.toString() === source &&
        editor.state.selection.main.head === context.pos;
    };
    try {
      if (!initial.active || initial.blocked || context.aborted) return null;
      const session = await initial.ensureSession();
      if (!applicable()) return null;
      const result = await initial.post({action: 'source_complete', session_id: session, source,
        source_before_cursor: context.state.sliceDoc(0, context.pos), database_target_id: initial.databaseTargetId,
        ...(initial.nativeProfile === 'firebird-sql' ? {client_sql_dialect: initial.clientSqlDialect} : {})});
      if (!applicable()) return null;
      const metadata = result.editor_context;
      if (metadata?.context?.engine + '-sql' !== initial.nativeProfile) throw new Error('Native completion language changed');
      const observed = nativeCompletionContext(metadata, context);
      const schema = nativeSchemaCompletion(observed.config, observed.context);
      const words = keywordCompletionSource(observed.config.dialect, true)(observed.context);
      initial.onMetadata(metadata);
      if (!schema) return words;
      if (!words || words.from !== schema.from) return schema;
      return {...schema, options: [...schema.options, ...words.options]};
    } catch (failure) {
      if (applicable()) initial.onError('Native metadata completion is unavailable: ' + failure.message);
      return null;
    } finally {available();}
  });
}
