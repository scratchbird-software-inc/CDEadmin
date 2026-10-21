import {nativeTokenSpans} from './nativeLexing';

const key=name=>name.replaceAll('.','\\.');
const lower=value=>value.replace(/[A-Z]/g,character=>character.toLowerCase());
const isName=token=>['Identifier','QuotedIdentifier'].includes(token?.name);
const isFieldName=token=>isName(token) || token?.name==='Keyword';
const name=(token,source)=>token.name==='QuotedIdentifier' ? source.slice(token.from+1,token.to-1).replaceAll('""','"') : source.slice(token.from,token.to);
const field=(entry,label)=> {
  const exact=entry?.children && Object.hasOwn(entry.children,key(label)) ? entry.children[key(label)] : undefined;
  if(exact)return exact;
  const matches=Object.values(entry?.children || {}).filter(item=>lower(item.self.label)===lower(label));
  return matches.length===1 ? matches[0] : undefined;
};

export function duckdbTypedEntry(shape,quote,self={}) {
  return {self:{...self,detail:shape.sql},nativeType:shape,
    children:Object.fromEntries((shape.fields || []).map(item=>[key(item.name),
      duckdbTypedEntry(item.type,quote,{label:item.name,apply:quote(item.name),type:'property'})]))};
}

// Resolve observed access and admitted core aggregate shapes. This is
// completion typing, not grammar acceptance; no user expression is evaluated.
export function duckdbAccessEntry(source,language,resolve,quote) {
  const tokens=nativeTokenSpans(source,language,{incomplete:true}).filter(token=>!/Comment/.test(token.name));
  if(tokens.length>2048)return undefined;
  let at=0;
  const access=depth=> {
    if(depth>32)return undefined;
    let entry;
    if(tokens[at]?.name==='(') {
      at++;entry=access(depth+1);
      if(!entry || tokens[at]?.name!==')')return undefined;
      at++;
    } else {
      const parts=[];
      const first=tokens[at],label=first && name(first,source);
      if(!isName(first) && !(first?.name==='Keyword' && tokens[at+1]?.name==='(' &&
          Object.hasOwn(language.aggregate_type_rules || {},lower(label))))return undefined;
      parts.push(name(tokens[at++],source));
      while(tokens[at] && source.slice(tokens[at].from,tokens[at].to)==='.' && isFieldName(tokens[at+1])) {
        at++;parts.push(name(tokens[at++],source));
      }
      if(tokens[at]?.name==='(') {
        const functionName=lower(parts.at(-1));
        const rule=Object.hasOwn(language.aggregate_type_rules || {},functionName) && language.aggregate_type_rules[functionName];
        const corePath=parts.length===1 || parts.length===2 && lower(parts[0])==='main' ||
          parts.length===3 && lower(parts[0])==='system' && lower(parts[1])==='main';
        if(!rule || !corePath)return undefined;
        at++;
        const argument=access(depth+1);
        if(!argument?.nativeType)return undefined;
        let list=rule.argument==='list';
        if(tokens[at]?.name===',') {
          if(!rule.positive_literal_count || tokens[at+1]?.name!=='Number')return undefined;
          const literal=source.slice(tokens[at+1].from,tokens[at+1].to),count=Number(literal);
          if(!/^\d+$/.test(literal) || !Number.isSafeInteger(count) || count<=0)return undefined;
          at+=2;list=true;
        }
        if(tokens[at]?.name!==')')return undefined;
        at++;
        const child=argument.nativeType;
        entry=duckdbTypedEntry(list ? {kind:'list',sql:child.sql+'[]',child} : child,quote);
      } else entry=resolve(parts);
    }
    while(entry && at<tokens.length && ![')',','].includes(source.slice(tokens[at].from,tokens[at].to))) {
      const token=tokens[at++],text=source.slice(token.from,token.to);
      if(text==='.' && isFieldName(tokens[at])) {entry=field(entry,name(tokens[at++],source));continue;}
      if(text!=='[')return undefined;
      const body=[];let depth=1;
      while(at<tokens.length && depth) {
        const next=tokens[at++],value=source.slice(next.from,next.to);
        if(value==='[')depth++;
        if(value===']')depth--;
        if(depth)body.push(next);
      }
      if(depth || !body.length)return undefined;
      const shape=entry.nativeType;
      let nesting=0,sliced=false;
      for(const item of body) {
        const value=source.slice(item.from,item.to);
        if(['[','('].includes(value))nesting++;
        if([']',')'].includes(value))nesting--;
        if(value===':' && nesting===0)sliced=true;
      }
      if(['list','array'].includes(shape?.kind)) {
        if(!shape.child)return undefined;
        entry=duckdbTypedEntry(sliced ? {kind:'list',sql:shape.child.sql+'[]',child:shape.child} : shape.child,quote);
      } else if(shape?.kind==='map' && !sliced && shape.value)entry=duckdbTypedEntry(shape.value,quote);
      else if(shape?.kind==='struct' && shape.positions && body.length===1 && body[0].name==='Number') {
        const value=source.slice(body[0].from,body[0].to);
        if(!/^\d+$/.test(value))return undefined;
        const ordinal=Number(value);
        if(!Number.isInteger(ordinal) || ordinal<1 || ordinal>shape.positions.length)return undefined;
        entry=duckdbTypedEntry(shape.positions[ordinal-1],quote);
      }
      else if(shape?.kind==='struct' && body.length===1 && body[0].name==='String') {
        const literal=source.slice(body[0].from,body[0].to);
        if(!/^'(?:[^']|'')*'$/.test(literal))return undefined;
        entry=field(entry,literal.slice(1,-1).replaceAll('\'\'','\''));
      } else return undefined;
    }
    return entry;
  };
  const entry=access(0);
  return at===tokens.length ? entry : undefined;
}

export function duckdbCompletionTarget(config,state,dot) {
  const before=config.nativeStructure.before;
  let token=before(dot),start;
  // The receiver is a chain of observed identifiers and balanced subscripts.
  // Parentheses retain types. Calls require an admitted native shape rule.
  let count=0;
  while(token && ++count<512) {
    const text=state.sliceDoc(token.from,token.to);
    if(text===']' || text===')') {
      const close=text,open=text===']' ? '[' : '(';
      let depth=1;
      while(depth && (token=before(token))) {
        if(++count>=512)return undefined;
        const value=state.sliceDoc(token.from,token.to);
        if(value===close)depth++;
        if(value===open)depth--;
      }
      if(depth)return undefined;
      start=token.from;token=before(token);
      if(close===')') {
        // A function argument is not its result. Refuse a possible call name
        // before the grouping expression. Expression
        // boundary keywords cannot be unquoted scalar function names here.
        const boundary=new Set(['SELECT','DISTINCT','ALL','WHERE','HAVING','QUALIFY','ON','AND','OR','NOT',
          'WHEN','THEN','ELSE','RETURNING','BY']);
        if(isName(token) || token?.name==='Keyword' && !boundary.has(state.sliceDoc(token.from,token.to).toUpperCase())) {
          start=token.from;token=before(token);
          while(token?.name==='.') {
            token=before(token);
            if(!isName(token))return undefined;
            start=token.from;token=before(token);
          }
        }
        break;
      }
    } else if(isName(token) || token.name==='Keyword' && before(token)?.name==='.') {
      start=token.from;token=before(token);
      if(token?.name!=='.')break;
      token=before(token);
    } else return undefined;
  }
  if(start===undefined || count>=512)return undefined;
  return duckdbAccessEntry(state.sliceDoc(start,dot.from),config.nativeLanguageContext,config.nativeResolve,config.nativeQuote);
}
