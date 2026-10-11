/////////////////////////////////////////////////////////////
// ScratchRobin shared SQL workspace.
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence.
/////////////////////////////////////////////////////////////
import SQLConnections from '../../../../static/js/cdeadmin_ui/editors/SQLConnections';
import withStandardTabInfo from '../../../../static/js/helpers/withStandardTabInfo';
import { BROWSER_PANELS } from '../../../../browser/static/js/constants';

function SQL() {
  return <SQLConnections />;
}
export default withStandardTabInfo(SQL, BROWSER_PANELS.SQL);
