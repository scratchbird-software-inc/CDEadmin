import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLHost from 'sources/Dialogs/MySQLHost';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLHost);
let originalHeight;
beforeEach(() => {originalHeight=window.innerHeight;window.innerHeight=1200;});
afterEach(() => {window.innerHeight=originalHeight;});
const review={job_id:'host-job',review_digest:'exact',state:'reviewed',warnings:['Native database host only'],source:{server_uuid:'native'},
  execution_host:{kind:'database-server-ssh-host',hostname:'database'},remote_observation:{},
  options:{connection:{host:'database',port:22,username:'operator',host_key:'expected',authentication:'password',platform:'posix',python:'python3'}}};

it('separates SSH secrets from review facts and requires exact native host confirmation',async () => {
  const post=jest.fn().mockResolvedValue(review);render(<Component post={post} />);
  fireEvent.change(screen.getByLabelText('SSH password'),{target:{value:'native-private-secret'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native host configuration check'}));
  await screen.findByLabelText('Native host diagnostic review');
  expect(screen.getByLabelText('Native host diagnostic review')).not.toHaveTextContent('native-private-secret');
  expect(screen.getByRole('button',{name:'Confirm native host configuration check'})).toBeDisabled();
  fireEvent.click(screen.getByLabelText('Authorize the reviewed native mysqld configuration check on this database SSH host'));
  post.mockResolvedValue({...review,state:'native_process_returned',remote_receipt:{result:{return_code:0}}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm native host configuration check'}));
  await screen.findByText(/Native host job host-job: native_process_returned/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_host_start',request:{job_id:'host-job',review_digest:'exact',confirmed:true,credentials:{password:'native-private-secret'}}});
  fireEvent.change(screen.getByLabelText('Native mysqld executable'),{target:{value:'/different/mysqld'}});
  expect(screen.queryByLabelText('Native host diagnostic review')).not.toBeInTheDocument();
});

it('loads an uncertain offline receipt and reconciles without issuing another native command',async () => {
  const post=jest.fn().mockResolvedValue({jobs:[{...review,state:'unknown'}],total:1,offset:0});render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native host receipts'}));
  await screen.findByRole('table',{name:'Native host diagnostic receipts'});
  post.mockResolvedValue({...review,state:'unknown'});fireEvent.click(screen.getByRole('button',{name:'Inspect native host job host-job'}));
  await screen.findByText(/original SSH reply is unconfirmed/);
  fireEvent.change(screen.getByLabelText('SSH password'),{target:{value:'renewed-native-secret'}});
  fireEvent.click(screen.getByRole('button',{name:'Reconcile native host receipt'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith({action:'mysql_host_reconcile',request:{job_id:'host-job',credentials:{password:'renewed-native-secret'}}}));
  expect(post.mock.calls.some(([value])=>value.action==='mysql_host_start')).toBe(false);
});

it.each(['changed','unreadable'])('keeps the native result and warns about %s configuration without replay',async outcome => {
  const receipt={...review,state:'native_process_returned',remote_receipt:{result:{return_code:0},
    configuration_after_process:{observed:outcome==='changed',matches_review:false}}};
  const post=jest.fn().mockResolvedValue({jobs:[receipt],total:1,offset:0});render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native host receipts'}));
  await screen.findByRole('table',{name:'Native host diagnostic receipts'});
  post.mockResolvedValue(receipt);fireEvent.click(screen.getByRole('button',{name:'Inspect native host job host-job'}));
  await screen.findByText(/Native host job host-job: native_process_returned/);
  expect(screen.getByText(outcome==='changed' ? /Configuration files changed after review/ : /Configuration files could not be observed/)).toBeVisible();
  expect(screen.getByText(/Native diagnostic output: exit 0/)).toBeInTheDocument();
  expect(post.mock.calls.some(([value])=>value.action==='mysql_host_start')).toBe(false);
});

it('reviews exact service controls and reuses a prior association for offline startup',async () => {
  const serviceOptions={...review.options,operation:'service_stop',service:{manager:'systemd',name:'mysql@owned.service'},
    executable:'/usr/sbin/mysqld',configuration_file:'/etc/owned.cnf',workspace:'/private/jobs',timeout_seconds:90};
  const post=jest.fn().mockResolvedValue({...review,options:serviceOptions});render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Native host operation'));
  fireEvent.click(await screen.findByRole('option',{name:'stop MySQL service (Linux systemd)'}));
  fireEvent.change(screen.getByLabelText('Exact systemd MySQL unit'),{target:{value:'mysql@owned.service'}});
  fireEvent.click(screen.getByLabelText('Disconnect all native service clients'));
  fireEvent.click(screen.getByRole('button',{name:'Review native host service action'}));
  await screen.findByLabelText('Native host diagnostic review');
  expect(post.mock.calls[0][0].request.options).toMatchObject({operation:'service_stop',service:{manager:'systemd',name:'mysql@owned.service'},disconnect_all_clients:true});
  fireEvent.click(screen.getByLabelText('Authorize the reviewed native MySQL service action on this database SSH host'));
  const finished={...review,options:serviceOptions,state:'native_process_returned',remote_receipt:{result:{return_code:0},service_request:{manager_client_completed:true}}};
  post.mockResolvedValue(finished);fireEvent.click(screen.getByRole('button',{name:'Confirm native host service action'}));
  await screen.findByText(/SQL readiness is unconfirmed/);
  expect(post.mock.calls.filter(([value])=>value.action==='mysql_host_start')).toHaveLength(1);
  post.mockResolvedValue({jobs:[finished],total:1,offset:0});fireEvent.click(screen.getByRole('button',{name:'Load native host receipts'}));
  await screen.findByRole('table',{name:'Native host diagnostic receipts'});
  post.mockResolvedValue(finished);fireEvent.click(screen.getByRole('button',{name:'Inspect native host job host-job'}));
  await waitFor(() => expect(screen.getByLabelText('Prior verified service job (for offline SQL)')).toHaveValue('host-job'));
  fireEvent.mouseDown(screen.getByLabelText('Native host operation'));
  fireEvent.click(await screen.findByRole('option',{name:'start MySQL service (Linux systemd)'}));
  fireEvent.click(screen.getByRole('button',{name:'Review native host service action'}));
  await waitFor(() => expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'mysql_host_review',request:expect.objectContaining({options:expect.objectContaining({operation:'service_start',binding_job_id:'host-job',service:{manager:'systemd',name:'mysql@owned.service'}})})})));
  expect(post.mock.calls.filter(([value])=>value.action==='mysql_host_start')).toHaveLength(1);
});
it('reviews exact uploaded native option-file bytes and dispatches only the resulting installation review',async()=> {
  const review={job_id:'install',review_digest:'exact-bytes',state:'reviewed',source:{server_uuid:'source'},execution_host:{hostname:'owned'},remote_observation:{configuration_deployment:{replacement_sha256:'reviewed-hash'}},warnings:[]};
  const post=jest.fn().mockResolvedValue(review);
  render(<Component post={post} />);
  fireEvent.change(screen.getByLabelText('Native configuration file (blank: no defaults)'),{target:{value:'/owned/my.cnf'}});
  fireEvent.mouseDown(screen.getByLabelText('Native host operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Install option file (Linux)'}));
  const data=new Uint8Array([91,109,121,115,113,108,100,93,10]);
  fireEvent.change(screen.getByLabelText('Replacement native option file'),{target:{files:[{name:'my.cnf',arrayBuffer:()=>Promise.resolve(data.buffer)}]}});
  await screen.findByText(/Selected file: my.cnf/);
  fireEvent.click(screen.getByRole('button',{name:'Review native option-file installation'}));
  await screen.findByLabelText('Native host diagnostic review');
  const request=post.mock.calls.at(-1)[0];expect(request.action).toBe('mysql_host_review');
  expect(request.request.options.operation).toBe('deploy_config');
  expect(request.request.options.configuration_replacement).toEqual({base64:'W215c3FsZF0K'});
  expect(request.request.options).not.toHaveProperty('service');
  fireEvent.click(screen.getByLabelText('Authorize the reviewed option-file installation on this database SSH host'));
  post.mockResolvedValue({...review,state:'native_process_returned',remote_receipt:{result:{return_code:0},configuration_deployment_result:{installed:true,restart_issued:false}}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm native option-file installation'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_host_start',request:{job_id:'install',review_digest:'exact-bytes',confirmed:true,credentials:{password:''}}}));
});

it('initializes without requesting a SQL binding and keeps original outcome separate from later writer termination',async()=> {
  const planned={...review,source:{kind:'authenticated_ssh_host',native_instance_identity:null},source_identity_scope:'authenticated_ssh_host_before_native_initialization',options:{...review.options,operation:'initialize_data',initialization:{datadir:'/owned/new',user:'mysql',secure:true}}};
  const post=jest.fn().mockResolvedValue(planned);render(<Component post={post} />);
  fireEvent.mouseDown(screen.getByLabelText('Native host operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Initialize MySQL data directory (Linux)'}));
  fireEvent.change(screen.getByLabelText('Native initialization data directory'),{target:{value:'/owned/new'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native data-directory initialization'}));
  await screen.findByLabelText('Native host diagnostic review');
  expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'mysql_host_review',request:expect.objectContaining({options:expect.objectContaining({operation:'initialize_data',initialization:{datadir:'/owned/new',user:'mysql',secure:true}})})}));
  expect(post.mock.calls.some(([value])=>value.action==='mysql_host_catalog')).toBe(false);
  fireEvent.click(screen.getByLabelText('Authorize the reviewed native data-directory initialization on this SSH host'));
  const unknown={...planned,state:'unknown',remote_receipt:{state:'native_dispatch'}};
  post.mockResolvedValue(unknown);fireEvent.click(screen.getByRole('button',{name:'Confirm native data-directory initialization'}));
  await screen.findByText(/Native host job host-job: unknown/);
  expect(screen.getByRole('button',{name:'Acknowledge ended initialization and release its directory claim'})).toBeDisabled();
  post.mockResolvedValue({...unknown,reconciliation:{remote_receipt:{state:'native_dispatch',initialization_reconciliation:{process_termination_confirmed:true,original_native_result_unchanged:true}}}});
  fireEvent.click(screen.getByRole('button',{name:'Cancel original native initializer'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_host_cancel_initialization',request:{job_id:'host-job',credentials:{password:''}}}));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Acknowledge ended initialization and release its directory claim'})).toBeEnabled());
  expect(screen.getByText(/Native initialization result: unconfirmed or unsuccessful/)).toBeVisible();
  fireEvent.click(screen.getByRole('button',{name:'Acknowledge ended initialization and release its directory claim'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_host_acknowledge_initialization',request:{job_id:'host-job',credentials:{password:''}}}));
  expect(post.mock.calls.filter(([value])=>value.action==='mysql_host_start')).toHaveLength(1);
});

it('uses a completed initializer for a separately reviewed native service installation',async()=> {
  const initialized={...review,state:'native_process_returned',options:{...review.options,operation:'initialize_data',initialization:{datadir:'/owned/new',user:'mysql',secure:true}},remote_receipt:{initialization_result:{native_initialization_returned:true}}};
  const post=jest.fn().mockResolvedValue({jobs:[initialized],total:1,offset:0});render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native host receipts'}));
  await screen.findByRole('table',{name:'Native host diagnostic receipts'});
  post.mockResolvedValue(initialized);fireEvent.click(screen.getByRole('button',{name:'Inspect native host job host-job'}));
  await screen.findByText(/Native host job host-job: native_process_returned/);
  fireEvent.mouseDown(screen.getByLabelText('Native host operation'));
  fireEvent.click(await screen.findByRole('option',{name:'Install new MySQL service (Linux systemd)'}));
  expect(screen.getByLabelText('Prior verified service job (for offline SQL)')).toHaveValue('host-job');
  fireEvent.change(screen.getByLabelText('Exact systemd MySQL unit'),{target:{value:'owned-new.service'}});
  const planned={...review,job_id:'install',options:{...review.options,operation:'install_service'},remote_observation:{service_installation:{automatic_start:false}}};
  post.mockResolvedValue(planned);fireEvent.click(screen.getByRole('button',{name:'Review native host service action'}));
  await screen.findByLabelText('Native host diagnostic review');
  expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'mysql_host_review',request:expect.objectContaining({options:expect.objectContaining({operation:'install_service',binding_job_id:'host-job',service:{manager:'systemd',name:'owned-new.service'},service_installation:{user:'mysql'}})})}));
  expect(post.mock.calls.at(-1)[0].request.options).not.toHaveProperty('initialization');
  fireEvent.click(screen.getByLabelText('Authorize the reviewed native MySQL service action on this database SSH host'));
  post.mockResolvedValue({...planned,state:'native_process_returned',remote_receipt:{result:{return_code:0},service_installation_result:{installed:true,restart_issued:false,enable_issued:false}}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm native host service action'}));
  await screen.findByText(/Native service unit installation: file installed/);
  expect(screen.getByText(/Installation does not start or enable MySQL/)).toBeVisible();
  expect(post.mock.calls.filter(([value])=>value.action==='mysql_host_start')).toHaveLength(1);
});
