import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLBackupProtection from 'sources/Dialogs/MySQLBackupProtection';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLBackupProtection);
it('shows physical clone role and retained uncertainty without claiming verified recovery',async () => {
  const post=jest.fn().mockResolvedValue({backups:[{backup_id:'clone',backup_kind:'mysql_native_physical_clone',clone_role:'registered_donor',
    source:{server_uuid:'observed-donor'},state:'native_clone_returned_unattested_source'}],total:1,offset:0});
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load managed backup protection'}));
  await screen.findByText('Physical clone / registered_donor');
  expect(screen.getByText('native_clone_returned_unattested_source')).toBeInTheDocument();
  expect(screen.getByText(/Remote clone source UUIDs are not attested/)).toBeInTheDocument();
});
it('retires an exact managed backup hold only after review and explicit authority, without repeating a backup',async () => {
  const backup={backup_id:'owned',database:'native',source:{server_uuid:'native-source'},state:'native_dump_returned'};
  const post=jest.fn().mockResolvedValue({backups:[backup],total:1,offset:0});render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load managed backup protection'}));
  await screen.findByRole('table',{name:'Managed backup protection'});
  post.mockResolvedValue({backup,review_id:'review',review_digest:'exact',warning:'Retire only this protection'});
  fireEvent.click(screen.getByRole('button',{name:'Review retirement of backup owned'}));
  await screen.findByLabelText('Managed backup retirement review');
  expect(screen.getByRole('button',{name:'Confirm backup protection retirement'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Retire this backup from archive protection and recovery planning; keep its files'));
  post.mockResolvedValue({...backup,state:'retired'});fireEvent.click(screen.getByRole('button',{name:'Confirm backup protection retirement'}));
  await screen.findByText(/Backup files remain; no native backup or restore was repeated/);
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_backup_protection_retire',request:{review_id:'review',review_digest:'exact',confirmed:true}}));
  expect(screen.getByRole('button',{name:'Confirm backup protection retirement'})).toBeDisabled();
  expect(post.mock.calls.every(([value]) => value.action.startsWith('mysql_binlog_backup_protection_'))).toBe(true);
});
it('inspects owner-wide holds and binds retirement to the selected registration scope',async()=> {
  const backup={backup_id:'orphan',database:'native',source:{server_uuid:'native-source'},state:'native_dump_returned',protection_endpoint_id:'removed-registration'};
  const post=jest.fn().mockImplementation(({action})=>Promise.resolve(action.endsWith('review_retire') ?
    {backup,review_id:'review',review_digest:'exact',protection_endpoint_id:'removed-registration'} :
    action.endsWith('retire') ? {...backup,state:'retired'} : {backups:[backup],total:1,offset:0}));
  render(<Component post={post} />);
  fireEvent.click(screen.getByLabelText('Show backup holds from all my registrations, including removed registrations'));
  fireEvent.click(screen.getByRole('button',{name:'Load managed backup protection'}));
  await screen.findByText('Registration: removed-registration');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_backup_protection_list',request:{offset:0,limit:25,all_registrations:true}});
  fireEvent.click(screen.getByRole('button',{name:'Review retirement of backup orphan'}));
  await screen.findByLabelText('Managed backup retirement review');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_backup_protection_review_retire',request:{backup_id:'orphan',protection_endpoint_id:'removed-registration'}});
  fireEvent.click(screen.getByLabelText('Retire this backup from archive protection and recovery planning; keep its files'));
  fireEvent.click(screen.getByRole('button',{name:'Confirm backup protection retirement'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_backup_protection_retire',request:{review_id:'review',review_digest:'exact',confirmed:true,protection_endpoint_id:'removed-registration'}}));
});
