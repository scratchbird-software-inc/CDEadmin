// Canonical reusable native forms, independent of object identities and parents.
const scopes = {
  endpoint: ['role', 'tablespace', 'database'],
  database: ['extension', 'language', 'cast', 'event_trigger',
    'foreign_data_wrapper', 'publication', 'subscription', 'schema'],
  schema: ['table', 'view', 'mview', 'sequence', 'foreign_table', 'domain',
    'type', 'function', 'procedure', 'aggregate', 'collation', 'operator',
    'fts_configuration', 'fts_dictionary', 'fts_parser', 'fts_template'],
  table: ['column', 'primary_key', 'unique_constraint', 'check_constraint',
    'exclusion_constraint', 'foreign_key', 'index', 'trigger', 'partition',
    'rule', 'row_security_policy'],
  'foreign-data-wrapper': ['foreign_server'],
  'foreign-server': ['user_mapping'],
  'foreign-table': ['foreign_table_column'],
};
const kinds = {
  mview: 'materialized-view', row_security_policy: 'row-policy',
  foreign_table_column: 'column',
  fts_configuration: 'text-search-configuration',
  fts_dictionary: 'text-search-dictionary', fts_parser: 'text-search-parser',
  fts_template: 'text-search-template',
};
const keys = Object.fromEntries(Object.entries(scopes).flatMap(([scope, types]) =>
  types.map(type => [type, `native:postgresql:${scope}:${kinds[type] || type.replaceAll('_', '-')}`])));

export function nativePropertyFormKey(type) {
  if (type === 'server') return 'server-profile';
  if (type === 'trigger_function') return keys.function;
  if (type === 'catalog') return 'native:postgresql:system-catalog:schema';
  if (type === 'catalog_object') return keys.table;
  if (type === 'catalog_object_column') return keys.column;
  if (type === 'domain_constraints') return 'native-property:domain-constraint';
  return keys[type] || 'inspector';
}
