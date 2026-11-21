/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import MySQLUtilityWorkspace from './MySQLUtilityWorkspace';

export const MYSQL_ADMIN_TABS = Object.freeze(['mysql-utilities']);

export function renderMySQLAdminWorkspace({tab, endpointUrl, databaseTargetId}) {
  if (tab === 'mysql-utilities') {
    return <MySQLUtilityWorkspace endpointUrl={endpointUrl} databaseTargetId={databaseTargetId} />;
  }
  return null;
}
