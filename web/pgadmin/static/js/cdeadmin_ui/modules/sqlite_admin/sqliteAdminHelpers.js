/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import PropTypes from 'prop-types';
import gettext from 'sources/gettext';
import {Panel, Stack} from '../../primitives/Layout';

export function createSqliteWorkspaceCaller(api, endpointUrl, databaseTargetId) {
  return async ({action, request = {}}) => {
    const mergedRequest = databaseTargetId
      ? {database_target_id: databaseTargetId, ...request}
      : request;
    const response = await api.post(endpointUrl, {
      action,
      request: mergedRequest,
    });
    const env = response?.data;
    if (env && env.success === 0) {
      throw new Error(env.errormsg || gettext('SQLite workspace request failed.'));
    }
    return env?.data ?? env;
  };
}

export function SqliteSectionCard({title, actions = null, children}) {
  return (
    <Panel style={{padding: 12}}>
      <Stack gap="standard">
        {(title || actions) && (
          <Stack
            direction="row"
            gap="compact"
            style={{justifyContent: 'space-between', alignItems: 'center'}}
          >
            {title ? <strong>{title}</strong> : <span />}
            {actions}
          </Stack>
        )}
        {children}
      </Stack>
    </Panel>
  );
}

SqliteSectionCard.propTypes = {
  title: PropTypes.node,
  actions: PropTypes.node,
  children: PropTypes.node,
};
