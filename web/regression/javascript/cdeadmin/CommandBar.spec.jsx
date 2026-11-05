/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The tabbed command bar in CDEadmin (2026-11-05): built from the main menus,
// running their callbacks, styled from the appearance settings, customized
// per account.

import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {PgAdminProvider} from 'sources/PgAdminProvider';
import AppNotebookBar from 'sources/AppNotebookBar';
import CommandBarCustomizer from
  'sources/cdeadmin_ui/customization/CommandBarCustomizer';
import {buildCommandBarModel} from 'sources/cdeadmin_ui/shell/commandBarModel';
import {COMMAND_BAR_THEME, commandBarMode} from
  'sources/cdeadmin_ui/shell/commandBarSettings';
import {CUSTOMIZATION_SCHEMA} from 'sources/scratch_notebookbar';
import usePreferences from '../../../pgadmin/preferences/static/js/store';

function item(label, extra={}) {
  return {label, name: label.toLowerCase().replace(/\W+/g, '_'),
    callback: jest.fn(), isDisabled: false, getMenuItems: () => undefined, ...extra};
}
const separator = {type: 'separator', getMenuItems: () => undefined};

// Like the real menus, each menu returns the same item objects every call.
function menu(name, label, entries) {
  return {name, label, getMenuItems: () => entries};
}

function menus() {
  const exportItems = [item('CSV'), item('JSON', {isDisabled: true})];
  return [
    menu('file', 'File', [
      item('New project', {commandId: 'project.create'}), item('Open'),
      item('Save'), item('Save as'), separator,
      item('Export', {getMenuItems: () => exportItems}), separator,
      item('Quit', {toolbarSize: 'large'}),
    ]),
    menu('view', 'View', [
      item('Show status bar', {checked: true}),
      item('Unavailable', {isDisabled: true}),
    ]),
    menu('empty', 'Empty', []),
  ];
}

describe('command bar model from the main menus', () => {
  it('maps menus to tabs, separators to groups and items to controls', () => {
    const source = menus();
    const {model, state, catalog, run} = buildCommandBarModel(source);
    expect(model.tabs.map((tab) => tab.id)).toEqual(['file', 'view']);
    const [first, second, third] = model.tabs[0].groups;
    // Small controls stack three high.
    expect(first.controls.map((control) => control.type)).toEqual(['stack', 'button']);
    expect(first.controls[0].controls.map((control) => control.id))
      .toEqual(['project.create', 'open', 'save']);
    expect(second.controls[0]).toMatchObject({type: 'menu', label: 'Export'});
    expect(second.controls[0].items.map((entry) => entry.disabled)).toEqual([false, true]);
    expect(third.controls[0]).toMatchObject({type: 'button', size: 'large', label: 'Quit'});
    // Rightmost groups fold first.
    expect(model.tabs[0].groups.map((group) => group.priority)).toEqual([-0, -1, -2]);
    const view = model.tabs[1].groups[0].controls[0].controls;
    expect(view[0]).toMatchObject({type: 'toggle'});
    expect(state[view[0].id]).toEqual({enabled: true, checked: true});
    expect(state[view[1].id]).toEqual({enabled: false});
    expect(Object.keys(catalog)).toContain('project.create');

    expect(run('project.create')).toBe(true);
    expect(source[0].getMenuItems()[0].callback).toHaveBeenCalled();
    const exportControl = second.controls[0];
    expect(run(exportControl.command, {item: exportControl.items[0].id})).toBe(true);
    expect(run(exportControl.command, {item: exportControl.items[1].id})).toBe(false);
    expect(run(view[1].id)).toBe(false);
  });

  it('splits long runs into groups, names groups and paths commands', () => {
    const many = Array.from({length: 14}, (_unused, index) => item(`Tool ${index}`));
    const exportItems = [item('CSV')];
    const {model, catalog} = buildCommandBarModel([menu('tools', 'Tools',
      [...many, separator, item('Export', {getMenuItems: () => exportItems})])]);
    const groups = model.tabs[0].groups;
    expect(groups.map((group) => group.id)).toEqual(['tools.g0', 'tools.g1', 'tools.g2']);
    expect(groups[0].controls.flatMap((control) => control.controls ?? [control]))
      .toHaveLength(12);
    expect(groups[0]).toMatchObject({label: '', title: 'Tool 0, Tool 1, …'});
    expect(groups[1].title).toBe('Tool 12, Tool 13');
    expect(catalog.tool_0.detail).toBe('Tools');
    expect(catalog.csv.detail).toBe('Tools › Export');
  });

  it('reads the bar mode setting, defaulting to the menu bar', () => {
    expect(commandBarMode({})).toBe('menu');
    expect(commandBarMode({accessibility_command_bar: 'notebook'})).toBe('notebook');
    expect(commandBarMode({accessibility_command_bar: 'other'})).toBe('menu');
  });
});

function setPreferences(customization='') {
  usePreferences.setState({data: [{id: 1, cid: 2, mid: 3, module: 'browser',
    name: 'command_bar_customization', value: customization}],
  version: Date.now(), isLoading: false, failed: false,
  setPreferences: jest.fn(async () => ({}))});
}

function renderBar(source) {
  const events = {on: jest.fn(), off: jest.fn()};
  const pgAdmin = {Browser: {MainMenus: source, Events: events,
    utils: {userMenuInfo: null}}};
  render(<PgAdminProvider value={pgAdmin}><AppNotebookBar /></PgAdminProvider>);
  return {events};
}

describe('AppNotebookBar', () => {
  beforeEach(() => setPreferences());

  it('shows the menus as tabs and runs commands through their callbacks', () => {
    const source = menus();
    const {events} = renderBar(source);
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent))
      .toEqual(['File', 'View']);
    fireEvent.click(screen.getByRole('button', {name: 'Open'}));
    expect(source[0].getMenuItems()[1].callback).toHaveBeenCalled();
    expect(events.on).toHaveBeenCalledWith('pgadmin:refresh-app-menu',
      expect.any(Function));
    const wrapper = document.querySelector('[data-test="app-command-bar"]');
    expect(wrapper.style.getPropertyValue('--snb-font-size'))
      .toBe(COMMAND_BAR_THEME['--snb-font-size']);
  });

  it('applies the saved customization', () => {
    setPreferences(JSON.stringify({schema: CUSTOMIZATION_SCHEMA,
      tabs: {file: {label: 'Start'}, view: {hidden: true}}, added: [],
      quickAccess: ['save']}));
    renderBar(menus());
    expect(screen.getAllByRole('tab').map((tab) => tab.textContent)).toEqual(['Start']);
    const quick = screen.getByRole('toolbar', {name: 'Quick access'});
    expect(within(quick).getByRole('button', {name: 'Save'})).toBeInTheDocument();
  });
});

describe('Customize Tabbed Bar dialog', () => {
  beforeEach(() => setPreferences());

  it('saves the customization to the account', async () => {
    const onClose = jest.fn();
    const Dialog = withTheme(CommandBarCustomizer);
    render(<Dialog menus={menus()} onClose={onClose} />);
    fireEvent.click(within(screen.getByRole('listbox', {name: 'Tabs'}))
      .getByRole('checkbox', {name: 'Show View'}));
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(onClose).toHaveBeenCalled());
    const [[records]] = usePreferences.getState().setPreferences.mock.calls;
    expect(records[0]).toMatchObject({name: 'command_bar_customization', mid: 3});
    expect(JSON.parse(records[0].value).tabs.view.hidden).toBe(true);
  });

  it('reports a refused save and stays open', async () => {
    usePreferences.setState({setPreferences: jest.fn(async () => {
      throw Object.assign(new Error('x'),
        {response: {data: {errormsg: 'The command bar customization is not valid.'}}});
    })});
    const onClose = jest.fn();
    const Dialog = withTheme(CommandBarCustomizer);
    render(<Dialog menus={menus()} onClose={onClose} />);
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    expect(await screen.findByText('The command bar customization is not valid.'))
      .toBeInTheDocument();
    expect(onClose).not.toHaveBeenCalled();
  });
});
