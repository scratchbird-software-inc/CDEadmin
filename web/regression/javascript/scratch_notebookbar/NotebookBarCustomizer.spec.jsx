/////////////////////////////////////////////////////////////
//
// Scratch notebook bar: the customization form.
//
//////////////////////////////////////////////////////////////

import {useState} from 'react';
import {fireEvent, render, screen, within} from '@testing-library/react';
import {
  CUSTOMIZATION_SCHEMA, NotebookBarCustomizer, applyCustomization, normalizeModel,
} from 'sources/scratch_notebookbar';

const MODEL = {
  tabs: [
    {id: 'file', label: 'File', groups: [
      {id: 'open', label: 'Open', controls: [
        {id: 'new', label: 'New', command: 'file.new'}]},
      {id: 'close', label: 'Close', controls: [
        {id: 'quit', label: 'Quit', command: 'file.quit'}]},
    ]},
    {id: 'tools', label: 'Tools', groups: [
      {id: 'query', label: 'Query', controls: [
        {id: 'qt', label: 'Query tool', command: 'tools.query'}]},
    ]},
  ],
  quickAccess: [{id: 'save', label: 'Save', command: 'file.save'}],
};
const CATALOG = {
  'file.save': {label: 'Save'}, 'tools.query': {label: 'Query tool'},
  'tools.diff': {label: 'Schema diff'},
};

function Harness({onChange}) {
  const [document, setDocument] = useState(null);
  return <NotebookBarCustomizer model={MODEL} catalog={CATALOG}
    customization={document}
    onChange={(next) => { setDocument(next); onChange(next); }} />;
}

function setup() {
  const onChange = jest.fn();
  render(<Harness onChange={onChange} />);
  const last = () => onChange.mock.calls.at(-1)[0];
  const resolved = () => applyCustomization(normalizeModel(MODEL), last(), CATALOG);
  return {onChange, last, resolved};
}

const tabsList = () => screen.getByRole('listbox', {name: 'Tabs'});
const option = (list, name) => within(list).getAllByRole('option')
  .find((item) => item.textContent.includes(name));

describe('NotebookBarCustomizer', () => {
  it('hides, renames and reorders tabs and groups', () => {
    const {last, resolved} = setup();
    fireEvent.click(within(option(tabsList(), 'Tools'))
      .getByRole('checkbox', {name: 'Show Tools'}));
    expect(last().schema).toBe(CUSTOMIZATION_SCHEMA);
    expect(resolved().tabs.find((tab) => tab.id === 'tools').hidden).toBe(true);

    fireEvent.click(option(tabsList(), 'Tools'));
    fireEvent.click(screen.getAllByRole('button', {name: 'Move up'})[0]);
    expect(resolved().tabs.map((tab) => tab.id)).toEqual(['tools', 'file']);

    fireEvent.click(option(tabsList(), 'File'));
    fireEvent.change(screen.getAllByLabelText('Name')[0], {target: {value: 'Start'}});
    expect(resolved().tabs.find((tab) => tab.id === 'file').label).toBe('Start');

    const groups = screen.getByRole('listbox', {name: 'Groups in Start'});
    fireEvent.click(option(groups, 'Close'));
    fireEvent.click(screen.getAllByRole('button', {name: 'Move up'})[1]);
    expect(resolved().tabs.find((tab) => tab.id === 'file').groups
      .map((group) => group.id)).toEqual(['close', 'open']);
    fireEvent.click(within(option(groups, 'Open'))
      .getByRole('checkbox', {name: 'Show Open'}));
    expect(resolved().tabs.find((tab) => tab.id === 'file').groups
      .find((group) => group.id === 'open').hidden).toBe(true);
  });

  it('adds a tab and places catalogued commands in its group', () => {
    const {resolved} = setup();
    fireEvent.click(screen.getByRole('button', {name: 'Add tab'}));
    const commands = screen.getByRole('listbox', {name: 'Commands'});
    fireEvent.change(screen.getByRole('searchbox', {name: 'Find a command'}),
      {target: {value: 'diff'}});
    fireEvent.click(option(commands, 'Schema diff'));
    fireEvent.click(screen.getByRole('button', {name: 'Add to group'}));
    const added = resolved().tabs.find((tab) => tab.custom);
    expect(added.label).toBe('New tab');
    expect(added.groups[0].controls.map((control) => control.command))
      .toEqual(['tools.diff']);
    fireEvent.click(screen.getByRole('button', {name: 'Remove Schema diff'}));
    expect(resolved().tabs.find((tab) => tab.custom).groups[0].controls).toEqual([]);
    fireEvent.click(screen.getByRole('button', {name: 'Remove tab'}));
    expect(resolved().tabs.some((tab) => tab.custom)).toBe(false);
  });

  it('edits the quick-access commands and resets everything', () => {
    const {last, resolved} = setup();
    fireEvent.click(option(screen.getByRole('listbox', {name: 'Commands'}),
      'Query tool'));
    fireEvent.click(screen.getByRole('button', {name: 'Add to quick access'}));
    expect(last().quickAccess).toEqual(['file.save', 'tools.query']);
    fireEvent.click(screen.getByRole('button', {name: 'Move up Query tool'}));
    expect(resolved().quickAccess.map((control) => control.command))
      .toEqual(['tools.query', 'file.save']);
    fireEvent.click(screen.getByRole('button', {name: 'Remove Save'}));
    expect(last().quickAccess).toEqual(['tools.query']);
    fireEvent.click(screen.getByRole('button', {name: 'Restore the default bar'}));
    expect(last()).toEqual({schema: CUSTOMIZATION_SCHEMA, tabs: {}, added: []});
  });

  it('cannot place a command the host does not offer', () => {
    setup();
    expect(screen.getByRole('button', {name: 'Add to group'})).toBeDisabled();
    const names = within(screen.getByRole('listbox', {name: 'Commands'}))
      .getAllByRole('option').map((item) => item.textContent);
    expect(names).toEqual(['Query tool', 'Save', 'Schema diff']);
  });
});
