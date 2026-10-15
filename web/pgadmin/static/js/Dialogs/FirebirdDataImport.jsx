import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';
import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import useFirebirdDataSession from './firebirdDataSession';
import {stageTestData, firebirdTransactionIdle} from './firebirdTestDataHelpers';

export default function FirebirdDataImport({post, generation, databaseTargetId, onCatalogRefresh, onOpenAllocation, disabled}) {
  const [allocations, setAllocations] = useState([]);
  const [rowOrder, setRowOrder] = useState('');
  const [source, setSource] = useState(''), [filename, setFilename] = useState('');
  const [preview, setPreview] = useState(null), [receipt, setReceipt] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [confirmed, setConfirmed] = useState(false), [attempted, setAttempted] = useState(false);
  const [pending, setPending] = useState(false), [progress, setProgress] = useState(0);
  const [transaction, setTransaction] = useState(null);
  const scope = useFirebirdDataSession({post, databaseTargetId, purpose: 'firebird-data-import'});
  useEffect(() => {
    setAllocations([]); setRowOrder(''); setSource(''); setFilename(''); setPreview(null); setReceipt(null);
    setBusy(false); setError(''); setConfirmed(false); setAttempted(false); setPending(false); setProgress(0); setTransaction(null);
  }, [scope]);
  const load = async event => {
    const file = event.target.files?.[0]; event.target.value = ''; if(!file) return;
    setSource(''); setFilename(''); setPreview(null); setReceipt(null); setConfirmed(false); setError('');
    setAllocations([]); setAttempted(false);
    setBusy(true);
    try {
      if(file.size > 8 * 1024 * 1024) throw new Error('Data archive exceeds 8 MiB.');
      const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
      if(scope.active) {setSource(text); setFilename(file.name);}
    } catch(failure) {if(scope.active) setError(failure.message);}
    finally {if(scope.active) setBusy(false); else await scope.releaseAfterWork().catch(() => {});}
  };
  const prepare = async () => {
    setBusy(true); setError(''); setPreview(null); setConfirmed(false); setAttempted(false); setReceipt(null); setAllocations([]);
    try {
      const result = await post({action: 'firebird_data_import_plan', request: {
        ...(rowOrder.trim() ? {row_order: JSON.parse(rowOrder)} : {}),
        source, generation, database_target_id: databaseTargetId, refresh: true, include_system: false}});
      if(scope.active) {setPreview(result); setAllocations(result.allocation_targets || []);}
      if (scope.active) await onCatalogRefresh?.();
    } catch(failure) {if(scope.active) setError(failure.message || 'Data import preview failed.');}
    finally {if(scope.active) setBusy(false); else await scope.releaseAfterWork().catch(() => {});}
  };
  const run = async () => {
    scope.stopped = false; setBusy(true); setAttempted(true); setPending(true); setProgress(0); setError('');
    try {
      const sessionId = await scope.ensure();
      const result = await stageTestData({preview, catalogs: preview.catalogs, post,
        sessionId, databaseTargetId,
        stopped: () => scope.stopped || !scope.active,
        onProgress: count => {if(scope.active) setProgress(count);}});
      if(scope.active) setReceipt(result);
    } catch {if(scope.active) setError('Import stopped. Inspect the dedicated transaction; do not replay this preview.');}
    finally {
      if(scope.active) setBusy(false);
      else if(scope.sessionId) {
        // An earlier close may have met an in-flight native operation.
        // Release after it settles; never redispatch an imported row.
        await scope.releaseAfterWork().catch(() => {});
      }
    }
  };
  const control = async action => {
    setBusy(true); setError('');
    try {
      const result = await post({action: action === 'state' ? 'transaction' : 'transaction_action',
        session_id: scope.sessionId, database_target_id: databaseTargetId,
        ...(action === 'state' ? {} : {transaction_action: action})});
      if(scope.active) {
        setTransaction(result);
        if(action !== 'state') {
          setPreview(null); setConfirmed(false);
          if (firebirdTransactionIdle(result)) {
            setPending(false);
            try {await onCatalogRefresh?.();}
            catch {if (scope.active) setError('Native transaction outcome was received, but catalog refresh failed. Refresh the workspace before preparing another import.');}
          } else {setPending(true); setError('Native transaction remains active or unavailable. Inspect this session before further work.');}
        }
      }
    } catch {if(scope.active) setError('Native outcome was not received. Keep this session and inspect its state; do not replay the import.');}
    finally {if(scope.active) setBusy(false); else await scope.releaseAfterWork().catch(() => {});}
  };
  return <Box data-cde-compact-form sx={{my: 2, ...compactFormSx}}>
    <FormReference formKey="firebird-data-import" />
    <Alert severity="warning">Import data into this selected database using a separate native transaction. Preview checks exact destination types; embedded metadata and SQL are not executed. Constraints and triggers remain active. Staged rows need explicit commit or rollback. Closing requests session release without claiming an outcome.</Alert>
    <Button component="label" disabled={disabled || busy || pending}>Read data archive
      <input hidden type="file" accept=".ddn,.json,text/plain,application/json" aria-label="Firebird data archive file"
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
    {busy && pending && <Button onClick={() => {scope.stopped = true;}}>Stop after current row</Button>}
    {attempted && <Box>{progress} rows confirmed staged. {receipt?.state}</Box>}
    {receipt?.message && <Alert severity="warning">{receipt.message}</Alert>}
    {scope.sessionId && <Box>
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
          catch(failure) {if(scope.active) setError(failure.message || 'Native allocation object unavailable.');}
          finally {if(scope.active) setBusy(false); else await scope.releaseAfterWork().catch(() => {});}
        }}>Review allocation: {resource.display_path.join(' / ')}</Button>)}
    </Box>}
    {transaction && <Box component="pre" sx={{maxHeight: 140, overflow: 'auto'}}>{JSON.stringify(transaction, null, 2)}</Box>}
  </Box>;
}
FirebirdDataImport.propTypes = {post: PropTypes.func.isRequired, generation: PropTypes.string,
  databaseTargetId: PropTypes.string, onCatalogRefresh: PropTypes.func, onOpenAllocation: PropTypes.func, disabled: PropTypes.bool};
