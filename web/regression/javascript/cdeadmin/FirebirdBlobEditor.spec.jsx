import {TextDecoder, TextEncoder} from 'util';
import {act, fireEvent, render, screen} from '@testing-library/react';
import {renderBlobChunk} from 'sources/Dialogs/FirebirdBlobChunk';
import FirebirdBlobEditor from 'sources/Dialogs/FirebirdBlobEditor';
import {blobBytes, blobImport, blobDraft, BLOB_EDIT_LIMIT} from 'sources/Dialogs/firebirdBlobValue';
import {withTheme} from '../fake_theme';

describe('Firebird typed BLOB editing', () => {
  const Component = withTheme(FirebirdBlobEditor);
  let encoder, decoder;
  beforeEach(() => {encoder = global.TextEncoder; decoder = global.TextDecoder; global.TextEncoder = TextEncoder; global.TextDecoder = TextDecoder;});
  afterEach(() => {global.TextEncoder = encoder; global.TextDecoder = decoder;});
  it('roundtrips binary bytes, empty values, Unicode and a UTF-8 BOM', () => {
    const bytes = Uint8Array.from({length: 256}, (_, index) => index);
    expect(blobBytes(blobImport(bytes, 'binary'), 'binary')).toEqual(bytes);
    for (const text of ['', '\ufeffHello\r\n世界\rnext\n']) expect(blobImport(blobBytes(text, 'text'), 'text')).toBe(text);
    expect(() => blobImport(Uint8Array.from([255]), 'text')).toThrow();
    expect(() => blobImport(new Uint8Array(BLOB_EDIT_LIMIT + 1), 'binary')).toThrow('limit');
    expect(() => blobBytes('YQ', 'binary')).toThrow();
  });
  it('preserves original endings and requires explicit conversion after editing CR text', () => {
    const original = 'a\r\nb\rc\n';
    const draft = {text: 'a\nb\nc\n', isNull: false};
    expect(blobDraft(original, draft, 'text', 'preserve', false).text).toBe(original);
    expect(() => blobDraft(original, draft, 'text', 'preserve', true)).toThrow('Choose LF');
    expect(blobDraft(original, draft, 'text', 'crlf', true).text).toBe('a\r\nb\r\nc\r\n');
    expect(blobDraft(original, {text: '', isNull: false}, 'text', 'lf', true)).toEqual({text: '', isNull: false});
    expect(blobDraft(original, {...draft, isNull: true}, 'text', 'preserve', true).isNull).toBe(true);
  });
  it('shows precise hex offsets and rejects split or invalid UTF-8 without substitution', () => {
    expect(renderBlobChunk({offset: '9007199254740993', data: 'AP9B'}, 'hex')).toContain('20000000000001  00 ff 41');
    expect(renderBlobChunk({offset: 0, data: 'aGk='}, 'utf8')).toBe('hi');
    expect(() => renderBlobChunk({offset: 0, data: 'ww=='}, 'utf8')).toThrow();
  });
  it('only stages on explicit Apply; Cancel does not apply', () => {
    const onApply = jest.fn(), onClose = jest.fn();
    render(<Component value={{text: 'initial', isNull: false}} kind="text" label="PAYLOAD" onApply={onApply} onClose={onClose} />);
    fireEvent.change(screen.getByLabelText('BLOB text'), {target: {value: 'changed'}});
    expect(onApply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Cancel'));
    expect(onApply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Apply to row'));
    expect(onApply).toHaveBeenCalledWith({text: 'changed', isNull: false});
  });
  it('offers read-only viewing without staging or file import', () => {
    render(<Component value={{text: 'aGVsbG8=', isNull: false}} kind="binary" label="PAYLOAD" readOnly onApply={jest.fn()} onClose={jest.fn()} />);
    expect(screen.getByText('Apply to row')).toBeDisabled();
    expect(screen.getByLabelText('Import BLOB file')).toBeDisabled();
    expect(screen.getByLabelText('BLOB Base64')).toHaveAttribute('readonly');
    expect(screen.getByText('Export file')).not.toBeDisabled();
  });
  it('discards a late file import when the native value changes', async () => {
    let finish;
    const props = {value: {text: 'old', isNull: false}, kind: 'text', label: 'PAYLOAD', onApply: jest.fn(), onClose: jest.fn()};
    const {rerender} = render(<Component {...props} />);
    fireEvent.change(screen.getByLabelText('Import BLOB file'), {target: {files: [{size: 3, arrayBuffer: () => new Promise(resolve => {finish = resolve;})}]}});
    rerender(<Component {...props} value={{text: 'new native value', isNull: false}} />);
    await act(async () => {finish(new TextEncoder().encode('old imported bytes').buffer);});
    expect(screen.getByLabelText('BLOB text')).toHaveValue('new native value');
    expect(props.onApply).not.toHaveBeenCalled();
    fireEvent.click(screen.getByText('Apply to row'));
    expect(props.onApply).toHaveBeenCalledWith({text: 'new native value', isNull: false});
  });

});
