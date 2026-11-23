/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import DuckdbRuntimeSettingsWorkspace from './DuckdbRuntimeSettingsWorkspace';
import DuckdbRetainedSchemaWorkspace from './DuckdbRetainedSchemaWorkspace';
import DuckdbShellWorkspace from './DuckdbShellWorkspace';
import DuckdbSqlDumpWorkspace from './DuckdbSqlDumpWorkspace';
import DuckdbContinuityStorageWorkspace from './DuckdbContinuityStorageWorkspace';

export const DUCKDB_ADMIN_TABS = Object.freeze([
  'duckdb-runtime-settings',
  'duckdb-retained-schema',
  'duckdb-shell',
  'duckdb-sql-dump',
  'duckdb-continuity-storage',
]);

export const DUCKDB_ADMIN_TOP_LEVEL_ACTIONS = Object.freeze([
  'duckdb_runtime_settings',
  'duckdb_editor_operation',
  'duckdb_retained_schema',
  'duckdb_retained_schema_receipts',
  'duckdb_attachments',
  'duckdb_database_copy',
  'duckdb_extensions',
]);

export const DUCKDB_ADMIN_REQUEST_ACTIONS = Object.freeze([
  'duckdb_ops_shell_provenance',
  'duckdb_ops_shell_execute',
  'duckdb_ops_dump_export',
  'duckdb_ops_dump_list',
  'duckdb_ops_dump_read',
  'duckdb_ops_dump_reload_review',
  'duckdb_ops_dump_reload_apply',
  'duckdb_ops_continuity_inspect',
  'duckdb_ops_continuity_snapshot',
  'duckdb_ops_continuity_wal_drill',
  'duckdb_ops_continuity_restore_new',
  'duckdb_ops_continuity_cutover_review',
  'duckdb_ops_continuity_cutover_apply',
  'duckdb_ops_storage_inspect',
  'duckdb_ops_storage_reopen_probe',
  'duckdb_ops_storage_migrate_review',
  'duckdb_ops_storage_migrate_apply',
]);

export function renderDuckdbAdminWorkspace({
  tab,
  endpointUrl,
  databaseTargetId = '',
  api = null,
}) {
  switch (tab) {
    case 'duckdb-runtime-settings':
      return <DuckdbRuntimeSettingsWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'duckdb-retained-schema':
      return <DuckdbRetainedSchemaWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'duckdb-shell':
      return <DuckdbShellWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'duckdb-sql-dump':
      return <DuckdbSqlDumpWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'duckdb-continuity-storage':
      return <DuckdbContinuityStorageWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    default:
      return null;
  }
}

export {
  DuckdbRuntimeSettingsWorkspace,
  DuckdbRetainedSchemaWorkspace,
  DuckdbShellWorkspace,
  DuckdbSqlDumpWorkspace,
  DuckdbContinuityStorageWorkspace,
};
