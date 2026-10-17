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

it('selects an owned sealed input and exact target before review and confirmation',async () => {
  const post=jest.fn(async ({action}) => ({
    mysql_binlog_replay_inspect:{identity:{server_uuid:target},state:{gtid_mode:'ON'}},
    mysql_binlog_replay_sources:{sources:[{server_id:7,name:'Registered source'}],offset:0,total:1},
    mysql_binlog_replay_archives:{jobs:[{job_id:'sealed-archive',state:'completed',native_process_termination_confirmed:true,result:{artifact:{total_bytes:'9007199254740993'}}}],offset:0,total:1},
    mysql_binlog_replay_review:item,
    mysql_binlog_replay_start:{...item,state:'native_load_returned',native_load_outcome:'returned'},
  }[action]));
  render(<Component post={post} />);expect(post).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Review replay'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Inspect replay target'}));await screen.findByText('Native replay target: '+target);
  fireEvent.click(screen.getByRole('button',{name:'Load archive sources'}));await screen.findByLabelText('Owned archive source');
  fireEvent.mouseDown(screen.getByLabelText('Owned archive source'));fireEvent.click(await screen.findByRole('option',{name:'Registered source (7)'}));
  fireEvent.click(screen.getByRole('button',{name:'Load sealed archives'}));await screen.findByLabelText('Sealed native archive');
  fireEvent.mouseDown(screen.getByLabelText('Sealed native archive'));fireEvent.click(await screen.findByRole('option',{name:'sealed-archive (9007199254740993 bytes)'}));
  fireEvent.change(screen.getByLabelText('Confirm target server UUID'),{target:{value:target}});
  fireEvent.click(screen.getByRole('button',{name:'Review replay'}));await screen.findByText('Native commits are independent');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_replay_review',request:{source_server_id:7,archive_job_id:'sealed-archive',options:{stop_mode:'all',stop_gtid:null,target_confirmation:target,timeout_seconds:3600}}});
  expect(screen.getByLabelText('Native replay review')).toHaveTextContent('sealed-native-bytes');
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start replay'}));await screen.findByText(/Native load: returned/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_replay_start',request:{job_id:item.job_id,review_digest:'digest',confirmed:true}});
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
