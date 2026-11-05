/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The Preferences tab with the interface pages (owner direction 2026-11-05:
// the interface designer is part of Preferences). Renders the real
// Preferences component against a faked preferences endpoint.

import axios from 'axios';
import MockAdapter from 'axios-mock-adapter';
import {act, fireEvent, render, screen} from '@testing-library/react';
import {withBrowser} from '../genericFunctions';
import fakePgAdmin from '../fake_pgadmin';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import PreferencesComponent from
  '../../../pgadmin/preferences/static/js/components/PreferencesComponent';
import {WorkspaceContext} from 'sources/cdeadmin_ui/workspace/Workspace';
import {
  DESIGNER_PREFERENCES_ID, requestPreferencesSection,
} from 'sources/cdeadmin_ui/customization/InterfacePreferences';
import {readAppearance} from 'sources/cdeadmin_ui/customization/appearance';

const INDEX = [{id: 7, label: 'Browser', name: 'browser', children: [
  {id: 8, label: 'Display', name: 'display', preferences: [
    {id: 900, cid: 8, mid: 7, name: 'confirm_on_refresh_close', label: 'Confirm on close',
      type: 'boolean', value: true, help_str: null}]},
]}];

function storeData() {
  return Object.entries({...readAppearance({}), theme: 'light', appearance_presets: ''})
    .map(([name, value], index) => ({id: index + 1, cid: 1, mid: 1, module: 'misc',
      name, value}));
}

function renderPreferences(listeners) {
  const docker = {eventBus: {registerListener: (event, listener) => {
    listeners.push(listener);
    return () => {};
  }}, close: jest.fn()};
  const Tab = withBrowser(() => <WorkspaceContext.Provider value={docker}>
    <PreferencesComponent panelId="id-preferences" />
  </WorkspaceContext.Provider>);
  render(<Tab />);
  return docker;
}

describe('Preferences tab with interface pages', () => {
  let network;

  beforeEach(() => {
    network = new MockAdapter(axios);
    network.onGet('/preferences/').reply(200, INDEX);
    usePreferences.setState({data: storeData(), version: 1, isLoading: false,
      failed: false, setPreferences: jest.fn(async () => ({}))});
  });

  afterEach(() => network.restore());

  it('lists the interface categories first and opens on their first page', async () => {
    renderPreferences([]);
    expect(await screen.findByRole('heading', {name: 'Profile and presets'}))
      .toBeInTheDocument();
    expect(screen.getByText('Appearance and accessibility')).toBeInTheDocument();
    expect(screen.getByText('Interface designer')).toBeInTheDocument();
    expect(screen.getByText('Browser')).toBeInTheDocument();
  });

  it('opens at the page that was requested before it loaded', async () => {
    requestPreferencesSection(`${DESIGNER_PREFERENCES_ID}-profiles`);
    renderPreferences([]);
    expect(await screen.findByRole('heading', {name: 'Interface profiles'}))
      .toBeInTheDocument();
  });

  it('moves to a requested page while open', async () => {
    renderPreferences([]);
    await screen.findByRole('heading', {name: 'Profile and presets'});
    act(() => requestPreferencesSection(`${DESIGNER_PREFERENCES_ID}-artwork`));
    expect(await screen.findByRole('heading', {name: 'Artwork and icon assignments'}))
      .toBeInTheDocument();
  }, 60000);

  it('warns before closing with unsaved interface changes', async () => {
    const confirm = jest.spyOn(fakePgAdmin.Browser.notifier, 'confirm');
    const listeners = [];
    const docker = renderPreferences(listeners);
    act(() => requestPreferencesSection(`${DESIGNER_PREFERENCES_ID}-profiles`));
    await screen.findByRole('heading', {name: 'Interface profiles'});
    fireEvent.click(screen.getByRole('button', {name: 'Restore packaged defaults'}));
    let result;
    act(() => { result = listeners.at(-1)('id-preferences'); });
    expect(result).toBe(false);
    expect(docker.close).not.toHaveBeenCalled();
    expect(confirm).toHaveBeenCalledWith('Warning',
      'Changes will be lost. Are you sure you want to close the preferences?',
      expect.any(Function), null);
    confirm.mockRestore();
  });

  it('closes without asking when nothing is unsaved', async () => {
    const confirm = jest.spyOn(fakePgAdmin.Browser.notifier, 'confirm');
    const listeners = [];
    const docker = renderPreferences(listeners);
    await screen.findByRole('heading', {name: 'Profile and presets'});
    act(() => { listeners.at(-1)('id-preferences'); });
    expect(confirm).not.toHaveBeenCalled();
    expect(docker.close).toHaveBeenCalledWith('id-preferences', true);
    confirm.mockRestore();
  });
});
