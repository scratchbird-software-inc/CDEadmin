import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FirebirdDesignStorage from './FirebirdDesignStorage';
import FirebirdERD from './FirebirdERD';
import MySQLDataImport from './MySQLDataImport';
import MariaDBSchemaChanges from './MariaDBSchemaChanges';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function MariaDBCatalog({post, databaseTargetId}) {
  const [result, setResult] = useState(null), [comparison, setComparison] = useState(null);
  const [metadata, setMetadata] = useState(null);
  const [reviewBaseline, setReviewBaseline] = useState(null);
  const [source, setSource] = useState(''), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [includeSystem, setIncludeSystem] = useState(false);
  const [display, setDisplay] = useState('inventory'), [view, setView] = useState('inventory_1');
  const [data, setData] = useState(null), [relation, setRelation] = useState('');
  const [dataMode, setDataMode] = useState('sample'), [rowLimit, setRowLimit] = useState('100');
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setReviewBaseline(null); setMetadata(null); setData(null); setRelation(''); setResult(null); setComparison(null); setSource(''); setError(''); setBusy(false);
    setDisplay('inventory'); setView('inventory_1');
    return () => {serial.current++;};
  }, [post, databaseTargetId]);
  const capture = async (compare=false) => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const value = await post({action: compare ? 'mariadb_catalog_compare' : 'mariadb_catalog_export',
        request: {database_target_id: databaseTargetId, include_system: includeSystem, ...(compare ? {source} : {})}});
      if(token !== serial.current) return;
      if(compare) setComparison(value);
      else {setMetadata(null); setData(null); setRelation(value.objects?.find(item => ['table', 'view'].includes(item.kind))?.resource_id || ''); setResult(value); setComparison(null); setDisplay('inventory'); setView(value.snapshot.view);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MariaDB capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const captureData = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setData(null);
    try {
      const value = await post({action: 'mariadb_data_capture', request: {database_target_id: databaseTargetId,
        resource_id: relation, expected_server_uid: result.server_uid, mode: dataMode, row_limit: Number(rowLimit)}});
      if(token === serial.current) {setData(value); setDisplay('data'); setView(value.snapshot.view);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MariaDB data capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const generateMetadata = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setMetadata(null);
    try {
      const value = await post({action: 'mariadb_native_metadata', request: {
        database_target_id: databaseTargetId, source: source || JSON.stringify(result.snapshot)}});
      if(token === serial.current) setMetadata(value);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Native metadata generation failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const downloadMetadata = () => {
    const encoded = metadata.encoded_script?.data_base64;
    const content = encoded ? Uint8Array.from(atob(encoded), char => char.charCodeAt(0)) : metadata.script;
    const url = URL.createObjectURL(new Blob([content], {type: 'application/octet-stream'}));
    const link = document.createElement('a'); link.href = url; link.download = 'mariadb-native-metadata.sql'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const shown = display === 'relations' ? result?.diagram : display === 'data' ? data : result;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(shown.snapshot)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url;
    link.download = `mariadb-${display}.ddn-workspace.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey="mariadb-catalog-ddn" />
    <MySQLDataImport engine="mariadb" post={post} databaseTargetId={databaseTargetId} />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">Native MariaDB metadata uses a separate connection. Visibility is privilege filtered and concurrent DDL is not fenced. Comparison is documentary and does not authorize changes.</Alert>
    <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1}}>
      <FormControlLabel label="Include system objects" control={<Checkbox checked={includeSystem} disabled={busy}
        onChange={event => setIncludeSystem(event.target.checked)} />} />
      <Button disabled={busy || !databaseTargetId} onClick={() => capture()}>Capture metadata</Button>
      <Button disabled={busy || !shown?.snapshot} onClick={download}>Download DDN</Button>
      <Button component="label" disabled={busy}>Read DDN<input hidden disabled={busy} type="file" accept=".ddn,.json" aria-label="MariaDB catalog DDN file"
        onChange={async event => {
          const file = event.target.files?.[0], token = ++serial.current; event.target.value = '';
          if(!file) return;
          if(file.size > 8 * 1024 * 1024) {setError('Catalog file exceeds 8 MiB'); return;}
          try {const text = await file.text(); if(token === serial.current) {setSource(text); setReviewBaseline(null); setMetadata(null); setComparison(null); setError('');}}
          catch {if(token === serial.current) setError('Unable to read catalog file');}
        }} /></Button>
      <Button disabled={busy || !source || !databaseTargetId} onClick={() => capture(true)}>Compare with live catalog</Button>
      <Button disabled={busy || (!source && !result?.snapshot) || !databaseTargetId} onClick={generateMetadata}>Generate native SQL</Button>
      <Button disabled={busy || !metadata?.script_available} onClick={downloadMetadata}>Download native SQL</Button>
      <TextField select size="small" label="Display" value={display} disabled={busy || !result}
        onChange={event => {setDisplay(event.target.value); setView(event.target.value === 'relations' ? result.diagram.snapshot.view : event.target.value === 'data' ? data.snapshot.view : result.snapshot.view);}}>
        <MenuItem value="inventory">Native inventory</MenuItem>
        <MenuItem value="relations" disabled={!result?.diagram?.snapshot}>Relations</MenuItem>
        <MenuItem value="data" disabled={!data?.snapshot}>Captured relation data</MenuItem>
      </TextField>
      {shown?.views && <TextField select size="small" label="DDN view" value={view} disabled={busy} onChange={event => setView(event.target.value)}>
        {shown.views.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>}
    </Box>
    {result && <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center'}}>
      <TextField select size="small" label="Native table or view" value={relation} disabled={busy} sx={{minWidth: 220}}
        onChange={event => setRelation(event.target.value)}>
        {(result.objects || []).filter(item => ['table', 'view'].includes(item.kind)).map(item =>
          <MenuItem key={item.resource_id} value={item.resource_id}>{item.kind}: {item.name}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Data capture mode" value={dataMode} disabled={busy}
        onChange={event => setDataMode(event.target.value)}>
        <MenuItem value="sample">Bounded sample</MenuItem><MenuItem value="full">Full current relation within budget</MenuItem>
      </TextField>
      <TextField size="small" type="number" label="Data row budget" value={rowLimit} disabled={busy} sx={{width: 150}}
        slotProps={{htmlInput: {min: 1, max: 6000, step: 1}}} onChange={event => setRowLimit(event.target.value)} />
      <Button disabled={busy || !relation || !result.server_uid || !Number.isInteger(Number(rowLimit)) || Number(rowLimit) < 1 || Number(rowLimit) > 6000}
        onClick={captureData}>Capture selected data</Button>
    </Box>}
    {display === 'data' && data?.acquisition && <Alert severity="info">Captured {data.acquisition.rows} current visible rows from {data.acquisition.relation}. Mode: {data.acquisition.mode}. Server UID: {data.acquisition.server_uid}.</Alert>}
    {display === 'data' && data?.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
    {result && <Alert severity="info">Server UID: {result.server_uid}. Coverage: {result.provenance.coverage}. Objects: {result.provenance.objects}.</Alert>}
    {result?.provenance?.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
    {result?.snapshot && <FirebirdDesignStorage engine="mariadb" post={post} databaseTargetId={databaseTargetId} kind="catalog" disabled={busy}
      capture={() => ({snapshot: source ? JSON.parse(source) : result.snapshot, baseline: reviewBaseline ? JSON.parse(reviewBaseline) : result.snapshot})}
      onLoad={value => {setReviewBaseline(JSON.stringify(value.baseline || result.snapshot)); setSource(JSON.stringify(value.snapshot)); setMetadata(null); setComparison(null);}} />}
    {(result?.snapshot || source) && <Box sx={{display: 'flex', gap: 1, alignItems: 'center'}}>
      <Box component="small">Native SQL source: {source ? 'imported or saved DDN' : 'latest native capture'}.</Box>
      <Button disabled={busy || !source} onClick={() => {setSource(''); setReviewBaseline(null); setMetadata(null); setComparison(null);}}>Use latest native capture</Button>
    </Box>}
    {metadata && <Box>
      <Alert severity="info">Native SQL export only. Imported definitions do not authorize execution. Statements: {metadata.statements.length}.</Alert>
      {metadata.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {metadata.blockers?.map((item, index) => <Alert key={index} severity="error">{item.name}: {item.reason}</Alert>)}
      {!!metadata.prerequisites?.length && <Alert severity="warning">Review {metadata.prerequisites.length} external or unresolved prerequisites before executing exported SQL.</Alert>}
      <TextField fullWidth multiline minRows={5} maxRows={14} label="Native SQL preview" value={metadata.script_preview || metadata.script || ''}
        slotProps={{input: {readOnly: true}}} />
    </Box>}
    {result?.snapshot && <MariaDBSchemaChanges post={post} databaseTargetId={databaseTargetId}
      baseline={reviewBaseline || JSON.stringify(result.snapshot)} source={source} />}
    {comparison && <Box sx={{height: 280, overflow: 'auto'}}>
      <PagedDataGrid readOnly gridId="mariadb/catalog-comparison" aria-label="MariaDB catalog differences"
        rows={comparison.changes} rowKeyGetter={row => row.resource_id} columns={[
          {key: 'name', name: 'Native object', minWidth: 180}, {key: 'kind', name: 'Kind', width: 140},
          {key: 'status', name: 'Difference', width: 140},
          {key: 'fields', name: 'Changed native fields', minWidth: 260, renderCell: ({row}) => row.fields.join(', ')},
        ]} />
    </Box>}
    {display === 'relations' && result?.diagram?.snapshot && <FirebirdERD engine="mariadb" diagram={result.diagram}
      post={post} databaseTargetId={databaseTargetId} generation={result.generation} onReviewBusyChange={setBusy}
      onReview={value => {setReviewBaseline(value.baseline); setSource(value.desired); setMetadata(null); setComparison(null); setDisplay('inventory'); setView(result.snapshot.view);}} />}
    {shown?.snapshot && display !== 'relations' && <Box sx={{height: 500, minHeight: 250, overflow: 'auto'}}>
      <DDNViewerSurface presentation snapshot={{...shown.snapshot, view,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry}} />
    </Box>}
  </Box>;
}
MariaDBCatalog.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string};
