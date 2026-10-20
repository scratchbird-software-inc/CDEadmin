import {useLayoutEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField} from '@mui/material';

export default function DuckDBSessionSecrets({post, ensureSession, sessionId, databaseTargetId,
  catalog, disabled, onBusyChange, onBlocked, renderAdministration}) {
  const binding = useMemo(() => ({post, sessionId, databaseTargetId}), [post, sessionId, databaseTargetId]);
  const current = useRef(binding), pending = useRef(0), blocked = useRef(onBlocked);
  const [loaded, setLoaded] = useState(null), [selected, setSelected] = useState('');
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [receipts, setReceipts] = useState(null);
  useLayoutEffect(() => {blocked.current = onBlocked;}, [onBlocked]);
  useLayoutEffect(() => {current.current = binding; return () => {current.current = null;};}, [binding]);
  const enter = () => {pending.current++; setBusy(true); onBusyChange(true);};
  const leave = () => {pending.current--; if (!pending.current) {setBusy(false); onBusyChange(false);}};
  const resources = loaded?.post === post && loaded?.sessionId === sessionId &&
    loaded?.databaseTargetId === databaseTargetId ? loaded.resources : null;
  const load = async () => {
    if (disabled || pending.current) return;
    enter(); setError('');
    const original = current.current;
    try {
      const active = sessionId || await ensureSession();
      if (!current.current || current.current.post !== original.post || current.current.databaseTargetId !== databaseTargetId ||
          current.current.sessionId && current.current.sessionId !== active) return;
      const result = await post({action: 'source_catalog', session_id: active, database_target_id: databaseTargetId});
      if (!current.current || current.current.post !== original.post || current.current.databaseTargetId !== databaseTargetId ||
          current.current.sessionId && current.current.sessionId !== active) return;
      if (!Array.isArray(result.resources)) throw new Error('Native session catalog is unavailable.');
      const secrets = result.resources.filter(row => row.resource_kind === 'secret');
      setLoaded({post, sessionId: active, databaseTargetId, resources: secrets});
      setSelected(previous => secrets.some(row => row.resource_id === previous) ? previous : '');
    } catch (failure) {if (current.current === binding) setError(failure.message);}
    finally {leave();}
  };
  const scopedPost = useMemo(() => async body => {
    if (current.current !== binding || !sessionId) throw new Error('The DuckDB session changed. Inspect its secrets again.');
    pending.current++; setBusy(true); onBusyChange(true);
    try {
      if (body.action === 'resource_inspect') {
        const result = await post({action: 'source_catalog', session_id: sessionId, database_target_id: databaseTargetId});
        if (current.current !== binding) throw new Error('The DuckDB session changed.');
        const resource = result.resources?.find(row => row.resource_kind === 'secret' && row.resource_id === body.request.resource_id);
        if (!resource) throw new Error('This secret storage target is no longer available in the native session.');
        return resource;
      }
      if (!body.action.startsWith('visual_admin_')) throw new Error('Unsupported session secret action.');
      const result = await post({...body, request: {...body.request, session_id: sessionId, database_target_id: databaseTargetId}});
      if (current.current !== binding) throw new Error('The DuckDB session changed. Read the original operation receipt before another action.');
      return result;
    } catch (failure) {
      if (body.action === 'visual_admin_apply' && current.current === binding) blocked.current?.();
      throw failure;
    } finally {pending.current--; if (!pending.current) {setBusy(false); onBusyChange(false);}}
  }, [binding, post, sessionId, databaseTargetId, onBusyChange]);
  const nativeCatalog = useMemo(() => ({...catalog, objects: (catalog?.objects || [])
    .filter(row => row.resource_kind === 'secret')}), [catalog]);
  const resource = resources?.find(row => row.resource_id === selected);
  const readReceipts = async () => {
    try {
      const value = await scopedPost({action: 'visual_admin_operation_list', request: {}});
      setReceipts({binding, items: value.items?.filter(row => row.resource_kind === 'secret') || []});
      setError('');
    } catch (failure) {if (current.current === binding) setError(failure.message);}
  };
  return <Box component="details" sx={{mt: 1}}>
    <summary>DuckDB session secrets</summary>
    <Alert severity="info">Uses this editor connection. Temporary and persistent storage targets are distinct. Values are never read. Persistent file writes can survive rollback and be loaded by a later native instance.</Alert>
    <Button disabled={disabled || busy} onClick={load}>Inspect session secrets</Button>
    <Button disabled={!sessionId || busy} onClick={readReceipts}>Read session secret operation receipts</Button>
    {receipts?.binding === binding && <Box component="pre" sx={{whiteSpace: 'pre-wrap', overflowWrap: 'anywhere'}}>{JSON.stringify(receipts.items, null, 2)}</Box>}
    {resources && <>
      <TextField select size="small" label="Session secret storage target" value={selected}
        disabled={disabled || busy} onChange={event => {setSelected(event.target.value); setError('');}}>
        <MenuItem value="">Create a secret</MenuItem>
        {resources.map(row => {
          const native = row.native || row.extensions?.duckdb?.native || {};
          return <MenuItem key={row.resource_id} value={row.resource_id}>{row.display_name} / {native.storage} / {native.persistent ? 'persistent' : 'temporary'}</MenuItem>;
        })}
      </TextField>
      <Box component="fieldset" disabled={disabled || busy} sx={{border: 0, m: 0, p: 0}}>
        {renderAdministration({key: sessionId + ':' + selected, catalog: nativeCatalog,
          resources: resource ? [resource] : [], selectedResource: resource, post: scopedPost, setError,
          initialResourceKind: 'secret', initialOperationId: resource ? 'inspect' : 'create'})}
      </Box>
    </>}
    {error && <Alert severity="error">{error}</Alert>}
  </Box>;
}

DuckDBSessionSecrets.propTypes = {post: PropTypes.func.isRequired, ensureSession: PropTypes.func.isRequired,
  sessionId: PropTypes.string, databaseTargetId: PropTypes.string.isRequired, catalog: PropTypes.object,
  disabled: PropTypes.bool, onBusyChange: PropTypes.func.isRequired, onBlocked: PropTypes.func,
  renderAdministration: PropTypes.func.isRequired};
