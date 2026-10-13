import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';
import FirebirdCatalogDesigner from './FirebirdCatalogDesigner';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function DuckDBCatalog({post, databaseTargetId}) {
  const [result, setResult] = useState(null), [comparison, setComparison] = useState(null);
  const [source, setSource] = useState(''), [error, setError] = useState('');
  const [baselineSource, setBaselineSource] = useState(''), [schemaPlan, setSchemaPlan] = useState(null);
  const [schemaReceipt, setSchemaReceipt] = useState(null), [confirmApply, setConfirmApply] = useState(false);
  const [busy, setBusy] = useState(false), [includeSystem, setIncludeSystem] = useState(false);
  const [display, setDisplay] = useState('inventory'), [view, setView] = useState('inventory_1');
  const [data, setData] = useState(null), [relation, setRelation] = useState('');
  const [dataMode, setDataMode] = useState('sample'), [rowLimit, setRowLimit] = useState('100');
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setResult(null); setComparison(null); setSource(''); setBaselineSource(''); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false); setData(null); setRelation(''); setError('');
    setBusy(false); setDisplay('inventory'); setView('inventory_1');
    return () => {serial.current++;};
  }, [post, databaseTargetId]);
  const capture = async (compare=false) => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const value = await post({action: compare ? 'duckdb_catalog_compare' : 'duckdb_catalog_export',
        request: {database_target_id: databaseTargetId, include_system: includeSystem,
          ...(compare ? {source} : {})}});
      if(token !== serial.current) return;
      if(compare) setComparison(value);
      else {setResult(value); setComparison(null); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false); setData(null);
        setRelation(value.objects?.find(item => ['table', 'view'].includes(item.kind))?.resource_id || '');
        setDisplay('inventory'); setView(value.snapshot.view);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'DuckDB catalog capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const captureData = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setData(null);
    try {
      const value = await post({action: 'duckdb_data_capture', request: {
        database_target_id: databaseTargetId, resource_id: relation,
        mode: dataMode, row_limit: Number(rowLimit)}});
      if(token === serial.current) {setData(value); setDisplay('data'); setView(value.snapshot.view);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'DuckDB data capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const previewSchema = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false);
    try {
      const value = await post({action: 'duckdb_schema_plan', request: {
        database_target_id: databaseTargetId, baseline: baselineSource, desired: source}});
      if(token === serial.current) setSchemaPlan(value);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'DuckDB schema preview failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const reviewSchema = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'duckdb_schema_review', request: {
        database_target_id: databaseTargetId, baseline: baselineSource, desired: source,
        execution_sha256: schemaPlan.execution_sha256}});
      if(token === serial.current) {setSchemaReceipt(value); setConfirmApply(false);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'DuckDB review failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const applySchema = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'duckdb_schema_apply', request: {
        database_target_id: databaseTargetId, review_id: schemaReceipt.review_id,
        review_digest: schemaReceipt.review_digest, confirmed: true}});
      if(token === serial.current) {setSchemaReceipt(value); setConfirmApply(false); setSchemaPlan(null);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'DuckDB application outcome is unavailable; read the receipt before any new review');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const readReceipt = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'duckdb_schema_receipt', request: {
        database_target_id: databaseTargetId, review_id: schemaReceipt.review_id}});
      if(token === serial.current) setSchemaReceipt(value);
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'DuckDB receipt is unavailable');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const shown = display === 'relations' ? result?.diagram : display === 'data' ? data : result;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(shown.snapshot)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url;
    link.download = `duckdb-${display}.ddn-workspace.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey="duckdb-catalog-ddn" />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">DuckDB metadata is captured on a separate native connection. Temporary objects and uncommitted work on other connections are outside this view. Comparison is documentary.</Alert>
    <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1}}>
      <FormControlLabel label="Include system objects" control={<Checkbox checked={includeSystem} disabled={busy}
        onChange={event => setIncludeSystem(event.target.checked)} />} />
      <Button disabled={busy || !databaseTargetId} onClick={() => capture()}>Capture metadata</Button>
      <Button disabled={busy || !shown?.snapshot} onClick={download}>Download DDN</Button>
      <Button component="label" disabled={busy}>Read DDN<input hidden disabled={busy} type="file" accept=".ddn,.json"
        aria-label="DuckDB catalog DDN file" onChange={async event => {
          const file = event.target.files?.[0]; event.target.value = '';
          if(!file) return;
          if(file.size > 8 * 1024 * 1024) {setError('Catalog file exceeds 8 MiB'); return;}
          try {setSource(await file.text()); setBaselineSource(''); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false); setComparison(null); setError('');}
          catch(failure) {setError(failure.message || 'Could not read DDN file');}
        }} /></Button>
      <Button disabled={busy || !source || !databaseTargetId} onClick={() => capture(true)}>Compare DDN with live catalog</Button>
      <Button disabled={busy || !source || !baselineSource || !databaseTargetId} onClick={previewSchema}>Preview native changes</Button>
      <TextField select size="small" label="Display" value={display} disabled={busy || !result}
        onChange={event => {setDisplay(event.target.value); setView(event.target.value === 'relations' ? result.diagram.snapshot.view : event.target.value === 'data' ? data.snapshot.view : result.snapshot.view);}}>
        <MenuItem value="inventory">Native inventory</MenuItem>
        <MenuItem value="relations" disabled={!result?.diagram?.snapshot}>Relations</MenuItem>
        <MenuItem value="data" disabled={!data?.snapshot}>Captured relation data</MenuItem>
      </TextField>
      {shown?.views && <TextField select size="small" label="DDN view" value={view} disabled={busy}
        onChange={event => setView(event.target.value)}>
        {shown.views.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>}
    </Box>
    {result && <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1}}>
      <TextField select size="small" label="Native table or view" value={relation} disabled={busy} sx={{minWidth: 220}}
        onChange={event => setRelation(event.target.value)}>
        {(result.objects || []).filter(item => ['table', 'view'].includes(item.kind)).map(item =>
          <MenuItem key={item.resource_id} value={item.resource_id}>{item.kind}: {item.path.join('.')}</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Data capture mode" value={dataMode} disabled={busy}
        onChange={event => setDataMode(event.target.value)}>
        <MenuItem value="sample">Bounded sample</MenuItem><MenuItem value="full">Full relation within budget</MenuItem>
      </TextField>
      <TextField size="small" type="number" label="Data row budget" value={rowLimit} disabled={busy} sx={{width: 150}}
        slotProps={{htmlInput: {min: 1, max: 6000, step: 1}}} onChange={event => setRowLimit(event.target.value)} />
      <Button disabled={busy || !relation || !Number.isInteger(Number(rowLimit)) || Number(rowLimit) < 1 || Number(rowLimit) > 6000}
        onClick={captureData}>Capture selected data</Button>
    </Box>}
    {display === 'data' && data?.acquisition && <Alert severity="info">Captured {data.acquisition.rows} visible rows from {data.acquisition.relation}. Mode: {data.acquisition.mode}.</Alert>}
    {display === 'data' && data?.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
    {result && <Alert severity="info">Visible objects: {result.provenance.objects}. Coverage: {result.provenance.coverage}.</Alert>}
    {result?.snapshot && <FirebirdCatalogDesigner engine="duckdb" baseline={JSON.stringify(result.snapshot)}
      post={post} databaseTargetId={databaseTargetId} disabled={busy}
      onReview={(desired, baseline) => {setSource(desired); setBaselineSource(baseline); setComparison(null); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false);}} />}
    {result?.provenance?.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
    {comparison && <Box sx={{height: 280, overflow: 'auto'}}>
      <PagedDataGrid readOnly gridId="duckdb/catalog-comparison" aria-label="DuckDB catalog differences"
        rows={comparison.changes} rowKeyGetter={row => row.resource_id} columns={[
          {key: 'name', name: 'Native object', minWidth: 180}, {key: 'kind', name: 'Kind', width: 140},
          {key: 'status', name: 'Difference', width: 140},
          {key: 'fields', name: 'Changed native fields', minWidth: 260, renderCell: ({row}) => row.fields.join(', ')},
        ]} />
    </Box>}
    {schemaPlan && <Box>
      <Alert severity={schemaPlan.blockers.length || schemaPlan.conflicts.length ? 'warning' : 'info'}>
        Native preview only; no SQL was executed. {schemaPlan.operations.length} operations, {schemaPlan.blockers.length} blockers, {schemaPlan.conflicts.length} conflicts. Missing desired objects do not authorize deletion.
      </Alert>
      <Box sx={{height: 260, overflow: 'auto'}}><PagedDataGrid readOnly gridId="duckdb/schema-preview"
        aria-label="DuckDB native schema preview" rows={[...schemaPlan.operations, ...schemaPlan.blockers, ...schemaPlan.conflicts]}
        rowKeyGetter={(row, index) => `${row.resource_id}/${row.operation || row.reason || index}`} columns={[
          {key: 'name', name: 'Native object', minWidth: 170}, {key: 'operation', name: 'Operation', width: 110},
          {key: 'source', name: 'Native SQL', minWidth: 340}, {key: 'reason', name: 'Blocker or conflict', minWidth: 260},
        ]} /></Box>
      {schemaPlan.application_supported && !schemaReceipt &&
        <Button disabled={busy} onClick={reviewSchema}>Prepare one-statement native review</Button>}
    </Box>}
    {schemaReceipt && <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap'}}>
      <Alert severity={schemaReceipt.state === 'committed' ? 'success' : schemaReceipt.state === 'unknown_outcome' ? 'warning' : 'info'}>
        Native receipt {schemaReceipt.review_id}: {schemaReceipt.state}. Rediscovery {schemaReceipt.outcome?.rediscovery_verified ? 'verified' : 'unverified'}.
      </Alert>
      {schemaReceipt.state === 'reviewed' && <FormControlLabel label="Confirm this reviewed DuckDB statement"
        control={<Checkbox checked={confirmApply} disabled={busy} onChange={event => setConfirmApply(event.target.checked)} />} />}
      {schemaReceipt.state === 'reviewed' && <Button disabled={busy || !confirmApply} onClick={applySchema}>Apply reviewed statement</Button>}
      <Button disabled={busy} onClick={readReceipt}>Read native receipt</Button>
    </Box>}
    {shown?.snapshot && <Box sx={{height: 500, minHeight: 250, overflow: 'auto'}}>
      <DDNViewerSurface presentation snapshot={{...shown.snapshot, view,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry}} />
    </Box>}
  </Box>;
}
DuckDBCatalog.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string};
