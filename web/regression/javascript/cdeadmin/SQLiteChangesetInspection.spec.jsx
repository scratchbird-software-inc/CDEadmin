import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteChangesetInspection from 'sources/Dialogs/SQLiteChangesetInspection';
import {withTheme} from '../fake_theme';
import {startBrowserFileDownload} from 'sources/Dialogs/browserFileDownload';
jest.mock('sources/Dialogs/browserFileDownload',() => ({startBrowserFileDownload:jest.fn(() => jest.fn())}));
const Component=withTheme(SQLiteChangesetInspection);
const reference={database_target_id:'source-target',kind:'capture',job_id:'source-job',path:'capture.changeset'};
const row={record_number:'9007199254740993',table:'native\n雪',primary_key:[1,0,0],operation:'insert',indirect:false,new_values:[{native_type:'integer',data:'9223372036854775807'},{native_type:'null',data:null},{native_type:'blob',hex:'00FF'}],old_values:null};
const metadata=(input=reference,mode='page') => ({options:mode==='page' ? {mode}:{mode,record_number:row.record_number,column_index:2,side:'new'},source:{input:{reference:input}},inspection:mode==='page' ? {rows:[row],offset:'0',rows_returned:1,more:false,column_name_scope:'Native column positions',validation_scope:'Bounded prefix'}:{native_type:'blob',byte_length:'2',native_written_bytes:'2'}});

it('inspects native rows and extracts full values with exact source, ordinal and download scope',async () => {
  let selected='page';const post=jest.fn(async value => {
    const operation=value.action.replace('sqlite_changeset_inspect_','');
    if(operation==='catalog')return {helper_available:true};
    if(operation==='review'){selected=value.request.options.mode;return {job_id:'inspection-'+selected,review_digest:'digest'};}
    if(operation==='start')return {job_id:'inspection-'+selected,state:'completed'};
    if(operation==='result')return metadata(reference,selected);
    if(operation==='files')return {files:[{path:'value.bin',size:'2'}]};
  });
  render(<Component post={post} databaseTargetId="destination" reference={reference} endpointUrl="/workspace" />);
  fireEvent.click(screen.getByText('SQLite typed changeset inspection'));fireEvent.click(screen.getByRole('button',{name:'Inspect typed native file support'}));
  await screen.findByRole('button',{name:'Inspect selected native records'});fireEvent.click(screen.getByRole('button',{name:'Inspect selected native records'}));
  await screen.findByRole('button',{name:'Select native record 9007199254740993'});
  expect(post.mock.calls.find(call => call[0].action.endsWith('_review'))[0].request).toEqual({database_target_id:'destination',input:reference,options:{mode:'page',offset:'0',limit:25,preview_bytes:256,max_json_bytes:1048576,timeout_seconds:3600}});
  fireEvent.click(screen.getByRole('button',{name:'Select native record 9007199254740993'}));fireEvent.change(screen.getByLabelText('Native column position (first is 1)'),{target:{value:'3'}});
  fireEvent.click(screen.getByRole('button',{name:'Extract complete native TEXT or BLOB value'}));
  await waitFor(() => expect(post.mock.calls.filter(call => call[0].action.endsWith('_review')).at(-1)[0].request.options).toEqual({mode:'extract',record_number:'9007199254740993',column_index:2,side:'new',timeout_seconds:3600}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Load native inspection files'})).toBeEnabled());fireEvent.click(screen.getByRole('button',{name:'Load native inspection files'}));
  fireEvent.click(await screen.findByRole('button',{name:'Download inspection value.bin'}));
  expect(startBrowserFileDownload).toHaveBeenLastCalledWith('/workspace',{database_target_id:'destination',job_id:'inspection-extract',path:'value.bin'},expect.objectContaining({action:'sqlite_changeset_inspect_download'}));
});

it('uses a retained page source for its value requests even when another file is selected for application',async () => {
  const retained={...reference,job_id:'retained-source'};const post=jest.fn(async value => {
    if(value.action.endsWith('_catalog'))return {helper_available:true};
    if(value.action.endsWith('_list'))return {jobs:[{job_id:'old-inspection'}],more:false};
    if(value.action.endsWith('_status'))return {job_id:'old-inspection',state:'completed'};
    if(value.action.endsWith('_result'))return metadata(retained);
    if(value.action.endsWith('_review'))return {job_id:'range',review_digest:'digest'};
    if(value.action.endsWith('_start'))return {job_id:'range',state:'active'};
  });
  render(<Component post={post} databaseTargetId="destination" reference={reference} />);
  fireEvent.click(screen.getByText('SQLite typed changeset inspection'));fireEvent.click(screen.getByRole('button',{name:'Inspect typed native file support'}));
  await screen.findByRole('button',{name:'Inspect native value range'});fireEvent.click(screen.getByRole('button',{name:'Load native inspection receipts'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect native file receipt old-inspection'}));
  fireEvent.click(await screen.findByRole('button',{name:'Select native record 9007199254740993'}));fireEvent.click(screen.getByRole('button',{name:'Inspect native value range'}));
  await waitFor(() => expect(post.mock.calls.find(call => call[0].action.endsWith('_review'))[0].request.input).toEqual(retained));
});

it('discards an old result that arrives after the selected native source changes',async () => {
  let resolveResult;const pending=new Promise(resolve => {resolveResult=resolve;});
  const post=jest.fn(async value => {
    if(value.action.endsWith('_catalog'))return {helper_available:true};
    if(value.action.endsWith('_review'))return {job_id:'old',review_digest:'digest'};
    if(value.action.endsWith('_start'))return {job_id:'old',state:'completed'};
    if(value.action.endsWith('_result'))return pending;
  });
  const {rerender}=render(<Component post={post} databaseTargetId="destination" reference={reference} />);
  fireEvent.click(screen.getByText('SQLite typed changeset inspection'));fireEvent.click(screen.getByRole('button',{name:'Inspect typed native file support'}));
  await screen.findByRole('button',{name:'Inspect selected native records'});fireEvent.click(screen.getByRole('button',{name:'Inspect selected native records'}));
  await waitFor(() => expect(post.mock.calls.some(call => call[0].action.endsWith('_result'))).toBe(true));
  rerender(<Component post={post} databaseTargetId="destination" reference={{...reference,job_id:'new-source'}} />);
  await act(async () => {resolveResult(metadata());await pending;});
  expect(screen.queryByRole('button',{name:'Select native record 9007199254740993'})).not.toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Inspect selected native records'})).toBeEnabled();
});

it('keeps terminal polling alive until the asynchronous result body arrives',async () => {
  let resolveResult;const pending=new Promise(resolve => {resolveResult=resolve;});
  const post=jest.fn(async value => {
    if(value.action.endsWith('_catalog'))return {helper_available:true};
    if(value.action.endsWith('_review'))return {job_id:'async-job',review_digest:'digest'};
    if(value.action.endsWith('_start'))return {job_id:'async-job',state:'active'};
    if(value.action.endsWith('_status'))return {job_id:'async-job',state:'completed'};
    if(value.action.endsWith('_result'))return pending;
  });
  render(<Component post={post} databaseTargetId="destination" reference={reference} />);
  fireEvent.click(screen.getByText('SQLite typed changeset inspection'));fireEvent.click(screen.getByRole('button',{name:'Inspect typed native file support'}));
  await screen.findByRole('button',{name:'Inspect selected native records'});fireEvent.click(screen.getByRole('button',{name:'Inspect selected native records'}));
  await waitFor(() => expect(post.mock.calls.some(call => call[0].action.endsWith('_result'))).toBe(true));
  await act(async () => {resolveResult(metadata());await pending;});
  expect(await screen.findByRole('button',{name:'Select native record 9007199254740993'})).toBeEnabled();
});
