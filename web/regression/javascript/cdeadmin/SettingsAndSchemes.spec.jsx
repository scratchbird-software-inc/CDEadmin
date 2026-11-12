/////////////////////////////////////////////////////////////
//
// ScratchRobin — Comprehensive Settings, Schemes, Fonts, Menus, Security & Engines Spec
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import {ProjectTopMenuRegistry, TActionsRegistry} from 'sources/cdeadmin_ui';
import {
  ProjectShellProvider,
  ProjectTopMenuBar,
  ProjectWorkbenchFrame,
} from 'sources/cdeadmin_ui/shell';

function renderShell(fetchImpl = null) {
  const actionsRegistry = new TActionsRegistry();
  const menuRegistry = new ProjectTopMenuRegistry();
  const Themed = withTheme(() => (
    <ProjectShellProvider
      actionsRegistry={actionsRegistry}
      menuRegistry={menuRegistry}
      fetchImpl={fetchImpl}
    >
      <ProjectTopMenuBar />
      <ProjectWorkbenchFrame />
    </ProjectShellProvider>
  ));
  return render(<Themed />);
}

describe('ScratchRobin Settings Expansion — Schemes, Fonts, Action/Menu Editor, Security & Engines', () => {
  beforeEach(() => {
    window.localStorage?.clear?.();
    usePreferences.setState({
      data: [{id: 1, cid: 1, mid: 1, module: 'misc', name: 'theme', value: 'standard'}],
      cache: jest.fn(async () => {}),
      setPreferences: jest.fn(async () => {}),
    });
  });

  it('supports curated & custom colour schemes and exposes them in Area 1 scheme toggle', async () => {
    const {container} = renderShell();

    // Open Global Settings directly at Colour Schemes
    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-preferences', {
          detail: {mode: 'global', sectionId: 'appearance:schemes'},
        })
      );
    });

    const schemesEditor = await screen.findByText('Colour Schemes & Top-Bar Scheme Toggle');
    expect(schemesEditor).toBeTruthy();

    // Apply Nordic Aurora (`nord_dark`)
    const applyNordBtn = document.querySelector('[data-cdeadmin-qa-key="scheme-apply-nord_dark"]');
    expect(applyNordBtn).toBeTruthy();
    await act(async () => {
      fireEvent.click(applyNordBtn);
    });

    expect(document.documentElement.style.getPropertyValue('--sr-scheme-backdrop-a')).toBe('#242933');
    // Area 1 tone button displays active non-default scheme label
    const toneBtn = container.querySelector('[data-cdeadmin-qa-key="top-menu-tone"]');
    expect(toneBtn.textContent).toContain('Nordic Aurora');

    // Create a custom scheme and activate it
    await act(async () => {
      fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="scheme-new-custom"]'));
    });
    const customNameInput = document.querySelector('[data-cdeadmin-qa-key="scheme-custom-name"]');
    fireEvent.change(customNameInput, {target: {value: 'Cobalt Studio'}});
    const accentInput = document.querySelector('[data-cdeadmin-qa-key="scheme-custom-color-accent"]');
    fireEvent.change(accentInput, {target: {value: '#ff6b35'}});
    await act(async () => {
      fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="scheme-save-custom"]'));
    });

    expect(document.documentElement.style.getPropertyValue('--sr-scheme-accent')).toBe('#ff6b35');
    expect(toneBtn.textContent).toContain('Cobalt Studio');

    // Area 1 scheme picker trigger exists alongside tone button
    const schemeMenuTrigger = container.querySelector('[data-cdeadmin-qa-key="top-menu-scheme-menu"]');
    expect(schemeMenuTrigger).toBeTruthy();
  });

  it('updates UI, Monospace & Diagram fonts, sizes and ligatures via CSS variables', async () => {
    renderShell();

    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-preferences', {
          detail: {mode: 'global', sectionId: 'appearance:fonts'},
        })
      );
    });

    await screen.findByText('Fonts & Typography');

    const uiFamily = document.querySelector('[data-cdeadmin-qa-key="font-ui-family"]');
    fireEvent.change(uiFamily, {target: {value: '"IBM Plex Sans", sans-serif'}});

    const monoSize = document.querySelector('[data-cdeadmin-qa-key="font-mono-size"]');
    fireEvent.change(monoSize, {target: {value: '16'}});

    expect(document.documentElement.style.getPropertyValue('--sr-font-ui')).toBe(
      '"IBM Plex Sans", sans-serif'
    );
    expect(document.documentElement.style.getPropertyValue('--sr-mono-font-size')).toBe('16px');
  });

  it('edits Global Top Menus and Application Tabbed-Notebook-Iconbars (3b / 3b1) live', async () => {
    const {container} = renderShell();

    // Launch SQL Editor so Area 3b Tabbed-Notebook-Iconbar is mounted
    const sqlDockBtn = container.querySelector('[data-cdeadmin-qa-key="side-menu-app-sql-editor"]');
    expect(sqlDockBtn).toBeTruthy();
    fireEvent.click(sqlDockBtn);

    // Open Preferences -> Global Top Menus
    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-preferences', {
          detail: {mode: 'global', sectionId: 'actions:global-menus'},
        })
      );
    });

    await screen.findByText('Global Top Menu Bar Editor (Area 1)');

    // Create a custom top-level menu "Favorites"
    const newMenuInput = document.querySelector('[data-cdeadmin-qa-key="global-menu-new-name"]');
    fireEvent.change(newMenuInput, {target: {value: 'Favorites'}});
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="global-menu-add-custom"]'));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="global-menu-place-action"]'));

    // Verify "Favorites" menu now appears in Area 1 Top Menu Bar!
    await waitFor(() => {
      const favTrigger = container.querySelector('[data-menu-name="favorites"]');
      expect(favTrigger).toBeTruthy();
    });

    // Switch to Tabbed-Notebook Iconbars (3b / 3b1) editor and add an icon to 3b1 Quick Access
    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-preferences', {
          detail: {mode: 'global', sectionId: 'actions:iconbars'},
        })
      );
    });

    await screen.findByText('Tabbed-Notebook Iconbars Editor (Area 3b & 3b1 Quick Strip)');
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="quick-access-add-icon"]'));
    expect(document.querySelector('[data-cdeadmin-qa-key="quick-access-chip-sql.execute"]')).toBeTruthy();
  });

  it('configures Security Application Availability, Users, and Groups', async () => {
    const calls = [];
    const mockFetch = jest.fn(async (url, opts = {}) => {
      calls.push({url, method: opts.method || 'GET', body: opts.body ? JSON.parse(opts.body) : null});
      return {ok: true, status: 200, json: async () => ({})};
    });

    const {container} = renderShell(mockFetch);

    // Open Security -> Application Availability
    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-preferences', {
          detail: {mode: 'global', sectionId: 'security:apps'},
        })
      );
    });

    await screen.findByText('Workspace Application Availability');
    const cubeSwitch = document.querySelector('[data-cdeadmin-qa-key="security-app-switch-cube-designer"]');
    expect(cubeSwitch).toBeTruthy();
    fireEvent.click(cubeSwitch);

    await waitFor(() => {
      expect(calls.some((c) => c.url === '/cdeadmin/api/shell/security' && c.method === 'PUT')).toBe(true);
    });

    // Save settings so permittedApps updates catalogApps on shell
    expect(container.querySelector('[data-cdeadmin-qa-key="side-menu-app-cube-designer"]')).toBeTruthy();
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="settings-save"]'));
    await waitFor(() => {
      expect(container.querySelector('[data-cdeadmin-qa-key="side-menu-app-cube-designer"]')).toBeNull();
    });

    // Open Security -> Users and add a new user
    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-preferences', {
          detail: {mode: 'global', sectionId: 'security:users'},
        })
      );
    });

    await screen.findByText('Users, Group Assignments & Application Overrides');
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="security-user-new"]'));
    fireEvent.change(document.querySelector('[data-cdeadmin-qa-key="security-user-username"]'), {
      target: {value: 'alice'},
    });
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="security-user-save"]'));

    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.url === '/cdeadmin/api/shell/security/users' &&
            c.method === 'POST' &&
            c.body?.username === 'alice'
        )
      ).toBe(true);
    });
  });

  it('toggles Database Engines ON and OFF and syncs with /cdeadmin/api/shell/engines', async () => {
    const calls = [];
    const mockFetch = jest.fn(async (url, opts = {}) => {
      calls.push({url, method: opts.method || 'GET', body: opts.body ? JSON.parse(opts.body) : null});
      return {ok: true, status: 200, json: async () => ({})};
    });

    renderShell(mockFetch);

    act(() => {
      window.dispatchEvent(
        new CustomEvent('scratchrobin:open-preferences', {
          detail: {mode: 'global', sectionId: 'engines:connectors'},
        })
      );
    });

    await screen.findByText(/Database Engines & Connectors On\/Off/);
    const chSwitch = document.querySelector('[data-cdeadmin-qa-key="engine-switch-clickhouse"]');
    expect(chSwitch).toBeTruthy();
    fireEvent.click(chSwitch);

    await waitFor(() => {
      expect(
        calls.some(
          (c) =>
            c.url === '/cdeadmin/api/shell/engines' &&
            c.method === 'PUT' &&
            c.body?.enabled_engines?.includes('clickhouse')
        )
      ).toBe(true);
    });
  });
});
