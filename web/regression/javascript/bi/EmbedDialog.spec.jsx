/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Theme from 'sources/Theme';
import EmbedDialog from 'sources/cdeadmin_ui/modules/bi/EmbedDialog';
import {embedFixtures as fx} from './embedFixtures';

beforeEach(() => {
  window.innerHeight = 1200;
  Object.defineProperty(navigator, 'clipboard', {value: {writeText: jest.fn(async () => {})}, configurable: true});
  window.localStorage.clear();
});

function fakeClient(overrides = {}) {
  return {
    embedCatalog: jest.fn(async () => fx.catalog),
    listEmbeds: jest.fn(async () => fx.list.items),
    getEmbed: jest.fn(async () => fx.created.embed),
    createEmbed: jest.fn(async () => fx.created),
    updateEmbed: jest.fn(async () => fx.created.embed),
    enableEmbed: jest.fn(async () => fx.enabled),
    disableEmbed: jest.fn(async () => fx.disabledByManager),
    revokeEmbed: jest.fn(async () => fx.revoked),
    deleteEmbed: jest.fn(async () => ({deleted: true})),
    rotateEmbedKey: jest.fn(async () => fx.rotated),
    retireEmbedKey: jest.fn(async () => fx.retired),
    previewEmbed: jest.fn(async () => fx.preview),
    embedStats: jest.fn(async () => fx.stats),
    ...overrides,
  };
}

const open = async (client, props = {}) => {
  const onClose = jest.fn();
  render(<Theme><EmbedDialog client={client} resourceType="dashboard" resourceId="d-sales"
    resourceName="Sales board" parameters={fx.dashboardFilters.map((item) => ({
      id: item.id, name: item.name, type: item.type}))} onClose={onClose} {...props} /></Theme>);
  await screen.findByRole('dialog');
  await waitFor(() => expect(screen.queryByText('Loading...')).not.toBeInTheDocument());
  return {onClose};
};

const row = (name) => within(screen.getByRole('list', {name: 'Embeds'})).getByRole('listitem', {name});

async function choose(label, option) {
  fireEvent.mouseDown(screen.getByRole('combobox', {name: label}));
  fireEvent.click(await screen.findByRole('option', {name: option}));
}

const type = (label, value) => fireEvent.change(screen.getByLabelText(label), {target: {value}});

async function fillNewEmbed() {
  fireEvent.click(screen.getByRole('button', {name: 'New embed'}));
  await screen.findByRole('region', {name: 'New embed'});
  type('Name', 'Partner portal');
  await choose('Mode of Region', 'Locked (set by the token)');
  type('Add an origin', 'https://app.example.com');
  fireEvent.click(screen.getByRole('button', {name: 'Add origin'}));
}

describe('EmbedDialog list', () => {
  it('lists the embeds of the resource with their state and keys', async () => {
    const client = fakeClient();
    await open(client);
    expect(client.listEmbeds).toHaveBeenCalledWith('dashboard', 'd-sales');
    expect(within(row('Partner portal')).getByText('Enabled')).toBeInTheDocument();
    expect(within(row('Draft embed')).getByText('Disabled')).toBeInTheDocument();
    expect(within(row('Draft embed')).getByText('The embed is created but not enabled yet.')).toBeInTheDocument();
    expect(within(row('Old embed')).getByText('Revoked')).toBeInTheDocument();
    expect(within(row('Partner portal')).getByText(/keys: kid-4 \(current\)/)).toBeInTheDocument();
    expect(within(row('Partner portal')).getByText(/runs as you until/)).toBeInTheDocument();
  });

  it('explains who the embed runs as', async () => {
    await open(fakeClient());
    expect(screen.getByText(/runs with your own database access \(as the "embedding" principal\)/)).toBeInTheDocument();
    expect(screen.getByText(/never your identity/)).toBeInTheDocument();
  });

  it('shows another manager only what they may do', async () => {
    await open(fakeClient({listEmbeds: jest.fn(async () => fx.listForManager.items)}));
    const theirs = row('Partner portal');
    expect(within(theirs).getByText('Owned by someone else. You can disable or revoke it and see its view counts.'))
      .toBeInTheDocument();
    expect(within(theirs).queryByText(/keys:/)).not.toBeInTheDocument();
    for(const name of ['Edit', 'Rotate key', 'Preview', 'Code', 'Enable']) {
      expect(within(theirs).queryByRole('button', {name: `${name} Partner portal`})).not.toBeInTheDocument();
    }
    expect(within(theirs).getByRole('button', {name: 'Disable Partner portal'})).toBeInTheDocument();
    expect(within(theirs).getByRole('button', {name: 'Views of Partner portal'})).toBeInTheDocument();
  });

  it('says why an embed was disabled', async () => {
    await open(fakeClient({listEmbeds: jest.fn(async () => [fx.ownerLost])}));
    expect(within(row('Manager embed')).getByText(
      'The owner no longer manages this content, so the embed was disabled.')).toBeInTheDocument();
  });

  it('says so when the server has the feature off and offers no way to create', async () => {
    const client = fakeClient({embedCatalog: jest.fn(async () => ({...fx.catalog, available: false}))});
    await open(client);
    expect(screen.getByText(/Signed embedding is not enabled on this server/)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'New embed'})).toBeDisabled();
    expect(client.listEmbeds).not.toHaveBeenCalled();
  });

  it('does not offer to create without manage access', async () => {
    await open(fakeClient(), {access: 'edit'});
    expect(screen.getByRole('button', {name: 'New embed'})).toBeDisabled();
  });

  it('shows an empty state and a failed load', async () => {
    await open(fakeClient({listEmbeds: jest.fn(async () => [])}));
    expect(screen.getByText('No embeds yet.')).toBeInTheDocument();
  });

  it('reports a failed load', async () => {
    await open(fakeClient({listEmbeds: jest.fn(async () => { throw new Error('manage access is required'); })}));
    expect(screen.getByText('manage access is required')).toBeInTheDocument();
  });
});

describe('EmbedDialog create', () => {
  it('creates a disabled embed and shows the secret once', async () => {
    const client = fakeClient();
    await open(client);
    await fillNewEmbed();
    fireEvent.click(screen.getByRole('button', {name: 'Create embed'}));
    await screen.findByRole('group', {name: 'Signing secret'});
    expect(client.createEmbed).toHaveBeenCalledTimes(1);
    const definition = client.createEmbed.mock.calls[0][0];
    expect(definition).toMatchObject({
      name: 'Partner portal', resource: {type: 'dashboard', id: 'd-sales', revision: null},
      parameters: [{id: 'region', mode: 'locked'}], origins: ['https://app.example.com'],
      max_token_lifetime_seconds: 600, require_jti: false,
      display: {title: true, theme: 'auto', border: true, download: false}});
    expect(screen.getByText(/Key id \(put it in the token header as "kid"\): kid-1/)).toBeInTheDocument();
    expect(screen.getByText(/shown only once and cannot be recovered/)).toBeInTheDocument();
    expect(screen.queryByRole('region', {name: 'New embed'})).not.toBeInTheDocument();
    // the secret is a password field until revealed, and goes nowhere but the clipboard
    expect(screen.getByLabelText('Secret')).toHaveAttribute('type', 'password');
    fireEvent.click(screen.getByRole('button', {name: 'Copy secret'}));
    await screen.findByText('Copied.');
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('SECRET-1');
    expect(JSON.stringify({...window.localStorage})).not.toMatch(/SECRET/);
    expect(JSON.stringify({...window.sessionStorage})).not.toMatch(/SECRET/);
    fireEvent.click(screen.getByRole('button', {name: 'I have saved it'}));
    expect(screen.queryByRole('group', {name: 'Signing secret'})).not.toBeInTheDocument();
    expect(screen.queryByText(/SECRET-1/)).not.toBeInTheDocument();
  });

  it('says when copying is blocked instead of pretending', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      value: {writeText: jest.fn(async () => { throw new Error('denied'); })}, configurable: true});
    await open(fakeClient());
    await fillNewEmbed();
    fireEvent.click(screen.getByRole('button', {name: 'Create embed'}));
    await screen.findByRole('group', {name: 'Signing secret'});
    fireEvent.click(screen.getByRole('button', {name: 'Copy secret'}));
    await screen.findByText(/Copying was blocked/);
  });

  it('checks the form before sending anything', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(screen.getByRole('button', {name: 'New embed'}));
    await screen.findByRole('region', {name: 'New embed'});
    type('Name', '');
    type('Longest token lifetime (seconds)', '5');
    fireEvent.click(screen.getByRole('button', {name: 'Create embed'}));
    expect(await screen.findByText('Enter a name.')).toBeInTheDocument();
    expect(screen.getByText('Use a whole number of seconds from 30 to 3600.')).toBeInTheDocument();
    expect(screen.getByText('Fix the marked fields first.')).toBeInTheDocument();
    expect(client.createEmbed).not.toHaveBeenCalled();
  });

  it('refuses an origin the server would refuse, while typing', async () => {
    await open(fakeClient());
    fireEvent.click(screen.getByRole('button', {name: 'New embed'}));
    await screen.findByRole('region', {name: 'New embed'});
    type('Add an origin', 'https://*.example.com');
    expect(screen.getByText(/Use an exact origin/)).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Add origin'})).toBeDisabled();
  });

  it('warns that an embed without origins cannot be framed and that editable values are viewer-controlled', async () => {
    await open(fakeClient());
    fireEvent.click(screen.getByRole('button', {name: 'New embed'}));
    await screen.findByRole('region', {name: 'New embed'});
    expect(screen.getByText('No origin is allowed, so no site can show this embed in a frame.')).toBeInTheDocument();
    await choose('Mode of Region', 'Editable by the viewer');
    expect(screen.getByText('Viewers can change editable parameters to any allowed value.')).toBeInTheDocument();
  });

  it('declares claims and lifetime', async () => {
    const client = fakeClient();
    await open(client);
    await fillNewEmbed();
    fireEvent.click(screen.getByRole('button', {name: 'Add a claim'}));
    type('Claim 1', 'tenant_id');
    fireEvent.click(screen.getByRole('checkbox', {name: 'Required'}));
    type('Longest token lifetime (seconds)', '300');
    fireEvent.click(screen.getByRole('checkbox', {name: 'Tokens are one-time (each needs a unique id)'}));
    fireEvent.click(screen.getByRole('button', {name: 'Create embed'}));
    await screen.findByRole('group', {name: 'Signing secret'});
    expect(client.createEmbed.mock.calls[0][0]).toMatchObject({
      claims: [{name: 'tenant_id', required: true}], max_token_lifetime_seconds: 300, require_jti: true});
  });

  it('refuses a reserved claim name early', async () => {
    await open(fakeClient());
    await fillNewEmbed();
    fireEvent.click(screen.getByRole('button', {name: 'Add a claim'}));
    type('Claim 1', 'user_id');
    fireEvent.click(screen.getByRole('button', {name: 'Create embed'}));
    expect(await screen.findByText('"user_id" is reserved for the server.')).toBeInTheDocument();
  });

  it('shows the server\'s refusal and keeps the form', async () => {
    const client = fakeClient({createEmbed: jest.fn(async () => {
      throw new Error(fx.errors.badOrigin);
    })});
    await open(client);
    await fillNewEmbed();
    fireEvent.click(screen.getByRole('button', {name: 'Create embed'}));
    expect(await screen.findByText(fx.errors.badOrigin)).toBeInTheDocument();
    expect(screen.getByRole('region', {name: 'New embed'})).toBeInTheDocument();
    expect(screen.queryByRole('group', {name: 'Signing secret'})).not.toBeInTheDocument();
  });

  it('keeps downloads off unless the server allows them', async () => {
    await open(fakeClient({embedCatalog: jest.fn(async () => ({...fx.catalog, downloads_allowed: false}))}));
    fireEvent.click(screen.getByRole('button', {name: 'New embed'}));
    await screen.findByRole('region', {name: 'New embed'});
    expect(screen.getByRole('checkbox', {name: 'Allow downloads'})).toBeDisabled();
    expect(screen.getByRole('checkbox', {name: 'Allow downloads'})).not.toBeChecked();
  });
});

describe('EmbedDialog edit and lifecycle', () => {
  it('edits with the stored revision', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Partner portal')).getByRole('button', {name: 'Edit Partner portal'}));
    await screen.findByRole('region', {name: 'Edit embed'});
    expect(screen.getByLabelText('Name')).toHaveValue('Partner portal');
    expect(screen.getByLabelText('Longest token lifetime (seconds)')).toHaveValue('900');
    type('Name', 'Partner portal 2');
    fireEvent.click(screen.getByRole('button', {name: 'Save changes'}));
    await screen.findByText('Saved.');
    expect(client.updateEmbed).toHaveBeenCalledWith('e-partner', 1, expect.objectContaining({name: 'Partner portal 2'}));
  });

  it('enables a created embed', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Draft embed')).getByRole('button', {name: 'Enable Draft embed'}));
    await waitFor(() => expect(client.enableEmbed).toHaveBeenCalledWith('e-draft'));
    expect(await screen.findByText(/runs with your database access until the authorization expires/i)).toBeInTheDocument();
  });

  it('disables with one click', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Partner portal')).getByRole('button', {name: 'Disable Partner portal'}));
    await waitFor(() => expect(client.disableEmbed).toHaveBeenCalledWith('e-partner'));
  });

  it('asks twice before revoking, which is permanent', async () => {
    const client = fakeClient();
    await open(client);
    const target = row('Partner portal');
    fireEvent.click(within(target).getByRole('button', {name: 'Revoke Partner portal'}));
    expect(client.revokeEmbed).not.toHaveBeenCalled();
    fireEvent.click(within(target).getByRole('button', {name: 'Confirm Revoke Partner portal'}));
    await waitFor(() => expect(client.revokeEmbed).toHaveBeenCalledWith('e-partner'));
  });

  it('asks twice before deleting and offers it only for an embed that is not running', async () => {
    const client = fakeClient();
    await open(client);
    expect(within(row('Partner portal')).queryByRole('button', {name: 'Delete Partner portal'})).not.toBeInTheDocument();
    const target = row('Draft embed');
    fireEvent.click(within(target).getByRole('button', {name: 'Delete Draft embed'}));
    expect(client.deleteEmbed).not.toHaveBeenCalled();
    fireEvent.click(within(target).getByRole('button', {name: 'Confirm Delete Draft embed'}));
    await waitFor(() => expect(client.deleteEmbed).toHaveBeenCalledWith('e-draft'));
  });

  it('rotates a key after confirmation and shows the new secret once', async () => {
    const client = fakeClient();
    await open(client);
    const target = row('Partner portal');
    fireEvent.click(within(target).getByRole('button', {name: 'Rotate key Partner portal'}));
    expect(client.rotateEmbedKey).not.toHaveBeenCalled();
    fireEvent.click(within(target).getByRole('button', {name: 'Confirm Rotate key Partner portal'}));
    await screen.findByRole('group', {name: 'Signing secret'});
    expect(client.rotateEmbedKey).toHaveBeenCalledWith('e-partner');
    expect(screen.getByText(/Key id \(put it in the token header as "kid"\): kid-4/)).toBeInTheDocument();
    expect(screen.getByText(/The old key keeps working until you retire it or rotate again/)).toBeInTheDocument();
  });

  it('retires the old key when two keys verify', async () => {
    const client = fakeClient({listEmbeds: jest.fn(async () => [fx.rotated.embed])});
    await open(client);
    fireEvent.click(screen.getByRole('button', {name: 'Retire old key of Partner portal'}));
    await waitFor(() => expect(client.retireEmbedKey).toHaveBeenCalledWith('e-partner'));
  });

  it('shows the server\'s refusal of an action', async () => {
    const client = fakeClient({enableEmbed: jest.fn(async () => { throw new Error('only the owner can authorize'); })});
    await open(client);
    fireEvent.click(within(row('Draft embed')).getByRole('button', {name: 'Enable Draft embed'}));
    expect(await screen.findByText('only the owner can authorize')).toBeInTheDocument();
  });
});

describe('EmbedDialog preview, code and views', () => {
  it('previews with a server-minted token in a locked-down frame', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Partner portal')).getByRole('button', {name: 'Preview Partner portal'}));
    await screen.findByRole('region', {name: 'Preview'});
    // the tenant claim is required, so the preview asks for it first
    fireEvent.click(screen.getByRole('button', {name: 'Load preview'}));
    expect(await screen.findByText('This claim is required.')).toBeInTheDocument();
    expect(client.previewEmbed).not.toHaveBeenCalled();
    type('Value of Region', 'east');
    type('Claim tenant_id', '7');
    fireEvent.click(screen.getByRole('button', {name: 'Load preview'}));
    const frame = await screen.findByTitle('Embed preview');
    expect(client.previewEmbed).toHaveBeenCalledWith('e-partner', {params: {region: 'east'}, claims: {tenant_id: 7}});
    expect(frame).toHaveAttribute('src', '/cdeadmin/embed/e-partner/frame?token=TOKEN-3');
    expect(frame).toHaveAttribute('sandbox', 'allow-scripts allow-same-origin');
    expect(frame).toHaveAttribute('referrerpolicy', 'no-referrer');
    expect(screen.getByText('This preview token expires in 120 seconds; reload to get a new one.')).toBeInTheDocument();
    // the token is not displayed as text
    expect(screen.queryByText(/TOKEN-3/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Reload preview'}));
    await waitFor(() => expect(client.previewEmbed).toHaveBeenCalledTimes(2));
  });

  it('reports a preview the server refuses', async () => {
    const client = fakeClient({previewEmbed: jest.fn(async () => { throw new Error('enable the embed to preview it'); })});
    await open(client);
    fireEvent.click(within(row('Partner portal')).getByRole('button', {name: 'Preview Partner portal'}));
    await screen.findByRole('region', {name: 'Preview'});
    type('Claim tenant_id', '7');
    fireEvent.click(screen.getByRole('button', {name: 'Load preview'}));
    expect(await screen.findByText('enable the embed to preview it')).toBeInTheDocument();
    expect(screen.queryByTitle('Embed preview')).not.toBeInTheDocument();
  });

  it('offers no preview for an embed that is not enabled', async () => {
    await open(fakeClient());
    expect(within(row('Draft embed')).queryByRole('button', {name: 'Preview Draft embed'})).not.toBeInTheDocument();
  });

  it('shows signing code without the secret', async () => {
    await open(fakeClient());
    fireEvent.click(within(row('Partner portal')).getByRole('button', {name: 'Code for Partner portal'}));
    const code = await screen.findByLabelText('Example code');
    expect(code.textContent).toContain('os.environ["CDE_EMBED_SECRET"]');
    expect(code.textContent).toContain('"aud": "e-partner"');
    expect(code.textContent).not.toMatch(/SECRET-\d/);
    await choose('Language', 'Node.js');
    expect(screen.getByLabelText('Example code').textContent).toContain('process.env.CDE_EMBED_SECRET');
    await choose('Language', 'Pseudo-code');
    expect(screen.getByLabelText('Example code').textContent).toContain('HS256_sign');
  });

  it('shows view counts and nothing personal', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(within(row('Partner portal')).getByRole('button', {name: 'Views of Partner portal'}));
    await screen.findByText('3 views, 2 card runs, 0 errors.');
    expect(client.embedStats).toHaveBeenCalledWith('e-partner', 30);
    const table = screen.getByRole('table', {name: 'Views per day'});
    expect(within(table).getByText('2026-03-02')).toBeInTheDocument();
    expect(screen.getByText('Only counts are kept: no viewer, address or claim values.')).toBeInTheDocument();
    fireEvent.click(within(row('Partner portal')).getByRole('button', {name: 'Views of Partner portal'}));
    await waitFor(() => expect(screen.queryByRole('region', {name: 'Views'})).not.toBeInTheDocument());
  });

  it('reports a failed statistics request', async () => {
    await open(fakeClient({embedStats: jest.fn(async () => { throw new Error('manage access is required'); })}));
    fireEvent.click(within(row('Partner portal')).getByRole('button', {name: 'Views of Partner portal'}));
    expect(await screen.findByText('manage access is required')).toBeInTheDocument();
  });
});

describe('EmbedDialog close', () => {
  it('closes and does not keep the secret anywhere', async () => {
    const client = fakeClient();
    const {onClose} = await open(client);
    await fillNewEmbed();
    fireEvent.click(screen.getByRole('button', {name: 'Create embed'}));
    await screen.findByRole('group', {name: 'Signing secret'});
    fireEvent.click(screen.getAllByRole('button', {name: 'Close'}).pop());
    expect(onClose).toHaveBeenCalled();
    expect(document.cookie).not.toMatch(/SECRET/);
    expect(JSON.stringify({...window.localStorage})).not.toMatch(/SECRET/);
  });

  it('warns about raw SQL', async () => {
    await open(fakeClient(), {rawSql: true});
    expect(screen.getByText(/This content uses raw SQL/)).toBeInTheDocument();
  });
});
