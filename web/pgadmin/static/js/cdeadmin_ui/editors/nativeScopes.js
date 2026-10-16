import {syntaxTree} from '@codemirror/language';

const key = name => name.replaceAll('.', '\\.');
const identifier = node => ['Identifier', 'QuotedIdentifier'].includes(node?.name);

// Context suggestions use the editor's mode-aware token tree. They never claim
// SQL grammar validity or infer column names from arbitrary expressions.
export function scopedSQLConfig(config, state, position) {
  const text = node => state.sliceDoc(node.from, node.to);
  const word = node => text(node).toUpperCase();
  const children = node => {
    const result = [];
    for (let child = node.firstChild; child; child = child.nextSibling)
      if (!/Comment/.test(child.name)) result.push(child);
    return result;
  };
  const name = node => {
    const value = text(node);
    if (node.name !== 'QuotedIdentifier') return value;
    const end = value[0] === '[' ? ']' : value[0];
    return value.slice(1, value.endsWith(end) ? -1 : undefined).replaceAll(end + end, end);
  };
  const path = node => node.name === 'CompositeIdentifier' ? children(node).filter(identifier).map(name) : identifier(node) ? [name(node)] : [];
  const quote = value => {
    const delimiter = config.dialect.spec.identifierQuotes?.[0] || '"';
    return delimiter + value.replaceAll(delimiter, delimiter + delimiter) + delimiter;
  };
  const schema = {...config.schema};
  const lookup = (branch, part, exact=false) => branch?.[key(part)] || (!exact && Object.entries(branch || {}).filter(([candidate]) =>
    candidate.toLowerCase() === key(part).toLowerCase()).map(([, entry]) => entry).filter((_, index, all) => all.length === 1)[0]);
  const resolve = (parts, node) => {
    const names = node?.name === 'CompositeIdentifier' ? children(node).filter(identifier) : [node];
    const follow = branch => {
      let entry;
      for (const [index, part] of parts.entries()) {entry = lookup(branch, part, names[index]?.name === 'QuotedIdentifier'); if (!entry) return undefined; branch = entry.children;}
      return entry;
    };
    return follow(schema) || follow(lookup(schema, config.defaultSchema || '')?.children);
  };
  const relation = (label, columns) => ({self: {label, apply: quote(label), type: 'type', detail: 'Source scope'},
    children: Object.fromEntries([...new Set(columns)].map(column => [key(column),
      {self: {label: column, apply: quote(column), type: 'property', detail: 'Source scope'}, children: Object.create(null)}]))});
  const columns = entry => Object.values(entry?.children || {}).filter(child => child.self?.type === 'property').map(child => child.self.label);

  const project = (body, depth=0) => {
    if (depth > 12) return [];
    const nodes = children(body).filter(node => !['(', ')'].includes(node.name));
    const select = nodes.findIndex(node => word(node) === 'SELECT');
    if (select < 0) return [];
    const from = nodes.findIndex((node, index) => index > select && word(node) === 'FROM');
    const bindings = new Map();
    for (let index = Math.max(0, from); from >= 0 && index < nodes.length - 1; index++) {
      if (!['FROM', 'JOIN', ','].includes(word(nodes[index]))) continue;
      let at = index + 1;
      if (word(nodes[at]) === 'LATERAL') at++;
      const target = nodes[at];
      if (!target) continue;
      const parts = path(target);
      const entry = target.name === 'Parens' ? relation('', project(target, depth + 1)) : resolve(parts, target);
      at++;
      if (nodes[at] && word(nodes[at]) === 'AS') at++;
      const alias = identifier(nodes[at]) ? name(nodes[at]) : parts.at(-1);
      if (alias && entry) bindings.set(alias.toLowerCase(), entry);
    }
    const groups = [[]];
    for (const node of nodes.slice(select + 1, from < 0 ? undefined : from)) {
      if (word(node) === ',') groups.push([]); else groups.at(-1).push(node);
    }
    const result = [];
    for (let group of groups) {
      group = group.filter(node => !['DISTINCT', 'ALL'].includes(word(node)));
      if (!group.length) continue;
      const last = group.at(-1), previous = group.at(-2);
      if (identifier(last) && previous && (word(previous) === 'AS' || group.length > 1)) result.push(name(last));
      else if (group.length === 1 && path(last).length) result.push(path(last).at(-1));
      else if (word(last) === '*') {
        const qualifier = previous && path(previous).at(-1);
        const entries = qualifier ? [bindings.get(qualifier.toLowerCase())] : [...bindings.values()];
        result.push(...entries.flatMap(columns));
      }
    }
    return result;
  };

  // Enclosing scopes only: a CTE in another statement or sibling subquery must
  // never appear here. Inner definitions shadow outer names.
  const containers = [];
  syntaxTree(state).iterate({enter(node) {
    if (node.from > position || node.to < position) return false;
    if (['Statement', 'Parens'].includes(node.name)) containers.push(node.node);
  }});
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
  return {...config, schema};
}
