import {useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdDocker({onRegister, bridge=window.electronUI?.firebirdDocker}) {
  const [config, setConfig] = useState({context: 'default', container: 'firebird-server', storage: 'volume', volume: 'firebird-server-data',
    bind: '127.0.0.1', port: 3050, eventPort: 3051, database: 'database.fdb', version: '5.0.4'});
  const [review, setReview] = useState(null), [password, setPassword] = useState('');
  const [confirmed, setConfirmed] = useState(false), [attempted, setAttempted] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [receiptId, setReceiptId] = useState(''), [host, setHost] = useState('');
  const [contexts, setContexts] = useState([]);
  const change = (key, value) => {setConfig({...config, [key]: value}); setReview(null); setConfirmed(false);};
  const readContexts = async () => {
    setBusy(true); setError('');
    try {
      const result = await bridge.contexts();
      if (result.contexts) {
        setContexts(result.contexts);
        change('context', (result.contexts.find(item => item.current) || result.contexts[0]).name);
      }
    } catch (failure) {setError(failure.message || 'Docker context inventory is unavailable.');}
    finally {setBusy(false);}
  };
  const prepare = async () => {
    setBusy(true); setError(''); setReview(null); setConfirmed(false);
    try {const value = await bridge.prepare(config); setReview(value); setReceiptId(value.review_id || '');}
    catch (failure) {setError(failure.message || 'Docker preparation failed.');}
    finally {setBusy(false);}
  };
  const apply = async () => {
    const secret = password; setPassword(''); setAttempted(true); setBusy(true); setError('');
    try {setReview(await bridge.apply({review_id: review.review_id, password: secret, confirmed}));}
    catch {setError('The provisioning response was not received. Open the saved receipt and inspect the named Docker resources. Do not repeat creation.');}
    finally {setBusy(false);}
  };
  const receipt = async () => {
    setBusy(true); setError(''); setAttempted(true); setConfirmed(false); setPassword('');
    try {setReview(await bridge.receipt(receiptId));}
    catch {setError('The local receipt is unavailable. Inspect the named resources in the selected Docker context.');}
    finally {setBusy(false);}
  };
  return <Box sx={{p: 1, overflow: 'auto'}}>
    <FormReference formKey="firebird-docker" />
    <Alert severity="info">Execution host: the Linux desktop Docker CLI and the explicitly selected Docker context. Preparation selects the CLI, inspects that daemon and may pull the official image; it does not create containers or storage. Confirm the resolved daemon and image before creation.</Alert>
    {!bridge?.available && <Alert severity="warning">Docker provisioning requires the Linux desktop application. The web server does not start Docker for browser clients.</Alert>}
    <Button disabled={!bridge?.contexts || busy || attempted} onClick={readContexts}>Read Docker contexts</Button>
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', my: 1}}>
      {['context', 'container', 'database'].map(key => <TextField key={key} size="small" label={{context: 'Docker context', container: 'Container name', database: 'Initial database filename'}[key]}
        select={key === 'context' && contexts.length > 0} value={config[key]} disabled={busy || attempted} onChange={event => change(key, event.target.value)}>
        {key === 'context' && contexts.map(item => <MenuItem key={item.name} value={item.name}>{item.name} — {item.endpoint}</MenuItem>)}
      </TextField>)}
      <TextField select size="small" label="Firebird version" value={config.version} disabled={busy || attempted} onChange={event => change('version', event.target.value)}><MenuItem value="5.0.4">5.0.4</MenuItem></TextField>
      <TextField select size="small" label="Persistent storage" value={config.storage} disabled={busy || attempted} onChange={event => change('storage', event.target.value)}>
        <MenuItem value="volume">New named Docker volume</MenuItem><MenuItem value="directory">Empty local directory</MenuItem>
      </TextField>
      {config.storage === 'volume' && <TextField size="small" label="New volume name" value={config.volume} disabled={busy || attempted} onChange={event => change('volume', event.target.value)} />}
      <TextField select size="small" label="Published IPv4 bind" value={config.bind} disabled={busy || attempted} onChange={event => change('bind', event.target.value)}>
        <MenuItem value="127.0.0.1">127.0.0.1 (daemon host loopback)</MenuItem><MenuItem value="0.0.0.0">0.0.0.0 (daemon host interfaces)</MenuItem>
      </TextField>
      <TextField size="small" label="Published SQL port" type="number" value={config.port} disabled={busy || attempted} onChange={event => change('port', Number(event.target.value))} />
      <TextField size="small" label="Published event port (blank disables)" type="number" value={config.eventPort ?? ''} disabled={busy || attempted} onChange={event => change('eventPort', event.target.value === '' ? null : Number(event.target.value))} />
    </Box>
    {config.storage === 'directory' && <Alert severity="info">Choose an empty directory through the desktop picker. Only Unix-socket contexts admit directory mounts. Existing files and permissions are unchanged; directory permissions may prevent Firebird startup.</Alert>}
    <Button disabled={!bridge?.available || busy || attempted} onClick={prepare}>Prepare Docker deployment</Button>
    <TextField size="small" label="Docker receipt ID" value={receiptId} disabled={busy} onChange={event => setReceiptId(event.target.value)} />
    <Button disabled={!bridge?.available || busy || !receiptId} onClick={receipt}>Open Docker receipt</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {review && <Box component="pre" sx={{maxHeight: 300, overflow: 'auto'}}>{JSON.stringify(review, null, 2)}</Box>}
    {review?.state === 'prepared' && !attempted && <>
      <Alert severity="warning">The bootstrap SYSDBA password is retained in Docker container configuration and is visible to Docker administrators. This image reapplies it on restart. Changing the native password later does not change that bootstrap value. ScratchRobin does not save it in its receipts.</Alert>
      <TextField size="small" type="password" label="Bootstrap SYSDBA password" value={password} disabled={busy} autoComplete="new-password" onChange={event => setPassword(event.target.value)} />
      <FormControlLabel label="I approve creating these resources on the reviewed Docker daemon" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || !password} onClick={apply}>Create reviewed Firebird container</Button>
    </>}
    {attempted && <Alert severity="info">A consumed review cannot be replayed. Partial or unconfirmed resources are retained for inspection. Container running does not prove Firebird authentication or database readiness.</Alert>}
    {review?.state === 'container_running' && <>
      <TextField size="small" label="Database host reachable by ScratchRobin" value={host} onChange={event => setHost(event.target.value)} />
      <Button disabled={!host.trim() || !onRegister} onClick={() => onRegister({profile_id: 'firebird-native', registration_intent: 'register_existing',
        host: host.trim(), port: review.configuration.port, database: '/var/lib/firebird/data/' + review.configuration.database,
        name: review.configuration.container, username: 'SYSDBA'})}>Open native registration form</Button>
    </>}
  </Box>;
}
FirebirdDocker.propTypes = {onRegister: PropTypes.func, bridge: PropTypes.object};
