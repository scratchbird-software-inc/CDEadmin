/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Derived from pgAdmin 4. Copyright (C) 2013 - 2026,
// The pgAdmin Development Team. PostgreSQL Licence.
//
//////////////////////////////////////////////////////////////

import {Icon} from 'sources/cdeadmin_ui/icons';
import gettext from 'sources/gettext';

export default function CDEadminLogo() {
  return (
    <div className="welcome-logo" aria-label="ScratchRobin CDE Administrator">
      <Icon iconKey="brand.scratchrobin" label="ScratchRobin" size="3rem" />
      <div className="welcome-wordmark">
        <h1>ScratchRobin CDE Administrator</h1>
        <p className="WelcomeDashboard-description">
          {gettext('A data management and business intelligence tool. A part of the ScratchBird CDE family of products.')}
        </p>
      </div>
    </div>
  );
}
