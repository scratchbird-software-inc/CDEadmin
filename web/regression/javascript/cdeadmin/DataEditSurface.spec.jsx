/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {useEffect} from 'react';
import {act, fireEvent, render, screen, within} from '@testing-library/react';
import '@testing-library/jest-dom';
import {withTheme} from '../fake_theme';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import {
  ProjectShellProvider,
  ProjectTopMenuBar,
  ProjectWorkbenchFrame,
  useProjectShell,
} from '../../../pgadmin/static/js/cdeadmin_ui/shell';
import DataEditSurface from '../../../pgadmin/static/js/cdeadmin_ui/surfaces/DataEditSurface';
import ProviderWorkspaceContent from '../../../pgadmin/static/js/Dialogs/ProviderWorkspaceContent';
import getApiInstance from '../../../pgadmin/static/js/api_instance';

jest.mock('../../../pgadmin/static/js/api_instance');

const TestShell = withTheme(({children}) => (
  <ProjectShellProvider username="dba@scratchrobin.org">
    {children}
    <ProjectTopMenuBar />
    <div style={{height: 680}}>
      <ProjectWorkbenchFrame />
    </div>
  </ProjectShellProvider>
));

function makeHostFixture(overrides = {}) {
  const stagedList = overrides.staged_sql || [];
  const hasActivity = Boolean(
    overrides.has_uncommitted_activity ?? stagedList.length > 0
  );
  return {
    surface_id: 'ds-data-account',
    has_uncommitted_activity: hasActivity,
    engine_id: 'firebird',
    language_profile: 'firebird-sql',
    database_target_id: 'frappe_suite.fdb',
    target_resource: {
      resource_id: 'table:ACCOUNT',
      resource_kind: 'table',
      display_name: 'ACCOUNT',
      name: 'ACCOUNT',
    },
    editable: true,
    identity_policy: 'primary-key',
    row_operations: ['insert', 'update', 'delete'],
    autocommit: false,
    page_size: 200,
    max_rows: 1000,
    window_offset: 0,
    window_size: 200,
    total_buffered_rows: 2,
    total_view_rows: 2,
    complete_in_buffer: true,
    retrieval_limited: false,
    sort_mode: 'auto',
    sort_execution: 'local',
    sorts: overrides.sorts || [],
    filters: overrides.filters || [],
    columns: [
      {
        name: 'ID',
        native_type: 'INTEGER',
        client_type: 'integer',
        default_alignment: 'right',
        nullable: false,
        key: true,
        editable: false,
        insertable: true,
        comment: 'Primary key ID',
      },
      {
        name: 'ACCOUNT_NAME',
        native_type: 'VARCHAR(120)',
        client_type: 'text',
        default_alignment: 'left',
        nullable: false,
        key: false,
        editable: true,
        insertable: true,
        domain_name: 'DM_LEDGER_NAME',
        comment: 'Ledger account display name',
      },
      {
        name: 'IS_ACTIVE',
        native_type: 'BOOLEAN',
        client_type: 'boolean',
        default_alignment: 'center',
        nullable: false,
        key: false,
        editable: true,
        insertable: true,
      },
      {
        name: 'BALANCE',
        native_type: 'NUMERIC(14,2)',
        client_type: 'decimal',
        default_alignment: 'right',
        nullable: true,
        key: false,
        editable: true,
        insertable: true,
      },
      {
        name: 'PAYLOAD_BLOB',
        native_type: 'BLOB SUB_TYPE TEXT',
        client_type: 'blob',
        default_alignment: 'left',
        is_complex: true,
        nullable: true,
        key: false,
        editable: true,
        insertable: true,
      },
    ],
    rows: overrides.rows || [
      {
        row_number: 1,
        base_row_index: 0,
        identity_token: 'pk:1',
        values: {
          ID: 1,
          ACCOUNT_NAME: 'Cash On Hand',
          IS_ACTIVE: true,
          BALANCE: 1250.5,
          PAYLOAD_BLOB: '{"branch":"HQ","vault":true}',
        },
        original_values: {
          ID: 1,
          ACCOUNT_NAME: 'Cash On Hand',
          IS_ACTIVE: true,
          BALANCE: 1250.5,
          PAYLOAD_BLOB: '{"branch":"HQ","vault":true}',
        },
        stage_state: null,
        mutation_id: null,
      },
      {
        row_number: 2,
        base_row_index: 1,
        identity_token: 'pk:2',
        values: {
          ID: 2,
          ACCOUNT_NAME: 'Dormant Suspense',
          IS_ACTIVE: false,
          BALANCE: null,
          PAYLOAD_BLOB: null,
        },
        original_values: {
          ID: 2,
          ACCOUNT_NAME: 'Dormant Suspense',
          IS_ACTIVE: false,
          BALANCE: null,
          PAYLOAD_BLOB: null,
        },
        stage_state: null,
        mutation_id: null,
      },
    ],
    fields_grid: [
      {
        ordinal: 1,
        name: 'ID',
        key: true,
        native_type: 'INTEGER',
        domain_type: '—',
        nullable: false,
        default_expr: '—',
        charset: '—',
        collation: '—',
        client_type: 'integer',
        default_alignment: 'right',
        editable: false,
        insertable: true,
        is_complex: false,
        comment: 'Primary key ID',
      },
      {
        ordinal: 2,
        name: 'ACCOUNT_NAME',
        key: false,
        native_type: 'VARCHAR(120)',
        domain_type: 'DM_LEDGER_NAME',
        nullable: false,
        default_expr: '—',
        charset: 'UTF8',
        collation: 'UNICODE_CI',
        client_type: 'text',
        default_alignment: 'left',
        editable: true,
        insertable: true,
        is_complex: false,
        comment: 'Ledger account display name',
      },
    ],
    sql_view: {
      server_sql: 'SELECT "ID", "ACCOUNT_NAME", "IS_ACTIVE", "BALANCE", "PAYLOAD_BLOB"\nFROM "ACCOUNT"',
      parameters: [],
      sort_execution: 'local',
      sort_mode: 'auto',
      is_local_sort_or_filter: Boolean((overrides.sorts || []).length),
      local_operations_summary: (overrides.sorts || []).length
        ? 'Local host-cached sort: ACCOUNT_NAME ASC'
        : 'Executed directly on database server',
      staged_sql: stagedList,
    },
    metrics_view: {
      timings_ms: {
        prepare_ms: 1.4,
        execute_ms: 4.2,
        fetch_ms: 2.1,
        host_sort_filter_ms: 0.3,
        total_ms: 8.0,
      },
      buffer: {
        buffered_rows: 2,
        visible_rows: 2,
        complete_in_buffer: true,
        retrieval_limited: false,
        host_memory_bytes: 1024,
        page_size: 200,
        max_rows: 1000,
      },
      transaction: {
        session_id: 'fb-sess-1',
        autocommit: false,
        staged_inserts: 0,
        staged_updates: stagedList.length,
        staged_deletes: 0,
        staged_total: stagedList.length,
        has_uncommitted_activity: hasActivity,
        provider_observation: {in_transaction: true, transaction_id: 412},
      },
      plan_text: 'PLAN (INDEX ("ACCOUNT" PK [ID]))',
      plan_nodes: [
        {
          id: 'plan-root',
          operation: 'SELECT / FETCH',
          target: '"ACCOUNT"',
          strategy: 'PK Indexed Order',
          rows_buffered: 2,
          sort_location: 'Host Cache (Local)',
          elapsed_ms: 8.0,
        },
      ],
    },
    messages: [
      {
        id: 'msg-err-1',
        timestamp: '2026-11-16T20:00:00Z',
        severity: 'warning',
        operation: 'Validation',
        elapsed_ms: 1.1,
        message: 'Check balance on Dormant Suspense',
        sqlstate: '01000',
        native_code: '',
        row_index: 1,
        column_name: 'BALANCE',
      },
    ],
    saved_specific_layout: null,
    ...overrides,
  };
}

function ShellLauncher({post, onShellReady}) {
  const shell = useProjectShell();
  useEffect(() => {
    if (!shell) return;
    onShellReady?.(shell);
    if (!shell.instances.some((i) => i.instanceId === 'data-account')) {
      shell.openInlineTab({
        instanceId: 'data-account',
        appId: 'data-navigator',
        title: 'data: ACCOUNT',
        closable: true,
        supportsLeftDrawer: true,
        supportsRightDrawer: true,
        supportsTabbedIconBar: true,
        renderWorkArea: () => (
          <DataEditSurface
            endpointLabel="Firebird localhost / frappe_suite.fdb"
            engineId="firebird"
            languageProfile="firebird-sql"
            databaseTargetId="frappe_suite.fdb"
            targetResource={{
              resource_id: 'table:ACCOUNT',
              resource_kind: 'table',
              display_name: 'ACCOUNT',
              name: 'ACCOUNT',
            }}
            post={post}
          />
        ),
      });
    }
  }, [shell, post, onShellReady]);
  return null;
}

describe('Surface 1: DataEditSurface (Browse & Edit Data)', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    usePreferences.setState({
      data: [{id: 1, cid: 1, mid: 1, module: 'misc', name: 'theme', value: 'light'}],
      version: Date.now(),
      isLoading: false,
      failed: false,
    });
  });

  it('renders 100% Area 3e surface with MS-grouped TiB, Under-Tabs, Segmented Pills, 5 Display Modes, 4 Companion Views & Right Drawer 3b', async () => {
    const post = jest.fn(async ({request}) => {
      if (request.surface_action === 'sort_filter') {
        return makeHostFixture({sorts: request.sorts || []});
      }
      if (request.surface_action === 'stage_row') {
        return makeHostFixture({
          has_uncommitted_activity: true,
          staged_sql: [
            {
              mutation_id: 'row-0',
              op: 'update',
              row_key: 'row-0',
              sql: 'UPDATE "ACCOUNT" SET "ACCOUNT_NAME" = \'Main Vault\' WHERE "ID" = 1',
            },
          ],
        });
      }
      return makeHostFixture();
    });

    render(
      <TestShell>
        <ShellLauncher post={post} />
      </TestShell>
    );

    // Wait for grid to load buffered rows
    expect(await screen.findByText('Cash On Hand')).toBeInTheDocument();

    // Formatting checks: <null>, T/F booleans, and [...] complex blob trigger
    expect(screen.getAllByText('<null>').length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText('T')).toBeInTheDocument();
    expect(screen.getByText('F')).toBeInTheDocument();

    // Under-tabs exist on TiB: Data | Format & Layout | Transfer & SQL
    const underTabs = screen.getByTestId
      ? document.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]')
      : null;
    expect(underTabs).toBeTruthy();
    expect(within(underTabs).getByRole('tab', {name: 'Data'})).toBeInTheDocument();
    expect(within(underTabs).getByRole('tab', {name: 'Format & Layout'})).toBeInTheDocument();
    expect(within(underTabs).getByRole('tab', {name: 'Transfer & SQL'})).toBeInTheDocument();

    // Clicking [...] opens Right Drawer 3b in Viewing Mode with JSON payload
    const complexBtn = screen.getByRole('button', {name: 'PAYLOAD_BLOB [...]'});
    fireEvent.click(complexBtn);
    const rightDrawer = await screen.findByLabelText(/data: ACCOUNT Right Drawer/i);
    expect(within(rightDrawer).getByText(/Viewing Mode/i)).toBeInTheDocument();
    expect(within(rightDrawer).getByText(/HQ/)).toBeInTheDocument();

    // Switch Display Mode pill to Mini-Forms, Hybrid, and Single Form
    fireEvent.click(screen.getByRole('radio', {name: 'Mini-Forms'}));
    await act(async () => {});
    expect(document.querySelector('[data-cdeadmin-qa-key="data-surface-mini-forms-list"]')).toBeTruthy();

    fireEvent.click(screen.getByRole('radio', {name: 'Hybrid (Grid + Current Mini-Form)'}));
    await act(async () => {});
    expect(document.querySelector('[data-cdeadmin-qa-key="data-surface-hybrid-pinned-form"]')).toBeTruthy();

    fireEvent.click(screen.getByRole('radio', {name: 'Single Form (100% Area)'}));
    await act(async () => {});
    expect(document.querySelector('[data-cdeadmin-qa-key="data-surface-record-form-1"]')).toBeTruthy();

    fireEvent.click(screen.getByRole('radio', {name: 'Standard Grid'}));
    await act(async () => {});
    expect(document.querySelector('[data-cdeadmin-qa-key="data-surface-standard-grid"]')).toBeTruthy();

    // Switch Companion Views via Surface Content Pill: Metrics -> SQL -> Fields -> Messages
    fireEvent.click(screen.getByRole('radio', {name: 'Metrics & Plan'}));
    expect(await screen.findByText(/Server Execute Time/i)).toBeInTheDocument();
    expect(screen.getByText(/PLAN \(INDEX \("ACCOUNT" PK \[ID\]\)\)/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', {name: 'SQL'}));
    expect(await screen.findByLabelText(/Active Server Retrieval SQL/i)).toBeInTheDocument();
    expect(screen.getByText(/LOCAL HOST-CACHED SORT \/ FILTER/i)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', {name: 'Fields'}));
    expect(await screen.findByText('DM_LEDGER_NAME')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('radio', {name: 'Messages & Log'}));
    expect(await screen.findByText(/Check balance on Dormant Suspense/i)).toBeInTheDocument();

    // Jump-back in Messages returns directly to Data view on Row #2!
    fireEvent.click(screen.getByText(/Jump to Row #2/i));
    expect(document.querySelector('[data-cdeadmin-qa-key="data-surface-standard-grid"]')).toBeTruthy();
  });

  it('merges Surface 1 menus (Data 15, Edit 20, View 25, Window 70) on focus and removes them when focus leaves', async () => {
    let shellRef = null;
    const post = jest.fn(async () => makeHostFixture());

    render(
      <TestShell>
        <ShellLauncher post={post} onShellReady={(s) => { shellRef = s; }} />
      </TestShell>
    );

    expect(await screen.findByText('Cash On Hand')).toBeInTheDocument();

    const topMenuBar = document.querySelector('[data-cdeadmin-qa-key="project-top-menu"]');
    expect(topMenuBar).toBeTruthy();
    expect(within(topMenuBar).getByText('Data')).toBeInTheDocument();
    expect(within(topMenuBar).getByText('Edit')).toBeInTheDocument();
    expect(within(topMenuBar).getByText('View')).toBeInTheDocument();
    expect(within(topMenuBar).getByText('Window')).toBeInTheDocument();

    // Open a second Surface without Data/Edit/View menus -> outgoing Surface menus unmerge!
    act(() => {
      shellRef.openInlineTab({
        instanceId: 'other-surface',
        appId: 'project-explorer',
        title: 'Project Explorer',
        closable: true,
        menus: [{name: 'project', label: 'Project', index: 10, items: []}],
        renderWorkArea: () => <div>Other Surface Active</div>,
      });
    });

    expect(await screen.findByText('Other Surface Active')).toBeInTheDocument();
    expect(within(topMenuBar).getByText('Project')).toBeInTheDocument();
    expect(within(topMenuBar).queryByText('Data')).not.toBeInTheDocument();
    expect(within(topMenuBar).queryByText('Edit')).not.toBeInTheDocument();
    expect(within(topMenuBar).queryByText('View')).not.toBeInTheDocument();

    // Refocusing data: ACCOUNT restores Data, Edit, View by index!
    act(() => {
      shellRef.focusInstance('data-account');
    });
    expect(await screen.findByText('Cash On Hand')).toBeInTheDocument();
    expect(within(topMenuBar).getByText('Data')).toBeInTheDocument();
    expect(within(topMenuBar).getByText('Edit')).toBeInTheDocument();
    expect(within(topMenuBar).getByText('View')).toBeInTheDocument();
    expect(within(topMenuBar).queryByText('Project')).not.toBeInTheDocument();
  });

  it('removes legacy chrome and SR-F-000001 badge when ProviderWorkspaceContent opens tab="data" inside ProjectShell', async () => {
    getApiInstance.mockReturnValue({
      get: jest.fn().mockResolvedValue({
        data: {
          data: {
            endpoint: {
              endpoint_id: 'fb-1',
              display_name: 'Firebird Local',
              profile_id: 'firebird-native',
              verified_runtime_family: 'firebird',
            },
            languages: [{language_profile: 'firebird-sql', title: 'Firebird SQL'}],
            visual_admin: {model_family: 'relational'},
            resource_page: {
              generation: 'g1',
              items: [
                {
                  resource_id: 'table:ACCOUNT',
                  resource_kind: 'table',
                  display_name: 'ACCOUNT',
                  name: 'ACCOUNT',
                },
              ],
            },
          },
        },
      }),
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'data_surface_action') {
          return {data: {data: makeHostFixture()}};
        }
        return {data: {data: {}}};
      }),
    });

    function WorkspaceShellHarness() {
      const shell = useProjectShell();
      useEffect(() => {
        if (!shell || shell.instances.some((i) => i.instanceId === 'ws-data')) return;
        shell.openInlineTab({
          instanceId: 'ws-data',
          appId: 'data-navigator',
          title: 'data: ACCOUNT',
          closable: true,
          renderWorkArea: () => (
            <ProviderWorkspaceContent
              closeModal={jest.fn()}
              endpointUrl="/browser/server/workspace/1/7"
              initialTab="data"
              initialContext={{
                resource_id: 'table:ACCOUNT',
                resource_kind: 'table',
                display_name: 'ACCOUNT',
                browse_data: true,
              }}
            />
          ),
        });
      }, [shell]);
      return null;
    }

    render(
      <TestShell>
        <WorkspaceShellHarness />
      </TestShell>
    );

    expect(await screen.findByText('Cash On Hand')).toBeInTheDocument();
    // Legacy chrome & SR-F-000001 badge are completely gone!
    expect(screen.queryByText('SR-F-000001')).not.toBeInTheDocument();
    expect(screen.queryByText('Search database metadata')).not.toBeInTheDocument();
    expect(screen.queryByText('Monitor database events')).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Table or view')).not.toBeInTheDocument();
  });

  it('closes clean Firebird surface without prompt, and prompts Yes / No / Cancel when uncommitted activity exists', async () => {
    let shellRef = null;
    let currentState = makeHostFixture({has_uncommitted_activity: false});
    const actionsCalled = [];

    const post = jest.fn(async ({request}) => {
      actionsCalled.push(request.surface_action);
      if (request.surface_action === 'stage_row') {
        currentState = makeHostFixture({
          has_uncommitted_activity: true,
          staged_sql: [{mutation_id: 'row-0', op: 'update', row_key: 'row-0', sql: 'UPDATE "ACCOUNT" ...'}],
        });
      } else if (
        request.surface_action === 'commit_batch' ||
        request.surface_action === 'rollback_batch'
      ) {
        currentState = makeHostFixture({has_uncommitted_activity: false, staged_sql: []});
      }
      return currentState;
    });

    const firstView = render(
      <TestShell>
        <ShellLauncher post={post} onShellReady={(s) => { shellRef = s; }} />
      </TestShell>
    );

    expect(await screen.findByText('Cash On Hand')).toBeInTheDocument();

    // Case 1: Firebird transaction is open from reading, but ZERO mutation activity -> closes immediately!
    await act(async () => {
      await shellRef.closeInstance('data-account');
    });
    expect(screen.queryByText('Abandon Uncommitted Work?')).not.toBeInTheDocument();
    expect(actionsCalled).toContain('close_surface');
    firstView.unmount();

    // Case 2: Stage an edit -> Cancel keeps open; Yes rolls back & closes; No commits & closes!
    actionsCalled.length = 0;
    currentState = makeHostFixture({
      has_uncommitted_activity: true,
      staged_sql: [{mutation_id: 'row-0', op: 'update', row_key: 'row-0', sql: 'UPDATE "ACCOUNT" ...'}],
    });

    const secondView = render(
      <TestShell>
        <ShellLauncher post={post} onShellReady={(s) => { shellRef = s; }} />
      </TestShell>
    );
    expect(await screen.findByText('Cash On Hand')).toBeInTheDocument();

    // Attempt close -> Cancel keeps surface open
    let closePromise;
    act(() => {
      closePromise = shellRef.closeInstance('data-account');
    });
    expect(await screen.findByText('Abandon Uncommitted Work?')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Cancel'}));
      await expect(closePromise).resolves.toBe(false);
    });
    expect(shellRef.instances.some((i) => i.instanceId === 'data-account')).toBe(true);
    expect(actionsCalled).not.toContain('rollback_batch');
    expect(actionsCalled).not.toContain('commit_batch');

    // Attempt close -> No commits work & closes surface!
    act(() => {
      closePromise = shellRef.closeInstance('data-account');
    });
    expect(await screen.findByText('Abandon Uncommitted Work?')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'No'}));
      await expect(closePromise).resolves.toBe(true);
    });
    expect(actionsCalled).toContain('commit_batch');
    expect(actionsCalled).toContain('close_surface');
    secondView.unmount();

    // Case 3: Attempt close -> Yes abandons work (rollback_batch) & closes surface!
    actionsCalled.length = 0;
    currentState = makeHostFixture({
      has_uncommitted_activity: true,
      staged_sql: [{mutation_id: 'row-0', op: 'update', row_key: 'row-0', sql: 'UPDATE "ACCOUNT" ...'}],
    });
    render(
      <TestShell>
        <ShellLauncher post={post} onShellReady={(s) => { shellRef = s; }} />
      </TestShell>
    );
    expect(await screen.findByText('Cash On Hand')).toBeInTheDocument();
    act(() => {
      closePromise = shellRef.closeInstance('data-account');
    });
    expect(await screen.findByText('Abandon Uncommitted Work?')).toBeInTheDocument();
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Yes'}));
      await expect(closePromise).resolves.toBe(true);
    });
    expect(actionsCalled).toContain('rollback_batch');
    expect(actionsCalled).toContain('close_surface');
  });
});
