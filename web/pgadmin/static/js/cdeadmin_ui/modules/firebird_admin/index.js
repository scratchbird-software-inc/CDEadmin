/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import FirebirdTraceWorkspace from './FirebirdTraceWorkspace';
import FirebirdLockPrintWorkspace from './FirebirdLockPrintWorkspace';
import FirebirdHostConfigWorkspace from './FirebirdHostConfigWorkspace';
import FirebirdPluginDeploymentWorkspace from './FirebirdPluginDeploymentWorkspace';
import FirebirdRuntimeLifecycleWorkspace from './FirebirdRuntimeLifecycleWorkspace';
import FirebirdDatabaseEncryptionWorkspace from './FirebirdDatabaseEncryptionWorkspace';
import FirebirdReplicationWorkspace from './FirebirdReplicationWorkspace';

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
