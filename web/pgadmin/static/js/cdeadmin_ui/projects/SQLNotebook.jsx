import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import {ProjectAssetClient} from './ProjectAssetClient';
import {useModalCloseGuard} from '../../helpers/ModalCloseGuard';
import {NOTEBOOK_TYPE, NOTEBOOK_LIMIT, newNotebook, notebookRequest, portableNotebook,
  rebindNotebook, retainedSnapshot, sameScope, sensitiveColumn, validateNotebook} from './SQLNotebookModel';

export default function SQLNotebook({client: suppliedClient, scope=null, editorSource='',
  rendered=null, executedSource=null, onLoad, onRun, disabled=false,
  initialProjectId='', initialAssetId='', onDirty}) {
  const client = useMemo(() => suppliedClient || new ProjectAssetClient(), [suppliedClient]);
  const [projects, setProjects] = useState([]), [assets, setAssets] = useState([]);
  const [projectId, setProjectId] = useState(initialProjectId), [assetId, setAssetId] = useState(initialAssetId);
  const [name, setName] = useState('SQL investigation'), [document, setDocument] = useState(newNotebook());
  const [version, setVersion] = useState(0), [revision, setRevision] = useState('');
  const [revisions, setRevisions] = useState([]), [access, setAccess] = useState('owner');
  const [selected, setSelected] = useState(''), [policies, setPolicies] = useState({});
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('');
  const [reviewed, setReviewed] = useState(false), [saved, setSaved] = useState(JSON.stringify({name: 'SQL investigation', document: newNotebook()}));
  const [member, setMember] = useState('');
  const mounted = useRef(true);
  const dirty = saved !== '' && saved !== JSON.stringify({name, document});
  const readonly = access === 'viewer';
  const locked = disabled || busy;
  const cell = document.cells.find(item => item.id === selected);
  const bound = scope && sameScope(scope, document.scope);
  const canRetain = bound && cell?.kind === 'sql' && cell.source === executedSource && rendered;
  useEffect(() => {onDirty?.(dirty); return () => onDirty?.(false);}, [dirty, onDirty]);
  useModalCloseGuard(() => !busy && !dirty);
  useEffect(() => {const guard = event => {if(dirty) {event.preventDefault(); event.returnValue = '';}};
    window.addEventListener('beforeunload', guard); return () => window.removeEventListener('beforeunload', guard);}, [dirty]);
  const perform = async callback => {
    setBusy(true); setError(''); setNotice('');
    try {await callback();} catch(failure) {if(mounted.current) setError(failure.message || 'Notebook operation failed.');}
    finally {if(mounted.current) setBusy(false);}
  };
  const refresh = async () => setProjects(await client.listProjects());
  const load = async (pid, aid, requested=null) => {
    const latest = await client.asset(pid, aid);
    const value = requested ? await client.asset(pid, aid, requested) : latest;
    if(!mounted.current) return;
    if(value.asset_type !== NOTEBOOK_TYPE) throw new Error('Select a SQL notebook asset.');
    const content = validateNotebook(value.content);
    setDocument(content); setName(value.name); setVersion(latest.version); setAccess(value.access);
    setSelected(content.cells[0]?.id || ''); setReviewed(false);
    setSaved(requested ? '{}' : JSON.stringify({name: value.name, document: content}));
    setRevisions(await client.revisions(pid, aid));
    setNotice(requested ? `Loaded revision ${requested} as a draft; next save checks current revision ${latest.version}.` : `Loaded revision ${latest.version}. No SQL executed.`);
  };
  useEffect(() => {
    mounted.current = true;
    perform(async () => {await refresh(); if(initialProjectId && initialAssetId) await load(initialProjectId, initialAssetId);});
    return () => {mounted.current = false;};
  }, [client]);
  useEffect(() => {
    let active = true;
    if(!projectId) {setAssets([]); return undefined;}
    client.project(projectId).then(value => {if(active) {
      setAssets(value.assets.filter(item => item.asset_type === NOTEBOOK_TYPE)); setAccess(value.access);
    }}).catch(failure => {if(active) setError(failure.message);});
    return () => {active = false;};
  }, [client, projectId, version]);
  useEffect(() => {setPolicies(Object.fromEntries((rendered?.view_model?.columns || []).map((column, index) =>
    [index, sensitiveColumn.test(column.name) ? 'redact' : 'omit'])));}, [rendered]);
  const change = value => {setDocument(value); setReviewed(false);};
  const editCell = (id, update) => change({...document, cells: document.cells.map(item => item.id === id ? {...item, ...update} : item)});
  const reset = () => {
    const next = newNotebook(scope); setDocument(next); setName('SQL investigation'); setAssetId('');
    setVersion(0); setRevision(''); setRevisions([]); setSelected(''); setReviewed(false);
    setSaved(JSON.stringify({name: 'SQL investigation', document: next})); setNotice('New notebook. No SQL executed.');
  };
  const add = kind => {
    const id = crypto.randomUUID(), next = {id, kind, source: '', ...(kind === 'sql' ? {snapshot: null} : {})};
    change({...document, cells: [...document.cells, next]}); setSelected(id);
  };
  const save = () => perform(async () => {
    const id = assetId || crypto.randomUUID();
    const value = await client.saveAsset(projectId, id, notebookRequest(document, name, version, id));
    setAssetId(id); setVersion(value.version); setSaved(JSON.stringify({name, document}));
    setRevisions(await client.revisions(projectId, id)); setNotice(`Saved notebook revision ${value.version}. No SQL executed.`);
  });
  const download = () => perform(async () => {
    if(!reviewed || dirty || !assetId || !version) throw new Error('Save and review the notebook before sharing.');
    const value = await client.asset(projectId, assetId, version);
    const content = portableNotebook(value.content);
    const url = URL.createObjectURL(new Blob([JSON.stringify(content, null, 2)], {type: 'application/json'}));
    const anchor = window.document.createElement('a'); anchor.href = url; anchor.download = 'investigation.sql-notebook.json'; anchor.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000); setNotice('Shared file contains no local connection binding. No SQL executed.');
  });
  const move = direction => {
    const cells = [...document.cells], index = cells.findIndex(item => item.id === selected), next = index + direction;
    if(next < 0 || next >= cells.length) return;
    [cells[index], cells[next]] = [cells[next], cells[index]]; change({...document, cells});
  };
  return <Box component="section" aria-label="SQL notebook" sx={{p: 1, overflow: 'auto', minHeight: 150}}>
    <Alert severity="info">Notes, SQL and explicitly retained result pages. Opening, importing and sharing never execute SQL.
      {scope ? ' Run cell uses this SQL editor session with empty parameter bindings and query attributes. Native transaction controls and cancellation remain in the editor.' : 'To execute, open SQL notebook in a native MySQL SQL editor and load this project asset.'}</Alert>
    {error && <Alert severity="error">{error}</Alert>}{notice && <Alert severity="info">{notice}</Alert>}
    <Box sx={{display: 'flex', flexWrap: 'wrap', gap: 1, my: 1}}>
      <TextField select size="small" label="Notebook project" value={projects.some(item => item.project_id === projectId) ? projectId : ''} disabled={locked || (dirty && !!assetId)}
        sx={{minWidth: 180}} onChange={event => {setProjectId(event.target.value); setAssetId(''); setVersion(0); setRevision(''); setRevisions([]);}}>
        <MenuItem value="">Select project</MenuItem>{projects.map(item => <MenuItem key={item.project_id} value={item.project_id}>{item.name}</MenuItem>)}
      </TextField>
      <Button disabled={locked || dirty} onClick={() => perform(refresh)}>Refresh projects</Button>
      <Button disabled={locked || readonly} onClick={reset}>Discard draft / new notebook</Button>
      <TextField select size="small" label="Saved notebook" value={assets.some(item => item.asset_id === assetId) ? assetId : ''} sx={{minWidth: 180}}
        disabled={locked || dirty || !projectId} onChange={event => {const id = event.target.value; setAssetId(id); setRevision(''); if(id) perform(() => load(projectId, id));}}>
        <MenuItem value="">New notebook</MenuItem>{assets.map(item => <MenuItem key={item.asset_id} value={item.asset_id}>{item.name} (v{item.version})</MenuItem>)}
      </TextField>
      <TextField size="small" label="Notebook name" value={name} disabled={locked || readonly}
        onChange={event => {setName(event.target.value); setReviewed(false);}} />
      <Button disabled={locked || readonly || !projectId} onClick={save}>Save notebook revision</Button>
      <TextField select size="small" label="Notebook revision" value={revision} disabled={locked || dirty || !version}
        sx={{minWidth: 160}} onChange={event => setRevision(event.target.value)}>
        <MenuItem value="">Latest</MenuItem>{revisions.map(item => <MenuItem key={item.version} value={String(item.version)}>v{item.version}</MenuItem>)}
      </TextField>
      <Button disabled={locked || dirty || !assetId} onClick={() => perform(() => load(projectId, assetId, revision ? Number(revision) : null))}>Reload notebook</Button>
      <Button component="label" disabled={locked || dirty || readonly}>Import notebook
        <input hidden type="file" aria-label="Import SQL notebook file" accept=".json" onChange={event => {
          const file = event.target.files?.[0]; event.target.value = '';
          if(file) perform(async () => {
            if(file.size > NOTEBOOK_LIMIT) throw new Error('Notebook exceeds 2 MiB.');
            // Imported files have no authority over this editor's connection.
            const next = portableNotebook(JSON.parse(await file.text()));
            setDocument(next); setAssetId(''); setVersion(0); setRevisions([]); setRevision(''); setReviewed(false);
            setSelected(next.cells[0]?.id || ''); setSaved('{}'); setNotice('Imported an unbound draft. Bind explicitly before running.');
          });
        }} />
      </Button>
    </Box>
    <Box role="status">Saved revision: {version} · {dirty ? 'Unsaved draft' : 'Saved / empty'} · Access: {access}<br />
      Connection scope: {document.scope ? `${document.scope.engine} / ${document.scope.endpoint_id} / ${document.scope.database_target_id}` : 'Unbound portable notebook'}</Box>
    {scope && <Button disabled={locked || readonly || bound} onClick={() => {change(rebindNotebook(document, scope)); setNotice('Bound to this editor; previous result snapshots cleared.');}}>Bind to this SQL editor (clear snapshots)</Button>}
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', my: 1}}>
      <Button disabled={locked || readonly || document.cells.length >= 200} onClick={() => add('note')}>Add note</Button>
      <Button disabled={locked || readonly || document.cells.length >= 200} onClick={() => add('sql')}>Add SQL cell</Button>
      <TextField select size="small" label="Notebook cell" value={selected} sx={{minWidth: 180}} disabled={locked}
        onChange={event => setSelected(event.target.value)}><MenuItem value="">Select cell</MenuItem>
        {document.cells.map((item, index) => <MenuItem key={item.id} value={item.id}>{index + 1}. {item.kind}: {item.source.slice(0, 40)}</MenuItem>)}
      </TextField>
      <Button disabled={locked || readonly || !cell} onClick={() => move(-1)}>Move cell up</Button>
      <Button disabled={locked || readonly || !cell} onClick={() => move(1)}>Move cell down</Button>
      <Button disabled={locked || readonly || !cell} onClick={() => {change({...document, cells: document.cells.filter(item => item.id !== selected)}); setSelected('');}}>Remove cell</Button>
    </Box>
    {cell && <><TextField fullWidth multiline minRows={3} label={cell.kind === 'sql' ? 'Notebook SQL cell' : 'Notebook note'} value={cell.source}
      disabled={locked || readonly} onChange={event => editCell(cell.id, {source: event.target.value, ...(cell.kind === 'sql' ? {snapshot: null} : {})})} />
    {cell.kind === 'sql' && <Box sx={{my: 1}}>
      <Button disabled={locked || !bound || !onLoad} onClick={() => onLoad(cell.source)}>Load cell in SQL editor</Button>
      <Button disabled={locked || readonly || !onLoad} onClick={() => editCell(cell.id, {source: editorSource, snapshot: null})}>Replace cell from SQL editor</Button>
      <Button disabled={locked || !bound || !onRun || !cell.source.trim()} onClick={() => onRun(cell.source)}>Run selected SQL cell</Button>
      {canRetain && <Box><Box>Retain at most 100 rows from the displayed page. Columns default to omitted; sensitive names default to redacted.</Box>
        {(rendered.view_model?.columns || []).map((column, index) => <TextField key={index} select size="small" sx={{m: 0.5, minWidth: 160}}
          label={`Snapshot ${column.name}`} value={policies[index] || 'omit'} disabled={locked || readonly}
          onChange={event => setPolicies({...policies, [index]: event.target.value})}>
          <MenuItem value="omit">Omit</MenuItem><MenuItem value="redact">Redact</MenuItem><MenuItem value="retain">Retain value</MenuItem>
        </TextField>)}
        <Button disabled={locked || readonly} onClick={() => perform(async () => editCell(cell.id,
          {snapshot: retainedSnapshot(rendered, cell.source, scope, policies)}))}>Retain reviewed page snapshot</Button>
      </Box>}
      {cell.snapshot && <><Box component="pre" aria-label="Retained notebook snapshot" sx={{maxHeight: 220, overflow: 'auto'}}>{JSON.stringify(cell.snapshot, null, 2)}</Box>
        <Button disabled={locked || readonly} onClick={() => editCell(cell.id, {snapshot: null})}>Remove retained snapshot</Button></>}
    </Box>}</>}
    <FormControlLabel control={<Checkbox checked={reviewed} disabled={locked || dirty || !version}
      onChange={event => setReviewed(event.target.checked)} />} label="I reviewed notes, SQL literals and retained data for secrets before sharing this saved revision." />
    <Button disabled={locked || dirty || !reviewed || !version} onClick={download}>Export shareable notebook</Button>
    {access === 'owner' && <Box sx={{display: 'flex', gap: 1, mt: 1}}>
      <TextField size="small" label="Project viewer user ID" value={member} disabled={locked} onChange={event => setMember(event.target.value)} />
      <Button disabled={locked || !projectId || !/^\d+$/.test(member)} onClick={() => perform(async () => {
        await client.setMember(projectId, {principal_type: 'user', principal_id: Number(member), access_level: 'viewer'});
        setNotice('Viewer access granted to the entire project, including saved revisions. Database permissions are separate.');
      })}>Grant project viewer access (all assets and revisions)</Button>
    </Box>}
  </Box>;
}
SQLNotebook.propTypes = {client: PropTypes.object, scope: PropTypes.object, editorSource: PropTypes.string,
  rendered: PropTypes.object, executedSource: PropTypes.string, onLoad: PropTypes.func, onRun: PropTypes.func,
  disabled: PropTypes.bool, initialProjectId: PropTypes.string, initialAssetId: PropTypes.string, onDirty: PropTypes.func};
