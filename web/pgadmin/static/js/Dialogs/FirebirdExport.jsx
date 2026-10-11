import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField, Table, TableBody, TableCell, TableHead, TableRow, TablePagination} from '@mui/material';
import gettext from 'sources/gettext';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import FirebirdSchemaPlan from './FirebirdSchemaPlan';
import FirebirdERD from './FirebirdERD';
import FirebirdDataImport from './FirebirdDataImport';

export default function FirebirdExport({post, generation, selectedResource, resources = [], onCatalogRefresh, onOpenAllocation, databaseTargetId, onLoadMore, hasMore=false, loadingMore=false}) {
  const [scope, setScope] = useState('database');
  const [branchFilter, setBranchFilter] = useState('');
  const [includeSystem, setIncludeSystem] = useState(false);
  const [refresh, setRefresh] = useState(false);
  const [result, setResult] = useState(null);
  const [diagram, setDiagram] = useState(null);
  const [designRequest, setDesignRequest] = useState(null);
  const [sqlResult, setSqlResult] = useState(null);
  const [dataResult, setDataResult] = useState(null);
  const [resourceId, setResourceId] = useState(selectedResource?.resource_id || '');
  const branches = resources.filter(item => !['service-operation', 'metric'].includes(item.resource_kind));
  const visibleBranches = branches.filter(item => item.resource_id === resourceId ||
    [item.resource_kind, item.display_name, ...(item.display_path || [])].join(' ').toLocaleLowerCase().includes(branchFilter.toLocaleLowerCase()));
  const [view, setView] = useState('inventory_1');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState('');
  const [filename, setFilename] = useState('');
  const [comparison, setComparison] = useState(null);
  const [page, setPage] = useState(0);
  const token = useRef(0);
  useEffect(() => {
    token.current++;
    setResult(null); setDiagram(null); setDesignRequest(null); setSqlResult(null); setDataResult(null); setError(''); setBusy(false);
    setSource(''); setFilename(''); setComparison(null);
    return () => {token.current++;};
  }, [post]);
  const capture = async (compare = false, sql = false, contents = null) => {
    const requestToken = ++token.current;
    setBusy(true); setError(''); setResult(null); setSqlResult(null); setDataResult(null); setComparison(null);
    try {
      const response = await post({action: compare ? 'firebird_catalog_compare' : sql ? 'firebird_sql_export' : contents ? 'firebird_data_export' : 'firebird_catalog_export', request: {
        generation, include_system: includeSystem, refresh,
        ...(contents ? {contents} : {}),
        ...(compare ? {source} : {}),
        ...(scope === 'branch' ? {resource_id: resourceId} : {}),
      }});
      if(requestToken !== token.current) return;
      if(compare) {setComparison(response); setPage(0);}
      else if(sql) setSqlResult(response);
      else if(contents) setDataResult(response);
      else {setResult(response); setDiagram(response.diagram || null); setView(response.snapshot.view);
        setSource(JSON.stringify(response.snapshot)); setFilename('Captured native catalog');}
      if(refresh) await onCatalogRefresh?.();
    } catch(err) {
      if(requestToken === token.current) setError(err.response?.data?.errormsg || err.message || gettext('Catalog export failed.'));
    } finally {if(requestToken === token.current) setBusy(false);}
  };
  const loadDocument = async (event) => {
    const file = event.target.files?.[0];
    event.target.value = '';
    if(!file) return;
    const requestToken = ++token.current;
    setSource(''); setFilename(''); setComparison(null); setError(''); setBusy(true);
    try {
      if(file.size > 8 * 1024 * 1024) throw new Error(gettext('Catalog document exceeds 8 MiB.'));
      const text = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer());
      if(requestToken === token.current) {setSource(text); setFilename(file.name);}
    } catch(err) {
      if(requestToken === token.current) setError(err.message || gettext('Unable to read UTF-8 DDN document.'));
    } finally {if(requestToken === token.current) setBusy(false);}
  };
  const download = (result) => {
    const url = URL.createObjectURL(new Blob([result.download_text ?? result.snapshot.files[result.snapshot.entry]], {type: 'text/plain;charset=utf-8'}));
    const link = document.createElement('a');
    link.href = url; link.download = result.filename;
    document.body.appendChild(link); link.click(); link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{p: 2, display: 'flex', flexDirection: 'column', gap: 1, height: '100%', overflow: 'auto'}}>
    <FormReference formKey="firebird-export" />
    <Alert severity="info">{gettext('Choose documentary DDN metadata, native metadata SQL, or a lossless data archive. Data capture uses a separate read-only snapshot and is limited to 100,000 rows and 8 MiB; exceeding a limit produces no partial download. DDN inventory pages show up to 100 objects.')}</Alert>
    <TextField select size="small" label={gettext('Metadata scope')} value={scope} disabled={busy}
      onChange={(event) => {setScope(event.target.value); setResult(null); setSqlResult(null); setDataResult(null);}}>
      <MenuItem value="database">{gettext('Database catalog')}</MenuItem>
      <MenuItem value="branch" disabled={!branches.length && !selectedResource?.resource_id}>{gettext('Selected object and children')}</MenuItem>
    </TextField>
    {scope === 'branch' && <Box>
      <TextField size="small" label={gettext('Filter loaded branches')} value={branchFilter}
        onChange={event => setBranchFilter(event.target.value)} disabled={busy || loadingMore} />
      {hasMore && <Button disabled={busy || loadingMore || !onLoadMore} onClick={onLoadMore}>
        {gettext('Load more native branches')}</Button>}
      {hasMore && <Alert severity="info">{gettext('More native objects remain unloaded. Filtering searches the loaded choices only.')}</Alert>}
    </Box>}
    {scope === 'branch' && <TextField select size="small" label={gettext('Native branch')} value={resourceId} disabled={busy}
      onChange={event => {setResourceId(event.target.value); setResult(null); setSqlResult(null); setDataResult(null);}}>
      {visibleBranches.map(item => <MenuItem key={item.resource_id} value={item.resource_id}>{item.resource_kind}: {item.display_path?.join(' / ') || item.display_name}</MenuItem>)}
      {selectedResource && !branches.some(item => item.resource_id === selectedResource.resource_id) && <MenuItem value={selectedResource.resource_id}>{selectedResource.display_name}</MenuItem>}
    </TextField>}
    <FormControlLabel label={gettext('Include objects marked as system')}
      control={<Checkbox checked={includeSystem} disabled={busy} onChange={(event) => setIncludeSystem(event.target.checked)} />} />
    <FormControlLabel label={gettext('Refresh native catalog before export')}
      control={<Checkbox checked={refresh} disabled={busy} onChange={(event) => setRefresh(event.target.checked)} />} />
    <Box><Button disabled={busy || !generation || (scope === 'branch' && !resourceId)}
      onClick={() => capture()}>{gettext('Capture metadata')}</Button>
    <Button disabled={busy || !generation || (scope === 'branch' && !resourceId)}
      onClick={() => capture(false, true)}>{gettext('Capture native SQL')}</Button>
    <Button disabled={busy || includeSystem || !generation || (scope === 'branch' && !resourceId)} onClick={() => capture(false, false, 'data')}>{gettext('Capture data archive')}</Button>
    <Button disabled={busy || includeSystem || !generation || (scope === 'branch' && !resourceId)} onClick={() => capture(false, false, 'both')}>{gettext('Capture metadata and data')}</Button>
    {result && <Button disabled={busy} onClick={() => download(result)}>{gettext('Download DDN')}</Button>}</Box>
    <Box>
      <Button component="label" disabled={busy}>{gettext('Read catalog DDN')}
        <input hidden type="file" accept=".ddn,.json,text/plain,application/json" aria-label={gettext('Catalog DDN file')} disabled={busy} onChange={loadDocument} />
      </Button>
      {filename && <span>{filename}</span>}
      <Button disabled={busy || !source || !generation || (scope === 'branch' && !resourceId)}
        onClick={() => capture(true)}>{gettext('Compare with database catalog')}</Button>
    </Box>
    <FirebirdSchemaPlan designRequest={designRequest} databaseTargetId={databaseTargetId} baseline={source} post={post} generation={generation}
      onCatalogRefresh={onCatalogRefresh} disabled={busy} />
    <FirebirdDataImport onOpenAllocation={onOpenAllocation} post={post} generation={generation} databaseTargetId={databaseTargetId} onCatalogRefresh={onCatalogRefresh} disabled={busy} />
    {error && <Alert severity="error">{error}</Alert>}
    {dataResult && <>
      <Alert severity="info">{gettext('Lossless native data archive captured in a separate read-only snapshot. The snapshot has been released. Computed and identity metadata remain explicit; this document is not an executable SQL script.')}</Alert>
      <Box>{dataResult.table_count} {gettext('tables')}; {dataResult.row_count} {gettext('rows')}. {gettext('Contents')}: {dataResult.contents}</Box>
      <Button onClick={() => download(dataResult)}>{gettext('Download data archive')}</Button>
    </>}
    {sqlResult && <>
      <Alert severity="info">{gettext('Native metadata only. Review ownership and external prerequisites before execution. This file has no connection credentials or transaction outcome statements. Data export is separate.')}</Alert>
      <Box>{gettext('Catalog coverage')}: {sqlResult.provenance.coverage}. {gettext('Observation')}: {sqlResult.provenance.observation}.</Box>
      {(sqlResult.provenance.warnings || []).map((warning, index) => <Alert severity="warning" key={index}>{warning}</Alert>)}
      {sqlResult.blockers.map((item, index) => <Alert severity="error" key={index}>{item.kind}: {item.name} — {item.reason}</Alert>)}
      {sqlResult.external_prerequisites.map((item, index) => <Alert severity="warning" key={index}>{gettext('External prerequisite')}: {item.name} ({item.kinds.join(', ')})</Alert>)}
      {!!sqlResult.ownership_requirements.length && <Table size="small" aria-label={gettext('Metadata ownership requirements')}>
        <TableHead><TableRow><TableCell>{gettext('Resource')}</TableCell><TableCell>{gettext('Create as user')}</TableCell></TableRow></TableHead>
        <TableBody>{sqlResult.ownership_requirements.map(item => <TableRow key={item.resource_id}>
          <TableCell>{item.resource_id}</TableCell><TableCell>{item.execute_as_user}</TableCell>
        </TableRow>)}</TableBody>
      </Table>}
      {sqlResult.download_text && <>
        <Button onClick={() => download(sqlResult)}>{gettext('Download native SQL')}</Button>
        <TextField multiline minRows={6} maxRows={18} label={gettext('Native metadata SQL')} value={sqlResult.download_text} InputProps={{readOnly: true}} />
      </>}
    </>}
    {comparison && <>
      {(comparison.warnings || []).map((warning, index) => <Alert severity="warning" key={index}>{warning}</Alert>)}
      <Box>{Object.entries(comparison.counts).map(([key, count]) => `${key}: ${count}`).join(' · ')}</Box>
      <Table size="small" aria-label={gettext('Catalog differences')}>
        <TableHead><TableRow>{['Object', 'Native kind', 'Difference', 'Changed fields'].map((label) => <TableCell key={label}>{gettext(label)}</TableCell>)}</TableRow></TableHead>
        <TableBody>{comparison.changes.slice(page * 50, (page + 1) * 50).map((item) => <TableRow key={item.resource_id}>
          <TableCell>{item.name}</TableCell><TableCell>{item.kind}</TableCell><TableCell>{item.status}</TableCell><TableCell>{item.fields.join(', ')}</TableCell>
        </TableRow>)}</TableBody>
      </Table>
      <TablePagination component="div" count={comparison.changes.length} page={page} rowsPerPage={50}
        rowsPerPageOptions={[50]} onPageChange={(_event, value) => setPage(value)} />
    </>}
    {result && <>
      <Alert severity={result.provenance.coverage === 'visible-catalog' ? 'info' : 'warning'}>
        {result.provenance.objects} objects. Coverage: {result.provenance.coverage}.
        Observation: {result.provenance.observation}. Exported: {result.provenance.exported_at}.
        Catalog visibility follows the connected account; omitted objects are not deletion instructions.
      </Alert>
      {(result.provenance.warnings || []).map((warning, index) => <Alert severity="warning" key={index}>{warning}</Alert>)}
      <TextField select size="small" label={gettext('Inventory page')} value={view}
        onChange={(event) => setView(event.target.value)}>
        {(result.views || []).map((item) => <MenuItem key={item.id} value={item.id}>{item.label}</MenuItem>)}
      </TextField>
      <DDNViewerSurface snapshot={{...result.snapshot, entry: result.views?.find((item) => item.id === view)?.entry || result.snapshot.entry, view}} presentation />
    </>}
    {diagram && <FirebirdERD diagram={diagram} post={post} databaseTargetId={databaseTargetId} generation={generation}
      onReview={async value => {
        await onCatalogRefresh?.(); setSource(value.baseline); setDesignRequest(value);
        setFilename('Relational design baseline');
      }} />}
  </Box>;
}
FirebirdExport.propTypes = {onLoadMore: PropTypes.func, hasMore: PropTypes.bool, loadingMore: PropTypes.bool, onOpenAllocation: PropTypes.func, databaseTargetId: PropTypes.string,post: PropTypes.func.isRequired, generation: PropTypes.string,
  selectedResource: PropTypes.object, resources: PropTypes.array, onCatalogRefresh: PropTypes.func};
