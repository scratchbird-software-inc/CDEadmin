import {format} from 'sql-formatter';

// Protected spans and token boundaries must survive formatting exactly. This is
// a whitespace-preservation guard, never a substitute for the native grammar.
export function nativeTokens(source, context) {
  const mysql = ['mysql', 'mariadb'].includes(context.engine);
  const modes = new Set((context.sql_mode || '').split(','));
  const result = [];
  let i = 0;
  while (i < source.length) {
    if (/\s/.test(source[i])) {i++; continue;}
    const start = i;
    const prefix = source.slice(i).match(/^(?:[eEbBxXnN]|[uU]&|_[A-Za-z0-9_]+)(?=['"])/)?.[0];
    if (prefix) i += prefix.length;
    if (source.startsWith('--', i) && (!mysql || !source[i + 2] || /\s/.test(source[i + 2])) || mysql && source[i] === '#') {
      while (i < source.length && source[i] !== '\n') i++;
    } else if (source.startsWith('/*', i)) {
      i += 2;
      let depth = 1;
      while (i < source.length && depth) {
        if (source.startsWith('/*', i) && ['postgresql', 'duckdb'].includes(context.engine)) {depth++; i += 2;}
        else if (source.startsWith('*/', i)) {depth--; i += 2;}
        else i++;
      }
      if (depth) throw new Error('Unterminated native comment');
    } else if (['postgresql', 'duckdb'].includes(context.engine) && /^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$/.test(source.slice(i))) {
      const marker = source.slice(i).match(/^\$(?:[A-Za-z_][A-Za-z_0-9]*)?\$/)[0];
      const end = source.indexOf(marker, i + marker.length);
      if (end < 0) throw new Error('Unterminated native body');
      i = end + marker.length;
    } else if (source[i] === '%' && /^%(?:s|\([A-Za-z_][A-Za-z_0-9]*\)s)/.test(source.slice(i))) {
      i += source.slice(i).match(/^%(?:s|\([A-Za-z_][A-Za-z_0-9]*\)s)/)[0].length;
    } else if (context.engine === 'sqlite' && /^(?:\?[0-9]+|[:@$][A-Za-z_][A-Za-z_0-9]*)/.test(source.slice(i))) {
      i += source.slice(i).match(/^(?:\?[0-9]+|[:@$][A-Za-z_][A-Za-z_0-9]*)/)[0].length;
    } else if (/['"`]/.test(source[i]) || context.engine === 'sqlite' && source[i] === '[') {
      const quote = source[i] === '[' ? ']' : source[i];
      i++;
      let closed = false;
      while (i < source.length) {
        if (source[i] === '\\' && (mysql && !modes.has('NO_BACKSLASH_ESCAPES') || context.engine === 'postgresql' &&
          (/^[eE]$/.test(prefix || '') || quote === '\'' && context.standard_conforming_strings === 'off'))) {i += 2; continue;}
        if (source[i] === quote) {
          i++;
          if (source[i] === quote && quote !== ']') {i++; continue;}
          closed = true; break;
        }
        i++;
      }
      if (!closed) throw new Error('Unterminated native quoted value');
    } else {
      const token = source.slice(i).match(/^(?:[\p{L}\p{N}_$]+|>=|<=|<>|!=|:=|::|\|\||->>|->|=>|[^\s])/u);
      i += token[0].length;
    }
    result.push(source.slice(start, i));
  }
  return result;
}

export function formatNative(source, context) {
  if (!['mysql', 'mariadb', 'postgresql', 'duckdb', 'sqlite'].includes(context?.engine))
    throw new Error('Select an observed native formatting context');
  if (['mysql', 'mariadb'].includes(context.engine) && typeof context.sql_mode !== 'string')
    throw new Error('Observe native SQL mode before formatting');
  const before = nativeTokens(source, context);
  const formatted = format(source, {language: context.engine,
    keywordCase: 'preserve', identifierCase: 'preserve', dataTypeCase: 'preserve', functionCase: 'preserve',
    paramTypes: {custom: [{regex: '%(?:s|\\([A-Za-z_][A-Za-z_0-9]*\\)s)'}]}});
  if (JSON.stringify(before) !== JSON.stringify(nativeTokens(formatted, context)))
    throw new Error('The formatter changed native tokens; the source was preserved');
  return formatted;
}
