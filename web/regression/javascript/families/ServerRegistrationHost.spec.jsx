import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import {
  ServerRegistrationHost, recordFromBackend,
} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {lifecycleProfileRequest, registrationPayload} from '../../../pgadmin/static/js/cdeadmin_ui/objects/ServerRegistrationHost';
import {loadEngineBundle} from './familyFixtures';

beforeEach(() => {
  window.innerHeight = 1200;
});

function fakeApi(bundle, properties={}, onWrite=() => ({success: 1, node: {_id: 7, _type: 'server'}})) {
  const api = jest.fn(async (request) => ({data: onWrite(request)}));
  api.writes = api.mock.calls;
  api.get = jest.fn(async (url) => ({data: url.startsWith('/cdeadmin/api/ui/descriptors') ? {success: 1, data: bundle} : properties}));
  return api;
}

describe('recordFromBackend', () => {
  it('re-keys backend ids to field ids and decodes JSON-text values', () => {
    const form = loadEngineBundle('sqlite').forms.server;
    const withJson = form.tabs.flatMap((tab) => tab.fields).find((field) => field.control === 'grid');
    const record = recordFromBackend(form, {db: '/tmp/a.db', name: 'S',
      ...(withJson ? {[withJson.backend_field_id]: '[{"name":"x","database":"/tmp/x.db"}]'} : {})});
    expect(record).toMatchObject({database: '/tmp/a.db', name: 'S'});
    if(withJson) expect(record[withJson.field_id]).toEqual([{name: 'x', database: '/tmp/x.db'}]);
  });
});

describe('registrationPayload', () => {
  it('moves the profile select into cde_profile_id and adds the envelope keys', () => {
    expect(registrationPayload({}, {name: 'N', profile: 'firebird-embedded'}, {profileId: 'firebird-native', intent: 'endpoint', verifyNow: false}))
      .toEqual({name: 'N', cde_profile_id: 'firebird-embedded', cde_registration_intent: 'endpoint', cde_verify_now: false});
  });
});

describe('ServerRegistrationHost', () => {
  it('hides the PostgreSQL registration envelope fields the host supplies (browser pass 2026-11-12)', async () => {
    const bundle = loadEngineBundle('postgresql');
    const api = fakeApi(bundle);
    render(<Theme><ServerRegistrationHost api={api} engine="postgresql" mode="create" urlFor={(isNew) => `/browser/server/obj/1/${isNew ? '' : '7'}`}
      initialData={{name: 'PostgreSQL on localhost', cde_profile_id: 'postgresql-native', cde_registration_intent: 'endpoint'}}
      profileId="postgresql-native" displayName="Register PostgreSQL" onClose={() => {}} onSaved={() => {}} /></Theme>);
    await screen.findByRole('dialog');
    expect(screen.getByLabelText(/^Name/)).toBeTruthy();
    for(const label of [/^Registration action/, /^Engine \/ interface profile/, /^Server group/, /Verify endpoint now/]) {
      expect(screen.queryByLabelText(label)).toBeNull();
    }
  });

  it('registers a SQLite endpoint through the servers API without a plan step', async () => {
    const bundle = loadEngineBundle('sqlite');
    const api = fakeApi(bundle);
    const onSaved = jest.fn();
    render(<Theme><ServerRegistrationHost api={api} engine="sqlite" mode="create" urlFor={(isNew) => `/browser/server/obj/1/${isNew ? '' : '7'}`}
      initialData={{name: 'SQLite local', cde_profile_id: 'sqlite-native'}} profileId="sqlite-native" displayName="Register SQLite"
      onClose={() => {}} onSaved={onSaved} /></Theme>);
    await screen.findByRole('dialog');
    expect(screen.queryByRole('button', {name: /Preview SQL/})).toBeNull();
    fireEvent.change(screen.getByLabelText(/^Database file/), {target: {value: '/tmp/a.db'}});
    fireEvent.click(screen.getByRole('button', {name: 'Register'}));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [request] = api.mock.calls.at(-1);
    expect(request).toMatchObject({method: 'POST', url: '/browser/server/obj/1/',
      data: {name: 'SQLite local', db: '/tmp/a.db', cde_profile_id: 'sqlite-native', cde_registration_intent: 'endpoint'}});
  });

  it('edits with a PUT carrying only changed fields', async () => {
    const bundle = loadEngineBundle('sqlite');
    const api = fakeApi(bundle, {name: 'Old', db: '/tmp/a.db', cde_profile_id: 'sqlite-native'});
    const onSaved = jest.fn();
    render(<Theme><ServerRegistrationHost api={api} engine="sqlite" mode="alter" urlFor={(isNew) => `/browser/server/obj/1/${isNew ? '' : '7'}`}
      profileId="sqlite-native" onClose={() => {}} onSaved={onSaved} /></Theme>);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByLabelText(/^Connection profile name/), {target: {value: 'New'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const [request] = api.mock.calls.at(-1);
    expect(request.method).toBe('PUT');
    expect(request.url).toBe('/browser/server/obj/1/7');
    expect(request.data).toMatchObject({name: 'New'});
    expect(request.data).not.toHaveProperty('db');
  });

  it('registers and edits Firebird server settings with custom port 53050 (inline without onClose)', async () => {
    const bundle = loadEngineBundle('firebird');
    const api = fakeApi(bundle, {
      name: 'Firebird on localhost',
      host: 'localhost',
      port: 3050,
      username: 'SYSDBA',
      cde_profile_id: 'firebird-native',
    });
    const onSaved = jest.fn();
    const {unmount} = render(
      <Theme>
        <ServerRegistrationHost
          api={api}
          engine="firebird"
          mode="create"
          urlFor={(isNew) => `/browser/server/obj/1/${isNew ? '' : '11'}`}
          initialData={{
            name: 'Firebird on localhost',
            host: 'localhost',
            port: 3050,
            cde_profile_id: 'firebird-native',
          }}
          profileId="firebird-native"
          displayName="Register Firebird server / instance"
          onSaved={onSaved}
        />
      </Theme>
    );
    await screen.findByRole('dialog');
    expect(screen.queryByRole('button', {name: 'Cancel'})).toBeNull();
    fireEvent.change(screen.getByLabelText(/^Server port/), {target: {value: '53050'}});
    fireEvent.click(screen.getByRole('button', {name: 'Register'}));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(api.mock.calls.at(-1)[0]).toMatchObject({
      method: 'POST',
      url: '/browser/server/obj/1/',
      data: expect.objectContaining({
        host: 'localhost',
        port: 53050,
        cde_profile_id: 'firebird-native',
      }),
    });
    unmount();

    render(
      <Theme>
        <ServerRegistrationHost
          api={api}
          engine="firebird"
          mode="alter"
          urlFor={(isNew) => `/browser/server/obj/1/${isNew ? '' : '11'}`}
          profileId="firebird-native"
          displayName="Server Settings — Firebird on localhost"
          onSaved={onSaved}
        />
      </Theme>
    );
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByLabelText(/^Server port/), {target: {value: '53050'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(2));
    expect(api.mock.calls.at(-1)[0]).toMatchObject({
      method: 'PUT',
      url: '/browser/server/obj/1/11',
      data: {port: 53050},
    });
  });

  it('supports Apply Changes and auto-verification when editing localhost port without or with credentials', async () => {
    const bundle = loadEngineBundle('firebird');
    const api = fakeApi(bundle, {});
    const onSaved = jest.fn();
    render(
      <Theme>
        <ServerRegistrationHost
          api={api}
          engine="firebird"
          mode="create"
          urlFor={() => '/browser/server/obj/1/'}
          initialData={{name: 'Firebird 5.0 on localhost', host: 'localhost', port: 3050, connect_now: false}}
          profileId="firebird-native"
          verifyNow="auto"
          applyLabel="Apply Changes"
          displayName="Server Properties — Firebird 5.0 on localhost"
          onSaved={onSaved}
        />
      </Theme>
    );
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByLabelText(/^Server port/), {target: {value: '53050'}});
    fireEvent.click(screen.getByRole('button', {name: 'Apply Changes'}));
    await waitFor(() => expect(onSaved).toHaveBeenCalledTimes(1));
    expect(api.mock.calls.at(-1)[0]).toMatchObject({
      method: 'POST',
      url: '/browser/server/obj/1/',
      data: expect.objectContaining({
        port: 53050,
        cde_verify_now: false,
      }),
    });
  });
});

describe('lifecycleProfileRequest (MySQL edits through the provider lifecycle, browser pass 2026-11-12)', () => {
  const owned = ['name', 'host', 'port', 'username', 'connection_timeout', 'password'];
  const record = {name: 'm', host: 'h', port: 3306, username: 'u', connection_timeout: 10, password: '', comment: 'c'};

  it('sends the complete owned values with the change merged in, and keeps the stored secret', () => {
    expect(lifecycleProfileRequest(owned, record, {connection_timeout: 11}))
      .toEqual({name: 'm', host: 'h', port: 3306, username: 'u', connection_timeout: 11});
  });

  it('sends a secret only when it was changed', () => {
    expect(lifecycleProfileRequest(owned, record, {password: 'new'}).password).toBe('new');
  });

  it('refuses a change the provider edit form does not own instead of dropping it', () => {
    expect(() => lifecycleProfileRequest(owned, record, {comment: 'x'})).toThrow(/does not edit: comment/);
  });
});

describe('ServerRegistrationHost refusals (browser pass 2026-11-12)', () => {
  it('shows the servers API reason instead of the HTTP status', async () => {
    const bundle = loadEngineBundle('sqlite');
    const api = jest.fn(async () => {
      const error = new Error('Request failed with status code 401');
      error.response = {status: 401, data: {success: 0, errormsg: 'A password is required to verify this endpoint.'}};
      throw error;
    });
    api.get = jest.fn(async () => ({data: {success: 1, data: bundle}}));
    render(<Theme><ServerRegistrationHost api={api} engine="sqlite" mode="create" urlFor={() => '/browser/server/obj/1/'}
      initialData={{name: 'S', cde_profile_id: 'sqlite-native'}} profileId="sqlite-native" displayName="Register SQLite"
      onClose={() => {}} onSaved={() => {}} /></Theme>);
    await screen.findByRole('dialog');
    fireEvent.change(screen.getByLabelText(/^Database file/), {target: {value: '/tmp/a.db'}});
    fireEvent.click(screen.getByRole('button', {name: 'Register'}));
    expect(await screen.findByText(/A password is required to verify this endpoint/)).toBeTruthy();
    expect(screen.queryByText(/status code 401/)).toBeNull();
  });
});

describe('MySQL edit through the lifecycle route (browser pass 2026-11-12)', () => {
  it('posts the provider edit form values with a route change keyed by field id', async () => {
    const bundle = loadEngineBundle('mysql');
    const editFields = ['name', 'host', 'port', 'username', 'compress'].map((field_id) => ({field_id}));
    const api = jest.fn(async ({data}) => ({data: data.action === 'endpoint_profile_read'
      ? {success: 1, data: {endpoint_registration: {forms: {forms: {edit: {fields: editFields}}}}}}
      : {success: 1, data: {}}}));
    api.get = jest.fn(async (url) => ({data: url.startsWith('/cdeadmin/api/ui/descriptors') ? {success: 1, data: bundle}
      : {name: 'm', host: 'h', port: 3306, username: 'u', cde_route_compress: false, cde_profile_id: 'mysql-native'}}));
    const onSaved = jest.fn();
    render(<Theme><ServerRegistrationHost api={api} engine="mysql" mode="alter" urlFor={() => '/browser/server/obj/1/7'}
      lifecycleUrl="/browser/server/cde_workspace/1/7" profileId="mysql-native" displayName="Edit MySQL"
      onClose={() => {}} onSaved={onSaved} /></Theme>);
    await screen.findByRole('dialog');
    fireEvent.click(screen.getByLabelText(/^Protocol compression/));
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(onSaved).toHaveBeenCalled());
    const update = api.mock.calls.map(([request]) => request).find((request) => request.data?.action === 'endpoint_profile_update');
    expect(update.url).toBe('/browser/server/cde_workspace/1/7');
    expect(update.data.request).toEqual({name: 'm', host: 'h', port: 3306, username: 'u', compress: true});
  });
});
