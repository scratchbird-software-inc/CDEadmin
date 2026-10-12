import {saveFirebirdArray} from '../../../pgadmin/static/js/Dialogs/firebirdArrayFile';

const descriptor = {array_reference: 'owned', bounds: [[-1, 0], [3, 4]], element_count: 4,
  native_element_type: 16, scale: 0, subtype: 0, charset_id: null};
const part = (offset, values, coordinates, complete=false) => ({array_reference: 'owned',
  offset, next_offset: offset + values.length, values, coordinates, complete});
const first = () => part(0, ['12345678901234567890', 'é\u0000 '], [-1, 3]);
const second = () => part(2, [{encoding: 'base64', data: 'AP8=', byte_length: 2}, false], [0, 3], true);
const sink = () => ({write: jest.fn().mockResolvedValue(), close: jest.fn().mockResolvedValue(), abort: jest.fn().mockResolvedValue()});

it('writes bounded JSON Lines with exact metadata/values and a completion footer', async () => {
  const writer = sink(), progress = jest.fn();
  const read = jest.fn().mockResolvedValueOnce(first()).mockResolvedValueOnce(second());
  const result = await saveFirebirdArray({writer, descriptor, read, stopped: () => false, progress});
  const records = writer.write.mock.calls.map(([bytes]) => JSON.parse(new TextDecoder().decode(bytes)));
  expect(records).toEqual([
    {format: 'cdeadmin.firebird-array.v1', bounds: descriptor.bounds, element_count: 4,
      native_element_type: 16, scale: 0, subtype: 0, charset_id: null},
    {offset: 0, coordinates: [-1, 3], values: first().values},
    {offset: 2, coordinates: [0, 3], values: second().values},
    {complete: true, element_count: 4},
  ]);
  expect(result.elements).toBe(4);
  expect(result.bytes).toBe(writer.write.mock.calls.reduce((sum, [bytes]) => sum + bytes.length, 0));
  expect(writer.close).toHaveBeenCalledTimes(1);
  expect(writer.abort).not.toHaveBeenCalled();
  expect(read.mock.calls).toEqual([[0], [2]]);
});

it('waits for each file write before pulling the next native slice', async () => {
  let release;
  const writer = sink();
  writer.write.mockResolvedValueOnce().mockImplementationOnce(() => new Promise(resolve => { release = resolve; }));
  const read = jest.fn().mockResolvedValueOnce(first()).mockResolvedValueOnce(second());
  const pending = saveFirebirdArray({writer, descriptor, read, stopped: () => false, progress: jest.fn()});
  while (!release) await Promise.resolve();
  expect(read).toHaveBeenCalledTimes(1);
  release();
  await pending;
  expect(read).toHaveBeenCalledTimes(2);
});

it.each([
  {array_reference: 'foreign'}, {offset: 1}, {next_offset: 3}, {values: []},
  {values: [1, 2, 3], next_offset: 3}, {coordinates: [0, 3]}, {complete: true},
])('aborts malformed slices without a completion footer: %s', async change => {
  const writer = sink();
  await expect(saveFirebirdArray({writer, descriptor,
    read: async () => ({...first(), ...change}), stopped: () => false, progress: jest.fn()})).rejects.toThrow('Invalid ARRAY');
  expect(writer.abort).toHaveBeenCalledTimes(1);
  expect(writer.close).not.toHaveBeenCalled();
  expect(writer.write).toHaveBeenCalledTimes(1);
});

it('aborts after stop without requesting a later slice', async () => {
  const writer = sink();
  let stopped = false;
  const read = jest.fn().mockResolvedValue(first());
  await expect(saveFirebirdArray({writer, descriptor, read, stopped: () => stopped,
    progress: () => { stopped = true; }})).rejects.toThrow('ARRAY save stopped');
  expect(read).toHaveBeenCalledTimes(1);
  expect(writer.abort).toHaveBeenCalledTimes(1);
  expect(writer.close).not.toHaveBeenCalled();
});

it('reports uncertain cleanup when the destination cannot be aborted', async () => {
  const writer = sink();
  writer.write.mockRejectedValue(new Error('disk full'));
  writer.abort.mockRejectedValue(new Error('abort failed'));
  const read = jest.fn();
  await expect(saveFirebirdArray({writer, descriptor, read, stopped: () => false,
    progress: jest.fn()})).rejects.toThrow('file cleanup is unconfirmed');
  expect(read).not.toHaveBeenCalled();
});


it.each([[-2147483648, -2147483647], [2147483646, 2147483647]])('preserves full signed native bounds %s:%s', async (low, high) => {
  const writer = sink();
  const result = await saveFirebirdArray({writer,
    descriptor: {...descriptor, bounds: [[low, high]], element_count: 2},
    read: async () => part(0, [1, 2], [low], true), stopped: () => false, progress: jest.fn()});
  expect(result.elements).toBe(2);
  expect(JSON.parse(new TextDecoder().decode(writer.write.mock.calls[0][0])).bounds).toEqual([[low, high]]);
});

it.each([[-2147483649, -2147483648], [2147483647, 2147483648]])('rejects coordinates beyond native range %s:%s', async (low, high) => {
  const writer = sink(), read = jest.fn();
  await expect(saveFirebirdArray({writer,
    descriptor: {...descriptor, bounds: [[low, high]], element_count: 2},
    read, stopped: () => false, progress: jest.fn()})).rejects.toThrow('Invalid ARRAY file descriptor');
  expect(read).not.toHaveBeenCalled();
  expect(writer.write).not.toHaveBeenCalled();
});
