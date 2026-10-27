import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLSourceLogs from 'sources/Dialogs/MySQLSourceLogs';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLSourceLogs);
const review={job_id:'purge',review_digest:'exact',state:'reviewed',source:{server_uuid:'native'},
  options:{mode:'TO',to_file:'log.2'},purge_selection:{candidate_names:['log.1']},warnings:['Irreversible native source files'],execution_host:{kind:'native-database-server'}};

it('requires explicit removal authority and invalidates the review when its condition changes',async () => {
  const post=jest.fn().mockResolvedValue(review);render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Review native server log purge'}));
  await screen.findByLabelText('Native source log purge review');
  expect(screen.getByRole('button',{name:'Confirm native server log purge'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('I checked required backups and replicas and authorize permanent server log removal'));
  post.mockResolvedValue({...review,state:'native_acknowledged'});
  fireEvent.click(screen.getByRole('button',{name:'Confirm native server log purge'}));
  await screen.findByText(/Native SQL returned successfully/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_source_purge_start',request:{job_id:'purge',review_digest:'exact',confirmed:true}});
  expect(screen.getByRole('button',{name:'Confirm native server log purge'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Purge client read timeout (blank: none)'),{target:{value:''}});
  expect(screen.queryByLabelText('Native source log purge review')).not.toBeInTheDocument();
});

it('loads uncertain durable receipts and reconciles without issuing another purge',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...review,state:'unknown'}],total:1});
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load source log purge receipts'}));
  await screen.findByRole('table',{name:'Native source log purge receipts'});
  post.mockResolvedValue({...review,state:'unknown'});fireEvent.click(screen.getByRole('button',{name:'Inspect source log purge purge'}));
  await screen.findByText(/original SQL reply is unconfirmed/);
  fireEvent.click(screen.getByRole('button',{name:'Reconcile source log purge'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_source_purge_reconcile',request:{job_id:'purge'}}));
  expect(post.mock.calls.some(([value]) => value.action==='mysql_binlog_source_purge_start')).toBe(false);
});

it('separately confirms native GTID reset and invalidates authority when its sequence changes',async () => {
  const resetReview={...review,options:{to_sequence:null},reset_selection:{before_names:['log.1']}};
  const post=jest.fn().mockResolvedValue(resetReview);render(<Component post={post} reset />);
  expect(screen.queryByLabelText('Native purge condition')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Review native server log and GTID reset'}));
  await screen.findByLabelText('Native source log and GTID reset review');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_source_reset_review',request:{options:{to_sequence:null,timeout_seconds:60}}});
  const confirm=screen.getByRole('button',{name:'Confirm native server log and GTID reset'});
  expect(confirm).toBeDisabled();
  fireEvent.click(screen.getByLabelText('I checked backups, replicas and receivers and authorize removal of ALL server logs and GTID history'));
  expect(confirm).toBeEnabled();
  fireEvent.change(screen.getByLabelText('Reset initial log sequence (blank: native default)'),{target:{value:'17'}});
  expect(screen.queryByLabelText('Native source log and GTID reset review')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Review native server log and GTID reset'}));
  await screen.findByLabelText('Native source log and GTID reset review');
  fireEvent.click(screen.getByLabelText('I checked backups, replicas and receivers and authorize removal of ALL server logs and GTID history'));
  post.mockResolvedValue({...resetReview,state:'unknown'});fireEvent.click(screen.getByRole('button',{name:'Confirm native server log and GTID reset'}));
  await screen.findByText(/original SQL reply is unconfirmed/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_source_reset_start',request:{job_id:'purge',review_digest:'exact',confirmed:true}});
  fireEvent.click(screen.getByRole('button',{name:'Reconcile source log and GTID reset'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_source_reset_reconcile',request:{job_id:'purge'}}));
  expect(post.mock.calls.filter(([value]) => value.action==='mysql_binlog_source_reset_start')).toHaveLength(1);
});
