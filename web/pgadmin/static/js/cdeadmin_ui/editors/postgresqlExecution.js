// Boundaries are native parser character offsets; CodeMirror uses UTF-16.
export async function postgresqlExecution(source, mode, from, to, validate) {
  if (!['selection', 'current', 'from-cursor'].includes(mode)) throw new Error('Unknown preparation mode');
  if (mode === 'selection' && from === to) throw new Error('Select SQL source first');
  const input = mode === 'selection' ? source.slice(from, to) : source;
  const result = await validate(input);
  if (!result.syntax_valid || !result.statements?.length) {
    throw new Error(result.diagnostics?.[0]?.message || 'Native PostgreSQL grammar did not accept this source');
  }
  let statements = result.statements;
  if (mode !== 'selection') {
    const cursor = Array.from(source.slice(0, from)).length;
    // Whitespace after a statement belongs to the next statement, except EOF.
    let index = statements.findIndex(statement => cursor <= statement.end);
    if (index < 0) index = statements.length - 1;
    statements = mode === 'current' ? [statements[index]] : statements.slice(index);
  }
  return {source: statements.map(statement => statement.source).join('\n;\n'), scriptMode: statements.length > 1};
}
