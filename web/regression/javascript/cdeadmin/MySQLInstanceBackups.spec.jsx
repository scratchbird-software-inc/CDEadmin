import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLInstanceBackups from 'sources/Dialogs/MySQLInstanceBackups';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLInstanceBackups);
it('requires a source-bound review before a full instance backup and submits the exact native account options',async()=> {
  const review={job_id:'owned',review_digest:'exact',state:'reviewed',source:{server_uuid:'source'},options:{native_options:{users:true}},warnings:['Native snapshot pause'],execution_host:{kind:'application-host'}};
  const post=jest.fn().mockResolvedValue(review);
  render(<Component post={post} endpointUrl="/workspace/owned" />);
  expect(screen.queryByRole('button',{name:'Confirm and start instance backup'})).not.toBeInTheDocument();
  fireEvent.change(screen.getByLabelText('Native instance backup options'),{target:{value:JSON.stringify({users:false,include_schemas:['native'],threads:2})}});
  fireEvent.click(screen.getByRole('button',{name:'Review full-instance backup'}));
  await screen.findByLabelText('Instance backup review');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_instance_backup_review',request:{options:{users:false,include_schemas:['native'],threads:2}}});
  post.mockResolvedValue({...review,state:'completed',native_dump_acknowledged:true,result:{artifact:{schemas:[]}}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start instance backup'}));
  await screen.findByText(/Native dump reply acknowledged: yes/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_instance_backup_start',request:{job_id:'owned',review_digest:'exact',confirmed:true}});
  expect(screen.getByRole('button',{name:'Confirm and start instance backup'})).toBeDisabled();
});
it('preserves a missing native reply after explicit file reconciliation and retries only private-script cleanup',async()=> {
  const failed={job_id:'owned',source:{server_uuid:'native'},state:'native_returned_unverified',native_dump_acknowledged:true,
    result:{private_script_cleanup:{complete:false}},private_script_cleanup:{complete:false}};
  const post=jest.fn().mockResolvedValue({jobs:[failed],total:1,offset:0});
  render(<Component post={post} endpointUrl="/workspace/owned" />);
  fireEvent.click(screen.getByRole('button',{name:'Load instance backup jobs'}));
  await screen.findByRole('table',{name:'Instance backup jobs'});
  post.mockResolvedValue(failed);fireEvent.click(screen.getByRole('button',{name:'Inspect instance backup owned'}));
  await screen.findByRole('button',{name:'Retry private-script cleanup'});
  post.mockResolvedValue({...failed,result:{private_script_cleanup:{complete:true}},private_script_cleanup:{complete:true}});
  fireEvent.click(screen.getByRole('button',{name:'Retry private-script cleanup'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_instance_backup_cleanup_script',request:{job_id:'owned'}}));
  post.mockResolvedValue({...failed,state:'artifact_verified',native_dump_acknowledged:false,result:{artifact:{schemas:[]}}});
  fireEvent.click(screen.getByRole('button',{name:'Verify instance backup files'}));
  await screen.findByText(/File acceptance does not change the original native reply/);
  expect(screen.getByText(/Native dump reply acknowledged: no/)).toBeInTheDocument();
  expect(post.mock.calls.every(([request])=>!request.action.includes('restore') && request.action!=='mysql_instance_backup_start')).toBe(true);
});
it('can cancel an interrupted durable backup without treating cancellation as completion',async()=> {
  const receipt={job_id:'interrupted',source:{server_uuid:'source'},state:'unknown',native_dump_acknowledged:false,durable_tool:{name:'native'},native_process_termination_confirmed:false};
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_instance_backup_list' ? {jobs:[receipt],total:1,offset:0} : receipt));
  render(<Component post={post} endpointUrl="/workspace/owned" />);fireEvent.click(screen.getByRole('button',{name:'Load instance backup jobs'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect instance backup interrupted'}));
  fireEvent.click(await screen.findByRole('button',{name:'Cancel instance backup'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_instance_backup_cancel',request:{job_id:'interrupted'}}));
  expect(screen.getByText(/Native dump reply acknowledged: no/)).toBeInTheDocument();
  expect(post.mock.calls.some(([value])=>value.action==='mysql_instance_backup_start')).toBe(false);
});
it('observes original source locks separately from dump acknowledgement and file acceptance',async()=> {
  const receipt={job_id:'owned',source:{server_uuid:'native'},state:'native_returned_unverified',native_dump_acknowledged:true,server_lock_owner:{admitted:true}};
  const post=jest.fn().mockResolvedValue({jobs:[receipt],total:1,offset:0});
  render(<Component post={post} endpointUrl="/workspace/owned" />);
  fireEvent.click(screen.getByRole('button',{name:'Load instance backup jobs'}));
  await screen.findByRole('table',{name:'Instance backup jobs'});
  post.mockResolvedValue(receipt);fireEvent.click(screen.getByRole('button',{name:'Inspect instance backup owned'}));
  await screen.findByRole('button',{name:'Observe original source lock cleanup'});
  post.mockResolvedValue({...receipt,source_lock_cleanup_observation:{qualified:true,released:true}});
  fireEvent.click(screen.getByRole('button',{name:'Observe original source lock cleanup'}));
  await screen.findByText(/Original source lock cleanup: confirmed/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_instance_backup_observe_source_locks',request:{job_id:'owned'}});
  expect(screen.getByText(/Native dump reply acknowledged: yes/)).toBeInTheDocument();
  expect(post.mock.calls.some(([request])=>['mysql_instance_backup_reconcile','mysql_instance_backup_start'].includes(request.action))).toBe(false);
});
