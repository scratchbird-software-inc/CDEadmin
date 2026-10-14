import {fireEvent, render, screen} from '@testing-library/react';
import DuckDBServerCatalog from 'sources/Dialogs/DuckDBServerCatalog';
import {withTheme} from '../fake_theme';

let viewer;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => {viewer = props; return <div>DuckDB DDN viewer</div>;},
}));
const Component = withTheme(DuckDBServerCatalog);
const snapshot = {format: 'ddn-workspace@1', entry: 'catalog.ddn',
  view: 'inventory_1', files: {'catalog.ddn': 'native facts'}};
const document = {snapshot, views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}]};

describe('DuckDB registered-file catalog', () => {
  it('captures selected files separately and displays unavailable targets', async () => {
    const post = jest.fn().mockResolvedValueOnce({files: [
      {target_id: 'first', display_name: 'First file', active: true},
      {target_id: 'missing', display_name: 'Missing file', active: false}]})
      .mockResolvedValueOnce({server: {document}, files: [
        {database_target_id: 'first', display_name: 'First file', available: true, document},
        {database_target_id: 'missing', display_name: 'Missing file', available: false,
          reason: 'Native file capture failed; no substitute file was used'}],
      all_selected_captured: false});
    render(<Component post={post} />);
    fireEvent.click(screen.getByRole('button', {name: 'Load registered files'}));
    expect(await screen.findByRole('table', {name: 'DuckDB registered file selection'})).toBeVisible();
    expect(post).toHaveBeenCalledWith({action: 'duckdb_catalog_export', request: {}});
    fireEvent.click(screen.getByRole('button', {name: 'Select all registered files'}));
    fireEvent.click(screen.getByRole('button', {name: 'Capture selected files (2/32)'}));
    await screen.findByText('DuckDB DDN viewer');
    expect(post).toHaveBeenLastCalledWith({action: 'duckdb_catalog_export', request: {
      database_target_ids: ['first', 'missing'], include_system: false}});
    expect(screen.getByText(/Some selected files could not be captured/)).toBeVisible();
    expect(screen.getByText(/Missing file: Native file capture failed/)).toBeVisible();
    expect(screen.getByText('SR-F-010008')).toBeVisible();
    expect(viewer.snapshot.files).toEqual(snapshot.files);
    expect(screen.getByRole('combobox', {name: 'Captured catalog'})).toBeVisible();
  });
});
