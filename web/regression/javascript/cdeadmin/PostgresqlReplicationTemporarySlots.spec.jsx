import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import PostgresqlReplicationTemporarySlots from 'sources/Dialogs/PostgresqlReplicationTemporarySlots';
import {withTheme} from '../fake_theme';
import {startBrowserFileDownload} from 'sources/Dialogs/browserFileDownload';
jest.mock('sources/Dialogs/browserFileDownload',() => ({startBrowserFileDownload:jest.fn(() => jest.fn())}));

const Component=withTheme(PostgresqlReplicationTemporarySlots);
const database='Native DB ü \'',target='postgresql-replication-database:4e617469766520444220c3bc2027';
const reviewed={job_id:'resource',state:'reviewed',review_digest:'resource-review',source:{database},warnings:[]};
const opened={...reviewed,state:'active',ready:true,backend_pid:'9001',pending_command:null};
const command={job_id:'command',state:'reviewed',review_digest:'command-review'};

function api() {
  let resource=opened;
  return jest.fn(payload => {
    const action=payload.action.replace('postgresql_replication_temporary_','');
    if(action==='scope')return Promise.resolve({database_target_id:target,source:{database}});
    if(action==='review')return Promise.resolve(reviewed);
    if(action==='start')return Promise.resolve(opened);
    if(action==='status')return Promise.resolve(resource);
    if(action==='command_review')return Promise.resolve({...command,state:'queued_review'});
    if(action==='command_status')return Promise.resolve(command);
    if(action==='command_start')return Promise.resolve({...command,state:'completed',native_command_acknowledged:true});
    if(action==='release'){resource={...opened,state:'closed',ready:false,native_owner_connection_close_returned:true};return Promise.resolve(resource);}
    return Promise.resolve({jobs:[],more:false});
  });
}

async function open(post,extra={}) {
  render(<Component post={post} {...extra} />);
  fireEvent.click(screen.getByText('Temporary replication slots and exported snapshots'));
  fireEvent.click(screen.getByText('Registered replication credentials'));
  fireEvent.change(screen.getByLabelText('Temporary replication password'),{target:{value:'private-native-password'}});
  fireEvent.click(screen.getByRole('button',{name:'Review temporary replication resource'}));
  await screen.findByRole('button',{name:'Open reviewed replication resource'});
  expect(screen.getByRole('button',{name:'Open reviewed replication resource'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm original replication resource'));
  fireEvent.click(screen.getByRole('button',{name:'Open reviewed replication resource'}));
  await screen.findByLabelText('Exact retained replication slot');
}

it('keeps native registration admission and command confirmation separate and clears private credentials',async () => {
  const post=api();await open(post);
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_review',request:{replication_access:{password:'private-native-password'},options:{max_lifetime_seconds:3600}}});
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_start',request:{database_target_id:target,replication_access:{password:'private-native-password'},job_id:'resource',review_digest:'resource-review',confirmed:true}});
  expect(screen.getByLabelText('Temporary replication password')).toHaveValue('');
  fireEvent.change(screen.getByLabelText('Exact retained replication slot'),{target:{value:'sr_export'}});
  fireEvent.click(screen.getByLabelText('Temporary replication two-phase decoding'));
  fireEvent.click(screen.getByLabelText('Allow invalidation of the current exported snapshot'));
  fireEvent.click(screen.getByRole('button',{name:'Review retained replication command'}));
  await screen.findByRole('button',{name:'Run reviewed replication command'});
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_command_review',request:{database_target_id:target,resource_id:'resource',operation:'logical_create',options:{slot:'sr_export',plugin:'test_decoding',snapshot:'export',two_phase:true,invalidate_snapshot:true,timeout_seconds:30}}});
  expect(screen.getByRole('button',{name:'Run reviewed replication command'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm retained replication command'));
  fireEvent.click(screen.getByRole('button',{name:'Run reviewed replication command'}));
  await screen.findByText(/Native acknowledgement: true/);
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_command_start',request:{database_target_id:target,resource_id:'resource',job_id:'command',review_digest:'command-review',confirmed:true}});
  expect(post.mock.calls.every(([request]) => request.action.startsWith('postgresql_replication_temporary_'))).toBe(true);
});

it('keeps the original backend open until explicit release and reports remote cleanup separately',async () => {
  const post=api();await open(post);
  expect(screen.getByRole('button',{name:'Release retained replication resource'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Release this replication backend and snapshot'));
  fireEvent.click(screen.getByRole('button',{name:'Release retained replication resource'}));
  await screen.findByText(/Remote cleanup is not independently observed/);
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_release',request:{database_target_id:target,job_id:'resource',confirmation:'resource'}});
  expect(screen.queryByRole('button',{name:'Review retained replication command'})).not.toBeInTheDocument();
});

it('selects only the native replication database scope and lists retained receipts without reopening a backend',async () => {
  const post=api();render(<Component post={post} />);
  fireEvent.click(screen.getByText('Temporary replication slots and exported snapshots'));
  fireEvent.click(screen.getByRole('button',{name:'Inspect registered replication database'}));
  await waitFor(() => expect(screen.getByLabelText('Retained replication database name')).toHaveValue(database));
  fireEvent.click(screen.getByRole('button',{name:'Load retained replication resources'}));
  await screen.findByLabelText('Retained replication resource');
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_scope',request:{replication_access:{}}});
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_list',request:{database_target_id:target,offset:0,limit:25}});
  expect(post.mock.calls.some(([request]) => request.action.endsWith('_start'))).toBe(false);
});

it('reviews native stream feedback explicitly and keeps capture preview and delivery on the original resource',async () => {
  const base=api();let selected=command;
  const post=jest.fn(payload => {
    if(payload.action.endsWith('_command_review')){selected={...command,options:{operation:payload.request.operation,native_options:payload.request.options}};return Promise.resolve(selected);}
    if(payload.action.endsWith('_command_start')){selected={...selected,state:'completed',worker_io_closed:true,native_command_acknowledged:true,protocol_stream_artifact:{state:'verified'}};return Promise.resolve(selected);}
    if(payload.action.endsWith('_stream_preview'))return Promise.resolve({rows:[{start_lsn:'0/1234',payload_base64:'bmF0aXZl'}],next_offset:null});
    return base(payload);
  });
  await open(post,{endpointUrl:'/owned-server/workspace'});
  fireEvent.change(screen.getByLabelText('Retained replication command').parentElement.querySelector('input'),{target:{value:'logical_stream'}});
  fireEvent.change(screen.getByLabelText('Exact retained replication slot'),{target:{value:'sr_stream'}});
  expect(screen.getByLabelText('Acknowledge fsynced output to the native slot')).not.toBeChecked();
  fireEvent.click(screen.getByLabelText('Acknowledge fsynced output to the native slot'));
  fireEvent.change(screen.getByLabelText('Native logical stream plugin options (JSON)'),{target:{value:'[{"name":"include-xids","value":"0"}]'}});
  fireEvent.click(screen.getByRole('button',{name:'Review retained replication command'}));
  await screen.findByRole('button',{name:'Run reviewed replication command'});
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_command_review',request:{database_target_id:target,resource_id:'resource',operation:'logical_stream',options:{slot:'sr_stream',timeout_seconds:30,invalidate_snapshot:false,start_lsn:'0/0',max_messages:100,max_capture_bytes:16777216,max_duration_seconds:5,acknowledge_flush:true,plugin_options:[{name:'include-xids',value:'0'}]}}});
  fireEvent.click(screen.getByLabelText('Confirm retained replication command'));
  fireEvent.click(screen.getByRole('button',{name:'Run reviewed replication command'}));
  fireEvent.click(await screen.findByRole('button',{name:'Preview original replication frames'}));
  await screen.findByLabelText('Original replication frame preview');
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_stream_preview',request:{database_target_id:target,resource_id:'resource',job_id:'command',offset:'0',limit:25}});
  fireEvent.click(screen.getByRole('button',{name:'Download original replication frames'}));
  expect(startBrowserFileDownload).toHaveBeenCalledWith('/owned-server/workspace',{database_target_id:target,resource_id:'resource',job_id:'command'},expect.objectContaining({action:'postgresql_replication_temporary_stream_download'}));
});
