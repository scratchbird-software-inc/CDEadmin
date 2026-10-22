import {fireEvent,render,screen} from '@testing-library/react';
import MySQLInstanceAcceptance from 'sources/Dialogs/MySQLInstanceAcceptance';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLInstanceAcceptance);
it('reviews and separately starts independent acceptance only after explicit write-pause consent',async()=> {
  const review={job_id:'acceptance',review_digest:'exact',state:'reviewed',target:{server_uuid:'target'},warnings:[]};
  const result={data:{requested:true,matched:true},definitions:{requested:true,matched:true},accounts:{requested:false,matched:null},server_locks_released:true};
  const post=jest.fn().mockResolvedValue(review);
  render(<Component post={post} sourceServerId={4} backupJobId="backup" targetUuid="target" targetConfirmation="target" />);
  fireEvent.click(screen.getByText('Independent dump acceptance'));
  expect(screen.getByRole('button',{name:'Review independent dump acceptance'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm server-wide write pause for independent acceptance'));
  fireEvent.click(screen.getByRole('button',{name:'Review independent dump acceptance'}));await screen.findByLabelText('Independent dump acceptance review');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_instance_acceptance_review',request:{source_server_id:4,backup_job_id:'backup',options:{threads:4,timeout_seconds:3600,target_confirmation:'target',server_wide_write_pause_confirmed:true}}});
  post.mockResolvedValue({...review,state:'verification_observed',acceptance_outcome:'matched',result});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start independent acceptance'}));
  await screen.findByText(/Recorded outcome: matched/);
  expect(screen.getByText('Not exported / not checked')).toBeInTheDocument();
  expect(post.mock.calls.some(([value])=>value.action.startsWith('mysql_instance_restore_'))).toBe(false);
});
it('keeps failed or cancelled checks unconfirmed instead of reporting a difference',async()=> {
  const receipt={job_id:'unconfirmed',state:'cancelled',acceptance_outcome:'unconfirmed',target:{server_uuid:'target'},result:{data:{requested:true,matched:null},server_locks_released:true}};
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_instance_acceptance_list' ? {jobs:[receipt],total:1,offset:0} : receipt));
  render(<Component post={post} />);fireEvent.click(screen.getByText('Independent dump acceptance'));
  fireEvent.click(screen.getByRole('button',{name:'Load independent acceptance jobs'}));fireEvent.click(await screen.findByRole('button',{name:'Inspect acceptance unconfirmed'}));
  await screen.findByRole('table',{name:'Recorded dump acceptance surfaces'});
  expect(screen.getByText('Unconfirmed')).toBeInTheDocument();expect(screen.queryByText('Different')).not.toBeInTheDocument();
  expect(post.mock.calls.some(([value])=>value.action==='mysql_instance_acceptance_start')).toBe(false);
});
