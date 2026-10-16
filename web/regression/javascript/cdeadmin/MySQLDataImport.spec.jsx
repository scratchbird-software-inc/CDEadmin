import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLDataImport from 'sources/Dialogs/MySQLDataImport';
import {withTheme} from '../fake_theme';

const Component = withTheme(MySQLDataImport);
describe('Native data DDN import workflows', () => {
  it.each(['mysql', 'mariadb'])('reviews and commits %s once on the selected database', async engine => {
    const plan = {database: 'demo', table: 'exact', row_count: 1, storage_engine: 'InnoDB', ready_for_review: true, execution_sha256: 'digest'};
    const receipt = {review_id: 'review', review_digest: 'review-digest', state: 'reviewed', plan};
    const post = jest.fn(async ({action}) => action.endsWith('_plan') ? plan :
      action.endsWith('_apply') ? {...receipt, state: 'unknown_outcome'} : receipt);
    render(<Component post={post} databaseTargetId="target" engine={engine} />);
    fireEvent.click(screen.getByText(`Import native ${engine === 'mariadb' ? 'MariaDB' : 'MySQL'} data DDN`));
    fireEvent.change(screen.getByLabelText(`Native ${engine === 'mariadb' ? 'MariaDB' : 'MySQL'} data DDN`), {
      target: {files: [{size: 10, text: async () => 'native-ddn'}]},
    });
    await waitFor(() => expect(screen.getByRole('button', {name: 'Preview native data import'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Preview native data import'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Prepare data review'}));
    await screen.findByText('Data receipt review: reviewed.');
    fireEvent.click(screen.getByRole('checkbox', {name: 'Insert and commit these reviewed rows'}));
    fireEvent.click(screen.getByRole('button', {name: 'Import and commit once'}));
    await screen.findByText('Data receipt review: unknown_outcome.');
    expect(post).toHaveBeenLastCalledWith({action: `${engine}_data_apply`, request: {
      database_target_id: 'target', review_id: 'review', review_digest: 'review-digest', confirmed: true,
    }});
    expect(screen.getByRole('button', {name: 'Import and commit once'})).toBeDisabled();
  });
  it('discards late receipt responses after switching native engines', async () => {
    let finish;
    const post = jest.fn(() => new Promise(resolve => {finish = resolve;}));
    const mounted = render(<Component post={post} databaseTargetId="target" engine="mariadb" />);
    fireEvent.click(screen.getByText('Import native MariaDB data DDN'));
    fireEvent.click(screen.getByRole('button', {name: 'Load recent data receipts'}));
    mounted.rerender(<Component post={post} databaseTargetId="target" engine="mysql" />);
    await act(async () => {finish({receipts: [{review_id: 'stale', state: 'committed'}]});});
    expect(screen.queryByRole('combobox', {name: 'Saved data receipt'})).not.toBeInTheDocument();
  });
});
