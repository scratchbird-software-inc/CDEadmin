import {useEffect, useId, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, MenuItem, TextField, Table, TableBody, TableCell, TableHead, TableRow, TablePagination} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

const initial = engine => JSON.stringify({format: `scratchrobin.${engine}.test-data@1`, scope: null, seed: 1, tables: []}, null, 2);
const save = (source, filename, type) => {
  const url = URL.createObjectURL(new Blob([source], {type}));
  const link = document.createElement('a'); link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
};
export default function DuckDBTestData({post, databaseTargetId, engine = 'duckdb'}) {
  const label = engine === 'sqlite' ? 'SQLite' : 'DuckDB';
  const formId = useId();
  const editorSx = {display: 'block', boxSizing: 'border-box', width: '100%', minHeight: 150, height: 210, maxHeight: 380, overflow: 'auto', resize: 'vertical', fontFamily: 'monospace', fontSize: '0.875rem', p: 1, color: 'text.primary', bgcolor: 'background.paper', border: 1, borderColor: 'divider'};
  const [tables, setTables] = useState([]), [selected, setSelected] = useState('');
  const [count, setCount] = useState(10), [source, setSource] = useState(() => initial(engine));
  const [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [page, setPage] = useState(0);
  const columns = tables.find(table => table.resource_id === selected)?.columns || [];
  useEffect(() => {setPage(0);}, [selected]);
  const serial = useRef(0), scope = useRef(null);
  useEffect(() => {serial.current++; scope.current = null; setTables([]); setSelected(''); setSource(initial(engine)); setResult(null); setError(''); setBusy(false);
    return () => {serial.current++;};}, [databaseTargetId, engine]);
  const change = value => {setSource(value); setResult(null);};
  const run = async generate => {
    const token = ++serial.current; setBusy(true); setError(''); setResult(null);
    try {
      const response = await post({action: `${engine}_test_data`, request: {database_target_id: databaseTargetId,
        ...(generate ? {recipe: JSON.parse(source)} : {})}});
      if(token !== serial.current) return;
      if(generate) setResult(response); else {scope.current = response.scope; setTables(response.tables); setSelected(response.tables[0]?.resource_id || '');}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Recipe generation failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const add = () => {
    try {
      const recipe = JSON.parse(source), table = tables.find(item => item.resource_id === selected);
      if(!table || !Number.isInteger(Number(count)) || Number(count) < 1 || Number(count) > 1000) throw new Error('Select a table and 1–1000 rows.');
      if(recipe.scope === null && recipe.tables.length === 0) recipe.scope = scope.current;
      if(recipe.scope?.endpoint_id !== scope.current?.endpoint_id || recipe.scope?.database_target_id !== scope.current?.database_target_id) throw new Error('Recipe belongs to another endpoint or database.');
      if(recipe.tables.some(item => item.table === selected)) throw new Error('Table already appears in the recipe.');
      recipe.tables.push({table: selected, count: Number(count), columns: Object.fromEntries(table.columns.map(column => [column.name, {kind: 'default'}]))});
      change(JSON.stringify(recipe, null, 2)); setError('');
    } catch(failure) {setError(failure.message);}
  };
  const load = async event => {
    const file = event.target.files?.[0]; event.target.value = '';
    if(!file) return;
    const token = serial.current;
    try {
      if(file.size > 4 * 1024 * 1024) throw new Error('Recipe exceeds 4 MiB.');
      const text = await file.text(); JSON.parse(text);
      if(token === serial.current) {change(text); setError('');}
    } catch(failure) {if(token === serial.current) setError(failure.message);}
  };
  return <Box sx={{...compactFormSx, gridAutoRows: 'max-content', p: 1, overflow: 'auto'}}>
    <FormReference formKey={engine === 'sqlite' ? 'sqlite-test-data' : 'duckdb-test-data'} />
    <Alert severity="info">Generate and review SQL, then open the saved script in the shared Query Tool on this database. Generation executes no SQL writes. The Query Tool owns autocommit, commit and rollback.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap', my: 1}}>
      <Button disabled={busy} onClick={() => run(false)}>Load native tables</Button>
      <TextField select size="small" label="Native table" value={selected} disabled={busy || !tables.length} onChange={event => setSelected(event.target.value)} sx={{minWidth: 260}}>
        {tables.map(table => <MenuItem key={table.resource_id} value={table.resource_id}>{engine === 'sqlite' ? `${table.schema}.${table.name}` : `${table.catalog}.${table.schema}.${table.name}`}</MenuItem>)}
      </TextField>
      <TextField size="small" type="number" label="Rows" value={count} disabled={busy} onChange={event => setCount(event.target.value)} inputProps={{min: 1, max: 1000}} sx={{width: 100}} />
      <Button disabled={busy || !selected} onClick={add}>Add table</Button>
    </Box>
    {selected && <Box sx={{maxHeight: 260, overflow: 'auto', mb: 1}}>
      <Table size="small" aria-label="Native recipe columns"><TableHead><TableRow><TableCell>Column</TableCell><TableCell>Native type</TableCell><TableCell>Values</TableCell></TableRow></TableHead>
        <TableBody>{columns.slice(page * 10, (page + 1) * 10).map(column => <TableRow key={column.name}><TableCell>{column.name}</TableCell><TableCell>{column.data_type || 'Unavailable'}</TableCell><TableCell>{column.has_default ? 'Native default available' : column.nullable ? 'Nullable' : 'Explicit value needed'}</TableCell></TableRow>)}</TableBody>
      </Table><TablePagination component="div" count={columns.length} page={page} rowsPerPage={10} rowsPerPageOptions={[10]} onPageChange={(_event, value) => setPage(value)} showFirstButton showLastButton />
    </Box>}
    <Box sx={{display: 'flex', flexDirection: 'column', gap: 0.5}}>
      <Box component="label" htmlFor={formId + '-recipe'}>Test-data recipe JSON</Box>
      <Box component="textarea" id={formId + '-recipe'} value={source} onChange={event => change(event.target.value)} disabled={busy} sx={editorSx} />
    </Box>
    <Box sx={{display: 'flex', gap: 1, my: 1, flexWrap: 'wrap'}}>
      <Button disabled={busy} onClick={() => run(true)}>Generate SQL preview</Button>
      <Button component="label" disabled={busy}>Read recipe<input hidden type="file" accept=".json,application/json" aria-label={`${label} recipe file`} disabled={busy} onChange={load} /></Button>
      <Button disabled={busy} onClick={() => save(source, `${engine}-test-data-recipe.json`, 'application/json')}>Save recipe</Button>
      <Button disabled={busy || !result} onClick={() => save(result.source, `${engine}-test-data.sql`, 'text/plain')}>Save SQL script</Button>
    </Box>
    <Box component="details"><summary>Recipe sources and limits</summary>
      Use constant (value), default, sequential (start/step as exact signed 64-bit strings), random-integer (min/max as exact strings), or choice/file (values). Maximum 32 tables, 5000 requested rows, 4 MiB recipe and 1 MiB SQL file. Recipes and scripts may contain data. Native defaults, constraints and file effects apply when the shared Query Tool executes the script.
    </Box>
    {result && <><Alert severity="success">{result.rows} rows in {result.tables} tables generated; not executed.</Alert>
      <Box sx={{display: 'flex', flexDirection: 'column', gap: 0.5}}>
        <Box component="label" htmlFor={formId + '-sql'}>Generated {label} SQL</Box>
        <Box component="textarea" id={formId + '-sql'} value={result.source} readOnly sx={editorSx} />
      </Box></>}
  </Box>;
}
DuckDBTestData.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired,
  engine: PropTypes.oneOf(['duckdb', 'sqlite'])};
