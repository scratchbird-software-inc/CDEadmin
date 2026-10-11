import PagedDataGrid from '../cdeadmin_ui/data/PagedDataGrid';
import {GridAction} from '../cdeadmin_ui/data/GridNavigation';
import DeleteOutlineIcon from '@mui/icons-material/DeleteOutline';
import {useLayoutEffect, useRef, useState} from 'react';
import PropTypes from 'prop-types';
import {Alert, Box, Button, Checkbox, FormControlLabel} from '@mui/material';
import gettext from 'sources/gettext';
import FormReference from '../cdeadmin_ui/navigation/FormReference';

export async function executePrivilegeQueue(items, post, isCurrent) {
  const receipts = [];
  let stopped = false;
  for (const item of items) {
    if (stopped || !isCurrent()) {
      receipts.push({...item, status: 'not-attempted'});
      continue;
    }
    try {
      const result = await post({action: 'visual_admin_apply', request: {
        plan_id: item.plan.plan_id, plan_digest: item.plan.plan_digest,
        confirmed: true,
        ...(item.databaseTargetId ? {database_target_id: item.databaseTargetId} : {}),
      }});
      receipts.push({...item, status: 'provider-response-recorded', result});
      stopped = result?.provider_result?.accepted !== true;
    } catch (error) {
      receipts.push({...item, status: 'unknown-or-failed',
        error: error?.response?.data?.errormsg || error?.message || 'Response unavailable'});
      stopped = true;
    }
  }
  return receipts;
}

export default function FirebirdPrivilegeQueue({post, candidate, disabled,
  consumePlan, beginExecution, endExecution, onApplied}) {
  const [queue, setQueue] = useState({post, items: []});
  const [confirmed, setConfirmed] = useState(false);
  const [receipts, setReceipts] = useState([]);
  const [receiptScope, setReceiptScope] = useState(() => post);
  const active = useRef(false);
  const currentPost = useRef(post);
  useLayoutEffect(() => {
    currentPost.current = post;
    setQueue({post, items: []});
    setConfirmed(false);
    return () => {currentPost.current = null;};
  }, [post]);
  const items = queue.post === post ? queue.items : [];
  const add = () => {
    if (disabled || active.current || !candidate || items.length >= 500 ||
        items.some((item) => item.plan.plan_id === candidate.plan.plan_id)) return;
    setQueue({post, items: [...items, JSON.parse(JSON.stringify(candidate))]});
    setConfirmed(false);
    consumePlan();
  };
  const execute = async () => {
    if (disabled || active.current || !confirmed || !items.length ||
        currentPost.current !== post || !beginExecution()) return;
    active.current = true;
    setQueue({post, items: []});
    setConfirmed(false);
    setReceipts([]);
    setReceiptScope(() => post);
    try {
      const results = await executePrivilegeQueue(items, post,
        () => currentPost.current === post);
      setReceipts(results);
      // Refresh only after all dispatches; refresh failure cannot replay a plan.
      if (currentPost.current === post && onApplied) {
        for (const item of results.filter((entry) => entry.result)) {
          if (currentPost.current !== post) break;
          try { await onApplied(item); }
          catch (error) {
            setReceipts((prior) => prior.map((entry) => entry === item ?
              {...entry, refresh_error: error?.message || 'Metadata refresh failed'} : entry));
          }
        }
      }
    } finally {
      active.current = false;
      endExecution();
    }
  };
  const visibleReceipts = receiptScope === post ? receipts : [];
  if (!candidate && !items.length && !visibleReceipts.length) return null;
  return <Box sx={{mt: 2}} aria-label={gettext('Firebird privilege statement queue')}>
    <FormReference formKey="firebird-privilege-queue" />
    <Alert severity="info">{gettext('Ordered GRANT/REVOKE plans. No batch atomicity or automatic retry. Review native receipts; staged work still requires its session owner to commit or roll back.')}</Alert>
    <Button disabled={disabled || !candidate || items.length >= 500} onClick={add}>
      {gettext('Add to statement list')}</Button>
    {items.length > 0 && <Box sx={{height: 320, minWidth: 0, overflow: 'auto'}}>
      <PagedDataGrid readOnly gridId="firebird/privilege-queue" aria-label={gettext('Queued privilege statements')}
        rows={items.map((item, index) => ({...item, __index: index}))}
        rowKeyGetter={row => row.plan.plan_id} rowHeight={90} columns={[
          {key: 'title', name: gettext('Statement'), width: 240,
            renderCell: ({row}) => `${row.__index + 1}. ${row.title} — ${row.target?.display_name || ''}`},
          {key: 'sql', name: gettext('SQL'), minWidth: 360,
            renderCell: ({row}) => <Box component="pre" sx={{m: 0, maxHeight: 80, overflow: 'auto', whiteSpace: 'pre-wrap'}}>{
              row.plan.command_preview?.statements?.map(statement => statement.source).join('\n')}</Box>},
          {key: 'remove', name: gettext('Remove'), width: 70, renderCell: ({row}) =>
            <GridAction label={`${gettext('Remove statement')} ${row.__index + 1}`} disabled={disabled}
              onClick={() => {
                setQueue({post, items: items.filter((_, position) => position !== row.__index)});
                setConfirmed(false);
              }}><DeleteOutlineIcon fontSize="small" /></GridAction>},
        ]} />
    </Box>}
    {items.length > 0 && <>
      <FormControlLabel control={<Checkbox checked={confirmed} disabled={disabled}
        onChange={(event) => setConfirmed(event.target.checked)} />}
      label={gettext('I confirm execution of this ordered statement list.')} />
      <Button disabled={disabled || !confirmed} onClick={execute}>{gettext('Execute all statements')}</Button>
    </>}
    {visibleReceipts.length > 0 && <Box component="pre" aria-label={gettext('Privilege queue receipts')}
      sx={{maxHeight: 360, overflow: 'auto', whiteSpace: 'pre-wrap'}}>{JSON.stringify(
        visibleReceipts.map(({title, target, status, result, error, refresh_error}) =>
          ({title, target, status, result, error, refresh_error})), null, 2)}</Box>}
  </Box>;
}

FirebirdPrivilegeQueue.propTypes = {
  post: PropTypes.func.isRequired, candidate: PropTypes.object,
  disabled: PropTypes.bool, consumePlan: PropTypes.func.isRequired,
  beginExecution: PropTypes.func.isRequired, endExecution: PropTypes.func.isRequired,
  onApplied: PropTypes.func,
};
