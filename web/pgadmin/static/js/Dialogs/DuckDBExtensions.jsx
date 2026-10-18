import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function DuckDBExtensions({post, databaseTargetId, ensureSession, sessionId,
  disabled=false, onBusyChange, onBlocked}) {
  const [action, setAction] = useState('install'), [extensionName, setExtensionName] = useState('');
  const [sourceKind, setSourceKind] = useState('NAME'), [source, setSource] = useState('');
  const [repositoryKind, setRepositoryKind] = useState('DEFAULT'), [repository, setRepository] = useState('');
  const [version, setVersion] = useState(''), [force, setForce] = useState(false);
  const [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [confirmation, setConfirmation] = useState(''), [confirmed, setConfirmed] = useState(false);
  const [awaitingReceipt, setAwaitingReceipt] = useState(false);
  const serial = useRef(0), previousSession = useRef(sessionId);
  const blocked = disabled || result?.session_reuse_blocked === true || result?.state === 'unknown_outcome';
  useEffect(() => {serial.current++; setExtensionName(''); setSource(''); setResult(null); setError('');
    setConfirmed(false); setConfirmation(''); setBusy(false); setAwaitingReceipt(false);
    return () => {serial.current++;};}, [databaseTargetId, post]);
  useEffect(() => {
    if(previousSession.current && previousSession.current !== sessionId) {
      serial.current++; setResult(null); setConfirmed(false); setConfirmation(''); setBusy(false); setAwaitingReceipt(false);
      setError('The original native session closed or changed. Inspect the native extensions before preparing another operation.');
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
      const request = operation === 'review' ? {operation, draft: {action, extension_name: extensionName,
        source_kind: sourceKind, ...(sourceKind === 'FILE' ? {source} : {}),
        ...(action === 'install' ? {force} : {}),
        ...(action === 'install' && sourceKind === 'NAME' ? {repository_kind: repositoryKind,
          ...(repositoryKind !== 'DEFAULT' ? {repository} : {}), ...(version ? {version} : {})} : {})}} :
        operation === 'inventory' ? {operation} : {operation, review_id: result.review_id,
          ...(operation === 'apply' ? {review_digest: result.review_digest, confirmation, confirmed} : {})};
      if(operation === 'apply') setAwaitingReceipt(true);
      const value = await post({action: 'duckdb_extensions', database_target_id: databaseTargetId,
        session_id: active, request});
      if(token === serial.current) {
        setResult(value); setConfirmed(false); setConfirmation(''); setAwaitingReceipt(false);
        if(value.session_reuse_blocked) onBlocked?.();
      }
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message ||
      'The native reply is unavailable. Read the extension receipt before preparing another operation.');}
    finally {if(token === serial.current) setBusy(false); onBusyChange(false);}
  };
  return <Box sx={{...compactFormSx, gridAutoRows: 'max-content', p: 1, overflow: 'auto'}}>
    <FormReference formKey="duckdb-extensions" />
    <Alert severity="info">Install extension files or load native extension code on the original query session. Installation files and loaded code have effects outside database rollback. Native signature and external-access policies remain enforced.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {awaitingReceipt && <Alert severity="warning">Read the extension receipt before changing the form or preparing another operation.</Alert>}
    <Box sx={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1, my: 1}}>
      <Button disabled={busy || blocked || awaitingReceipt} onClick={() => run('inventory')}>Inspect native extensions</Button>
      <TextField select size="small" label="Extension action" value={action} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setAction)}><MenuItem value="install">Install file</MenuItem><MenuItem value="load">Load native code</MenuItem></TextField>
      <TextField size="small" label="Exact native extension name" value={extensionName} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setExtensionName)} />
      <TextField select size="small" label="Extension source" value={sourceKind} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setSourceKind)}><MenuItem value="NAME">Native name</MenuItem><MenuItem value="FILE">Authorized local file</MenuItem></TextField>
      {sourceKind === 'FILE' && <TextField size="small" label="Absolute native extension file" value={source} disabled={busy || blocked || awaitingReceipt}
        onChange={change(setSource)} sx={{minWidth: 350}} />}
      {action === 'install' && <FormControlLabel label="FORCE replacement of extension file" control={<Checkbox checked={force} disabled={busy || blocked || awaitingReceipt}
        onChange={event => {setForce(event.target.checked); clear();}} />} />}
      {action === 'install' && sourceKind === 'NAME' && <>
        <TextField select size="small" label="Repository kind" value={repositoryKind} disabled={busy || blocked || awaitingReceipt} onChange={change(setRepositoryKind)}>
          <MenuItem value="DEFAULT">Native default</MenuItem><MenuItem value="ALIAS">Native alias</MenuItem>
          <MenuItem value="URL">Public HTTP(S) URL</MenuItem><MenuItem value="DIRECTORY">Authorized directory</MenuItem>
        </TextField>
        {repositoryKind !== 'DEFAULT' && <TextField size="small" label="Native extension repository" value={repository} disabled={busy || blocked || awaitingReceipt} onChange={change(setRepository)} />}
        <TextField size="small" label="Exact extension version (optional)" value={version} disabled={busy || blocked || awaitingReceipt} onChange={change(setVersion)} />
      </>}
      <Button disabled={busy || blocked || awaitingReceipt || !extensionName || (sourceKind === 'FILE' && !source)} onClick={() => run('review')}>Review native extension</Button>
    </Box>
    {result?.extensions && <Box component="pre" aria-label="Native DuckDB extensions" sx={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(result.extensions, null, 2)}</Box>}
    {result?.source && <><Alert severity="info">Native extension review: {result.state}. Session scope: {result.session_scope_id}. Repeated submissions read the same receipt.</Alert>
      <Box component="textarea" aria-label="Generated DuckDB extension SQL" value={result.source} readOnly
        sx={{width: '100%', boxSizing: 'border-box', minHeight: 90, resize: 'vertical', fontFamily: 'monospace', fontSize: '0.875rem'}} />
      {(result.warnings || []).map(warning => <Alert key={warning} severity="warning">{warning}</Alert>)}
      {result.state === 'reviewed' && <>
        <TextField size="small" label="Exact reviewed extension name" value={confirmation} disabled={busy || blocked || awaitingReceipt} onChange={event => setConfirmation(event.target.value)} />
        <FormControlLabel label="I reviewed the native extension code and file effects" control={<Checkbox checked={confirmed} disabled={busy || blocked || awaitingReceipt} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || blocked || awaitingReceipt || !confirmed || confirmation !== result.extension_name} onClick={() => run('apply')}>Apply reviewed extension once</Button>
      </>}
      <Button disabled={busy} onClick={() => run('receipt')}>Read extension receipt</Button>
      {result.state !== 'reviewed' && <Box component="pre" aria-label="DuckDB extension receipt" sx={{whiteSpace: 'pre-wrap'}}>{JSON.stringify(result, null, 2)}</Box>}
    </>}
  </Box>;
}
DuckDBExtensions.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  ensureSession: PropTypes.func.isRequired, sessionId: PropTypes.string,
  disabled: PropTypes.bool, onBusyChange: PropTypes.func.isRequired, onBlocked: PropTypes.func};
