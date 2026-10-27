import {act, fireEvent, render, screen} from '@testing-library/react';
import MySQLServerCatalog from 'sources/Dialogs/MySQLServerCatalog';
import {withTheme} from '../fake_theme';
let mockViewer;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({DDNViewerSurface: props => {
  mockViewer=props; return <div>Server DDN viewer</div>;
}}));
const Component=withTheme(MySQLServerCatalog);
const result={server_uuid: 'native-id', snapshot: {view: 'inventory_1', entry: 'server.ddn', files: {'server.ddn': 'server metadata'}},
  views: [{id: 'inventory_1', label: 'Inventory', entry: 'server.ddn'}], databases: [],
  registered_targets: [{target_id: 'db', database: 'demo', display_name: 'Demo'}]};
describe('MySQL server DDN discovery', () => {
  it('captures no database implicitly and displays a readonly native DDN projection', async () => {
    const post=jest.fn().mockResolvedValue(result);
    render(<Component post={post} />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Capture server inventory'}));
    await screen.findByText('Server DDN viewer');
    expect(post).toHaveBeenCalledWith({action: 'mysql_server_catalog', request: {include_system: true, targets: []}});
    expect(mockViewer.presentation).toBe(true);
    expect(mockViewer.snapshot.files).toEqual(result.snapshot.files);
    expect(screen.getByText('SR-F-001400')).toBeVisible();
    expect(screen.getByRole('button', {name: 'Capture selected databases'})).toBeDisabled();
    expect(screen.queryByRole('button', {name: /execute|apply/i})).not.toBeInTheDocument();
  });
  it('drops stale responses when the owner/server binding changes', async () => {
    let finish;
    const post=jest.fn().mockImplementation(() => new Promise(resolve => {finish=resolve;}));
    const mounted=render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture server inventory'}));
    mounted.rerender(<Component post={jest.fn()} />);
    await act(async () => {finish(result);});
    expect(screen.queryByText('Server DDN viewer')).not.toBeInTheDocument();
  });
  it('captures an explicit bounded SRID selection and resets it on endpoint changes', async () => {
    const post=jest.fn().mockResolvedValue(result);
    const mounted=render(<Component post={post} />);
    fireEvent.change(screen.getByLabelText('Spatial reference IDs to include'), {target:{value:'4326, 4294967000'}});
    fireEvent.click(screen.getByRole('button', {name:'Capture server inventory'}));
    await screen.findByText('Server DDN viewer');
    expect(post).toHaveBeenCalledWith({action:'mysql_server_catalog',request:{include_system:true,targets:[],spatial_reference_ids:[4326,4294967000]}});
    mounted.rerender(<Component post={jest.fn()} />);
    expect(screen.getByLabelText('Spatial reference IDs to include')).toHaveValue('');
  });
  it('refuses invalid SRIDs before requesting a capture and keeps MariaDB separate', async () => {
    const post=jest.fn();
    const mounted=render(<Component post={post} />);
    fireEvent.change(screen.getByLabelText('Spatial reference IDs to include'), {target:{value:'4294967296'}});
    fireEvent.click(screen.getByRole('button', {name:'Capture server inventory'}));
    await screen.findByText('Select at most 128 distinct unsigned 32-bit SRIDs, separated by commas.');
    expect(post).not.toHaveBeenCalled();
    mounted.rerender(<Component post={post} engine="mariadb" />);
    expect(screen.queryByLabelText('Spatial reference IDs to include')).not.toBeInTheDocument();
  });
});
