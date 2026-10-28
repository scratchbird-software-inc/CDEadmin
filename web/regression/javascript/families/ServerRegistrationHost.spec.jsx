import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import Theme from 'sources/Theme';
import {
  ServerRegistrationHost, recordFromBackend,
} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {registrationPayload} from '../../../pgadmin/static/js/cdeadmin_ui/objects/ServerRegistrationHost';
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
});
