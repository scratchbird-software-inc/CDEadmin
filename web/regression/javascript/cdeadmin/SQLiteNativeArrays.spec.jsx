import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteNativeArrays from 'sources/Dialogs/SQLiteNativeArrays';
import {withTheme} from '../fake_theme';
const Component=withTheme(SQLiteNativeArrays);
const array={array_id:'owned-array',type_name:'int64',element_count:'1',native_data_bytes:'8',binding:{encoding:'carray',data:'owned-array'}};

it('creates a native typed array and loads ordinary carray SQL with an exact parameter envelope',async () => {
  const post=jest.fn().mockResolvedValue({arrays:[],offset:0,more:false,helper_available:true}),ensure=jest.fn().mockResolvedValue('query-session'),load=jest.fn(),busy=jest.fn();
  render(<Component post={post} ensureSession={ensure} databaseTargetId="file-target" onBusyChange={busy} onLoad={load} />);
  fireEvent.click(screen.getByText('SQLite native arrays'));fireEvent.click(screen.getByRole('button',{name:'Inspect native arrays'}));
  await screen.findByRole('button',{name:'Create native array'});
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_native_arrays',session_id:'query-session',database_target_id:'file-target',request:{operation:'inventory',offset:0,limit:25}});
  post.mockResolvedValue({array});fireEvent.click(screen.getByRole('button',{name:'Create native array'}));
  await screen.findByRole('button',{name:'Use native array in editor'});
  expect(post.mock.calls.at(-1)[0].request).toEqual({operation:'create',type:'int64',values:['9007199254740993']});
  fireEvent.click(screen.getByRole('button',{name:'Use native array in editor'}));
  expect(load).toHaveBeenCalledWith({source:'SELECT value, typeof(value) AS storage_class FROM carray(:items)',parameters:{items:array.binding}});
  expect(screen.getByRole('button',{name:'Close native array'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Release this array and its parameter bindings'));
  post.mockResolvedValue({closed:true,array_id:array.array_id});fireEvent.click(screen.getByRole('button',{name:'Close native array'}));
  await waitFor(() => expect(screen.queryByRole('button',{name:'Use native array in editor'})).not.toBeInTheDocument());
  expect(post.mock.calls.at(-1)[0].request).toEqual({operation:'close',array_id:array.array_id,confirmed:true});
});

it('clears array ownership when its retained query session changes',async () => {
  const post=jest.fn().mockResolvedValue({arrays:[array],offset:0,more:false,helper_available:true}),ensure=jest.fn(),busy=jest.fn(),load=jest.fn();
  const {rerender}=render(<Component post={post} ensureSession={ensure} sessionId="first" databaseTargetId="file-target" onBusyChange={busy} onLoad={load} />);
  fireEvent.click(screen.getByText('SQLite native arrays'));fireEvent.click(screen.getByRole('button',{name:'Inspect native arrays'}));
  await screen.findByRole('button',{name:'Inspect array owned-array'});post.mockResolvedValue({array});
  fireEvent.click(screen.getByRole('button',{name:'Inspect array owned-array'}));await screen.findByRole('button',{name:'Use native array in editor'});
  rerender(<Component post={post} ensureSession={ensure} sessionId="second" databaseTargetId="file-target" onBusyChange={busy} onLoad={load} />);
  await waitFor(() => expect(screen.queryByRole('button',{name:'Use native array in editor'})).not.toBeInTheDocument());
});
