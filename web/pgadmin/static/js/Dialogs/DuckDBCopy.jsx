import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function DuckDBCopy({post, databaseTargetId, resourceId}) {
  const [tables, setTables] = useState([]), [selected, setSelected] = useState('');
  const [direction, setDirection] = useState('to'), [format, setFormat] = useState('PARQUET');
  const [path, setPath] = useState(''), [result, setResult] = useState(null);
  const [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const serial = useRef(0);
  useEffect(() => {serial.current++; setTables([]); setSelected(''); setResult(null); setError('');
    return () => {serial.current++;};}, [databaseTargetId, resourceId]);
  const load = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const data = await post({action: 'duckdb_test_data', request: {database_target_id: databaseTargetId}});
      if(token === serial.current) {setTables(data.tables || []); setSelected(previous =>
        (data.tables || []).some(item => item.resource_id === previous) ? previous :
          (data.tables || []).some(item => item.resource_id === resourceId) ? resourceId :
            data.tables?.[0]?.resource_id || '');}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Native tables unavailable');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const preview = async () => {
    const token = ++serial.current; setBusy(true); setError(''); setResult(null);
    try {
      const value = await post({action: 'duckdb_copy_plan', request: {
        database_target_id: databaseTargetId, resource_id: selected, direction, format, path}});
      if(token === serial.current) setResult(value);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'COPY preview failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([result.source], {type: 'text/plain'}));
    const link = document.createElement('a'); link.href = url; link.download = 'duckdb-copy.sql';
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const clear = () => setResult(null);
  return <Box sx={{...compactFormSx, gridAutoRows: 'max-content', p: 1, overflow: 'auto'}}>
    <FormReference formKey="duckdb-copy" />
    <Alert severity="info">Preview one native COPY statement for the selected registered file. Open the downloaded script on this same file in the shared Query Tool to execute it. Export creates an external file that SQL rollback may not remove.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap', my: 1}}>
      <Button disabled={busy} onClick={load}>Load native tables</Button>
      <TextField select size="small" label="Native table" value={selected} disabled={busy || !tables.length}
        onChange={event => {setSelected(event.target.value); clear();}} sx={{minWidth: 260}}>
        {tables.map(table => <MenuItem key={table.resource_id} value={table.resource_id}>{table.catalog}.{table.schema}.{table.name}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Direction" value={direction} disabled={busy}
        onChange={event => {setDirection(event.target.value); clear();}}>
        <MenuItem value="to">Export table to file</MenuItem><MenuItem value="from">Import file into table</MenuItem>
      </TextField>
      <TextField select size="small" label="Format" value={format} disabled={busy}
        onChange={event => {setFormat(event.target.value); clear();}}>
        <MenuItem value="PARQUET">PARQUET</MenuItem><MenuItem value="CSV">CSV with header</MenuItem>
      </TextField>
      <TextField size="small" label="Absolute file path" value={path} disabled={busy} sx={{minWidth: 340}}
        onChange={event => {setPath(event.target.value); clear();}} />
      <Button disabled={busy || !selected || !path} onClick={preview}>Preview native COPY</Button>
      <Button disabled={busy || !result} onClick={download}>Save SQL script</Button>
    </Box>
    {result && <><Alert severity="success">One native {result.native_format} COPY statement generated; not executed.</Alert>
      <Box component="textarea" aria-label="Generated DuckDB COPY SQL" value={result.source} readOnly
        sx={{width: '100%', boxSizing: 'border-box', minHeight: 100, resize: 'vertical', fontFamily: 'monospace', fontSize: '0.875rem'}} />
    </>}
  </Box>;
}
DuckDBCopy.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  resourceId: PropTypes.string};
