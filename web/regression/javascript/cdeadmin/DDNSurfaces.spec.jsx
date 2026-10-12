import {act, fireEvent, render, screen, waitFor} from '@testing-library/react';
import viewer from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {DDNDesignerSurface, DDNViewerSurface, setDDNLibraryLoaderForTests,
  resetDDNLibraryLoaderForTests} from 'sources/cdeadmin_ui/integrations/ddn';
import {withTheme} from '../fake_theme';
const files = {'model.ddn': 'ddn "0.5"; module "test"; data model { object a "Alpha" { kind: table; } } view main { data: [@model]; select: [@model.a]; }'};
describe('current DDN surfaces', () => {
  beforeEach(() => {
    setDDNLibraryLoaderForTests(async () => [viewer]);
    viewer.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
      ascent: size * 0.8, descent: size * 0.2}), 'surface-test');
  });
  afterEach(() => { viewer.setTextProvider(null); resetDDNLibraryLoaderForTests(); });
  it('renders passive SVG images without editing handlers and exports exact SVG', async () => {
    const onReady = jest.fn(), onExport = jest.fn(), onSelectionChange = jest.fn();
    const Component = withTheme(DDNViewerSurface);
    const {container, unmount} = render(<Component files={files} onReady={onReady} onExport={onExport} onSelectionChange={onSelectionChange} />);
    await waitFor(() => expect(onReady).toHaveBeenCalled());
    expect(onSelectionChange).toHaveBeenCalledWith(expect.objectContaining({entry: 'model.ddn', view: expect.any(String)}));
    expect(screen.getByRole('img', {name: 'DDN diagram'}).src).toContain('data:image/svg+xml');
    expect(container.querySelector('ddn-example')).toBeNull();
    expect(container.querySelector('iframe')).toBeNull();
    fireEvent.click(screen.getByRole('button', {name: 'Export SVG'}));
    expect(onExport.mock.calls[0][0]).toContain('<svg'); unmount();
  });
  it('uses only the viewer for read-only editor assets', async () => {
    const Component = withTheme(DDNDesignerSurface);
    const {container} = render(<Component files={files} readOnly />);
    await screen.findByRole('img');
    expect(container.querySelector('iframe')).toBeNull();
    expect(screen.queryByRole('button', {name: 'Save'})).toBeNull();
  });
  it('loads the documented source bridge and saves appearance-bearing source', async () => {
    const onReady = jest.fn();
    const assetRef = {projectId: 'p', assetId: 'a', assetVersion: 2, assetType: 'ddn-workspace'};
    const saveAsset = jest.fn(async () => ({assetRef: {...assetRef, assetVersion: 3}}));
    const workspace = viewer.createWorkspace(files);
    const tool = {workspace, setSource: jest.fn(async () => ({})),
      snapshot: () => workspace.snapshot('model.ddn', 'test.main'),
      getSource: jest.fn(() => ({files, entry: 'model.ddn', view: 'test.main'})),
      onSourceChange: jest.fn(() => jest.fn()), exportSvgString: jest.fn(() => '<svg/>')};
    const Component = withTheme(DDNDesignerSurface);
    render(<Component files={files} assetRef={assetRef} onReady={onReady} saveAsset={saveAsset} />);
    const frame = screen.getByTitle('DDN Designer');
    frame.contentWindow.DDNTool = tool;
    frame.contentWindow.DDNLive = viewer;
    await act(async () => { fireEvent.load(frame); });
    await waitFor(() => expect(onReady).toHaveBeenCalled());
    expect(tool.setSource).toHaveBeenCalledWith(files, expect.any(Object));
    fireEvent.click(screen.getByRole('button', {name: 'Save'}));
    await waitFor(() => expect(saveAsset).toHaveBeenCalled());
    expect(tool.getSource).toHaveBeenCalledWith({includeAppearance: true});
    expect(saveAsset.mock.calls[0][1].expectedAssetVersion).toBe(2);
    workspace.destroy();
  });
});
