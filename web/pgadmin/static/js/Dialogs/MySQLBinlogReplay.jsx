import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLBinlogReplay({post,engine='mysql'}) {
  const prefix=engine+'_binlog_replay_',identityKey=engine==='mariadb' ? 'server_uid' : 'server_uuid';
  const identityLabel=engine==='mariadb' ? 'server UID' : 'server UUID';
  const [family,setFamily]=useState('shell'),[boundaries,setBoundaries]=useState(null),[start,setStart]=useState(null),[stop,setStop]=useState(null);
  const raw=engine==='mysql' && family==='raw';
  const [target,setTarget]=useState(null),[sources,setSources]=useState(null),[source,setSource]=useState('');
  const [archives,setArchives]=useState(null),[archive,setArchive]=useState('');
  const [mode,setMode]=useState('all'),[gtid,setGtid]=useState(''),[confirmation,setConfirmation]=useState(''),[timeout,setTimeoutValue]=useState(3600);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null),[facts,setFacts]=useState(null),[ack,setAck]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  useEffect(() => {generation.current++;setFamily('shell');setBoundaries(null);setStart(null);setStop(null);setTarget(null);setSources(null);setSource('');setArchives(null);setArchive('');setReview(null);setReceipt(null);setJobs(null);setFacts(null);setAck('');setConfirmation('');setBusy(false);setError('');return () => {generation.current++;};},[post,engine]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:prefix+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native replay request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:prefix+'status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[post,engine,receipt?.job_id,receipt?.state]);
  const change=setter => event => {setter(event.target.value);setReview(null);};
  const archiveRequest=request => raw ? {...request,archive_family:'raw'} : request;
  const loadBoundaries=offset => run('boundaries',archiveRequest({source_server_id:source,archive_job_id:archive,offset,limit:100}),setBoundaries);
  const selectedOptions=() => ({target_confirmation:confirmation,timeout_seconds:timeout,stop_mode:mode,
    ...(raw ? {start_file:start?.file ?? null,start_position:start?.position ?? null,stop_file:mode==='all' ? null : stop?.file,stop_position:mode==='all' ? null : stop?.position} : {stop_gtid:mode==='all' ? null : gtid})});
  const loadJobs=offset => run('list',{offset,limit:25},setJobs);
  const inspect=job => run('status',{job_id:job.job_id},value => {setReceipt(value);setFacts(null);setAck('');});
  const save=() => {
    const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=engine+'-replay-'+receipt.job_id+'.json';link.click();
    window.setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <Alert severity="warning">Replay changes from a sealed whole-server archive onto this separate target. Restore and verify a compatible base first. Transactions can commit individually; cancellation does not undo them. Native utility return and GTID coverage do not verify recovered data or production cutover.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    {engine==='mysql' && <TextField disabled={busy} select size="small" label="Archive format" value={family} onChange={event => {generation.current++;setFamily(event.target.value);setTarget(null);setArchives(null);setArchive('');setBoundaries(null);setStart(null);setStop(null);setMode('all');setReview(null);}}><MenuItem value="shell">MySQL Shell archive</MenuItem><MenuItem value="raw">MySQL raw closed logs</MenuItem></TextField>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <Button disabled={busy} onClick={() => run('inspect',archiveRequest({}),value => {setTarget(value);setReview(null);})}>Inspect replay target</Button>
      <Button disabled={busy} onClick={() => run('sources',{offset:0,limit:25},setSources)}>Load archive sources</Button>
      <Button disabled={busy} onClick={() => loadJobs(0)}>Load replay jobs</Button>
    </Box>
    {target && <Box component="details" open><summary>Native replay target: {target.identity[identityKey]}</summary><Box component="pre" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(target,null,2)}</Box></Box>}
    {sources && <>
      <TextField disabled={busy} select size="small" label="Owned archive source" value={source} sx={{minWidth:280}} onChange={event => {setSource(event.target.value);setArchives(null);setArchive('');setBoundaries(null);setStart(null);setStop(null);setReview(null);}}>
        {sources.sources.map(item => <MenuItem key={item.server_id} value={item.server_id}>{item.name} ({item.server_id})</MenuItem>)}
      </TextField>
      <TablePagination component="div" count={sources.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={sources.offset/25} onPageChange={(_event,next) => run('sources',{offset:next*25,limit:25},value => {setSources(value);setSource('');setArchives(null);setArchive('');setReview(null);})} />
      <Button disabled={busy || source===''} onClick={() => run('archives',archiveRequest({source_server_id:source,offset:0,limit:25}),setArchives)}>Load sealed archives</Button>
    </>}
    {archives && <>
      <TextField disabled={busy} select size="small" label="Sealed native archive" value={archive} sx={{minWidth:380}} onChange={event => {setArchive(event.target.value);setBoundaries(null);setStart(null);setStop(null);setReview(null);}}>
        {archives.jobs.filter(item => ['completed','artifact_verified'].includes(item.state) && !item.artifact_removed && item.native_process_termination_confirmed===true).map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} ({item.result?.artifact?.total_bytes} bytes)</MenuItem>)}
      </TextField>
      <TablePagination component="div" count={archives.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={archives.offset/25} onPageChange={(_event,next) => run('archives',archiveRequest({source_server_id:source,offset:next*25,limit:25}),value => {setArchives(value);setArchive('');setReview(null);})} />
      {archives.unavailable_job_ids?.length>0 && <Alert severity="warning">Some archive receipts are unavailable: {archives.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {raw && <Box sx={{my:1}}>
      <Alert severity="info">Raw replay uses native mysqlbinlog and mysql 9.7 clients. The target needs native backup privileges to observe its dispatch position. Named GTIDs already present are skipped. Anonymous recovery resumes only from an explicitly selected start after independent data verification.</Alert>
      <Button disabled={busy || !archive} onClick={() => loadBoundaries(0)}>Inspect native transaction groups</Button>
      <Button disabled={busy} onClick={() => {setStart(null);setStop(null);setMode('all');setReview(null);}}>Use whole archive</Button>
      <Box>Start: {start ? start.file+' @ '+start.position : 'archive beginning'}. Stop: {mode==='all' ? 'archive end' : mode+' '+(stop ? stop.file+' @ '+stop.position : 'select a native group')}.</Box>
      {boundaries && <>
        <Table size="small" aria-label="Native raw transaction groups"><TableHead><TableRow>{['Group','File','Position','Event time (UTC)','Native group','Selection'].map(label => <TableCell key={label}>{label}</TableCell>)}</TableRow></TableHead><TableBody>{boundaries.groups.map((group,index) => <TableRow key={group.file+'@'+group.position}><TableCell>{boundaries.offset+index+1}</TableCell><TableCell>{group.file}</TableCell><TableCell>{group.position}</TableCell><TableCell>{group.event_time_utc}</TableCell><TableCell>{group.event_type===34 ? 'anonymous' : group.event_type===42 ? 'tagged GTID' : 'GTID'}</TableCell><TableCell>
          <Button disabled={busy || !['OFF','OFF_PERMISSIVE'].includes(target?.state?.gtid_mode)} aria-label={'Start raw replay at '+group.file+'@'+group.position} onClick={() => {setStart(group);setReview(null);}}>Start here</Button>
          <Button disabled={busy} aria-label={'Stop raw replay before '+group.file+'@'+group.position} onClick={() => {setStop(group);setMode('before');setReview(null);}}>Stop before</Button>
          <Button disabled={busy} aria-label={'Stop raw replay after '+group.file+'@'+group.position} onClick={() => {setStop(group);setMode('after');setReview(null);}}>Stop after</Button>
        </TableCell></TableRow>)}</TableBody></Table>
        <TablePagination component="div" count={boundaries.total} rowsPerPage={100} rowsPerPageOptions={[100]} page={boundaries.offset/100} onPageChange={(_event,next) => loadBoundaries(next*100)} />
        <Box>Times describe event headers; they are not commit-time recovery targets. Sealed bytes and selected boundaries are checked before execution.</Box>
      </>}
    </Box>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      {!raw && <TextField disabled={busy} select size="small" label="Replay boundary" value={mode} onChange={change(setMode)}><MenuItem value="all">All archived transactions</MenuItem><MenuItem value="before">Stop before GTID</MenuItem><MenuItem value="after">Stop after GTID</MenuItem></TextField>}
      {!raw && mode!=='all' && <TextField disabled={busy} size="small" label="Native stop GTID" value={gtid} onChange={change(setGtid)} />}
      <TextField disabled={busy} size="small" label={'Confirm target '+identityLabel} value={confirmation} onChange={change(setConfirmation)} />
      <TextField disabled={busy} size="small" type="number" label="Runtime seconds (blank: no deadline)" value={timeout ?? ''} onChange={event => {setTimeoutValue(event.target.value==='' ? null : Number(event.target.value));setReview(null);}} />
      <Button disabled={busy || !target || source==='' || !archive || confirmation!==target.identity[identityKey]} onClick={() => run('review',archiveRequest({source_server_id:source,archive_job_id:archive,options:selectedOptions()}),setReview)}>Review replay</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native replay review" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify({target:review.target,source_archive:review.source_archive,options:review.options,execution_host:review.execution_host},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setFacts(null);setAck('');setReview(current => ({...current,state:value.state}));})}>Confirm and start replay</Button>
    </Box>}
    {jobs && <>
      <Table size="small" aria-label={'Native '+(engine==='mariadb' ? 'MariaDB' : 'MySQL')+' replay jobs'}><TableHead><TableRow>{['Job','State','Native load','Receipt'].map(value => <TableCell key={value}>{value}</TableCell>)}</TableRow></TableHead><TableBody>{jobs.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.state}</TableCell><TableCell>{job.native_load_outcome}</TableCell><TableCell><Button disabled={busy} aria-label={'Inspect replay '+job.job_id} onClick={() => inspect(job)}>Inspect</Button></TableCell></TableRow>)}</TableBody></Table>
      <TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={jobs.offset/25} onPageChange={(_event,next) => loadJobs(next*25)} />
      {jobs.unavailable_job_ids?.length>0 && <Alert severity="warning">Some replay receipts are unavailable: {jobs.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={receipt.state==='unknown' ? 'warning' : 'info'}>Replay {receipt.job_id}: {receipt.state}. Native load: {receipt.native_load_outcome}. {receipt.state==='unknown' && ('The outcome is uncertain. '+(receipt.target_state_acknowledged_at ? '' : 'This target is fenced. ')+'This operation will not replay automatically.')} Recovered data has not been independently verified.</Alert>
      <Button disabled={busy} onClick={() => inspect(receipt)}>Refresh replay receipt</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !receipt.utility_cancellation_available} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel replay</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={() => run('reconcile',{job_id:receipt.job_id},value => {setReceipt(value);setFacts(value);setAck('');})}>Inspect current target facts</Button>
      <Button onClick={save}>Download replay receipt</Button>
      {facts && <Box component="pre" aria-label="Native replay reconciliation" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(facts.interrupted_utility_observation ?
        {...facts.reconciliation,native_utilities:facts.interrupted_utility_observation} : facts.reconciliation,null,2)}</Box>}
      {receipt.state==='unknown' && !receipt.target_state_acknowledged_at && facts && <Box sx={{display:'flex',gap:1,my:1}}>
        <TextField disabled={busy} size="small" label={engine==='mariadb' ? 'Acknowledge uncertain target server UID' : 'Acknowledge uncertain target UUID'} value={ack} onChange={event => setAck(event.target.value)} />
        <Button disabled={busy || receipt.native_process_termination_confirmed!==true || facts.reconciliation?.native_lock_free!==true || ack!==receipt.target[identityKey]} onClick={() => run('acknowledge',{job_id:receipt.job_id,target_confirmation:ack,observation_digest:facts.observation_digest},value => {setReceipt(value);setFacts(null);setAck('');})}>Acknowledge facts and release target fence</Button>
      </Box>}
      {receipt.target_state_acknowledged_at && <Alert severity="info">The observed target state was acknowledged. The original native load outcome remains uncertain. A new operation requires a new review.</Alert>}
      <Box component="details"><summary>Native replay observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLBinlogReplay.propTypes={post:PropTypes.func.isRequired,engine:PropTypes.oneOf(['mysql','mariadb'])};
