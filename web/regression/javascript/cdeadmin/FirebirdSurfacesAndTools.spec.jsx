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
  SqlFirebirdSessionToolsDialog,
  SqlPersistentHistoryPanel,
  SqlProfilerAndStatsView,
  SqlProfilerConsentDialog,
} from 'sources/cdeadmin_ui/surfaces/SqlFirebirdDiagnostics';
import {
  DataFirebirdBlobDialog,
  DataFirebirdRowSqlDialog,
} from 'sources/cdeadmin_ui/surfaces/DataFirebirdTools';
import OperationDialog from 'sources/cdeadmin_ui/objects/OperationDialog';
import FirebirdTestData from 'sources/Dialogs/FirebirdTestData';
import {SchemaCompareWorkspace} from 'sources/cdeadmin_ui/modules/schema_compare';

describe('Firebird surfaced SQL, Data, Operation, Recipe & Schema Compare UX (FB-UI-08..FB-UI-16)', () => {
  it('FB-UI-08: renders native RDB$PROFILER report and MON$ attachment statistics in Metrics & Plan', () => {
    const ThemedView = withTheme(SqlProfilerAndStatsView);
    render(
      <ThemedView
        statistics={{
          complete: true,
          scope: 'MON$ATTACHMENT',
          elapsed: 482000,
          before: {attachment_id: 14, counters: {page_reads: 2, page_fetches: 18}},
          after: {attachment_id: 14, counters: {page_reads: 5, page_fetches: 42}},
          deltas: {page_reads: 3, page_fetches: 24},
        }}
        profiling={{
          state: 'complete',
          profile_id: '9001',
          session: {session_id: '9001', description: 'ScratchRobin profile'},
          requests: [{request_id: '1', total_elapsed_time: 410000}],
          psql_summary: [{line_num: 4, column_num: 1, counter: 2, total_elapsed_time: 310000}],
        }}
      />
    );
    expect(screen.getByText('Attachment Query Statistics (MON$)')).toBeVisible();
    expect(screen.getByText('page_fetches')).toBeVisible();
    expect(screen.getByText('24')).toBeVisible();
    expect(screen.getByText('Native SQL / PSQL Profile (RDB$PROFILER)')).toBeVisible();
    expect(screen.getByText('9001')).toBeVisible();
  });

  it('FB-UI-08: requires explicit consent before RDB$PROFILER execution', () => {
    const ThemedConsent = withTheme(SqlProfilerConsentDialog);
    const onConfirm = jest.fn();
    render(<ThemedConsent open onConfirm={onConfirm} onClose={jest.fn()} />);
    expect(screen.getAllByText(/RDB\$PROFILER/i).length).toBeGreaterThan(0);
    const runBtn = screen.getByRole('button', {name: /Start Profiler & Run Statement/i});
    expect(runBtn).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox'));
    expect(runBtn).not.toBeDisabled();
    fireEvent.click(runBtn);
    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it('FB-UI-09: loads, configures, and clears persistent Firebird SQL history', async () => {
    const post = jest.fn(async (payload) => {
      if (payload.action === 'query_history_read') {
        return {
          config: {retention_limit: 500, logging_enabled: true},
          entries: [
            {
              entry_id: 'h-1',
              recorded_at: '2026-11-21T10:00:00Z',
              source: 'SELECT * FROM EMPLOYEE',
              statement_kind: 'SELECT',
              client_sql_dialect: 3,
              status: 'succeeded',
            },
          ],
          total: 1,
        };
      }
      return {config: {retention_limit: 250, logging_enabled: true}, entries: [], total: 0};
    });
    const onLoadSql = jest.fn();
    const ThemedHistory = withTheme(SqlPersistentHistoryPanel);
    render(<ThemedHistory post={post} databaseTargetId="db-1" onLoadSql={onLoadSql} />);
    expect(await screen.findByText(/SELECT \* FROM EMPLOYEE/)).toBeVisible();
    fireEvent.click(screen.getByRole('button', {name: /Load into Editor/i}));
    expect(onLoadSql).toHaveBeenCalledWith('SELECT * FROM EMPLOYEE');
  });

  it('FB-UI-10: surfaces EDS External Connection Pool inventory, review/apply, traps, and stream reader', async () => {
    const post = jest.fn(async (payload) => {
      if (payload.action === 'firebird_eds_pool') {
        return {
          pool_active: true,
          pool_size: 16,
          pool_lifetime_seconds: 120,
          connections: [{connection_id: 'eds-1', remote_database: 'localhost:/data/peer.fdb', idle: true}],
        };
      }
      if (payload.action === 'firebird_eds_pool_receipts') {
        return {receipts: []};
      }
      return {};
    });
    const ThemedDialog = withTheme(SqlFirebirdSessionToolsDialog);
    render(
      <ThemedDialog
        open
        onClose={jest.fn()}
        post={post}
        databaseTargetId="db-1"
        sessionId="sess-1"
        ensureSession={async () => 'sess-1'}
        sqlSource="SELECT 1 FROM RDB$DATABASE"
        onExecuteTrapSql={jest.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', {name: /Inspect Native EDS Pool/i}));
    expect(await screen.findByText(/localhost:\/data\/peer\.fdb/)).toBeVisible();
  });

  it('FB-UI-11: edits UTF-8/Hex BLOB values and generates selected-row Firebird SQL with SqlEditor handoff', () => {
    const onApplyValue = jest.fn();
    const ThemedBlob = withTheme(DataFirebirdBlobDialog);
    const {unmount} = render(
      <ThemedBlob
        open
        column={{name: 'NOTES', data_type: 'BLOB SUB_TYPE TEXT', input_kind: 'text', nullable: true}}
        rawValue="Initial note"
        onApplyValue={onApplyValue}
        onClose={jest.fn()}
      />
    );
    const area = screen.getByRole('textbox');
    fireEvent.change(area, {target: {value: 'Updated Firebird BLOB text'}});
    fireEvent.click(screen.getByRole('button', {name: /Stage in Row/i}));
    expect(onApplyValue).toHaveBeenCalledWith('Updated Firebird BLOB text');
    unmount();

    const onOpenInSqlEditor = jest.fn();
    const ThemedRowSql = withTheme(DataFirebirdRowSqlDialog);
    render(
      <ThemedRowSql
        open
        tableName="CUSTOMER"
        columns={[
          {name: 'CUST_NO', data_type: 'INTEGER', primary_key: true, insertable: true, updatable: true},
          {name: 'CUSTOMER', data_type: 'VARCHAR(25)', insertable: true, updatable: true},
        ]}
        fetchedRows={[{CUST_NO: 1001, CUSTOMER: 'Signature Design'}]}
        initialSelectedIndices={[0]}
        onOpenInSqlEditor={onOpenInSqlEditor}
        onClose={jest.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', {name: /Generate SQL Preview/i}));
    fireEvent.click(screen.getByRole('button', {name: /Load into SQL Editor/i}));
    expect(onOpenInSqlEditor).toHaveBeenCalledWith(
      expect.objectContaining({source: expect.stringContaining('INSERT INTO')})
    );
  });

  it('FB-UI-13: renders structured FirebirdServiceObservation inside OperationDialog on completion', async () => {
    const ThemedOp = withTheme(OperationDialog);
    const plan = jest.fn().mockResolvedValue({
      state: 'ready',
      execution_available: true,
      statements: ['-- gstat -h'],
      warnings: [],
    });
    const apply = jest.fn().mockResolvedValue({
      provider_result: {
        driver_observation: {
          schema: 'cdeadmin.firebird-service-result.v1',
          operation_id: 'database_statistics',
          database: '/data/employee.fdb',
          server_completed: true,
          output_truncated: false,
          output: ['Database header page information:\n', '    ODS version 13.1\n'],
          service_release: {service_handle_released: true},
        },
      },
    });
    render(
      <ThemedOp
        open
        operation={{
          operation_id: 'database_statistics',
          title: 'Database statistics (gstat)',
          tier: 2,
          produces_log: true,
          fields: [],
        }}
        targetName="employee.fdb"
        plan={plan}
        apply={apply}
        onClose={jest.fn()}
      />
    );
    fireEvent.click(screen.getByRole('button', {name: 'Preview and run'}));
    expect(await screen.findByLabelText('Firebird service result')).toHaveTextContent('/data/employee.fdb');
    expect(screen.getByLabelText('Firebird native service output')).toHaveTextContent('ODS version 13.1');
  });

  it('FB-UI-14: loads and saves server-stored Firebird test-data recipes via firebird_recipe_read/save', async () => {
    const savedRecipe = {
      format: 'scratchrobin.firebird.test-data@1',
      scope: {endpoint_id: 'ep-1', database_target_id: 'db-1'},
      seed: 7,
      tables: [{table: 'T', count: 5, columns: {ID: {kind: 'default'}}}],
    };
    const post = jest.fn(async (req) => {
      if (req.action === 'firebird_recipe_read') {
        return {current_version: 2, version: 2, recipe: savedRecipe};
      }
      if (req.action === 'firebird_recipe_save') {
        return {current_version: 3, version: 3, recipe: req.request.recipe};
      }
      return {};
    });
    const ThemedTestData = withTheme(FirebirdTestData);
    render(
      <ThemedTestData
        resources={[{resource_kind: 'table', resource_id: 'table:T', display_name: 'T', display_path: ['T'], native: {}}]}
        post={post}
        databaseTargetId="db-1"
        endpointId="ep-1"
        languageProfile="firebird-sql"
      />
    );
    fireEvent.click(screen.getByRole('button', {name: 'Load server recipe'}));
    await waitFor(() =>
      expect(screen.getByLabelText('Test-data recipe JSON').value).toContain('"seed": 7')
    );
    fireEvent.click(screen.getByRole('button', {name: 'Save server recipe (v2)'}));
    await waitFor(() =>
      expect(post).toHaveBeenCalledWith(
        expect.objectContaining({
          action: 'firebird_recipe_save',
          request: expect.objectContaining({expected_version: 2, recipe_id: 'default'}),
        })
      )
    );
  });

  it('FB-UI-16: updates SchemaCompareWorkspace normalization options via typed checkboxes', () => {
    const sessionObj = {
      schema: 'cdeadmin.schema-compare.session.v1',
      id: 'sc-1',
      state: 'empty',
      dirty: false,
      activeTaskId: null,
      error: '',
      selectedDiffId: null,
      content: {leftRef: null, rightRef: null, options: {}, acceptedMappings: [], ignoredDiffs: []},
      result: null,
      plan: null,
      validation: null,
    };
    const service = {
      get: jest.fn(() => sessionObj),
      list: jest.fn(() => [sessionObj]),
      subscribe: jest.fn(() => () => {}),
      selectDiff: jest.fn(),
      reportError: jest.fn(),
    };
    const executeCommand = jest.fn().mockResolvedValue({});
    const ThemedCompare = withTheme(SchemaCompareWorkspace);
    render(<ThemedCompare service={service} sessionId="sc-1" executeCommand={executeCommand} />);
    fireEvent.click(screen.getByLabelText('Ignore SQL body whitespace differences'));
    expect(executeCommand).toHaveBeenCalledWith(
      'schema_compare.session.create',
      {configureSessionId: 'sc-1', options: {ignoreWhitespace: true}},
      expect.objectContaining({sessionId: 'sc-1'})
    );
  });
});
