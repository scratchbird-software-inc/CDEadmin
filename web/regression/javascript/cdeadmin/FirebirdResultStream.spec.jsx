import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {startFirebirdBrowserDownload} from '../../../pgadmin/static/js/Dialogs/firebirdBrowserDownload';
jest.mock('../../../pgadmin/static/js/Dialogs/firebirdBrowserDownload', () => ({
  startFirebirdBrowserDownload: jest.fn(() => jest.fn()),
}));
import FirebirdResultStream from '../../../pgadmin/static/js/Dialogs/FirebirdResultStream';

const page = (sequence, value, end=false) => ({sequence, rows: [[value]],
  columns: [{name: 'VALUE'}], stream_reference: 'stream', end_of_cursor: end,
  rows_read: sequence + 1});

describe('Firebird bounded stream controls', () => {
  afterEach(() => { delete window.showSaveFilePicker; });

  const blobPage = () => page(0, {blob_reference: 'blob'}, true);
  const sink = () => ({write: jest.fn().mockResolvedValue(), close: jest.fn().mockResolvedValue(),
    abort: jest.fn().mockResolvedValue()});

  it('delegates full downloads without a picker and never claims disk completion', async () => {
    const post = jest.fn().mockImplementation(async ({request}) => {
      if (request.stream_action === 'open') return blobPage();
      if (request.stream_action === 'download_begin') return {download_id: 'delivery'};
      if (request.stream_action === 'download_status') return {state: 'sent', bytes: 42};
      return {state: 'sent'};
    });
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'}
      source="select value" downloadUrl="/workspace" />);
    fireEvent.click(screen.getByText('Run streaming'));
    fireEvent.click(await screen.findByText('Download BLOB to browser'));
    await screen.findByText(/File sent to browser. Verify completion/);
    expect(screen.queryByText(/BLOB file saved/)).not.toBeInTheDocument();
    expect(startFirebirdBrowserDownload).toHaveBeenCalledWith('/workspace', expect.objectContaining({
      session_id: 'session', request: expect.objectContaining({download_id: 'delivery', stream_reference: 'stream'}),
    }));
    expect(screen.getByText('Download BLOB to browser')).toBeDisabled();
    expect(post.mock.calls.map(([value]) => value.request.stream_action)).toEqual([
      'open', 'download_begin', 'download_status', 'download_abort',
    ]);
  });

  it('saves the complete unread ARRAY and prevents a second export of its consumed reference', async () => {
    const writer = sink();
    window.showSaveFilePicker = jest.fn().mockResolvedValue({createWritable: async () => writer});
    const post = jest.fn().mockResolvedValueOnce(page(0, {
      array_reference: 'array', bounds: [[-1, 0]], element_count: 2,
      native_element_type: 8, scale: 0, subtype: 0, charset_id: null,
    }, true)).mockResolvedValueOnce({array_reference: 'array', offset: 0, next_offset: 2,
      coordinates: [-1], values: [1, 2], complete: true}).mockResolvedValue({closed: true});
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'} source="select array_value" />);
    fireEvent.click(screen.getByText('Run streaming'));
    fireEvent.click(await screen.findByText('Save ARRAY to file'));
    await screen.findByText('ARRAY file saved. Elements:', {exact: false});
    expect(writer.write).toHaveBeenCalledTimes(3);
    expect(writer.close).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Save ARRAY to file')).toBeDisabled();
    expect(screen.getByText('Read ARRAY slice')).toBeDisabled();
    expect(post.mock.calls.map(([value]) => value.request.stream_action)).toEqual(['open', 'array']);
  });

  it('pulls ARRAY slices by offset and retries a lost response without executing SQL again', async () => {
    window.showSaveFilePicker = jest.fn();
    const post = jest.fn().mockResolvedValueOnce(page(0, {
      array_reference: 'array', bounds: [[-1, 0]], element_count: 2,
    }, true)).mockRejectedValueOnce(new Error('Lost response'))
      .mockResolvedValueOnce({array_reference: 'array', offset: 0, next_offset: 1,
        coordinates: [-1], values: ['12345678901234567890'], complete: false})
      .mockResolvedValueOnce({array_reference: 'array', offset: 1, next_offset: 2,
        coordinates: [0], values: [null], complete: true})
      .mockResolvedValue({closed: true});
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'} source="select array_value" />);
    fireEvent.click(screen.getByText('Run streaming'));
    fireEvent.click(await screen.findByText('Read ARRAY slice'));
    await screen.findByText('Lost response');
    expect(screen.getByText('Save ARRAY to file')).toBeDisabled();
    fireEvent.click(screen.getByText('Read ARRAY slice'));
    await screen.findByText(/12345678901234567890/);
    expect(screen.getByText('Starting coordinates:', {exact: false})).toHaveTextContent('[-1]');
    fireEvent.click(screen.getByText('Next ARRAY slice'));
    await waitFor(() => expect(screen.getByText('Next ARRAY slice')).toBeDisabled());
    expect(screen.getByText('Read ARRAY slice')).toBeDisabled();
    expect(post.mock.calls.map(([value]) => value.request.stream_action)).toEqual(['open', 'array', 'array', 'array']);
    expect(post.mock.calls.slice(1).map(([value]) => value.request.offset)).toEqual([0, 0, 1]);
    fireEvent.click(screen.getByText('Close stream'));
    await waitFor(() => expect(screen.queryByText('Read ARRAY slice')).not.toBeInTheDocument());
  });

  it('saves through a user-selected writer and disables replay after native reading', async () => {
    const writer = sink();
    const createWritable = jest.fn().mockResolvedValue(writer);
    window.showSaveFilePicker = jest.fn().mockResolvedValue({createWritable});
    const post = jest.fn().mockResolvedValueOnce(blobPage()).mockResolvedValueOnce({
      blob_reference: 'blob', offset: 0, next_offset: 2, data: 'AP8=', encoding: 'base64', complete: true,
    }).mockResolvedValue({closed: true});
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'} source="select payload" />);
    fireEvent.click(screen.getByText('Run streaming'));
    fireEvent.click(await screen.findByText('Save BLOB to file'));
    await screen.findByText('BLOB file saved. Bytes:', {exact: false});
    expect(createWritable).toHaveBeenCalledWith({keepExistingData: false});
    expect([...writer.write.mock.calls[0][0]]).toEqual([0, 255]);
    expect(writer.close).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Save BLOB to file')).toBeDisabled();
    expect(screen.getByText('Read BLOB chunk')).toBeDisabled();
    expect(post.mock.calls.map(([value]) => value.request.stream_action)).toEqual(['open', 'blob']);
  });

  it('picker cancellation leaves the native BLOB unread and retryable', async () => {
    window.showSaveFilePicker = jest.fn().mockRejectedValue(Object.assign(new Error(), {name: 'AbortError'}));
    const post = jest.fn().mockResolvedValue(blobPage());
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'} source="select payload" />);
    fireEvent.click(screen.getByText('Run streaming'));
    fireEvent.click(await screen.findByText('Save BLOB to file'));
    await screen.findByText('BLOB save cancelled.');
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Save BLOB to file')).toBeEnabled();
  });

  it('stopping while the picker is pending clears progress without reading', async () => {
    let release;
    window.showSaveFilePicker = jest.fn(() => new Promise(resolve => { release = resolve; }));
    const createWritable = jest.fn();
    const post = jest.fn().mockResolvedValue(blobPage());
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'} source="select payload" />);
    fireEvent.click(screen.getByText('Run streaming'));
    fireEvent.click(await screen.findByText('Save BLOB to file'));
    fireEvent.click(screen.getByText('Stop BLOB save'));
    release({createWritable});
    await screen.findByText('BLOB save stopped.');
    expect(screen.queryByText('Stop BLOB save')).not.toBeInTheDocument();
    expect(screen.getByText('Save BLOB to file')).toBeEnabled();
    expect(createWritable).not.toHaveBeenCalled();
    expect(post).toHaveBeenCalledTimes(1);
  });

  it('does not offer a complete file after an inspection read loses its response', async () => {
    window.showSaveFilePicker = jest.fn();
    const post = jest.fn().mockResolvedValueOnce(blobPage()).mockRejectedValueOnce(new Error('Lost response'))
      .mockResolvedValue({closed: true});
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'} source="select payload" />);
    fireEvent.click(screen.getByText('Run streaming'));
    fireEvent.click(await screen.findByText('Read BLOB chunk'));
    await screen.findByText('Lost response');
    expect(screen.getByText('Save BLOB to file')).toBeDisabled();
    expect(window.showSaveFilePicker).not.toHaveBeenCalled();
  });

  it('stops an in-flight download, aborts the file and retains explicit stream cleanup', async () => {
    const writer = sink();
    window.showSaveFilePicker = jest.fn().mockResolvedValue({createWritable: async () => writer});
    let release;
    const post = jest.fn().mockResolvedValueOnce(blobPage())
      .mockImplementationOnce(() => new Promise(resolve => { release = resolve; }))
      .mockResolvedValue({closed: true});
    render(<FirebirdResultStream post={post} ensureSession={async () => 'session'} source="select payload" />);
    fireEvent.click(screen.getByText('Run streaming'));
    fireEvent.click(await screen.findByText('Save BLOB to file'));
    await waitFor(() => expect(post).toHaveBeenCalledTimes(2));
    expect(screen.getByText('Close stream')).toBeDisabled();
    fireEvent.click(screen.getByText('Stop BLOB save'));
    release({blob_reference: 'blob', offset: 0, next_offset: 1, data: 'eA==', encoding: 'base64', complete: true});
    await screen.findByText('BLOB save stopped.');
    expect(writer.write).not.toHaveBeenCalled();
    expect(writer.abort).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Save BLOB to file')).toBeDisabled();
    fireEvent.click(screen.getByText('Close stream'));
    await waitFor(() => expect(screen.getByText('Run streaming')).toBeEnabled());
    expect(post.mock.calls[2][0].request.stream_action).toBe('close');
  });

  it('explains missing browser support without advertising an unavailable action', async () => {
    render(<FirebirdResultStream post={jest.fn().mockResolvedValue(blobPage())}
      ensureSession={async () => 'session'} source="select payload" />);
    fireEvent.click(screen.getByText('Run streaming'));
    await screen.findByText('Read BLOB chunk');
    expect(screen.queryByText('Save BLOB to file')).not.toBeInTheDocument();
    expect(screen.getByText(/Use Download to browser/)).toBeInTheDocument();
  });

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

  it.each([
    ['blob', 'Stage BLOB parameter (raw file bytes)'],
    ['array', 'Stage ARRAY parameter (exported JSON Lines file)'],
  ])('uploads a %s file in bounded chunks, with a session-owned parameter token', async (kind, label) => {
    const post = jest.fn().mockImplementation(async ({request}) => {
      if (request.stream_action === 'upload_begin') return {[request.value_kind + '_upload']: 'owned'};
      return {};
    });
    const bytes = new Uint8Array(65537).fill(255);
    const file = {size: bytes.length, slice: (start, end) => ({
      arrayBuffer: async () => bytes.slice(start, end).buffer,
    })};
    const {unmount} = render(<FirebirdResultStream post={post}
      ensureSession={async () => 'session'} source="insert into t values (?)" />);
    fireEvent.change(screen.getByLabelText(label),
      {target: {files: [file]}});
    await screen.findByText(JSON.stringify({[kind + '_upload']: 'owned'}));
    expect(post.mock.calls[0][0].request.value_kind).toBe(kind);
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
