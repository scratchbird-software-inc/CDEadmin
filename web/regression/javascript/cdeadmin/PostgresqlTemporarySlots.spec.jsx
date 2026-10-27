import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import PostgresqlTemporarySlots from 'sources/Dialogs/PostgresqlTemporarySlots';
import {startBrowserFileDownload} from 'sources/Dialogs/browserFileDownload';
import {withTheme} from '../fake_theme';

const Component=withTheme(PostgresqlTemporarySlots),target='postgresql-database:123';
jest.mock('sources/Dialogs/browserFileDownload',() => ({startBrowserFileDownload:jest.fn(() => jest.fn())}));
const reviewed={job_id:'resource',state:'reviewed',review_digest:'resource-review',warnings:[]};
const opened={...reviewed,state:'active',ready:true,backend_pid:'9001',pending_command:null};
const command={job_id:'command',state:'reviewed',review_digest:'command-review'};
let originalHeight;
beforeEach(() => {originalHeight=window.innerHeight;window.innerHeight=1200;});
afterEach(() => {window.innerHeight=originalHeight;});

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

async function open(post,props={}) {
  render(<Component post={post} databaseTargetId={target} {...props} />);
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

it('preserves ordered duplicate plugin options and exact native decoding thresholds',async () => {
  const post=api();await open(post);
  fireEvent.mouseDown(screen.getByLabelText('Temporary slot operation'));
  fireEvent.click(screen.getByRole('option',{name:'Consume temporary logical binary'}));
  fireEvent.change(screen.getByLabelText('Exact temporary slot name'),{target:{value:'native_output'}});
  fireEvent.change(screen.getByLabelText('Temporary logical output up to LSN'),{target:{value:'FFFFFFFF/FFFFFFFF'}});
  fireEvent.change(screen.getByLabelText('Temporary logical native transaction threshold'),{target:{value:''}});
  for(const [index,value] of ['first','second'].entries()) {
    fireEvent.click(screen.getByRole('button',{name:'Add ordered temporary plugin option'}));
    fireEvent.change(screen.getByLabelText('Temporary plugin option '+(index+1)+' name'),{target:{value:'same'}});
    fireEvent.change(screen.getByLabelText('Temporary plugin option '+(index+1)+' value'),{target:{value}});
  }
  fireEvent.click(screen.getByRole('button',{name:'Review temporary slot command'}));
  await screen.findByRole('button',{name:'Run reviewed temporary slot command'});
  expect(post).toHaveBeenCalledWith({action:'postgresql_temporary_slots_command_review',request:{database_target_id:target,resource_id:'resource',operation:'get_binary',options:{slot:'native_output',timeout_seconds:30,upto_lsn:'FFFFFFFF/FFFFFFFF',upto_nchanges:null,plugin_options:[{name:'same',value:'first'},{name:'same',value:'second'}]}}});
});

it('previews and downloads retained output without replaying an unknown get and confirms removal',async () => {
  const fallback=api(),captured={...command,state:'unknown',worker_io_closed:true,options:{operation:'get_text'},native_sql_acknowledged:true,change_artifact:{state:'verified'}};
  const post=jest.fn(request => {
    const action=request.action.replace('postgresql_temporary_slots_','');
    if(action==='command_status' || action==='change_reconcile')return Promise.resolve(captured);
    if(action==='change_preview')return Promise.resolve({rows:[{data:'<script>native 😀</script>'}],next_offset:request.request.offset==='0' ? '123456789012345678' : null});
    if(action==='change_remove')return Promise.resolve({...captured,artifact_removed:true});
    return fallback(request);
  });
  await open(post,{endpointUrl:'/owned/workspace'});
  fireEvent.change(screen.getByLabelText('Exact temporary slot name'),{target:{value:'native_output'}});
  fireEvent.click(screen.getByRole('button',{name:'Review temporary slot command'}));
  await screen.findByRole('button',{name:'Download temporary logical capture'});
  fireEvent.click(screen.getByRole('button',{name:'Preview temporary logical records'}));
  await screen.findByLabelText('Temporary logical output preview');
  expect(screen.getByLabelText('Temporary logical output preview')).toHaveTextContent('<script>native 😀</script>');
  fireEvent.click(screen.getByRole('button',{name:'Next temporary logical records'}));
  await waitFor(() => expect(post).toHaveBeenCalledWith({action:'postgresql_temporary_slots_change_preview',request:{database_target_id:target,resource_id:'resource',job_id:'command',offset:'123456789012345678',limit:25}}));
  fireEvent.click(screen.getByRole('button',{name:'Download temporary logical capture'}));
  expect(startBrowserFileDownload).toHaveBeenCalledWith('/owned/workspace',{database_target_id:target,resource_id:'resource',job_id:'command'},expect.objectContaining({action:'postgresql_temporary_slots_change_download'}));
  expect(screen.getByRole('button',{name:'Remove temporary logical capture'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Remove this temporary logical capture; retain receipt'));
  fireEvent.click(screen.getByRole('button',{name:'Remove temporary logical capture'}));
  await waitFor(() => expect(screen.queryByRole('button',{name:'Download temporary logical capture'})).not.toBeInTheDocument());
  expect(post).toHaveBeenCalledWith({action:'postgresql_temporary_slots_change_remove',request:{database_target_id:target,resource_id:'resource',job_id:'command',confirmation:'command'}});
  expect(post.mock.calls.some(([request]) => request.action==='postgresql_temporary_slots_command_start')).toBe(false);
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
