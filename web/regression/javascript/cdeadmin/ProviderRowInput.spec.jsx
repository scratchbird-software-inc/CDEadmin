import {render, screen, fireEvent} from '@testing-library/react';
import ProviderRowInput, {rowInputDraft, rowInputValue} from
  '../../../pgadmin/static/js/Dialogs/ProviderRowInput';

describe('Provider scalar inputs', () => {
  let originalHeight;
  beforeEach(() => {
    originalHeight = window.innerHeight;
    window.innerHeight = 1200;
  });
  afterEach(() => { window.innerHeight = originalHeight; });
  it.each(['null', 'true', 'false', '0012', '{"a":1}', '', 'λ'])('preserves text %s', (text) => {
    expect(rowInputValue(rowInputDraft(text), 'text')).toBe(text);
  });
  it.each(['', 'AP9/', 'AA=='])('round trips binary %s', (data) => {
    const value = {encoding: 'base64', data, byte_length: atob(data).length};
    expect(rowInputValue(rowInputDraft(value, 'binary'), 'binary')).toEqual(value);
  });
  it.each(['AA', 'AR==', 'λ', 'AA==\n', '%%%'])('rejects noncanonical binary %s', (data) => {
    expect(() => rowInputValue({text: data, isNull: false}, 'binary')).toThrow(/Base64/);
  });
  it('keeps empty binary and NULL distinct', () => {
    expect(rowInputValue(rowInputDraft(null, 'binary'), 'binary')).toBeNull();
    expect(rowInputValue(rowInputDraft('', 'binary'), 'binary')).toEqual({
      encoding: 'base64', data: '', byte_length: 0,
    });
  });
  it.each([
    ['integer', '170141183460469231731687303715884105727'],
    ['integer', '-9223372036854775808'],
    ['decimal', '12345678901234567890.123456789012345678'],
    ['decimal', '1.234567890123456789e-20'],
  ])('does not round %s %s', (kind, text) => {
    expect(rowInputValue(rowInputDraft(text), kind)).toBe(text);
  });
  it.each(['text', 'integer', 'decimal', 'boolean'])('separates %s NULL', (kind) => {
    expect(rowInputValue(rowInputDraft(null), kind)).toBeNull();
  });
  it.each([['integer', '1.2'], ['integer', ''], ['decimal', 'bad'], ['boolean', '']])('rejects invalid %s %s', (kind, value) => {
    expect(() => rowInputValue(rowInputDraft(value), kind)).toThrow();
  });
  it.each([true, false])('preserves boolean %s', (value) => {
    expect(rowInputValue(rowInputDraft(value), 'boolean')).toBe(value);
  });
  it.each(['NaN', 'sNaN', 'Infinity', '-Infinity', '+Infinity',
    '12345678901234567890.12345678901234', '1.234567890123456789e-200'])('preserves DECFLOAT %s', (value) => {
    expect(rowInputValue(rowInputDraft(value), 'decfloat')).toBe(value);
  });
  it.each(['NaN', 'Infinity', 'sNaN'])('does not admit DECFLOAT special %s for fixed point', (value) => {
    expect(() => rowInputValue(rowInputDraft(value), 'decimal')).toThrow();
  });
  it.each(['NaN', 'nan', 'Infinity', '-Infinity', 'inf', '-inf', '-0.0', '1.7976931348623157e308', '2.2250738585072014e-308'])('tags float %s without JS numeric coercion', (value) => {
    expect(rowInputValue(rowInputDraft(value, 'float64'), 'float64')).toEqual({
      encoding: 'float64', data: value,
    });
  });
  it.each(['sNaN', 'NaN(1)', '1_2', ' 1'])('rejects invalid float %s', (value) => {
    expect(() => rowInputValue(rowInputDraft(value), 'float32')).toThrow();
  });
  it('uses a separate NULL selector without losing the text draft', () => {
    const changed = jest.fn();
    const {rerender} = render(<ProviderRowInput kind="text" label="value"
      draft={rowInputDraft('null')} onChange={changed} />);
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'value mode'}));
    fireEvent.click(screen.getByRole('option', {name: 'NULL'}));
    expect(changed).toHaveBeenLastCalledWith({text: 'null', isNull: true});
    rerender(<ProviderRowInput kind="text" label="value"
      draft={{text: 'null', isNull: true}} onChange={changed} />);
    expect(screen.getByRole('textbox', {name: 'value'})).toBeDisabled();
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'value mode'}));
    fireEvent.click(screen.getByRole('option', {name: 'Value'}));
    expect(changed).toHaveBeenLastCalledWith({text: 'null', isNull: false});
  });
  it('keeps disabled Boolean and NULL controls disabled', () => {
    render(<ProviderRowInput kind="boolean" label="value" disabled
      draft={rowInputDraft(false)} onChange={jest.fn()} />);
    for (const control of screen.getAllByRole('combobox')) {
      expect(control).toHaveAttribute('aria-disabled', 'true');
    }
  });
});


describe('Firebird zoned drafts', () => {
  it.each(['firebird-time-tz', 'firebird-timestamp-tz'])('keeps %s UTC and region', (kind) => {
    const value = {encoding: kind, utc: kind === 'firebird-time-tz' ? '12:34:56.000100' : '2025-11-02 06:30:00.000100', time_zone: 'America/New_York'};
    expect(rowInputValue(rowInputDraft(value, kind), kind)).toEqual(value);
    expect(rowInputValue(rowInputDraft(JSON.stringify(value), kind), kind)).toEqual(value);
    const spec = {bounds: [[-1, -1]], element_kind: kind};
    expect(rowInputValue(rowInputDraft([value], 'array'), 'array', spec)).toEqual([value]);
    expect(rowInputValue(rowInputDraft([JSON.stringify(value)], 'array'), 'array', spec)).toEqual([value]);
  });
  it.each(['{}', 'null', '[]', '{"encoding":"firebird-time-tz","utc":"12:00:00","time_zone":"UTC","extra":1}'])('rejects invalid draft %s', (text) => {
    expect(() => rowInputValue({text, isNull: false}, 'firebird-time-tz')).toThrow();
  });
});
