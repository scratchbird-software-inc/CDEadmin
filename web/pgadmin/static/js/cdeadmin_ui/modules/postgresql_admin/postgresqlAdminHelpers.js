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

export const POSTGRES_SURFACE_KEYS = new Set([
  'postgresql',
  'postgresql-sql',
  'postgresql-native',
]);

export function stripQueryParams(url) {
  return String(url || '').split('?')[0];
}

export function createPostgresqlServerCaller(api, endpointUrl) {
  const cleanUrl = stripQueryParams(endpointUrl);
  return async (payload) => {
    const response = await api.post(cleanUrl, payload);
    const env = response?.data;
    if (env && env.success === 0) {
      throw new Error(env.errormsg || gettext('PostgreSQL workspace request failed.'));
    }
    return env?.data ?? env;
  };
}

export function PostgresqlSectionCard({title, actions = null, children}) {
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

PostgresqlSectionCard.propTypes = {
  title: PropTypes.node,
  actions: PropTypes.node,
  children: PropTypes.node,
};
