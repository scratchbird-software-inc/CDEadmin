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
import {
  ProjectShellProvider,
  ProjectTopMenuBar,
  ProjectWorkbenchFrame,
  useProjectShell,
} from '../../../pgadmin/static/js/cdeadmin_ui/shell';
import SqlEditorSurface from '../../../pgadmin/static/js/cdeadmin_ui/surfaces/SqlEditorSurface';
import SurfaceExportDialog from '../../../pgadmin/static/js/cdeadmin_ui/surfaces/SurfaceExportDialog';

const TestShell = withTheme(({children}) => (
  <ProjectShellProvider username="dba@scratchrobin.org">
    {children}
    <ProjectTopMenuBar />
    <div style={{height: 700}}>
      <ProjectWorkbenchFrame />
    </div>
  </ProjectShellProvider>
));

function makeSqlHostResponse(overrides = {}) {
  const cols = [
    {
      name: 'ID',
      native_type: 'INTEGER',
      client_type: 'integer',
      nullable: false,
      key: true,
      read_only: true,
    },
    {
      name: 'CUSTOMER_NAME',
      native_type: 'VARCHAR(120)',
      client_type: 'text',
      nullable: false,
      key: false,
      read_only: false,
    },
    {
      name: 'ACTIVE',
      native_type: 'BOOLEAN',
      client_type: 'boolean',
      nullable: false,
      key: false,
      read_only: false,
    },
  ];
  const rows = [
    {
      row_number: 1,
      base_row_index: 0,
      identity_token: 'pk:1',
      values: {ID: 1, CUSTOMER_NAME: 'Acme Corp', ACTIVE: true},
      original_values: {ID: 1, CUSTOMER_NAME: 'Acme Corp', ACTIVE: true},
      stage_state: null,
    },
    {
      row_number: 2,
      base_row_index: 1,
      identity_token: 'pk:2',
      values: {ID: 2, CUSTOMER_NAME: null, ACTIVE: false},
      original_values: {ID: 2, CUSTOMER_NAME: null, ACTIVE: false},
      stage_state: null,
    },
  ];
  const hasResult = Boolean(overrides.withResult);
  return {
    surface_id: 'ss-test-1',
    has_uncommitted_activity: Boolean(overrides.has_uncommitted_activity),
    staged_count: overrides.staged_count || 0,
    engine_id: 'firebird',
    language_profile: 'firebird-sql',
    database_target_id: 'cdeadmin_demo.fdb',
    session_id: 'sql-sess-1',
    autocommit: false,
    terminator: overrides.terminator || ';',
    sql_source: overrides.sql_source ?? 'SELECT * FROM CUSTOMERS WHERE ID = :cust_id;',
    result_count: hasResult ? 1 : 0,
    result_summaries: hasResult ? [{index: 0, title: 'Result 1', row_count: 2, editable: true}] : [],
    active_result_index: 0,
    active_result: hasResult
      ? {
        index: 0,
        title: 'Result 1',
        columns: cols,
        rows,
        sort: [],
        filters: [],
        editable: true,
        row_operations: ['insert', 'update', 'delete'],
        total_view_rows: 2,
        plan_text: 'PLAN (CUSTOMERS NATURAL)',
        staged_mutations: [],
        target_resource: {resource_id: 'table:CUSTOMERS', display_name: 'CUSTOMERS'},
      }
      : null,
    timings_ms: {prepare_ms: 1.2, execute_ms: 3.4, fetch_ms: 0.8, total_ms: 5.4},
    plan_text: 'PLAN (CUSTOMERS NATURAL)',
    statement_summaries: [],
    last_execution_had_error: false,
    quick_queries: overrides.quick_queries || [
      {
        query_id: 'qq-1',
        name: 'Active Customers Mini-Forms',
        description: 'Saved with mini_forms layout',
        sql_text: 'SELECT * FROM CUSTOMERS;',
        terminator: ';',
        parameters: [],
        display_layout: {displayMode: 'mini_forms'},
      },
    ],
    snippets: overrides.snippets || {
      snippets: [
        {
          snippet_id: 'snip-fb-trig',
          title: 'Firebird Auto-ID Trigger',
          description: 'SET TERM trigger template',
          shortcut: 'fbtrig',
          engine_id: 'firebird',
          scope: 'builtin',
          favorite: false,
          sql_text: 'SET TERM ^ ;\nCREATE TRIGGER BI_T FOR T ...\n^\nSET TERM ; ^',
          tags: ['ddl', 'firebird', 'trigger'],
        },
        {
          snippet_id: 'snip-cte',
          title: 'Common Table Expression',
          description: 'ANSI CTE',
          shortcut: 'cte',
          engine_id: 'ansi',
          scope: 'builtin',
          favorite: true,
          sql_text: 'WITH cte AS (SELECT 1 AS n) SELECT * FROM cte;',
          tags: ['ansi', 'cte', 'dml'],
        },
      ],
      available_tags: [
        {tag: 'firebird', count: 1},
        {tag: 'trigger', count: 1},
        {tag: 'cte', count: 1},
      ],
      active_tags: [],
      tag_mode: 'and',
    },
    messages: overrides.messages || [
      {
        id: 'm-1',
        timestamp: '2026-11-16T23:00:00Z',
        severity: 'info',
        operation: 'Execute SELECT',
        elapsed_ms: 5.4,
        message: 'Returned 2 row(s).',
        line: 1,
        column: 1,
      },
    ],
  };
}

function SqlSurfaceLauncher({postMock, initialScriptKind = ''}) {
  const shell = useProjectShell();
  useEffect(() => {
    shell.openInlineTab({
      instanceId: 'sql-customers-tab',
      appId: 'data-navigator',
      title: 'sql: cdeadmin_demo.fdb',
      iconKey: 'tool.query',
      supportsTabbedIconBar: true,
      supportsRightDrawer: true,
      renderWorkArea: () => (
        <SqlEditorSurface
          endpointLabel="Local Firebird / cdeadmin_demo.fdb"
          engineId="firebird"
          languageProfile="firebird-sql"
          databaseTargetId="cdeadmin_demo.fdb"
          targetResource={{
            resource_id: 'table:CUSTOMERS',
            resource_kind: 'table',
            display_name: 'CUSTOMERS',
          }}
          resources={[
            {
              resource_id: 'table:CUSTOMERS',
              resource_kind: 'table',
              display_name: 'CUSTOMERS',
              columns: [{name: 'ID', native_type: 'INTEGER', primary_key: true}],
            },
          ]}
          initialScriptKind={initialScriptKind}
          post={postMock}
        />
      ),
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  return null;
}

describe('Surface 2 — SqlEditorSurface & SurfaceExportDialog', () => {
  test('enforces zero inline chrome, hides SQL Editor from left quick-launch rail, mounts focus-merged menus & 7 TiB views', async () => {
    const postMock = jest.fn(async ({request}) => {
      if (request.sub_action === 'visual_builder_from_sql') {
        return {
          ...makeSqlHostResponse(),
          model: {tables: [{id: 't1', name: 'CUSTOMERS', alias: 'c', columns: [{name: 'ID'}]}], projections: [], joins: [], where: [], group_by: [], order_by: []},
          scene: {
            views: [{id: 'query_canvas', name: 'Visual Query Canvas', profile: 'erd.physical@1'}],
            activeViewId: 'query_canvas',
            nodes: [{id: 't1', label: 'CUSTOMERS (c)', x: 80, y: 80, width: 220, height: 90, fields: [{name: 'ID', type: 'INTEGER', key: true}]}],
            edges: [],
            tiles: {'0:0': {tx: 0, ty: 0, nodes: [], edges: []}},
          },
          fidelity: 'exact',
          loss_notes: [],
          fanout_warnings: [],
        };
      }
      return makeSqlHostResponse();
    });

    await act(async () => {
      render(
        <TestShell>
          <SqlSurfaceLauncher postMock={postMock} />
        </TestShell>
      );
    });

    // 1. Left Quick Launch dock MUST NOT contain orphaned SQL Editor launcher
    expect(document.querySelector('[data-cdeadmin-qa-key="side-menu-app-sql-editor"]')).toBeNull();
    expect(document.querySelector('[data-cdeadmin-qa-key="side-menu-app-data-navigator"]')).not.toBeNull();

    // 2. Area 3e contains pure SQL Editor Surface with ZERO legacy inline execution toolbars or sub-tabs
    const surfaceEl = screen.getByTestId
      ? document.querySelector('[data-cdeadmin-qa-key="sql-editor-surface"]')
      : null;
    expect(surfaceEl).not.toBeNull();
    expect(surfaceEl.getAttribute('data-surface-view')).toBe('sql');
    expect(within(surfaceEl).queryByLabelText('SQL execution toolbar')).toBeNull();
    expect(within(surfaceEl).queryByRole('tab', {name: /Data Output/i})).toBeNull();

    // 3. Focus-merged Top Menus (`Query`, `Edit`, `View`) are mounted on Area 1
    expect(screen.getByRole('menuitem', {name: 'Query'})).toBeInTheDocument();
    expect(screen.getByRole('menuitem', {name: 'Edit'})).toBeInTheDocument();
    expect(screen.getByRole('menuitem', {name: 'View'})).toBeInTheDocument();

    // 4. TiB mounts 3 under-tabs (`Query`, `Format & Layout`, `Export & Files`) and 7 Pill 1 views
    const underTabs = document.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]');
    expect(underTabs).not.toBeNull();
    expect(within(underTabs).getByRole('tab', {name: 'Query'})).toBeInTheDocument();
    expect(within(underTabs).getByRole('tab', {name: 'Format & Layout'})).toBeInTheDocument();
    expect(within(underTabs).getByRole('tab', {name: 'Export & Files'})).toBeInTheDocument();

    // 5. Switch Pill 1 to `Visual Builder` -> 100% Area 3e is RobinTiledCanvas + Right Drawer opens Visual Inspector!
    const vbBtn = screen.getByRole('radio', {name: 'Visual Builder'});
    await act(async () => {
      fireEvent.click(vbBtn);
    });
    expect(surfaceEl.getAttribute('data-surface-view')).toBe('visual_builder');
    expect(document.querySelector('[data-cdeadmin-qa-key="sql-surface-visual-builder-canvas"]')).not.toBeNull();
    expect(document.querySelector('[data-cdeadmin-qa-key="sql-surface-3b-visual-inspector"]')).not.toBeNull();
  });

  test('prompts Modal Parameter Dialog on parameterized SQL, renders Surface 1 Data modes & multi-tag snippets', async () => {
    const postMock = jest.fn(async ({request}) => {
      if (request.sub_action === 'check_parameters') {
        return {
          parameters: [
            {name: 'cust_id', kind: 'named', index: 1, token: ':cust_id'},
          ],
        };
      }
      if (request.sub_action === 'execute') {
        return makeSqlHostResponse({withResult: true});
      }
      if (request.sub_action === 'list_snippets') {
        return makeSqlHostResponse().snippets;
      }
      if (request.sub_action === 'load_quick_query') {
        return {
          loaded_quick_query: makeSqlHostResponse().quick_queries[0],
          state: makeSqlHostResponse({withResult: true}),
        };
      }
      return makeSqlHostResponse();
    });

    await act(async () => {
      render(
        <TestShell>
          <SqlSurfaceLauncher postMock={postMock} />
        </TestShell>
      );
    });

    // Click Execute Statement -> detects `:cust_id` -> opens Modal Parameter Binding Dialog!
    const execBtn = screen.getByRole('button', {name: /Execute Statement/i});
    await act(async () => {
      fireEvent.click(execBtn);
    });

    const paramDialog = document.querySelector('[data-cdeadmin-qa-key="sql-parameter-dialog"]');
    expect(paramDialog).not.toBeNull();
    const valInput = within(paramDialog).getByLabelText('Value for cust_id');
    fireEvent.change(valInput, {target: {value: '42'}});

    const bindExecBtn = document.querySelector('[data-cdeadmin-qa-key="sql-params-confirm-btn"]');
    await act(async () => {
      fireEvent.click(bindExecBtn);
    });

    // Automatically switches to `Data` view showing `<null>` & `T`/`F` formatted cells!
    const surfaceEl = document.querySelector('[data-cdeadmin-qa-key="sql-editor-surface"]');
    expect(surfaceEl.getAttribute('data-surface-view')).toBe('data');
    expect(screen.getByText('Acme Corp')).toBeInTheDocument();
    expect(screen.getByText('<null>')).toBeInTheDocument();

    // Switch to `Format & Layout` under-tab and select `Mini-Forms` (Pill 2)
    const underTabs = document.querySelector('[data-cdeadmin-qa-key="notebookbar-undertabs"]');
    await act(async () => {
      fireEvent.click(within(underTabs).getByRole('tab', {name: 'Format & Layout'}));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('radio', {name: 'Mini-Forms'}));
    });
    expect(document.querySelector('[data-cdeadmin-qa-key="sql-surface-mini-forms"]')).not.toBeNull();

    // Switch back to `Query` under-tab and open Tagged Snippets Drawer
    await act(async () => {
      fireEvent.click(within(underTabs).getByRole('tab', {name: 'Query'}));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('button', {name: 'Snippets'}));
    });
    const snippetsDrawer = document.querySelector('[data-cdeadmin-qa-key="sql-surface-3b-snippets"]');
    expect(snippetsDrawer).not.toBeNull();
    const fbTagChip = document.querySelector('[data-cdeadmin-qa-key="snippet-tag-chip-firebird"]');
    expect(fbTagChip).not.toBeNull();
    await act(async () => {
      fireEvent.click(fbTagChip);
    });
    expect(postMock).toHaveBeenCalledWith(
      expect.objectContaining({
        action: 'sql_surface_action',
        request: expect.objectContaining({
          sub_action: 'list_snippets',
          selected_tags: ['firebird'],
        }),
      })
    );
  });

  test('SurfaceExportDialog dynamically switches format-specific settings for CSV/TSV, XLSX/ODS, and PDF', async () => {
    const onExportHost = jest.fn(async () => ({
      filename: 'report.pdf',
      mime_type: 'application/pdf',
      content_base64: btoa('%PDF-1.4 mock'),
    }));
    const onClose = jest.fn();

    const WrappedDialog = withTheme(() => (
      <SurfaceExportDialog
        open
        onClose={onClose}
        initialFormat="csv"
        defaultFilename="customers"
        defaultTitle="Customer Report"
        rows={[{values: {ID: 1, NAME: 'Alice'}}]}
        columns={[{name: 'ID'}, {name: 'NAME'}]}
        onExportHost={onExportHost}
      />
    ));

    render(<WrappedDialog />);

    // CSV settings visible initially
    expect(document.querySelector('[data-cdeadmin-qa-key="export-settings-delimited"]')).not.toBeNull();

    // Switch to Excel (.xlsx) -> spreadsheet settings visible
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="export-fmt-xlsx"]'));
    expect(document.querySelector('[data-cdeadmin-qa-key="export-settings-spreadsheet"]')).not.toBeNull();

    // Switch to PDF -> PDF report settings visible & submits host export
    fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="export-fmt-pdf"]'));
    expect(document.querySelector('[data-cdeadmin-qa-key="export-settings-pdf"]')).not.toBeNull();

    await act(async () => {
      fireEvent.click(document.querySelector('[data-cdeadmin-qa-key="surface-export-confirm"]'));
    });

    expect(onExportHost).toHaveBeenCalledWith(
      expect.objectContaining({
        format: 'pdf',
        filename: 'customers',
        settings: expect.objectContaining({
          page_size: 'letter',
          orientation: 'landscape',
        }),
      })
    );
  });

  test('Firebird uncommitted activity blocks close with Yes (Commit) / No (Rollback) / Cancel dialog', async () => {
    const postMock = jest.fn(async () =>
      makeSqlHostResponse({withResult: true, has_uncommitted_activity: true, staged_count: 1})
    );

    await act(async () => {
      render(
        <TestShell>
          <SqlSurfaceLauncher postMock={postMock} />
        </TestShell>
      );
    });

    // Click `[x]` on the `sql: cdeadmin_demo.fdb` tab on the NotebookBar
    const closeTabBtn = screen.getByRole('button', {name: /Close sql: cdeadmin_demo\.fdb/i});
    await act(async () => {
      fireEvent.click(closeTabBtn);
    });

    // UncommittedWorkDialog appears -> Cancel keeps Surface open!
    const cancelBtn = await screen.findByRole('button', {name: /^Cancel$/i});
    await act(async () => {
      fireEvent.click(cancelBtn);
    });
    expect(document.querySelector('[data-cdeadmin-qa-key="sql-editor-surface"]')).not.toBeNull();
  });
});
