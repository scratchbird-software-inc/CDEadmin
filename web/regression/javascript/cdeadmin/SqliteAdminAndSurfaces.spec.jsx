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

describe('SQLite Native Administration Workspaces (SQ-AUD-09, 10, 11, 12, 13, 15)', () => {
  it('SQ-AUD-09 (SR-F-030560): renders RBU workspace, opens vacuum/update, steps, pauses and resumes', async () => {
    expect(SQLITE_ADMIN_TABS).toEqual([
      'sqlite-rbu',
      'sqlite-expert',
      'sqlite-intck',
      'sqlite-blob-stream',
      'sqlite-shell',
      'sqlite-sql-dump',
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
});
