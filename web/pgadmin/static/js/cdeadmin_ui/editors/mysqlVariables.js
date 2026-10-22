import {nativeTokenSpans} from './nativeLexing';

const scopes=['GLOBAL','SESSION','LOCAL','PERSIST','PERSIST_ONLY'];
const word = (source, token) => source.slice(token.from,token.to).toUpperCase();
const nameToken = token => ['Identifier','Keyword','QuotedIdentifier','String'].includes(token?.name);

// Native metadata supplies names/types/scopes, never values. This resolves a
// completion position only; the native parser remains the syntax authority.
export function mysqlVariableCompletion(config, context) {
  if(config.nativeEngine!=='mysql') return undefined;
  const source=context.state.doc.toString(), position=context.pos;
  const spans=nativeTokenSpans(source,config.nativeLanguageContext,{incomplete:true});
  const at=spans.find(token=>token.from<position && token.to>=position);
  if(at && /Comment/.test(at.name)) return undefined;
  const tokens=spans.filter(token=>token.from<position && !/Comment/.test(token.name));
  const boundary=tokens.findLastIndex(token=>token.name===';');
  const statement=tokens.slice(boundary+1);
  const assignment=word(source,statement[0] || {from:0,to:0})==='SET';
  let marker=-1;
  for(let i=0;i<statement.length-1;i++)
    if(source.slice(statement[i].from,statement[i].to)==='@' && source.slice(statement[i+1].from,statement[i+1].to)==='@') marker=i;
  let tail, from, scope, variableContext;
  if(marker>=0) {
    tail=statement.slice(marker+2); from=statement[marker+1].to; variableContext='reference';
    const candidate=tail[0] && word(source,tail[0]);
    if(tail[0]?.name!=='QuotedIdentifier' && tail[0]?.name!=='String' && scopes.includes(candidate) && tail[1]?.name==='.') {
      if(!assignment && candidate.startsWith('PERSIST')) return {from:tail[1].to,to:position,options:[],nativeVariableContext:'reference'};
      scope=candidate; from=tail[1].to; tail=tail.slice(2);
    }
  } else if(assignment) {
    tail=statement.slice(1); from=statement[0].to; variableContext='assignment';
    const candidate=tail[0] && word(source,tail[0]);
    if(tail[0]?.name!=='QuotedIdentifier' && tail[0]?.name!=='String' && scopes.includes(candidate) &&
      (tail.length>1 || position>tail[0].to)) {
      scope=candidate; from=tail[0].to; tail=tail.slice(1);
    }
  } else return undefined;
  // An assignment value, function call, user variable or another expression
  // ends this variable-name position. Quoted component names stay one token.
  if(tail.some((token,index)=>index%2===0 ? !nameToken(token) : token.name!=='.')) return undefined;
  if(tail.some(token=>['QuotedIdentifier','String'].includes(token.name)) && tail.length!==1) return undefined;
  if(tail.length>3) return undefined;
  if(tail.length) from=tail[0].from;
  else {
    const whitespace=source.slice(from,position);
    if(!/^\s*$/.test(whitespace)) return undefined;
    from=position;
  }
  const delimiter=tail[0] && ['QuotedIdentifier','String'].includes(tail[0].name) ? source[tail[0].from] : null;
  const globalScope=scope==='GLOBAL' || scope==='PERSIST' || scope==='PERSIST_ONLY';
  const sessionScope=scope==='SESSION' || scope==='LOCAL' || variableContext==='assignment' && !scope;
  const options=(config.nativeSystemVariables || []).filter(item=>
    globalScope ? item.scope!=='SESSION_ONLY' : sessionScope ? item.scope!=='GLOBAL' : true).map(item=>({
    label:delimiter ? delimiter+item.name.replaceAll(delimiter,delimiter+delimiter)+delimiter : item.name,
    apply:'`'+item.name.replaceAll('`','``')+'`',type:'variable',detail:item.detail,
  }));
  if(!scope && !delimiter && tail.length<=1) {
    for(const option of variableContext==='assignment' ? scopes : ['GLOBAL','SESSION','LOCAL'])
      options.push({label:option,apply:option+(variableContext==='assignment' ? ' ' : '.'),type:'keyword',detail:'Native variable scope'});
  }
  const to=Math.max(position,at?.to || position);
  return {from,to,options,nativeVariableContext:variableContext};
}
