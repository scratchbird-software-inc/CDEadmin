import {fireEvent, render, screen} from '@testing-library/react';
import PostgresqlTestData from 'sources/Dialogs/PostgresqlTestData';
import {withTheme} from '../fake_theme';
const Component = withTheme(PostgresqlTestData);
describe('PostgreSQL native test-data recipes', () => {
  it('binds generation to the selected database and does not dispatch SQL', async () => {
    const post = jest.fn().mockResolvedValue({scope: {endpoint_id: 'ep', database_target_id: 'postgresql-database:42'}, tables: [{resource_id: 'postgresql:pg_class:42', schema: 'public', name: 'example', columns: [{name: 'id', insertable: true}]}]});
    render(<Component post={post} databaseTargetId="postgresql-database:42" />);
    expect(screen.getByText('SR-F-001385')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Load native tables'}));
    await screen.findByText('public.example');
    fireEvent.click(screen.getByRole('button', {name: 'Add table'}));
    const recipe = JSON.parse(screen.getByRole('textbox', {name: 'Test-data recipe JSON'}).value);
    expect(recipe.tables[0].table).toBe('postgresql:pg_class:42');
    post.mockResolvedValue({source: 'INSERT INTO public.example DEFAULT VALUES;', rows: 10, tables: 1});
    fireEvent.click(screen.getByRole('button', {name: 'Generate SQL preview'}));
    await screen.findByText('10 rows in 1 tables generated; not executed.');
    expect(post).toHaveBeenLastCalledWith({action: 'postgresql_test_data', request: {database_target_id: 'postgresql-database:42', recipe}});
    expect(post.mock.calls.every(([request]) => request.action === 'postgresql_test_data')).toBe(true);
    fireEvent.change(screen.getByRole('textbox', {name: 'Test-data recipe JSON'}), {target: {value: '{}'}});
    expect(screen.getByRole('button', {name: 'Save SQL script'})).toBeDisabled();
  });
});
