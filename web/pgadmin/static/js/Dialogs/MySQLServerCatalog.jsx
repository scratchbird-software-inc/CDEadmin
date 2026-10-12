import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import {DDNViewerSurface} from '../cdeadmin_ui/integrations/ddn';
import {compactFormSx} from '../cdeadmin_ui/foundations/compactFormLayout';

export default function MySQLServerCatalog({post}) {
  const [result, setResult] = useState(null), [error, setError] = useState(''), [busy, setBusy] = useState(false);
  const [system, setSystem] = useState(true), [targets, setTargets] = useState([]), [scope, setScope] = useState('server');
  const [view, setView] = useState('inventory_1');
  const serial = useRef(0);
  useEffect(() => {
    serial.current++; setResult(null); setTargets([]); setScope('server'); setView('inventory_1'); setBusy(false); setError('');
    return () => {serial.current++;};
  }, [post]);
  const capture = async (expand=false) => {
    const token = ++serial.current;
    setBusy(true); setError('');
    try {
      const value = await post({action: 'mysql_server_catalog', request: {include_system: system, targets: expand ? targets : []}});
      if(token === serial.current) {setResult(value); setScope('server'); setView(value.snapshot.view);}
    } catch(failure) {if(token === serial.current) setError(failure.response?.data?.errormsg || failure.message || 'MySQL server capture failed');}
    finally {if(token === serial.current) setBusy(false);}
  };
  const shown = scope === 'server' ? result : result?.databases?.find(item => item.target_id === scope)?.capture;
  const download = () => {
    const content = {format: 'scratchrobin.mysql.server-collection@1', server_uuid: result.server_uuid,
      server: result.snapshot, databases: result.databases.map(item => ({target_id: item.target_id,
        snapshot: item.capture.snapshot, diagram: item.capture.diagram}))};
    const url = URL.createObjectURL(new Blob([JSON.stringify(content)], {type: 'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = 'mysql-server-ddn-collection.json'; link.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
  return <Box sx={{...compactFormSx, p: 1, overflow: 'auto', flex: 1}}>
    <FormReference formKey="mysql-server-catalog" />
    {error && <Alert severity="error">{error}</Alert>}
    <Alert severity="info">Credential-free native server metadata. Optional database captures are independent, explicitly selected registered targets. This is observational discovery; it does not create a consistent server backup or execute metadata.</Alert>
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', alignItems: 'center'}}>
      <FormControlLabel label="Include built-in system objects" control={<Checkbox checked={system} disabled={busy}
        onChange={event => setSystem(event.target.checked)} />} />
      <Button disabled={busy} onClick={() => capture()}>Capture server inventory</Button>
      <TextField select size="small" label="Registered databases to include" value={targets} disabled={busy || !result}
        slotProps={{select: {multiple: true}}} sx={{minWidth: 260}} onChange={event => setTargets(event.target.value)}>
        {(result?.registered_targets || []).map(item => <MenuItem value={item.target_id} key={item.target_id}>
          {item.display_name || item.database} ({item.database})</MenuItem>)}
      </TextField>
      <Button disabled={busy || !targets.length || targets.length > 32} onClick={() => capture(true)}>Capture selected databases</Button>
      <Button disabled={busy || !result} onClick={download}>Download DDN collection</Button>
      <TextField select size="small" label="Captured scope" value={scope} disabled={busy || !result}
        onChange={event => {
          const selected = event.target.value; setScope(selected);
          setView(selected === 'server' ? result.snapshot.view : result.databases.find(item => item.target_id === selected).capture.snapshot.view);
        }}>
        <MenuItem value="server">MySQL server</MenuItem>
        {(result?.databases || []).map(item => <MenuItem value={item.target_id} key={item.target_id}>
          {result.registered_targets.find(target => target.target_id === item.target_id)?.display_name || item.target_id}</MenuItem>)}
      </TextField>
      {shown?.views && <TextField select size="small" label="Server collection DDN view" value={view} disabled={busy}
        onChange={event => setView(event.target.value)}>
        {shown.views.map(item => <MenuItem value={item.id} key={item.id}>{item.label}</MenuItem>)}
      </TextField>}
    </Box>
    {(shown?.provenance?.warnings || []).map(warning => <Alert severity="warning" key={warning}>{warning}</Alert>)}
    {shown?.snapshot && <Box sx={{height: 550, minHeight: 250, overflow: 'auto'}}>
      <DDNViewerSurface presentation snapshot={{...shown.snapshot, view,
        entry: shown.views.find(item => item.id === view)?.entry || shown.snapshot.entry}} />
    </Box>}
  </Box>;
}
MySQLServerCatalog.propTypes = {post: PropTypes.func.isRequired};
