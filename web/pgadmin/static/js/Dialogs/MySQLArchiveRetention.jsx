import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,TextField} from '@mui/material';
import MySQLRetentionSchedule from './MySQLRetentionSchedule';
import MySQLBackupProtection from './MySQLBackupProtection';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';

const ACTIVE=new Set(['dispatching','active','cancel_requested']);
export default function MySQLArchiveRetention({post,prefix,sourceArchive}) {
  const [days,setDays]=useState(30),[keep,setKeep]=useState(1);
  const [review,setReview]=useState(null),[receipt,setReceipt]=useState(null),[jobs,setJobs]=useState(null);
  const [busy,setBusy]=useState(false),[error,setError]=useState('');
  const generation=useRef(0);
  useEffect(() => {
    generation.current++;setReview(null);setReceipt(null);setJobs(null);setBusy(false);setError('');
    return () => {generation.current++;};
  },[post,prefix]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const result=await post({action:prefix+action,request});if(token===generation.current)accept(result);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Archive retention request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  useEffect(() => {
    if(!ACTIVE.has(receipt?.state))return;
    let live=true,pending=false;
    const timer=setInterval(async () => {
      if(pending)return;pending=true;
      try {const value=await post({action:prefix+'retention_status',request:{job_id:receipt.job_id}});if(live)setReceipt(value);}
      catch(failure) {if(live)setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending=false;}
    },1000);
    return () => {live=false;clearInterval(timer);};
  },[post,prefix,receipt?.job_id,receipt?.state]);
  const load=offset => run('retention_list',{offset,limit:25},setJobs);
  return <Box sx={{p:1}}>
    <FormReference formKey="mysql-archive-retention" />
    <Alert severity="info">Retention removes application archive files and keeps operation receipts. Managed graphical backups add automatic archive holds. Protect archives needed by external backups or recovery targets with the archive’s protection control. Age and minimum-count rules do not verify recovery coverage. Native server logs are unchanged.</Alert>
    <Box component="details"><summary>Managed backup protection</summary><MySQLBackupProtection post={post} /></Box>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display:'flex',gap:1,flexWrap:'wrap',my:1}}>
      <TextField size="small" type="number" label="Remove archives older than days" value={days} onChange={event => {setDays(Number(event.target.value));setReview(null);}} />
      <TextField size="small" type="number" label="Keep latest archives per source and principal" value={keep} onChange={event => {setKeep(Number(event.target.value));setReview(null);}} />
      <Button disabled={busy} onClick={() => run('retention_review',{policy:{retention_days:days,keep_latest:keep}},setReview)}>Review archive retention</Button>
      <Button disabled={busy} onClick={() => load(0)}>Load retention receipts</Button>
    </Box>
    {review && <Box>
      <ul>{review.warnings.map(warning => <li key={warning}>{warning}</li>)}</ul>
      <Alert severity="warning">This review removes {review.continuation.archives.length} archives ({review.continuation.total_bytes} bytes). {review.continuation.eligible_count} archives matched the policy when reviewed.</Alert>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Reviewed archive retention candidates"
        rows={(review.continuation.archives || []).map(row => ({
          id: row.job_id,
          job_id: row.job_id,
          source: `${row.source.server_uuid} / ${row.source.authenticated_principal}`,
          created_at: new Date(row.created_at*1000).toISOString(),
          bytes: row.bytes,
        }))}
        columns={[
          {key: 'job_id', name: 'Archive'},
          {key: 'source', name: 'Native source'},
          {key: 'created_at', name: 'Created'},
          {key: 'bytes', name: 'Bytes'},
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <Box component="details"><summary>Retention exclusions and execution host</summary><Box component="pre" sx={{whiteSpace:'pre-wrap'}}>{JSON.stringify({excluded:review.continuation.excluded,execution_host:review.execution_host},null,2)}</Box></Box>
      <Button disabled={busy || review.state!=='reviewed'} onClick={() => run('retention_start',{job_id:review.job_id,review_digest:review.review_digest,confirmed:true},value => {setReceipt(value);setReview(current => ({...current,state:value.state}));})}>Confirm removal of reviewed archives</Button>
    </Box>}
    {jobs && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Archive retention receipts"
        rows={(jobs.jobs || []).map(job => ({
          id: job.job_id,
          job_id: job.job_id,
          state: job.state,
          _raw: job,
        }))}
        columns={[
          {key: 'job_id', name: 'Retention job'},
          {key: 'state', name: 'State'},
          {
            key: '_receipt',
            name: 'Receipt',
            render: (_val, row) => <Button disabled={busy} aria-label={'Inspect retention '+row._raw.job_id} onClick={() => run('retention_status',{job_id:row._raw.job_id},setReceipt)}>Inspect</Button>,
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
        onFirst={() => load(0)}
        onPrevious={() => load(Math.max(0, (jobs.offset || 0) - 25))}
        onNext={() => load((jobs.offset || 0) + 25)}
        onLast={() => load(Math.max(0, (Math.ceil((jobs.total || 0) / 25) - 1) * 25))}
      />
      {jobs.unavailable_job_ids?.length>0 && <Alert severity="warning">Some retention receipts could not be read: {jobs.unavailable_job_ids.join(', ')}</Alert>}
    </>}
    {receipt && <Box sx={{my:1}}>
      <Alert severity={receipt.state==='completed' || receipt.state==='reconciled' ? 'success' : 'warning'}>Retention {receipt.job_id}: {receipt.state}. {receipt.state==='unknown' || receipt.state==='interrupted' ? 'No automatic retry occurs. Reconciliation finishes recorded removal intents and reports unattempted archives.' : ''}</Alert>
      <Button disabled={busy} onClick={() => run('retention_status',{job_id:receipt.job_id},setReceipt)}>Refresh retention receipt</Button>
      <Button disabled={busy || !ACTIVE.has(receipt.state) && receipt.state!=='reviewed'} onClick={() => run('retention_cancel',{job_id:receipt.job_id},setReceipt)}>Cancel retention</Button>
      <Button disabled={busy || ACTIVE.has(receipt.state) || receipt.state==='reviewed'} onClick={() => run('retention_reconcile',{job_id:receipt.job_id,confirmed:true},setReceipt)}>Reconcile recorded removals</Button>
      <Box component="details"><summary>Archive retention observations</summary><Box component="pre" aria-label="Archive retention observations" sx={{whiteSpace:'pre-wrap',maxHeight:400,overflow:'auto'}}>{JSON.stringify(receipt,null,2)}</Box></Box>
    </Box>}
    <MySQLRetentionSchedule post={post} prefix={prefix} sourceArchive={sourceArchive} days={days} keep={keep} onOccurrence={setReceipt} />
  </Box>;
}
MySQLArchiveRetention.propTypes={post:PropTypes.func.isRequired,prefix:PropTypes.string.isRequired,sourceArchive:PropTypes.object};
