import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {stageTestData} from './firebirdTestData';

export default function FirebirdDataImport({post, generation, databaseTargetId, onCatalogRefresh, onOpenAllocation, disabled}) {
  const [allocations, setAllocations] = useState([]);
  const [rowOrder, setRowOrder] = useState('');
  const [source, setSource] = useState(''), [filename, setFilename] = useState('');
  const [preview, setPreview] = useState(null), [receipt, setReceipt] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [confirmed, setConfirmed] = useState(false), [attempted, setAttempted] = useState(false);
  const [pending, setPending] = useState(false), [progress, setProgress] = useState(0);
  const [transaction, setTransaction] = useState(null);
  const session = useRef(null), mounted = useRef(true), stopped = useRef(false);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false; stopped.current = true;
      if (session.current) post({action: 'close_session', session_id: session.current,
        database_target_id: databaseTargetId}).catch(() => {});
    };
  }, [post, databaseTargetId]);
  const load = async event => {
    const file = event.target.files?.[0]; event.target.value = ''; if(!file) return;
    setSource(''); setFilename(''); setPreview(null); setReceipt(null); setConfirmed(false); setError('');
    setAllocations([]); setAttempted(false);
    setBusy(true);
    try {
      if(file.size > 8 * 1024 * 1024) throw new Error('Data archive exceeds 8 MiB.');
      const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
      if(mounted.current) {setSource(text); setFilename(file.name);}
    } catch(failure) {if(mounted.current) setError(failure.message);}
    finally {if(mounted.current) setBusy(false);}
  };
  const prepare = async () => {
    setBusy(true); setError(''); setPreview(null); setConfirmed(false); setAttempted(false); setReceipt(null); setAllocations([]);
    try {
      const result = await post({action: 'firebird_data_import_plan', request: {
        ...(rowOrder.trim() ? {row_order: JSON.parse(rowOrder)} : {}),
        source, generation, database_target_id: databaseTargetId, refresh: true, include_system: false}});
      if(mounted.current) {setPreview(result); setAllocations(result.allocation_targets || []);}
      await onCatalogRefresh?.();
    } catch(failure) {if(mounted.current) setError(failure.message || 'Data import preview failed.');}
    finally {if(mounted.current) setBusy(false);}
  };
  const run = async () => {
    stopped.current = false; setBusy(true); setAttempted(true); setPending(true); setProgress(0); setError('');
    try {
      if(!session.current) {
        const opened = await post({action: 'open_session', language_profile: 'firebird-sql',
          database_target_id: databaseTargetId, session_purpose: 'firebird-data-import'});
        session.current = opened.session_id;
        if(!mounted.current) {
          await post({action: 'close_session', session_id: opened.session_id, database_target_id: databaseTargetId});
          session.current = null; return;
        }
      }
      const result = await stageTestData({preview, catalogs: preview.catalogs, post,
        sessionId: session.current, databaseTargetId,
        stopped: () => stopped.current || !mounted.current,
        onProgress: count => {if(mounted.current) setProgress(count);}});
      if(mounted.current) setReceipt(result);
    } catch {if(mounted.current) setError('Import stopped. Inspect the dedicated transaction; do not replay this preview.');}
    finally {
      if(mounted.current) setBusy(false);
      else if(session.current) {
        // An earlier close may have met an in-flight native operation.
        // Release after it settles; never redispatch an imported row.
        await post({action: 'close_session', session_id: session.current,
          database_target_id: databaseTargetId}).catch(() => {});
      }
    }
  };
  const control = async action => {
    setBusy(true); setError('');
    try {
      const result = await post({action: action === 'state' ? 'transaction' : 'transaction_action',
        session_id: session.current, database_target_id: databaseTargetId,
        ...(action === 'state' ? {} : {transaction_action: action})});
      if(mounted.current) {
        setTransaction(result);
        if(action !== 'state') {
          setPending(false); setPreview(null); setConfirmed(false);
          try {await onCatalogRefresh?.();}
          catch {setError('Native transaction outcome was received, but catalog refresh failed. Refresh the workspace before preparing another import.');}
        }
      }
    } catch {if(mounted.current) setError('Native outcome was not received. Keep this session and inspect its state; do not replay the import.');}
    finally {if(mounted.current) setBusy(false);}
  };
  return <Box sx={{my: 2}}>
    <FormReference formKey="firebird-data-import" />
    <Alert severity="warning">Import data into this selected database using a separate native transaction. Preview checks exact destination types; embedded metadata and SQL are not executed. Constraints and triggers remain active. Staged rows need explicit commit or rollback. Closing requests session release without claiming an outcome.</Alert>
    <Button component="label" disabled={disabled || busy || pending}>Read data archive
      <input hidden type="file" accept=".json,application/json" aria-label="Firebird data archive file"
        disabled={disabled || busy || pending} onChange={load} />
    </Button>
    <span>{filename}</span>
    <TextField label="Explicit row order (optional JSON)" multiline minRows={2} value={rowOrder}
      disabled={disabled || busy || pending} helperText={'Complete list, for example [{"table":"T","row":0}]. Rows are zero-based. Values and native constraints remain unchanged.'}
      onChange={event => {setRowOrder(event.target.value); setPreview(null); setConfirmed(false);}} />
    <Button disabled={disabled || busy || pending || !source || !generation} onClick={prepare}>Preview data import</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {preview && <>
      <Box>Import ordering: {preview.ordering || 'table-dependencies'}</Box>
      <Box>{preview.operations.length} rows. Table order: {preview.order.join(', ')}. Source SHA-256: {preview.source_sha256}</Box>
      {preview.external_prerequisites.map((item, index) => <Alert severity="warning" key={index}>{item.table}: referenced rows must already exist in {item.requires_existing_rows_in}.</Alert>)}
      {preview.identity_requirements.map(item => <Alert severity="warning" key={item.table}>{item.table}: preserve {item.columns.join(', ')} with OVERRIDING SYSTEM VALUE. Reconcile native identity allocation separately before enabling generated inserts; this import does not advance generators.</Alert>)}
      <Box component="pre" sx={{maxHeight: 220, overflow: 'auto'}}>{JSON.stringify(preview.operations.slice(0, 10), null, 2)}</Box>
      <FormControlLabel label="I authorize importing these rows into the selected database" control={<Checkbox checked={confirmed}
        disabled={disabled || busy || attempted} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={disabled || busy || attempted || !confirmed || !preview.operations.length} onClick={run}>Stage imported rows</Button>
    </>}
    {busy && pending && <Button onClick={() => {stopped.current = true;}}>Stop after current row</Button>}
    {attempted && <Box>{progress} rows confirmed staged. {receipt?.state}</Box>}
    {receipt?.message && <Alert severity="warning">{receipt.message}</Alert>}
    {session.current && <Box>
      <Button disabled={busy} onClick={() => control('state')}>Inspect import transaction</Button>
      <Button disabled={busy || !pending} onClick={() => control('commit')}>Commit imported rows</Button>
      <Button disabled={busy || !pending} onClick={() => control('rollback')}>Roll back imported rows</Button>
    </Box>}
    {!pending && attempted && allocations.length > 0 && onOpenAllocation && <Box>
      <Alert severity="warning">Coordinate concurrent writers before restarting allocation. No next value is inferred from imported rows. Each link opens a separate native Alter form for review and confirmation.</Alert>
      {allocations.map(resource => <Button key={resource.resource_id} disabled={busy || disabled}
        onClick={async () => {
          setBusy(true); setError('');
          try {await onOpenAllocation(resource);}
          catch(failure) {if(mounted.current) setError(failure.message || 'Native allocation object unavailable.');}
          finally {if(mounted.current) setBusy(false);}
        }}>Review allocation: {resource.display_path.join(' / ')}</Button>)}
    </Box>}
    {transaction && <Box component="pre" sx={{maxHeight: 140, overflow: 'auto'}}>{JSON.stringify(transaction, null, 2)}</Box>}
  </Box>;
}
FirebirdDataImport.propTypes = {post: PropTypes.func.isRequired, generation: PropTypes.string,
  databaseTargetId: PropTypes.string, onCatalogRefresh: PropTypes.func, onOpenAllocation: PropTypes.func, disabled: PropTypes.bool};
