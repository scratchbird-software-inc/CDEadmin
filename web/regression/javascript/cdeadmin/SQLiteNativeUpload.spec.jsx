import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {Buffer} from 'buffer';
import SQLiteNativeUpload from 'sources/Dialogs/SQLiteNativeUpload';
import {withTheme} from '../fake_theme';

const Component=withTheme(SQLiteNativeUpload),CHUNK=262144;
const hash=bytes => require('crypto').createHash('sha256').update(Buffer.from(bytes)).digest('hex');
beforeEach(() => {
  Object.defineProperty(window.crypto,'subtle',{configurable:true,value:{digest:async (_name,bytes) => Uint8Array.from(Buffer.from(hash(bytes),'hex')).buffer}});
});

function fixture({loseAcknowledgement=false}={}) {
  const data=new Uint8Array(CHUNK+7);data.fill(84);let received=0,lost=false;
  const file={name:'external.native',size:data.length,slice:jest.fn((start,end) => ({arrayBuffer:async () => data.slice(start,end).buffer}))};
  const options={filename:file.name,length:String(file.size),kind:'auto',expected_sha256:null,timeout_seconds:3600};
  const record=() => ({job_id:'input-job',state:'uploading',uploaded_bytes:String(received),options});
  const post=jest.fn(async payload => {
    const action=payload.action.replace('sqlite_changeset_upload_','');
    if(action==='catalog')return {helper_available:true,chunk_bytes:CHUNK};
    if(action==='create' || action==='status')return record();
    if(action==='chunk'){
      const chunk=payload.request.chunk,bytes=Buffer.from(chunk.data_base64,'base64'),offset=Number(chunk.offset);
      expect(bytes.length).toBeLessThanOrEqual(CHUNK);expect(bytes).toEqual(Buffer.from(data.slice(offset,offset+bytes.length)));expect(chunk.sha256).toBe(hash(bytes));
      received=Math.max(received,offset+bytes.length);
      if(loseAcknowledgement && !lost){lost=true;throw new Error('Owned lost HTTP acknowledgement');}
      return {job_id:'input-job',uploaded_bytes:String(received),chunk_sha256:chunk.sha256};
    }
    if(action==='seal')return {...record(),state:'completed',result:{artifact:{native_kind:'changeset',native_record_count:'1',input_name:'uploaded.native'}}};
    throw new Error('Unexpected native input action: '+action);
  });
  return {post,file,data};
}

it('uploads bounded checksum-acknowledged slices and selects only the validated native artifact',async () => {
  const {post,file}=fixture(),selected=jest.fn();render(<Component post={post} databaseTargetId="file-target" onSelected={selected} />);
  fireEvent.click(screen.getByText('External SQLite changeset files'));fireEvent.click(screen.getByRole('button',{name:'Inspect native upload support'}));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));
  fireEvent.change(screen.getByLabelText('External native SQLite file'),{target:{files:[file]}});
  fireEvent.click(screen.getByRole('button',{name:'Upload and validate native file'}));
  fireEvent.click(await screen.findByRole('button',{name:'Use validated native file for apply'}));
  expect(file.slice.mock.calls).toEqual([[0,CHUNK],[CHUNK,CHUNK+7]]);
  expect(post.mock.calls.filter(([value]) => value.action==='sqlite_changeset_upload_chunk')).toHaveLength(2);
  expect(selected).toHaveBeenCalledWith(expect.objectContaining({job_id:'input-job',state:'completed'}));
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_changeset_upload_seal',request:{database_target_id:'file-target',job_id:'input-job'}});
});

it('refreshes durable progress and verifies the original prefix after a lost upload acknowledgement',async () => {
  const {post,file}=fixture({loseAcknowledgement:true});render(<Component post={post} databaseTargetId="file-target" onSelected={jest.fn()} />);
  fireEvent.click(screen.getByText('External SQLite changeset files'));fireEvent.click(screen.getByRole('button',{name:'Inspect native upload support'}));
  await waitFor(() => expect(post).toHaveBeenCalledTimes(1));fireEvent.change(screen.getByLabelText('External native SQLite file'),{target:{files:[file]}});
  fireEvent.click(screen.getByRole('button',{name:'Upload and validate native file'}));
  await screen.findByText('Owned lost HTTP acknowledgement');fireEvent.click(screen.getByRole('button',{name:'Resume native file upload'}));
  await screen.findByRole('button',{name:'Use validated native file for apply'});
  expect(file.slice.mock.calls).toEqual([[0,CHUNK],[0,CHUNK],[CHUNK,CHUNK+7]]);
  expect(post.mock.calls.filter(([value]) => value.action==='sqlite_changeset_upload_create')).toHaveLength(1);
  expect(post.mock.calls.filter(([value]) => value.action==='sqlite_changeset_upload_status')).toHaveLength(1);
});
