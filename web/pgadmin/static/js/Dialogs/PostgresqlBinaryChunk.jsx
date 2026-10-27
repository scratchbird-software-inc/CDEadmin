import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, TextField} from '@mui/material';
import gettext from 'sources/gettext';

const CHUNK = 1024 * 1024;
const encode = bytes => {
  let text = '';
  for (let at = 0; at < bytes.length; at += 8192)
    text += String.fromCharCode(...bytes.subarray(at, at + 8192));
  return btoa(text);
};

export function PostgresqlBinaryField({field, value, onChange, disabled}) {
  const [file, setFile] = useState(null), [offset, setOffset] = useState('0');
  const [busy, setBusy] = useState(false), [error, setError] = useState('');
  const generation = useRef(0), current = useRef({});
  current.current = {disabled, file, offset, onChange};
  useEffect(() => () => {generation.current++;}, []);
  useEffect(() => {generation.current++; setBusy(false);}, [disabled, value]);
  const load = async () => {
    const initial = {...current.current}, epoch = ++generation.current;
    const applicable = () => epoch === generation.current && !current.current.disabled &&
      current.current.file === initial.file && current.current.offset === initial.offset;
    setError(''); setBusy(true);
    try {
      if (!/^(0|[1-9][0-9]*)$/.test(offset) || !Number.isSafeInteger(Number(offset)) || Number(offset) > file.size)
        throw new Error(gettext('Choose a byte offset within this file.'));
      const bytes = new Uint8Array(await file.slice(Number(offset), Number(offset) + CHUNK).arrayBuffer());
      if (applicable()) initial.onChange(encode(bytes));
    } catch (failure) {if (applicable()) setError(failure.message);}
    finally {if (epoch === generation.current) setBusy(false);}
  };
  return <Box sx={{display: 'grid', gap: 1}}>
    <TextField fullWidth multiline minRows={3} maxRows={8} label={field.label}
      disabled={disabled || busy} value={value || ''} helperText={field.help}
      onChange={event => {generation.current++; setBusy(false); onChange(event.target.value);}} />
    <Button component="label" disabled={disabled || busy}>{gettext('Choose binary file')}
      <input hidden type="file" onChange={event => {
        generation.current++; setFile(event.target.files?.[0] || null); setOffset('0'); setError(''); setBusy(false);
      }} />
    </Button>
    {file && <>
      <Box>{file.name} — {file.size} {gettext('bytes')}</Box>
      <TextField label={gettext('Byte offset in file')} value={offset} disabled={disabled || busy}
        onChange={event => {generation.current++; setOffset(event.target.value); setBusy(false);}} />
      <Button disabled={disabled || busy} onClick={load}>{gettext('Load up to 1 MiB into review')}</Button>
      <Alert severity="info">{gettext('Loading fills the review only. Set the destination byte offset separately, then preview and apply the chunk.')}</Alert>
    </>}
    {error && <Alert severity="error">{error}</Alert>}
  </Box>;
}
PostgresqlBinaryField.propTypes = {field: PropTypes.object.isRequired, value: PropTypes.string,
  onChange: PropTypes.func.isRequired, disabled: PropTypes.bool};

export function PostgresqlBinaryResult({row}) {
  const [error, setError] = useState('');
  const download = async () => {
    try {
      if (typeof row.data_base64 !== 'string' || row.data_base64.length > 4 * Math.ceil(CHUNK / 3) ||
          !/^[0-9]+$/.test(String(row.oid)) || !/^[0-9]+$/.test(String(row.offset))) throw new Error(gettext('Invalid binary chunk identity.'));
      const text = atob(row.data_base64), bytes = Uint8Array.from(text, value => value.charCodeAt(0));
      if (bytes.length !== Number(row.byte_length) || bytes.length > CHUNK || encode(bytes) !== row.data_base64)
        throw new Error(gettext('Binary chunk length or encoding does not match.'));
      const hash = [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(value => value.toString(16).padStart(2, '0')).join('');
      if (hash !== row.sha256) throw new Error(gettext('Binary chunk checksum does not match.'));
      const url = URL.createObjectURL(new Blob([bytes], {type: 'application/octet-stream'}));
      const link = document.createElement('a'); link.href = url;
      link.download = `large-object-${row.oid}-offset-${row.offset}.bin`; link.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      setError('');
    } catch (failure) {setError(failure.message);}
  };
  return <Box>
    <Button onClick={download}>{gettext('Download binary chunk')} ({row.byte_length} {gettext('bytes')})</Button>
    {error && <Alert severity="error">{error}</Alert>}
  </Box>;
}
PostgresqlBinaryResult.propTypes = {row: PropTypes.object.isRequired};
