/////////////////////////////////////////////////////////////
// ScratchRobin Interface Designer interaction coverage.
/////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import usePreferences from '../../../pgadmin/preferences/static/js/store';
import InterfaceDesigner from
  'sources/cdeadmin_ui/customization/InterfaceDesigner';
import {commandRegistry} from 'sources/cdeadmin_ui/commands/CommandRegistry';

const APPEARANCE_NAMES = [
  'accessibility_profile', 'accessibility_density', 'accessibility_motion',
  'accessibility_ui_font_family', 'accessibility_monospace_font_family',
  'accessibility_ui_scale', 'accessibility_icon_scale',
  'accessibility_line_height', 'accessibility_letter_spacing',
  'accessibility_control_height', 'accessibility_target_size',
  'accessibility_target_spacing', 'accessibility_scrollbar_size',
  'accessibility_resize_handle_size', 'accessibility_panel_gap',
  'accessibility_tree_row_height', 'accessibility_tree_indent',
  'accessibility_tree_expander_size', 'accessibility_tree_guide_width',
  'accessibility_grid_row_height', 'accessibility_grid_header_height',
  'accessibility_grid_cell_padding', 'accessibility_tab_height',
  'accessibility_toolbar_height', 'accessibility_menu_row_height',
  'accessibility_menu_font_size', 'accessibility_activity_bar_width',
  'accessibility_activity_icon_size', 'accessibility_status_height', 'accessibility_corner_radius',
  'accessibility_active_tab_scale', 'accessibility_inactive_brightness',
  'accessibility_focus_width', 'accessibility_focus_offset',
  'accessibility_color_canvas', 'accessibility_color_panel',
  'accessibility_color_text', 'accessibility_color_muted_text',
  'accessibility_color_primary', 'accessibility_color_focus',
  'accessibility_color_border', 'accessibility_color_selection',
  'accessibility_color_success', 'accessibility_color_warning',
  'accessibility_color_error',
];

function preferenceData() {
  const appearance = APPEARANCE_NAMES.map((name, index)=>({
    id: index + 1, cid: 1, mid: 1, module: 'misc', name,
    value: name === 'accessibility_profile' ? 'cdeadmin_standard' :
      name === 'accessibility_density' || name === 'accessibility_motion' ?
        'profile' :
        name.includes('_color_') || name.includes('font_family') ? '' : -1,
  }));
  return [...appearance,
    {id: 100, cid: 2, mid: 2, module: 'browser', name: 'icon_assignments',
      value: '{"schema":"cdeadmin.icon-assignments.v1","assignments":{}}'},
    {id: 101, cid: 2, mid: 2, module: 'browser', name: 'menu_customizations',
      value: '{"schema":"cdeadmin.menu-customization.v1","menus":{}}'},
    {id: 102, cid: 2, mid: 2, module: 'browser', name: 'command_customizations',
      value: '{}'},
  ];
}

describe('ScratchRobin Interface Designer', () => {
  beforeEach(() => {
    usePreferences.setState({data: preferenceData(), version: 1,
      isLoading: false, failed: false, setPreferences: jest.fn(async ()=>({}))});
    if(!commandRegistry.has('test.interface-designer.command')) {
      commandRegistry.register({id: 'test.interface-designer.command',
        label: 'Designer test command', iconKey: 'action.open',
        surfaces: ['tools'], execute: jest.fn()});
    }
  });

  // 2026-11-05: appearance moved to View > Appearance and Accessibility
  // (AppearanceSettings.spec.jsx); the designer keeps artwork and menus.
  it('exposes artwork, menu, and command editors and points appearance elsewhere', () => {
    const Component = withTheme(InterfaceDesigner);
    render(<Component />);
    expect(screen.queryByRole('button', {name: 'Appearance'})).not.toBeInTheDocument();
    expect(screen.queryByLabelText('Interface font family')).not.toBeInTheDocument();
    expect(screen.getByText(/View > Appearance and Accessibility/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Artwork & icons'}));
    expect(screen.getByRole('heading', {name: 'Artwork and icon assignments'}))
      .toBeInTheDocument();
    expect(screen.getByLabelText('Find semantic icon')).toBeInTheDocument();
    expect(screen.getByLabelText('Icon preview')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Menus & commands'}));
    expect(screen.getByRole('heading', {name: 'Menus and commands'}))
      .toBeInTheDocument();
    expect(screen.getByText('Designer test command')).toBeInTheDocument();
  });

  it('adds and removes user menus without altering packaged menus', () => {
    const Component = withTheme(InterfaceDesigner);
    render(<Component />);
    fireEvent.click(screen.getByRole('button', {name: 'Menus & commands'}));
    fireEvent.change(screen.getByLabelText('New menu ID'), {
      target: {value: 'research'},
    });
    fireEvent.change(screen.getByLabelText('New menu label'), {
      target: {value: 'Research'},
    });
    fireEvent.click(screen.getByRole('button', {name: 'Add menu'}));
    expect(screen.getByRole('button', {name: 'Research'})).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Remove custom menu'}));
    expect(screen.queryByRole('button', {name: 'Research'}))
      .not.toBeInTheDocument();
  });

  it('saves catalog assignments without rewriting appearance', async () => {
    const Component = withTheme(InterfaceDesigner);
    render(<Component />);
    fireEvent.click(screen.getByRole('button', {name: 'Save profile'}));
    await waitFor(() => expect(screen.getByRole('status')).toHaveTextContent(
      'Interface profile saved'
    ));
    const written = usePreferences.getState().setPreferences.mock.calls
      .flatMap(([records]) => records.map((record) => record.name));
    expect(written.some((name) => name.startsWith('accessibility_'))).toBe(false);
    expect(written).toEqual(expect.arrayContaining(['icon_assignments']));
  });

  it('writes appearance restored from the packaged profile when saved', async () => {
    const Component = withTheme(InterfaceDesigner);
    render(<Component />);
    fireEvent.click(screen.getByRole('button', {name: 'Restore packaged defaults'}));
    fireEvent.click(screen.getByRole('button', {name: 'Save profile'}));
    await waitFor(() => expect(usePreferences.getState().setPreferences)
      .toHaveBeenCalledTimes(2));
    const appearance = usePreferences.getState().setPreferences.mock.calls[0][0];
    expect(appearance).toEqual(expect.arrayContaining([
      expect.objectContaining({name: 'accessibility_profile'}),
      expect.objectContaining({name: 'accessibility_ui_scale', value: -1}),
    ]));
    expect(appearance.map((record) => record.name)).not.toContain('theme');
    expect(appearance.map((record) => record.name))
      .not.toContain('accessibility_command_bar');
  });

  it('stages the packaged profile without changing preferences until saved', () => {
    const Component = withTheme(InterfaceDesigner);
    render(<Component />);
    const setter = usePreferences.getState().setPreferences;
    fireEvent.click(screen.getByRole('button', {
      name: 'Restore packaged defaults',
    }));
    expect(setter).not.toHaveBeenCalled();
    expect(screen.getByRole('status')).toHaveTextContent(
      'Packaged defaults are staged'
    );
  });
});
