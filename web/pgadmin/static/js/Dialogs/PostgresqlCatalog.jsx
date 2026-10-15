import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, Dialog, FormControlLabel, MenuItem, TextField, Table, TableBody, TableCell, TableHead, TableRow, TablePagination} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNDesignerSurface, DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {validateDDNSnapshot} from '../cdeadmin_ui/integrations/ddn/contracts';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function PostgresqlCatalog({post, databaseTargetId}) {
  const [result, setResult] = useState(null), [error, setError] = useState('');
  const [busy, setBusy] = useState(false), [includeSystem, setIncludeSystem] = useState(false);
  const [display, setDisplay] = useState('inventory');
  const [view, setView] = useState('inventory_1'), [scope, setScope] = useState('');
  const [source, setSource] = useState(''), [comparison, setComparison] = useState(null);
  const [baseline, setBaseline] = useState(''), [plan, setPlan] = useState(null);
  const [page, setPage] = useState(0), [editing, setEditing] = useState(false), [ready, setReady] = useState(false);
  const editor = useRef(null), seed = useRef(null), serial = useRef(0), relationalOriginal = useRef(null);
  const [relationalEditing, setRelationalEditing] = useState(false);
  const [receipt, setReceipt] = useState(null), [confirmed, setConfirmed] = useState(false);
  useEffect(() => {setConfirmed(false);}, [source, baseline, plan, includeSystem]);
  useEffect(() => {
    serial.current++; setReceipt(null); setConfirmed(false); setResult(null); setSource(''); setBaseline(''); setPlan(null);
    setComparison(null); setScope(''); setBusy(false); setError(''); setEditing(false);
    return () => {serial.current++;};
  }, [databaseTargetId]);
  const run = async (compare=false, planning=false) => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const response = await post({action: planning ? 'postgresql_schema_plan' : compare ? 'postgresql_catalog_compare' : 'postgresql_catalog_export',
        request: {database_target_id: databaseTargetId, include_system: includeSystem,
          ...(scope ? {resource_id: scope} : {}), ...(compare || planning ? {source} : {}), ...(planning ? {baseline} : {})}});
      if(token !== serial.current) return;
      if(planning) {setPlan(response); setComparison(null); setPage(0);}
      else if(compare) {setComparison(response); setPlan(null); setPage(0);}
      else {setResult(response); setDisplay('inventory'); setView(response.snapshot.view); setComparison(null); setPlan(null);
        if(!baseline) setBaseline(JSON.stringify(response.snapshot));}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Catalog capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const application = async action => {
    const token = ++serial.current;
    setBusy(true); setError('');
    const request = action === 'postgresql_schema_review' ? {
      database_target_id: databaseTargetId, include_system: includeSystem,
      baseline, source, execution_sha256: plan.execution_sha256,
    } : {database_target_id: databaseTargetId, review_id: receipt.review_id,
      ...(action === 'postgresql_schema_apply' ? {review_digest: receipt.review_digest, confirmed} : {})};
    try {
      const value = await post({action, request});
      if(token === serial.current) {setReceipt(value); setConfirmed(false);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Schema application request failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const download = (draft=false, diagram=false) => {
    const text = draft ? source : JSON.stringify(diagram ? result.diagram.snapshot : result.snapshot);
    const url = URL.createObjectURL(new Blob([text], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = diagram ? 'postgresql-relations.ddn-workspace.json' : 'postgresql-catalog.ddn-workspace.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const keepDraft = async () => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const snapshot = editor.current.snapshot(); validateDDNSnapshot(snapshot);
      const {format, entry, view: selectedView, files} = snapshot;
      const draft = {format, entry, view: selectedView, files};
      if(relationalEditing) {
        const response = await post({action: 'postgresql_relational_review', request: {
          database_target_id: databaseTargetId, include_system: includeSystem,
          original: relationalOriginal.current, snapshot: draft}});
        if(token !== serial.current) return;
        setBaseline(response.baseline); setSource(response.desired);
      } else setSource(JSON.stringify(draft));
      setComparison(null); setPlan(null); setEditing(false); setReady(false); editor.current = null;
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Unable to read DDN draft');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const shown = display === 'relations' ? result?.diagram : result;
  return <Box sx={{...compactFormSx, gridAutoRows: 'max-content', overflow: 'auto', flex: 1, p: 1}}>
    <FormReference formKey="postgresql-catalog-ddn" />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">Native catalog evidence and DDN design. Capture and comparison do not execute imported definitions. Coverage and omissions are recorded with each capture.</Alert>
    <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap'}}>
      <FormControlLabel label="Include system objects" control={<Checkbox checked={includeSystem} disabled={busy} onChange={event => setIncludeSystem(event.target.checked)} />} />
      <TextField select size="small" label="Native scope" value={scope} disabled={busy} sx={{minWidth: 220}} SelectProps={{displayEmpty: true}} InputLabelProps={{shrink: true}}
        onChange={event => setScope(event.target.value)}>
        <MenuItem value="">Database catalog</MenuItem>
        {(result?.objects || []).filter(item => item.kind !== 'database').map(item =>
          <MenuItem key={item.resource_id} value={item.resource_id}>{item.kind}: {item.path.join(' / ')}</MenuItem>)}
      </TextField>
      <Button disabled={busy || !databaseTargetId} onClick={() => run()}>Capture metadata</Button>
      <Button disabled={busy || !result} onClick={() => download()}>Download capture</Button>
      <Button disabled={busy || !result} onClick={() => {setBaseline(JSON.stringify(result.snapshot)); setPlan(null);}}>Use capture as baseline</Button>
      <Button disabled={busy || !source} onClick={() => download(true)}>Download draft</Button>
      <Button disabled={busy || !result} onClick={() => {
        try {seed.current = source ? (source.trimStart().startsWith('{') ? JSON.parse(source) : {
          format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1', files: {'catalog.ddn': source},
        }) : result.snapshot; validateDDNSnapshot(seed.current);
        setRelationalEditing(false); setReady(false); setError(''); setEditing(true);
        } catch {setError('Select a valid DDN workspace before editing');}
      }}>Edit DDN draft</Button>
      <Button component="label" disabled={busy}>Read DDN<input hidden type="file" accept=".ddn,.json" aria-label="PostgreSQL catalog DDN file"
        onChange={async event => {
          const file = event.target.files?.[0], token = serial.current;
          if(!file) return;
          if(file.size > 8 * 1024 * 1024) {setError('Catalog file exceeds 8 MiB'); return;}
          try {
            const text = await file.text(); if(token !== serial.current) return;
            setSource(text); setComparison(null); setPlan(null); setError('');
          } catch {if(token === serial.current) setError('Unable to read catalog file');}
        }} /></Button>
      <Button disabled={busy || !source} onClick={() => run(true)}>Compare with live catalog</Button>
      <Button disabled={busy || !source || !baseline} onClick={() => run(false, true)}>Preview native changes</Button>
    </Box>
    {source && <Alert severity="info">An imported or edited document is retained separately from the latest live capture.</Alert>}
    {result && <PostgresqlDataCapture key={databaseTargetId} post={post}
      databaseTargetId={databaseTargetId} objects={result.objects || []} />}
    {plan && <Box sx={{overflow: 'auto'}}>
      <Alert severity={plan.blockers.length ? 'warning' : 'info'}>Native plan preview: {plan.blockers.length} blockers. Application outcomes are shown in the receipt below.</Alert>
      {plan.application_supported && <Button disabled={busy || receipt?.state === 'unknown_outcome'}
        onClick={() => application('postgresql_schema_review')}>Prepare application</Button>}
      {plan.blockers.length > 0 && <Box component="details"><summary>Unresolved native changes</summary>
        <ul>{plan.blockers.map(item => <li key={item.resource_id}>{item.resource_id}: {item.reason}</li>)}</ul></Box>}
      <Table size="small" aria-label="PostgreSQL native change preview"><TableHead><TableRow>
        <TableCell>Object</TableCell><TableCell>Native statement</TableCell>
      </TableRow></TableHead><TableBody>{plan.operations.slice(page * 25, page * 25 + 25).map(item =>
        <TableRow key={item.resource_id}><TableCell>{item.name}</TableCell>
          <TableCell><Box component="pre" sx={{m: 0, whiteSpace: 'pre-wrap'}}>{item.statement}</Box></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={plan.operations.length} page={page} rowsPerPage={25}
        rowsPerPageOptions={[25]} onPageChange={(_event, value) => setPage(value)} showFirstButton showLastButton />
    </Box>}
    {receipt && <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center'}}>
      <Alert severity={receipt.state === 'unknown_outcome' ? 'warning' : 'info'}>
        Review {receipt.review_id}: {receipt.state}. No automatic retry.
        {receipt.outcome?.rediscovery && (receipt.outcome.rediscovery.matches_reviewed_properties ? ' Reviewed properties confirmed.' : ' Inspect fresh metadata before further changes.')}
      </Alert>
      {receipt.state === 'reviewed' && plan?.execution_sha256 === receipt.plan.execution_sha256 && <>
        <FormControlLabel label="Confirm reviewed native changes" control={<Checkbox checked={confirmed} disabled={busy}
          onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || !confirmed} onClick={() => application('postgresql_schema_apply')}>Apply reviewed changes</Button>
      </>}
      <Button disabled={busy} onClick={() => application('postgresql_schema_receipt')}>Refresh application receipt</Button>
    </Box>}
    {result && <>
      <Box component="details" sx={{my: 1}}><summary>Coverage and exclusions ({result.provenance.warnings.length})</summary>
        <ul>{result.provenance.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      </Box>
      <Box sx={{display: 'flex', gap: 1, alignItems: 'center', flexWrap: 'wrap'}}>
        <TextField select size="small" label="Display" value={display} onChange={event => {
          const value = event.target.value; setDisplay(value);
          setView((value === 'relations' ? result.diagram : result).snapshot.view);
        }}>
          <MenuItem value="inventory">Catalog inventory</MenuItem>
          {result.diagram?.snapshot && <MenuItem value="relations">Relational diagram</MenuItem>}
        </TextField>
        {result.diagram?.snapshot && <>
          <Button disabled={busy} onClick={() => download(false, true)}>Download relational DDN</Button>
          <Button disabled={busy} onClick={() => {
            relationalOriginal.current = result.diagram.snapshot; seed.current = result.diagram.snapshot;
            setRelationalEditing(true); setReady(false); setError(''); setEditing(true);
          }}>Edit relational DDN</Button>
        </>}
      </Box>
      {result.diagram?.unavailable && <Alert severity="warning">{result.diagram.unavailable}</Alert>}
      {display === 'relations' && shown.warnings?.length > 0 && <Box component="details"><summary>Diagram observations</summary>
        <ul>{shown.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul></Box>}
      <TextField select size="small" label="Inventory view" value={view} onChange={event => setView(event.target.value)}>
        {shown.views.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      <Box sx={{height: 500, minHeight: 250, overflow: 'auto'}}><DDNViewerSurface presentation snapshot={{...shown.snapshot,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry, view}} /></Box>
    </>}
    {comparison && <Box sx={{overflow: 'auto'}}>
      <Alert severity="info">Documentary differences only; missing objects are not deletion instructions.</Alert>
      <Table size="small" aria-label="PostgreSQL native catalog differences"><TableHead><TableRow>
        {['Object', 'Kind', 'Difference', 'Native fields'].map(label => <TableCell key={label}>{label}</TableCell>)}
      </TableRow></TableHead><TableBody>{comparison.changes.slice(page * 25, page * 25 + 25).map(item =>
        <TableRow key={item.resource_id}><TableCell>{item.name}</TableCell><TableCell>{item.kind}</TableCell>
          <TableCell>{item.status}</TableCell><TableCell>{item.fields.join(', ')}</TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={comparison.changes.length} page={page} rowsPerPage={25}
        rowsPerPageOptions={[25]} onPageChange={(_event, value) => setPage(value)} showFirstButton showLastButton />
    </Box>}
    <Dialog fullScreen open={editing}>
      <Box sx={{display: 'flex', p: 1, gap: 1, alignItems: 'center'}}>
        <FormReference formKey="postgresql-catalog-ddn" />
        <Box sx={{flex: 1}}>{relationalEditing ? 'PostgreSQL relational DDN draft' : 'PostgreSQL native catalog DDN draft'}</Box>
        <Button disabled={!ready || busy} onClick={keepDraft}>Keep draft</Button>
        <Button disabled={busy} onClick={() => {setEditing(false); editor.current = null;}}>Discard editor changes</Button>
      </Box>
      {error && <Alert severity="error">{error}</Alert>}
      <Alert severity="info">Native definitions are in native_json. Labels, layout and hidden objects do not alter database metadata.</Alert>
      <Box sx={{flex: 1, minHeight: 0}}>{editing && <DDNDesignerSurface snapshot={seed.current}
        onReady={value => {editor.current = value; setReady(true);}}
        onError={failure => {setReady(false); setError(failure.message);}} />}</Box>
    </Dialog>
  </Box>;
}
PostgresqlCatalog.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string};

export function PostgresqlDataCapture({post, databaseTargetId, objects}) {
  const [relation, setRelation] = useState(''), [mode, setMode] = useState('sample');
  const [limit, setLimit] = useState(100), [busy, setBusy] = useState(false);
  const [result, setResult] = useState(null), [error, setError] = useState(''), [view, setView] = useState('');
  const serial = useRef(0);
  useEffect(() => () => {serial.current++;}, []);
  const relations = objects.filter(item => ['table', 'partitioned-table', 'view', 'materialized-view'].includes(item.kind));
  const selected = relations.some(item => item.resource_id === relation);
  const run = async () => {
    const token = ++serial.current;
    setBusy(true); setError(''); setResult(null);
    try {
      const captured = await post({action: 'postgresql_data_capture', request: {
        database_target_id: databaseTargetId, resource_id: relation, mode, row_limit: limit}});
      if(token !== serial.current) return;
      setResult(captured); setView(captured.snapshot.view);
    } catch(failure) {
      if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'Data capture failed');
    } finally {if(token === serial.current) setBusy(false);}
  };
  const download = () => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(result.snapshot)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = 'postgresql-data.ddn-workspace.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box component="details" sx={{my: 1}}><summary>Selected relation data</summary>
    <Box sx={{display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1, my: 1}}>
      <TextField select size="small" label="Data relation" value={selected ? relation : ''} disabled={busy} sx={{minWidth: 220}}
        onChange={event => setRelation(event.target.value)}>
        <MenuItem value="">Select a relation</MenuItem>
        {relations.map(item => <MenuItem key={item.resource_id} value={item.resource_id}>{item.path.join(' / ')} ({item.kind})</MenuItem>)}
      </TextField>
      <TextField select size="small" label="Data capture mode" value={mode} disabled={busy} onChange={event => {
        setMode(event.target.value); setLimit(event.target.value === 'full' ? 6000 : 100);
      }}><MenuItem value="sample">Sample (native scan order)</MenuItem><MenuItem value="full">Full selection within budget</MenuItem></TextField>
      <TextField size="small" type="number" label="Data row budget" value={limit} disabled={busy} sx={{width: 140}}
        inputProps={{min: 1, max: 6000, step: 1}} onChange={event => setLimit(event.target.value === '' ? '' : Number(event.target.value))} />
      <Button disabled={busy || !selected || !Number.isInteger(limit) || limit < 1 || limit > 6000} onClick={run}>Capture selected data</Button>
      <Button disabled={busy || !result} onClick={download}>Download data DDN</Button>
    </Box>
    <Alert severity="info">Explicit read on a separate connection. Native row permissions apply. Unordered sample/full selection; 6,000 rows and document size limits. This is static data, not a backup.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {result && <>
      <Alert severity={result.coverage.selection_complete ? 'info' : 'warning'}>
        {result.coverage.schema}.{result.coverage.name}: {result.coverage.rows} rows captured.
        {' '}{result.coverage.selection_complete ? 'All attachment-visible rows captured.' : 'Partial selection: row budget reached.'}
      </Alert>
      <TextField select size="small" label="Data view" value={view} onChange={event => setView(event.target.value)}>
        {result.views.map(item => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      <Box sx={{height: 400, overflow: 'auto'}}><DDNViewerSurface presentation snapshot={{...result.snapshot,
        view, entry: result.views.find(item => item.id === view)?.entry || result.snapshot.entry}} /></Box>
    </>}
  </Box>;
}
PostgresqlDataCapture.propTypes = {post: PropTypes.func.isRequired, databaseTargetId: PropTypes.string.isRequired, objects: PropTypes.array.isRequired};
