/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

// To Diagram (owner direction 2026-11-06). The fixture is the catalog_diagram
// response for a real SQLite file (customer, purchase, note; two foreign
// keys), captured with the worktree's builders on 2026-11-08.
import {libraries, setupDDNDOM} from './ddnTestRuntime';
import contribution from './fixtures/sqlite-catalog-diagram.json';
import {newDiagramAsset, verifyDiagramSnapshot} from 'sources/cdeadmin_ui/integrations/ddn/diagrams';
import {mergeIntoDiagram, objectsSource} from 'sources/cdeadmin_ui/integrations/ddn/toDiagram';
import {
  addNodeToDiagram, diagramChoices, refreshDiagramChoices, resetDiagramChoicesForTests,
  setDiagramChoices,
} from 'sources/cdeadmin_ui/integrations/ddn/toDiagramMenu';
import {providerTreeContextActions} from '../../../pgadmin/browser/static/js/ProviderContextMenu';

// The menu's own listing goes through the project API.
jest.mock('sources/api_instance', () => () => ({
  get: jest.fn().mockResolvedValue({data: {data: []}}),
}));

beforeAll(() => setupDDNDOM());
beforeEach(() => resetDiagramChoicesForTests());

const start = () => newDiagramAsset({projectId: 'models', name: 'Shop', random: () => 'abc'}).snapshot;
const relation = (name) => contribution.relations.find((item) => item.name === name);
const decoded = (snapshot) => libraries.language.decodeSources({entry: snapshot.entry,
  files: Object.entries(snapshot.files).map(([id, text]) => ({id, text, revision: 'r', encoding: 'utf-8', writable: false}))});
const view = (snapshot) => libraries.model.listRecords(decoded(snapshot).normalized)
  .find((item) => item.kind === 'view' && item.ref.id === 'diagram').record;

describe('To Diagram', () => {
  it('adds one table, then its database, in nested regions that DDN verifies', async () => {
    const one = mergeIntoDiagram(libraries, start(), contribution,
      {resourceIds: [relation('purchase').resource_id]});
    expect([one.added, one.dropped, one.selected]).toEqual([1, 0, 1]);
    expect((await verifyDiagramSnapshot(libraries, one.snapshot)).outcome).toBe('valid');
    expect(one.snapshot.files['diagram.ddn']).toContain('include "objects/sqlite-abc.ddn"');
    expect(Object.keys(one.snapshot.files).sort()).toEqual(['diagram.ddn', 'objects/sqlite-abc.ddn']);
    // The catalog's own views are not carried into the diagram.
    expect(one.snapshot.files['objects/sqlite-abc.ddn']).not.toMatch(/^view /m);
    const regions = view(one.snapshot).regions;
    expect(regions.map((item) => [item.role, item.name])).toEqual([
      ['host', 'localhost'], ['server', 'Local SQLite'], ['database', 'shop.sqlite'], ['schema', 'main']]);
    expect(regions[3].members).toEqual([{id: relation('purchase').key, file: 'objects/sqlite-abc.ddn'}]);
    const all = mergeIntoDiagram(libraries, one.snapshot, contribution);
    expect([all.added, all.dropped, all.selected]).toEqual([2, 0, 3]);
    expect((await verifyDiagramSnapshot(libraries, all.snapshot)).outcome).toBe('valid');
    expect(view(all.snapshot).regions[3].members).toHaveLength(3);
    // The first view, its title and layout are the diagram's own.
    expect(all.snapshot.files['diagram.ddn']).toContain('title "Shop"');
    expect(all.snapshot.files['diagram.ddn']).toContain('algorithm "organic"');
    const again = mergeIntoDiagram(libraries, all.snapshot, contribution);
    expect(again.added).toBe(0);
    expect(again.snapshot.files).toEqual(all.snapshot.files);
  });

  it('keeps crow\'s-foot marks and drops objects that left the database', async () => {
    const all = mergeIntoDiagram(libraries, start(), contribution);
    expect(all.snapshot.files['objects/sqlite-abc.ddn']).toMatch(/source_mark "zeromany"\n\s+target_mark "one"/);
    expect(all.snapshot.files['objects/sqlite-abc.ddn']).toMatch(/source_mark "zeromany"\n\s+target_mark "zeroone"/);
    const fewer = {...contribution, relations: contribution.relations.filter((item) => item.name !== 'note')};
    const refreshed = mergeIntoDiagram(libraries, all.snapshot, fewer);
    expect([refreshed.added, refreshed.dropped, refreshed.selected]).toEqual([0, 1, 2]);
    expect(view(refreshed.snapshot).regions[3].members.map((item) => item.id))
      .not.toContain(relation('note').key);
  });

  it('refuses an object the catalog diagram does not draw', () => {
    expect(() => mergeIntoDiagram(libraries, start(), contribution, {resourceIds: ['column:x']}))
      .toThrow('not drawn');
    expect(objectsSource(libraries, 'x.ddn', contribution.snapshot.files['relations.ddn']))
      .toContain('as "table"');
  });

  it('loads the diagram, saves the next version and opens it', async () => {
    const asset = {asset_id: 'diagram-abc', name: 'Shop', asset_type: 'ddn-workspace', version: 4,
      access: 'owner', editor_capable: true, metadata: {diagram: {schema: 'cdeadmin.diagram.v1',
        notation: 'erd.crowfoot@1'}}, assetRef: {schemaVersion: 1, projectId: 'models', assetId: 'diagram-abc',
        assetType: 'ddn-workspace', assetVersion: 4, path: 'diagrams/shop-abc.ddn', displayName: 'Shop'},
      content: start()};
    const client = {asset: jest.fn().mockResolvedValue(asset), listProjects: jest.fn().mockResolvedValue([]),
      saveAsset: jest.fn().mockResolvedValue({version: 5})};
    const post = jest.fn().mockResolvedValue(contribution);
    const opened = jest.fn();
    window.addEventListener('cdeadmin:open-project-asset', opened);
    const result = await addNodeToDiagram({client, libraries, post, args: {
      database_target_id: 't-1', resource_id: relation('customer').resource_id, resource_kind: 'table',
      diagram: {project: {project_id: 'models'}, asset}}});
    window.removeEventListener('cdeadmin:open-project-asset', opened);
    expect(post).toHaveBeenCalledWith({action: 'catalog_diagram', request: {database_target_id: 't-1'}});
    expect(result.added).toBe(1);
    const [projectId, assetId, payload] = client.saveAsset.mock.calls[0];
    expect([projectId, assetId]).toEqual(['models', 'diagram-abc']);
    expect(payload.assetRef.assetVersion).toBe(4);
    expect(payload.metadata).toEqual(asset.metadata);
    expect(Object.keys(payload.snapshot.files)).toContain('objects/sqlite-abc.ddn');
    expect(opened).toHaveBeenCalledTimes(1);
    expect(opened.mock.calls[0][0].detail.asset).toMatchObject({asset_id: 'diagram-abc', version: 5});
  });

  it('offers the editable diagrams as a submenu of the provider menu', async () => {
    const action = {schema: 'cdeadmin.context-action.v1', command_id: 'resource.sqlite.to_diagram',
      label: 'To Diagram', handler: 'add_to_diagram', icon_key: 'tool.erd', menu_group: 'common',
      priority: 90, mutation_class: 'none', enabled: true,
      arguments: {resource_id: 'r1', database_target_id: 't-1', resource_kind: 'table'}};
    const itemData = {_type: 'cde_resource', cde_provider_id: 'org.cdeadmin.sqlite', cde_context_actions: [action]};
    const client = {listProjects: jest.fn().mockResolvedValue([]), project: jest.fn()};
    // The first opening lists while it loads; New diagram is always there.
    expect(diagramChoices()).toBeNull();
    let entry = providerTreeContextActions(itemData).find((item) => item.id === 'resource.sqlite.to_diagram');
    expect(entry.children.map((item) => [item.label, item.enabled])).toEqual([
      ['Loading diagrams…', false], ['New diagram…', true]]);
    await refreshDiagramChoices(client);
    setDiagramChoices([
      {project: {project_id: 'models', access: 'owner'}, diagrams: [{asset_id: 'a', name: 'Shop'}]},
      {project: {project_id: 'shared', access: 'viewer'}, diagrams: [{asset_id: 'b', name: 'Read only'}]},
    ]);
    entry = providerTreeContextActions(itemData).find((item) => item.id === 'resource.sqlite.to_diagram');
    expect(entry.children.map((item) => item.label)).toEqual(['Shop', 'New diagram…']);
  });
});
