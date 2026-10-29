// Public standalone DDN APIs only. No commercial Weaver dependency or service.
import {importPublicModule} from './importModule.mjs';
import integration from '../../../../vendor/ddn/current/integration.json';
export const DDN_RUNTIME_VERSION = 'ddn-next-1';
export const DDN_DESIGNER_VERSION = '1.0';
let librariesPromise, designerPromise;
const scriptLoads = new Map();
export function staticAssetUrl(path) {
  if(typeof document === 'undefined') throw new Error('DDN browser libraries require a document host.');
  const base = new URL(window.resourceBasePath || '/static/js/generated/', document.baseURI);
  const url = new URL(`../../vendor/ddn/current/${path}`, base);
  url.searchParams.set('release', integration.release);
  return url.href;
}
function loadScript(path, available) {
  if(available()) return Promise.resolve();
  const src = staticAssetUrl(path);
  if(scriptLoads.has(src)) return scriptLoads.get(src);
  const pending = new Promise((resolve,reject) => {
    const script = document.createElement('script');
    script.src=src;script.async=true;script.dataset.cdeadminDdnLibrary=path;
    const finish = error => {
      clearTimeout(timer);script.onload=null;script.onerror=null;scriptLoads.delete(src);
      if(error) {script.remove();reject(error);} else resolve();
    };
    const timer=setTimeout(()=>finish(new Error(`Timed out loading bundled DDN: ${path}`)),15000);
    script.onload=()=>finish(available() ? null : new Error('The bundled DDN module loader is unavailable.'));
    script.onerror=()=>finish(new Error(`Unable to load bundled DDN: ${path}`));
    document.head.appendChild(script);
  });
  scriptLoads.set(src,pending);return pending;
}
function checkLoader(loader) {
  if(loader?.version !== integration.contract || loader?.hash !== integration.release) {
    throw new Error('The DDN loader belongs to another release. Reload the workbench.');
  }
  for(const name of ['loadEntry','prepareEntry']) if(typeof loader[name] !== 'function') throw new Error(`Missing DDN loader API: ${name}`);
}
async function browserLibraryLoader() {
  await loadScript('modular/ddn-loader.js',()=>Boolean(window.DDN_LOADER));
  const loader=window.DDN_LOADER;checkLoader(loader);
  await loadScript('modular/ddn-fonts.js',()=>Array.isArray(window.DDN_FONT_RESOURCES));
  await loader.prepareEntry('worker');
  const [viewer,language,model] = await Promise.all([
    loader.loadEntry('api:viewer'),
    importPublicModule(staticAssetUrl('modules/language/src/index.js')),
    importPublicModule(staticAssetUrl('modules/model/src/index.js')),
  ]);
  for(const name of ['createRuntime','createViewer','createVerifier','createBrowserRuntimeOptions']) {
    if(typeof viewer[name] !== 'function') throw new Error(`Missing DDN public API: ${name}`);
  }
  return {viewer,language,model,loader};
}
let libraryLoader=browserLibraryLoader;
export function loadDDNLibraries({designer=false}={}) {
  if(!librariesPromise) librariesPromise=Promise.resolve().then(()=>libraryLoader()).catch(error=>{librariesPromise=undefined;throw error;});
  if(!designer) return librariesPromise;
  if(!designerPromise) designerPromise=librariesPromise.then(async libraries=> {
    const api=await libraries.loader.loadEntry('api:designer');
    if(typeof api.createDesigner !== 'function') throw new Error('The public DDN designer API is unavailable.');
    return {...libraries,designer:api};
  }).catch(error=>{designerPromise=undefined;throw error;});
  return designerPromise;
}
// Geography is an installed DDN presentation family, never a separate renderer.
export const loadDDNGeoLibraries = () => loadDDNLibraries();
export function setDDNLibraryLoaderForTests(loader) {
  if(process.env.NODE_ENV !== 'test' || typeof loader !== 'function') throw new Error('DDN loader replacement is restricted to tests.');
  librariesPromise=undefined;designerPromise=undefined;libraryLoader=loader;
}
export function resetDDNLibraryLoaderForTests() {
  librariesPromise=undefined;designerPromise=undefined;libraryLoader=browserLibraryLoader;scriptLoads.clear();
}
