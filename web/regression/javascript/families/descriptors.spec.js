import {
  activeFields, editorAvailable, fieldOptions, fieldVisible, formForKind, initialDraft, menuForKind,
  resolveBundle, resolveForm, toBackendDraft, validateDraft,
} from '../../../pgadmin/static/js/cdeadmin_ui/objects/descriptors';
import {loadEngineBundle, loadFamilies} from './familyFixtures';

const family = {
  family: 'widget', title: 'Widget',
  tabs: [
    {tab: 'General', primitive: 'group', required: true},
    {tab: 'Columns', primitive: 'grid', required: true},
    {tab: 'Options', primitive: 'group'},
    {tab: 'Engine', primitive: 'group'},
    {tab: 'Dependencies', primitive: 'readonly_grid'},
    {tab: 'SQL', primitive: 'sql_preview', required: true},
  ],
};

const form = {
  schema: 'cdeadmin.ui-form.v1', engine: 'acme', family: 'widget', resource_kinds: ['widget'],
  status: 'draft', engine_tab_title: 'Acme',
  omitted_tabs: [{tab: 'Options', reason: 'none'}],
  fields: [
    {field_id: 'name', label: 'Name', tab: 'General', control: 'text', required: true},
    {field_id: 'engine', label: 'Storage engine', tab: 'Engine', control: 'select',
      options: [{value: 'a', label: 'A'}, {value: 'b', label: 'B'}], default: 'a',
      backend_field_id: 'widget_options.engine'},
    {field_id: 'union', label: 'Members', tab: 'Engine', control: 'multiselect',
      visible_when: {field: 'engine', equals: 'b'}, option_values_path: ['catalog', 'tables']},
    {field_id: 'columns', label: 'Columns', tab: 'Columns', control: 'grid', required: true,
      columns: [{field_id: 'name', label: 'Name', control: 'text', required: true},
        {field_id: 'type', label: 'Type', control: 'select', option_values_path: ['dialect', 'column_types']}]},
    {field_id: 'pk', label: 'Primary key', tab: 'Columns', control: 'grid', backend_field_id: 'constraints[kind=primary_key]',
      columns: [{field_id: 'columns', label: 'Columns', control: 'multiselect', option_values_path: ['draft', 'columns']}]},
    {field_id: 'lock', label: 'Lock', tab: 'General', control: 'select', modes: ['alter'],
      options: [{value: 'none', label: 'None'}]},
  ],
};

describe('resolveForm', () => {
  const resolved = resolveForm(family, form);
  it('keeps skeleton order, drops omitted and empty tabs, keeps shell tabs', () => {
    expect(resolved.tabs.map((tab) => tab.tab)).toEqual(['General', 'Columns', 'Engine', 'Dependencies', 'SQL']);
  });
  it('titles the Engine tab after the engine', () => {
    expect(resolved.tabs.find((tab) => tab.tab === 'Engine').title).toBe('Acme');
  });
  it('reports no missing required tabs when they are present or omitted', () => {
    expect(resolved.missing_required_tabs).toEqual([]);
    const thin = resolveForm(family, {...form, fields: form.fields.filter((field) => field.tab !== 'Columns')});
    expect(thin.missing_required_tabs).toEqual(['Columns']);
  });
  it('throws on an unknown family', () => {
    expect(() => resolveForm(undefined, form)).toThrow(/unknown family/);
  });
});

describe('visibility, modes and options', () => {
  const resolved = resolveForm(family, form);
  const engineTab = resolved.tabs.find((tab) => tab.tab === 'Engine');
  it('hides fields by visible_when and by mode', () => {
    expect(fieldVisible(form.fields[2], {engine: 'a'})).toBe(false);
    expect(fieldVisible(form.fields[2], {engine: 'b'})).toBe(true);
    expect(activeFields(engineTab.fields, {draft: {engine: 'a'}}).map((f) => f.field_id)).toEqual(['engine']);
    const general = resolved.tabs[0];
    expect(activeFields(general.fields, {mode: 'create'}).map((f) => f.field_id)).toEqual(['name']);
    expect(activeFields(general.fields, {mode: 'alter'}).map((f) => f.field_id)).toEqual(['name', 'lock']);
  });
  it('resolves option paths from context and from the draft', () => {
    const context = {catalog: {tables: [{name: 't1'}, {name: 't2'}]}, dialect: {column_types: ['int', 'text']}};
    expect(fieldOptions(form.fields[2], {context})).toEqual([{value: 't1', label: 't1'}, {value: 't2', label: 't2'}]);
    expect(fieldOptions(form.fields[3].columns[1], {context})).toEqual([{value: 'int', label: 'int'}, {value: 'text', label: 'text'}]);
    const pkColumns = form.fields[4].columns[0];
    expect(fieldOptions(pkColumns, {draft: {columns: [{name: 'id'}, {name: 'label'}]}}))
      .toEqual([{value: 'id', label: 'id'}, {value: 'label', label: 'label'}]);
    expect(fieldOptions({control: 'reference', reference_kind: 'table'}, {context: {resources: {table: [{resource_id: 'r1', display_name: 'T'}]}}}))
      .toEqual([{value: 'r1', label: 'T'}]);
    expect(fieldOptions({control: 'text'}, {})).toEqual([]);
  });
});

describe('drafts', () => {
  const resolved = resolveForm(family, form);
  it('starts from defaults and existing records, including dotted backend ids', () => {
    expect(initialDraft(resolved)).toEqual({engine: 'a', columns: [], pk: []});
    expect(initialDraft(resolved, {mode: 'alter', record: {name: 'w', widget_options: {engine: 'b'}}}))
      .toMatchObject({name: 'w', engine: 'b'});
  });
  it('validates required fields and grid rows', () => {
    expect(validateDraft(resolved, {engine: 'a', columns: []})).toEqual({
      name: 'Name is required.', columns: 'Columns is required.'});
    expect(validateDraft(resolved, {name: 'w', engine: 'a', columns: [{type: 'int'}]})).toEqual({
      'columns[0].name': 'Name is required in row 1.'});
    expect(validateDraft(resolved, {name: 'w', engine: 'a', columns: [{name: 'id'}]})).toEqual({});
  });
  it('maps the draft onto backend ids: dotted, bracketed and plain', () => {
    const draft = {name: 'w', engine: 'b', union: ['t1'], columns: [{name: 'id', type: 'int'}], pk: [{columns: ['id']}]};
    expect(toBackendDraft(resolved, draft)).toEqual({
      name: 'w', widget_options: {engine: 'b'}, union: ['t1'],
      columns: [{name: 'id', type: 'int'}], constraints: [{kind: 'primary_key', columns: ['id']}],
    });
    // hidden fields are not sent
    expect(toBackendDraft(resolved, {name: 'w', engine: 'a', union: ['t1'], columns: []})).not.toHaveProperty('union');
  });
});

describe('bundles and menus', () => {
  const bundle = resolveBundle({
    engine: 'acme', families: {widget: family},
    capabilities: {engine: 'acme', kinds: [
      {resource_kind: 'widget', family: 'widget', operations: [{operation_id: 'create', tier: 1}, {operation_id: 'alter', tier: 1}, {operation_id: 'drop', tier: 1}, {operation_id: 'grant', tier: 1}]},
      {resource_kind: 'gizmo', family: 'engine_object', operations: []},
    ]},
    operations: [
      {operation_id: 'analyze', resource_kind: 'widget', title: 'Analyze', menu: {category: 'diagnostics'}, tier: 2, status: 'draft', fields: []},
      {operation_id: 'backup', resource_kind: 'widget', title: 'Back up', menu: {category: 'backup_restore', order: 2}, tier: 3, status: 'draft', fields: []},
      {operation_id: 'verify', resource_kind: 'widget', title: 'Verify backup', menu: {category: 'backup_restore', order: 1}, tier: 3, status: 'draft', fields: []},
    ],
    forms: {widget: form},
  });
  it('indexes kinds, forms and operations', () => {
    expect(formForKind(bundle, 'widget').family).toBe('widget');
    expect(formForKind(bundle, 'gizmo')).toBeNull();
    expect(editorAvailable(bundle, 'widget')).toBe(true);
    expect(editorAvailable(bundle, 'gizmo')).toBe(false);
    expect(bundle.kinds.widget.tier1).toEqual(['create', 'alter', 'drop', 'grant']);
  });
  it('builds the categorised menu in the fixed order with children, lifecycle and tiers', () => {
    const menu = menuForKind(bundle, 'widget', {childKinds: ['gizmo']});
    expect(menu.map((group) => group.category)).toEqual(['create', 'open', 'lifecycle', 'backup_restore', 'security', 'diagnostics', 'refresh']);
    expect(menu.find((g) => g.category === 'create').items[0].label).toBe('Gizmo...');
    expect(menu.find((g) => g.category === 'lifecycle').items.map((i) => i.label)).toEqual(['Edit...', 'Drop...']);
    expect(menu.find((g) => g.category === 'backup_restore').items.map((i) => i.label)).toEqual(['Verify backup', 'Back up']);
    expect(menu.find((g) => g.category === 'security').items[0].operation_id).toBe('grant');
  });
  it('disables everything that needs a connection when disconnected', () => {
    const menu = menuForKind(bundle, 'widget', {connected: false});
    const ops = menu.flatMap((group) => group.items).filter((item) => item.operation_id);
    expect(ops.every((item) => item.enabled === false)).toBe(true);
  });
});

describe('real engine descriptors', () => {
  it('every beta engine declares a table editor the shell will open', () => {
    for(const engine of ['postgresql', 'mysql', 'mariadb', 'firebird', 'duckdb', 'sqlite']) {
      const bundle = loadEngineBundle(engine);
      expect(editorAvailable(bundle, 'table')).toBe(true);
      const menu = menuForKind(bundle, 'table');
      expect(menu[0].category).toBe('open');
      expect(menu.at(-1).category).toBe('refresh');
    }
  });
  it('the family skeleton list matches the ten families', () => {
    expect(Object.keys(loadFamilies()).sort()).toEqual(
      ['database', 'index', 'role', 'routine', 'sequence', 'server', 'table', 'trigger', 'type', 'view']);
  });
});
