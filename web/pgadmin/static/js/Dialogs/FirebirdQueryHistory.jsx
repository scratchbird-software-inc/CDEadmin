import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField, Table, TableHead, TableBody, TableRow, TableCell} from '@mui/material';
import gettext from 'sources/gettext';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdQueryHistory({post, databaseTargetId, dialect, onLoad, disabled, notice}) {
  const [open, setOpen] = useState(false);
  const [data, setData] = useState(null);
  const [policy, setPolicy] = useState(null);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(-1);
  const [clearConfirmed, setClearConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const token = useRef(0);
  useEffect(() => {
    token.current++; setData(null); setPolicy(null); setSearch(''); setSelected(-1);
    setClearConfirmed(false); setError(''); setBusy(false); setOpen(false);
    return () => {token.current++;};
  }, [post, databaseTargetId, dialect]);
  const call = async (action = 'query_history_read') => {
    const id = ++token.current;
    setBusy(true); setError('');
    const scope = {database_target_id: databaseTargetId, client_sql_dialect: dialect};
    try {
      if(action !== 'query_history_read') await post({action, request: {...scope,
        ...(action === 'query_history_configure' ? {policy} : {confirmed: clearConfirmed})}});
      const response = await post({action: 'query_history_read', request: {...scope, search}});
      if(token.current !== id) return;
      setData(response); setPolicy(response.policy); setSelected(-1); setClearConfirmed(false);
    } catch(err) {if(token.current === id) setError(err.response?.data?.errormsg || err.message);}
    finally {if(token.current === id) setBusy(false);}
  };
  const load = (index) => {
    const entry = data.entries[index];
    if(typeof entry?.source === 'string') {setSelected(index); onLoad(entry.source);}
  };
  const previous = data?.entries.findIndex((item, index) => index > selected && typeof item.source === 'string') ?? -1;
  let next = -1;
  for(let index = selected - 1; index >= 0; index--) {
    if(typeof data?.entries[index]?.source === 'string') {next = index; break;}
  }
  return <Box sx={{mt: 1}}>
    {notice && <Alert severity="warning">{notice}</Alert>}
    <Button disabled={disabled || busy} onClick={() => {setOpen(!open); if(!open) call();}}>{gettext('SQL history')}</Button>
    {open && <Box sx={{border: 1, borderColor: 'divider', p: 1}}>
      <FormReference formKey="firebird-query-history" />
      <Alert severity="info">{gettext('History records requests, not transaction outcomes. Source capture is optional and can retain sensitive SQL literals. Bound parameters and result rows are never saved. Credential-bearing text is omitted. Loading history only replaces editor text.')}</Alert>
      {error && <Alert severity="error">{error}</Alert>}
      {policy && <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center', my: 1}}>
        <FormControlLabel label={gettext('Remember SQL source')} control={<Checkbox checked={policy.capture_source}
          disabled={disabled || busy} onChange={(event) => setPolicy({...policy, capture_source: event.target.checked})} />} />
        <TextField size="small" type="number" label={gettext('Retention days')} value={policy.retention_days}
          disabled={disabled || busy} onChange={(event) => setPolicy({...policy, retention_days: Number(event.target.value)})} />
        <TextField size="small" type="number" label={gettext('Maximum history records')} value={policy.max_records}
          disabled={disabled || busy} onChange={(event) => setPolicy({...policy, max_records: Number(event.target.value)})} />
        <Button disabled={disabled || busy} onClick={() => call('query_history_configure')}>{gettext('Save history policy')}</Button>
      </Box>}
      <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
        <TextField size="small" label={gettext('Search SQL history')} value={search} disabled={busy}
          onChange={(event) => setSearch(event.target.value)} />
        <Button disabled={disabled || busy} onClick={() => call()}>{gettext('Search / refresh history')}</Button>
        <Button disabled={disabled || busy || previous < 0} onClick={() => load(previous)}>{gettext('Previous history entry')}</Button>
        <Button disabled={disabled || busy || next < 0} onClick={() => load(next)}>{gettext('Next history entry')}</Button>
      </Box>
      {data && <Box sx={{maxHeight: 320, overflow: 'auto'}}><Table size="small" aria-label={gettext('Retained SQL history')}>
        <TableHead><TableRow>{['Time', 'Request state', 'SQL source', 'Action'].map((label) => <TableCell key={label}>{gettext(label)}</TableCell>)}</TableRow></TableHead>
        <TableBody>{data.entries.map((entry, index) => <TableRow key={entry.entry_id} selected={selected === index}>
          <TableCell>{new Date(entry.created_at * 1000).toLocaleString()}</TableCell>
          <TableCell>{entry.kind}: {entry.request_state}</TableCell>
          <TableCell sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{entry.source ?? entry.source_omitted_reason}</TableCell>
          <TableCell><Button disabled={disabled || busy || typeof entry.source !== 'string'} onClick={() => load(index)}>{gettext('Load into editor')}</Button></TableCell>
        </TableRow>)}</TableBody>
      </Table></Box>}
      <FormControlLabel label={gettext('Confirm clearing this database and dialect history')}
        control={<Checkbox checked={clearConfirmed} disabled={disabled || busy} onChange={(event) => setClearConfirmed(event.target.checked)} />} />
      <Button disabled={disabled || busy || !clearConfirmed} onClick={() => call('query_history_clear')}>{gettext('Clear SQL history')}</Button>
    </Box>}
  </Box>;
}
FirebirdQueryHistory.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string,
  dialect: PropTypes.number.isRequired, onLoad: PropTypes.func.isRequired, disabled: PropTypes.bool, notice: PropTypes.string};
