/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// The Diagrams tool (owner direction 2026-11-06): named diagrams with default
// settings, crow's foot by default, stored as DDN workspace project assets.
import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import {withTheme} from '../fake_theme';
import {libraries, setupDDNDOM} from './ddnTestRuntime';
import {
  DEFAULT_DIAGRAM_NOTATION, DIAGRAM_NOTATIONS, DIAGRAM_SCHEMA, createDiagram,
  isDiagramAsset, listDiagrams, newDiagramAsset, newDiagramSource,
  verifyDiagramSnapshot,
} from 'sources/cdeadmin_ui/integrations/ddn/diagrams';
import {
  DiagramsNavigator, requestDiagramCreate,
} from 'sources/cdeadmin_ui/integrations/ddn/DiagramsNavigator';
import {ddnModuleDefinition} from 'sources/cdeadmin_ui/integrations/ddn/module';

// The panel the activity renders makes its own project client.
const mockActivityClient = {listProjects: jest.fn().mockResolvedValue([]), project: jest.fn()};
jest.mock('sources/cdeadmin_ui/projects/ProjectAssetClient', () => ({
  ProjectAssetClient: function ProjectAssetClient() { return mockActivityClient; },
}));

beforeAll(() => setupDDNDOM());

const owned = {project_id: 'models', name: 'Models', access: 'owner'};
const viewed = {project_id: 'shared', name: 'Shared', access: 'viewer'};
const diagram = (id, name, notation='erd.crowfoot@1') => ({asset_id: id, name,
  asset_type: 'ddn-workspace', version: 1, access: 'owner', editor_capable: true,
  metadata: {diagram: {schema: DIAGRAM_SCHEMA, notation}}});
const dashboardDraft = {asset_id: 'draft', name: 'MySQL server dashboard draft',
  asset_type: 'ddn-workspace', version: 2, metadata: {}};

function fakeClient(states) {
  const client = {
    listProjects: jest.fn(async () => Object.values(states).map((state) => state.project)),
    project: jest.fn(async (id) => ({...states[id].project, assets: states[id].assets})),
    createProject: jest.fn(async (id, request) => {
      states[id] = {project: {project_id: id, name: request.name, access: 'owner'}, assets: []};
      return states[id].project;
    }),
    saveAsset: jest.fn(async (projectId, assetId, payload) => {
      states[projectId].assets.push({...diagram(assetId, payload.assetRef.displayName,
        payload.metadata.diagram.notation)});
      return {assetRef: {...payload.assetRef, assetVersion: 1}};
    }),
  };
  return client;
}

describe('Diagrams tool', () => {
  it('starts crow\'s foot by default and lists the other ERD notations as unavailable', () => {
    expect(DEFAULT_DIAGRAM_NOTATION).toBe('erd.crowfoot@1');
    expect(DIAGRAM_NOTATIONS.filter((item) => item.available).map((item) => item.id))
      .toEqual(['erd.crowfoot@1', 'ddn@1']);
    for(const item of DIAGRAM_NOTATIONS.filter((value) => !value.available)) {
      expect(item.reason).toMatch(/no catalog mapping/);
      expect(() => newDiagramSource('x', item.id)).toThrow('not available');
    }
  });

  it('writes a new, empty view that DDN verifies for every available notation', async () => {
    for(const item of DIAGRAM_NOTATIONS.filter((value) => value.available)) {
      const payload = newDiagramAsset({projectId: 'models', name: 'Order "core" model',
        notation: item.id, random: () => 'abc'});
      expect(payload.assetRef).toEqual({schemaVersion: 1, projectId: 'models',
        assetId: 'diagram-abc', assetType: 'ddn-workspace', assetVersion: 0,
        path: 'diagrams/order-core-model-abc.ddn', displayName: 'Order "core" model'});
      expect(payload.metadata).toEqual({diagram: {schema: DIAGRAM_SCHEMA, notation: item.id}});
      const source = payload.snapshot.files['diagram.ddn'];
      expect(source).toContain(`view "diagram" as "${item.id}"`);
      expect(source).toContain('title "Order ""core"" model"');
      expect((await verifyDiagramSnapshot(libraries, payload.snapshot)).outcome).toBe('valid');
    }
    expect(() => newDiagramAsset({projectId: 'models', name: 'two\nlines'})).toThrow('line breaks');
    expect(() => newDiagramAsset({projectId: 'models', name: '  '})).toThrow('needs a name');
  });

  it('lists only diagrams, grouped by project, and keeps a failing project visible', async () => {
    const client = {
      listProjects: jest.fn().mockResolvedValue([owned, viewed]),
      project: jest.fn(async (id) => {
        if(id === 'shared') throw new Error('Project is unavailable');
        return {...owned, assets: [diagram('b', 'Billing'), dashboardDraft, diagram('a', 'Accounts')]};
      }),
    };
    const groups = await listDiagrams(client);
    expect(groups[0].diagrams.map((item) => item.name)).toEqual(['Accounts', 'Billing']);
    expect(groups[1]).toMatchObject({project: viewed, error: 'Project is unavailable', diagrams: []});
    expect(isDiagramAsset(dashboardDraft)).toBe(false);
  });

  it('refuses to store a diagram that DDN does not admit', async () => {
    const client = {saveAsset: jest.fn()};
    const refusing = {viewer: {...libraries.viewer,
      verifySourcesWithModel: async () => ({report: {outcome: 'invalid',
        diagnostics: [{severity: 'error', message: 'refused for the test'}]}})}};
    await expect(createDiagram(client, refusing, {projectId: 'models', name: 'Orders'}))
      .rejects.toThrow('refused for the test');
    expect(client.saveAsset).not.toHaveBeenCalled();
  });

  it('creates a named diagram in a new project and opens it', async () => {
    const client = fakeClient({});
    const onOpenDiagram = jest.fn();
    const Component = withTheme(DiagramsNavigator);
    render(<Component client={client} libraries={libraries} onOpenDiagram={onOpenDiagram} />);
    expect(await screen.findByText(/No diagrams yet/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'New diagram…'}));
    const dialog = await screen.findByRole('dialog', {name: 'New diagram'});
    expect(within(dialog).getByText('SR-F-010016')).toBeInTheDocument();
    fireEvent.change(within(dialog).getByLabelText(/Diagram name/), {target: {value: 'Orders'}});
    expect(within(dialog).getByLabelText(/Project ID/)).toHaveValue('diagrams');
    fireEvent.click(within(dialog).getByRole('button', {name: 'Create diagram'}));
    await waitFor(() => expect(onOpenDiagram).toHaveBeenCalledTimes(1));
    expect(client.createProject).toHaveBeenCalledWith('diagrams', {name: 'Diagrams'});
    const [projectId, assetId, payload] = client.saveAsset.mock.calls[0];
    expect(projectId).toBe('diagrams');
    expect(assetId).toMatch(/^diagram-[0-9a-f]{32}$/);
    expect(payload.assetRef.path).toBe(`diagrams/orders-${assetId.slice(8, 16)}.ddn`);
    expect(payload.metadata.diagram.notation).toBe('erd.crowfoot@1');
    expect(onOpenDiagram.mock.calls[0][0]).toMatchObject({project_id: 'diagrams'});
    expect(onOpenDiagram.mock.calls[0][1]).toMatchObject({asset_id: assetId, name: 'Orders'});
    expect(await screen.findByText('Orders')).toBeInTheDocument();
  });

  it('greys out notations without a catalog mapping', async () => {
    const client = fakeClient({models: {project: owned, assets: [diagram('a', 'Accounts')]}});
    const Component = withTheme(DiagramsNavigator);
    render(<Component client={client} libraries={libraries} onOpenDiagram={jest.fn()} />);
    expect(await screen.findByText('Accounts')).toBeInTheDocument();
    expect(screen.getByText('Crow\'s foot ERD')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'New diagram…'}));
    const dialog = await screen.findByRole('dialog', {name: 'New diagram'});
    expect(within(dialog).queryByLabelText(/Project ID/)).not.toBeInTheDocument();
    fireEvent.mouseDown(within(dialog).getByRole('combobox', {name: /Notation/}));
    const listbox = await screen.findByRole('listbox');
    expect(within(listbox).getByRole('option', {name: 'Crow\'s foot ERD'})).not.toHaveAttribute('aria-disabled');
    expect(within(listbox).getByRole('option', {name: 'Chen ERD (no catalog mapping yet)'}))
      .toHaveAttribute('aria-disabled', 'true');
  });

  it('opens the create dialog when Tools > New Diagram runs before the panel exists', async () => {
    const client = fakeClient({models: {project: owned, assets: []}});
    const definition = ddnModuleDefinition();
    const command = definition.contributions.commands.find((item) => item.id === 'ddn.diagrams.new');
    expect(command.surfaces).toContain('tools');
    // Shown to users whose permission list carries names, not dotted values.
    expect(command.permission ?? []).toEqual([]);
    const showActivity = jest.fn();
    command.execute({}, {showActivity});
    expect(showActivity).toHaveBeenCalledWith('activity.diagrams');
    const activity = definition.contributions.activity.find((item) => item.id === 'activity.diagrams');
    const Activity = withTheme(() => activity.render());
    render(<Activity />);
    expect(await screen.findByRole('dialog', {name: 'New diagram'})).toBeInTheDocument();
    expect(mockActivityClient.listProjects).toHaveBeenCalled();
    expect(client.listProjects).not.toHaveBeenCalled();
  });

  it('opens the dialog of a mounted panel on request', async () => {
    const client = fakeClient({models: {project: owned, assets: [diagram('a', 'Accounts')]}});
    const Component = withTheme(DiagramsNavigator);
    render(<Component client={client} libraries={libraries} onOpenDiagram={jest.fn()} />);
    expect(await screen.findByText('Accounts')).toBeInTheDocument();
    act(() => requestDiagramCreate());
    const dialog = await screen.findByRole('dialog', {name: 'New diagram'});
    expect(within(dialog).getByRole('combobox', {name: /Project/})).toHaveTextContent('Models');
  });
});
