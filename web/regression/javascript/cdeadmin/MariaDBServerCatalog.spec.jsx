import {act, fireEvent, render, screen} from '@testing-library/react';
import MySQLServerCatalog from 'sources/Dialogs/MySQLServerCatalog';
import {withTheme} from '../fake_theme';
let mockViewer;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({DDNViewerSurface: props => {
  mockViewer=props; return <div>Server DDN viewer</div>;
}}));
const Component=withTheme(MySQLServerCatalog);
const result={server_uid: 'native-id', snapshot: {view: 'inventory_1', entry: 'server.ddn', files: {'server.ddn': 'server metadata'}},
  views: [{id: 'inventory_1', label: 'Inventory', entry: 'server.ddn'}], databases: [],
  registered_targets: [{target_id: 'db', database: 'demo', display_name: 'Demo'}]};
describe('MariaDB server DDN discovery', () => {
  it('captures no database implicitly and displays a readonly native DDN projection', async () => {
    const post=jest.fn().mockResolvedValue(result);
    render(<Component engine="mariadb" post={post} />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Capture server inventory'}));
    await screen.findByText('Server DDN viewer');
    expect(post).toHaveBeenCalledWith({action: 'mariadb_server_catalog', request: {include_system: true, targets: []}});
    expect(mockViewer.presentation).toBe(true);
    expect(mockViewer.snapshot.files).toEqual(result.snapshot.files);
    expect(screen.getByText('SR-F-001408')).toBeVisible();
    expect(screen.getByRole('button', {name: 'Capture selected databases'})).toBeDisabled();
    expect(screen.queryByRole('button', {name: /execute|apply/i})).not.toBeInTheDocument();
  });
  it('drops stale responses when the owner/server binding changes', async () => {
    let finish;
    const post=jest.fn().mockImplementation(() => new Promise(resolve => {finish=resolve;}));
    const mounted=render(<Component engine="mariadb" post={post} />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture server inventory'}));
    mounted.rerender(<Component engine="mariadb" post={jest.fn()} />);
    await act(async () => {finish(result);});
    expect(screen.queryByText('Server DDN viewer')).not.toBeInTheDocument();
  });
});
