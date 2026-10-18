import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import SQLiteChangesetApply from 'sources/Dialogs/SQLiteChangesetApply';
import {withTheme} from '../fake_theme';

const Component=withTheme(SQLiteChangesetApply);
const reviewed={job_id:'apply-job',state:'reviewed',review_digest:'owned-review',warnings:[]};

it('reviews a selected native export and requires confirmation before independent writes and commit',async () => {
  const post=jest.fn().mockImplementation(request => {
    const operation=request.action.replace('sqlite_changeset_','');
    return Promise.resolve(operation==='catalog' ? {targets:[{target_id:'file',display_name:'native.sqlite'}],helper_available:true} :
      operation==='sources' ? {jobs:[{job_id:'export-job',state:'completed',options:{kind:'changeset'}}],more:false} :
        operation==='start' ? {...reviewed,state:'completed',native_returned:true,commit_returned:true} : reviewed);
  });
  render(<Component post={post} databaseTargetId="file" endpointUrl="/workspace" />);
  fireEvent.click(screen.getByText('SQLite changeset application'));fireEvent.click(screen.getByRole('button',{name:'Inspect native apply sources'}));
  fireEvent.click(await screen.findByRole('button',{name:'Load verified source exports'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Review native changeset application'})).toBeEnabled());
  fireEvent.click(screen.getByLabelText('Write native rebase data'));fireEvent.click(screen.getByRole('button',{name:'Review native changeset application'}));
  await screen.findByRole('button',{name:'Apply reviewed native changeset'});
  expect(post.mock.calls.at(-1)[0]).toEqual({action:'sqlite_changeset_review',request:{database_target_id:'file',source_database_target_id:'file',source_job_id:'export-job',path:'capture.changeset',options:{
    invert:false,ignore_noop:false,fk_no_action:false,foreign_keys:true,recursive_triggers:false,include_rebase:true,table_name:null,timeout_seconds:3600,
    conflicts:{data:'abort',not_found:'abort',conflict:'abort',constraint:'abort',foreign_key:'abort'}}}});
  expect(screen.getByRole('button',{name:'Apply reviewed native changeset'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm native changes and commit to this destination'));
  fireEvent.click(screen.getByRole('button',{name:'Apply reviewed native changeset'}));
  await screen.findByRole('button',{name:'Load native apply output files'});
  expect(post).toHaveBeenLastCalledWith({action:'sqlite_changeset_start',request:{database_target_id:'file',job_id:'apply-job',review_digest:'owned-review',confirmed:true}});
  expect(screen.getByRole('status')).toHaveTextContent('Commit acknowledgement: received');
});

it('invalidates an unconsumed review after native options change',async () => {
  const post=jest.fn().mockImplementation(request => Promise.resolve(request.action==='sqlite_changeset_catalog' ? {targets:[{target_id:'file',display_name:'native.sqlite'}],helper_available:true} :
    request.action==='sqlite_changeset_sources' ? {jobs:[{job_id:'export-job',state:'completed',options:{kind:'changeset'}}],more:false} : reviewed));
  render(<Component post={post} databaseTargetId="file" />);
  fireEvent.click(screen.getByText('SQLite changeset application'));fireEvent.click(screen.getByRole('button',{name:'Inspect native apply sources'}));
  fireEvent.click(await screen.findByRole('button',{name:'Load verified source exports'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Review native changeset application'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Review native changeset application'}));await screen.findByRole('button',{name:'Apply reviewed native changeset'});
  fireEvent.click(screen.getByLabelText('Invert incoming changeset'));
  await waitFor(() => expect(screen.queryByRole('button',{name:'Apply reviewed native changeset'})).not.toBeInTheDocument());
});
