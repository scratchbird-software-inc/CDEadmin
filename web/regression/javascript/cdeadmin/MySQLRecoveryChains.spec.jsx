import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLRecoveryChains from 'sources/Dialogs/MySQLRecoveryChains';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLRecoveryChains);
const backup={backup_id:'base',database:'native',state:'native_dump_returned',native_dump_completion_acknowledged:true,native_consistent:true,native_gtid_snapshot_inconsistent:false};
const archive={job_id:'archive',state:'completed'};

it('reviews ordered native dependencies and requires source lineage authority before file protection',async()=> {
  const post=jest.fn().mockImplementation(({action})=>Promise.resolve(
    action.endsWith('backup_protection_list') ? {backups:[backup],total:1,offset:0} :
      action==='mysql_binlog_list' ? {jobs:[archive,{job_id:'second',state:'completed'}],total:2,offset:0} :
        action.endsWith('recovery_chain_review') ? {review_id:'review',review_digest:'exact',inputs:{database:'native'}} :
          {chain_id:'chain',state:'active'}));
  render(<Component post={post} />);fireEvent.click(screen.getByText('Recovery chain dependencies'));
  fireEvent.click(screen.getByRole('button',{name:'Load recovery base backups'}));
  fireEvent.click(await screen.findByRole('button',{name:'Use backup base'}));
  fireEvent.click(screen.getByRole('button',{name:'Load recovery chain archives'}));
  fireEvent.click(await screen.findByRole('button',{name:'Append archive archive'}));
  fireEvent.click(screen.getByRole('button',{name:'Append archive second'}));
  fireEvent.click(screen.getByRole('button',{name:'Move second earlier'}));
  fireEvent.click(screen.getByRole('button',{name:'Review recovery dependencies'}));
  await screen.findByLabelText('Recovery dependency review');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_recovery_chain_review',request:{backup_id:'base',archive_job_ids:['second','archive'],stop_mode:'all',stop_gtid:null}});
  expect(screen.getByRole('button',{name:'Protect reviewed recovery chain'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('I confirm these inputs belong to the original source GTID lineage'));
  fireEvent.click(screen.getByRole('button',{name:'Protect reviewed recovery chain'}));
  await screen.findByText(/Recovery chain chain: active/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_recovery_chain_activate',request:{review_id:'review',review_digest:'exact',confirmed:true,source_lineage_confirmed:true}});
  expect(post.mock.calls.some(([request])=>request.action.includes('backup_protection_retire'))).toBe(false);
  expect(screen.getByText(/Recovery and cutover have not been verified/)).toBeInTheDocument();
});

it('releases only the reviewed chain after separate retirement confirmation',async()=> {
  const chain={chain_id:'chain',state:'active',database:'native',archives:[archive]};
  const post=jest.fn().mockImplementation(({action})=>Promise.resolve(action.endsWith('chain_list') ? {chains:[chain],total:1,offset:0} :
    action.endsWith('review_retire') ? {chain,review_id:'retire-review',review_digest:'exact'} : {...chain,state:'retired'}));
  render(<Component post={post} />);fireEvent.click(screen.getByText('Recovery chain dependencies'));
  fireEvent.click(screen.getByRole('button',{name:'Load recovery chains'}));
  fireEvent.click(await screen.findByRole('button',{name:'Review retirement of chain chain'}));
  await screen.findByLabelText('Recovery dependency retirement');
  expect(screen.getByRole('button',{name:'Confirm recovery chain retirement'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Release this recovery chain\'s archive protection'));
  fireEvent.click(screen.getByRole('button',{name:'Confirm recovery chain retirement'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_recovery_chain_retire',request:{review_id:'retire-review',review_digest:'exact',confirmed:true}}));
  expect(post.mock.calls.every(([request])=>request.action.startsWith('mysql_binlog_recovery_chain_'))).toBe(true);
});
