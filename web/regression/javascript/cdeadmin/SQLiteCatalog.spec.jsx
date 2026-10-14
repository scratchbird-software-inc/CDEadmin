import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import SQLiteCatalog from 'sources/Dialogs/SQLiteCatalog';
import {withTheme} from '../fake_theme';

jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: () => <div>SQLite DDN viewer</div>,
}));
jest.mock('sources/Dialogs/FirebirdCatalogDesigner', () => () => null);

const Component = withTheme(SQLiteCatalog);
const snapshot = {format: 'ddn-workspace@1', entry: 'catalog.ddn',
  view: 'inventory_1', files: {'catalog.ddn': 'native facts'}};

it('previews a SQLite native design from its captured baseline', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot,
    views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [], provenance: {objects: 0, coverage: 'partial'}})
    .mockResolvedValueOnce({operations: [], blockers: [], conflicts: [],
      application_supported: false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  const input = screen.getByLabelText('SQLite catalog DDN file');
  const file = new File([JSON.stringify(snapshot)], 'desired.json', {type: 'application/json'});
  file.text = jest.fn().mockResolvedValue(JSON.stringify(snapshot));
  fireEvent.change(input, {target: {files: [file]}});
  await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
  await screen.findByText(/Native preview only; no SQL was executed/);
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_schema_plan', request: {
    database_target_id: 'file-1', baseline: JSON.stringify(snapshot), desired: JSON.stringify(snapshot), deletions: [], rebuilds: [], column_renames: []}});
});

it('exports only a selected SQLite user table as reviewable SQL', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot,
    views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [{resource_id: 'table-1', kind: 'table', path: ['main', 'owned']}],
    provenance: {objects: 1, coverage: 'partial'}})
    .mockResolvedValueOnce({source: 'INSERT INTO "main"."owned" VALUES (1);', rows: 1});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  fireEvent.click(screen.getByRole('button', {name: 'Export table as native SQL'}));
  await screen.findByText(/1 SQLite rows exported as SQL/);
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_data_script', request: {
    database_target_id: 'file-1', resource_id: 'table-1'}});
  expect(screen.getByRole('textbox', {name: 'SQLite native data SQL'}).value).toContain('INSERT INTO');
});

it('sends an explicit deletion identity with the SQLite DDN preview', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot,
    views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [{resource_id: 'table-1', kind: 'table', name: 'owned', path: ['main', 'owned']}],
    provenance: {objects: 1, coverage: 'partial'}})
    .mockResolvedValueOnce({operations: [], blockers: [], conflicts: [], application_supported: false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  const file = new File([JSON.stringify(snapshot)], 'desired.json', {type: 'application/json'});
  file.text = jest.fn().mockResolvedValue(JSON.stringify(snapshot));
  fireEvent.change(screen.getByLabelText('SQLite catalog DDN file'), {target: {files: [file]}});
  await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByText('Explicit native deletions (0)'));
  fireEvent.click(screen.getByRole('checkbox', {name: 'Delete SQLite table owned'}));
  fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
  await screen.findByText(/Native preview only; no SQL was executed/);
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_schema_plan', request: {
    database_target_id: 'file-1', baseline: JSON.stringify(snapshot), desired: JSON.stringify(snapshot),
    deletions: ['table-1'], rebuilds: [], column_renames: []}});
});

it('sends a reviewed column rename mapping with its selected table rebuild', async () => {
  const post = jest.fn().mockResolvedValueOnce({snapshot,
    views: [{id: 'inventory_1', label: 'Inventory', entry: 'catalog.ddn'}],
    objects: [{resource_id: 'table-1', kind: 'table', name: 'owned', path: ['main', 'owned']},
      {resource_id: 'column-1', kind: 'column', name: 'old_note', path: ['main', 'owned', 'old_note']}],
    provenance: {objects: 2, coverage: 'partial'}})
    .mockResolvedValueOnce({operations: [], blockers: [], conflicts: [], application_supported: false});
  render(<Component post={post} databaseTargetId="file-1" />);
  fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
  await screen.findByText('SQLite DDN viewer');
  const file = new File([JSON.stringify(snapshot)], 'desired.json', {type: 'application/json'});
  file.text = jest.fn().mockResolvedValue(JSON.stringify(snapshot));
  fireEvent.change(screen.getByLabelText('SQLite catalog DDN file'), {target: {files: [file]}});
  await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native changes'})).toBeEnabled());
  fireEvent.click(screen.getByText('Isolated table rebuild (0)'));
  fireEvent.click(screen.getByRole('checkbox', {name: 'Rebuild SQLite table owned'}));
  fireEvent.click(screen.getByText('Retained column renames (0)'));
  fireEvent.click(screen.getByRole('button', {name: 'Map column rename'}));
  fireEvent.change(screen.getByRole('combobox', {name: 'Existing column'})
    .parentElement.querySelector('input'), {target: {value: 'old_note'}});
  fireEvent.change(screen.getByRole('textbox', {name: 'Desired column name'}),
    {target: {value: 'new_note'}});
  fireEvent.click(screen.getByRole('button', {name: 'Preview native changes'}));
  await screen.findByText(/Native preview only; no SQL was executed/);
  expect(post).toHaveBeenLastCalledWith({action: 'sqlite_schema_plan', request: {
    database_target_id: 'file-1', baseline: JSON.stringify(snapshot), desired: JSON.stringify(snapshot),
    deletions: [], rebuilds: ['table-1'], column_renames: [
      {table: 'table-1', from: 'old_note', to: 'new_note'}]}});
});
