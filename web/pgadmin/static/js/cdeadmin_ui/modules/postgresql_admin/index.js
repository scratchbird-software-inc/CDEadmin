/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {lazySurface} from '../../foundations/lazySurface';

const PostgresqlHostToolsWorkspace = lazySurface(
  () => import('./PostgresqlHostToolsWorkspace'),
  'PostgresqlHostToolsWorkspace',
);
const PostgresqlConfigurationWorkspace = lazySurface(
  () => import('./PostgresqlConfigurationWorkspace'),
  'PostgresqlConfigurationWorkspace',
);
const PostgresqlHaTopologyWorkspace = lazySurface(
  () => import('./PostgresqlHaTopologyWorkspace'),
  'PostgresqlHaTopologyWorkspace',
);
const PostgresqlPreparedXactsWorkspace = lazySurface(
  () => import('./PostgresqlPreparedXactsWorkspace'),
  'PostgresqlPreparedXactsWorkspace',
);
const PostgresqlSnapshotCopyWorkspace = lazySurface(
  () => import('./PostgresqlSnapshotCopyWorkspace'),
  'PostgresqlSnapshotCopyWorkspace',
);
const PostgresqlActivityLocksWorkspace = lazySurface(
  () => import('./PostgresqlActivityLocksWorkspace'),
  'PostgresqlActivityLocksWorkspace',
);
const PostgresqlListenNotifyWorkspace = lazySurface(
  () => import('./PostgresqlListenNotifyWorkspace'),
  'PostgresqlListenNotifyWorkspace',
);
const PostgresqlLogicalToolsWorkspace = lazySurface(
  () => import('./PostgresqlLogicalToolsWorkspace'),
  'PostgresqlLogicalToolsWorkspace',
);

export const POSTGRESQL_ADMIN_TABS = Object.freeze([
  'postgresql-host-tools',
  'postgresql-configuration',
  'postgresql-ha-topology',
  'postgresql-prepared-xacts',
  'postgresql-snapshot-copy',
  'postgresql-activity-locks',
  'postgresql-listen-notify',
  'postgresql-logical-tools',
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
    case 'postgresql-activity-locks':
      return <PostgresqlActivityLocksWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'postgresql-listen-notify':
      return <PostgresqlListenNotifyWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'postgresql-logical-tools':
      return <PostgresqlLogicalToolsWorkspace endpointUrl={endpointUrl} api={api} />;
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
  PostgresqlActivityLocksWorkspace,
  PostgresqlListenNotifyWorkspace,
  PostgresqlLogicalToolsWorkspace,
};
