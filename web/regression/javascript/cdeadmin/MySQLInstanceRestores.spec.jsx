import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLInstanceRestores from 'sources/Dialogs/MySQLInstanceRestores';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLInstanceRestores);
it('requires target inspection, an owned backup and exact confirmation before explicitly starting a reviewed load',async()=> {
  const target={identity:{server_uuid:'target-uuid'}},backup={job_id:'backup',state:'completed'};
  const review={job_id:'restore',review_digest:'digest',state:'reviewed',target:target.identity,warnings:[],source_backup:{job_id:'backup'}};
  const values={inspect:target,sources:{sources:[{server_id:4,name:'owned source'}],offset:0,total:1},backups:{jobs:[backup],offset:0,total:1},review,
    start:{...review,state:'native_load_returned',native_load_outcome:'returned'}};
  const post=jest.fn(({action})=>Promise.resolve(values[action.replace('mysql_instance_restore_','')]));
  render(<Component post={post} />);
  expect(screen.getByRole('button',{name:'Review full-instance restore'})).toBeDisabled();
  expect(screen.queryByRole('button',{name:'Confirm and start instance restore'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Inspect instance restore target'}));await screen.findByLabelText('Native instance restore target');
  fireEvent.click(screen.getByRole('button',{name:'Load instance backup sources'}));fireEvent.click(await screen.findByRole('button',{name:'Use backup source owned source'}));
  fireEvent.click(screen.getByRole('button',{name:'Load source instance backups'}));fireEvent.click(await screen.findByRole('button',{name:'Use instance backup backup'}));
  fireEvent.change(screen.getByLabelText('Confirm native restore target UUID'),{target:{value:'target-uuid'}});
  fireEvent.click(screen.getByRole('button',{name:'Review full-instance restore'}));await screen.findByLabelText('Instance restore review');
  expect(post.mock.calls.some(([value])=>value.action==='mysql_instance_restore_start')).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start instance restore'}));
  await screen.findByText(/Original native load outcome: returned/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_instance_restore_start',request:{job_id:'restore',review_digest:'digest',confirmed:true}});
  expect(screen.getByRole('button',{name:'Confirm and start instance restore'})).toBeDisabled();
});
it('observes an uncertain target separately and preserves its original outcome',async()=> {
  const receipt={job_id:'uncertain',state:'unknown',native_load_outcome:'unknown',target:{server_uuid:'target-uuid'}};
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_instance_restore_list' ? {jobs:[receipt],total:1,offset:0} : {...receipt,observation_digest:'observed'}));
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load instance restore jobs'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect instance restore uncertain'}));
  fireEvent.click(await screen.findByRole('button',{name:'Observe instance restore target'}));
  await screen.findByRole('button',{name:'Acknowledge observed target for another recovery'});
  fireEvent.change(screen.getByLabelText('Confirm native restore target UUID'),{target:{value:'target-uuid'}});
  fireEvent.click(screen.getByRole('button',{name:'Acknowledge observed target for another recovery'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_instance_restore_acknowledge',request:{job_id:'uncertain',target_confirmation:'target-uuid',observation_digest:'observed'}}));
  expect(screen.getByText(/Original native load outcome: unknown/)).toBeInTheDocument();
  expect(post.mock.calls.some(([value])=>value.action==='mysql_instance_restore_start')).toBe(false);
});
