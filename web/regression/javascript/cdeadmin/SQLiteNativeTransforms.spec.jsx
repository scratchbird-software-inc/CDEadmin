import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteNativeTransforms from 'sources/Dialogs/SQLiteNativeTransforms';
import {withTheme} from '../fake_theme';

const Component=withTheme(SQLiteNativeTransforms),artifact={native_iterator_complete:true,native_kind:'changeset',input_name:'transformed.native',native_record_count:'1'};
const source={job_id:'input-job',state:'completed',options:{kind:'changeset'},result:{artifact}};
const reviewed={job_id:'transform-job',state:'reviewed',review_digest:'owned-review',warnings:[]};

function api() {return jest.fn(request => {
  const operation=request.action.replace('sqlite_changeset_transform_','');
  return Promise.resolve(operation==='catalog' ? {helper_available:true,targets:[{target_id:'file',display_name:'native.sqlite'}]} :
    operation==='sources' ? {jobs:[source],more:false} : operation==='start' ? {...reviewed,state:'completed',result:{artifact}} : reviewed);
});}

it('reviews exact ordered inputs and confirms a separate native artifact before offering apply',async () => {
  const post=api(),selected=jest.fn();render(<Component post={post} databaseTargetId="file" onSelected={selected} />);
  fireEvent.click(screen.getByText('SQLite native file transformations'));fireEvent.click(screen.getByRole('button',{name:'Inspect native transform support'}));
  fireEvent.click(await screen.findByRole('button',{name:'Load native transform inputs'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Add ordered native input'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Add ordered native input'}));fireEvent.click(screen.getByRole('button',{name:'Review native file transformation'}));
  await screen.findByRole('button',{name:'Start reviewed native transformation'});
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_changeset_transform_review',request:{database_target_id:'file',
    inputs:[{database_target_id:'file',kind:'capture',job_id:'input-job',path:'capture.changeset'}],
    options:{operation:'invert',schema_database:null,patchset_output:null,timeout_seconds:3600}}});
  expect(screen.getByRole('button',{name:'Start reviewed native transformation'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm new native transformed artifact'));fireEvent.click(screen.getByRole('button',{name:'Start reviewed native transformation'}));
  fireEvent.click(await screen.findByRole('button',{name:'Use transformed native file for apply'}));
  expect(selected).toHaveBeenCalledWith(expect.objectContaining({job_id:'transform-job',state:'completed'}));
});

it('invalidates the unconsumed review after an ordered input is removed',async () => {
  const post=api();render(<Component post={post} databaseTargetId="file" onSelected={jest.fn()} />);
  fireEvent.click(screen.getByText('SQLite native file transformations'));fireEvent.click(screen.getByRole('button',{name:'Inspect native transform support'}));
  fireEvent.click(await screen.findByRole('button',{name:'Load native transform inputs'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Add ordered native input'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Add ordered native input'}));fireEvent.click(screen.getByRole('button',{name:'Review native file transformation'}));
  await screen.findByRole('button',{name:'Start reviewed native transformation'});fireEvent.click(screen.getByRole('button',{name:'Remove native input 1'}));
  await waitFor(() => expect(screen.queryByRole('button',{name:'Start reviewed native transformation'})).not.toBeInTheDocument());
  expect(screen.getByRole('button',{name:'Review native file transformation'})).toBeDisabled();
});
