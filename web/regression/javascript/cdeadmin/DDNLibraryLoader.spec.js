import {loadDDNLibraries, resetDDNLibraryLoaderForTests} from 'sources/cdeadmin_ui/integrations/ddn';
const runtime = () => ({VERSION: '0.8.0', createWorkspace: jest.fn(), mount: jest.fn()});
describe('DDN current same-origin loader', () => {
  beforeEach(() => { resetDDNLibraryLoaderForTests(); delete window.DDNLive;
    window.resourceBasePath = '/mounted/static/js/generated/'; });
  afterEach(() => {
    document.head.querySelectorAll('[data-cdeadmin-ddn-library]').forEach((e) => e.remove());
    delete window.DDNLive; delete window.resourceBasePath; resetDDNLibraryLoaderForTests();
  });
  it('loads the current runtime without loading an editor into the viewer', async () => {
    const result = loadDDNLibraries(); await Promise.resolve(); await Promise.resolve();
    const script = document.querySelector('[data-cdeadmin-ddn-library]');
    expect(script.src).toContain('/mounted/static/vendor/ddn/current/ddn.global.js');
    window.DDNLive = runtime(); script.dispatchEvent(new Event('load'));
    expect((await result).toolUrl).toContain('/mounted/static/vendor/ddn/current/ddn-tool.html');
    expect(document.querySelectorAll('[data-cdeadmin-ddn-library]')).toHaveLength(1);
  });
  it('rejects missing assets and retries', async () => {
    const result = loadDDNLibraries(); await Promise.resolve(); await Promise.resolve();
    document.querySelector('script[data-cdeadmin-ddn-library]').dispatchEvent(new Event('error'));
    await expect(result).rejects.toThrow('Unable to load');
    const retry = loadDDNLibraries(); await Promise.resolve(); await Promise.resolve();
    window.DDNLive = runtime();
    document.querySelector('script[data-cdeadmin-ddn-library]').dispatchEvent(new Event('load'));
    await expect(retry).resolves.toHaveProperty('viewer', window.DDNLive);
  });
  it('refuses another runtime version already present in the page', async () => {
    window.DDNLive = {...runtime(), VERSION: '0.5.0-draft.2'};
    await expect(loadDDNLibraries()).rejects.toThrow('0.8.0 is required');
  });
});
