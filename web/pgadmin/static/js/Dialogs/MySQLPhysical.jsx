import {useEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel, MenuItem, Table, TableBody, TableCell, TableHead, TableRow, TextField} from '@mui/material';
import {useModalCloseGuard} from '../helpers/ModalCloseGuard';
import MySQLPhysicalBatchRetention from './MySQLPhysicalBatchRetention';
import MySQLPhysicalBackupSchedule from './MySQLPhysicalBackupSchedule';

const initial = {connection: {host: '', port: 22, username: '', host_key: '', authentication: 'private_key', platform: 'posix', python: '/usr/bin/python3'},
  workspace: '/var/backups/scratchrobin/physical', executable: '/usr/bin/xtrabackup', mysql: '/usr/bin/mysql', phase: 'backup',
  sql_host: '127.0.0.1', sql_port: 3306, input_job_id: null, parallel: 2, memory_bytes: 268435456,
  timeout_seconds: 3600, accept_release_candidate: false};
const phaseOptions = (current, phase, input_job_id) => {
  const {mysqld, recovery_gtid_mode, recovery_port, recovery_mode, recovery_server_id, ...base} = current;
  return {...base, phase, input_job_id, ...(phase === 'recover' ? {mysqld: mysqld || '/usr/sbin/mysqld', recovery_gtid_mode: recovery_gtid_mode || 'ON', recovery_port: recovery_port ?? 3307,
    recovery_mode: recovery_mode || 'read_only', ...(recovery_mode === 'replay' ? {recovery_server_id: recovery_server_id || 10001} : {})} : {})};
};
export default function MySQLPhysical({post, onTargetRegistered = () => {}}) {
  const [options, setOptions] = useState(initial), [credentials, setCredentials] = useState({});
  const [review, setReview] = useState(null), [receipt, setReceipt] = useState(null), [jobs, setJobs] = useState(null);
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [peer, setPeer] = useState(null);
  const [confirmed, setConfirmed] = useState(false), [delegate, setDelegate] = useState(false), [output, setOutput] = useState(null);
  const [connectionReview, setConnectionReview] = useState(null), [connectionReceipt, setConnectionReceipt] = useState(null);
  const [connectionName, setConnectionName] = useState('Recovered MySQL'), [connectionConfirmed, setConnectionConfirmed] = useState(false), [connectionDelegate, setConnectionDelegate] = useState(false);
  const [retention, setRetention] = useState(null), [retentionConfirmed, setRetentionConfirmed] = useState(false), [retentionName, setRetentionName] = useState('');
  const mounted = useRef(true), pending = useRef(false);
  useEffect(() => {mounted.current = true; return () => {mounted.current = false;};}, []);
  useModalCloseGuard(() => !busy);
  const run = async (action, request, accept) => {
    setBusy(true); setError('');
    try {
      const value = await post({action: 'mysql_physical_' + action, request});
      if(mounted.current) {
        const accepted = accept(value);
        if(accepted?.then) await accepted;
      }
    } catch(failure) {if(mounted.current) setError(failure.response?.data?.errormsg || failure.message || 'Native physical request failed.');}
    finally {if(mounted.current) setBusy(false);}
  };
  useEffect(() => {
    if(receipt?.state !== 'remote_running' || !Object.values(credentials).some(Boolean)) return undefined;
    let live = true;
    const timer = setInterval(async () => {
      if(pending.current) return;
      pending.current = true;
      try {
        const value = await post({action: 'mysql_physical_reconcile', request: {job_id: receipt.job_id, credentials}});
        if(mounted.current && live) setReceipt(value);
      } catch(failure) {if(mounted.current && live) setError(failure.response?.data?.errormsg || failure.message);}
      finally {pending.current = false;}
    }, 1500);
    return () => {live = false; clearInterval(timer);};
  }, [post, receipt?.job_id, receipt?.state, credentials]);
  const clearConnectionReview = () => {setConnectionReview(null); setConnectionConfirmed(false); setConnectionDelegate(false);};
  const change = (key, value) => {setOptions(current => ({...current, [key]: value})); setReview(null); setConfirmed(false); setDelegate(false); clearConnectionReview(); setRetention(null); setRetentionConfirmed(false); setRetentionName('');};
  const connection = (key, value) => change('connection', {...options.connection, [key]: value});
  const inspect = value => {
    setReceipt(value); setReview(value.state === 'reviewed' ? value : null); setOptions(value.options);
    setCredentials({}); setConfirmed(false); setDelegate(false); setOutput(null);
    clearConnectionReview(); setConnectionReceipt(null);
    setRetention(null); setRetentionConfirmed(false); setRetentionName('');
  };
  const observe = operation => run(operation, {job_id: receipt.job_id, credentials}, operation === 'output' ? setOutput : setReceipt);
  const derived = phase => {
    setOptions(current => phaseOptions(current, phase, receipt.job_id));
    setReview(null); setConfirmed(false); setDelegate(false); clearConnectionReview();
  };
  const retain = async value => {
    setRetention(value);
    if(['removed', 'not_dispatched'].includes(value.state)) {
      const current = await post({action: 'mysql_physical_status', request: {job_id: receipt.job_id}});
      if(mounted.current) setReceipt(current);
    }
  };
  return <Box component="section" aria-label="Native MySQL physical backups" sx={{p: 1, overflow: 'auto', flex: 1}}>
    <Alert severity="info">XtraBackup 9.7.1-rc1 runs on the pinned Linux database SSH host. Backup, prepare and copy-back retain separate files. Managed recovery starts another data copy using native MySQL 9.7.0. Choose read-only inspection or explicitly writable replay with binary logging. It stops on request or its reviewed lifetime. Recovered-data acceptance and cutover have separate gates. Closing this viewer leaves admitted remote work running.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', my: 1}}>
      <TextField size="small" label="Physical SSH host" value={options.connection.host} disabled={busy} onChange={event => connection('host', event.target.value)} />
      <TextField size="small" type="number" label="Physical SSH port" value={options.connection.port} disabled={busy} onChange={event => connection('port', Number(event.target.value))} />
      <TextField size="small" label="Physical SSH user" value={options.connection.username} disabled={busy} onChange={event => connection('username', event.target.value)} />
      <Button disabled={busy} onClick={() => run('peer', {host: options.connection.host, port: options.connection.port}, setPeer)}>Inspect physical SSH public key</Button>
      {peer && <Box><Box>{peer.fingerprint} — unauthenticated public-key observation</Box>
        <Button disabled={busy} onClick={() => connection('host_key', peer.openssh_key)}>Use this explicitly reviewed public key</Button></Box>}
      <TextField size="small" label="Pinned physical SSH public key" value={options.connection.host_key} disabled={busy} sx={{minWidth: 320}} onChange={event => connection('host_key', event.target.value)} />
      <TextField select size="small" label="Physical SSH authentication" value={options.connection.authentication} disabled={busy} onChange={event => {connection('authentication', event.target.value); setCredentials({});}}>
        <MenuItem value="private_key">Private key</MenuItem><MenuItem value="password">Password</MenuItem>
      </TextField>
      {options.connection.authentication === 'password' ? <TextField type="password" size="small" label="Physical SSH password" value={credentials.password || ''} disabled={busy} onChange={event => setCredentials({password: event.target.value})} /> :
        <><TextField multiline rows={3} size="small" label="Physical SSH private key" value={credentials.private_key || ''} disabled={busy}
          sx={{width: 420, maxWidth: '100%', '& .MuiInputBase-root': {height: 'auto'}, '& textarea': {overflow: 'auto', overflowWrap: 'anywhere'}}}
          onChange={event => setCredentials(current => ({...current, private_key: event.target.value}))} />
        <TextField type="password" size="small" label="Physical SSH key passphrase" value={credentials.private_key_password || ''} disabled={busy} onChange={event => setCredentials(current => ({...current, private_key_password: event.target.value}))} /></>}
      <TextField size="small" label="Physical host Python" value={options.connection.python} disabled={busy} onChange={event => connection('python', event.target.value)} />
    </Box>
    <Box sx={{display: 'flex', gap: 1, flexWrap: 'wrap', my: 1}}>
      <TextField size="small" label="XtraBackup executable" value={options.executable} disabled={busy} onChange={event => change('executable', event.target.value)} />
      <TextField size="small" label="Native host mysql client" value={options.mysql} disabled={busy} onChange={event => change('mysql', event.target.value)} />
      <TextField size="small" label="Private physical workspace" value={options.workspace} disabled={busy} sx={{minWidth: 320}} onChange={event => change('workspace', event.target.value)} />
      <TextField size="small" label="Backup source host loopback address" value={options.sql_host} disabled={busy} onChange={event => change('sql_host', event.target.value)} />
      <TextField size="small" type="number" label="Backup source native TCP port" value={options.sql_port} disabled={busy} onChange={event => change('sql_port', Number(event.target.value))} />
      <TextField select size="small" label="Physical operation" value={options.phase} disabled={busy} onChange={event => {
        const phase = event.target.value;
        setOptions(current => phaseOptions(current, phase, phase === 'backup' ? null : current.input_job_id));
        setReview(null); setConfirmed(false); setDelegate(false); clearConnectionReview();
      }}>
        <MenuItem value="backup">Full backup</MenuItem><MenuItem value="prepare">Prepare immutable copy</MenuItem><MenuItem value="copy_back">Copy back to new isolated directory</MenuItem><MenuItem value="recover">Start managed recovery instance</MenuItem>
      </TextField>
      {options.phase === 'recover' && <>
        <TextField select size="small" label="Recovery startup mode" value={options.recovery_mode || 'read_only'} disabled={busy} onChange={event => {
          const {recovery_server_id, ...base} = options;
          setOptions({...base, recovery_mode: event.target.value, ...(event.target.value === 'replay' ? {recovery_server_id: recovery_server_id || 10001} : {})});
          setReview(null); setConfirmed(false); setDelegate(false); clearConnectionReview();
        }}>
          <MenuItem value="read_only">Read-only inspection</MenuItem><MenuItem value="replay">Replay (writable, binary logging)</MenuItem>
        </TextField>
        {options.recovery_mode === 'replay' && <TextField type="number" size="small" label="Recovery native server ID" value={options.recovery_server_id} disabled={busy} onChange={event => change('recovery_server_id', Number(event.target.value))} />}
        <TextField size="small" label="Recovery mysqld executable" value={options.mysqld} disabled={busy} onChange={event => change('mysqld', event.target.value)} />
        <TextField type="number" size="small" label="Recovery loopback TCP port (0 disables)" value={options.recovery_port || 0} disabled={busy} onChange={event => change('recovery_port', Number(event.target.value))} />
        <TextField select size="small" label="Recovery GTID mode" value={options.recovery_gtid_mode} disabled={busy} onChange={event => change('recovery_gtid_mode', event.target.value)}>
          {['OFF', 'OFF_PERMISSIVE', 'ON_PERMISSIVE', 'ON'].map(mode => <MenuItem key={mode} value={mode}>{mode}</MenuItem>)}
        </TextField>
      </>}
      {options.phase !== 'backup' && <TextField size="small" label="Physical input job ID" value={options.input_job_id || ''} disabled={busy} onChange={event => change('input_job_id', event.target.value)} />}
      <TextField type="number" size="small" label="Physical parallel workers" value={options.parallel} disabled={busy} onChange={event => change('parallel', Number(event.target.value))} />
      <TextField type="number" size="small" label="Prepare memory bytes" value={options.memory_bytes} disabled={busy} onChange={event => change('memory_bytes', Number(event.target.value))} />
      <TextField type="number" size="small" label="Physical native timeout seconds" value={options.timeout_seconds} disabled={busy} onChange={event => change('timeout_seconds', Number(event.target.value))} />
    </Box>
    <FormControlLabel label="I accept this pinned XtraBackup release candidate for this physical operation." control={<Checkbox checked={options.accept_release_candidate} disabled={busy} onChange={event => change('accept_release_candidate', event.target.checked)} />} />
    <Box sx={{display: 'flex', gap: 1, my: 1}}>
      <Button disabled={busy || !options.accept_release_candidate} onClick={() => run('review', {options, credentials}, value => {setReview(value); setReceipt(value); setConfirmed(false); setDelegate(false);})}>Review native physical job</Button>
      <Button disabled={busy} onClick={() => run('list', {offset: 0, limit: 25}, setJobs)}>Load physical jobs</Button>
      <Button disabled={busy} onClick={() => run('connection_info', {}, inspect)}>Load this registration’s recovery instance</Button>
    </Box>
    {review && <Box>
      <Box component="pre" aria-label="Native physical review" sx={{whiteSpace: 'pre-wrap', maxHeight: 280, overflow: 'auto'}}>{JSON.stringify({job_id: review.job_id, source: review.source, remote_review: review.remote_review, warnings: review.warnings}, null, 2)}</Box>
      <FormControlLabel label="I confirm this exact reviewed physical operation." control={<Checkbox checked={confirmed} disabled={busy} onChange={event => setConfirmed(event.target.checked)} />} />
      {['backup', 'recover'].includes(review.options.phase) && <FormControlLabel label="Delegate the registered database password privately to the pinned SSH host." control={<Checkbox checked={delegate} disabled={busy} onChange={event => setDelegate(event.target.checked)} />} />}
      <Button disabled={busy || !confirmed || review.state !== 'reviewed' || ['backup', 'recover'].includes(review.options.phase) && !delegate} onClick={() => run('start',
        {job_id: review.job_id, review_digest: review.review_digest, confirmed, delegate_database_credentials: delegate, credentials}, value => {setReceipt(value); setReview(null);})}>Start reviewed physical job</Button>
    </Box>}
    {jobs && <><Table size="small" aria-label="Native physical jobs"><TableHead><TableRow>{['Job', 'Operation', 'State', 'Inspect'].map(name => <TableCell key={name}>{name}</TableCell>)}</TableRow></TableHead>
      <TableBody>{jobs.jobs.map(job => <TableRow key={job.job_id}><TableCell>{job.job_id}</TableCell><TableCell>{job.options.phase}</TableCell><TableCell>{job.state}</TableCell>
        <TableCell><Button disabled={busy} aria-label={'Inspect physical job ' + job.job_id} onClick={() => run('status', {job_id: job.job_id}, inspect)}>Inspect</Button></TableCell></TableRow>)}</TableBody></Table>
    {jobs.more && <Button disabled={busy} onClick={() => run('list', {offset: jobs.offset + jobs.limit, limit: jobs.limit}, next => setJobs(current => ({...next, jobs: [...current.jobs, ...next.jobs]})))}>More physical jobs</Button>}
    </>}
    {receipt && <Box sx={{my: 1}}>
      <Alert severity={receipt.file_verification_confirmed || receipt.recovery_running ? 'success' : ['unknown', 'native_failed', 'native_returned'].includes(receipt.state) ? 'warning' : 'info'}>Physical job {receipt.job_id}: {receipt.state}. {receipt.options.phase === 'recover' ? `SQL startup readiness: ${receipt.recovery_sql_startup_observed ? 'observed' : 'unconfirmed'}. Original native process: ${receipt.recovery_running ? 'present' : 'unconfirmed'}.` : `File verification: ${receipt.file_verification_confirmed ? 'confirmed' : 'unconfirmed'}.`} Original dispatch, native completion, file verification and database recovery are separate facts.</Alert>
      <Button disabled={busy} onClick={() => observe('reconcile')}>Observe remote physical job</Button>
      <Button disabled={busy || receipt.remote_observation?.process_termination_confirmed} onClick={() => observe('cancel')}>{receipt.options.phase === 'recover' ? 'Stop managed recovery instance' : 'Request native physical cancellation'}</Button>
      <Button disabled={busy} onClick={() => observe('output')}>Inspect native physical output</Button>
      {receipt.file_verification_confirmed && receipt.remote_observation?.artifact && <Button disabled={busy} onClick={() => derived(receipt.remote_observation.artifact.prepared ? 'copy_back' : 'prepare')}>{receipt.remote_observation.artifact.prepared ? 'Use prepared artifact for isolated copy-back' : 'Use backup for separate prepare'}</Button>}
      {receipt.file_verification_confirmed && receipt.remote_observation?.restored_files && <Button disabled={busy} onClick={() => derived('recover')}>Use copy-back for managed recovery</Button>}
      <Box component="pre" aria-label="Native physical receipt" sx={{whiteSpace: 'pre-wrap', maxHeight: 400, overflow: 'auto'}}>{JSON.stringify(receipt, null, 2)}</Box>
      <Box component="section" aria-label="Physical artifact retention" sx={{my: 1}}>
        <Alert severity="warning">Physical retention removes the reviewed backup files, recovered data copy and private replay logs on the pinned SSH host. Remove dependent artifacts first, stop recovery and remove its registrations. Original receipts and native outcomes are preserved. Binary-log protection is managed separately.</Alert>
        <FormControlLabel label="Protect this physical artifact from retention" control={<Checkbox checked={!!receipt.retention_pinned} disabled={busy || receipt.artifact_removed || !!receipt.artifact_removal} onChange={event => run('retention_pin', {job_id: receipt.job_id, pinned: event.target.checked}, setReceipt)} />} />
        <Button disabled={busy || receipt.artifact_removed || !!receipt.artifact_removal || !!receipt.retention_batch_id || receipt.retention_pinned} onClick={() => run('retention_review', {job_id: receipt.job_id, credentials}, value => {setRetention(value); setRetentionConfirmed(false); setRetentionName('');})}>Review physical artifact retention</Button>
        <Button disabled={busy || !(receipt.artifact_removal?.retention_job_id || receipt.retention_review_job_id)} onClick={() => run('retention_status', {job_id: receipt.artifact_removal?.retention_job_id || receipt.retention_review_job_id}, value => {setRetention(value); setRetentionConfirmed(false); setRetentionName('');})}>Load physical retention receipt</Button>
        {retention && <>
          <Box component="pre" aria-label="Physical retention review" sx={{whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto'}}>{JSON.stringify(retention, null, 2)}</Box>
          <TextField size="small" label="Exact physical job UUID to remove" value={retentionName} disabled={busy} onChange={event => setRetentionName(event.target.value)} />
          <FormControlLabel label="I confirm removal of these reviewed physical files." control={<Checkbox checked={retentionConfirmed} disabled={busy} onChange={event => setRetentionConfirmed(event.target.checked)} />} />
          <Button disabled={busy || !retentionConfirmed || retentionName !== receipt.job_id || !['reviewed', 'unknown', 'removing'].includes(retention.state)} onClick={() => run('retention_start', {job_id: retention.job_id, review_digest: retention.review_digest, job_confirmation: retentionName, confirmed: true, credentials}, retain)}>{retention.state === 'reviewed' ? 'Remove reviewed physical artifacts' : 'Resume original physical removal'}</Button>
          <Button disabled={busy} onClick={() => run('retention_reconcile', {job_id: retention.job_id, credentials}, retain)}>Inspect original physical removal</Button>
          <Button disabled={busy || !retentionConfirmed || retentionName !== receipt.job_id || ['removed', 'not_dispatched'].includes(retention.state)} onClick={() => run('retention_abandon', {job_id: retention.job_id, review_digest: retention.review_digest, job_confirmation: retentionName, confirmed: true, credentials}, retain)}>Invalidate an unclaimed removal review</Button>
        </>}
      </Box>
    </Box>}
    <MySQLPhysicalBatchRetention post={post} credentials={credentials} scopeJobId={receipt?.job_id} busy={busy} onBusy={setBusy} onChanged={async () => {
      if(receipt) {const value = await post({action: 'mysql_physical_status', request: {job_id: receipt.job_id}}); if(mounted.current) setReceipt(value);}
    }} />
    <MySQLPhysicalBackupSchedule post={post} physical={options} credentials={credentials} busy={busy} onBusy={setBusy} />
    {output && <Box component="pre" aria-label="Native physical output" sx={{whiteSpace: 'pre-wrap', maxHeight: 350, overflow: 'auto'}}>{JSON.stringify(output, null, 2)}</Box>}
    {receipt?.options.phase === 'recover' && <Box sx={{my: 1}}>
      <Alert severity="info">Register this recovery instance as a separate MySQL target for the native editor and catalog. Use its reviewed loopback TCP port through pinned SSH. After application restart, reattach with fresh SSH authentication. Writable replay startups support native raw-log and POSIX Shell replay from the target’s recovery menu.</Alert>
      <TextField size="small" label="Recovery registration name" value={connectionName} disabled={busy} onChange={event => {setConnectionName(event.target.value); clearConnectionReview();}} />
      <Button disabled={busy} onClick={() => run('connection_review', {job_id: receipt.job_id, name: connectionName, credentials}, value => {setConnectionReview(value); setConnectionConfirmed(false); setConnectionDelegate(false);})}>Review recovery connection</Button>
      {connectionReview && <>
        <Box component="pre" aria-label="Native recovery connection review" sx={{whiteSpace: 'pre-wrap', maxHeight: 250, overflow: 'auto'}}>{JSON.stringify(connectionReview, null, 2)}</Box>
        <FormControlLabel label="I confirm this separate recovery connection registration." control={<Checkbox checked={connectionConfirmed} disabled={busy} onChange={event => setConnectionConfirmed(event.target.checked)} />} />
        <FormControlLabel label="Use the registered database credential for this recovery registration." control={<Checkbox checked={connectionDelegate} disabled={busy} onChange={event => setConnectionDelegate(event.target.checked)} />} />
        <Button disabled={busy || !connectionConfirmed || !connectionDelegate} onClick={() => run('connection_connect', {review_id: connectionReview.job_id, review_digest: connectionReview.review_digest,
          confirmed: connectionConfirmed, delegate_database_credentials: connectionDelegate, credentials}, value => {setConnectionReceipt(value); setConnectionReview(null); if(value.result) onTargetRegistered(value.result);})}>Attach reviewed recovery connection</Button>
      </>}
      {connectionReceipt && <>
        <Alert severity={connectionReceipt.result?.transport_attached ? 'success' : 'warning'}>{connectionReceipt.result ? `Recovery target: ${connectionReceipt.result.name}. Open its native query tool from Data Explorer.` : 'Original connection outcome is unknown. Observe the retained registration before another review.'}</Alert>
        <Button disabled={busy} onClick={() => run('connection_status', {review_id: connectionReceipt.job_id}, setConnectionReceipt)}>Observe recovery registration</Button>
        {connectionReceipt.result && <Button disabled={busy} onClick={() => run('connection_detach', {server_id: connectionReceipt.result.server_id}, value => setConnectionReceipt(current => ({...current, result: value})))}>Detach recovery transport</Button>}
        <Box component="pre" aria-label="Native recovery connection receipt" sx={{whiteSpace: 'pre-wrap', maxHeight: 300, overflow: 'auto'}}>{JSON.stringify(connectionReceipt, null, 2)}</Box>
      </>}
    </Box>}
  </Box>;
}
MySQLPhysical.propTypes = {post: PropTypes.func.isRequired, onTargetRegistered: PropTypes.func};
