import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import DuckDBCatalog from 'sources/Dialogs/DuckDBCatalog';
import {withTheme} from '../fake_theme';

let viewer;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => {viewer = props; return <div>Native DDN viewer</div>;},
}));
jest.mock('sources/cdeadmin_ui/data/PagedDataGrid', () => function MockGrid(props) {
  return <div aria-label={props['aria-label']}>{props.rows.length} changes</div>;
});
const Component = withTheme(DuckDBCatalog);
const snapshot = {format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1',
  files: {'catalog.ddn': 'native metadata'}};
const capture = {snapshot, views: [{id: 'inventory_1', label: 'Native inventory', entry: 'catalog.ddn'}],
  provenance: {objects: 2, coverage: 'partial', warnings: ['Visibility is partial']}};

describe('DuckDB native catalog form', () => {
  it('binds the registered database and shows the public DDN viewer', async () => {
    const post = jest.fn().mockResolvedValue(capture);
    render(<Component post={post} databaseTargetId="owned-duckdb-file" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    expect(post).toHaveBeenCalledWith({action: 'duckdb_catalog_export', request: {
      database_target_id: 'owned-duckdb-file', include_system: false}});
    expect(viewer.snapshot.files).toEqual(snapshot.files);
    expect(viewer.presentation).toBe(true);
    expect(screen.getByText('SR-F-010000')).toBeVisible();
    expect(screen.getByText('Visibility is partial')).toBeVisible();
  });

  it('drops a late capture when the selected file changes', async () => {
    let finish;
    const post = jest.fn().mockImplementation(() => new Promise(resolve => {finish = resolve;}));
    const mounted = render(<Component post={post} databaseTargetId="old-file" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    mounted.rerender(<Component post={post} databaseTargetId="new-file" />);
    await act(async () => {finish(capture);});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Capture metadata'})).toBeEnabled());
    expect(screen.queryByText('Native DDN viewer')).not.toBeInTheDocument();
  });

  it('captures selected native relation data with an explicit row budget', async () => {
    const catalog = {...capture, objects: [{resource_id: 'native-table', kind: 'table',
      path: ['owned', 'main', 'facts']}]};
    const data = {snapshot: {...snapshot, view: 'result_1'},
      views: [{id: 'result_1', label: 'Data page 1', entry: 'catalog.ddn'}],
      acquisition: {rows: 1, relation: 'facts', mode: 'sample'}, warnings: []};
    const post = jest.fn().mockResolvedValueOnce(catalog).mockResolvedValueOnce(data);
    render(<Component post={post} databaseTargetId="owned-duckdb-file" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.change(screen.getByRole('spinbutton', {name: 'Data row budget'}), {target: {value: '3'}});
    fireEvent.click(screen.getByRole('button', {name: 'Capture selected data'}));
    await screen.findByText(/Captured 1 visible rows from facts/);
    expect(post).toHaveBeenLastCalledWith({action: 'duckdb_data_capture', request: {
      database_target_id: 'owned-duckdb-file', resource_id: 'native-table', mode: 'sample', row_limit: 3}});
    expect(viewer.snapshot.view).toBe('result_1');
  });
});
