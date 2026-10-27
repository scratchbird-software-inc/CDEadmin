import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TablePagination, TableRow, TextField} from '@mui/material';
import {DDNViewerSurface} from '../integrations/ddn';

export default function SessionCatalog({post, ensureSession, databaseTargetId, disabled=false, engine='postgresql'}) {
  const [catalog, setCatalog] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('');
  const [includeSystem, setIncludeSystem] = useState(false), [filter, setFilter] = useState('');
  const [page, setPage] = useState(0), [selected, setSelected] = useState(''), [view, setView] = useState('');
  const epoch = useRef({values: [], token: 0, active: true});
  const values = [post, ensureSession, databaseTargetId, disabled, engine];
  if (values.some((value, index) => value !== epoch.current.values[index])) {
    epoch.current = {values, token: epoch.current.token + 1, active: epoch.current.active};
  }
  useEffect(() => {
    setCatalog(null); setBusy(false); setError(''); setPage(0); setSelected(''); setView('');
  }, [post, ensureSession, databaseTargetId, disabled, engine]);
  useEffect(() => {
    epoch.current.active = true;
    return () => {epoch.current.active = false; epoch.current.token++;};
  }, []);
  const refresh = async () => {
    const token = ++epoch.current.token;
    const current = () => epoch.current.active && token === epoch.current.token;
    setBusy(true); setError('');
    try {
      const session = await ensureSession();
      if (!current()) return;
      const response = await post({action: 'source_catalog', session_id: session,
        database_target_id: databaseTargetId, include_system: includeSystem});
      if (!current()) return;
      setCatalog(response); setPage(0); setSelected(''); setView('');
    } catch (failure) {if (current()) setError(failure.message || 'Session catalog is unavailable');}
    finally {if (current()) setBusy(false);}
  };
  const objects = (catalog?.resources || []).filter(item => !filter || item.display_path.join('.').toLowerCase().includes(filter.toLowerCase()));
  const inspected = catalog?.resources.find(item => item.resource_id === selected);
  const denied = catalog?.observations?.filter(item => !item.available) || [];
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(catalog.document.snapshot)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = engine+'-session-catalog.ddn-workspace.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box component="details" sx={{my: 1}}><summary>Session catalog</summary>
    <Alert severity="info">Inspect this editor session, including its temporary objects and pending catalog changes. The observation preserves pending work and cannot be applied as an independent database migration. Refresh after changing objects or privileges.</Alert>
    <Button disabled={disabled || busy} onClick={refresh}>Refresh session catalog</Button>
    <FormControlLabel label="Include system objects in session catalog" control={<Checkbox checked={includeSystem}
      disabled={disabled || busy} onChange={event => setIncludeSystem(event.target.checked)} />} />
    {error && <Alert severity="error">{error}</Alert>}
    {catalog && <>
      {denied.length > 0 && <Alert severity="warning">Unavailable sections: {denied.map(item => item.section).join(', ')}</Alert>}
      {catalog.export_warning && <Alert severity="warning">{catalog.export_warning}</Alert>}
      {catalog.warnings?.length>0 && <Box component="details"><summary>Native catalog coverage</summary><ul>
        {catalog.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></Box>}
      <TextField label="Filter session objects" size="small" value={filter} onChange={event => {setFilter(event.target.value); setPage(0);}} />
      <Table size="small" aria-label={(engine==='postgresql' ? 'PostgreSQL' : engine==='duckdb' ? 'DuckDB' : 'SQLite')+' session objects'}><TableHead><TableRow>
        {['Object', 'Kind', 'Scope', 'Properties'].map(label => <TableCell key={label}>{label}</TableCell>)}
      </TableRow></TableHead><TableBody>{objects.slice(page * 25, page * 25 + 25).map(item => <TableRow key={item.resource_id}>
        <TableCell>{item.display_path.join(' / ')}</TableCell><TableCell>{item.resource_kind}</TableCell>
        <TableCell>{{temporary:'Temporary',connection:'Connection',runtime:'Runtime','attached-database':'Attached database',database:'Database'}[item.native.session_scope_kind] || (item.native.session_local ? 'Temporary' : 'Database')}</TableCell><TableCell>
          <Button onClick={() => setSelected(item.resource_id)} aria-label={`Inspect session object ${item.display_name}`}>Inspect</Button>
        </TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={objects.length} page={page} rowsPerPage={25}
        rowsPerPageOptions={[25]} onPageChange={(_event, value) => setPage(value)} showFirstButton showLastButton />
      {inspected && <Box component="pre" aria-label={(engine==='postgresql' ? 'PostgreSQL' : engine==='duckdb' ? 'DuckDB' : 'SQLite')+' session object properties'}
        sx={{overflow: 'auto', maxHeight: 320, whiteSpace: 'pre-wrap'}}>{JSON.stringify(inspected.native, null, 2)}</Box>}
      <Button disabled={disabled || busy || !catalog.document} onClick={download}>Download session DDN</Button>
      {catalog.document && <>
        <TextField select size="small" label="Session catalog view" value={view} onChange={event => setView(event.target.value)}>
          <MenuItem value="">Native inventory</MenuItem>
          {catalog.document.views.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
        </TextField>
        {view && <Box sx={{height: 320}}><DDNViewerSurface snapshot={{...catalog.document.snapshot, view,
          entry: catalog.document.views.find(item => item.id === view)?.entry || catalog.document.snapshot.entry}} /></Box>}
      </>}
    </>}
  </Box>;
}
SessionCatalog.propTypes = {post: PropTypes.func.isRequired, ensureSession: PropTypes.func.isRequired,
  databaseTargetId: PropTypes.string, disabled: PropTypes.bool, engine:PropTypes.oneOf(['postgresql','duckdb','sqlite'])};
