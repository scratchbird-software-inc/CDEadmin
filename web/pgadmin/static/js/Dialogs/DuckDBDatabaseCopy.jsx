import {useCallback, useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField, Typography} from '@mui/material';

const running = record => !!record?.review_id && record.phase !== 'finished';

export default function DuckDBDatabaseCopy({post, databaseTargetId, sessionId, ensureSession,
  disabled=false, onBusyChange, onBlocked}) {
  const [source, setSource] = useState(''), [destination, setDestination] = useState('');
  const [mode, setMode] = useState('ALL'), [record, setRecord] = useState(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState(''), [confirmed, setConfirmed] = useState(false);
  const [awaitingReceipt, setAwaitingReceipt] = useState(false), [catalogs, setCatalogs] = useState([]);
  const serial = useRef(0), previousSession = useRef(sessionId);
  const ownsBusy = useRef(false);
  useEffect(() => {
    serial.current++; setRecord(null); setSource(''); setDestination(''); setCatalogs([]);
    setConfirmation(''); setConfirmed(false); setError(''); setBusy(false); setAwaitingReceipt(false);
    return () => {serial.current++; if(ownsBusy.current) onBusyChange(false); ownsBusy.current = false;};
  }, [post, databaseTargetId, onBusyChange]);
  useEffect(() => {
    if(previousSession.current && previousSession.current !== sessionId) {
      if(ownsBusy.current) onBusyChange(false);
      ownsBusy.current = false;
      serial.current++; setRecord(null); setCatalogs([]); setBusy(false); setAwaitingReceipt(false);
      setConfirmation(''); setConfirmed(false);
      setError('The original copy session closed or changed. Its receipts cannot be applied on another session.');
    }
    previousSession.current = sessionId;
  }, [sessionId, onBusyChange]);
  const receive = useCallback(value => {
    ownsBusy.current = running(value);
    setRecord(value); setAwaitingReceipt(false);
    onBusyChange(running(value));
    if(value.session_reuse_blocked) onBlocked?.();
  }, [onBusyChange, onBlocked]);
  const send = async operation => {
    ownsBusy.current = true;
    const token = ++serial.current; setBusy(true); setError(''); onBusyChange(true);
    let keepBusy = false;
    try {
      const active = sessionId || await ensureSession();
      if(token !== serial.current) return;
      const request = operation === 'review' ? {operation, draft: {
        source_catalog: source, destination_catalog: destination, mode}} : operation === 'inventory' ? {operation} :
        {operation, review_id: record.review_id,
          ...(operation === 'apply' ? {review_digest: record.review_digest, confirmation, confirmed} :
            operation === 'discard' ? {review_digest: record.review_digest} : {})};
      if(operation === 'apply') {setAwaitingReceipt(true); keepBusy = true;}
      const value = await post({action: 'duckdb_database_copy', database_target_id: databaseTargetId,
        session_id: active, request});
      if(token === serial.current) {
        if(operation === 'inventory') setCatalogs(value.catalogs);
        else receive(value);
        keepBusy = operation !== 'inventory' && running(value);
        setConfirmation(''); setConfirmed(false);
      }
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message ||
        'Copy reply unavailable. Read the existing receipt before preparing another copy.');
    } finally {if(token === serial.current) {setBusy(false); ownsBusy.current = keepBusy; onBusyChange(keepBusy);}}
  };
  useEffect(() => {
    if(!running(record) || !sessionId || busy) return undefined;
    const token = serial.current;
    const timer = setTimeout(async () => {
      try {
        const value = await post({action: 'duckdb_database_copy', database_target_id: databaseTargetId,
          session_id: sessionId, request: {operation: 'receipt', review_id: record.review_id}});
        if(token === serial.current) receive(value);
      } catch(failure) {if(token === serial.current) setError(failure.message || 'Read the copy receipt to recover progress.');}
    }, 500);
    return () => clearTimeout(timer);
  }, [record, post, sessionId, databaseTargetId, busy, receive]);
  const locked = disabled || busy || running(record) || awaitingReceipt || record?.session_reuse_blocked;
  const changed = setter => event => {
    setter(event.target.value); setRecord(null); setConfirmation(''); setConfirmed(false);
  };
  return <Box sx={{p: 1, borderTop: '1px solid', borderColor: 'divider'}}>
    <Typography variant="h6">Copy between attached DuckDB catalogs</Typography>
    <Alert severity="info">Copies run on the current native session. Schema and data uses two native steps.
      Data mode appends rows. Commit and rollback remain explicit; a failed copy can require rollback.</Alert>
    <Alert severity="info">To encrypt, decrypt or change the key of a database copy, first attach a separate destination with its intended encryption settings.
      Copy schema and data, commit, detach, then reopen the destination with its intended key to verify it before retiring the source.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {awaitingReceipt && <Alert severity="warning">The apply reply is unavailable. Read this copy receipt before continuing.</Alert>}
    <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, my: 1}}>
      <Button disabled={locked} onClick={() => send('inventory')}>Inspect copy catalogs</Button>
      <TextField size="small" label="Copy source catalog" value={source} disabled={locked} onChange={changed(setSource)} />
      <TextField size="small" label="Copy destination catalog" value={destination} disabled={locked} onChange={changed(setDestination)} />
      <TextField select size="small" label="Native database copy mode" value={mode} disabled={locked} onChange={changed(setMode)}>
        <MenuItem value="ALL">Schema and data</MenuItem><MenuItem value="SCHEMA">Schema only</MenuItem><MenuItem value="DATA">Data only (append)</MenuItem>
      </TextField>
      <Button disabled={locked || !source || !destination} onClick={() => send('review')}>Review native database copy</Button>
    </Box>
    {!!catalogs.length && <Box component="pre" aria-label="DuckDB copy catalogs" sx={{whiteSpace: 'pre-wrap'}}>
      {JSON.stringify(catalogs, null, 2)}</Box>}
    {record && <>
      <Alert severity={record.state === 'refused' || record.state === 'partial' || record.state === 'unknown_outcome' ? 'warning' : 'info'}>
        Native database copy: {record.state}. Phase: {record.phase}. Acknowledgement does not mean committed.</Alert>
      {record.source && <Box component="textarea" aria-label="Reviewed DuckDB database copy SQL" readOnly value={record.source}
        sx={{width: '100%', minHeight: 80, fontFamily: 'monospace'}} />}
      {record.storage && <Box component="pre" aria-label="Reviewed DuckDB copy storage" sx={{whiteSpace: 'pre-wrap'}}>
        {JSON.stringify(record.storage, null, 2)}</Box>}
      {(record.warnings || []).map(warning => <Alert key={warning} severity="warning">{warning}</Alert>)}
      {record.state === 'reviewed' && record.phase === 'finished' && <>
        <TextField size="small" label="Exact copy destination confirmation" value={confirmation}
          disabled={locked} onChange={event => setConfirmation(event.target.value)} />
        <FormControlLabel label="I reviewed the native database copy and its transaction effects" control={<Checkbox
          checked={confirmed} disabled={locked} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={locked || !confirmed || confirmation !== record.destination_catalog}
          onClick={() => send('apply')}>Apply reviewed database copy once</Button>
        <Button disabled={busy || awaitingReceipt} onClick={() => send('discard')}>Discard database copy review</Button>
      </>}
      <Button disabled={busy} onClick={() => send('receipt')}>Read database copy receipt</Button>
      <Button disabled={busy || !running(record)} onClick={() => send('cancel')}>Cancel active database copy</Button>
      <Box component="pre" aria-label="DuckDB database copy receipt" sx={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(record, null, 2)}</Box>
    </>}
  </Box>;
}

DuckDBDatabaseCopy.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  sessionId: PropTypes.string, ensureSession: PropTypes.func.isRequired, disabled: PropTypes.bool,
  onBusyChange: PropTypes.func.isRequired, onBlocked: PropTypes.func};
