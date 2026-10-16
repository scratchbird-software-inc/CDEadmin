import {format} from 'sql-formatter';
import {nativeTokens} from './nativeLexing';
export {nativeTokens} from './nativeLexing';

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
