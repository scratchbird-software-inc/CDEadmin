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

const DELIVERY_TONE = {would_send: 'info', delivered: 'success', skipped: 'warning', failed: 'error'};

function Preview({preview}) {
  if(!preview || !preview.columns.length) return null;
  return <Box sx={{overflow: 'auto', maxHeight: 200}}>
    <Box component="table" aria-label={gettext('Message preview')}
      sx={{borderCollapse: 'collapse', fontSize: '0.75rem', width: '100%'}}>
      <thead><tr>{preview.columns.map((name) => <Box component="th" key={name}
        sx={{textAlign: 'left', p: 0.5, borderBottom: '1px solid', borderColor: 'divider'}}>{name}</Box>)}</tr></thead>
      <tbody>{preview.rows.map((row, index) => <tr key={index}>
        {preview.columns.map((name) => <Box component="td" key={name} sx={{p: 0.5}}>
          {row[name] === null || row[name] === undefined ? '' : String(row[name])}</Box>)}
      </tr>)}</tbody>
    </Box>
    {preview.truncated && <Box sx={{fontSize: '0.7rem', color: 'text.secondary'}}>
      {gettext('Showing %s of %s rows. A message never carries more than the configured limit.',
        preview.shown, preview.row_count)}</Box>}
  </Box>;
}

Preview.propTypes = {preview: PropTypes.object};

/**
 * The dry-run result: what the condition evaluated to, whether it would fire,
 * and the message and deliveries that would result. Nothing here was sent.
 */
export default function AlertTestResult({view}) {
  if(!view) return null;
  return <Box role="region" aria-label={gettext('Test result')}
    sx={{display: 'grid', gap: 0.75, border: '1px solid', borderColor: 'divider', p: 1}}>
    <Banner status="info">{gettext('This was a dry run. Nothing was sent and no state changed.')}</Banner>
    {view.kind === 'alert' ? <>
      <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap'}}>
        <Badge status={view.breached ? 'error' : view.breached === false ? 'success' : 'neutral'}
          label={view.breached ? gettext('Condition met') : view.breached === false ? gettext('Condition not met') :
            gettext('No value')} />
        <Badge status={view.wouldFire ? 'warning' : 'neutral'}
          label={view.wouldFire ? gettext('Would notify') : gettext('Would stay quiet')} />
        {view.suppressed && <Badge status="neutral" label={gettext('Suppressed: %s', view.suppressed)} />}
      </Box>
      <Box sx={{fontSize: '0.8125rem'}}>
        {view.condition}. {view.value === null || view.value === undefined ?
          (view.detail || gettext('There is no value to compare.')) :
          gettext('Value: %s over %s rows.', view.value, view.rowCount)}
        {view.previous !== null && view.previous !== undefined && ' ' + gettext('Previous: %s.', view.previous)}
      </Box>
      {view.truncated && <Banner status="warning">{gettext('The result was truncated.')}</Banner>}
    </> : <>
      {view.items.length > 0 && <Box component="ul" aria-label={gettext('Snapshot contents')} sx={{m: 0, pl: 2.5}}>
        {view.items.map((item) => <li key={item.key}>
          {item.title}: {item.status === 'ok' ? gettext('%s rows', item.rowCount) : gettext('not included')}
        </li>)}
      </Box>}
      {view.attachments.length > 0 && <Box sx={{fontSize: '0.75rem'}}>
        {gettext('Attachments: %s', view.attachments.map((item) => item.filename).join(', '))}</Box>}
    </>}
    {view.message?.title && <Box sx={{fontSize: '0.8125rem'}}><strong>{view.message.title}</strong></Box>}
    {view.message?.text && <Box component="pre" sx={{m: 0, fontSize: '0.75rem', whiteSpace: 'pre-wrap'}}>
      {view.message.text}</Box>}
    <Preview preview={view.preview} />
    {view.deliveries.length > 0 && <Box component="ul" aria-label={gettext('Deliveries')}
      sx={{m: 0, p: 0, listStyle: 'none', display: 'grid', gap: 0.25}}>
      {view.deliveries.map((item) => <li key={item.key}>
        <Badge status={DELIVERY_TONE[item.state] || 'neutral'}
          label={`${item.channel} ${item.target}: ${item.state}${item.code ? ` (${item.code})` : ''}`} />
      </li>)}
    </Box>}
  </Box>;
}

AlertTestResult.propTypes = {view: PropTypes.object};
