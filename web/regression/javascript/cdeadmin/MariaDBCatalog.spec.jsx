import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import MariaDBCatalog from 'sources/Dialogs/MariaDBCatalog';
import {withTheme} from '../fake_theme';
let mockViewer;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => {mockViewer = props; return <div>Native DDN viewer</div>;},
}));
jest.mock('sources/cdeadmin_ui/data/PagedDataGrid', () => function MockGrid(props) {return <div aria-label={props['aria-label']}>{props.rows.length} changes</div>;});
const Component = withTheme(MariaDBCatalog);

const capture = {snapshot: {format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1', files: {'catalog.ddn': 'native metadata'}},
  server_uid: 'native-server',
  views: [{id: 'inventory_1', label: 'Native inventory', entry: 'catalog.ddn'}],
  provenance: {coverage: 'partial', objects: 2, warnings: ['Visibility is partial']}};

describe('MariaDB native catalog form', () => {
  it('binds capture to its database and presents DDN without engine-specific substitution', async () => {
    const post = jest.fn().mockResolvedValue(capture);
    render(<Component post={post} databaseTargetId="mariadb-owned-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    expect(post).toHaveBeenCalledWith({action: 'mariadb_catalog_export', request: {
      database_target_id: 'mariadb-owned-target', include_system: false}});
    expect(mockViewer.snapshot.files).toEqual(capture.snapshot.files);
    expect(mockViewer.presentation).toBe(true);
    expect(screen.getByText(/Coverage: partial/)).toBeVisible();
    expect(screen.getByText('SR-F-001407')).toBeVisible();
  });

  it('does not show a late response from a previously selected database', async () => {
    let finish;
    const post = jest.fn().mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const mounted = render(<Component post={post} databaseTargetId="old-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    mounted.rerender(<Component post={post} databaseTargetId="new-target" />);
    await act(async () => {finish(capture);});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Capture metadata'})).toBeEnabled());
    expect(screen.queryByText('Native DDN viewer')).not.toBeInTheDocument();
  });

});
