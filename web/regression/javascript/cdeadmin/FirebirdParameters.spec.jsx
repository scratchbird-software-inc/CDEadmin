import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {createHash} from 'crypto';
import FirebirdParameters, {parameterKind} from 'sources/Dialogs/FirebirdParameters';
import {withTheme} from '../fake_theme';

const Component = withTheme(FirebirdParameters);
const source = 'SELECT * FROM T WHERE ID=?';
const nativePlan = {source_sha256: createHash('sha256').update(source).digest('hex'),
  client_sql_dialect: 3, parameter_count: 1, parameters_complete: true,
  parameters: [{position: 0, native_type: 'INT128', scale: 0, length: 16, charset: 0, nullable: true, field: 'ID', relation: 'T'}]};

describe('Firebird prepared native parameter grid', () => {
  let subtle;
  beforeEach(() => {
    subtle = Object.getOwnPropertyDescriptor(global.crypto, 'subtle');
    Object.defineProperty(global.crypto, 'subtle', {configurable: true, value: {
      digest: async (_algorithm, data) => Uint8Array.from(createHash('sha256').update(data).digest()).buffer,
    }});
  });
  afterEach(() => {
    if(subtle) Object.defineProperty(global.crypto, 'subtle', subtle);
    else delete global.crypto.subtle;
  });
  it('requires native preparation and explicit initialization/application without executing', async () => {
    const change = jest.fn(), prepare = jest.fn();
    const props = {source, dialect: 3, parameters: '["1267650600228229401496703205376"]', onChange: change, onPrepare: prepare};
    const {rerender} = render(<Component {...props} />);
    expect(screen.getByText('SR-F-001374')).toBeVisible();
    fireEvent.click(screen.getByText('Prepare parameter metadata'));
    expect(prepare).toHaveBeenCalledTimes(1);
    expect(change).not.toHaveBeenCalled();
    rerender(<Component {...props} plan={nativePlan} />);
    fireEvent.click(await screen.findByText('Initialize parameter grid from bindings'));
    expect(screen.getByLabelText('Parameter 1')).toHaveValue('1267650600228229401496703205376');
    fireEvent.click(screen.getByText('Use parameter grid values'));
    expect(change).toHaveBeenCalledWith(props.parameters);
    await act(async () => rerender(<Component {...props} plan={nativePlan} source={source + ' AND 1=1'} />));
    expect(screen.queryByText('Use parameter grid values')).toBeNull();
  });
  it('rejects unsafe bindings and invalidates drafts when external JSON or dialect changes', async () => {
    const props = {source, dialect: 3, plan: nativePlan, parameters: '[9007199254740993]', onChange: jest.fn(), onPrepare: jest.fn()};
    const {rerender} = render(<Component {...props} />);
    fireEvent.click(await screen.findByText('Initialize parameter grid from bindings'));
    expect(screen.getByText('Use exact text for fractional or large numeric values.')).toBeVisible();
    expect(props.onChange).not.toHaveBeenCalled();
    rerender(<Component {...props} parameters="[]" />);
    fireEvent.click(screen.getByText('Initialize parameter grid from bindings'));
    expect(screen.getByText('Use parameter grid values')).toBeVisible();
    rerender(<Component {...props} parameters="[1]" />);
    expect(screen.queryByText('Use parameter grid values')).toBeNull();
    rerender(<Component {...props} dialect={1} />);
    await waitFor(() => expect(screen.queryByText('Initialize parameter grid from bindings')).toBeNull());
  });
  it('maps actual native encodings without guessing names or structured types', () => {
    expect(parameterKind({native_type: 'INT64', scale: -4})).toBe('decimal');
    expect(parameterKind({native_type: 'VARYING', charset: 1})).toBe('binary');
    expect(parameterKind({native_type: 'BOOLEAN'})).toBe('boolean');
    expect(parameterKind({native_type: 'TIME_TZ'})).toBe('firebird-time-tz');
    expect(parameterKind({native_type: 'ARRAY'})).toBe('json');
  });
});
