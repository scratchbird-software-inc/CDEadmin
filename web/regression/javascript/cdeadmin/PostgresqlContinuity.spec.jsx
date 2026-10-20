import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import PostgresqlContinuity from 'sources/Dialogs/PostgresqlContinuity';
import {startBrowserFileDownload} from 'sources/Dialogs/browserFileDownload';
import {withTheme} from '../fake_theme';
const Component=withTheme(PostgresqlContinuity);
jest.mock('sources/Dialogs/browserFileDownload',() => ({startBrowserFileDownload:jest.fn(() => jest.fn())}));
const reviewed={job_id:'native-job',review_digest:'native-digest',state:'reviewed',operation:'full_backup',
  source:{system_identifier:'18446744073709551615'},options:{format:'plain'},inputs:[],tool_identities:{},warnings:['Complete cluster backup']};
let originalHeight;
beforeEach(() => {originalHeight=window.innerHeight;window.innerHeight=1200;});
afterEach(() => {window.innerHeight=originalHeight;});

describe('PostgreSQL native continuity jobs',() => {
  it('creates a logical slot through registered replication with native options and private reauthentication',async () => {
    const nativeReview={...reviewed,operation:'logical_slot_create',source:{admission_interface:'logical-replication',slot_catalog_observed:false}};
    const post=jest.fn().mockResolvedValue(nativeReview);render(<Component post={post} />);
    fireEvent.mouseDown(screen.getByRole('combobox',{name:'Continuity operation'}));
    fireEvent.click(await screen.findByRole('option',{name:'Create logical slot through replication'}));
    expect(screen.getByRole('checkbox',{name:'Use native replication-only admission'})).toBeChecked();
    expect(screen.getByRole('checkbox',{name:'Use native replication-only admission'})).toBeDisabled();
    expect(screen.getByRole('button',{name:'Load replication slots'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Replication slot name'),{target:{value:'owned_logical'}});
    fireEvent.change(screen.getByLabelText('Native logical output plugin'),{target:{value:'pgoutput'}});
    fireEvent.click(screen.getByLabelText('Logical slot two phase'));fireEvent.click(screen.getByLabelText('Logical slot failover'));
    fireEvent.change(screen.getByLabelText('Replication principal password'),{target:{value:'native-only'}});
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));await screen.findByLabelText('Native backup review');
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'logical_slot_create',
      options:{slot:'owned_logical',if_not_exists:false,timeout_seconds:30,plugin:'pgoutput',two_phase:true,failover:true},replication_access:{password:'native-only'}}});
    post.mockResolvedValue({...nativeReview,state:'completed',native_utility_acknowledged:true});
    fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));await screen.findByRole('button',{name:'Refresh receipt'});
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:reviewed.job_id,review_digest:reviewed.review_digest,confirmed:true,replication_access:{password:'native-only'}}});
    expect(screen.getByLabelText('Replication principal password')).toHaveValue('');
  });

  it.each(['wal_slot_create','wal_slot_drop'])('admits %s through physical replication without claiming catalog observations',async operation => {
    const nativeReview={...reviewed,operation,source:{admission_interface:'physical-replication',slot_catalog_observed:false}};
    const post=jest.fn().mockResolvedValue(nativeReview);
    render(<Component post={post} />);
    fireEvent.mouseDown(screen.getByRole('combobox',{name:'Continuity operation'}));
    fireEvent.click(await screen.findByRole('option',{name:operation==='wal_slot_create' ? 'Create physical replication slot' : 'Drop replication slot'}));
    fireEvent.change(screen.getByLabelText('Replication slot name'),{target:{value:'owned_slot'}});
    fireEvent.click(screen.getByRole('checkbox',{name:'Use native replication-only admission'}));
    expect(screen.getByRole('button',{name:'Load replication slots'})).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Replication principal password'),{target:{value:'native-only'}});
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    await screen.findByLabelText('Native backup review');
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation,options:{slot:'owned_slot',if_not_exists:false,timeout_seconds:30},replication_access:{password:'native-only'}}});
    post.mockResolvedValue({...nativeReview,state:'completed',native_utility_acknowledged:true,slot_observation_state:'unavailable'});
    fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
    await screen.findByRole('button',{name:'Refresh receipt'});
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:reviewed.job_id,review_digest:reviewed.review_digest,confirmed:true,replication_access:{password:'native-only'}}});
    expect(screen.getByLabelText('Replication principal password')).toHaveValue('');
    expect(post.mock.calls.some(([value]) => value.action==='postgresql_continuity_slots')).toBe(false);
  });

  it('releases an uncertain owned SSH transport without repeating its acknowledged native backup',async () => {
    const record={...reviewed,state:'failed',native_backup_acknowledged:true,transport_release:{state:'unconfirmed'}};
    const post=jest.fn().mockResolvedValue({jobs:[record],total:1,unavailable_job_ids:[]});
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
    const inspect=await screen.findByRole('button',{name:'Inspect backup native-job'});
    post.mockResolvedValue(record);
    fireEvent.click(inspect);
    fireEvent.click(await screen.findByRole('button',{name:'Retry owned transport release'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_release_transport',request:{job_id:record.job_id}}));
    expect(post.mock.calls.every(([value]) => value.action!=='postgresql_continuity_start')).toBe(true);
  });

  it.each(['password','private_key'])('uses the inspected registered SSH peer with %s authentication',async authentication => {
    const metadata={ssh:{authentication,host:'ssh.native',port:22,username:'registered-user',remote_host:'db.native',remote_port:5432},
      ssh_peer:{openssh_key:'ssh-rsa public-native-key',fingerprint:'SHA256:observed'}};
    const nativeReview={...reviewed,source:{admission_interface:'physical-replication'}};
    const post=jest.fn().mockImplementation(value => Promise.resolve(value.action==='postgresql_continuity_transport' ? metadata :
      value.action==='postgresql_continuity_start' ? {...nativeReview,state:'cancelled'} : nativeReview));
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('checkbox',{name:'Use native replication-only admission'}));
    fireEvent.change(screen.getByLabelText('Replication principal password'),{target:{value:'db-credential'}});
    fireEvent.click(screen.getByRole('button',{name:'Inspect registered SSH transport'}));
    await screen.findByLabelText('Expected SSH public host key');
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_transport',request:{probe_ssh:true}});
    const label=authentication==='private_key' ? 'SSH private-key passphrase' : 'SSH password';
    fireEvent.change(screen.getByLabelText(label),{target:{value:'ssh-credential'}});
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    await screen.findByLabelText('Native backup review');
    const access={password:'db-credential',ssh_host_key:'ssh-rsa public-native-key',
      [authentication==='private_key' ? 'ssh_private_key_password' : 'ssh_password']:'ssh-credential'};
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'postgresql_continuity_review',request:expect.objectContaining({replication_access:access})}));
    fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
    await screen.findByRole('button',{name:'Refresh receipt'});
    expect(screen.getByLabelText(label)).toHaveValue('');
    expect(screen.getByLabelText('Replication principal password')).toHaveValue('');
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:'native-job',review_digest:'native-digest',confirmed:true,replication_access:access}});
    fireEvent.click(screen.getByRole('button',{name:'Refresh receipt'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_status',request:{job_id:'native-job'}}));
  });

  it.each(['full_backup','incremental_backup'])('reviews %s with explicit replication credentials and native options',async operation => {
    const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'verified'}],total:1,unavailable_job_ids:[]});
    render(<Component post={post} />);
    if(operation==='incremental_backup') {
      fireEvent.mouseDown(screen.getByRole('combobox',{name:'Continuity operation'}));
      fireEvent.click(await screen.findByRole('option',{name:'Incremental physical backup'}));
      fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
      fireEvent.click(await screen.findByRole('button',{name:'Select input'}));
    }
    fireEvent.click(screen.getByRole('checkbox',{name:'Use native replication-only admission'}));
    fireEvent.change(screen.getByLabelText('Replication principal password'),{target:{value:'native-only'}});
    post.mockResolvedValue({...reviewed,operation,source:{admission_interface:'physical-replication'}});
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    await screen.findByLabelText('Native backup review');
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'postgresql_continuity_review',request:expect.objectContaining({operation,replication_access:{password:'native-only'},options:expect.objectContaining({format:'plain'})})}));
    expect(screen.getByLabelText('Native backup review')).not.toHaveTextContent('native-only');
  });

  it('starts offline verification of a replication-only backup without new credentials or SQL admission',async () => {
    const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'verified'}],total:1,unavailable_job_ids:[]});
    render(<Component post={post} />);
    fireEvent.mouseDown(screen.getByRole('combobox',{name:'Continuity operation'}));
    fireEvent.click(await screen.findByRole('option',{name:'Verify existing backup'}));
    fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
    fireEvent.click(await screen.findByRole('button',{name:'Select input'}));
    post.mockResolvedValue({...reviewed,operation:'verify',source:{admission_interface:'physical-replication'}});
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    await screen.findByLabelText('Native backup review');
    post.mockResolvedValue({...reviewed,operation:'verify',state:'verified'});
    fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
    await screen.findByRole('button',{name:'Refresh receipt'});
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:'native-job',review_digest:'native-digest',confirmed:true}});
  });

  it('admits WAL through replication without SQL and keeps credentials out of receipt requests',async () => {
    const nativeReview={...reviewed,operation:'wal_capture',source:{...reviewed.source,admission_interface:'physical-replication'}};
    const post=jest.fn().mockResolvedValue(nativeReview);
    render(<Component post={post} />);
    fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
    fireEvent.click(await screen.findByRole('option',{name:'Capture native WAL archive'}));
    fireEvent.click(screen.getByRole('checkbox',{name:'Use native replication-only admission'}));
    fireEvent.change(screen.getByLabelText('Replication principal password'),{target:{value:'ephemeral-native-secret'}});
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    await screen.findByLabelText('Native backup review');
    expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'postgresql_continuity_review',request:expect.objectContaining({replication_access:{password:'ephemeral-native-secret'}})}));
    expect(screen.getByLabelText('Native backup review')).not.toHaveTextContent('ephemeral-native-secret');
    post.mockResolvedValue({...nativeReview,state:'cancelled'});
    fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
    await screen.findByRole('button',{name:'Refresh receipt'});
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:'native-job',review_digest:'native-digest',confirmed:true,replication_access:{password:'ephemeral-native-secret'}}});
    expect(screen.getByLabelText('Replication principal password')).toHaveValue('');
    fireEvent.click(screen.getByRole('button',{name:'Refresh receipt'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_status',request:{job_id:'native-job'}}));
  });

  it('clears replication credentials when changing operation or endpoint',async () => {
    const post=jest.fn();const mounted=render(<Component post={post} />);
    fireEvent.mouseDown(await screen.findByRole('combobox',{name:'Continuity operation'}));
    fireEvent.click(await screen.findByRole('option',{name:'Capture native WAL archive'}));
    fireEvent.click(screen.getByRole('checkbox',{name:'Use native replication-only admission'}));
    fireEvent.change(screen.getByLabelText('Replication principal password'),{target:{value:'private'}});
    fireEvent.mouseDown(await screen.findByRole('combobox',{name:'Continuity operation'}));
    fireEvent.click(await screen.findByRole('option',{name:'Full physical backup'}));
    expect(screen.queryByLabelText('Replication principal password')).not.toBeInTheDocument();
    fireEvent.mouseDown(await screen.findByRole('combobox',{name:'Continuity operation'}));
    fireEvent.click(await screen.findByRole('option',{name:'Capture native WAL archive'}));
    fireEvent.click(screen.getByRole('checkbox',{name:'Use native replication-only admission'}));
    expect(screen.getByLabelText('Replication principal password')).toHaveValue('');
    fireEvent.change(screen.getByLabelText('Replication principal password'),{target:{value:'private-again'}});
    mounted.rerender(<Component post={jest.fn()} />);
    expect(screen.queryByLabelText('Replication principal password')).not.toBeInTheDocument();
    expect(post).not.toHaveBeenCalled();
  });

  it('does not start a backup until the displayed review is explicitly confirmed',async () => {
    const post=jest.fn().mockResolvedValue(reviewed);
    render(<Component post={post} />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    await screen.findByText('Complete cluster backup');
    expect(post.mock.calls[0][0].action).toBe('postgresql_continuity_review');
    expect(screen.getByLabelText('Native backup review')).toHaveTextContent('18446744073709551615');
    post.mockResolvedValue({...reviewed,state:'verified',verification_scope:{files:true,wal:true},recovery_drill_complete:false});
    fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
    await screen.findByText(/Recovery drill: not completed/);
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_start',request:{job_id:'native-job',review_digest:'native-digest',confirmed:true}});
    expect(screen.getByRole('button',{name:'Confirm and start reviewed operation'})).toBeDisabled();
  });
  it('loads offline receipts directly and never bootstraps a connected workspace',async () => {
    const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'unknown'}],total:1,unavailable_job_ids:[]});
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
    await screen.findByRole('table',{name:'Native physical backup jobs'});
    expect(post).toHaveBeenCalledWith({action:'postgresql_continuity_list',request:{offset:0,limit:25}});
    post.mockResolvedValue({...reviewed,state:'unknown',observation_blocker:'Inspect the artifact before repeating'});
    fireEvent.click(screen.getByRole('button',{name:'Inspect backup native-job'}));
    await screen.findByText(/Inspect the artifact before repeating/, {selector:'.MuiAlert-message'});
    expect(screen.getByRole('button',{name:'Cancel native job'})).toBeDisabled();
  });
  it('drops the previous endpoint review and ignores its late response',async () => {
    let finish;
    const first=jest.fn(() => new Promise(resolve => {finish=resolve;}));
    const mounted=render(<Component post={first} />);
    fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
    mounted.rerender(<Component post={jest.fn()} />);
    finish(reviewed);
    await waitFor(() => expect(screen.getByRole('button',{name:'Review native operation'})).toBeEnabled());
    expect(screen.queryByText('Complete cluster backup')).not.toBeInTheDocument();
  });
  it('requires explicit writer cleanup confirmation and keeps an uncertain backup unverified',async () => {
    const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'unknown'}],total:1,unavailable_job_ids:[]});
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
    await screen.findByRole('table',{name:'Native physical backup jobs'});
    post.mockResolvedValue({...reviewed,state:'unknown'});
    fireEvent.click(screen.getByRole('button',{name:'Inspect backup native-job'}));
    const reconcile=await screen.findByRole('button',{name:'Reconcile native writer'});
    expect(reconcile).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox',{name:'Confirm stopping this job\'s remaining native utilities'}));
    post.mockResolvedValue({...reviewed,state:'unknown',writer_reconciliation:{process_scope_stopped:true,artifact_verified:false}});
    fireEvent.click(reconcile);
    await screen.findByText('Owned native utilities are stopped. Backup verification and recovery retain separate receipts.');
    expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_reconcile_writer',request:{job_id:'native-job',confirmed:true}});
    expect(screen.getByRole('button',{name:'Reconcile native writer'})).toBeDisabled();
    expect(screen.queryByText(/Native file verification: yes/)).not.toBeInTheDocument();
  });
});

it('preserves an explicit no-deadline selection in native review',async () => {
  const post=jest.fn().mockResolvedValue(reviewed);
  render(<Component post={post} />);
  fireEvent.change(screen.getByLabelText('Timeout seconds (blank: no limit)'),{target:{value:''}});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post.mock.calls[0][0].request.options.timeout_seconds).toBeNull();
});

it('reviews structured recovery counts without rounding int64 text',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'verified'}],total:1,unavailable_job_ids:[]});
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Recover isolated backup copy'}));
  fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
  fireEvent.click(await screen.findByRole('button',{name:'Select input'}));
  fireEvent.click(screen.getByRole('button',{name:'Add recovery table check'}));
  fireEvent.change(screen.getByLabelText('table 1'),{target:{value:'Exact "😀"'}});
  fireEvent.change(screen.getByLabelText('expected rows 1'),{target:{value:'9007199254740993'}});
  post.mockResolvedValue({...reviewed,operation:'recovery_drill'});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'recovery_drill',base_job_id:'native-job',options:{database:'postgres',checks:[{schema:'public',table:'Exact "😀"',expected_rows:'9007199254740993'}],timeout_seconds:3600}}});
  post.mockResolvedValue({...reviewed,state:'recovered',recovery_drill_complete:true,verification_scope:{selected_heap_counts:1}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
  await screen.findByText(/Isolated native recovery completed/);
  expect(screen.getByRole('button',{name:'Cancel native job'})).toBeDisabled();
});

it('reviews a native restore point and the selected owner-scoped WAL archive',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...reviewed,state:'verified'}],total:1,unavailable_job_ids:[]});
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Recover isolated backup copy'}));
  fireEvent.click(screen.getByRole('button',{name:'Load backup jobs'}));
  fireEvent.click(await screen.findByRole('button',{name:'Select input'}));
  fireEvent.mouseDown(screen.getByLabelText('Recovery target'));
  fireEvent.click(await screen.findByRole('option',{name:'Named restore point'}));
  fireEvent.change(screen.getByLabelText('Exact native target value'),{target:{value:'Exact ü \' restore point'}});
  post.mockResolvedValue({archives:['completed'],owner_endpoint_directory:'/owned/native/archives'});
  fireEvent.click(screen.getByRole('button',{name:'Load WAL archives'}));
  await screen.findByText(/Archive directory: \/owned\/native\/archives/);
  fireEvent.mouseDown(screen.getByLabelText('Native WAL archive'));
  fireEvent.click(await screen.findByRole('option',{name:'completed'}));
  post.mockResolvedValue({...reviewed,operation:'recovery_drill'});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'recovery_drill',base_job_id:'native-job',
    options:{database:'postgres',checks:[],timeout_seconds:3600,wal_archive:'completed',target:{kind:'name',value:'Exact ü \' restore point',inclusive:true,timeline:'current'}}}});
  fireEvent.change(screen.getByLabelText('Exact native target value'),{target:{value:'new target'}});
  expect(screen.queryByRole('button',{name:'Confirm and start reviewed operation'})).not.toBeInTheDocument();
});

it('reviews native WAL capture independently of backup inputs and preserves an unlimited receiver duration',async () => {
  const post=jest.fn().mockResolvedValue({...reviewed,operation:'wal_capture'});
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Capture native WAL archive'}));
  fireEvent.change(screen.getByLabelText('WAL archive'),{target:{value:'owned.capture'}});
  fireEvent.change(screen.getByLabelText('WAL compression'),{target:{value:'gzip:level=3'}});
  fireEvent.change(screen.getByLabelText('WAL end lsn'),{target:{value:'A/FFFFFFFF'}});
  fireEvent.change(screen.getByLabelText('WAL status interval seconds'),{target:{value:'0'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'wal_capture',
    options:{archive:'owned.capture',compression:'gzip:level=3',end_lsn:'A/FFFFFFFF',slot:'',
      synchronous:true,sync:true,status_interval_seconds:0,no_loop:false,timeout_seconds:null}}});
  expect(screen.queryByText('Selected input')).not.toBeInTheDocument();
  post.mockResolvedValue({...reviewed,operation:'wal_capture',state:'captured',archive_observation:{completed_files:3,new_files:2}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
  await screen.findByText(/Completed archive files observed: 3. Newly published: 2/);
  expect(screen.queryByText(/Native file verification: yes/)).not.toBeInTheDocument();
});

it('loads native slot properties, selects an exact name and reviews physical creation without a backup input',async () => {
  const post=jest.fn().mockResolvedValue({slots:[{slot_name:'owned_slot',slot_type:'physical',active:false,
    safe_wal_size:'9223372036854775807',database:null}],total:1,offset:0,limit:25});
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Create physical replication slot'}));
  fireEvent.click(screen.getByRole('button',{name:'Load replication slots'}));
  await screen.findByRole('table',{name:'Native replication slots'});
  expect(post).toHaveBeenCalledWith({action:'postgresql_continuity_slots',request:{offset:0,limit:25}});
  expect(screen.getByText(/9223372036854775807/, {selector:'pre'})).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Use slot owned_slot'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'Accept existing slot unchanged'}));
  post.mockResolvedValue({...reviewed,operation:'wal_slot_create'});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'wal_slot_create',
    options:{slot:'owned_slot',if_not_exists:true,timeout_seconds:30}}});
  expect(screen.queryByText('Selected input')).not.toBeInTheDocument();
});

it('keeps polling a completed native acknowledgement until its later slot observation arrives',async () => {
  const post=jest.fn().mockResolvedValue({...reviewed,operation:'wal_slot_create'});
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Create physical replication slot'}));
  fireEvent.change(screen.getByLabelText('Replication slot name'),{target:{value:'owned_slot'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  post.mockResolvedValue({...reviewed,operation:'wal_slot_create',state:'completed',native_utility_acknowledged:true,slot_observation_state:'pending'});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
  await screen.findByText(/Native utility acknowledged: yes. Current slot observation: pending/);
  post.mockResolvedValue({...reviewed,operation:'wal_slot_create',state:'completed',native_utility_acknowledged:true,
    slot_observation_state:'observed',slot_observation:{slot_type:'physical',active:false}});
  await screen.findByText(/Current slot observation: physical; active: false/,{}, {timeout:5000});
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_status',request:{job_id:'native-job'}});
});

it('selects the native database and logical slot options without a utility or backup input',async () => {
  const post=jest.fn().mockResolvedValue({targets:[{target_id:'postgresql-database:123',display_name:'Exact "ü"'}]});
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Create logical replication slot'}));
  expect(screen.getByRole('button',{name:'Review native operation'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Load slot databases'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Load slot databases'})).toBeEnabled());
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_slot_databases',request:{}});
  post.mockResolvedValue({...reviewed,operation:'wal_slot_sql_logical_create'});
  fireEvent.mouseDown(screen.getByLabelText('Native SQL slot database'));
  fireEvent.click(await screen.findByRole('option',{name:'Exact "ü"'}));
  fireEvent.change(screen.getByLabelText('Replication slot name'),{target:{value:'owned_logical'}});
  fireEvent.click(screen.getByRole('checkbox',{name:'two phase'}));
  fireEvent.click(screen.getByRole('checkbox',{name:'failover'}));
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'wal_slot_sql_logical_create',
    database_target_id:'postgresql-database:123',options:{slot:'owned_logical',plugin:'pgoutput',two_phase:true,failover:true,timeout_seconds:30}}});
  expect(screen.queryByText('Selected input')).not.toBeInTheDocument();
  expect(screen.queryByLabelText('manifest checksums')).not.toBeInTheDocument();
});

it('copies the selected source slot and preserves plugin inheritance and the owned database',async () => {
  const post=jest.fn().mockResolvedValue({slots:[{slot_name:'source_slot',slot_type:'logical',active:false}],total:1});
  const {rerender}=render(<Component post={post} databaseTargetId="postgresql-database:123" />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Copy logical replication slot'}));
  fireEvent.click(screen.getByRole('button',{name:'Load replication slots'}));
  fireEvent.click(await screen.findByRole('button',{name:'Use slot source_slot'}));
  expect(screen.getByLabelText('Source replication slot')).toHaveValue('source_slot');
  fireEvent.change(screen.getByLabelText('Replication slot name'),{target:{value:'destination'}});
  fireEvent.change(screen.getByLabelText('Output plugin (blank copy: inherit)'),{target:{value:''}});
  post.mockResolvedValue({...reviewed,operation:'wal_slot_sql_logical_copy'});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'wal_slot_sql_logical_copy',
    database_target_id:'postgresql-database:123',options:{slot:'destination',source_slot:'source_slot',plugin:'',timeout_seconds:30}}});
  post.mockResolvedValue({...reviewed,operation:'wal_slot_sql_logical_copy',state:'unknown',native_sql_acknowledged:false});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
  await screen.findByText(/Native SQL acknowledged: unconfirmed/);
  expect(screen.queryByRole('button',{name:'Reconcile native writer'})).not.toBeInTheDocument();
  rerender(<Component post={post} databaseTargetId="postgresql-database:456" />);
  expect(screen.queryByRole('button',{name:'Confirm and start reviewed operation'})).not.toBeInTheDocument();
});

it('reviews exact ordered decoding options and delivers a lossless binary artifact through the download manager',async () => {
  const post=jest.fn().mockResolvedValue({...reviewed,operation:'wal_slot_sql_get_binary'});
  render(<Component post={post} databaseTargetId="postgresql-database:123" endpointUrl="/owned/workspace" />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Consume logical binary changes'}));
  fireEvent.change(screen.getByLabelText('Replication slot name'),{target:{value:'owned_logical'}});
  fireEvent.change(screen.getByLabelText('Native change threshold (blank: no limit)'),{target:{value:''}});
  fireEvent.change(screen.getByLabelText('Changes up to LSN (blank: native end)'),{target:{value:'FFFFFFFF/FFFFFFFF'}});
  for(const [index,name,value] of [[1,'proto_version','4'],[2,'publication_names','Exact "ü"']]) {
    fireEvent.click(screen.getByRole('button',{name:'Add output plugin option'}));
    fireEvent.change(screen.getByLabelText(`Plugin option name ${index}`),{target:{value:name}});
    fireEvent.change(screen.getByLabelText(`Plugin option value ${index}`),{target:{value}});
  }
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_review',request:{operation:'wal_slot_sql_get_binary',database_target_id:'postgresql-database:123',
    options:{slot:'owned_logical',timeout_seconds:30,upto_lsn:'FFFFFFFF/FFFFFFFF',upto_nchanges:null,plugin_options:[{name:'proto_version',value:'4'},{name:'publication_names',value:'Exact "ü"'}]}}});
  post.mockResolvedValue({...reviewed,operation:'wal_slot_sql_get_binary',state:'completed',native_sql_acknowledged:true,native_sql_result:{rows:'4294967295'},change_artifact:{state:'verified'}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
  await screen.findByText(/Captured change rows: 4294967295. Artifact: verified/);
  fireEvent.click(screen.getByRole('button',{name:'Download logical changes'}));
  expect(startBrowserFileDownload).toHaveBeenCalledWith('/owned/workspace',{job_id:'native-job'},
    {action:'postgresql_continuity_change_download',prefix:'postgresql-logical',title:'PostgreSQL logical change download'});
  post.mockResolvedValue({rows:[{lsn:'FFFFFFFF/FFFFFFFF',xid:'4294967295',data_encoding:'base64',data:'AID/'}],next_offset:null});
  fireEvent.click(screen.getByRole('button',{name:'Preview captured changes'}));
  await screen.findByRole('table',{name:'Captured native logical changes'});
  expect(screen.getByText('AID/')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Next change page'})).toBeDisabled();
});

it('keeps incomplete capture inspection separate from an unknown native consumption outcome',async () => {
  const post=jest.fn().mockResolvedValue({...reviewed,operation:'wal_slot_sql_get_text'});
  render(<Component post={post} databaseTargetId="postgresql-database:123" endpointUrl="/owned/workspace" />);
  fireEvent.mouseDown(screen.getByLabelText('Continuity operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Consume logical text changes'}));
  fireEvent.change(screen.getByLabelText('Replication slot name'),{target:{value:'owned_logical'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native operation'}));
  await screen.findByText('Complete cluster backup');
  post.mockResolvedValue({...reviewed,operation:'wal_slot_sql_get_text',state:'unknown',native_sql_acknowledged:false,change_artifact:{state:'unavailable'}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start reviewed operation'}));
  await screen.findByText(/Native SQL acknowledged: unconfirmed/);
  expect(screen.getByRole('button',{name:'Preview captured changes'})).toBeDisabled();
  post.mockResolvedValue({...reviewed,operation:'wal_slot_sql_get_text',state:'unknown',native_sql_acknowledged:false,change_artifact:{state:'partial'}});
  fireEvent.click(screen.getByRole('button',{name:'Inspect and reconcile captured bytes'}));
  await screen.findByText(/These captured bytes are incomplete evidence/);
  expect(post).toHaveBeenLastCalledWith({action:'postgresql_continuity_change_reconcile',request:{job_id:'native-job'}});
  expect(screen.getByRole('button',{name:'Download incomplete captured changes'})).toBeEnabled();
  expect(screen.queryByRole('button',{name:'Reconcile native writer'})).not.toBeInTheDocument();
});
