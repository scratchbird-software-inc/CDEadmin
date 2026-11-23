/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {lazySurface} from '../../foundations/lazySurface';

const FirebirdTraceWorkspace = lazySurface(
  () => import('./FirebirdTraceWorkspace'),
  'FirebirdTraceWorkspace',
);
const FirebirdLockPrintWorkspace = lazySurface(
  () => import('./FirebirdLockPrintWorkspace'),
  'FirebirdLockPrintWorkspace',
);
const FirebirdHostConfigWorkspace = lazySurface(
  () => import('./FirebirdHostConfigWorkspace'),
  'FirebirdHostConfigWorkspace',
);
const FirebirdPluginDeploymentWorkspace = lazySurface(
  () => import('./FirebirdPluginDeploymentWorkspace'),
  'FirebirdPluginDeploymentWorkspace',
);
const FirebirdRuntimeLifecycleWorkspace = lazySurface(
  () => import('./FirebirdRuntimeLifecycleWorkspace'),
  'FirebirdRuntimeLifecycleWorkspace',
);
const FirebirdDatabaseEncryptionWorkspace = lazySurface(
  () => import('./FirebirdDatabaseEncryptionWorkspace'),
  'FirebirdDatabaseEncryptionWorkspace',
);
const FirebirdReplicationWorkspace = lazySurface(
  () => import('./FirebirdReplicationWorkspace'),
  'FirebirdReplicationWorkspace',
);

export const FIREBIRD_ADMIN_TABS = Object.freeze([
  'firebird-trace',
  'firebird-lock-print',
  'firebird-host-configuration',
  'firebird-plugin-deployment',
  'firebird-runtime-lifecycle',
  'firebird-database-encryption',
  'firebird-replication',
]);

export function renderFirebirdAdminWorkspace({
  tab,
  endpointUrl,
  databaseTargetId = null,
  initialContext = {},
}) {
  switch (tab) {
  case 'firebird-trace':
    return (
      <FirebirdTraceWorkspace
        endpointUrl={endpointUrl}
        databaseTargetId={databaseTargetId}
        initialTraceScope={initialContext.trace_scope || 'database'}
      />
    );
  case 'firebird-lock-print':
    return (
      <FirebirdLockPrintWorkspace
        endpointUrl={endpointUrl}
        databaseTargetId={databaseTargetId}
      />
    );
  case 'firebird-host-configuration':
    return (
      <FirebirdHostConfigWorkspace
        endpointUrl={endpointUrl}
        databaseTargetId={databaseTargetId}
      />
    );
  case 'firebird-plugin-deployment':
    return (
      <FirebirdPluginDeploymentWorkspace
        endpointUrl={endpointUrl}
        databaseTargetId={databaseTargetId}
      />
    );
  case 'firebird-runtime-lifecycle':
    return (
      <FirebirdRuntimeLifecycleWorkspace
        endpointUrl={endpointUrl}
        databaseTargetId={databaseTargetId}
        defaultOperation={initialContext.default_operation || 'migrate_database'}
      />
    );
  case 'firebird-database-encryption':
    return (
      <FirebirdDatabaseEncryptionWorkspace
        endpointUrl={endpointUrl}
        databaseTargetId={databaseTargetId}
      />
    );
  case 'firebird-replication':
    return (
      <FirebirdReplicationWorkspace
        endpointUrl={endpointUrl}
        databaseTargetId={databaseTargetId}
      />
    );
  default:
    return null;
  }
}

export {
  FirebirdTraceWorkspace,
  FirebirdLockPrintWorkspace,
  FirebirdHostConfigWorkspace,
  FirebirdPluginDeploymentWorkspace,
  FirebirdRuntimeLifecycleWorkspace,
  FirebirdDatabaseEncryptionWorkspace,
  FirebirdReplicationWorkspace,
};
