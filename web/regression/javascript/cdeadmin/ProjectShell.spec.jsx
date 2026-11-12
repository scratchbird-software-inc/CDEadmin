/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useMemo} from 'react';
import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import {
  PROJECT_TOP_MENU_INDICES,
  ProjectTopMenuRegistry,
  TActionsRegistry,
  T_ACTION_STATUS,
  T_ACTION_TARGET_KIND,
  assertUnsignedMenuIndex,
} from 'sources/cdeadmin_ui';
import {
  ProjectShellProvider,
  ProjectTopMenuBar,
  ProjectWorkbenchFrame,
  computeDockProximity,
} from 'sources/cdeadmin_ui/shell';

function setMiscPreferences(values) {
  usePreferences.setState({
    data: Object.entries(values).map(([name, value], id) => ({
      id,
      cid: 1,
      mid: 1,
      module: 'misc',
      name,
      value,
    })),
    setPreferences: jest.fn(async (updates) => {
      const nextMap = {...values};
      (updates || []).forEach((u) => {
        nextMap[u.name] = u.value;
      });
      usePreferences.setState({
        data: Object.entries(nextMap).map(([name, value], id) => ({
          id,
          cid: 1,
          mid: 1,
          module: 'misc',
          name,
          value,
        })),
        version: Date.now(),
      });
    }),
    version: Date.now(),
    isLoading: false,
    failed: false,
  });
}

function createMockPopupWindow() {
  const popupDoc = document.implementation.createHTMLDocument('Floating Subform');
  Object.defineProperty(popupDoc, 'defaultView', {value: window, configurable: true});
  const listeners = new Map();
  const win = {
    document: popupDoc,
    closed: false,
    focus: jest.fn(() => {
      (listeners.get('focus') || []).forEach((fn) => fn());
    }),
    close: jest.fn(() => {
      win.closed = true;
      (listeners.get('beforeunload') || []).forEach((fn) => fn());
    }),
    addEventListener: jest.fn((type, fn) => {
      listeners.set(type, [...(listeners.get(type) || []), fn]);
    }),
    triggerEvent: (type) => {
      (listeners.get(type) || []).forEach((fn) => fn());
    },
  };
  return win;
}

function ShellHarness({
  fetchImpl,
  openPopupWindow,
  onOpenPreferences,
  onTeardownStep,
}) {
  const actionsRegistry = useMemo(() => new TActionsRegistry({fetchImpl}), [fetchImpl]);
  const menuRegistry = useMemo(() => new ProjectTopMenuRegistry(), []);

  const applicationFactory = ({appId, instanceId, sequence}) => {
    if (appId === 'sql-editor') {
      const engine = sequence === 1 ? 'Firebird 5' : 'MySQL 8';
      const runId = `sql.run.${instanceId}`;
      return {
        title: `SQL Editor (${engine})`,
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        actions: [
          {
            id: runId,
            icon: 'action.execute',
            application: 'sql-editor',
            defaultText: `Run on ${engine}`,
            defaultHint: `Execute statement on ${engine}`,
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: jest.fn()},
          },
        ],
        menus: [
          {
            name: 'query',
            label: 'Query',
            index: 25,
            items: [{id: runId, actionId: runId, label: `Run on ${engine}`, index: 10}],
          },
          {
            // Merge into existing Window menu (index 70) at child index 25
            name: 'window',
            label: 'Window',
            index: PROJECT_TOP_MENU_INDICES.WINDOW,
            items: [
              {
                id: `sql.pin.${instanceId}`,
                label: `Pin ${engine} Results`,
                index: 25,
                callback: () => {},
              },
            ],
          },
        ],
        ribbonTabs: [
          {
            id: `ribbon-${instanceId}`,
            label: 'SQL',
            groups: [{id: 'exec', label: 'Execution', controls: [runId]}],
          },
        ],
        renderLeftDrawer: () => <div>{`${engine} Schema Tree`}</div>,
        renderWorkArea: () => (
          <div>
            <span>{`${engine} Query Buffer`}</span>
            <input aria-label={`${engine} SQL Input`} defaultValue={`SELECT * FROM ${engine};`} />
          </div>
        ),
        renderRightDrawer: (inst) => <div>{`${engine} Inspector (${inst.rightMode})`}</div>,
        statusText: `Connected: ${engine}`,
      };
    }

    if (appId === 'data-navigator') {
      return {
        title: sequence > 1 ? `Data Navigator #${sequence}` : 'Data Navigator',
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        menus: [
          {
            name: 'object',
            label: 'Object',
            index: 20,
            items: [{id: 'nav.refresh', label: 'Refresh Tree', index: 10, callback: () => {}}],
          },
        ],
        renderLeftDrawer: () => <div>Engines &gt; Servers &gt; Schemas &gt; Tables</div>,
        renderWorkArea: () => <div>Selected Catalog Object Details</div>,
        renderRightDrawer: () => <div>Navigator Object Properties</div>,
        statusText: 'Navigator Ready',
      };
    }

    return null;
  };

  return (
    <ProjectShellProvider
      username="dba@scratchrobin.org"
      actionsRegistry={actionsRegistry}
      menuRegistry={menuRegistry}
      applicationFactory={applicationFactory}
      fetchImpl={fetchImpl}
      openPopupWindow={openPopupWindow}
      onOpenPreferences={onOpenPreferences}
      onTeardownStep={onTeardownStep}
    >
      <ProjectTopMenuBar />
      <div style={{height: 640}}>
        <ProjectWorkbenchFrame />
      </div>
    </ProjectShellProvider>
  );
}

describe('Standardized ScratchRobin Project Shell & t_actions', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-cde-theme');
    setMiscPreferences({theme: 'light'});
  });

  it('enforces the 5 canonical t_actions fields, i18n lookup, authorization clamping, and target execution', async () => {
    const serverFetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ok: true, rows: 4}),
    });
    const registry = new TActionsRegistry({fetchImpl: serverFetch});
    const clientSpy = jest.fn(() => 'client-done');

    registry.registerStrings('fr', {
      'sql.execute.text': 'Exécuter SQL',
      'sql.execute.hint': 'Exécuter la requête active',
    });

    registry.register({
      id: 'sql.execute',
      icon: 'action.execute',
      application: 'sql-editor',
      defaultText: 'Execute SQL',
      defaultHint: 'Run active query',
      status: T_ACTION_STATUS.ENABLED,
      target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: clientSpy},
    });

    registry.register({
      id: 'catalog.sync',
      icon: 'action.refresh',
      application: 'data-navigator',
      defaultText: 'Sync Catalog',
      defaultHint: 'Sync remote catalog metadata',
      status: T_ACTION_STATUS.ENABLED,
      target: {
        kind: T_ACTION_TARGET_KIND.SERVER,
        endpoint: '/cdeadmin/api/shell/actions/catalog.sync/invoke',
        method: 'POST',
      },
    });

    expect(registry.resolve('sql.execute')).toMatchObject({
      id: 'sql.execute',
      icon: 'action.execute',
      application: 'sql-editor',
      status: 'enabled',
      text: 'Execute SQL',
      hint: 'Run active query',
    });

    registry.setLocale('fr');
    expect(registry.resolve('sql.execute').text).toBe('Exécuter SQL');
    expect(registry.resolve('sql.execute').hint).toBe('Exécuter la requête active');

    expect(await registry.execute('sql.execute', {limit: 10})).toBe('client-done');
    expect(clientSpy).toHaveBeenCalledWith({limit: 10}, {});

    const serverRes = await registry.execute('catalog.sync', {engine: 'firebird'});
    expect(serverRes).toEqual({ok: true, rows: 4});
    expect(serverFetch).toHaveBeenCalledWith(
      '/cdeadmin/api/shell/actions/catalog.sync/invoke',
      expect.objectContaining({method: 'POST'})
    );

    // Authorization overrides clamp enabled -> disabled/invisible
    registry.setAuthorizationOverrides({
      'sql.execute': 'disabled',
      'catalog.sync': 'invisible',
    });
    expect(registry.resolve('sql.execute').enabled).toBe(false);
    expect(registry.resolve('catalog.sync').visible).toBe(false);
    await expect(registry.execute('sql.execute')).rejects.toThrow(/disabled/i);
    await expect(registry.execute('catalog.sync')).rejects.toThrow(/invisible/i);
  });

  it('sorts Area 1 Top Menus and nested submenus by unsigned integer index and merges/unmerges cleanly', () => {
    expect(() => assertUnsignedMenuIndex(-1)).toThrow(RangeError);
    expect(() => assertUnsignedMenuIndex(1.5)).toThrow(RangeError);
    expect(assertUnsignedMenuIndex(0)).toBe(0);

    const reg = new ProjectTopMenuRegistry();
    expect(reg.resolve().map((m) => [m.index, m.name])).toEqual([
      [0, 'system'],
      [60, 'applications'],
      [70, 'window'],
      [80, 'help'],
    ]);

    reg.setBaselineMenus([
      {name: 'system', index: 0, isSystemIcon: true, items: []},
      {
        name: 'applications',
        index: 60,
        items: [
          {id: 'prefs', label: 'Preferences', index: 20},
          {id: 'ds', label: 'Data Sources', index: 10},
        ],
      },
      {name: 'window', index: 70, items: [{id: 'close', label: 'Close', index: 45}]},
      {name: 'help', index: 80, items: []},
    ]);

    // Focused app inserts at index 25 and merges an item at index 15 into Applications (60)
    reg.setFocusedApplicationMenus('sql-1', [
      {name: 'query', label: 'Query', index: 25, items: [{id: 'run', label: 'Run', index: 5}]},
      {
        name: 'applications',
        label: 'Applications',
        index: 60,
        items: [{id: 'import_sql', label: 'Import SQL Bundle', index: 15}],
      },
    ]);

    const resolved = reg.resolve();
    expect(resolved.map((m) => [m.index, m.name])).toEqual([
      [0, 'system'],
      [25, 'query'],
      [60, 'applications'],
      [70, 'window'],
      [80, 'help'],
    ]);
    expect(resolved.find((m) => m.name === 'applications').items.map((i) => i.id)).toEqual([
      'ds',
      'import_sql',
      'prefs',
    ]);

    // Teardown cleanly unmerges
    reg.clearFocusedApplicationMenus();
    expect(reg.resolve().map((m) => m.name)).toEqual(['system', 'applications', 'window', 'help']);
    expect(reg.resolve().find((m) => m.name === 'applications').items.map((i) => i.id)).toEqual([
      'ds',
      'prefs',
    ]);
  });

  it('starts on tabless User Dashboard placeholder with disabled Left Drawer toggle and no preloaded SQL tab', () => {
    const Component = withTheme(ShellHarness);
    render(<Component fetchImpl={jest.fn().mockResolvedValue({ok: false, status: 404})} />);

    // Startup Area 3: tabless User Dashboard placeholder, no tab strip, no NotebookBar
    expect(screen.getByText('User Dashboard')).toBeInTheDocument();
    expect(screen.queryByRole('tablist', {name: 'Open Applications'})).not.toBeInTheDocument();
    expect(document.querySelector('[data-cdeadmin-qa-key="project-application-notebookbar"]'))
      .not.toBeInTheDocument();

    // Area 1 Top Menu: 0 System Icon immediately adjacent to 60 Applications, 70 Window, 80 Help + Language + Dark
    const menuItems = screen.getAllByRole('menuitem');
    expect(menuItems.map((el) => el.getAttribute('data-menu-index'))).toEqual([
      '0',
      '60',
      '70',
      '80',
    ]);
    expect(document.querySelector('[data-cdeadmin-qa-key="top-menu-language"]')).toBeInTheDocument();
    expect(document.querySelector('[data-cdeadmin-qa-key="top-menu-tone"]')).toBeInTheDocument();

    // Area 2 Side Menu: Left Drawer toggle disabled, Data Navigator first, Gear at bottom
    const leftToggle = document.querySelector('[data-cdeadmin-qa-key="side-menu-left-drawer-toggle"]');
    expect(leftToggle).toBeDisabled();

    const launcherButtons = within(
      screen.getByRole('toolbar', {name: 'Launch Applications'})
    ).getAllByRole('button');
    expect(launcherButtons[0]).toHaveAttribute('aria-label', 'Open Data Navigator');

    // Gear popup: Application Settings is disabled when no application is open
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="side-menu-settings-gear"]'));
    expect(document.querySelector('[data-cdeadmin-qa-key="gear-application-settings"]')).toBeDisabled();
    expect(document.querySelector('[data-cdeadmin-qa-key="gear-global-settings"]')).not.toBeDisabled();
  });

  it('manages 1-app tabless view, 2+ tabs with [x] on active tab, NotebookBar [x], Window > User Dashboard lifecycle, and teardown-before-activate', () => {
    const teardownSteps = [];
    const Component = withTheme(ShellHarness);
    render(
      <Component
        fetchImpl={jest.fn().mockResolvedValue({ok: false, status: 404})}
        onTeardownStep={(step, detail) => teardownSteps.push({step, ...detail})}
      />
    );

    // 1. Open first application (Data Navigator): placeholder disappears, STILL NO tab strip!
    fireEvent.click(screen.getByRole('button', {name: 'Open Data Navigator'}));
    expect(screen.getByText('Selected Catalog Object Details')).toBeInTheDocument();
    expect(screen.queryByRole('tablist', {name: 'Open Applications'})).not.toBeInTheDocument();

    // Standard [x] close button IS present on the Main Form NotebookBar even with 1 tabless app
    expect(
      document.querySelector('[data-cdeadmin-qa-key="notebookbar-close-active"]')
    ).toBeInTheDocument();
    // And Left Drawer opened automatically for Data Navigator, enabling Area 2's toggle
    expect(
      document.querySelector('[data-cdeadmin-qa-key="side-menu-left-drawer-toggle"]')
    ).not.toBeDisabled();
    expect(screen.getByText(/Engines > Servers > Schemas > Tables/)).toBeInTheDocument();

    // Dynamic menu 'Object' (index 20) inserted between 0 and 60
    expect(
      screen.getAllByRole('menuitem').map((el) => el.getAttribute('data-menu-index'))
    ).toEqual(['0', '20', '60', '70', '80']);

    // 2. Open two SQL Editor instances (Firebird 5 and MySQL 8) from Area 2 Side Menu
    teardownSteps.length = 0;
    fireEvent.click(screen.getByRole('button', {name: 'Open SQL Editor'}));
    // Verify Teardown-Before-Activate happened in exact order before activating SQL Editor
    expect(teardownSteps.map((s) => s.step)).toEqual([
      '1.menus_cleared',
      '2.left_drawer_reset',
      '3.app_settings_cleared',
      '4.incoming_activated',
    ]);

    // Area 3 now has >= 2 docked apps -> tab strip appears, ONLY active tab has [x]
    const tabList = screen.getByRole('tablist', {name: 'Open Applications'});
    const tabsAfterTwo = within(tabList).getAllByRole('tab');
    expect(tabsAfterTwo).toHaveLength(2);
    expect(within(tabsAfterTwo[0]).queryByRole('button')).not.toBeInTheDocument();
    expect(within(tabsAfterTwo[1]).getByRole('button', {name: /Close SQL Editor \(Firebird 5\)/})).toBeInTheDocument();

    // Open Left & Right drawers on Firebird SQL Editor
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="side-menu-left-drawer-toggle"]'));
    expect(screen.getByText('Firebird 5 Schema Tree')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('menuitem', {name: 'Window'}));
    fireEvent.click(screen.getByRole('menuitemcheckbox', {name: 'Right Side Drawer'}));
    expect(screen.getByText('Firebird 5 Inspector (properties)')).toBeInTheDocument();

    // Open second SQL Editor (MySQL 8) -> its Left & Right drawers start closed independently!
    fireEvent.click(screen.getByRole('button', {name: 'Open SQL Editor'}));
    expect(screen.getByText('MySQL 8 Query Buffer')).toBeInTheDocument();
    expect(screen.queryByText('MySQL 8 Schema Tree')).not.toBeInTheDocument();
    expect(screen.queryByText(/MySQL 8 Inspector/)).not.toBeInTheDocument();

    // Switch back to Firebird 5 tab -> Firebird's Left & Right drawers restore automatically!
    fireEvent.click(screen.getByRole('tab', {name: /SQL Editor \(Firebird 5\)/}));
    expect(screen.getByText('Firebird 5 Schema Tree')).toBeInTheDocument();
    expect(screen.getByText('Firebird 5 Inspector (properties)')).toBeInTheDocument();

    // 3. Open User Dashboard as a tab via Window > User Dashboard
    fireEvent.click(screen.getByRole('menuitem', {name: 'Window'}));
    fireEvent.click(screen.getByRole('menuitemcheckbox', {name: 'User Dashboard'}));
    expect(screen.getByRole('tab', {name: /User Dashboard/})).toHaveAttribute('aria-selected', 'true');
    // User Dashboard NEVER shows a Tabbed-Icon-Bar and disables Left Drawer toggle
    expect(
      document.querySelector('[data-cdeadmin-qa-key="project-application-notebookbar"]')
    ).not.toBeInTheDocument();
    expect(
      document.querySelector('[data-cdeadmin-qa-key="side-menu-left-drawer-toggle"]')
    ).toBeDisabled();

    // 4. Close all 3 application instances -> User Dashboard tab automatically reverts to tabless placeholder!
    const openAppsTabs = () => screen.getByRole('tablist', {name: 'Open Applications'});
    fireEvent.click(within(openAppsTabs()).getByRole('tab', {name: /SQL Editor \(MySQL 8\)/}));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="notebookbar-close-active"]'));
    fireEvent.click(within(openAppsTabs()).getByRole('tab', {name: /SQL Editor \(Firebird 5\)/}));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="active-tab-close"]'));
    fireEvent.click(within(openAppsTabs()).getByRole('tab', {name: /Data Navigator/}));
    fireEvent.click(screen.getByRole('menuitem', {name: 'Window'}));
    fireEvent.click(screen.getByRole('menuitem', {name: 'Close'}));

    // Zero docked apps remain -> User Dashboard tab strip disappears and reverts to placeholder mode!
    expect(screen.queryByRole('tablist', {name: 'Open Applications'})).not.toBeInTheDocument();
    expect(document.querySelector('[data-cdeadmin-qa-key="user-dashboard-surface"]'))
      .toHaveAttribute('data-dashboard-mode', 'placeholder');
    // Stale menus, left drawer toggle, and gear application settings are completely cleared
    expect(
      screen.getAllByRole('menuitem').map((el) => el.getAttribute('data-menu-index'))
    ).toEqual(['0', '60', '70', '80']);
    expect(
      document.querySelector('[data-cdeadmin-qa-key="side-menu-left-drawer-toggle"]')
    ).toBeDisabled();
  });

  it('detaches a dragged tab into a chrome-free pop-out window, syncs Main Form focus, and re-docks on drop', () => {
    const popups = [];
    const openPopupWindow = jest.fn(() => {
      const win = createMockPopupWindow();
      popups.push(win);
      return win;
    });
    const Component = withTheme(ShellHarness);
    render(
      <Component
        fetchImpl={jest.fn().mockResolvedValue({ok: false, status: 404})}
        openPopupWindow={openPopupWindow}
      />
    );

    fireEvent.click(screen.getByRole('button', {name: 'Open Data Navigator'}));
    fireEvent.click(screen.getByRole('button', {name: 'Open SQL Editor'}));

    const area3 = document.querySelector('[data-cdeadmin-qa-key="project-area-3"]');
    area3.getBoundingClientRect = () => ({left: 100, top: 100, right: 900, bottom: 600});

    // Drag SQL Editor tab outside Area 3 bounds -> detaches into native pop-out window
    const sqlTab = within(
      screen.getByRole('tablist', {name: 'Open Applications'})
    ).getByRole('tab', {name: /SQL Editor \(Firebird 5\)/});
    fireEvent.dragStart(sqlTab);
    fireEvent.dragLeave(sqlTab);
    fireEvent.dragEnd(sqlTab);

    expect(openPopupWindow).toHaveBeenCalledTimes(1);
    const popupDoc = popups[0].document;
    // Floating window renders ONLY Main Work Area + bottom Status Area (no Top Menu, no Ribbon, no Drawers)
    expect(popupDoc.body.textContent).toContain('Firebird 5 Query Buffer');
    expect(popupDoc.body.textContent).toContain('Connected: Firebird 5');
    expect(popupDoc.querySelector('[data-cdeadmin-qa-key="project-top-menu"]')).toBeNull();
    expect(popupDoc.querySelector('[data-cdeadmin-qa-key="project-application-notebookbar"]')).toBeNull();

    // Only 1 docked app (Data Navigator) remains in Area 3 -> Area 3 tab strip hides!
    expect(screen.queryByRole('tablist', {name: 'Open Applications'})).not.toBeInTheDocument();

    // Click docked Data Navigator in Area 3 -> Main Form menus switch to Object (20)
    fireEvent.pointerDown(screen.getByText('Selected Catalog Object Details'));
    expect(screen.getByRole('menuitem', {name: 'Object'})).toBeInTheDocument();
    expect(screen.queryByRole('menuitem', {name: 'Query'})).not.toBeInTheDocument();

    // Focus the floating SQL Editor window -> Main Form menus & Ribbon update to SQL Editor (Query 25)!
    act(() => {
      popups[0].triggerEvent('focus');
    });
    expect(screen.getByRole('menuitem', {name: 'Query'})).toBeInTheDocument();

    // Drag floating sub-form back onto Area 3 -> pop-out closes and tab re-docks!
    const redockBtn = popupDoc.querySelector('[data-cdeadmin-qa-key^="floating-redock-"]');
    fireEvent.dragStart(redockBtn);
    fireEvent.drop(area3);

    expect(popups[0].close).toHaveBeenCalledTimes(1);
    expect(screen.getByRole('tablist', {name: 'Open Applications'})).toBeInTheDocument();
    expect(screen.getByText('Firebird 5 Query Buffer')).toBeInTheDocument();
  });

  it('locks the entire application down to a single Unlock Dialog and resets persisted drawer widths in Application Settings', async () => {
    const fetchMock = jest.fn(async (url, init) => {
      if (String(url).endsWith('/session/unlock')) {
        const body = JSON.parse(init?.body || '{}');
        if (body.password === 'correct-pass') {
          return {ok: true, status: 200, json: async () => ({locked: false})};
        }
        return {ok: false, status: 403, json: async () => ({locked: true, error: 'Wrong password'})};
      }
      if (String(url).endsWith('/reset-drawers')) {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            application_settings: {left_drawer_width: 288, right_drawer_width: 320},
          }),
        };
      }
      return {ok: false, status: 404, json: async () => ({})};
    });

    const Component = withTheme(ShellHarness);
    render(<Component fetchImpl={fetchMock} />);

    // Open Data Navigator and resize Left Side Drawer via keyboard
    fireEvent.click(screen.getByRole('button', {name: 'Open Data Navigator'}));
    const leftSplitter = screen.getByRole('separator', {name: 'Resize Left Side Drawer'});
    fireEvent.keyDown(leftSplitter, {key: 'ArrowRight', shiftKey: true});
    expect(leftSplitter).toHaveAttribute('aria-valuenow', '304');

    // Reset drawer sizes via Area 2 Gear -> Application Settings -> Reset Drawer Sizes to Default
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="side-menu-settings-gear"]'));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="gear-application-settings"]'));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="settings-reset-drawers"]'));
    await waitFor(() => {
      expect(screen.getByText(/Left and right drawer widths reset to defaults/i))
        .toBeInTheDocument();
    });
    fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
    await waitFor(() => {
      expect(screen.getByRole('separator', {name: 'Resize Left Side Drawer'}))
        .toHaveAttribute('aria-valuenow', '288');
    });

    // System Icon (0) -> Lock Screen hides the entire Main Form down to ONLY the Unlock Dialog
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="top-menu-system-icon"]'));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="session-lock-screen"]'));

    expect(document.querySelector('[data-cdeadmin-qa-key="project-lock-screen"]')).toBeInTheDocument();
    expect(document.querySelector('[data-cdeadmin-qa-key="project-top-menu"]')).not.toBeInTheDocument();
    expect(screen.queryByText('Selected Catalog Object Details')).not.toBeInTheDocument();

    // Wrong password stays locked
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'wrong'}});
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="lock-screen-unlock"]'));
    await waitFor(() => expect(screen.getByText('Wrong password')).toBeInTheDocument());

    // Correct password unlocks and restores open Data Navigator instance intact
    fireEvent.change(screen.getByLabelText('Password'), {target: {value: 'correct-pass'}});
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="lock-screen-unlock"]'));
    await waitFor(() =>
      expect(screen.getByText('Selected Catalog Object Details')).toBeInTheDocument()
    );
  });

  it('renders Base UI NavigationMenu popups with arrows/descriptions and live-translates all Main Menu text across locales', async () => {
    const Component = withTheme(ShellHarness);
    render(<Component fetchImpl={jest.fn().mockResolvedValue({ok: false, status: 404})} />);

    // Open Data Navigator so dynamic 'Object' (index 20) menu is active alongside baseline menus
    fireEvent.click(screen.getByRole('button', {name: 'Open Data Navigator'}));

    const navBar = document.querySelector('[data-cdeadmin-qa-key="project-top-menu"]');
    expect(navBar).toHaveClass('sr-nav-bar');
    expect(navBar).toHaveAttribute('data-tone', 'light');

    // Open Applications menu -> Base UI NavigationMenu Popup, Arrow, Viewport & descriptions render
    fireEvent.click(screen.getByRole('menuitem', {name: 'Applications'}));
    expect(document.querySelector('.sr-nav-popup')).toBeInTheDocument();
    expect(document.querySelector('.sr-nav-arrow')).toBeInTheDocument();
    expect(document.querySelector('.sr-nav-viewport')).toBeInTheDocument();
    expect(
      screen.getByText('Configure database servers, engines, and connection profiles.')
    ).toBeInTheDocument();

    // Switch interface language to French ('fr') via right-aligned Base UI Language NavigationMenu
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="top-menu-language"]'));
    fireEvent.click(screen.getByRole('menuitemradio', {name: 'Français'}));

    await waitFor(() => {
      expect(navBar).toHaveAttribute('data-locale', 'fr');
    });

    // Positional indices remain ['0', '20', '60', '70', '80'] while labels translate to French
    expect(
      screen.getAllByRole('menuitem').map((el) => el.getAttribute('data-menu-index'))
    ).toEqual(['0', '20', '60', '70', '80']);
    expect(screen.getByRole('menuitem', {name: 'Objet'})).toBeInTheDocument();
    expect(screen.getByRole('menuitem', {name: 'Fenêtre'})).toBeInTheDocument();
    expect(screen.getByRole('menuitem', {name: 'Aide'})).toBeInTheDocument();

    // Open French Applications popup -> translated items and descriptions appear
    fireEvent.click(screen.getByRole('menuitem', {name: 'Applications'}));
    expect(screen.getByRole('menuitem', {name: 'Sources de données'})).toBeInTheDocument();
    expect(
      screen.getByText('Configurer les serveurs, moteurs et profils de connexion.')
    ).toBeInTheDocument();

    // Switch interface language to Japanese ('ja') and toggle Light -> Dark theme
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="top-menu-language"]'));
    fireEvent.click(screen.getByRole('menuitemradio', {name: '日本語'}));

    await waitFor(() => {
      expect(screen.getByRole('menuitem', {name: 'オブジェクト'})).toBeInTheDocument();
      expect(screen.getByRole('menuitem', {name: 'アプリケーション'})).toBeInTheDocument();
      expect(screen.getByRole('menuitem', {name: 'ウィンドウ'})).toBeInTheDocument();
      expect(screen.getByRole('menuitem', {name: 'ヘルプ'})).toBeInTheDocument();
    });

    const toneBtn = document.querySelector('[data-cdeadmin-qa-key="top-menu-tone"]');
    expect(toneBtn.textContent).toContain('ライト');
    fireEvent.click(toneBtn);
    await waitFor(() => {
      expect(navBar).toHaveAttribute('data-tone', 'dark');
      expect(toneBtn.textContent).toContain('ダーク');
    });
  });

  it('magnifies all Area 2 vertical dock items rightward on hover — including isolated top drawer toggle and bottom-aligned settings gear', () => {
    // Verify pure cosine-bell proximity math
    expect(computeDockProximity(100, 100, 135)).toBeCloseTo(1, 5);
    expect(computeDockProximity(167.5, 100, 135)).toBeCloseTo(0.5, 3);
    expect(computeDockProximity(300, 100, 135)).toBe(0);

    const Component = withTheme(ShellHarness);
    render(<Component fetchImpl={jest.fn().mockResolvedValue({ok: false, status: 404})} />);

    const dockRail = document.querySelector('[data-cdeadmin-qa-key="project-side-menu"]');
    expect(dockRail).toHaveClass('sr-vdock-rail');

    // Assign deterministic Y centers to each dock slot in JSDOM:
    //   top isolated Left Drawer toggle = 26
    //   middle apps = 80, 124, 168, ...
    //   bottom-aligned isolated Settings Gear = 560
    const slots = Array.from(dockRail.querySelectorAll('.sr-vdock-slot'));
    slots.forEach((slot, idx) => {
      const cy =
        idx === 0
          ? 26
          : idx === slots.length - 1
            ? 560
            : 80 + (idx - 1) * 44;
      slot.getBoundingClientRect = () => ({
        top: cy - 18,
        bottom: cy + 18,
        left: 0,
        right: 52,
        width: 52,
        height: 36,
      });
    });

    const topBtn = document.querySelector('[data-cdeadmin-qa-key="side-menu-left-drawer-toggle"]');
    const navAppBtn = document.querySelector('[data-cdeadmin-qa-key="side-menu-app-data-navigator"]');
    const sqlAppBtn = document.querySelector('[data-cdeadmin-qa-key="side-menu-app-sql-editor"]');
    const gearBtn = document.querySelector('[data-cdeadmin-qa-key="side-menu-settings-gear"]');
    const gearSlot = gearBtn.closest('.sr-vdock-slot');

    expect(gearSlot).toHaveAttribute('data-anchor', 'bottom');
    expect(gearSlot.parentElement).toHaveClass('sr-vdock-zone--bottom');

    // 1. Hover over isolated top Left Drawer Toggle (y = 26) -> expands to full 58px + 7px rightward lift even on its own
    fireEvent.mouseMove(dockRail, {clientY: 26});
    expect(topBtn).toHaveAttribute('data-magnified', 'true');
    expect(topBtn).toHaveAttribute('data-target-size', '58');
    expect(topBtn.style.width).toBe('58px');
    expect(topBtn.style.transform).toBe('translate3d(7.00px, 0, 0)');
    // Distant bottom-aligned Settings Gear (y = 560) stays at resting 36px
    expect(gearBtn).toHaveAttribute('data-magnified', 'false');
    expect(gearBtn).toHaveAttribute('data-target-size', '36');
    expect(gearBtn.style.width).toBe('36px');

    // 2. Hover over middle Data Navigator (y = 80) -> peaks at 58px while neighbor SQL Editor (y = 124) swells proportionally
    fireEvent.mouseMove(dockRail, {clientY: 80});
    expect(navAppBtn).toHaveAttribute('data-target-size', '58');
    expect(navAppBtn.style.width).toBe('58px');
    const neighborSize = Number(sqlAppBtn.getAttribute('data-target-size'));
    expect(neighborSize).toBeGreaterThan(36);
    expect(neighborSize).toBeLessThan(58);

    // 3. Selecting/clicking an application launcher icon immediately returns it to default 36px size
    //    (even if the mouse jitters slightly over the same icon while the app loads),
    //    and Area 2 acts purely as a stateless launcher (no active tint, pips, or instance badges)
    fireEvent.mouseDown(navAppBtn);
    fireEvent.focus(navAppBtn);
    fireEvent.click(navAppBtn);
    fireEvent.mouseMove(dockRail, {clientY: 82});
    expect(navAppBtn).toHaveAttribute('data-magnified', 'false');
    expect(navAppBtn).toHaveAttribute('data-target-size', '36');
    expect(navAppBtn.style.width).toBe('36px');
    expect(navAppBtn).not.toHaveAttribute('data-active');

    // Launch a second SQL Editor instance too — still zero open-application tracking on Area 2
    fireEvent.mouseMove(dockRail, {clientY: 124});
    expect(sqlAppBtn).toHaveAttribute('data-target-size', '58');
    fireEvent.mouseDown(sqlAppBtn);
    fireEvent.focus(sqlAppBtn);
    fireEvent.click(sqlAppBtn);
    fireEvent.click(sqlAppBtn);
    expect(sqlAppBtn).toHaveAttribute('data-magnified', 'false');
    expect(sqlAppBtn).toHaveAttribute('data-target-size', '36');
    expect(sqlAppBtn.style.width).toBe('36px');
    expect(sqlAppBtn).not.toHaveAttribute('data-active');
    expect(dockRail.querySelector('.sr-vdock-pip')).toBeNull();
    expect(dockRail.querySelector('.sr-vdock-badge')).toBeNull();

    // 4. Hover over bottom-aligned isolated Settings Gear (y = 560) -> expands to full 58px + 7px rightward lift on its own
    fireEvent.mouseMove(dockRail, {clientY: 560});
    expect(gearBtn).toHaveAttribute('data-magnified', 'true');
    expect(gearBtn).toHaveAttribute('data-target-size', '58');
    expect(gearBtn.style.width).toBe('58px');
    expect(gearBtn.style.transform).toBe('translate3d(7.00px, 0, 0)');
    expect(topBtn).toHaveAttribute('data-magnified', 'false');

    // 5. Mouse leaves rail -> all items shrink smoothly back to 36px
    fireEvent.mouseLeave(dockRail);
    expect(topBtn).toHaveAttribute('data-target-size', '36');
    expect(navAppBtn).toHaveAttribute('data-target-size', '36');
    expect(gearBtn).toHaveAttribute('data-target-size', '36');
    expect(gearBtn.style.width).toBe('36px');
    expect(gearBtn.style.transform).toBe('translate3d(0.00px, 0, 0)');
  });

  it('renders rounded islands (Area 2 + 3a..3e with 3b1..3b4), inset resize handles, configurable panel spacing, and per-area zoom', async () => {
    const Component = withTheme(ShellHarness);
    render(<Component fetchImpl={jest.fn().mockResolvedValue({ok: false, status: 404})} />);

    // Backdrop Colour a wraps Area 2 and Area 3 with default 6px panel gap
    const backdrop = document.querySelector('[data-cdeadmin-qa-key="project-shell-backdrop"]');
    expect(backdrop).toHaveClass('sr-shell-backdrop');
    expect(backdrop.style.getPropertyValue('--sr-panel-gap')).toBe('6px');

    // Open Data Navigator and also open Right Side Drawer (3c) so all islands 3a, 3b, 3c, 3d, 3e are active
    fireEvent.click(screen.getByRole('button', {name: 'Open Data Navigator'}));
    fireEvent.click(screen.getByRole('menuitem', {name: 'Window'}));
    fireEvent.click(screen.getByRole('menuitemcheckbox', {name: 'Right Side Drawer'}));

    const island3a = document.querySelector('[data-area-part="3a"]');
    const island3b = document.querySelector('[data-area-part="3b"]');
    const island3c = document.querySelector('[data-area-part="3c"]');
    const island3d = document.querySelector('[data-area-part="3d"]');
    const island3e = document.querySelector('[data-area-part="3e"]');

    expect(island3a).toHaveClass('sr-island', 'sr-island-3a');
    expect(island3b).toHaveClass('sr-island', 'sr-island-3b');
    expect(island3c).toHaveClass('sr-island', 'sr-island-3c');
    expect(island3d).toHaveClass('sr-island', 'sr-island-3d');
    expect(island3e).toHaveClass('sr-island', 'sr-island-3e');

    // Verify spatial hierarchy:
    // - 3b sits at the top of .sr-area3-outer (above 3a + 3e + 3c)
    // - 3a sits in .sr-area3-lower-row alongside .sr-area3-center-right-col (so 3a extends to bottom)
    // - 3d sits in .sr-area3-center-right-col below .sr-area3-work-and-right-row (spanning under 3e + 3c)
    expect(island3b.parentElement).toHaveClass('sr-area3-outer');
    expect(island3a.parentElement).toHaveClass('sr-area3-lower-row');
    expect(island3e.parentElement).toHaveClass('sr-area3-work-and-right-row');
    expect(island3c.parentElement).toHaveClass('sr-area3-work-and-right-row');
    expect(island3d.parentElement).toHaveClass('sr-area3-center-right-col');

    // Verify 3b sub-parts:
    // - 3b1 (.snb-quick): New, Save, Undo, Redo quick-access buttons
    // - 3b2 (.snb-tabs) & 3b3 (.snb-tab[aria-selected="true"])
    // - 3b4 ([data-area-part="3b4"] close button)
    const quickBar = island3b.querySelector('.snb-quick');
    expect(quickBar).toBeInTheDocument();
    expect(quickBar.querySelectorAll('[data-snb-control]')).toHaveLength(4);
    expect(
      Array.from(quickBar.querySelectorAll('[data-snb-control]')).map((el) =>
        el.getAttribute('data-snb-control')
      )
    ).toEqual([
      'shell.quick.new',
      'shell.quick.save',
      'shell.quick.undo',
      'shell.quick.redo',
    ]);
    expect(island3b.querySelector('.snb-tabs')).toBeInTheDocument();
    expect(island3b.querySelector('.snb-tab[aria-selected="true"]')).toHaveTextContent(
      'Data Navigator'
    );
    expect(island3b.querySelector('[data-area-part="3b4"]')).toBeInTheDocument();

    // Verify inset short vertical line resize handles inside 3a (right edge) and 3c (left edge)
    const leftHandle = within(island3a).getByRole('separator', {
      name: 'Resize Left Side Drawer',
    });
    const rightHandle = within(island3c).getByRole('separator', {
      name: 'Resize Right Side Drawer',
    });
    expect(leftHandle).toHaveClass('sr-drawer-resize-handle', 'sr-drawer-resize-handle--left');
    expect(rightHandle).toHaveClass('sr-drawer-resize-handle', 'sr-drawer-resize-handle--right');

    // Drag/keyboard resize right drawer (inverted handle on left edge of 3c)
    expect(rightHandle).toHaveAttribute('aria-valuenow', '320');
    fireEvent.keyDown(rightHandle, {key: 'ArrowLeft', shiftKey: true});
    expect(rightHandle).toHaveAttribute('aria-valuenow', '336');

    // Configure Global panel_gap (12px) and per-area zoom (Area 1 = 115%, Area 2 = 125%, Area 3b = 110%, Area 3e = 120%)
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="side-menu-settings-gear"]'));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="gear-global-settings"]'));

    fireEvent.change(
      document.querySelector('[data-cdeadmin-qa-key="settings-global-panel-gap"]'),
      {target: {value: '12'}}
    );
    fireEvent.change(
      document.querySelector('[data-cdeadmin-qa-key="settings-global-zoom-area_1"]'),
      {target: {value: '115'}}
    );
    fireEvent.change(
      document.querySelector('[data-cdeadmin-qa-key="settings-global-zoom-area_2"]'),
      {target: {value: '125'}}
    );
    fireEvent.change(
      document.querySelector('[data-cdeadmin-qa-key="settings-global-zoom-area_3b"]'),
      {target: {value: '110'}}
    );
    fireEvent.change(
      document.querySelector('[data-cdeadmin-qa-key="settings-global-zoom-area_3e"]'),
      {target: {value: '120'}}
    );
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="settings-save"]'));

    await waitFor(() => {
      expect(backdrop.style.getPropertyValue('--sr-panel-gap')).toBe('12px');
      expect(backdrop.style.getPropertyValue('--sr-zoom-3b')).toBe('1.1');
      expect(backdrop.style.getPropertyValue('--sr-zoom-3e')).toBe('1.2');
    });

    const navBar = document.querySelector('[data-cdeadmin-qa-key="project-top-menu"]');
    const dockRail = document.querySelector('[data-cdeadmin-qa-key="project-side-menu"]');
    expect(navBar.style.getPropertyValue('--sr-area1-zoom')).toBe('1.15');
    expect(dockRail.style.getPropertyValue('--sr-vdock-zoom')).toBe('1.25');

    // Override panel_gap (4px) and Area 3e zoom (135%) specifically for Data Navigator in Application Settings
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="side-menu-settings-gear"]'));
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="gear-application-settings"]'));
    fireEvent.change(
      document.querySelector('[data-cdeadmin-qa-key="settings-app-panel-gap"]'),
      {target: {value: '4'}}
    );
    fireEvent.change(
      document.querySelector('[data-cdeadmin-qa-key="settings-app-zoom-area_3e"]'),
      {target: {value: '135'}}
    );
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="settings-save"]'));

    await waitFor(() => {
      expect(backdrop.style.getPropertyValue('--sr-panel-gap')).toBe('4px');
      expect(backdrop.style.getPropertyValue('--sr-zoom-3e')).toBe('1.35');
      // Area 3b inherits global 110% since Data Navigator left 3b blank
      expect(backdrop.style.getPropertyValue('--sr-zoom-3b')).toBe('1.1');
    });
  });
});
