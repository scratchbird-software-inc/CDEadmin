import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLTopologies from 'sources/Dialogs/MySQLTopologies';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLTopologies);
const viewportHeight=window.innerHeight;
beforeAll(()=>{window.innerHeight=1200;});
afterAll(()=>{window.innerHeight=viewportHeight;});
const catalog={operations:[
  {id:'instance.check_configuration',context:'instance',method:'check_instance_configuration',arguments:['options?'],read_only:true},
  {id:'cluster.set_option',context:'cluster',method:'set_option',arguments:['option','value'],read_only:false},
]};
it('preserves raw native integer arguments and explicitly reviews and starts a topology change',async()=> {
  const target={identity:{server_uuid:'seed'}},review={job_id:'job',review_digest:'bound',state:'reviewed',target:target.identity,warnings:[]};
  const values={catalog,inspect:target,review,start:{...review,state:'operation_returned',native_operation_outcome:'returned',
    result:{control:{result_json:'{"wide":9223372036854775807,"enabled":true}'},
      native_json_observation:{native_shell_json_signed_limit:true,tags:[{tags_json:'{"wide":9223372036854775808,"enabled":true}'}]}}}};
  const post=jest.fn(({action})=>Promise.resolve(values[action.replace('mysql_topology_','')]));
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native topology methods'}));await screen.findByLabelText('Native topology method');
  fireEvent.mouseDown(screen.getByLabelText('Native topology method'));fireEvent.click(await screen.findByRole('option',{name:'cluster.set_option'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect topology seed'}));await screen.findByLabelText('Native topology seed');
  fireEvent.change(screen.getByLabelText('Native topology arguments (JSON array)'),{target:{value:'["tag:wide",9223372036854775808]'}});
  fireEvent.change(screen.getByLabelText('Confirm topology seed UUID'),{target:{value:'seed'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native topology change'}));await screen.findByLabelText('Native topology review');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_topology_review',request:{options:{operation:'cluster.set_option',
    arguments_json:'["tag:wide",9223372036854775808]',context_name:'',context_options_json:'{}',use_advertised_endpoint:false,witness_server_ids:[],timeout_seconds:3600,target_confirmation:'seed'}}});
  expect(post.mock.calls.some(([value])=>value.action==='mysql_topology_start')).toBe(false);
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start native topology change'}));
  await screen.findByLabelText('Native topology result JSON');
  expect(screen.getByLabelText('Native topology result JSON').textContent).toBe('{"wide":9223372036854775807,"enabled":true}');
  expect(screen.getByLabelText('Native topology stored tag JSON').textContent).toContain('9223372036854775808');
  expect(screen.getByText(/options decoding can clamp/)).toBeInTheDocument();
  expect(post).toHaveBeenLastCalledWith({action:'mysql_topology_start',request:{job_id:'job',review_digest:'bound',confirmed:true}});
});
it('runs a native inspection without a mutation confirmation or automatic mutation call',async()=> {
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_topology_catalog' ? catalog : action==='mysql_topology_inspect' ? {identity:{server_uuid:'seed'}} :
    {job_id:'read',state:'operation_returned',native_operation_outcome:'returned',remote_database_mutation:false,target:{server_uuid:'seed'}}));
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load native topology methods'}));await screen.findByLabelText('Native topology method');
  fireEvent.click(screen.getByRole('button',{name:'Inspect topology seed'}));await screen.findByLabelText('Native topology seed');
  expect(screen.queryByLabelText('Confirm topology seed UUID')).not.toBeInTheDocument();
  fireEvent.click(screen.getByRole('button',{name:'Run native topology inspection'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_topology_inspect_native',request:{options:{operation:'instance.check_configuration',
    arguments_json:'[{}]',context_name:'',context_options_json:'{}',use_advertised_endpoint:false,witness_server_ids:[],timeout_seconds:3600,target_confirmation:'seed'}}}));
  expect(post.mock.calls.some(([value])=>['mysql_topology_review','mysql_topology_start'].includes(value.action))).toBe(false);
});
it('retains explicitly selected recovery observation registrations in the native request',async()=> {
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_topology_catalog' ? catalog : action==='mysql_topology_members' ?
    {instances:[{server_id:4,name:'peer'}],total:1,offset:0,limit:25} : action==='mysql_topology_inspect' ? {identity:{server_uuid:'seed'}} :
      {job_id:'read',state:'operation_returned',native_operation_outcome:'returned',remote_database_mutation:false}));
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native topology methods'}));await screen.findByLabelText('Native topology method');
  fireEvent.click(screen.getByRole('button',{name:'Load registered topology instances'}));
  fireEvent.click(await screen.findByRole('checkbox',{name:'Observe recovery member peer'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect topology seed'}));await screen.findByLabelText('Native topology seed');
  fireEvent.click(screen.getByRole('button',{name:'Run native topology inspection'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_topology_inspect_native',request:{options:{operation:'instance.check_configuration',
    arguments_json:'[{}]',context_name:'',context_options_json:'{}',use_advertised_endpoint:false,witness_server_ids:[4],timeout_seconds:3600,target_confirmation:'seed'}}}));
});
it('shows recovery clearance and acknowledges the observed target without rewriting an unknown outcome',async()=> {
  const receipt={job_id:'uncertain',options:{operation:'cluster.add_instance'},state:'unknown',native_operation_outcome:'unknown',
    remote_database_mutation:true,server_recovery_clearance_required:true,target:{server_uuid:'seed'}};
  const observed={...receipt,observation_digest:'observed',reconciliation:{server_recovery_quiescence:{qualified:true,idle:true,
    targets:{seed:{qualified:true,idle:true}}}}};
  const values={list:{jobs:[receipt],offset:0,limit:25,total:1},status:receipt,reconcile:observed,
    acknowledge:{...observed,target_state_acknowledged_at:1,server_recovery_clearance_required:false}};
  const post=jest.fn(({action})=>Promise.resolve(values[action.replace('mysql_topology_','')]));
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load native topology jobs'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect topology job uncertain'}));
  fireEvent.click(await screen.findByRole('button',{name:'Observe current topology target'}));
  await screen.findByLabelText('Native recovery member observations');
  fireEvent.change(screen.getByLabelText('Confirm uncertain topology target UUID'),{target:{value:'seed'}});
  fireEvent.click(screen.getByRole('button',{name:'Acknowledge observed topology target'}));
  await screen.findByText('Observed target state acknowledged. The original operation outcome remains unknown.');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_topology_acknowledge',request:{job_id:'uncertain',target_confirmation:'seed',observation_digest:'observed'}});
});
