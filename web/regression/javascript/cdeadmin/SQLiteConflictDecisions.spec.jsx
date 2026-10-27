import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteConflictDecisions from 'sources/Dialogs/SQLiteConflictDecisions';
import {withTheme} from '../fake_theme';
import {startBrowserFileDownload} from 'sources/Dialogs/browserFileDownload';
jest.mock('sources/Dialogs/browserFileDownload',() => ({startBrowserFileDownload:jest.fn(() => jest.fn())}));
const Component=withTheme(SQLiteConflictDecisions);
const challenge='A'.repeat(32),pending={challenge,sequence:'9007199254740993',kind:'conflict',waiting:true};
const receipt={job_id:'native-apply',state:'active',pending_conflict:pending};
const event={challenge,sequence:pending.sequence,kind:3,kind_name:'conflict',allowed_choices:['omit','replace','abort'],incoming:{new_values:[{native_type:'integer',data:'9223372036854775807'}]},current_values:[{native_type:'text',preview_text:'target 雪'}],byte_values:[{side:'current',column_index:1,native_type:'blob',byte_length:'9007199254740993'}]};

it('binds full value downloads and remembered live decisions to their native challenge',async () => {
  const changed={...receipt,conflict_response:{challenge,choice:'replace'}},onReceipt=jest.fn();
  const post=jest.fn(async value => value.action==='sqlite_changeset_conflict' ? {event} : changed);
  const {rerender}=render(<Component post={post} databaseTargetId="file-target" endpointUrl="/workspace" receipt={receipt} onReceipt={onReceipt} />);
  await screen.findByRole('button',{name:'Use native replace for this conflict'});
  expect(post.mock.calls[0][0]).toEqual({action:'sqlite_changeset_conflict',request:{database_target_id:'file-target',job_id:'native-apply',challenge}});
  fireEvent.click(screen.getByRole('button',{name:'Download current column 2 bytes'}));
  expect(startBrowserFileDownload).toHaveBeenCalledWith('/workspace',{database_target_id:'file-target',job_id:'native-apply',challenge,side:'current',column_index:1},expect.objectContaining({action:'sqlite_changeset_conflict_value_download'}));
  fireEvent.click(screen.getByLabelText('Use this choice for remaining conflicts of this kind'));fireEvent.click(screen.getByRole('button',{name:'Use native replace for this conflict'}));
  await waitFor(() => expect(onReceipt).toHaveBeenCalledWith(changed));
  expect(post.mock.calls.at(-1)[0]).toEqual({action:'sqlite_changeset_decide',request:{database_target_id:'file-target',job_id:'native-apply',response:{challenge,choice:'replace',remember_kind:true}}});
  rerender(<Component post={post} databaseTargetId="file-target" receipt={changed} onReceipt={onReceipt} />);
  expect(screen.getByRole('button',{name:'Use native replace for this conflict'})).toBeDisabled();
});

it('offers only native choices for an aggregate foreign-key conflict',async () => {
  const post=jest.fn().mockResolvedValue({event:{...event,kind:5,kind_name:'foreign_key',foreign_key_count:3,allowed_choices:['omit','abort'],byte_values:[]}});
  render(<Component post={post} databaseTargetId="file-target" receipt={{...receipt,pending_conflict:{...pending,kind:'foreign_key'}}} onReceipt={jest.fn()} />);
  await screen.findByText(/Native foreign-key violations: 3/);
  expect(screen.queryByRole('button',{name:'Use native replace for this conflict'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Use native omit for this conflict'})).toBeEnabled();
});

it('discards a conflict body received after its native callback changed',async () => {
  let resolveFirst;const first=new Promise(resolve => {resolveFirst=resolve;});
  const nextChallenge='B'.repeat(32);const post=jest.fn(async value => value.request.challenge===challenge ? first : {event:{...event,challenge:nextChallenge,kind_name:'data'}});
  const {rerender}=render(<Component post={post} databaseTargetId="file-target" receipt={receipt} onReceipt={jest.fn()} />);
  rerender(<Component post={post} databaseTargetId="file-target" receipt={{...receipt,pending_conflict:{...pending,challenge:nextChallenge}}} onReceipt={jest.fn()} />);
  await screen.findByText(/Native data conflict/);
  await act(async () => {resolveFirst({event});await first;});
  expect(screen.queryByText(/Native conflict conflict/)).not.toBeInTheDocument();
});
