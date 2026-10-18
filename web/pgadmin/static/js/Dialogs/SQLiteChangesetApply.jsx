import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel,MenuItem,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';

const active=state => ['dispatching','active','committing','cancel_requested'].includes(state);
const kinds=['data','not_found','conflict','constraint','foreign_key'];
const initial={invert:false,ignore_noop:false,fk_no_action:false,foreign_keys:true,recursive_triggers:false,include_rebase:false,
  table_name:null,timeout_seconds:3600,conflicts:Object.fromEntries(kinds.map(kind => [kind,'abort']))};
const switches={invert:'Invert incoming changeset',ignore_noop:'Ignore native no-op conflicts',fk_no_action:'Use NO ACTION for native foreign keys',
  foreign_keys:'Enforce native foreign keys',recursive_triggers:'Enable recursive triggers on owned apply connection',include_rebase:'Write native rebase data'};

export default function SQLiteChangesetApply({post,databaseTargetId,endpointUrl,disabled}) {
  const [catalog,setCatalog]=useState(null),[sourceTarget,setSourceTarget]=useState(''),[sources,setSources]=useState(null),[sourceOffset,setSourceOffset]=useState(0),[input,setInput]=useState('');
  const [options,setOptions]=useState(initial),[receipt,setReceipt]=useState(null),[confirmed,setConfirmed]=useState(false);
  const [jobs,setJobs]=useState(null),[offset,setOffset]=useState(0),[files,setFiles]=useState(null),[remove,setRemove]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');const serial=useRef(0),downloads=useRef([]);
  const call=(operation,fields={}) => post({action:'sqlite_changeset_'+operation,request:{database_target_id:databaseTargetId,...fields}});
  useEffect(() => {
    serial.current++;setCatalog(null);setSourceTarget('');setSources(null);setSourceOffset(0);setInput('');setReceipt(null);setJobs(null);setOffset(0);setFiles(null);setConfirmed(false);setRemove(false);setBusy(false);setError('');
    return () => {serial.current++;downloads.current.forEach(close => close());downloads.current=[];};
  },[databaseTargetId]);
  useEffect(() => {
    if(!receipt?.job_id || !active(receipt.state))return undefined;
    let alive=true,timer;
    const poll=async () => {
      try {
        const value=await call('status',{job_id:receipt.job_id});if(!alive)return;setReceipt(value);
        if(active(value.state))timer=setTimeout(poll,400);
      } catch(failure) {if(alive)setError(failure.response?.data?.errormsg || failure.message);}
    };
    timer=setTimeout(poll,400);return () => {alive=false;clearTimeout(timer);};
  },[post,databaseTargetId,receipt?.job_id,active(receipt?.state)]);
  const perform=async (operation,fields={}) => {
    const token=serial.current;setBusy(true);setError('');
    try {
      const value=await call(operation,fields);if(token!==serial.current)return;
      if(operation==='catalog'){setCatalog(value);setSourceTarget(current => current || databaseTargetId);}
      else if(operation==='sources'){
        setSources(value);setInput(value.jobs.find(item => ['completed','artifact_verified'].includes(item.state) && !item.artifact_removed)?.job_id || '');
        setReceipt(current => current?.state==='reviewed' ? null : current);setConfirmed(false);
      }
      else if(operation==='list')setJobs(value);
      else if(operation==='files')setFiles(value);
      else {setReceipt(value);setConfirmed(false);setRemove(false);setFiles(null);}
    } catch(failure) {if(token===serial.current)setError(failure.response?.data?.errormsg || failure.message);}
    finally {if(token===serial.current)setBusy(false);}
  };
  const change=(name,value) => {setOptions(current => ({...current,[name]:value}));setReceipt(current => current?.state==='reviewed' ? null : current);setConfirmed(false);};
  const changeSource=value => {setSourceTarget(value);setSources(null);setSourceOffset(0);setInput('');setReceipt(current => current?.state==='reviewed' ? null : current);setConfirmed(false);};
  const selectInput=value => {setInput(value);setReceipt(current => current?.state==='reviewed' ? null : current);setConfirmed(false);};
  const selected=sources?.jobs.find(item => item.job_id===input);
  const blocked=busy || active(receipt?.state);
  const download=path => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{database_target_id:databaseTargetId,job_id:receipt.job_id,path},
      {action:'sqlite_changeset_download',prefix:'sqlite-apply',title:'SQLite native apply output download'}));}
    catch(failure) {setError(failure.message);}
  };
  return <Box component="details" sx={{my:1}}><summary>SQLite changeset application</summary>
    <Alert severity="info">Apply a verified native export to this registered destination using a separate owned connection. Query sessions and pending SQL work stay separate. Review conflict responses before committing native changes. Rebase data and output verification have separate receipts from database commit.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Button disabled={blocked} onClick={() => perform('catalog')}>Inspect native apply sources</Button>
    <Button disabled={busy} onClick={() => perform('list',{offset,limit:25})}>Load changeset apply receipts</Button>
    {catalog && <>
      {!catalog.helper_available && <Alert severity="warning">{catalog.unavailable_reason}</Alert>}
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
        <TextField select size="small" label="Native source database" value={sourceTarget} disabled={blocked} onChange={event => changeSource(event.target.value)}>
          {catalog.targets.map(target => <MenuItem key={target.target_id} value={target.target_id}>{target.display_name}</MenuItem>)}
        </TextField>
        <Button disabled={blocked || !sourceTarget} onClick={() => perform('sources',{source_database_target_id:sourceTarget,offset:sourceOffset,limit:25})}>Load verified source exports</Button>
      </Box>
      {sources && <>
        <TextField select size="small" label="Native source export" value={input} disabled={blocked} onChange={event => selectInput(event.target.value)} sx={{minWidth:420}}>
          {sources.jobs.filter(item => ['completed','artifact_verified'].includes(item.state) && !item.artifact_removed).map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.options.kind}</MenuItem>)}
        </TextField>
        <Button disabled={blocked || sourceOffset===0} onClick={() => {const next=Math.max(0,sourceOffset-25);setSourceOffset(next);perform('sources',{source_database_target_id:sourceTarget,offset:next,limit:25});}}>Previous source exports</Button>
        <Button disabled={blocked || !sources.more} onClick={() => {setSourceOffset(sourceOffset+25);perform('sources',{source_database_target_id:sourceTarget,offset:sourceOffset+25,limit:25});}}>Next source exports</Button>
      </>}
      <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>{kinds.map(kind => <TextField key={kind} select size="small" label={'Native '+kind+' conflict response'} value={options.conflicts[kind]} disabled={blocked}
        onChange={event => change('conflicts',{...options.conflicts,[kind]:event.target.value})}>
        <MenuItem value="abort">Abort and roll back owned changes</MenuItem><MenuItem value="omit">{kind==='foreign_key' ? 'Keep changes, including foreign-key violations' : 'Omit conflicting change'}</MenuItem>
        {['data','conflict'].includes(kind) && <MenuItem value="replace">Replace conflicting target values</MenuItem>}
      </TextField>)}</Box>
      <Alert severity="warning">FOREIGN KEY omit can commit violations. Native replacement is supported only for DATA and CONFLICT. Native counts distinguish compatible selected changes from actual conflict responses.</Alert>
      <Box>{Object.entries(switches).map(([key,label]) => <FormControlLabel key={key} label={label} control={<Checkbox checked={options[key]} disabled={blocked} onChange={event => change(key,event.target.checked)} />} />)}</Box>
      <TextField multiline size="small" label="Apply only exact native table (empty means all tables)" value={options.table_name ?? ''} disabled={blocked} onChange={event => change('table_name',event.target.value || null)} />
      <TextField size="small" type="number" label="Native apply maximum seconds" value={options.timeout_seconds ?? ''} disabled={blocked} onChange={event => change('timeout_seconds',event.target.value==='' ? null : Number(event.target.value))} />
      <Button disabled={blocked || disabled || !selected || !catalog.helper_available} onClick={() => perform('review',{source_database_target_id:sourceTarget,source_job_id:input,path:'capture.'+selected.options.kind,options})}>Review native changeset application</Button>
    </>}
    {jobs && <Box>
      <TextField select size="small" label="Retained native apply receipt" value={jobs.jobs.some(item => item.job_id===receipt?.job_id) ? receipt.job_id : ''} disabled={blocked}
        onChange={event => perform('status',{job_id:event.target.value})} sx={{minWidth:420}}>
        {jobs.jobs.map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} — {item.state}</MenuItem>)}
      </TextField>
      <Button disabled={busy || offset===0} onClick={() => {const next=Math.max(0,offset-25);setOffset(next);perform('list',{offset:next,limit:25});}}>Previous native apply receipts</Button>
      <Button disabled={busy || !jobs.more} onClick={() => {setOffset(offset+25);perform('list',{offset:offset+25,limit:25});}}>Next native apply receipts</Button>
    </Box>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={receipt.state==='completed' ? 'success' : 'info'}>Native apply {receipt.job_id}: {receipt.state}. Automatic retry is disabled.</Alert>
      {receipt.warnings?.map(message => <Alert key={message} severity="warning">{message}</Alert>)}
      {receipt.error_message && <Alert severity="warning">{receipt.error_message}</Alert>}
      {receipt.state==='reviewed' && <>
        <FormControlLabel label="Confirm native changes and commit to this destination" control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
        <Button disabled={busy || disabled || !confirmed} onClick={() => perform('start',{job_id:receipt.job_id,review_digest:receipt.review_digest,confirmed:true})}>Apply reviewed native changeset</Button>
      </>}
      {active(receipt.state) && receipt.state!=='committing' && <Button disabled={busy} onClick={() => perform('cancel',{job_id:receipt.job_id})}>Cancel native changeset application</Button>}
      <Box role="status">Native apply acknowledgement: {receipt.native_returned ? 'received' : 'unconfirmed'}. Commit acknowledgement: {receipt.commit_returned ? 'received' : 'unconfirmed'}. Owned rollback: {receipt.owned_rollback_confirmed ? 'confirmed' : 'unconfirmed'}.</Box>
      {receipt.native_apply && <Box component="pre" aria-label="Native SQLite conflict observations" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(receipt.native_apply,null,2)}</Box>}
      {!active(receipt.state) && receipt.state!=='reviewed' && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('reconcile',{job_id:receipt.job_id})}>Verify native apply output</Button>}
      {(receipt.state==='completed' || receipt.output_artifact_verified) && !receipt.artifact_removed && <Button disabled={busy} onClick={() => perform('files',{job_id:receipt.job_id,offset:0,limit:25})}>Load native apply output files</Button>}
      {files && files.files.map(row => <Box key={row.path}>{row.path} ({row.size} bytes) <Button disabled={busy || !endpointUrl || files.artifact_removed} onClick={() => download(row.path)}>Download apply {row.path}</Button></Box>)}
      {!active(receipt.state) && !receipt.artifact_removed && <>
        <FormControlLabel label="Remove native apply output files; retain the operation receipt" control={<Checkbox checked={remove} disabled={busy} onChange={event => setRemove(event.target.checked)} />} />
        <Button disabled={busy || !remove} onClick={() => perform('remove_artifact',{job_id:receipt.job_id,confirmation:receipt.job_id})}>Remove native apply output</Button>
      </>}
      <Box component="details"><summary>Native SQLite apply receipt</summary><Box component="pre" aria-label="Native SQLite apply receipt" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
SQLiteChangesetApply.propTypes={post:PropTypes.func.isRequired,databaseTargetId:PropTypes.string.isRequired,endpointUrl:PropTypes.string,disabled:PropTypes.bool};
