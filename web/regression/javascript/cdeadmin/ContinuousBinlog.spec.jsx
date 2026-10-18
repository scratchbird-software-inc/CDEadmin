import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import ContinuousBinlog from 'sources/Dialogs/ContinuousBinlog';
import {withTheme} from '../fake_theme';

const Component=withTheme(ContinuousBinlog);
let originalHeight;
beforeEach(() => {originalHeight=window.innerHeight;window.innerHeight=1200;});
afterEach(() => {window.innerHeight=originalHeight;});
const reviewed={job_id:'owned-receiver',review_digest:'native-review',state:'reviewed',source:{server_uuid:'owned'},
  options:{start_file:'native.000001',receiver_server_id:4294967295,timeout_seconds:null},
  program:{tool_version:'9.7.0'},execution_host:{kind:'application-host'},warnings:['Explicit native receiver ID']};

it('reviews an active native log and explicit uint32 receiver ID without introducing a deadline',async () => {
  const post=jest.fn().mockResolvedValue({status:'available',logs:[{Log_name:'native.000001',closed:false}]}),inspect=jest.fn();
  render(<Component post={post} engine="mysql" onInspectArchive={inspect} />);
  fireEvent.click(screen.getByRole('button',{name:'Inspect receiver source'}));
  await screen.findByText('Native receiver source: available');
  fireEvent.mouseDown(screen.getByLabelText('Receiver starting native log'));
  fireEvent.click(await screen.findByRole('option',{name:'native.000001 (active)'}));
  fireEvent.change(screen.getByLabelText('Unique receiver server ID'),{target:{value:'4294967295'}});
  post.mockResolvedValue(reviewed);
  fireEvent.click(screen.getByRole('button',{name:'Review continuous receiver'}));
  await screen.findByText('Explicit native receiver ID');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_capture_review',request:{options:{start_file:'native.000001',receiver_server_id:4294967295,timeout_seconds:null}}});
  post.mockResolvedValue({...reviewed,state:'active',progress:{published_batches:1,last_archive_job_ids:['verified-native-archive']}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start continuous receiver'}));
  await screen.findByText(/Published archive batches: 1/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_capture_start',request:{job_id:'owned-receiver',review_digest:'native-review',confirmed:true}});
  fireEvent.click(screen.getByRole('button',{name:'Inspect produced archive verified-native-archive'}));
  expect(inspect).toHaveBeenCalledWith('verified-native-archive');
  post.mockResolvedValue({...reviewed,state:'cancelled',result:{published_batches:1,last_archive_job_ids:['verified-native-archive']}});
  fireEvent.click(screen.getByRole('button',{name:'Cancel continuous receiver'}));
  await screen.findByText(/Receiver owned-receiver: cancelled/);
  expect(screen.getByRole('button',{name:'Cancel continuous receiver'})).toBeDisabled();
});

it('uses the native MariaDB action family and clears a stale review when the engine changes',async () => {
  const post=jest.fn().mockResolvedValue(reviewed),inspect=jest.fn();
  const {rerender}=render(<Component post={post} engine="mariadb" onInspectArchive={inspect} />);
  fireEvent.change(screen.getByLabelText('Unique receiver server ID'),{target:{value:'43'}});
  fireEvent.change(screen.getByLabelText('Receiver runtime seconds (blank: no deadline)'),{target:{value:'60'}});
  fireEvent.click(screen.getByRole('button',{name:'Review continuous receiver'}));
  await screen.findByText('Explicit native receiver ID');
  expect(post).toHaveBeenLastCalledWith({action:'mariadb_binlog_capture_review',request:{options:{start_file:'',receiver_server_id:43,timeout_seconds:60}}});
  rerender(<Component post={post} engine="mysql" onInspectArchive={inspect} />);
  await waitFor(() => expect(screen.queryByRole('button',{name:'Confirm and start continuous receiver'})).not.toBeInTheDocument());
  expect(screen.getByLabelText('Unique receiver server ID')).toHaveValue(null);
});
