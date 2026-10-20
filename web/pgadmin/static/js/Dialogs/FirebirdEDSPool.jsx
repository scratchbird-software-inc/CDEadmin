import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export default function FirebirdEDSPool({post,databaseTargetId,sessionId,ensureSession,disabled=false,onBusyChange,onBlocked}) {
  const [action,setAction]=useState('set_size'),[value,setValue]=useState('32'),[unit,setUnit]=useState('SECOND');
  const [record,setRecord]=useState(null),[inventory,setInventory]=useState(null),[receipts,setReceipts]=useState(null);
  const [confirmation,setConfirmation]=useState(''),[confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[awaiting,setAwaiting]=useState(false),[error,setError]=useState('');
  const serial=useRef(0),previousSession=useRef(sessionId),ownsBusy=useRef(false);
  useEffect(() => {
    serial.current++;setRecord(null);setInventory(null);setReceipts(null);setConfirmation('');setConfirmed(false);setBusy(false);setAwaiting(false);setError('');
    return () => {serial.current++;if(ownsBusy.current)onBusyChange(false);ownsBusy.current=false;};
  },[post,databaseTargetId,onBusyChange]);
  useEffect(() => {
    if(previousSession.current && previousSession.current!==sessionId) {
      serial.current++;setRecord(null);setInventory(null);setBusy(false);setAwaiting(false);setConfirmation('');setConfirmed(false);
      if(ownsBusy.current)onBusyChange(false);ownsBusy.current=false;
      setError('The original native attachment changed. Read retained receipts or inspect the new engine process.');
    }
    previousSession.current=sessionId;
  },[sessionId,onBusyChange]);
  const running=record?.native_operation_running===true;
  const receive=(result,live=true) => {
    setRecord(result);setAwaiting(false);
    if(live) {
      const active=result.native_operation_running===true;ownsBusy.current=active;onBusyChange(active);
      if(result.session_reuse_blocked)onBlocked?.();
    }
  };
  const run=async (operation,archived=false,selected=record,offset=0) => {
    const token=++serial.current;setBusy(true);setError('');
    if(!archived){ownsBusy.current=true;onBusyChange(true);}
    let keepBusy=false;
    try {
      const active=archived ? null : sessionId || await ensureSession();
      if(token!==serial.current)return;
      const request=operation==='inventory' ? {operation} : operation==='list' ? {operation,offset,limit:25} :
        operation==='review' ? {operation,draft:{action,...(action.startsWith('set_') ? {value:value==='' ? null : Number(value)} : {}),...(action==='set_lifetime' ? {unit} : {})}} :
          {operation,review_id:selected.review_id,...(operation==='apply' ? {review_digest:selected.review_digest,confirmation,confirmed} : operation==='remove' ? {review_digest:selected.review_digest,confirmed:confirmation===selected.review_id} : operation==='discard' ? {review_digest:selected.review_digest} : {})};
      if(operation==='apply')setAwaiting(true);
      const result=await post({action:archived ? 'firebird_eds_pool_receipts' : 'firebird_eds_pool',
        database_target_id:databaseTargetId,...(!archived ? {session_id:active} : {}),request});
      if(token===serial.current) {
        if(operation==='inventory')setInventory(result);
        else if(operation==='list')setReceipts(result);
        else if(operation==='remove'){setRecord(null);setReceipts(null);}
        else {receive(result,!archived);keepBusy=result.native_operation_running===true;}
        setConfirmation('');setConfirmed(false);
      }
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message || 'Read the retained EDS receipt before preparing another command.');}
    finally {if(token===serial.current){setBusy(false);if(!archived){ownsBusy.current=keepBusy;onBusyChange(keepBusy);}}}
  };
  useEffect(() => {
    if(!running || busy || !sessionId)return undefined;
    const token=serial.current,timer=setTimeout(async () => {
      try {
        const result=await post({action:'firebird_eds_pool',database_target_id:databaseTargetId,session_id:sessionId,
          request:{operation:'receipt',review_id:record.review_id}});
        if(token===serial.current)receive(result);
      } catch(failure) {if(token===serial.current)setError(failure.message || 'Read the retained EDS operation receipt.');}
    },500);
    return () => clearTimeout(timer);
  },[record,busy,sessionId,post,databaseTargetId]);
  const locked=disabled || busy || awaiting || running || (!record?.archived_read_only && record?.session_reuse_blocked);
  const change=setter => event => {setter(event.target.value);setRecord(null);setConfirmation('');setConfirmed(false);};
  return <Box component="details" sx={{p:1}}><summary>Firebird external connection pool</summary><FormReference formKey="firebird-eds-pool">
    <Alert severity="warning">This pool belongs to the native engine process and can be shared by other attachments and databases. Changes take effect immediately, survive transaction rollback, and do not update configuration files. The original query attachment owns this workflow.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {awaiting && <Alert severity="warning">Read the existing EDS receipt before dispatching another command.</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <Button disabled={locked} onClick={() => run('inventory')}>Inspect native EDS pool</Button>
      <TextField select size="small" label="Native EDS pool action" value={action} disabled={locked} onChange={change(setAction)}>
        {[['set_size','Set pool size'],['set_lifetime','Set native lifetime'],['clear_all','Clear all pool bindings'],['clear_oldest','Clear expired idle connections']].map(([key,label]) => <MenuItem key={key} value={key}>{label}</MenuItem>)}
      </TextField>
      {action.startsWith('set_') && <TextField size="small" label="Native EDS pool quantity" value={value} disabled={locked} onChange={change(setValue)} />}
      {action==='set_lifetime' && <TextField select size="small" label="Native EDS lifetime unit" value={unit} disabled={locked} onChange={change(setUnit)}>
        {['SECOND','MINUTE','HOUR'].map(name => <MenuItem key={name} value={name}>{name}</MenuItem>)}</TextField>}
      <Button disabled={locked} onClick={() => run('review')}>Review native EDS pool change</Button>
      <Button disabled={busy || running || awaiting} onClick={() => run('list',true)}>Load retained EDS receipts</Button>
    </Box>
    {inventory && <Box component="pre" aria-label="Native Firebird EDS pool" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(inventory,null,2)}</Box>}
    {receipts && <Box>{receipts.receipts.map(item => <Button key={item.review_id} disabled={busy || running || awaiting}
      onClick={() => run('receipt',true,item)}>Inspect EDS receipt {item.review_id}</Button>)}
    <Button disabled={busy || running || awaiting || !receipts.offset} onClick={() => run('list',true,null,Math.max(0,receipts.offset-25))}>Previous EDS receipt page</Button>
    <Button disabled={busy || running || awaiting || !receipts.more} onClick={() => run('list',true,null,receipts.offset+25)}>Next EDS receipt page</Button>
    </Box>}
    {record && <Box>
      <Alert severity={record.state==='unknown_outcome' ? 'warning' : 'info'}>Native EDS change: {record.state}. Native acknowledgement: {String(Boolean(record.native_acknowledged))}. Current global pool state is not inferred from this receipt.</Alert>
      {record.warnings?.map(warning => <Alert key={warning} severity="warning">{warning}</Alert>)}
      <Box component="pre" aria-label="Reviewed Firebird EDS SQL" sx={{whiteSpace:'pre-wrap'}}>{record.source}</Box>
      {record.state==='reviewed' && !record.archived_read_only && <Box>
        <TextField size="small" label="Confirm native EDS engine process ID" value={confirmation} disabled={locked} onChange={event => setConfirmation(event.target.value)} />
        <FormControlLabel label="I reviewed the shared process scope and effects outside rollback" control={<Checkbox checked={confirmed} disabled={locked} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={locked || !confirmed || confirmation!==record.native_before?.server_process_id} onClick={() => run('apply')}>Apply reviewed EDS change once</Button>
        <Button disabled={busy || awaiting} onClick={() => run('discard')}>Discard EDS review</Button>
      </Box>}
      <Button disabled={busy} onClick={() => run('receipt',!sessionId || record.archived_read_only)}>Read native EDS receipt</Button>
      <Button disabled={busy || !running} onClick={() => run('cancel')}>Cancel active EDS command</Button>
      {record.archived_read_only && (!record.native_dispatch_admitted || record.last_native_phase==='session_release') && <Box>
        <Alert severity="info">Removing this saved receipt does not change the native pool or undo its effects. Unresolved dispatch evidence must be retained.</Alert>
        <TextField size="small" label="Confirm EDS receipt ID for removal" value={confirmation} disabled={busy} onChange={event => setConfirmation(event.target.value)} />
        <Button disabled={busy || confirmation!==record.review_id} onClick={() => run('remove',true)}>Remove retained EDS receipt</Button>
      </Box>}
      <Box component="pre" aria-label="Firebird EDS operation receipt" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(record,null,2)}</Box>
    </Box>}
  </FormReference></Box>;
}
FirebirdEDSPool.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,
  sessionId:PropTypes.string,ensureSession:PropTypes.func.isRequired,disabled:PropTypes.bool,
  onBusyChange:PropTypes.func.isRequired,onBlocked:PropTypes.func};
