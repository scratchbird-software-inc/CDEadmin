import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdIsql from '../../../pgadmin/static/js/Dialogs/FirebirdIsql';
const connection = {schema: 'scratchrobin.firebird.isql-context@1', database_target_id: 'owned',
  dsn: 'inet://localhost:3050//owned/db.fdb', user: 'Account', role: '', charset: 'UTF8', sql_dialect: 3};

describe('external Firebird ISQL', () => {
  it('provides no process launch on browser-only clients', async () => {
    const post = jest.fn().mockResolvedValue(connection);
    render(<FirebirdIsql post={post} databaseTargetId="owned" bridge={null} />);
    await screen.findByLabelText('ISQL password');
    expect(screen.getByRole('button', {name: 'Launch local ISQL'})).toBeDisabled();
    expect(post).toHaveBeenCalledWith({action: 'firebird_isql_context', request: {database_target_id: 'owned'}});
  });
  it('sends the independent credential only to the desktop bridge and clears the field', async () => {
    const post = jest.fn().mockResolvedValue(connection);
    const bridge = {available: true, launch: jest.fn().mockResolvedValue({state: 'process_started'})};
    render(<FirebirdIsql post={post} databaseTargetId="owned" bridge={bridge} />);
    const password = await screen.findByLabelText('ISQL password');
    fireEvent.change(password, {target: {value: 'single-launch-secret'}});
    await act(async () => fireEvent.click(screen.getByRole('button', {name: 'Launch local ISQL'})));
    expect(bridge.launch).toHaveBeenCalledWith({connection, password: 'single-launch-secret'});
    expect(password).toHaveValue('');
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByText(/Check the terminal for native connection status/)).toBeInTheDocument();
  });
  it('does not bind a late context response to a different database', async () => {
    let resolve;
    const post = jest.fn().mockImplementationOnce(() => new Promise(done => {resolve = done;})).mockResolvedValue({...connection, database_target_id: 'next', user: 'Next'});
    const view = render(<FirebirdIsql post={post} databaseTargetId="owned" bridge={null} />);
    view.rerender(<FirebirdIsql post={post} databaseTargetId="next" bridge={null} />);
    await waitFor(() => expect(screen.getByLabelText('ISQL username')).toHaveValue('Next'));
    await act(async () => resolve(connection));
    expect(screen.getByLabelText('ISQL username')).toHaveValue('Next');
  });
});
