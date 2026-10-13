import {compactActionsSx} from '../cdeadmin_ui/foundations/compactFormLayout';
import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, TextField} from '@mui/material';

export default function FirebirdDesignStorage({post, databaseTargetId, kind, capture, onLoad, disabled, engine='firebird'}) {
  const family = kind === 'catalog' ? 'catalog' : 'relational';
  const [reference, setReference] = useState(null), [revision, setRevision] = useState('');
  const [busy, setBusy] = useState(false), [message, setMessage] = useState(''), [error, setError] = useState('');
  const epoch = useRef(0), running = useRef(false);
  useEffect(() => {
    epoch.current++; running.current = false; setReference(null); setRevision(''); setMessage(''); setError(''); setBusy(false);
    return () => {epoch.current++;};
  }, [post, databaseTargetId, kind, engine]);
  const act = async mode => {
    if (running.current) return;
    const serial = epoch.current;
    running.current = true; setBusy(true); setError('');
    try {
      const request = {kind, database_target_id: databaseTargetId};
      if (mode === 'save') Object.assign(request, capture(), {assetRef: reference});
      if (mode === 'load' && revision) {
        if (!/^[1-9][0-9]*$/.test(revision) || !Number.isSafeInteger(Number(revision))) throw new Error('Enter a positive revision number.');
        request.version = Number(revision);
      }
      const value = await post({action: engine + '_design_' + (mode === 'save' ? 'save' : 'read'), request});
      if (serial !== epoch.current) return;
      setReference(value.assetRef);
      if (mode === 'load' && value.snapshot) onLoad(value);
      setMessage(value.version ? `${mode === 'save' ? 'Saved' : mode === 'load' ? 'Loaded' : 'Available'} ${family} design revision ${value.version}; current revision ${value.assetRef.assetVersion}.` : `No saved ${family} design yet.`);
    } catch (failure) {if (serial === epoch.current) setError(failure.response?.data?.errormsg || failure.message || 'Design storage request failed.');}
    finally {if (serial === epoch.current) {running.current = false; setBusy(false);}}
  };
  if (!post || !databaseTargetId) return null;
  return <Box sx={compactActionsSx}>
    <Button disabled={disabled || busy} onClick={() => act('check')}>Check saved {family} design</Button>
    <Button disabled={disabled || busy || !reference} onClick={() => act('save')}>Save {family} design revision</Button>
    <TextField size="small" label={`${family === 'catalog' ? 'Catalog' : 'Relational'} design revision (blank for latest)`} value={revision}
      disabled={disabled || busy} onChange={event => setRevision(event.target.value)} />
    <Button disabled={disabled || busy} onClick={() => act('load')}>Load saved {family} design</Button>
    {message && <Alert severity="info">{message}</Alert>}
    {error && <Alert severity="error">{error}</Alert>}
  </Box>;
}
FirebirdDesignStorage.propTypes = {engine: PropTypes.oneOf(['firebird', 'mysql', 'mariadb']), post: PropTypes.func, databaseTargetId: PropTypes.string,
  kind: PropTypes.oneOf(['catalog', 'relations']).isRequired, capture: PropTypes.func.isRequired,
  onLoad: PropTypes.func.isRequired, disabled: PropTypes.bool};
