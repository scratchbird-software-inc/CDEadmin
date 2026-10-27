import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import ReceiverFileCleanup from 'sources/Dialogs/ReceiverFileCleanup';
import {withTheme} from '../fake_theme';

const Component=withTheme(ReceiverFileCleanup);

it('reviews exact private files before removal and keeps uncertain acknowledgements visible',async () => {
  const post=jest.fn().mockResolvedValue({files:[{name:'native.000001',bytes:'9007199254740993'}],more:true,next_after:'native.000001'});
  render(<Component post={post} engine="mariadb" receiverJobId="owned-receiver" />);
  fireEvent.click(screen.getByText('Private receiver file cleanup'));
  fireEvent.click(screen.getByRole('button',{name:'Inspect private receiver files'}));
  await screen.findByText('9007199254740993');
  expect(screen.getByRole('button',{name:'Review private-file removal'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Remove native.000001'));
  const review={job_id:'cleanup',review_digest:'exact-files',state:'reviewed',warnings:['Unpublished changes may be lost']};
  post.mockResolvedValue(review);fireEvent.click(screen.getByRole('button',{name:'Review private-file removal'}));
  await screen.findByText('Unpublished changes may be lost');
  expect(post).toHaveBeenLastCalledWith({action:'mariadb_binlog_capture_cleanup_review',request:{job_id:'owned-receiver',file_names:['native.000001']}});
  post.mockResolvedValue({job_id:'cleanup',state:'unknown',progress:{removed_bytes:'0',removal_intent_recorded:true,removal_acknowledged:false}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and remove reviewed private files'}));
  await screen.findByText(/Private cleanup cleanup: unknown/);
  expect(post).toHaveBeenLastCalledWith({action:'mariadb_binlog_capture_cleanup_start',request:{job_id:'cleanup',review_digest:'exact-files',confirmed:true}});
  expect(screen.getByRole('button',{name:'Confirm and remove reviewed private files'})).toBeDisabled();
  expect(screen.getByLabelText('Private cleanup receipt')).toHaveTextContent('removal_acknowledged');
});

it('uses the returned filename cursor and clears selection on an endpoint change',async () => {
  const post=jest.fn().mockResolvedValue({files:[{name:'native.000001',bytes:'4'}],more:true,next_after:'native.000001'});
  const {rerender}=render(<Component post={post} engine="mysql" receiverJobId="one" />);
  fireEvent.click(screen.getByText('Private receiver file cleanup'));fireEvent.click(screen.getByRole('button',{name:'Inspect private receiver files'}));
  await screen.findByLabelText('Remove native.000001');
  post.mockResolvedValue({files:[],more:false});fireEvent.click(screen.getByRole('button',{name:'Next private-file page'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_capture_cleanup_catalog',request:{job_id:'one',after:'native.000001'}}));
  rerender(<Component post={post} engine="mysql" receiverJobId="two" />);
  await waitFor(() => expect(screen.queryByRole('table',{name:'Private receiver files'})).not.toBeInTheDocument());
});

it('explicitly reconciles an interrupted MySQL receipt without repeating its removal review',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{job_id:'interrupted'}],more:false});
  render(<Component post={post} engine="mysql" receiverJobId="owned-receiver" />);
  fireEvent.click(screen.getByText('Private receiver file cleanup'));
  fireEvent.click(screen.getByRole('button',{name:'Load private cleanup receipts'}));
  await screen.findByRole('button',{name:'Inspect cleanup interrupted'});
  post.mockResolvedValue({job_id:'interrupted',state:'unknown',progress:{removal_acknowledged:false}});
  fireEvent.click(screen.getByRole('button',{name:'Inspect cleanup interrupted'}));
  await screen.findByRole('button',{name:'Reconcile recorded private removal'});
  post.mockResolvedValue({job_id:'interrupted',state:'reconciled',result:{unattempted_files:['native.000002'],reconciliation_removed_bytes:'9'}});
  fireEvent.click(screen.getByRole('button',{name:'Reconcile recorded private removal'}));
  await screen.findByText(/Bytes removed during reconciliation: 9/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_capture_cleanup_reconcile',request:{job_id:'interrupted',confirmed:true}});
  expect(screen.queryByRole('button',{name:'Reconcile recorded private removal'})).not.toBeInTheDocument();
  expect(screen.getByLabelText('Private cleanup receipt')).toHaveTextContent('native.000002');
  expect(post.mock.calls.some(([value]) => value.action.endsWith('_start'))).toBe(false);
});
