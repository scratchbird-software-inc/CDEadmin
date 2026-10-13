import {fireEvent, render, screen} from '@testing-library/react';
import DuckDBCopy from 'sources/Dialogs/DuckDBCopy';
import {withTheme} from '../fake_theme';

const Component = withTheme(DuckDBCopy);

describe('DuckDB native COPY preview', () => {
  it('binds one registered table and never dispatches SQL', async () => {
    const post = jest.fn().mockResolvedValueOnce({tables: [{resource_id: 'native-table',
      catalog: 'demo', schema: 'main', name: 'facts'}]})
      .mockResolvedValueOnce({source: 'COPY "demo"."main"."facts" TO \'/owned/facts.parquet\' (FORMAT PARQUET);',
        native_format: 'PARQUET', executed: false});
    render(<Component post={post} databaseTargetId="file-1" resourceId="native-table" />);
    expect(screen.getByText('SR-F-010006')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Load native tables'}));
    await screen.findByText('demo.main.facts');
    fireEvent.change(screen.getByRole('textbox', {name: 'Absolute file path'}),
      {target: {value: '/owned/facts.parquet'}});
    fireEvent.click(screen.getByRole('button', {name: 'Preview native COPY'}));
    await screen.findByText('One native PARQUET COPY statement generated; not executed.');
    expect(post).toHaveBeenLastCalledWith({action: 'duckdb_copy_plan', request: {
      database_target_id: 'file-1', resource_id: 'native-table', direction: 'to',
      format: 'PARQUET', path: '/owned/facts.parquet'}});
    expect(post.mock.calls.every(([request]) => ['duckdb_test_data', 'duckdb_copy_plan'].includes(request.action))).toBe(true);
  });
});
