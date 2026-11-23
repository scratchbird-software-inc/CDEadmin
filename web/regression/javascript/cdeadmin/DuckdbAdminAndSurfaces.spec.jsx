/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {
  DUCKDB_ADMIN_TABS,
  renderDuckdbAdminWorkspace,
} from 'sources/cdeadmin_ui/modules/duckdb_admin';
import {
  SqlDuckdbExplainDialog,
  SqlDuckdbSessionDialog,
} from 'sources/cdeadmin_ui/surfaces/SqlDuckdbDiagnostics';
import {
  DataDuckdbCellInspectorModal,
  DataDuckdbRowSqlDialog,
} from 'sources/cdeadmin_ui/surfaces/DataDuckdbTools';

describe('DuckDB Native Administration Workspaces & SQL/Data Surface Parity (SR-F-030587..SR-F-030595)', () => {
  it('SR-F-030587: renders DuckDB runtime settings, rich COPY planner, foreign adapters & editor task runner', async () => {
    expect(DUCKDB_ADMIN_TABS).toEqual([
      'duckdb-runtime-settings',
      'duckdb-retained-schema',
      'duckdb-shell',
      'duckdb-sql-dump',
      'duckdb-continuity-storage',
    ]);

    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'open_session') {
          return {data: {success: 1, data: {session_id: 'duck-sess-12345678'}}};
        }
        if (payload.action === 'duckdb_runtime_settings') {
          if (payload.request?.operation === 'inventory') {
            return {data: {success: 1, data: {settings: [{name: 'threads', value: '4'}]}}};
          }
          if (payload.request?.operation === 'review') {
            return {data: {success: 1, data: {review_id: 'rev-1', review_digest: 'dig-1', sql: 'SET SESSION threads = 2'}}};
          }
          if (payload.request?.operation === 'apply') {
            return {data: {success: 1, data: {applied: true, effective_value: '2'}}};
          }
        }
        if (payload.action === 'duckdb_copy_plan') {
          return {data: {success: 1, data: {sql: "COPY \"main\".\"events\" TO 'exports/events.ndjson' (FORMAT JSON);"}}};
        }
        if (payload.action === 'duckdb_attachments') {
          return {data: {success: 1, data: {adapters: ['duckdb', 'sqlite', 'postgres', 'mysql', 'httpfs']}}};
        }
        if (payload.action === 'duckdb_editor_operation') {
          return {data: {success: 1, data: {catalogs: [{database_name: 'owned'}]}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderDuckdbAdminWorkspace({
        tab: 'duckdb-runtime-settings',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);

    expect(screen.getByText('SR-F-030587')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Inspect Runtime Settings'));
    await waitFor(() => expect(screen.getByText('Settings observed: 1')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Review SET'));
    await waitFor(() => expect(screen.getByText(/SET SESSION threads = 2/)).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Confirm reviewed setting change'));
    fireEvent.click(screen.getByText('Apply Setting'));
    await waitFor(() => expect(screen.getByText(/"applied": true/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Plan Native COPY / Reader SQL'));
    await waitFor(() => expect(document.body.textContent).toContain('FORMAT JSON'));

    fireEvent.click(screen.getByText('Probe Foreign Attachment Adapters'));
    await waitFor(() => expect(screen.getByText(/"adapters"/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Execute Original-Session Descriptor Task'));
    await waitFor(() => expect(screen.getByText(/owned/)).toBeInTheDocument());
  });

  it('SR-F-030588: observes, previews, reviews and applies retained-session DDN schema changes', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'open_session') {
          return {data: {success: 1, data: {session_id: 'duck-sess-ret-1'}}};
        }
        if (payload.action === 'duckdb_retained_schema') {
          if (payload.request?.operation === 'observe') {
            return {data: {success: 1, data: {model: {contract: 'scratchrobin.duckdb.retained-session-ddn@1', rows: {}}}}};
          }
          if (payload.request?.operation === 'preview') {
            return {data: {success: 1, data: {statement_count: 1, statements: ['CREATE TEMP TABLE t1 (id INT)']}}};
          }
          if (payload.request?.operation === 'review') {
            return {data: {success: 1, data: {application_id: 'ret-app-1', plan_digest: 'ret-dig-1'}}};
          }
          if (payload.request?.operation === 'apply') {
            return {data: {success: 1, data: {applied: true, commit_requested: false, rollback_requested: false}}};
          }
        }
        if (payload.action === 'duckdb_retained_schema_receipts') {
          return {data: {success: 1, data: {items: [{application_id: 'ret-app-1'}]}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderDuckdbAdminWorkspace({
        tab: 'duckdb-retained-schema',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);

    expect(screen.getByText('SR-F-030588')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Observe Retained Session'));
    await waitFor(() =>
      expect(screen.getAllByText(/scratchrobin\.duckdb\.retained-session-ddn@1/).length).toBeGreaterThan(0)
    );

    fireEvent.click(screen.getByText('Preview Diff'));
    await waitFor(() => expect(screen.getByText(/CREATE TEMP TABLE t1/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Seal Review Plan'));
    await waitFor(() => expect(screen.getByText('Application: ret-app-1')).toBeInTheDocument());

    fireEvent.click(
      screen.getByLabelText('Confirm applying reviewed DDN changes on the retained session (caller retains COMMIT/ROLLBACK)')
    );
    fireEvent.click(screen.getByText('Apply Reviewed Retained Schema Plan'));
    await waitFor(() => expect(screen.getByText(/"commit_requested": false/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Refresh Retained Schema Receipts'));
    await waitFor(() => expect(screen.getByText('Archived retained receipts: 1')).toBeInTheDocument());
  });

  it('SR-F-030589: renders DuckDB shell provenance and executes supervised directive batch', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'duckdb_ops_shell_provenance') {
          return {
            data: {
              success: 1,
              data: {
                python_package: {version: '1.5.2', source_id: '8a5851971f'},
                cli_binary: {status: 'not_configured'},
              },
            },
          };
        }
        if (payload.action === 'duckdb_ops_shell_execute') {
          return {data: {success: 1, data: {output: '┌────────────────┐\n│ duckdb_version │\n│     v1.5.2     │\n└────────────────┘'}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderDuckdbAdminWorkspace({
        tab: 'duckdb-shell',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);

    await waitFor(() => expect(screen.getAllByText(/8a5851971f/).length).toBeGreaterThan(0));
    expect(screen.getByText('SR-F-030589')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Execute Batch Script'));
    await waitFor(() => expect(screen.getByText(/v1\.5\.2/)).toBeInTheDocument());
  });

  it('SR-F-030590: exports, previews, reviews and reloads single-stream logical SQL dumps', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'duckdb_ops_dump_list') {
          return {data: {success: 1, data: {dumps: [{path: 'dumps/logical_dump.sql'}]}}};
        }
        if (payload.action === 'duckdb_ops_dump_export') {
          return {data: {success: 1, data: {sha256: 'abc123def456'}}};
        }
        if (payload.action === 'duckdb_ops_dump_read') {
          return {data: {success: 1, data: {content: '-- scratchrobin.duckdb.sql-stream-dump@1\nCREATE TABLE "main"."t1"(id INTEGER);'}}};
        }
        if (payload.action === 'duckdb_ops_dump_reload_review') {
          return {data: {success: 1, data: {review_id: 'dmp-rev-1', review_digest: 'dmp-dig-1', statement_count: 4}}};
        }
        if (payload.action === 'duckdb_ops_dump_reload_apply') {
          return {data: {success: 1, data: {applied: true, statements_executed: 4}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderDuckdbAdminWorkspace({
        tab: 'duckdb-sql-dump',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);

    await waitFor(() => expect(screen.getByText('Saved dumps: 1')).toBeInTheDocument());
    expect(screen.getByText('SR-F-030590')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Export SQL Dump'));
    await waitFor(() => expect(screen.getByText('SHA-256: abc123def456')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Preview Dump File'));
    await waitFor(() => expect(screen.getByText(/sql-stream-dump@1/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Review Reload Plan'));
    await waitFor(() => expect(screen.getByText('Statements verified: 4')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Confirm atomic single-transaction SQL reload'));
    fireEvent.click(screen.getByText('Apply Atomic Reload'));
    await waitFor(() => expect(screen.getByText(/"statements_executed": 4/)).toBeInTheDocument());
  });

  it('SR-F-030591: inspects continuity & storage headers, runs WAL drill, reopen probe & storage migration', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'duckdb_ops_continuity_inspect') {
          return {
            data: {
              success: 1,
              data: {database_file: {size_bytes: 262144}, wal_file: {exists: false, size_bytes: 0}},
            },
          };
        }
        if (payload.action === 'duckdb_ops_storage_inspect') {
          return {
            data: {
              success: 1,
              data: {
                storage_version_band: 'v1.5.0+',
                main_header: {magic: 'DUCK', version_number: 68, library_git_desc: 'v1.5.2', encrypted: false},
              },
            },
          };
        }
        if (payload.action === 'duckdb_ops_continuity_wal_drill') {
          return {data: {success: 1, data: {wal_replayed: true, isolated_copy: true}}};
        }
        if (payload.action === 'duckdb_ops_storage_reopen_probe') {
          return {data: {success: 1, data: {header_unchanged_after_open: true}}};
        }
        if (payload.action === 'duckdb_ops_storage_migrate_review') {
          return {data: {success: 1, data: {review_id: 'mig-1', review_digest: 'mig-dig-1'}}};
        }
        if (payload.action === 'duckdb_ops_storage_migrate_apply') {
          return {data: {success: 1, data: {migrated: true, after_version_number: 68}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderDuckdbAdminWorkspace({
        tab: 'duckdb-continuity-storage',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);

    await waitFor(() => expect(screen.getByText(/Storage v68/)).toBeInTheDocument());
    expect(screen.getByText('SR-F-030591')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Run Isolated WAL Recovery Drill'));
    await waitFor(() => expect(screen.getByText(/"wal_replayed": true/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Run Non-Rewriting Reopen Probe'));
    await waitFor(() => expect(screen.getByText('Header unchanged on open: true')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Review Storage Migration'));
    await waitFor(() => expect(screen.getByLabelText('Confirm writing migrated DuckDB file')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Confirm writing migrated DuckDB file'));
    fireEvent.click(screen.getByText('Apply Storage Migration'));
    await waitFor(() => expect(screen.getByText(/"after_version_number": 68/)).toBeInTheDocument());
  });

  it('SR-F-030592 & SR-F-030593: renders SQL editor DuckDB session/PREPARE dialog and EXPLAIN ANALYZE dialog', async () => {
    const callHost = jest.fn(async (subAction) => {
      if (subAction === 'describe_statement') {
        return {statement_type: 'SELECT', columns: [{position: 1, name: 'x', native_type: 'HUGEINT'}]};
      }
      return {valid: true};
    });
    const onInsertSql = jest.fn();
    const onRunExplain = jest.fn();

    const SessionWrapped = withTheme(() => (
      <SqlDuckdbSessionDialog
        open
        editorSource="SELECT 42::HUGEINT AS x"
        sessionId="duck-sess-99"
        callHost={callHost}
        onInsertSql={onInsertSql}
        onClose={() => {}}
      />
    ));
    render(<SessionWrapped />);
    expect(screen.getByText('SR-F-030592')).toBeInTheDocument();

    fireEvent.click(screen.getByText('PREPARE & Inspect Types'));
    await waitFor(() => expect(screen.getByText(/HUGEINT/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Insert ATTACH'));
    expect(onInsertSql).toHaveBeenCalledWith("ATTACH ':memory:' AS \"aux_catalog\";");

    const ExplainWrapped = withTheme(() => (
      <SqlDuckdbExplainDialog
        open
        editorSource="SELECT * FROM items;"
        onClose={() => {}}
        onRunExplain={onRunExplain}
      />
    ));
    render(<ExplainWrapped />);
    expect(screen.getByText('SR-F-030593')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Execute DuckDB Explain'));
    expect(onRunExplain).toHaveBeenCalledWith('EXPLAIN SELECT * FROM items;', 'logical_physical');
  });

  it('SR-F-030594 & SR-F-030595: renders DuckDB row SQL generator and Arrow 19-family cell inspector', () => {
    const RowSqlWrapped = withTheme(() => (
      <DataDuckdbRowSqlDialog
        open
        tableLabel='"main"."orders"'
        columns={[
          {name: 'id', native_type: 'INTEGER'},
          {name: 'tags', native_type: 'VARCHAR[]'},
          {name: 'payload', native_type: 'BLOB'},
        ]}
        row={{
          id: 7,
          tags: ['alpha', 'beta'],
          payload: {encoding: 'base64', data: btoa('Hi')},
        }}
        onClose={() => {}}
      />
    ));
    render(<RowSqlWrapped />);
    expect(screen.getByText('SR-F-030594')).toBeInTheDocument();
    expect(document.body.textContent).toContain("from_hex('4869')");

    const CellWrapped = withTheme(() => (
      <DataDuckdbCellInspectorModal
        open
        column={{
          name: 'tags',
          native_type: 'VARCHAR[]',
          input_envelope: {admitted: true, family: 'LIST'},
        }}
        value={['alpha', 'beta']}
        onClose={() => {}}
      />
    ));
    render(<CellWrapped />);
    expect(screen.getByText('SR-F-030595')).toBeInTheDocument();
    expect(screen.getByText('Family: LIST / ARRAY')).toBeInTheDocument();
    expect(screen.getByText(/"family": "LIST"/)).toBeInTheDocument();
  });
});
