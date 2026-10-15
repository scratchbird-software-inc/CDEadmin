import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdHistoryView from 'sources/Dialogs/FirebirdHistoryView';
import getApiInstance from 'sources/api_instance';
import {withTheme} from '../fake_theme';
jest.mock('sources/api_instance');
jest.mock('sources/url_for', () => jest.fn(() => '/monitoring/7/history'));
jest.mock('sources/Dialogs/FirebirdTrendView', () => function MockTrend(props) {
  return <div data-testid="archived">{props.snapshot.samples[0]?.sample_id}</div>;
});

describe('ScratchBird historical browsing', () => {
  it('reads bounded scope and pages without scheduling collection; failures clear samples', async () => {
    const get = jest.fn().mockResolvedValueOnce({data: {data: {samples: [{sample_id: 'old', history_provenance: {}}], next: 'cursor'}}})
      .mockRejectedValueOnce({response: {data: {errormsg: 'Scope denied'}}});
    getApiInstance.mockReturnValue({get});
    const Component = withTheme(FirebirdHistoryView);
    render(<Component serverId={7} targetId="target" />);
    expect(get).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Read history'}));
    await screen.findByText('old');
    expect(get.mock.calls[0][1].params).toMatchObject({target_id: 'target', tier: 'raw', limit: 720});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Next page'})).not.toBeDisabled());
    fireEvent.click(screen.getByRole('button', {name: 'Next page'}));
    await screen.findByText('Scope denied');
    expect(screen.queryByText('old')).toBeNull();
    expect(get.mock.calls[1][1].params.after).toBe('cursor');
  });
});
