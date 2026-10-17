// Token boundaries for source tools, not a SQL grammar or execution authority.
export function mysqlDollarQuoteEnd(source, start, marker) {
  let position=start+marker.length;
  while(position<source.length) {
    const candidate=source.indexOf('$',position);
    if(candidate<0)break;
    let matched=1;
    while(matched<marker.length && source[candidate+matched]===marker[matched])matched++;
    if(matched===marker.length)return candidate+matched;
    // MySQL9.7 consumes the mismatched character before seeking another '$'.
    position=candidate+matched+1;
  }
  return -1;
}

export function nativeTokenSpans(source, context, {incomplete=false}={}) {
  const upper=value=>value.replace(/[a-z]/g,character=>character.toUpperCase());
  const mysql = ['mysql', 'mariadb'].includes(context.engine);
  const modes = new Set((context.sql_mode || '').split(','));
  const words = new Set((context.keywords || '').toUpperCase().split(/\s+/));
  const identifierWords=new Set(context.engine==='duckdb' ? (context.identifier_keywords || []).map(word=>word.toUpperCase()) : []);
  const result = [];
  let i = 0;
  while (i < source.length) {
    if (/[ \t\r\n\f\v]/.test(source[i])) {i++; continue;}
    const start = i;
    let name;
    const prefix = context.engine==='sqlite' ? source.slice(i).match(/^[xX](?=')/)?.[0] :
      source.slice(i).match(/^(?:[eEbBxXnN]|[uU]&|_[A-Za-z0-9_]+)(?=['"])/)?.[0];
    if (prefix) i += prefix.length;
    if (source.startsWith('--', i) && (!mysql || !source[i + 2] || /\s/.test(source[i + 2])) || mysql && source[i] === '#') {
      while (i < source.length && source[i] !== '\n') i++;
      name = 'LineComment';
    } else if (source.startsWith('/*', i)) {
      i += 2;
      let depth = 1;
      while (i < source.length && depth) {
        if (source.startsWith('/*', i) && ['postgresql', 'duckdb'].includes(context.engine)) {depth++; i += 2;}
        else if (source.startsWith('*/', i)) {depth--; i += 2;}
        else i++;
      }
      if (depth && !incomplete) throw new Error('Unterminated native comment');
      name = 'BlockComment';
    } else if (context.engine==='mysql' && /^9\.7\.0(?:[-\s]|$)/.test(context.version || '') && source[i-1]!=='.' &&
      /^\$[A-Za-z0-9_\u0080-\u{10ffff}]*\$/u.test(source.slice(i))) {
      const marker=source.slice(i).match(/^\$[A-Za-z0-9_\u0080-\u{10ffff}]*\$/u)[0];
      const end=mysqlDollarQuoteEnd(source,i,marker);
      if(end<0 && !incomplete)throw new Error('Unterminated native MySQL dollar-quoted text');
      i=end<0 ? source.length : end;
      name='String';
    } else if (['postgresql', 'duckdb'].includes(context.engine) && /^\$(?:[A-Za-z_\u0080-\u{10ffff}][A-Za-z_0-9\u0080-\u{10ffff}]*)?\$/u.test(source.slice(i))) {
      const marker = source.slice(i).match(/^\$(?:[A-Za-z_\u0080-\u{10ffff}][A-Za-z_0-9\u0080-\u{10ffff}]*)?\$/u)[0];
      const end = source.indexOf(marker, i + marker.length);
      if (end < 0 && !incomplete) throw new Error('Unterminated native body');
      i = end < 0 ? source.length : end + marker.length;
      name = 'String';
    } else if (context.engine === 'firebird' && /^[qQ]'[^\s]/.test(source.slice(i))) {
      const close = {'[':']','(':')','{':'}','<':'>'}[source[i + 2]] || source[i + 2];
      const end = source.indexOf(close + '\'', i + 3);
      if (end < 0 && !incomplete) throw new Error('Unterminated native quoted value');
      i = end < 0 ? source.length : end + 2;
      name = 'String';
    } else if (source[i] === '%' && /^%(?:s|\([A-Za-z_][A-Za-z_0-9]*\)s)/.test(source.slice(i))) {
      i += source.slice(i).match(/^%(?:s|\([A-Za-z_][A-Za-z_0-9]*\)s)/)[0].length;
      name = 'SpecialVar';
    } else if (context.engine === 'sqlite' && /^(?:\?[0-9]+|[:@$][\p{L}_][\p{L}\p{N}\p{M}_]*)/u.test(source.slice(i))) {
      i += source.slice(i).match(/^(?:\?[0-9]+|[:@$][\p{L}_][\p{L}\p{N}\p{M}_]*)/u)[0].length;
      name = 'SpecialVar';
    } else if (/['"`]/.test(source[i]) || context.engine === 'sqlite' && source[i] === '[') {
      const opening = source[i], quote = opening === '[' ? ']' : opening;
      const quotedIdentifier = !prefix && (opening === '`' && (mysql || context.engine === 'sqlite') || opening === '[' ||
        opening === '"' && (!mysql || modes.has('ANSI_QUOTES')) && !(context.engine === 'firebird' && context.sql_dialect === 1));
      name = quotedIdentifier ? 'QuotedIdentifier' : 'String';
      i++;
      let closed = false;
      while (i < source.length) {
        if (source[i] === '\\' && !quotedIdentifier && (mysql && !modes.has('NO_BACKSLASH_ESCAPES') || context.engine === 'postgresql' &&
          (/^[eE]$/.test(prefix || '') || quote === '\'' && context.standard_conforming_strings === 'off'))) {i = Math.min(i + 2, source.length); continue;}
        if (source[i] === quote) {
          i++;
          if (source[i] === quote && quote !== ']') {i++; continue;}
          closed = true; break;
        }
        i++;
      }
      if (!closed && !incomplete) throw new Error('Unterminated native quoted value');
    } else {
      const token = source.slice(i).match(/^(?:[A-Za-z_0-9$\u0080-\u{10ffff}]+|>=|<=|<>|!=|:=|::|\|\||->>|->|=>|[^ \t\n\r\f\v])/u)[0];
      i += token.length;
      name = /^[A-Za-z_$\u0080-\u{10ffff}][A-Za-z_0-9$\u0080-\u{10ffff}]*$/u.test(token) ? words.has(upper(token)) && !identifierWords.has(upper(token)) ? 'Keyword' : 'Identifier' :
        /^\p{N}/u.test(token) ? 'Number' : ['.', '(', ')', ';', ','].includes(token) ? token : 'Operator';
      // Both native MySQL-family lexers enter IDENT_START for an
      // immediately adjacent identifier after a qualifying dot.
      if(mysql && name==='Keyword' && result.at(-1)?.name==='.' && result.at(-1).to===start)name='Identifier';
    }
    result.push({name, from: start, to: i});
  }
  if(context.engine==='sqlite') {
    const roles=Object.fromEntries(Object.entries(context.identifier_keyword_roles || {}).map(([role,names])=>[role,new Set(names)]));
    const visible=result.filter(token=>!/Comment/.test(token.name));
    const word=token=>token && upper(source.slice(token.from,token.to));
    const lookahead=token=>token && (['Identifier','QuotedIdentifier','String'].includes(token.name) || roles.lookahead?.has(word(token)));
    for(const [index,token] of visible.entries()) {
      if(token.name==='String' && source[token.from]==='\'')token.nativeIdentifierRoles=['nm','ids','qualifier'];
      if(token.name!=='Keyword')continue;
      token.nativeIdentifierRoles=Object.entries(roles).filter(([_role,names])=>names.has(word(token))).map(([role])=>role);
      if(!(context.sqlite_contextual_keywords || []).includes(word(token)))continue;
      const previous=visible[index-1],next=visible[index+1];
      const keyword=word(token)==='WINDOW' ? lookahead(next) && word(visible[index+2])==='AS' :
        word(token)==='OVER' ? previous?.name===')' && (next?.name==='(' || lookahead(next)) : previous?.name===')' && next?.name==='(';
      if(keyword)token.nativeIdentifierRoles=[];
      else token.name='Identifier';
    }
  }
  return result;
}

export function nativeTokens(source, context) {
  return nativeTokenSpans(source, context).map(token => source.slice(token.from, token.to));
}

export function nativeSourceStructure(source, context, position) {
  const tokens = nativeTokenSpans(source, context, {incomplete:true});
  const containers = [];
  const root = {name:'Script', from:0, to:source.length, children:[]};
  let statement = {name:'Statement', from:0, to:source.length, children:[]};
  root.children.push(statement);
  let stack = [statement];
  for (const token of tokens) {
    if (token.name === '(') {
      if (stack.length > 128) throw new Error('Source nesting exceeds the completion limit');
      const container = {name:'Parens', from:token.from, to:source.length, children:[token]};
      stack.at(-1).children.push(container); stack.push(container);
    } else if (token.name === ')' && stack.length > 1) {
      stack.at(-1).children.push(token); stack.at(-1).to=token.to; stack.pop();
    } else if (token.name === ';' && stack.length === 1) {
      statement.children.push(token); statement.to=token.to;
      statement = {name:'Statement', from:token.to, to:source.length, children:[]};
      root.children.push(statement); stack=[statement];
    } else stack.at(-1).children.push(token);
  }
  const combine = container => {
    const children = container.children.filter(token => !/Comment/.test(token.name));
    const grouped = [];
    for (let index=0; index<children.length; index++) {
      const first=children[index];
      if (first.children) combine(first);
      const nativeName=node=>['Identifier','QuotedIdentifier'].includes(node?.name) || node?.nativeIdentifierRoles?.includes('nm');
      if (nativeName(first) && children[index + 1]?.name === '.') {
        const path=[first];
        while (children[index + 1]?.name === '.') {
          path.push(children[++index]);
          const next=children[index+1];
          // A dangling dot at the caret must not consume the following
          // FROM/WHERE clause as a keyword-named member of that expression.
          const keywordMember=context.engine==='duckdb' && next?.name==='Keyword' &&
            !(children[index].from<position && next.from>=position);
          if (!nativeName(next) && !keywordMember) break;
          path.push(children[++index]);
        }
        grouped.push({name:'CompositeIdentifier', from:first.from, to:path.at(-1).to, children:path});
      } else grouped.push(first);
    }
    container.children=grouped;
    if (container.from<=position && container.to>=position && ['Statement','Parens'].includes(container.name)) containers.push(container);
  };
  for (const item of root.children) combine(item);
  // Outer scopes precede inner scopes so the nearest binding wins.
  containers.sort((left,right)=>(right.to-right.from)-(left.to-left.from));
  let at = tokens.findLast(token => token.from < position && token.to >= position);
  if (!at) {
    const previous=tokens.findLast(token => token.to<=position && !/Comment/.test(token.name));
    if (previous?.name === '.') at=previous;
  }
  const before = token => tokens.findLast(candidate => candidate.to<=token.from && !/Comment/.test(candidate.name));
  return {containers, at, before};
}
