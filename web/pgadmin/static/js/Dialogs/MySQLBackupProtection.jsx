import {useEffect,useRef,useState} from 'react';
import PropTypes from 'prop-types';
import {Alert,Box,Button,Checkbox,FormControlLabel} from '@mui/material';
import MySQLRecoveryChains from './MySQLRecoveryChains';
import FormReference from '../cdeadmin_ui/navigation/FormReference';
import UnifiedDataGrid from '../cdeadmin_ui/data/UnifiedDataGrid';
import GridNavigation from '../cdeadmin_ui/data/GridNavigation';

export default function MySQLBackupProtection({post}) {
  const [page,setPage]=useState(null),[review,setReview]=useState(null),[confirmed,setConfirmed]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState(''),[retired,setRetired]=useState(null);
  const [allRegistrations,setAllRegistrations]=useState(false);
  const generation=useRef(0);
  useEffect(() => {generation.current++;setPage(null);setReview(null);setConfirmed(false);setRetired(null);setError('');setBusy(false);setAllRegistrations(false);return () => {generation.current++;};},[post]);
  const run=async (action,request,accept) => {
    const token=generation.current;setBusy(true);setError('');
    try {const value=await post({action:'mysql_binlog_backup_protection_'+action,request});if(token===generation.current)accept(value);}
    catch(failure) {if(token===generation.current)setError(failure.response?.data?.errormsg || failure.message || 'Backup protection request failed');}
    finally {if(token===generation.current)setBusy(false);}
  };
  const load=offset => run('list',{offset,limit:25,...(allRegistrations ? {all_registrations:true} : {})},setPage);
  return <Box sx={{my:1}}>
    <FormReference formKey="mysql-backup-protection" />
    <Alert severity="info">Managed native dumps and physical clones protect application archives. Native source holds also apply to other registrations of the same instance owned by the same user. Pending or uncertain records retain all archives of their own registration. Remote clone source UUIDs are not attested by the clone protocol, so donor and recipient holds remain conservative. These holds do not discover external backups. Native server logs have separate administration.</Alert>
    {error && <Alert severity="error">{error}</Alert>}
    <FormControlLabel label="Show backup holds from all my registrations, including removed registrations" control={<Checkbox disabled={busy} checked={allRegistrations} onChange={event=>{setAllRegistrations(event.target.checked);setPage(null);setReview(null);setConfirmed(false);setRetired(null);}} />} />
    <Button disabled={busy} onClick={() => load(0)}>Load managed backup protection</Button>
    {page && <>
      <UnifiedDataGrid
        gridRole="table"
        ariaLabel="Managed backup protection"
        rows={(page.backups || []).map(backup => ({
          id: (backup.protection_endpoint_id || '') + backup.backup_id,
          backup_id: backup.backup_id,
          kind_db: backup.backup_kind==='mysql_native_physical_clone' ? 'Physical clone / '+backup.clone_role : backup.database,
          state: backup.state,
          server_uuid: backup.source.server_uuid,
          _raw: backup,
        }))}
        columns={[
          {
            key: 'backup_id',
            name: 'Backup',
            render: (_val, row) => <>{row._raw.backup_id}{row._raw.protection_endpoint_id && <Box>Registration: {row._raw.protection_endpoint_id}</Box>}</>,
          },
          {key: 'kind_db', name: 'Kind / database'},
          {key: 'state', name: 'State'},
          {key: 'server_uuid', name: 'Native source'},
          {
            key: '_protection',
            name: 'Protection',
            render: (_val, row) => <Button disabled={busy || row._raw.state==='retired'} aria-label={'Review retirement of backup '+row._raw.backup_id} onClick={() => run('review_retire',{backup_id:row._raw.backup_id,...(row._raw.protection_endpoint_id ? {protection_endpoint_id:row._raw.protection_endpoint_id} : {})},value => {setReview(value);setConfirmed(false);setRetired(null);})}>Review retirement</Button>,
          },
        ]}
        compact
        searchable={false}
        exportable={false}
      />
      <GridNavigation
        busy={busy}
        page={Math.floor((page.offset || 0) / 25)}
        pages={Math.max(1, Math.ceil((page.total || 0) / 25))}
        endKnown
        canNext={(page.offset || 0) + 25 < (page.total || 0)}
        onFirst={() => load(0)}
        onPrevious={() => load(Math.max(0, (page.offset || 0) - 25))}
        onNext={() => load((page.offset || 0) + 25)}
        onLast={() => load(Math.max(0, (Math.ceil((page.total || 0) / 25) - 1) * 25))}
      />
    </>}
    {review && <Box>
      <Alert severity="warning">{review.warning} Retiring a pending backup abandons its archive protection even if its native operation later returns.</Alert>
      <Box component="pre" aria-label="Managed backup retirement review" sx={{whiteSpace:'pre-wrap',maxHeight:260,overflow:'auto'}}>{JSON.stringify(review.backup,null,2)}</Box>
      <FormControlLabel label="Retire this backup from archive protection and recovery planning; keep its files" control={<Checkbox disabled={busy || !!retired} checked={confirmed} onChange={event => setConfirmed(event.target.checked)} />} />
      <Button disabled={busy || !confirmed || !!retired} onClick={() => run('retire',{review_id:review.review_id,review_digest:review.review_digest,confirmed:true,...(review.protection_endpoint_id ? {protection_endpoint_id:review.protection_endpoint_id} : {})},value => {setRetired(value);setConfirmed(false);setPage(null);})}>Confirm backup protection retirement</Button>
    </Box>}
    {retired && <Alert severity="success">Backup protection {retired.backup_id}: retired. Backup files remain; no native backup or restore was repeated.</Alert>}
    <MySQLRecoveryChains post={post} />
  </Box>;
}
MySQLBackupProtection.propTypes={post:PropTypes.func.isRequired};
