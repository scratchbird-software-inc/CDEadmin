import {act, fireEvent, render, screen} from '@testing-library/react';
import SessionCatalog from 'sources/cdeadmin_ui/editors/SessionCatalog';
import {withTheme} from '../fake_theme';
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({DDNViewerSurface: () => <div>Session DDN viewer</div>}));
const Component = withTheme(SessionCatalog);
const catalog = {resources:[{resource_id:'temp',resource_kind:'table',display_name:'Quoted ü',display_path:['db','pg_temp_3','Quoted ü'],
  native:{session_local:true,children:{pg_attribute:[{attname:'Exact column'}]}}}],
observations:[{section:'pg_subscription',available:false}],
document:{snapshot:{format:'ddn-source-workspace@1',entry:'catalog.ddn',view:'inventory_1',files:{'catalog.ddn':'native source'}},
  views:[{id:'inventory_1',label:'Inventory'}]}};

describe('Retained-session native catalog', () => {
  it('captures explicitly on the retained session and inspects native facts and denials', async () => {
    const post = jest.fn().mockResolvedValue(catalog), ensureSession = jest.fn().mockResolvedValue('retained-session');
    render(<Component post={post} ensureSession={ensureSession} databaseTargetId="db-one" />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name:'Refresh session catalog'}));
    fireEvent.click(await screen.findByRole('button', {name:'Inspect session object Quoted ü'}));
    expect(post).toHaveBeenCalledWith({action:'source_catalog',session_id:'retained-session',database_target_id:'db-one',include_system:false});
    expect(screen.getByLabelText('PostgreSQL session object properties')).toHaveTextContent('Exact column');
    expect(screen.getByText('Unavailable sections: pg_subscription')).toBeInTheDocument();
    expect(screen.getByRole('button', {name:'Download session DDN'})).toBeEnabled();
  });
  it('discards in-flight results after a target change', async () => {
    let finish;
    const post = jest.fn(() => new Promise(resolve => {finish=resolve;})), ensureSession=jest.fn().mockResolvedValue('retained');
    const mounted = render(<Component post={post} ensureSession={ensureSession} databaseTargetId="before" />);
    fireEvent.click(screen.getByRole('button', {name:'Refresh session catalog'}));
    await act(async () => {});
    mounted.rerender(<Component post={post} ensureSession={ensureSession} databaseTargetId="after" />);
    await act(async () => finish(catalog));
    expect(screen.queryByText('Temporary')).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name:'Refresh session catalog'})).toBeEnabled();
  });
  it('does not dispatch after session creation if the editor becomes busy', async () => {
    let finish;
    const ensureSession=jest.fn(() => new Promise(resolve => {finish=resolve;})), post=jest.fn();
    const mounted=render(<Component post={post} ensureSession={ensureSession} />);
    fireEvent.click(screen.getByRole('button', {name:'Refresh session catalog'}));
    mounted.rerender(<Component post={post} ensureSession={ensureSession} disabled />);
    await act(async () => finish('old-session'));
    expect(post).not.toHaveBeenCalled();
  });
});

it.each([['duckdb','DuckDB'],['sqlite','SQLite']])('shows %s session-native facts without a PostgreSQL label',async (engine,label) => {
  const post=jest.fn().mockResolvedValue({...catalog,resources:[{resource_id:'wide',resource_kind:'sequence',display_name:'Exact sequence',
    display_path:['native','main','Exact sequence'],native:{session_scope_kind:'connection',catalog_metadata:{start_value:'9007199254740993'}}}]});
  render(<Component engine={engine} post={post} ensureSession={jest.fn().mockResolvedValue('retained')} />);
  fireEvent.click(screen.getByRole('button',{name:'Refresh session catalog'}));
  fireEvent.click(await screen.findByRole('button',{name:'Inspect session object Exact sequence'}));
  expect(screen.getByRole('table',{name:label+' session objects'})).toBeInTheDocument();
  expect(screen.getByLabelText(label+' session object properties')).toHaveTextContent('9007199254740993');
  expect(screen.getByText('Connection')).toBeInTheDocument();
});
