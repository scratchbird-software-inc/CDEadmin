import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdResultStream from '../../../pgadmin/static/js/Dialogs/FirebirdResultStream';

const page = (sequence, value, end=false) => ({sequence, rows: [[value]],
  columns: [{name: 'VALUE'}], stream_reference: 'stream', end_of_cursor: end,
  rows_read: sequence + 1});

describe('Firebird bounded stream controls', () => {
  it('pulls only on demand, replaces pages, and closes without finality', async () => {
    const post = jest.fn().mockResolvedValueOnce(page(0, 'first'))
      .mockResolvedValueOnce(page(1, 'second', true)).mockResolvedValue({closed: true});
    const {unmount} = render(<FirebirdResultStream post={post}
      ensureSession={async () => 'session'} databaseTargetId="db"
      source="select value from example" parameters="[]" dialect={3} />);
    fireEvent.click(screen.getByText('Run streaming'));
    await screen.findByText('"first"');
    expect(post).toHaveBeenCalledTimes(1);
    expect(post.mock.calls[0][0]).toMatchObject({session_id: 'session',
      database_target_id: 'db', request: {stream_action: 'open'}});
    fireEvent.click(screen.getByText('Next stream page'));
    await screen.findByText('"second"');
    expect(screen.queryByText('"first"')).not.toBeInTheDocument();
    expect(screen.getByText('Next stream page')).toBeDisabled();
    fireEvent.click(screen.getByText('Close stream'));
    await waitFor(() => expect(screen.queryByText('"second"')).not.toBeInTheDocument());
    unmount();
    expect(post).toHaveBeenCalledTimes(3);
    expect(post.mock.calls[2][0].request).toMatchObject({stream_action: 'close'});
  });

  it('retains cleanup after failed native execution and never retries SQL', async () => {
    const post = jest.fn().mockRejectedValueOnce(new Error('owned failure'))
      .mockResolvedValue({closed: true});
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'}
      source="update example set value=1" parameters="[]" />);
    fireEvent.click(screen.getByText('Run streaming'));
    await screen.findByText('owned failure');
    expect(screen.getByText('Run streaming')).toBeDisabled();
    fireEvent.click(screen.getByText('Close stream'));
    await waitFor(() => expect(screen.getByText('Run streaming')).toBeEnabled());
    expect(post).toHaveBeenCalledTimes(2);
  });

  it('uses a fresh owner for a subsequent stream on the same session', async () => {
    const post = jest.fn().mockResolvedValue(page(0, 42));
    const {unmount} = render(<FirebirdResultStream post={post}
      ensureSession={async () => 'session'} source="select 42" />);
    fireEvent.click(screen.getByText('Run streaming'));
    await screen.findByText('42');
    const firstOwner = post.mock.calls[0][0].request.owner_id;
    fireEvent.click(screen.getByText('Close stream'));
    await waitFor(() => expect(screen.getByText('Run streaming')).toBeEnabled());
    expect(post.mock.calls[1][0].request.owner_id).toBe(firstOwner);
    fireEvent.click(screen.getByText('Run streaming'));
    await screen.findByText('42');
    const secondOwner = post.mock.calls[2][0].request.owner_id;
    expect(secondOwner).not.toBe(firstOwner);
    unmount();
    expect(post.mock.calls[3][0].request.owner_id).toBe(secondOwner);
  });

  it('releases native ownership on unmount', async () => {
    const post = jest.fn().mockResolvedValue(page(0, 42));
    const {unmount} = render(<FirebirdResultStream post={post}
      ensureSession={async () => 'session'} source="select 42" />);
    fireEvent.click(screen.getByText('Run streaming'));
    await screen.findByText('42');
    unmount();
    expect(post.mock.calls[1][0].request).toMatchObject({stream_action: 'close'});
  });

  it('uploads a file in bounded chunks, with a session-owned parameter token', async () => {
    const post = jest.fn().mockImplementation(async ({request}) => {
      if (request.stream_action === 'upload_begin') return {blob_upload: 'owned'};
      return {};
    });
    const bytes = new Uint8Array(65537).fill(255);
    const file = {size: bytes.length, slice: (start, end) => ({
      arrayBuffer: async () => bytes.slice(start, end).buffer,
    })};
    const {unmount} = render(<FirebirdResultStream post={post}
      ensureSession={async () => 'session'} source="insert into t values (?)" />);
    fireEvent.change(screen.getByLabelText('Stage BLOB parameter (raw file bytes)'),
      {target: {files: [file]}});
    await screen.findByText('{"blob_upload":"owned"}');
    expect(post.mock.calls.map(([call]) => call.request.stream_action)).toEqual([
      'upload_begin', 'upload_chunk', 'upload_chunk', 'upload_finish',
    ]);
    const chunks = post.mock.calls.slice(1, 3).map(([call]) => call.request);
    expect(chunks.map((chunk) => atob(chunk.data).length)).toEqual([65536, 1]);
    expect(chunks.map((chunk) => chunk.offset)).toEqual([0, 65536]);
    unmount();
    expect(post.mock.calls[4][0].request).toMatchObject({stream_action: 'close'});
  });
});
