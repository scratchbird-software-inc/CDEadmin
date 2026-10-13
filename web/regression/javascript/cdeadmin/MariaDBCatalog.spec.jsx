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


  it('reads current relation data only after explicit selection with the captured server UID and row budget', async () => {
    const catalog = {...capture, objects: [{resource_id: 'native-table', kind: 'table', name: 'Exact values'},
      {resource_id: 'native-sequence', kind: 'sequence', name: 'Never advance'}]};
    const data = {snapshot: {format: 'ddn-workspace@1', entry: 'result-1.ddn', view: 'result_1',
      files: {'result-1.ddn': 'exact native data'}}, views: [{id: 'result_1', label: 'Data page 1', entry: 'result-1.ddn'}],
    acquisition: {rows: 1, relation: 'Exact values', mode: 'sample', server_uid: 'native-server'}, warnings: ['Explicit sample coverage']};
    const post = jest.fn().mockResolvedValueOnce(catalog).mockResolvedValueOnce(data);
    render(<Component post={post} databaseTargetId="mariadb-owned-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    expect(post).toHaveBeenCalledTimes(1);
    fireEvent.change(screen.getByRole('spinbutton', {name: 'Data row budget'}), {target: {value: '3'}});
    fireEvent.click(screen.getByRole('button', {name: 'Capture selected data'}));
    await screen.findByText('Explicit sample coverage');
    expect(post).toHaveBeenLastCalledWith({action: 'mariadb_data_capture', request: {
      database_target_id: 'mariadb-owned-target', resource_id: 'native-table', expected_server_uid: 'native-server', mode: 'sample', row_limit: 3}});
    expect(mockViewer.snapshot.files).toEqual(data.snapshot.files);
    expect(mockViewer.presentation).toBe(true);
  });
});
