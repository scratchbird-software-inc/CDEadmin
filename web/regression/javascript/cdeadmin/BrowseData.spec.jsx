/////////////////////////////////////////////////////////////
// Browse data (owner direction 2026-11-05, 2026-11-06): a resource's context
// menu opens the query editor holding text that reads every record of it.
// The connector's provider builds the text (server tests cover each one);
// here the editor's handling of it is checked. It is never run automatically.
/////////////////////////////////////////////////////////////

import {TextEncoder} from 'util';
import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import LanguageSourceEditor from 'sources/cdeadmin_ui/editors/LanguageSourceEditor';
import {requestSQLSource, takeSQLSourceRequest, useSQLSourceRequest} from 'sources/cdeadmin_ui/editors/SQLConnections';
import {withTheme} from '../fake_theme';

// 2026-11-06: the browser-side builder (relationSelect.js) and its quoting
// tests were retired; each provider now builds the text on the server.
const ASSETS = 'SELECT "ASSET_ID", "TAG", "Mixed ""Case"""\nFROM "ASSETS"';
const VIEW = 'SELECT "WORK_ORDER_ID"\nFROM "OPEN_WORK_ORDERS"';
const request = (source, nonce, extra={}) => ({source, languageProfile: 'firebird-sql', nonce, ...extra});

describe('Browse data in the SQL editor', () => {
  const Component = withTheme(LanguageSourceEditor);
  let encoder;
  beforeEach(() => {encoder = global.TextEncoder; global.TextEncoder = TextEncoder;});
  afterEach(() => {global.TextEncoder = encoder;});
  const props = (overrides={}) => ({language: {language_profile: 'firebird-sql', starter_source: 'SELECT 1 FROM RDB$DATABASE'},
    databaseTargetId: 'db', clientSqlDialect: 3, onChange: jest.fn(),
    post: jest.fn().mockResolvedValue({resources: []}),
    ensureSession: jest.fn(), onScriptLock: jest.fn(), onExecute: jest.fn(), ...overrides});

  it('fills an empty editor with the provider text and does not run it', async () => {
    const values = props({source: ''});
    render(<Component {...values} selectRequest={request(ASSETS, 1)} />);
    await waitFor(() => expect(values.onChange).toHaveBeenCalledWith(ASSETS));
    expect(values.onExecute).not.toHaveBeenCalled();
    expect(values.post.mock.calls.map(([payload]) => payload.action)).not.toContain('execute');
  });

  it('replaces the untouched starter statement without asking', async () => {
    const values = props({source: 'SELECT 1 FROM RDB$DATABASE'});
    render(<Component {...values} selectRequest={request(VIEW, 2)} />);
    await waitFor(() => expect(values.onChange).toHaveBeenCalledWith(VIEW));
  });

  it('asks before replacing text the user wrote', async () => {
    const values = props({source: 'SELECT draft FROM work'});
    render(<Component {...values} selectRequest={request(ASSETS, 3)} />);
    expect(await screen.findByText('Replace the editor text?')).toBeInTheDocument();
    // The code editor reports its initial text on mount; the statement
    // itself must not have been applied.
    expect(values.onChange).not.toHaveBeenCalledWith(ASSETS);
    fireEvent.click(screen.getByRole('button', {name: 'Keep current text'}));
    expect(values.onChange).not.toHaveBeenCalledWith(ASSETS);
    await waitFor(() => expect(screen.queryByText('Replace the editor text?')).not.toBeInTheDocument());
  });

  it('replaces user text only after Replace', async () => {
    const values = props({source: 'SELECT draft FROM work'});
    render(<Component {...values} selectRequest={request(ASSETS, 4)} />);
    fireEvent.click(await screen.findByRole('button', {name: 'Replace'}));
    expect(values.onChange).toHaveBeenCalledWith(ASSETS);
  });

  it('replaces its own untouched statement without asking, but asks once it is edited', async () => {
    const values = props({source: ''});
    const {rerender} = render(<Component {...values} selectRequest={request(ASSETS, 10)} />);
    await waitFor(() => expect(values.onChange).toHaveBeenCalledWith(ASSETS));
    rerender(<Component {...values} source={ASSETS} selectRequest={request(VIEW, 11)} />);
    await waitFor(() => expect(values.onChange).toHaveBeenCalledWith(VIEW));
    expect(screen.queryByText('Replace the editor text?')).not.toBeInTheDocument();
    rerender(<Component {...values} source={VIEW + ' WHERE 1 = 1'} selectRequest={request(ASSETS, 12)} />);
    expect(await screen.findByText('Replace the editor text?')).toBeInTheDocument();
  });

  it('leaves the text alone while a statement is running', async () => {
    const values = props({source: '', disabled: true});
    render(<Component {...values} selectRequest={request(ASSETS, 20)} />);
    expect(await screen.findByText(/Finish or cancel the current statement/)).toBeInTheDocument();
    expect(values.onChange).not.toHaveBeenCalledWith(ASSETS);
  });

  it('names the dialect the text is written in when another one is chosen', async () => {
    const values = props({source: ''});
    render(<Component {...values} selectRequest={request('MATCH (n:`Customer`) RETURN n', 5,
      {languageProfile: 'cypher', languageTitle: 'Cypher'})} />);
    expect(await screen.findByText(/Browse data is written in Cypher\. Choose that dialect/)).toBeInTheDocument();
    expect(values.onChange).not.toHaveBeenCalledWith(expect.stringMatching(/^MATCH/));
  });
});

describe('SQL source requests', () => {
  function Probe() {
    const request = useSQLSourceRequest('connection-a');
    return <span aria-label="request">{request ? `${request.resource_id}:${request.nonce}` : 'none'}</span>;
  }

  it('reach an editor that is already open and are taken once', () => {
    render(<Probe />);
    expect(screen.getByLabelText('request')).toHaveTextContent('none');
    act(() => requestSQLSource('connection-b', {resource_id: 'table:OTHER'}));
    expect(screen.getByLabelText('request')).toHaveTextContent('none');
    act(() => requestSQLSource('connection-a', {resource_id: 'table:ASSETS'}));
    const [, nonce] = screen.getByLabelText('request').textContent.split(':').slice(-2);
    expect(screen.getByLabelText('request')).toHaveTextContent('table:ASSETS');
    act(() => takeSQLSourceRequest('connection-a', Number(nonce) + 1));
    expect(screen.getByLabelText('request')).toHaveTextContent('table:ASSETS');
    act(() => {takeSQLSourceRequest('connection-a', Number(nonce)); requestSQLSource('connection-c', {resource_id: 'x'});});
    expect(screen.getByLabelText('request')).toHaveTextContent('none');
  });
});
