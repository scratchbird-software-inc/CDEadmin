import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { DDNDesignerSurface, DDNViewerSurface, setDDNLibraryLoaderForTests, resetDDNLibraryLoaderForTests } from 'sources/cdeadmin_ui/integrations/ddn';
import { libraries, setupDDNDOM } from './ddnTestRuntime';
import { withTheme } from '../fake_theme';
const files = {
  'model.ddn': 'version ddn-next-1\nerd main\n    with\n        id main\n    Alpha\n'
};
describe('standalone DDN surfaces', () => {
  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(async () => libraries);
  });
  afterEach(resetDDNLibraryLoaderForTests);
  it('captures presentation SVG through DDN and keeps it display-only', async () => {
    const Component = withTheme(DDNViewerSurface),
      onReady = jest.fn(),
      onSelectionChange = jest.fn();
    const {
      container
    } = render(<Component files={files} presentation onReady={onReady} onSelectionChange={onSelectionChange} />);
    await waitFor(() => expect(onReady).toHaveBeenCalled());
    expect(screen.getByRole('img', {
      name: 'DDN diagram'
    }).src).toContain('data:image/svg+xml');
    expect(onSelectionChange).toHaveBeenCalledWith({
      entry: 'model.ddn',
      view: expect.any(String)
    });
    expect(container.querySelector('iframe')).toBeNull();
    expect(screen.queryByRole('button', {
      name: 'Save'
    })).toBeNull();
  });
  it('retains view selection across provider refreshes without an editor', async () => {
    const Component = withTheme(DDNViewerSurface),
      onSelectionChange = jest.fn();
    const pages = {
      'model.ddn': files['model.ddn'] + 'erd second\n    with\n        id second\n    Beta\n'
    };
    const {
      rerender
    } = render(<Component files={pages} presentation viewSelection onSelectionChange={onSelectionChange} />);
    const selector = await screen.findByRole('combobox', {
      name: 'Dashboard view'
    });
    await waitFor(() => expect(onSelectionChange).toHaveBeenCalled());
    fireEvent.mouseDown(selector);
    fireEvent.click(await screen.findByRole('option', {
      name: 'model.ddn / second'
    }));
    await waitFor(() => expect(onSelectionChange).toHaveBeenCalledWith({
      entry: 'model.ddn',
      view: 'second'
    }));
    rerender(<Component files={{
      'model.ddn': pages['model.ddn'] + '// refreshed\n'
    }} presentation viewSelection onSelectionChange={onSelectionChange} />);
    await waitFor(() => expect(onSelectionChange.mock.calls.at(-1)[0]).toEqual({
      entry: 'model.ddn',
      view: 'second'
    }));
  });
  it('exports the actual interactive viewer capture', async () => {
    const Component = withTheme(DDNViewerSurface),
      onExport = jest.fn();
    render(<Component files={files} onExport={onExport} />);
    const button = screen.getByRole('button', {
      name: 'Export SVG'
    });
    await waitFor(() => expect(button).toBeEnabled());
    fireEvent.click(button);
    await waitFor(() => expect(onExport).toHaveBeenCalled());
    expect(onExport.mock.calls[0][0]).toContain('<svg');
  });
  it('uses the viewer for read-only editor assets', async () => {
    const Component = withTheme(DDNDesignerSurface);
    render(<Component files={files} readOnly />);
    await waitFor(() => expect(screen.getByRole('button', {
      name: 'Export SVG'
    })).toBeEnabled());
    expect(screen.queryByRole('button', {
      name: 'Save'
    })).toBeNull();
  });
  it('flushes structured drafts and persists coherent DDN source artifacts', async () => {
    const Component = withTheme(DDNDesignerSurface),
      onReady = jest.fn();
    const assetRef = {
      projectId: 'p',
      assetId: 'a',
      assetVersion: 2,
      assetType: 'ddn-workspace'
    };
    const saveAsset = jest.fn(async () => ({
      assetRef: {
        ...assetRef,
        assetVersion: 3
      }
    }));
    const {
      container
    } = render(<Component files={files} assetRef={assetRef} onReady={onReady} saveAsset={saveAsset} />);
    await waitFor(() => expect(onReady).toHaveBeenCalled());
    expect(container.querySelector('iframe')).toBeNull();
    fireEvent.click(screen.getByRole('button', {
      name: 'Save',
      exact: true
    }));
    await waitFor(() => expect(saveAsset).toHaveBeenCalled());
    expect(saveAsset.mock.calls[0][0].snapshot.files).toEqual(files);
    expect(saveAsset.mock.calls[0][1].expectedAssetVersion).toBe(2);
  });
});
