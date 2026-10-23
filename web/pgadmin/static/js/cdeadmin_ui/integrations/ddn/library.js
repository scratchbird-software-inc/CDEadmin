/////////////////////////////////////////////////////////////
//
// CDEadmin - Multi-engine Database Administration
//
// Copyright (C) 2013 - 2026, The pgAdmin Development Team
// This software is released under the PostgreSQL Licence
//
//////////////////////////////////////////////////////////////

export const DDN_RUNTIME_VERSION = '0.8.0';
export const DDN_DESIGNER_VERSION = '0.8.0';

let librariesPromise;
const scriptLoads = new Map();

export function staticAssetUrl(path) {
  if(typeof document === 'undefined') {
    throw new Error('DDN browser libraries require a document host.');
  }
  const generated = window.resourceBasePath || '/static/js/generated/';
  const base = new URL(generated, document.baseURI);
  return new URL(`../../vendor/ddn/current/${path}`, base).href;
}

function loadScript(path, available) {
  if(available()) return Promise.resolve();
  const source = staticAssetUrl(path);
  if(scriptLoads.has(source)) return scriptLoads.get(source);
  const load = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = source;
    script.async = true;
    script.dataset.cdeadminDdnLibrary = path;
    script.addEventListener('load', () => {
      scriptLoads.delete(source);
      if(available()) resolve();
      else {
        script.remove();
        reject(new Error(`DDN library did not publish its public API: ${path}`));
      }
    }, {once: true});
    script.addEventListener('error', () => {
      scriptLoads.delete(source);
      script.remove();
      reject(new Error(`Unable to load the bundled DDN library: ${path}`));
    }, {once: true});
    document.head.appendChild(script);
  });
  scriptLoads.set(source, load);
  return load;
}

async function browserLibraryLoader() {
  await loadScript('ddn.global.js', () => Boolean(window.DDNLive));
  return [window.DDNLive];
}

let libraryLoader = browserLibraryLoader;

function requireFunction(value, name) {
  if(typeof value !== 'function') {
    throw new Error(`DDN public API is missing ${name}.`);
  }
}

function validateLibraries(viewer) {
  if(viewer?.VERSION !== DDN_RUNTIME_VERSION) {
    throw new Error(`DDN runtime ${DDN_RUNTIME_VERSION} is required; received ${viewer?.VERSION || 'unidentified'}.`);
  }
  requireFunction(viewer.createWorkspace, 'createWorkspace()');
  requireFunction(viewer.mount, 'mount()');
  return Object.freeze({viewer, toolUrl: staticAssetUrl('ddn-tool.html')});
}

export function loadDDNLibraries() {
  if(!librariesPromise) {
    librariesPromise = Promise.resolve().then(() => libraryLoader())
      .then(([viewer]) => validateLibraries(viewer))
      .catch((error) => {
        librariesPromise = undefined;
        throw error;
      });
  }
  return librariesPromise;
}

export async function loadDDNGeoLibraries() {
  const libraries = await loadDDNLibraries();
  await loadScript('ddn-geo.js', () => Boolean(window.DDNGeo));
  if(window.DDNGeo?.VERSION !== DDN_RUNTIME_VERSION) throw new Error('The paired DDN geographic module is required.');
  for(const name of ['render', 'ingest', 'geoPath']) requireFunction(window.DDNGeo[name], `geo.${name}()`);
  return {...libraries, geo: window.DDNGeo};
}

export function setDDNLibraryLoaderForTests(loader) {
  if(process.env.NODE_ENV !== 'test' || typeof loader !== 'function') {
    throw new Error('DDN library loader replacement is restricted to tests.');
  }
  librariesPromise = undefined;
  libraryLoader = loader;
}

export function resetDDNLibraryLoaderForTests() {
  librariesPromise = undefined;
  libraryLoader = browserLibraryLoader;
  scriptLoads.clear();
}
