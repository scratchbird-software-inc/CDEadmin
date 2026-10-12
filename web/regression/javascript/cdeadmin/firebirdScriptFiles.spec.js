import {TextDecoder, TextEncoder} from 'util';
import {readFirebirdScriptFile} from '../../../pgadmin/static/js/Dialogs/firebirdScriptFiles';

describe('Browser-local Firebird script input', () => {
  beforeAll(() => { global.TextDecoder = TextDecoder; });
  it('preserves UTF-8 and source line breaks without executing or including commands', async () => {
    const source = 'SET TERM ^ ;\r\nSELECT \'é漢\';^\r\nINPUT private.sql^';
    const bytes = new TextEncoder().encode(source);
    expect(await readFirebirdScriptFile({size: bytes.length, arrayBuffer: async () => bytes})).toBe(source);
  });
  it('refuses oversized files before reading and invalid UTF-8 or NUL', async () => {
    const large = {size: 1048577, arrayBuffer: jest.fn()};
    await expect(readFirebirdScriptFile(large)).rejects.toThrow('at most 1 MiB');
    expect(large.arrayBuffer).not.toHaveBeenCalled();
    await expect(readFirebirdScriptFile({size: 1, arrayBuffer: async () => new Uint8Array([255])})).rejects.toThrow('valid UTF-8');
    await expect(readFirebirdScriptFile({size: 1, arrayBuffer: async () => new Uint8Array([0])})).rejects.toThrow('NUL');
  });
});
