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
import ShareDialog from 'sources/cdeadmin_ui/modules/bi/ShareDialog';
import {sharingFixtures as fx} from './sharingFixtures';

beforeEach(() => { window.innerHeight = 1200; });

function fakeClient(overrides = {}) {
  return {
    listGrants: jest.fn(async () => fx.grantListing),
    searchPrincipals: jest.fn(async () => fx.principalSearch),
    addGrant: jest.fn(async () => ({})),
    updateGrant: jest.fn(async () => ({})),
    removeGrant: jest.fn(async () => ({})),
    setInherit: jest.fn(async () => ({})),
    transferOwner: jest.fn(async () => ({})),
    ...overrides,
  };
}

const open = async (client, props = {}) => {
  const onClose = jest.fn();
  const onChanged = jest.fn();
  render(<Theme><ShareDialog client={client} resourceType="question" resourceId="q-detail"
    resourceName="Detail by region" onClose={onClose} onChanged={onChanged} {...props} /></Theme>);
  await screen.findByRole('list', {name: 'Access list'});
  return {onClose, onChanged};
};

describe('ShareDialog', () => {
  it('lists the owner, direct grants and inherited grants with their source', async () => {
    await open(fakeClient());
    const list = screen.getByRole('list', {name: 'Access list'});
    expect(within(list).getByText('You')).toBeInTheDocument();
    expect(within(list).getByText('editor')).toBeInTheDocument();
    expect(within(list).getByText('Can view, inherited from Team')).toBeInTheDocument();
    expect(within(list).getByText('Can edit, inherited from Team')).toBeInTheDocument();
    // inherited rows cannot be removed here
    expect(screen.getAllByRole('button', {name: /^Remove access of/})).toHaveLength(1);
  });

  it('adds a searched principal at the chosen level', async () => {
    const client = fakeClient();
    const {onChanged} = await open(client);
    const hit = await screen.findByRole('button', {name: /manager/});
    fireEvent.click(hit);
    expect(screen.getByRole('button', {name: 'Add'})).toBeEnabled();
    fireEvent.click(screen.getByRole('button', {name: 'Add'}));
    await waitFor(() => expect(client.addGrant).toHaveBeenCalledWith('question', 'q-detail', 'user', 4, 'view'));
    await waitFor(() => expect(onChanged).toHaveBeenCalled());
    expect(client.listGrants).toHaveBeenCalledTimes(2);
  });

  it('removes a direct grant', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(screen.getByRole('button', {name: 'Remove access of editor'}));
    await waitFor(() => expect(client.removeGrant).toHaveBeenCalledWith(
      'question', 'q-detail', fx.grantListing.direct[0].grant_id));
  });

  it('shows the server refusal and keeps the list', async () => {
    const client = fakeClient({removeGrant: jest.fn(async () => { throw new Error('manage access is required'); })});
    await open(client);
    fireEvent.click(screen.getByRole('button', {name: 'Remove access of editor'}));
    expect(await screen.findByText('manage access is required')).toBeInTheDocument();
    expect(screen.getByRole('list', {name: 'Access list'})).toBeInTheDocument();
  });

  it('turns inheritance off', async () => {
    const client = fakeClient();
    await open(client);
    fireEvent.click(screen.getByRole('checkbox', {name: /Inherit access/}));
    await waitFor(() => expect(client.setInherit).toHaveBeenCalledWith('question', 'q-detail', false));
  });

  it('hides the inheritance section for a resource without a collection', async () => {
    await open(fakeClient(), {hasCollection: false});
    expect(screen.queryByRole('checkbox', {name: /Inherit access/})).not.toBeInTheDocument();
  });

  it('transfers ownership only after the exact name is typed', async () => {
    const client = fakeClient();
    const {onClose} = await open(client);
    await screen.findByRole('button', {name: /manager/});
    const transfer = screen.getByRole('button', {name: 'Transfer ownership'});
    expect(transfer).toBeDisabled();
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'New owner'}));
    fireEvent.click(await screen.findByRole('option', {name: 'manager'}));
    const box = screen.getByLabelText('Type the name Detail by region to confirm');
    fireEvent.change(box, {target: {value: 'detail by region'}});
    expect(transfer).toBeDisabled();
    fireEvent.change(box, {target: {value: 'Detail by region'}});
    expect(transfer).toBeEnabled();
    fireEvent.click(transfer);
    await waitFor(() => expect(client.transferOwner).toHaveBeenCalledWith(
      'question', 'q-detail', 4, 'Detail by region'));
    await waitFor(() => expect(onClose).toHaveBeenCalledWith({transferred: true}));
  });

  it('reports an unavailable list', async () => {
    const client = fakeClient({listGrants: jest.fn(async () => { throw new Error('saved question is unavailable'); })});
    render(<Theme><ShareDialog client={client} resourceType="question" resourceId="x" resourceName="X"
      onClose={jest.fn()} /></Theme>);
    expect(await screen.findByText('The access list is unavailable.')).toBeInTheDocument();
  });
});
