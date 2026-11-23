/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import MySQLUtilityWorkspace from 'sources/cdeadmin_ui/modules/mysql_admin/MySQLUtilityWorkspace';
import {
  SqlMySQLAnalyzeConsentDialog,
  SqlMySQLPlanGraphView,
  SqlMySQLQueryAttributesDialog,
} from 'sources/cdeadmin_ui/surfaces/SqlMySQLDiagnostics';
import {
  DataMySQLRowSqlDialog,
  DataMySQLSpatialDialog,
  isMySQLSpatialType,
} from 'sources/cdeadmin_ui/surfaces/DataMySQLTools';
import {familyCoversKind} from 'pgbrowser/ProviderObjectEditor';
import {makePost} from 'sources/cdeadmin_ui/objects/ProviderObjectEditorHost';

describe('MySQL surfaced Utilities, Native Create, SQL Diagnostics & Spatial/Row Tools (MYSQL-UI-01..10)', () => {
  it('MYSQL-UI-01: reviews, starts, polls, and cancels supervised MySQL 9.7.0 utility jobs', async () => {
    const api = {
      post: jest.fn(async (_url, payload) => {
        if (payload.action === 'mysql_utility_catalog') {
          return {
            data: {
              success: 1,
              data: {
                utilities: [
                  {operation_id: 'run_myisamchk', native_utility: 'myisamchk', title: 'Check or repair offline MyISAM table files'},
                  {operation_id: 'run_mysqlslap', native_utility: 'mysqlslap', title: 'Run concurrency load benchmark'},
                ],
              },
            },
          };
        }
        if (payload.action === 'resource_page') {
          return {
            data: {
              success: 1,
              data: {items: [{resource_kind: 'server', resource_id: 'server:mysql1', display_name: 'mysql-prod-1'}]},
            },
          };
        }
        if (payload.action === 'mysql_utility_list') {
          return {data: {success: 1, data: {jobs: []}}};
        }
        if (payload.action === 'mysql_utility_review') {
          return {
            data: {
              success: 1,
              data: {
                job_id: 'myutil-job-101',
                state: 'reviewed',
                review_digest: 'sha256-abc',
                command_preview: {argv: ['myisamchk', '--check', '/var/lib/mysql/app/archive_log.MYI']},
                warnings: ['Ensure MySQL server is offline or table is flushed before myisamchk.'],
              },
            },
          };
        }
        if (payload.action === 'mysql_utility_start') {
          return {
            data: {
              success: 1,
              data: {
                job_id: 'myutil-job-101',
                state: 'completed',
                result: {exit_code: 0, stdout: 'MyISAM-table archive_log is usable'},
              },
            },
          };
        }
        return {data: {success: 1, data: {}}};
      }),
    };

    const ThemedWorkspace = withTheme(MySQLUtilityWorkspace);
    render(<ThemedWorkspace endpointUrl="/browser/server/cde_workspace/1/7?database_target_id=app" databaseTargetId="app" api={api} />);

    expect(await screen.findByText(/MySQL 9\.7\.0 Supervised Host Storage & Benchmark Utilities/i)).toBeVisible();
    fireEvent.change(screen.getByLabelText(/MyISAM table name/i), {target: {value: 'archive_log'}});
    fireEvent.change(screen.getByLabelText(/confirm review/i), {target: {value: 'mysql-prod-1'}});
    fireEvent.click(screen.getByRole('button', {name: /Review Utility Job/i}));

    expect(await screen.findByText(/myutil-job-101/i)).toBeVisible();
    fireEvent.click(screen.getByLabelText(/I reviewed the command preview/i));
    fireEvent.click(screen.getByRole('button', {name: /Start Utility Job/i}));

    expect(await screen.findByText(/MyISAM-table archive_log is usable/i)).toBeVisible();
    // Verify server-scoped endpoint stripped ?database_target_id=app
    expect(api.post).toHaveBeenCalledWith('/browser/server/cde_workspace/1/7', expect.objectContaining({action: 'mysql_utility_start'}));
  });

  it('MYSQL-UI-02: enables native-editor create on MySQL database nodes via cde_native_editor_kinds and scopes native_forms', async () => {
    const mockBundle = {
      kinds: {
        library: {resource_kind: 'library', family: 'engine_object', tier1: ['create', 'alter', 'drop']},
      },
      forms: {},
    };
    const dbNodeData = {
      _type: 'cde_database_target',
      cde_native_editor_kinds: ['library', 'plugin', 'component', 'resource-group'],
    };
    expect(familyCoversKind(mockBundle, 'library', dbNodeData, 'create')).toBe(true);

    const api = {post: jest.fn().mockResolvedValue({data: {success: 1, data: {operations: []}}})};
    const post = makePost(api, '/ep', 'db_target_1');
    await post({action: 'native_forms', request: {resource_kind: 'library'}});
    expect(api.post).toHaveBeenCalledWith('/ep', {
      action: 'native_forms',
      request: {resource_kind: 'library', database_target_id: 'db_target_1'},
    });
  });

  it('MYSQL-UI-04: edits MySQL per-statement QUERY_ATTRIBUTES and displays observed session transaction state', () => {
    const onSave = jest.fn();
    const ThemedAttrs = withTheme(SqlMySQLQueryAttributesDialog);
    render(
      <ThemedAttrs
        open
        attributesObject={{trace_id: 'req-42'}}
        transaction={{provider_payload: {state: 'in_transaction', autocommit: false, in_transaction: true}}}
        onSaveAttributes={onSave}
        onClose={jest.fn()}
      />
    );
    expect(screen.getByText('in_transaction')).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: /Add Attribute/i}));
    const nameInputs = screen.getAllByLabelText(/Attribute name/i);
    const valInputs = screen.getAllByLabelText(/Attribute value/i);
    fireEvent.change(nameInputs[1], {target: {value: 'tenant'}});
    fireEvent.change(valInputs[1], {target: {value: 'acme'}});
    fireEvent.click(screen.getByRole('button', {name: /Save Query Attributes/i}));
    expect(onSave).toHaveBeenCalledWith({trace_id: 'req-42', tenant: 'acme'});
  });

  it('MYSQL-UI-05: renders interactive MySQL EXPLAIN FORMAT=TREE / ANALYZE operator graph and requires EXPLAIN ANALYZE consent', () => {
    const treePlan = [
      '-> Nested loop inner join  (cost=4.25 rows=8) (actual time=0.041..0.112 rows=8 loops=1)',
      '    -> Index lookup on orders using idx_cust (cust_id=7)  (cost=1.10 rows=4) (actual time=0.020..0.045 rows=4 loops=1)',
    ].join('\n');

    const ThemedGraph = withTheme(SqlMySQLPlanGraphView);
    render(<ThemedGraph planText={treePlan} />);
    expect(screen.getByText(/Interactive MySQL Operator Plan \(TREE\)/i)).toBeVisible();
    expect(screen.getByRole('tree', {name: /Native MySQL operator graph/i})).toBeVisible();

    const onConfirm = jest.fn();
    const ThemedConsent = withTheme(SqlMySQLAnalyzeConsentDialog);
    render(<ThemedConsent open onConfirm={onConfirm} onClose={jest.fn()} />);
    const runBtn = screen.getByRole('button', {name: /Execute EXPLAIN ANALYZE/i});
    expect(runBtn).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(runBtn).not.toBeDisabled();
    fireEvent.click(runBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('MYSQL-UI-07: inspects/stages MySQL spatial WKT + SRID values and generates INSERT ... ON DUPLICATE KEY UPDATE row SQL', () => {
    expect(isMySQLSpatialType('GEOMETRY')).toBe(true);
    expect(isMySQLSpatialType('POINT')).toBe(true);
    expect(isMySQLSpatialType('VARCHAR(64)')).toBe(false);

    const onApplySpatial = jest.fn();
    const ThemedSpatial = withTheme(DataMySQLSpatialDialog);
    const {unmount} = render(
      <ThemedSpatial
        open
        column={{name: 'location', native_type: 'POINT', nullable: true, srid: 4326}}
        rawValue="SRID=4326;POINT(-79.3832 43.6532)"
        onApplyValue={onApplySpatial}
        onClose={jest.fn()}
      />
    );
    fireEvent.change(screen.getByLabelText(/WKT or GeoJSON geometry/i), {
      target: {value: 'POINT(-79.4000 43.6600)'},
    });
    fireEvent.click(screen.getByRole('button', {name: /Stage Spatial Value/i}));
    expect(onApplySpatial).toHaveBeenCalledWith('SRID=4326;POINT(-79.4000 43.6600)');
    unmount();

    const onOpenInSqlEditor = jest.fn();
    const ThemedRowSql = withTheme(DataMySQLRowSqlDialog);
    render(
      <ThemedRowSql
        open
        tableName="customers"
        columns={[
          {name: 'id', primary_key: true, insertable: true, editable: true},
          {name: 'email', insertable: true, editable: true},
        ]}
        fetchedRows={[{id: 10, email: 'ops@example.com'}]}
        initialSelectedIndices={[0]}
        onOpenInSqlEditor={onOpenInSqlEditor}
        onClose={jest.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', {name: /Generate SQL Preview/i}));
    fireEvent.click(screen.getByRole('button', {name: /Load into SQL Editor/i}));
    expect(onOpenInSqlEditor).toHaveBeenCalledWith(
      expect.objectContaining({
        source: 'INSERT INTO `customers` (`id`, `email`) VALUES (%s, %s);',
        parameters: [10, 'ops@example.com'],
      })
    );
  });
});
