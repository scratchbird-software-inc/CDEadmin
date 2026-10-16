import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import History from 'sources/Dialogs/FirebirdHistoryView';
import MySQLTestData from 'sources/Dialogs/MySQLTestData';
import MySQLDataImport from 'sources/Dialogs/MySQLDataImport';
import getApiInstance from 'sources/api_instance';
import {withTheme} from '../fake_theme';

jest.mock('sources/api_instance');
jest.mock('sources/url_for', () => jest.fn((_route, {sid}) => `/mysql/${sid}/history`));
jest.mock('sources/Dialogs/MySQLTrendView', () => function NativeObservations() {return <div>Historical native observations</div>;});
jest.mock('sources/Dialogs/FirebirdTrendView', () => function FirebirdObservations() {return <div>Firebird observations</div>;});

const HistoryView = withTheme(History), Recipes = withTheme(MySQLTestData), Import = withTheme(MySQLDataImport);

describe('MySQL persistent native workflows', () => {
  it('reads a bounded historical scope without starting collection and rejects late scopes', async () => {
    let resolve;
    const api = {get: jest.fn(() => new Promise(done => {resolve = done;}))};
    getApiInstance.mockReturnValue(api);
    const mounted = render(<HistoryView engine="mysql" serverId={7} targetId="old" />);
    expect(api.get).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Read history'}));
    expect(api.get).toHaveBeenCalledWith('/mysql/7/history', expect.objectContaining({params: expect.objectContaining({target_id: 'old', tier: 'raw', limit: 720})}));
    mounted.rerender(<HistoryView engine="mysql" serverId={8} targetId="new" />);
    await act(async () => {resolve({data: {data: {samples: [{source: 'old-private-source'}]}}});});
    expect(screen.queryByText('Historical native observations')).toBeNull();
    expect(screen.queryByText(/old-private-source/)).toBeNull();
    expect(screen.getByRole('button', {name: 'Read history'})).toBeEnabled();
  });

  it('loads an older named recipe with the current save version and executes no SQL', async () => {
    const recipe = {format: 'scratchrobin.mysql.test-data@1', scope: {endpoint_id: 'ep', database_target_id: 'db'}, seed: 1, tables: []};
    const post = jest.fn().mockResolvedValue({recipe, version: 1, current_version: 3});
    render(<Recipes post={post} databaseTargetId="db" />);
    fireEvent.change(screen.getByLabelText('Revision (blank for latest)'), {target: {value: '1'}});
    fireEvent.click(screen.getByRole('button', {name: 'Load saved recipe'}));
    await waitFor(() => expect(screen.getByLabelText('Test-data recipe JSON')).toHaveValue(JSON.stringify(recipe, null, 2)));
    expect(post).toHaveBeenLastCalledWith({action: 'mysql_recipe_read', request: {database_target_id: 'db', recipe_id: 'default', version: 1}});
    fireEvent.click(screen.getByRole('button', {name: 'Store recipe revision'}));
    await waitFor(() => expect(post).toHaveBeenLastCalledWith({action: 'mysql_recipe_save', request: {database_target_id: 'db', recipe_id: 'default', expected_version: 3, recipe}}));
    expect(post.mock.calls.every(([request]) => !request.action.includes('execute'))).toBe(true);
  });

  it('requires explicit confirmation and keeps unknown import receipts without offering replay', async () => {
    const post = jest.fn(async ({action}) => {
      if(action === 'mysql_data_plan') return {database: 'demo', table: 't', row_count: 1, storage_engine: 'InnoDB', ready_for_review: true, execution_sha256: 'plan'};
      if(action === 'mysql_data_review') return {review_id: 'review', review_digest: 'digest', state: 'reviewed'};
      return {review_id: 'review', review_digest: 'digest', state: 'unknown_outcome', outcome: {state: 'unknown_outcome', automatic_retry: false}};
    });
    render(<Import post={post} databaseTargetId="db" />);
    fireEvent.click(screen.getByText('Import native MySQL data DDN'));
    const file = {size: 10, text: async () => 'native data'};
    fireEvent.change(screen.getByLabelText('Native MySQL data DDN'), {target: {files: [file]}});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native data import'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Preview native data import'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Prepare data review'}));
    const apply = await screen.findByRole('button', {name: 'Import and commit once'});
    expect(apply).toBeDisabled();
    fireEvent.click(screen.getByRole('checkbox', {name: 'Insert and commit these reviewed rows'}));
    fireEvent.click(apply);
    await waitFor(() => expect(screen.getByText('Data receipt review: unknown_outcome.')).toBeVisible());
    expect(screen.getByRole('button', {name: 'Import and commit once'})).toBeDisabled();
    expect(post.mock.calls.filter(([request]) => request.action === 'mysql_data_apply')).toHaveLength(1);
  });
});
