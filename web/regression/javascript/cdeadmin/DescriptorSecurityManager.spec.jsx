import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import DescriptorSecurityManager, {principalLabel} from '../../../pgadmin/static/js/cdeadmin_ui/security/DescriptorSecurityManager';
import SecurityManagerSurface from '../../../pgadmin/static/js/cdeadmin_ui/security/SecurityManagerSurface';
import {resetDescriptorClient} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {loadEngineBundle} from '../families/familyFixtures';

const mockEditor = jest.fn();
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/objects/ProviderObjectEditorHost', () => ({
  __esModule: true,
  ...jest.requireActual('../../../pgadmin/static/js/cdeadmin_ui/objects/ProviderObjectEditorHost'),
  default: (props) => { mockEditor(props); return <div data-testid="editor">{`${props.mode}:${props.resourceKind}:${props.resourceId || ''}`}</div>; },
}));
const mockLegacy = jest.fn();
jest.mock('../../../pgadmin/static/js/cdeadmin_ui/security/PrincipalSecurityManager', () => ({
  __esModule: true,
  default: (props) => { mockLegacy(props); return <div data-testid="legacy-manager" />; },
}));

const user = (name, extra = {}) => ({resource_kind: 'user', resource_id: `user:${name}`, display_name: name, native: {...extra}});
const role = (name, extra = {}) => ({resource_kind: 'role', resource_id: `role:${name}`, display_name: name, native: {...extra}});

function makeApi(engine, items, {failList = false} = {}) {
  const posts = [];
  const api = {
    get: jest.fn(async () => ({data: {success: 1, data: loadEngineBundle(engine)}})),
    post: jest.fn(async (_url, payload) => {
      posts.push(payload);
      if(payload.action === 'resource_page') {
        if(failList) throw new Error('The account may not list principals');
        return {data: {success: 1, data: {items, next_cursor: null, generation: 'g'}}};
      }
      if(payload.action === 'visual_admin_validate') return {data: {success: 1, data: {valid: true, errors: []}}};
      if(payload.action === 'visual_admin_plan') {
        return {data: {success: 1, data: {plan_id: 'p', plan_digest: 'd', state: 'ready', execution_available: true,
          command_preview: {statements: [{source: 'GRANT "R1" TO USER "X"'}]}}}};
      }
      return {data: {success: 1, data: {}}};
    }),
  };
  return {api, posts};
}

const mount = (props) => render(<Theme><DescriptorSecurityManager endpointUrl="/ws/1" {...props} /></Theme>);

describe('DescriptorSecurityManager', () => {
  beforeEach(() => { resetDescriptorClient(); mockEditor.mockClear(); mockLegacy.mockClear(); });

  it('lists only the principals the descriptor declares for the server scope', async () => {
    // The endpoint returns both kinds; Firebird users are server-wide and roles are per database.
    const {api} = makeApi('firebird', [user('ALICE'), user('BOB'), role('AUDITOR')]);
    mount({api, engine: 'firebird', scope: 'server'});
    expect(await screen.findByRole('button', {name: 'ALICE'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'BOB'})).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'AUDITOR'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'New user'})).toBeInTheDocument();
    // A single principal kind needs no kind switcher.
    expect(screen.queryByRole('group', {name: 'Principal kind'})).not.toBeInTheDocument();
  });

  it('lists roles, not users, at database scope and names them from the descriptor', async () => {
    const {api, posts} = makeApi('firebird', [user('ALICE'), role('AUDITOR')]);
    mount({api, engine: 'firebird', scope: 'database', databaseTargetId: 'db-1'});
    expect(await screen.findByRole('button', {name: 'AUDITOR'})).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'ALICE'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'New role'})).toBeInTheDocument();
    // The list request is scoped to the database, as the provider requires.
    expect(posts.find((p) => p.action === 'resource_page').request.database_target_id).toBe('db-1');
  });

  it('filters the roster', async () => {
    const {api} = makeApi('firebird', [user('ALICE'), user('BOB')]);
    mount({api, engine: 'firebird', scope: 'server'});
    await screen.findByRole('button', {name: 'ALICE'});
    fireEvent.change(screen.getByLabelText('Filter'), {target: {value: 'bo'}});
    expect(screen.queryByRole('button', {name: 'ALICE'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'BOB'})).toBeInTheDocument();
  });

  it('opens a selected principal in the role-family editor, and a new one in create mode with its variant', async () => {
    const {api} = makeApi('firebird', [role('AUDITOR')]);
    mount({api, engine: 'firebird', scope: 'database', databaseTargetId: 'db-1'});
    fireEvent.click(await screen.findByRole('button', {name: 'AUDITOR'}));
    expect((await screen.findByTestId('editor')).textContent).toBe('alter:role:role:AUDITOR');
    fireEvent.click(screen.getByRole('button', {name: 'New role'}));
    await waitFor(() => expect(screen.getByTestId('editor').textContent).toBe('create:role:'));
    expect(mockEditor.mock.calls.at(-1)[0].initialRecord).toEqual({variant: 'role'});
  });

  it('offers the engine\'s declared membership operations and runs one against the selected role', async () => {
    const {api, posts} = makeApi('firebird', [role('AUDITOR')]);
    mount({api, engine: 'firebird', scope: 'database', databaseTargetId: 'db-1'});
    fireEvent.click(await screen.findByRole('button', {name: 'AUDITOR'}));
    expect(await screen.findByRole('button', {name: 'Revoke role membership'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Grant role membership'}));
    fireEvent.change(await screen.findByRole('textbox', {name: /Member/}), {target: {value: 'X'}});
    fireEvent.click(await screen.findByRole('button', {name: 'Preview'}));
    await waitFor(() => expect(posts.some((p) => p.action === 'visual_admin_plan')).toBe(true));
    const planned = posts.find((p) => p.action === 'visual_admin_plan').request;
    expect(planned).toMatchObject({resource_kind: 'role', operation_id: 'grant', database_target_id: 'db-1'});
    expect(planned.target_resource.display_name).toBe('AUDITOR');
    expect(planned.draft).toMatchObject({member: 'X', member_kind: 'USER'});
  });

  it('shows the memberships the descriptor says the resource carries', async () => {
    const memberships = [{grantee: 'ALICE', default_role: true, grant_option: 2, grantor: 'SYSDBA'},
      {grantee: 'BOB', default_role: false, grant_option: 0, grantor: 'SYSDBA'}];
    const {api} = makeApi('firebird', [role('AUDITOR', {memberships})]);
    mount({api, engine: 'firebird', scope: 'database', databaseTargetId: 'db-1'});
    fireEvent.click(await screen.findByRole('button', {name: 'AUDITOR'}));
    const table = await screen.findByRole('region', {name: 'Memberships'});
    const rows = Array.from(table.querySelectorAll('tbody tr')).map((tr) =>
      Array.from(tr.querySelectorAll('td')).map((td) => td.textContent));
    expect(rows).toEqual([['ALICE', 'Yes', 'Yes', 'SYSDBA'], ['BOB', 'No', 'No', 'SYSDBA']]);
  });

  it('explains an engine with no principals instead of offering an empty manager', async () => {
    const {api} = makeApi('sqlite', []);
    mount({api, engine: 'sqlite', scope: 'server'});
    expect(await screen.findByText(/no users, roles or GRANT\/REVOKE/)).toBeInTheDocument();
    expect(screen.queryByRole('button', {name: /^New /})).not.toBeInTheDocument();
  });

  it('reports a provider failure instead of an empty list', async () => {
    const {api} = makeApi('firebird', [], {failList: true});
    mount({api, engine: 'firebird', scope: 'server'});
    expect(await screen.findByRole('alert')).toHaveTextContent('may not list principals');
  });

  it('labels a principal by the descriptor identity fields', () => {
    const mysql = loadEngineBundle('mysql').security.principals[0];
    expect(principalLabel(mysql, user('app', {name: 'app', host: '10.0.%'}))).toBe('app@10.0.%');
    const firebird = loadEngineBundle('firebird').security.principals[0];
    expect(principalLabel(firebird, user('ALICE', {name: 'ALICE'}))).toBe('ALICE');
  });
});

describe('SecurityManagerSurface', () => {
  const legacyProps = {engine: 'mysql', sid: 3, scope: 'server', instanceId: 'x'};
  beforeEach(() => { resetDescriptorClient(); mockEditor.mockClear(); mockLegacy.mockClear(); });

  it('serves an engine whose security descriptor is complete with the descriptor-driven manager', async () => {
    const {api} = makeApi('firebird', [user('ALICE')]);
    render(<Theme><SecurityManagerSurface api={api} endpointUrl="/ws/1" engine="firebird" scope="server" sid={3} /></Theme>);
    expect(await screen.findByRole('button', {name: 'ALICE'})).toBeInTheDocument();
    expect(screen.queryByTestId('legacy-manager')).not.toBeInTheDocument();
  });

  it('keeps an engine whose descriptor is still a draft on the previous manager', async () => {
    const {api} = makeApi('mysql', []);
    render(<Theme><SecurityManagerSurface api={api} endpointUrl="/ws/1" {...legacyProps} /></Theme>);
    expect(await screen.findByTestId('legacy-manager')).toBeInTheDocument();
    expect(mockLegacy.mock.calls[0][0]).toMatchObject({sid: 3, engine: 'mysql'});
  });

  it('falls back to the previous manager when no endpoint is known', () => {
    render(<Theme><SecurityManagerSurface {...legacyProps} /></Theme>);
    expect(screen.getByTestId('legacy-manager')).toBeInTheDocument();
  });

  it('falls back when the descriptor bundle cannot be loaded', async () => {
    const api = {get: jest.fn(async () => { throw new Error('offline'); }), post: jest.fn()};
    render(<Theme><SecurityManagerSurface api={api} endpointUrl="/ws/1" {...legacyProps} /></Theme>);
    expect(await screen.findByTestId('legacy-manager')).toBeInTheDocument();
  });
});
