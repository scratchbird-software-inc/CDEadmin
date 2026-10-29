import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {PostgresqlDataCapture} from 'sources/Dialogs/PostgresqlCatalog';
import {withTheme} from '../fake_theme';
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: () => <div>Captured data viewer</div>, DDNDesignerSurface: () => null,
}));
const Component=withTheme(PostgresqlDataCapture);
const objects=[{resource_id:'postgresql:pg_class:81',kind:'table',path:['db','public','orders']},
  {resource_id:'postgresql:pg_proc:90',kind:'function',path:['db','public','orders']}];
const response={snapshot:{format:'ddn-source-workspace@1',entry:'result-1.ddn',view:'result_1',files:{}},
  views:[{entry:'result-1.ddn',id:'result_1',label:'Data page 1'}],
  coverage:{schema:'public',name:'orders',rows:2,selection_complete:false}};
const select=(label,value)=>fireEvent.change(screen.getByRole('combobox',{name:label}).parentElement.querySelector('input'),{target:{value}});
it('performs no implicit data read and binds an explicit selection to the database',async()=>{
  const post=jest.fn().mockResolvedValue(response);
  render(<Component post={post} objects={objects} databaseTargetId="postgresql-database:42" />);
  fireEvent.click(screen.getByText('Selected relation data'));
  expect(post).not.toHaveBeenCalled();
  expect(screen.getByRole('button',{name:'Capture selected data'})).toBeDisabled();
  select('Data relation','postgresql:pg_class:81');
  select('Data capture mode','full');
  fireEvent.change(screen.getByRole('spinbutton',{name:'Data row budget'}),{target:{value:'2'}});
  fireEvent.click(screen.getByRole('button',{name:'Capture selected data'}));
  await screen.findByText('Captured data viewer');
  expect(post).toHaveBeenCalledWith({action:'postgresql_data_capture',request:{database_target_id:'postgresql-database:42',resource_id:'postgresql:pg_class:81',mode:'full',row_limit:2}});
  expect(screen.getByText(/Partial selection: row budget reached/)).toBeInTheDocument();
});
it('rejects invalid row budgets and discards a prior result when a new read fails',async()=>{
  const post=jest.fn().mockResolvedValue(response);
  render(<Component post={post} objects={objects} databaseTargetId="postgresql-database:42" />);
  fireEvent.click(screen.getByText('Selected relation data'));
  select('Data relation','postgresql:pg_class:81');
  fireEvent.change(screen.getByRole('spinbutton',{name:'Data row budget'}),{target:{value:'6001'}});
  expect(screen.getByRole('button',{name:'Capture selected data'})).toBeDisabled();
  fireEvent.change(screen.getByRole('spinbutton',{name:'Data row budget'}),{target:{value:'100'}});
  fireEvent.click(screen.getByRole('button',{name:'Capture selected data'}));
  await screen.findByText('Captured data viewer');
  post.mockRejectedValue(new Error('Native read denied'));
  await waitFor(()=>expect(screen.getByRole('button',{name:'Capture selected data'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button',{name:'Capture selected data'}));
  await screen.findByText('Native read denied');
  expect(screen.queryByText('Captured data viewer')).not.toBeInTheDocument();
});
