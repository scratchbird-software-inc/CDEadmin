/////////////////////////////////////////////////////////////
// Browse data (owner direction 2026-11-05): a table or view's context menu
// opens the SQL editor with SELECT of every column, built from the editor's
// own metadata and quoting. The statement is never run automatically.
/////////////////////////////////////////////////////////////

import {TextEncoder} from 'util';
import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import LanguageSourceEditor from 'sources/cdeadmin_ui/editors/LanguageSourceEditor';
import {relationSelectSource} from 'sources/cdeadmin_ui/editors/relationSelect';
import {firebirdSQLConfig} from 'sources/cdeadmin_ui/editors/firebirdSyntax';
import {nativeSQLConfig} from 'sources/cdeadmin_ui/editors/nativeCompletion';
import {requestSQLSource, takeSQLSourceRequest, useSQLSourceRequest} from 'sources/cdeadmin_ui/editors/SQLConnections';
import {withTheme} from '../fake_theme';

const FIREBIRD_RESOURCES = [
  {resource_kind: 'table', display_name: 'ASSETS', display_path: ['ASSETS']},
  {resource_kind: 'column', display_name: 'ASSET_ID', display_path: ['ASSETS', 'ASSET_ID']},
  {resource_kind: 'column', display_name: 'TAG', display_path: ['ASSETS', 'TAG']},
  {resource_kind: 'column', display_name: 'Mixed "Case"', display_path: ['ASSETS', 'Mixed "Case"']},
  {resource_kind: 'column', display_name: 'RDB$DB_KEY', display_path: ['ASSETS', 'RDB$DB_KEY'],
    native_identifier_token: true, hidden_from_star: true},
  {resource_kind: 'view', display_name: 'OPEN_WORK_ORDERS', display_path: ['OPEN_WORK_ORDERS']},
  {resource_kind: 'column', display_name: 'WORK_ORDER_ID', display_path: ['OPEN_WORK_ORDERS', 'WORK_ORDER_ID']},
];

describe('relation SELECT from editor metadata', () => {
  it('quotes Firebird names as the editor does and leaves out columns hidden from star', () => {
    const {schema} = firebirdSQLConfig('', 3, FIREBIRD_RESOURCES);
    expect(relationSelectSource(schema, 'ASSETS', ['ASSETS'])).toEqual({
      source: 'SELECT "ASSET_ID", "TAG", "Mixed ""Case"""\nFROM "ASSETS"'});
    expect(relationSelectSource(schema, 'OPEN_WORK_ORDERS').source).toBe(
      'SELECT "WORK_ORDER_ID"\nFROM "OPEN_WORK_ORDERS"');
  });

  it('uses unquoted names in Firebird dialect 1, as the editor does', () => {
    const resources = FIREBIRD_RESOURCES.filter((item) => item.display_name !== 'Mixed "Case"');
    const {schema} = firebirdSQLConfig('', 1, resources);
    expect(relationSelectSource(schema, 'ASSETS').source).toBe('SELECT ASSET_ID, TAG\nFROM ASSETS');
  });

  it('qualifies a native relation with its schema and keeps column order', () => {
    const config = nativeSQLConfig({context: {engine: 'sqlite', default_schema: 'main'}, resources: [
      {resource_kind: 'table', display_path: ['main', 'orders']},
      {resource_kind: 'column', display_path: ['main', 'orders', 'id']},
      {resource_kind: 'column', display_path: ['main', 'orders', 'total']},
      {resource_kind: 'column', display_path: ['main', 'orders', 'rowid'], hidden_from_star: true},
      {resource_kind: 'table', display_path: ['archive', 'orders']},
      {resource_kind: 'column', display_path: ['archive', 'orders', 'old_id']},
    ]});
    expect(relationSelectSource(config.schema, 'orders', ['main', 'tables', 'orders']).source).toBe(
      'SELECT "id", "total"\nFROM "main"."orders"');
    expect(relationSelectSource(config.schema, 'orders', ['archive', 'orders']).source).toBe(
      'SELECT "old_id"\nFROM "archive"."orders"');
    expect(relationSelectSource(config.schema, 'orders', []).error).toMatch(/More than one relation/);
  });

  it('quotes MySQL names with backticks unless ANSI_QUOTES is set', () => {
    const resources = [
      {resource_kind: 'table', display_path: ['shop', 'order`s']},
      {resource_kind: 'column', display_path: ['shop', 'order`s', 'id']},
    ];
    expect(relationSelectSource(nativeSQLConfig({context: {engine: 'mysql', sql_mode: ''}, resources}).schema,
      'order`s').source).toBe('SELECT `id`\nFROM `shop`.`order``s`');
    expect(relationSelectSource(nativeSQLConfig({context: {engine: 'mysql', sql_mode: 'ANSI_QUOTES'}, resources}).schema,
      'order`s').source).toBe('SELECT "id"\nFROM "shop"."order`s"');
  });

  it('falls back to the session database when two MySQL databases hold the name', () => {
    const resources = [
      {resource_kind: 'table', display_path: ['shop', 'orders']},
      {resource_kind: 'column', display_path: ['shop', 'orders', 'id']},
      {resource_kind: 'table', display_path: ['archive', 'orders']},
      {resource_kind: 'column', display_path: ['archive', 'orders', 'old_id']},
    ];
    const config = nativeSQLConfig({context: {engine: 'mysql', sql_mode: '', default_schema: 'shop'}, resources});
    expect(config.defaultSchema).toBe('shop');
    expect(relationSelectSource(config.schema, 'orders', [], config.defaultSchema).source).toBe(
      'SELECT `id`\nFROM `shop`.`orders`');
    expect(relationSelectSource(config.schema, 'orders', ['archive', 'orders'], config.defaultSchema).source).toBe(
      'SELECT `old_id`\nFROM `archive`.`orders`');
    expect(relationSelectSource(config.schema, 'orders', [], 'elsewhere').error).toMatch(/More than one relation/);
  });

  it('reports a relation the metadata does not list', () => {
    const {schema} = firebirdSQLConfig('', 3, FIREBIRD_RESOURCES);
    expect(relationSelectSource(schema, 'MISSING').error).toMatch(/lists no columns for MISSING/);
  });
});

describe('Browse data in the SQL editor', () => {
  const Component = withTheme(LanguageSourceEditor);
  let encoder;
  beforeEach(() => {encoder = global.TextEncoder; global.TextEncoder = TextEncoder;});
  afterEach(() => {global.TextEncoder = encoder;});
  const props = (overrides={}) => ({language: {language_profile: 'firebird-sql', starter_source: 'SELECT 1 FROM RDB$DATABASE'},
    databaseTargetId: 'db', clientSqlDialect: 3, onChange: jest.fn(),
    post: jest.fn().mockResolvedValue({resources: FIREBIRD_RESOURCES}),
    ensureSession: jest.fn(), onScriptLock: jest.fn(), onExecute: jest.fn(), ...overrides});

  it('fills an empty editor with the SELECT and does not run it', async () => {
    const values = props({source: ''});
    render(<Component {...values} selectRequest={{name: 'ASSETS', path: ['ASSETS'], nonce: 1}} />);
    await waitFor(() => expect(values.onChange).toHaveBeenCalledWith(
      'SELECT "ASSET_ID", "TAG", "Mixed ""Case"""\nFROM "ASSETS"'));
    expect(values.post).toHaveBeenCalledWith({action: 'firebird_editor_metadata', database_target_id: 'db'});
    expect(values.onExecute).not.toHaveBeenCalled();
  });

  it('replaces the untouched starter statement without asking', async () => {
    const values = props({source: 'SELECT 1 FROM RDB$DATABASE'});
    render(<Component {...values} selectRequest={{name: 'OPEN_WORK_ORDERS', path: [], nonce: 2}} />);
    await waitFor(() => expect(values.onChange).toHaveBeenCalledWith(
      'SELECT "WORK_ORDER_ID"\nFROM "OPEN_WORK_ORDERS"'));
  });

  it('asks before replacing text the user wrote', async () => {
    const values = props({source: 'SELECT draft FROM work'});
    render(<Component {...values} selectRequest={{name: 'ASSETS', path: ['ASSETS'], nonce: 3}} />);
    expect(await screen.findByText('Replace the editor text?')).toBeInTheDocument();
    // The code editor reports its initial text on mount; the SELECT itself
    // must not have been applied.
    const statement = 'SELECT "ASSET_ID", "TAG", "Mixed ""Case"""\nFROM "ASSETS"';
    expect(values.onChange).not.toHaveBeenCalledWith(statement);
    fireEvent.click(screen.getByRole('button', {name: 'Keep current text'}));
    expect(values.onChange).not.toHaveBeenCalledWith(statement);
    await waitFor(() => expect(screen.queryByText('Replace the editor text?')).not.toBeInTheDocument());
  });

  it('replaces user text only after Replace', async () => {
    const values = props({source: 'SELECT draft FROM work'});
    render(<Component {...values} selectRequest={{name: 'ASSETS', path: ['ASSETS'], nonce: 4}} />);
    fireEvent.click(await screen.findByRole('button', {name: 'Replace'}));
    expect(values.onChange).toHaveBeenCalledWith('SELECT "ASSET_ID", "TAG", "Mixed ""Case"""\nFROM "ASSETS"');
  });

  it('replaces its own untouched statement without asking, but asks once it is edited', async () => {
    const assets = 'SELECT "ASSET_ID", "TAG", "Mixed ""Case"""\nFROM "ASSETS"';
    const view = 'SELECT "WORK_ORDER_ID"\nFROM "OPEN_WORK_ORDERS"';
    const values = props({source: ''});
    const {rerender} = render(<Component {...values} selectRequest={{name: 'ASSETS', path: [], nonce: 10}} />);
    await waitFor(() => expect(values.onChange).toHaveBeenCalledWith(assets));
    rerender(<Component {...values} source={assets} selectRequest={{name: 'OPEN_WORK_ORDERS', path: [], nonce: 11}} />);
    await waitFor(() => expect(values.onChange).toHaveBeenCalledWith(view));
    expect(screen.queryByText('Replace the editor text?')).not.toBeInTheDocument();
    rerender(<Component {...values} source={view + ' WHERE 1 = 1'} selectRequest={{name: 'ASSETS', path: [], nonce: 12}} />);
    expect(await screen.findByText('Replace the editor text?')).toBeInTheDocument();
  });

  it('leaves the text alone while a statement is running', async () => {
    const values = props({source: '', disabled: true});
    render(<Component {...values} selectRequest={{name: 'ASSETS', path: [], nonce: 20}} />);
    expect(await screen.findByText(/Finish or cancel the current statement/)).toBeInTheDocument();
    expect(values.onChange).not.toHaveBeenCalledWith(expect.stringMatching(/^SELECT "ASSET_ID"/));
  });

  it('shows why a SELECT cannot be built', async () => {
    const values = props({source: ''});
    render(<Component {...values} selectRequest={{name: 'MISSING', path: [], nonce: 5}} />);
    expect(await screen.findByText(/lists no columns for MISSING/)).toBeInTheDocument();
    expect(values.onChange).not.toHaveBeenCalledWith(expect.stringMatching(/^SELECT/));
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
