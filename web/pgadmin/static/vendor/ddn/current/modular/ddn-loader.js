/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const name="DDN_MODULES",version="ddn-next-1",hash="3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8";if(Object.hasOwn(globalThis,name)){const current=globalThis[name];if(current?.version!==version||current?.hash!==hash||typeof current.register!=="function")throw Error("Incompatible DDN module runtime");return;}Object.defineProperty(globalThis,name,{value:(function createModuleRuntime(version, releaseHash) {
    const modules = Object.create(null), metadata = Object.create(null), chunks = new Map();
    const cache = Object.create(null);
    function require(id) {
        if (Object.hasOwn(cache, id)) return cache[id].exports;
        if (!Object.hasOwn(modules, id)) throw new Error('Missing bundled module ' + id);
        const module = cache[id] = { exports: {} };
        try { modules[id](module, module.exports, require); }
        catch (error) { delete cache[id]; throw error; }
        return module.exports;
    }
    function closure(entries) {
        const seen = new Set();
        function visit(id) {
            if (seen.has(id)) return;
            if (!Object.hasOwn(metadata, id)) throw new Error('Missing bundled module ' + id);
            seen.add(id);
            metadata[id].dependencies.forEach(visit);
        }
        entries.forEach(visit);
        return [...seen];
    }
    function register(manifest, incoming) {
        if (!manifest || typeof manifest.id !== 'string' || !manifest.id || typeof manifest.hash !== 'string' || !manifest.hash ||
            manifest.version !== version || manifest.releaseHash !== releaseHash || !Array.isArray(manifest.dependencies) || !Array.isArray(manifest.modules))
            throw new Error('Incompatible or malformed DDN chunk');
        const existing = chunks.get(manifest.id);
        if (existing) {
            if (existing.hash !== manifest.hash) throw new Error('Conflicting DDN chunk ' + manifest.id);
            return;
        }
        for (const dependency of manifest.dependencies)
            if (dependency === manifest.id || !chunks.has(dependency)) throw new Error('Missing DDN chunk dependency ' + dependency);
        const names = new Set();
        for (const item of manifest.modules) {
            if (!item || typeof item.id !== 'string' || !item.id || names.has(item.id) || typeof item.sha256 !== 'string' || !item.sha256 || !Array.isArray(item.dependencies) ||
                item.dependencies.some(id => typeof id !== 'string') || !incoming || !Object.hasOwn(incoming, item.id) || typeof incoming[item.id] !== 'function') throw new Error('Malformed DDN module');
            names.add(item.id);
            if (Object.hasOwn(metadata, item.id) && (metadata[item.id].sha256 !== item.sha256 || JSON.stringify(metadata[item.id].dependencies) !== JSON.stringify(item.dependencies))) throw new Error('Conflicting DDN module ' + item.id);
        }
        if (Object.keys(incoming).length !== names.size) throw new Error('Undeclared DDN chunk module');
        // Validate first, then install atomically so a failed chunk changes nothing.
        for (const item of manifest.modules) if (!Object.hasOwn(metadata, item.id)) {
            metadata[item.id] = { sha256: item.sha256, dependencies: [...item.dependencies] };
            modules[item.id] = incoming[item.id];
        }
        chunks.set(manifest.id, { hash: manifest.hash, dependencies: [...manifest.dependencies], modules: [...names] });
    }
    function worker(entry, preloads = []) {
        if (typeof entry !== 'string' || !Array.isArray(preloads) || preloads.some(id => typeof id !== 'string')) throw new TypeError('Invalid worker module selection');
        const entries = [...preloads, entry], ids = closure(entries);
        const source = 'const modules={' + ids.map(id => JSON.stringify(id) + ':' + modules[id].toString()).join(',') + '};const require=(' +
            // This loader is spelled locally so the serialized runtime has no closure dependencies.
            function (modules) {
                const cache = Object.create(null);
                return function require(id) {
                    if (Object.hasOwn(cache, id)) return cache[id].exports;
                    if (!Object.hasOwn(modules, id)) throw new Error('Missing bundled module ' + id);
                    const module = cache[id] = { exports: {} };
                    try { modules[id](module, module.exports, require); }
                    catch (error) { delete cache[id]; throw error; }
                    return module.exports;
                };
            }.toString() + ')(modules);' + entries.map(id => 'require(' + JSON.stringify(id) + ');').join('');
        const url = URL.createObjectURL(new Blob([source], { type: 'text/javascript' }));
        try { return new Worker(url, { name: 'ddn-compute' }); }
        finally { URL.revokeObjectURL(url); }
    }
    function describe() {
        return { version, hash: releaseHash, chunks: [...chunks].map(([id, value]) => ({ id, ...value, dependencies: [...value.dependencies], modules: [...value.modules] })),
            modules: Object.keys(metadata), executed: Object.keys(cache) };
    }
    return Object.freeze({ version, hash: releaseHash, register, require, worker, describe });
})(version,hash)});})();
(function installLoader(manifest, timeoutMs) {
    const script = document.currentScript;
    if (!script?.src) throw new Error('DDN loader must be loaded from a local script resource');
    const base = new URL('.', script.src), runtime = globalThis.DDN_MODULES;
    if (!runtime || runtime.version !== manifest.version || runtime.hash !== manifest.releaseHash) throw new Error('Incompatible DDN module runtime');
    const existing = globalThis.DDN_LOADER;
    if (existing) {
        if (existing.version !== manifest.version || existing.hash !== manifest.releaseHash) throw new Error('Incompatible DDN loader');
        return;
    }
    const chunks = new Map(manifest.chunks.map(chunk => [chunk.id, chunk]));
    const pendingChunks = new Map(), pendingEntries = new Map(), loadedEntries = new Set();
    const freeze = value => { if (value && typeof value === 'object' && !Object.isFrozen(value)) { Object.values(value).forEach(freeze); Object.freeze(value); } return value; };
    freeze(manifest);
    const entry = alias => {
        if (typeof alias !== 'string' || !Object.hasOwn(manifest.entries, alias)) throw new Error('Unknown DDN entry ' + String(alias));
        return manifest.entries[alias];
    };
    function registered(chunk) {
        const found = runtime.describe().chunks.find(value => value.id === chunk.id);
        if (found && found.hash !== chunk.hash) throw new Error('Incompatible DDN chunk ' + chunk.id);
        return !!found;
    }
    function loadChunk(id) {
        const chunk = chunks.get(id);
        if (!chunk) return Promise.reject(new Error('Unknown DDN chunk ' + id));
        try { if (registered(chunk)) return Promise.resolve(); } catch (error) { return Promise.reject(error); }
        const existing = pendingChunks.get(id);
        if (existing) return existing;
        const task = Promise.all(chunk.dependencies.map(loadChunk)).then(() => {
            if (registered(chunk)) return;
            return new Promise((resolve, reject) => {
                const element = document.createElement('script');
                const done = error => {
                    clearTimeout(timer); element.onload = element.onerror = null;
                    if (error) { element.remove(); reject(error); } else resolve();
                };
                const timer = setTimeout(() => done(new Error('Timed out loading DDN chunk ' + chunk.id)), timeoutMs);
                if (script.nonce) element.nonce = script.nonce;
                element.async = true;
                element.onload = () => { try { if (!registered(chunk)) throw new Error('DDN chunk did not register ' + chunk.id); done(); } catch (error) { done(error); } };
                element.onerror = () => done(new Error('Unable to load DDN chunk ' + chunk.id));
                element.src = new URL(chunk.file, base).href;
                document.head.append(element);
            });
        }).then(value => { pendingChunks.delete(id); return value; }, error => { pendingChunks.delete(id); throw error; });
        pendingChunks.set(id, task);
        return task;
    }
    function prepareEntry(alias) {
        let selected;
        try { selected = entry(alias); } catch (error) { return Promise.reject(error); }
        return loadChunk(selected.chunkId);
    }
    function loadEntry(alias) {
        let selected;
        try { selected = entry(alias); if (selected.kind === 'worker') throw new Error('Use prepareEntry for the DDN worker'); } catch (error) { return Promise.reject(error); }
        const existing = pendingEntries.get(alias);
        if (existing) return existing;
        const task = prepareEntry(alias).then(() => {
            const exports = runtime.require(selected.moduleId);
            loadedEntries.add(alias);
            return exports;
        }).catch(error => { pendingEntries.delete(alias); throw error; });
        pendingEntries.set(alias, task);
        return task;
    }
    function worker(alias, initializerAliases = []) {
        const selected = entry(alias);
        if (selected.kind !== 'worker' || !Array.isArray(initializerAliases)) throw new Error('Invalid DDN worker selection');
        for (const id of selected.chunks) if (!registered(chunks.get(id))) throw new Error('DDN worker is not prepared');
        const initializers = initializerAliases.map(alias => {
            const initializer = entry(alias);
            if (initializer.kind !== 'verification' || !loadedEntries.has(alias)) throw new Error('DDN worker initializer is not loaded: ' + alias);
            return initializer.moduleId;
        });
        return runtime.worker(selected.moduleId, [...new Set(initializers)]);
    }
    function describe() {
        return { version: manifest.version, hash: manifest.releaseHash, loadedEntries: [...loadedEntries],
            pendingEntries: [...pendingEntries.keys()].filter(alias => !loadedEntries.has(alias)), pendingChunks: [...pendingChunks.keys()], registry: runtime.describe() };
    }
    const auto = script.dataset.entry;
    const ready = auto ? prepareEntry('worker').then(() => loadEntry(auto)) : Promise.resolve();
    const api = Object.freeze({ version: manifest.version, hash: manifest.releaseHash, manifest, prepareEntry, loadEntry, worker, describe, ready });
    Object.defineProperty(globalThis, 'DDN_LOADER', { value: api });
    ready.then(() => { if (auto) document.querySelector('[data-ddn-loader-status]')?.remove(); }).catch(error => {
        const message = document.querySelector('[data-ddn-loader-status]') ?? document.createElement('p');
        message.setAttribute('role', 'alert'); message.textContent = 'Unable to load DDN: ' + error.message;
        if (!message.isConnected) (document.body ?? document.documentElement).append(message);
        document.dispatchEvent(new CustomEvent('ddn:load-error', { detail: { entry: auto, message: error.message } }));
    });
})({"format":"ddn-modular-1","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","license":"GPL-2.0-or-later","licenseFile":"LICENSE","notices":"NOTICE.md","copyright":"Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.","project":"https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation","sponsor":"https://scratchbird.ca","entries":{"api:designer":{"kind":"api","moduleId":"standalone/src/modular-designer-api.js","chunkId":"shared-7ffdd3196bf7","chunks":["shared-da593b1d80b5","shared-27149a72b67b","shared-2f1e15abcacd","shared-45f6b699ca1c","shared-4d0c8910f2dc","shared-957e9e2a3bbc","shared-90accf46a20e","shared-c0332320f91a","shared-f819ef245126","shared-9eb6624f1d40","shared-a3cf0afb56c8","shared-be0d56f8d05c","shared-7ffdd3196bf7"],"moduleCount":94,"rawBytes":2079963,"gzipBytes":419553},"api:verifier":{"kind":"api","moduleId":"standalone/src/modular-verifier-api.js","chunkId":"shared-cc6b5c75a915","chunks":["shared-da593b1d80b5","shared-27149a72b67b","shared-90accf46a20e","shared-c0332320f91a","shared-cc6b5c75a915"],"moduleCount":26,"rawBytes":1014060,"gzipBytes":169204},"api:viewer":{"kind":"api","moduleId":"standalone/src/modular-viewer-api.js","chunkId":"shared-b954ff0d3573","chunks":["shared-da593b1d80b5","shared-27149a72b67b","shared-2f1e15abcacd","shared-45f6b699ca1c","shared-4d0c8910f2dc","shared-90accf46a20e","shared-957e9e2a3bbc","shared-c0332320f91a","shared-f819ef245126","shared-9eb6624f1d40","shared-b954ff0d3573"],"moduleCount":70,"rawBytes":1593134,"gzipBytes":308120},"designer":{"kind":"utility","moduleId":"standalone/src/modular-designer-entry.js","chunkId":"designer-f0c69783274d","chunks":["shared-da593b1d80b5","shared-27149a72b67b","shared-2f1e15abcacd","shared-45f6b699ca1c","shared-4d0c8910f2dc","shared-957e9e2a3bbc","shared-90accf46a20e","shared-c0332320f91a","shared-f819ef245126","shared-9eb6624f1d40","shared-a3cf0afb56c8","shared-be0d56f8d05c","shared-7ffdd3196bf7","shared-9d235030a726","designer-f0c69783274d"],"moduleCount":102,"rawBytes":2257981,"gzipBytes":462534},"render:charts":{"kind":"rendering","moduleId":"standalone/src/families/charts.js","chunkId":"render-charts-4b9684e69142","chunks":["shared-2f1e15abcacd","shared-da593b1d80b5","shared-30d874e36969","shared-f819ef245126","shared-53b1375e60be","render-charts-4b9684e69142"],"moduleCount":24,"rawBytes":1028554,"gzipBytes":181292},"render:geography":{"kind":"rendering","moduleId":"standalone/src/families/geography.js","chunkId":"render-geography-bf877a421604","chunks":["shared-2f1e15abcacd","shared-f819ef245126","shared-53b1375e60be","shared-8e440530605d","render-geography-bf877a421604"],"moduleCount":10,"rawBytes":77520,"gzipBytes":23591},"render:graphs":{"kind":"rendering","moduleId":"standalone/src/families/graphs.js","chunkId":"render-graphs-b1f407355aef","chunks":["shared-2f1e15abcacd","shared-da593b1d80b5","shared-30d874e36969","shared-4d0c8910f2dc","shared-957e9e2a3bbc","shared-a3cf0afb56c8","render-graphs-b1f407355aef"],"moduleCount":28,"rawBytes":1150070,"gzipBytes":206825},"render:surfaces":{"kind":"rendering","moduleId":"standalone/src/families/surfaces.js","chunkId":"render-surfaces-ed072ebb93ca","chunks":["shared-2f1e15abcacd","shared-da593b1d80b5","shared-30d874e36969","shared-4d0c8910f2dc","shared-f819ef245126","shared-53b1375e60be","shared-8e440530605d","render-surfaces-ed072ebb93ca"],"moduleCount":22,"rawBytes":982286,"gzipBytes":174003},"verifier":{"kind":"utility","moduleId":"standalone/src/modular-verifier-entry.js","chunkId":"verifier-a92aa39dd4bd","chunks":["shared-da593b1d80b5","shared-27149a72b67b","shared-45f6b699ca1c","shared-be0d56f8d05c","shared-90accf46a20e","shared-c0332320f91a","shared-9d235030a726","shared-cc6b5c75a915","verifier-a92aa39dd4bd"],"moduleCount":44,"rawBytes":1290911,"gzipBytes":238497},"verify:charts":{"kind":"verification","moduleId":"profiles/src/families/charts.js","chunkId":"verify-charts-1f598b7d57ba","chunks":["shared-da593b1d80b5","shared-30d874e36969","shared-90accf46a20e","verify-charts-1f598b7d57ba"],"moduleCount":16,"rawBytes":945963,"gzipBytes":150637},"verify:geography":{"kind":"verification","moduleId":"profiles/src/families/geography.js","chunkId":"verify-geography-72edd281a0be","chunks":["shared-da593b1d80b5","shared-30d874e36969","shared-90accf46a20e","verify-geography-72edd281a0be"],"moduleCount":16,"rawBytes":883182,"gzipBytes":144551},"verify:graphs":{"kind":"verification","moduleId":"profiles/src/families/graphs.js","chunkId":"verify-graphs-2f61d2f4a428","chunks":["shared-da593b1d80b5","shared-30d874e36969","shared-90accf46a20e","verify-graphs-2f61d2f4a428"],"moduleCount":16,"rawBytes":1082276,"gzipBytes":174772},"verify:surfaces":{"kind":"verification","moduleId":"profiles/src/families/surfaces.js","chunkId":"verify-surfaces-75f505521ed3","chunks":["shared-da593b1d80b5","shared-30d874e36969","shared-90accf46a20e","verify-surfaces-75f505521ed3"],"moduleCount":16,"rawBytes":993529,"gzipBytes":156589},"viewer":{"kind":"utility","moduleId":"standalone/src/modular-viewer-entry.js","chunkId":"viewer-3ded8044c5c2","chunks":["shared-da593b1d80b5","shared-27149a72b67b","shared-45f6b699ca1c","shared-be0d56f8d05c","shared-90accf46a20e","shared-c0332320f91a","shared-9d235030a726","shared-2f1e15abcacd","shared-4d0c8910f2dc","shared-957e9e2a3bbc","shared-f819ef245126","shared-9eb6624f1d40","shared-b954ff0d3573","viewer-3ded8044c5c2"],"moduleCount":79,"rawBytes":1784722,"gzipBytes":355473},"worker":{"kind":"worker","moduleId":"standalone/src/modular-worker.js","chunkId":"worker-286113c36adf","chunks":["shared-da593b1d80b5","shared-27149a72b67b","shared-90accf46a20e","worker-286113c36adf"],"moduleCount":21,"rawBytes":986151,"gzipBytes":162654}},"chunks":[{"id":"shared-da593b1d80b5","file":"chunks/shared-da593b1d80b5.js","hash":"63d26571e2feb7efe4dc4247b3bcc0b0404b6b3c7903aa04fe2b7206225be16a","dependencies":[],"moduleIds":["profiles/src/catalogue-store.js","profiles/src/core.js","profiles/src/generated-codec.js","profiles/src/generated-families.js","profiles/src/generated-native.js","profiles/src/mindmap.js","profiles/src/schema-core.js"],"entries":["api:designer","api:verifier","api:viewer","designer","render:charts","render:graphs","render:surfaces","verifier","verify:charts","verify:geography","verify:graphs","verify:surfaces","viewer","worker"],"rawBytes":714132,"gzipBytes":102387},{"id":"shared-27149a72b67b","file":"chunks/shared-27149a72b67b.js","hash":"9097d25ebdbbff04888d374027330b0778a324d2a8cf548e2d1b3961b314281c","dependencies":["shared-da593b1d80b5"],"moduleIds":["defaults/src/index.js","defaults/src/method-names.js","execution/src/compute.js","execution/src/index.js","language/src/index.js","language/src/schema.js","model/src/index.js","profiles/src/view-surfaces.js","verifier/src/index.js"],"entries":["api:designer","api:verifier","api:viewer","designer","verifier","viewer","worker"],"rawBytes":257957,"gzipBytes":55548},{"id":"shared-2f1e15abcacd","file":"chunks/shared-2f1e15abcacd.js","hash":"a853d86d6228d8daecedfe686d68dc439ad6ab818b406cc55c1ddc55df8ff86f","dependencies":[],"moduleIds":["presentation/src/adapters.js","presentation/src/model.js"],"entries":["api:designer","api:viewer","designer","render:charts","render:geography","render:graphs","render:surfaces","viewer"],"rawBytes":9132,"gzipBytes":2990},{"id":"shared-45f6b699ca1c","file":"chunks/shared-45f6b699ca1c.js","hash":"8d3eef7f52060be8fd9de1444115b5a935ea0e31be894b24b53ee62b5fbae275","dependencies":[],"moduleIds":["viewer/src/dialogs.js","viewer/src/drawer.js","viewer/src/fonts.js","viewer/src/popout.js","viewer/src/resize-grip.js","viewer/src/texture.js","viewer/src/ui-commands.js","viewer/src/ui-icons.js","viewer/src/ui-theme.js"],"entries":["api:designer","api:viewer","designer","verifier","viewer"],"rawBytes":85359,"gzipBytes":21982},{"id":"shared-4d0c8910f2dc","file":"chunks/shared-4d0c8910f2dc.js","hash":"809ccf349de2fc4f2a4047a89d8eedb19cb07ff5ae91bd4d7996686648cba683","dependencies":[],"moduleIds":["presentation/src/table.js"],"entries":["api:designer","api:viewer","designer","render:graphs","render:surfaces","viewer"],"rawBytes":4695,"gzipBytes":1963},{"id":"shared-957e9e2a3bbc","file":"chunks/shared-957e9e2a3bbc.js","hash":"6bcf2602a406401199f8e1d9256acd64c37cda82efc3bca2b838da9765384762","dependencies":["shared-2f1e15abcacd","shared-4d0c8910f2dc","shared-da593b1d80b5"],"moduleIds":["presentation/src/card-text.js","presentation/src/graph-common.js","presentation/src/graph-glyphs.js","presentation/src/graph-layouts.js","presentation/src/graph-native.js","presentation/src/markdown.js","presentation/src/mindmap.js","presentation/src/relation-presentation.js","presentation/src/symbol-presentation.js"],"entries":["api:designer","api:viewer","designer","render:graphs","viewer"],"rawBytes":177803,"gzipBytes":41707},{"id":"shared-90accf46a20e","file":"chunks/shared-90accf46a20e.js","hash":"1a9114ae8ea6d40b9a5fa7cf51d7301d906a258d34ec0de1b82e6d8483afc12a","dependencies":["shared-da593b1d80b5"],"moduleIds":["profiles/src/family-packs.js","profiles/src/native.js","profiles/src/rules.js"],"entries":["api:designer","api:verifier","api:viewer","designer","verifier","verify:charts","verify:geography","verify:graphs","verify:surfaces","viewer","worker"],"rawBytes":9517,"gzipBytes":2883},{"id":"shared-c0332320f91a","file":"chunks/shared-c0332320f91a.js","hash":"dff85034dc07e9c032138b9e45a1a0c4fe52d421c16b29c63d68f0ab05ab557f","dependencies":["shared-27149a72b67b","shared-90accf46a20e","shared-da593b1d80b5"],"moduleIds":["execution/src/browser-verifier.js","execution/src/worker-host.js","runtime/src/versions.js","standalone/src/browser-options.js","standalone/src/modular-loading.js","standalone/src/modular-verifier.js"],"entries":["api:designer","api:verifier","api:viewer","designer","verifier","viewer"],"rawBytes":30441,"gzipBytes":7483},{"id":"shared-f819ef245126","file":"chunks/shared-f819ef245126.js","hash":"7630a2403f99f3b9f3e984b36aa091dbd64692c1bd390e18ee65c4415ad5efb2","dependencies":["shared-2f1e15abcacd"],"moduleIds":["presentation/src/stationery.js"],"entries":["api:designer","api:viewer","designer","render:charts","render:geography","render:surfaces","viewer"],"rawBytes":18631,"gzipBytes":5410},{"id":"shared-9eb6624f1d40","file":"chunks/shared-9eb6624f1d40.js","hash":"78148bc944c4a541aa182110473a7c3f0afff0a98fbcf15992842ad5c2532911","dependencies":["shared-27149a72b67b","shared-2f1e15abcacd","shared-45f6b699ca1c","shared-4d0c8910f2dc","shared-90accf46a20e","shared-957e9e2a3bbc","shared-c0332320f91a","shared-da593b1d80b5","shared-f819ef245126"],"moduleIds":["presentation/src/graph-isometric.js","presentation/src/native-render.js","presentation/src/native.js","presentation/src/project-core.js","presentation/src/publication.js","presentation/src/records.js","presentation/src/view-surface.js","runtime/src/guards.js","runtime/src/native.js","runtime/src/profile-loading.js","runtime/src/providers.js","runtime/src/registry.js","runtime/src/runtime.js","standalone/src/modular-runtime.js","standalone/src/modular-viewer.js","viewer/src/core.js","viewer/src/grid.js","viewer/src/native.js","viewer/src/side-tabs.js","viewer/src/standalone-viewport.js","viewer/src/status-hint.js","viewer/src/svg-assets.js"],"entries":["api:designer","api:viewer","designer","viewer"],"rawBytes":282732,"gzipBytes":64762},{"id":"shared-a3cf0afb56c8","file":"chunks/shared-a3cf0afb56c8.js","hash":"a924dc307b75f18402191e32b009a1171c31a3bafd59943d0c8c780e8523841b","dependencies":["shared-2f1e15abcacd","shared-957e9e2a3bbc","shared-da593b1d80b5"],"moduleIds":["presentation/src/node-dimensions.js"],"entries":["api:designer","designer","render:graphs"],"rawBytes":3785,"gzipBytes":1583},{"id":"shared-be0d56f8d05c","file":"chunks/shared-be0d56f8d05c.js","hash":"3fe406ca909f30b6eda05359c6bc68061bca059312bec3cb8a3c5411c78f8749","dependencies":["shared-45f6b699ca1c"],"moduleIds":["viewer/src/choice-field.js"],"entries":["api:designer","designer","verifier","viewer"],"rawBytes":14071,"gzipBytes":4557},{"id":"shared-7ffdd3196bf7","file":"chunks/shared-7ffdd3196bf7.js","hash":"d1acb28d7039fd5e4bf8251bbabbf648e81204a35daca616e8956e9246c70130","dependencies":["shared-27149a72b67b","shared-2f1e15abcacd","shared-45f6b699ca1c","shared-957e9e2a3bbc","shared-9eb6624f1d40","shared-a3cf0afb56c8","shared-be0d56f8d05c","shared-c0332320f91a","shared-da593b1d80b5"],"moduleIds":["designer/src/appearance.js","designer/src/clipboard.js","designer/src/dialogs.js","designer/src/element-preview.js","designer/src/index.js","designer/src/live-settings.js","designer/src/mindmap-actions.js","designer/src/mindmap-source.js","designer/src/new-diagram.js","designer/src/palette-groups.js","designer/src/presets.js","designer/src/properties.js","designer/src/relation-menu.js","designer/src/resize-handles.js","designer/src/schema-editor.js","designer/src/symbol.js","designer/src/view-layout-picker.js","designer/src/view-picker.js","designer/src/view-previews.js","runtime/src/commands.js","runtime/src/layout-edit.js","runtime/src/save.js","standalone/src/modular-designer-api.js"],"entries":["api:designer","designer"],"rawBytes":471708,"gzipBytes":106298},{"id":"shared-9d235030a726","file":"chunks/shared-9d235030a726.js","hash":"954ea8ef6eee0cc2519a33bb5a93db0758263a90506513ec9f2e333b418c760a","dependencies":["shared-27149a72b67b","shared-45f6b699ca1c","shared-be0d56f8d05c","shared-c0332320f91a"],"moduleIds":["standalone/src/brand.js","standalone/src/document-draft.js","standalone/src/menus.js","standalone/src/modular-shell.js","standalone/src/shell.js","standalone/src/website-navigation.js","standalone/src/zip.js"],"entries":["designer","verifier","viewer"],"rawBytes":175872,"gzipBytes":41901},{"id":"designer-f0c69783274d","file":"chunks/designer-f0c69783274d.js","hash":"c90d75ff823fb606aec8ac6dc7d86c62cc5c30c3d97fa13ea22875be7daabd5e","dependencies":["shared-7ffdd3196bf7","shared-9d235030a726"],"moduleIds":["standalone/src/modular-designer-entry.js"],"entries":["designer"],"rawBytes":2146,"gzipBytes":1080},{"id":"shared-30d874e36969","file":"chunks/shared-30d874e36969.js","hash":"987c1e72735564f529c905874fbdcd6323200e4dccfb6825a62ba849dcfa380d","dependencies":["shared-da593b1d80b5"],"moduleIds":["profiles/src/analysis-profile.js","profiles/src/analysis.js","profiles/src/projection-rules.js","profiles/src/semantic.js"],"entries":["render:charts","render:graphs","render:surfaces","verify:charts","verify:geography","verify:graphs","verify:surfaces"],"rawBytes":144506,"gzipBytes":34892},{"id":"shared-53b1375e60be","file":"chunks/shared-53b1375e60be.js","hash":"79bc33d6055de528c8a1160f528064b404e1d2290e2d01468e4d508efbc2e41d","dependencies":["shared-2f1e15abcacd","shared-f819ef245126"],"moduleIds":["presentation/src/data-adapter.js","presentation/src/data-catalogue.js","presentation/src/data-common.js"],"entries":["render:charts","render:geography","render:surfaces"],"rawBytes":21359,"gzipBytes":6731},{"id":"render-charts-4b9684e69142","file":"chunks/render-charts-4b9684e69142.js","hash":"661d5aba26538b10d2e8555a85f589659ce465d83b0e63468205db93b32c1362","dependencies":["shared-2f1e15abcacd","shared-30d874e36969","shared-53b1375e60be"],"moduleIds":["presentation/src/data-charts.js","presentation/src/data-hierarchy.js","presentation/src/data-isometric.js","presentation/src/data-quality.js","presentation/src/data-statistics.js","presentation/src/family-charts.js","standalone/src/families/charts.js"],"entries":["render:charts"],"rawBytes":120794,"gzipBytes":28882},{"id":"shared-8e440530605d","file":"chunks/shared-8e440530605d.js","hash":"1d7caeb56eb9ebf53e940690786cc79de947046506807baffe25cbb9c9592a08","dependencies":["shared-2f1e15abcacd","shared-53b1375e60be"],"moduleIds":["presentation/src/data-encoding.js"],"entries":["render:geography","render:surfaces"],"rawBytes":5982,"gzipBytes":2201},{"id":"render-geography-bf877a421604","file":"chunks/render-geography-bf877a421604.js","hash":"2b28648748dcd91741fa9f381090de09cd87cf3e4f6bbf7af186d998eaa40009","dependencies":["shared-2f1e15abcacd","shared-53b1375e60be","shared-8e440530605d"],"moduleIds":["presentation/src/data-geo.js","presentation/src/family-geography.js","standalone/src/families/geography.js"],"entries":["render:geography"],"rawBytes":22416,"gzipBytes":6259},{"id":"render-graphs-b1f407355aef","file":"chunks/render-graphs-b1f407355aef.js","hash":"403675d7aad3308cbd6db2834c50364ecdc2d0170019370c5622a9181e9ca279","dependencies":["shared-2f1e15abcacd","shared-30d874e36969","shared-4d0c8910f2dc","shared-957e9e2a3bbc","shared-a3cf0afb56c8","shared-da593b1d80b5"],"moduleIds":["presentation/src/family-graphs.js","presentation/src/graph-catalogue.js","presentation/src/graph-profiles.js","standalone/src/families/graphs.js"],"entries":["render:graphs"],"rawBytes":96017,"gzipBytes":21303},{"id":"render-surfaces-ed072ebb93ca","file":"chunks/render-surfaces-ed072ebb93ca.js","hash":"2346c17710201b5df6ed7095e851b784c64feca83a6498c9941ee94f2e752b33","dependencies":["shared-2f1e15abcacd","shared-30d874e36969","shared-4d0c8910f2dc","shared-53b1375e60be","shared-8e440530605d"],"moduleIds":["presentation/src/data-surfaces.js","presentation/src/family-surfaces.js","standalone/src/families/surfaces.js"],"entries":["render:surfaces"],"rawBytes":63849,"gzipBytes":17429},{"id":"shared-b954ff0d3573","file":"chunks/shared-b954ff0d3573.js","hash":"9a5b937d6c0ecfdf3b9dc53be7f0c99fcce489f8a58cdd044ba400725f43d074","dependencies":["shared-9eb6624f1d40","shared-c0332320f91a"],"moduleIds":["standalone/src/modular-viewer-api.js"],"entries":["api:viewer","viewer"],"rawBytes":2735,"gzipBytes":1005},{"id":"shared-cc6b5c75a915","file":"chunks/shared-cc6b5c75a915.js","hash":"4d8af505c6009714dc14abab11cb1a3486c3bb6be87c604c2fc5feb1fb5382e6","dependencies":["shared-c0332320f91a"],"moduleIds":["standalone/src/modular-verifier-api.js"],"entries":["api:verifier","verifier"],"rawBytes":2013,"gzipBytes":903},{"id":"verifier-a92aa39dd4bd","file":"chunks/verifier-a92aa39dd4bd.js","hash":"b6a88f109453f3bc5e46093aa812c14f5e551affbfb09dd1cb8fa1bc447b45ef","dependencies":["shared-9d235030a726","shared-cc6b5c75a915"],"moduleIds":["standalone/src/modular-verifier-entry.js"],"entries":["verifier"],"rawBytes":1549,"gzipBytes":853},{"id":"verify-charts-1f598b7d57ba","file":"chunks/verify-charts-1f598b7d57ba.js","hash":"66b93ec6bdcdb7a0864e0531d418226a7d4d354ccf6bf646badc69079e21a71d","dependencies":["shared-30d874e36969","shared-90accf46a20e","shared-da593b1d80b5"],"moduleIds":["profiles/src/families/charts.js","profiles/src/generated-family-charts.js"],"entries":["verify:charts"],"rawBytes":77808,"gzipBytes":10475},{"id":"verify-geography-72edd281a0be","file":"chunks/verify-geography-72edd281a0be.js","hash":"fdb129acaafd87d5d3553588e1c3e27ecc01a6eeecf174f2e5daab32ca3e4264","dependencies":["shared-30d874e36969","shared-90accf46a20e","shared-da593b1d80b5"],"moduleIds":["profiles/src/families/geography.js","profiles/src/generated-family-geography.js"],"entries":["verify:geography"],"rawBytes":15027,"gzipBytes":4389},{"id":"verify-graphs-2f61d2f4a428","file":"chunks/verify-graphs-2f61d2f4a428.js","hash":"bb120ff6ce6771c569074001739f964dccbf4792564f8dd65dd31d538f588093","dependencies":["shared-30d874e36969","shared-90accf46a20e","shared-da593b1d80b5"],"moduleIds":["profiles/src/families/graphs.js","profiles/src/generated-family-graphs.js"],"entries":["verify:graphs"],"rawBytes":214121,"gzipBytes":34610},{"id":"verify-surfaces-75f505521ed3","file":"chunks/verify-surfaces-75f505521ed3.js","hash":"d5b59ca5924ec468950cf3004b0e43bf5716f239dc799e54fba0e2105d872cbf","dependencies":["shared-30d874e36969","shared-90accf46a20e","shared-da593b1d80b5"],"moduleIds":["profiles/src/families/surfaces.js","profiles/src/generated-family-surfaces.js"],"entries":["verify:surfaces"],"rawBytes":125374,"gzipBytes":16427},{"id":"viewer-3ded8044c5c2","file":"chunks/viewer-3ded8044c5c2.js","hash":"af158e0efcd93829b69abe95c22360066f5c3bb62d66493fcbb26dfca11b5c0e","dependencies":["shared-9d235030a726","shared-b954ff0d3573"],"moduleIds":["standalone/src/modular-viewer-entry.js"],"entries":["viewer"],"rawBytes":1645,"gzipBytes":895},{"id":"worker-286113c36adf","file":"chunks/worker-286113c36adf.js","hash":"15275a3a335f280a371ac767e490ee0e0ce0b295990fd4afa33c99fa33c39095","dependencies":["shared-27149a72b67b","shared-90accf46a20e"],"moduleIds":["execution/src/worker-entry.js","standalone/src/modular-worker.js"],"entries":["worker"],"rawBytes":4545,"gzipBytes":1836}],"totals":{"modules":141,"chunks":31,"rawBytes":3177721,"gzipBytes":651624}},15000);
