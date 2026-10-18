import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteNativeSessions from 'sources/Dialogs/SQLiteNativeSessions';
import {withTheme} from '../fake_theme';

const Component=withTheme(SQLiteNativeSessions);
const capture={capture_id:'native-capture',database:'main',enabled:true,indirect:false,empty:true,
  estimate_size:true,track_rowids:true,memory_bytes:'9007199254740993',changeset_estimate_bytes:'0',tables:[]};

it('opens and controls captures on the selected SQLite connection with exact table identities',async () => {
  const post=jest.fn().mockResolvedValue({captures:[],offset:0,total:0,more:false,helper_available:true}),ensure=jest.fn().mockResolvedValue('owned-query-session'),busy=jest.fn();
  render(<Component post={post} ensureSession={ensure} databaseTargetId="file-target" onBusyChange={busy} />);
  fireEvent.click(screen.getByText('SQLite native captures'));fireEvent.click(screen.getByRole('button',{name:'Inspect native captures'}));
  await screen.findByRole('button',{name:'Open native capture'});
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_native_sessions',session_id:'owned-query-session',database_target_id:'file-target',request:{operation:'inventory',offset:0,limit:25}});
  fireEvent.click(screen.getByLabelText('Track changeset size estimate'));fireEvent.click(screen.getByLabelText('Track tables through native rowids'));
  post.mockResolvedValue({capture,program:{adapter_abi:1}});fireEvent.click(screen.getByRole('button',{name:'Open native capture'}));
  await screen.findByText(/Native memory bytes: 9007199254740993/);
  expect(post.mock.calls.at(-1)[0].request).toEqual({operation:'open',database:'main',estimate_size:true,track_rowids:true});
  fireEvent.change(screen.getByLabelText('Exact native capture table'),{target:{value:'native\n雪'}});
  fireEvent.click(screen.getByRole('button',{name:'Attach native capture tables'}));
  await waitFor(() => expect(post.mock.calls.at(-1)[0].request).toEqual({operation:'attach',capture_id:'native-capture',table_name:'native\n雪'}));
  expect(screen.getByRole('button',{name:'Close native capture'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Discard this capture and any unexported changes'));
  post.mockResolvedValue({closed:true,capture_id:'native-capture'});fireEvent.click(screen.getByRole('button',{name:'Close native capture'}));
  await waitFor(() => expect(screen.queryByRole('button',{name:'Close native capture'})).not.toBeInTheDocument());
});

it('clears a capture after its query connection changes',async () => {
  const post=jest.fn().mockResolvedValue({captures:[capture],offset:0,total:1,more:false,helper_available:true}),ensure=jest.fn(),busy=jest.fn();
  const {rerender}=render(<Component post={post} ensureSession={ensure} sessionId="first" databaseTargetId="file-target" onBusyChange={busy} />);
  fireEvent.click(screen.getByText('SQLite native captures'));fireEvent.click(screen.getByRole('button',{name:'Inspect native captures'}));
  await screen.findByRole('button',{name:'Inspect capture native-capture'});post.mockResolvedValue({capture});
  fireEvent.click(screen.getByRole('button',{name:'Inspect capture native-capture'}));await screen.findByRole('button',{name:'Refresh native capture'});
  rerender(<Component post={post} ensureSession={ensure} sessionId="second" databaseTargetId="file-target" onBusyChange={busy} />);
  await waitFor(() => expect(screen.queryByRole('button',{name:'Refresh native capture'})).not.toBeInTheDocument());
});
