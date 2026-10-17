import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLBinlogReplay from 'sources/Dialogs/MySQLBinlogReplay';
import {withTheme} from '../fake_theme';
const Component=withTheme(MySQLBinlogReplay);
const target='00000000-0000-0000-0000-000000000002';
const item={job_id:'owned-replay',review_digest:'digest',state:'reviewed',warnings:['Native commits are independent'],
  target:{server_uuid:target},options:{},source_archive:{artifact_digest:'sealed-native-bytes'},execution_host:{kind:'application-host'},native_load_outcome:'not_dispatched'};
const oldHeight=window.innerHeight;
beforeAll(() => {window.innerHeight=1800;});
afterAll(() => {window.innerHeight=oldHeight;});

it.each(['mysql','mariadb'])('selects an owned sealed input and exact %s target before review and confirmation',async engine => {
  const identityKey=engine==='mariadb' ? 'server_uid' : 'server_uuid';
  const replayTarget=engine==='mariadb' ? 'aBcDeFgHiJkLmNoPqRsTuVwXyZ0=' : target;
  const prefix=engine+'_binlog_replay_';
  const post=jest.fn(async ({action}) => ({
    [prefix+'inspect']:{identity:{[identityKey]:replayTarget},state:{gtid_mode:'ON'}},
    [prefix+'sources']:{sources:[{server_id:7,name:'Registered source'}],offset:0,total:1},
    [prefix+'archives']:{jobs:[{job_id:'sealed-archive',state:'completed',native_process_termination_confirmed:true,result:{artifact:{total_bytes:'9007199254740993'}}}],offset:0,total:1},
    [prefix+'review']:{...item,target:{[identityKey]:replayTarget}},
    [prefix+'start']:{...item,state:'native_load_returned',native_load_outcome:'returned'},
  }[action]));
  render(<Component post={post} engine={engine} />);expect(post).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Review replay'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Inspect replay target'}));await screen.findByText('Native replay target: '+replayTarget);
  fireEvent.click(screen.getByRole('button',{name:'Load archive sources'}));await screen.findByLabelText('Owned archive source');
  fireEvent.mouseDown(screen.getByLabelText('Owned archive source'));fireEvent.click(await screen.findByRole('option',{name:'Registered source (7)'}));
  fireEvent.click(screen.getByRole('button',{name:'Load sealed archives'}));await screen.findByLabelText('Sealed native archive');
  fireEvent.mouseDown(screen.getByLabelText('Sealed native archive'));fireEvent.click(await screen.findByRole('option',{name:'sealed-archive (9007199254740993 bytes)'}));
  fireEvent.change(screen.getByLabelText(engine==='mariadb' ? 'Confirm target server UID' : 'Confirm target server UUID'),{target:{value:replayTarget}});
  fireEvent.click(screen.getByRole('button',{name:'Review replay'}));await screen.findByText('Native commits are independent');
  expect(post).toHaveBeenLastCalledWith({action:prefix+'review',request:{source_server_id:7,archive_job_id:'sealed-archive',options:{stop_mode:'all',stop_gtid:null,target_confirmation:replayTarget,timeout_seconds:3600}}});
  expect(screen.getByLabelText('Native replay review')).toHaveTextContent('sealed-native-bytes');
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start replay'}));await screen.findByText(/Native load: returned/);
  expect(post).toHaveBeenLastCalledWith({action:prefix+'start',request:{job_id:item.job_id,review_digest:'digest',confirmed:true}});
  expect(screen.getByRole('button',{name:'Confirm and start replay'})).toBeDisabled();
  expect(screen.getByText(/Recovered data has not been independently verified/)).toBeInTheDocument();
});

it('keeps unknown outcomes explicit and binds acknowledgement to current reconciliation facts',async () => {
  const unknown={...item,state:'unknown',native_load_outcome:'unknown',native_process_termination_confirmed:true};
  const post=jest.fn(async ({action}) => ({mysql_binlog_replay_list:{jobs:[unknown],offset:0,total:1},mysql_binlog_replay_status:unknown,
    mysql_binlog_replay_reconcile:{...unknown,reconciliation:{native_lock_free:true,all_archive_gtids_present:1},observation_digest:'fresh-native-facts'},
    mysql_binlog_replay_acknowledge:{...unknown,target_state_acknowledged_at:123}}[action]));
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load replay jobs'}));await screen.findByRole('table',{name:'Native MySQL replay jobs'});
  fireEvent.click(screen.getByRole('button',{name:'Inspect replay '+item.job_id}));await screen.findByText(/This target is fenced/);
  fireEvent.click(screen.getByRole('button',{name:'Inspect current target facts'}));await screen.findByLabelText('Native replay reconciliation');
  const acknowledge=screen.getByRole('button',{name:'Acknowledge facts and release target fence'});expect(acknowledge).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Acknowledge uncertain target UUID'),{target:{value:target}});fireEvent.click(acknowledge);
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_replay_acknowledge',request:{job_id:item.job_id,target_confirmation:target,observation_digest:'fresh-native-facts'}}));
  await screen.findByText(/original native load outcome remains uncertain/);
  expect(screen.queryByText(/This target is fenced/)).not.toBeInTheDocument();
  expect(post.mock.calls.every(([request]) => request.action!=='mysql_binlog_replay_start')).toBe(true);
});

it('discards an in-flight reply when the registered target changes',async () => {
  let resolve;const oldPost=jest.fn(() => new Promise(accept => {resolve=accept;}));const newPost=jest.fn();
  const view=render(<Component post={oldPost} />);fireEvent.click(screen.getByRole('button',{name:'Inspect replay target'}));
  view.rerender(<Component post={newPost} />);resolve({identity:{server_uuid:target}});
  await waitFor(() => expect(screen.queryByText('Native replay target: '+target)).not.toBeInTheDocument());
  expect(newPost).not.toHaveBeenCalled();
});

it('selects native raw boundaries and keeps wide positions exact in review',async () => {
  const groups=[{file:'native.000001',position:'9007199254740993',event_type:34,event_time_utc:'2026-10-17T12:00:00Z'},
    {file:'native.000001',position:'18446744073709551600',event_type:34,event_time_utc:'2026-10-17T12:00:01Z'}];
  const post=jest.fn(async ({action}) => ({
    mysql_binlog_replay_inspect:{identity:{server_uuid:target},state:{gtid_mode:'OFF'}},
    mysql_binlog_replay_sources:{sources:[{server_id:7,name:'Registered source'}],offset:0,total:1},
    mysql_binlog_replay_archives:{jobs:[{job_id:'raw-archive',state:'completed',native_process_termination_confirmed:true,result:{artifact:{total_bytes:'9007199254740993'}}}],offset:0,total:1},
    mysql_binlog_replay_boundaries:{groups,offset:0,total:2,limit:100},
    mysql_binlog_replay_review:item,
  }[action]));
  render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Archive format'));fireEvent.click(await screen.findByRole('option',{name:'MySQL raw closed logs'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect replay target'}));await screen.findByText('Native replay target: '+target);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_replay_inspect',request:{archive_family:'raw'}});
  fireEvent.click(screen.getByRole('button',{name:'Load archive sources'}));await screen.findByLabelText('Owned archive source');
  fireEvent.mouseDown(screen.getByLabelText('Owned archive source'));fireEvent.click(await screen.findByRole('option',{name:'Registered source (7)'}));
  fireEvent.click(screen.getByRole('button',{name:'Load sealed archives'}));await screen.findByLabelText('Sealed native archive');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_replay_archives',request:{source_server_id:7,offset:0,limit:25,archive_family:'raw'}});
  fireEvent.mouseDown(screen.getByLabelText('Sealed native archive'));fireEvent.click(await screen.findByRole('option',{name:'raw-archive (9007199254740993 bytes)'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect native transaction groups'}));await screen.findByRole('table',{name:'Native raw transaction groups'});
  fireEvent.click(screen.getByRole('button',{name:'Start raw replay at native.000001@9007199254740993'}));
  fireEvent.click(screen.getByRole('button',{name:'Stop raw replay after native.000001@18446744073709551600'}));
  fireEvent.change(screen.getByLabelText('Confirm target server UUID'),{target:{value:target}});
  fireEvent.click(screen.getByRole('button',{name:'Review replay'}));await screen.findByText('Native commits are independent');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_replay_review',request:{source_server_id:7,archive_job_id:'raw-archive',archive_family:'raw',
    options:{target_confirmation:target,timeout_seconds:3600,stop_mode:'after',start_file:'native.000001',start_position:'9007199254740993',stop_file:'native.000001',stop_position:'18446744073709551600'}}});
});
