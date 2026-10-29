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
import {sharingFixtures as fx} from './sharingFixtures';
import {alertFixtures as alerts} from './alertFixtures';

jest.mock('sources/cdeadmin_ui/editors/CodeEditor', () => ({
  __esModule: true, default: ({label, value, onChange, readonly}) =>
    <textarea aria-label={label} value={value} readOnly={readonly}
      onChange={(event) => onChange?.(event.target.value)} />,
}));
jest.mock('sources/cdeadmin_ui/data/PagedDataGrid', () => ({
  __esModule: true, default: ({rows}) => <table aria-label="grid"><tbody>
    {rows.map((row, index) => <tr key={index}><td>{String(row[0])}</td></tr>)}</tbody></table>,
}));
jest.mock('sources/chartjs', () => ({
  __esModule: true, default: ({type, title}) => <div role="img" aria-label={title}>{type}</div>,
}));

const URL = '/browser/server/cde_workspace/1/2';

beforeEach(() => { window.innerHeight = 1200; });

// The backend as a viewer sees it: nothing of their own, everything shared (real responses).
function viewerBackend(record, extra = {}) {
  const calls = [];
  const handlers = {
    bi_collection_list: () => ({items: []}),
    bi_question_list: () => ({items: fx.viewerQuestions}),
    bi_dashboard_list: () => ({items: fx.viewerDashboards}),
    bi_shared_with_me: () => fx.sharedWithMe,
    bi_question_get: () => record,
    bi_question_execute: () => ({
      result: {result_id: 'r1'},
      page: {view_model: {columns: [{key: 'region'}], rows: [['east']]}, page: {source_count: 1, next_cursor: ''}},
      redacted_columns: [], cache: {hit: false}, sql: fx.rawRunForViewer.sql, sql_redacted: fx.rawRunForViewer.sql_redacted,
    }),
    bi_question_compile: () => ({source: null, warnings: []}),
    semantic_model_list: () => ({items: []}),
    resource_page: () => ({items: []}),
    ...extra,
  };
  const api = {
    calls,
    post: jest.fn(async (_url, payload) => {
      calls.push(payload);
      const handler = handlers[payload.action];
      if(!handler) return {data: {success: 0, errormsg: `unexpected ${payload.action}`}};
      return {data: {success: 1, data: await handler(payload.request)}};
    }),
  };
  return api;
}

const renderTool = (api) => render(<Theme><BIQuestionsTool api={api} endpointUrl={URL} previewDelay={0} /></Theme>);

describe('a viewer in the BI module', () => {
  it('finds shared content under the Shared with me root and gets no editing controls', async () => {
    renderTool(viewerBackend(fx.plainForViewer));
    const nav = await screen.findByRole('navigation', {name: 'Collections'});
    expect(screen.queryByRole('button', {name: 'Open Detail by region'})).not.toBeInTheDocument();
    fireEvent.click(await within(nav).findByRole('button', {name: /^Shared with me/}));
    expect(await screen.findByRole('button', {name: 'Open East revenue'})).toBeInTheDocument();
    expect(screen.getAllByText('Shared: view only').length).toBeGreaterThan(0);
    for(const verb of ['Rename', 'Move', 'Archive', 'Duplicate', 'Share']) {
      const control = screen.queryByRole('button', {name: `${verb} East revenue`});
      if(control) expect(control).toBeDisabled();
    }
    expect(screen.queryByRole('button', {name: 'Share East revenue'})).not.toBeInTheDocument();
  });

  it('opens a question read only', async () => {
    renderTool(viewerBackend(fx.plainForViewer));
    const nav = await screen.findByRole('navigation', {name: 'Collections'});
    fireEvent.click(await within(nav).findByRole('button', {name: /^Shared with me/}));
    fireEvent.click(await screen.findByRole('button', {name: 'Open East revenue'}));
    expect(await screen.findByText(/Read only: you can run this question but not change it/)).toBeInTheDocument();
    expect(screen.getByLabelText('Question name')).toBeDisabled();
    expect(screen.queryByRole('button', {name: 'Share...'})).not.toBeInTheDocument();
    expect(screen.queryByRole('button', {name: 'Embed...'})).not.toBeInTheDocument();
  });

  it('never shows the SQL of a raw question and runs it by id', async () => {
    const api = viewerBackend(fx.rawForViewer);
    renderTool(api);
    const nav = await screen.findByRole('navigation', {name: 'Collections'});
    fireEvent.click(await within(nav).findByRole('button', {name: /^Shared with me/}));
    fireEvent.click(await screen.findByRole('button', {name: 'Open Secret revenue'}));
    expect(await screen.findByText(/The SQL of this question is hidden/)).toBeInTheDocument();
    expect(screen.getByText(/its SQL is hidden/)).toBeInTheDocument();
    await waitFor(() => expect(api.calls.some((call) => call.action === 'bi_question_get')).toBe(true));
    expect(document.body.textContent).not.toContain('zzz_hidden_filter');
  });

  it('lets a viewer schedule alerts on a shared question with their own access, in-app and mail only', async () => {
    const api = viewerBackend(fx.plainForViewer, {
      bi_alert_catalog: () => alerts.catalog,
      bi_alert_list: () => ({items: alerts.listForViewer.items}),
      bi_alert_schedule_preview: () => alerts.schedulePreview,
    });
    renderTool(api);
    const nav = await screen.findByRole('navigation', {name: 'Collections'});
    fireEvent.click(await within(nav).findByRole('button', {name: /^Shared with me/}));
    fireEvent.click(await screen.findByRole('button', {name: 'Open East revenue'}));
    fireEvent.click(await screen.findByRole('button', {name: 'Alerts...'}));
    const panel = await screen.findByRole('region', {name: 'Alerts and subscriptions'});
    expect(await within(panel).findByText('Viewer watch')).toBeInTheDocument();
    expect(within(panel).getByText('The owner can no longer view the resource.')).toBeInTheDocument();
    await waitFor(() => expect(within(panel).getByRole('button', {name: 'New alert'})).toBeEnabled());
    expect(api.calls.filter((call) => call.action === 'bi_alert_list')[0].request).toMatchObject({
      resource_type: 'question'});
    fireEvent.click(within(panel).getByRole('button', {name: 'New alert'}));
    const dialog = await screen.findByRole('dialog');
    fireEvent.mouseDown(within(dialog).getByRole('combobox', {name: 'Add a channel'}));
    expect((await screen.findAllByRole('option')).map((option) => option.textContent))
      .toEqual(['In-app notification', 'Email']);
  });
});
