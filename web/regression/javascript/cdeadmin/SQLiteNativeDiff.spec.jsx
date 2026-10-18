import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteNativeDiff from 'sources/Dialogs/SQLiteNativeDiff';
import {withTheme} from '../fake_theme';

const Component=withTheme(SQLiteNativeDiff),reviewed={job_id:'native-diff',state:'reviewed',review_digest:'exact-diff',warnings:[]};
const artifact={native_kind:'changeset',input_name:'difference.native',native_iterator_complete:true,native_record_count:'3'};
function api(started='completed') {return jest.fn(request => {
  const operation=request.action.replace('sqlite_changeset_diff_','');
  return Promise.resolve(operation==='catalog' ? {schemas:[{name:'main',filename:'owned.sqlite'},{name:'old',filename:''}],transaction_open:true,scope:'current connection'} :
    operation==='tables' ? {tables:[{name:'native 雪',definition:'CREATE TABLE "native 雪"(id PRIMARY KEY)'}]} :
      operation==='review' ? reviewed : operation==='cancel' ? {...reviewed,state:'cancel_requested'} : {...reviewed,state:started,result:{artifact}});
});}

async function review(post,ensureSession=undefined) {
  const selected=jest.fn();
  render(<Component post={post} databaseTargetId="owned-file" sessionId={ensureSession ? undefined : 'owned-session'} ensureSession={ensureSession} onSelected={selected} />);
  fireEvent.click(screen.getByText('SQLite managed table differences'));
  fireEvent.click(screen.getByRole('button',{name:'Inspect retained table comparison support'}));
  fireEvent.click(await screen.findByRole('button',{name:'Load native comparison tables'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'sqlite_changeset_diff_tables'})));
  fireEvent.mouseDown(screen.getByLabelText('Exact native comparison table'));
  fireEvent.click(await screen.findByRole('option',{name:'native 雪'}));
  fireEvent.click(screen.getByRole('button',{name:'Review native table comparison'}));
  await screen.findByRole('button',{name:'Start reviewed native table comparison'});
  return selected;
}

it('reviews exact retained comparison options and requires confirmation before native dispatch',async () => {
  const height=window.innerHeight;Object.defineProperty(window,'innerHeight',{configurable:true,value:4096});
  try {
    const post=api(),selected=await review(post);
    expect(post).toHaveBeenLastCalledWith({action:'sqlite_changeset_diff_review',request:{database_target_id:'owned-file',session_id:'owned-session',
      options:{database:'main',source_database:'old',table_name:'native 雪',kind:'changeset',estimate_size:false,track_rowids:false,timeout_seconds:3600}}});
    expect(screen.getByRole('button',{name:'Start reviewed native table comparison'})).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Confirm disposable native table comparison'));
    fireEvent.click(screen.getByRole('button',{name:'Start reviewed native table comparison'}));
    await screen.findByRole('button',{name:'Use native table difference for apply'});
    expect(post).toHaveBeenLastCalledWith({action:'sqlite_changeset_diff_start',request:{database_target_id:'owned-file',job_id:'native-diff',review_digest:'exact-diff',confirmed:true}});
    fireEvent.click(screen.getByRole('button',{name:'Use native table difference for apply'}));
    expect(selected).toHaveBeenCalledWith(expect.objectContaining({job_id:'native-diff',state:'completed',result:{artifact}}));
  } finally {Object.defineProperty(window,'innerHeight',{configurable:true,value:height});}
});

it('opens a query session when needed and sends a separate durable cancellation request',async () => {
  const height=window.innerHeight;Object.defineProperty(window,'innerHeight',{configurable:true,value:4096});
  try {
    const post=api('active'),ensureSession=jest.fn(() => Promise.resolve('new-session'));await review(post,ensureSession);
    expect(ensureSession).toHaveBeenCalled();
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({request:expect.objectContaining({session_id:'new-session'})}));
    fireEvent.click(screen.getByLabelText('Confirm disposable native table comparison'));
    fireEvent.click(screen.getByRole('button',{name:'Start reviewed native table comparison'}));
    fireEvent.click(await screen.findByRole('button',{name:'Cancel native table comparison'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'sqlite_changeset_diff_cancel',request:{database_target_id:'owned-file',job_id:'native-diff'}}));
    expect(screen.queryByRole('button',{name:'Use native table difference for apply'})).not.toBeInTheDocument();
  } finally {Object.defineProperty(window,'innerHeight',{configurable:true,value:height});}
});

it('discards an outstanding catalog reply after the retained session changes',async () => {
  let resolve;const post=jest.fn(() => new Promise(done => {resolve=done;}));
  const {rerender}=render(<Component post={post} databaseTargetId="owned-file" sessionId="original" onSelected={jest.fn()} />);
  fireEvent.click(screen.getByText('SQLite managed table differences'));fireEvent.click(screen.getByRole('button',{name:'Inspect retained table comparison support'}));
  rerender(<Component post={post} databaseTargetId="owned-file" sessionId="replacement" onSelected={jest.fn()} />);
  resolve({schemas:[{name:'stale',filename:''}],scope:'obsolete connection',transaction_open:true});
  await waitFor(() => expect(screen.getByRole('button',{name:'Inspect retained table comparison support'})).toBeEnabled());
  expect(screen.queryByText(/obsolete connection/)).not.toBeInTheDocument();
});
