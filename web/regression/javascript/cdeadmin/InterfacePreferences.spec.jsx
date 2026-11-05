/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2026, The ScratchBird Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The interface designer is part of Preferences (owner direction
// 2026-11-05): artwork, menus and commands, the tabbed bar and interface
// profiles are Preferences pages, with Appearance and accessibility beside
// them. Replaces the former Interface Designer form's tests.

import {useState} from 'react';
import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import pgAdmin from 'sources/pgadmin';
import {commandRegistry} from 'sources/cdeadmin_ui/commands/CommandRegistry';
import {InterfacePreferencesProvider} from
  'sources/cdeadmin_ui/customization/interfaceDrafts';
import {
  APPEARANCE_PREFERENCES_ID, DESIGNER_PREFERENCES_ID, InterfacePreferenceEditor,
  PREFERENCES_SECTION_EVENT, interfacePreferenceCategories,
  interfacePreferenceMatches, requestPreferencesSection,
  takePendingPreferencesSection,
} from 'sources/cdeadmin_ui/customization/InterfacePreferences';
import {readAppearance} from 'sources/cdeadmin_ui/customization/appearance';
import LeftTree from '../../../pgadmin/preferences/static/js/components/LeftTree';
import RightPreference from
  '../../../pgadmin/preferences/static/js/components/RightPreference';

function preferenceData() {
  const appearance = Object.entries({...readAppearance({}), theme: 'light',
    appearance_presets: ''}).map(([name, value], index) => ({
    id: index + 1, cid: 1, mid: 1, module: 'misc', name, value}));
  return [...appearance,
    {id: 100, cid: 2, mid: 2, module: 'browser', name: 'icon_assignments',
      value: '{"schema":"cdeadmin.icon-assignments.v1","assignments":{}}'},
    {id: 101, cid: 2, mid: 2, module: 'browser', name: 'menu_customizations',
      value: '{"schema":"cdeadmin.menu-customization.v1","menus":{}}'},
    {id: 102, cid: 2, mid: 2, module: 'browser', name: 'command_customizations',
      value: '{}'},
    {id: 103, cid: 2, mid: 2, module: 'browser', name: 'command_bar_customization',
      value: ''},
  ];
}

const written = () => usePreferences.getState().setPreferences.mock.calls
  .flatMap(([records]) => records);

function Pages({initial}) {
  const [page, setPage] = useState(initial);
  return <InterfacePreferencesProvider>
    {['artwork', 'menus', 'profiles', 'command-bar'].map((editor) =>
      <button type="button" key={editor} onClick={() => setPage(editor)}>
        {`Go ${editor}`}</button>)}
    <InterfacePreferenceEditor item={{editor: page}} />
  </InterfacePreferencesProvider>;
}

function renderPages(initial='artwork') {
  const Component = withTheme(Pages);
  return render(<Component initial={initial} />);
}

describe('Preferences interface pages', () => {
  beforeEach(() => {
    usePreferences.setState({data: preferenceData(), version: 1,
      isLoading: false, failed: false, setPreferences: jest.fn(async () => ({}))});
    if(!commandRegistry.has('test.interface-designer.command')) {
      commandRegistry.register({id: 'test.interface-designer.command',
        label: 'Designer test command', iconKey: 'action.open',
        surfaces: ['tools'], execute: jest.fn()});
    }
    pgAdmin.Browser = {...pgAdmin.Browser, MainMenus: [{name: 'file', label: 'File',
      getMenuItems: () => [{label: 'Open', name: 'open', callback: jest.fn(),
        isDisabled: false, getMenuItems: () => undefined}]}]};
  });

  it('adds two categories to the Preferences tree, with searchable pages', () => {
    const [appearance, designer] = interfacePreferenceCategories();
    expect(appearance.id).toBe(APPEARANCE_PREFERENCES_ID);
    expect(appearance.children.map((child) => child.name)).toEqual(expect.arrayContaining(
      ['Profile and presets', 'Text and fonts', 'Colours', 'Menu and activity bar']));
    expect(designer.id).toBe(DESIGNER_PREFERENCES_ID);
    expect(designer.children.map((child) => child.name)).toEqual(
      ['Artwork and icons', 'Menus and commands', 'Tabbed bar', 'Interface profiles']);
    const tabbed = designer.children[2];
    expect(interfacePreferenceMatches(tabbed, '')).toBe(true);
    expect(interfacePreferenceMatches(tabbed, 'ribbon')).toBe(true);
    expect(interfacePreferenceMatches(tabbed, 'kerberos')).toBe(false);
    // Section fields are searchable by their labels.
    expect(interfacePreferenceMatches(appearance.children.find((child) =>
      child.key === 'menus'), 'activity bar width')).toBe(true);
  });

  it('keeps an open-at request until Preferences takes it', () => {
    const seen = jest.fn();
    window.addEventListener(PREFERENCES_SECTION_EVENT, seen);
    requestPreferencesSection(`${DESIGNER_PREFERENCES_ID}-command-bar`);
    window.removeEventListener(PREFERENCES_SECTION_EVENT, seen);
    expect(seen).toHaveBeenCalled();
    expect(takePendingPreferencesSection()).toBe(`${DESIGNER_PREFERENCES_ID}-command-bar`);
    expect(takePendingPreferencesSection()).toBeNull();
  });

  it('shows artwork assignments and saves the designer customization', async () => {
    renderPages('artwork');
    expect(screen.getByRole('heading', {name: 'Artwork and icon assignments'}))
      .toBeInTheDocument();
    expect(screen.getByLabelText('Icon preview')).toBeInTheDocument();
    const save = screen.getByRole('button', {name: 'Save interface customization'});
    expect(save).toBeDisabled();
    fireEvent.change(screen.getByLabelText('Find semantic icon'),
      {target: {value: 'action.open'}});
    // Text queries: the full icon and command catalogs make role queries slow.
    fireEvent.click(screen.getByText('action.open').closest('button'));
    expect(screen.getByRole('heading', {level: 3})).toHaveTextContent('Open');
    // A change on another page of the designer is saved from this one.
    fireEvent.click(screen.getByText('Go menus'));
    fireEvent.change(screen.getByLabelText('New menu ID'), {target: {value: 'lab'}});
    fireEvent.click(screen.getByText('Add menu'));
    fireEvent.click(screen.getByText('Go artwork'));
    fireEvent.click(screen.getByText('Save interface customization'));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(
      'Interface customization saved'));
    const names = written().map((record) => record.name);
    expect(names).toEqual(expect.arrayContaining(['icon_assignments',
      'menu_customizations']));
    expect(names.some((name) => name.startsWith('accessibility_'))).toBe(false);
    expect(JSON.parse(written().find((record) =>
      record.name === 'menu_customizations').value).menus.lab).toBeDefined();
  }, 60000);

  it('stores a chosen artwork assignment', async () => {
    // jsdom has no layout; a tall window keeps MUI's popover-fit check quiet.
    const height = window.innerHeight;
    Object.defineProperty(window, 'innerHeight', {value: 100000, configurable: true});
    try {
      renderPages('artwork');
      fireEvent.change(screen.getByLabelText('Find semantic icon'),
        {target: {value: 'action.open'}});
      fireEvent.click(screen.getByText('action.open').closest('button'));
      fireEvent.mouseDown(screen.getByRole('combobox',
        {name: 'Assigned catalog artwork'}));
      const options = within(screen.getByRole('listbox')).getAllByRole('option');
      const chosen = options.find((option) =>
        option.textContent.endsWith('— action.settings'));
      fireEvent.click(chosen);
      fireEvent.click(screen.getByText('Save interface customization'));
      await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(
        'Interface customization saved'));
      const record = written().find((item) => item.name === 'icon_assignments');
      expect(JSON.parse(record.value).assignments).toEqual(
        {'action.open': 'action.settings'});
    } finally {
      Object.defineProperty(window, 'innerHeight', {value: height, configurable: true});
    }
  }, 60000);

  it('adds and removes user menus and keeps the change across pages', () => {
    renderPages('menus');
    expect(screen.getByText('Designer test command')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('New menu ID'), {target: {value: 'research'}});
    fireEvent.change(screen.getByLabelText('New menu label'), {target: {value: 'Research'}});
    fireEvent.click(screen.getByRole('button', {name: 'Add menu'}));
    expect(screen.getByRole('button', {name: 'Research'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Go artwork'}));
    fireEvent.click(screen.getByRole('button', {name: 'Go menus'}));
    fireEvent.click(screen.getByRole('button', {name: 'Research'}));
    fireEvent.click(screen.getByRole('button', {name: 'Remove custom menu'}));
    expect(screen.queryByRole('button', {name: 'Research'})).not.toBeInTheDocument();
  });

  it('stages the packaged profile and writes its appearance only when saved', async () => {
    renderPages('profiles');
    fireEvent.click(screen.getByRole('button', {name: 'Restore packaged defaults'}));
    expect(usePreferences.getState().setPreferences).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent('Packaged defaults are staged');
    fireEvent.click(screen.getByRole('button', {name: 'Save interface customization'}));
    await waitFor(() => expect(usePreferences.getState().setPreferences)
      .toHaveBeenCalledTimes(2));
    const appearance = usePreferences.getState().setPreferences.mock.calls[0][0];
    expect(appearance).toEqual(expect.arrayContaining([
      expect.objectContaining({name: 'accessibility_profile'}),
      expect.objectContaining({name: 'accessibility_ui_scale', value: -1}),
    ]));
    const names = appearance.map((record) => record.name);
    expect(names).not.toContain('theme');
    expect(names).not.toContain('accessibility_command_bar');
  });

  it('saves the tabbed bar customization from its page', async () => {
    renderPages('command-bar');
    fireEvent.click(within(screen.getByRole('listbox', {name: 'Tabs'}))
      .getByRole('checkbox', {name: 'Show File'}));
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(screen.getByRole('status'))
      .toHaveTextContent('Tabbed bar saved.'));
    const [record] = written();
    expect(record.name).toBe('command_bar_customization');
    expect(JSON.parse(record.value).tabs.file.hidden).toBe(true);
  });
});

describe('Preferences tree and pane with interface pages', () => {
  const tree = () => [...interfacePreferenceCategories(), {id: '1', name: 'Browser',
    key: 'browser', children: [{id: '1_2', name: 'Display', key: 'display'}]}];

  // The tree view settles asynchronously after rendering.
  const settle = () => act(async () => {});

  it('lists interface pages without preference fields and filters them by search', async () => {
    const setSelectedItem = jest.fn();
    const Tree = withTheme(LeftTree);
    const {rerender} = render(<Tree prefTreeData={tree()} selectedItem={null}
      setSelectedItem={setSelectedItem} filteredList={[{parentId: '1_2'}]} searchVal="" />);
    await settle();
    expect(screen.getByText('Interface designer')).toBeInTheDocument();
    expect(screen.getByText('Display')).toBeInTheDocument();
    rerender(<Tree prefTreeData={tree()} selectedItem={null}
      setSelectedItem={setSelectedItem} filteredList={[]} searchVal="ribbon" />);
    await settle();
    expect(screen.getByText('Tabbed bar')).toBeInTheDocument();
    expect(screen.queryByText('Display')).not.toBeInTheDocument();
    expect(screen.queryByText('Colours')).not.toBeInTheDocument();
  });

  it('keeps a page opened on request selected', async () => {
    const requested = tree()[1].children[2];
    const setSelectedItem = jest.fn();
    const Tree = withTheme(LeftTree);
    render(<Tree prefTreeData={tree()} selectedItem={requested}
      setSelectedItem={setSelectedItem} filteredList={[{parentId: '1_2'}]} searchVal="" />);
    await settle();
    expect(setSelectedItem).not.toHaveBeenCalled();
  });

  it('shows the page editor instead of preference fields', () => {
    usePreferences.setState({data: preferenceData(), version: 2,
      isLoading: false, failed: false, setPreferences: jest.fn(async () => ({}))});
    const Component = withTheme(() => <InterfacePreferencesProvider>
      <RightPreference schema={{schemaFields: [], categoryUpdated: jest.fn()}}
        initValues={{}} filteredItemIds={[]} onDataChange={jest.fn()}
        setSelectedItem={jest.fn()} selectedItem={tree()[1].children[3]} />
    </InterfacePreferencesProvider>);
    render(<Component />);
    expect(screen.getByRole('heading', {name: 'Interface profiles'})).toBeInTheDocument();
    expect(document.querySelector('[data-cdeadmin-preferences-editor="profiles"]'))
      .toBeInTheDocument();
  });
});
