import {render, fireEvent, screen, waitFor, act} from '@testing-library/react';
import {PostgresqlBinaryField, PostgresqlBinaryResult} from '../../../pgadmin/static/js/Dialogs/PostgresqlBinaryChunk';

describe('PostgreSQL native binary chunks', () => {
  const field = {label: 'Binary chunk', help: 'Native bytes'};
  it('loads file bytes into the review without a database request', async () => {
    const onChange = jest.fn(), slice = jest.fn(() => ({arrayBuffer: async () => new Uint8Array([0, 255]).buffer}));
    const {container} = render(<PostgresqlBinaryField field={field} value="" onChange={onChange} />);
    fireEvent.change(container.querySelector('input[type=file]'), {target: {files: [{name: 'native.bin', size: 2, slice}]}});
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Load up to 1 MiB into review'}));
    await waitFor(() => expect(onChange).toHaveBeenCalledWith('AP8='));
    expect(slice).toHaveBeenCalledWith(0, 1024 * 1024);
  });
  it('discards a file read after the target form is unmounted', async () => {
    let finish;
    const onChange = jest.fn(), slice = () => ({arrayBuffer: () => new Promise(resolve => {finish = resolve;})});
    const {container, unmount} = render(<PostgresqlBinaryField field={field} value="" onChange={onChange} />);
    fireEvent.change(container.querySelector('input[type=file]'), {target: {files: [{name: 'native.bin', size: 2, slice}]}});
    fireEvent.click(screen.getByRole('button', {name: 'Load up to 1 MiB into review'}));
    unmount();
    await act(async () => {finish(new Uint8Array([0, 255]).buffer);});
    expect(onChange).not.toHaveBeenCalled();
  });
  it('refuses a corrupt chunk before downloading', async () => {
    render(<PostgresqlBinaryResult row={{oid: 42, offset: '0', byte_length: 2, data_base64: 'AP8=', sha256: 'incorrect'}} />);
    const original = Object.getOwnPropertyDescriptor(global, 'crypto');
    Object.defineProperty(global, 'crypto', {configurable: true, value: require('node:crypto').webcrypto});
    try {
      fireEvent.click(screen.getByRole('button', {name: /Download binary chunk/}));
      expect(await screen.findByRole('alert')).toHaveTextContent('Binary chunk checksum does not match.');
    } finally {Object.defineProperty(global, 'crypto', original);}
  });
});
