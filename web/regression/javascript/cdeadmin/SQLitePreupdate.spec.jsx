import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLitePreupdate from 'sources/Dialogs/SQLitePreupdate';
import {withTheme} from '../fake_theme';
const Component=withTheme(SQLitePreupdate);
const state={run_id:'generation-one',enabled:true,observed_events:'9007199254740993',retained_events:1,dropped_events:'1',retained_json_bytes:'300'};

it('starts bounded observations and admits event pages, stop and confirmed reset using the exact generation',async () => {
  const post=jest.fn().mockResolvedValue({helper_available:true,status:null}),ensure=jest.fn().mockResolvedValue('query-session'),busy=jest.fn();
  render(<Component post={post} ensureSession={ensure} databaseTargetId="file-target" onBusyChange={busy} />);
  fireEvent.click(screen.getByText('SQLite before-change diagnostics'));fireEvent.click(screen.getByRole('button',{name:'Inspect native preupdate support'}));
  await screen.findByRole('button',{name:'Start native preupdate observations'});
  post.mockResolvedValue({status:state});fireEvent.click(screen.getByRole('button',{name:'Start native preupdate observations'}));
  await screen.findByText(/Observed: 9007199254740993/);
  expect(post.mock.calls.at(-1)[0]).toEqual({action:'sqlite_native_preupdate',session_id:'query-session',database_target_id:'file-target',request:{operation:'start',max_events:1000,max_json_bytes:'16777216'}});
  const event={sequence:'9007199254740993',operation:'update',database:'main',table:'native\n雪',depth:2,new_values:[{native_type:'integer',data:'9223372036854775807'}]};
  post.mockResolvedValue({status:state,events:[event],more:true});fireEvent.click(screen.getByRole('button',{name:'Load first native preupdate events'}));
  await screen.findByText('Inspect native event 9007199254740993');
  fireEvent.click(screen.getByRole('button',{name:'Next native preupdate events'}));
  await waitFor(() => expect(post.mock.calls.at(-1)[0].request).toEqual({operation:'events',run_id:'generation-one',after_sequence:'9007199254740993',limit:25}));
  post.mockResolvedValue({status:{...state,enabled:false}});fireEvent.click(screen.getByRole('button',{name:'Stop native preupdate observations'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Stop native preupdate observations'})).toBeDisabled());
  expect(screen.getByRole('button',{name:'Clear native preupdate observations'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Discard retained before-change observations'));post.mockResolvedValue({status:{...state,run_id:'generation-two',enabled:false,retained_events:0}});
  fireEvent.click(screen.getByRole('button',{name:'Clear native preupdate observations'}));
  await waitFor(() => expect(screen.queryByText('Inspect native event 9007199254740993')).not.toBeInTheDocument());
  expect(post.mock.calls.at(-1)[0].request).toEqual({operation:'clear',run_id:'generation-one',confirmed:true});
});

it('drops observation state after switching query connections',async () => {
  const post=jest.fn().mockResolvedValue({helper_available:true,status:state}),ensure=jest.fn(),busy=jest.fn();
  const {rerender}=render(<Component post={post} ensureSession={ensure} sessionId="first" databaseTargetId="file-target" onBusyChange={busy} />);
  fireEvent.click(screen.getByText('SQLite before-change diagnostics'));fireEvent.click(screen.getByRole('button',{name:'Inspect native preupdate support'}));await screen.findByRole('button',{name:'Stop native preupdate observations'});
  rerender(<Component post={post} ensureSession={ensure} sessionId="second" databaseTargetId="file-target" onBusyChange={busy} />);
  await waitFor(() => expect(screen.queryByRole('button',{name:'Stop native preupdate observations'})).not.toBeInTheDocument());
});
