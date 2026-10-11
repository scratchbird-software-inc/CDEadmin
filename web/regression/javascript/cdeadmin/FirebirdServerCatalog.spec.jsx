import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import FirebirdServerCatalog, {catalogBundle} from 'sources/Dialogs/FirebirdServerCatalog';
import {withTheme} from '../fake_theme';
import {TextEncoder} from 'util';

jest.mock('sources/cdeadmin_ui/integrations/ddn', () => ({
  DDNViewerSurface: ({snapshot}) => <div data-testid="catalog-view">{JSON.stringify(snapshot)}</div>,
}));

describe('Registered server catalog capture', () => {
  const Component = withTheme(FirebirdServerCatalog);
  const endpoint = {endpoint_id: 'endpoint', display_name: 'Server'};
  const targets = [{target_id: 'one', label: 'First'}, {target_id: 'two', label: 'Second'}];
  const catalog = target => ({target_id: target, snapshot: {files: {'catalog.ddn': 'native facts'}},
    provenance: {endpoint_id: 'endpoint', database_target_id: target, coverage: 'visible-catalog', objects: 3}});
  beforeAll(() => {global.TextEncoder = TextEncoder;});
  it('retains partial success and hides credential-bearing errors', async () => {
    const post = jest.fn().mockResolvedValueOnce(catalog('one')).mockRejectedValueOnce({response: {status: 403}, message: 'secret'});
    render(<Component endpoint={endpoint} targets={targets} post={post} />);
    fireEvent.click(screen.getByText('Select all registered databases'));
    fireEvent.click(screen.getByText('Capture selected database catalogs'));
    expect(await screen.findByText(/Second: inaccessible/)).toBeVisible();
    expect(screen.getByText(/First: captured/)).toBeVisible();
    expect(screen.queryByText('secret')).toBeNull();
    expect(post.mock.calls.map(([value]) => value.request)).toEqual(targets.map(item => ({target_id: item.target_id, refresh: true, include_system: false})));
  });
  it('stops after the active capture and keeps unattempted registrations visible', async () => {
    let resolve;
    const post = jest.fn(() => new Promise(done => {resolve = done;}));
    render(<Component endpoint={endpoint} targets={targets} post={post} />);
    fireEvent.click(screen.getByText('Select all registered databases'));
    fireEvent.click(screen.getByText('Capture selected database catalogs'));
    fireEvent.click(screen.getByText('Stop after current database'));
    await act(async () => resolve(catalog('one')));
    expect(screen.getByText(/Second: not-attempted/)).toBeVisible();
    expect(post).toHaveBeenCalledTimes(1);
    expect(screen.getByText('Download server catalog bundle')).toBeEnabled();
  });
  it('rejects a response for another registration', async () => {
    const post = jest.fn().mockResolvedValue(catalog('two'));
    render(<Component endpoint={endpoint} targets={targets} post={post} />);
    fireEvent.click(screen.getByLabelText('First'));
    fireEvent.click(screen.getByText('Capture selected database catalogs'));
    expect(await screen.findByText(/First: failed/)).toBeVisible();
    expect(screen.queryByText('Download this database DDN')).toBeNull();
  });
  it('discards a pending response when endpoint scope changes', async () => {
    let resolve;
    const post = jest.fn(() => new Promise(done => {resolve = done;}));
    const {rerender} = render(<Component endpoint={endpoint} targets={targets} post={post} />);
    fireEvent.click(screen.getByLabelText('First'));
    fireEvent.click(screen.getByText('Capture selected database catalogs'));
    rerender(<Component endpoint={{endpoint_id: 'other'}} targets={[]} post={post} />);
    await act(async () => resolve(catalog('one')));
    await waitFor(() => expect(screen.queryByTestId('catalog-view')).toBeNull());
  });
  it('preserves original per-database evidence and never labels partial coverage complete', () => {
    const entries = [{target_id: 'one', label: 'First', status: 'captured', catalog: catalog('one')}];
    expect(catalogBundle(endpoint, entries).complete).toBe(true);
    entries[0].catalog.provenance.coverage = 'partial';
    const bundle = catalogBundle(endpoint, entries);
    expect(bundle.complete).toBe(false);
    expect(bundle.entries[0].catalog).toBe(entries[0].catalog);
    expect(bundle.consistency).toContain('not an atomic');
    expect(bundle.overview.files['server.ddn']).toContain('records: [@databases.db_0]');
  });
});
