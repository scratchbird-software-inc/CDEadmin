import {observationTable} from '../cdeadmin_ui/integrations/ddn/source';
import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField} from '@mui/material';
import getApiInstance from '../api_instance';
import url_for from 'sources/url_for';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';

export function statementFiles(result) {
  const rows=['sql_text','explained_plan'].map(field=>({source:field.replaceAll('_',' '),
    text:result[field]?.value ?? 'Unavailable',truncated:result[field]?.truncated?'Yes':'No'}));
  if(result.call_stack) rows.push({source:'Native PSQL call stack',text:result.call_stack.status==='available'?
    (result.call_stack.rows?.length?result.call_stack.rows.map(row=>
      `${row.call_id} caller=${row.caller_id ?? 'none'} ${row.package_name?row.package_name+'.':''}${row.object_name ?? 'dynamic SQL'} line=${row.source_line ?? 'unknown'} column=${row.source_column ?? 'unknown'}`).join('\n'):'No visible calls in this snapshot'):'Unavailable',
  truncated:result.call_stack.truncated?'Yes':'No'});
  return observationTable('statement.ddn','statement','Native statement inspection',rows,['source','text','truncated'],'scratchrobin.firebird.statement');
}

export default function FirebirdStatementDetails({serverId, targetId, sample, compiled=false}) {
  const [selected, setSelected] = useState('');
  const [result, setResult] = useState(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const alive = useRef(true);
  useEffect(() => {alive.current = true; return () => {alive.current = false;};}, []);
  const group = sample?.groups?.[compiled ? 'compiled_details' : 'statement_details'];
  const rows = group?.status === 'available' ? (group.values?.rows || []) : [];
  const idField = compiled ? 'compiled_statement_id' : 'statement_id';
  const row = rows.find((item) => item[idField] === selected);
  const inspect = async () => {
    if(!row || busy) return;
    setBusy(true); setError(''); setResult(null);
    const fields = compiled ? ['compiled_statement_id', 'object_name', 'object_type', 'package_name', 'stat_id'] :
      ['statement_id', 'attachment_id', 'compiled_statement_id', 'timestamp'];
    const reference = Object.fromEntries(fields.map((field) => [field, row[field]]));
    try {
      const response = await getApiInstance().post(url_for('cdeadmin_monitoring.statement', {sid: serverId}) +
        '?target_id=' + encodeURIComponent(targetId), {...reference, sample_id: sample.sample_id,
        ...(compiled ? {kind: 'compiled'} : {})});
      if(alive.current) setResult(response.data.data);
    } catch(err) {
      if(alive.current) setError(err.response?.data?.errormsg || 'Statement inspection is unavailable.');
    } finally {
      if(alive.current) setBusy(false);
    }
  };
  return <Box sx={{my: 1}}>
    <FormReference formKey="firebird-statement-details" />
    <Box>SQL text and plans are fetched only on request and may contain values. Each text is limited to 4096 characters.</Box>
    <TextField select size="small" label={compiled ? 'Compiled statement to inspect' : 'Statement to inspect'} value={row ? selected : ''}
      onChange={(event) => setSelected(event.target.value)} disabled={busy} sx={{minWidth: 250, my: 1}}>
      <MenuItem value="">Select a sampled statement</MenuItem>
      {rows.map((item) => <MenuItem key={item[idField]} value={item[idField]}>
        {compiled ? `${item[idField]} (${item.object_name || 'dynamic SQL'})` : `${item.statement_id} (attachment ${item.attachment_id})`}
      </MenuItem>)}
    </TextField>
    <Button disabled={!row || busy} onClick={inspect}>Inspect SQL and plan</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {result && <Alert severity={result.status === 'available' ? 'info' : 'warning'}>
      Inspection: {result.status}. Observed: {result.observed_at || 'Unavailable'}.
      {result.identity && (compiled ? ` Compiled statement ${result.identity.compiled_statement_id}.` :
        ` Statement ${result.identity.statement_id}, attachment ${result.identity.attachment_id}.`)}
      {result.status !== 'available' && ' Refresh the activity snapshot and select the statement again.'}
    </Alert>}
    {result?.status === 'available' && <DDNViewerSurface files={statementFiles(result)}
      entry="statement.ddn" view="statement" presentation />}
  </Box>;
}
FirebirdStatementDetails.propTypes = {serverId: PropTypes.number.isRequired,
  targetId: PropTypes.string.isRequired, sample: PropTypes.object, compiled: PropTypes.bool};
