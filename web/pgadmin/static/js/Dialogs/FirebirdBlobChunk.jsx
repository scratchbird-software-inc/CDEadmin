/* global BigInt */
import {useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, MenuItem, TextField} from '@mui/material';
import {blobBytes} from './firebirdBlobValue';

export function renderBlobChunk(chunk, mode) {
  if (mode === 'base64') return chunk.data;
  const bytes = blobBytes(chunk.data, 'binary');
  if (mode === 'utf8') return new TextDecoder('utf-8', {fatal: true, ignoreBOM: true}).decode(bytes);
  const rows = [];
  for (let start = 0; start < bytes.length; start += 16) {
    const slice = bytes.subarray(start, start + 16);
    const hex = Array.from(slice, value => value.toString(16).padStart(2, '0')).join(' ');
    const ascii = Array.from(slice, value => value >= 32 && value <= 126 ? String.fromCharCode(value) : '.').join('');
    rows.push(`${(BigInt(chunk.offset) + BigInt(start)).toString(16).padStart(8, '0')}  ${hex.padEnd(47)}  ${ascii}`);
  }
  return rows.join('\n');
}
export default function FirebirdBlobChunk({chunk}) {
  const [mode, setMode] = useState('base64');
  let text, error;
  try {text = renderBlobChunk(chunk, mode);} catch {error = 'This chunk is not independently valid UTF-8 or Base64. A UTF-8 character may cross a chunk boundary. Inspect bytes or download the complete value; no replacement characters are substituted.';}
  return <Box>
    <div>BLOB bytes: {chunk.offset}–{chunk.next_offset}. Only this chunk is displayed.</div>
    <TextField select label="BLOB chunk representation" value={mode} onChange={event => setMode(event.target.value)}>
      <MenuItem value="base64">Base64</MenuItem><MenuItem value="hex">Hexadecimal / ASCII</MenuItem><MenuItem value="utf8">UTF-8 (strict chunk decode)</MenuItem>
    </TextField>
    {error ? <Alert severity="warning">{error}</Alert> : <Box component="pre" sx={{maxHeight: 240, overflow: 'auto', whiteSpace: mode === 'hex' ? 'pre' : 'pre-wrap', overflowWrap: 'anywhere'}}>{text}</Box>}
  </Box>;
}
FirebirdBlobChunk.propTypes = {chunk: PropTypes.object.isRequired};
