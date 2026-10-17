import {format} from 'sql-formatter';
import {nativeTokens, nativeTokenSpans} from './nativeLexing';
export {nativeTokens} from './nativeLexing';

export function formatNative(source, context) {
  if (!['mysql', 'mariadb', 'postgresql', 'duckdb', 'sqlite'].includes(context?.engine))
    throw new Error('Select an observed native formatting context');
  if (['mysql', 'mariadb'].includes(context.engine) && typeof context.sql_mode !== 'string')
    throw new Error('Observe native SQL mode before formatting');
  const before = nativeTokens(source, context);
  const literals=[];
  let input=source;
  if(context.engine==='mysql') {
    const spans=nativeTokenSpans(source,context).filter(token=>token.name==='String' && source[token.from]==='$');
    let ordinal=0;
    for(const token of [...spans].reverse()) {
      let marker;
      do {marker='%(__scratchrobin_literal_'+(ordinal++)+')s';} while(source.includes(marker));
      literals.push([marker,source.slice(token.from,token.to)]);
      input=input.slice(0,token.from)+marker+input.slice(token.to);
    }
  }
  let formatted = format(input, {language: context.engine,
    keywordCase: 'preserve', identifierCase: 'preserve', dataTypeCase: 'preserve', functionCase: 'preserve',
    paramTypes: {custom: [{regex: '%(?:s|\\([A-Za-z_][A-Za-z_0-9]*\\)s)'}]}});
  for(const [marker,literal] of literals) {
    const parts=formatted.split(marker);
    if(parts.length!==2)throw new Error('The formatter changed a native literal; the source was preserved');
    formatted=parts[0]+literal+parts[1];
  }
  if (JSON.stringify(before) !== JSON.stringify(nativeTokens(formatted, context)))
    throw new Error('The formatter changed native tokens; the source was preserved');
  return formatted;
}
