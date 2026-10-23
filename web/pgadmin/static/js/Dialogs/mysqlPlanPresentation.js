// Native plan presentation only. This module never executes or rewrites SQL.
import {parse, stringify, isLosslessNumber} from 'lossless-json';

export const PLAN_LIMITS = Object.freeze({bytes: 4 * 1024 * 1024, nodes: 500, depth: 64});
const own = (value, key) => Object.prototype.hasOwnProperty.call(value, key);
const object = value => value !== null && typeof value === 'object' &&
  !Array.isArray(value) && !isLosslessNumber(value);
const literal = value => typeof value === 'string' ? value : stringify(value);
const METADATA = new Set(['cost_info', 'used_columns', 'used_key_parts', 'possible_keys',
  'partitions', 'key_length', 'attached_condition', 'index_condition']);

function boundedJSON(source) {
  let quoted = false, escaped = false, depth = 0;
  for (const char of source) {
    if (quoted) {
      if (escaped) escaped = false;
      else if (char === '\\') escaped = true;
      else if (char === '"') quoted = false;
    } else if (char === '"') quoted = true;
    else if (char === '{' || char === '[') {
      if (++depth > PLAN_LIMITS.depth) throw new Error('Native plan nesting exceeds the graphical limit.');
    } else if (char === '}' || char === ']') depth--;
  }
  // The parser assigns object properties. Refuse prototype setters before it
  // constructs any objects, including escaped spellings; retain raw text.
  for (const match of source.matchAll(/"(?:\\[\s\S]|[^"\\])*"\s*:/g)) {
    if (JSON.parse(match[0].slice(0, match[0].lastIndexOf(':')).trim()) === '__proto__') {
      throw new Error('Native plan contains an unsupported object key.');
    }
  }
  return parse(source);
}

function jsonGraph(root) {
  const version2 = own(root, 'query_plan') && object(root.query_plan);
  if (!version2 && !(own(root, 'query_block') && object(root.query_block))) {
    throw new Error('The returned JSON is not a recognized native MySQL plan.');
  }
  const nodes = [], roots = [];
  const add = (value, name, parent, path, depth) => {
    if (depth > PLAN_LIMITS.depth || nodes.length >= PLAN_LIMITS.nodes) {
      throw new Error('Native plan exceeds the graphical node or nesting limit.');
    }
    const node = {id: nodes.length, label: typeof value.operation === 'string' ? value.operation : name,
      path, parent, children: [], facts: [], actual: false};
    nodes.push(node);
    if (parent === null) roots.push(node.id);
    else nodes[parent].children.push(node.id);
    const children = [];
    for (const [key, item] of Object.entries(value)) {
      if (key === 'operation') continue;
      const branch = !METADATA.has(key) && (object(item) ||
        Array.isArray(item) && item.some(object));
      if (branch && (!version2 || key === 'inputs' || object(item) && typeof item.operation === 'string')) {
        const entries = Array.isArray(item) ? item.map((entry, index) => [index, entry]) : [[null, item]];
        for (const [index, entry] of entries) {
          if (!object(entry)) {
            node.facts.push({name: key + '[' + index + ']', value: literal(entry)});
            continue;
          }
          const childName = index === null ? key : key + '[' + index + ']';
          children.push([entry, childName, path + '.' + childName]);
        }
      } else {
        node.facts.push({name: key, value: literal(item)});
        if (key.startsWith('actual_')) node.actual = true;
      }
    }
    for (const [entry, childName, childPath] of children) add(entry, childName, node.id, childPath, depth + 1);
  };
  if (version2) add(root.query_plan, 'query_plan', null, '$.query_plan', 0);
  else add(root.query_block, 'query_block', null, '$.query_block', 0);
  return {format: version2 ? 'JSON version 2' : 'JSON version 1', nodes, roots,
    metadata: Object.entries(root).filter(([key]) => key !== (version2 ? 'query_plan' : 'query_block'))
      .map(([name, value]) => ({name, value: literal(value)}))};
}

function treeGraph(source) {
  const nodes = [], roots = [], stack = [];
  for (const [lineIndex, line] of source.split(/\r?\n/).entries()) {
    if (!line.trim()) continue;
    const match = /^( *)-> (.+)$/.exec(line);
    if (!match) {
      if (!nodes.length) throw new Error('The returned text is not a native MySQL TREE plan.');
      // Native descriptions can wrap; preserve them without inventing an edge.
      nodes[nodes.length - 1].facts.push({name: 'native continuation', value: line});
      continue;
    }
    if (nodes.length >= PLAN_LIMITS.nodes) throw new Error('Native plan exceeds the graphical node limit.');
    const indent = match[1].length;
    while (stack.length && stack[stack.length - 1].indent >= indent) stack.pop();
    if (stack.length >= PLAN_LIMITS.depth) throw new Error('Native plan nesting exceeds the graphical limit.');
    const parent = stack.length ? stack[stack.length - 1].id : null;
    const text = match[2], facts = [];
    const estimates = /\(cost=[^\r\n]*?\)/.exec(text);
    const actual = /\(actual time=[^\r\n]*?\)|\(never executed\)/.exec(text);
    if (estimates) facts.push({name: 'native estimates', value: estimates[0]});
    if (actual) facts.push({name: 'native actuals', value: actual[0]});
    const node = {id: nodes.length, parent, label: text, path: 'line ' + (lineIndex + 1),
      children: [], facts, actual: Boolean(actual)};
    nodes.push(node);
    if (parent === null) roots.push(node.id);
    else nodes[parent].children.push(node.id);
    stack.push({indent, id: node.id});
  }
  if (!nodes.length) throw new Error('The native plan contains no operator lines.');
  return {format: 'TREE', nodes, roots, metadata: []};
}

export function mysqlPlanText(rendered) {
  const view = rendered?.view_model;
  const rows = view?.rows || view?.records;
  const columns = view?.columns || view?.schema?.columns;
  if (!Array.isArray(rows) || rows.length !== 1 || !Array.isArray(columns) || columns.length !== 1 ||
      String(columns[0].native_name || columns[0].name).toUpperCase() !== 'EXPLAIN') return null;
  const row = rows[0];
  const value = Array.isArray(row) ? row[0] : object(row) ? row[columns[0].key || columns[0].name] : null;
  return typeof value === 'string' ? value : null;
}

export function parseMySQLPlan(source) {
  if (typeof source !== 'string') return {available: false, reason: 'No single native EXPLAIN text cell was returned.'};
  if (new TextEncoder().encode(source).length > PLAN_LIMITS.bytes) {
    return {available: false, reason: 'Native plan exceeds the 4 MiB graphical limit.'};
  }
  try {
    const graph = source.trimStart().startsWith('{') ? jsonGraph(boundedJSON(source)) : treeGraph(source);
    return {...graph, available: true, hasActual: graph.nodes.some(node => node.actual)};
  } catch (error) {
    return {available: false, reason: error instanceof RangeError ? 'Native plan exceeds the graphical nesting limit.' : error.message};
  }
}
