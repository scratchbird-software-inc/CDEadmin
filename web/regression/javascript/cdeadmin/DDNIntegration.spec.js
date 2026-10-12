import viewer from '../../../pgadmin/static/vendor/ddn/current/ddn.mjs';
import {DDNSessionController, loadDDNLibraries, setDDNLibraryLoaderForTests,
  resetDDNLibraryLoaderForTests, validateDDNFiles, validateDDNAssetRef,
  validateDDNSnapshot} from 'sources/cdeadmin_ui/integrations/ddn';
const files = {'model.ddn': 'ddn "0.5"; module "test"; data model { object a "Alpha" { kind: table; } } view main { data: [@model]; select: [@model.a]; }'};
const assetRef = (assetVersion=0) => ({projectId: 'p', assetId: 'a', assetVersion, assetType: 'ddn-workspace'});

describe('current DDN public workspace and persistence boundary', () => {
  beforeEach(() => {
    setDDNLibraryLoaderForTests(async () => [viewer]);
    viewer.setTextProvider((text, size) => ({width: String(text).length * size * 0.6,
      ascent: size * 0.8, descent: size * 0.2}), 'scratchrobin-test');
  });
  afterEach(() => { viewer.setTextProvider(null); resetDDNLibraryLoaderForTests(); });
  it('uses the current runtime with a separate tool URL', async () => {
    const lib = await loadDDNLibraries();
    expect(lib.viewer.VERSION).toBe('0.8.0');
    expect(lib.toolUrl).toContain('/vendor/ddn/current/ddn-tool.html');
    expect(lib.designer).toBeUndefined();
    expect(await loadDDNLibraries()).toBe(lib);
  });
  it.each([null, {}, {'../bad.ddn': ''}, {'bad.txt': ''}, {'a.ddn': 42}])('rejects invalid files %j', (input) => {
    expect(() => validateDDNFiles(input)).toThrow();
  });
  it('preserves source, metadata and source maps through rendering and snapshots', async () => {
    const c = await DDNSessionController.create({files, assetRef: assetRef()});
    expect(c.render().svg).toContain('<svg');
    expect(c.render().sourceMap).toEqual(expect.any(Object));
    expect(c.snapshot().files).toEqual(files);
    expect(() => validateDDNSnapshot({...c.snapshot(), format: 'svg'})).toThrow();
    expect(() => validateDDNAssetRef({...assetRef(), assetType: 'table'})).toThrow();
    c.destroy();
    expect(() => c.render()).toThrow('destroyed');
  });
  it('previews source edits, applies only on commit and retains undo/redo', async () => {
    const c = await DDNSessionController.create({files});
    const plan = c.prepare({type: 'files', changes: {'model.ddn': files['model.ddn'].replace('Alpha', 'Beta')}});
    expect(c.getFiles()['model.ddn']).toContain('Alpha');
    c.commit(plan);
    expect(c.getFiles()['model.ddn']).toContain('Beta');
    expect(c.state().persistence).toBe('dirty');
    c.undo(); expect(c.getFiles()['model.ddn']).toContain('Alpha');
    c.redo(); expect(c.getFiles()['model.ddn']).toContain('Beta');
    c.destroy();
  });
  it('blocks writes and saves through a read-only controller', async () => {
    const c = await DDNSessionController.create({files, readOnly: true});
    expect(() => c.updateSource('model.ddn', '')).toThrow('read-only');
    await expect(c.save(jest.fn())).rejects.toThrow('read-only'); c.destroy();
  });
  it('does not mark newer source clean when an older save completes', async () => {
    let release;
    const c = await DDNSessionController.create({files, assetRef: assetRef(4)});
    const saving = c.save((payload, options) => {
      expect(payload.snapshot.files).toEqual(files);
      expect(options.expectedAssetVersion).toBe(4);
      return new Promise((resolve) => { release = resolve; });
    });
    await expect(c.save(jest.fn())).rejects.toThrow('already in progress');
    c.updateSource('model.ddn', files['model.ddn'].replace('Alpha', 'Beta'));
    release({assetRef: assetRef(5)}); await saving;
    expect(c.state().persistence).toBe('saved-newer-edits');
    expect(c.assetRef.assetVersion).toBe(5); c.destroy();
  });
  it.each([['asset_conflict', 'external-conflict'], ['network_error', 'save-failed']])('retains source on %s', async (code, state) => {
    const c = await DDNSessionController.create({files, assetRef: assetRef()});
    await expect(c.save(async () => { throw Object.assign(new Error(code), {code}); })).rejects.toThrow(code);
    expect(c.state().persistence).toBe(state); expect(c.getFiles()).toEqual(files); c.destroy();
  });
});
