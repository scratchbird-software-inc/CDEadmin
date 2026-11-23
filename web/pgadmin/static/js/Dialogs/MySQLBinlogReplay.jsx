import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,TextField} from '@mui/material';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';

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
    <FormReference formKey="mysql-binlog-replay" />
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
      {sources.total > 25 && (
        <GridNavigation
          busy={busy}
          page={Math.floor(sources.offset / 25)}
          pages={Math.max(1, Math.ceil(sources.total / 25))}
          endKnown
          canNext={sources.offset + 25 < sources.total}
          onFirst={() => run('sources',{offset:0,limit:25},value => {setSources(value);setSource('');setArchives(null);setArchive('');setReview(null);})}
          onPrevious={() => run('sources',{offset:Math.max(0,sources.offset-25),limit:25},value => {setSources(value);setSource('');setArchives(null);setArchive('');setReview(null);})}
          onNext={() => run('sources',{offset:sources.offset+25,limit:25},value => {setSources(value);setSource('');setArchives(null);setArchive('');setReview(null);})}
          onLast={() => run('sources',{offset:Math.max(0,(Math.ceil(sources.total/25)-1)*25),limit:25},value => {setSources(value);setSource('');setArchives(null);setArchive('');setReview(null);})}
        />
      )}
      <Button disabled={busy || source===''} onClick={() => run('archives',archiveRequest({source_server_id:source,offset:0,limit:25}),setArchives)}>Load sealed archives</Button>
    </>}
    {archives && <>
      <TextField disabled={busy} select size="small" label="Sealed native archive" value={archive} sx={{minWidth:380}} onChange={event => {setArchive(event.target.value);setBoundaries(null);setStart(null);setStop(null);setReview(null);}}>
        {archives.jobs.filter(item => ['completed','artifact_verified'].includes(item.state) && !item.artifact_removed && item.native_process_termination_confirmed===true).map(item => <MenuItem key={item.job_id} value={item.job_id}>{item.job_id} ({item.result?.artifact?.total_bytes} bytes)</MenuItem>)}
      </TextField>
      {archives.total > 25 && (
        <GridNavigation
          busy={busy}
          page={Math.floor(archives.offset / 25)}
          pages={Math.max(1, Math.ceil(archives.total / 25))}
          endKnown
          canNext={archives.offset + 25 < archives.total}
          onFirst={() => run('archives',archiveRequest({source_server_id:source,offset:0,limit:25}),value => {setArchives(value);setArchive('');setReview(null);})}
          onPrevious={() => run('archives',archiveRequest({source_server_id:source,offset:Math.max(0,archives.offset-25),limit:25}),value => {setArchives(value);setArchive('');setReview(null);})}
          onNext={() => run('archives',archiveRequest({source_server_id:source,offset:archives.offset+25,limit:25}),value => {setArchives(value);setArchive('');setReview(null);})}
          onLast={() => run('archives',archiveRequest({source_server_id:source,offset:Math.max(0,(Math.ceil(archives.total/25)-1)*25),limit:25}),value => {setArchives(value);setArchive('');setReview(null);})}
        />
      )}
      {archives.unavailable_job_ids?.length>0 && <Alert severity="warning">Some archive receipts are unavailable: {archives.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {raw && <Box sx={{my:1}}>
      <Alert severity="info">Raw replay uses native mysqlbinlog and mysql 9.7 clients. The target needs native backup privileges to observe its dispatch position. Named GTIDs already present are skipped. Anonymous recovery resumes only from an explicitly selected start after independent data verification.</Alert>
      <Button disabled={busy || !archive} onClick={() => loadBoundaries(0)}>Inspect native transaction groups</Button>
      <Button disabled={busy} onClick={() => {setStart(null);setStop(null);setMode('all');setReview(null);}}>Use whole archive</Button>
      <Box>Start: {start ? start.file+' @ '+start.position : 'archive beginning'}. Stop: {mode==='all' ? 'archive end' : mode+' '+(stop ? stop.file+' @ '+stop.position : 'select a native group')}.</Box>
      {boundaries && <>
        <UnifiedDataGrid
          gridRole="table"
          ariaLabel="Native raw transaction groups"
          rows={(boundaries.groups || []).map((group, index) => ({
            id: `${group.file}@${group.position}`,
            ordinal: boundaries.offset + index + 1,
            file: group.file,
            position: group.position,
            event_time_utc: group.event_time_utc,
            native_group: group.event_type===34 ? 'anonymous' : group.event_type===42 ? 'tagged GTID' : 'GTID',
            _raw: group,
          }))}
          columns={[
            {key: 'ordinal', name: 'Group'},
            {key: 'file', name: 'File'},
            {key: 'position', name: 'Position'},
            {key: 'event_time_utc', name: 'Event time (UTC)'},
            {key: 'native_group', name: 'Native group'},
            {
              key: '_selection',
              name: 'Selection',
              render: (_val, row) => <>
                <Button disabled={busy || !['OFF','OFF_PERMISSIVE'].includes(target?.state?.gtid_mode)} aria-label={'Start raw replay at '+row._raw.file+'@'+row._raw.position} onClick={() => {setStart(row._raw);setReview(null);}}>Start here</Button>
                <Button disabled={busy} aria-label={'Stop raw replay before '+row._raw.file+'@'+row._raw.position} onClick={() => {setStop(row._raw);setMode('before');setReview(null);}}>Stop before</Button>
                <Button disabled={busy} aria-label={'Stop raw replay after '+row._raw.file+'@'+row._raw.position} onClick={() => {setStop(row._raw);setMode('after');setReview(null);}}>Stop after</Button>
              </>,
            },
          ]}
          compact
          searchable={false}
          exportable={false}
        />
        <GridNavigation
          busy={busy}
          page={Math.floor((boundaries.offset || 0) / 100)}
          pages={Math.max(1, Math.ceil((boundaries.total || 0) / 100))}
          endKnown
          canNext={(boundaries.offset || 0) + 100 < (boundaries.total || 0)}
          onFirst={() => loadBoundaries(0)}
          onPrevious={() => loadBoundaries(Math.max(0, (boundaries.offset || 0) - 100))}
          onNext={() => loadBoundaries((boundaries.offset || 0) + 100)}
          onLast={() => loadBoundaries(Math.max(0, (Math.ceil((boundaries.total || 0) / 100) - 1) * 100))}
        />
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
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel={'Native '+(engine==='mariadb' ? 'MariaDB' : 'MySQL')+' replay jobs'}
        rows={(jobs.jobs || []).map(job => ({
          id: job.job_id,
          job_id: job.job_id,
          state: job.state,
          native_load_outcome: job.native_load_outcome,
          _raw: job,
        }))}
        columns={[
          {key: 'job_id', name: 'Job'},
          {key: 'state', name: 'State'},
          {key: 'native_load_outcome', name: 'Native load'},
          {
            key: '_receipt',
            name: 'Receipt',
            render: (_val, row) => <Button disabled={busy} aria-label={'Inspect replay '+row._raw.job_id} onClick={() => inspect(row._raw)}>Inspect</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <GridNavigation
        busy={busy}
        page={Math.floor((jobs.offset || 0) / 25)}
        pages={Math.max(1, Math.ceil((jobs.total || 0) / 25))}
        endKnown
        canNext={(jobs.offset || 0) + 25 < (jobs.total || 0)}
        onFirst={() => loadJobs(0)}
        onPrevious={() => loadJobs(Math.max(0, (jobs.offset || 0) - 25))}
        onNext={() => loadJobs((jobs.offset || 0) + 25)}
        onLast={() => loadJobs(Math.max(0, (Math.ceil((jobs.total || 0) / 25) - 1) * 25))}
      />
      {jobs.unavailable_job_ids?.length>0 && <Alert severity="warning">Some replay receipts are unavailable: {jobs.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={receipt.state==='unknown' ? 'warning' : 'info'}>Replay {receipt.job_id}: {receipt.state}. Native load: {receipt.native_load_outcome}. {receipt.state==='unknown' && ('The outcome is uncertain. '+(receipt.target_state_acknowledged_at ? '' : 'This target is fenced. ')+'This operation will not replay automatically.')} Recovered data has not been independently verified.</Alert>
      <Button disabled={busy} onClick={() => inspect(receipt)}>Refresh replay receipt</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed' && !receipt.utility_cancellation_available} onClick={() => run('cancel',{job_id:receipt.job_id},value => {setReceipt(value);setFacts(null);setAck('');})}>Cancel replay</Button>
      {engine==='mysql' && <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={() => run('observe_utilities',{job_id:receipt.job_id},value => {setReceipt(value);setFacts(null);setAck('');})}>Inspect original replay utilities</Button>}
      <Button disabled={busy || ACTIVE.has(receipt.state)} onClick={() => run('reconcile',{job_id:receipt.job_id},value => {setReceipt(value);setFacts(value);setAck('');})}>Inspect current target facts</Button>
      <Button onClick={save}>Download replay receipt</Button>
      {receipt.utility_observation_unavailable && receipt.native_process_termination_confirmed!==true && <Alert severity="warning">The original utility reference is unavailable. This receipt cannot confirm cleanup or cancel that client. The original outcome is unchanged.</Alert>}
      {receipt.interrupted_utility_observation && <Box component="pre" aria-label="Original replay utility observations" sx={{whiteSpace:'pre-wrap',maxHeight:300,overflow:'auto'}}>{JSON.stringify({utilities:receipt.interrupted_utility_observation,staged_input_cleanup:receipt.staged_input_cleanup,recovery_utility_release:receipt.recovery_utility_release},null,2)}</Box>}
      {facts && <Box component="pre" aria-label="Native replay reconciliation" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(facts.interrupted_utility_observation ?
        {...facts.reconciliation,native_utilities:facts.interrupted_utility_observation} : facts.reconciliation,null,2)}</Box>}
      {receipt.state==='unknown' && !receipt.target_state_acknowledged_at && facts && <Box sx={{display:'flex',gap:1,my:1}}>
        <TextField disabled={busy} size="small" label={engine==='mariadb' ? 'Acknowledge uncertain target server UID' : 'Acknowledge uncertain target UUID'} value={ack} onChange={event => setAck(event.target.value)} />
        <Button disabled={busy || receipt.native_process_termination_confirmed!==true || facts.reconciliation?.native_lock_free!==true || facts.reconciliation?.native_principal_work_free===false || ack!==receipt.target[identityKey]} onClick={() => run('acknowledge',{job_id:receipt.job_id,target_confirmation:ack,observation_digest:facts.observation_digest},value => {setReceipt(value);setFacts(null);setAck('');})}>Acknowledge facts and release target fence</Button>
      </Box>}
      {receipt.target_state_acknowledged_at && <Alert severity="info">The observed target state was acknowledged. The original native load outcome remains uncertain. A new operation requires a new review.</Alert>}
      <Box component="details"><summary>Native replay observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLBinlogReplay.propTypes={post:PropTypes.func.isRequired,engine:PropTypes.oneOf(['mysql','mariadb'])};
