import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdIsql({post, databaseTargetId, bridge=window.electronUI?.firebirdIsql}) {
  const [connection, setConnection] = useState(null), [password, setPassword] = useState('');
  const [error, setError] = useState(''), [busy, setBusy] = useState(false), [receipt, setReceipt] = useState(null);
  const generation = useRef(0);
  useEffect(() => {
    const serial = ++generation.current;
    setConnection(null); setPassword(''); setError(''); setReceipt(null); setBusy(false);
    if (databaseTargetId) post({action: 'firebird_isql_context', request: {database_target_id: databaseTargetId}})
      .then(value => {if (generation.current === serial) setConnection(value);})
      .catch(reason => {if (generation.current === serial) setError(reason?.response?.data?.errormsg || reason.message);});
    return () => {generation.current++;};
  }, [post, databaseTargetId]);
  const launch = async () => {
    const serial = generation.current;
    setBusy(true); setError(''); setReceipt(null);
    const credential = password; setPassword('');
    try {
      const value = await bridge.launch({connection, password: credential});
      if (serial === generation.current) setReceipt(value);
    } catch (reason) {if (serial === generation.current) setError(reason.message);}
    finally {if (serial === generation.current) setBusy(false);}
  };
  return <Box sx={{p: 2, overflow: 'auto'}}>
    <FormReference formKey="firebird-external-isql" />
    <Alert severity="info">Execution host: this Linux desktop. ISQL opens a separate terminal and owns its own native connection and transactions. Existing editor sessions are unaffected.</Alert>
    {!bridge?.available && <Alert severity="warning">Open this database in the Linux desktop application to launch ISQL. The web server cannot launch a local terminal for your browser.</Alert>}
    {!databaseTargetId && <Alert severity="warning">Select a registered Firebird database.</Alert>}
    {error && <Alert severity="error">{error}</Alert>}
    {connection && <>
      <TextField fullWidth label="Native TCP database address" value={connection.dsn} InputProps={{readOnly: true}} />
      <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap'}}>
        {['user', 'role', 'charset'].map(key => <TextField key={key} label={{user: 'ISQL username', role: 'ISQL role', charset: 'ISQL character set'}[key]}
          value={connection[key]} disabled={busy} onChange={event => setConnection({...connection, [key]: event.target.value})} />)}
        <TextField select label="ISQL client dialect" value={connection.sql_dialect} disabled={busy}
          onChange={event => setConnection({...connection, sql_dialect: Number(event.target.value)})}>
          {[1, 3].map(value => <MenuItem key={value} value={value}>{value}</MenuItem>)}
        </TextField>
        <TextField type="password" label="ISQL password" value={password} autoComplete="new-password" disabled={busy}
          onChange={event => setPassword(event.target.value)} />
      </Box>
      <Alert severity="info">Choose your local Firebird 5 ISQL executable and Konsole or xterm in the desktop file dialogs. The password is used only for this launch and is not saved or passed in command arguments.</Alert>
      <Button disabled={busy || !bridge?.available || !password || !connection.user || !connection.charset} onClick={launch}>Launch local ISQL</Button>
    </>}
    {receipt && <Alert severity="info">{receipt.state === 'cancelled_before_launch' ? 'Cancelled before starting ISQL.' :
      'Local terminal process started. Check the terminal for native connection status; transaction outcomes belong to ISQL.'}</Alert>}
  </Box>;
}
FirebirdIsql.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string, bridge: PropTypes.object};
