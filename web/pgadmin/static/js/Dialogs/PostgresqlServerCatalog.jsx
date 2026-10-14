import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TablePagination, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';

export default function PostgresqlServerCatalog({post}) {
  const [inventory, setInventory] = useState(null), [result, setResult] = useState(null);
  const [selected, setSelected] = useState([]), [includeSystem, setIncludeSystem] = useState(false);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [page, setPage] = useState(0);
  const [documentId, setDocumentId] = useState('server'), [view, setView] = useState('inventory_1');
  const [display, setDisplay] = useState('inventory');
  const serial = useRef(0);
  useEffect(() => () => {serial.current++;}, [post]);
  const run = async capture => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const response = await post({action: 'postgresql_server_catalog', request: capture ? {
        database_ids: selected, include_system: includeSystem} : {}});
      if(token !== serial.current) return;
      if(capture) {setResult(response); setDocumentId('server'); setDisplay('inventory'); setView(response.server.document.snapshot.view);}
      else {setInventory(response); setSelected([]); setResult(null); setPage(0);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Server capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const documents = result ? [{id: 'server', name: 'PostgreSQL server catalog', document: result.server.document},
    ...result.databases.filter(item => item.available).map(item => ({id: String(item.database_oid), name: `PostgreSQL — ${item.database_name}`, document: item.document}))] : [];
  const selectedDocument = documents.find(item => item.id === documentId)?.document;
  const shown = display === 'relations' ? selectedDocument?.diagram : selectedDocument;
  const download = (single=false) => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(single ? shown.snapshot : result)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = single ? 'postgresql-catalog.ddn-workspace.json' : 'postgresql-server-ddn-bundle.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey="postgresql-server-catalog-ddn" />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">Each selected database uses its own metadata snapshot. This bundle is not a consistent backup or an atomic server migration. Passwords and credential settings are excluded.</Alert>
    <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap'}}>
      <Button disabled={busy} onClick={() => run(false)}>Load server inventory</Button>
      <FormControlLabel label="Include system objects in DDN" control={<Checkbox checked={includeSystem} disabled={busy} onChange={event => setIncludeSystem(event.target.checked)} />} />
      <Button disabled={busy || !selected.length} onClick={() => run(true)}>Capture selected databases ({selected.length}/32)</Button>
      <Button disabled={busy || !result} onClick={() => download()}>Download server DDN bundle</Button>
    </Box>
    {inventory && <>
      <Table size="small" aria-label="PostgreSQL server database selection"><TableHead><TableRow>
        {['Select', 'Database', 'Native OID', 'Template', 'Connection'].map(label => <TableCell key={label}>{label}</TableCell>)}
      </TableRow></TableHead><TableBody>{inventory.databases.slice(page * 25, page * 25 + 25).map(item =>
        <TableRow key={item.oid}><TableCell><Checkbox inputProps={{'aria-label': `Select PostgreSQL database ${item.name}`}}
          checked={selected.includes(item.oid)} disabled={busy || !item.allows_connections || !item.connect_privilege || (!selected.includes(item.oid) && selected.length >= 32)}
          onChange={event => setSelected(current => event.target.checked ? [...current, item.oid] : current.filter(oid => oid !== item.oid))} /></TableCell>
        <TableCell>{item.name}</TableCell><TableCell>{item.oid}</TableCell><TableCell>{item.template ? 'Yes' : 'No'}</TableCell>
        <TableCell>{item.allows_connections && item.connect_privilege ? 'CONNECT admitted; attachment checked during capture' : 'Unavailable'}</TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={inventory.databases.length} page={page} rowsPerPage={25}
        rowsPerPageOptions={[25]} onPageChange={(_event, value) => setPage(value)} showFirstButton showLastButton />
    </>}
    {result && <>
      <Alert severity={result.all_selected_captured ? 'info' : 'warning'}>{result.all_selected_captured ? 'All selected databases captured; review coverage and exclusions in each document.' : 'Some selected databases were unavailable; no substitute database was used.'}</Alert>
      {result.databases.filter(item => !item.available).map(item => <Alert key={item.database_oid} severity="warning">Database OID {item.database_oid}: {item.reason}</Alert>)}
      <Box sx={{display: 'flex', gap: 1, my: 1, flexWrap: 'wrap'}}>
        <TextField select size="small" label="Captured catalog" value={documentId} onChange={event => {
          const next = documents.find(item => item.id === event.target.value); setDocumentId(next.id); setDisplay('inventory'); setView(next.document.snapshot.view);
        }}>{documents.map(item => <MenuItem key={item.id} value={item.id}>{item.name}</MenuItem>)}</TextField>
        {selectedDocument.diagram?.snapshot && <TextField select size="small" label="Display" value={display} onChange={event => {
          const next = event.target.value; setDisplay(next); setView((next === 'relations' ? selectedDocument.diagram : selectedDocument).snapshot.view);
        }}><MenuItem value="inventory">Catalog inventory</MenuItem><MenuItem value="relations">Relational diagram</MenuItem></TextField>}
        <Button onClick={() => download(true)}>Download selected DDN workspace</Button>
        <TextField select size="small" label="Catalog view" value={view} onChange={event => setView(event.target.value)}>
          {shown.views.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
        </TextField>
      </Box>
      <Box component="details"><summary>Capture coverage and exclusions</summary><ul>{(shown.provenance?.warnings || shown.warnings || []).map(item => <li key={item}>{item}</li>)}</ul></Box>
      <Box sx={{height: 500, minHeight: 250, overflow: 'auto'}}><DDNViewerSurface presentation snapshot={{...shown.snapshot,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry, view}} /></Box>
    </>}
  </Box>;
}
PostgresqlServerCatalog.propTypes = {post: PropTypes.func.isRequired};
