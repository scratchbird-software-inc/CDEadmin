import {useState} from 'react';
import {render, screen, fireEvent, waitFor} from '@testing-library/react';
import ProviderArrayInput, {arrayCoordinates, newArray} from '../../../pgadmin/static/js/Dialogs/ProviderArrayInput';
import {rowInputDraft, rowInputValue} from '../../../pgadmin/static/js/Dialogs/ProviderRowInput';

const spec = {bounds: [[-1, 0], [3, 4]], element_kind: 'integer', scale: 0};
function Editor({initial, specification = spec, disabled = false}) {
  const [draft, setDraft] = useState(rowInputDraft(initial, 'array'));
  return <><ProviderArrayInput draft={draft} spec={specification} label="A" disabled={disabled} onChange={setDraft} />
    <output data-testid="draft">{JSON.stringify(draft)}</output></>;
}

describe('Native coordinate array editor', () => {
  let originalHeight;
  beforeEach(() => { originalHeight = window.innerHeight; window.innerHeight = 1200; });
  afterEach(() => { window.innerHeight = originalHeight; });
  it('retains non-one-based coordinates and initializes independent dimensions', () => {
    expect([0, 1, 2, 3].map((n) => arrayCoordinates(n, spec))).toEqual([[-1, 3], [-1, 4], [0, 3], [0, 4]]);
    const value = newArray(spec);
    value[0][0] = '9';
    expect(value).toEqual([['9', '0'], ['0', '0']]);
  });
  it.each(['integer', 'decimal', 'float32', 'float64'])('retains exact %s lexical elements', (kind) => {
    const value = [['9223372036854775807', '-0'], ['1', '2']];
    expect(rowInputValue(rowInputDraft(value, 'array'), 'array', {...spec, element_kind: kind})).toEqual(value);
  });
  it.each([[], [1, 2], [[1], [2]], [[null, 1], [2, 3]], [['bad', '1'], ['2', '3']]].map((value) => [value]))('rejects malformed array %j', (value) => {
    expect(() => rowInputValue(rowInputDraft(value, 'array'), 'array', spec)).toThrow();
  });
  it('preserves NULL separately from elements', () => {
    expect(rowInputValue(rowInputDraft(null, 'array'), 'array', spec)).toBeNull();
  });
  it('edits a native coordinate without rounding or touching its siblings', () => {
    render(<Editor initial={[[1, 2], [3, 4]]} />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    fireEvent.change(screen.getByRole('textbox', {name: 'A [-1, 4]'}), {target: {value: '170141183460469231731687303715884105727'}});
    const draft = JSON.parse(screen.getByTestId('draft').textContent);
    expect(rowInputValue(draft, 'array', spec)).toEqual([['1', '170141183460469231731687303715884105727'], ['3', '4']]);
  });
  it('initializes NULL arrays deliberately', () => {
    render(<Editor initial={null} />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    fireEvent.click(screen.getByRole('button', {name: 'Initialize array'}));
    expect(JSON.parse(screen.getByTestId('draft').textContent)).toEqual({text: '[["0","0"],["0","0"]]', isNull: false});
  });
  it('pages element controls without losing edited values', () => {
    render(<Editor initial={Array.from({length: 30}, (_, n) => n)} specification={{...spec, bounds: [[-10, 19]]}} />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    expect(screen.getAllByRole('textbox')).toHaveLength(25);
    fireEvent.change(screen.getByRole('textbox', {name: 'A [-10]'}), {target: {value: '9007199254740993'}});
    fireEvent.click(screen.getByRole('button', {name: 'Next elements'}));
    expect(screen.getAllByRole('textbox')).toHaveLength(5);
    fireEvent.click(screen.getByRole('button', {name: 'Previous elements'}));
    expect(screen.getByRole('textbox', {name: 'A [-10]'}).value).toBe('9007199254740993');
  });
  it('disables writes while permitting inspection', () => {
    render(<Editor initial={[[1, 2], [3, 4]]} disabled />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    expect(screen.getAllByRole('textbox').every((input) => input.disabled)).toBe(true);
  });
  it('uses native Boolean controls and payloads', () => {
    const booleanSpec = {...spec, element_kind: 'boolean', bounds: [[0, 0]]};
    render(<Editor initial={[false]} specification={booleanSpec} />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'A [0]'}));
    fireEvent.click(screen.getByRole('option', {name: 'True'}));
    expect(rowInputValue(JSON.parse(screen.getByTestId('draft').textContent), 'array', booleanSpec)).toEqual([true]);
  });
  it('guards oversized initialization explicitly', () => {
    expect(() => newArray({...spec, bounds: [[0, 100000]]})).toThrow(/100,000/);
  });
  it('closes with Escape and retains the uncommitted draft on reopening', async () => {
    render(<Editor initial={[[1, 2], [3, 4]]} />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    fireEvent.change(screen.getByRole('textbox', {name: 'A [-1, 3]'}), {target: {value: '9'}});
    fireEvent.keyDown(screen.getByRole('dialog'), {key: 'Escape', code: 'Escape'});
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    expect(screen.getByRole('textbox', {name: 'A [-1, 3]'}).value).toBe('9');
  });
  it('restores elements after toggling the whole-array NULL state', () => {
    render(<Editor initial={[[1, 2], [3, 4]]} />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'A mode'}));
    fireEvent.click(screen.getByRole('option', {name: 'NULL'}));
    expect(screen.getAllByRole('textbox').every((input) => input.disabled)).toBe(true);
    expect(rowInputValue(JSON.parse(screen.getByTestId('draft').textContent), 'array', spec)).toBeNull();
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'A mode'}));
    fireEvent.click(screen.getByRole('option', {name: 'Value'}));
    expect(rowInputValue(JSON.parse(screen.getByTestId('draft').textContent), 'array', spec)).toEqual([['1', '2'], ['3', '4']]);
  });
  it('refuses unsafe numeric wire values instead of silently accepting rounding', () => {
    expect(() => rowInputValue(rowInputDraft([[9007199254740992, 1], [2, 3]], 'array'), 'array', spec)).toThrow(/text/);
  });
  it('retains signed zero and subnormal floating-point text', () => {
    const value = [['-0.0', '1.401298464324817e-45'], ['0.0', '1e-30']];
    expect(rowInputValue(rowInputDraft(value, 'array'), 'array', {...spec, element_kind: 'float32'})).toEqual(value);
  });
  it.each(['NaN', '-NaN', 'sNaN', '-sNaN', 'Infinity', '-Infinity', '-0',
    '1e-6176', '9.999999999999999999999999999999999e6144'])('retains DECFLOAT array text %s', (text) => {
    const value = [[text, '0'], ['1', '2']];
    expect(rowInputValue(rowInputDraft(value, 'array'), 'array', {...spec, element_kind: 'decfloat'})).toEqual(value);
  });
  it.each([16, 34])('shows native DECFLOAT precision %s and edits special values', (precision) => {
    const specification = {...spec, element_kind: 'decfloat', precision};
    render(<Editor initial={[['0', '1'], ['2', '3']]} specification={specification} />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    expect(screen.getByText(`Element type: decfloat(${precision}); Scale: 0`)).toBeInTheDocument();
    fireEvent.change(screen.getByRole('textbox', {name: 'A [-1, 3]'}), {target: {value: 'sNaN'}});
    expect(rowInputValue(JSON.parse(screen.getByTestId('draft').textContent), 'array', specification)[0][0]).toBe('sNaN');
  });
  it.each([
    ['date', '0001-01-01', '2000-01-01'],
    ['time', '23:59:59.9999', '00:00:00'],
    ['timestamp', '0001-01-01 12:34:56.0001', '2000-01-01 00:00:00'],
  ])('initializes and edits native %s text without JS Date conversion', (element_kind, text, initial) => {
    const specification = {...spec, element_kind};
    expect(newArray(specification)).toEqual([[initial, initial], [initial, initial]]);
    render(<Editor initial={null} specification={specification} />);
    fireEvent.click(screen.getByRole('button', {name: /A \[/}));
    fireEvent.click(screen.getByRole('button', {name: 'Initialize array'}));
    fireEvent.change(screen.getByRole('textbox', {name: 'A [-1, 3]'}), {target: {value: text}});
    expect(rowInputValue(JSON.parse(screen.getByTestId('draft').textContent), 'array', specification)[0][0]).toBe(text);
  });
  it.each([
    ['date', '20000101'], ['date', '2000-01-01Z'], ['time', '12:00:00.00001'],
    ['time', '12:00:00+01:00'], ['timestamp', '2000-01-01'],
    ['timestamp', '2000-01-01 12:00:00Z'],
  ])('rejects %s lexical loss %s', (element_kind, text) => {
    expect(() => rowInputValue(rowInputDraft([[text, text], [text, text]], 'array'), 'array', {...spec, element_kind})).toThrow(/ISO/);
  });
});
