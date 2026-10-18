import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function DuckDBAttachment({post, databaseTargetId, ensureSession, sessionId,
  disabled=false, onBusyChange, onBlocked}) {
  const [action, setAction] = useState('attach'), [alias, setAlias] = useState('');
  const [path, setPath] = useState(''), [readOnly, setReadOnly] = useState(true);
  const [conflict, setConflict] = useState('ERROR'), [create, setCreate] = useState(false), [missing, setMissing] = useState(false);
  const [blockSize, setBlockSize] = useState(''), [rowGroupSize, setRowGroupSize] = useState('');
  const [storageVersion, setStorageVersion] = useState(''), [compress, setCompress] = useState('');
  const [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState(''), [confirmed, setConfirmed] = useState(false);
  const [awaitingReceipt, setAwaitingReceipt] = useState(false);
  const serial = useRef(0), previousSession = useRef(sessionId);
  const blocked = disabled || result?.session_reuse_blocked === true || result?.state === 'unknown_outcome';
  useEffect(() => {serial.current++; setAlias(''); setPath(''); setResult(null); setError('');
    setBlockSize(''); setRowGroupSize(''); setStorageVersion(''); setCompress('');
    setConfirmed(false); setConfirmation(''); setBusy(false); setAwaitingReceipt(false);
    return () => {serial.current++;};}, [databaseTargetId, post]);
  useEffect(() => {
    if(previousSession.current && previousSession.current !== sessionId) {
      serial.current++; setResult(null); setConfirmed(false); setConfirmation(''); setBusy(false); setAwaitingReceipt(false);
      setError('The original native session closed or changed. Inspect the current catalogs before preparing another operation.');
    }
    previousSession.current = sessionId;
  }, [sessionId]);
  const clear = () => {setResult(null); setConfirmed(false); setConfirmation(''); setAwaitingReceipt(false);};
  const change = setter => event => {setter(event.target.value); clear();};
  const run = async operation => {
    const token = ++serial.current; setBusy(true); onBusyChange(true); setError('');
    try {
      const active = sessionId || await ensureSession();
      if(token !== serial.current) return;
      const options = {...(blockSize ? {block_size: blockSize} : {}), ...(rowGroupSize ? {row_group_size: rowGroupSize} : {}),
        ...(storageVersion ? {storage_version: storageVersion} : {}), ...(path === ':memory:' && compress ? {compress: compress === 'true'} : {})};
      const request = operation === 'review' ? {operation, draft: {action, alias,
        ...(action === 'attach' ? {path, read_only: readOnly, conflict, create_if_missing: create,
          ...(Object.keys(options).length ? {storage_options: options} : {})} : {if_exists: missing})}} :
        operation === 'inventory' ? {operation} : {operation, review_id: result.review_id,
          ...(operation === 'apply' ? {review_digest: result.review_digest, confirmation, confirmed} : {})};
      if(operation === 'apply') setAwaitingReceipt(true);
      const value = await post({action: 'duckdb_attachments', database_target_id: databaseTargetId,
        session_id: active, request});
      if(token === serial.current) {
        setResult(value); setConfirmed(false); setConfirmation(''); setAwaitingReceipt(false);
        if(value.session_reuse_blocked) onBlocked?.();
      }
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message ||
      'The native reply is unavailable. Read the attachment receipt before preparing another operation.');}
    finally {if(token === serial.current) setBusy(false); onBusyChange(false);}
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([result.source], {type: 'text/plain'}));
    const link = document.createElement('a'); link.href = url; link.download = `duckdb-${action}.sql`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, gridAutoRows: 'max-content', p: 1, overflow: 'auto'}}>
    <FormReference formKey="duckdb-attachment" />
    <Alert severity="info">Review and apply on the current native query session. Catalog changes can be visible to other connections sharing its DuckDB instance. Commit and rollback remain explicit. Rollback does not restore a detached catalog or remove a newly created file.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {awaitingReceipt && <Alert severity="warning">Read the attachment receipt before changing the form or preparing another operation.</Alert>}
    <Box sx={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1, my: 1}}>
      <Button disabled={busy || blocked || awaitingReceipt} onClick={() => run('inventory')}>Inspect current native catalogs</Button>
      <TextField select size="small" label="Action" value={action} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setAction)}><MenuItem value="attach">Attach file</MenuItem><MenuItem value="detach">Detach alias</MenuItem></TextField>
      <TextField size="small" label="Native catalog alias" value={alias} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setAlias)} sx={{minWidth: 210}} />
      {action === 'attach' && <><TextField size="small" label="Absolute DuckDB file path" value={path} disabled={busy || blocked || awaitingReceipt}
        onChange={event => {setPath(event.target.value); setCompress(''); if(event.target.value === ':memory:') setCreate(false); clear();}} sx={{minWidth: 350}}
        helperText="Use :memory: for an authorized writable in-memory catalog." />
      <FormControlLabel label="Read only" control={<Checkbox checked={readOnly} disabled={busy || blocked || awaitingReceipt}
        onChange={event => {setReadOnly(event.target.checked); if(event.target.checked) setCreate(false); clear();}} />} />
      <TextField select size="small" label="Existing alias" value={conflict} disabled={busy || blocked || awaitingReceipt} onChange={change(setConflict)}>
        <MenuItem value="ERROR">Refuse</MenuItem><MenuItem value="IGNORE">IF NOT EXISTS</MenuItem><MenuItem value="REPLACE">OR REPLACE</MenuItem>
      </TextField>
      <FormControlLabel label="Allow native file creation" control={<Checkbox checked={create} disabled={busy || blocked || awaitingReceipt || readOnly || path === ':memory:'}
        onChange={event => {setCreate(event.target.checked); clear();}} />} />
      <TextField size="small" label="Block size (bytes)" value={blockSize} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setBlockSize)} helperText="Optional native unsigned integer; blank uses the engine default." />
      <TextField size="small" label="Row-group size (rows)" value={rowGroupSize} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setRowGroupSize)} helperText="Optional native unsigned integer." />
      <TextField size="small" label="Storage version" value={storageVersion} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setStorageVersion)} helperText="Optional native version, for example v1.5.0 or latest." />
      <TextField select size="small" label="In-memory compression" value={compress} disabled={busy || blocked || awaitingReceipt || path !== ':memory:'}
        onChange={change(setCompress)}><MenuItem value="">Native default</MenuItem><MenuItem value="true">Compress</MenuItem><MenuItem value="false">Do not compress</MenuItem></TextField>
      </>}
      {action === 'detach' && <FormControlLabel label="IF EXISTS" control={<Checkbox checked={missing} disabled={busy || blocked || awaitingReceipt}
        onChange={event => {setMissing(event.target.checked); clear();}} />} />}
      <Button disabled={busy || blocked || awaitingReceipt || !alias || (action === 'attach' && !path)} onClick={() => run('review')}>Review native attachment</Button>
      <Button disabled={busy || !result?.source} onClick={download}>Save SQL script</Button>
    </Box>
    {result?.catalogs && <Box component="pre" aria-label="Current DuckDB catalogs" sx={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(result.catalogs, null, 2)}</Box>}
    {result?.source && <><Alert severity="info">Native attachment review: {result.state}. Session scope: {result.session_scope_id}. Repeated submissions read the same receipt.</Alert>
      <Box component="textarea" aria-label="Generated DuckDB attachment SQL" value={result.source} readOnly
        sx={{width: '100%', boxSizing: 'border-box', minHeight: 90, resize: 'vertical', fontFamily: 'monospace', fontSize: '0.875rem'}} />
      {(result.warnings || []).map(warning => <Alert key={warning} severity="warning">{warning}</Alert>)}
      {result.state === 'reviewed' && <>
        <TextField size="small" label="Exact reviewed catalog alias" value={confirmation} disabled={busy || blocked || awaitingReceipt} onChange={event => setConfirmation(event.target.value)} />
        <FormControlLabel label="I reviewed the native catalog and file effects" control={<Checkbox checked={confirmed} disabled={busy || blocked || awaitingReceipt} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || blocked || awaitingReceipt || !confirmed || confirmation !== result.alias} onClick={() => run('apply')}>Apply reviewed attachment once</Button>
      </>}
      <Button disabled={busy} onClick={() => run('receipt')}>Read attachment receipt</Button>
      {result.state !== 'reviewed' && <Box component="pre" aria-label="DuckDB attachment receipt" sx={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(result, null, 2)}</Box>}
    </>}
  </Box>;
}
DuckDBAttachment.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  ensureSession: PropTypes.func.isRequired, sessionId: PropTypes.string,
  disabled: PropTypes.bool, onBusyChange: PropTypes.func.isRequired, onBlocked: PropTypes.func};
