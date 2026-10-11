import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdQueryHistory from 'sources/Dialogs/FirebirdQueryHistory';
import {withTheme} from '../fake_theme';

describe('Firebird persistent SQL history', () => {
  const Component = withTheme(FirebirdQueryHistory);
  const response = {policy: {capture_source: false, retention_days: 30, max_records: 500},
    entries: [{entry_id: 'one', created_at: 100, kind: 'statement', request_state: 'accepted', source: 'select 1'},
      {entry_id: 'secret', created_at: 90, kind: 'statement', request_state: 'accepted', source: null, source_omitted_reason: 'Sensitive source omitted'},
      {entry_id: 'two', created_at: 80, kind: 'statement', request_state: 'request-error', source: 'select 2'}]};
  it('loads text without executing and navigates past omitted source', async () => {
    const post = jest.fn().mockResolvedValue(response), onLoad = jest.fn();
    render(<Component post={post} databaseTargetId="db" dialect={3} onLoad={onLoad} />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('SQL history'));
    await screen.findByText('select 1');
    expect(post).toHaveBeenCalledWith({action: 'query_history_read', request: {database_target_id: 'db', client_sql_dialect: 3, search: ''}});
    fireEvent.click(screen.getByText('Previous history entry'));
    expect(onLoad).toHaveBeenLastCalledWith('select 1');
    fireEvent.click(screen.getByText('Previous history entry'));
    expect(onLoad).toHaveBeenLastCalledWith('select 2');
    fireEvent.click(screen.getByText('Next history entry'));
    expect(onLoad).toHaveBeenLastCalledWith('select 1');
    expect(post).toHaveBeenCalledTimes(1);
  });
  it('requires explicit confirmation to clear the selected scope', async () => {
    const post = jest.fn().mockResolvedValue(response);
    render(<Component post={post} databaseTargetId="db" dialect={1} onLoad={jest.fn()} />);
    fireEvent.click(screen.getByText('SQL history'));
    await screen.findByText('select 1');
    expect(screen.getByText('Clear SQL history')).toBeDisabled();
    fireEvent.click(screen.getByLabelText('Confirm clearing this database and dialect history'));
    fireEvent.click(screen.getByText('Clear SQL history'));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'query_history_clear', request: {
      database_target_id: 'db', client_sql_dialect: 1, confirmed: true,
    }}));
  });
});
