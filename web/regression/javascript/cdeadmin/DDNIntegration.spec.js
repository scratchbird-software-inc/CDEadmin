import { DDNSessionController, loadDDNLibraries, setDDNLibraryLoaderForTests, resetDDNLibraryLoaderForTests, validateDDNFiles, validateDDNAssetRef, validateDDNSnapshot } from 'sources/cdeadmin_ui/integrations/ddn';
import { libraries, setupDDNDOM } from './ddnTestRuntime';
const files = {
  'model.ddn': 'version ddn-next-1\nerd main\n    with\n        id main\n    Alpha\n'
};
const assetRef = (assetVersion = 0) => ({
  projectId: 'p',
  assetId: 'a',
  assetVersion,
  assetType: 'ddn-workspace'
});
describe('DDN public command, capture and host persistence boundary', () => {
  beforeEach(() => {
    setupDDNDOM();
    setDDNLibraryLoaderForTests(async () => libraries);
  });
  afterEach(() => resetDDNLibraryLoaderForTests());
  it('loads read-only APIs without initializing the designer', async () => {
    expect((await loadDDNLibraries()).designer).toBeUndefined();
    expect(await loadDDNLibraries()).toBe(libraries);
  });
  it.each([null, {}, {
    '../bad.ddn': ''
  }, {
    'bad.txt': ''
  }, {
    'a.ddn': 42
  }])('rejects invalid source files %j', input => expect(() => validateDDNFiles(input)).toThrow());
  it('captures real SVG and source without changing the native contract', async () => {
    const c = await DDNSessionController.create({
      files,
      assetRef: assetRef()
    });
    try {
      const result = await c.render();
      expect(result.svg).toContain('<svg');
      expect(result.manifest.revision).toEqual(expect.any(Object));
      const snapshot = await c.snapshot();
      expect(snapshot.files).toEqual(files);
      expect(() => validateDDNSnapshot({
        ...snapshot,
        format: 'ddn-workspace@1'
      })).toThrow('Legacy');
      expect(() => validateDDNAssetRef({
        ...assetRef(),
        assetType: 'table'
      })).toThrow();
    } finally {
      c.destroy();
    }
    await expect(c.render()).rejects.toThrow('destroyed');
  });
  it('retains an untouched BOM and CRLF source through save artifacts',async()=> {
    const text='\uFEFF'+files['model.ddn'].replaceAll('\n','\r\n');
    const c=await DDNSessionController.create({files:{'model.ddn':text}});
    try {expect((await c.snapshot()).files['model.ddn']).toBe(text);}finally{c.destroy();}
  });
  it('prepares without mutation, commits and preserves undo/redo', async () => {
    const c = await DDNSessionController.create({
      files
    });
    try {
      const file = c.runtime.sources().files[0];
      const plan = await c.prepare({
        kind: 'edit-source',
        patches: [{
          file: file.id,
          base: file.revision,
          start: 0,
          end: file.text.length,
          text: file.text.replace('Alpha', 'Beta')
        }]
      });
      expect(c.getFiles()['model.ddn']).toContain('Alpha');
      await c.commit(plan);
      expect(c.getFiles()['model.ddn']).toContain('Beta');
      expect(c.state().persistence).toBe('dirty');
      await c.undo();
      expect(c.getFiles()['model.ddn']).toContain('Alpha');
      await c.redo();
      expect(c.getFiles()['model.ddn']).toContain('Beta');
    } finally {
      c.destroy();
    }
  });
  it('captures the view selected through the native designer viewer',async()=> {
    const text=files['model.ddn']+'erd second\n    with\n        id second\n    Beta\n';
    const c=await DDNSessionController.create({files:{'model.ddn':text}});
    try {await c.viewer.navigate({kind:'expand-view',target:{file:'model.ddn',id:'second'}});expect((await c.snapshot()).view).toBe('second');}
    finally {c.destroy();}
  });
  it('blocks read-only edits and does not grant lifecycle acceptance', async () => {
    const c = await DDNSessionController.create({
      files,
      readOnly: true
    });
    try {
      await expect(c.updateSource('model.ddn', '')).rejects.toThrow('read-only');
      await expect(c.save(jest.fn())).rejects.toThrow('read-only');
      expect((await c.authority.authorize('lifecycle.accept')).allowed).toBe(false);
    } finally {
      c.destroy();
    }
  });
  it('does not mark newer source clean after an older save completes', async () => {
    const c = await DDNSessionController.create({
      files,
      assetRef: assetRef(4)
    });
    let release;
    try {
      const saveAsset = jest.fn((payload, options) => {
        expect(payload.snapshot.files).toEqual(files);
        expect(options.expectedAssetVersion).toBe(4);
        return new Promise(resolve => {
          release = resolve;
        });
      });
      const saving = c.save(saveAsset);
      await expect(c.save(jest.fn())).rejects.toThrow('already in progress');
      while (!release) await new Promise(resolve => setTimeout(resolve, 0));
      await c.updateSource('model.ddn', files['model.ddn'].replace('Alpha', 'Beta'));
      release({
        assetRef: assetRef(5)
      });
      await saving;
      expect(c.state().persistence).toBe('saved-newer-edits');
      expect(c.assetRef.assetVersion).toBe(5);
    } finally {
      c.destroy();
    }
  });
  it.each([['asset_conflict', 'external-conflict'], ['network_error', 'save-failed']])('retains source on %s', async (code, state) => {
    const c = await DDNSessionController.create({
      files,
      assetRef: assetRef()
    });
    try {
      await expect(c.save(async () => {
        throw Object.assign(new Error(code), {
          code
        });
      })).rejects.toThrow(code);
      expect(c.state().persistence).toBe(state);
      expect(c.getFiles()).toEqual(files);
    } finally {
      c.destroy();
    }
  });
});
