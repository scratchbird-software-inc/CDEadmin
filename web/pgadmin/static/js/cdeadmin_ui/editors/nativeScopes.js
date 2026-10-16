import {nativeSourceStructure} from './nativeLexing';

const key = name => name.replaceAll('.', '\\.');
const identifier = node => ['Identifier', 'QuotedIdentifier'].includes(node?.name);

// Context suggestions use native mode-aware token boundaries. They never claim
// SQL grammar validity or infer column names from arbitrary expressions.
export function scopedSQLConfig(config, state, position) {
  const lower = value => value.replace(/[A-Z]/g, character => character.toLowerCase());
  const upper = value => value.replace(/[a-z]/g, character => character.toUpperCase());
  const exactCase = ['postgresql', 'firebird'].includes(config.nativeEngine) || config.nativeRelationCaseSensitive;
  const bindingKey = value => exactCase ? value : lower(value);
  const text = node => state.sliceDoc(node.from, node.to);
  const word = node => text(node).toUpperCase();
  const structure = nativeSourceStructure(state.doc.toString(), config.nativeLanguageContext, position);
  const children = node => node.children || [];
  const name = node => {
    const value = text(node);
    if (node.name !== 'QuotedIdentifier') return config.nativeEngine === 'postgresql' ? lower(value) :
      config.nativeEngine === 'firebird' ? upper(value) : value;
    const end = value[0] === '[' ? ']' : value[0];
    return value.slice(1, value.endsWith(end) ? -1 : undefined).replaceAll(end + end, end);
  };
  const path = node => node.name === 'CompositeIdentifier' ? children(node).filter(identifier).map(name) : identifier(node) ? [name(node)] : [];
  const quote = value => {
    const delimiter = config.nativeIdentifierQuote ?? config.dialect.spec.identifierQuotes?.[0] ?? '"';
    if (!delimiter) return value;
    return delimiter + value.replaceAll(delimiter, delimiter + delimiter) + delimiter;
  };
  const schema = {...config.schema};
  const lookup = (branch, part, exact=false) => branch?.[key(part)] || (!exact && Object.entries(branch || {}).filter(([candidate]) =>
    lower(candidate) === lower(key(part))).map(([, entry]) => entry).filter((_, index, all) => all.length === 1)[0]);
  const resolve = parts => {
    const follow = branch => {
      let entry;
      for (const part of parts) {entry = lookup(branch, part, exactCase); if (!entry) return undefined; branch = entry.children;}
      return entry;
    };
    return follow(schema) || follow(lookup(schema, config.defaultSchema || '')?.children);
  };
  const relation = (label, columns) => ({self: {label, apply: quote(label), type: 'type', detail: 'Source scope'},
    children: Object.fromEntries([...new Set(columns)].map(column => [key(column),
      {self: {label: column, apply: quote(column), type: 'property', detail: 'Source scope'}, children: Object.create(null)}]))});
  const columns = entry => Object.values(entry?.children || {}).map(child => child.self || child)
    .filter(child => child.type === 'property').map(child => child.label);

  const sourceBindings = (body, depth=0) => {
    const nodes = children(body).filter(node => !['(', ')'].includes(node.name));
    const select = nodes.findIndex(node => word(node) === 'SELECT');
    const from = nodes.findIndex((node, index) => index > select && word(node) === 'FROM');
    const bindings = new Map();
    for (let index = Math.max(0, from); from >= 0 && index < nodes.length - 1; index++) {
      if (['WHERE', 'GROUP', 'HAVING', 'ORDER', 'UNION', 'INTERSECT', 'EXCEPT', 'LIMIT', 'OFFSET', 'FETCH', 'FOR', 'RETURNING', 'WINDOW', 'QUALIFY'].includes(word(nodes[index]))) break;
      if (!['FROM', 'JOIN', ','].includes(word(nodes[index]))) continue;
      let at = index + 1;
      if (word(nodes[at]) === 'LATERAL') at++;
      const target = nodes[at];
      if (!target) continue;
      const parts = path(target);
      const entry = target.name === 'Parens' ? relation('', project(target, depth + 1)) : resolve(parts);
      at++;
      if (nodes[at] && word(nodes[at]) === 'AS') at++;
      const alias = identifier(nodes[at]) ? name(nodes[at]) : parts.at(-1);
      if (alias && entry) bindings.set(bindingKey(alias), entry);
    }
    return bindings;
  };
  const project = (body, depth=0) => {
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
    for (let group of groups) {
      group = group.filter(node => !['DISTINCT', 'ALL'].includes(word(node)));
      if (!group.length) continue;
      const last = group.at(-1), previous = group.at(-2);
      const implicitAlias = previous && previous.to < last.from && previous.name !== 'Operator' &&
        (previous.name !== 'Keyword' || word(previous) === 'END');
      if (identifier(last) && previous && (word(previous) === 'AS' || implicitAlias)) result.push(name(last));
      else if (group.length === 1 && path(last).length) result.push(path(last).at(-1));
      else if (word(last) === '*') {
        const qualifier = previous && path(previous).at(-1);
        const entries = qualifier ? [bindings.get(bindingKey(qualifier))] : [...bindings.values()];
        result.push(...entries.flatMap(columns));
      }
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
    while (identifier(nodes[at])) {
      const cte = nodes[at++], label = name(cte);
      let explicit;
      if (nodes[at]?.name === 'Parens') explicit = children(nodes[at++]).filter(identifier).map(name);
      if (!nodes[at] || word(nodes[at++]) !== 'AS') break;
      while (nodes[at] && ['NOT', 'MATERIALIZED'].includes(word(nodes[at]))) at++;
      const body = nodes[at++];
      if (body?.name !== 'Parens') break;
      if (recursive || position >= body.to) schema[key(label)] = relation(label, explicit || project(body));
      if (!nodes[at] || word(nodes[at++]) !== ',') break;
    }
  }
  const bindings = new Map();
  for (const container of containers) for (const [alias, entry] of sourceBindings(container)) bindings.set(alias, entry);
  return {...config, schema, nativeScopeBindings: bindings,
    nativeResolve: parts => parts.length === 1 && bindings.get(bindingKey(parts[0])) || resolve(parts),
    nativeName: name, nativeStructure: structure, nativeQuote: quote};
}

// CodeMirror's schema source performs literal path lookup and strips quoted
// identifiers without decoding doubled delimiters. Native identity rules must
// resolve these paths before constructing suggestions.
export function nativeSchemaCompletion(config, context) {
  const {state, pos} = context;
  let node = config.nativeStructure.at, from = pos, to = pos;
  if (node && /Comment|String/.test(node.name)) return null;
  const before = current => current && config.nativeStructure.before(current);
  let quoted;
  if (identifier(node) || node?.name === 'Keyword') {
    from = node.from;
    to = node.to;
    quoted = node.name === 'QuotedIdentifier' ? state.sliceDoc(from, from + 1) : undefined;
    node = before(node);
  } else if (node?.name !== '.') {
    if (!context.explicit) return null;
    node = null;
  }
  const parents = [];
  while (node?.name === '.') {
    const parent = before(node);
    if (!identifier(parent)) return null;
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
  if (parents.length) {
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
