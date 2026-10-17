import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import {createHash} from 'crypto';
import PostgresqlLargeObjectFiles from 'sources/Dialogs/PostgresqlLargeObjectFiles';
import {withTheme} from '../fake_theme';

const Component=withTheme(PostgresqlLargeObjectFiles);
const review={job_id:'job',state:'reviewed',review_digest:'digest',warnings:['Native transfer review'],
  options:{operation:'import',filename:'file.bin',length:'3'},source:{database_oid:'5'}};
const previousHeight=window.innerHeight;
beforeAll(() => {window.innerHeight=1200;});
afterAll(() => {window.innerHeight=previousHeight;});

it('stages bounded exact chunks and requires confirmation before native import',async () => {
  const bytes=new Uint8Array([0,128,255]);
  const original=Object.getOwnPropertyDescriptor(window.crypto,'subtle');
  Object.defineProperty(window.crypto,'subtle',{configurable:true,value:{digest:async (_name,data) => createHash('sha256').update(data).digest()}});
  const file=new File([bytes],'file.bin');file.slice=() => ({arrayBuffer:async () => bytes.buffer});
  const post=jest.fn(({action}) => Promise.resolve(action.endsWith('_create') ? {...review,state:'uploading'} :
    action.endsWith('_upload') ? {uploaded_bytes:'3',chunk_sha256:createHash('sha256').update(bytes).digest('hex')} : review));
  try {
    render(<Component post={post} databaseTargetId="database" endpointUrl="/workspace" />);
    fireEvent.change(screen.getByLabelText('Binary file to import'),{target:{files:[file]}});
    fireEvent.click(screen.getByRole('button',{name:'Upload and review file'}));
    await screen.findByText('Native transfer review');
    expect(post).toHaveBeenCalledWith({action:'postgresql_large_object_upload',request:{database_target_id:'database',job_id:'job',offset:'0',data_base64:'AID/',sha256:createHash('sha256').update(bytes).digest('hex')}});
    expect(post).not.toHaveBeenCalledWith(expect.objectContaining({action:'postgresql_large_object_start'}));
    fireEvent.click(screen.getByRole('button',{name:'Confirm and start native file transfer'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'postgresql_large_object_start',request:{database_target_id:'database',job_id:'job',review_digest:'digest',confirmed:true}}));
  } finally {
    if(original)Object.defineProperty(window.crypto,'subtle',original);else delete window.crypto.subtle;
  }
});

it('exports through authenticated browser navigation without a complete-file Blob',async () => {
  const exported={...review,state:'committed',options:{operation:'export',filename:'export.bin'},result:{oid:'42',length:'10000000000',sha256:'checksum'}};
  const post=jest.fn().mockResolvedValue({jobs:[exported],total:1});
  const submit=jest.spyOn(HTMLFormElement.prototype,'submit').mockImplementation(function() {
    expect(this.method).toBe('post');expect(this.elements.action.value).toBe('postgresql_large_object_download');
    expect(JSON.parse(this.elements.payload.value)).toEqual({job_id:'job',database_target_id:'database'});
  });
  try {
    render(<Component post={post} databaseTargetId="database" endpointUrl="/workspace" />);
    fireEvent.click(screen.getByRole('button',{name:'Load file transfer receipts'}));
    await screen.findByRole('table',{name:'PostgreSQL file transfers'});
    post.mockResolvedValue(exported);fireEvent.click(screen.getByRole('button',{name:'Inspect job'}));
    fireEvent.click(await screen.findByRole('button',{name:'Download complete binary file'}));
    expect(submit).toHaveBeenCalledTimes(1);
  } finally {submit.mockRestore();}
});
