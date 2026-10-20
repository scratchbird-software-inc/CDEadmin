import {useCallback, useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField, Typography} from '@mui/material';

export default function MariaDBBackupStages({post, databaseTargetId, sessionId, ensureSession,
  disabled=false, onBusyChange, onBlocked}) {
  const [stage, setStage] = useState('START'), [waitSeconds, setWaitSeconds] = useState('5');
  const [database, setDatabase] = useState(''), [table, setTable] = useState('');
  const [record, setRecord] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState(''), [confirmed, setConfirmed] = useState(false);
  const [awaitingReceipt, setAwaitingReceipt] = useState(false);
  const serial = useRef(0), previousSession = useRef(sessionId);
  const ownsBusy = useRef(false);
  useEffect(() => {
    serial.current++; setRecord(null); setError(''); setConfirmation(''); setConfirmed(false);
    setBusy(false); setAwaitingReceipt(false);
    return () => {serial.current++; if(ownsBusy.current) onBusyChange(false); ownsBusy.current = false;};
  }, [post, databaseTargetId, onBusyChange]);
  useEffect(() => {
    if(previousSession.current && previousSession.current !== sessionId) {
      if(ownsBusy.current) onBusyChange(false);
      ownsBusy.current = false;
      serial.current++; setRecord(null); setConfirmation(''); setConfirmed(false); setBusy(false); setAwaitingReceipt(false);
      setError('The native session changed. Inspect the new connection before reviewing another stage.');
    }
    previousSession.current = sessionId;
  }, [sessionId, onBusyChange]);
  const receive = useCallback(value => {
    ownsBusy.current = value.state === 'executing';
    setRecord(value); setAwaitingReceipt(false); onBusyChange(value.state === 'executing');
    if(value.session_reuse_blocked) onBlocked?.();
  }, [onBusyChange, onBlocked]);
  const send = async operation => {
    ownsBusy.current = true;
    const token = ++serial.current; setBusy(true); setError(''); onBusyChange(true);
    let keepBusy = false;
    try {
      const active = sessionId || await ensureSession();
      if(token !== serial.current) return;
      const request = operation === 'inventory' ? {operation} : operation === 'review' ?
        {operation, draft: {lock_wait_seconds: waitSeconds === '' ? null : Number(waitSeconds),
          ...(stage === 'LOCK' ? {action: 'lock', database, table} : stage === 'UNLOCK' ? {action: 'unlock'} : {stage})}} :
        {operation, review_id: record.review_id,
          ...(operation === 'apply' ? {review_digest: record.review_digest, confirmation, confirmed} :
            operation === 'discard' ? {review_digest: record.review_digest} : {})};
      if(operation === 'apply') setAwaitingReceipt(true);
      const value = await post({action: 'mariadb_backup_stages', database_target_id: databaseTargetId,
        session_id: active, request});
      if(token === serial.current) {
        receive(value); keepBusy = value.state === 'executing';
        setConfirmation(''); setConfirmed(false);
      }
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message ||
      'The native reply is unavailable. Read the existing stage receipt before dispatching another command.');}
    finally {if(token === serial.current) {setBusy(false); ownsBusy.current = keepBusy; onBusyChange(keepBusy);}}
  };
  useEffect(() => {
    if(record?.state !== 'executing' || busy || !sessionId) return undefined;
    const token = serial.current;
    const timer = setTimeout(async () => {
      try {
        const value = await post({action: 'mariadb_backup_stages', database_target_id: databaseTargetId,
          session_id: sessionId, request: {operation: 'receipt', review_id: record.review_id}});
        if(token === serial.current) receive(value);
      } catch(failure) {if(token === serial.current) setError(failure.message || 'Read the stage receipt to recover the native result.');}
    }, 500);
    return () => clearTimeout(timer);
  }, [record, busy, sessionId, post, databaseTargetId, receive]);
  const locked = disabled || busy || awaitingReceipt || record?.state === 'executing' || record?.session_reuse_blocked;
  const change = setter => event => {setter(event.target.value); setRecord(null); setConfirmation(''); setConfirmed(false);};
  return <Box sx={{p: 1, borderTop: '1px solid', borderColor: 'divider'}}>
    <Typography variant="h6">MariaDB native backup stages</Typography>
    <Alert severity="warning">These commands affect server-wide backup locks and perform implicit commits.
      The workflow refuses an active transaction. Use this original SQL connection: END releases stages, UNLOCK releases a table backup lock, and closing the session releases its backup locks.
      Stage commands do not create or verify backup files.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {awaitingReceipt && <Alert severity="warning">Read the native stage receipt before dispatching another command.</Alert>}
    <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, my: 1}}>
      <Button disabled={locked} onClick={() => send('inventory')}>Inspect native backup connection</Button>
      <TextField select size="small" label="Native MariaDB backup stage" value={stage} disabled={locked} onChange={change(setStage)}>
        {['START', 'FLUSH', 'BLOCK_DDL', 'BLOCK_COMMIT', 'END', 'LOCK', 'UNLOCK'].map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}
      </TextField>
      {stage === 'LOCK' && <>
        <TextField size="small" label="Backup-lock database" value={database} disabled={locked} onChange={change(setDatabase)} />
        <TextField size="small" label="Backup-lock table" value={table} disabled={locked} onChange={change(setTable)} />
      </>}
      <TextField size="small" label="Backup lock wait (seconds)" value={waitSeconds} disabled={locked}
        onChange={change(setWaitSeconds)} helperText="Native integer 0–31536000; zero does not wait." />
      <Button disabled={locked} onClick={() => send('review')}>Review native backup stage</Button>
    </Box>
    {record?.native_session && !record?.review_id && <Box component="pre" aria-label="MariaDB backup connection" sx={{whiteSpace: 'pre-wrap'}}>
      {JSON.stringify(record, null, 2)}</Box>}
    {record?.review_id && <>
      <Alert severity={record.state === 'refused' || record.state === 'unknown_outcome' ? 'warning' : 'info'}>
        Native stage command: {record.stage}. Result: {record.state}. This receipt does not infer the current global lock state.</Alert>
      <Box component="textarea" aria-label="Reviewed MariaDB backup stage SQL" readOnly value={record.source}
        sx={{width: '100%', minHeight: 65, fontFamily: 'monospace'}} />
      {(record.warnings || []).map(value => <Alert key={value} severity="warning">{value}</Alert>)}
      {record.state === 'reviewed' && <>
        <TextField size="small" label="Exact native stage confirmation" value={confirmation} disabled={locked}
          onChange={event => setConfirmation(event.target.value)} />
        <FormControlLabel label="I reviewed the server-wide backup locks and implicit commit behavior" control={<Checkbox
          checked={confirmed} disabled={locked} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={locked || !confirmed || confirmation !== record.stage} onClick={() => send('apply')}>Apply reviewed backup stage once</Button>
        <Button disabled={busy || awaitingReceipt} onClick={() => send('discard')}>Discard backup stage review</Button>
      </>}
      <Button disabled={busy} onClick={() => send('receipt')}>Read backup stage receipt</Button>
      <Button disabled={busy || record.state !== 'executing'} onClick={() => send('cancel')}>Cancel active backup stage command</Button>
      <Box component="pre" aria-label="MariaDB backup stage receipt" sx={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(record, null, 2)}</Box>
    </>}
  </Box>;
}

MariaDBBackupStages.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  sessionId: PropTypes.string, ensureSession: PropTypes.func.isRequired, disabled: PropTypes.bool,
  onBusyChange: PropTypes.func.isRequired, onBlocked: PropTypes.func};
