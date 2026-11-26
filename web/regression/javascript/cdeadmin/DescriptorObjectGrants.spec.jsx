import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import DescriptorObjectGrants, {
  grantRows, objectGrantsOffered, objectTypeValue, parseAccount, dialogValues, canRevoke, heldRows, granteeSpelling, embeddedGrants, narrowedOperation,
} from '../../../pgadmin/static/js/cdeadmin_ui/security/DescriptorObjectGrants';
import ObjectGrantsSurface, {objectContext} from '../../../pgadmin/static/js/cdeadmin_ui/security/ObjectGrantsSurface';
import {resetDescriptorClient} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {loadEngineBundle} from '../families/familyFixtures';

const mockMatrix = jest.fn();
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/security/ObjectPermissionsMatrix', () => ({
  __esModule: true,
  default: (props) => { mockMatrix(props); return <div data-testid="legacy-matrix" />; },
}));

const grant = (object, grantee, code, extra = {}) => ({
  resource_kind: 'privilege', resource_id: `p:${grantee}:${code}:${object}:${extra.field || ''}`,
  display_name: `${grantee}:${code} on ${object}`,
  native: {grantee, privilege: code, object_name: object, user_type: 8, grant_option: 0, field: null, grantor: 'SYSDBA', ...extra},
});
const RESOURCES = [
  grant('ORDERS', 'ALICE', 'S', {grant_option: 1}),
  grant('ORDERS', 'ALICE', 'U', {field: 'NOTE'}),
  grant('ORDERS', 'AUDITOR', 'S', {user_type: 13}),
  grant('OTHER', 'BOB', 'S'),
  // A role membership and a system row are not object grants.
  grant('AUDITOR', 'ALICE', 'M', {user_type: 8}),
  {resource_kind: 'table', resource_id: 't:ORDERS', display_name: 'ORDERS', native: {}},
];

function makeApi(engine = 'firebird', items = RESOURCES, {fail = false} = {}) {
  const posts = [];
  return {posts, api: {
    get: jest.fn(async () => ({data: {success: 1, data: loadEngineBundle(engine)}})),
    post: jest.fn(async (_url, payload) => {
      posts.push(payload);
      if(payload.action === 'resource_page') {
        if(fail) throw new Error('permission denied reading grants');
        return {data: {success: 1, data: {items, next_cursor: null, generation: 'g'}}};
      }
      if(payload.action === 'visual_admin_validate') return {data: {success: 1, data: {valid: true, errors: []}}};
      if(payload.action === 'visual_admin_plan') {
        return {data: {success: 1, data: {plan_id: 'p', plan_digest: 'd', state: 'ready', execution_available: true}}};
      }
      return {data: {success: 1, data: {}}};
    }),
  }};
}

const mount = (props) => render(<Theme><DescriptorObjectGrants endpointUrl="/ws/1" engine="firebird"
  objectKind="table" objectName="ORDERS" {...props} /></Theme>);

describe('grant rows read through the descriptor', () => {
  const bundle = loadEngineBundle('firebird');
  it('keeps only the grants on this object and decodes the engine\'s stored codes', () => {
    const rows = grantRows(bundle.security.grants, RESOURCES, 'ORDERS');
    expect(rows.map((r) => [r.grantee, r.privilege, r.column, r.grantOption, r.granteeKind])).toEqual([
      ['ALICE', 'SELECT', '', true, 'USER'],
      ['ALICE', 'UPDATE', 'NOTE', false, 'USER'],
      ['AUDITOR', 'SELECT', '', false, 'ROLE'],
    ]);
  });

  it('offers grants only for engines with a complete descriptor and grantable kinds', () => {
    expect(objectGrantsOffered(bundle, 'table')).toBe(true);
    expect(objectGrantsOffered(bundle, 'trigger')).toBe(false);
    expect(objectGrantsOffered(loadEngineBundle('postgresql'), 'table')).toBe(false);
    expect(objectGrantsOffered(loadEngineBundle('mysql'), 'table')).toBe(true);
    expect(objectGrantsOffered(loadEngineBundle('mysql'), 'server')).toBe(false);
    expect(objectGrantsOffered(loadEngineBundle('sqlite'), 'table')).toBe(false);
  });

  it('spells the object type the way the operation does', () => {
    const op = bundle.kinds.privilege.operations.find((o) => o.operation_id === 'grant');
    expect(objectTypeValue(op, 'table')).toBe('TABLE');
    expect(objectTypeValue(op, 'procedure')).toBe('PROCEDURE');
    expect(objectTypeValue(op, 'warlock')).toBeNull();
  });
});

describe('DescriptorObjectGrants', () => {
  beforeEach(() => { resetDescriptorClient(); mockMatrix.mockClear(); });

  it('lists the object\'s grants with column, grant option and grantor', async () => {
    const {api} = makeApi();
    mount({api});
    const table = await screen.findByRole('table', {name: 'Granted privileges'});
    const rows = Array.from(table.querySelectorAll('tbody tr')).map((tr) =>
      Array.from(tr.querySelectorAll('td')).slice(0, 5).map((td) => td.textContent));
    expect(rows).toEqual([['ALICE', 'SELECT', '', 'Yes', 'SYSDBA'], ['ALICE', 'UPDATE', 'NOTE', 'No', 'SYSDBA'],
      ['AUDITOR', 'SELECT', '', 'No', 'SYSDBA']]);
  });

  it('revokes one grant with the object and grantee fixed, from the declared operation', async () => {
    const {api, posts} = makeApi();
    mount({api, databaseTargetId: 'db-1'});
    fireEvent.click(await screen.findByRole('button', {name: 'Revoke SELECT from ALICE'}));
    fireEvent.change(await screen.findByLabelText(/Confirm/i), {target: {value: 'ALICE'}});
    fireEvent.click(await screen.findByRole('button', {name: 'Preview'}));
    await waitFor(() => expect(posts.some((p) => p.action === 'visual_admin_plan')).toBe(true));
    const request = posts.find((p) => p.action === 'visual_admin_plan').request;
    expect(request).toMatchObject({resource_kind: 'privilege', operation_id: 'revoke', database_target_id: 'db-1'});
    expect(request.draft).toMatchObject({privilege_scope: 'object', object_type: 'TABLE', object_name: 'ORDERS',
      principal_kind: 'USER', principal: 'ALICE', privileges: ['SELECT'], confirmation: 'ALICE'});
    expect(request.draft).not.toHaveProperty('ddl_class');
  });

  it('does not offer a one-click revoke for a column grant', async () => {
    const {api} = makeApi();
    mount({api});
    await screen.findByRole('table', {name: 'Granted privileges'});
    expect(screen.queryByRole('button', {name: 'Revoke UPDATE from ALICE'})).not.toBeInTheDocument();
  });

  it('grants through the declared operation with the object fixed', async () => {
    const {api} = makeApi();
    mount({api});
    fireEvent.click(await screen.findByRole('button', {name: 'Grant privileges'}));
    expect(await screen.findByLabelText(/Grantee name/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/Exact object name/)).not.toBeInTheDocument();
  });

  it('says so when there are no grants, and reports a provider failure', async () => {
    const empty = makeApi('firebird', []);
    mount({api: empty.api});
    expect(await screen.findByText('No grants on ORDERS.')).toBeInTheDocument();
    resetDescriptorClient();
    const failing = makeApi('firebird', [], {fail: true});
    mount({api: failing.api});
    expect(await screen.findByRole('alert')).toHaveTextContent('permission denied reading grants');
  });
});

describe('ObjectGrantsSurface', () => {
  const node = {_type: 'cde_resource', cde_engine_id: 'firebird', cde_workspace_url: '/ws/1', cde_resource_kind: 'table',
    cde_database_target_id: 'db-1', label: 'ORDERS'};
  beforeEach(() => { resetDescriptorClient(); mockMatrix.mockClear(); });

  it('reads where and what the object is from the tree node', () => {
    expect(objectContext(node, {display_name: 'ORDERS'})).toMatchObject({
      engine: 'firebird', endpointUrl: '/ws/1', databaseTargetId: 'db-1', objectKind: 'table', objectName: 'ORDERS'});
  });

  it('uses the descriptor-driven view for a complete engine and kind', async () => {
    const {api} = makeApi();
    render(<Theme><ObjectGrantsSurface api={api} boundNodeData={node} resource={{display_name: 'ORDERS'}} /></Theme>);
    expect(await screen.findByRole('table', {name: 'Granted privileges'})).toBeInTheDocument();
    expect(screen.queryByTestId('legacy-matrix')).not.toBeInTheDocument();
  });

  it('keeps a draft engine on the previous permissions matrix', async () => {
    const {api} = makeApi('postgresql');
    render(<Theme><ObjectGrantsSurface api={api} boundNodeData={{...node, cde_engine_id: 'postgresql'}} /></Theme>);
    expect(await screen.findByTestId('legacy-matrix')).toBeInTheDocument();
  });

  it('keeps the previous matrix when the node does not say where the endpoint is', () => {
    render(<Theme><ObjectGrantsSurface boundNodeData={{...node, cde_workspace_url: undefined}} /></Theme>);
    expect(screen.getByTestId('legacy-matrix')).toBeInTheDocument();
  });
});

describe('grantRows with a composite object path and stored privilege names', () => {
  const grants = {grant_kind: 'privilege', listing: {object_fields: ['database', 'table_name'], grantee_field: 'grantee',
    privilege_field: 'privilege', column_field: 'column_name', grant_option_field: 'is_grantable', grant_option_equals: 'YES'}};
  const grant = (native) => ({resource_kind: 'privilege', native});
  it('matches on the last path field and keeps privilege names as stored', () => {
    const rows = grantRows(grants, [
      grant({grantee: '\'app\'@\'%\'', privilege: 'SELECT', database: 'd', table_name: 't', is_grantable: 'YES'}),
      grant({grantee: '\'app\'@\'%\'', privilege: 'DROP', database: 'd', table_name: 'other'}),
    ], 't');
    expect(rows).toEqual([expect.objectContaining({grantee: '\'app\'@\'%\'', privilege: 'SELECT', grantOption: true, granteeKind: null})]);
  });
});


describe('MySQL-shaped grants: scope-keyed rows, account strings and the declared dialog', () => {
  const mysql = () => loadEngineBundle('mysql').security.grants;
  const grant = (native) => ({resource_kind: 'privilege', native: {grantee: '\'app\'@\'%\'', is_grantable: 'NO', ...native}});
  const RESOURCES = [
    grant({scope: 'table', database: 'd', table_name: 't', privilege: 'SELECT', is_grantable: 'YES'}),
    grant({scope: 'column', database: 'd', table_name: 't', column_name: 'a', privilege: 'UPDATE'}),
    grant({scope: 'table', database: 'other', table_name: 't', privilege: 'DROP'}),
    grant({scope: 'database', database: 'd', privilege: 'SELECT'}),
    grant({scope: 'routine', database: 'd', routine_name: 'p', routine_type: 'PROCEDURE', privilege: 'EXECUTE'}),
    grant({scope: 'routine', database: 'd', routine_name: 'p', routine_type: 'FUNCTION', privilege: 'ALTER ROUTINE'}),
    grant({scope: 'global', privilege: 'PROCESS'}),
    grant({scope: 'table', database: 'd', table_name: 't', privilege: 'USAGE', grantee: '\'x\'@\'h\'', is_grantable: 'YES'}),
  ];

  it('finds a table\'s table and column grants only in its own database, keeping USAGE', () => {
    const rows = grantRows(mysql(), RESOURCES, 't', ['d', 't'], 'table');
    expect(rows.map((r) => `${r.grantee}:${r.privilege}:${r.column}:${r.grantOption}`)).toEqual([
      '\'app\'@\'%\':SELECT::true', '\'app\'@\'%\':UPDATE:a:false', '\'x\'@\'h\':USAGE::true']);
  });

  it('keeps database, routine and routine-type grants apart', () => {
    expect(grantRows(mysql(), RESOURCES, 'd', ['d'], 'database').map((r) => r.privilege)).toEqual(['SELECT']);
    expect(grantRows(mysql(), RESOURCES, 'p', ['d', 'p'], 'procedure').map((r) => r.privilege)).toEqual(['EXECUTE']);
    expect(grantRows(mysql(), RESOURCES, 'p', ['d', 'p'], 'function').map((r) => r.privilege)).toEqual(['ALTER ROUTINE']);
  });

  it('splits an account string, with quotes and a doubled quote', () => {
    expect(parseAccount('\'app\'@\'10.0.%\'')).toEqual({user: 'app', host: '10.0.%'});
    expect(parseAccount('\'o\'\'brien\'@\'%\'')).toEqual({user: 'o\'brien', host: '%'});
    expect(parseAccount('`a`@`b`')).toEqual({user: 'a', host: 'b'});
    expect(parseAccount('plain')).toEqual({user: 'plain', host: ''});
  });

  it('fills the declared dialog fields for a table, a column row and a database', () => {
    const grants = mysql();
    const operation = loadEngineBundle('mysql').kinds.privilege.operations.find((op) => op.operation_id === 'revoke');
    const column = grantRows(grants, RESOURCES, 't', ['d', 't'], 'table').find((r) => r.column);
    expect(dialogValues(grants, operation, 'table', 't', ['d', 't'], column)).toEqual({
      object_type: 'TABLE', object: 't', database: 'd',
      grantees: [{user: 'app', host: '%'}], privileges: [{name: 'UPDATE', columns: ['a']}]});
    expect(dialogValues(grants, operation, 'database', 'd', ['d'])).toEqual({object_type: 'DATABASE', database: 'd'});
  });

  it('allows a one-click revoke of a column grant only where the engine\'s dialog takes columns', () => {
    const mysqlRow = {column: 'a', granteeKind: null};
    expect(canRevoke(mysql(), mysqlRow)).toBe(true);
    const firebird = loadEngineBundle('firebird').security.grants;
    expect(canRevoke(firebird, {column: 'N', granteeKind: 'USER'})).toBe(false);
    expect(canRevoke(firebird, {column: '', granteeKind: 'USER'})).toBe(true);
    expect(canRevoke(firebird, {column: '', granteeKind: null})).toBe(false);
  });

  it('lists everything an account holds, global grants included, by its spelled grantee', () => {
    const security = loadEngineBundle('mysql').security;
    const grantee = granteeSpelling(security, security.principals[0], {display_name: 'app@%', native: {user: 'app', host: '%'}});
    expect(grantee).toBe('\'app\'@\'%\'');
    const held = heldRows(security.grants, RESOURCES, grantee, 'user');
    expect(held.map((r) => `${r.scope}:${r.object}:${r.privilege}`)).toEqual([
      'column:d.t:UPDATE', 'database:d:SELECT', 'global::PROCESS', 'routine:d.p:ALTER ROUTINE', 'routine:d.p:EXECUTE',
      'table:d.t:SELECT', 'table:other.t:DROP']);
  });
});

describe('heldRows for a Firebird principal', () => {
  const grants = () => loadEngineBundle('firebird').security.grants;
  const row = (native) => ({resource_kind: 'privilege', native: {grantee: 'APP', user_type: 8, grant_option: 0, ...native}});
  it('lists object grants by their object name, skips membership rows, and keeps a user apart from a same-named role', () => {
    const resources = [
      row({privilege: 'S', object_name: 'T1'}),
      row({privilege: 'U', object_name: 'T1', field: 'N', grant_option: 1}),
      row({privilege: 'M', object_name: 'R_ONE'}),
      row({privilege: 'X', object_name: 'P1', user_type: 13}),
    ];
    const asUser = heldRows(grants(), resources, 'APP', 'user');
    expect(asUser.map((r) => `${r.object}:${r.privilege}:${r.column}:${r.grantOption}`)).toEqual(['T1:SELECT::false', 'T1:UPDATE:N:true']);
    expect(heldRows(grants(), resources, 'APP', 'role').map((r) => r.object)).toEqual(['P1']);
  });
});

describe('DescriptorObjectGrants for a tree node that knows only its id (MySQL)', () => {
  beforeEach(() => { resetDescriptorClient(); });
  const priv = (extra) => ({resource_kind: 'privilege', resource_id: `g:${JSON.stringify(extra)}`, display_name: 'g',
    native: {grantee: '\'ct_app\'@\'%\'', privilege: 'SELECT', is_grantable: 'NO', ...extra}});
  const ITEMS = [
    {resource_kind: 'table', resource_id: 'table:d:customers', display_name: 'customers', display_path: ['d', 'customers'], native: {}},
    priv({scope: 'table', database: 'd', table_name: 'customers', is_grantable: 'YES'}),
    priv({scope: 'column', database: 'd', table_name: 'customers', column_name: 'city', privilege: 'UPDATE'}),
    priv({scope: 'table', database: 'other', table_name: 'customers', privilege: 'DROP'}),
  ];
  const mountMysql = (api) => render(<Theme><DescriptorObjectGrants api={api} endpointUrl="/ws/1" engine="mysql"
    objectKind="table" objectName="customers" objectId="table:d:customers" databaseTargetId="db-1" /></Theme>);

  it('finds the object\'s path in the listing and shows only its own database\'s grants', async () => {
    const {api} = makeApi('mysql', ITEMS);
    mountMysql(api);
    const table = await screen.findByRole('table', {name: 'Granted privileges'});
    const rows = Array.from(table.querySelectorAll('tbody tr')).map((tr) => Array.from(tr.querySelectorAll('td')).map((td) => td.textContent).slice(0, 4));
    expect(rows).toEqual([['\'ct_app\'@\'%\'', 'SELECT', '', 'Yes'], ['\'ct_app\'@\'%\'', 'UPDATE', 'city', 'No']]);
    expect(screen.queryByText('DROP')).not.toBeInTheDocument();
  });

  it('opens the grant dialog with the object fixed, so its database and object are not asked for again', async () => {
    const {api} = makeApi('mysql', ITEMS);
    mountMysql(api);
    fireEvent.click(await screen.findByRole('button', {name: 'Grant privileges'}));
    expect((await screen.findAllByText(/Grantees/)).length).toBeGreaterThan(0);
    expect(screen.queryByRole('textbox', {name: /^Database/})).not.toBeInTheDocument();
    expect(screen.queryByRole('textbox', {name: /^Object/})).not.toBeInTheDocument();
  });

  it('still matches by the tail when no path can be found', () => {
    const rows = grantRows(loadEngineBundle('mysql').security.grants, ITEMS.slice(1), 'customers', undefined, 'table');
    expect(rows.map((r) => r.privilege).sort()).toEqual(['DROP', 'SELECT', 'UPDATE']);
  });
});


describe('PostgreSQL-shaped grants: rows carried on the object, defaults and columns', () => {
  beforeEach(() => { resetDescriptorClient(); });
  const acl = (grantee, privilege, extra = {}) => ({grantee, grantee_kind: grantee === 'PUBLIC' ? 'special' : 'role',
    grantor: 'owner', privilege, grant_option: false, ...extra});
  const orders = {resource_kind: 'table', resource_id: 'oid:1', display_name: 'orders', display_path: ['db', 'public', 'orders'],
    native: {privileges: [acl('app', 'SELECT', {grant_option: true}), acl('app', 'INSERT')], privileges_default: false}};
  const column = {resource_kind: 'column', resource_id: 'oid:1:1', display_name: 'a', display_path: ['db', 'public', 'orders', 'a'],
    native: {privileges: [acl('PUBLIC', 'SELECT')]}};
  const plainColumn = {resource_kind: 'column', resource_id: 'oid:1:2', display_name: 'b', display_path: ['db', 'public', 'orders', 'b'],
    native: {privileges: []}};
  const elsewhere = {resource_kind: 'table', resource_id: 'oid:2', display_name: 'orders', display_path: ['db', 'other', 'orders'],
    native: {privileges: [acl('mallory', 'DELETE')], privileges_default: false}};
  const fn = {resource_kind: 'function', resource_id: 'oid:3', display_name: 'f', display_path: ['db', 'public', 'f'],
    native: {privileges: [acl('(owner)', 'EXECUTE', {grant_option: true}), acl('PUBLIC', 'EXECUTE')], privileges_default: true}};
  const ALL = [orders, column, plainColumn, elsewhere, fn];
  const pg = () => loadEngineBundle('postgresql').security.grants;

  it('reads the object\'s own rows and its columns, and nothing from a same-named object in another schema', () => {
    const rows = grantRows(pg(), ALL, 'orders', ['db', 'public', 'orders'], 'table', 'oid:1');
    expect(rows.map((r) => `${r.grantee}:${r.privilege}:${r.column}:${r.grantOption}`)).toEqual([
      'app:INSERT::false', 'app:SELECT::true', 'PUBLIC:SELECT:a:false']);
    expect(rows.find((r) => r.grantee === 'PUBLIC').granteeKind).toBe('PUBLIC');
    expect(rows.find((r) => r.grantee === 'app').granteeKind).toBe('ROLE');
  });

  it('says when the rows are the default ACL, because none is stored', () => {
    expect(embeddedGrants(pg().listing, ALL, 'oid:3', 'function', 'f', ['db', 'public', 'f']).isDefault).toBe(true);
    expect(embeddedGrants(pg().listing, ALL, 'oid:1', 'table', 'orders', undefined).isDefault).toBe(false);
  });

  it('offers a table only the privileges the dialect grants on a table, keeping ALL', () => {
    const bundle = loadEngineBundle('postgresql');
    const operation = bundle.kinds.privilege.operations.find((op) => op.operation_id === 'grant');
    const optionsOf = (op) => op.fields.find((f) => f.field_id === 'privileges').columns.find((c) => c.field_id === 'privilege')
      .options.map((o) => o.value ?? o);
    expect(optionsOf(operation)).toContain('CONNECT');
    const table = optionsOf(narrowedOperation(bundle, operation, 'table'));
    expect(table).toEqual(expect.arrayContaining(['ALL', 'SELECT', 'MAINTAIN']));
    expect(table).not.toEqual(expect.arrayContaining(['CONNECT']));
    expect(optionsOf(narrowedOperation(bundle, operation, 'schema')).sort()).toEqual(['ALL', 'CREATE', 'USAGE']);
    expect(narrowedOperation(bundle, operation, 'no-such-kind')).toBe(operation);
  });

  it('offers a column list only on the kinds the engine grants columns on', () => {
    const bundle = loadEngineBundle('postgresql');
    const operation = bundle.kinds.privilege.operations.find((op) => op.operation_id === 'grant');
    const columnsOf = (op) => op.fields.find((f) => f.field_id === 'privileges').columns.map((c) => c.field_id);
    expect(columnsOf(narrowedOperation(bundle, operation, 'table'))).toContain('columns');
    expect(columnsOf(narrowedOperation(bundle, operation, 'view'))).toContain('columns');
    expect(columnsOf(narrowedOperation(bundle, operation, 'function'))).toEqual(['privilege']);
    expect(columnsOf(narrowedOperation(bundle, operation, 'schema'))).toEqual(['privilege']);
  });

  it('names an overloadable object by its argument types, from the listed object', () => {
    const operation = loadEngineBundle('postgresql').kinds.privilege.operations.find((op) => op.operation_id === 'grant');
    const path = ['db', 'service', 'priority_label'];
    expect(dialogValues(pg(), operation, 'function', 'priority_label', path, undefined, {argument_types: 'integer'}))
      .toEqual({object_type: 'FUNCTION', object: 'priority_label', schema: 'service', arguments: 'integer'});
    // A kind whose listing has no such field, or an empty argument list, is not given the field wrongly.
    expect(dialogValues(pg(), operation, 'table', 't', ['db', 'service', 't'], undefined, {})).not.toHaveProperty('arguments');
    expect(dialogValues(pg(), operation, 'function', 'f0', ['db', 'service', 'f0'], undefined, {argument_types: ''}).arguments).toBe('');
  });

  it('finds the object by kind and name when the node has no id', () => {
    const rows = grantRows(pg(), ALL, 'f', ['db', 'public', 'f'], 'function', undefined);
    expect(rows.map((r) => r.grantee)).toEqual(['(owner)', 'PUBLIC']);
  });

  it('fills the dialog per kind: a view is a TABLE, a schema has no schema qualifier, a column row carries its column', () => {
    const operation = loadEngineBundle('postgresql').kinds.privilege.operations.find((op) => op.operation_id === 'revoke');
    expect(dialogValues(pg(), operation, 'table', 'orders', ['db', 'public', 'orders'])).toEqual({
      object_type: 'TABLE', object: 'orders', schema: 'public'});
    expect(dialogValues(pg(), operation, 'view', 'v', ['db', 'public', 'v'])).toEqual({object_type: 'TABLE', object: 'v', schema: 'public'});
    expect(dialogValues(pg(), operation, 'schema', 'public', ['db', 'public'])).toEqual({object_type: 'SCHEMA', object: 'public'});
    const row = grantRows(pg(), ALL, 'orders', ['db', 'public', 'orders'], 'table', 'oid:1').find((r) => r.column === 'a');
    expect(dialogValues(pg(), operation, 'table', 'orders', ['db', 'public', 'orders'], row)).toEqual({
      object_type: 'TABLE', object: 'orders', schema: 'public',
      grantees: [{role: 'PUBLIC'}], privileges: [{privilege: 'SELECT', columns: ['a']}]});
  });

  it('offers a one-click revoke for every row, columns included, because the dialog takes a column list', () => {
    const rows = grantRows(pg(), ALL, 'orders', ['db', 'public', 'orders'], 'table', 'oid:1');
    expect(rows.every((row) => canRevoke(pg(), row))).toBe(true);
  });

  it('lists everything a role holds across objects and columns, never another role\'s', () => {
    const security = loadEngineBundle('postgresql').security;
    const held = heldRows(security.grants, ALL, 'app', 'role');
    expect(held.map((r) => `${r.scope}:${r.object}:${r.privilege}`)).toEqual(['table:public.orders:INSERT', 'table:public.orders:SELECT']);
    expect(heldRows(security.grants, ALL, 'PUBLIC').map((r) => `${r.scope}:${r.object}`)).toEqual(
      ['function:public.f', 'column:public.orders.a']);
  });

  it('renders the default-privileges notice and the rows when the descriptor is complete', async () => {
    const bundle = loadEngineBundle('postgresql');
    bundle.security.grants.status = 'complete';
    const api = {get: jest.fn(async () => ({data: {success: 1, data: bundle}})),
      post: jest.fn(async () => ({data: {success: 1, data: {items: ALL, next_cursor: null, generation: 'g'}}}))};
    render(<Theme><DescriptorObjectGrants api={api} endpointUrl="/ws/1" engine="postgresql" objectKind="function"
      objectName="f" objectId="oid:3" /></Theme>);
    expect(await screen.findByText(/these are its default privileges/)).toBeInTheDocument();
    const table = await screen.findByRole('table', {name: 'Granted privileges'});
    expect(Array.from(table.querySelectorAll('tbody tr')).map((tr) => tr.querySelector('td').textContent)).toEqual(['(owner)', 'PUBLIC']);
  });
});
