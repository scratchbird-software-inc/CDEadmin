import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TablePagination, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function DuckDBServerCatalog({post}) {
  const [inventory, setInventory] = useState(null), [result, setResult] = useState(null);
  const [selected, setSelected] = useState([]), [includeSystem, setIncludeSystem] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [page, setPage] = useState(0);
  const [documentId, setDocumentId] = useState('endpoint'), [view, setView] = useState('inventory_1');
  const [display, setDisplay] = useState('inventory');
  const serial = useRef(0);
  useEffect(() => () => {serial.current++;}, [post]);
  const run = async capture => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const response = await post({action: 'duckdb_catalog_export', request: capture ? {
        database_target_ids: selected, include_system: includeSystem} : {}});
      if(token !== serial.current) return;
      if(capture) {setResult(response); setDocumentId('endpoint'); setDisplay('inventory'); setView(response.server.document.snapshot.view);}
      else {setInventory(response); setSelected([]); setResult(null); setPage(0);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'DuckDB endpoint capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const documents = result ? [{id: 'endpoint', name: 'Registered files', document: result.server.document},
    ...result.files.filter(item => item.available).map(item => ({id: item.database_target_id,
      name: item.display_name, document: item.document}))] : [];
  const selectedDocument = documents.find(item => item.id === documentId)?.document;
  const shown = display === 'relations' ? selectedDocument?.diagram : selectedDocument;
  const download = single => {
    const body = JSON.stringify(single ? shown.snapshot : result);
    const url = URL.createObjectURL(new Blob([body], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url;
    link.download = single ? 'duckdb-catalog.ddn-workspace.json' : 'duckdb-registered-files-ddn-bundle.json';
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey="duckdb-server-catalog-ddn" />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">Each registered file is captured on its own DuckDB connection. The documents are independent observations, not an atomic endpoint snapshot or a multi-file migration.</Alert>
    <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap'}}>
      <Button disabled={busy} onClick={() => run(false)}>Load registered files</Button>
      <FormControlLabel label="Include system objects" control={<Checkbox checked={includeSystem} disabled={busy}
        onChange={event => setIncludeSystem(event.target.checked)} />} />
      <Button disabled={busy || !selected.length} onClick={() => run(true)}>Capture selected files ({selected.length}/32)</Button>
      <Button disabled={busy || !result} onClick={() => download(false)}>Download DDN bundle</Button>
    </Box>
    {inventory && <>
      <Box sx={{display: 'flex', gap: 1, my: 1}}>
        <Button disabled={busy || !inventory.files.length || inventory.files.length > 32}
          onClick={() => setSelected(inventory.files.map(item => item.target_id))}>Select all registered files</Button>
        <Button disabled={busy || !selected.length} onClick={() => setSelected([])}>Clear selection</Button>
      </Box>
      <Table size="small" aria-label="DuckDB registered file selection"><TableHead><TableRow>
        <TableCell>Select</TableCell><TableCell>Registered file</TableCell><TableCell>Active</TableCell>
      </TableRow></TableHead><TableBody>{inventory.files.slice(page * 25, page * 25 + 25).map(item =>
        <TableRow key={item.target_id}><TableCell><Checkbox inputProps={{'aria-label': `Select DuckDB file ${item.display_name}`}}
          checked={selected.includes(item.target_id)} disabled={busy || (!selected.includes(item.target_id) && selected.length >= 32)}
          onChange={event => setSelected(current => event.target.checked ? [...current, item.target_id] :
            current.filter(identity => identity !== item.target_id))} /></TableCell>
        <TableCell>{item.display_name}</TableCell><TableCell>{item.active ? 'Yes' : 'No'}</TableCell></TableRow>)}</TableBody></Table>
      <TablePagination component="div" count={inventory.files.length} page={page} rowsPerPage={25}
        rowsPerPageOptions={[25]} onPageChange={(_event, value) => setPage(value)} showFirstButton showLastButton />
    </>}
    {result && <>
      <Alert severity={result.all_selected_captured ? 'info' : 'warning'}>{result.all_selected_captured ?
        'All selected files were captured; inspect each document’s coverage.' :
        'Some selected files could not be captured; no substitute file was used.'}</Alert>
      {result.files.filter(item => !item.available).map(item =>
        <Alert key={item.database_target_id} severity="warning">{item.display_name}: {item.reason}</Alert>)}
      <Box sx={{display: 'flex', gap: 1, my: 1, alignItems: 'center', flexWrap: 'wrap'}}>
        <TextField select size="small" label="Captured catalog" value={documentId} onChange={event => {
          const next = documents.find(item => item.id === event.target.value);
          setDocumentId(next.id); setDisplay('inventory'); setView(next.document.snapshot.view);
        }}>{documents.map(item => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}</TextField>
        {selectedDocument?.diagram?.snapshot && <TextField select size="small" label="Display" value={display}
          onChange={event => {const next = event.target.value; setDisplay(next);
            setView((next === 'relations' ? selectedDocument.diagram : selectedDocument).snapshot.view);}}>
          <MenuItem value="inventory">Catalog inventory</MenuItem><MenuItem value="relations">Relational diagram</MenuItem>
        </TextField>}
        <Button onClick={() => download(true)}>Download selected DDN</Button>
        <TextField select size="small" label="Catalog view" value={view}
          onChange={event => setView(event.target.value)}>{shown?.views?.map(item =>
            <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}</TextField>
      </Box>
      {shown?.snapshot && <Box sx={{height: 500, minHeight: 250, overflow: 'auto'}}>
        <DDNViewerSurface presentation snapshot={{...shown.snapshot,
          entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry, view}} />
      </Box>}
    </>}
  </Box>;
}
DuckDBServerCatalog.propTypes = {post: PropTypes.func.isRequired};
