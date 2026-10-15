import {firebirdTokens} from './firebirdFormatting';

const meaningful = tokens => tokens.filter(token => !['comment', 'line-comment'].includes(token.kind));

export function firebirdFragments(source) {
  if(typeof source !== 'string' || new TextEncoder().encode(source).length > 1024 * 1024) throw new Error('Firebird source exceeds 1 MiB');
  const tokens = firebirdTokens(source);
  const entries = [];
  let start = 0, delimiter = ';', depth = 0;
  const append = (end, following) => {
    const text = source.slice(start, end);
    const lexical = firebirdTokens(text);
    const parts = meaningful(lexical);
    if(parts.length) {
      let clean = '', previous = 0;
      lexical.forEach(token => {
        clean += text.slice(previous, token.start) + (['comment', 'line-comment'].includes(token.kind) ? ' ' : token.text);
        previous = token.end;
      });
      const originalWords = clean.trim().split(/\s+/);
      const words = originalWords.map(word => word.toUpperCase());
      let kind = 'sql';
      if(words[0] === 'SET' && words[1]?.length >= 4 && 'TERMINATOR'.startsWith(words[1])) {
        const term = originalWords[2] || ';';
        if(words.length > 3 || term.length > 31 || /[^\x21-\x7e]|['"\-/*]/.test(term)) throw new Error('Invalid Firebird script delimiter');
        delimiter = term; kind = 'terminator';
      } else if(words[0] === 'SET' && (words[1] === 'BAIL' || words[1]?.length >= 4 && 'AUTODDL'.startsWith(words[1]) ||
          words[1] === 'SQL' && words[2] === 'DIALECT')) {
        kind = words[1] === 'SQL' ? 'dialect' : words[1] === 'BAIL' ? 'bail' : 'autoddl';
      }
      entries.push({source: text.trim(), start, end: following, kind});
      if(entries.length > 1000) throw new Error('Firebird source exceeds 1000 entries');
    }
    start = following;
  };
  let tokenIndex = 0;
  for(let offset = 0; offset < source.length;) {
    while(tokens[tokenIndex] && tokens[tokenIndex].end <= offset) tokenIndex++;
    const token = tokens[tokenIndex];
    if(token && token.start <= offset && ['comment', 'line-comment', 'quoted', 'literal'].includes(token.kind)) {
      offset = token.end; continue;
    }
    if(depth === 0 && source.startsWith(delimiter, offset)) {
      const following = offset + delimiter.length;
      append(offset, following);
      offset = following;
      continue;
    }
    if(token?.kind === 'word' && (token.start === offset || start === offset)) {
      const word = source.slice(offset, token.end).toUpperCase();
      if(word === 'BEGIN' || word === 'CASE') depth++;
      else if(word === 'END') {
        if(!depth) throw new Error('Unmatched END in Firebird source');
        depth--;
      }
    }
    offset++;
  }
  if(depth) throw new Error('Incomplete Firebird BEGIN/CASE block');
  append(source.length, source.length);
  return entries;
}

export function firebirdExecution(source, mode, from, to = from) {
  if(!['selection', 'current', 'from-cursor'].includes(mode) || !Number.isInteger(from) || !Number.isInteger(to) ||
      from < 0 || to < from || to > source.length) throw new Error('Invalid editor selection');
  let entries, inherited = [];
  if(mode === 'selection') {
    if(from === to) throw new Error('Select source text first');
    entries = firebirdFragments(source.slice(from, to));
  } else {
    const all = firebirdFragments(source);
    let index = all.findIndex(entry => from >= entry.start && from < entry.end);
    if(index < 0 && from === source.length) index = all.length - 1;
    if(index < 0) throw new Error('No statement at this cursor');
    const settings = new Map();
    for(const entry of all.slice(0, index)) {
      if(['dialect', 'autoddl', 'bail'].includes(entry.kind)) settings.set(entry.kind, entry);
    }
    inherited = [...settings.values()];
    entries = mode === 'current' ? [all[index]] : all.slice(index);
  }
  entries = [...inherited, ...entries].filter(entry => entry.kind !== 'terminator');
  if(!entries.some(entry => entry.kind === 'sql')) throw new Error('Choose a SQL statement to execute');
  if(entries.length === 1 && entries[0].kind === 'sql') return {source: entries[0].source, scriptMode: false};
  let delimiter = '^';
  while(entries.some(entry => entry.source.includes(delimiter))) delimiter += '^';
  if(delimiter.length > 31) throw new Error('No safe Firebird script delimiter available');
  return {source: `SET TERM ${delimiter} ;\n` + entries.map(entry => entry.source + '\n' + delimiter).join('\n') +
    `\nSET TERM ; ${delimiter}\n`, scriptMode: true};
}
