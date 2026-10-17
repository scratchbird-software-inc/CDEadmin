import {nativeSourceStructure} from './nativeLexing';
import {duckdbAccessEntry,duckdbCompletionTarget} from './duckdbNestedTypes';

const key = name => name.replaceAll('.', '\\.');
const identifier = (node,role='nm',stringName=false) => ['Identifier', 'QuotedIdentifier'].includes(node?.name) ||
  (node?.name!=='String' || stringName) && node?.nativeIdentifierRoles?.includes(role);

// Context suggestions use native mode-aware token boundaries. They never claim
// SQL grammar validity or infer column names from arbitrary expressions.
export function scopedSQLConfig(config, state, position) {
  const lower = value => value.replace(/[A-Z]/g, character => character.toLowerCase());
  const upper = value => value.replace(/[a-z]/g, character => character.toUpperCase());
  const exactCase = ['postgresql', 'firebird'].includes(config.nativeEngine) || config.nativeRelationCaseSensitive;
  const bindingKey = value => exactCase ? value : lower(value);
  const text = node => state.sliceDoc(node.from, node.to);
  const word = node => node ? upper(text(node)) : '';
  const structure = nativeSourceStructure(state.doc.toString(), config.nativeLanguageContext, position);
  const children = node => node.children || [];
  const name = node => {
    const value = text(node);
    if (node.name !== 'QuotedIdentifier' && !(node.name==='String' && node.nativeIdentifierRoles?.includes('nm'))) return config.nativeEngine === 'postgresql' ? lower(value) :
      config.nativeEngine === 'firebird' ? upper(value) : value;
    const end = value[0] === '[' ? ']' : value[0];
    return value.slice(1, value.endsWith(end) ? -1 : undefined).replaceAll(end + end, end);
  };
  const path = (node,stringName=false,bare=false) => node.name === 'CompositeIdentifier' ?
    children(node).filter(child=>identifier(child,'nm',true) || config.nativeEngine==='duckdb' && child.name==='Keyword').map(name) :
    identifier(node,'nm',stringName) && (!bare || node.name!=='Keyword' || node.nativeIdentifierRoles?.includes('bare')) ? [name(node)] : [];
  const quote = value => {
    const delimiter = config.nativeIdentifierQuote ?? config.dialect.spec.identifierQuotes?.[0] ?? '"';
    if (!delimiter) return value;
    return delimiter + value.replaceAll(delimiter, delimiter + delimiter) + delimiter;
  };
  const schema = Object.assign(Object.create(null),config.schema);
  const asEntry = entry => entry.self ? entry : {self:entry,children:Object.create(null)};
  const lookup = (branch, part, exact=false) => {
    if (branch && !Array.isArray(branch) && Object.hasOwn(branch,key(part)))return asEntry(branch[key(part)]);
    const candidates=Object.values(branch || {}).map(asEntry).filter(entry =>
      exact ? entry.self.label===part : lower(entry.self.label)===lower(part));
    return candidates.length===1 ? candidates[0] : undefined;
  };
  const resolve = parts => {
    const follow = branch => {
      let entry;
      for (const part of parts) {entry = lookup(branch, part, exactCase); if (!entry) return undefined; branch = entry.children;}
      return entry;
    };
    if(config.nativeEngine === 'sqlite' && parts.length === 1) {
      const local = lookup(schema, parts[0], exactCase);
      if(local?.self.nativeSourceScope) return local;
      const native = lookup(config.nativeRelationBindings || {}, parts[0], exactCase);
      if(native) return native;
    }
    return follow(schema) || follow(lookup(schema, config.defaultSchema || '')?.children);
  };
  const relation = (label, columns) => ({self: {label, apply: quote(label), type: 'type', detail: 'Source scope', nativeSourceScope: true},
    children: Object.fromEntries(columns.map(column => {
      const name=typeof column==='string' ? column : column.label, native=column.native;
      const self={...(native?.self || {}),label:name,apply:quote(name),type:'property'};
      if (!self.detail)self.detail='Source scope';
      // An explicitly projected hidden/pseudo column is an ordinary visible
      // column of the CTE/derived relation. Its nested native members survive.
      delete self.nativeHiddenFromStar;
      return [key(name),{self,children:native?.children || Object.create(null),nativeType:native?.nativeType}];
    }))});
  const columns = entry => Object.values(entry?.children || {}).map(asEntry)
    .filter(child => child.self?.type === 'property' && !child.self.nativeHiddenFromStar)
    .map(child => ({label:child.self.label,native:child}));

  const sourceBindings = (body, depth=0) => {
    const nodes = children(body).filter(node => !['(', ')'].includes(node.name));
    const select = nodes.findIndex(node => word(node) === 'SELECT');
    const from = nodes.findIndex((node, index) => index > select && word(node) === 'FROM');
    const bindings = new Map();
    for (let index = Math.max(0, from); from >= 0 && index < nodes.length - 1; index++) {
      if (['WHERE', 'GROUP', 'HAVING', 'ORDER', 'UNION', 'INTERSECT', 'EXCEPT', 'LIMIT', 'OFFSET', 'FETCH', 'FOR', 'RETURNING', 'WINDOW', 'QUALIFY'].includes(word(nodes[index]))) break;
      if (!['FROM', 'JOIN', ','].includes(word(nodes[index]))) continue;
      let at = index + 1;
      if (config.nativeEngine!=='sqlite' && word(nodes[at]) === 'LATERAL') at++;
      const target = nodes[at];
      if (!target) continue;
      const parts = path(target,true);
      const entry = target.name === 'Parens' ? relation('', project(target, depth + 1)) : resolve(parts);
      at++;
      if (config.nativeEngine === 'sqlite' && target.name !== 'Parens' && nodes[at]?.name === 'Parens') {
        if (!entry?.self.nativeTableValued) {index = at; continue;}
        at++;
      }
      const explicitAlias=nodes[at] && word(nodes[at]) === 'AS';
      if (explicitAlias) at++;
      const hasAlias=identifier(nodes[at],explicitAlias ? 'nm' : config.nativeEngine==='sqlite' ? 'ids' : 'nm',true);
      const alias = hasAlias ? name(nodes[at++]) : parts.at(-1);
      if (alias && entry) bindings.set(bindingKey(alias), entry);
      index=at-1;
    }
    return bindings;
  };
  const project = (body, depth=0, positional=false) => {
    if (depth > 12) return [];
    const nodes = children(body).filter(node => !['(', ')'].includes(node.name));
    const select = nodes.findIndex(node => word(node) === 'SELECT');
    if (select < 0) return [];
    const from = nodes.findIndex((node, index) => index > select && word(node) === 'FROM');
    const bindings = sourceBindings(body, depth);
    const groups = [[]];
    for (const node of nodes.slice(select + 1, from < 0 ? undefined : from)) {
      if (word(node) === ',') groups.push([]); else groups.at(-1).push(node);
    }
    const result = [];
    const nativeColumn = parts => {
      if (!parts.length)return undefined;
      if (parts.length===1) {
        const candidates=[...bindings.values()].map(entry => lookup(entry.children,parts[0],exactCase)).filter(Boolean);
        return candidates.length===1 ? candidates[0] : undefined;
      }
      let entry=bindings.get(bindingKey(parts[0]));
      if (!entry)return resolve(parts);
      for (const part of parts.slice(1)) {
        entry=lookup(entry.children,part,exactCase);
        if (!entry)return undefined;
      }
      return entry;
    };
    const expressionColumn = expression => config.nativeEngine==='duckdb' && expression.length ?
      duckdbAccessEntry(state.sliceDoc(expression[0].from,expression.at(-1).to),config.nativeLanguageContext,nativeColumn,quote) :
      expression.length===1 ? nativeColumn(path(expression[0],false,true)) : undefined;
    for (let group of groups) {
      group = group.filter(node => !['DISTINCT', 'ALL'].includes(word(node)));
      if (!group.length) continue;
      const last = group.at(-1), previous = group.at(-2);
      const delimiterBoundary=config.nativeEngine==='sqlite' &&
        (['QuotedIdentifier','String'].includes(last.name) || previous?.name==='QuotedIdentifier');
      const implicitAlias = previous && (previous.to < last.from || delimiterBoundary) && previous.name !== 'Operator' &&
        (previous.name !== 'Keyword' || word(previous) === 'END' || previous.nativeIdentifierRoles?.includes('nm'));
      if (identifier(last,word(previous)==='AS' ? 'nm' : config.nativeEngine==='sqlite' ? 'ids' : 'nm',true) && previous && (word(previous) === 'AS' || implicitAlias)) {
        const expression=group.slice(0,word(previous)==='AS' ? -2 : -1);
        result.push({label:name(last),native:expressionColumn(expression)});
      } else if (group.length === 1 && path(last,false,true).length) result.push({label:path(last).at(-1),native:nativeColumn(path(last))});
      else if(group.length===1 && last.nativeIdentifierRoles?.includes('nm'))result.push({label:text(last)});
      else if (word(last) === '*') {
        const qualifier = previous && path(previous);
        let entries;
        if (qualifier?.length) {
          const entry=(qualifier.length===1 && bindings.get(bindingKey(qualifier[0]))) || nativeColumn(qualifier);
          // DuckDB expands a native STRUCT star. UNION members remain dot
          // expressions and must not be invented as a star projection.
          entries=entry && (entry.self.type==='type' || entry.self.nativeTableValued || /^STRUCT\s*\(/i.test(entry.self.detail || '')) ? [entry] : [];
        } else entries=[...bindings.values()];
        result.push(...entries.flatMap(columns));
      } else if(positional) result.push({native:expressionColumn(group)});
    }
    return result;
  };

  // Enclosing scopes only: a CTE in another statement or sibling subquery must
  // never appear here. Inner definitions shadow outer names.
  const containers = structure.containers;
  for (const container of containers) {
    const nodes = children(container);
    let at = nodes.findIndex(node => word(node) === 'WITH');
    if (at < 0) continue;
    at++;
    const recursive = nodes[at] && word(nodes[at]) === 'RECURSIVE';
    if (recursive) at++;
    while (identifier(nodes[at],'nm',true)) {
      const cte = nodes[at++], label = name(cte);
      let explicit;
      if (nodes[at]?.name === 'Parens') explicit = children(nodes[at++]).filter(node=>identifier(node,'nm',true)).map(name);
      if (!nodes[at] || word(nodes[at++]) !== 'AS') break;
      while (nodes[at] && ['NOT', 'MATERIALIZED'].includes(word(nodes[at]))) at++;
      const body = nodes[at++];
      if (body?.name !== 'Parens') break;
      if (recursive || position >= body.to) {
        const projected=project(body,0,Boolean(explicit));
        schema[key(label)] = relation(label,explicit ? explicit.map((name,index) => ({label:name,native:projected[index]?.native})) : projected);
      }
      if (!nodes[at] || word(nodes[at++]) !== ',') break;
    }
  }
  const bindings = new Map();
  for (const container of containers) for (const [alias, entry] of sourceBindings(container)) bindings.set(alias, entry);
  return {...config, schema, nativeScopeBindings: bindings,
    nativeResolve: parts => {
      let entry=bindings.get(bindingKey(parts[0]));
      if (!entry) {
        const direct=resolve(parts);
        if(config.nativeEngine!=='duckdb' || direct && direct.self.type!=='function')return direct;
        const candidates=[...bindings.values()].map(owner=>lookup(owner.children,parts[0],exactCase)).filter(Boolean);
        if(candidates.length!==1)return candidates.length ? undefined : direct;
        entry=candidates[0];
      }
      for (const part of parts.slice(1)) {
        entry=lookup(entry.children,part,exactCase);
        if (!entry)return undefined;
      }
      return entry;
    },
    nativeName: name, nativeStructure: structure, nativeQuote: quote};
}

// CodeMirror's schema source performs literal path lookup and strips quoted
// identifiers without decoding doubled delimiters. Native identity rules must
// resolve these paths before constructing suggestions.
export function nativeSchemaCompletion(config, context) {
  const {state, pos} = context;
  let node = config.nativeStructure.at, from = pos, to = pos;
  const before = current => current && config.nativeStructure.before(current);
  const stringMember=node?.name==='String' && node.nativeIdentifierRoles?.includes('nm') && before(node)?.name==='.';
  if (node && /Comment|String/.test(node.name) && !stringMember) return null;
  let quoted;
  if (identifier(node,'nm',stringMember) || node?.name === 'Keyword') {
    from = node.from;
    to = node.to;
    quoted = node.name === 'QuotedIdentifier' || stringMember ? state.sliceDoc(from, from + 1) : undefined;
    node = before(node);
  } else if (node?.name !== '.') {
    if (!context.explicit) return null;
    node = null;
  }
  const parents = [];
  const duckDot=config.nativeEngine==='duckdb' && node?.name==='.' ? node : null;
  while (!duckDot && node?.name === '.') {
    const parent = before(node);
    if (!identifier(parent,'qualifier',true)) return null;
    parents.unshift(config.nativeName(parent));
    node = before(parent);
  }
  const options = [], seen = new Set();
  const add = option => {
    if (option?.label && !seen.has(option.label)) {seen.add(option.label); options.push(option);}
  };
  const addBranch = branch => {
    for (const entry of Object.values(branch || {})) add(entry.self || entry);
  };
  if(duckDot) {
    const target=duckdbCompletionTarget(config,state,duckDot);
    if(!target)return null;
    addBranch(target.children);
  } else if (parents.length) {
    const target = config.nativeResolve(parents);
    if (!target) return null;
    addBranch(target.children);
  } else {
    addBranch(config.schema);
    if (config.defaultSchema) addBranch(config.nativeResolve([config.defaultSchema])?.children);
    for (const [alias, entry] of config.nativeScopeBindings) {
      add({label: alias, apply: config.nativeQuote(alias), type: 'constant', detail: 'Source alias'});
      addBranch(entry.children);
    }
  }
  if (quoted) {
    const end = quoted === '[' ? ']' : quoted;
    return {from, to: Math.max(to, state.sliceDoc(pos, pos + 1) === end ? pos + 1 : pos),
      options: options.map(option => ({...option, label: quoted + option.label.replaceAll(end, end + end) + end,
        apply: quoted + option.label.replaceAll(end, end + end) + end}))};
  }
  return {from, to, options};
}
