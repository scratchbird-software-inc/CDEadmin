import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';
import {useEffect, useMemo, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

const MAX_BYTES = 64 * 1024 * 1024;
export function catalogBundle(endpoint, entries) {
  const q = JSON.stringify;
  const records = entries.map((entry, index) => `record db_${index} ${q(entry.label)} {
    uid: ${q('firebird:' + endpoint.endpoint_id + ':' + entry.target_id + ':database')};
    x_record: {target_id:${q(entry.target_id)},status:${q(entry.status)},coverage:${q(entry.catalog?.provenance?.coverage || 'unavailable')},objects:${q(String(entry.catalog?.provenance?.objects ?? 'unknown'))}};
  }`).join('\n');
  const source = `ddn "0.5"; module "scratchrobin.firebird.server";
    data databases {${records}}
    view server "Registered Firebird databases" {data: [@databases]; projection {kind: table; profile: "table.records@1";
      records: [${entries.map((_, index) => '@databases.db_' + index).join(',')}]; columns: [{key:"name",label:"Database"},{key:"x_record.status",label:"Capture"},
      {key:"x_record.coverage",label:"Coverage"},{key:"x_record.objects",label:"Objects"}];}}`;
  return {format: 'scratchrobin.firebird.server-catalog@1',
    endpoint: {endpoint_id: endpoint.endpoint_id, display_name: endpoint.display_name},
    scope: 'selected registered databases', consistency: 'independent database observations; not an atomic server snapshot',
    captured_at: new Date().toISOString(), complete: entries.length > 0 && entries.every(item =>
      item.status === 'captured' && item.catalog.provenance.coverage === 'visible-catalog'),
    overview: {format: 'ddn-workspace@1', entry: 'server.ddn', view: 'server', files: {'server.ddn': source}}, entries};
}

export default function FirebirdServerCatalog({endpoint, targets, post}) {
  const [selected, setSelected] = useState([]), [entries, setEntries] = useState([]);
  const [includeSystem, setIncludeSystem] = useState(false), [refresh, setRefresh] = useState(true);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [view, setView] = useState('server');
  const generation = useRef(0), stop = useRef(false), running = useRef(false);
  useEffect(() => {
    generation.current++; stop.current = true; running.current = false; setSelected([]); setEntries([]); setBusy(false); setError(''); setView('server');
    return () => {generation.current++; stop.current = true;};
  }, [post, endpoint.endpoint_id]);
  const bundle = useMemo(() => catalogBundle(endpoint, entries), [endpoint, entries]);
  const capture = async () => {
    if (running.current) return;
    const chosen = targets.filter(item => selected.includes(item.target_id));
    if (!chosen.length || chosen.length > 256) {setError('Select between 1 and 256 registered databases.'); return;}
    const token = ++generation.current;
    running.current = true; stop.current = false; setBusy(true); setError(''); setView('server');
    const results = chosen.map(item => ({target_id: item.target_id,
      label: item.display_name || item.label || item.database || item.target_id, status: 'not-attempted'}));
    setEntries([...results]);
    try {
      for (let index = 0; index < results.length; index++) {
        if (stop.current || token !== generation.current) break;
        results[index] = {...results[index], status: 'capturing'}; setEntries([...results]);
        try {
          const catalog = await post({action: 'firebird_registered_catalog', request: {
            target_id: results[index].target_id, include_system: includeSystem, refresh,
          }});
          if (token !== generation.current) return;
          if (catalog.target_id !== results[index].target_id || catalog.provenance?.database_target_id !== results[index].target_id ||
              catalog.provenance?.endpoint_id !== endpoint.endpoint_id) throw new Error('Catalog identity differs from the requested registration.');
          const candidate = {...results[index], status: 'captured', catalog};
          const draft = [...results]; draft[index] = candidate;
          if (new TextEncoder().encode(JSON.stringify(catalogBundle(endpoint, draft))).length > MAX_BYTES) {
            results[index] = {...results[index], status: 'size-limit'}; stop.current = true;
            setError('The 64 MiB bundle limit was reached. Capture the remaining databases separately.');
          } else results[index] = candidate;
        } catch (failure) {
          if (token !== generation.current) return;
          results[index] = {...results[index], status: [401, 403].includes(failure.response?.status) ? 'inaccessible' : 'failed'};
        }
        setEntries([...results]);
      }
    } finally {if (token === generation.current) {running.current = false; setBusy(false);}}
  };
  const download = (value, name) => {
    const url = URL.createObjectURL(new Blob([JSON.stringify(value)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = name; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  const chosen = entries.find(item => item.target_id === view);
  return <Box data-cde-compact-form sx={{p: 2, overflow: 'auto', ...compactFormSx}}>
    <FormReference formKey="firebird-server-catalog" />
    <Alert severity="info">Capture metadata from registered databases on this endpoint. Each uses its authorized catalog connection. These are independent observations, not an atomic server backup. Unregistered database files and row data are not captured.</Alert>
    <Button disabled={busy} onClick={() => setSelected(targets.map(item => item.target_id))}>Select all registered databases</Button>
    <Button disabled={busy} onClick={() => setSelected([])}>Clear database selection</Button>
    <Box>{targets.map(target => <FormControlLabel key={target.target_id} label={target.display_name || target.label || target.database || target.target_id}
      control={<Checkbox disabled={busy} checked={selected.includes(target.target_id)} onChange={() => setSelected(old =>
        old.includes(target.target_id) ? old.filter(item => item !== target.target_id) : [...old, target.target_id])} />} />)}</Box>
    <FormControlLabel label="Include system objects" control={<Checkbox disabled={busy} checked={includeSystem} onChange={event => setIncludeSystem(event.target.checked)} />} />
    <FormControlLabel label="Refresh each native catalog" control={<Checkbox disabled={busy} checked={refresh} onChange={event => setRefresh(event.target.checked)} />} />
    <Button disabled={busy || !selected.length} onClick={capture}>Capture selected database catalogs</Button>
    <Button disabled={!busy} onClick={() => {stop.current = true;}}>Stop after current database</Button>
    {error && <Alert severity="error">{error}</Alert>}
    {!!entries.length && <>
      <Alert severity={bundle.complete ? 'info' : 'warning'}>{bundle.complete ? 'All selected visible catalogs captured.' : 'Capture is incomplete. Failed, inaccessible and unattempted databases remain listed.'}</Alert>
      <Button disabled={busy} onClick={() => download(bundle, 'firebird-server-catalog.json')}>Download server catalog bundle</Button>
      <TextField select label="Captured catalog view" value={view} onChange={event => setView(event.target.value)}>
        <MenuItem value="server">Server overview</MenuItem>
        {entries.filter(item => item.catalog).map(item => <MenuItem key={item.target_id} value={item.target_id}>{item.label}</MenuItem>)}
      </TextField>
      {entries.map(item => <Box key={item.target_id}>{item.label}: {item.status} — {item.catalog?.provenance?.coverage || 'no catalog observation'}</Box>)}
      {chosen?.catalog && <Button onClick={() => download(chosen.catalog.snapshot, `firebird-${chosen.target_id}.ddn-workspace.json`)}>Download this database DDN</Button>}
      <Box sx={{minHeight: 400}}><DDNViewerSurface key={view} snapshot={chosen?.catalog?.snapshot || bundle.overview} /></Box>
    </>}
  </Box>;
}
FirebirdServerCatalog.propTypes = {endpoint: PropTypes.object.isRequired, targets: PropTypes.array.isRequired, post: PropTypes.func.isRequired};
