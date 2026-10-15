import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import MySQLMonitoring from 'sources/Dialogs/MySQLMonitoring';
import getApiInstance from 'sources/api_instance';
import {withTheme} from '../fake_theme';

jest.mock('sources/api_instance');
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: props => <div data-testid="viewer" data-read-only={props.presentation} />,
}));

const Component = withTheme(MySQLMonitoring);

describe('SQLite native file monitoring', () => {
  let api;
  beforeEach(() => {
    api = {get: jest.fn(async () => ({data: {data: {state: 'disabled', samples: []}}})),
      post: jest.fn(async () => ({data: {data: {state: 'collecting', samples: []}}})),
      delete: jest.fn()};
    getApiInstance.mockReturnValue(api);
  });

  it('keeps the file dashboard display-only', async () => {
    render(<Component engine="sqlite" serverId={8} targetId="file-one" />);
    await waitFor(() => expect(api.get).toHaveBeenCalledWith(
      '/cdeadmin/api/monitoring/sqlite/8?target_id=file-one'));
    expect(screen.getByTestId('viewer')).toHaveAttribute('data-read-only', 'true');
    expect(screen.queryByRole('button', {name: 'Start collection'})).toBeNull();
  });

  it('does not ask for network credentials', async () => {
    render(<Component engine="sqlite" serverId={8} targetId="file-one" policyMode />);
    await waitFor(() => expect(screen.getByRole('button', {name: 'Start collection'})).toBeEnabled());
    expect(screen.queryByRole('combobox', {name: 'Monitoring credentials'})).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Start collection'}));
    await waitFor(() => expect(api.post).toHaveBeenCalledWith(
      '/cdeadmin/api/monitoring/sqlite/8?target_id=file-one',
      expect.not.objectContaining({credentials: expect.anything()})));
  });
});
