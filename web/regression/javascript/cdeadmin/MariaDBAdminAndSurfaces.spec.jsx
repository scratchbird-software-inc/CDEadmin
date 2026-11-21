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
  MARIADB_ADMIN_TABS,
  MariaDBArchiveRetentionWorkspace,
  MariaDBGaleraWorkspace,
  MariaDBHostWorkspace,
  MariaDBPhysicalWorkspace,
  MariaDBUpgradeWorkspace,
  MariaDBUtilityWorkspace,
  renderMariaDBAdminWorkspace,
} from 'sources/cdeadmin_ui/modules/mariadb_admin';
import {
  SqlMariaDBAnalyzeConsentDialog,
  SqlMariaDBSessionDialog,
} from 'sources/cdeadmin_ui/surfaces/SqlMariaDBDiagnostics';
import {SqlMySQLPlanGraphView} from 'sources/cdeadmin_ui/surfaces/SqlMySQLDiagnostics';
import {DataMySQLRowSqlDialog} from 'sources/cdeadmin_ui/surfaces/DataMySQLTools';

describe('MariaDB surfaced Administration, Continuity, Host Utilities, SQL & Data Tools (MDB-UI-01..12)', () => {
  it('MDB-UI-01: inspects source, reviews & starts physical backup, and supports one-use cutover', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'mariadb_physical_inspect') {
          return {
            data: {
              success: 1,
              data: {
                source: {version: '12.2.2-MariaDB', server_uid: 'uid-mariadb-1'},
                state: {datadir: '/var/lib/mysql', gtid_binlog_pos: '0-1-42'},
              },
            },
          };
        }
        if (payload.action === 'mariadb_physical_list') {
          return {data: {success: 1, data: {jobs: []}}};
        }
        if (payload.action === 'mariadb_physical_cutover_list') {
          return {data: {success: 1, data: {cutovers: []}}};
        }
        if (payload.action === 'mariadb_physical_review') {
          return {
            data: {
              success: 1,
              data: {
                job_id: 'mb-phys-1',
                state: 'reviewed',
                review_digest: 'digest-phys-1',
                warnings: ['Full physical backup runs mariadb-backup.'],
                options: payload.request.options,
              },
            },
          };
        }
        if (payload.action === 'mariadb_physical_start') {
          return {
            data: {
              success: 1,
              data: {job_id: 'mb-phys-1', phase: 'backup', state: 'completed'},
            },
          };
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const Themed = withTheme(MariaDBPhysicalWorkspace);
    render(<Themed endpointUrl="/browser/server/cde_workspace/1/9?database_target_id=sales" api={api} />);

    expect(await screen.findByText(/uid-mariadb-1/i)).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: /Review Physical Operation/i}));
    expect(await screen.findByText(/mb-phys-1/i)).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: /Confirm & Start Physical Job/i}));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/browser/server/cde_workspace/1/9',
        expect.objectContaining({
          action: 'mariadb_physical_start',
          request: {job_id: 'mb-phys-1', review_digest: 'digest-phys-1', confirmed: true},
        })
      );
    });
  });

  it('MDB-UI-02..05: renders Archive Retention, Host Config/Service, Server Upgrade & Galera Cluster workspaces via renderMariaDBAdminWorkspace', async () => {
    expect(MARIADB_ADMIN_TABS).toEqual([
      'mariadb-physical',
      'mariadb-archive-retention',
      'mariadb-host',
      'mariadb-upgrade',
      'mariadb-galera',
      'mariadb-utilities',
    ]);

    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'mariadb_binlog_hold_list') {
          return {
            data: {
              success: 1,
              data: {holds: [{hold_id: 'hold-01', hold_kind: 'physical_backup', state: 'active', gtid_pos: '0-1-10'}]},
            },
          };
        }
        if (payload.action === 'mariadb_host_service_status') {
          return {data: {success: 1, data: {running: true, service_mode: 'managed_daemon'}}};
        }
        if (payload.action === 'mariadb_upgrade_inspect_source') {
          return {data: {success: 1, data: {version: '11.8.2-MariaDB', datadir: '/var/lib/mysql', server_uid: 'uid-up'}}};
        }
        if (payload.action === 'mariadb_galera_inspect') {
          return {
            data: {
              success: 1,
              data: {
                galera_available: true,
                cluster: {wsrep_cluster_status: 'Primary', wsrep_cluster_size: 3},
                local_member: {wsrep_local_state_comment: 'Synced', wsrep_last_committed: 991},
              },
            },
          };
        }
        return {data: {success: 1, data: {jobs: [], chains: []}}};
      }),
    };

    const WrapArchive = withTheme(() =>
      renderMariaDBAdminWorkspace({tab: 'mariadb-archive-retention', endpointUrl: '/ep', api})
    );
    const {unmount: u1} = render(<WrapArchive />);
    expect(await screen.findByText(/hold-01/i)).toBeVisible();
    u1();

    const WrapHost = withTheme(() =>
      renderMariaDBAdminWorkspace({tab: 'mariadb-host', endpointUrl: '/ep', api})
    );
    const {unmount: u2} = render(<WrapHost />);
    expect(await screen.findByText(/Daemon Running/i)).toBeVisible();
    u2();

    const WrapUpgrade = withTheme(() =>
      renderMariaDBAdminWorkspace({tab: 'mariadb-upgrade', endpointUrl: '/ep', api})
    );
    const {unmount: u3} = render(<WrapUpgrade />);
    expect(await screen.findByText(/11\.8\.2-MariaDB/i)).toBeVisible();
    u3();

    const WrapGalera = withTheme(() =>
      renderMariaDBAdminWorkspace({tab: 'mariadb-galera', endpointUrl: '/ep', api})
    );
    const {unmount: u4} = render(<WrapGalera />);
    expect(await screen.findByText(/wsrep Provider Loaded/i)).toBeVisible();
    expect(screen.getAllByText(/Synced/i).length).toBeGreaterThan(0);
    u4();
  });

  it('MDB-UI-06: reviews and starts supervised MariaDB 12.2.2 host utilities (aria_chk..mariadb-slap)', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'mariadb_utility_catalog') {
          return {
            data: {
              success: 1,
              data: {
                engine: 'mariadb',
                version: '12.2.2',
                utilities: [{operation_id: 'run_aria_chk', native_utility: 'aria_chk', title: 'Check Aria table'}],
              },
            },
          };
        }
        if (payload.action === 'resource_page') {
          return {
            data: {
              success: 1,
              data: {items: [{resource_kind: 'server', resource_id: 'server:MariaDB', display_name: 'MariaDB-12'}]},
            },
          };
        }
        if (payload.action === 'mariadb_utility_list') {
          return {data: {success: 1, data: {jobs: []}}};
        }
        if (payload.action === 'mariadb_utility_review') {
          return {
            data: {
              success: 1,
              data: {
                job_id: 'mautil-job-77',
                state: 'reviewed',
                review_digest: 'sha256-ma-77',
                command_preview: {preview: 'aria_chk --check /var/lib/mysql/sales/ledger.MAI'},
                warnings: [],
              },
            },
          };
        }
        if (payload.action === 'mariadb_utility_start') {
          return {
            data: {
              success: 1,
              data: {job_id: 'mautil-job-77', state: 'completed', utility: 'aria_chk'},
            },
          };
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const ThemedUtil = withTheme(MariaDBUtilityWorkspace);
    render(<ThemedUtil endpointUrl="/browser/server/cde_workspace/1/9?database_target_id=sales" databaseTargetId="sales" api={api} />);

    expect(await screen.findByText(/MariaDB-12/i)).toBeVisible();
    fireEvent.change(screen.getByLabelText(/Table Name/i), {target: {value: 'ledger'}});
    fireEvent.click(screen.getByRole('button', {name: /Review MariaDB Utility Run/i}));

    expect((await screen.findAllByText(/mautil-job-77/i)).length).toBeGreaterThan(0);
    fireEvent.click(screen.getByRole('button', {name: /Confirm & Start Utility Job/i}));

    await waitFor(() => {
      expect(api.post).toHaveBeenCalledWith(
        '/browser/server/cde_workspace/1/9',
        expect.objectContaining({
          action: 'mariadb_utility_review',
          request: expect.objectContaining({
            operation_id: 'run_aria_chk',
            target_resource: expect.objectContaining({display_name: 'MariaDB-12'}),
          }),
        })
      );
      expect(api.post).toHaveBeenCalledWith(
        '/browser/server/cde_workspace/1/9',
        expect.objectContaining({action: 'mariadb_utility_start'})
      );
    });
  });

  it('MDB-UI-08..10: surfaces MariaDB Session Variables/Flagsets/Context, ANALYZE FORMAT=JSON operator actuals, and REPLACE INTO row SQL', async () => {
    const callHost = jest.fn(async (action) => {
      if (action === 'mariadb_editor_context') {
        return {context: {sql_mode: 'STRICT_TRANS_TABLES,ORACLE', temporary_table_count: 2}};
      }
      if (action === 'mariadb_session_variables') {
        return {variable: 'sql_mode', effective_value: 'STRICT_TRANS_TABLES', expected_value: 'STRICT_TRANS_TABLES', ready_to_apply: true};
      }
      if (action === 'mariadb_session_flagsets') {
        return {variable: 'optimizer_switch', effective_value: 'index_merge=on', expected_value: 'index_merge=on', ready_to_apply: true};
      }
      return {};
    });

    const ThemedDiag = withTheme(SqlMariaDBSessionDialog);
    const {unmount: uDiag} = render(
      <ThemedDiag
        open
        transaction={{provider_payload: {autocommit: false, in_transaction: true}}}
        callHost={callHost}
        onClose={jest.fn()}
      />
    );

    fireEvent.click(screen.getByRole('button', {name: /Refresh Session Context & Temporary Tables/i}));
    expect(await screen.findByText(/STRICT_TRANS_TABLES,ORACLE/i)).toBeVisible();

    fireEvent.click(screen.getByRole('button', {name: /Review Assignment/i}));
    expect(await screen.findByRole('button', {name: /Confirm & Apply SET SESSION/i})).toBeVisible();
    uDiag();

    // MDB-UI-09: MariaDB ANALYZE FORMAT=JSON actual measurements (r_loops, r_rows, r_total_time_ms)
    const analyzeJson = JSON.stringify({
      query_block: {
        select_id: 1,
        r_loops: 1,
        r_total_time_ms: 0.412,
        table: {
          table_name: 'orders',
          access_type: 'ALL',
          r_loops: 1,
          r_rows: 128,
          r_total_time_ms: 0.301,
        },
      },
    });
    const ThemedPlan = withTheme(SqlMySQLPlanGraphView);
    const {unmount: uPlan} = render(<ThemedPlan planText={analyzeJson} />);
    expect(screen.getAllByText(/Native actual measurements/i).length).toBeGreaterThan(0);
    expect(screen.getByText(/r_rows: 128/i)).toBeVisible();
    uPlan();

    // ANALYZE FORMAT=JSON consent dialog
    const onConfirmAnalyze = jest.fn();
    const ThemedConsent = withTheme(SqlMariaDBAnalyzeConsentDialog);
    const {unmount: uConsent} = render(<ThemedConsent open onConfirm={onConfirmAnalyze} onClose={jest.fn()} />);
    const execBtn = screen.getByRole('button', {name: /Execute ANALYZE FORMAT=JSON/i});
    expect(execBtn).toBeDisabled();
    fireEvent.click(screen.getByLabelText(/I understand ANALYZE FORMAT=JSON executes this statement/i));
    expect(execBtn).not.toBeDisabled();
    fireEvent.click(execBtn);
    expect(onConfirmAnalyze).toHaveBeenCalledTimes(1);
    uConsent();

    // MDB-UI-10: Selected-row SQL generator supports MariaDB/MySQL row SQL handoff
    const onOpenInSqlEditor = jest.fn();
    const ThemedRowSql = withTheme(DataMySQLRowSqlDialog);
    render(
      <ThemedRowSql
        open
        tableName="orders"
        columns={[
          {name: 'id', primary_key: true, insertable: true, editable: true},
          {name: 'status', insertable: true, editable: true},
        ]}
        fetchedRows={[{id: 10, status: 'shipped'}]}
        initialSelectedIndices={[0]}
        onOpenInSqlEditor={onOpenInSqlEditor}
        onClose={jest.fn()}
      />
    );
    fireEvent.click(screen.getByLabelText(/Inline SQL scalar literals/i));
    fireEvent.click(screen.getByRole('button', {name: /Generate SQL Preview/i}));
    fireEvent.click(screen.getByRole('button', {name: /Load into SQL Editor/i}));
    expect(onOpenInSqlEditor).toHaveBeenCalledWith(
      expect.objectContaining({
        source: "INSERT INTO `orders` (`id`, `status`) VALUES (10, 'shipped');",
      })
    );
  });
});
