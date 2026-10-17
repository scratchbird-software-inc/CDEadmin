import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteRecovery from 'sources/Dialogs/SQLiteRecovery';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/data/PagedDataGrid',() => function Grid({rows}) {
  return <div data-testid="recovery-facts">{JSON.stringify(rows)}</div>;
});
const Component=withTheme(SQLiteRecovery);
const viewportHeight=window.innerHeight;
beforeAll(() => {window.innerHeight=1200;});
afterAll(() => {window.innerHeight=viewportHeight;});
const catalog={execution_host:{name:'native-host',platform:'linux'},runtime:{available:true,native:{version:'3.53.0'}},
  targets:[{target_id:'file-one',display_name:'First file',path:'/native/first.sqlite'},
    {target_id:'file-two',display_name:'Second file',path:'/native/second.sqlite'}]};
const review={job_id:'owned-job',review_digest:'native-digest',state:'reviewed',warnings:[],
  source:{output_path:'/native/recovered.sqlite'}};

it('reviews exact file options and requires confirmation before native dispatch',async () => {
  const changed=jest.fn();
  const post=jest.fn(({action}) => Promise.resolve(action==='sqlite_recovery_catalog' ? catalog :
    action==='sqlite_recovery_review' ? review : action==='sqlite_recovery_activate' ?
      {database_target_id:'recovered-target',receipt:{...review,state:'completed',activated_target_id:'recovered-target'}} :
      {...review,state:'completed',result:{integrity_check:'ok',application_data_verified:false,
        tables:[{name:'healthy',row_count:'9007199254740993',readable:true}]}}));
  render(<Component post={post} databaseTargetId="file-one" onTargetCatalogChanged={changed} />);
  await screen.findByText('Native SQLite recovery: 3.53.0');
  fireEvent.change(screen.getByLabelText('New recovered database filename (application host)'),{target:{value:'/native/recovered.sqlite'}});
  fireEvent.click(screen.getByLabelText('Writers to the source file are stopped or isolated'));
  fireEvent.click(screen.getByRole('button',{name:'Review native recovery'}));
  await screen.findByText(/Recovery state: reviewed/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_recovery_review',request:{database_target_id:'file-one',options:{
    output_path:'/native/recovered.sqlite',source_isolated:true,include_freelist:false,preserve_rowids:true,
    lost_and_found:'recovered_orphans',timeout_seconds:3600}}});
  expect(screen.getByRole('button',{name:'Start reviewed recovery'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm recovery into this new file'));
  fireEvent.click(screen.getByRole('button',{name:'Start reviewed recovery'}));
  await screen.findByText(/Recovery state: completed/);
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_recovery_start',request:{database_target_id:'file-one',job_id:'owned-job',review_digest:'native-digest',confirmed:true}});
  expect(screen.getByText(/Application data still requires verification/)).toBeInTheDocument();
  expect(screen.getByTestId('recovery-facts')).toHaveTextContent('9007199254740993');
  fireEvent.click(screen.getByRole('button',{name:'Register and activate recovered copy'}));
  await waitFor(() => expect(changed).toHaveBeenCalledTimes(1));
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_recovery_activate',request:{database_target_id:'file-one',job_id:'owned-job',confirmation:'/native/recovered.sqlite'}});
});

it('drops a stale review when the selected registered file changes',async () => {
  let resolve;
  const pending=new Promise(accept => {resolve=accept;});
  const post=jest.fn(({action}) => action==='sqlite_recovery_review' ? pending : Promise.resolve(catalog));
  const {rerender}=render(<Component post={post} databaseTargetId="file-one" />);
  await screen.findByText('Native SQLite recovery: 3.53.0');
  fireEvent.click(screen.getByRole('button',{name:'Review native recovery'}));
  rerender(<Component post={post} databaseTargetId="file-two" />);
  await screen.findByText('Source file: /native/second.sqlite');
  await act(async () => {resolve(review);});
  expect(screen.queryByText(/Recovery state: reviewed/)).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Start reviewed recovery'})).not.toBeInTheDocument();
});

it('stops consuming old-file poll replies without cancelling the background recovery',async () => {
  let resolve;
  const pending=new Promise(accept => {resolve=accept;});
  const post=jest.fn(({action}) => action==='sqlite_recovery_status' ? pending : Promise.resolve(
    action==='sqlite_recovery_catalog' ? catalog : action==='sqlite_recovery_review' ? review : {...review,state:'active'}));
  const {rerender,unmount}=render(<Component post={post} databaseTargetId="file-one" />);
  await screen.findByText('Native SQLite recovery: 3.53.0');
  fireEvent.click(screen.getByRole('button',{name:'Review native recovery'}));
  await screen.findByText(/Recovery state: reviewed/);
  fireEvent.click(screen.getByLabelText('Confirm recovery into this new file'));
  fireEvent.click(screen.getByRole('button',{name:'Start reviewed recovery'}));
  await waitFor(() => expect(post).toHaveBeenCalledWith({action:'sqlite_recovery_status',request:{database_target_id:'file-one',job_id:'owned-job'}}));
  rerender(<Component post={post} databaseTargetId="file-two" />);
  await screen.findByText('Source file: /native/second.sqlite');
  await act(async () => {resolve({...review,state:'completed'});});
  expect(screen.queryByText(/Recovery state: completed/)).not.toBeInTheDocument();
  unmount();
  expect(post.mock.calls.some(([value]) => value.action==='sqlite_recovery_cancel')).toBe(false);
});

it('keeps uncertain receipts readable when the recovery runtime is unavailable',async () => {
  const unknown={...review,state:'unknown_outcome'};
  const post=jest.fn(({action}) => Promise.resolve(action==='sqlite_recovery_catalog' ?
    {...catalog,runtime:{available:false,reason:'Native recovery runtime unavailable'}} :
    action==='sqlite_recovery_list' ? {jobs:[unknown],more:false,total:1} : unknown));
  render(<Component post={post} databaseTargetId="file-one" />);
  await screen.findByText('Native recovery runtime unavailable');
  expect(screen.getByRole('button',{name:'Review native recovery'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Load recovery receipts'}));
  const selected=await screen.findByLabelText('Retained recovery job');fireEvent.mouseDown(selected);
  fireEvent.click(await screen.findByRole('option',{name:'owned-job — unknown_outcome'}));
  await screen.findByText(/Recovery state: unknown_outcome/);
  expect(screen.queryByRole('button',{name:'Start reviewed recovery'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Register and activate recovered copy'})).not.toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Remove staged images'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Reconcile recovered file'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'sqlite_recovery_reconcile',request:{database_target_id:'file-one',job_id:'owned-job'}}));
});
