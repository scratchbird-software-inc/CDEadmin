import {nativePropertyFormKey} from '../../../pgadmin/static/js/cdeadmin_ui/navigation/nativePropertyReferences';
import references from '../../../pgadmin/static/js/cdeadmin_ui/navigation/formReferences.json';

describe('Native property references', () => {
  it.each(['server', 'role', 'tablespace', 'database', 'extension', 'language',
    'cast', 'event_trigger', 'foreign_data_wrapper', 'foreign_server',
    'user_mapping', 'publication', 'subscription', 'schema', 'table', 'view',
    'mview', 'sequence', 'foreign_table', 'foreign_table_column', 'domain',
    'domain_constraints', 'type', 'function', 'procedure', 'trigger_function',
    'aggregate', 'collation', 'operator', 'fts_configuration', 'fts_dictionary',
    'fts_parser', 'fts_template', 'column', 'primary_key', 'unique_constraint',
    'check_constraint', 'exclusion_constraint', 'foreign_key', 'index', 'trigger',
    'partition', 'rule', 'row_security_policy', 'catalog', 'catalog_object',
    'catalog_object_column'])('%s resolves an allocated native form', type => {
    const key = nativePropertyFormKey(type);
    expect(key).not.toBe('inspector');
    expect(references.forms[key]?.reference).toMatch(/^SR-F-\d{6}$/);
  });

  it('reuses the original function and catalog relation forms', () => {
    expect(nativePropertyFormKey('trigger_function')).toBe(nativePropertyFormKey('function'));
    expect(nativePropertyFormKey('catalog_object')).toBe(nativePropertyFormKey('table'));
    expect(nativePropertyFormKey('catalog_object_column')).toBe(nativePropertyFormKey('column'));
    expect(references.forms[nativePropertyFormKey('table')].reference).toBe('SR-F-000333');
  });
});
