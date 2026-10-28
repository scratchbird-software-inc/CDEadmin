import {libraries} from './ddnTestRuntime';
import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdStatementDetails, {statementFiles} from 'sources/Dialogs/FirebirdStatementDetails';
import getApiInstance from 'sources/api_instance';
import {withTheme} from '../fake_theme';

jest.mock('sources/api_instance', () => ({__esModule: true, default: jest.fn()}));
jest.mock('sources/url_for', () => ({__esModule: true, default: () => '/monitor/statement'}));
jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({DDNViewerSurface: ({files}) => <pre>{files['statement.ddn']}</pre>}));

describe('Firebird statement inspection', () => {
  const Component = withTheme(FirebirdStatementDetails);
  let height;
  beforeEach(() => {height = window.innerHeight; window.innerHeight = 1200;});
  afterEach(() => {window.innerHeight = height;});
  const row = {statement_id: '17', attachment_id: '19', compiled_statement_id: '21', timestamp: 'native-time'};
  const sample = {sample_id: 'sample', groups: {statement_details: {status: 'available', values: {rows: [row]}}}};
  it('fetches only on request and sends the exact sampled identity', async () => {
    const post = jest.fn().mockResolvedValue({data: {data: {status: 'available', observed_at: 'now', identity: row,
      sql_text: {value: 'SELECT 1', truncated: false}, explained_plan: {value: 'native plan', truncated: true}}}});
    getApiInstance.mockReturnValue({post});
    render(<Component serverId={8} targetId="registered db" sample={sample} />);
    expect(screen.getByText('SR-F-001372')).toBeVisible();
    expect(post).not.toHaveBeenCalled();
    fireEvent.mouseDown(screen.getByLabelText('Statement to inspect'));
    fireEvent.click(await screen.findByRole('option', {name: '17 (attachment 19)'}));
    fireEvent.click(screen.getByRole('button', {name: 'Inspect SQL and plan'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith('/monitor/statement?target_id=registered%20db', {...row, sample_id: 'sample'}));
    expect(await screen.findByText(/Native statement inspection/)).toHaveTextContent('native plan');
    expect(screen.queryByRole('button', {name: /execute|cancel statement/i})).toBeNull();
  });
  it('keeps native text as quoted DDN data, including multiline delimiters', () => {
    const text = 'quote " }\nview injected { /*';
    const files = statementFiles({sql_text: {value: text, truncated: true}, explained_plan: {value: null}});
    const parsed=libraries.language.decodeSources({entry:'statement.ddn',files:[{id:'statement.ddn',text:files['statement.ddn'],revision:'test',encoding:'utf-8',writable:true}]});
    expect(parsed.syntaxValid).toBe(true);
    const records=libraries.model.listRecords(parsed.normalized);
    expect(records.filter(row=>row.kind==='view')).toHaveLength(1);
    const record=records.find(row=>row.ref.id==='r0').record.metadata.x_record;
    expect(JSON.parse(record.native_json).text).toBe(text);
    expect(record.truncated).toBe('Yes');
  });
});
