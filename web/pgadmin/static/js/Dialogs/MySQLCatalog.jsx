import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function MySQLCatalog({post, databaseTargetId}) {
  const [result, setResult] = useState(null), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [includeSystem, setIncludeSystem] = useState(false);
  const [source, setSource] = useState(''), [comparison, setComparison] = useState(null);
  const [metadata, setMetadata] = useState(null);
  const [display, setDisplay] = useState('inventory'), [view, setView] = useState('inventory_1');
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setMetadata(null); setResult(null); setSource(''); setComparison(null); setError(''); setBusy(false);
    setDisplay('inventory'); setView('inventory_1');
    return () => {serial.current++;};
  }, [post, databaseTargetId]);
  const run = async (compare=false) => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const response = await post({action: compare ? 'mysql_catalog_compare' : 'mysql_catalog_export',
        request: {database_target_id: databaseTargetId, include_system: includeSystem, ...(compare ? {source} : {})}});
      if(token !== serial.current) return;
      if(compare) setComparison(response);
      else {setSource(''); setMetadata(null); setResult(response); setComparison(null); setDisplay('inventory'); setView(response.snapshot.view);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MySQL catalog capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const generate = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setMetadata(null);
    try {
      const response = await post({action: 'mysql_sql_export', request: {database_target_id: databaseTargetId,
        source: source || JSON.stringify(result.snapshot)}});
      if(token === serial.current) setMetadata(response);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MySQL metadata generation failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const downloadSQL = () => {
    const url = URL.createObjectURL(new Blob([metadata.script], {type: 'text/plain;charset=utf-8'}));
    const link = document.createElement('a'); link.href = url; link.download = 'mysql-native-metadata.sql'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const shown = display === 'relations' ? result?.diagram : result;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(shown.snapshot)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = `mysql-${display}.ddn-workspace.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey="mysql-catalog-ddn" />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">Native MySQL metadata on a separate connection. Catalog visibility is privilege filtered and concurrent DDL is not fenced. Documentary comparison does not authorize migration or deletion.</Alert>
    <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1}}>
      <FormControlLabel label="Include system objects" control={<Checkbox checked={includeSystem} disabled={busy}
        onChange={event => setIncludeSystem(event.target.checked)} />} />
      <Button disabled={busy || !databaseTargetId} onClick={() => run()}>Capture metadata</Button>
      <Button disabled={busy || !shown?.snapshot} onClick={download}>Download DDN</Button>
      <Button component="label" disabled={busy}>Read DDN<input hidden type="file" accept=".ddn,.json" aria-label="MySQL catalog DDN file"
        onChange={async event => {
          const file = event.target.files?.[0], token = serial.current;
          event.target.value = '';
          if(!file) return;
          if(file.size > 8 * 1024 * 1024) {setError('Catalog file exceeds 8 MiB'); return;}
          try {const text = await file.text(); if(token === serial.current) {setSource(text); setMetadata(null); setComparison(null);}}
          catch {if(token === serial.current) setError('Unable to read catalog file');}
        }} /></Button>
      <Button disabled={busy || !source || !databaseTargetId} onClick={() => run(true)}>Compare with live catalog</Button>
      <Button disabled={busy || !(source || result?.snapshot) || !databaseTargetId} onClick={generate}>Generate native SQL</Button>
      <Button disabled={busy || !metadata?.script_available} onClick={downloadSQL}>Download native SQL</Button>
      <TextField select size="small" label="Display" value={display} disabled={busy || !result}
        onChange={event => {setDisplay(event.target.value); setView(event.target.value === 'relations' ? result.diagram.snapshot.view : result.snapshot.view);}}>
        <MenuItem value="inventory">Native inventory</MenuItem>
        <MenuItem value="relations" disabled={!result?.diagram?.snapshot}>Relations</MenuItem>
      </TextField>
      {shown?.views && <TextField select size="small" label="DDN view" value={view} disabled={busy} onChange={event => setView(event.target.value)}>
        {shown.views.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>}
    </Box>
    {(result?.provenance?.warnings || []).map(warning => <Alert key={warning} severity="warning">{warning}</Alert>)}
    {metadata && <Box>
      <Alert severity="info">Native SQL export only. Imported definitions have not been validated against the live server and this does not execute a migration.</Alert>
      {metadata.warnings?.map(warning => <Alert severity="warning" key={warning}>{warning}</Alert>)}
      {metadata.blockers?.map(item => <Alert severity="error" key={item.resource_id + item.reason}>{item.name}: {item.reason}</Alert>)}
      {metadata.script && <TextField label="Native MySQL metadata script" multiline minRows={6} maxRows={16}
        value={metadata.script} slotProps={{input: {readOnly: true}}} sx={{width: '100%'}} />}
      {!!metadata.prerequisites?.length && <Box sx={{height: 220, overflow: 'auto'}}>
        <PagedDataGrid readOnly gridId="mysql/native-prerequisites" aria-label="MySQL native prerequisites"
          rows={metadata.prerequisites.map((item, index) => ({...item, id: index}))} rowKeyGetter={row => row.id}
          columns={[{key: 'database', name: 'Database', width: 160}, {key: 'name', name: 'Prerequisite', minWidth: 180},
            {key: 'kind', name: 'Kind', minWidth: 160}]} />
      </Box>}
    </Box>}
    {comparison && <Box sx={{height: 280, overflow: 'auto'}}>
      <PagedDataGrid readOnly gridId="mysql/catalog-comparison" aria-label="MySQL catalog differences"
        rows={comparison.changes} rowKeyGetter={row => row.resource_id} columns={[
          {key: 'name', name: 'Native object', minWidth: 180}, {key: 'kind', name: 'Kind', width: 140},
          {key: 'status', name: 'Difference', width: 140},
          {key: 'fields', name: 'Changed native fields', minWidth: 260, renderCell: ({row}) => row.fields.join(', ')},
        ]} />
    </Box>}
    {shown?.snapshot && <Box sx={{height: 500, minHeight: 250, overflow: 'auto'}}>
      <DDNViewerSurface presentation snapshot={{...shown.snapshot, view,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry}} />
    </Box>}
  </Box>;
}
MySQLCatalog.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string};
