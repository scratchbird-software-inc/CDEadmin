import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import PostgresqlTemporarySlots from 'sources/Dialogs/PostgresqlTemporarySlots';
import {withTheme} from '../fake_theme';

const Component=withTheme(PostgresqlTemporarySlots),target='postgresql-database:123';
const reviewed={job_id:'resource',state:'reviewed',review_digest:'resource-review',warnings:[]};
const opened={...reviewed,state:'active',ready:true,backend_pid:'9001',pending_command:null};
const command={job_id:'command',state:'reviewed',review_digest:'command-review'};

function api() {
  let resource=opened;
  return jest.fn(request => {
    const action=request.action.replace('postgresql_temporary_slots_','');
    if(action==='review')return Promise.resolve(reviewed);
    if(action==='start')return Promise.resolve(opened);
    if(action==='status')return Promise.resolve(resource);
    if(action==='command_review')return Promise.resolve({...command,state:'queued_review'});
    if(action==='command_status')return Promise.resolve(command);
    if(action==='command_start')return Promise.resolve({...command,state:'completed',native_command_acknowledged:true});
    if(action==='release'){resource={...opened,state:'closed',ready:false,worker_io_closed:true,native_owner_connection_close_returned:true};return Promise.resolve(resource);}
    if(action==='reconcile')return Promise.resolve({...resource,backend_cleanup_observation:{original_backend_termination_observed:true,temporary_slot_cleanup_observed:true}});
    return Promise.resolve({targets:[],jobs:[],more:false});
  });
}

async function open(post) {
  render(<Component post={post} databaseTargetId={target} />);
  fireEvent.click(screen.getByText('PostgreSQL temporary replication slots'));
  fireEvent.click(screen.getByRole('button',{name:'Review temporary slot resource'}));
  await screen.findByRole('button',{name:'Open reviewed temporary slot resource'});
  expect(screen.getByRole('button',{name:'Open reviewed temporary slot resource'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm independent temporary slot resource'));
  fireEvent.click(screen.getByRole('button',{name:'Open reviewed temporary slot resource'}));
  await screen.findByLabelText('Exact temporary slot name');
}

it('keeps resource opening, owner-channel review and native command confirmation separate',async () => {
  const post=api();await open(post);
  expect(post).toHaveBeenCalledWith({action:'postgresql_temporary_slots_start',request:{database_target_id:target,job_id:'resource',review_digest:'resource-review',confirmed:true}});
  fireEvent.change(screen.getByLabelText('Exact temporary slot name'),{target:{value:'sr_owned'}});
  fireEvent.click(screen.getByRole('button',{name:'Review temporary slot command'}));
  await screen.findByRole('button',{name:'Run reviewed temporary slot command'});
  expect(post).toHaveBeenCalledWith({action:'postgresql_temporary_slots_command_review',request:{database_target_id:target,resource_id:'resource',operation:'physical_create',options:{slot:'sr_owned',timeout_seconds:30,reserve_wal:true}}});
  expect(screen.getByRole('button',{name:'Run reviewed temporary slot command'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm native temporary slot command'));
  fireEvent.click(screen.getByRole('button',{name:'Run reviewed temporary slot command'}));
  await screen.findByText(/Native command acknowledged: true/);
  expect(post).toHaveBeenCalledWith({action:'postgresql_temporary_slots_command_start',request:{database_target_id:target,resource_id:'resource',job_id:'command',review_digest:'command-review',confirmed:true}});
});

it('confirms resource release and checks native cleanup in a later independent request',async () => {
  const post=api();await open(post);
  expect(screen.getByRole('button',{name:'Release temporary slot resource'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Release this backend and all its temporary slots'));
  fireEvent.click(screen.getByRole('button',{name:'Release temporary slot resource'}));
  fireEvent.click(await screen.findByRole('button',{name:'Verify native temporary slot cleanup'}));
  await screen.findByText(/Native temporary-slot cleanup observed: true/);
  expect(post).toHaveBeenCalledWith({action:'postgresql_temporary_slots_release',request:{database_target_id:target,job_id:'resource',confirmation:'resource'}});
  expect(post).toHaveBeenCalledWith({action:'postgresql_temporary_slots_reconcile',request:{database_target_id:target,job_id:'resource'}});
});

it('discards a late resource review when the database scope changes',async () => {
  let resolve;const post=jest.fn(() => new Promise(done => {resolve=done;}));
  const {rerender}=render(<Component post={post} databaseTargetId={target} />);
  fireEvent.click(screen.getByText('PostgreSQL temporary replication slots'));fireEvent.click(screen.getByRole('button',{name:'Review temporary slot resource'}));
  rerender(<Component post={post} databaseTargetId="postgresql-database:456" />);resolve(reviewed);
  await waitFor(() => expect(screen.getByRole('button',{name:'Review temporary slot resource'})).toBeEnabled());
  expect(screen.queryByRole('button',{name:'Open reviewed temporary slot resource'})).not.toBeInTheDocument();
});
