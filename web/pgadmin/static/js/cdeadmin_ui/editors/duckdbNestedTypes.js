import {nativeTokenSpans} from './nativeLexing';

const key=name=>name.replaceAll('.','\\.');
const lower=value=>value.replace(/[A-Z]/g,character=>character.toLowerCase());
const upper=value=>value.replace(/[a-z]/g,character=>character.toUpperCase());
const isName=token=>['Identifier','QuotedIdentifier'].includes(token?.name);
const isFieldName=token=>isName(token) || token?.name==='Keyword';
const name=(token,source)=>token.name==='QuotedIdentifier' ?
  source.slice(token.from+1,token.to-1).replaceAll('""','"') :
  source.slice(token.from,token.to);

const SCALAR_TYPE_WORDS=new Set([
  'BOOLEAN','BOOL','TINYINT','INT1','SMALLINT','INT2','SHORT','INTEGER','INT','INT4','SIGNED',
  'BIGINT','INT8','LONG','HUGEINT','INT128','UTINYINT','USMALLINT','UINTEGER','UBIGINT','UHUGEINT','UINT128',
  'BIGNUM','VARINT','FLOAT','FLOAT4','REAL','DOUBLE','FLOAT8','DECIMAL','NUMERIC','DEC',
  'VARCHAR','CHAR','BPCHAR','TEXT','STRING','BLOB','BYTEA','BINARY','VARBINARY','BIT','BITSTRING',
  'UUID','DATE','TIME','TIMETZ','TIMESTAMP','DATETIME','TIMESTAMP_S','TIMESTAMP_MS','TIMESTAMP_NS','TIMESTAMPTZ',
  'INTERVAL','JSON',
]);

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

function splitTopLevelCommas(tokens,fromIdx,toIdx,source) {
  const parts=[];
  let start=fromIdx,depth=0;
  for(let idx=fromIdx;idx<toIdx;idx++) {
    const text=source.slice(tokens[idx].from,tokens[idx].to);
    if(text==='(' || text==='[')depth++;
    else if(text===')' || text===']') {
      depth--;
      if(depth<0)return null;
    } else if(text===',' && depth===0) {
      if(idx===start)return null;
      parts.push([start,idx]);
      start=idx+1;
    }
  }
  if(depth!==0)return null;
  if(toIdx>fromIdx) {
    if(start>=toIdx)return null;
    parts.push([start,toIdx]);
  }
  return parts;
}

function parseStringLiteral(token,source) {
  if(token?.name!=='String')return null;
  const literal=source.slice(token.from,token.to);
  if(!/^'(?:[^']|'')*'$/.test(literal))return null;
  return literal.slice(1,-1).replaceAll('\'\'','\'');
}

function parsePositiveSafeInt(token,source) {
  if(token?.name!=='Number')return null;
  const literal=source.slice(token.from,token.to);
  if(!/^\d+$/.test(literal))return null;
  const count=Number(literal);
  if(!Number.isSafeInteger(count) || count<=0)return null;
  return count;
}

function parseDuckdbType(tokens,fromIdx,toIdx,source,resolve,quote,depth=0) {
  if(depth>24 || fromIdx>=toIdx)return null;
  let idx=fromIdx;
  const headText=upper(source.slice(tokens[idx].from,tokens[idx].to));
  const unquotedHead=tokens[idx].name!=='QuotedIdentifier';
  let base=null;

  if(unquotedHead && (headText==='STRUCT' || headText==='UNION') && tokens[idx+1]?.name==='(') {
    const kind=lower(headText);
    let closeIdx=idx+2,nesting=1;
    while(closeIdx<toIdx && nesting>0) {
      const t=source.slice(tokens[closeIdx].from,tokens[closeIdx].to);
      if(t==='(' || t==='[')nesting++;
      else if(t===')' || t===']')nesting--;
      if(nesting>0)closeIdx++;
    }
    if(nesting!==0 || closeIdx>=toIdx)return null;
    const members=splitTopLevelCommas(tokens,idx+2,closeIdx,source);
    if(!members || !members.length)return null;
    const namedFields=[],positionalFields=[];
    for(const [mStart,mEnd] of members) {
      if(kind==='struct') {
        const asTypeOnly=parseDuckdbType(tokens,mStart,mEnd,source,resolve,quote,depth+1);
        const firstTok=tokens[mStart];
        const hasMemberType=mEnd-mStart>=2 && isFieldName(firstTok) &&
          source.slice(tokens[mStart+1].from,tokens[mStart+1].to)!=='(' &&
          source.slice(tokens[mStart+1].from,tokens[mStart+1].to)!=='[' &&
          source.slice(tokens[mStart+1].from,tokens[mStart+1].to)!=='.';
        if(hasMemberType) {
          const memberType=parseDuckdbType(tokens,mStart+1,mEnd,source,resolve,quote,depth+1);
          if(!memberType)return null;
          namedFields.push({name:name(firstTok,source),type:memberType});
          continue;
        }
        if(asTypeOnly && !namedFields.length) {
          positionalFields.push(asTypeOnly);
          continue;
        }
        return null;
      }
      if(mEnd-mStart<2 || !isFieldName(tokens[mStart]))return null;
      const memberType=parseDuckdbType(tokens,mStart+1,mEnd,source,resolve,quote,depth+1);
      if(!memberType)return null;
      namedFields.push({name:name(tokens[mStart],source),type:memberType});
    }
    if(namedFields.length && positionalFields.length)return null;
    const sqlText=positionalFields.length ?
      `STRUCT(${positionalFields.map(p=>p.sql).join(', ')})` :
      `${headText}(${namedFields.map(f=>`${quote(f.name)} ${f.type.sql}`).join(', ')})`;
    base=positionalFields.length ?
      {kind:'struct',sql:sqlText,positions:positionalFields} :
      {kind,sql:sqlText,fields:namedFields};
    idx=closeIdx+1;
  } else if(unquotedHead && headText==='MAP' && tokens[idx+1]?.name==='(') {
    let closeIdx=idx+2,nesting=1;
    while(closeIdx<toIdx && nesting>0) {
      const t=source.slice(tokens[closeIdx].from,tokens[closeIdx].to);
      if(t==='(' || t==='[')nesting++;
      else if(t===')' || t===']')nesting--;
      if(nesting>0)closeIdx++;
    }
    if(nesting!==0 || closeIdx>=toIdx)return null;
    const args=splitTopLevelCommas(tokens,idx+2,closeIdx,source);
    if(!args || args.length!==2)return null;
    const keyType=parseDuckdbType(tokens,args[0][0],args[0][1],source,resolve,quote,depth+1);
    const valType=parseDuckdbType(tokens,args[1][0],args[1][1],source,resolve,quote,depth+1);
    if(!keyType || !valType)return null;
    base={kind:'map',sql:`MAP(${keyType.sql}, ${valType.sql})`,key:keyType,value:valType};
    idx=closeIdx+1;
  } else {
    const parts=[];
    if(!isFieldName(tokens[idx]))return null;
    const singleUnquoted=tokens[idx].name!=='QuotedIdentifier';
    parts.push(name(tokens[idx++],source));
    while(idx+1<toIdx && source.slice(tokens[idx].from,tokens[idx].to)==='.' && isFieldName(tokens[idx+1])) {
      idx++;parts.push(name(tokens[idx++],source));
    }
    if(parts.length===1 && singleUnquoted) {
      const phraseWords=[upper(parts[0])];
      while(idx<toIdx && tokens[idx].name!=='QuotedIdentifier' && isFieldName(tokens[idx]) &&
          ['WITH','WITHOUT','TIME','ZONE','PRECISION','VARYING','CHARACTER'].includes(upper(source.slice(tokens[idx].from,tokens[idx].to)))) {
        phraseWords.push(upper(source.slice(tokens[idx++].from,tokens[idx-1].to)));
      }
      if(idx<toIdx && tokens[idx].name==='(') {
        let closeIdx=idx+1,nesting=1;
        while(closeIdx<toIdx && nesting>0) {
          const t=source.slice(tokens[closeIdx].from,tokens[closeIdx].to);
          if(t==='(')nesting++;
          else if(t===')')nesting--;
          if(nesting>0)closeIdx++;
        }
        if(nesting!==0)return null;
        idx=closeIdx+1;
      }
      const resolved=phraseWords.length===1 ? resolve(parts) : undefined;
      if(resolved?.nativeType)base=resolved.nativeType;
      else if(phraseWords.length>1 || SCALAR_TYPE_WORDS.has(phraseWords[0])) {
        const joined=phraseWords.join(' ');
        base={kind:lower(joined),sql:joined};
      } else return null;
    } else {
      const resolved=resolve(parts);
      if(!resolved?.nativeType)return null;
      base=resolved.nativeType;
    }
  }

  while(idx<toIdx) {
    if(source.slice(tokens[idx].from,tokens[idx].to)!=='[')return null;
    idx++;
    if(idx<toIdx && source.slice(tokens[idx].from,tokens[idx].to)===']') {
      idx++;
      base={kind:'list',sql:base.sql+'[]',child:base};
      continue;
    }
    const size=parsePositiveSafeInt(tokens[idx],source);
    if(!size || idx+1>=toIdx || source.slice(tokens[idx+1].from,tokens[idx+1].to)!==']')return null;
    idx+=2;
    base={kind:'array',sql:`${base.sql}[${size}]`,size,child:base};
  }
  return base;
}

// Resolve observed access and admitted core aggregate / computed shapes. This is
// completion typing, not grammar acceptance; no user expression is evaluated.
export function duckdbAccessEntry(source,language,resolve,quote,subqueryResolver=null) {
  const tokens=nativeTokenSpans(source,language,{incomplete:true}).filter(token=>!/Comment/.test(token.name));
  if(tokens.length>2048)return undefined;
  const computed=language?.computed_type_rules || null;
  let at=0;
  const word=value=>tokens[at]?.name!=='QuotedIdentifier' && tokens[at] &&
    upper(source.slice(tokens[at].from,tokens[at].to))===value;
  const balanced=()=> {
    if(tokens[at]?.name!=='(')return false;
    let nesting=0;
    do {
      const token=tokens[at++];
      if(token.name==='(')nesting++;
      if(token.name===')')nesting--;
      if(nesting>32)return false;
    } while(nesting && at<tokens.length);
    return nesting===0;
  };
  const evalSlice=(fromIdx,toIdx,depth)=> {
    if(depth>32 || fromIdx>=toIdx)return undefined;
    const subText=source.slice(tokens[fromIdx].from,tokens[toIdx-1].to);
    return duckdbAccessEntry(subText,language,resolve,quote,subqueryResolver);
  };
  const consumeAggregateTail=()=> {
    if(word('FILTER')) {
      at++;
      if(tokens[at]?.name!=='(' || tokens[at+1]?.name==='QuotedIdentifier' ||
          upper(source.slice(tokens[at+1]?.from,tokens[at+1]?.to))!=='WHERE' ||
          !tokens[at+2] || tokens[at+2].name===')' || !balanced())return false;
    }
    if(word('OVER')) {
      at++;
      if(tokens[at]?.name==='(') {if(!balanced())return false;}
      else if(isName(tokens[at]))at++;
      else return false;
    }
    return true;
  };
  const skipOrderByClause=closeIdx=> {
    if(!computed?.ordered_aggregates)return false;
    if(!word('ORDER'))return false;
    const nextTok=tokens[at+1];
    if(!nextTok || nextTok.name==='QuotedIdentifier' || upper(source.slice(nextTok.from,nextTok.to))!=='BY')return false;
    if(at+2>=closeIdx)return false;
    at=closeIdx;
    return true;
  };
  const findCallClose=openIdx=> {
    let idx=openIdx+1,nesting=1;
    while(idx<tokens.length && nesting>0) {
      const t=source.slice(tokens[idx].from,tokens[idx].to);
      if(t==='(' || t==='[')nesting++;
      else if(t===')' || t===']')nesting--;
      if(nesting>0)idx++;
    }
    return nesting===0 ? idx : -1;
  };

  const evalScalarFunction=(fnName,openIdx,closeIdx,depth)=> {
    const special=computed?.special_forms || {};
    const scalarRule=computed?.scalar_functions && Object.hasOwn(computed.scalar_functions,fnName) ?
      computed.scalar_functions[fnName] : null;
    const args=splitTopLevelCommas(tokens,openIdx+1,closeIdx,source);
    if(!args)return undefined;

    if((fnName==='coalesce' && special.coalesce) || (fnName==='ifnull' && special.ifnull)) {
      if(fnName==='ifnull' && args.length!==2)return undefined;
      if(!args.length)return undefined;
      let common=null;
      for(const [aStart,aEnd] of args) {
        const argEntry=evalSlice(aStart,aEnd,depth+1);
        if(!argEntry?.nativeType)return undefined;
        if(!common)common=argEntry.nativeType;
        else if(common.sql!==argEntry.nativeType.sql)return undefined;
      }
      return duckdbTypedEntry(common,quote);
    }

    if(!scalarRule || args.length<scalarRule.min_args || args.length>scalarRule.max_args)return undefined;
    const shapeKind=scalarRule.shape;
    if(shapeKind==='struct_pack') {
      const fields=[];
      const seen=new Set();
      for(const [aStart,aEnd] of args) {
        if(aEnd-aStart<3 || !isFieldName(tokens[aStart]))return undefined;
        const opText=source.slice(tokens[aStart+1].from,tokens[aStart+1].to);
        if(opText!==':=' && opText!=='=>')return undefined;
        const fName=name(tokens[aStart],source);
        if(seen.has(lower(fName)))return undefined;
        seen.add(lower(fName));
        const valEntry=evalSlice(aStart+2,aEnd,depth+1);
        if(!valEntry?.nativeType)return undefined;
        fields.push({name:fName,type:valEntry.nativeType});
      }
      const sqlText=`STRUCT(${fields.map(f=>`${quote(f.name)} ${f.type.sql}`).join(', ')})`;
      return duckdbTypedEntry({kind:'struct',sql:sqlText,fields},quote);
    }
    if(shapeKind==='row_tuple') {
      const positions=[];
      for(const [aStart,aEnd] of args) {
        const valEntry=evalSlice(aStart,aEnd,depth+1);
        positions.push(valEntry?.nativeType || {kind:'unknown',sql:'ANY'});
      }
      return duckdbTypedEntry({kind:'struct',sql:`STRUCT(${positions.map(p=>p.sql).join(', ')})`,positions},quote);
    }

    const firstArg=evalSlice(args[0][0],args[0][1],depth+1);
    const firstShape=firstArg?.nativeType;
    if(!firstShape)return undefined;

    if(shapeKind==='first_arg')return duckdbTypedEntry(firstShape,quote);
    if(shapeKind==='list_element') {
      if(!['list','array'].includes(firstShape.kind) || !firstShape.child)return undefined;
      return duckdbTypedEntry(firstShape.child,quote);
    }
    if(shapeKind==='array_or_struct_extract') {
      if(['list','array'].includes(firstShape.kind) && firstShape.child)return duckdbTypedEntry(firstShape.child,quote);
      if(firstShape.kind==='struct' && args[1][1]-args[1][0]===1) {
        const strLit=parseStringLiteral(tokens[args[1][0]],source);
        if(strLit!==null)return field(duckdbTypedEntry(firstShape,quote),strLit);
        const posInt=parsePositiveSafeInt(tokens[args[1][0]],source);
        if(posInt!==null && firstShape.positions && posInt<=firstShape.positions.length)
          return duckdbTypedEntry(firstShape.positions[posInt-1],quote);
      }
      return undefined;
    }
    if(shapeKind==='list_slice' || shapeKind==='list_preserve') {
      if(!['list','array'].includes(firstShape.kind) || !firstShape.child)return undefined;
      return duckdbTypedEntry({kind:'list',sql:firstShape.child.sql+'[]',child:firstShape.child},quote);
    }
    if(shapeKind==='list_flatten') {
      if(!['list','array'].includes(firstShape.kind) || !['list','array'].includes(firstShape.child?.kind) || !firstShape.child.child)
        return undefined;
      const grand=firstShape.child.child;
      return duckdbTypedEntry({kind:'list',sql:grand.sql+'[]',child:grand},quote);
    }
    if(shapeKind==='map_extract_list') {
      if(firstShape.kind!=='map' || !firstShape.value)return undefined;
      return duckdbTypedEntry({kind:'list',sql:firstShape.value.sql+'[]',child:firstShape.value},quote);
    }
    if(shapeKind==='map_extract_value') {
      if(firstShape.kind!=='map' || !firstShape.value)return undefined;
      return duckdbTypedEntry(firstShape.value,quote);
    }
    if(shapeKind==='map_keys') {
      if(firstShape.kind!=='map' || !firstShape.key)return undefined;
      return duckdbTypedEntry({kind:'list',sql:firstShape.key.sql+'[]',child:firstShape.key},quote);
    }
    if(shapeKind==='map_values') {
      if(firstShape.kind!=='map' || !firstShape.value)return undefined;
      return duckdbTypedEntry({kind:'list',sql:firstShape.value.sql+'[]',child:firstShape.value},quote);
    }
    if(shapeKind==='map_entries') {
      if(firstShape.kind!=='map' || !firstShape.key || !firstShape.value)return undefined;
      const elem={kind:'struct',sql:`STRUCT("key" ${firstShape.key.sql}, "value" ${firstShape.value.sql})`,
        fields:[{name:'key',type:firstShape.key},{name:'value',type:firstShape.value}]};
      return duckdbTypedEntry({kind:'list',sql:elem.sql+'[]',child:elem},quote);
    }
    if(shapeKind==='struct_extract') {
      if(firstShape.kind!=='struct' || args[1][1]-args[1][0]!==1)return undefined;
      const strLit=parseStringLiteral(tokens[args[1][0]],source);
      if(strLit!==null)return field(duckdbTypedEntry(firstShape,quote),strLit);
      const posInt=parsePositiveSafeInt(tokens[args[1][0]],source);
      if(posInt!==null && firstShape.positions && posInt<=firstShape.positions.length)
        return duckdbTypedEntry(firstShape.positions[posInt-1],quote);
      return undefined;
    }
    if(shapeKind==='union_extract') {
      if(firstShape.kind!=='union' || args[1][1]-args[1][0]!==1)return undefined;
      const tagLit=parseStringLiteral(tokens[args[1][0]],source);
      if(tagLit===null)return undefined;
      const match=(firstShape.fields || []).find(f=>lower(f.name)===lower(tagLit));
      return match ? duckdbTypedEntry(match.type,quote) : undefined;
    }
    return undefined;
  };

  const access=depth=> {
    if(depth>32)return undefined;
    let entry;
    if(tokens[at]?.name==='(') {
      const closeIdx=findCallClose(at);
      if(closeIdx<0)return undefined;
      const innerFirst=tokens[at+1];
      const isSubquery=innerFirst && innerFirst.name!=='QuotedIdentifier' &&
        ['SELECT','WITH'].includes(upper(source.slice(innerFirst.from,innerFirst.to)));
      if(isSubquery) {
        if(!computed?.special_forms?.scalar_subquery || typeof subqueryResolver!=='function')return undefined;
        const subText=source.slice(tokens[at].from,tokens[closeIdx].to);
        entry=subqueryResolver(subText,depth+1);
        if(!entry?.nativeType)return undefined;
        at=closeIdx+1;
      } else {
        at++;entry=access(depth+1);
        if(!entry || tokens[at]?.name!==')')return undefined;
        at++;
      }
    } else if(computed?.special_forms?.casts && (word('CAST') || word('TRY_CAST')) && tokens[at+1]?.name==='(') {
      const closeIdx=findCallClose(at+1);
      if(closeIdx<0)return undefined;
      let asIdx=-1,nesting=0;
      for(let idx=at+2;idx<closeIdx;idx++) {
        const t=source.slice(tokens[idx].from,tokens[idx].to);
        if(t==='(' || t==='[')nesting++;
        else if(t===')' || t===']')nesting--;
        else if(nesting===0 && tokens[idx].name!=='QuotedIdentifier' && upper(t)==='AS') {
          asIdx=idx;break;
        }
      }
      if(asIdx<=at+2 || asIdx+1>=closeIdx)return undefined;
      const targetShape=parseDuckdbType(tokens,asIdx+1,closeIdx,source,resolve,quote);
      if(!targetShape)return undefined;
      entry=duckdbTypedEntry(targetShape,quote);
      at=closeIdx+1;
    } else {
      const parts=[];
      const first=tokens[at],label=first && name(first,source);
      const lowerLabel=label ? lower(label) : '';
      const admittedKeywordCall=first?.name==='Keyword' && tokens[at+1]?.name==='(' && (
        Object.hasOwn(language.aggregate_type_rules || {},lowerLabel) ||
        Object.hasOwn(computed?.keyed_aggregates || {},lowerLabel) ||
        Object.hasOwn(computed?.scalar_functions || {},lowerLabel) ||
        (lowerLabel==='coalesce' && computed?.special_forms?.coalesce) ||
        (lowerLabel==='ifnull' && computed?.special_forms?.ifnull)
      );
      if(!isName(first) && !admittedKeywordCall)return undefined;
      parts.push(name(tokens[at++],source));
      while(tokens[at] && source.slice(tokens[at].from,tokens[at].to)==='.' && isFieldName(tokens[at+1])) {
        at++;parts.push(name(tokens[at++],source));
      }
      if(tokens[at]?.name==='(') {
        const functionName=lower(parts.at(-1));
        const corePath=parts.length===1 || parts.length===2 && lower(parts[0])==='main' ||
          parts.length===3 && lower(parts[0])==='system' && lower(parts[1])==='main';
        if(!corePath)return undefined;
        const closeIdx=findCallClose(at);
        if(closeIdx<0)return undefined;
        const aggRule=Object.hasOwn(language.aggregate_type_rules || {},functionName) && language.aggregate_type_rules[functionName];
        const keyedRule=computed?.keyed_aggregates && Object.hasOwn(computed.keyed_aggregates,functionName) && computed.keyed_aggregates[functionName];
        if(aggRule) {
          at++;
          if(word('DISTINCT') || word('ALL'))at++;
          let argEnd=closeIdx,countVal=null;
          let nesting=0,commaIdx=-1,orderIdx=-1;
          for(let idx=at;idx<closeIdx;idx++) {
            const t=source.slice(tokens[idx].from,tokens[idx].to);
            if(t==='(' || t==='[')nesting++;
            else if(t===')' || t===']')nesting--;
            else if(nesting===0) {
              if(t===',' && commaIdx<0 && orderIdx<0)commaIdx=idx;
              else if(tokens[idx].name!=='QuotedIdentifier' && upper(t)==='ORDER' && orderIdx<0)orderIdx=idx;
            }
          }
          if(commaIdx>=0) {
            argEnd=commaIdx;
            if(!aggRule.positive_literal_count)return undefined;
            const afterCount=orderIdx>=0 ? orderIdx : closeIdx;
            if(afterCount!==commaIdx+2)return undefined;
            countVal=parsePositiveSafeInt(tokens[commaIdx+1],source);
            if(!countVal)return undefined;
          } else if(orderIdx>=0)argEnd=orderIdx;
          const argument=evalSlice(at,argEnd,depth+1);
          if(!argument?.nativeType)return undefined;
          if(orderIdx>=0) {
            at=orderIdx;
            if(!skipOrderByClause(closeIdx))return undefined;
          } else at=closeIdx;
          if(tokens[at]?.name!==')')return undefined;
          at++;
          if(!consumeAggregateTail())return undefined;
          const child=argument.nativeType;
          const list=aggRule.argument==='list' || countVal!==null;
          entry=duckdbTypedEntry(list ? {kind:'list',sql:child.sql+'[]',child} : child,quote);
        } else if(keyedRule) {
          let orderIdx=-1,nesting=0;
          for(let idx=at+1;idx<closeIdx;idx++) {
            const t=source.slice(tokens[idx].from,tokens[idx].to);
            if(t==='(' || t==='[')nesting++;
            else if(t===')' || t===']')nesting--;
            else if(nesting===0 && tokens[idx].name!=='QuotedIdentifier' && upper(t)==='ORDER') {
              orderIdx=idx;break;
            }
          }
          const argsEnd=orderIdx>=0 ? orderIdx : closeIdx;
          let innerStart=at+1;
          if(tokens[innerStart] && tokens[innerStart].name!=='QuotedIdentifier' &&
              ['DISTINCT','ALL'].includes(upper(source.slice(tokens[innerStart].from,tokens[innerStart].to))))innerStart++;
          const args=splitTopLevelCommas(tokens,innerStart,argsEnd,source);
          if(!args || (args.length!==2 && args.length!==3))return undefined;
          let list=false;
          if(args.length===3) {
            if(!keyedRule.positive_literal_count || args[2][1]-args[2][0]!==1)return undefined;
            if(!parsePositiveSafeInt(tokens[args[2][0]],source))return undefined;
            list=true;
          }
          const argument=evalSlice(args[0][0],args[0][1],depth+1);
          if(!argument?.nativeType)return undefined;
          if(orderIdx>=0) {
            at=orderIdx;
            if(!skipOrderByClause(closeIdx))return undefined;
          } else at=closeIdx;
          at++;
          if(!consumeAggregateTail())return undefined;
          const child=argument.nativeType;
          entry=duckdbTypedEntry(list ? {kind:'list',sql:child.sql+'[]',child} : child,quote);
        } else {
          entry=evalScalarFunction(functionName,at,closeIdx,depth);
          if(!entry)return undefined;
          at=closeIdx+1;
        }
      } else entry=resolve(parts);
    }

    while(entry && at<tokens.length && ![')',','].includes(source.slice(tokens[at].from,tokens[at].to))) {
      const token=tokens[at++],text=source.slice(token.from,token.to);
      if(text==='.' && isFieldName(tokens[at])) {entry=field(entry,name(tokens[at++],source));continue;}
      if(text==='::') {
        if(!computed?.special_forms?.casts)return undefined;
        let typeEnd=at;
        while(typeEnd<tokens.length) {
          const nextText=source.slice(tokens[typeEnd].from,tokens[typeEnd].to);
          if(nextText==='::')break;
          if(nextText==='.') {
            const prevTok=tokens[typeEnd-1],afterDot=tokens[typeEnd+1];
            const prevIsTypePart=typeEnd>at && isFieldName(prevTok) &&
              source.slice(prevTok.from,prevTok.to)!==')' && source.slice(prevTok.from,prevTok.to)!==']';
            if(prevIsTypePart && isFieldName(afterDot) && typeEnd-at<=3) {
              const candidateParts=[];
              for(let p=at;p<=typeEnd+1;p+=2)candidateParts.push(name(tokens[p],source));
              if(resolve(candidateParts)?.nativeType) {typeEnd+=2;continue;}
            }
            break;
          }
          if(nextText==='[') {
            if(tokens[typeEnd+1] && source.slice(tokens[typeEnd+1].from,tokens[typeEnd+1].to)===']') {
              typeEnd+=2;continue;
            }
            if(parsePositiveSafeInt(tokens[typeEnd+1],source) && tokens[typeEnd+2] &&
                source.slice(tokens[typeEnd+2].from,tokens[typeEnd+2].to)===']') {
              const afterBracket=tokens[typeEnd+3];
              if(afterBracket && source.slice(afterBracket.from,afterBracket.to)==='.')break;
              typeEnd+=3;continue;
            }
            break;
          }
          if(nextText==='(') {
            const closeIdx=findCallClose(typeEnd);
            if(closeIdx<0)return undefined;
            typeEnd=closeIdx+1;
            continue;
          }
          if(isFieldName(tokens[typeEnd])) {typeEnd++;continue;}
          break;
        }
        const castShape=parseDuckdbType(tokens,at,typeEnd,source,resolve,quote);
        if(!castShape)return undefined;
        entry=duckdbTypedEntry(castShape,quote);
        at=typeEnd;
        continue;
      }
      if(text!=='[')return undefined;
      const body=[];let depthCount=1;
      while(at<tokens.length && depthCount) {
        const next=tokens[at++],value=source.slice(next.from,next.to);
        if(value==='[')depthCount++;
        if(value===']')depthCount--;
        if(depthCount)body.push(next);
      }
      if(depthCount || !body.length)return undefined;
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
        const ordinal=parsePositiveSafeInt(body[0],source);
        if(!ordinal || ordinal>shape.positions.length)return undefined;
        entry=duckdbTypedEntry(shape.positions[ordinal-1],quote);
      }
      else if(shape?.kind==='struct' && body.length===1 && body[0].name==='String') {
        const literal=parseStringLiteral(body[0],source);
        if(literal===null)return undefined;
        entry=field(entry,literal);
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
        const boundary=new Set(['SELECT','DISTINCT','ALL','WHERE','HAVING','QUALIFY','ON','AND','OR','NOT',
          'WHEN','THEN','ELSE','RETURNING','BY']);
        if(isName(token) || token?.name==='Keyword' && !boundary.has(upper(state.sliceDoc(token.from,token.to)))) {
          start=token.from;token=before(token);
          while(token?.name==='.') {
            token=before(token);
            if(!isName(token))return undefined;
            start=token.from;token=before(token);
          }
        }
        if(token && state.sliceDoc(token.from,token.to)==='::') {
          token=before(token);
          continue;
        }
        break;
      }
    } else if(isName(token) || token.name==='Keyword' && (before(token)?.name==='.' ||
        before(token) && state.sliceDoc(before(token).from,before(token).to)==='::')) {
      start=token.from;token=before(token);
      if(token && state.sliceDoc(token.from,token.to)==='::') {
        token=before(token);
        continue;
      }
      if(token?.name!=='.')break;
      token=before(token);
    } else return undefined;
  }
  if(start===undefined || count>=512)return undefined;
  const entry=duckdbAccessEntry(
    state.sliceDoc(start,dot.from),
    config.nativeLanguageContext,
    config.nativeResolve,
    config.nativeQuote,
    config.nativeSubqueryResolve,
  );
  if(!entry)return undefined;
  if(entry.nativeType && !['struct','union','list','array','map'].includes(entry.nativeType.kind) &&
      !Object.keys(entry.children || {}).length)return undefined;
  return entry;
}
