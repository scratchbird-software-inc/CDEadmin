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

it('uses the original snapshot catalog, native COPY options and an explicit transaction end',async () => {
  const base=api();let resource=opened,selected,count=0;
  const post=jest.fn(payload => {
    const action=payload.action.replace('postgresql_replication_temporary_','');
    if(action==='status')return Promise.resolve(resource);
    if(action==='command_review'){
      selected={job_id:'snapshot-command-'+(++count),state:'reviewed',review_digest:'native-review',options:{operation:payload.request.operation,native_options:payload.request.options}};
      return Promise.resolve(selected);
    }
    if(action==='command_start'){
      const operation=selected.options.operation;
      if(operation==='logical_create')resource={...opened,latest_native_inventory:{owns_snapshot_transaction:true,used_snapshot:{slot:'sr_use'}}};
      if(operation==='snapshot_end')resource={...opened,latest_native_inventory:{owns_snapshot_transaction:false,used_snapshot:null}};
      selected={...selected,state:'completed',worker_io_closed:true,native_command_acknowledged:true,native_acknowledgement:{operation,
        native_result:operation==='snapshot_tables' ? {relations:[{relation_oid:'7',schema:'public',name:'exact',native_kind:'r',can_select:true,row_security_active:false}],offset:0,limit:25,more:false} : null},
      ...(operation==='snapshot_copy' ? {snapshot_copy_artifact:{state:'verified',copy_format:'csv',rows:'1'}} : {})};
      return Promise.resolve({...selected,state:'active'});
    }
    if(action==='command_status')return Promise.resolve(selected);
    if(action==='copy_preview')return Promise.resolve({data_base64:'Y29weQ==',next_offset:null,copy_format:'csv',native_values_decoded:false});
    return base(payload);
  });
  const choose=(label,value) => fireEvent.change(screen.getByLabelText(label).parentElement.querySelector('input'),{target:{value}});
  const run=async () => {
    fireEvent.click(screen.getByRole('button',{name:'Review retained replication command'}));
    await screen.findByRole('button',{name:'Run reviewed replication command'});
    fireEvent.click(screen.getByLabelText('Confirm retained replication command'));
    fireEvent.click(screen.getByRole('button',{name:'Run reviewed replication command'}));
    await screen.findByText(new RegExp('Retained replication command snapshot-command-'+count+': completed'));
  };
  await open(post,{endpointUrl:'/owned-server/workspace'});
  fireEvent.change(screen.getByLabelText('Exact retained replication slot'),{target:{value:'sr_use'}});
  choose('Native replication snapshot','use');await run();
  await screen.findByText(/The original backend owns a read-only repeatable-read SNAPSHOT USE/);
  choose('Retained replication command','snapshot_tables');
  fireEvent.change(screen.getByLabelText('Original snapshot schema name (empty for all)'),{target:{value:'public'}});
  await run();await screen.findByText(/Native snapshot relation page:/);
  choose('Retained replication command','snapshot_inspect');
  choose('Original snapshot relation','7');await run();
  choose('Retained replication command','snapshot_copy');choose('Original snapshot COPY format','csv');
  fireEvent.change(screen.getByLabelText('Native snapshot COPY TO options (JSON)'),{target:{value:'{"header":true,"force_quote":"all"}'}});
  await run();
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_command_review',request:{database_target_id:target,resource_id:'resource',operation:'snapshot_copy',options:{timeout_seconds:30,invalidate_snapshot:false,relation_oid:'7',include_descendants:true,format:'csv',copy_options:{header:true,force_quote:'all'}}}});
  fireEvent.click(screen.getByRole('button',{name:'Preview original snapshot COPY bytes'}));
  await screen.findByLabelText('Original snapshot COPY byte preview');
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_copy_preview',request:{database_target_id:target,resource_id:'resource',job_id:'snapshot-command-4',offset:'0',length:4096}});
  fireEvent.click(screen.getByRole('button',{name:'Download original snapshot COPY'}));
  expect(startBrowserFileDownload).toHaveBeenCalledWith('/owned-server/workspace',expect.objectContaining({job_id:'snapshot-command-4'}),expect.objectContaining({action:'postgresql_replication_temporary_copy_download'}));
  choose('Retained replication command','snapshot_end');await run();
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_command_review',request:{database_target_id:target,resource_id:'resource',operation:'snapshot_end',options:{timeout_seconds:30,invalidate_snapshot:false,decision:'commit'}}});
  await waitFor(() => expect(screen.queryByText(/The original backend owns a read-only repeatable-read SNAPSHOT USE/)).not.toBeInTheDocument());
});

it('reviews an independent consumer by exporter resource identity and exposes its own snapshot workflow',async () => {
  const base=api();let current={...opened,latest_native_inventory:{snapshot:{snapshot_name:'0000007E-00000002-1'}}};
  const consumer={...reviewed,job_id:'consumer',options:{snapshot_import:{exporter_job_id:'resource'}}};
  const post=jest.fn(payload => {
    const action=payload.action.replace('postgresql_replication_temporary_','');
    if(action==='status')return Promise.resolve(current);
    if(action==='start' && payload.request.job_id==='resource')return Promise.resolve(current);
    if(action==='review' && payload.request.options.import_from_resource_id)return Promise.resolve(consumer);
    if(action==='start' && payload.request.job_id==='consumer'){
      current={...consumer,state:'active',ready:true,snapshot_import_acknowledged:true,snapshot_import_verified:true,
        latest_native_inventory:{owns_snapshot_transaction:true,used_snapshot:{origin:'imported-exported-snapshot',source_slot:'source_slot'}}};
      return Promise.resolve(current);
    }
    return base(payload);
  });
  await open(post);
  fireEvent.change(screen.getByLabelText('Temporary replication password'),{target:{value:'consumer-secret'}});
  fireEvent.click(screen.getByRole('button',{name:'Review independent snapshot consumer'}));
  await screen.findByText(/Independent snapshot consumer of resource resource/);
  expect(post).toHaveBeenCalledWith({action:'postgresql_replication_temporary_review',request:{database_target_id:target,
    replication_access:{password:'consumer-secret'},options:{max_lifetime_seconds:3600,import_from_resource_id:'resource'}}});
  expect(screen.getByRole('button',{name:'Open reviewed replication resource'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm original replication resource'));
  fireEvent.click(screen.getByRole('button',{name:'Open reviewed replication resource'}));
  await screen.findByText(/This independent backend owns an imported/);
  await waitFor(() => expect(screen.getByLabelText('Retained replication command').parentElement.querySelector('input')).toHaveValue('snapshot_tables'));
  expect(screen.getByText(/Import acknowledged: true. Import verified: true/)).toBeInTheDocument();
  expect(screen.queryByRole('button',{name:'Review independent snapshot consumer'})).not.toBeInTheDocument();
  expect(screen.getByLabelText('Temporary replication password')).toHaveValue('');
  expect(post.mock.calls.some(([payload]) => payload.action.endsWith('_command_start'))).toBe(false);
});
