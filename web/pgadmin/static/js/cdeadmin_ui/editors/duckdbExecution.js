// DuckDB native parser spans count Unicode code points; CodeMirror counts UTF-16.
export async function duckdbExecution(source, mode, from, to, validate) {
  if (!['selection', 'current', 'from-cursor'].includes(mode)) throw new Error('Unknown preparation mode');
  if (mode === 'selection' && from === to) throw new Error('Select DuckDB SQL source first');
  const selected = mode === 'selection' ? source.slice(from, to) : source;
  const checked = await validate(selected);
  if (!checked.syntax_valid || !checked.statements?.length) {
    throw new Error(checked.diagnostics?.[0]?.message || 'Native DuckDB parser did not accept this source');
  }
  let statements = checked.statements;
  if (mode !== 'selection') {
    const cursor = Array.from(source.slice(0, from)).length;
    let index = statements.findIndex(statement => cursor <= statement.end);
    if (index < 0) index = statements.length - 1;
    statements = mode === 'current' ? [statements[index]] : statements.slice(index);
  }
  return {source: statements.map(statement => statement.source).join('\n;\n'),
    scriptMode: statements.length > 1};
}
