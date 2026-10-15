import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import PostgresqlServerCatalog from 'sources/Dialogs/PostgresqlServerCatalog';
import {withTheme} from '../fake_theme';
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({DDNViewerSurface: () => <div>Server DDN viewer</div>}));
const Component = withTheme(PostgresqlServerCatalog);
const snapshot = {format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1', files: {'catalog.ddn': 'native source'}};
const document = {snapshot, views: [{id: 'inventory_1', label: 'Inventory'}], provenance: {warnings: ['No password hashes']}};

describe('PostgreSQL server DDN capture', () => {
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
