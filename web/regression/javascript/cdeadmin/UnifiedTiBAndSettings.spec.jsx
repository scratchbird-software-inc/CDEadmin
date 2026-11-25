/////////////////////////////////////////////////////////////
//
// ScratchRobin — Unified Tabbed-Icon-Bar, Focus/Blur Restoration & Global Settings Regression Suite
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {
  ProjectShellProvider,
  ProjectTopMenuBar,
  ProjectWorkbenchFrame,
  USER_DASHBOARD_ID,
  useProjectShell,
} from 'sources/cdeadmin_ui/shell';
import {ActionMenuToolbarEditor} from 'sources/cdeadmin_ui/shell/settings/ActionMenuToolbarEditor';
import {
  TActionsRegistry,
  T_ACTION_STATUS,
  T_ACTION_TARGET_KIND,
  seedStandardTiBActions,
} from 'sources/cdeadmin_ui/actions/t_actions';
import {ProjectTopMenuRegistry} from 'sources/cdeadmin_ui/commands/MenuStructure';
import {listIconDefinitions} from 'sources/cdeadmin_ui/icons';
import {DesignerTabbedMenu} from 'sources/cdeadmin_ui/integrations/ddn/DesignerChrome';
import {
  STANDARD_TIB_ACTIONS,
  STANDARD_TIB_SECTIONS,
} from 'sources/cdeadmin_ui/shell/tibStandardConfig';

function getTopMenuNames(menuRegistry) {
  return menuRegistry
    .resolve()
    .filter((m) => !m.isSystemIcon)
    .map((m) => m.label);
}

describe('Unified Tabbed-Icon-Bar (TiB), Focus/Blur Restoration & Global Settings', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('registers all 242 three-tone tib.* icons, 26 standard sections, and 232 canonical TiB actions', () => {
    const allIcons = listIconDefinitions();
    const tibIcons = allIcons.filter((d) => d.key.startsWith('tib.'));
    expect(tibIcons.length).toBeGreaterThanOrEqual(242);
    expect(STANDARD_TIB_SECTIONS.length).toBeGreaterThanOrEqual(26);
    expect(STANDARD_TIB_ACTIONS.length).toBeGreaterThanOrEqual(232);

    const reg = new TActionsRegistry();
    seedStandardTiBActions(reg);
    expect(reg.has('tib.exec.execute_sql')).toBe(true);
    expect(reg.has('tib.tx.commit')).toBe(true);
    expect(reg.resolve('tib.tx.commit').icon).toBe('tib.commit');
  });

  it('hides the sub-tab bar when a workspace has 1 sub-tab and shows it when > 1 sub-tabs, and updates all workspaces from one Settings change', async () => {
    let shellApi = null;
    function Probe() {
      shellApi = useProjectShell();
      return null;
    }

    const actionsRegistry = new TActionsRegistry();
    const menuRegistry = new ProjectTopMenuRegistry();
    const Harness = withTheme(() => (
      <ProjectShellProvider
        actionsRegistry={actionsRegistry}
        menuRegistry={menuRegistry}
        fetchImpl={jest.fn(async () => ({ok: false, status: 404, json: async () => ({})}))}
      >
        <Probe />
        <ProjectWorkbenchFrame />
      </ProjectShellProvider>
    ));

    const {container} = render(<Harness />);

    // 1. Open a single-sub-tab workspace (e.g. Terminal / Connectors)
    act(() => {
      shellApi.openInlineTab({
        instanceId: 'cli-1',
        appId: 'command-line',
        title: 'Command Line',
        supportsTabbedIconBar: true,
        actions: [
          {
            id: 'cli.exec.1',
            icon: 'tib.execute_statement',
            defaultText: 'Execute Statement',
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => {}},
          },
          {
            id: 'cli.clear.1',
            icon: 'tib.clear_filters',
            defaultText: 'Clear Console',
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => {}},
          },
        ],
        ribbonTabs: [
          {
            id: 'cli-home',
            label: 'Terminal',
            groups: [
              {
                id: 'cli-exec',
                sectionId: 'SEC-EXEC',
                label: 'Query Execution',
                controls: ['cli.exec.1', 'cli.clear.1'],
              },
            ],
          },
        ],
      });
    });

    // Single sub-tab workspace hides the sub-tab strip by default (`multi_only`)
    expect(container.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]')).toBeNull();
    const execGroup = container.querySelector('.sr-island-3b .snb-group[data-section-id="SEC-EXEC"]');
    expect(execGroup).not.toBeNull();
    expect(execGroup.querySelector('.snb-group-icon')).not.toBeNull();

    // 2. Open a multi-sub-tab workspace (e.g. Data Viewer with 2 sub-tabs)
    act(() => {
      shellApi.openInlineTab({
        instanceId: 'dv-1',
        appId: 'data-navigator',
        title: 'data: ORDERS',
        supportsTabbedIconBar: true,
        useUnderTabs: true,
        actions: [
          {
            id: 'dv.commit.1',
            icon: 'tib.commit',
            defaultText: 'Commit',
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => {}},
          },
          {
            id: 'dv.autofit.1',
            icon: 'tib.auto_fit_columns',
            defaultText: 'Auto-Fit',
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => {}},
          },
        ],
        ribbonTabs: [
          {
            id: 'dv-data',
            label: 'Data',
            isUnderTab: true,
            groups: [
              {
                id: 'tx',
                sectionId: 'SEC-TX',
                label: 'Transaction',
                controls: ['dv.commit.1'],
              },
            ],
          },
          {
            id: 'dv-fmt',
            label: 'Format & Layout',
            isUnderTab: true,
            groups: [
              {
                id: 'cols',
                sectionId: 'SEC-COLTEXT',
                label: 'Columns & Text',
                controls: ['dv.autofit.1'],
              },
            ],
          },
        ],
      });
    });

    // Multi-sub-tab workspace shows the sub-tab strip!
    const undertabs = container.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]');
    expect(undertabs).not.toBeNull();
    expect(within(undertabs).getAllByRole('tab').map((t) => t.textContent)).toEqual([
      'Data',
      'Format & Layout',
    ]);

    // 3. Change `subtab_visibility` + `section_height_px` + `show_section_headers` globally in Settings ->
    //    single change updates BOTH `dv-1` and `cli-1`!
    await act(async () => {
      await shellApi.saveShellSettings({
        scope: 'global',
        values: {
          tib_config: {
            subtab_visibility: 'always',
            section_height_px: 96,
            show_section_headers: false,
          },
          tib_sections: {
            'SEC-TX': {label: 'ACID Controls'},
          },
        },
      });
    });

    const bar3b = container.querySelector('.sr-island-3b');
    expect(bar3b.style.getPropertyValue('--tib-section-height')).toContain('96px');
    expect(bar3b).toHaveAttribute('data-tib-headers', 'false');
    expect(within(bar3b).getByText('ACID Controls')).toBeInTheDocument();

    // Switch back to single-sub-tab `cli-1`: because `subtab_visibility` is now `'always'`, its sub-tab strip is shown AND height is 96px!
    act(() => {
      shellApi.focusInstance('cli-1');
    });
    expect(container.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]')).not.toBeNull();
    expect(
      container.querySelector('.sr-island-3b').style.getPropertyValue('--tib-section-height')
    ).toContain('96px');
  });

  it('mounts workspace-specific menu items, sub-tabs, and sections on focus and removes/restores originals on focus loss', async () => {
    let shellApi = null;
    function Probe() {
      shellApi = useProjectShell();
      return null;
    }

    function ErdMockWorkspace() {
      return (
        <div>
          <DesignerTabbedMenu
            label="ERD Designer"
            tabs={[
              {
                id: 'lifecycle',
                label: 'Model & Lifecycle',
                groups: [
                  {
                    id: 'gov',
                    sectionId: 'SEC-GOV',
                    label: 'Checkpoints',
                    items: [{id: 'save_cp', label: 'Save Checkpoint', icon: 'tib.save_checkpoint', onClick: () => {}}],
                  },
                ],
              },
              {
                id: 'levels',
                label: 'Levels & Roles',
                groups: [
                  {
                    id: 'mod',
                    sectionId: 'SEC-ERD-MOD',
                    label: 'Modelling Levels',
                    items: [{id: 'add_ent', label: 'Add Entity', icon: 'tib.erd_add_entity', onClick: () => {}}],
                  },
                ],
              },
            ]}
          />
          <div data-testid="erd-canvas">ERD Work Area</div>
        </div>
      );
    }

    const actionsRegistry = new TActionsRegistry();
    const menuRegistry = new ProjectTopMenuRegistry();
    const Harness = withTheme(() => (
      <ProjectShellProvider
        actionsRegistry={actionsRegistry}
        menuRegistry={menuRegistry}
        userDashboard={<div>Dashboard Home</div>}
        fetchImpl={jest.fn(async () => ({ok: false, status: 404, json: async () => ({})}))}
      >
        <Probe />
        <ProjectTopMenuBar />
        <ProjectWorkbenchFrame />
      </ProjectShellProvider>
    ));

    const {container} = render(<Harness />);

    // Baseline state before any workspace has focus: ONLY Applications, Window, Help
    expect(getTopMenuNames(menuRegistry)).toEqual(['Applications', 'Window', 'Help']);
    const baselineWindowItems = menuRegistry
      .resolve()
      .find((m) => m.name === 'window')
      .items.map((it) => it.label);
    expect(baselineWindowItems).toContain('Rename Active Tab…');
    expect(baselineWindowItems).not.toContain('SQL Connection Details…');

    // 1. Focus Workspace A (`SQL Editor`): mounts Query & Edit menus, overrides Rename slot in Window, mounts SQL sub-tabs & sections
    act(() => {
      shellApi.openInlineTab({
        instanceId: 'sql-ws-1',
        appId: 'sql-editor',
        title: 'sql: billing',
        supportsTabbedIconBar: true,
        useUnderTabs: true,
        actions: [
          {
            id: 'sql.ws1.exec',
            icon: 'tib.execute_statement',
            defaultText: 'Execute Statement',
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => {}},
          },
          {
            id: 'sql.ws1.fmt',
            icon: 'tib.format_sql',
            defaultText: 'Format SQL',
            focusScoped: true,
            target: {kind: T_ACTION_TARGET_KIND.CLIENT, invoke: () => {}},
          },
        ],
        menus: [
          {
            name: 'query',
            label: 'Query',
            index: 15,
            items: [{id: 'm.exec', actionId: 'sql.ws1.exec', label: 'Execute Statement', index: 10}],
          },
          {
            name: 'window',
            label: 'Window',
            index: 70,
            items: [
              {
                id: 'sql.ws1.rename',
                replacesId: 'shell.window.rename_tab',
                label: 'Rename SQL Tab… (F2)',
                index: 41,
                callback: () => {},
              },
              {
                id: 'sql.ws1.conn_info',
                label: 'SQL Connection Details…',
                index: 92,
                callback: () => {},
              },
            ],
          },
        ],
        ribbonTabs: [
          {
            id: 'sql-q',
            label: 'Query',
            isUnderTab: true,
            groups: [{id: 'exec', sectionId: 'SEC-EXEC', label: 'Query Execution', controls: ['sql.ws1.exec']}],
          },
          {
            id: 'sql-fmt',
            label: 'Format & Layout',
            isUnderTab: true,
            groups: [{id: 'fmt', sectionId: 'SEC-VALFMT', label: 'SQL & Values', controls: ['sql.ws1.fmt']}],
          },
        ],
      });
    });

    expect(getTopMenuNames(menuRegistry)).toEqual(['Query', 'Applications', 'Window', 'Help']);
    const sqlWindowItems = menuRegistry
      .resolve()
      .find((m) => m.name === 'window')
      .items.map((it) => it.label);
    expect(sqlWindowItems).toContain('Rename SQL Tab… (F2)');
    expect(sqlWindowItems).not.toContain('Rename Active Tab…');
    expect(sqlWindowItems).toContain('SQL Connection Details…');

    // Switch SQL Editor to its 2nd sub-tab (`Format & Layout`)
    const sqlSubTabs = within(
      container.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]')
    ).getAllByRole('tab');
    fireEvent.click(sqlSubTabs[1]);
    expect(within(container.querySelector('.sr-island-3b')).getByRole('button', {name: 'Format SQL'})).toBeInTheDocument();

    // 2. Focus Workspace B (`ERD Designer`): removes SQL menus/items/sub-tabs/sections, restores original Window items, mounts ERD sub-tabs & menus!
    act(() => {
      shellApi.openInlineTab({
        instanceId: 'erd-ws-1',
        appId: 'erd-designer',
        title: 'erd: core',
        supportsTabbedIconBar: true,
        menus: [
          {
            name: 'model',
            label: 'Model',
            index: 30,
            items: [{id: 'erd.new', label: 'New Data Model', index: 10, callback: () => {}}],
          },
        ],
        renderWorkArea: () => <ErdMockWorkspace />,
      });
    });

    await waitFor(() =>
      expect(
        within(container.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]'))
          .getAllByRole('tab')
          .map((t) => t.textContent)
      ).toEqual(['Model & Lifecycle', 'Levels & Roles'])
    );

    // Outgoing SQL menus removed, Model menu mounted, original Window menu items restored!
    expect(getTopMenuNames(menuRegistry)).toEqual(['Model', 'Applications', 'Window', 'Help']);
    const erdWindowItems = menuRegistry
      .resolve()
      .find((m) => m.name === 'window')
      .items.map((it) => it.label);
    expect(erdWindowItems).toContain('Rename Active Tab…');
    expect(erdWindowItems).not.toContain('Rename SQL Tab… (F2)');
    expect(erdWindowItems).not.toContain('SQL Connection Details…');

    // Outgoing SQL actions are hidden (`invisible`) while unfocused
    expect(actionsRegistry.resolve('sql.ws1.exec').visible).toBe(false);
    expect(within(container.querySelector('.sr-island-3b')).queryByRole('button', {name: 'Format SQL'})).toBeNull();
    expect(within(container.querySelector('.sr-island-3b')).getByRole('button', {name: 'Save Checkpoint'})).toBeInTheDocument();

    // 3. Focus User Dashboard (both workspaces lose focus): ALL workspace menus, sub-tabs, and sections removed; baseline restored!
    act(() => {
      shellApi.openUserDashboardTab();
    });
    expect(shellApi.focusedId).toBe(USER_DASHBOARD_ID);
    expect(getTopMenuNames(menuRegistry)).toEqual(['Applications', 'Window', 'Help']);
    expect(container.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]')).toBeNull();
    expect(container.querySelector('.sr-island-3b .snb-panel')).toBeNull();

    // 4. Re-focus Workspace A (`sql-ws-1`): restores its Query menu, its `Format & Layout` sub-tab selection, and its sections!
    act(() => {
      shellApi.focusInstance('sql-ws-1');
    });
    expect(getTopMenuNames(menuRegistry)).toEqual(['Query', 'Applications', 'Window', 'Help']);
    expect(actionsRegistry.resolve('sql.ws1.fmt').visible).toBe(true);
    expect(within(container.querySelector('.sr-island-3b')).getByRole('button', {name: 'Format SQL'})).toBeInTheDocument();
  });

  it('edits an action’s text, icon, hint, status, and callable code target from one Settings location and updates live execution', async () => {
    const actionsRegistry = new TActionsRegistry();
    seedStandardTiBActions(actionsRegistry);

    const handlerAlpha = jest.fn(() => 'alpha');
    const handlerBeta = jest.fn(() => 'beta');
    actionsRegistry.registerCallableTarget('custom.alpha', handlerAlpha, {
      label: 'Alpha Handler',
      category: 'Custom',
    });
    actionsRegistry.registerCallableTarget('custom.beta', handlerBeta, {
      label: 'Beta Handler',
      category: 'Custom',
    });

    actionsRegistry.upsert({
      id: 'tib.exec.execute_sql',
      icon: 'tib.execute_statement',
      application: 'tib',
      defaultText: 'Execute Statement',
      defaultHint: 'Execute active statement',
      target: {
        kind: T_ACTION_TARGET_KIND.CLIENT,
        handlerId: 'custom.alpha',
        invoke: handlerAlpha,
      },
    });

    const onChangeGlobal = jest.fn();
    const Editor = withTheme(ActionMenuToolbarEditor);
    render(
      <Editor
        subView="icons"
        actionsRegistry={actionsRegistry}
        onChangeGlobal={onChangeGlobal}
      />
    );

    // Filter down to `tib.exec.execute_sql` (<= 5 results auto-expands full inline editor!)
    const searchInput = screen.getByPlaceholderText(/Search by action ID/i);
    fireEvent.change(searchInput, {target: {value: 'tib.exec.execute_sql'}});

    const row = document.querySelector('[data-cdeadmin-qa-key="action-icon-row-tib.exec.execute_sql"]');
    expect(row).not.toBeNull();

    // 1. Update text & hint
    fireEvent.change(within(row).getByLabelText('Button text for tib.exec.execute_sql'), {
      target: {value: 'Run Active SQL'},
    });
    fireEvent.change(within(row).getByLabelText('Hint for tib.exec.execute_sql'), {
      target: {value: 'Runs statement via reassigned handler'},
    });
    fireEvent.change(within(row).getByLabelText('Shortcut for tib.exec.execute_sql'), {
      target: {value: 'Ctrl+Enter'},
    });

    expect(actionsRegistry.resolve('tib.exec.execute_sql').text).toBe('Run Active SQL');
    expect(actionsRegistry.resolve('tib.exec.execute_sql').hint).toBe(
      'Runs statement via reassigned handler'
    );
    expect(actionsRegistry.resolve('tib.exec.execute_sql').shortcut).toBe('Ctrl+Enter');

    // 2. Reassign callable code target (`custom.alpha` -> `custom.beta`) via Settings
    actionsRegistry.setActionDefinitions({
      ...actionsRegistry.getActionDefinitions(),
      'tib.exec.execute_sql': {
        ...actionsRegistry.getActionDefinitions()['tib.exec.execute_sql'],
        icon: 'tib.execute_script',
        target: {kind: 'client', handlerId: 'custom.beta'},
      },
    });

    expect(actionsRegistry.resolve('tib.exec.execute_sql').icon).toBe('tib.execute_script');
    const result = await actionsRegistry.execute('tib.exec.execute_sql', {row: 1});
    expect(result).toBe('beta');
    expect(handlerBeta).toHaveBeenCalledTimes(1);
    expect(handlerAlpha).not.toHaveBeenCalled();

    // 3. Switch target to Server Endpoint & verify fetch invocation, then test Disabled status
    const mockFetch = jest.fn(async () => ({
      ok: true,
      json: async () => ({ok: true, serverRan: true}),
    }));
    const srvRegistry = new TActionsRegistry({fetchImpl: mockFetch});
    seedStandardTiBActions(srvRegistry);
    srvRegistry.setActionDefinitions({
      'tib.tx.commit': {
        text: 'Server Commit',
        target: {kind: 'server', endpoint: '/cdeadmin/api/custom/commit', method: 'PUT'},
      },
    });
    const srvRes = await srvRegistry.execute('tib.tx.commit', {tx: 42});
    expect(srvRes).toEqual({ok: true, serverRan: true});
    expect(mockFetch).toHaveBeenCalledWith(
      '/cdeadmin/api/custom/commit',
      expect.objectContaining({method: 'PUT'})
    );

    srvRegistry.setActionDefinitions({
      'tib.tx.commit': {status: T_ACTION_STATUS.DISABLED},
    });
    expect(srvRegistry.resolve('tib.tx.commit').enabled).toBe(false);
    await expect(srvRegistry.execute('tib.tx.commit')).rejects.toThrow(/disabled/i);
  });
});
