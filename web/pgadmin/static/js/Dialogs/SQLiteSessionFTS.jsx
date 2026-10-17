import {useLayoutEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField} from '@mui/material';

export default function SQLiteSessionFTS({post, ensureSession, sessionId, databaseTargetId,
  catalog, disabled, onBusyChange, onBlocked, renderAdministration}) {
  const binding = useMemo(() => ({post, sessionId, databaseTargetId}), [post, sessionId, databaseTargetId]);
  const current = useRef(binding), pending = useRef(0);
  const blocked = useRef(onBlocked);
  useLayoutEffect(() => { blocked.current = onBlocked; }, [onBlocked]);
  const [loaded, setLoaded] = useState(null), [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false);
  const [receipts, setReceipts] = useState(null);
  const [error, setError] = useState('');
  useLayoutEffect(() => {
    current.current = binding;
    return () => { current.current = null; };
  }, [binding]);
  const resources = loaded?.post === post && loaded?.sessionId === sessionId && loaded?.databaseTargetId === databaseTargetId ? loaded.resources : null;
  const enter = () => { pending.current++; setBusy(true); onBusyChange(true); };
  const leave = () => { pending.current--; if (!pending.current) {setBusy(false); onBusyChange(false);} };
  const load = async () => {
    if (disabled || pending.current) return;
    enter(); setError('');
    const original = current.current;
    try {
      const active = sessionId || await ensureSession();
      const result = await post({action: 'source_catalog', session_id: active, database_target_id: databaseTargetId});
      if (!current.current || current.current.post !== original.post || current.current.databaseTargetId !== databaseTargetId ||
          (current.current.sessionId && current.current.sessionId !== active)) return;
      if (!Array.isArray(result.resources)) throw new Error('Native session catalog is unavailable.');
      const tables = result.resources.filter(row => row.resource_kind === 'fts-table');
      setLoaded({post, sessionId: active, databaseTargetId, resources: tables});
      setSelected(previous => tables.some(row => row.resource_id === previous) ? previous : tables[0]?.resource_id || '');
    } catch (failure) {
      if (current.current?.databaseTargetId === databaseTargetId) setError(failure.message);
    } finally { leave(); }
  };
  const scopedPost = useMemo(() => async body => {
    if (current.current !== binding || !binding.sessionId) throw new Error('The SQLite session changed. Inspect its FTS tables again.');
    pending.current++; setBusy(true); onBusyChange(true);
    try {
      if (body.action === 'resource_inspect') {
        const fresh = await post({action: 'source_catalog', session_id: sessionId, database_target_id: databaseTargetId});
        if (current.current !== binding) throw new Error('The SQLite session changed.');
        const resource = fresh.resources?.find(row => row.resource_id === body.request.resource_id);
        if (!resource) throw new Error('This FTS table is no longer available in the native session.');
        return resource;
      }
      if (!body.action.startsWith('visual_admin_')) throw new Error('Unsupported session FTS action.');
      const result = await post({...body, request: {...body.request, session_id: sessionId, database_target_id: databaseTargetId}});
      if (current.current !== binding) throw new Error('The SQLite session changed. Read the original operation receipt before any further action.');
      if (result.provider_result?.native_fts_maintenance?.native_outcome === 'unknown_outcome') blocked.current?.();
      return result;
    } catch (failure) {
      if (body.action === 'visual_admin_apply' && current.current === binding) blocked.current?.();
      throw failure;
    } finally {
      pending.current--; if (!pending.current) {setBusy(false); onBusyChange(false);}
    }
  }, [binding, post, sessionId, databaseTargetId, onBusyChange]);
  const nativeCatalog = useMemo(() => ({...catalog, objects: (catalog?.objects || [])
    .filter(row => row.resource_kind === 'fts-table').map(row => ({...row,
      operations: row.operations.filter(operation => operation.operation_id.startsWith('fts_'))}))}), [catalog]);
  const resource = resources?.find(row => row.resource_id === selected);
  const readReceipts = async () => {
    try {
      const value = await scopedPost({action: 'visual_admin_operation_list', request: {}});
      setReceipts({binding, items: value.items?.filter(row => row.operation_kind?.startsWith('fts_')) || []});
      setError('');
    } catch (failure) {if (current.current === binding) setError(failure.message);}
  };
  const observeReceipt = async operationId => {
    try {
      const value = await scopedPost({action: 'visual_admin_operation_refresh', request: {operation_id: operationId}});
      setReceipts(previous => previous?.binding === binding ? {...previous, items: previous.items.map(
        row => row.operation_id === operationId ? value : row)} : previous);
    } catch (failure) {if (current.current === binding) setError(failure.message);}
  };
  return <Box component="details" sx={{mt: 1}}>
    <summary>SQLite session FTS maintenance</summary>
    <Alert severity="info">Uses this SQL editor connection, including its TEMP and attached databases. Changes remain staged until you commit or roll back this session. SQLite interruption can roll back its entire write transaction.</Alert>
    <Button disabled={disabled || busy} onClick={load}>Inspect session FTS tables</Button>
    <Button disabled={!sessionId || busy} onClick={readReceipts}>Read session FTS operation receipts</Button>
    {receipts?.binding === binding && receipts.items.map(row => <Box key={row.operation_id}>
      <Button disabled={busy} onClick={() => observeReceipt(row.operation_id)}>Observe FTS task {row.operation_kind}</Button>
      <Box component="pre" sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{JSON.stringify(row, null, 2)}</Box>
    </Box>)}
    {resources && !resources.length && <Alert severity="info">No FTS tables were observed in this native session.</Alert>}
    {Boolean(resources?.length) && <>
      <TextField select size="small" label="Session FTS table" value={selected}
        disabled={disabled || busy} onChange={event => {setSelected(event.target.value); setError('');}}>
        {resources.map(row => <MenuItem key={row.resource_id} value={row.resource_id}>{row.display_path.join(' / ')}</MenuItem>)}
      </TextField>
      <Box component="fieldset" disabled={disabled || busy} sx={{border: 0, m: 0, p: 0}}>
        {resource && renderAdministration({key: sessionId + ':' + resource.resource_id, catalog: nativeCatalog,
          resources, selectedResource: resource, post: scopedPost, setError,
          initialResourceKind: 'fts-table', initialOperationId: 'fts_flush', focused: true})}
      </Box>
    </>}
    {error && <Alert severity="error">{error}</Alert>}
  </Box>;
}

SQLiteSessionFTS.propTypes = {post: PropTypes.func.isRequired, ensureSession: PropTypes.func.isRequired,
  sessionId: PropTypes.string, databaseTargetId: PropTypes.string.isRequired, catalog: PropTypes.object,
  disabled: PropTypes.bool, onBusyChange: PropTypes.func.isRequired, onBlocked: PropTypes.func,
  renderAdministration: PropTypes.func.isRequired};
