import {fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdExport from 'sources/Dialogs/FirebirdExport';
import {withTheme} from '../fake_theme';
import {TextDecoder} from 'util';
import {Buffer} from 'buffer';

jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: ({snapshot}) => <div data-testid="ddn-preview" data-entry={snapshot.entry} />,
}));

describe('Firebird DDN metadata export', () => {
  const Component = withTheme(FirebirdExport);
  let height;
  beforeEach(() => { height = window.innerHeight; window.innerHeight = 1200; });
  afterEach(() => { window.innerHeight = height; });
  it('shows native script ownership and blocks incomplete metadata downloads', async () => {
    const post = jest.fn().mockResolvedValueOnce({provenance: {coverage: 'visible-catalog'},
      blockers: [], ownership_requirements: [{resource_id: 'table-A', execute_as_user: 'ALICE'}],
      external_prerequisites: [{name: 'DOMAIN_A', kinds: ['domain']}], download_text: 'CREATE TABLE A (V INT);'})
      .mockResolvedValueOnce({provenance: {coverage: 'partial'}, blockers: [{kind: 'view', name: 'V', reason: 'Missing definition'}],
        ownership_requirements: [], external_prerequisites: [], download_text: null});
    render(<Component post={post} generation="current" />);
    fireEvent.click(screen.getByRole('button', {name: 'Capture native SQL'}));
    await screen.findByText('ALICE');
    expect(post.mock.calls[0][0].action).toBe('firebird_sql_export');
    expect(screen.getByLabelText('Native metadata SQL')).toHaveValue('CREATE TABLE A (V INT);');
    expect(screen.getByRole('button', {name: 'Download native SQL'})).toBeEnabled();
    expect(screen.queryByTestId('ddn-preview')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Capture native SQL'}));
    await screen.findByText('view: V — Missing definition');
    expect(screen.queryByRole('button', {name: 'Download native SQL'})).toBeNull();
  });
  it('captures one exact table branch as data without issuing SQL', async () => {
    const post = jest.fn().mockResolvedValue({contents: 'data', table_count: 1, row_count: 2,
      filename: 'firebird-data.json', download_text: '{}'});
    render(<Component post={post} generation="g" resources={[{resource_id: 'table:T', resource_kind: 'table', display_name: 'T', display_path: ['T']}]} selectedResource={{resource_id: 'table:T', display_name: 'T'}} />);
    fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Metadata scope'}));
    fireEvent.click(await screen.findByRole('option', {name: 'Selected object and children'}));
    fireEvent.click(screen.getByRole('button', {name: 'Capture data archive'}));
    await screen.findByRole('button', {name: 'Download data archive'});
    expect(post).toHaveBeenCalledWith({action: 'firebird_data_export', request: {
      generation: 'g', include_system: false, refresh: false, contents: 'data', resource_id: 'table:T',
    }});
    expect(screen.queryByLabelText('Native metadata SQL')).toBeNull();
  });
  it('captures only on request and displays coverage before downloading', async () => {
    const post = jest.fn(async () => ({snapshot: {view: 'inventory_1'}, views: [{id: 'inventory_1', label: 'Page 1'}], provenance: {objects: 2, coverage: 'partial',
      warnings: ['Security catalog unavailable'], observation: 'cached-catalog'}}));
    render(<Component post={post} generation="current" />);
    expect(post).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByTestId('ddn-preview');
    expect(post).toHaveBeenCalledWith({action: 'firebird_catalog_export', request: {
      generation: 'current', include_system: false, refresh: false,
    }});
    expect(screen.getByText('Security catalog unavailable')).toBeInTheDocument();
    expect(screen.getByRole('button', {name: 'Download DDN'})).toBeEnabled();
    expect(screen.getByText('SR-F-001348')).toBeInTheDocument();
  });
  it('previews the selected file and downloads the complete workspace', async () => {
    const snapshot = {format: 'ddn-workspace@1', entry: 'catalog.ddn', view: 'inventory_1',
      files: {'catalog.ddn': 'first', 'catalog-2.ddn': 'second'}};
    const download = JSON.stringify(snapshot);
    const post = jest.fn().mockResolvedValue({snapshot, download_text: download,
      filename: 'firebird-catalog.ddn-workspace.json', provenance: {objects: 150},
      views: [{id: 'inventory_1', label: 'Page 1', entry: 'catalog.ddn'},
        {id: 'inventory_2', label: 'Page 2', entry: 'catalog-2.ddn'}]});
    const createURL = URL.createObjectURL, revokeURL = URL.revokeObjectURL;
    URL.createObjectURL = jest.fn(() => 'blob:test');
    URL.revokeObjectURL = jest.fn();
    const click = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    try {
      render(<Component post={post} generation="current" />);
      fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
      await screen.findByTestId('ddn-preview');
      fireEvent.mouseDown(screen.getByRole('combobox', {name: 'Inventory page'}));
      fireEvent.click(await screen.findByRole('option', {name: 'Page 2'}));
      expect(screen.getByTestId('ddn-preview')).toHaveAttribute('data-entry', 'catalog-2.ddn');
      fireEvent.click(screen.getByRole('button', {name: 'Download DDN'}));
      expect(URL.createObjectURL.mock.calls[0][0].size).toBe(new Blob([download]).size);
      expect(click).toHaveBeenCalled();
      await waitFor(() => expect(URL.revokeObjectURL).toHaveBeenCalledWith('blob:test'), {timeout: 2000});
    } finally {
      click.mockRestore(); URL.createObjectURL = createURL; URL.revokeObjectURL = revokeURL;
    }
  });
  it('reconciles the explorer after explicit refresh and surfaces failures', async () => {
    const refresh = jest.fn();
    const post = jest.fn().mockResolvedValueOnce({snapshot: {view: 'inventory_1'}, views: [{id: 'inventory_1', label: 'Page 1'}], provenance: {coverage: 'unknown'}})
      .mockRejectedValueOnce(new Error('Catalog generation changed'));
    render(<Component post={post} generation="current" onCatalogRefresh={refresh} />);
    fireEvent.click(screen.getByLabelText('Refresh native catalog before export'));
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await waitFor(() => expect(refresh).toHaveBeenCalled());
    await waitFor(() => expect(screen.getByRole('button', {name: 'Capture metadata'})).toBeEnabled());
    fireEvent.click(screen.getByRole('button', {name: 'Capture metadata'}));
    await screen.findByText('Catalog generation changed');
    expect(screen.queryByRole('button', {name: 'Download DDN'})).toBeNull();
  });
  it('reads a local document without posting it until comparison is requested', async () => {
    const previous = global.TextDecoder;
    global.TextDecoder = TextDecoder;
    try {
      const post = jest.fn().mockResolvedValue({counts: {equal: 2, changed: 1},
        changes: [{resource_id: 't', name: 'TABLE_A', kind: 'table', status: 'changed', fields: ['native.ddl']}],
        warnings: ['Missing objects do not authorize deletion.']});
      render(<Component post={post} generation="current" />);
      const file = {name: 'catalog.ddn', size: 10, arrayBuffer: async () => Buffer.from('ddn source')};
      fireEvent.change(screen.getByLabelText('Catalog DDN file'), {target: {files: [file]}});
      await screen.findByText('catalog.ddn');
      expect(post).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole('button', {name: 'Compare with database catalog'}));
      await screen.findByText('TABLE_A');
      expect(post).toHaveBeenCalledWith({action: 'firebird_catalog_compare', request: {
        generation: 'current', include_system: false, refresh: false, source: 'ddn source',
      }});
      expect(screen.getByText('native.ddl')).toBeInTheDocument();
      expect(screen.getByText('Missing objects do not authorize deletion.')).toBeInTheDocument();
    } finally {global.TextDecoder = previous;}
  });
  it('rejects oversized local documents without reading or sending them', async () => {
    const post = jest.fn();
    const file = {name: 'large.ddn', size: 8 * 1024 * 1024 + 1, arrayBuffer: jest.fn()};
    render(<Component post={post} generation="current" />);
    fireEvent.change(screen.getByLabelText('Catalog DDN file'), {target: {files: [file]}});
    await screen.findByText('Catalog document exceeds 8 MiB.');
    expect(post).not.toHaveBeenCalled(); expect(file.arrayBuffer).not.toHaveBeenCalled();
    expect(screen.getByRole('button', {name: 'Compare with database catalog'})).toBeDisabled();
  });
  it('exposes generation-bound paging and filtering without changing the chosen branch', async () => {
    const post = jest.fn().mockResolvedValue({contents: 'data', table_count: 1, row_count: 0});
    const more = jest.fn();
    const props = {post, generation: 'g', onLoadMore: more, hasMore: true,
      resources: [{resource_id: 'table:A', resource_kind: 'table', display_name: 'A', display_path: ['A']}]};
    const {rerender} = render(<Component {...props} />);
    fireEvent.mouseDown(screen.getByLabelText('Metadata scope'));
    fireEvent.click(await screen.findByRole('option', {name: 'Selected object and children'}));
    expect(screen.getByText(/More native objects remain unloaded/)).toBeInTheDocument();
    fireEvent.click(screen.getByText('Load more native branches'));
    expect(more).toHaveBeenCalledTimes(1);
    rerender(<Component {...props} hasMore={false} resources={[...props.resources,
      {resource_id: 'table:B', resource_kind: 'table', display_name: 'B', display_path: ['B']}]} />);
    fireEvent.change(screen.getByLabelText('Filter loaded branches'), {target: {value: ' B'}});
    fireEvent.mouseDown(screen.getByLabelText('Native branch'));
    expect(screen.queryByRole('option', {name: 'table: A'})).toBeNull();
    fireEvent.click(await screen.findByRole('option', {name: 'table: B'}));
    fireEvent.change(screen.getByLabelText('Filter loaded branches'), {target: {value: ' A'}});
    fireEvent.click(screen.getByRole('button', {name: 'Capture data archive'}));
    await waitFor(() => expect(post).toHaveBeenCalledWith({action: 'firebird_data_export', request: {
      generation: 'g', include_system: false, refresh: false, resource_id: 'table:B', contents: 'data'}}));
  });

});
