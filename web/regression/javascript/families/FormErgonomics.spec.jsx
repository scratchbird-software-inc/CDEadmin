/*
 * Form ergonomics (owner review of docs/notes, 2026-10-31): help text is not
 * an error; errors wait for an edit or an apply attempt; one click plans and
 * applies unless the plan must be read first; wide grids keep six columns
 * inline with a details drawer; operation dialogs ask for a typed name once
 * and show only user-facing text; Enter in a picker does not submit.
 */
import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Theme from 'sources/Theme';
import {FieldControl, ObjectEditor, OperationDialog, RecordGrid} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {gridColumns, MAX_INLINE_COLUMNS} from '../../../pgadmin/static/js/cdeadmin_ui/objects/RecordGrid';
import {MAX_CHECKBOX_CHOICES, showsChoicesAsCheckboxes} from '../../../pgadmin/static/js/cdeadmin_ui/objects/FieldControl';
import {enterSubmits} from '../../../pgadmin/static/js/cdeadmin_ui/overlays/Dialog';
import {validateDraft, initialDraft} from '../../../pgadmin/static/js/cdeadmin_ui/objects/descriptors';
import {getSystemTimeZone} from '../../../pgadmin/static/js/cdeadmin_ui/objects/smartFieldDefaults';
import {
  computeCellGridLayout,
  estimateFieldNaturalWidth,
} from '../../../pgadmin/static/js/cdeadmin_ui/objects/formCellLayout';
import {navigatorTabIdsForNodeType} from '../../../pgadmin/static/js/BrowserComponent';
import {resolveStatisticsUrl} from '../../../pgadmin/misc/statistics/static/js/Statistics';
import {loadEngineBundle} from './familyFixtures';

const READY = {plan_id: 'p1', state: 'ready', execution_available: true,
  command_preview: {statements: [{source: 'CREATE TABLE t'}]}};

function simpleForm() {
  const field = (values) => ({tab: 'General', ...values});
  return {family: 'table', family_title: 'Table', status: 'complete', resource_kinds: ['table'],
    family_tabs: ['General', 'SQL'], tabs: [
      {tab: 'General', title: 'General', nested: [], fields: [
        field({field_id: 'name', label: 'Name', control: 'text', required: true}),
        field({field_id: 'owner', label: 'Owner', control: 'reference', help: 'Who owns it'}),
      ]},
      {tab: 'SQL', title: 'SQL', primitive: 'sql_preview', fields: []},
    ]};
}

function editor(props) {
  return render(<Theme><ObjectEditor form={simpleForm()} mode="create" resourceKind="table" autoPlan={false}
    onClose={() => {}} {...props} /></Theme>);
}

describe('pickers', () => {
  it('show help in the normal colour and keep the required marker', () => {
    render(<Theme><FieldControl field={{field_id: 'owner', label: 'Owner', control: 'reference', required: true,
      help: 'Who owns it'}} value={null} onChange={() => {}} /></Theme>);
    const input = screen.getByRole('combobox');
    expect(input.getAttribute('aria-invalid')).toBe('false');
    expect(input.required).toBe(true);
    expect(screen.getByText('Who owns it')).toBeTruthy();
  });

  it('turn red only for an error', () => {
    // 2026-11-05: a short fixed list now renders as checkboxes (see
    // 'short fixed choices' below), so this picker test uses a list one
    // longer than that limit to keep testing the picker.
    const options = Array.from({length: MAX_CHECKBOX_CHOICES + 1}, (_item, index) =>
      ({value: `o${index}`, label: `o${index}`}));
    render(<Theme><FieldControl field={{field_id: 'owner', label: 'Owner', control: 'multiselect', help: 'h',
      options}} value={[]} error="Owner is required." onChange={() => {}} /></Theme>);
    expect(screen.getByRole('combobox').getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByText('Owner is required.')).toBeTruthy();
  });
});

describe('short fixed choices', () => {
  const FLAGS = [{value: 'IGNORE_CHECKSUMS', label: 'Ignore checksums'},
    {value: 'IGNORE_LIMBO', label: 'Ignore limbo transactions'},
    {value: 'METADATA_ONLY', label: 'Only metadata'}];
  const flags = (extra={}) => ({field_id: 'backup_flags', label: 'Backup options', control: 'multiselect',
    help: 'Native gbak switches.', options: FLAGS, ...extra});

  it('show every option as a checkbox in a labelled group', () => {
    render(<Theme><FieldControl field={flags({required: true})} value={['IGNORE_LIMBO']} onChange={() => {}} /></Theme>);
    const group = screen.getByRole('group', {name: 'Backup options *'});
    expect(screen.queryByRole('combobox')).toBeNull();
    const boxes = within(group).getAllByRole('checkbox');
    expect(boxes.map((box) => box.checked)).toEqual([false, true, false]);
    expect(within(group).getByLabelText('Ignore limbo transactions').checked).toBe(true);
    const help = screen.getByText('Native gbak switches.');
    expect(group.getAttribute('aria-describedby')).toBe(help.id);
  });

  it('send the chosen values in option order and drop a value no option offers', () => {
    const onChange = jest.fn();
    render(<Theme><FieldControl field={flags()} value={['METADATA_ONLY', 'NOT_OFFERED']} onChange={onChange} /></Theme>);
    fireEvent.click(screen.getByLabelText('Ignore checksums'));
    expect(onChange).toHaveBeenLastCalledWith(['IGNORE_CHECKSUMS', 'METADATA_ONLY']);
    fireEvent.click(screen.getByLabelText('Only metadata'));
    expect(onChange).toHaveBeenLastCalledWith([]);
  });

  it('mark the group invalid and show the error', () => {
    render(<Theme><FieldControl field={flags()} value={[]} error="Choose at least one." onChange={() => {}} /></Theme>);
    const group = screen.getByRole('group', {name: 'Backup options'});
    expect(group.getAttribute('aria-invalid')).toBe('true');
    expect(screen.getByText('Choose at least one.')).toBeTruthy();
  });

  it('disable every checkbox when the field is disabled', () => {
    render(<Theme><FieldControl field={flags()} value={[]} disabled onChange={() => {}} /></Theme>);
    expect(screen.getAllByRole('checkbox').every((box) => box.disabled)).toBe(true);
  });

  it('keep the picker in a grid cell, for runtime choices and for long lists', () => {
    expect(showsChoicesAsCheckboxes(flags())).toBe(true);
    expect(showsChoicesAsCheckboxes(flags(), true)).toBe(false);
    expect(showsChoicesAsCheckboxes(flags({options: undefined, option_values_path: ['draft', 'columns']}))).toBe(false);
    expect(showsChoicesAsCheckboxes(flags({options: Array.from({length: MAX_CHECKBOX_CHOICES + 1},
      (_item, index) => ({value: index, label: String(index)}))}))).toBe(false);
    render(<Theme><FieldControl field={flags()} value={[]} inGrid onChange={() => {}} /></Theme>);
    expect(screen.getByRole('combobox')).toBeTruthy();
  });

  it('keep the picker for a multiselect column of a record grid', () => {
    const {field_id: _id, label: _label, ...column} = flags();
    const field = {field_id: 'rows', label: 'Rows', control: 'grid',
      columns: [{field_id: 'name', label: 'Name', control: 'text'}, {field_id: 'flags', label: 'Flags', ...column}]};
    render(<Theme><RecordGrid field={field} rows={[{name: 'a', flags: []}]} onChange={() => {}} /></Theme>);
    const table = screen.getByRole('table', {name: 'Rows'});
    expect(within(table).queryAllByRole('checkbox')).toEqual([]);
    expect(within(table).getByRole('combobox', {name: 'Flags (row 1)'})).toBeTruthy();
  });
});

describe('object editor', () => {
  it('shows no field error on a new form, and every error once apply is tried', async () => {
    const plan = jest.fn(async () => READY);
    editor({plan, apply: jest.fn()});
    expect(screen.queryByText('Name is required.')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Apply'}));
    await waitFor(() => expect(screen.getByText('1 field(s) need attention.')).toBeTruthy());
    expect(screen.getByText('Name is required.')).toBeTruthy();
    expect(plan).not.toHaveBeenCalled();
  });

  it('plans and applies in one click', async () => {
    const plan = jest.fn(async () => READY);
    const apply = jest.fn(async () => ({ok: true}));
    editor({plan, apply});
    fireEvent.change(screen.getByRole('textbox', {name: /Name/}), {target: {value: 't'}});
    fireEvent.click(screen.getByRole('button', {name: 'Apply'}));
    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(apply.mock.calls[0][0].plan).toBe(READY);
  });

  it.each([
    ['asks for confirmation', {confirmation_required: true}],
    ['carries warnings', {warnings: ['Unloading stops the listing.']}],
  ])('stops on the SQL tab when the plan %s', async (_label, extra) => {
    const plan = jest.fn(async () => ({...READY, ...extra}));
    const apply = jest.fn();
    editor({plan, apply});
    fireEvent.change(screen.getByRole('textbox', {name: /Name/}), {target: {value: 't'}});
    fireEvent.click(screen.getByRole('button', {name: 'Apply'}));
    await waitFor(() => expect(screen.getByRole('tabpanel', {name: 'SQL'})).toBeTruthy());
    expect(apply).not.toHaveBeenCalled();
  });

  it('offers Reset once the draft changes', () => {
    editor({plan: jest.fn(), apply: jest.fn()});
    expect(screen.queryByRole('button', {name: 'Reset'})).toBeNull();
    const name = screen.getByRole('textbox', {name: /Name/});
    fireEvent.change(name, {target: {value: 't'}});
    fireEvent.click(screen.getByRole('button', {name: 'Reset'}));
    expect(screen.getByRole('textbox', {name: /Name/}).value).toBe('');
  });

  it('shows one constraint section at a time', () => {
    const form = loadEngineBundle('mysql').forms.table;
    render(<Theme><ObjectEditor form={form} mode="create" resourceKind="table" autoPlan={false}
      plan={jest.fn()} apply={jest.fn()} onClose={() => {}} /></Theme>);
    fireEvent.click(screen.getByRole('tab', {name: 'Constraints'}));
    const sections = screen.getByRole('tablist', {name: 'Constraints sections'});
    const names = within(sections).getAllByRole('tab').map((tab) => tab.textContent);
    expect(names.length).toBeGreaterThan(1);
    const panel = screen.getByRole('tabpanel', {name: 'Constraints'});
    expect(within(panel).getAllByRole('region').length).toBe(1);
    fireEvent.click(within(sections).getByRole('tab', {name: names[1]}));
    expect(within(panel).getByRole('region', {name: names[1]})).toBeTruthy();
  });
});

describe('record grid', () => {
  const columns = Array.from({length: 9}, (_value, index) => ({field_id: `c${index}`, label: `C${index}`,
    control: 'text'}));

  it('keeps hidden and inapplicable columns out, and six columns inline', () => {
    const all = [...columns, {field_id: 'internal', label: 'Internal', control: 'text', hidden: true},
      {field_id: 'cond', label: 'Cond', control: 'text', visible_when: {field: 'c0', equals: 'x'}}];
    const {inline, detail} = gridColumns(all, [{c0: 'y'}]);
    expect(inline.map((column) => column.field_id)).toEqual(['c0', 'c1', 'c2', 'c3', 'c4', 'c5']);
    expect(inline.length).toBe(MAX_INLINE_COLUMNS);
    expect(detail.map((column) => column.field_id)).toEqual(['c6', 'c7', 'c8']);
    expect(gridColumns(all, [{c0: 'x'}]).detail.map((column) => column.field_id)).toContain('cond');
  });

  it('does not report a required hidden column the user cannot fill', () => {
    const form = {tabs: [{tab: 'Columns', fields: [{field_id: 'cols', label: 'Columns', control: 'grid',
      columns: [{field_id: 'name', label: 'Name', control: 'text', required: true},
        {field_id: 'oid', label: 'Oid', control: 'text', required: true, hidden: true}]}]}]};
    expect(validateDraft(form, {cols: [{name: 'a'}]})).toEqual({});
    expect(validateDraft(form, {cols: [{}]})).toEqual({'cols[0].name': 'Name is required in row 1.'});
  });

  it('opens the rest in a row drawer and marks cell errors', () => {
    const field = {field_id: 'cols', label: 'Columns', control: 'grid', columns};
    render(<Theme><RecordGrid field={field} rows={[{c0: 'a'}]} onChange={() => {}}
      cellErrors={{'cols[0].c7': 'C7 is required in row 1.'}} /></Theme>);
    const table = screen.getByRole('table', {name: 'Columns'});
    expect(within(table).getAllByRole('columnheader').map((cell) => cell.textContent)).toEqual(
      ['#', 'C0', 'C1', 'C2', 'C3', 'C4', 'C5', 'Actions']);
    fireEvent.click(screen.getByRole('button', {name: 'Details (3)'}));
    expect(screen.getByRole('textbox', {name: 'C7 (row 1)'})).toBeTruthy();
    expect(screen.getByText('C7 is required in row 1.')).toBeTruthy();
  });
});

describe('operation dialog', () => {
  const dropPartition = {operation_id: 'drop_partition', resource_kind: 'table', title: 'Drop partition',
    tier: 2, confirmation: 'typed_name', notes: 'Round-tripped by tools/tests/x.py',
    description: 'Drops one partition and its rows.',
    fields: [{field_id: 'confirmation', label: 'Table name', control: 'text', required: true}]};

  function dialog(operation, plan, apply) {
    return render(<Theme><OperationDialog open operation={operation} targetName="orders" plan={plan}
      apply={apply} onClose={() => {}} /></Theme>);
  }

  it('asks for the typed name once and shows the description, not the notes', () => {
    dialog(dropPartition, jest.fn(), jest.fn());
    expect(screen.queryByRole('textbox', {name: /^Table name/})).toBeNull();
    expect(screen.getByRole('textbox', {name: 'Type orders to confirm'})).toBeTruthy();
    expect(screen.getByText('Drops one partition and its rows.')).toBeTruthy();
    expect(screen.queryByText(/Round-tripped by/)).toBeNull();
  });

  it('says when the operation is a draft', () => {
    dialog({...dropPartition, status: 'draft'}, jest.fn(), jest.fn());
    expect(screen.getByText(/This operation is a draft/)).toBeTruthy();
  });

  it('previews and runs in one click, sending the typed name as the confirmation', async () => {
    const plan = jest.fn(async () => READY);
    const apply = jest.fn(async () => ({ok: true}));
    dialog(dropPartition, plan, apply);
    fireEvent.change(screen.getByRole('textbox', {name: 'Type orders to confirm'}), {target: {value: 'orders'}});
    fireEvent.click(screen.getByRole('button', {name: 'Preview and run'}));
    await waitFor(() => expect(apply).toHaveBeenCalledTimes(1));
    expect(plan.mock.calls[0][0].draft.confirmation).toBe('orders');
  });

  it('stops to show a plan that carries warnings', async () => {
    const plan = jest.fn(async () => ({...READY, warnings: ['Read this first.']}));
    const apply = jest.fn();
    dialog({...dropPartition, confirmation: 'confirm', fields: []}, plan, apply);
    fireEvent.click(screen.getByRole('button', {name: 'Preview and run'}));
    await waitFor(() => expect(screen.getByText('Read this first.')).toBeTruthy());
    expect(apply).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Run'})).toBeTruthy();
  });
});

describe('Enter', () => {
  const event = (element) => ({target: element});
  it('submits from a text input but not from a picker, button or text area', () => {
    const input = document.createElement('input');
    const combobox = document.createElement('input');
    combobox.setAttribute('role', 'combobox');
    expect(enterSubmits(event(input))).toBe(true);
    expect(enterSubmits(event(combobox))).toBe(false);
    expect(enterSubmits(event(document.createElement('button')))).toBe(false);
    expect(enterSubmits(event(document.createElement('textarea')))).toBe(false);
  });
});

describe('free-text controls of provider-native forms (browser pass 2026-11-12)', () => {
  it('edits a multiline comment instead of showing it as unsupported', () => {
    const onChange = jest.fn();
    render(<Theme><FieldControl field={{field_id: 'description', label: 'Comment', control: 'multiline'}}
      value="" onChange={onChange} /></Theme>);
    const box = screen.getByLabelText('Comment');
    expect(box.disabled).toBe(false);
    expect(box.value).toBe('');
    expect(screen.queryByText(/Unsupported control/)).toBeNull();
    fireEvent.change(box, {target: {value: 'a note'}});
    expect(onChange).toHaveBeenCalledWith('a note');
  });

  it('edits a json value as text the provider parses', () => {
    const onChange = jest.fn();
    render(<Theme><FieldControl field={{field_id: 'options', label: 'Options', control: 'json'}}
      value={{a: 1}} onChange={onChange} /></Theme>);
    const box = screen.getByLabelText('Options');
    expect(box.disabled).toBe(false);
    expect(JSON.parse(box.value)).toEqual({a: 1});
    fireEvent.change(box, {target: {value: '{"a": 2}'}});
    expect(onChange).toHaveBeenCalledWith('{"a": 2}');
  });
});

describe('compact pop-below hints, sample placeholders and OS defaults (2026-11-13)', () => {
  it('renders field help as a non-error pop-below element and validation errors with data-error="true"', () => {
    const {rerender} = render(<Theme><FieldControl
      field={{field_id: 'port', label: 'Server port', control: 'number', help: 'TCP port of the server.', placeholder: 'e.g. 3050'}}
      value={3050} onChange={() => {}} /></Theme>);
    const helpNode = screen.getByText('TCP port of the server.');
    expect(helpNode.classList.contains('sr-field-help')).toBe(true);
    expect(helpNode.getAttribute('data-error')).toBeNull();
    expect(screen.getByRole('spinbutton', {name: 'Server port'}).getAttribute('placeholder')).toBe('e.g. 3050');

    rerender(<Theme><FieldControl
      field={{field_id: 'port', label: 'Server port', control: 'number', help: 'TCP port of the server.'}}
      value="" error="Server port is required." onChange={() => {}} /></Theme>);
    const errNode = screen.getByText('Server port is required.');
    expect(errNode.getAttribute('data-error')).toBe('true');
  });

  it('autopopulates OS local time zone on session_time_zone and offers a combobox dropdown of other time zones', () => {
    const fbServerForm = loadEngineBundle('firebird').forms.server;
    const draft = initialDraft(fbServerForm);
    const osTz = getSystemTimeZone();
    expect(draft.session_time_zone).toBe(osTz);
    expect(draft.charset).toBe('UTF8');

    const tzField = fbServerForm.tabs
      .flatMap((t) => t.fields)
      .find((f) => f.field_id === 'session_time_zone');
    const onChange = jest.fn();
    render(<Theme><FieldControl field={tzField} value={draft.session_time_zone} onChange={onChange} /></Theme>);
    const combo = screen.getByRole('combobox', {name: /Session time zone/i});
    expect(combo.value).toBe(osTz);
    fireEvent.focus(combo);
    const listbox = screen.getByRole('listbox');
    expect(within(listbox).getByRole('option', {name: 'UTC'})).toBeTruthy();
    fireEvent.mouseDown(within(listbox).getByRole('option', {name: 'UTC'}));
    expect(onChange).toHaveBeenCalledWith('UTC');
  });
});

describe('datatype-sized dynamic cell packing and selection-scoped tabs (2026-11-13)', () => {
  it('packs fields into average-sized cells and leaves trailing cells empty when the next field exceeds remaining space', () => {
    // 9 fields whose average natural width is 200px => 1 cell = 200px.
    // Field 1 = 250px (1.25 cells -> spans cells 1..2), Field 2 = 100px (0.5 cells -> fits in cell 3),
    // Field 3 = 200px (1.0 cell -> starts on row 2, cell 1).
    const fields = [
      {field_id: 'f1', width_px: 250},
      {field_id: 'f2', width_px: 100},
      {field_id: 'f3', width_px: 200},
      {field_id: 'f4', width_px: 200},
      {field_id: 'f5', width_px: 200},
      {field_id: 'f6', width_px: 200},
      {field_id: 'f7', width_px: 250},
      {field_id: 'f8', width_px: 200},
      {field_id: 'f9', width_px: 200},
    ];
    // 3 cells of 200px + 2 gaps of 16px = 632px available width => 3 columns.
    const layout = computeCellGridLayout(fields, 640, {}, {colGap: 16});
    expect(layout.cellWidth).toBe(200);
    expect(layout.numCols).toBe(3);
    expect(layout.placements[0]).toMatchObject({colStart: 1, span: 2, row: 1, gridColumn: '1 / span 2'});
    expect(layout.placements[1]).toMatchObject({colStart: 3, span: 1, row: 1, gridColumn: '3 / span 1'});
    expect(layout.placements[2]).toMatchObject({colStart: 1, span: 1, row: 2, gridColumn: '1 / span 1'});

    // When field 2 also requires >1 cell (e.g. 250px = 1.25 cells -> span 2), cell 3 on row 1 is left empty
    // and field 2 starts on row 2 at cell 1.
    const widerSecond = [
      {field_id: 'f1', width_px: 250},
      {field_id: 'f2', width_px: 250},
      {field_id: 'f3', width_px: 100},
      {field_id: 'f4', width_px: 200},
      {field_id: 'f5', width_px: 200},
      {field_id: 'f6', width_px: 200},
      {field_id: 'f7', width_px: 200},
      {field_id: 'f8', width_px: 200},
      {field_id: 'f9', width_px: 200},
    ];
    const wrapped = computeCellGridLayout(widerSecond, 640, {}, {colGap: 16});
    expect(wrapped.numCols).toBe(3);
    expect(wrapped.placements[0]).toMatchObject({colStart: 1, span: 2, row: 1, gridColumn: '1 / span 2'});
    expect(wrapped.placements[1]).toMatchObject({colStart: 1, span: 2, row: 2, gridColumn: '1 / span 2'});
    expect(wrapped.placements[2]).toMatchObject({colStart: 3, span: 1, row: 2, gridColumn: '3 / span 1'});
  });

  it('sizes fields according to their datatype and renders prose code comments as a textarea', () => {
    const portWidth = estimateFieldNaturalWidth({field_id: 'port', label: 'Port', control: 'number'});
    const hostWidth = estimateFieldNaturalWidth({field_id: 'host', label: 'Server host', control: 'text'});
    const pathWidth = estimateFieldNaturalWidth(
      {field_id: 'database_root', label: 'Approved database creation root', control: 'text'}
    );
    expect(portWidth).toBeLessThan(hostWidth);
    expect(hostWidth).toBeLessThan(pathWidth);

    const fbServerForm = loadEngineBundle('firebird').forms.server;
    const commentField = fbServerForm.tabs
      .flatMap((t) => t.fields)
      .find((f) => f.field_id === 'comment');
    render(<Theme><FieldControl field={commentField} value="" onChange={() => {}} /></Theme>);
    expect(screen.getByRole('textbox', {name: /Comments/i}).tagName).toBe('TEXTAREA');
  });

  it('hides Connectors, SQL, Dependencies and Dependents on servers and resolves provider statistics URLs', () => {
    expect(navigatorTabIdsForNodeType('server_group')).toEqual(['connectors']);
    expect(navigatorTabIdsForNodeType('engine_type')).toEqual(['properties', 'statistics']);
    expect(navigatorTabIdsForNodeType('localhost_placeholder')).toEqual(['properties', 'statistics']);
    expect(navigatorTabIdsForNodeType('server')).toEqual(['properties', 'statistics']);
    expect(navigatorTabIdsForNodeType('cde_database_target')).toEqual(['properties', 'statistics']);
    expect(navigatorTabIdsForNodeType('database')).toEqual(['properties', 'sql', 'statistics']);

    expect(resolveStatisticsUrl(
      {_type: 'engine_type', engine_id: 'firebird'},
      {server_group: {_id: 1}},
      {hasStatistics: true}
    )).toBe('/browser/engine_type/stats/1/firebird');
    expect(resolveStatisticsUrl(
      {_type: 'server', _id: 7},
      {server_group: {_id: 1}},
      {hasStatistics: true}
    )).toBe('/browser/server/stats/1/7');
    expect(resolveStatisticsUrl(
      {_type: 'cde_database_target', _id: 'emp_target', _pid: 7},
      {server_group: {_id: 1}, server: {_id: 7}},
      {hasStatistics: true}
    )).toBe('/browser/server/stats/1/7?database_target_id=emp_target');
  });
});
