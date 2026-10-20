import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import NativeDataImport from './NativeDataImport';
import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';
import FirebirdCatalogDesigner from './FirebirdCatalogDesigner';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function SQLiteCatalog({post, databaseTargetId, resourceId}) {
  const [result, setResult] = useState(null), [comparison, setComparison] = useState(null);
  const [source, setSource] = useState(''), [error, setError] = useState('');
  const [baselineSource, setBaselineSource] = useState(''), [schemaPlan, setSchemaPlan] = useState(null);
  const [schemaReceipt, setSchemaReceipt] = useState(null), [confirmApply, setConfirmApply] = useState(false);
  const [deletions, setDeletions] = useState([]);
  const [rebuilds, setRebuilds] = useState([]);
  const [columnRenames, setColumnRenames] = useState([]);
  const [nativeRenames,setNativeRenames]=useState([]),[renameKind,setRenameKind]=useState('table');
  const [ftsRebindings,setFtsRebindings]=useState([]);
  const [ftsConfigId, setFtsConfigId] = useState(''), [ftsSettings, setFtsSettings] = useState('{}');
  const [renameTable,setRenameTable]=useState(''),[renameColumn,setRenameColumn]=useState(''),[renameTo,setRenameTo]=useState('');
  const [busy, setBusy] = useState(false), [includeSystem, setIncludeSystem] = useState(false);
  const [display, setDisplay] = useState('inventory'), [view, setView] = useState('inventory_1');
  const [data, setData] = useState(null), [relation, setRelation] = useState('');
  const [dataScript, setDataScript] = useState(null);
  const [dataMode, setDataMode] = useState('sample'), [rowLimit, setRowLimit] = useState('100');
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setResult(null); setComparison(null); setSource(''); setBaselineSource(''); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false); setDeletions([]); setRebuilds([]); setColumnRenames([]); setError('');
    setNativeRenames([]);setFtsRebindings([]);setRenameKind('table');setRenameTable('');setRenameColumn('');setRenameTo('');
    setFtsConfigId(''); setFtsSettings('{}');
    setBusy(false); setDisplay('inventory'); setView('inventory_1'); setData(null); setDataScript(null); setRelation('');
    return () => {serial.current++;};
  }, [post, databaseTargetId]);
  const capture = async (compare=false) => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const value = await post({action: compare ? 'sqlite_catalog_compare' : 'sqlite_catalog_export',
        request: {database_target_id: databaseTargetId, include_system: includeSystem,
          ...(compare ? {source} : {})}});
      if(token !== serial.current) return;
      if(compare) setComparison(value);
      else {setResult(value); setComparison(null); setData(null); setDataScript(null); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false); setDeletions([]); setRebuilds([]); setColumnRenames([]);
        setNativeRenames([]);setFtsRebindings([]);setRenameTable('');setRenameColumn('');setRenameTo('');
        setBaselineSource(JSON.stringify(value.snapshot));
        const fts = value.objects?.find(item => item.kind === 'fts-table' && item.fts_configuration?.restorable);
        setFtsConfigId(fts?.resource_id || ''); setFtsSettings(JSON.stringify(Object.fromEntries(fts?.fts_configuration?.commands || []), null, 2));
        setRelation(value.objects?.find(item => item.resource_id === resourceId && item.kind === 'table')?.resource_id ||
          value.objects?.find(item => ['table', 'view', 'virtual-table', 'fts-table'].includes(item.kind))?.resource_id || '');
        setDisplay('inventory'); setView(value.snapshot.view);}
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'SQLite catalog capture failed');
    } finally {if(token === serial.current) setBusy(false);}
  };
  const captureData = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setData(null);
    try {
      const value = await post({action: 'sqlite_data_capture', request: {
        database_target_id: databaseTargetId, resource_id: relation,
        mode: dataMode, row_limit: Number(rowLimit)}});
      if(token === serial.current) {setData(value); setDisplay('data'); setView(value.snapshot.view);}
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'SQLite data capture failed');
    } finally {if(token === serial.current) setBusy(false);}
  };
  const exportDataScript = async () => {
    const token = ++serial.current; setBusy(true); setError(''); setDataScript(null);
    try {
      const value = await post({action: 'sqlite_data_script', request: {
        database_target_id: databaseTargetId, resource_id: relation}});
      if(token === serial.current) setDataScript(value);
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'SQLite SQL export failed');
    } finally {if(token === serial.current) setBusy(false);}
  };
  const previewSchema = async () => {
    const token = ++serial.current; setBusy(true); setError(''); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false);
    try {
      const value = await post({action: 'sqlite_schema_plan', request: {
        database_target_id: databaseTargetId, baseline: baselineSource, desired: source,
        deletions, rebuilds, column_renames: columnRenames,...(nativeRenames.length ? {renames:nativeRenames} : {}),...(ftsRebindings.length ? {fts_rebindings:ftsRebindings} : {})}});
      if(token === serial.current) setSchemaPlan(value);
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'SQLite schema preview failed');
    } finally {if(token === serial.current) setBusy(false);}
  };
  const reviewSchema = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'sqlite_schema_review', request: {
        database_target_id: databaseTargetId, baseline: baselineSource, desired: source,
        execution_sha256: schemaPlan.execution_sha256, deletions, rebuilds,
        column_renames: columnRenames,...(nativeRenames.length ? {renames:nativeRenames} : {}),...(ftsRebindings.length ? {fts_rebindings:ftsRebindings} : {})}});
      if(token === serial.current) {setSchemaReceipt(value); setConfirmApply(false);}
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'SQLite review failed');
    } finally {if(token === serial.current) setBusy(false);}
  };
  const generateRename = async () => {
    const token=++serial.current;setBusy(true);setError('');
    try {
      const value=await post({action:'sqlite_schema_rename_design',request:{database_target_id:databaseTargetId,
        baseline:baselineSource,renames:[{kind:renameKind,table:renameTable,to:renameTo,...(renameKind==='column' ? {from:renameColumn} : {})}],...(ftsRebindings.length ? {fts_rebindings:ftsRebindings} : {})}});
      if(token===serial.current) {setSource(JSON.stringify(value.snapshot,null,2));setNativeRenames(value.renames);setFtsRebindings(value.fts_rebindings || []);setDeletions([]);setRebuilds([]);setColumnRenames([]);setSchemaPlan(null);setSchemaReceipt(null);setConfirmApply(false);}
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message || 'Native SQLite rename design generation failed');}
    finally {if(token===serial.current)setBusy(false);}
  };
  const applySchema = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'sqlite_schema_apply', request: {
        database_target_id: databaseTargetId, review_id: schemaReceipt.review_id,
        review_digest: schemaReceipt.review_digest, confirmed: true}});
      if(token === serial.current) {setSchemaReceipt(value); setConfirmApply(false); setSchemaPlan(null);}
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'SQLite application outcome is unavailable; read the receipt before reviewing again');
    } finally {if(token === serial.current) setBusy(false);}
  };
  const generateFTSSettings = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'sqlite_fts_configuration_design', request: {
        database_target_id: databaseTargetId, baseline: baselineSource, resource_id: ftsConfigId, settings: JSON.parse(ftsSettings)}});
      if(token === serial.current) {
        setSource(JSON.stringify(value.snapshot, null, 2)); setNativeRenames([]); setFtsRebindings([]);
        setDeletions([]); setRebuilds([]); setColumnRenames([]); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false);
      }
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Native FTS settings design failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const readReceipt = async () => {
    const token = ++serial.current; setBusy(true); setError('');
    try {
      const value = await post({action: 'sqlite_schema_receipt', request: {
        database_target_id: databaseTargetId, review_id: schemaReceipt.review_id}});
      if(token === serial.current) setSchemaReceipt(value);
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'SQLite receipt is unavailable');
    } finally {if(token === serial.current) setBusy(false);}
  };
  const shown = display === 'relations' ? result?.diagram : display === 'data' ? data : result;
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(shown.snapshot)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url;
    link.download = `sqlite-${display}.ddn-workspace.json`; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey="sqlite-catalog-ddn" />
    <NativeDataImport post={post} databaseTargetId={databaseTargetId} engine="sqlite" objects={result?.objects} />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">SQLite metadata is captured from a separate connection to this registered file. Uncommitted changes and temporary objects on other connections are outside this view.</Alert>
    <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1}}>
      <FormControlLabel label="Include system objects" control={<Checkbox checked={includeSystem} disabled={busy}
        onChange={event => setIncludeSystem(event.target.checked)} />} />
      <Button disabled={busy || !databaseTargetId} onClick={() => capture()}>Capture metadata</Button>
      <Button disabled={busy || !shown?.snapshot} onClick={download}>Download DDN</Button>
      <Button component="label" disabled={busy}>Read DDN<input hidden disabled={busy} type="file" accept=".ddn,.json"
        aria-label="SQLite catalog DDN file" onChange={async event => {
          const file = event.target.files?.[0]; event.target.value = '';
          if(!file) return;
          if(file.size > 8 * 1024 * 1024) {setError('Catalog file exceeds 8 MiB'); return;}
          try {setNativeRenames([]);setFtsRebindings([]);setSource(await file.text()); setComparison(null); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false); setDeletions([]); setRebuilds([]); setColumnRenames([]); setError('');}
          catch(failure) {setError(failure.message || 'Could not read DDN file');}
        }} /></Button>
      <Button disabled={busy || !source || !databaseTargetId} onClick={() => capture(true)}>Compare with live catalog</Button>
      <Button disabled={busy || includeSystem || !source || !baselineSource || !databaseTargetId} onClick={previewSchema}>Preview native changes</Button>
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
        onChange={event => {setRelation(event.target.value); setDataScript(null);}}>
        {(result.objects || []).filter(item => ['table', 'view', 'virtual-table', 'fts-table'].includes(item.kind)).map(item =>
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
      <Button disabled={busy || !result.objects?.some(item => item.resource_id === relation && item.kind === 'table')}
        onClick={exportDataScript}>Export table as native SQL</Button>
    </Box>}
    {result && <Box component="details" sx={{my: 1}}>
      <summary>Native FTS configuration</summary>
      <Alert severity="info">Generate native settings without changing this file. Preview, review and confirm the resulting DDN change before applying. Existing settings remain unless explicitly reset to another native value. Index content is preserved.</Alert>
      <TextField select size="small" label="FTS configuration table" value={ftsConfigId} disabled={busy || includeSystem}
        onChange={event => {
          setFtsConfigId(event.target.value);
          const item = result.objects?.find(row => row.resource_id === event.target.value);
          setFtsSettings(JSON.stringify(Object.fromEntries(item?.fts_configuration?.commands || []), null, 2));
        }}>
        <MenuItem value="">Select an observed FTS table</MenuItem>
        {(result.objects || []).filter(item => item.kind === 'fts-table').map(item => <MenuItem
          key={item.resource_id} value={item.resource_id} disabled={!item.fts_configuration?.restorable}>{item.name}</MenuItem>)}
      </TextField>
      <TextField multiline minRows={3} fullWidth label="Native FTS settings (JSON)" value={ftsSettings}
        disabled={busy || includeSystem} onChange={event => setFtsSettings(event.target.value)}
        helperText="FTS5: automerge, usermerge, crisismerge, deletemerge, pgsz, hashsize, rank, secure-delete, insttoken. FTS3/4: automerge. Values are checked and normalized by SQLite." />
      <Button disabled={busy || includeSystem || !ftsConfigId || !baselineSource} onClick={generateFTSSettings}>Generate FTS settings design</Button>
    </Box>}
    {dataScript && <Box sx={{display: 'flex', flexDirection: 'column', gap: 0.5, my: 1}}>
      <Alert severity="info">{dataScript.rows} SQLite rows exported as SQL; no writes were executed. Review the script before importing it through the shared Query Tool.</Alert>
      <Button sx={{alignSelf: 'flex-start'}} onClick={() => {const url = URL.createObjectURL(new Blob([dataScript.source], {type: 'text/plain'}));
        const link = document.createElement('a'); link.href = url; link.download = 'sqlite-table-data.sql'; link.click();
        setTimeout(() => URL.revokeObjectURL(url), 1000);}}>Download SQL script</Button>
      <Box component="textarea" aria-label="SQLite native data SQL" value={dataScript.source} readOnly
        sx={{width: '100%', minHeight: 150, maxHeight: 300, resize: 'vertical', overflow: 'auto', fontFamily: 'monospace'}} />
    </Box>}
    {display === 'data' && data?.acquisition && <Alert severity="info">Captured {data.acquisition.rows} visible rows from {data.acquisition.relation}. Mode: {data.acquisition.mode}.</Alert>}
    {display === 'data' && data?.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
    {result && <Alert severity="info">Visible objects: {result.provenance.objects}. Coverage: {result.provenance.coverage}.</Alert>}
    {result && <Box component="details" sx={{my:1}}><summary>Native table and column renames</summary>
      <Alert severity="info">Generate the desired design using native SQLite name and reference rewriting. This leaves the registered file unchanged. Preview and review the generated design before applying it.</Alert>
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField select size="small" label="Native rename kind" value={renameKind} disabled={busy} onChange={event => {setRenameKind(event.target.value);setRenameTable('');setRenameColumn('');}}><MenuItem value="table">Table</MenuItem><MenuItem value="column">Column</MenuItem></TextField>
        <TextField select size="small" label="Native rename table" value={renameTable} disabled={busy} sx={{minWidth:180}} onChange={event => {setRenameTable(event.target.value);setRenameColumn('');}}>{(result.objects || []).filter(item => (renameKind==='column' ? item.kind==='table' : ['table','fts-table','virtual-table'].includes(item.kind)) && item.path?.[0]==='main').map(item => <MenuItem key={item.resource_id} value={item.name}>{item.name}</MenuItem>)}</TextField>
        {renameKind==='column' && <TextField select size="small" label="Native rename column" value={renameColumn} disabled={busy} sx={{minWidth:180}} onChange={event => setRenameColumn(event.target.value)}>{(result.objects || []).filter(item => item.kind==='column' && item.path?.[0]==='main' && item.path?.[1]===renameTable).map(item => <MenuItem key={item.resource_id} value={item.name}>{item.name}</MenuItem>)}</TextField>}
        <TextField size="small" label="New native name" value={renameTo} disabled={busy} onChange={event => setRenameTo(event.target.value)} />
        <Button disabled={busy || includeSystem || !renameTable || !renameTo || renameKind==='column' && !renameColumn} onClick={generateRename}>Generate native rename design</Button>
        {nativeRenames.length>0 && <Button disabled={busy} onClick={() => {setNativeRenames([]);setFtsRebindings([]);setSource('');setSchemaPlan(null);setSchemaReceipt(null);setConfirmApply(false);}}>Discard native rename design</Button>}
      </Box>
      {(result.objects || []).filter(item => item.kind==='fts-table' && item.external_content).map(item => <FormControlLabel key={item.resource_id}
        label={'Rebuild external-content FTS '+item.name+' from '+item.external_content}
        control={<Checkbox disabled={busy} checked={ftsRebindings.includes(item.resource_id)} onChange={event => {setFtsRebindings(current => event.target.checked ? [...current,item.resource_id] : current.filter(identity => identity!==item.resource_id));setSchemaPlan(null);setSchemaReceipt(null);setConfirmApply(false);}} />} />)}
      {nativeRenames.length>0 && <Alert severity="info">The generated rename intent is included in the next preview and review. Capture a fresh baseline after applying it.</Alert>}
    </Box>}
    {result && <Box component="details" sx={{my: 1}}><summary>Explicit native deletions ({deletions.length})</summary>
      <Alert severity="warning">A missing DDN row alone never deletes a SQLite object. Select each exact target here and remove that target and its children from the desired DDN. Table and virtual-table deletion requires a separate review.</Alert>
      <Box sx={{height: 230, overflow: 'auto'}}><PagedDataGrid readOnly gridId="sqlite/deletion-targets"
        aria-label="SQLite explicit deletion targets" rows={(result.objects || []).filter(item =>
          ['table', 'view', 'index', 'trigger', 'fts-table', 'virtual-table'].includes(item.kind))}
        rowKeyGetter={row => row.resource_id} columns={[
          {key: 'select', name: 'Delete', width: 90, renderCell: ({row}) =>
            <Checkbox size="small" checked={deletions.includes(row.resource_id)}
              disabled={busy || (!deletions.includes(row.resource_id) && deletions.length >= 32)}
              inputProps={{'aria-label': `Delete SQLite ${row.kind} ${row.name}`}}
              onChange={event => {setDeletions(current => event.target.checked ? [...current, row.resource_id] :
                current.filter(identity => identity !== row.resource_id)); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false);}} />},
          {key: 'name', name: 'Native object', minWidth: 170},
          {key: 'kind', name: 'Kind', width: 120},
          {key: 'path', name: 'Exact path', minWidth: 250, renderCell: ({row}) => row.path.join('.')},
        ]} /></Box>
    </Box>}
    {result && <Box component="details" sx={{my: 1}}><summary>Table rebuilds ({rebuilds.length})</summary>
      <Alert severity="warning">Selected tables are rebuilt together in one SQLite write transaction. Edit each desired CREATE TABLE definition before selecting it. Unchanged indexes and owning triggers are preserved; native foreign keys and retained view/trigger bindings are checked against the final batch schema before commit.</Alert>
      <Box sx={{height: 200, overflow: 'auto'}}><PagedDataGrid readOnly gridId="sqlite/rebuild-targets"
        aria-label="SQLite table rebuild targets" rows={(result.objects || []).filter(item => item.kind === 'table')}
        rowKeyGetter={row => row.resource_id} columns={[
          {key: 'select', name: 'Rebuild', width: 95, renderCell: ({row}) =>
            <Checkbox size="small" checked={rebuilds.includes(row.resource_id)}
              disabled={busy || (!rebuilds.includes(row.resource_id) && rebuilds.length >= 32)}
              inputProps={{'aria-label': `Rebuild SQLite table ${row.name}`}}
              onChange={event => {setRebuilds(current => event.target.checked ? [...current, row.resource_id] : current.filter(identity => identity !== row.resource_id)); setColumnRenames([]);
                setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false);}} />},
          {key: 'name', name: 'Native table', minWidth: 170},
          {key: 'path', name: 'Exact path', minWidth: 250, renderCell: ({row}) => row.path.join('.')},
        ]} /></Box>
      {rebuilds.length === 1 && <Box component="details" sx={{mt: 1}}><summary>Retained column renames ({columnRenames.length})</summary>
        <Alert severity="info">Map each old non-key column to its new name in the desired DDN. Without an explicit mapping, a removed column is discarded and a new column receives its declared default.</Alert>
        {columnRenames.map((item, index) => <Box key={index} sx={{display: 'flex', gap: 1, alignItems: 'center', my: 0.5}}>
          <TextField select size="small" label="Existing column" value={item.from} disabled={busy}
            sx={{minWidth: 180}} onChange={event => {setColumnRenames(current => current.map((entry, position) =>
              position === index ? {...entry, from: event.target.value} : entry)); setSchemaPlan(null); setSchemaReceipt(null);}}>
            {(result.objects || []).filter(row => row.kind === 'column' &&
              row.path?.[0] === (result.objects || []).find(table => table.resource_id === rebuilds[0])?.path?.[0] &&
              row.path?.[1] === (result.objects || []).find(table => table.resource_id === rebuilds[0])?.path?.[1])
              .map(row => <MenuItem key={row.resource_id} value={row.name}>{row.name}</MenuItem>)}
          </TextField>
          <TextField size="small" label="Desired column name" value={item.to} disabled={busy}
            onChange={event => {setColumnRenames(current => current.map((entry, position) =>
              position === index ? {...entry, to: event.target.value} : entry)); setSchemaPlan(null); setSchemaReceipt(null);}} />
          <Button size="small" disabled={busy} onClick={() => {setColumnRenames(current => current.filter((_, position) => position !== index));
            setSchemaPlan(null); setSchemaReceipt(null);}}>Remove</Button>
        </Box>)}
        <Button size="small" disabled={busy || columnRenames.length >= 16}
          onClick={() => {setColumnRenames(current => [...current, {table: rebuilds[0], from: '', to: ''}]);
            setSchemaPlan(null); setSchemaReceipt(null);}}>Map column rename</Button>
      </Box>}
    </Box>}
    {result?.snapshot && <FirebirdCatalogDesigner engine="sqlite" baseline={JSON.stringify(result.snapshot)}
      post={post} databaseTargetId={databaseTargetId} disabled={busy}
      onReview={(desired, baseline) => {setNativeRenames([]);setFtsRebindings([]);setSource(desired); setBaselineSource(baseline); setComparison(null); setSchemaPlan(null); setSchemaReceipt(null); setConfirmApply(false); setDeletions([]); setRebuilds([]); setColumnRenames([]);}} />}
    {result?.provenance?.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
    {comparison && <Box sx={{height: 280, overflow: 'auto'}}>
      <PagedDataGrid readOnly gridId="sqlite/catalog-comparison" aria-label="SQLite catalog differences"
        rows={comparison.changes} rowKeyGetter={row => row.resource_id} columns={[
          {key: 'name', name: 'Native object', minWidth: 180}, {key: 'kind', name: 'Kind', width: 140},
          {key: 'status', name: 'Difference', width: 140},
          {key: 'fields', name: 'Changed native fields', minWidth: 260, renderCell: ({row}) => row.fields.join(', ')},
        ]} />
    </Box>}
    {schemaPlan && <Box>
      <Alert severity={schemaPlan.blockers.length || schemaPlan.conflicts.length ? 'warning' : 'info'}>
        Native preview only; no SQL was executed on the registered file. {schemaPlan.operations.length} operations, {schemaPlan.blockers.length} blockers, {schemaPlan.conflicts.length} conflicts. Table and virtual-table deletions require separate review from additions.
      </Alert>
      <Box sx={{height: 260, overflow: 'auto'}}><PagedDataGrid readOnly gridId="sqlite/schema-preview"
        aria-label="SQLite native schema preview" rows={[...schemaPlan.operations, ...schemaPlan.blockers, ...schemaPlan.conflicts]}
        rowKeyGetter={(row, index) => `${row.resource_id}/${row.operation || row.reason || index}`} columns={[
          {key: 'name', name: 'Native object', minWidth: 170}, {key: 'operation', name: 'Operation', width: 110},
          {key: 'source', name: 'Native SQL', minWidth: 340,
            renderCell: ({row}) => row.source || row.stages?.join(';\n') || ''},
          {key: 'reason', name: 'Blocker or conflict', minWidth: 260},
        ]} /></Box>
      {schemaPlan.application_supported && !schemaReceipt &&
        <Button disabled={busy} onClick={reviewSchema}>Prepare native change review</Button>}
      {schemaPlan.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {schemaPlan.operations.some(item => item.operation==='rename-batch') && <Box component="details"><summary>Exact native rename statements and settings</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:350,overflow:'auto'}}>{JSON.stringify(schemaPlan.operations,null,2)}</Box></Box>}
      {schemaPlan.operations.some(item => item.operation!=='rename-batch' && item.stages?.length) &&
        <Box component="details"><summary>Exact native migration statements</summary>
          <Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:350,overflow:'auto'}}>
            {schemaPlan.operations.flatMap(item => item.stages || (item.source ? [item.source] : [])).join(';\n\n')}
          </Box>
        </Box>}
    </Box>}
    {schemaReceipt && <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap'}}>
      <Alert severity={schemaReceipt.state === 'committed' ? 'success' : schemaReceipt.state === 'unknown_outcome' ? 'warning' : 'info'}>
        Native receipt {schemaReceipt.review_id}: {schemaReceipt.state}. Rediscovery {schemaReceipt.outcome?.rediscovery_verified ? 'verified' : 'unverified'}.
      </Alert>
      {(schemaReceipt.outcome?.native_error || schemaReceipt.outcome?.reason || schemaReceipt.outcome?.error_type) &&
        <Alert severity={schemaReceipt.state==='unknown_outcome' ? 'warning' : 'error'} aria-label="SQLite native outcome">
          {schemaReceipt.outcome.native_error || schemaReceipt.outcome.reason || schemaReceipt.outcome.error_type}
          {schemaReceipt.outcome.native_error_name && ` (${schemaReceipt.outcome.native_error_name})`}
        </Alert>}
      {schemaReceipt.state === 'reviewed' && <FormControlLabel label="Confirm this reviewed SQLite change"
        control={<Checkbox checked={confirmApply} disabled={busy} onChange={event => setConfirmApply(event.target.checked)} />} />}
      {schemaReceipt.state === 'reviewed' && <Button disabled={busy || !confirmApply} onClick={applySchema}>Apply reviewed change</Button>}
      <Button disabled={busy} onClick={readReceipt}>Read native receipt</Button>
    </Box>}
    {shown?.snapshot && <Box sx={{height: 500, minHeight: 250, overflow: 'auto'}}>
      <DDNViewerSurface presentation snapshot={{...shown.snapshot, view,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry}} />
    </Box>}
  </Box>;
}
SQLiteCatalog.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string,
  resourceId: PropTypes.string};
