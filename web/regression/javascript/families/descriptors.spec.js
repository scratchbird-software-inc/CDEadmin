import {
  activeFields, editorAvailable, fieldOptions, fieldVisible, formForKind, initialDraft, menuForKind,
  operationContext, resolveBundle, resolveForm, toBackendDraft, toOperationDraft, validateDraft,
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
    // references are sent as dotted display paths, which is what providers parse
    expect(fieldOptions({control: 'reference', reference_kind: 'table'}, {context: {resources: {table: [
      {resource_id: 'r1', display_name: 'T', display_path: ['public', 'T']}, {resource_id: 'r2', display_name: 'U'}]}}}))
      .toEqual([{value: 'public.T', label: 'T'}, {value: 'U', label: 'U'}]);
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
  it('gives each engine-object kind its own form (decision 15, 2026-10-29)', () => {
    const engineObject = {schema: 'cdeadmin.ui-family.v1', family: 'engine_object', title: 'Engine object',
      tabs: [{tab: 'General', primitive: 'group', required: true}, {tab: 'SQL', primitive: 'sql_preview', required: true}]};
    const objectForm = (kind) => ({schema: 'cdeadmin.ui-form.v1', engine: 'acme', family: 'engine_object',
      resource_kinds: [kind], status: 'draft', fields: [{field_id: `${kind}_name`, label: 'Name', tab: 'General', control: 'text'}]});
    const objects = resolveBundle({
      engine: 'acme', families: {widget: family, engine_object: engineObject},
      capabilities: {engine: 'acme', kinds: [
        {resource_kind: 'gizmo', family: 'engine_object', operations: [{operation_id: 'create', tier: 1}]},
        {resource_kind: 'gadget', family: 'engine_object', operations: [{operation_id: 'create', tier: 1}]},
        {resource_kind: 'doohickey', family: 'engine_object', operations: []},
      ]},
      forms: {a: objectForm('gizmo'), b: objectForm('gadget')},
    });
    expect(formForKind(objects, 'gizmo').fields[0].field_id).toBe('gizmo_name');
    expect(formForKind(objects, 'gadget').fields[0].field_id).toBe('gadget_name');
    expect(formForKind(objects, 'doohickey')).toBeNull();
    expect(editorAvailable(objects, 'gizmo')).toBe(true);
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
  it('the family skeleton list matches the ten families plus the engine object', () => {
    // engine_object added by owner direction 2026-10-29 (ui_unified_design.rst decision 15).
    expect(Object.keys(loadFamilies()).sort()).toEqual(
      ['database', 'engine_object', 'index', 'role', 'routine', 'sequence', 'server', 'table', 'trigger',
        'type', 'view']);
  });
});

describe('alter-mode column diff', () => {
  const {diffColumns} = require('../../../pgadmin/static/js/cdeadmin_ui/objects/descriptors');
  it('produces add, drop and rename lists from grid rows', () => {
    const before = [{_id: '0', name: 'id', type: 'INTEGER'}, {_id: '1', name: 'note', type: 'TEXT'}, {_id: '2', name: 'old', type: 'TEXT'}];
    const after = [{_id: '0', name: 'id', type: 'INTEGER'}, {_id: '1', name: 'remark', type: 'TEXT'}, {name: 'added', type: 'REAL'}];
    expect(diffColumns(before, after)).toEqual({
      add_columns: [{name: 'added', type: 'REAL'}], drop_columns: ['old'], rename_columns: [{from: 'note', to: 'remark'}],
      alter_columns: []});
  });
  it('reports changed cells on existing rows as alter_columns, grid columns only', () => {
    const before = [{_id: '0', name: 'id', type: 'INT', default: '1', position: 1},
      {_id: '1', name: 'note', type: 'TEXT', nullable: true}];
    const after = [{_id: '0', name: 'id', type: 'BIGINT', default: '', position: 9},
      {_id: '1', name: 'remark', type: 'TEXT', nullable: false}];
    expect(diffColumns(before, after, ['name', 'type', 'default', 'nullable'])).toEqual({
      add_columns: [], drop_columns: [], rename_columns: [{from: 'note', to: 'remark'}],
      alter_columns: [{name: 'id', changes: {type: 'BIGINT', default: null}},
        {name: 'remark', changes: {nullable: false}}]});
  });
  it('sends only the ALTER set through toBackendDraft', () => {
    const resolved = resolveForm(family, form);
    const record = {name: 'w', columns: [{name: 'id', type: 'int'}], widget_options: {engine: 'a'}};
    const baseline = initialDraft(resolved, {mode: 'alter', record});
    const draft = {...baseline, columns: [...baseline.columns, {name: 'extra', type: 'text'}], engine: 'b'};
    expect(toBackendDraft(resolved, draft, {mode: 'alter', baseline})).toEqual({
      add_columns: [{name: 'extra', type: 'text'}], widget_options: {engine: 'b'}}); // unchanged name stays out
  });
});

describe('record pre-fill and list projections (kept in step with tools/ui_descriptor_roundtrip.py)', () => {
  const {gridRowFromRecord} = require('../../../pgadmin/static/js/cdeadmin_ui/objects/descriptors');
  const listFamily = {family: 'thing', title: 'Thing', tabs: [{tab: 'General', primitive: 'group', required: true}, {tab: 'SQL', primitive: 'sql_preview', required: true}]};
  const listForm = {schema: 'cdeadmin.ui-form.v1', engine: 'acme', family: 'thing', resource_kinds: ['thing'], status: 'draft', fields: [
    {field_id: 'name', label: 'Name', tab: 'General', control: 'text', required: true},
    {field_id: 'columns', label: 'Columns', tab: 'General', control: 'grid', item_kind: 'string',
      columns: [{field_id: 'value', label: 'Column', control: 'reference', reference_kind: 'column'}]},
    {field_id: 'events', label: 'Event', tab: 'General', control: 'select', wrap_list: true, options: [{value: 'INSERT', label: 'Insert'}]},
    {field_id: 'cols', label: 'Cols', tab: 'General', control: 'grid', columns: [
      {field_id: 'name', label: 'Name', control: 'text'}, {field_id: 'type', label: 'Type', control: 'text', record_key: 'data_type'},
      {field_id: 'primary_key', label: 'PK', control: 'boolean', record_key: 'primary_key_position', record_truthy: true}]},
  ]};
  const resolved = resolveForm(listFamily, listForm);
  it('flattens string grids and wraps single selects into lists', () => {
    expect(toBackendDraft(resolved, {name: 'ix', columns: [{value: 'label'}, {value: ''}], events: 'INSERT', cols: []}))
      .toEqual({name: 'ix', columns: ['label'], events: ['INSERT'], cols: []});
  });
  it('pre-fills grids from inspected record keys', () => {
    const draft = initialDraft(resolved, {mode: 'alter', record: {name: 'orders', columns: ['a', 'b'],
      cols: [{name: 'id', data_type: 'INTEGER', primary_key_position: 1}, {name: 'note', data_type: 'TEXT', primary_key_position: 0}]}});
    expect(draft.columns).toEqual([{value: 'a', _id: '0'}, {value: 'b', _id: '1'}]);
    expect(draft.cols).toEqual([
      {name: 'id', data_type: 'INTEGER', primary_key_position: 1, type: 'INTEGER', primary_key: true, _id: '0'},
      {name: 'note', data_type: 'TEXT', primary_key_position: 0, type: 'TEXT', primary_key: false, _id: '1'}]);
  });
  it('pre-fills through dotted keys, derive rules, list filters, plucks and patterns', () => {
    const fbFamily = {family: 'fb', title: 'Fb', tabs: [{tab: 'General', primitive: 'group', required: true}, {tab: 'SQL', primitive: 'sql_preview', required: true}]};
    const fbForm = {schema: 'cdeadmin.ui-form.v1', engine: 'acme', family: 'fb', resource_kinds: ['fb'], status: 'draft', fields: [
      {field_id: 'name', label: 'Name', tab: 'General', control: 'text', required: true},
      {field_id: 'unique', label: 'Unique', tab: 'General', control: 'boolean', record_truthy: true},
      {field_id: 'body', label: 'Body', tab: 'General', control: 'code', record_key: 'metadata_source', record_pattern: '^\\s*AS\\s+(.*)$'},
      {field_id: 'kind', label: 'Kind', tab: 'General', control: 'select', options: [{value: 'columns', label: 'c'}, {value: 'expression', label: 'e'}],
        record_derive: {cases: [{key: 'expression_source', truthy: true, value: 'expression'}], default: 'columns'}},
      {field_id: 'cols', label: 'Cols', tab: 'General', control: 'grid', columns: [
        {field_id: 'name', label: 'Name', control: 'text'}, {field_id: 'type', label: 'Type', control: 'text', record_key: 'type_editor.data_type'},
        {field_id: 'mode', label: 'Mode', control: 'select', options: [{value: 'STORED', label: 's'}, {value: 'COMPUTED', label: 'c'}],
          record_derive: {cases: [{key: 'computed_source', truthy: true, value: 'COMPUTED'}], default: 'STORED'}}]},
      {field_id: 'pk', label: 'PK', tab: 'General', control: 'grid', backend_field_id: 'constraints[kind=PRIMARY KEY]',
        record_key: 'constraints', record_filter: {key: 'constraint_type', equals: 'PRIMARY KEY'}, columns: [
          {field_id: 'name', label: 'Name', control: 'text'},
          {field_id: 'columns', label: 'Columns', control: 'multiselect', record_key: 'backing_index.segments', record_pluck: 'field_name'}]},
    ]};
    const draft = initialDraft(resolveForm(fbFamily, fbForm), {mode: 'alter', record: {
      name: 'x', unique: '0', metadata_source: 'AS BEGIN END', expression_source: '(UPPER(A))',
      cols: [{name: 'a', type_editor: {data_type: 'INTEGER'}, computed_source: null}, {name: 'b', type_editor: {}, computed_source: '(a*2)'}],
      constraints: [{name: 'ck', constraint_type: 'CHECK'}, {name: 'pk', constraint_type: 'PRIMARY KEY', backing_index: {segments: [{field_name: 'a'}]}}],
    }});
    expect(draft.unique).toBe(false);
    expect(draft.body).toBe('BEGIN END');
    expect(draft.kind).toBe('expression');
    expect(draft.cols.map((row) => [row.name, row.type, row.mode])).toEqual([['a', 'INTEGER', 'STORED'], ['b', undefined, 'COMPUTED']]);
    expect(draft.pk).toEqual([{name: 'pk', constraint_type: 'PRIMARY KEY', backing_index: {segments: [{field_name: 'a'}]}, columns: ['a'], _id: '0'}]);
    expect(gridRowFromRecord({item_kind: 'string', columns: [{field_id: 'value'}]}, 'x', 3)).toEqual({value: 'x', _id: '3'});
  });
});

describe('operation dialog drafts (kept in step with operation_backend_draft)', () => {
  const operation = {fields: [
    {field_id: 'cells', control: 'grid', item_kind: 'string', columns: [{field_id: 'value'}]},
    {field_id: 'rules', control: 'grid', backend_field_id: 'rules.rules',
      columns: [{field_id: 'fromTable'}, {field_id: 'toTable'}]},
    {field_id: 'skip_rebuild', control: 'boolean'},
    {field_id: 'hidden', control: 'text', visible_when: {field: 'skip_rebuild', equals: true}},
  ]};

  it('sends string grids as plain lists and grid rows without _id', () => {
    expect(toOperationDraft(operation, {
      cells: [{value: 'zone1', _id: '0'}, {value: '', _id: '1'}],
      rules: [{fromTable: 'a.t', toTable: 'b.t', _id: '0'}],
      skip_rebuild: false, hidden: 'x',
    })).toEqual({cells: ['zone1'], rules: {rules: [{fromTable: 'a.t', toTable: 'b.t'}]}, skip_rebuild: false});
  });

  it('keeps a typed-name confirmation', () => {
    expect(toOperationDraft(operation, {cells: [], confirmation: 'ks'})).toEqual({cells: [], confirmation: 'ks'});
  });
});

describe('reference pickers fed by the catalog (operation dialog and editor)', () => {
  const row = (kind, path, native={}) => ({resource_kind: kind, resource_id: `${kind}:${path.join(':')}`,
    display_name: path.at(-1), display_path: path, native});
  const catalog = [
    row('keyspace', ['test_keyspace'], {sharded: true}),
    row('keyspace', ['lookup_keyspace'], {sharded: false}),
    row('keyspace', ['unknown_keyspace']),
    row('tablet', ['test_keyspace', '-80', 'test-0000000101']),
    row('tablet', ['test_keyspace', '80-', 'test-0000000201']),
    row('tablet', ['lookup_keyspace', '-', 'test-0000000301']),
    row('backup', ['lookup_keyspace', '-', '2026-10-30.125734.test-0000000301']),
    row('backup', ['test_keyspace', '-80', '2026-10-30.120000.test-0000000101']),
  ];
  const vitess = loadEngineBundle('vitess');
  const operation = (kind, id) => vitess.kinds[kind].operations.find((op) => op.operation_id === id);
  const values = (field, context) => fieldOptions(field, {context}).map((option) => option.value);

  it('restore offers only the target tablet\'s shard backups, by name', () => {
    const [field] = operation('tablet', 'restore').fields;
    const context = operationContext(vitess, catalog, catalog[5]);
    expect(values(field, context)).toEqual(['2026-10-30.125734.test-0000000301']);
    // No target, no scope match: nothing is offered.
    expect(values(field, operationContext(vitess, catalog, null))).toEqual([]);
  });

  it('reparent offers the shard\'s own tablets as aliases', () => {
    const field = operation('shard', 'planned_reparent').fields.find((item) => item.field_id === 'new_primary');
    const shard = row('shard', ['test_keyspace', '-80']);
    expect(values(field, operationContext(vitess, catalog, shard))).toEqual(['test-0000000101']);
  });

  it('procedure and sequence keyspaces are unsharded only; an unknown sharding is not offered', () => {
    const context = operationContext(vitess, catalog, null);
    for(const family of ['routine', 'sequence']) {
      const parent = vitess.forms[family].tabs.flatMap((tab) => tab.fields).find((item) => item.field_id === 'parent');
      expect(values(parent, context)).toEqual(['lookup_keyspace']);
    }
  });

  it('TiDB\'s exchange table sends the bare table name its provider joins to the database', () => {
    const tidb = loadEngineBundle('tidb');
    const field = tidb.kinds.partition.operations.find((op) => op.operation_id === 'exchange').fields
      .find((item) => item.field_id === 'exchange_table');
    const context = operationContext(tidb, [row('table', ['shop', 'orders_2025'])], null);
    expect(values(field, context)).toEqual(['orders_2025']);
  });

  it('keeps the dotted display path where no reference_value is set', () => {
    const field = {field_id: 'policy', control: 'reference', reference_kind: 'table'};
    expect(values(field, operationContext(vitess, [row('table', ['shop', 'orders'])], null))).toEqual(['shop.orders']);
  });
});
