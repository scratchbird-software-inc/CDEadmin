import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function DuckDBAttachment({post, databaseTargetId}) {
  const [action, setAction] = useState('attach'), [alias, setAlias] = useState('');
  const [path, setPath] = useState(''), [readOnly, setReadOnly] = useState(true);
  const [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const serial = useRef(0);
  useEffect(() => {serial.current++; setAlias(''); setPath(''); setResult(null); setError('');
    return () => {serial.current++;};}, [databaseTargetId]);
  const change = setter => event => {setter(event.target.value); setResult(null);};
  const preview = async () => {
    const token = ++serial.current; setBusy(true); setError(''); setResult(null);
    try {
      const value = await post({action: 'duckdb_attachment_plan', request: {
        database_target_id: databaseTargetId, action, alias,
        ...(action === 'attach' ? {path, read_only: readOnly} : {})}});
      if(token === serial.current) setResult(value);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Attachment preview failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([result.source], {type: 'text/plain'}));
    const link = document.createElement('a'); link.href = url; link.download = `duckdb-${action}.sql`;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, gridAutoRows: 'max-content', p: 1, overflow: 'auto'}}>
    <FormReference formKey="duckdb-attachment" />
    <Alert severity="info">ATTACH and DETACH belong to one DuckDB session. This form previews native SQL only. Open the saved script in the shared Query Tool on the specific retained connection whose attachments you intend to change.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 1, my: 1}}>
      <TextField select size="small" label="Action" value={action} disabled={busy}
        onChange={change(setAction)}><MenuItem value="attach">Attach file</MenuItem><MenuItem value="detach">Detach alias</MenuItem></TextField>
      <TextField size="small" label="Native catalog alias" value={alias} disabled={busy}
        onChange={change(setAlias)} sx={{minWidth: 210}} />
      {action === 'attach' && <><TextField size="small" label="Absolute DuckDB file path" value={path} disabled={busy}
        onChange={change(setPath)} sx={{minWidth: 350}} />
        <FormControlLabel label="Read only" control={<Checkbox checked={readOnly} disabled={busy}
          onChange={event => {setReadOnly(event.target.checked); setResult(null);}} />} /></>}
      <Button disabled={busy || !alias || (action === 'attach' && !path)} onClick={preview}>Preview native attachment</Button>
      <Button disabled={busy || !result} onClick={download}>Save SQL script</Button>
    </Box>
    {result && <><Alert severity="success">One native {result.action.toUpperCase()} statement generated; not executed.</Alert>
      <Box component="textarea" aria-label="Generated DuckDB attachment SQL" value={result.source} readOnly
        sx={{width: '100%', boxSizing: 'border-box', minHeight: 90, resize: 'vertical', fontFamily: 'monospace', fontSize: '0.875rem'}} />
    </>}
  </Box>;
}
DuckDBAttachment.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired};
