/////////////////////////////////////////////////////////////
// CDEadmin main dock tab identity and presentation tests.
/////////////////////////////////////////////////////////////

import {render, screen} from '@testing-library/react';
import Theme from 'sources/Theme';
import {
  dockTabIconKey, ToolTabTitle, WorkspaceController,
} from 'sources/cdeadmin_ui/workspace/Workspace';
import rcdockOverride from 'sources/Theme/overrides/rcdock.override';

describe('CDEadmin main dock tab switcher', () => {
  it('maps product, help, and tool tabs to semantic non-PostgreSQL icons', () => {
    expect(dockTabIconKey({id: 'id-dashboard', title: 'ScratchRobin'}))
      .toBe('tool.scratchrobin');
    expect(dockTabIconKey({id: 'help', title: 'Help'})).toBe('action.help');
    expect(dockTabIconKey({id: 'sql', title: 'SQL'})).toBe('tool.query');
    expect(dockTabIconKey({icon: 'pg-font-icon icon-terminal'}))
      .toBe('action.terminal');
    expect(dockTabIconKey({icon: 'pg-font-icon icon-server'}))
      .toBe('command.default');
  });

  it('stores a semantic icon on every dock panel', () => {
    const home = WorkspaceController.getPanel({
      id: 'id-dashboard', title: 'ScratchRobin', group: 'playground',
    });
    const unknown = WorkspaceController.getPanel({
      id: 'tool-unknown', title: 'Provider utility', group: 'playground',
    });
    expect(home.internal.iconKey).toBe('tool.scratchrobin');
    expect(unknown.internal.iconKey).toBe('command.default');
  });

  it('renders a tool icon with the tab name and omits the product logo', () => {
    const {unmount} = render(<Theme><ToolTabTitle id="sql" defaultInternal={{
      title: 'SQL', iconKey: 'tool.query', closable: false,
    }} /></Theme>);
    expect(screen.getByText('SQL')).toBeInTheDocument();
    expect(document.querySelector('[data-icon-key="tool.query"]'))
      .toBeInTheDocument();
    unmount();

    render(<Theme><ToolTabTitle id="id-dashboard" defaultInternal={{
      title: 'ScratchRobin', tooltip: 'ScratchRobin Dashboard',
      iconKey: 'tool.scratchrobin', closable: false,
    }} /></Theme>);
    expect(screen.getByText('ScratchRobin')).toBeInTheDocument();
    expect(document.querySelector('[data-icon-key="tool.scratchrobin"]'))
      .not.toBeInTheDocument();
    expect(document.querySelector('[data-cdeadmin-tab-id="id-dashboard"]'))
      .toBeInTheDocument();
  });

  it('fills the main dock bar with the active tab', () => {
    const theme = {
      custom: {icon: {contrastText: '#111'}},
      mixins: {panelBorder: {top: {}, bottom: {}}},
      otherVars: {activeBorder: '#00f', activeColor: '#00f',
        borderColor: '#999'},
      palette: {background: {default: '#fff'}, text: {primary: '#111'},
        primary: {main: '#00f', contrastText: '#fff'}},
      shape: {borderRadius: 0},
    };
    const layout = rcdockOverride(theme)['.dock-layout'];
    expect(layout['& .dock-bar'].flexShrink).toBe(0);
    expect(layout['& .dock-tab'].height).toBe('auto');
    const panel = layout['& .dock-panel'];
    expect(panel['&.dock-style-playground'][
      '& > .dock > .dock-bar:has(.dock-tab):not(:has(.dock-tab ~ .dock-tab))'
    ]).toEqual({display: 'none'});
    const main = panel['&.dock-style-playground']['&[data-dockid="id-main"]'];
    const tab = main['& > .dock > .dock-bar']['& .dock-tab'];
    expect(tab.filter).toBe(
      'brightness(var(--cde-inactive-brightness, 0.85))'
    );
    expect(tab.margin).toBe(0);
    expect(tab.height).toBe('100%');
    expect(main['& > .dock > .dock-bar']['& .dock-nav, & .dock-nav-wrap, & .dock-nav-list'].padding).toBe(0);
    expect(tab['&.dock-tab-active']).toMatchObject({
      backgroundColor: '#00f',
      color: '#fff',
      filter: 'none',
    });
  });
});
