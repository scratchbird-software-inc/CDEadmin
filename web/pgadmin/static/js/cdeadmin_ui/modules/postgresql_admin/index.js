/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PostgresqlHostToolsWorkspace from './PostgresqlHostToolsWorkspace';
import PostgresqlConfigurationWorkspace from './PostgresqlConfigurationWorkspace';
import PostgresqlHaTopologyWorkspace from './PostgresqlHaTopologyWorkspace';
import PostgresqlPreparedXactsWorkspace from './PostgresqlPreparedXactsWorkspace';
import PostgresqlSnapshotCopyWorkspace from './PostgresqlSnapshotCopyWorkspace';

export const POSTGRESQL_ADMIN_TABS = Object.freeze([
  'postgresql-host-tools',
  'postgresql-configuration',
  'postgresql-ha-topology',
  'postgresql-prepared-xacts',
  'postgresql-snapshot-copy',
]);

export function renderPostgresqlAdminWorkspace({
  tab,
  endpointUrl,
  api = null,
}) {
  switch (tab) {
    case 'postgresql-host-tools':
      return <PostgresqlHostToolsWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'postgresql-configuration':
      return <PostgresqlConfigurationWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'postgresql-ha-topology':
      return <PostgresqlHaTopologyWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'postgresql-prepared-xacts':
      return <PostgresqlPreparedXactsWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'postgresql-snapshot-copy':
      return <PostgresqlSnapshotCopyWorkspace endpointUrl={endpointUrl} api={api} />;
    default:
      return null;
  }
}

export {
  PostgresqlHostToolsWorkspace,
  PostgresqlConfigurationWorkspace,
  PostgresqlHaTopologyWorkspace,
  PostgresqlPreparedXactsWorkspace,
  PostgresqlSnapshotCopyWorkspace,
};
