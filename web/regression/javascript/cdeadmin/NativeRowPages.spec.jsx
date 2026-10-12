import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {useState} from 'react';
import useNativeRowPages from '../../../pgadmin/static/js/cdeadmin_ui/data/useNativeRowPages';

function Browser({post}) {
  const paging = useNativeRowPages(post), [busy, setBusy] = useState(false);
  const load = async (continuation=null) => {
    setBusy(true);
    try {await paging.read({target_resource: {resource_id: 'native'}, continuation});}
    finally {setBusy(false);}
  };
  return <div>{paging.controls(load, busy)}<button onClick={() => load()} disabled={busy}>Load</button>
    <span>{paging.page?.records?.join(',')}</span></div>;
}

describe('native non-SQL row page history', () => {
  it('uses each continuation once and returns to cached records', async () => {
    const post = jest.fn().mockResolvedValueOnce({records: ['one'], continuation: 'cursor'})
      .mockResolvedValueOnce({records: ['two']});
    render(<Browser post={post} />);
    fireEvent.click(screen.getByText('Load')); await screen.findByText('one');
    fireEvent.click(screen.getByRole('button', {name: 'Next page'})); await screen.findByText('two');
    fireEvent.click(screen.getByRole('button', {name: 'First page'}));
    expect(screen.getByText('one')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Last page'}));
    expect(screen.getByText('two')).toBeInTheDocument();
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[1][0].request.continuation).toBe('cursor');
  });
  it('caps native retrieval, releases the cursor, and never invents a transaction action', async () => {
    const post = jest.fn().mockResolvedValueOnce({records: ['one'], continuation: 'cursor'}).mockResolvedValue({});
    render(<Browser post={post} />);
    fireEvent.change(screen.getByRole('spinbutton', {name: 'Maximum rows retrieved'}), {target: {value: '1'}});
    fireEvent.click(screen.getByText('Load')); await screen.findByText('one');
    expect(screen.getByText('Retrieval limit reached')).toBeInTheDocument();
    expect(post.mock.calls.map(call => call[0].action)).toEqual(['visual_admin_rows', 'visual_admin_rows_cancel']);
    expect(post.mock.calls[0][0].request.limit).toBe(1);
    fireEvent.click(screen.getByText('Close result'));
    await waitFor(() => expect(screen.queryByText('one')).toBeNull());
  });
});
