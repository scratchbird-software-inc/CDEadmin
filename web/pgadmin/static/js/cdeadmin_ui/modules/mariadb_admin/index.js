/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import MariaDBPhysicalWorkspace from './MariaDBPhysicalWorkspace';
import MariaDBArchiveRetentionWorkspace from './MariaDBArchiveRetentionWorkspace';
import MariaDBHostWorkspace from './MariaDBHostWorkspace';
import MariaDBUpgradeWorkspace from './MariaDBUpgradeWorkspace';
import MariaDBGaleraWorkspace from './MariaDBGaleraWorkspace';
import MariaDBUtilityWorkspace from './MariaDBUtilityWorkspace';

export const MARIADB_ADMIN_TABS = [
  'mariadb-physical',
  'mariadb-archive-retention',
  'mariadb-host',
  'mariadb-upgrade',
  'mariadb-galera',
  'mariadb-utilities',
];

export function renderMariaDBAdminWorkspace({
  tab,
  endpointUrl,
  databaseTargetId = null,
  api = null,
}) {
  switch (tab) {
    case 'mariadb-physical':
      return <MariaDBPhysicalWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'mariadb-archive-retention':
      return <MariaDBArchiveRetentionWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'mariadb-host':
      return <MariaDBHostWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'mariadb-upgrade':
      return <MariaDBUpgradeWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'mariadb-galera':
      return <MariaDBGaleraWorkspace endpointUrl={endpointUrl} api={api} />;
    case 'mariadb-utilities':
      return (
        <MariaDBUtilityWorkspace
          endpointUrl={endpointUrl}
          databaseTargetId={databaseTargetId}
          api={api}
        />
      );
    default:
      return null;
  }
}

export {
  MariaDBPhysicalWorkspace,
  MariaDBArchiveRetentionWorkspace,
  MariaDBHostWorkspace,
  MariaDBUpgradeWorkspace,
  MariaDBGaleraWorkspace,
  MariaDBUtilityWorkspace,
};
