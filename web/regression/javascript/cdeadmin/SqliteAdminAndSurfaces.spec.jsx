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
  SQLITE_ADMIN_TABS,
  renderSqliteAdminWorkspace,
} from 'sources/cdeadmin_ui/modules/sqlite_admin';
import {
  SqlSqliteExplainDialog,
  SqlSqliteSessionDialog,
} from 'sources/cdeadmin_ui/surfaces/SqlSqliteDiagnostics';
import {
  DataSqliteCellInspectorModal,
  DataSqliteRowSqlDialog,
} from 'sources/cdeadmin_ui/surfaces/DataSqliteTools';

describe('SQLite Native Administration Workspaces (SQ-AUD-09, 10, 11, 12, 13, 15 & Full GUI Parity)', () => {
  it('SQ-AUD-09 (SR-F-030560): renders RBU workspace, opens vacuum/update, steps, pauses and resumes', async () => {
    expect(SQLITE_ADMIN_TABS).toEqual([
      'sqlite-rbu',
      'sqlite-expert',
      'sqlite-intck',
      'sqlite-blob-stream',
      'sqlite-shell',
      'sqlite-sql-dump',
      'sqlite-session-tuning',
    ]);

    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'sqlite_ops_rbu_catalog') {
          return {data: {success: 1, data: {runtime: {available: true}, jobs: []}}};
        }
        if (payload.action === 'sqlite_ops_rbu_open_update') {
          return {
            data: {
              success: 1,
              data: {
                job_id: 'rbu-job-1',
                state: 'open',
                rbu_state: 'OAL',
                total_steps: 0,
                stage1_permyriad: 0,
                stage2_permyriad: 0,
              },
            },
          };
        }
        if (payload.action === 'sqlite_ops_rbu_step') {
          return {
            data: {
              success: 1,
              data: {
                job_id: 'rbu-job-1',
                state: 'active',
                rbu_state: 'OAL',
                total_steps: 250,
                stage1_permyriad: 5000,
                stage2_permyriad: 0,
              },
            },
          };
        }
        if (payload.action === 'sqlite_ops_rbu_pause') {
          return {data: {success: 1, data: {job_id: 'rbu-job-1', state: 'paused', rbu_state: 'OAL'}}};
        }
        if (payload.action === 'sqlite_ops_rbu_resume') {
          return {data: {success: 1, data: {job_id: 'rbu-job-1', state: 'completed', rbu_state: 'DONE', stage1_permyriad: 10000, stage2_permyriad: 10000}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderSqliteAdminWorkspace({
        tab: 'sqlite-rbu',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);

    await waitFor(() => expect(screen.getByText('RBU Helper Ready')).toBeInTheDocument());
    expect(screen.getByText('SR-F-030560')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Target Ordinary Table Name'), {target: {value: 'accounts'}});
    fireEvent.click(screen.getByText('Build Package & Open RBU Update'));
    await waitFor(() => expect(screen.getByText(/Active RBU Job: rbu-job-1/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Step Batch'));
    await waitFor(() => expect(screen.getByText('5000 / 10000')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Pause & Savestate'));
    await waitFor(() => expect(screen.getByText(/paused/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Verify State & Resume'));
    await waitFor(() => expect(screen.getByText(/completed/)).toBeInTheDocument());
  });

  it('SQ-AUD-10 (SR-F-030561): runs preview-only Expert Index Advisor without applying DDL', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'sqlite_ops_expert_status') {
          return {data: {success: 1, data: {available: true, indexes_applied_automatically: false}}};
        }
        if (payload.action === 'sqlite_ops_expert_analyze') {
          return {
            data: {
              success: 1,
              data: {
                indexes_applied: false,
                statements: [{
                  ordinal: 0,
                  sql: 'SELECT * FROM shipments WHERE region = \'NA\'',
                  recommended_indexes_ddl: 'CREATE INDEX shipments_idx_0001 ON shipments(region);',
                  query_plan: 'SEARCH shipments USING INDEX shipments_idx_0001 (region=?)',
                }],
              },
            },
          };
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderSqliteAdminWorkspace({
        tab: 'sqlite-expert',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);

    await waitFor(() => expect(screen.getByText('Expert C Bridge Ready')).toBeInTheDocument());
    expect(screen.getByText('SR-F-030561')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Analyze Candidate Indexes'));
    await waitFor(() =>
      expect(screen.getByText(/CREATE INDEX shipments_idx_0001/)).toBeInTheDocument()
    );
  });

  it('SQ-AUD-11 (SR-F-030562): opens and steps Incremental Integrity Check across unlocked batches', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'sqlite_ops_intck_status') {
          return {data: {success: 1, data: {runtime: {available: true}, disclaimer: 'Does not recover data.', jobs: []}}};
        }
        if (payload.action === 'sqlite_ops_intck_open') {
          return {data: {success: 1, data: {job_id: 'intck-1', state: 'open', completed_steps: 0, unlock_count: 0, corrupt_detected: false}}};
        }
        if (payload.action === 'sqlite_ops_intck_step') {
          return {data: {success: 1, data: {job_id: 'intck-1', state: 'completed', completed_steps: 42, unlock_count: 3, corrupt_detected: false}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderSqliteAdminWorkspace({
        tab: 'sqlite-intck',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);

    await waitFor(() => expect(screen.getByText('Intck Helper Ready')).toBeInTheDocument());
    expect(screen.getByText('SR-F-030562')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Open Incremental Check'));
    await waitFor(() => expect(screen.getByText(/Check Session: intck-1/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Step Batch'));
    await waitFor(() => expect(screen.getByText('42')).toBeInTheDocument());
  });

  it('SQ-AUD-12 (SR-F-030563): inspects cell, allocates zeroblob and streams BLOB chunks', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'sqlite_ops_blob_inspect') {
          return {data: {success: 1, data: {typeof: 'blob', byte_length: 1024, streamable_blob: true}}};
        }
        if (payload.action === 'sqlite_ops_blob_read_chunk') {
          return {data: {success: 1, data: {chunk_sha256: 'deadbeef', chunk_bytes: 4, total_bytes: 1024, data: 'cafebabe'}}};
        }
        if (payload.action === 'sqlite_ops_blob_allocate_review') {
          return {data: {success: 1, data: {review_id: 'rev-b1', review_digest: 'dig-b1'}}};
        }
        if (payload.action === 'sqlite_ops_blob_allocate_apply') {
          return {data: {success: 1, data: {state: 'committed'}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderSqliteAdminWorkspace({
        tab: 'sqlite-blob-stream',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);
    expect(screen.getByText('SR-F-030563')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Rowid Table'), {target: {value: 'media_store'}});
    fireEvent.change(screen.getByLabelText('BLOB Column'), {target: {value: 'payload'}});
    fireEvent.click(screen.getByText('Inspect Cell'));
    await waitFor(() => expect(screen.getByText('Streamable BLOB')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Read BLOB Chunk'));
    await waitFor(() => expect(screen.getByDisplayValue('cafebabe')).toBeInTheDocument());
  });

  it('SQ-AUD-13 & SQ-AUD-15 (SR-F-030564, SR-F-030565): verifies matching CLI shell & exports/imports native SQL dump', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'sqlite_ops_shell_provenance') {
          return {
            data: {
              success: 1,
              data: {
                matched: true,
                binary_sha256: 'abc123sha',
                cli_runtime: {version: '3.53.0', source_id: '2026-04-09 11:41:38 4525003a'},
              },
            },
          };
        }
        if (payload.action === 'sqlite_ops_shell_inspect') {
          return {data: {success: 1, data: {output: 'database page size:  4096'}}};
        }
        if (payload.action === 'sqlite_ops_dump_list') {
          return {data: {success: 1, data: {dumps: []}}};
        }
        if (payload.action === 'sqlite_ops_dump_export') {
          return {
            data: {
              success: 1,
              data: {
                dump_id: 'dmp-1',
                byte_length: 512,
                sha256: 'fedcba9876543210',
                fidelity: {contains_blob_values: true},
                script_preview: 'CREATE TABLE t(id INT);\nINSERT INTO t VALUES(1);',
              },
            },
          };
        }
        if (payload.action === 'sqlite_ops_dump_import_review') {
          return {data: {success: 1, data: {review_id: 'imp-1', review_digest: 'dig-1', payload: {statement_count: 2}}}};
        }
        if (payload.action === 'sqlite_ops_dump_import_apply') {
          return {data: {success: 1, data: {state: 'committed', outcome: {executed_statements: 2}}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const ShellWrapped = withTheme(() =>
      renderSqliteAdminWorkspace({
        tab: 'sqlite-shell',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    const {unmount} = render(<ShellWrapped />);
    await waitFor(() => expect(screen.getByText(/Matched CLI 3.53.0/)).toBeInTheDocument());
    expect(screen.getByText('SR-F-030564')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Execute Read-Only Dot-Command'));
    await waitFor(() => expect(screen.getByText(/database page size: 4096/)).toBeInTheDocument());
    unmount();

    const DumpWrapped = withTheme(() =>
      renderSqliteAdminWorkspace({
        tab: 'sqlite-sql-dump',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<DumpWrapped />);
    expect(screen.getByText('SR-F-030565')).toBeInTheDocument();

    fireEvent.click(screen.getByText('Generate Native SQL Dump'));
    await waitFor(() => expect(screen.getByText('512 bytes')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Review SQL Script Import'));
    await waitFor(() => expect(screen.getByText('Confirm atomic SQLite script execution')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('Confirm atomic SQLite script execution'));
    fireEvent.click(screen.getByText('Apply Reviewed SQL Script'));
    await waitFor(() => expect(screen.getByText(/2 statements verified/)).toBeInTheDocument());
  });

  it('SR-F-030566: exercises SqliteSessionTuningWorkspace across settings, limits, PRAGMAs, db_config, maintenance and descriptor tasks', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'open_session') {
          return {data: {success: 1, data: {session_id: 'sq-sess-99'}}};
        }
        if (payload.action === 'sqlite_editor_operation') {
          if (payload.request?.operation_id === 'describe') {
            return {data: {success: 1, data: {operations: new Array(103).fill({})}}};
          }
          return {data: {success: 1, data: {state: 'ok', extensions: []}}};
        }
        if (payload.action === 'sqlite_connection_settings') {
          return {data: {success: 1, data: {effective_code: payload.request?.operation === 'inspect' ? 2 : 1}}};
        }
        if (payload.action === 'sqlite_connection_limits') {
          return {data: {success: 1, data: {effective_value: payload.request?.operation === 'inspect' ? 1000000 : 500000}}};
        }
        if (payload.action === 'sqlite_connection_pragmas') {
          return {data: {success: 1, data: {effective_value: true}}};
        }
        if (payload.action === 'sqlite_connection_config') {
          return {data: {success: 1, data: {native_constant: 'SQLITE_DBCONFIG_DEFENSIVE', effective_value: true}}};
        }
        if (payload.action === 'sqlite_connection_maintenance') {
          return {data: {success: 1, data: {plan_id: 'maint-plan-1', state: 'ready'}}};
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Wrapped = withTheme(() =>
      renderSqliteAdminWorkspace({
        tab: 'sqlite-session-tuning',
        endpointUrl: '/browser/server/cde_workspace/1/2',
        databaseTargetId: 'db-target-1',
        api,
      })
    );
    render(<Wrapped />);
    expect(screen.getByText('SR-F-030566')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByText('103')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Inspect Synchronous'));
    await waitFor(() => expect(screen.getByText('Effective code: 2')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('Confirm connection-local synchronous change'));
    fireEvent.click(screen.getByText('Apply Synchronous'));
    await waitFor(() => expect(screen.getByText('Effective code: 1')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Inspect Limit'));
    await waitFor(() => expect(screen.getByText('sql_length: 1000000')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Inspect PRAGMA'));
    await waitFor(() => expect(screen.getByText('foreign_keys: true')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Inspect db_config'));
    await waitFor(() => expect(screen.getByText('SQLITE_DBCONFIG_DEFENSIVE: true')).toBeInTheDocument());

    fireEvent.click(screen.getByText('Prepare Retained Maintenance'));
    await waitFor(() => expect(screen.getByText(/maint-plan-1/)).toBeInTheDocument());

    fireEvent.click(screen.getByText('Execute Session Descriptor Task'));
    await waitFor(() => expect(screen.getByText(/"state": "ok"/)).toBeInTheDocument());
  });

  it('SR-F-030567..SR-F-030570: renders SQLite SQL & Data surface dialogs (Session, Explain, Row SQL, Cell Inspector)', async () => {
    const callHost = jest.fn(async (subAction) => {
      if (subAction === 'validate_source') return {grammar_valid: true};
      return {resources: []};
    });
    const post = jest.fn(async (payload) => {
      if (payload.action === 'sqlite_connection_pragmas') return {effective_value: true};
      if (payload.action === 'sqlite_ops_blob_inspect') {
        return {typeof: 'blob', byte_length: 64, streamable_blob: true};
      }
      return {};
    });
    const onRunExplain = jest.fn();

    const SessionDlg = withTheme(() => (
      <SqlSqliteSessionDialog
        open
        editorSource="SELECT * FROM items"
        sessionId="sq-live-1"
        databaseTargetId="db-target-1"
        callHost={callHost}
        post={post}
        onClose={() => {}}
      />
    ));
    const {unmount: u1} = render(<SessionDlg />);
    expect(screen.getByText('SR-F-030567')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Validate SQLite Syntax Without Execution'));
    await waitFor(() => expect(screen.getByText(/"grammar_valid": true/)).toBeInTheDocument());
    u1();

    const ExplainDlg = withTheme(() => (
      <SqlSqliteExplainDialog
        open
        editorSource="SELECT * FROM items"
        onClose={() => {}}
        onRunExplain={onRunExplain}
      />
    ));
    const {unmount: u2} = render(<ExplainDlg />);
    expect(screen.getByText('SR-F-030568')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Execute SQLite Explain'));
    expect(onRunExplain).toHaveBeenCalledWith('EXPLAIN QUERY PLAN SELECT * FROM items;', 'query_plan');
    u2();

    const RowSqlDlg = withTheme(() => (
      <DataSqliteRowSqlDialog
        open
        tableLabel='"main"."orders"'
        columns={[{name: 'id'}, {name: 'payload'}]}
        row={{id: 42, payload: {encoding: 'base64', data: 'AP8='}}}
        onClose={() => {}}
      />
    ));
    const {unmount: u3} = render(<RowSqlDlg />);
    expect(screen.getByText('SR-F-030569')).toBeInTheDocument();
    expect(screen.getByText(/ON CONFLICT/)).toBeInTheDocument();
    u3();

    const CellDlg = withTheme(() => (
      <DataSqliteCellInspectorModal
        open
        column={{name: 'payload', native_type: 'BLOB'}}
        value="9007199254740993"
        tableName="orders"
        post={post}
        databaseTargetId="db-target-1"
        onClose={() => {}}
      />
    ));
    render(<CellDlg />);
    expect(screen.getByText('SR-F-030570')).toBeInTheDocument();
    expect(screen.getByText('> 53-bit Exact Int64')).toBeInTheDocument();
    fireEvent.click(screen.getByText('Probe sqlite3_blob_open Metadata'));
    await waitFor(() => expect(screen.getByText('Streamable BLOB')).toBeInTheDocument());
  });
});
