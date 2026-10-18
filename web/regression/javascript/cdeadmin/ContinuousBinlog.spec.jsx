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

it('requires explicit writer-stop confirmation and prepares a separate reviewed restart',async () => {
  const stopped={...reviewed,state:'cancelled',native_process_termination_confirmed:true,result:{next_file:'native.000004'}};
  const post=jest.fn().mockResolvedValue({jobs:[stopped],total:1}),inspect=jest.fn();
  render(<Component post={post} engine="mariadb" onInspectArchive={inspect} />);
  fireEvent.click(screen.getByRole('button',{name:'Load binary-log receivers'}));
  await screen.findByRole('button',{name:'Inspect receiver owned-receiver'});
  post.mockResolvedValue(stopped);fireEvent.click(screen.getByRole('button',{name:'Inspect receiver owned-receiver'}));
  await screen.findByText(/Receiver owned-receiver: cancelled/);
  expect(screen.getByRole('button',{name:'Reconcile receiver writers'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Confirm stopping this receiver\'s remaining native utilities'));
  post.mockResolvedValue({...stopped,writer_reconciliation:{process_scope_stopped:true}});
  fireEvent.click(screen.getByRole('button',{name:'Reconcile receiver writers'}));
  await screen.findByText(/Owned receiver and snapshot-parser utilities are stopped/);
  expect(post).toHaveBeenLastCalledWith({action:'mariadb_binlog_capture_reconcile_writer',request:{job_id:'owned-receiver',confirmed:true}});
  fireEvent.change(screen.getByLabelText('Unique receiver server ID'),{target:{value:'44'}});
  post.mockResolvedValue({...reviewed,job_id:'new-reviewed-receiver',options:{...reviewed.options,start_file:'native.000004',receiver_server_id:44}});
  fireEvent.click(screen.getByRole('button',{name:'Review restart from stopped receiver'}));
  await screen.findByText('Explicit native receiver ID');
  expect(post).toHaveBeenLastCalledWith({action:'mariadb_binlog_capture_review',request:{resume_job_id:'owned-receiver',options:{start_file:'native.000004',receiver_server_id:44,timeout_seconds:null}}});
  expect(screen.getByRole('button',{name:'Confirm and start continuous receiver'})).toBeEnabled();
});

it('does not offer restart for an uncertain receiver even after its writers were stopped',async () => {
  const unknown={...reviewed,state:'unknown',writer_reconciliation:{process_scope_stopped:true},result:{next_file:'native.000004'}};
  const post=jest.fn().mockResolvedValue({jobs:[unknown],total:1});
  render(<Component post={post} engine="mysql" onInspectArchive={jest.fn()} />);
  fireEvent.click(screen.getByRole('button',{name:'Load binary-log receivers'}));
  await screen.findByRole('button',{name:'Inspect receiver owned-receiver'});
  post.mockResolvedValue(unknown);fireEvent.click(screen.getByRole('button',{name:'Inspect receiver owned-receiver'}));
  await screen.findByText(/Receiver owned-receiver: unknown/);
  expect(screen.queryByRole('button',{name:'Review restart from stopped receiver'})).not.toBeInTheDocument();
});

it('selects complete stopped files and dispatches a separate reviewed archive without rewriting the receiver',async () => {
  const failed={...reviewed,state:'failed'},post=jest.fn().mockResolvedValue({jobs:[failed],total:1}),inspect=jest.fn();
  render(<Component post={post} engine="mysql" onInspectArchive={inspect} />);
  fireEvent.click(screen.getByRole('button',{name:'Load binary-log receivers'}));
  await screen.findByRole('button',{name:'Inspect receiver owned-receiver'});
  post.mockResolvedValue(failed);fireEvent.click(screen.getByRole('button',{name:'Inspect receiver owned-receiver'}));
  await screen.findByText(/Receiver owned-receiver: failed/);
  post.mockResolvedValue({logs:[{Log_name:'native.000001',eligible:true,local_bytes:'9007199254740993',File_size:'9007199254740993'},
    {Log_name:'native.000002',eligible:false,reason:'Active or incomplete',local_bytes:'40',File_size:'80'}]});
  fireEvent.click(screen.getByRole('button',{name:'Inspect stopped receiver files'}));
  await screen.findByRole('table',{name:'Stopped native receiver files'});
  expect(screen.getByLabelText('Adopt native.000002')).toBeDisabled();
  expect(screen.getByRole('button',{name:'Review stopped-file adoption'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Adopt native.000001'));
  post.mockResolvedValue({...reviewed,job_id:'separate-archive'});
  fireEvent.click(screen.getByRole('button',{name:'Review stopped-file adoption'}));
  await screen.findByLabelText('Stopped-file archive review');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_capture_tail_review',request:{job_id:'owned-receiver',options:{log_names:['native.000001'],timeout_seconds:null}}});
  post.mockResolvedValue({job_id:'separate-archive',state:'active'});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and adopt stopped logs'}));
  await waitFor(() => expect(inspect).toHaveBeenCalledWith('separate-archive'));
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_capture_tail_start',request:{job_id:'separate-archive',review_digest:'native-review',confirmed:true}});
  expect(screen.getByText(/Receiver owned-receiver: failed/)).toBeInTheDocument();
});
