import {fireEvent,render,screen,waitFor} from '@testing-library/react';
import MySQLSandboxes from 'sources/Dialogs/MySQLSandboxes';
import {withTheme} from '../fake_theme';

const Component=withTheme(MySQLSandboxes);
const catalog={version:'9.7.0',methods:{deploy:'deploy_sandbox_instance',stop:'stop_sandbox_instance',delete:'delete_sandbox_instance'},
  sandbox_directories:['/host/sandboxes'],deploy_options:['portx','mysqldOptions'],execution_scope:'ScratchRobin application execution host'};
const review={job_id:'job',review_digest:'bound',state:'reviewed',sandbox:{port:3310},warnings:[],options:{operation:'deploy'}};
it('reviews offline execution-host options and supplies the password only at explicit dispatch',async()=> {
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_sandbox_catalog' ? catalog : action==='mysql_sandbox_review' ? review :
    {...review,state:'operation_returned',native_operation_outcome:'returned'}));
  render(<Component post={post} />);
  fireEvent.click(screen.getByRole('button',{name:'Load native sandbox capabilities'}));await screen.findByLabelText('Native sandbox method');
  fireEvent.change(screen.getByLabelText('Native sandbox deployment options (JSON object)'),{target:{value:'{"portx":33101,"mysqldOptions":["max_connections=47"]}'}});
  fireEvent.click(screen.getByRole('button',{name:'Review native sandbox operation'}));await screen.findByLabelText('Native sandbox review');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_sandbox_review',request:{options:{operation:'deploy',port:3310,
    sandbox_directory:'/host/sandboxes',native_options:{portx:33101,mysqldOptions:['max_connections=47']},timeout_seconds:300}}});
  expect(post.mock.calls.some(([value])=>value.action==='mysql_sandbox_start')).toBe(false);
  fireEvent.change(screen.getByLabelText('Sandbox native root password'),{target:{value:'private-password'}});
  fireEvent.change(screen.getByLabelText('Confirm reviewed sandbox port'),{target:{value:'3310'}});
  fireEvent.click(screen.getByRole('button',{name:'Confirm and start native sandbox operation'}));
  await screen.findByLabelText('Native sandbox receipt');
  expect(post).toHaveBeenLastCalledWith({action:'mysql_sandbox_start',request:{job_id:'job',review_digest:'bound',confirmed:true,sandbox_secret:{password:'private-password'}}});
  expect(screen.getByLabelText('Sandbox native root password')).toHaveValue('');
  expect(screen.getByText(/SQL readiness is unverified/)).toBeInTheDocument();
});
it('invalidates a review when its host identity inputs change',async()=> {
  const post=jest.fn(({action})=>Promise.resolve(action==='mysql_sandbox_catalog' ? catalog : review));
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load native sandbox capabilities'}));
  await screen.findByLabelText('Native sandbox method');fireEvent.click(screen.getByRole('button',{name:'Review native sandbox operation'}));
  await screen.findByLabelText('Native sandbox review');fireEvent.change(screen.getByLabelText('Sandbox classic protocol port'),{target:{value:'3311'}});
  expect(screen.queryByLabelText('Native sandbox review')).not.toBeInTheDocument();
});
it('acknowledges observed uncertainty without changing the original native outcome',async()=> {
  const receipt={...review,state:'unknown',native_operation_outcome:'unknown',native_process_termination_confirmed:true};
  const observed={...receipt,observation_digest:'state',reconciliation:{state:{process:{qualified:true}}}};
  const values={list:{jobs:[receipt],offset:0,limit:25,total:1},status:receipt,reconcile:observed,acknowledge:{...observed,target_state_acknowledged_at:1}};
  const post=jest.fn(({action})=>Promise.resolve(values[action.replace('mysql_sandbox_','')]));
  render(<Component post={post} />);fireEvent.click(screen.getByRole('button',{name:'Load native sandbox jobs'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect sandbox job job'}));
  fireEvent.click(await screen.findByRole('button',{name:'Observe current sandbox state'}));
  fireEvent.change(await screen.findByLabelText('Confirm uncertain sandbox port'),{target:{value:'3310'}});
  fireEvent.click(screen.getByRole('button',{name:'Acknowledge observed sandbox state'}));
  await waitFor(()=>expect(post).toHaveBeenLastCalledWith({action:'mysql_sandbox_acknowledge',request:{job_id:'job',observation_digest:'state',sandbox_confirmation:'3310'}}));
  await screen.findByText('Observed sandbox state acknowledged. The original uncertain outcome is unchanged.');
});
