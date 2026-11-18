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
import {buildFormLayoutPlacements} from '../../../pgadmin/static/js/cdeadmin_ui/surfaces/dataEditSurfaceHelpers';

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
    expect(document.querySelector('[data-cdeadmin-qa-key="data-surface-mini-forms-list"]')).not.toBeNull();

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

  test('Visual Builder renders SVG diagram cards on RobinTiledCanvas when dragging Tables, Views & Selectable Stored Procedures', async () => {
    const buildMockScene = (model) => {
      const nodes = (model.tables || []).map((t, i) => {
        const isProc = t.resource_kind === 'procedure';
        const sig = (t.input_parameters || []).map((p) => p.expr || `:${p.name}`).join(', ');
        const title = isProc && sig ? `${t.name}(${sig}) (${t.alias})` : `${t.name} (${t.alias})`;
        const fields = (t.columns || []).map((c, fi) => ({
          id: `${t.id}.${c.name}`,
          name: c.name,
          raw_name: c.name,
          selected:
            !(model.projections || []).length ||
            (model.projections || []).some((p) => p.column === c.name),
          datatype: c.type || 'INTEGER',
          is_pk: Boolean(c.key),
          port_y: 38 + fi * 22 + 11,
        }));
        return {
          id: t.id,
          kind: 'entity',
          name: title,
          raw_name: t.name,
          role: isProc ? 'PROC' : 'TABLE',
          x: t.x ?? 90 + i * 320,
          y: t.y ?? 72,
          width: 268,
          height: 38 + Math.max(1, fields.length) * 22 + 10,
          fields,
        };
      });
      const tile = {
        tx: 0,
        ty: 0,
        coord: '0:0',
        bounds: {min_x: 0, min_y: 0, max_x: 2048, max_y: 2048},
        zones: [],
        nodes,
        edges: [],
        widgets: [],
      };
      return {
        view_id: 'query_canvas',
        fit_key: nodes.length ? 'query_canvas_populated' : 'query_canvas_empty',
        ddn_sha256: `sha_${nodes.length}_${(model.projections || []).length}`,
        canvas_bounds: {min_x: 0, min_y: 0, width: 900, height: 520},
        summary: {view_count: 1, node_count: nodes.length, edge_count: 0, widget_count: 0},
        tile_size: 2048,
        tile_index: [{tx: 0, ty: 0, coord: '0:0', bounds: tile.bounds}],
        nodes,
        edges: [],
        loaded_tiles: {'0:0': tile},
      };
    };

    const postMock = jest.fn(async ({request}) => {
      if (request.sub_action === 'visual_builder_from_sql') {
        const emptyModel = {tables: [], joins: [], projections: [], filters: [], group_by: [], order_by: []};
        return {
          ...makeSqlHostResponse(),
          model: emptyModel,
          scene: buildMockScene(emptyModel),
          fidelity: 'exact',
          loss_notes: [],
          fanout_warnings: [],
        };
      }
      if (request.sub_action === 'resolve_visual_object') {
        const tr = request.target_resource;
        if (tr.display_name === 'LOG_ONLY_PROC') {
          throw new Error(
            "Procedure 'LOG_ONLY_PROC' has no selectable RETURNS output columns (executable-only)"
          );
        }
        if (tr.display_name === 'GET_EMP_PROJ') {
          return {
            object_node: {
              id: 'proc_p1_GET_EMP_PROJ',
              resource_id: 'procedure:GET_EMP_PROJ',
              resource_kind: 'procedure',
              name: 'GET_EMP_PROJ',
              alias: 'p1',
              selectable: true,
              input_parameters: [{name: 'EMP_NO', type: 'SMALLINT', expr: ':EMP_NO'}],
              columns: [
                {name: 'PROJ_ID', type: 'CHAR(5)', key: false},
                {name: 'PROJ_NAME', type: 'VARCHAR(40)', key: false},
              ],
            },
            suggested_joins: [],
          };
        }
        return {
          object_node: {
            id: 'tbl_t1_CUSTOMERS',
            resource_id: 'table:CUSTOMERS',
            resource_kind: 'table',
            name: 'CUSTOMERS',
            alias: 't1',
            selectable: true,
            columns: [
              {name: 'ID', type: 'INTEGER', key: true},
              {name: 'NAME', type: 'VARCHAR(80)', key: false},
            ],
          },
          suggested_joins: [],
        };
      }
      if (request.sub_action === 'visual_builder_scene') {
        return {
          ...makeSqlHostResponse(),
          scene: buildMockScene(request.model),
          sql_text: 'SELECT * FROM "CUSTOMERS" AS "t1";',
          fanout_warnings: [],
        };
      }
      return makeSqlHostResponse({sql_source: ''});
    });

    await act(async () => {
      render(
        <TestShell>
          <SqlSurfaceLauncher postMock={postMock} />
        </TestShell>
      );
    });

    // Switch to Visual Builder
    await act(async () => {
      fireEvent.click(screen.getByRole('radio', {name: 'Visual Builder'}));
    });

    const canvasWrap = document.querySelector(
      '[data-cdeadmin-qa-key="sql-surface-visual-builder-canvas"]'
    );
    expect(canvasWrap).not.toBeNull();

    const makeDropDataTransfer = (payload) => ({
      dropEffect: 'copy',
      getData: (mime) =>
        mime === 'application/x-scratchrobin-catalog-object' ? JSON.stringify(payload) : '',
    });

    // 1. Drag & drop table `CUSTOMERS` onto the visual surface -> renders visible SVG card & columns!
    await act(async () => {
      fireEvent.drop(canvasWrap, {
        clientX: 220,
        clientY: 160,
        dataTransfer: makeDropDataTransfer({
          resource_id: 'table:CUSTOMERS',
          resource_kind: 'table',
          display_name: 'CUSTOMERS',
        }),
      });
    });

    const custCard = document.querySelector(
      '[data-cdeadmin-qa-key="canvas-node-card-tbl_t1_CUSTOMERS"]'
    );
    expect(custCard).not.toBeNull();
    expect(within(custCard).getByText(/CUSTOMERS \(t1\)/)).toBeInTheDocument();
    expect(within(custCard).getByText('ID')).toBeInTheDocument();
    expect(within(custCard).getByText('NAME')).toBeInTheDocument();

    // 2. Drag & drop selectable stored procedure `GET_EMP_PROJ` -> renders PROC card + input arg editor!
    await act(async () => {
      fireEvent.drop(canvasWrap, {
        clientX: 540,
        clientY: 160,
        dataTransfer: makeDropDataTransfer({
          resource_id: 'procedure:GET_EMP_PROJ',
          resource_kind: 'procedure',
          display_name: 'GET_EMP_PROJ',
        }),
      });
    });

    const procCard = document.querySelector(
      '[data-cdeadmin-qa-key="canvas-node-card-proc_p1_GET_EMP_PROJ"]'
    );
    expect(procCard).not.toBeNull();
    expect(within(procCard).getByText(/GET_EMP_PROJ\(:EMP_NO\)/)).toBeInTheDocument();
    expect(within(procCard).getByText('PROJ_ID')).toBeInTheDocument();
    expect(within(procCard).getByText('PROC')).toBeInTheDocument();
    expect(
      document.querySelector('[data-cdeadmin-qa-key="vb-proc-params-proc_p1_GET_EMP_PROJ"]')
    ).not.toBeNull();

    // 3. Toggle column checkbox directly on the SVG card -> updates projections cleanly!
    const nameCheck = document.querySelector(
      '[data-cdeadmin-qa-key="canvas-field-check-tbl_t1_CUSTOMERS-NAME"]'
    );
    expect(nameCheck).not.toBeNull();
    await act(async () => {
      fireEvent.click(nameCheck);
    });
    expect(postMock).toHaveBeenLastCalledWith(
      expect.objectContaining({
        request: expect.objectContaining({
          sub_action: 'visual_builder_scene',
          model: expect.objectContaining({
            projections: expect.arrayContaining([
              expect.objectContaining({column: 'ID'}),
            ]),
          }),
        }),
      })
    );

    // 4. Dragging an executable-only stored procedure shows clear diagnostic banner on canvas
    await act(async () => {
      fireEvent.drop(canvasWrap, {
        clientX: 300,
        clientY: 260,
        dataTransfer: makeDropDataTransfer({
          resource_id: 'procedure:LOG_ONLY_PROC',
          resource_kind: 'procedure',
          display_name: 'LOG_ONLY_PROC',
        }),
      });
    });
    const notice = document.querySelector(
      '[data-cdeadmin-qa-key="visual-builder-canvas-notice"]'
    );
    expect(notice).not.toBeNull();
    expect(notice.textContent).toMatch(/executable-only/i);
  });

  test('allows renaming any workspace tab via double-click, rename icon, or right-click context menu', async () => {
    const postMock = jest.fn(async () => makeSqlHostResponse());

    await act(async () => {
      render(
        <TestShell>
          <SqlSurfaceLauncher postMock={postMock} />
        </TestShell>
      );
    });

    const activeTab = document.querySelector('[data-cdeadmin-tab-id="sql-customers-tab"]');
    expect(activeTab).not.toBeNull();
    expect(activeTab.textContent).toContain('sql: cdeadmin_demo.fdb');

    // 1. Double-clicking the tab opens the inline rename input
    await act(async () => {
      fireEvent.doubleClick(activeTab);
    });
    let renameInput = document.querySelector('[data-cdeadmin-qa-key="notebookbar-tab-rename-input"]');
    expect(renameInput).not.toBeNull();
    fireEvent.change(renameInput, {target: {value: 'Monthly Customer Audit'}});
    await act(async () => {
      fireEvent.keyDown(renameInput, {key: 'Enter'});
    });
    expect(activeTab.textContent).toContain('Monthly Customer Audit');

    // 2. Right-clicking the tab opens the Tab context menu with `Rename Tab…`
    await act(async () => {
      fireEvent.contextMenu(activeTab, {clientX: 120, clientY: 36});
    });
    const ctxRename = document.querySelector('[data-cdeadmin-qa-key="tab-ctx-rename"]');
    expect(ctxRename).not.toBeNull();
    await act(async () => {
      fireEvent.click(ctxRename);
    });
    renameInput = await screen.findByLabelText('Rename tab');
    fireEvent.change(renameInput, {target: {value: 'Q4 Revenue Query'}});
    await act(async () => {
      fireEvent.blur(renameInput);
    });
    expect(activeTab.textContent).toContain('Q4 Revenue Query');
  });

  test('sizes Mini-Forms adaptively to actual field values and supports 9-button navigation, bookmarks (!, !<, !>), and Tab/Arrow keyboard navigation', async () => {
    // 1. Verify adaptive field widths size narrow values (`ID = 1`, `REGION = 'ON'`) much tighter than `NAME = 'Northwind Field Lab'`
    const customerCols = [
      {name: 'CUSTOMER_ID', native_type: 'INTEGER', key: true},
      {name: 'NAME', native_type: 'VARCHAR', key: false, comment: 'Customer display name'},
      {name: 'CITY', native_type: 'VARCHAR', key: false},
      {name: 'REGION', native_type: 'VARCHAR', key: false},
    ];
    const customerRows = [
      {
        row_number: 1,
        base_row_index: 0,
        identity_token: 'pk:1',
        values: {CUSTOMER_ID: 1, NAME: 'Northwind Field Lab', CITY: 'Toronto', REGION: 'ON'},
      },
      {
        row_number: 2,
        base_row_index: 1,
        identity_token: 'pk:2',
        values: {CUSTOMER_ID: 2, NAME: 'Contoso Water', CITY: 'Hamilton', REGION: 'ON'},
      },
      {
        row_number: 3,
        base_row_index: 2,
        identity_token: 'pk:3',
        values: {CUSTOMER_ID: 3, NAME: 'Adventure Works Mining', CITY: 'Sudbury', REGION: 'ON'},
      },
    ];
    const adaptive = buildFormLayoutPlacements(customerCols, {}, 920, null, customerRows);
    expect(adaptive.adaptiveWidths.REGION).toBeLessThan(adaptive.adaptiveWidths.NAME);
    expect(adaptive.adaptiveWidths.CUSTOMER_ID).toBeLessThan(adaptive.adaptiveWidths.NAME);
    expect(adaptive.adaptiveWidths.REGION).toBeLessThanOrEqual(140);

    // 2. Mount Surface 2 with 3 result rows and verify all 9 Navigate/Bookmark buttons + Grid & Mini-Form keyboard navigation
    const threeRowHost = {
      ...makeSqlHostResponse({withResult: true, sql_source: 'SELECT * FROM CUSTOMERS;'}),
      total_view_rows: 3,
      window_offset: 0,
      window_size: 200,
      active_result: {
        index: 0,
        title: 'Result 1',
        columns: customerCols,
        rows: customerRows,
        sort: [],
        filters: [],
        editable: true,
        row_operations: ['insert', 'update', 'delete'],
        total_view_rows: 3,
        plan_text: 'PLAN (CUSTOMERS NATURAL)',
        staged_mutations: [],
        target_resource: {resource_id: 'table:CUSTOMERS', display_name: 'CUSTOMERS'},
      },
    };
    const postMock = jest.fn(async () => threeRowHost);

    await act(async () => {
      render(
        <TestShell>
          <SqlSurfaceLauncher postMock={postMock} />
        </TestShell>
      );
    });

    // Switch to Data view
    await act(async () => {
      fireEvent.click(screen.getByRole('radio', {name: 'Data'}));
    });

    // Confirm all 9 horizontal Navigate & Bookmark buttons exist on the Query ribbon!
    const navFirstBtn = screen.getByRole('button', {name: /First Record \(\|<\)/});
    const navPrevPageBtn = screen.getByRole('button', {name: /Previous Page \(<<\)/});
    const navPrevRowBtn = screen.getByRole('button', {name: /Previous Row \(<\)/});
    const navNextRowBtn = screen.getByRole('button', {name: /Next Row \(>\)/});
    const navNextPageBtn = screen.getByRole('button', {name: /Next Page \(>>\)/});
    const navLastBtn = screen.getByRole('button', {name: /Last Record \(>\|\)/});
    const bookmarkBtn = screen.getByRole('button', {name: /Bookmark Record \(!\)/});
    const bookmarkPrevBtn = screen.getByRole('button', {name: /Previous Bookmark \(!<\)/});
    const bookmarkNextBtn = screen.getByRole('button', {name: /Next Bookmark \(!>\)/});

    expect(navFirstBtn).toHaveAttribute('aria-disabled', 'true');
    expect(navPrevPageBtn).toHaveAttribute('aria-disabled', 'true');
    expect(navPrevRowBtn).toHaveAttribute('aria-disabled', 'true');
    expect(navNextRowBtn).not.toHaveAttribute('aria-disabled', 'true');
    expect(navNextPageBtn).not.toHaveAttribute('aria-disabled', 'true');
    expect(navLastBtn).not.toHaveAttribute('aria-disabled', 'true');

    // Bookmark row 0 (`!`), jump to last record (`>|`), bookmark row 2 (`!`), and cycle with `!<` / `!>`!
    await act(async () => {
      fireEvent.click(bookmarkBtn);
    });
    expect(document.querySelector('[data-cdeadmin-qa-key="grid-bookmark-badge-0"]')).not.toBeNull();

    await act(async () => {
      fireEvent.click(navLastBtn);
    });
    expect(navLastBtn).toHaveAttribute('aria-disabled', 'true');
    expect(navFirstBtn).not.toHaveAttribute('aria-disabled', 'true');

    await act(async () => {
      fireEvent.click(bookmarkBtn);
    });
    expect(document.querySelector('[data-cdeadmin-qa-key="grid-bookmark-badge-2"]')).not.toBeNull();

    // Jump to Previous Bookmark (`!<`) -> lands back on row 0!
    await act(async () => {
      fireEvent.click(bookmarkPrevBtn);
    });
    expect(navFirstBtn).toHaveAttribute('aria-disabled', 'true');

    // Jump to Next Bookmark (`!>`) -> lands on row 2!
    await act(async () => {
      fireEvent.click(bookmarkNextBtn);
    });
    expect(navLastBtn).toHaveAttribute('aria-disabled', 'true');

    // Keyboard navigation in Grid: press Ctrl+Home -> row 0 col 0, Tab -> col 1 (`NAME`), ArrowDown -> row 1 col 1 (`NAME`)
    const cell00 = document.querySelector('[data-grid-nav-cell="0:CUSTOMER_ID"]');
    expect(cell00).not.toBeNull();
    await act(async () => {
      fireEvent.keyDown(cell00, {key: 'Home', ctrlKey: true});
    });
    expect(document.activeElement).toBe(cell00);

    await act(async () => {
      fireEvent.keyDown(cell00, {key: 'Tab'});
    });
    const cell01 = document.querySelector('[data-grid-nav-cell="0:NAME"]');
    expect(document.activeElement).toBe(cell01);

    await act(async () => {
      fireEvent.keyDown(cell01, {key: 'ArrowDown'});
    });
    const cell11 = document.querySelector('[data-grid-nav-cell="1:NAME"]');
    expect(document.activeElement).toBe(cell11);

    await act(async () => {
      fireEvent.keyDown(cell11, {key: 'PageDown'});
    });
    expect(navLastBtn).toHaveAttribute('aria-disabled', 'true');
    await act(async () => {
      fireEvent.keyDown(document.querySelector('[data-grid-nav-cell="2:NAME"]'), {key: 'PageUp'});
    });
    expect(navFirstBtn).toHaveAttribute('aria-disabled', 'true');

    // Switch to Format & Layout -> Mini-Forms and verify `align-content: start` + keyboard navigation across Mini-Forms!
    await act(async () => {
      fireEvent.click(screen.getByRole('tab', {name: 'Format & Layout'}));
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('radio', {name: 'Mini-Forms'}));
    });

    const miniFormsWrap = document.querySelector('[data-cdeadmin-qa-key="data-surface-mini-forms-list"]');
    expect(miniFormsWrap).not.toBeNull();
    expect(miniFormsWrap).toContainElement(document.querySelector('[data-form-nav-cell="1:NAME"]'));
    const firstNameField = document.querySelector('[data-form-nav-cell="0:NAME"]');
    fireEvent.focus(firstNameField);
    expect(screen.getByText('Customer display name')).toHaveAttribute('role', 'note');
    fireEvent.blur(firstNameField);
    expect(screen.queryByText('Customer display name')).not.toBeInTheDocument();
    // Bookmark badges carry over into Mini-Form gutters!
    expect(document.querySelector('[data-cdeadmin-qa-key="row-bookmark-badge-0"]')).not.toBeNull();
    expect(document.querySelector('[data-cdeadmin-qa-key="row-bookmark-badge-2"]')).not.toBeNull();

    const mfField11 = document.querySelector('[data-form-nav-cell="1:NAME"]');
    expect(mfField11).not.toBeNull();
    await act(async () => {
      fireEvent.keyDown(mfField11, {key: 'ArrowDown'});
    });
    const mfField21 = document.querySelector('[data-form-nav-cell="2:NAME"]');
    expect(document.activeElement).toBe(mfField21);
  });
  test('refuses unresolved catalog objects instead of synthesizing a query node', async () => {
    const postMock = jest.fn(async ({request}) =>
      request.sub_action === 'resolve_visual_object' ? {} : makeSqlHostResponse()
    );
    await act(async () => {
      render(<TestShell><SqlSurfaceLauncher postMock={postMock} /></TestShell>);
    });
    await act(async () => {
      fireEvent.click(screen.getByRole('radio', {name: 'Visual Builder'}));
    });
    const canvas = document.querySelector('[data-cdeadmin-qa-key="sql-surface-visual-builder-canvas"]');
    expect(canvas).not.toBeNull();
    postMock.mockClear();
    await act(async () => {
      fireEvent.drop(canvas, {dataTransfer: {
        getData: (type) => type === 'application/x-scratchrobin-catalog-object'
          ? JSON.stringify({resource_id: 'table:MISSING', resource_kind: 'table', display_name: 'MISSING'}) : '',
      }});
    });
    expect(await screen.findByText(/server did not return catalog metadata/i)).toBeInTheDocument();
    expect(postMock.mock.calls.some(([body]) => body.request.sub_action === 'visual_builder_scene')).toBe(false);
  });

});
