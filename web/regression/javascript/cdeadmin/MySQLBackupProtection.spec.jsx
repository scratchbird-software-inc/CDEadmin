import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLBackupProtection from 'sources/Dialogs/MySQLBackupProtection';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLBackupProtection);
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
