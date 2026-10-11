// Whitespace-only formatting. Native parsing remains the grammar authority.
export function firebirdTokens(source) {
  const tokens = [];
  let index = 0;
  while(index < source.length) {
    if(/\s/.test(source[index])) {index++; continue;}
    const start = index;
    let kind = 'symbol';
    if(source.startsWith('--', index)) {
      kind = 'line-comment';
      const end = source.indexOf('\n', index + 2);
      index = end < 0 ? source.length : end;
    } else if(source.startsWith('/*', index)) {
      kind = 'comment';
      const end = source.indexOf('*/', index + 2);
      if(end < 0) throw new Error('Unterminated Firebird block comment');
      index = end + 2;
    } else if(/[qQ]/.test(source[index]) && source[index+1] === '\'') {
      kind = 'literal';
      const opening = source[index+2];
      if(!opening) throw new Error('Unterminated Firebird alternate quote');
      const closing = ({'[': ']', '(': ')', '{': '}', '<': '>'})[opening] || opening;
      const end = source.indexOf(closing + '\'', index + 3);
      if(end < 0) throw new Error('Unterminated Firebird alternate quote');
      index = end + 2;
    } else if(source[index] === '\'' || source[index] === '"') {
      kind = 'quoted';
      const quote = source[index++];
      let closed = false;
      while(index < source.length) {
        if(source[index++] === quote) {
          if(source[index] === quote) index++;
          else {closed = true; break;}
        }
      }
      if(!closed) throw new Error('Unterminated Firebird quoted value');
    } else if(/[\p{L}\p{N}_$]/u.test(source[index])) {
      kind = 'word'; index++;
      while(index < source.length && /[\p{L}\p{N}_$]/u.test(source[index])) index++;
    } else index++;
    tokens.push({kind, text: source.slice(start, index), start, end: index});
  }
  return tokens;
}

export function formatFirebird(source) {
  const tokens = firebirdTokens(source);
  let output = '', depth = 0;
  const breaks = new Set(['SELECT', 'FROM', 'WHERE', 'GROUP', 'ORDER', 'HAVING', 'UNION', 'JOIN', 'BEGIN', 'END', 'ELSE']);
  tokens.forEach((token, index) => {
    const word = token.kind === 'word' ? token.text.toUpperCase() : '';
    if(word === 'END' || token.text === ')') depth = Math.max(0, depth - 1);
    const previous = tokens[index-1];
    if(previous) {
      const gap = source.slice(previous.end, token.start);
      if(previous.kind === 'line-comment' || previous.text === ';' ||
          breaks.has(word) || ['BEGIN', 'THEN', 'ELSE'].includes(previous.text.toUpperCase())) {
        output += '\n' + '  '.repeat(Math.min(depth, 32));
      } else if(gap) output += ' ';
    }
    output += token.text;
    if(word === 'BEGIN' || word === 'CASE' || token.text === '(') depth++;
  });
  const signature = values => JSON.stringify(values.map(({kind, text}) => [kind, text]));
  if(signature(firebirdTokens(output)) !== signature(tokens)) throw new Error('Formatting would change Firebird tokens');
  return output;
}
