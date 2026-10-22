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
it('imports file text without parsing native numbers in JavaScript and binds the selected guideline',async()=> {
  const methods={operations:[{id:'cluster.import_routing_guideline',context:'cluster',method:'import_routing_guideline',arguments:['document','options?'],read_only:false},
    {id:'cluster.guideline.rename',context:'cluster',method:'rename',arguments:['name'],guideline:true,read_only:false}]};
  const target={identity:{server_uuid:'seed'}};
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_topology_catalog' ? methods : action==='mysql_topology_inspect' ? target :
    {state:'reviewed',target:target.identity,warnings:[],options:{}}));
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native topology methods'}));await screen.findByLabelText('Native topology method');
  fireEvent.mouseDown(screen.getByLabelText('Native topology method'));fireEvent.click(await screen.findByRole('option',{name:'cluster.import_routing_guideline'}));
  const text='{ "name":"routes", "wide":9223372036854775808 }';
  const bytes=new TextEncoder().encode(text);
  fireEvent.change(screen.getByLabelText('Routing guideline JSON file'),{target:{files:[{size:bytes.length,arrayBuffer:()=>Promise.resolve(bytes.buffer)}]}});
  await waitFor(()=>expect(screen.getByLabelText('Native topology arguments (JSON array)').value).toBe('['+text+',{}]'));
  fireEvent.click(screen.getByRole('button',{name:'Inspect topology seed'}));await screen.findByLabelText('Native topology seed');
  fireEvent.change(screen.getByLabelText('Confirm topology seed UUID'),{target:{value:'seed'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native topology change'}));await screen.findByLabelText('Native topology review');
  expect(post.mock.calls.at(-1)[0].request.options.arguments_json).toBe('['+text+',{}]');
  fireEvent.mouseDown(screen.getByLabelText('Native topology method'));fireEvent.click(await screen.findByRole('option',{name:'cluster.guideline.rename'}));
  fireEvent.change(screen.getByLabelText('Native routing guideline name (empty selects active guideline)'),{target:{value:'old_routes'}});
  fireEvent.change(screen.getByLabelText('Native topology arguments (JSON array)'),{target:{value:'["new_routes"]'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native topology change'}));
  await waitFor(()=>expect(post.mock.calls.at(-1)[0].request.options.guideline_name).toBe('old_routes'));
});
it('rejects invalid UTF-8 file bytes without replacing characters or dispatching a native import',async()=> {
  const methods={operations:[...catalog.operations,{id:'cluster.import_routing_guideline',context:'cluster',method:'import_routing_guideline',arguments:['document','options?'],read_only:false}]};
  const post=jest.fn(()=>Promise.resolve(methods));
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load native topology methods'}));await screen.findByLabelText('Native topology method');
  fireEvent.mouseDown(screen.getByLabelText('Native topology method'));fireEvent.click(await screen.findByRole('option',{name:'cluster.import_routing_guideline'}));
  const original=screen.getByLabelText('Native topology arguments (JSON array)').value;
  fireEvent.change(screen.getByLabelText('Routing guideline JSON file'),{target:{files:[{size:1,arrayBuffer:()=>Promise.resolve(new Uint8Array([255]).buffer)}]}});
  await screen.findByText(/must contain valid UTF-8/);
  expect(screen.getByLabelText('Native topology arguments (JSON array)').value).toBe(original);
  expect(post.mock.calls.some(([value])=>value.action!=='mysql_topology_catalog')).toBe(false);
});
it('downloads native exported JSON text with its original whitespace and exact integer digits',async()=> {
  const text='{ "name": "routes", "wide": 9223372036854775808, "enabled": true }\n';
  const receipt={job_id:'export',state:'operation_returned',native_operation_outcome:'returned',
    options:{operation:'cluster.guideline.export'},result:{control:{result_json:JSON.stringify({guideline_export_json:text,guideline_export_redacted:false})}}};
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_topology_list' ? {jobs:[receipt],offset:0,limit:25,total:1} : receipt));
  const originalCreate=URL.createObjectURL,originalRevoke=URL.revokeObjectURL;
  URL.createObjectURL=jest.fn(()=> 'blob:owned');URL.revokeObjectURL=jest.fn();
  const click=jest.spyOn(HTMLAnchorElement.prototype,'click').mockImplementation(()=>{});
  try {
    render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load native topology jobs'}));
    fireEvent.click(await screen.findByRole('button',{name:'Inspect topology job export'}));
    fireEvent.click(await screen.findByRole('button',{name:'Download native routing guideline JSON'}));
    const blob=URL.createObjectURL.mock.calls[0][0];
    const actual=await new Promise(resolve=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.readAsText(blob);});
    expect(actual).toBe(text);expect(click).toHaveBeenCalledTimes(1);expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:owned');
    expect(screen.queryByText(/downloaded JSON is a redacted copy/)).not.toBeInTheDocument();
  } finally {click.mockRestore();URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke;}
});
it('keeps account passwords out of reviews and supplies them once at explicit dispatch',async()=> {
  const methods={operations:[...catalog.operations,{id:'cluster.setup_admin_account',context:'cluster',method:'setup_admin_account',
    arguments:['account','options?'],account:true,read_only:false}]};
  const target={identity:{server_uuid:'seed'}};
  const review={job_id:'account-job',review_digest:'bound',state:'reviewed',warnings:[],target:target.identity,
    options:{operation:'cluster.setup_admin_account',account_password_mode:'set'}};
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_topology_catalog' ? methods : action==='mysql_topology_inspect' ? target :
    action==='mysql_topology_review' ? review : {...review,state:'operation_returned',native_operation_outcome:'returned'}));
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native topology methods'}));await screen.findByLabelText('Native topology method');
  fireEvent.mouseDown(screen.getByLabelText('Native topology method'));fireEvent.click(await screen.findByRole('option',{name:'cluster.setup_admin_account'}));
  fireEvent.click(screen.getByRole('button',{name:'Inspect topology seed'}));await screen.findByLabelText('Native topology seed');
  fireEvent.change(screen.getByLabelText('Native topology arguments (JSON array)'),{target:{value:'[{"user":"admin","host":"%"}]'}});
  fireEvent.click(screen.getByRole('checkbox',{name:'Set account password at dispatch'}));
  fireEvent.change(screen.getByLabelText('Native account password'),{target:{value:'private-native-雪'}});
  fireEvent.change(screen.getByLabelText('Confirm topology seed UUID'),{target:{value:'seed'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native topology change'}));await screen.findByLabelText('Native topology review');
  expect(post.mock.calls.at(-1)[0].request.options.account_password_mode).toBe('set');
  expect(JSON.stringify(post.mock.calls.at(-1)[0])).not.toContain('private-native-雪');
  expect(screen.getByLabelText('Native topology review').textContent).not.toContain('private-native-雪');
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start native topology change'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_topology_start',request:{job_id:'account-job',review_digest:'bound',confirmed:true,
    account_secret:{password:'private-native-雪'}}}));
  await waitFor(()=>expect(screen.getByLabelText('Native account password').value).toBe(''));
});
