/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

import {fireEvent, render, screen, waitFor, within} from '@testing-library/react';
import Theme from 'sources/Theme';
import BIQuestionsTool from 'sources/cdeadmin_ui/modules/bi/BIQuestionsTool';
import {ConversionReport} from 'sources/cdeadmin_ui/modules/bi/SqlPanel';
import {conversions, questions} from './biFixtures';

// jsdom has no layout, so the heavy widgets are replaced by plain elements
// that keep the props the tool passes (label, value, rows).
jest.mock('sources/cdeadmin_ui/editors/CodeEditor', () => ({
  __esModule: true, default: ({label, value, onChange, readonly}) =>
    <textarea aria-label={label} value={value} readOnly={readonly}
      onChange={(event) => onChange?.(event.target.value)} />,
}));
jest.mock('sources/cdeadmin_ui/data/PagedDataGrid', () => ({
  __esModule: true, default: ({rows, columns}) =>
    <table aria-label="grid"><tbody>
      <tr>{columns.map((column) => <th key={column.key}>{column.name}</th>)}</tr>
      {rows.map((row, index) => <tr key={index}>{columns.map((column) =>
        <td key={column.key}>{String(row[column.key])}</td>)}</tr>)}
    </tbody></table>,
}));
jest.mock('sources/chartjs', () => ({
  __esModule: true, default: ({type, title}) => <div role="img" aria-label={title}>{type}</div>,
}));

const URL = '/browser/server/cde_workspace/1/2';

// MUI warns about popovers taller than jsdom's default 768px window.
beforeEach(() => {
  window.innerHeight = 1200;
});

function fakeBackend(overrides = {}) {
  const db = {
    tree: [{collection_id: 'c1', parent_id: null, name: 'Sales', description: '', children: []}],
    questions: [
      {question_id: 'q1', name: 'Big sales', collection_id: 'c1', status: 'active', revision: 3},
      {question_id: 'q2', name: 'Old report', collection_id: null, status: 'active', revision: 1},
    ],
    record: {question_id: 'q1', revision: 3, status: 'active',
      definition: {...questions.detail, collection_id: 'c1'}},
    ...overrides.db,
  };
  const calls = [];
  const handlers = {
    bi_collection_list: () => ({items: db.tree}),
    bi_question_list: () => ({items: db.questions}),
    bi_dashboard_list: () => ({items: db.dashboards || []}),
    bi_question_get: () => db.record,
    bi_collection_create: ({collection}) => ({collection_id: 'c2', ...collection, children: []}),
    bi_collection_update: ({collection}) => collection,
    bi_question_status: ({question_id: id, status}) => ({question_id: id, status}),
    bi_question_move: ({question_id: id}) => ({question_id: id}),
    bi_question_update: ({question}) => ({...db.record, revision: 4, definition: question}),
    bi_question_create: ({question}) => ({question_id: 'q9', revision: 1, status: 'active', definition: question}),
    bi_question_compile: () => ({source: 'SELECT region FROM sales', warnings: []}),
    bi_question_execute: () => ({
      result: {result_id: 'r1'},
      page: {view_model: {columns: [{key: 'region'}, {key: 'amount'}], rows: [['east', 5], ['west', 7]]},
        page: {source_count: 2, next_cursor: ''}},
      redacted_columns: ['ssn'], cache: {hit: false}, sql: 'SELECT region, amount FROM sales',
    }),
    bi_sql_to_question: () => conversions.exact,
    bi_question_history: () => ({items: [
      {revision: 3, created_at: '2026-01-02T03:04:05Z', status: 'active'},
      {revision: 2, created_at: '2026-01-01T03:04:05Z', status: 'active'}]}),
    bi_question_revision: ({revision}) => ({question_id: 'q1', revision,
      definition: {...questions.detail, name: `Revision ${revision}`}}),
    resource_page: () => ({items: [{resource_id: 'tbl-sales', resource_kind: 'table', display_name: 'sales',
      display_path: ['sales']}]}),
    resource_inspect: () => ({resource_id: 'tbl-sales', extensions: {native: {native: {columns: [
      {name: 'region', data_type: 'text'}, {name: 'amount', data_type: 'numeric'}]}}}}),
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
  return {api, calls, sent};
}

function renderTool(backend, props = {}) {
  return render(<Theme><BIQuestionsTool api={backend.api} endpointUrl={URL} previewDelay={0} {...props} /></Theme>);
}

const openQuestion = async (name) => {
  fireEvent.click(await screen.findByRole('button', {name: `Open ${name}`}));
  return screen.findByLabelText('Question name');
};

describe('collections and question list', () => {
  it('lists collections and questions and filters by name', async () => {
    renderTool(fakeBackend());
    expect(await screen.findByRole('button', {name: 'Open Big sales'})).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Open Old report'})).toBeInTheDocument();
    const nav = screen.getByRole('navigation', {name: 'Collections'});
    expect(within(nav).getByRole('button', {name: /^Sales/})).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search questions, dashboards and collections'), {target: {value: 'OLD'}});
    expect(screen.queryByRole('button', {name: 'Open Big sales'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Open Old report'})).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText('Search questions, dashboards and collections'), {target: {value: 'zzz'}});
    expect(screen.getByText('No question or collection matches the search.')).toBeInTheDocument();
  });

  it('shows only the questions of the selected collection', async () => {
    renderTool(fakeBackend());
    await screen.findByRole('button', {name: 'Open Old report'});
    const nav = screen.getByRole('navigation', {name: 'Collections'});
    fireEvent.click(within(nav).getByRole('button', {name: /^Sales/}));
    expect(screen.queryByRole('button', {name: 'Open Old report'})).not.toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Open Big sales'})).toBeInTheDocument();
  });

  it('creates a collection under the selected one', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await screen.findByRole('button', {name: 'Open Old report'});
    fireEvent.click(within(screen.getByRole('navigation', {name: 'Collections'})).getByRole('button', {name: /^Sales/}));
    fireEvent.click(screen.getByRole('button', {name: 'New collection'}));
    const dialog = await screen.findByRole('dialog', {name: 'New collection'});
    fireEvent.change(within(dialog).getByLabelText('Collection name'), {target: {value: ' Finance '}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Create'}));
    await waitFor(() => expect(backend.sent('bi_collection_create')).toHaveLength(1));
    expect(backend.sent('bi_collection_create')[0].request).toEqual({
      collection: {name: 'Finance', description: '', parent_id: 'c1'}});
    await waitFor(() => expect(screen.queryByRole('dialog', {name: 'New collection'})).not.toBeInTheDocument());
    expect(backend.sent('bi_collection_list').length).toBeGreaterThan(1);
  });

  it('renames a collection keeping its parent and description', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await screen.findByRole('button', {name: 'Open Old report'});
    fireEvent.click(within(screen.getByRole('navigation', {name: 'Collections'})).getByRole('button', {name: /^Sales/}));
    fireEvent.click(screen.getByRole('button', {name: 'Rename collection'}));
    const dialog = await screen.findByRole('dialog', {name: 'Rename collection'});
    fireEvent.change(within(dialog).getByLabelText('Collection name'), {target: {value: 'Revenue'}});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Rename'}));
    await waitFor(() => expect(backend.sent('bi_collection_update')).toHaveLength(1));
    expect(backend.sent('bi_collection_update')[0].request).toEqual({
      collection_id: 'c1', collection: {name: 'Revenue', description: '', parent_id: null}});
  });

  it('moves a question to the root with its stored revision', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await screen.findByRole('button', {name: 'Open Big sales'});
    fireEvent.click(screen.getByRole('button', {name: 'Move Big sales'}));
    const dialog = await screen.findByRole('dialog', {name: 'Move question'});
    fireEvent.mouseDown(within(dialog).getByRole('combobox'));
    fireEvent.click(await screen.findByRole('option', {name: 'No collection'}));
    fireEvent.click(within(dialog).getByRole('button', {name: 'Move'}));
    await waitFor(() => expect(backend.sent('bi_question_move')).toHaveLength(1));
    expect(backend.sent('bi_question_move')[0].request).toEqual({
      question_id: 'q1', expected_revision: 3, collection_id: null});
  });

  it('archives a question with its stored revision', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await screen.findByRole('button', {name: 'Open Big sales'});
    fireEvent.click(screen.getByRole('button', {name: 'Archive Big sales'}));
    await waitFor(() => expect(backend.sent('bi_question_status')).toHaveLength(1));
    expect(backend.sent('bi_question_status')[0].request).toEqual({
      question_id: 'q1', expected_revision: 3, status: 'archived'});
  });

  it('reports a failed change as an alert', async () => {
    renderTool(fakeBackend({handlers: {bi_question_status: () => { throw new Error('revision has changed'); }}}));
    fireEvent.click(await screen.findByRole('button', {name: 'Archive Old report'}));
    expect(await screen.findByRole('alert')).toHaveTextContent('revision has changed');
  });

  it('duplicates a question through bi_question_clone', async () => {
    const backend = fakeBackend({handlers: {bi_question_clone: ({name}) => ({question_id: 'q3', name})}});
    renderTool(backend);
    await screen.findByRole('button', {name: 'Open Big sales'});
    fireEvent.click(screen.getByRole('button', {name: 'Duplicate Big sales'}));
    const dialog = await screen.findByRole('dialog', {name: 'Duplicate question'});
    expect(within(dialog).getByLabelText('Name of the copy')).toHaveValue('Copy of Big sales');
    fireEvent.click(within(dialog).getByRole('button', {name: 'Duplicate'}));
    await waitFor(() => expect(backend.sent('bi_question_clone')).toHaveLength(1));
    expect(backend.sent('bi_question_clone')[0].request).toEqual({question_id: 'q1', name: 'Copy of Big sales'});
  });
});

describe('opening, previewing, running and saving a question', () => {
  it('compiles a live SQL preview without binding and runs with the result policy notes', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    expect(await openQuestion('Big sales')).toHaveValue('Big sales');
    await waitFor(() => expect(backend.sent('bi_question_compile')).toHaveLength(1));
    const compile = backend.sent('bi_question_compile')[0].request;
    expect(compile.question.query.builder.source).toEqual({relation: ['sales']});
    expect(compile).not.toHaveProperty('parameters');

    fireEvent.click(screen.getByRole('tab', {name: 'SQL preview'}));
    expect(await screen.findByLabelText('Compiled SQL')).toHaveValue('SELECT region FROM sales');
    fireEvent.click(screen.getByRole('tab', {name: 'Result'}));

    fireEvent.click(screen.getByRole('button', {name: 'Run'}));
    expect(await screen.findByRole('table', {name: 'grid'})).toBeInTheDocument();
    expect(screen.getByText('2 of 2 rows loaded')).toBeInTheDocument();
    expect(screen.getByText('Redacted: ssn')).toBeInTheDocument();
    expect(screen.getByText('west')).toBeInTheDocument();
    const execute = backend.sent('bi_question_execute')[0].request;
    expect(execute).toMatchObject({page_size: 100});
    expect(execute).not.toHaveProperty('bypass_cache');

    fireEvent.click(screen.getByRole('button', {name: 'Refresh'}));
    await waitFor(() => expect(backend.sent('bi_question_execute')).toHaveLength(2));
    expect(backend.sent('bi_question_execute')[1].request.bypass_cache).toBe(true);
  });

  it('draws a chart through the shared chart wrapper', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await openQuestion('Big sales');
    fireEvent.click(screen.getByRole('button', {name: 'Run'}));
    await screen.findByRole('table', {name: 'grid'});
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Display as'}));
    fireEvent.click(await screen.findByRole('option', {name: 'Bar'}));
    expect(await screen.findByRole('img', {name: 'Bar chart of the query result'})).toHaveTextContent('bar');
    expect(screen.queryByRole('table', {name: 'grid'})).not.toBeInTheDocument();
  });

  it('shows an execution failure and keeps the editor usable', async () => {
    const backend = fakeBackend({handlers: {bi_question_execute: () => { throw new Error('permission denied'); }}});
    renderTool(backend);
    await openQuestion('Big sales');
    fireEvent.click(screen.getByRole('button', {name: 'Run'}));
    expect(await screen.findByText('permission denied')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Run'})).toBeEnabled();
  });

  it('saves with the expected revision and marks the question clean', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    const name = await openQuestion('Big sales');
    expect(screen.getByRole('button', {name: 'Save'})).toBeDisabled();
    fireEvent.change(name, {target: {value: 'Bigger sales'}});
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    expect(await screen.findByText('Saved as revision 4.')).toBeInTheDocument();
    const update = backend.sent('bi_question_update')[0].request;
    expect(update.question_id).toBe('q1');
    expect(update.expected_revision).toBe(3);
    expect(update.question.name).toBe('Bigger sales');
    expect(screen.queryByText('Unsaved changes')).not.toBeInTheDocument();
    expect(screen.getByText('Revision 4')).toBeInTheDocument();
  });

  it('offers to reload the latest revision after a conflict', async () => {
    const backend = fakeBackend({handlers: {bi_question_update: () => {
      throw new Error('The question revision has changed.'); }}});
    renderTool(backend);
    const name = await openQuestion('Big sales');
    fireEvent.change(name, {target: {value: 'Mine'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    expect(await screen.findByText(/revision has changed/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', {name: 'Reload latest'}));
    expect(await screen.findByText('Loaded the latest saved revision.')).toBeInTheDocument();
    expect(screen.getByLabelText('Question name')).toHaveValue('Big sales');
  });

  it('saves a copy as a new question from Save as', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await openQuestion('Big sales');
    fireEvent.click(screen.getByRole('button', {name: 'Save as...'}));
    const dialog = await screen.findByRole('dialog', {name: 'Save a copy'});
    expect(within(dialog).getByLabelText('Question name')).toHaveValue('Copy of Big sales');
    fireEvent.click(within(dialog).getByRole('button', {name: 'Save copy'}));
    await waitFor(() => expect(backend.sent('bi_question_create')).toHaveLength(1));
    const created = backend.sent('bi_question_create')[0].request.question;
    expect(created.name).toBe('Copy of Big sales');
    expect(created.collection_id).toBe('c1');
  });
});

describe('building a new question', () => {
  it('picks a table, columns and a typed filter, previews and saves', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    fireEvent.click(await screen.findByRole('button', {name: 'New question'}));
    fireEvent.mouseDown(await screen.findByRole('combobox', {name: 'Start from'}));
    fireEvent.click(await screen.findByRole('option', {name: 'Table: sales'}));

    const group = await screen.findByRole('group', {name: 'Columns'});
    fireEvent.click(await within(group).findByLabelText(/^region/));
    fireEvent.click(within(group).getByLabelText(/^amount/));
    await waitFor(() => expect(backend.sent('bi_question_compile').length).toBeGreaterThan(0));
    const compiled = backend.sent('bi_question_compile').at(-1).request.question;
    expect(compiled.query.kind).toBe('builder');
    expect(compiled.query.builder.source).toEqual({relation: ['sales']});
    expect(compiled.query.builder.columns).toEqual([{column: 'region'}, {column: 'amount'}]);

    fireEvent.change(screen.getByLabelText('Question name'), {target: {value: 'Fresh'}});
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    const dialog = await screen.findByRole('dialog', {name: 'Save question'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(backend.sent('bi_question_create')).toHaveLength(1));
    expect(backend.sent('bi_question_create')[0].request.question.name).toBe('Fresh');
    expect(await screen.findByText('Saved Fresh.')).toBeInTheDocument();
  });

  it('keeps Run disabled until the question is complete', async () => {
    renderTool(fakeBackend());
    fireEvent.click(await screen.findByRole('button', {name: 'New question'}));
    expect(await screen.findByRole('button', {name: 'Run'})).toBeDisabled();
    expect(screen.getByRole('button', {name: 'Save as...'})).toBeDisabled();
  });
});

describe('SQL mode and conversion', () => {
  const startSql = async (backend) => {
    renderTool(backend);
    fireEvent.click(await screen.findByRole('button', {name: 'New question'}));
    fireEvent.click(await screen.findByRole('tab', {name: 'SQL'}));
    const editor = await screen.findByLabelText('SQL statement');
    fireEvent.change(editor, {target: {value: 'SELECT region FROM sales'}});
    return editor;
  };

  it('converts an exactly mappable statement and switches to the builder', async () => {
    const backend = fakeBackend();
    await startSql(backend);
    fireEvent.click(screen.getByRole('button', {name: 'Convert to builder'}));
    const report = await screen.findByRole('region', {name: 'Conversion to the builder'});
    expect(within(report).getByText('The builder reproduces this statement exactly.')).toBeInTheDocument();
    expect(backend.sent('bi_sql_to_question')[0].request.sql).toBe('SELECT region FROM sales');
    fireEvent.click(within(report).getByRole('button', {name: 'Switch to builder'}));
    expect(await screen.findByRole('combobox', {name: 'Start from'})).toHaveTextContent('Table: sales');
    expect(screen.queryByLabelText('SQL statement')).not.toBeInTheDocument();
  });

  it('shows why a statement cannot be converted and stays in SQL', async () => {
    const backend = fakeBackend({handlers: {bi_sql_to_question: () => conversions.none}});
    await startSql(backend);
    fireEvent.click(screen.getByRole('button', {name: 'Convert to builder'}));
    const report = await screen.findByRole('region', {name: 'Conversion to the builder'});
    expect(within(report).getByText('This statement cannot be shown in the builder, so it stays SQL.')).toBeInTheDocument();
    for(const item of conversions.none.loss) {
      expect(within(report).getByText(item.detail, {exact: false})).toBeInTheDocument();
    }
    expect(within(report).queryByRole('button')).not.toBeInTheDocument();
    expect(screen.getByLabelText('SQL statement')).toBeInTheDocument();
  });

  it('forgets a report once the statement changes', async () => {
    const editor = await startSql(fakeBackend());
    fireEvent.click(screen.getByRole('button', {name: 'Convert to builder'}));
    await screen.findByRole('region', {name: 'Conversion to the builder'});
    fireEvent.change(editor, {target: {value: 'SELECT 2'}});
    expect(screen.queryByRole('region', {name: 'Conversion to the builder'})).not.toBeInTheDocument();
  });
});

describe('ConversionReport', () => {
  it('lists the differences of a lossy conversion and requires accepting them', () => {
    const onSwitch = jest.fn();
    render(<Theme><ConversionReport outcome={conversions.lossy} onSwitch={onSwitch} /></Theme>);
    expect(screen.getByText(/only with the differences below/)).toBeInTheDocument();
    for(const item of conversions.lossy.loss) {
      expect(screen.getByText(item.detail, {exact: false})).toBeInTheDocument();
    }
    fireEvent.click(screen.getByRole('button', {name: 'Switch to builder and accept the differences'}));
    expect(onSwitch).toHaveBeenCalledWith(conversions.lossy.question);
  });

  it('renders nothing without an outcome', () => {
    const {container} = render(<Theme><ConversionReport outcome={null} onSwitch={() => {}} /></Theme>);
    expect(container).toBeEmptyDOMElement();
  });
});

describe('revision history', () => {
  it('lists revisions, previews one as SQL and restores it as an unsaved draft', async () => {
    const backend = fakeBackend();
    renderTool(backend);
    await openQuestion('Big sales');
    fireEvent.click(screen.getByRole('button', {name: 'History'}));
    const dialog = await screen.findByRole('dialog', {name: 'Revision history'});
    const list = await within(dialog).findByRole('list', {name: 'Revisions'});
    expect(within(list).getAllByRole('listitem')).toHaveLength(2);
    expect(within(list).getByText('Current')).toBeInTheDocument();

    fireEvent.click(within(dialog).getByRole('button', {name: 'Preview SQL of revision 2'}));
    expect(await within(dialog).findByLabelText('Revision SQL')).toHaveValue('SELECT region FROM sales');
    expect(backend.sent('bi_question_compile').at(-1).request).toEqual({question_id: 'q1', revision: 2});

    fireEvent.click(within(dialog).getByRole('button', {name: 'Restore revision 2'}));
    await waitFor(() => expect(screen.queryByRole('dialog', {name: 'Revision history'})).not.toBeInTheDocument());
    expect(screen.getByLabelText('Question name')).toHaveValue('Revision 2');
    expect(screen.getByText('Unsaved changes')).toBeInTheDocument();
    // Restoring changes nothing on the server until the draft is saved.
    expect(backend.sent('bi_question_update')).toHaveLength(0);
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(backend.sent('bi_question_update')).toHaveLength(1));
    expect(backend.sent('bi_question_update')[0].request.expected_revision).toBe(3);
  });
});

describe('unsaved changes', () => {
  it('asks before another question replaces edits, and keeps them on request', async () => {
    const onDirtyChange = jest.fn();
    const backend = fakeBackend();
    renderTool(backend, {onDirtyChange});
    const name = await openQuestion('Big sales');
    fireEvent.change(name, {target: {value: 'Edited'}});
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(true));
    // The open question's own actions are blocked while it has edits.
    expect(screen.getByRole('button', {name: 'Rename Big sales'})).toBeDisabled();

    fireEvent.click(screen.getByRole('button', {name: 'Open Old report'}));
    const dialog = await screen.findByRole('dialog', {name: 'Discard unsaved changes?'});
    fireEvent.click(within(dialog).getByRole('button', {name: 'Keep editing'}));
    expect(screen.getByLabelText('Question name')).toHaveValue('Edited');

    fireEvent.click(screen.getByRole('button', {name: 'Open Old report'}));
    fireEvent.click(within(await screen.findByRole('dialog', {name: 'Discard unsaved changes?'}))
      .getByRole('button', {name: 'Discard changes'}));
    await waitFor(() => expect(backend.sent('bi_question_get')).toHaveLength(2));
    await waitFor(() => expect(onDirtyChange).toHaveBeenLastCalledWith(false));
  });
});
