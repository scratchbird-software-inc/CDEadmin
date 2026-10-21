import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,MenuItem,Table,TableBody,TableCell,TableHead,TableRow,TablePagination,TextField} from '@mui/material';
import {startBrowserFileDownload} from './browserFileDownload';
import ContinuousBinlog from './ContinuousBinlog';
import MySQLArchiveRetention from './MySQLArchiveRetention';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLBinlogArchives({post,endpointUrl,engine='mysql',raw=false}) {
  const maria=engine==='mariadb',closed=maria || raw,prefix=raw ? 'mysql_raw_binlog_' : maria ? 'mariadb_binlog_' : 'mysql_binlog_',engineLabel=maria ? 'MariaDB' : 'MySQL';
  const [catalog,setCatalog]=useState(null),[jobs,setJobs]=useState(null),[page,setPage]=useState(0);
  const [source,setSource]=useState('position'),[filename,setFilename]=useState(''),[position,setPosition]=useState('4'),[since,setSince]=useState('');
  const [compression,setCompression]=useState('zstd;level=1'),[threads,setThreads]=useState(4),[timeout,setTimeoutValue]=useState(3600);
  const [logNames,setLogNames]=useState([]);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[files,setFiles]=useState(null),[confirmation,setConfirmation]=useState('');
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0),downloads=useRef([]);
  useEffect(() => {
    generation.current++;setCatalog(null);setJobs(null);setPage(0);setReview(null);setReceipt(null);setFiles(null);setLogNames([]);setConfirmation('');setBusy(false);setError('');
    return () => {generation.current++;downloads.current.splice(0).forEach(close => close());};
  },[post,endpointUrl,engine,raw]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:prefix+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Native archive request failed');}
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
  },[post,prefix,receipt?.job_id,receipt?.state]);
  const change=setter => event => {setter(event.target.value);setReview(null);};
  const load=next => run('list',{offset:next*25,limit:25},value => {setJobs(value);setPage(next);});
  const inspect=job => run('status',{job_id:job.job_id},value => {setReceipt(value);setFiles(null);setConfirmation('');});
  const loadFiles=offset => run('files',{job_id:receipt.job_id,offset,limit:100},setFiles);
  const download=row => {
    try {downloads.current.push(startBrowserFileDownload(endpointUrl,{job_id:receipt.job_id,path:row.path},
      {action:prefix+'download',prefix:engine+'-binlog',title:'Native binary-log archive download'}));}
    catch(failure) {setError(failure.message);}
  };
  const saveReceipt=() => {
    const url=URL.createObjectURL(new Blob([JSON.stringify(receipt,null,2)],{type:'application/json'}));
    const link=document.createElement('a');link.href=url;link.download=engine+'-binlog-'+receipt.job_id+'.json';link.click();
    window.setTimeout(() => URL.revokeObjectURL(url),1000);
  };
  return <Box sx={{p:1,overflow:'auto',flex:1}}>
    <Alert severity="info">{raw ? 'Archive a contiguous range of closed native MySQL binary logs on the application host using mysqlbinlog. GTID mode can be ON or OFF. Encrypted source logs are decrypted in the archive. The active log remains on the server.' : maria ? 'Archive a contiguous range of closed native MariaDB binary logs on the application host using mariadb-binlog. The active log remains on the server.' : 'Archive native binary logs on the application host using MySQL Shell.'} Logs include changes from the whole server. Keep downloaded files private and preserve their relative paths. Archive verification and successful database recovery have separate receipts.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <Button disabled={busy} onClick={() => run('catalog',{},setCatalog)}>Inspect native binary logs</Button>
      <Button disabled={busy} onClick={() => load(page)}>Load archive jobs</Button>
    </Box>
    {closed && <Box component="details"><summary>Continuous native binary-log collection</summary><ContinuousBinlog post={post} engine={engine} onInspectArchive={id => inspect({job_id:id})} /></Box>}
    {!maria && <Box component="details"><summary>Archive retention</summary><MySQLArchiveRetention post={post} prefix={prefix} sourceArchive={receipt} /></Box>}
    {catalog && <Box component="details"><summary>Native source, GTID state and available logs: {catalog.status}</summary><Box component="pre" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify(catalog,null,2)}</Box></Box>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      {closed ? <TextField select size="small" label="Native closed binary logs" value={logNames} SelectProps={{multiple:true}} sx={{minWidth:280}} onChange={event => {setLogNames((catalog?.logs || []).filter(row => event.target.value.includes(row.Log_name)).map(row => row.Log_name));setReview(null);}}>
        {(catalog?.logs || []).filter(row => row.closed).map(row => <MenuItem key={row.Log_name} value={row.Log_name}>{row.Log_name} ({row.File_size} bytes)</MenuItem>)}
      </TextField> : <>
        <TextField select size="small" label="Archive starting point" value={source} onChange={change(setSource)}><MenuItem value="position">Native file and position</MenuItem><MenuItem value="continuation">Completed archive</MenuItem></TextField>
        {source==='position' ? <>
          <TextField size="small" label="Native binary-log filename" value={filename} onChange={change(setFilename)} />
          <TextField size="small" label="Native position" value={position} onChange={change(setPosition)} />
        </> : <TextField size="small" label="Previous archive job identity" value={since} onChange={change(setSince)} />}
        <TextField size="small" label="Native compression" value={compression} onChange={change(setCompression)} helperText="none, gzip;level=0–9, zstd;level=1–22" />
        <TextField size="small" type="number" label="Native dump threads" value={threads} onChange={event => {setThreads(Number(event.target.value));setReview(null);}} />
      </>}
      <TextField size="small" type="number" label="Runtime seconds (blank: no deadline)" value={timeout ?? ''} onChange={event => {setTimeoutValue(event.target.value==='' ? null : Number(event.target.value));setReview(null);}} />
      <Button disabled={busy} onClick={() => run('review',{options:closed ? {log_names:logNames,timeout_seconds:timeout} : {...(source==='position' ? {start_file:filename,start_position:position} : {since_job_id:since}),compression,threads,timeout_seconds:timeout}},setReview)}>Review archive</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Box component="pre" aria-label="Native archive review" sx={{whiteSpace:'pre-wrap',maxHeight:280,overflow:'auto'}}>{JSON.stringify({source:review.source,options:review.options,continuation:review.continuation,execution_host:review.execution_host},null,2)}</Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setFiles(null);setReview(current => ({...current,state:value.state}));})}>Confirm and start archive</Button>
    </Box>}
    {jobs && <>
      <Table size="small" aria-label={'Native '+engineLabel+' archive jobs'}><TableHead><TableRow>{['Job','Starting point','State','Receipt'].map(value => <TableCell key={value}>{value}</TableCell>)}</TableRow></TableHead><TableBody>
        {jobs.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{closed ? job.options.log_names.join(' → ') : job.options.since_job_id || job.options.start_file+':'+job.options.start_position}</TableCell><TableCell>{job.state}</TableCell><TableCell><Button disabled={busy} aria-label={'Inspect archive '+job.job_id} onClick={() => inspect(job)}>Inspect</Button></TableCell></TableRow>)}
      </TableBody></Table><TablePagination component="div" count={jobs.total} rowsPerPage={25} rowsPerPageOptions={[25]} page={page} onPageChange={(_event,next) => load(next)} />
      {jobs.unavailable_job_ids?.length>0 && <Alert severity="warning">Some archive receipts could not be read: {jobs.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={['completed','artifact_verified'].includes(receipt.state) ? 'success' : ['failed','unknown','not_dispatched'].includes(receipt.state) ? 'warning' : 'info'}>
        Archive {receipt.job_id}: {receipt.state}.
        {receipt.state==='unknown' && ' Native process termination is uncertain. This operation will not be replayed.'}
        {receipt.state==='no_new_snapshot' && ' The native utility produced no new archive; the continuation cursor was not advanced.'}
        {receipt.artifact_removed && ' Application archive files were removed; the receipt is retained.'}
        {receipt.artifact_removal?.state==='pending' && ' Archive file removal was interrupted. Reconcile the recorded removal intent.'}
        {receipt.retention_pinned && ' This archive is protected from file removal.'}
      </Alert>
      <Button disabled={busy} onClick={() => inspect(receipt)}>Refresh archive receipt</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state) || receipt.artifact_removed} onClick={() => run('reconcile',{job_id:receipt.job_id},setReceipt)}>Verify archive again</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed'} onClick={() => run('cancel',{job_id:receipt.job_id},setReceipt)}>Cancel archive</Button>
      <Button disabled={busy || !['completed','artifact_verified'].includes(receipt.state) || receipt.artifact_removed} onClick={() => loadFiles(0)}>Load archive files</Button>
      <Button onClick={saveReceipt}>Download archive receipt</Button>
      {!maria && !receipt.artifact_removed && !receipt.artifact_removal && ['completed','artifact_verified'].includes(receipt.state) && <Button disabled={busy} onClick={() => run('pin',{job_id:receipt.job_id,pinned:!receipt.retention_pinned},setReceipt)}>{receipt.retention_pinned ? 'Unprotect archive from removal' : 'Protect archive from removal'}</Button>}
      {!maria && receipt.artifact_removal?.state==='pending' && <Button disabled={busy} onClick={() => run('removal_reconcile',{job_id:receipt.job_id,confirmation:receipt.job_id},setReceipt)}>Reconcile archive file removal</Button>}
      {files && !receipt.artifact_removed && <>
        <Table size="small" aria-label="Verified native archive files"><TableHead><TableRow>{['Relative path','Bytes','SHA256','Download'].map(value => <TableCell key={value}>{value}</TableCell>)}</TableRow></TableHead><TableBody>{files.files.map(row => <TableRow key={row.path}><TableCell>{row.path}</TableCell><TableCell>{row.size}</TableCell><TableCell>{row.sha256}</TableCell><TableCell><Button aria-label={'Download '+row.path} onClick={() => download(row)}>Download file</Button></TableCell></TableRow>)}</TableBody></Table>
        <TablePagination component="div" count={files.total} rowsPerPage={100} rowsPerPageOptions={[100]} page={files.offset/100} onPageChange={(_event,next) => loadFiles(next*100)} />
      </>}
      {!receipt.artifact_removed && !receipt.artifact_removal && !receipt.retention_pinned && !ACTIVE.has(receipt.state) && <Box sx={{display:'flex',gap:1,my:1}}>
        <TextField size="small" label="Confirm job identity to remove archive files" value={confirmation} onChange={event => setConfirmation(event.target.value)} />
        <Button disabled={busy || confirmation!==receipt.job_id} onClick={() => run('remove_artifact',{job_id:receipt.job_id,confirmation},value => {setReceipt(value);setFiles(null);})}>Remove application archive files</Button>
      </Box>}
      <Box component="details"><summary>Native archive observations</summary><Box component="pre" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
  </Box>;
}
MySQLBinlogArchives.propTypes={post:PropTypes.func.isRequired,endpointUrl:PropTypes.string.isRequired,engine:PropTypes.oneOf(['mysql','mariadb']),raw:PropTypes.bool};
