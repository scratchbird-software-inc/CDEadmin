/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {lazySurface} from '../../foundations/lazySurface';

const SqliteRbuWorkspace = lazySurface(
  () => import('./SqliteRbuWorkspace'),
  'SqliteRbuWorkspace',
);
const SqliteExpertWorkspace = lazySurface(
  () => import('./SqliteExpertWorkspace'),
  'SqliteExpertWorkspace',
);
const SqliteIntckWorkspace = lazySurface(
  () => import('./SqliteIntckWorkspace'),
  'SqliteIntckWorkspace',
);
const SqliteBlobStreamWorkspace = lazySurface(
  () => import('./SqliteBlobStreamWorkspace'),
  'SqliteBlobStreamWorkspace',
);
const SqliteShellWorkspace = lazySurface(
  () => import('./SqliteShellWorkspace'),
  'SqliteShellWorkspace',
);
const SqliteSqlDumpWorkspace = lazySurface(
  () => import('./SqliteSqlDumpWorkspace'),
  'SqliteSqlDumpWorkspace',
);
const SqliteSessionTuningWorkspace = lazySurface(
  () => import('./SqliteSessionTuningWorkspace'),
  'SqliteSessionTuningWorkspace',
);

export const SQLITE_ADMIN_TABS = Object.freeze([
  'sqlite-rbu',
  'sqlite-expert',
  'sqlite-intck',
  'sqlite-blob-stream',
  'sqlite-shell',
  'sqlite-sql-dump',
  'sqlite-session-tuning',
]);

export const SQLITE_ADMIN_REQUEST_ACTIONS = Object.freeze([
  'sqlite_ops_rbu_catalog',
  'sqlite_ops_rbu_open_update',
  'sqlite_ops_rbu_open_vacuum',
  'sqlite_ops_rbu_step',
  'sqlite_ops_rbu_pause',
  'sqlite_ops_rbu_resume',
  'sqlite_ops_rbu_abort',
  'sqlite_ops_rbu_status',
  'sqlite_ops_rbu_list',
  'sqlite_ops_expert_status',
  'sqlite_ops_expert_analyze',
  'sqlite_ops_intck_status',
  'sqlite_ops_intck_open',
  'sqlite_ops_intck_step',
  'sqlite_ops_intck_pause',
  'sqlite_ops_intck_resume',
  'sqlite_ops_intck_close',
  'sqlite_ops_blob_inspect',
  'sqlite_ops_blob_read_chunk',
  'sqlite_ops_blob_allocate_review',
  'sqlite_ops_blob_allocate_apply',
  'sqlite_ops_blob_write_review',
  'sqlite_ops_blob_write_apply',
  'sqlite_ops_shell_provenance',
  'sqlite_ops_shell_inspect',
  'sqlite_ops_dump_export',
  'sqlite_ops_dump_list',
  'sqlite_ops_dump_read',
  'sqlite_ops_dump_import_review',
  'sqlite_ops_dump_import_apply',
]);

export function renderSqliteAdminWorkspace({
  tab,
  endpointUrl,
  databaseTargetId = '',
  api = null,
}) {
  switch (tab) {
    case 'sqlite-rbu':
      return <SqliteRbuWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'sqlite-expert':
      return <SqliteExpertWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'sqlite-intck':
      return <SqliteIntckWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'sqlite-blob-stream':
      return <SqliteBlobStreamWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'sqlite-shell':
      return <SqliteShellWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'sqlite-sql-dump':
      return <SqliteSqlDumpWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    case 'sqlite-session-tuning':
      return <SqliteSessionTuningWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} api={api} />;
    default:
      return null;
  }
}

export {
  SqliteRbuWorkspace,
  SqliteExpertWorkspace,
  SqliteIntckWorkspace,
  SqliteBlobStreamWorkspace,
  SqliteShellWorkspace,
  SqliteSqlDumpWorkspace,
  SqliteSessionTuningWorkspace,
};
