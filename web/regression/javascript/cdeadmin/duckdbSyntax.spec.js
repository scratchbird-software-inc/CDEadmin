import {duckdbSQLConfig} from 'sources/cdeadmin_ui/editors/duckdbSyntax';

describe('DuckDB catalog-qualified SQL completion', () => {
  it('keeps catalogs distinct and quotes every native identifier', () => {
    const resources = [
      {resource_kind: 'table', display_path: ['main.file', 'work', 'a"b']},
      {resource_kind: 'column', display_path: ['main.file', 'work', 'a"b', 'c.d']},
      {resource_kind: 'table', display_path: ['archive', 'work', 'a"b']},
      {resource_kind: 'column', display_path: ['archive', 'work', 'a"b', 'other']},
      {resource_kind: 'secret', display_path: ['archive', 'private']},
    ];
    const config = duckdbSQLConfig({keywords: 'select from'}, resources);
    expect(config.dialect.spec.keywords).toBe('select from');
    const first = config.schema['main\\.file'].children.work.children['a"b'];
    const second = config.schema.archive.children.work.children['a"b'];
    expect(config.schema['main\\.file'].self.apply).toBe('"main.file"');
    expect(first.self.apply).toBe('"a""b"');
    expect(first.children).toEqual([{label: 'c.d', apply: '"c.d"', type: 'property'}]);
    expect(second.children).toEqual([{label: 'other', apply: '"other"', type: 'property'}]);
    expect(config.schema.archive.children.private).toBeUndefined();
  });

  it('does not invent columns when only a truncated relation page is visible', () => {
    const config = duckdbSQLConfig({}, [{resource_kind: 'column',
      display_path: ['main', 'main', 'missing', 'unloaded']}]);
    expect(Object.keys(config.schema)).toEqual([]);
  });
});
