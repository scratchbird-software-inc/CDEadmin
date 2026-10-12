import {saveFirebirdBlob} from '../../../pgadmin/static/js/Dialogs/firebirdBlobFile';

const part = (offset, raw, complete) => ({blob_reference: 'blob', offset,
  next_offset: offset + raw.length, data: btoa(raw), encoding: 'base64', complete});
const writer = () => ({write: jest.fn().mockResolvedValue(),
  close: jest.fn().mockResolvedValue(), abort: jest.fn().mockResolvedValue()});
const options = (sink, read, other={}) => ({writer: sink, reference: 'blob', read,
  stopped: () => false, progress: jest.fn(), ...other});

describe('Firebird bounded file pump', () => {
  it('waits for each write before another native pull and preserves raw bytes', async () => {
    const sink = writer();
    let release;
    sink.write.mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
    const read = jest.fn().mockResolvedValueOnce(part(0, '\x00\xff\xc3', false))
      .mockResolvedValueOnce(part(3, '\xa9', true));
    const job = saveFirebirdBlob(options(sink, read));
    await Promise.resolve();
    expect(read).toHaveBeenCalledTimes(1);
    expect([...sink.write.mock.calls[0][0]]).toEqual([0, 255, 195]);
    release();
    expect(await job).toBe(4);
    expect(read.mock.calls).toEqual([[0], [3]]);
    expect([...sink.write.mock.calls[1][0]]).toEqual([169]);
    expect(sink.close).toHaveBeenCalledTimes(1);
    expect(sink.abort).not.toHaveBeenCalled();
  });

  it('handles an empty BLOB and the terminal empty chunk after an exact boundary', async () => {
    for (const length of [0, 65536]) {
      const sink = writer();
      const read = jest.fn().mockResolvedValueOnce(part(0, 'x'.repeat(length), length === 0))
        .mockResolvedValueOnce(part(length, '', true));
      expect(await saveFirebirdBlob(options(sink, read))).toBe(length);
      expect(sink.write.mock.calls.every(([bytes]) => bytes.length <= 65536)).toBe(true);
    }
  });

  it.each([
    {blob_reference: 'other'}, {offset: 1}, {next_offset: 4}, {next_offset: '1'},
    {encoding: 'text'}, {complete: 'true'}, {data: '!'}, {data: 'eA==junk'},
    {data: btoa('x'.repeat(65537)), next_offset: 65537},
    {data: '', next_offset: 0, complete: false},
  ])('rejects an invalid response before writing: %j', async (invalid) => {
    const sink = writer();
    await expect(saveFirebirdBlob(options(sink, async () => ({...part(0, 'x', true), ...invalid}))))
      .rejects.toThrow('Invalid BLOB');
    expect(sink.write).not.toHaveBeenCalled();
    expect(sink.close).not.toHaveBeenCalled();
    expect(sink.abort).toHaveBeenCalledTimes(1);
  });

  it.each(['read', 'write', 'close'])('aborts on %s failure and never replays', async (stage) => {
    const sink = writer();
    const read = jest.fn().mockResolvedValue(part(0, 'x', true));
    (stage === 'read' ? read : sink[stage]).mockRejectedValueOnce(new Error('owned failure'));
    await expect(saveFirebirdBlob(options(sink, read))).rejects.toThrow('owned failure');
    expect(read).toHaveBeenCalledTimes(1);
    expect(sink.abort).toHaveBeenCalledTimes(1);
  });

  it('reports unknown cleanup without claiming a saved file', async () => {
    const sink = writer();
    sink.abort.mockRejectedValue(new Error('owned abort failure'));
    await expect(saveFirebirdBlob(options(sink, async () => { throw new Error('owned read'); })))
      .rejects.toThrow('cleanup is unconfirmed');
    expect(sink.close).not.toHaveBeenCalled();
  });

  it('stops after an outstanding read without writing or fetching again', async () => {
    const sink = writer();
    let stop = false;
    let release;
    const read = jest.fn(() => new Promise(resolve => { release = resolve; }));
    const job = saveFirebirdBlob(options(sink, read, {stopped: () => stop}));
    stop = true;
    release(part(0, 'x', true));
    await expect(job).rejects.toThrow('stopped');
    expect(read).toHaveBeenCalledTimes(1);
    expect(sink.write).not.toHaveBeenCalled();
    expect(sink.abort).toHaveBeenCalledTimes(1);
  });
});
