import {fireEvent, render, screen} from '@testing-library/react';
import MySQLTestData from 'sources/Dialogs/MySQLTestData';
import {withTheme} from '../fake_theme';
const Component = withTheme(MySQLTestData);
describe('MySQL native test-data recipes', () => {
  it('binds generation to the selected database and does not dispatch SQL', async () => {
    const post = jest.fn().mockResolvedValue({scope: {endpoint_id: 'ep', database_target_id: 'mysql-database:42'}, tables: [{resource_id: 'mysql:pg_class:42', schema: 'public', name: 'example', columns: [{name: 'id', insertable: true}]}]});
    render(<Component post={post} databaseTargetId="mysql-database:42" />);
    expect(screen.getByText('SR-F-001401')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Load native tables'}));
    await screen.findByText('public.example');
    fireEvent.click(screen.getByRole('button', {name: 'Add table'}));
    const recipe = JSON.parse(screen.getByRole('textbox', {name: 'Test-data recipe JSON'}).value);
    expect(recipe.tables[0].table).toBe('mysql:pg_class:42');
    post.mockResolvedValue({source: 'INSERT INTO `public`.`example` () VALUES ();', rows: 10, tables: 1});
    fireEvent.click(screen.getByRole('button', {name: 'Generate SQL preview'}));
    await screen.findByText('10 rows in 1 tables generated; not executed.');
    expect(post).toHaveBeenLastCalledWith({action: 'mysql_test_data', request: {database_target_id: 'mysql-database:42', recipe}});
    expect(post.mock.calls.every(([request]) => request.action === 'mysql_test_data')).toBe(true);
    fireEvent.change(screen.getByRole('textbox', {name: 'Test-data recipe JSON'}), {target: {value: '{}'}});
    expect(screen.getByRole('button', {name: 'Save SQL script'})).toBeDisabled();
  });
  it('uses native MariaDB recipes with the same compact controls and no SQL dispatch', async () => {
    const post = jest.fn().mockResolvedValue({scope: {endpoint_id: 'ep', database_target_id: 'maria-target'},
      tables: [{resource_id: 'mariadb:table', schema: 'demo', name: 'native', columns: [{name: 'id', insertable: true}]}]});
    render(<Component engine="mariadb" post={post} databaseTargetId="maria-target" />);
    expect(screen.getByText('SR-F-001410')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Load native tables'}));
    await screen.findByText('demo.native');
    fireEvent.click(screen.getByRole('button', {name: 'Add table'}));
    const recipe = JSON.parse(screen.getByRole('textbox', {name: 'Test-data recipe JSON'}).value);
    expect(recipe.format).toBe('scratchrobin.mariadb.test-data@1');
    post.mockResolvedValue({source: 'INSERT INTO native VALUES (VEC_FromText(\'[1,2]\'));', rows: 10, tables: 1});
    fireEvent.click(screen.getByRole('button', {name: 'Generate SQL preview'}));
    await screen.findByText('10 rows in 1 tables generated; not executed.');
    expect(screen.getByRole('textbox', {name: 'Generated MariaDB SQL'})).toHaveValue('INSERT INTO native VALUES (VEC_FromText(\'[1,2]\'));');
    expect(post).toHaveBeenLastCalledWith({action: 'mariadb_test_data', request: {database_target_id: 'maria-target', recipe}});
    expect(post.mock.calls.every(([request]) => request.action === 'mariadb_test_data')).toBe(true);
  });
});
