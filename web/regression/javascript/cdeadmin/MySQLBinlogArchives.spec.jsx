import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLBinlogArchives from 'sources/Dialogs/MySQLBinlogArchives';
import {startBrowserFileDownload} from 'sources/Dialogs/browserFileDownload';
import {withTheme} from '../fake_theme';
jest.mock('sources/Dialogs/browserFileDownload',() => ({startBrowserFileDownload:jest.fn(() => jest.fn())}));
const Component=withTheme(MySQLBinlogArchives);
const viewportHeight=window.innerHeight;
beforeAll(() => {window.innerHeight=1200;});
afterAll(() => {window.innerHeight=viewportHeight;});
const review={job_id:'owned-job',review_digest:'digest',state:'reviewed',warnings:['Native whole-server archive'],
  source:{server_uuid:'native-source'},options:{start_file:'mysql-bin.000004',start_position:'9007199254740993'},execution_host:{kind:'application-host'}};

it('preserves a wide native position and reviews before confirming execution',async () => {
  const post=jest.fn().mockResolvedValue(review);render(<Component post={post} endpointUrl="/workspace" />);
  expect(post).not.toHaveBeenCalled();
  fireEvent.change(screen.getByLabelText('Native binary-log filename'),{target:{value:'mysql-bin.000004'}});
  fireEvent.change(screen.getByLabelText('Native position'),{target:{value:'9007199254740993'}});
  fireEvent.click(screen.getByRole('button',{name:'Review archive'}));
  await screen.findByText('Native whole-server archive');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_review',request:{options:{start_file:'mysql-bin.000004',start_position:'9007199254740993',compression:'zstd;level=1',threads:4,timeout_seconds:3600}}});
  expect(screen.getByLabelText('Native archive review')).toHaveTextContent('application-host');
  post.mockResolvedValue({...review,state:'no_new_snapshot',result:{artifact:null,continuation_cursor_advanced:false}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start archive'}));
  await screen.findByText(/continuation cursor was not advanced/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_start',request:{job_id:'owned-job',review_digest:'digest',confirmed:true}});
  expect(screen.getByRole('button',{name:'Confirm and start archive'})).toBeDisabled();
});

it('loads offline receipts, pages file identities and downloads through the authenticated browser form',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...review,state:'completed'}],total:1,unavailable_job_ids:[]});
  render(<Component post={post} endpointUrl="/workspace" />);
  fireEvent.click(screen.getByRole('button',{name:'Load archive jobs'}));await screen.findByRole('table',{name:'Native MySQL archive jobs'});
  post.mockResolvedValue({...review,state:'completed',native_process_termination_confirmed:true});
  fireEvent.click(screen.getByRole('button',{name:'Inspect archive owned-job'}));await screen.findByRole('button',{name:'Load archive files'});
  post.mockResolvedValue({files:[{path:'native/sr.000001.zst',size:'9007199254740993',sha256:'verified-hash'}],offset:0,limit:100,total:1});
  fireEvent.click(screen.getByRole('button',{name:'Load archive files'}));await screen.findByRole('table',{name:'Verified native archive files'});
  fireEvent.click(screen.getByRole('button',{name:'Download native/sr.000001.zst'}));
  expect(startBrowserFileDownload).toHaveBeenLastCalledWith('/workspace',{job_id:'owned-job',path:'native/sr.000001.zst'},expect.objectContaining({action:'mysql_binlog_download'}));
  expect(screen.getByText('9007199254740993')).toBeInTheDocument();
  expect(screen.getByRole('button',{name:'Remove application archive files'})).toBeDisabled();
  fireEvent.change(screen.getByLabelText('Confirm job identity to remove archive files'),{target:{value:'owned-job'}});
  post.mockResolvedValue({...review,state:'completed',artifact_removed:true});
  fireEvent.click(screen.getByRole('button',{name:'Remove application archive files'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_remove_artifact',request:{job_id:'owned-job',confirmation:'owned-job'}}));
  await screen.findByText(/receipt is retained/);
});

it('keeps uncertain termination explicit and exposes verification without replay',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...review,state:'unknown'}],total:1,unavailable_job_ids:[]});
  render(<Component post={post} endpointUrl="/workspace" />);
  fireEvent.click(screen.getByRole('button',{name:'Load archive jobs'}));await screen.findByRole('table',{name:'Native MySQL archive jobs'});
  post.mockResolvedValue({...review,state:'unknown'});fireEvent.click(screen.getByRole('button',{name:'Inspect archive owned-job'}));
  await screen.findByText(/process termination is uncertain/);
  expect(screen.getByRole('button',{name:'Cancel archive'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Verify archive again'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_binlog_reconcile',request:{job_id:'owned-job'}}));
});

it('uses native closed-log identities in server order for MariaDB without MySQL dump options',async () => {
  const post=jest.fn().mockResolvedValue({status:'available',logs:[{Log_name:'native.1',File_size:'600',closed:true},
    {Log_name:'native.2',File_size:'700',closed:true},{Log_name:'native.3',File_size:'800',closed:false}]});
  render(<Component engine="mariadb" post={post} endpointUrl="/workspace" />);
  expect(screen.queryByLabelText('Native compression')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Inspect native binary logs'}));await screen.findByText('Native source, GTID state and available logs: available');
  fireEvent.mouseDown(screen.getByLabelText('Native closed binary logs'));
  expect(screen.queryByRole('option',{name:'native.3 (800 bytes)'})).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('option',{name:'native.2 (700 bytes)'}));
  fireEvent.click(screen.getByRole('option',{name:'native.1 (600 bytes)'}));
  fireEvent.keyDown(screen.getByRole('listbox'),{key:'Escape'});
  post.mockResolvedValue({...review,source:{server_uid:'mariadb-native-uid'}});
  fireEvent.click(screen.getByRole('button',{name:'Review archive'}));await screen.findByLabelText('Native archive review');
  expect(post).toHaveBeenLastCalledWith({action:'mariadb_binlog_review',request:{options:{log_names:['native.1','native.2'],timeout_seconds:3600}}});
});
