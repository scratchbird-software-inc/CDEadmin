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
import {Box} from '../../primitives/Layout';
import {Badge, Banner} from '../../feedback/Indicators';
import {EmptyState} from '../../feedback/EmptyState';
import {historyRows} from './alerts';

const when = (value) => {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString();
};

/**
 * What each check did. Failures show a fixed explanation, never SQL or a
 * database message; people who can edit also see a short technical detail.
 */
export default function AlertHistory({history}) {
  if(history.status === 'loading') return <Box role="status" sx={{fontSize: '0.75rem'}}>{gettext('Loading history...')}</Box>;
  if(history.status === 'error') return <Banner status="error">{history.error}</Banner>;
  const rows = historyRows(history.items);
  if(!rows.length) return <EmptyState message={gettext('Nothing has run yet.')} />;
  return <Box sx={{overflow: 'auto'}}>
    <Box component="table" aria-label={gettext('History')}
      sx={{borderCollapse: 'collapse', fontSize: '0.75rem', width: '100%'}}>
      <thead><tr>
        {[gettext('When'), gettext('Trigger'), gettext('Result'), gettext('Value'), gettext('Delivery')].map((title) =>
          <Box component="th" key={title} sx={{textAlign: 'left', p: 0.5, borderBottom: '1px solid', borderColor: 'divider'}}>
            {title}</Box>)}
      </tr></thead>
      <tbody>{rows.map((row) => <tr key={row.key}>
        <Box component="td" sx={{p: 0.5}}>{when(row.at)}</Box>
        <Box component="td" sx={{p: 0.5}}>{row.trigger}</Box>
        <Box component="td" sx={{p: 0.5}}>
          <Badge status={row.tone} label={row.label} />
          {row.fired && ' '}{row.fired && <Badge status="warning" label={gettext('Notified')} />}
          {row.suppressed && <Box component="span"> {gettext('Suppressed: %s', row.suppressed)}</Box>}
          {row.problem && <Box>{row.problem}</Box>}
          {row.detail && <Box sx={{color: 'text.secondary'}}>{row.detail}</Box>}
        </Box>
        <Box component="td" sx={{p: 0.5}}>{row.value}</Box>
        <Box component="td" sx={{p: 0.5}}>
          {row.deliveries.map((item) => <Box key={item.key}>{item.channel}: {item.state}{item.code ? ` (${item.code})` : ''}</Box>)}
        </Box>
      </tr>)}</tbody>
    </Box>
  </Box>;
}

AlertHistory.propTypes = {
  history: PropTypes.shape({status: PropTypes.string.isRequired, items: PropTypes.array.isRequired,
    error: PropTypes.string}).isRequired,
};
