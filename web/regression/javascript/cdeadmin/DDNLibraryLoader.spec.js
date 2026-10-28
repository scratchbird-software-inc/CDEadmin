import {loadDDNLibraries,resetDDNLibraryLoaderForTests} from 'sources/cdeadmin_ui/integrations/ddn';
import integration from '../../../pgadmin/static/vendor/ddn/current/integration.json';
describe('same-origin release-bound DDN module loading',()=> {
  beforeEach(()=>{resetDDNLibraryLoaderForTests();delete window.DDN_LOADER;window.resourceBasePath='/mounted/static/js/generated/';});
  afterEach(()=>{document.head.querySelectorAll('[data-cdeadmin-ddn-library]').forEach(node=>node.remove());delete window.DDN_LOADER;delete window.resourceBasePath;resetDDNLibraryLoaderForTests();});
  const started=async()=>{await Promise.resolve();await Promise.resolve();return document.querySelector('[data-cdeadmin-ddn-library]');};
  it('requests a mounted, release-bound loader without an editor shell',async()=> {
    const pending=loadDDNLibraries(),script=await started();
    expect(script.src).toContain('/mounted/static/vendor/ddn/current/modular/ddn-loader.js');expect(script.src).toContain('release='+integration.release);
    expect(document.querySelector('iframe')).toBeNull();script.dispatchEvent(new Event('error'));
    await expect(pending).rejects.toThrow('Unable to load');
  });
  it('retries missing assets and rejects a mismatched release',async()=> {
    const first=loadDDNLibraries(),script=await started();script.dispatchEvent(new Event('error'));await expect(first).rejects.toThrow();
    const retry=loadDDNLibraries(),replacement=await started();window.DDN_LOADER={version:integration.contract,hash:'stale'};
    replacement.dispatchEvent(new Event('load'));await expect(retry).rejects.toThrow('another release');
  });
  it('rejects an incompatible loader already present',async()=> {
    window.DDN_LOADER={version:'old',hash:integration.release};await expect(loadDDNLibraries()).rejects.toThrow('another release');
  });
});
