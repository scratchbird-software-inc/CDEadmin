import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import PostgresqlServerCatalog from 'sources/Dialogs/PostgresqlServerCatalog';
import {withTheme} from '../fake_theme';
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({DDNViewerSurface: () => <div>Server DDN viewer</div>}));
const Component = withTheme(PostgresqlServerCatalog);
const snapshot = {format: 'ddn-source-workspace@1', entry: 'catalog.ddn', view: 'inventory_1', files: {'catalog.ddn': 'native source'}};
const document = {snapshot, views: [{id: 'inventory_1', label: 'Inventory'}], provenance: {warnings: ['No password hashes']}};

describe('PostgreSQL server DDN capture', () => {
  it('inspects and downloads server metadata without selecting databases, preserving denied sections', async () => {
    const post = jest.fn().mockResolvedValue({document, databases: [], coverage: {state:'partial', unavailable_sections:['authentication-rules']},
      resources:[{resource_id:'postgresql:pg_roles:42',resource_kind:'role',display_name:'Native reader',display_path:['1','roles','Native reader'],
        native:{native_identity:'42',catalog_row:{rolcanlogin:true}}}]});
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button', {name:'Load server inventory'}));
    fireEvent.click(await screen.findByRole('button', {name:'Inspect PostgreSQL role Native reader'}));
    expect(screen.getByLabelText('PostgreSQL native server object properties')).toHaveTextContent('rolcanlogin');
    expect(screen.getByText('Unavailable native sections: authentication-rules')).toBeInTheDocument();
    expect(screen.getByText('Server catalog captured.')).toBeInTheDocument();
    expect(screen.getByRole('button', {name:'Download server DDN bundle'})).toBeEnabled();
    expect(post).toHaveBeenCalledTimes(1);
    expect(post).toHaveBeenCalledWith({action:'postgresql_server_catalog',request:{}});
  });
  it('discards the previous server inventory when the endpoint changes', async () => {
    const post = jest.fn().mockResolvedValue({databases:[], resources:[{resource_id:'old', resource_kind:'role', display_name:'Previous private role', display_path:['1','roles','Previous private role'], native:{}}]});
    const mounted = render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button', {name:'Load server inventory'}));
    await screen.findByText('Previous private role');
    mounted.rerender(<Component post={jest.fn()} />);
    expect(screen.queryByText('Previous private role')).not.toBeInTheDocument();
  });
  it('requires explicit selection, disables inaccessible databases and sends exact native OIDs', async () => {
    const post = jest.fn().mockResolvedValue({databases: [
      {oid: 42, name: ' chosen ', allows_connections: true, connect_privilege: true, template: false},
      {oid: 43, name: 'denied', allows_connections: true, connect_privilege: false, template: false}], resources: []});
    render(<Component post={post} />);
    expect(screen.getByText('SR-F-001384')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Load server inventory'}));
    await screen.findByRole('table', {name: 'PostgreSQL server database selection'});
    expect(post).toHaveBeenLastCalledWith({action: 'postgresql_server_catalog', request: {}});
    expect(screen.getByRole('checkbox', {name: 'Select PostgreSQL database denied'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Capture selected databases (0/32)'})).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', {name: /Select PostgreSQL database.*chosen/}));
    post.mockResolvedValue({server: {document}, databases: [{database_oid: 42, database_name: ' chosen ', available: true, document}], all_selected_captured: true});
    fireEvent.click(screen.getByRole('button', {name: 'Capture selected databases (1/32)'}));
    await screen.findByText('Server DDN viewer');
    expect(post).toHaveBeenLastCalledWith({action: 'postgresql_server_catalog', request: {database_ids: [42], include_system: false}});
    expect(screen.getByText('No password hashes')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Download server DDN bundle'})).toBeEnabled();
  });
  it('retains unavailable database outcomes instead of substituting another capture', async () => {
    const post = jest.fn().mockResolvedValue({databases: [{oid: 42, name: 'db', allows_connections: true, connect_privilege: true}], resources: []});
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button', {name: 'Load server inventory'}));
    fireEvent.click(await screen.findByRole('checkbox', {name: 'Select PostgreSQL database db'}));
    post.mockResolvedValue({server: {document}, databases: [{database_oid: 42, available: false, reason: 'Server epoch changed'}], all_selected_captured: false});
    fireEvent.click(screen.getByRole('button', {name: 'Capture selected databases (1/32)'}));
    await waitFor(() => expect(screen.getByText(/Database OID 42: Server epoch changed/)).toBeInTheDocument());
    expect(screen.getByText(/Some selected databases were unavailable/)).toBeInTheDocument();
  });
});
