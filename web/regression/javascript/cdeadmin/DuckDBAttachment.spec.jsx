import {fireEvent, render, screen} from '@testing-library/react';
import DuckDBAttachment from 'sources/Dialogs/DuckDBAttachment';
import {withTheme} from '../fake_theme';

const Component = withTheme(DuckDBAttachment);

describe('DuckDB session attachment preview', () => {
  it('binds one registered file and generates a retained-session script only', async () => {
    const post = jest.fn().mockResolvedValue({action: 'attach', source: 'ATTACH ...', executed: false});
    render(<Component post={post} databaseTargetId="file-1" />);
    expect(screen.getByText('SR-F-010007')).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', {name: 'Native catalog alias'}),
      {target: {value: 'history'}});
    fireEvent.change(screen.getByRole('textbox', {name: 'Absolute DuckDB file path'}),
      {target: {value: '/owned/archive.duckdb'}});
    fireEvent.click(screen.getByRole('button', {name: 'Preview native attachment'}));
    await screen.findByText('One native ATTACH statement generated; not executed.');
    expect(post).toHaveBeenCalledWith({action: 'duckdb_attachment_plan', request: {
      database_target_id: 'file-1', action: 'attach', alias: 'history',
      path: '/owned/archive.duckdb', read_only: true}});
    expect(post.mock.calls.every(([request]) => request.action === 'duckdb_attachment_plan')).toBe(true);
  });
});
