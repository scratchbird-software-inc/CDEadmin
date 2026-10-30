/*
 * editable_after_create: false (form.schema.json) locks a field in alter
 * mode, and a grid column on the rows the record loaded, so an edit the
 * engine cannot apply is never offered and then silently left out.
 */
import {fireEvent, render, screen} from '@testing-library/react';
import Theme from 'sources/Theme';
import {ObjectEditor} from '../../../pgadmin/static/js/cdeadmin_ui/objects';
import {lockedCell} from '../../../pgadmin/static/js/cdeadmin_ui/objects/RecordGrid';

const FORM = {
  family: 'table', family_title: 'Table', family_tabs: ['General', 'SQL'],
  resource_kinds: ['table'],
  tabs: [
    {tab: 'General', title: 'General', primitive: 'group', fields: [
      {field_id: 'name', label: 'Name', control: 'text', required: true, editable_after_create: false},
      {field_id: 'note', label: 'Note', control: 'text'},
      {field_id: 'columns', label: 'Columns', control: 'grid', columns: [
        {field_id: 'name', label: 'Column', control: 'text'},
        {field_id: 'type', label: 'Type', control: 'text', editable_after_create: false},
      ]},
    ]},
    {tab: 'SQL', title: 'SQL', primitive: 'sql_preview', fields: []},
  ],
};

function editor(mode, record={}) {
  return render(<Theme><ObjectEditor form={FORM} mode={mode} resourceKind="table" record={record}
    plan={jest.fn()} apply={jest.fn()} onClose={() => {}} autoPlan={false} /></Theme>);
}

describe('editable_after_create', () => {
  it('locks only loaded rows in alter mode', () => {
    expect(lockedCell({editable_after_create: false}, {_id: '0'}, 'alter')).toBe(true);
    expect(lockedCell({editable_after_create: false}, {}, 'alter')).toBe(false);
    expect(lockedCell({editable_after_create: false}, {_id: '0'}, 'create')).toBe(false);
    expect(lockedCell({}, {_id: '0'}, 'alter')).toBe(false);
  });

  it('is editable when creating', () => {
    editor('create');
    expect(screen.getByLabelText(/^Name/)).not.toBeDisabled();
  });

  it('locks the field and existing cells, not new rows, when altering', () => {
    editor('alter', {name: 't', note: 'n', columns: [{name: 'id', type: 'INT8'}]});
    expect(screen.getByLabelText(/^Name/)).toBeDisabled();
    expect(screen.getByLabelText(/^Note/)).not.toBeDisabled();
    expect(screen.getByLabelText(/^Type \(row 1\)/)).toBeDisabled();
    expect(screen.getByLabelText(/^Column \(row 1\)/)).not.toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: /Add/}));
    expect(screen.getByLabelText(/^Type \(row 2\)/)).not.toBeDisabled();
  });
});
