import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLCatalog from 'sources/Dialogs/MySQLCatalog';
import {withTheme} from '../fake_theme';
let mockViewer;
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => {mockViewer = props; return <div>Native DDN viewer</div>;},
}));
jest.mock('sources/cdeadmin_ui/data/PagedDataGrid', () => function MockGrid(props) {return <div aria-label={props['aria-label']}>{props.rows.length} changes</div>;});
const Component = withTheme(MySQLCatalog);

const capture = {snapshot: {format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1', files: {'catalog.ddn': 'native metadata'}},
  views: [{id: 'inventory_1', label: 'Native inventory', entry: 'catalog.ddn'}],
  provenance: {warnings: ['Visibility is partial']}};

describe('MySQL native catalog form', () => {
  it('binds capture to its database and presents DDN without engine-specific substitution', async () => {
    const post = jest.fn().mockResolvedValue(capture);
    render(<Component post={post} databaseTargetId="mysql-owned-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    expect(post).toHaveBeenCalledWith({action: 'mysql_catalog_export', request: {
      database_target_id: 'mysql-owned-target', include_system: false}});
    expect(mockViewer.snapshot.files).toEqual(capture.snapshot.files);
    expect(mockViewer.presentation).toBe(true);
    expect(screen.getByText('Visibility is partial')).toBeVisible();
    expect(screen.getByText('SR-F-001393')).toBeVisible();
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

  it('generates native SQL from the complete capture without executing or using only its displayed view', async () => {
    const metadata = {script: 'CREATE TABLE native_table(id int);', script_available: true,
      blockers: [], prerequisites: [], warnings: ['Observational export only']};
    const post = jest.fn().mockResolvedValueOnce(capture).mockResolvedValueOnce(metadata);
    render(<Component post={post} databaseTargetId="mysql-owned-target" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Native DDN viewer');
    fireEvent.click(screen.getByRole('button', {name: 'Generate native SQL'}));
    const script = await screen.findByRole('textbox', {name: 'Native MySQL metadata script'});
    expect(script).toHaveValue(metadata.script);
    expect(script).toHaveAttribute('readonly');
    expect(post).toHaveBeenLastCalledWith({action: 'mysql_sql_export', request: {
      database_target_id: 'mysql-owned-target', source: JSON.stringify(capture.snapshot)}});
    expect(screen.getByRole('button', {name: 'Download native SQL'})).toBeEnabled();
    expect(post).toHaveBeenCalledTimes(2);
  });

});
