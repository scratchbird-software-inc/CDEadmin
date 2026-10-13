import {fireEvent, render, screen} from '@testing-library/react';
import DuckDBTestData from 'sources/Dialogs/DuckDBTestData';
import {withTheme} from '../fake_theme';

const Component = withTheme(DuckDBTestData);

describe('DuckDB native test-data recipes', () => {
  it('binds a recipe to one registered file and only previews SQL', async () => {
    const scope = {endpoint_id: 'ep', database_target_id: 'file-1'};
    const post = jest.fn().mockResolvedValue({scope, tables: [{resource_id: 'table-1',
      catalog: 'demo', schema: 'main', name: 'facts',
      columns: [{name: 'n', data_type: 'INTEGER', nullable: false, has_default: false}]}]});
    render(<Component post={post} databaseTargetId="file-1" />);
    expect(screen.getByText('SR-F-010005')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Load native tables'}));
    await screen.findByText('demo.main.facts');
    fireEvent.click(screen.getByRole('button', {name: 'Add table'}));
    const recipe = JSON.parse(screen.getByRole('textbox', {name: 'Test-data recipe JSON'}).value);
    expect(recipe.scope).toEqual(scope);
    expect(recipe.tables[0].table).toBe('table-1');
    post.mockResolvedValue({source: 'INSERT INTO "demo"."main"."facts" DEFAULT VALUES;', rows: 10, tables: 1});
    fireEvent.click(screen.getByRole('button', {name: 'Generate SQL preview'}));
    await screen.findByText('10 rows in 1 tables generated; not executed.');
    expect(post).toHaveBeenLastCalledWith({action: 'duckdb_test_data', request: {
      database_target_id: 'file-1', recipe}});
    expect(post.mock.calls.every(([request]) => request.action === 'duckdb_test_data')).toBe(true);
  });
});
