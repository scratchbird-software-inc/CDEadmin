/////////////////////////////////////////////////////////////
// Firebird native host, trace, lock-print, plugin, runtime/ODS,
// database encryption, and journal replication workspace gates.
/////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {
  FIREBIRD_ADMIN_TABS,
  FirebirdTraceWorkspace,
  FirebirdLockPrintWorkspace,
  FirebirdHostConfigWorkspace,
  FirebirdPluginDeploymentWorkspace,
  FirebirdRuntimeLifecycleWorkspace,
  FirebirdDatabaseEncryptionWorkspace,
  FirebirdReplicationWorkspace,
  renderFirebirdAdminWorkspace,
} from 'sources/cdeadmin_ui/modules/firebird_admin';
import {buildScopedEndpointUrl} from 'sources/cdeadmin_ui/modules/firebird_admin/firebirdAdminHelpers';

function makeMockPost(handlers = {}) {
  return jest.fn(async ({action, request = {}}) => {
    if (action === 'database_target_list') {
      return {
        targets: [
          {target_id: 'target-emp', display_name: 'employee.fdb', database_name: '/srv/fb/employee.fdb', active: true},
        ],
      };
    }
    if (action === 'resource_page') {
      return {
        items: [{resource_id: 'database:/srv/fb/employee.fdb', resource_kind: 'database', display_name: 'employee.fdb'}],
      };
    }
    if (handlers[action]) {
      return handlers[action](request);
    }
    return {};
  });
}

describe('FirebirdAdminWorkspaces (FB-UI-01 .. FB-UI-07)', () => {
  it('registers all 7 Firebird workspace tabs and scopes endpoint URLs cleanly', () => {
    expect(FIREBIRD_ADMIN_TABS).toEqual([
      'firebird-trace',
      'firebird-lock-print',
      'firebird-host-configuration',
      'firebird-plugin-deployment',
      'firebird-runtime-lifecycle',
      'firebird-database-encryption',
      'firebird-replication',
    ]);
    expect(buildScopedEndpointUrl('/browser/server/cde_workspace/1/4', 'target-emp')).toBe(
      '/browser/server/cde_workspace/1/4?database_target_id=target-emp'
    );
    expect(buildScopedEndpointUrl('/browser/server/cde_workspace/1/4?database_target_id=old', null)).toBe(
      '/browser/server/cde_workspace/1/4'
    );
    expect(renderFirebirdAdminWorkspace({tab: 'unknown-tab', endpointUrl: '/x'})).toBeNull();
  });

  it('FB-UI-01: reviews and applies a one-use Firebird trace session and polls output', async () => {
    const Trace = withTheme(FirebirdTraceWorkspace);
    const customPost = makeMockPost({
      firebird_trace: (req) => {
        if (req.action === 'describe') {
          return {
            option_fields: [{field_id: 'log_connections', control: 'checkbox', default: true}],
            service_option_fields: [{field_id: 'log_services', control: 'checkbox', default: true}],
          };
        }
        if (req.action === 'list') {
          return {items: [{trace_id: 'tr-1', name: 'Live Trace', state: 'active', native_session_id: 7}]};
        }
        if (req.action === 'review') {
          return {
            review_id: 'rev-trace-1',
            review_digest: 'abcdef0123456789abcdef',
            state: 'reviewed',
            operation: req.operation,
            expires_at: 1900000000,
            payload: {native_configuration: 'database = /srv/fb/employee.fdb {\n  enabled = true\n}'},
          };
        }
        if (req.action === 'apply') {
          return {review_id: req.review_id, state: 'submitted', outcome: {trace_id: 'tr-1', state: 'active'}};
        }
        if (req.action === 'poll') {
          return {lines: ['2026-11-21T10:00:00 ATTACH_DATABASE /srv/fb/employee.fdb']};
        }
        return {};
      },
    });

    render(<Trace endpointUrl="/ws/1" customPost={customPost} />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Review Trace Configuration'})).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', {name: 'Review Trace Configuration'}));
    await waitFor(() => expect(screen.getByText(/Reviewed Native Trace Operation/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', {name: 'Confirm & Apply Reviewed Operation'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Poll Output'})).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', {name: 'Poll Output'}));
    await waitFor(() =>
      expect(customPost).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'firebird_trace',
          request: expect.objectContaining({action: 'poll', trace_id: 'tr-1', database_target_id: 'target-emp'}),
        })
      )
    );
  });

  it('FB-UI-02: reviews and executes fb_lock_print diagnostics with structured summary', async () => {
    const LockPrint = withTheme(FirebirdLockPrintWorkspace);
    const customPost = makeMockPost({
      firebird_lock_print: (req) => {
        if (req.action === 'describe') return {notes: 'Native fb_lock_print'};
        if (req.action === 'list') return {items: []};
        if (req.action === 'review') {
          return {
            review_id: 'rev-lp-1',
            review_digest: '1234567890abcdef1234',
            state: 'reviewed',
            expires_at: 1900000000,
            payload: {cli_arguments: ['fb_lock_print', '-d', '/srv/fb/employee.fdb', '-o', '-w', '-l', '-c']},
          };
        }
        if (req.action === 'apply') {
          return {
            review_id: req.review_id,
            durable_summary: {
              state: 'completed',
              lock_table_state: 'healthy',
              owners_observed: 3,
              waiting_owners_observed: 0,
              locks_observed: 5,
            },
            outcome: {
              stdout: 'LOCK_HEADER BLOCK\n\tVersion: 145',
              parsed: {header: {version: 145}, owners: [], locks: []},
            },
          };
        }
        return {};
      },
    });

    render(<LockPrint endpointUrl="/ws/1" databaseTargetId="target-emp" customPost={customPost} />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Review fb_lock_print Command'})).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', {name: 'Review fb_lock_print Command'}));
    await waitFor(() => expect(screen.getByText(/Reviewed fb_lock_print Execution/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', {name: 'Confirm & Apply Reviewed Operation'}));
    await waitFor(() => expect(screen.getByText(/Lock Table Observation/i)).toBeInTheDocument());
  });

  it('FB-UI-03: inspects firebird.conf and applies reviewed SHA-256 compare-and-set updates', async () => {
    const HostCfg = withTheme(FirebirdHostConfigWorkspace);
    const customPost = makeMockPost({
      firebird_host_configuration: (req) => {
        if (req.action === 'describe') return {managed_files: ['firebird.conf']};
        if (req.action === 'list') return {items: []};
        if (req.action === 'inspect') {
          return {
            pending_restart_keys: ['DefaultDbCachePages'],
            files: {
              'firebird.conf': {
                exists: true,
                generation_sha256: 'sha256-gen-111122223333',
                size_bytes: 128,
                entries: {DefaultDbCachePages: {value: '2048'}},
              },
            },
          };
        }
        if (req.action === 'review') {
          return {
            review_id: 'rev-cfg-1',
            review_digest: 'cfgdigest1234567890',
            state: 'reviewed',
            expires_at: 1900000000,
            payload: {target_file: 'firebird.conf', rendered_text: 'DefaultDbCachePages = 4096\n'},
          };
        }
        if (req.action === 'apply') {
          return {review_id: req.review_id, state: 'submitted', outcome: {state: 'completed'}};
        }
        return {};
      },
    });

    render(<HostCfg endpointUrl="/ws/1" customPost={customPost} />);
    await waitFor(() => expect(screen.getByText(/Global configuration keys differ/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Configuration key/i), {target: {value: 'DefaultDbCachePages'}});
    fireEvent.change(screen.getByLabelText(/^Value$/i), {target: {value: '4096'}});
    fireEvent.click(screen.getByRole('button', {name: 'Stage Key'}));
    fireEvent.click(screen.getByRole('button', {name: 'Review firebird.conf Changes'}));
    await waitFor(() => expect(screen.getByText(/Reviewed Host Configuration Update/i)).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', {name: 'Confirm & Apply Reviewed Operation'}));
    await waitFor(() =>
      expect(customPost).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'firebird_host_configuration',
          request: expect.objectContaining({action: 'apply', review_id: 'rev-cfg-1', confirmed: true}),
        })
      )
    );
  });

  it('FB-UI-04: inspects plugin/UDR inventory and reviews UDR module deployment', async () => {
    const Plugins = withTheme(FirebirdPluginDeploymentWorkspace);
    const customPost = makeMockPost({
      firebird_plugin_deployment: (req) => {
        if (req.action === 'describe') {
          return {platform_constraints: {Win_Sspi: {reason: 'Windows SSPI unavailable on Linux.'}}};
        }
        if (req.action === 'list') return {items: []};
        if (req.action === 'inspect') {
          return {
            runtime_root: '/opt/firebird',
            plugins: [{module_name: 'Srp'}],
            udr_modules: [{module_name: 'udrcpp_example'}],
            database_udr_dependents: [],
          };
        }
        if (req.action === 'review') {
          return {
            review_id: 'rev-plg-1',
            review_digest: 'plgdigest12345678',
            state: 'reviewed',
            operation: req.operation,
            expires_at: 1900000000,
            payload: {module_name: req.module_name, destination_path: '/opt/firebird/plugins/udr/libmy_udr.so'},
          };
        }
        return {};
      },
    });

    render(<Plugins endpointUrl="/ws/1" customPost={customPost} />);
    await waitFor(() => expect(screen.getByText('/opt/firebird')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Module name/i), {target: {value: 'my_udr'}});
    fireEvent.click(screen.getByRole('button', {name: 'Review Plugin / UDR Operation'}));
    await waitFor(() => expect(screen.getByText(/Reviewed Module Operation: deploy_udr_module/i)).toBeInTheDocument());
  });

  it('FB-UI-05: probes database ODS header and reviews cross-ODS migration', async () => {
    const Runtime = withTheme(FirebirdRuntimeLifecycleWorkspace);
    const customPost = makeMockPost({
      firebird_runtime_lifecycle: (req) => {
        if (req.action === 'describe') return {native_ods_version: '13.1'};
        if (req.action === 'list') return {items: []};
        if (req.action === 'inspect') {
          return {
            runtime_root: '/opt/firebird',
            engine_version: '5.0.4',
            native_ods_version: '13.1',
            daemon_status: {state: 'running'},
          };
        }
        if (req.action === 'inspect_ods') {
          return {ods_text: '12.0', compatibility: 'requires_gbak_backup_restore', recommended_migration_route: 'gbak_backup_restore'};
        }
        if (req.action === 'review') {
          return {
            review_id: 'rev-ods-1',
            review_digest: 'odsdigest12345678',
            state: 'reviewed',
            operation: 'migrate_database',
            expires_at: 1900000000,
            payload: {migration_route: req.migration_route, target_database_path: req.target_database_path},
          };
        }
        return {};
      },
    });

    render(<Runtime endpointUrl="/ws/1" defaultOperation="migrate_database" customPost={customPost} />);
    await waitFor(() => expect(screen.getByText('Native ODS 13.1')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Canonical database file path on host/i), {target: {value: '/stage/legacy.fbk'}});
    fireEvent.click(screen.getByRole('button', {name: 'Inspect ODS'}));
    await waitFor(() => expect(screen.getByText(/Observed ODS 12.0/i)).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/New target database file path/i), {target: {value: '/stage/migrated.fdb'}});
    fireEvent.change(screen.getByLabelText(/Type exact target database filename/i), {target: {value: 'migrated.fdb'}});
    fireEvent.click(screen.getByRole('button', {name: 'Review Lifecycle Operation'}));
    await waitFor(() => expect(screen.getByText(/Reviewed Runtime \/ Migration Operation: migrate_database/i)).toBeInTheDocument());
  });

  it('FB-UI-06: inspects MON$CRYPT_STATE and plans/applies ALTER DATABASE ENCRYPT', async () => {
    const Encryption = withTheme(FirebirdDatabaseEncryptionWorkspace);
    const customPost = makeMockPost({
      firebird_database_encryption: (req) => {
        if (req.action === 'describe') return {external_plugin_dependency: 'DbCrypt plugin required'};
        if (req.action === 'inspect') {
          return {
            crypt_state_code: 0,
            crypt_state: 'not_encrypted',
            in_transition: false,
            crypt_page: 0,
            total_pages: 250,
          };
        }
        if (req.action === 'wait_settle') {
          return {crypt_state_code: 1, crypt_state: 'encrypted', in_transition: false, settled: true};
        }
        return {};
      },
      visual_admin_plan: () => ({
        plan_id: 'plan-enc-1',
        plan_digest: 'dg-enc-1',
        statements: ['ALTER DATABASE ENCRYPT WITH "DbCryptPlugin" KEY "MasterKey"'],
      }),
      visual_admin_apply: () => ({state: 'completed'}),
    });

    render(<Encryption endpointUrl="/ws/1" databaseTargetId="target-emp" customPost={customPost} />);
    await waitFor(() => expect(screen.getByText('not_encrypted')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/DbCrypt plugin name/i), {target: {value: 'DbCryptPlugin'}});
    fireEvent.change(screen.getByLabelText(/Key name/i), {target: {value: 'MasterKey'}});
    fireEvent.click(screen.getByRole('button', {name: 'Preview Native SQL Plan'}));
    await waitFor(() => expect(screen.getByRole('button', {name: 'Execute Reviewed DDL'})).toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', {name: 'Execute Reviewed DDL'}));
    await waitFor(() =>
      expect(customPost).toHaveBeenCalledWith(
        expect.objectContaining({action: 'visual_admin_apply'})
      )
    );
  });

  it('FB-UI-07: inspects journal replication state and reviews primary journal configuration', async () => {
    const Replication = withTheme(FirebirdReplicationWorkspace);
    const customPost = makeMockPost({
      firebird_replication: (req) => {
        if (req.action === 'describe') return {lag_authority: 'Unapplied journal segment count'};
        if (req.action === 'list') return {items: []};
        if (req.action === 'inspect') {
          return {
            database: {
              replica_mode: 'NONE',
              database_guid: '{11111111-2222-3333-4444-555555555555}',
              publications: [{name: 'RDB$DEFAULT', active: false}],
            },
          };
        }
        if (req.action === 'review') {
          return {
            review_id: 'rev-repl-1',
            review_digest: 'repldigest123456',
            state: 'reviewed',
            operation: 'configure_primary',
            expires_at: 1900000000,
            payload: {replication_conf_text: 'database = /srv/fb/employee.fdb {\n  journal_directory = /jrn\n}'},
          };
        }
        return {};
      },
    });

    render(<Replication endpointUrl="/ws/1" databaseTargetId="target-emp" customPost={customPost} />);
    await waitFor(() => expect(screen.getByText('Replica Mode: NONE')).toBeInTheDocument());
    fireEvent.change(screen.getByLabelText(/Active journal directory/i), {target: {value: '/jrn/active'}});
    fireEvent.change(screen.getByLabelText(/Journal archive directory/i), {target: {value: '/jrn/archive'}});
    fireEvent.click(screen.getByRole('button', {name: 'Review Replication Operation'}));
    await waitFor(() => expect(screen.getByText(/Reviewed Replication Operation: configure_primary/i)).toBeInTheDocument());
  });
});
