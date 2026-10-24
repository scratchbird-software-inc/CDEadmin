import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLRouters from 'sources/Dialogs/MySQLRouters';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLRouters);
const options={connection:{host:'router',port:22,username:'operator',host_key:'expected',authentication:'password',platform:'posix',python:'python3'},
  executable:'/usr/bin/mysqlrouter',directory:'/opt/native-router',user:'router',base_port:6446,bind_address:'127.0.0.1',
  seed:{host:'metadata',port:3306,user:'bootstrap',ssl_mode:'REQUIRED',ssl_ca:null,ssl_cert:null,ssl_key:null},extra_arguments:[],workspace:'/private/receipts',timeout_seconds:120};
const reviewed={job_id:'original',review_digest:'exact',state:'reviewed',warnings:['Native bootstrap is separate from routed SQL readiness'],source:{server_uuid:'native'},execution_host:{hostname:'separate-router'},remote_observation:{},options};

it('requires the reviewed native request and keeps explicit SSH/bootstrap credentials out of visible facts',async()=>{
  const post=jest.fn().mockResolvedValue(reviewed);render(<Component post={post} />);
  fireEvent.change(screen.getByLabelText('Router SSH password'),{target:{value:'private-ssh'}});
  fireEvent.click(screen.getByLabelText('Use separate bootstrap account password'));
  fireEvent.change(screen.getByLabelText('Private bootstrap database password'),{target:{value:'private-database'}});
  const argumentsField=screen.getByLabelText('Additional native bootstrap arguments (one per line)');
  fireEvent.change(argumentsField,{target:{value:'--name=owned\n'}});expect(argumentsField).toHaveValue('--name=owned\n');
  fireEvent.change(argumentsField,{target:{value:'--name=owned\n--conf-skip-x-protocol'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native Router request'}));
  const review=await screen.findByLabelText('Native Router review');expect(review).not.toHaveTextContent('private-ssh');expect(review).not.toHaveTextContent('private-database');
  expect(screen.getByRole('button',{name:'Confirm native Router request'})).toBeDisabled();
  expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'mysql_router_review',request:expect.objectContaining({credentials:{password:'private-ssh'},bootstrap_secret:{password:'private-database'}})}));
  expect(post.mock.calls.at(-1)[0].request.options.extra_arguments).toEqual(['--name=owned','--conf-skip-x-protocol']);
  fireEvent.click(screen.getByLabelText('Authorize the exact reviewed native Router request'));
  post.mockResolvedValue({...reviewed,state:'native_process_returned',ssh_reply_observed:true,remote_receipt:{result:{return_code:0}}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm native Router request'}));
  await screen.findByText(/Native Router job original: native_process_returned/);
  expect(post).toHaveBeenLastCalledWith({action:'mysql_router_start',request:{job_id:'original',review_digest:'exact',confirmed:true,credentials:{password:'private-ssh'},bootstrap_secret:{password:'private-database'}}});
  expect(screen.getByLabelText('Router SSH password')).toHaveValue('');expect(screen.getByLabelText('Private bootstrap database password')).toHaveValue('');
});

it('loads original offline receipts and reviews service controls without requesting SQL catalog access',async()=>{
  const completed={...reviewed,state:'native_process_returned'};
  const post=jest.fn().mockResolvedValue({jobs:[completed],offset:0,total:1});render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load Router receipts'}));await screen.findByRole('table',{name:'Native Router receipts'});
  post.mockResolvedValue(completed);fireEvent.click(screen.getByRole('button',{name:'Inspect Router job original'}));
  await waitFor(()=>expect(screen.getByLabelText('Original Router deployment or service job')).toHaveValue('original'));
  fireEvent.change(screen.getByLabelText('Exact Router systemd unit'),{target:{value:'native-owned.service'}});
  post.mockResolvedValue({...reviewed,options:{...options,operation:'install_service'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native Router request'}));
  await screen.findByLabelText('Native Router review');
  expect(post).toHaveBeenLastCalledWith(expect.objectContaining({action:'mysql_router_review',request:expect.objectContaining({options:{...options,operation:'install_service',binding_job_id:'original',service:{manager:'systemd',name:'native-owned.service'},disconnect_all_clients:false}})}));
  expect(post.mock.calls.some(([value])=>value.action==='mysql_router_catalog')).toBe(false);
});

it('preserves an unknown original result when inspecting ended native commands and never repeats it',async()=>{
  const unknown={...reviewed,state:'unknown',options:{...options,operation:'service_stop',service:{manager:'systemd',name:'native.service'}},ssh_reply_observed:false};
  const post=jest.fn().mockResolvedValue({jobs:[unknown],offset:0,total:1});render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load Router receipts'}));await screen.findByRole('table',{name:'Native Router receipts'});
  post.mockResolvedValue(unknown);fireEvent.click(screen.getByRole('button',{name:'Inspect Router job original'}));await screen.findByText(/Original SSH acknowledgement: unconfirmed/);
  fireEvent.change(screen.getByLabelText('Router SSH password'),{target:{value:'renewed-host-secret'}});
  post.mockResolvedValue({...unknown,reconciliation:{remote_receipt:{native_command_observations:[{cleanup_confirmed:true}]}}});
  fireEvent.click(screen.getByRole('button',{name:'Inspect original Router invocation'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_router_reconcile',request:{job_id:'original',credentials:{password:'renewed-host-secret'}}}));
  expect(screen.getByText(/Native Router job original: unknown/)).toBeVisible();
  expect(post.mock.calls.some(([value])=>value.action==='mysql_router_start')).toBe(false);
  expect(screen.queryByRole('button',{name:'Cancel original Router bootstrap'})).not.toBeInTheDocument();
});
