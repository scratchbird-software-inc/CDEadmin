import {SQLDialect, StandardSQL} from '@codemirror/lang-sql';

const key = value => value.replaceAll('.', '\\.');
const quoted = value => `"${value.replaceAll('"', '""')}"`;
const node = (name, children={}) => ({self: {label: name, apply: quoted(name), type: 'type'}, children});

// The navigator supplies one selected file's visible page. Never merge names
// from a different endpoint or infer absent objects from a truncated page.
export function duckdbSQLConfig(editor={}, resources=[]) {
  const schema = Object.create(null), relations = new Map();
  const kinds = new Set(['table', 'view']);
  for(const item of resources) {
    const path = item?.display_path;
    if(!kinds.has(item?.resource_kind) || !Array.isArray(path) || path.length !== 3 ||
      path.some(part => typeof part !== 'string' || !part)) continue;
    const [catalog, scope, name] = path;
    const catalogKey = key(catalog), scopeKey = key(scope), relationKey = key(name);
    schema[catalogKey] ||= node(catalog);
    schema[catalogKey].children[scopeKey] ||= node(scope);
    const branch = schema[catalogKey].children[scopeKey].children;
    branch[relationKey] = node(name, []);
    relations.set(JSON.stringify(path), branch[relationKey].children);
  }
  for(const item of resources) {
    const path = item?.display_path;
    if(item?.resource_kind !== 'column' || !Array.isArray(path) || path.length !== 4) continue;
    const columns = relations.get(JSON.stringify(path.slice(0, 3)));
    if(columns && typeof path[3] === 'string' && path[3] &&
      !columns.some(entry => entry.label === path[3]))
      columns.push({label: path[3], apply: quoted(path[3]), type: 'property'});
  }
  return {dialect: SQLDialect.define({keywords: editor.keywords?.toLowerCase() || StandardSQL.spec.keywords,
    identifierQuotes: '"', caseInsensitiveIdentifiers: true,
    doubleDollarQuotedStrings: true, backslashEscapes: false}),
  schema, upperCaseKeywords: true};
}
