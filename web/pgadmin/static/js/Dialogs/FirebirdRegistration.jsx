import {useEffect, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdRegistration({post, targetId, operation='clone', onChanged}) {
  const [catalog, setCatalog] = useState(null), [error, setError] = useState('');
  const [destination, setDestination] = useState(''), [name, setName] = useState('');
  const [credentials, setCredentials] = useState('source'), [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false), [attempted, setAttempted] = useState(false), [result, setResult] = useState(null);
  useEffect(() => {
    let live = true;
    post({action: 'database_target_transfer_catalog', request: {target_id: targetId}}).then(value => {
      if (!live) return;
      setCatalog(value); setName(value.source.display_name + (operation === 'clone' ? ' clone' : ''));
      setDestination(operation === 'clone' ? value.source_server_id : '');
    }).catch(failure => {if (live) setError(failure.message || 'Registration catalog is unavailable.');});
    return () => {live = false;};
  }, [post, targetId, operation]);
  const apply = async () => {
    setBusy(true); setAttempted(true); setError('');
    try {
      const value = await post({action: 'database_target_transfer', request: {target_id: targetId,
        destination_server_id: Number(destination), operation, display_name: name, credentials, confirmed}});
      setResult(value); onChanged?.(value);
    } catch (failure) {setError((failure.message || 'Registration change was not confirmed.') +
      ' Inspect and refresh both server registrations before trying again. No native database operation was requested.');}
    finally {setBusy(false);}
  };
  return <Box sx={{p: 1, overflow: 'auto'}}>
    <FormReference formKey="firebird-registration" />
    <Alert severity="info">{operation === 'clone' ? 'Clone' : 'Move'} registration metadata only. The native database is not copied, moved, created or dropped. Close open sessions first. The resulting registration is inactive and must be verified separately.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {catalog && <>
      <Box component="p">Source: {catalog.source.display_name} — {catalog.source.database}</Box>
      <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', my: 1}}>
        <TextField size="small" select label="Destination server" value={destination} disabled={busy || attempted}
          onChange={event => {setDestination(event.target.value); setConfirmed(false);}}>
          {catalog.destinations.filter(item => operation !== 'move' || item.server_id !== catalog.source_server_id).map(item =>
            <MenuItem key={item.server_id} value={item.server_id}>{item.name} (registration {item.server_id})</MenuItem>)}
        </TextField>
        <TextField size="small" label="Registration display name" value={name} disabled={busy || attempted}
          onChange={event => {setName(event.target.value); setConfirmed(false);}} />
        <TextField size="small" select label="Credentials" value={credentials} disabled={busy || attempted}
          onChange={event => {setCredentials(event.target.value); setConfirmed(false);}}>
          <MenuItem value="source">Copy source saved credentials</MenuItem>
          <MenuItem value="destination">Use destination endpoint credentials</MenuItem>
        </TextField>
      </Box>
      <Alert severity="info">Copying source credentials preserves its saved encrypted password, user, role and character set. An unsaved password will require a prompt; process-only passwords are not saved by this operation.</Alert>
      <FormControlLabel label="I confirm this registration change" control={<Checkbox checked={confirmed} disabled={busy || attempted}
        onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || attempted || !confirmed || !destination || !name.trim()} onClick={apply}>
        {operation === 'clone' ? 'Clone registration' : 'Move registration'}
      </Button>
    </>}
    {result && <Alert severity="success">Registration {result.target.display_name} {operation === 'clone' ? 'cloned' : 'moved'}. Native connection has not been verified.</Alert>}
  </Box>;
}
FirebirdRegistration.propTypes = {post: PropTypes.func.isRequired, targetId: PropTypes.string.isRequired,
  operation: PropTypes.oneOf(['clone', 'move']), onChanged: PropTypes.func};
