/////////////////////////////////////////////////////////////
// ScratchRobin welcome page and workspace launcher tests.
/////////////////////////////////////////////////////////////

import {fireEvent, render, screen, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import WelcomeDashboard from '../../../pgadmin/dashboard/static/js/WelcomeDashboard';
import {WorkbenchShell} from 'sources/cdeadmin_ui/shell/WorkbenchShell';

const activities = [
  {id: 'activity.data', label: 'Data Explorer',
    iconKey: 'tool.data-explorer'},
  {id: 'activity.projects', label: 'Project Explorer',
    iconKey: 'tool.project-explorer'},
  {id: 'activity.disabled', label: 'Unavailable Workspace',
    iconKey: 'tool.query', disabled: true},
];

describe('ScratchRobin welcome dashboard', () => {
  beforeEach(() => window.localStorage.clear());

  it('uses the product identity and requested description', () => {
    const Component = withTheme(WorkbenchShell);
    render(<Component activities={activities} navigationViews={{}}>
      <WelcomeDashboard pgBrowser={{}} />
    </Component>);

    expect(screen.getByRole('heading', {
      name: 'ScratchRobin CDE Administrator', level: 1,
    })).toBeInTheDocument();
    expect(screen.getByText('A data management and business intelligence tool. ' +
      'A part of the ScratchBird CDE family of products.')).toBeInTheDocument();
    expect(document.querySelector(
      '.WelcomeDashboard-welcomeLogo svg'
    )).toBeInTheDocument();
  });

  it('shows every registered activity as a large named launcher', () => {
    const Component = withTheme(WorkbenchShell);
    render(<Component activities={activities} navigationViews={{
      'activity.projects': <div>Project content</div>,
    }}><WelcomeDashboard pgBrowser={{}} /></Component>);

    const launchers = document.querySelector(
      '[data-cdeadmin-qa-key="dashboard.welcome.workspace-launchers"]'
    );
    const workspaceLaunchers = within(launchers);
    expect(launchers.querySelectorAll('button')).toHaveLength(activities.length);
    expect(workspaceLaunchers.getByRole('button', {
      name: 'Data Explorer',
    }).querySelector(
      '[data-icon-key="tool.data-explorer"]')).toBeInTheDocument();
    expect(workspaceLaunchers.getByRole('button', {
      name: 'Unavailable Workspace',
    }))
      .toBeDisabled();

    fireEvent.click(workspaceLaunchers.getByRole('button', {
      name: 'Project Explorer',
    }));
    expect(within(screen.getByRole('navigation', {
      name: 'Application activities',
    })).getByRole('button', {name: 'Project Explorer'}))
      .toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('complementary', {name: 'Project Explorer'}))
      .toHaveTextContent('Project content');
  });

  it('uses the ScratchRobin and ScratchBird icons for documentation', () => {
    const Component = withTheme(WorkbenchShell);
    render(<Component activities={activities} navigationViews={{}}>
      <WelcomeDashboard pgBrowser={{}} />
    </Component>);

    expect(screen.getByRole('link', {name: 'ScratchRobin Documentation'})
      .querySelector('[data-icon-key="tool.scratchrobin"]'))
      .toBeInTheDocument();
    expect(screen.getByRole('link', {name: 'ScratchBird Documentation'})
      .querySelector('[data-icon-key="engine.scratchbird"]'))
      .toBeInTheDocument();
  });

  it('exposes System Administration & Settings launchers for Engines, Security, Users, Menus & Schemes', () => {
    const events = [];
    const onOpenPrefs = (e) => events.push(e.detail);
    window.addEventListener('scratchrobin:open-preferences', onOpenPrefs);

    try {
      const Component = withTheme(WorkbenchShell);
      render(<Component activities={activities} navigationViews={{}}>
        <WelcomeDashboard pgBrowser={{}} />
      </Component>);

      const settingsGrid = document.querySelector(
        '[data-cdeadmin-qa-key="dashboard.welcome.system-settings"]'
      );
      expect(settingsGrid).toBeInTheDocument();
      const scope = within(settingsGrid);

      fireEvent.click(scope.getByRole('button', {name: 'Database Engines (On / Off)'}));
      fireEvent.click(scope.getByRole('button', {name: 'Security & Application Access'}));
      fireEvent.click(scope.getByRole('button', {name: 'Users, Roles & Groups'}));
      fireEvent.click(scope.getByRole('button', {name: 'Menus, Toolbars & Icons'}));
      fireEvent.click(scope.getByRole('button', {name: 'Colour Schemes & Fonts'}));

      expect(events.map((d) => d.sectionId)).toEqual([
        'engines:connectors',
        'security:apps',
        'security:users',
        'actions:global-menus',
        'appearance:schemes',
      ]);
    } finally {
      window.removeEventListener('scratchrobin:open-preferences', onOpenPrefs);
    }
  });
});
