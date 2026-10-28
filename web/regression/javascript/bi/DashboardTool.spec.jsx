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
import BIQuestionsTool from 'sources/cdeadmin_ui/modules/bi/BIQuestionsTool';
import {dashboardFixtures as fixtures} from './dashboardFixtures';

jest.mock('sources/cdeadmin_ui/editors/CodeEditor', () => ({
  __esModule: true, default: ({label, value, onChange, readonly}) =>
    <textarea aria-label={label} value={value} readOnly={readonly}
      onChange={(event) => onChange?.(event.target.value)} />,
}));
jest.mock('sources/cdeadmin_ui/data/PagedDataGrid', () => ({
  __esModule: true, default: ({rows, columns, onCellClick}) =>
    <table aria-label="grid"><tbody>
      <tr>{columns.map((column) => <th key={column.key}>{column.name}</th>)}</tr>
      {rows.map((row, index) => <tr key={index}>{columns.map((column) =>
        <td key={column.key}
          onClick={() => onCellClick?.({row, column, rowIdx: index}, {preventGridDefault() {}, isGridDefaultPrevented: () => false})}>
          {String(row[column.key])}</td>)}</tr>)}
    </tbody></table>,
}));
jest.mock('sources/chartjs', () => ({
  __esModule: true, default: ({type, title}) => <div role="img" aria-label={title}>{type}</div>,
}));

const URL = '/browser/server/cde_workspace/1/2';
const {board, questions} = fixtures;

beforeEach(() => { window.innerHeight = 1200; });

const summary = (id, name, extra = {}) => ({dashboard_id: id, name, collection_id: null,
  status: 'active', revision: 3, ...extra});

function fakeBackend(overrides = {}) {
  const db = {
    dashboards: [summary('d1', 'Sales board'), summary('d2', 'Other board')],
    ...overrides.db,
  };
  const record = (id, revision = 3, definition = board) => ({dashboard_id: id, revision, status: 'active',
    definition: {...definition, name: db.dashboards.find((item) => item.dashboard_id === id)?.name || definition.name}});
  const calls = [];
  const handlers = {
    bi_collection_list: () => ({items: []}),
    bi_question_list: () => ({items: [
      {question_id: 'q-by-region', name: 'Sales by region', collection_id: null, status: 'active', revision: 2},
      {question_id: 'q-floor', name: 'Floor report', collection_id: null, status: 'active', revision: 1}]}),
    bi_dashboard_list: () => ({items: db.dashboards}),
    bi_dashboard_get: ({dashboard_id: id}) => record(id),
    bi_dashboard_create: ({dashboard}) => ({dashboard_id: 'd9', revision: 1, status: 'active', definition: dashboard}),
    bi_dashboard_update: ({dashboard_id: id, dashboard}) => ({dashboard_id: id, revision: 4, status: 'active', definition: dashboard}),
    bi_dashboard_status: ({dashboard_id: id, status}) => ({dashboard_id: id, status}),
    bi_dashboard_move: ({dashboard_id: id}) => ({dashboard_id: id}),
    bi_dashboard_clone: ({name}) => ({dashboard_id: 'd8', revision: 1, status: 'active', definition: {...board, name}}),
    bi_dashboard_history: () => ({items: [
      {revision: 3, created_at: '2026-01-02T03:04:05Z', status: 'active'},
      {revision: 2, created_at: '2026-01-01T03:04:05Z', status: 'active'}]}),
    bi_dashboard_revision: ({dashboard_id: id, revision}) => record(id, revision, {...board, name: 'Sales board'}),
    bi_question_revision: ({question_id: id, revision}) => ({question_id: id, revision,
      definition: questions[id.replace('q-by-region', 'q-by-region')] || questions['q-by-region']}),
    bi_dashboard_card_run: ({card_id: id}) => ({
      result: {result_id: `r-${id}`},
      page: {view_model: {columns: [{key: 'region'}, {key: 'amount'}], rows: [['east', 5], ['west', 7]]},
        page: {source_count: 2, next_cursor: ''}},
      redacted_columns: [], cache: {hit: id === 'floor', age_seconds: 12},
    }),
    bi_dashboard_cross_filter: () => fixtures.cross.outcome,
    bi_dashboard_drill: () => fixtures.drill,
    bi_dashboard_from_ddn: () => ({dashboard: fixtures.monitoring.dashboard,
      loss: [{code: 'unsupported_panel', severity: 'warning', detail: 'Panel x was dropped'}]}),
    bi_question_execute: () => ({
      result: {result_id: 'rq'},
      page: {view_model: {columns: [{key: 'region'}], rows: [['east']]}, page: {source_count: 1, next_cursor: ''}},
      redacted_columns: [], cache: {hit: false},
    }),
    resource_page: () => ({items: []}),
    semantic_model_list: () => ({items: []}),
    ...overrides.handlers,
  };
  const api = {
    calls,
    post: jest.fn(async (_url, payload) => {
      calls.push(payload);
      const handler = handlers[payload.action];
      if(!handler) return {data: {success: 0, errormsg: `unexpected ${payload.action}`}};
      try {
        return {data: {success: 1, data: await handler(payload.request)}};
      } catch(error) {
        return {data: {success: 0, errormsg: error.message}};
      }
    }),
  };
  const sent = (action) => calls.filter((call) => call.action === action);
  return {api, calls, sent, db};
}

const renderTool = (backend) => render(
  <Theme><BIQuestionsTool api={backend.api} endpointUrl={URL} previewDelay={0} /></Theme>);

const edit = async (name) => {
  fireEvent.click(await screen.findByRole('button', {name: `Edit dashboard ${name}`}));
  return screen.findByLabelText('Dashboard name');
};

describe('dashboard list', () => {
  it('lists dashboards and filters them by search', async () => {
    renderTool(fakeBackend());
    expect(await screen.findByRole('button', {name: 'Open dashboard Sales board'})).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search questions, dashboards and collections'), {target: {value: 'other'}});
    expect(screen.queryByRole('button', {name: 'Open dashboard Sales board'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Open dashboard Other board'})).toBeInTheDocument();
  });

  it('renames with the stored revision', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    fireEvent.click(await screen.findByRole('button', {name: 'Rename dashboard Sales board'}));
    const dialog = await screen.findByRole('dialog', {name: 'Rename dashboard'});
    fireEvent.change(within(dialog).getByLabelText('Dashboard name'), {target: {value: 'Renamed'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Rename'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_update')).toHaveLength(1));
    const request = backend.sent('bi_dashboard_update')[0].request;
    expect(request).toMatchObject({dashboard_id: 'd1', expected_revision: 3});
    expect(request.dashboard.name).toBe('Renamed');
  });

  it('archives with expected_revision and duplicates under a new name', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    fireEvent.click(await screen.findByRole('button', {name: 'Archive dashboard Sales board'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_status')).toHaveLength(1));
    expect(backend.sent('bi_dashboard_status')[0].request).toEqual({
      dashboard_id: 'd1', expected_revision: 3, status: 'archived'});
    fireEvent.click(screen.getByRole('button', {name: 'Duplicate dashboard Sales board'}));
    const dialog = await screen.findByRole('dialog', {name: 'Duplicate dashboard'});
    fireEvent.change(within(dialog).getByLabelText('Name of the copy'), {target: {value: 'Sales copy'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Duplicate'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_clone')).toHaveLength(1));
    expect(backend.sent('bi_dashboard_clone')[0].request).toEqual({dashboard_id: 'd1', name: 'Sales copy'});
  });

  it('moves a dashboard', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    fireEvent.click(await screen.findByRole('button', {name: 'Move dashboard Sales board'}));
    const dialog = await screen.findByRole('dialog', {name: 'Move dashboard'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Move'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_move')).toHaveLength(1));
    expect(backend.sent('bi_dashboard_move')[0].request).toMatchObject({dashboard_id: 'd1', expected_revision: 3});
  });
});

describe('unsaved changes guard', () => {
  it('blocks opening another dashboard until the person decides, and keeps the draft on Keep editing', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    const name = await edit('Sales board');
    expect(backend.sent('bi_dashboard_get')).toHaveLength(1);
    fireEvent.change(name, {target: {value: 'Edited name'}});

    fireEvent.click(screen.getByRole('button', {name: 'Open dashboard Other board'}));
    const dialog = await screen.findByRole('dialog', {name: 'Discard unsaved changes?'});
    expect(within(dialog).getByText(/open dashboard has changes/)).toBeInTheDocument();
    expect(backend.sent('bi_dashboard_get')).toHaveLength(1);

    fireEvent.click(within(dialog).getByRole('button', {name: 'Keep editing'}));
    expect(screen.queryByRole('dialog', {name: 'Discard unsaved changes?'})).not.toBeInTheDocument();
    expect(screen.getByLabelText('Dashboard name')).toHaveValue('Edited name');
    expect(backend.sent('bi_dashboard_get')).toHaveLength(1);

    fireEvent.click(screen.getByRole('button', {name: 'Open dashboard Other board'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Discard changes'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_get')).toHaveLength(2));
    expect(backend.sent('bi_dashboard_get')[1].request).toEqual({dashboard_id: 'd2'});
  });

  it('an unedited dashboard opens another without asking', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await edit('Sales board');
    fireEvent.click(screen.getByRole('button', {name: 'Open dashboard Other board'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_get')).toHaveLength(2));
    expect(screen.queryByRole('dialog', {name: 'Discard unsaved changes?'})).not.toBeInTheDocument();
  });

  it('is a plain-data intent: confirming performs exactly the blocked action', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    const name = await edit('Sales board');
    fireEvent.change(name, {target: {value: 'Edited name'}});
    fireEvent.click(screen.getByRole('button', {name: 'New dashboard'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Discard changes'}));
    expect(await screen.findByLabelText('Dashboard name')).toHaveValue('');
    expect(backend.sent('bi_dashboard_get')).toHaveLength(1);
  });
});

describe('editor', () => {
  it('saves with the stored revision and the server document shape', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    const name = await edit('Sales board');
    fireEvent.change(name, {target: {value: 'Edited name'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_update')).toHaveLength(1));
    const request = backend.sent('bi_dashboard_update')[0].request;
    expect(request).toMatchObject({dashboard_id: 'd1', expected_revision: 3});
    const {contract_version: _version, ...expected} = board;
    expect(request.dashboard).toEqual({...expected, name: 'Edited name'});
    expect(await screen.findByText('Saved as revision 4.')).toBeInTheDocument();
  });

  it('adds a text card and a tab and sends them on save', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await edit('Sales board');
    fireEvent.click(await screen.findByRole('button', {name: 'Add text card'}));
    fireEvent.click(screen.getByRole('button', {name: 'Add tab'}));
    const tabDialog = await screen.findByRole('dialog', {name: 'Add a tab'});
    fireEvent.change(within(tabDialog).getByLabelText('Tab name'), {target: {value: 'Second'}});
    fireEvent.click(within(tabDialog).getByRole('button', {name: 'Add tab'}));
    await waitFor(() => expect(screen.queryByRole('dialog', {name: 'Add a tab'})).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_update')).toHaveLength(1));
    const sent = backend.sent('bi_dashboard_update')[0].request.dashboard;
    expect(sent.cards.filter((card) => card.type === 'text')).toHaveLength(2);
    expect(sent.tabs).toHaveLength(2);
  });

  it('moves a card from the keyboard through its handle', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await edit('Sales board');
    await screen.findAllByRole('button', {name: 'Move by_region'});
    // The card chrome re-renders when the pinned questions load; use the live element.
    await waitFor(() => expect(backend.sent('bi_question_revision').length).toBeGreaterThan(0));
    fireEvent.keyDown(screen.getAllByRole('button', {name: 'Move by_region'})[0], {key: 'ArrowRight'});
    await waitFor(() => expect(screen.getByRole('button', {name: 'Save'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_update')).toHaveLength(1));
    const sent = backend.sent('bi_dashboard_update')[0].request.dashboard;
    expect(sent.cards.map((card) => card.layout)).not.toEqual(board.cards.map((card) => card.layout));
  });
});

describe('viewer', () => {
  const view = async (backend, name = 'Sales board') => {
    fireEvent.click(await screen.findByRole('button', {name: `Open dashboard ${name}`}));
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run').length).toBeGreaterThan(0));
  };

  it('runs every question card with the filter defaults and shows cache state', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await view(backend);
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run')).toHaveLength(3));
    const ids = backend.sent('bi_dashboard_card_run').map((call) => call.request.card_id).sort();
    expect(ids).toEqual(['by_region', 'detail', 'floor']);
    for(const call of backend.sent('bi_dashboard_card_run')) {
      expect(call.request).toMatchObject({dashboard_id: 'd1'});
      expect(call.request.bypass_cache).toBeUndefined();
    }
    expect(await screen.findAllByText(/^Cached at /)).not.toHaveLength(0);
  });

  it('refreshes one card bypassing the cache, and all cards', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await view(backend);
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run')).toHaveLength(3));
    const refresh = (await screen.findAllByRole('button', {name: /^Refresh (?!all)/}))[0];
    fireEvent.click(refresh);
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run')).toHaveLength(4));
    expect(backend.sent('bi_dashboard_card_run')[3].request.bypass_cache).toBe(true);
    fireEvent.click(screen.getByRole('button', {name: 'Refresh all cards'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run')).toHaveLength(7));
    expect(backend.sent('bi_dashboard_card_run').slice(4).every((call) => call.request.bypass_cache)).toBe(true);
  });

  it('shows a failed card without breaking the others', async () => {
    const backend = fakeBackend({handlers: {
      bi_dashboard_card_run: ({card_id: id}) => {
        if(id === 'detail') throw new Error('query failed');
        return {result: {result_id: id}, page: {view_model: {columns: [{key: 'a'}], rows: [[1]]},
          page: {source_count: 1, next_cursor: ''}}, redacted_columns: [], cache: {hit: false}};
      }}});
    renderTool(backend);
    await view(backend);
    expect(await screen.findByText(/This card could not run: query failed/)).toBeInTheDocument();
  });

  it('applies the filter bar values to every card', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await view(backend);
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run')).toHaveLength(3));
    const bar = await screen.findByRole('search', {name: 'Dashboard filters'});
    fireEvent.change(within(bar).getByLabelText('Minimum'), {target: {value: '9'}});
    fireEvent.click(within(bar).getByRole('button', {name: 'Apply filters'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run')).toHaveLength(6));
    expect(backend.sent('bi_dashboard_card_run')[5].request.filters).toMatchObject({floor: 9});
  });

  it('auto-refreshes on the chosen interval', async () => {
    jest.useFakeTimers();
    try {
      const backend = fakeBackend({db: {dashboards: [summary('d1', 'Sales board')]}});
      renderTool(backend);
      fireEvent.click(await screen.findByRole('button', {name: 'Open dashboard Sales board'}));
      await waitFor(() => expect(backend.sent('bi_dashboard_card_run')).toHaveLength(3));
      fireEvent.mouseDown(await screen.findByRole('combobox', {name: 'Auto-refresh'}));
      fireEvent.click(await screen.findByRole('option', {name: 'Every 30 seconds'}));
      await act(async () => { jest.advanceTimersByTime(31000); });
      await waitFor(() => expect(backend.sent('bi_dashboard_card_run').length).toBeGreaterThan(3));
    } finally {
      jest.useRealTimers();
    }
  });
});

describe('interactions', () => {
  it('a cell click resolves the cross-filter on the server and reruns with its exclusions', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    fireEvent.click(await screen.findByRole('button', {name: 'Open dashboard Sales board'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run')).toHaveLength(3));
    await waitFor(() => expect(document.querySelector('[data-bi-card="detail"] table')).toBeTruthy());
    fireEvent.click(within(document.querySelector('[data-bi-card="detail"]')).getAllByText('east')[0]);
    const choose = screen.queryByRole('dialog', {name: /What should this click do/});
    if(choose) fireEvent.click(within(choose).getAllByRole('button')[0]);
    await waitFor(() => expect(backend.sent('bi_dashboard_cross_filter').length).toBeGreaterThan(0));
    expect(backend.sent('bi_dashboard_cross_filter')[0].request).toMatchObject({
      dashboard_id: 'd1', cross_filter_id: 'click_region'});
    await waitFor(() => expect(backend.sent('bi_dashboard_card_run').length).toBeGreaterThan(3));
    const last = backend.sent('bi_dashboard_card_run').at(-1).request;
    expect(last.filters).toMatchObject(fixtures.cross.outcome.filters);
    expect(backend.sent('bi_dashboard_card_run').some((call) =>
      JSON.stringify(call.request.exclude) === JSON.stringify(fixtures.cross.outcome.exclude))).toBe(true);
  });
});

describe('history', () => {
  it('lists revisions and restores one as an unsaved draft', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await edit('Sales board');
    fireEvent.click(screen.getByRole('button', {name: 'History'}));
    const dialog = await screen.findByRole('dialog', {name: 'Dashboard revision history'});
    fireEvent.click(await within(dialog).findByRole('button', {name: 'Restore revision 2'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_revision').length).toBeGreaterThan(0));
    expect(await screen.findByText('Revision loaded as a draft. Save to append it as a new revision.')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Save'})).toBeEnabled();
  });
});

describe('monitoring import', () => {
  it('opens a converted dashboard as an unsaved draft with its loss report', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    fireEvent.click(await screen.findByRole('button', {name: 'Import monitoring dashboard'}));
    const dialog = await screen.findByRole('dialog', {name: 'Import monitoring dashboard'});
    const file = new File(['dashboard x {}'], 'monitor.ddn', {type: 'text/plain'});
    file.text = async () => 'dashboard x {}';
    fireEvent.change(dialog.querySelector('input[type="file"]'), {target: {files: [file]}});
    fireEvent.click(await within(dialog).findByRole('button', {name: 'Convert'}));
    await waitFor(() => expect(backend.sent('bi_dashboard_from_ddn')).toHaveLength(1));
    expect(backend.sent('bi_dashboard_from_ddn')[0].request.snapshot).toEqual({
      format: 'ddn-source-workspace@1', entry: 'dashboard.ddn', files: {'dashboard.ddn': 'dashboard x {}'}});
    expect(await screen.findByText(/Panel x was dropped/)).toBeInTheDocument();
    expect(backend.sent('bi_dashboard_create')).toHaveLength(0);
  });
});
