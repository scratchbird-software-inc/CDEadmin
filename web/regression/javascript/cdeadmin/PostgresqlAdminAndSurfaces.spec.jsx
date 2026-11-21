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
  POSTGRESQL_ADMIN_TABS,
  PostgresqlConfigurationWorkspace,
  PostgresqlHaTopologyWorkspace,
  PostgresqlHostToolsWorkspace,
  PostgresqlPreparedXactsWorkspace,
  PostgresqlSnapshotCopyWorkspace,
  renderPostgresqlAdminWorkspace,
} from 'sources/cdeadmin_ui/modules/postgresql_admin';
import {
  SqlPostgresAnalyzeConsentDialog,
  SqlPostgresSessionDialog,
} from 'sources/cdeadmin_ui/surfaces/SqlPostgresDiagnostics';
import {
  DataPostgresCellInspectorModal,
  DataPostgresRowSqlDialog,
} from 'sources/cdeadmin_ui/surfaces/DataPostgresTools';

describe('PostgreSQL surfaced Administration, Host Utilities, Continuity/HA, Snapshot, SQL & Data Tools (PG-UI-01..09)', () => {
  it('PG-UI-01: loads catalog, reviews and starts supervised PostgreSQL 18 host utilities', async () => {
    expect(POSTGRESQL_ADMIN_TABS).toEqual([
      'postgresql-host-tools',
      'postgresql-configuration',
      'postgresql-ha-topology',
      'postgresql-prepared-xacts',
      'postgresql-snapshot-copy',
    ]);

    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'postgresql_host_tools' && payload.request.stage === 'catalog') {
          return {
            data: {
              success: 1,
              data: {
                hostname: 'pg-host-01',
                clusters: [{id: 'pg18_main'}],
                init_roots: [{id: 'init_root_1'}],
                archive_dirs: [{id: 'wal_arch_1'}],
                upgrade_pairs: [{id: 'pg17_to_18'}],
              },
            },
          };
        }
        if (payload.action === 'postgresql_host_tools' && payload.request.stage === 'list') {
          return {data: {success: 1, data: {jobs: []}}};
        }
        if (payload.action === 'postgresql_host_tools' && payload.request.stage === 'review') {
          return {
            data: {
              success: 1,
              data: {
                job_id: 'pg-util-1',
                operation_id: payload.request.operation_id,
                review_digest: 'digest-pg-util-1',
                state: 'reviewed',
              },
            },
          };
        }
        if (payload.action === 'postgresql_host_tools' && payload.request.stage === 'start') {
          return {
            data: {
              success: 1,
              data: {
                job_id: 'pg-util-1',
                operation_id: 'host_pg_controldata',
                state: 'completed',
              },
            },
          };
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Themed = withTheme(PostgresqlHostToolsWorkspace);
    render(<Themed endpointUrl="/browser/server/cde_workspace/1/5" api={api} />);

    await waitFor(() => {
      expect(screen.getByRole('button', {name: /Review Utility Plan/i})).not.toBeDisabled();
    });
    fireEvent.click(screen.getByRole('button', {name: /Review Utility Plan/i}));
    expect(await screen.findByText(/digest-pg-util-1/i)).toBeVisible();

    fireEvent.click(screen.getByLabelText(/Confirm one-time utility dispatch/i));
    fireEvent.click(screen.getByRole('button', {name: /Start Supervised Utility/i}));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/browser/server/cde_workspace/1/5',
        expect.objectContaining({
          action: 'postgresql_host_tools',
          request: {
            stage: 'start',
            job_id: 'pg-util-1',
            review_digest: 'digest-pg-util-1',
            confirmed: true,
          },
        })
      );
    });
  });

  it('PG-UI-02..05: renders Configuration, HA Topology, Prepared 2PC & Snapshot Copy workspaces via renderPostgresqlAdminWorkspace', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'postgresql_config_list') {
          return {data: {success: 1, data: {jobs: []}}};
        }
        if (payload.action === 'postgresql_config_inspect_file') {
          return {
            data: {
              success: 1,
              data: {
                file_kind: 'postgresql.conf',
                content: "shared_buffers = '256MB'\n",
                sha256: 'abc123',
                redacted: false,
              },
            },
          };
        }
        if (payload.action === 'postgresql_ha_topology') {
          return {
            data: {
              success: 1,
              data: {
                role: 'primary',
                in_recovery: false,
                server_version_num: 180003,
                replicas: [{application_name: 'standby1', state: 'streaming'}],
              },
            },
          };
        }
        if (payload.action === 'resource_page') {
          return {
            data: {
              success: 1,
              data: {items: [{resource_kind: 'server', resource_id: 'postgresql:server/5', display_name: 'PG 18'}]},
            },
          };
        }
        if (payload.action === 'visual_admin_plan') {
          return {
            data: {
              success: 1,
              data: {
                plan_id: 'plan-2pc-1',
                plan_digest: 'digest-2pc-1',
                command_preview: {statement: "ROLLBACK PREPARED 'gid_orphan_1'"},
              },
            },
          };
        }
        if (payload.action === 'visual_admin_apply') {
          return {
            data: {
              success: 1,
              data: {
                result: {
                  rows: [{gid: 'gid_orphan_1', database: 'postgres', owner: 'postgres', transaction: '777'}],
                },
              },
            },
          };
        }
        if (payload.action === 'postgresql_runtime_capabilities') {
          return {
            data: {
              success: 1,
              data: {
                encoding: {server_encoding: 'UTF8'},
                version_capabilities: {public_version: '18.3'},
                installed_extensions: [{name: 'plpgsql'}],
              },
            },
          };
        }
        if (payload.action === 'postgresql_snapshot_output_plugins') {
          return {
            data: {
              success: 1,
              data: {plugins: [{plugin: 'pgoutput', installed: true}]},
            },
          };
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const WrapConfig = withTheme(() =>
      renderPostgresqlAdminWorkspace({tab: 'postgresql-configuration', endpointUrl: '/ep', api})
    );
    const {unmount: u1} = render(<WrapConfig />);
    expect(await screen.findByText(/SR-F-030451/i)).toBeVisible();
    u1();

    const WrapHa = withTheme(() =>
      renderPostgresqlAdminWorkspace({tab: 'postgresql-ha-topology', endpointUrl: '/ep', api})
    );
    const {unmount: u2} = render(<WrapHa />);
    expect(await screen.findByText(/SR-F-030452/i)).toBeVisible();
    u2();

    const Wrap2pc = withTheme(() =>
      renderPostgresqlAdminWorkspace({tab: 'postgresql-prepared-xacts', endpointUrl: '/ep', api})
    );
    const {unmount: u3} = render(<Wrap2pc />);
    expect(await screen.findByText(/gid_orphan_1/i)).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: /^Select$/i}));
    fireEvent.click(screen.getByRole('button', {name: /Review Two-Phase Resolution/i}));
    expect(await screen.findByText(/ROLLBACK PREPARED 'gid_orphan_1'/i)).toBeVisible();
    u3();

    const WrapSnap = withTheme(() =>
      renderPostgresqlAdminWorkspace({tab: 'postgresql-snapshot-copy', endpointUrl: '/ep', api})
    );
    const {unmount: u4} = render(<WrapSnap />);
    expect(await screen.findByText(/pgoutput/i)).toBeVisible();
    u4();
  });

  it('PG-UI-06..09: validates non-executing target-major SQL, gates EXPLAIN ANALYZE consent, and generates PostgreSQL row SQL & cell inspection', async () => {
    const callHost = jest.fn(async (subAction, extra) => {
      if (subAction === 'validate_source') {
        return {valid: true, target_server_version: extra.target_server_version, diagnostics: []};
      }
      if (subAction === 'refresh_session_metadata') {
        return {schemas: ['pg_temp_3', 'public']};
      }
      return {};
    });

    const ThemedSession = withTheme(SqlPostgresSessionDialog);
    const {unmount: us} = render(
      <ThemedSession
        open
        transaction={{provider_payload: {transaction_status: 'INTRANS'}}}
        editorSource="SELECT 1;"
        callHost={callHost}
        onClose={jest.fn()}
      />
    );
    expect(screen.getByText(/INTRANS/i)).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: /Validate Editor SQL Without Execution/i}));
    await waitFor(() => {
      expect(callHost).toHaveBeenCalledWith(
        'validate_source',
        expect.objectContaining({target_server_version: 180000})
      );
    });
    us();

    const onConfirmAnalyze = jest.fn();
    const ThemedAnalyze = withTheme(SqlPostgresAnalyzeConsentDialog);
    const {unmount: ua} = render(
      <ThemedAnalyze open onClose={jest.fn()} onConfirmAnalyze={onConfirmAnalyze} />
    );
    const execBtn = screen.getByRole('button', {name: /Execute EXPLAIN ANALYZE/i});
    expect(execBtn).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/I understand EXPLAIN ANALYZE executes the statement/i));
    expect(execBtn).not.toBeDisabled();
    fireEvent.click(execBtn);
    expect(onConfirmAnalyze).toHaveBeenCalledWith({
      analyze: true,
      buffers: true,
      wal: true,
      settings: true,
      generic_plan: false,
    });
    ua();

    const ThemedRowSql = withTheme(DataPostgresRowSqlDialog);
    const {unmount: ur} = render(
      <ThemedRowSql
        open
        tableLabel='"public"."orders"'
        columns={[{name: 'id'}, {name: 'note'}]}
        row={{id: 42, note: "it's ok"}}
        onClose={jest.fn()}
      />
    );
    expect(screen.getByText(/SR-F-030457/i)).toBeVisible();
    ur();

    const ThemedInspector = withTheme(DataPostgresCellInspectorModal);
    render(
      <ThemedInspector
        open
        column={{name: 'payload', native_type: 'jsonb'}}
        value={{hello: 'world'}}
        onClose={jest.fn()}
      />
    );
    expect(screen.getByText(/SR-F-030458/i)).toBeVisible();
    expect(screen.getAllByText(/jsonb/i).length).toBeGreaterThanOrEqual(2);
  });
});
