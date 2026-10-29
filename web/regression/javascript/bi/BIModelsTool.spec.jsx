/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {act, fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Theme from 'sources/Theme';
import BIModelsTool from 'sources/cdeadmin_ui/modules/bi/models/BIModelsTool';
import {CellsetGrid} from 'sources/cdeadmin_ui/modules/bi/models/QueryPanel';
import {modelFixtures as fixtures} from './modelFixtures';

jest.mock('sources/cdeadmin_ui/editors/CodeEditor', () => ({
  __esModule: true, default: ({label, value, onChange, readonly}) =>
    <textarea aria-label={label} value={value} readOnly={readonly}
      onChange={(event) => onChange?.(event.target.value)} />,
}));

const MODEL = fixtures.ids.model;
const LOSSY = fixtures.ids.lossy;
const RESOURCES = [{resource_id: 'table:sales', resource_kind: 'table', display_name: 'sales',
  display_path: ['analytics', 'sales']}, {resource_id: 'table:extra', resource_kind: 'table',
  display_name: 'extra', display_path: ['analytics', 'extra']}];

beforeEach(() => {
  window.innerHeight = 1200;
});

/** A workspace post that answers the way the real backend did when the fixtures were generated. */
function fakeWorkspace({scheduling = false} = {}) {
  // the fixture list is the final state of the generating run; the model starts as the first revision
  const state = {record: {...fixtures.draft}, list: fixtures.list.map((item) => item.model_id === MODEL ?
    {...item, status: fixtures.draft.status, revision: fixtures.draft.revision} : {...item})};
  const catalog = {...fixtures.catalog, capabilities: {...fixtures.catalog.capabilities,
    scheduled_report_execution: scheduling}};
  const calls = [];
  const handlers = {
    semantic_model_capabilities: () => catalog,
    semantic_model_list: () => ({items: state.list}),
    resource_page: () => ({items: RESOURCES}),
    semantic_model_get: ({model_id: id}) => id === LOSSY ? fixtures.lossy : state.record,
    semantic_model_create: ({definition}) => ({...fixtures.draft, model_id: 'id-new', name: definition.name,
      revision: 1, definition}),
    semantic_model_update: ({definition, expected_revision: revision}) => {
      state.record = {...state.record, name: definition.name, definition, revision: revision + 1};
      return state.record;
    },
    semantic_model_status: ({status, expected_revision: revision}) => {
      state.record = {...state.record, status, revision: revision + 1};
      return state.record;
    },
    semantic_model_validate: ({definition}) => definition.name === 'Broken' ? fixtures.invalidOutcome :
      fixtures.validOutcome,
    semantic_model_lineage: () => fixtures.lineage,
    semantic_model_history: () => fixtures.history,
    semantic_model_compare: () => fixtures.compare,
    semantic_model_clone: ({name}) => ({...state.record, model_id: 'id-clone', name, status: 'draft', revision: 1,
      definition: {...state.record.definition, name}}),
    semantic_model_delete: () => ({}),
    semantic_model_migrate: ({dry_run: dry}) => dry ? fixtures.migration.dry : fixtures.migration.applied,
    semantic_query_compile: () => ({compiled: {source: 'SELECT region FROM sales', language_profile: 'sql'}}),
    semantic_query_diagnostics: () => ({schema: 'cdeadmin.semantic-query-diagnostics.v1'}),
    semantic_query_execute: () => ({occurrence: {occurrence_id: 'occ-1'}}),
    poll: () => ({rendered_result: {component_reference: 'cdeadmin/results/CubePivotView', view_model: {
      levels: ['region_level'], measures: ['revenue'], slice: [],
      cells: [{coordinates: {region_level: 'North'}, measures: {revenue: 42.5}}]}}}),
    close_session: () => ({}),
    report_scheduler_list: () => ({items: []}),
    report_scheduler_occurrences: () => ({items: []}),
    report_scheduler_authorize: () => ({}),
  };
  const post = jest.fn(async (payload) => {
    calls.push(payload);
    const handler = handlers[payload.action];
    if(!handler) throw new Error(`unexpected action ${payload.action}`);
    return handler(payload.request || payload);
  });
  const called = (action) => post.mock.calls.map(([payload]) => payload).filter((item) => item.action === action);
  return {post, state, called};
}

async function open(workspace, props = {}) {
  render(<Theme><BIModelsTool post={workspace.post} {...props} /></Theme>);
  fireEvent.click(await screen.findByRole('button', {name: /Sales cube/}));
  await screen.findByRole('heading', {name: 'Sales cube'});
}

const tab = (name) => fireEvent.click(screen.getByRole('tab', {name}));
// a closing dialog keeps the page behind it hidden from the accessibility tree until its transition ends
const closed = () => waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());

describe('BIModelsTool', () => {
  it('lists the endpoint models with their status and revision', async () => {
    const workspace = fakeWorkspace();
    render(<Theme><BIModelsTool post={workspace.post} /></Theme>);
    const list = await screen.findByRole('navigation', {name: 'Semantic models'});
    const sales = await within(list).findByRole('button', {name: /Sales cube/});
    expect(sales).toHaveTextContent('draft');
    expect(sales).toHaveTextContent('r1');
    expect(within(list).getByRole('button', {name: /Trend cube/})).toHaveTextContent('draft');
    expect(screen.getByText('Choose a semantic model, or start a new one.')).toBeInTheDocument();
  });

  it('opens a model on the typed Model tab and shows its sources', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    expect(screen.getByLabelText(/^Model name/)).toHaveValue('Sales cube');
    expect(screen.getByRole('button', {name: 'Save'})).toBeDisabled();
    expect(screen.queryByText(/read-only/)).not.toBeInTheDocument();
    expect(workspace.called('semantic_model_get')).toHaveLength(1);
  });

  it('has a tab for every part of the old workspace', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    expect(screen.getAllByRole('tab').map((item) => item.textContent)).toEqual([
      'Model', 'Dimensions', 'Measures', 'Parameters & filters', 'Security', 'Materializations', 'Try it',
      'Charts and reports', 'Lineage', 'Revisions', 'Advanced JSON']);
  });

  it('saves an edit with the revision it was based on and keeps embedded content', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    fireEvent.change(screen.getByLabelText(/^Model name/), {target: {value: 'Sales cube v2'}});
    expect(screen.getByLabelText('Unsaved changes')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(workspace.called('semantic_model_update')).toHaveLength(1));
    const [{request}] = workspace.called('semantic_model_update');
    expect(request.model_id).toBe(MODEL);
    expect(request.expected_revision).toBe(fixtures.draft.revision);
    expect(request.definition.name).toBe('Sales cube v2');
    for(const key of ['visualizations', 'dashboards', 'reports', 'schedules']) {
      expect(request.definition[key]).toEqual(fixtures.draft.definition[key]);
    }
    await waitFor(() => expect(screen.queryByLabelText('Unsaved changes')).not.toBeInTheDocument());
    expect(screen.getByText(`r${fixtures.draft.revision + 1}`)).toBeInTheDocument();
  });

  it('validates the draft and reports a valid model or its errors', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    fireEvent.click(screen.getByRole('button', {name: 'Validate'}));
    expect(await screen.findByText('The model is valid.')).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText(/^Model name/), {target: {value: 'Broken'}});
    expect(screen.queryByText('The model is valid.')).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Validate'}));
    const errors = await screen.findByRole('list', {name: 'Validation errors'});
    expect(errors).toHaveTextContent(fixtures.invalidOutcome.errors[0].message);
  });

  it('publishes after a confirmation and then holds the model read-only', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    fireEvent.click(screen.getByRole('button', {name: 'Publish'}));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Publishing freezes this revision');
    fireEvent.click(within(dialog).getByRole('button', {name: 'Publish'}));
    await closed();
    await waitFor(() => expect(workspace.called('semantic_model_status')).toHaveLength(1));
    expect(workspace.called('semantic_model_status')[0].request).toEqual({
      model_id: MODEL, expected_revision: fixtures.draft.revision, status: 'published'});
    expect(await screen.findByText(/published and read-only/)).toBeInTheDocument();
    expect(screen.getByLabelText(/^Model name/)).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Save'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Return to draft'})).toBeEnabled();
    expect(screen.getByRole('button', {name: 'Delete'})).toBeDisabled();
  });

  it('archives without asking and restores to draft', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    fireEvent.click(screen.getByRole('button', {name: 'Archive'}));
    expect(await screen.findByRole('button', {name: 'Restore'})).toBeInTheDocument();
    expect(workspace.called('semantic_model_status')[0].request.status).toBe('archived');
    expect(screen.getByText(/archived/, {selector: '[role="status"] *'})).toBeInTheDocument();
  });

  it('clones under a new name', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    fireEvent.click(screen.getByRole('button', {name: 'Clone'}));
    const dialog = await screen.findByRole('dialog');
    fireEvent.change(within(dialog).getByLabelText('Name of the copy'), {target: {value: 'Sales copy'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Clone'}));
    await closed();
    await waitFor(() => expect(workspace.called('semantic_model_clone')).toHaveLength(1));
    expect(workspace.called('semantic_model_clone')[0].request).toEqual({model_id: MODEL, name: 'Sales copy'});
    expect(await screen.findByRole('heading', {name: 'Sales copy'})).toBeInTheDocument();
  });

  it('deletes only after a confirmation', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    fireEvent.click(screen.getByRole('button', {name: 'Delete'}));
    const dialog = await screen.findByRole('dialog');
    expect(workspace.called('semantic_model_delete')).toHaveLength(0);
    fireEvent.click(within(dialog).getByRole('button', {name: 'Delete'}));
    await closed();
    await waitFor(() => expect(workspace.called('semantic_model_delete')).toHaveLength(1));
    expect(workspace.called('semantic_model_delete')[0].request).toEqual({
      model_id: MODEL, expected_revision: fixtures.draft.revision});
  });

  it('starts a new model from a discovered table and can add another source', async () => {
    const workspace = fakeWorkspace();
    render(<Theme><BIModelsTool post={workspace.post} /></Theme>);
    await screen.findByRole('button', {name: /Sales cube/});
    await waitFor(() => expect(workspace.post).toHaveBeenCalledWith({action: 'resource_page', request: {}}));
    await act(async () => {});
    fireEvent.click(screen.getByRole('button', {name: 'New model'}));
    expect(await screen.findByLabelText(/^Model name/)).toHaveValue('New semantic model');
    fireEvent.change(screen.getByRole('combobox', {name: 'Discovered resource'}).parentElement.querySelector('input'),
      {target: {value: 'table:extra'}});
    fireEvent.click(screen.getByRole('button', {name: 'Add as source'}));
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(workspace.called('semantic_model_create')).toHaveLength(1));
    const {definition} = workspace.called('semantic_model_create')[0].request;
    expect(definition.sources.map((source) => source.resource_id)).toEqual(['table:sales', 'table:extra']);
    expect(definition.sources.map((source) => source.id)).toEqual(['sales', 'extra']);
  });

  it('asks before leaving unsaved edits for another model', async () => {
    const workspace = fakeWorkspace();
    await open(workspace);
    fireEvent.change(screen.getByLabelText(/^Model name/), {target: {value: 'Edited'}});
    fireEvent.click(screen.getByRole('button', {name: /Trend cube/}));
    const dialog = await screen.findByRole('dialog');
    expect(dialog).toHaveTextContent('Discard unsaved changes?');
    fireEvent.click(within(dialog).getByRole('button', {name: 'Keep editing'}));
    await waitFor(() => expect(screen.queryByRole('dialog')).not.toBeInTheDocument());
    expect(screen.getByLabelText(/^Model name/)).toHaveValue('Edited');
    fireEvent.click(screen.getByRole('button', {name: /Trend cube/}));
    fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', {name: 'Discard changes'}));
    expect(await screen.findByRole('heading', {name: 'Trend cube'})).toBeInTheDocument();
  });

  it('reports the dirty state to the host', async () => {
    const workspace = fakeWorkspace();
    const onDirtyChange = jest.fn();
    await open(workspace, {onDirtyChange});
    fireEvent.change(screen.getByLabelText(/^Model name/), {target: {value: 'Edited'}});
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(true));
  });

  describe('panels', () => {
    it('shows revisions and compares two of them', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      tab('Revisions');
      const history = await screen.findByRole('list', {name: 'Revision history'});
      expect(await within(history).findAllByRole('listitem')).toHaveLength(fixtures.history.items.length);
      fireEvent.click(screen.getByRole('button', {name: 'Compare revisions'}));
      const changes = await screen.findByRole('table', {name: 'Revision changes'});
      expect(changes).toHaveTextContent('description');
      expect(changes).toHaveTextContent('Revenue by region');
      expect(workspace.called('semantic_model_compare')[0].request).toEqual({
        model_id: MODEL, left_revision: 2, right_revision: 3});
    });

    it('refreshes lineage from the current draft', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      tab('Lineage');
      fireEvent.click(screen.getByRole('button', {name: 'Refresh lineage'}));
      const nodes = await screen.findByRole('list', {name: 'Lineage nodes'});
      expect(nodes).toHaveTextContent('source');
      expect(workspace.called('semantic_model_lineage')[0].request.definition.name).toBe('Sales cube');
    });

    it('edits the whole document as JSON and rejects text that is not JSON', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      tab('Advanced JSON');
      const editor = screen.getByLabelText('Model JSON');
      expect(JSON.parse(editor.value).name).toBe('Sales cube');
      fireEvent.change(editor, {target: {value: '{ not json'}});
      fireEvent.click(screen.getByRole('button', {name: 'Apply JSON'}));
      expect(await screen.findByText(/The JSON is not valid/)).toBeInTheDocument();
      fireEvent.change(editor, {target: {value: JSON.stringify({...fixtures.draft.definition, name: 'From JSON'})}});
      fireEvent.click(screen.getByRole('button', {name: 'Apply JSON'}));
      tab('Model');
      expect(screen.getByLabelText(/^Model name/)).toHaveValue('From JSON');
      expect(screen.getByLabelText('Unsaved changes')).toBeInTheDocument();
    });

    it('runs a cube query against the stored model and shows the pivot', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      tab('Try it');
      expect(screen.getByLabelText('Time operation')).toBeInTheDocument();
      expect(screen.getByRole('button', {name: 'Run query'})).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', {name: 'Run query'}));
      expect((await screen.findAllByText('Choose at least one measure.')).length).toBeGreaterThan(0);
      expect(workspace.called('semantic_query_execute')).toHaveLength(0);

      const measures = screen.getByRole('combobox', {name: /^Measures/});
      fireEvent.mouseDown(measures);
      fireEvent.click(await screen.findByRole('option', {name: 'Revenue'}));
      fireEvent.click(screen.getByRole('button', {name: 'Compile query'}));
      expect(await screen.findByLabelText('Compiled query')).toHaveTextContent('SELECT region FROM sales');
      expect(workspace.called('semantic_query_compile')[0].request).toMatchObject({
        model_id: MODEL, query: {measures: ['revenue'], limit: 500}});
      fireEvent.click(screen.getByRole('button', {name: 'Query diagnostics'}));
      expect(await screen.findByLabelText('Query diagnostics result')).toHaveTextContent('semantic-query-diagnostics');
      fireEvent.click(screen.getByRole('button', {name: 'Run query'}));
      const pivot = await screen.findByLabelText('Cube pivot results');
      expect(pivot).toHaveTextContent('North');
      expect(pivot).toHaveTextContent('42.5');
      expect(workspace.called('semantic_query_execute')[0].request.model_id).toBe(MODEL);
      expect(workspace.post).toHaveBeenCalledWith({action: 'poll', occurrence_id: 'occ-1'});
    });

    it('queries the unsaved draft, not the stored model, once it has been edited', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      fireEvent.change(screen.getByLabelText(/^Model name/), {target: {value: 'Edited'}});
      tab('Try it');
      expect(screen.getByText('Queries run against your unsaved edits.')).toBeInTheDocument();
      fireEvent.mouseDown(screen.getByRole('combobox', {name: /^Measures/}));
      fireEvent.click(await screen.findByRole('option', {name: 'Revenue'}));
      fireEvent.click(screen.getByRole('button', {name: 'Compile query'}));
      await waitFor(() => expect(workspace.called('semantic_query_compile')).toHaveLength(1));
      const {request} = workspace.called('semantic_query_compile')[0];
      expect(request.model_id).toBeUndefined();
      expect(request.definition.name).toBe('Edited');
    });

    it('closes its query session when the view is left', async () => {
      const workspace = fakeWorkspace();
      workspace.post.mockImplementation(async (payload) => payload.action === 'semantic_query_execute' ?
        {occurrence: {occurrence_id: 'occ-1'}, session_id: 'sess-1'} :
        fakeWorkspace().post(payload));
      const view = render(<Theme><BIModelsTool post={workspace.post} /></Theme>);
      fireEvent.click(await screen.findByRole('button', {name: /Sales cube/}));
      await screen.findByRole('heading', {name: 'Sales cube'});
      tab('Try it');
      fireEvent.mouseDown(screen.getByRole('combobox', {name: /^Measures/}));
      fireEvent.click(await screen.findByRole('option', {name: 'Revenue'}));
      fireEvent.click(screen.getByRole('button', {name: 'Run query'}));
      await waitFor(() => expect(workspace.called('semantic_query_execute')).toHaveLength(1));
      view.unmount();
      expect(workspace.post).toHaveBeenCalledWith({action: 'close_session', session_id: 'sess-1'});
    });

    it('explains when the endpoint cannot execute queries', async () => {
      const workspace = fakeWorkspace();
      const post = (payload) => payload.action === 'semantic_model_capabilities' ?
        Promise.resolve({...fixtures.catalog, capabilities: {...fixtures.catalog.capabilities,
          execution_available: false}}) : workspace.post(payload);
      render(<Theme><BIModelsTool post={post} /></Theme>);
      fireEvent.click(await screen.findByRole('button', {name: /Sales cube/}));
      await screen.findByRole('heading', {name: 'Sales cube'});
      tab('Try it');
      expect(screen.getByText(/cannot execute semantic queries/)).toBeInTheDocument();
    });
  });

  describe('charts, dashboards, reports and schedules', () => {
    it('lists what the model holds without letting it be edited', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      tab('Charts and reports');
      expect(screen.getByRole('table', {name: 'Charts'})).toHaveTextContent('Revenue by region');
      expect(screen.getByRole('table', {name: 'Dashboards'})).toHaveTextContent('Overview');
      expect(screen.getByRole('table', {name: 'Reports'})).toHaveTextContent('Morning');
      expect(screen.getByRole('table', {name: 'Schedules'})).toHaveTextContent('0 8 * * *');
      expect(screen.queryByRole('button', {name: /Add chart|Add dashboard|Add report/})).not.toBeInTheDocument();
    });

    it('previews the migration without creating anything, then applies it', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      tab('Charts and reports');
      fireEvent.click(screen.getByRole('button', {name: 'Preview migration'}));
      const report = await screen.findByRole('table', {name: 'Migration result'});
      expect(report).toHaveTextContent('Would create');
      expect(report).toHaveTextContent('Revenue by region');
      expect(workspace.called('semantic_model_migrate')[0].request).toEqual({
        model_id: MODEL, dry_run: true, accept_loss: false});
      fireEvent.click(screen.getByRole('button', {name: 'Migrate to BI'}));
      await waitFor(() => expect(workspace.called('semantic_model_migrate')).toHaveLength(2));
      expect(workspace.called('semantic_model_migrate')[1].request.dry_run).toBe(false);
      expect(await screen.findByText(/Migrated revision/)).toBeInTheDocument();
    });

    it('sends the accept-loss choice with the migration', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      tab('Charts and reports');
      fireEvent.click(screen.getByRole('checkbox', {name: 'Also migrate charts that lose features'}));
      fireEvent.click(screen.getByRole('button', {name: 'Preview migration'}));
      await waitFor(() => expect(workspace.called('semantic_model_migrate')).toHaveLength(1));
      expect(workspace.called('semantic_model_migrate')[0].request.accept_loss).toBe(true);
    });

    it('migrates from the saved revision and says so when there are unsaved edits', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      fireEvent.change(screen.getByLabelText(/^Model name/), {target: {value: 'Edited'}});
      tab('Charts and reports');
      expect(screen.getByText(/unsaved edits/)).toBeInTheDocument();
    });

    it('documents that subscription conversion waits for the alerts branch', async () => {
      const workspace = fakeWorkspace();
      await open(workspace);
      tab('Charts and reports');
      expect(screen.getByText(/not available yet/)).toBeInTheDocument();
      expect(screen.queryByRole('button', {name: /subscription/i})).not.toBeInTheDocument();
    });

    it('shows a lossy chart as skipped and its dashboard as blocked', async () => {
      const workspace = fakeWorkspace();
      render(<Theme><BIModelsTool post={(payload) => payload.action === 'semantic_model_migrate' ?
        Promise.resolve(fixtures.migration.lossyDry) : workspace.post(payload)} /></Theme>);
      fireEvent.click(await screen.findByRole('button', {name: /Trend cube/}));
      await screen.findByRole('heading', {name: 'Trend cube'});
      tab('Charts and reports');
      fireEvent.click(screen.getByRole('button', {name: 'Preview migration'}));
      const report = await screen.findByRole('table', {name: 'Migration result'});
      expect(report).toHaveTextContent('Skipped');
      expect(report).toHaveTextContent('Blocked');
      expect(report).toHaveTextContent('analytical window');
    });

    it('authorizes a scheduled report on a published model through the scheduler', async () => {
      const workspace = fakeWorkspace({scheduling: true});
      render(<Theme><BIModelsTool post={workspace.post} /></Theme>);
      fireEvent.click(await screen.findByRole('button', {name: /Sales cube/}));
      await screen.findByRole('heading', {name: 'Sales cube'});
      fireEvent.click(screen.getByRole('button', {name: 'Publish'}));
      fireEvent.click(within(await screen.findByRole('dialog')).getByRole('button', {name: 'Publish'}));
      await closed();
      await screen.findByText(/published and read-only/);
      tab('Charts and reports');
      fireEvent.click(await screen.findByRole('button', {name: 'Authorize schedule'}));
      await waitFor(() => expect(workspace.called('report_scheduler_authorize')).toHaveLength(1));
      expect(workspace.called('report_scheduler_authorize')[0].request).toMatchObject({
        model_id: MODEL, report_id: 'morning'});
    });
  });
});

describe('CellsetGrid', () => {
  const rendered = {view_model: {levels: ['country', 'city'], measures: ['revenue'], slice: [{level: 'country', value: 'DE'}],
    cells: [{coordinates: {country: 'DE', city: 'Berlin'}, measures: {revenue: 10}},
      {coordinates: {country: 'DE', city: 'Bonn'}, measures: {revenue: 5}}]}};
  const headers = () => within(screen.getByRole('table', {name: 'Cube pivot cell grid'}))
    .getAllByRole('columnheader').map((cell) => cell.textContent);

  it('shows levels then measures, and transposes the axes', () => {
    render(<Theme><CellsetGrid rendered={rendered} /></Theme>);
    expect(headers()).toEqual(['country', 'city', 'revenue']);
    fireEvent.click(screen.getByRole('button', {name: 'Transpose axes'}));
    expect(headers()).toEqual(['revenue', 'country', 'city']);
    expect(screen.getByText(/Active slice/)).toHaveTextContent('DE');
  });

  it('drills up and down through the levels', () => {
    render(<Theme><CellsetGrid rendered={rendered} /></Theme>);
    expect(screen.getByRole('button', {name: 'Drill down'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Drill up'}));
    expect(headers()).toEqual(['country', 'revenue']);
    expect(screen.getByRole('button', {name: 'Drill up'})).toBeDisabled();
    fireEvent.click(screen.getByRole('button', {name: 'Drill down'}));
    expect(headers()).toEqual(['country', 'city', 'revenue']);
  });

  it('exports the cells as CSV', () => {
    const blobs = [];
    const create = URL.createObjectURL;
    URL.createObjectURL = jest.fn((blob) => { blobs.push(blob); return 'blob:x'; });
    URL.revokeObjectURL = jest.fn();
    const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    render(<Theme><CellsetGrid rendered={rendered} /></Theme>);
    fireEvent.click(screen.getByRole('button', {name: 'Export CSV'}));
    expect(click).toHaveBeenCalledTimes(1);
    expect(blobs[0].type).toBe('text/csv');
    click.mockRestore();
    URL.createObjectURL = create;
  });

  it('says so when the query returned no cells', () => {
    render(<Theme><CellsetGrid rendered={{view_model: {levels: [], measures: [], cells: []}}} /></Theme>);
    expect(screen.getByText('The query returned no cells.')).toBeInTheDocument();
  });
});
