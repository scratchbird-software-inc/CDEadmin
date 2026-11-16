/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {
  ProjectExplorer,
  buildProjectVirtualTree,
  canAssignProjectParent,
  collectDescendantProjectIds,
} from 'sources/cdeadmin_ui/projects/ProjectExplorer';
import {assetIcon} from 'sources/cdeadmin_ui/projects/ProjectNavigatorModel';

const projects = [{project_id: 'project-one', name: 'Project One', access: 'owner'}];
const state = {
  assets: [
    {
      asset_id: 'diagram-one',
      name: 'System diagram',
      path: 'diagrams/system.ddn',
      asset_type: 'ddn-workspace',
      version: 3,
      validation_state: 'valid',
      resource_bindings: [
        {kind: 'table', nativeIdentity: 'GL_ENTRY', resource_id: 'table:GL_ENTRY', bindingRole: 'owned'},
        {kind: 'view', nativeIdentity: 'VW_ERP_GL_TRIAL_BALANCE', resource_id: 'view:VW_ERP_GL_TRIAL_BALANCE', bindingRole: 'owned'},
        {kind: 'procedure', nativeIdentity: 'SP_COMPANY_FINANCIAL_SNAPSHOT', resource_id: 'procedure:SP_COMPANY_FINANCIAL_SNAPSHOT', bindingRole: 'owned'},
        {kind: 'package', nativeIdentity: 'PKG_FRAPPE_SUITE', resource_id: 'package:PKG_FRAPPE_SUITE', bindingRole: 'owned'},
        {kind: 'function', nativeIdentity: 'FN_DOCSTATUS_LABEL', resource_id: 'function:FN_DOCSTATUS_LABEL', bindingRole: 'owned'},
        {kind: 'sequence', nativeIdentity: 'SEQ_GL_ENTRY', resource_id: 'sequence:SEQ_GL_ENTRY', bindingRole: 'owned'},
      ],
    },
  ],
};

describe('Project Explorer / Project Navigator', () => {
  it('loads projects separately from assets, renders virtual levels, and opens the selected asset', async () => {
    const client = {listProjects: jest.fn().mockResolvedValue(projects),
      project: jest.fn().mockResolvedValue(state)};
    const onOpenAsset = jest.fn();
    const Component = withTheme(ProjectExplorer);
    render(<Component client={client} onOpenAsset={onOpenAsset} />);
    expect(await screen.findByText('Project One')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Expand Project One'}));
    expect(await screen.findByText('System diagram')).toBeInTheDocument();
    expect(screen.getByText('Tables')).toBeInTheDocument();
    expect(screen.getByText('Views')).toBeInTheDocument();
    expect(screen.getByText('Coding')).toBeInTheDocument();
    expect(screen.getByText('Screens')).toBeInTheDocument();
    expect(screen.getByText('Reports')).toBeInTheDocument();
    expect(screen.getByText('Tasks')).toBeInTheDocument();
    expect(screen.getByText('Calendars')).toBeInTheDocument();
    expect(screen.getByText('Channels')).toBeInTheDocument();
    expect(screen.getByText('Members')).toBeInTheDocument();
    expect(screen.getByText('Notes, Documents, Transcripts')).toBeInTheDocument();

    fireEvent.doubleClick(screen.getByRole('treeitem', {name: /System diagram/}));
    expect(onOpenAsset).toHaveBeenCalledWith(projects[0], state.assets[0]);
    expect(client.project).toHaveBeenCalledWith('project-one');
  });

  it('builds the complete virtual hierarchy including Coding, Reports, Tasks, Calendars, Channels, and Members', () => {
    const vtree = buildProjectVirtualTree(projects[0], state, [{project_id: 'sub-1', name: 'Sub Project'}]);
    const keys = vtree.map((v) => v.key);
    expect(keys).toEqual([
      'projects',
      'tables',
      'views',
      'coding',
      'screens',
      'reports',
      'tasks',
      'calendars',
      'channels',
      'members',
      'documents',
    ]);
    const coding = vtree.find((v) => v.key === 'coding');
    expect(coding.subgroups.map((s) => s.key)).toEqual([
      'procedures', 'packages', 'functions', 'sequences',
    ]);
    expect(coding.totalCount).toBe(4);

    const reports = vtree.find((v) => v.key === 'reports');
    expect(reports.subgroups.map((s) => s.key)).toEqual([
      'print', 'graphs', 'diagrams', 'pdf',
    ]);
    expect(reports.totalCount).toBe(1);

    const tasks = vtree.find((v) => v.key === 'tasks');
    expect(tasks.subgroups.map((s) => s.key)).toEqual([
      'pending', 'in_process', 'completed',
    ]);

    const calendars = vtree.find((v) => v.key === 'calendars');
    expect(calendars.subgroups.map((s) => s.key)).toEqual([
      'shared_personal', 'gantt',
    ]);

    const members = vtree.find((v) => v.key === 'members');
    expect(members.subgroups.map((s) => s.key)).toEqual([
      'groups', 'individuals',
    ]);
  });

  it('populates Area 3e workspace with auto-placing fields and virtual-spot item buttons when clicking virtual folders', async () => {
    const client = {listProjects: jest.fn().mockResolvedValue(projects),
      project: jest.fn().mockResolvedValue(state)};
    const TreeComp = withTheme(ProjectExplorer);
    render(
      <div>
        <TreeComp variant="tree" client={client} />
        <TreeComp variant="workspace" client={client} />
      </div>
    );
    await screen.findAllByText('Project One');
    expect(await screen.findByTestId('auto-placing-properties-grid')).toBeInTheDocument();
    expect(screen.getByTestId('virtual-group-buttons-grid')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Expand Project One'}));
    await screen.findByText('GL_ENTRY');
    fireEvent.click(screen.getByRole('treeitem', {name: /Tables/}));
    const grid = await screen.findByTestId('virtual-group-buttons-grid');
    expect(grid).toHaveTextContent('GL_ENTRY');
  });

  it('filters loaded authored assets by name, path, and type', async () => {
    const client = {listProjects: jest.fn().mockResolvedValue(projects),
      project: jest.fn().mockResolvedValue(state)};
    const Component = withTheme(ProjectExplorer);
    render(<Component client={client} />);
    await screen.findByText('Project One');
    fireEvent.click(screen.getByRole('button', {name: 'Expand Project One'}));
    await screen.findByText('System diagram');
    fireEvent.change(screen.getByLabelText('Filter projects and assets'),
      {target: {value: 'ddn-workspace'}});
    expect(screen.getByText('System diagram')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Filter projects and assets'),
      {target: {value: 'no-match'}});
    expect(screen.queryByText('Project One')).not.toBeInTheDocument();
  });

  it('reports list failures and retries without hiding the error', async () => {
    const client = {listProjects: jest.fn()
      .mockRejectedValueOnce(new Error('Network unavailable'))
      .mockResolvedValueOnce(projects)};
    const Component = withTheme(ProjectExplorer);
    render(<Component client={client} />);
    expect(await screen.findByRole('alert')).toHaveTextContent('Network unavailable');
    await act(async () => fireEvent.click(screen.getByRole('button', {name: 'Retry'})));
    await waitFor(() => expect(screen.getByText('Project One')).toBeInTheDocument());
    expect(client.listProjects).toHaveBeenCalledTimes(2);
  });

  it('provides intentional empty-state project creation', async () => {
    const onCreateProject = jest.fn();
    const Component = withTheme(ProjectExplorer);
    render(<Component client={{listProjects: () => Promise.resolve([])}}
      onCreateProject={onCreateProject} />);
    const buttons = await screen.findAllByRole('button', {name: 'New project'});
    fireEvent.click(buttons.at(-1));
    expect(onCreateProject).toHaveBeenCalledTimes(1);
  });

  it('creates a validated project through the authenticated client', async () => {
    const client = {listProjects: jest.fn().mockResolvedValue([]),
      createProject: jest.fn().mockResolvedValue({project_id: 'new-project'})};
    const Component = withTheme(ProjectExplorer);
    render(<Component client={client} />);
    const buttons = await screen.findAllByRole('button', {name: 'New project'});
    fireEvent.click(buttons[0]);
    expect(screen.getByRole('dialog', {name: 'New project'})).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/Project ID/),
      {target: {value: 'invalid project'}});
    fireEvent.click(screen.getByRole('button', {name: 'Create project'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('without spaces');
    expect(client.createProject).not.toHaveBeenCalled();
    fireEvent.change(screen.getByLabelText(/Project ID/),
      {target: {value: 'new-project'}});
    fireEvent.change(screen.getByLabelText('Project name'),
      {target: {value: 'New Project'}});
    fireEvent.click(screen.getByRole('button', {name: 'Create project'}));
    await waitFor(() => expect(client.createProject).toHaveBeenCalledWith(
      'new-project', {name: 'New Project', description: ''}
    ));
    await waitFor(() => expect(screen.queryByRole('dialog', {name: 'New project'}))
      .not.toBeInTheDocument());
  });

  it('renders nested parent/child projects under (virt) Projects and prevents circular dependency loops', async () => {
    const hierarchical = [
      {project_id: 'erp-suite', name: 'ERP Suite', parent_project_id: null, revision: 0, access: 'owner'},
      {project_id: 'accounting', name: 'Accounting', parent_project_id: 'erp-suite', revision: 0, access: 'owner'},
      {project_id: 'general-ledger', name: 'General Ledger', parent_project_id: 'accounting', revision: 0, access: 'owner'},
      {project_id: 'standalone', name: 'Standalone BI', parent_project_id: null, revision: 0, access: 'owner'},
    ];
    expect([...collectDescendantProjectIds(hierarchical, 'erp-suite')].sort())
      .toEqual(['accounting', 'general-ledger']);
    expect(canAssignProjectParent(hierarchical, 'erp-suite', 'erp-suite')).toBe(false);
    expect(canAssignProjectParent(hierarchical, 'erp-suite', 'accounting')).toBe(false);
    expect(canAssignProjectParent(hierarchical, 'erp-suite', 'general-ledger')).toBe(false);
    expect(canAssignProjectParent(hierarchical, 'erp-suite', 'standalone')).toBe(true);

    const client = {
      listProjects: jest.fn().mockResolvedValue(hierarchical),
      project: jest.fn().mockResolvedValue({assets: []}),
      updateProject: jest.fn().mockResolvedValue({}),
    };
    const Component = withTheme(ProjectExplorer);
    render(<Component client={client} />);
    expect(await screen.findByText('ERP Suite')).toBeInTheDocument();
    expect(screen.queryByText('Accounting')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Expand ERP Suite'}));
    expect(await screen.findByText('Projects')).toBeInTheDocument();
    expect(await screen.findByText('Accounting')).toBeInTheDocument();

    fireEvent.click(screen.getByRole('button', {name: 'Set parent'}));
    const select = screen.getByLabelText('Parent project');
    const optionValues = [...select.querySelectorAll('option')].map((o) => o.value);
    expect(optionValues).toContain('standalone');
    expect(optionValues).not.toContain('erp-suite');
    expect(optionValues).not.toContain('accounting');
    expect(optionValues).not.toContain('general-ledger');
  });

  it('maps semantic icons and virtual folders for cubes, composed dashboards, and all platform module assets', () => {
    expect(assetIcon('cdeadmin.design.cube')).toBe('object.cube');
    expect(assetIcon('cdeadmin.design.dashboard')).toBe('tool.bi');
    expect(assetIcon('cdeadmin.design.monitoring_dashboard')).toBe('tool.bi');
    expect(assetIcon('cdeadmin.design.screen')).toBe('tool.screen-mesh');
    expect(assetIcon('cdeadmin.design.screen_mesh')).toBe('tool.screen-mesh');
    expect(assetIcon('cdeadmin.lineage.v1')).toBe('tool.lineage');
    expect(assetIcon('cdeadmin.schema_compare.v1')).toBe('tool.schema-compare');
    expect(assetIcon('cdeadmin.quality.v1')).toBe('tool.quality');
    expect(assetIcon('cdeadmin.contract.v1')).toBe('tool.contract');
    expect(assetIcon('cdeadmin.etl.v1')).toBe('tool.etl');
    expect(assetIcon('cdeadmin.cdc.v1')).toBe('tool.cdc');
    expect(assetIcon('cdeadmin.replication.v1')).toBe('tool.replication');
    expect(assetIcon('cdeadmin.tracing.v1')).toBe('tool.tracing');
    expect(assetIcon('cdeadmin.migration.v1')).toBe('tool.migration');
    expect(assetIcon('cdeadmin.api.v1')).toBe('tool.api');
    expect(assetIcon('cdeadmin.ml_vector.v1')).toBe('tool.ml-vector');
    expect(assetIcon('cdeadmin.ai.v1')).toBe('tool.ai');
    expect(assetIcon('cdeadmin.ai_interface.agent_profile.v1')).toBe('tool.ai');

    const richTree = buildProjectVirtualTree(projects[0], {
      assets: [
        {asset_id: 'c1', name: 'GL Cube', asset_type: 'cdeadmin.design.cube'},
        {asset_id: 'd1', name: 'CFO Dashboard', asset_type: 'cdeadmin.design.dashboard'},
        {asset_id: 'e1', name: 'Edge to Lakehouse ETL', asset_type: 'cdeadmin.etl.v1'},
        {asset_id: 'q1', name: 'Balanced GL Rules', asset_type: 'cdeadmin.quality.v1'},
      ],
    });
    const reports = richTree.find((v) => v.key === 'reports');
    const graphs = reports.subgroups.find((s) => s.key === 'graphs');
    const diagrams = reports.subgroups.find((s) => s.key === 'diagrams');
    const docs = richTree.find((v) => v.key === 'documents');
    expect(graphs.items.map((i) => i.asset.asset_id)).toEqual(['c1', 'd1']);
    expect(diagrams.items.map((i) => i.asset.asset_id)).toEqual(['e1']);
    expect(docs.items.map((i) => i.asset.asset_id)).toEqual(['q1']);
  });

  it('streams CDETree nodes from the host navigatorNodes endpoint with Data Explorer parity', async () => {
    const navigatorNodes = jest.fn(async ({parent = '', query = ''}) => {
      if (!parent) {
        return {
          matching_project_count: 1,
          nodes: [
            {
              id: 'proj~analytics',
              label: 'Analytics BI',
              info_label: ' (Owner)',
              icon_key: 'object.schema',
              _type: 'cde_project',
              inode: true,
              has_children: true,
              auto_expand: Boolean(query),
              project_id: 'analytics',
              project: {project_id: 'analytics', name: 'Analytics BI', access: 'owner'},
            },
          ],
        };
      }
      if (parent.endsWith('proj~analytics')) {
        return {
          matching_project_count: 1,
          nodes: [
            {
              id: 'virt~analytics~screens',
              label: 'Screens',
              info_label: ' (1)',
              icon_key: 'ui.screen_frame',
              _type: 'cde_project_virtual',
              inode: true,
              has_children: true,
              auto_expand: true,
              project_id: 'analytics',
              virtual_id: 'virt:analytics:screens',
            },
          ],
        };
      }
      if (parent.endsWith('virt~analytics~screens')) {
        return {
          matching_project_count: 1,
          nodes: [
            {
              id: 'item~analytics~asset~mesh-1',
              label: 'Lakehouse Analytics Explorer — Screen Mesh',
              info_label: ' · v1',
              icon_key: 'ui.screen_frame',
              _type: 'cde_project_leaf',
              inode: false,
              has_children: false,
              project_id: 'analytics',
              leaf: {
                itemKind: 'asset',
                id: 'analytics:asset:mesh-1',
                label: 'Lakehouse Analytics Explorer — Screen Mesh',
                asset: {asset_id: 'mesh-1', name: 'Lakehouse Analytics Explorer — Screen Mesh', asset_type: 'cdeadmin.design.screen'},
                project: {project_id: 'analytics', name: 'Analytics BI'},
              },
            },
          ],
        };
      }
      return {matching_project_count: 1, nodes: []};
    });
    const projectSpy = jest.fn();
    const onOpenAsset = jest.fn();
    const client = {
      listProjects: jest.fn().mockResolvedValue([{project_id: 'analytics', name: 'Analytics BI', access: 'owner'}]),
      navigatorNodes,
      project: projectSpy,
    };
    const Component = withTheme(ProjectExplorer);
    const {container} = render(<Component client={client} onOpenAsset={onOpenAsset} />);

    expect(await screen.findByText('Analytics BI')).toBeInTheDocument();
    expect(container.querySelector('.file-tree .file-entry button.directory-toggle')).not.toBeNull();

    fireEvent.click(screen.getByRole('button', {name: 'Expand Analytics BI'}));
    expect(await screen.findByText('Screens')).toBeInTheDocument();
    expect(await screen.findByText('Lakehouse Analytics Explorer — Screen Mesh')).toBeInTheDocument();
    expect(projectSpy).not.toHaveBeenCalled();

    fireEvent.doubleClick(screen.getByRole('treeitem', {name: /Lakehouse Analytics Explorer/}));
    expect(onOpenAsset).toHaveBeenCalledTimes(1);
  });
});
