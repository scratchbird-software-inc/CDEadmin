import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';

export default function SQLiteExtensions({post, ensureSession, sessionId, databaseTargetId, disabled, onBusyChange, onBlocked}) {
  const [inventory, setInventory] = useState(null), [selected, setSelected] = useState('');
  const [receipt, setReceipt] = useState(null), [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const serial = useRef(0), previousSession = useRef(sessionId);
  useEffect(() => {
    if(previousSession.current && previousSession.current !== sessionId) {
      serial.current++; setInventory(null); setReceipt(null); setConfirmed(false); setError('');
    }
    previousSession.current = sessionId;
  }, [sessionId]);
  useEffect(() => () => {serial.current++;}, []);
  const run = async operation => {
    const token = ++serial.current;
    setBusy(true); onBusyChange(true); setError('');
    if(operation === 'load') setReceipt({...receipt, state: 'awaiting_native_response'});
    try {
      const active = sessionId || await ensureSession();
      const value = await post({action: 'sqlite_extensions', session_id: active,
        database_target_id: databaseTargetId, request: {operation,
          ...(operation === 'review' ? {extension_id: selected} : {}),
          ...(['load', 'receipt'].includes(operation) ? {review_id: receipt.review_id} : {}),
          ...(operation === 'load' ? {confirmed: true} : {})}});
      if(token !== serial.current) return;
      if(operation === 'inventory') {
        setInventory(value); setSelected(value.extensions?.[0]?.id || ''); setReceipt(null);
      } else setReceipt(value);
      if(value.state === 'unknown_outcome') onBlocked?.();
      setConfirmed(false);
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message ||
        'Extension response unavailable. Read its receipt before any further action.');
    } finally {setBusy(false); onBusyChange(false);}
  };
  return <Box component="details" sx={{mt: 1}}>
    <summary>SQLite native extensions</summary>
    <Alert severity="info">Libraries load on the application host into this query session. Closing ends the connection; native process effects may persist. Native initialization can have irreversible effects; loaded libraries are never automatically retried or reloaded.</Alert>
    <Button disabled={disabled || busy} onClick={() => run('inventory')}>Inspect approved extensions</Button>
    {inventory && <>
      <Alert severity={inventory.loader_available ? 'info' : 'warning'}>
        Execution host: {inventory.execution_host}. {inventory.loader_available ? 'Native loading API available.' : 'Native loading API unavailable; rebuild the application interpreter.'}
      </Alert>
      {!inventory.extensions?.length && <Alert severity="info">The application operator has not approved any native libraries.</Alert>}
      {Boolean(inventory.extensions?.length) && <>
        <TextField select size="small" label="Approved SQLite extension" value={selected}
          disabled={disabled || busy} onChange={event => {setSelected(event.target.value); setReceipt(null); setConfirmed(false);}}>
          {inventory.extensions.map(item => <MenuItem key={item.id} value={item.id}>{item.id}</MenuItem>)}
        </TextField>
        <Button disabled={disabled || busy || !selected || !inventory.loader_available} onClick={() => run('review')}>Review native library</Button>
      </>}
    </>}
    {receipt && <>
      <Alert severity={receipt.state === 'unknown_outcome' ? 'error' : 'info'}>Extension receipt {receipt.review_id}: {receipt.state}</Alert>
      <Box component="pre" sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{JSON.stringify(receipt, null, 2)}</Box>
      {receipt.state === 'reviewed' && <>
        <FormControlLabel label="Load this reviewed native library into the query session"
          control={<Checkbox checked={confirmed} disabled={disabled || busy} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={disabled || busy || !confirmed} onClick={() => run('load')}>Load native library</Button>
      </>}
      <Button disabled={busy} onClick={() => run('receipt')}>Read extension receipt</Button>
    </>}
    {error && <Alert severity="error">{error}</Alert>}
  </Box>;
}

SQLiteExtensions.propTypes = {post: PropTypes.func.isRequired, ensureSession: PropTypes.func.isRequired,
  sessionId: PropTypes.string, databaseTargetId: PropTypes.string.isRequired,
  disabled: PropTypes.bool, onBusyChange: PropTypes.func.isRequired, onBlocked: PropTypes.func};
