import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button} from '@mui/material';
import getApiInstance from '../api_instance';
import url_for from 'sources/url_for';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';

const quote = (value) => JSON.stringify(String(value ?? 'NULL'));
export function monitoringDetailFiles(result) {
  const fields = result.operation === 'accounts' ?
    ['user_name', 'plugin', 'active', 'admin', 'first_name', 'middle_name', 'last_name'] :
    result.operation === 'receipts' ? ['operation_id', 'operation_kind', 'database', 'stage',
      'unknown_outcome', 'post_state_required', 'server_completed', 'service_handle_released', 'updated_at'] : ['name', 'value'];
  const rows = (result.rows || []).slice(0, 100);
  return {'details.ddn': `ddn "0.5"; module "scratchrobin.firebird.monitoring.details";
    data observations {${rows.length ? rows.map((row, index) => `record r${index} ${quote(row[fields[0]])} {
      x_record: {${fields.map((field) => `${field}:${quote(row[field])}`).join(',')}}; }`).join('\n') :
    'record empty "No visible rows" {}'}}
    view details "Authorized native details" {data: [@observations];
      projection {kind: table; profile: "table.records@1";
        records: [${rows.length ? rows.map((_, index) => `@observations.r${index}`).join(',') : '@observations.empty'}];
        columns: [${rows.length ? fields.map((field) => `{key:${quote('x_record.' + field)},label:${quote(field)}}`).join(',') : '{key:"name",label:"Observation"}'}];
      } publication {size: content; fit: none;}
    }`};
}

export default function FirebirdMonitoringDetails({serverId, targetId, sample}) {
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const alive = useRef(true);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  const inspect = async (operation) => {
    setBusy(true); setError(''); setResult(null);
    try {
      const endpoint = url_for('cdeadmin_monitoring.details', {sid: serverId}) +
        (targetId ? '?target_id=' + encodeURIComponent(targetId) : '');
      const response = await getApiInstance().post(endpoint, {operation, sample_id: sample?.sample_id || ''});
      if(alive.current) setResult(response.data.data);
    } catch(exception) {
      if(alive.current) setError(exception.response?.data?.errormsg || 'Native detail inspection failed.');
    } finally {if(alive.current) setBusy(false);}
  };
  const available = ['available', 'partial'].includes(sample?.status) && sample?.sample_id;
  return <Box sx={{flexShrink: 0}}>
    <FormReference formKey="firebird-monitoring-details" />
    <Button disabled={busy} onClick={() => inspect('receipts')}>Inspect local operation receipts</Button>
    {targetId ? <Button disabled={busy || !available} onClick={() => inspect('accounts')}>Inspect visible security accounts</Button> : <>
      <Button disabled={busy || !available} onClick={() => inspect('server-paths')}>Inspect server paths</Button>
      <Button disabled={busy || !available} onClick={() => inspect('server-log')}>Read bounded server log prefix</Button>
    </>}
    {error && <Alert severity="error">{error}</Alert>}
    {result && <Alert severity={result.status === 'available' ? 'info' : 'warning'}>
      Inspection: {result.status}. Observed: {result.observed_at || 'Unavailable'}.
      {result.truncated && ' Result truncated.'} Native account visibility is limited by the monitoring account.
      {result.status === 'changed' && ' The collector changed; wait for the next dashboard refresh and request the detail again.'}
    </Alert>}
    {result?.status === 'available' && (result.operation === 'server-log' ?
      <Box component="pre" aria-label="Native server log prefix" sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 400, overflow: 'auto'}}>
        {result.text || 'No text returned.'}
      </Box> : <DDNViewerSurface files={monitoringDetailFiles(result)} entry="details.ddn" view="details" presentation />)}
  </Box>;
}
FirebirdMonitoringDetails.propTypes = {serverId: PropTypes.number.isRequired,
  targetId: PropTypes.string, sample: PropTypes.object};
