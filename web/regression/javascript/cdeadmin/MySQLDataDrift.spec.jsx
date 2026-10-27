import {act,fireEvent,render,screen,waitFor} from '@testing-library/react';
import DataDrift from 'sources/Dialogs/MySQLDataDrift';
import {withTheme} from '../fake_theme';
const Component=withTheme(DataDrift);
const height=window.innerHeight;
beforeAll(() => {window.innerHeight=1800;});
afterAll(() => {window.innerHeight=height;});
const observed={server_uuid:'native',engine:'InnoDB',key:['id'],column_count:2,fingerprint:'a'.repeat(64)};
const report={job_id:'private',state:'completed',stage:'terminal',terminal:true,coverage:[{source_table:'t',target_table:'t',state:'different',
  source_rows:'9007199254740993',target_rows:'9007199254740993',source_only_rows:'2',target_only_rows:'2',examples:[],examples_truncated:true}],positions:[],release:[],identities:[],cancellation:{},repair_dispatched:false};

async function choosePeer() {
  fireEvent.click(screen.getByRole('button',{name:'Discover registered comparison endpoints'}));
  await waitFor(() => expect(screen.getByRole('combobox',{name:'Comparison target endpoint'})).toBeEnabled());
  fireEvent.mouseDown(screen.getByRole('combobox',{name:'Comparison target endpoint'}));
  fireEvent.click(await screen.findByRole('option',{name:'Owned peer'}));
}
async function selectPair() {
  await choosePeer();
  for(const side of ['Source','Target']) {
    fireEvent.change(screen.getByLabelText(`${side} comparison database`),{target:{value:'db'}});
    fireEvent.change(screen.getByRole('textbox',{name:`${side} complete table`}),{target:{value:'t'}});
  }
  fireEvent.click(screen.getByRole('button',{name:'Observe source table'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Observe target table'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Observe target table'}));
  await waitFor(() => expect(screen.getByRole('button',{name:'Add complete table pair'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Add complete table pair'}));
}
function respond(start=report) {
  return jest.fn().mockImplementation(({action}) => Promise.resolve(action==='mysql_drift_peers' ? {rows:[{endpoint_id:2,label:'Owned peer'}],next_offset:null} :
    action==='mysql_drift_describe' ? observed : action==='mysql_drift_start' ? start : {...start,terminal:true,state:'cancelled'}));
}

it('requires complete observed pairs and explicit lock consent, then binds both scopes',async () => {
  const post=respond();render(<Component post={post} databaseTargetId="registered-source" />);
  expect(post).not.toHaveBeenCalled();await selectPair();
  expect(screen.getByRole('button',{name:'Start full native comparison'})).toBeDisabled();
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow native server read locks and complete private table scans'}));
  fireEvent.click(screen.getByRole('button',{name:'Start full native comparison'}));
  await screen.findByText(/Comparison: completed/);
  expect(post).toHaveBeenCalledWith({action:'mysql_drift_start',request:expect.objectContaining({database_target_id:'registered-source',peer_endpoint_id:2,
    source_schema:'db',target_schema:'db',confirmed:true,tables:[{source_table:'t',target_table:'t',source_fingerprint:observed.fingerprint,target_fingerprint:observed.fingerprint}]})});
  expect(screen.getByText(/9007199254740993/)).toBeVisible();expect(screen.getByText(/total mismatch counts cover the full completed scans/)).toBeVisible();
});

it('preserves incomplete coverage and issues only an owned cancellation',async () => {
  const post=respond({...report,state:'running',terminal:false,coverage:[{source_table:'t',target_table:'t',state:'uncompared'}]});
  render(<Component post={post} />);await selectPair();
  fireEvent.click(screen.getByRole('checkbox',{name:'Allow native server read locks and complete private table scans'}));
  fireEvent.click(screen.getByRole('button',{name:'Start full native comparison'}));await screen.findByText(/Comparison: running/);
  fireEvent.click(screen.getByRole('button',{name:'Cancel native comparison'}));await screen.findByText(/Comparison: cancelled/);
  expect(post).toHaveBeenCalledWith({action:'mysql_drift_cancel',request:{database_target_id:null,peer_endpoint_id:2,job_id:'private'}});
  expect(screen.getByRole('button',{name:'Start full native comparison'})).toBeDisabled();
});

it('drops late private observations after source target replacement',async () => {
  let reply;const base=respond(),post=jest.fn().mockImplementation(request => request.action==='mysql_drift_describe' ? new Promise(resolve => {reply=resolve;}) : base(request));
  const mounted=render(<Component post={post} databaseTargetId="first" />);await choosePeer();
  fireEvent.change(screen.getByLabelText('Source comparison database'),{target:{value:'db'}});
  fireEvent.change(screen.getByRole('textbox',{name:'Source complete table'}),{target:{value:'t'}});
  fireEvent.click(screen.getByRole('button',{name:'Observe source table'}));
  mounted.rerender(<Component post={post} databaseTargetId="second" />);
  await act(async () => {reply(observed);});
  expect(screen.queryByText(/native: InnoDB/)).not.toBeInTheDocument();expect(screen.getByRole('button',{name:'Add complete table pair'})).toBeDisabled();
});
