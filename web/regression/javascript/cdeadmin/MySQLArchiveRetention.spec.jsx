import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLArchiveRetention from 'sources/Dialogs/MySQLArchiveRetention';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLArchiveRetention);
const plan={job_id:'retention-job',review_digest:'exact-digest',state:'reviewed',warnings:['Protect the required recovery chain'],
  continuation:{archives:[{job_id:'old-archive',source:{server_uuid:'native-source',authenticated_principal:'archive@%'},created_at:1,bytes:'9007199254740993'}],
    total_bytes:'9007199254740993',eligible_count:1,excluded:{pinned:2}},execution_host:{kind:'application-host'}};

it('reviews exact policy and archive identities before removal and never rounds bytes',async () => {
  const post=jest.fn().mockResolvedValue(plan);
  render(<Component post={post} prefix="mysql_raw_binlog_" />);
  expect(post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Remove archives older than days'),{target:{value:'90'}});
  fireEvent.change(screen.getByLabelText('Keep latest archives per source and principal'),{target:{value:'3'}});
  fireEvent.click(screen.getByRole('button',{name:'Review archive retention'}));
  await screen.findByRole('table',{name:'Reviewed archive retention candidates'});
  expect(post).toHaveBeenLastCalledWith({action:'mysql_raw_binlog_retention_review',request:{policy:{retention_days:90,keep_latest:3}}});
  expect(screen.getByText('9007199254740993')).toBeInTheDocument();
  post.mockResolvedValue({...plan,state:'completed',result:{removed_job_ids:['old-archive']}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm removal of reviewed archives'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_raw_binlog_retention_start',request:{job_id:'retention-job',review_digest:'exact-digest',confirmed:true}}));
  expect(await screen.findByRole('button',{name:'Confirm removal of reviewed archives'})).toBeDisabled();
});

it('invalidates a review after policy edits and clears it when switching archive kind',async () => {
  const post=jest.fn().mockResolvedValue(plan);
  const {rerender}=render(<Component post={post} prefix="mysql_binlog_" />);
  fireEvent.click(screen.getByRole('button',{name:'Review archive retention'}));
  await screen.findByRole('table',{name:'Reviewed archive retention candidates'});
  fireEvent.change(screen.getByLabelText('Remove archives older than days'),{target:{value:'5'}});
  expect(screen.queryByRole('button',{name:'Confirm removal of reviewed archives'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Review archive retention'}));
  await screen.findByRole('table',{name:'Reviewed archive retention candidates'});
  rerender(<Component post={post} prefix="mysql_raw_binlog_" />);
  expect(screen.queryByRole('table',{name:'Reviewed archive retention candidates'})).not.toBeInTheDocument();
});

it('reconciles an interrupted receipt explicitly without starting another scan',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...plan,state:'interrupted'}],offset:0,total:1});
  render(<Component post={post} prefix="mysql_binlog_" />);
  fireEvent.click(screen.getByRole('button',{name:'Load retention receipts'}));
  await screen.findByRole('table',{name:'Archive retention receipts'});
  post.mockResolvedValue({...plan,state:'interrupted'});
  fireEvent.click(screen.getByRole('button',{name:'Inspect retention retention-job'}));
  await screen.findByText(/No automatic retry occurs/);
  post.mockResolvedValue({...plan,state:'reconciled',result:{removed_job_ids:[],unattempted_job_ids:['old-archive']}});
  fireEvent.click(screen.getByRole('button',{name:'Reconcile recorded removals'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_retention_reconcile',request:{job_id:'retention-job',confirmed:true}}));
  expect(await screen.findByLabelText('Archive retention observations')).toHaveTextContent('unattempted_job_ids');
});
