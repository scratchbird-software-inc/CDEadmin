import {SQLDialect} from '@codemirror/lang-sql';

export function firebirdSQLConfig(keywords, dialect, resources, reservedWords = []) {
  const schema = Object.create(null);
  const names = new Map();
  const reserved = new Set(reservedWords);
  const admitted = name => typeof name === 'string' && (dialect !== 1 || /^[A-Z][A-Z0-9_$]*$/.test(name) && !reserved.has(name));
  const quoted = name => dialect === 1 ? name : '"' + name.replaceAll('"', '""') + '"';
  for(const item of resources || []) {
    if(['table', 'view'].includes(item.resource_kind) && admitted(item.display_name)) {
      const key = item.display_name.replaceAll('.', '\\.');
      names.set(item.display_name, key);
      schema[key] = {self: {label: item.display_name, apply: quoted(item.display_name), type: 'type'}, children: []};
    }
  }
  for(const item of resources || []) {
    if(item.resource_kind !== 'column') continue;
    const owner = item.native?.relation_name || item.display_path?.at(-2);
    if(names.has(owner) && admitted(item.display_name)) schema[names.get(owner)].children.push({label: item.display_name,
      apply: quoted(item.display_name), type: 'property'});
  }
  return {dialect: SQLDialect.define({keywords, backslashEscapes: false,
    doubleDollarQuotedStrings: false, doubleQuotedStrings: dialect === 1,
    plsqlQuotingMechanism: true, charSetCasts: true, specialVar: ':?',
    identifierQuotes: dialect === 1 ? '' : '"', caseInsensitiveIdentifiers: false}),
  schema, upperCaseKeywords: true};
}
