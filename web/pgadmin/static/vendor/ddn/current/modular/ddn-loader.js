/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const name="DDN_MODULES",version="ddn-next-1",hash="4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131";if(Object.hasOwn(globalThis,name)){const current=globalThis[name];if(current?.version!==version||current?.hash!==hash||typeof current.register!=="function")throw Error("Incompatible DDN module runtime");return;}Object.defineProperty(globalThis,name,{value:(function createModuleRuntime(version, releaseHash) {
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
})({"format":"ddn-modular-1","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","license":"GPL-2.0-or-later","licenseFile":"LICENSE","notices":"NOTICE.md","copyright":"Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.","project":"https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation","sponsor":"https://scratchbird.ca","entries":{"api:designer":{"kind":"api","moduleId":"standalone/src/modular-designer-api.js","chunkId":"shared-673390dbad9b","chunks":["shared-6cf9d24a4527","shared-89ca0b52749b","shared-aea9ceabbf71","shared-5331ef8070e8","shared-73905c5bd21c","shared-30b5187aadd6","shared-e89a1c8e2b2d","shared-f98a38a4da4d","shared-ebd47c4e1fef","shared-822f2cb38cc6","shared-8f37b97a0edc","shared-a1e32f51fc2a","shared-673390dbad9b"],"moduleCount":94,"rawBytes":2083710,"gzipBytes":420231},"api:verifier":{"kind":"api","moduleId":"standalone/src/modular-verifier-api.js","chunkId":"shared-a67aa111fa97","chunks":["shared-89ca0b52749b","shared-e89a1c8e2b2d","shared-f98a38a4da4d","shared-ebd47c4e1fef","shared-a67aa111fa97"],"moduleCount":26,"rawBytes":1017807,"gzipBytes":169887},"api:viewer":{"kind":"api","moduleId":"standalone/src/modular-viewer-api.js","chunkId":"shared-1d7e2e746c2a","chunks":["shared-6cf9d24a4527","shared-30b5187aadd6","shared-89ca0b52749b","shared-aea9ceabbf71","shared-5331ef8070e8","shared-73905c5bd21c","shared-e89a1c8e2b2d","shared-f98a38a4da4d","shared-ebd47c4e1fef","shared-822f2cb38cc6","shared-1d7e2e746c2a"],"moduleCount":70,"rawBytes":1596881,"gzipBytes":308795},"designer":{"kind":"utility","moduleId":"standalone/src/modular-designer-entry.js","chunkId":"designer-296e54f2516f","chunks":["shared-6cf9d24a4527","shared-89ca0b52749b","shared-aea9ceabbf71","shared-5331ef8070e8","shared-73905c5bd21c","shared-30b5187aadd6","shared-e89a1c8e2b2d","shared-f98a38a4da4d","shared-ebd47c4e1fef","shared-822f2cb38cc6","shared-8f37b97a0edc","shared-a1e32f51fc2a","shared-673390dbad9b","shared-e37dea31afcf","designer-296e54f2516f"],"moduleCount":102,"rawBytes":2261728,"gzipBytes":463207},"render:charts":{"kind":"rendering","moduleId":"standalone/src/families/charts.js","chunkId":"render-charts-875491bc3a3b","chunks":["shared-6cf9d24a4527","shared-30b5187aadd6","shared-6502a4606789","shared-89ca0b52749b","shared-98e37fe0f266","render-charts-875491bc3a3b"],"moduleCount":24,"rawBytes":1028554,"gzipBytes":181293},"render:geography":{"kind":"rendering","moduleId":"standalone/src/families/geography.js","chunkId":"render-geography-a05e8125ccba","chunks":["shared-6cf9d24a4527","shared-30b5187aadd6","shared-6502a4606789","shared-75a64c87e8fc","render-geography-a05e8125ccba"],"moduleCount":10,"rawBytes":77520,"gzipBytes":23594},"render:graphs":{"kind":"rendering","moduleId":"standalone/src/families/graphs.js","chunkId":"render-graphs-7fe3f90de312","chunks":["shared-6cf9d24a4527","shared-89ca0b52749b","shared-aea9ceabbf71","shared-5331ef8070e8","shared-8f37b97a0edc","shared-98e37fe0f266","render-graphs-7fe3f90de312"],"moduleCount":28,"rawBytes":1150070,"gzipBytes":206821},"render:surfaces":{"kind":"rendering","moduleId":"standalone/src/families/surfaces.js","chunkId":"render-surfaces-27d8be99e458","chunks":["shared-6cf9d24a4527","shared-30b5187aadd6","shared-6502a4606789","shared-75a64c87e8fc","shared-89ca0b52749b","shared-98e37fe0f266","shared-aea9ceabbf71","render-surfaces-27d8be99e458"],"moduleCount":22,"rawBytes":982286,"gzipBytes":173999},"verifier":{"kind":"utility","moduleId":"standalone/src/modular-verifier-entry.js","chunkId":"verifier-48faa5330b54","chunks":["shared-89ca0b52749b","shared-e89a1c8e2b2d","shared-f98a38a4da4d","shared-ebd47c4e1fef","shared-a67aa111fa97","shared-73905c5bd21c","shared-a1e32f51fc2a","shared-e37dea31afcf","verifier-48faa5330b54"],"moduleCount":44,"rawBytes":1294658,"gzipBytes":239173},"verify:charts":{"kind":"verification","moduleId":"profiles/src/families/charts.js","chunkId":"verify-charts-caa2720e883d","chunks":["shared-89ca0b52749b","shared-98e37fe0f266","shared-e89a1c8e2b2d","verify-charts-caa2720e883d"],"moduleCount":16,"rawBytes":945963,"gzipBytes":150632},"verify:geography":{"kind":"verification","moduleId":"profiles/src/families/geography.js","chunkId":"verify-geography-bcc5a9b92d5c","chunks":["shared-89ca0b52749b","shared-98e37fe0f266","shared-e89a1c8e2b2d","verify-geography-bcc5a9b92d5c"],"moduleCount":16,"rawBytes":883182,"gzipBytes":144552},"verify:graphs":{"kind":"verification","moduleId":"profiles/src/families/graphs.js","chunkId":"verify-graphs-772258308814","chunks":["shared-89ca0b52749b","shared-98e37fe0f266","shared-e89a1c8e2b2d","verify-graphs-772258308814"],"moduleCount":16,"rawBytes":1082276,"gzipBytes":174769},"verify:surfaces":{"kind":"verification","moduleId":"profiles/src/families/surfaces.js","chunkId":"verify-surfaces-0dc5102a6fd9","chunks":["shared-89ca0b52749b","shared-98e37fe0f266","shared-e89a1c8e2b2d","verify-surfaces-0dc5102a6fd9"],"moduleCount":16,"rawBytes":993529,"gzipBytes":156581},"viewer":{"kind":"utility","moduleId":"standalone/src/modular-viewer-entry.js","chunkId":"viewer-defe0ef52de3","chunks":["shared-6cf9d24a4527","shared-30b5187aadd6","shared-89ca0b52749b","shared-aea9ceabbf71","shared-5331ef8070e8","shared-73905c5bd21c","shared-e89a1c8e2b2d","shared-f98a38a4da4d","shared-ebd47c4e1fef","shared-822f2cb38cc6","shared-1d7e2e746c2a","shared-a1e32f51fc2a","shared-e37dea31afcf","viewer-defe0ef52de3"],"moduleCount":79,"rawBytes":1788469,"gzipBytes":356140},"worker":{"kind":"worker","moduleId":"standalone/src/modular-worker.js","chunkId":"worker-f621ec472de9","chunks":["shared-89ca0b52749b","shared-e89a1c8e2b2d","shared-f98a38a4da4d","worker-f621ec472de9"],"moduleCount":21,"rawBytes":989898,"gzipBytes":163345}},"chunks":[{"id":"shared-6cf9d24a4527","file":"chunks/shared-6cf9d24a4527.js","hash":"bfb87fc63c461203438ff7a63ed517d51b327a8704b1fb09a099ec6e4582b911","dependencies":[],"moduleIds":["presentation/src/adapters.js","presentation/src/model.js"],"entries":["api:designer","api:viewer","designer","render:charts","render:geography","render:graphs","render:surfaces","viewer"],"rawBytes":9132,"gzipBytes":2996},{"id":"shared-89ca0b52749b","file":"chunks/shared-89ca0b52749b.js","hash":"6ca3bc9d0d1f0ab9c4de7a3471ee03b4a3730ee814ef9ba464250ccde94002d6","dependencies":[],"moduleIds":["profiles/src/catalogue-store.js","profiles/src/core.js","profiles/src/generated-codec.js","profiles/src/generated-families.js","profiles/src/generated-native.js","profiles/src/mindmap.js","profiles/src/schema-core.js"],"entries":["api:designer","api:verifier","api:viewer","designer","render:charts","render:graphs","render:surfaces","verifier","verify:charts","verify:geography","verify:graphs","verify:surfaces","viewer","worker"],"rawBytes":714132,"gzipBytes":102387},{"id":"shared-aea9ceabbf71","file":"chunks/shared-aea9ceabbf71.js","hash":"f2abe8a3107ecffe9d75b65294fc17588bff8118cd6b776c9b4c7eed9f373ea7","dependencies":[],"moduleIds":["presentation/src/table.js"],"entries":["api:designer","api:viewer","designer","render:graphs","render:surfaces","viewer"],"rawBytes":4695,"gzipBytes":1960},{"id":"shared-5331ef8070e8","file":"chunks/shared-5331ef8070e8.js","hash":"ac4dfe5356bc64c1a90c624c08c867b6b4dba34b33d87398ac3b9061c44ebc8b","dependencies":["shared-6cf9d24a4527","shared-89ca0b52749b","shared-aea9ceabbf71"],"moduleIds":["presentation/src/card-text.js","presentation/src/graph-common.js","presentation/src/graph-glyphs.js","presentation/src/graph-layouts.js","presentation/src/graph-native.js","presentation/src/markdown.js","presentation/src/mindmap.js","presentation/src/relation-presentation.js","presentation/src/symbol-presentation.js"],"entries":["api:designer","api:viewer","designer","render:graphs","viewer"],"rawBytes":177803,"gzipBytes":41705},{"id":"shared-73905c5bd21c","file":"chunks/shared-73905c5bd21c.js","hash":"30acc2156c8aa4f46cf732357a6d4e47957b0ade583f70b597a5705033d0c1f3","dependencies":[],"moduleIds":["viewer/src/dialogs.js","viewer/src/drawer.js","viewer/src/fonts.js","viewer/src/popout.js","viewer/src/resize-grip.js","viewer/src/texture.js","viewer/src/ui-commands.js","viewer/src/ui-icons.js","viewer/src/ui-theme.js"],"entries":["api:designer","api:viewer","designer","verifier","viewer"],"rawBytes":85359,"gzipBytes":21982},{"id":"shared-30b5187aadd6","file":"chunks/shared-30b5187aadd6.js","hash":"b0cc2743b6f16df38a75d3ec66411b32930b7fc47cb8a01d89f7310eef40d2bf","dependencies":["shared-6cf9d24a4527"],"moduleIds":["presentation/src/stationery.js"],"entries":["api:designer","api:viewer","designer","render:charts","render:geography","render:surfaces","viewer"],"rawBytes":18631,"gzipBytes":5410},{"id":"shared-e89a1c8e2b2d","file":"chunks/shared-e89a1c8e2b2d.js","hash":"50621f2128363c4d3e3d646e4a9d9144c4621cf3f175df7aed3e2d9cbdb4e0af","dependencies":["shared-89ca0b52749b"],"moduleIds":["profiles/src/family-packs.js","profiles/src/native.js","profiles/src/rules.js"],"entries":["api:designer","api:verifier","api:viewer","designer","verifier","verify:charts","verify:geography","verify:graphs","verify:surfaces","viewer","worker"],"rawBytes":9517,"gzipBytes":2884},{"id":"shared-f98a38a4da4d","file":"chunks/shared-f98a38a4da4d.js","hash":"393615f4f4643cbbcd63e28898cc9b88ce418cebab5baa683dadb0984667a3f5","dependencies":["shared-89ca0b52749b"],"moduleIds":["defaults/src/index.js","defaults/src/method-names.js","execution/src/compute.js","execution/src/index.js","language/src/index.js","language/src/schema.js","model/src/index.js","profiles/src/view-surfaces.js","verifier/src/index.js"],"entries":["api:designer","api:verifier","api:viewer","designer","verifier","viewer","worker"],"rawBytes":261704,"gzipBytes":56238},{"id":"shared-ebd47c4e1fef","file":"chunks/shared-ebd47c4e1fef.js","hash":"b2a6f3f77c2d41402934bee079e3742d7a77a5792704c3a8a4667a58da2857d0","dependencies":["shared-89ca0b52749b","shared-e89a1c8e2b2d","shared-f98a38a4da4d"],"moduleIds":["execution/src/browser-verifier.js","execution/src/worker-host.js","runtime/src/versions.js","standalone/src/browser-options.js","standalone/src/modular-loading.js","standalone/src/modular-verifier.js"],"entries":["api:designer","api:verifier","api:viewer","designer","verifier","viewer"],"rawBytes":30441,"gzipBytes":7477},{"id":"shared-822f2cb38cc6","file":"chunks/shared-822f2cb38cc6.js","hash":"bb7f980cee32d1121397983a48e5d4acab7333d5f7700366049ca3040fb63c8d","dependencies":["shared-30b5187aadd6","shared-5331ef8070e8","shared-6cf9d24a4527","shared-73905c5bd21c","shared-89ca0b52749b","shared-aea9ceabbf71","shared-e89a1c8e2b2d","shared-ebd47c4e1fef","shared-f98a38a4da4d"],"moduleIds":["presentation/src/graph-isometric.js","presentation/src/native-render.js","presentation/src/native.js","presentation/src/project-core.js","presentation/src/publication.js","presentation/src/records.js","presentation/src/view-surface.js","runtime/src/guards.js","runtime/src/native.js","runtime/src/profile-loading.js","runtime/src/providers.js","runtime/src/registry.js","runtime/src/runtime.js","standalone/src/modular-runtime.js","standalone/src/modular-viewer.js","viewer/src/core.js","viewer/src/grid.js","viewer/src/native.js","viewer/src/side-tabs.js","viewer/src/standalone-viewport.js","viewer/src/status-hint.js","viewer/src/svg-assets.js"],"entries":["api:designer","api:viewer","designer","viewer"],"rawBytes":282732,"gzipBytes":64752},{"id":"shared-8f37b97a0edc","file":"chunks/shared-8f37b97a0edc.js","hash":"e32b5b628ab2521fc105e9f7164b8a4284ca47313fc89de1e09894e1daf0c4e4","dependencies":["shared-5331ef8070e8","shared-6cf9d24a4527","shared-89ca0b52749b"],"moduleIds":["presentation/src/node-dimensions.js"],"entries":["api:designer","designer","render:graphs"],"rawBytes":3785,"gzipBytes":1584},{"id":"shared-a1e32f51fc2a","file":"chunks/shared-a1e32f51fc2a.js","hash":"ed1a7322694de1e832ea1470ec4713b966a1cc2d58876cba9b4503d13216e177","dependencies":["shared-73905c5bd21c"],"moduleIds":["viewer/src/choice-field.js"],"entries":["api:designer","designer","verifier","viewer"],"rawBytes":14071,"gzipBytes":4557},{"id":"shared-673390dbad9b","file":"chunks/shared-673390dbad9b.js","hash":"63a770fcf3b872d131b8a49b9dd8816a437c145a19cba27c113d055d1a5b2e62","dependencies":["shared-5331ef8070e8","shared-6cf9d24a4527","shared-73905c5bd21c","shared-822f2cb38cc6","shared-89ca0b52749b","shared-8f37b97a0edc","shared-a1e32f51fc2a","shared-ebd47c4e1fef","shared-f98a38a4da4d"],"moduleIds":["designer/src/appearance.js","designer/src/clipboard.js","designer/src/dialogs.js","designer/src/element-preview.js","designer/src/index.js","designer/src/live-settings.js","designer/src/mindmap-actions.js","designer/src/mindmap-source.js","designer/src/new-diagram.js","designer/src/palette-groups.js","designer/src/presets.js","designer/src/properties.js","designer/src/relation-menu.js","designer/src/resize-handles.js","designer/src/schema-editor.js","designer/src/symbol.js","designer/src/view-layout-picker.js","designer/src/view-picker.js","designer/src/view-previews.js","runtime/src/commands.js","runtime/src/layout-edit.js","runtime/src/save.js","standalone/src/modular-designer-api.js"],"entries":["api:designer","designer"],"rawBytes":471708,"gzipBytes":106299},{"id":"shared-e37dea31afcf","file":"chunks/shared-e37dea31afcf.js","hash":"9d3a2c343e5d3d30f3bab6e1a1a30057c205086d96db9798bc7aa951ea787491","dependencies":["shared-73905c5bd21c","shared-a1e32f51fc2a","shared-ebd47c4e1fef","shared-f98a38a4da4d"],"moduleIds":["standalone/src/brand.js","standalone/src/document-draft.js","standalone/src/menus.js","standalone/src/modular-shell.js","standalone/src/shell.js","standalone/src/website-navigation.js","standalone/src/zip.js"],"entries":["designer","verifier","viewer"],"rawBytes":175872,"gzipBytes":41896},{"id":"designer-296e54f2516f","file":"chunks/designer-296e54f2516f.js","hash":"a4e5a7c2e294a94965ab441454b54dde70513d0fee8aa1f25a1459a4ed320e56","dependencies":["shared-673390dbad9b","shared-e37dea31afcf"],"moduleIds":["standalone/src/modular-designer-entry.js"],"entries":["designer"],"rawBytes":2146,"gzipBytes":1080},{"id":"shared-6502a4606789","file":"chunks/shared-6502a4606789.js","hash":"9f5835bb182a80fa783d7fef6c6681586e545861f469312d8cd2f3212af377f9","dependencies":["shared-30b5187aadd6","shared-6cf9d24a4527"],"moduleIds":["presentation/src/data-adapter.js","presentation/src/data-catalogue.js","presentation/src/data-common.js"],"entries":["render:charts","render:geography","render:surfaces"],"rawBytes":21359,"gzipBytes":6733},{"id":"shared-98e37fe0f266","file":"chunks/shared-98e37fe0f266.js","hash":"ed76d8c00864af0e785d2e0879426fc905f2612e496d2e138e6875328c05d1a4","dependencies":["shared-89ca0b52749b"],"moduleIds":["profiles/src/analysis-profile.js","profiles/src/analysis.js","profiles/src/projection-rules.js","profiles/src/semantic.js"],"entries":["render:charts","render:graphs","render:surfaces","verify:charts","verify:geography","verify:graphs","verify:surfaces"],"rawBytes":144506,"gzipBytes":34888},{"id":"render-charts-875491bc3a3b","file":"chunks/render-charts-875491bc3a3b.js","hash":"2a9e05d23acda8c123cacef0d55e0238b975ad2e7ba54a70501fcdbbc09fa303","dependencies":["shared-6502a4606789","shared-6cf9d24a4527","shared-98e37fe0f266"],"moduleIds":["presentation/src/data-charts.js","presentation/src/data-hierarchy.js","presentation/src/data-isometric.js","presentation/src/data-quality.js","presentation/src/data-statistics.js","presentation/src/family-charts.js","standalone/src/families/charts.js"],"entries":["render:charts"],"rawBytes":120794,"gzipBytes":28879},{"id":"shared-75a64c87e8fc","file":"chunks/shared-75a64c87e8fc.js","hash":"96054e000d6bf1dc8a27443324d0e70ed345ecafb36a0dd987b2b50e99475254","dependencies":["shared-6502a4606789","shared-6cf9d24a4527"],"moduleIds":["presentation/src/data-encoding.js"],"entries":["render:geography","render:surfaces"],"rawBytes":5982,"gzipBytes":2199},{"id":"render-geography-a05e8125ccba","file":"chunks/render-geography-a05e8125ccba.js","hash":"a80094f5e16916dcdc7d8d357765ccd047b5ec0f36d21cd4ccc59d3492c4d21e","dependencies":["shared-6502a4606789","shared-6cf9d24a4527","shared-75a64c87e8fc"],"moduleIds":["presentation/src/data-geo.js","presentation/src/family-geography.js","standalone/src/families/geography.js"],"entries":["render:geography"],"rawBytes":22416,"gzipBytes":6256},{"id":"render-graphs-7fe3f90de312","file":"chunks/render-graphs-7fe3f90de312.js","hash":"b8d129fa40910da92c50c010fc3202b32311da5e6235e4df5bedf2b0e5de539f","dependencies":["shared-5331ef8070e8","shared-6cf9d24a4527","shared-89ca0b52749b","shared-8f37b97a0edc","shared-98e37fe0f266","shared-aea9ceabbf71"],"moduleIds":["presentation/src/family-graphs.js","presentation/src/graph-catalogue.js","presentation/src/graph-profiles.js","standalone/src/families/graphs.js"],"entries":["render:graphs"],"rawBytes":96017,"gzipBytes":21301},{"id":"render-surfaces-27d8be99e458","file":"chunks/render-surfaces-27d8be99e458.js","hash":"8d597f1c627ba021287f0f38346b6b86826a866154f94f95090f7c5ddb77c45a","dependencies":["shared-6502a4606789","shared-6cf9d24a4527","shared-75a64c87e8fc","shared-98e37fe0f266","shared-aea9ceabbf71"],"moduleIds":["presentation/src/data-surfaces.js","presentation/src/family-surfaces.js","standalone/src/families/surfaces.js"],"entries":["render:surfaces"],"rawBytes":63849,"gzipBytes":17426},{"id":"shared-1d7e2e746c2a","file":"chunks/shared-1d7e2e746c2a.js","hash":"1e99a6850dbb53e23c3f3f417c9189c08ada06a59d8af7e50ff60f533af20274","dependencies":["shared-822f2cb38cc6","shared-ebd47c4e1fef"],"moduleIds":["standalone/src/modular-viewer-api.js"],"entries":["api:viewer","viewer"],"rawBytes":2735,"gzipBytes":1004},{"id":"shared-a67aa111fa97","file":"chunks/shared-a67aa111fa97.js","hash":"b0d29295831d218fb9baef4f48bb0bec2934b214fa03232ab4a0d65fa98c539b","dependencies":["shared-ebd47c4e1fef"],"moduleIds":["standalone/src/modular-verifier-api.js"],"entries":["api:verifier","verifier"],"rawBytes":2013,"gzipBytes":901},{"id":"verifier-48faa5330b54","file":"chunks/verifier-48faa5330b54.js","hash":"6b8cbc3e720214676ced4e10fea00845feb0e0749febe80b0c5c146c9df75afa","dependencies":["shared-a67aa111fa97","shared-e37dea31afcf"],"moduleIds":["standalone/src/modular-verifier-entry.js"],"entries":["verifier"],"rawBytes":1549,"gzipBytes":851},{"id":"verify-charts-caa2720e883d","file":"chunks/verify-charts-caa2720e883d.js","hash":"a507f78f4bbed465d0b1169473affb8eb2f80e2acf338150fab66b5b684c6330","dependencies":["shared-89ca0b52749b","shared-98e37fe0f266","shared-e89a1c8e2b2d"],"moduleIds":["profiles/src/families/charts.js","profiles/src/generated-family-charts.js"],"entries":["verify:charts"],"rawBytes":77808,"gzipBytes":10473},{"id":"verify-geography-bcc5a9b92d5c","file":"chunks/verify-geography-bcc5a9b92d5c.js","hash":"e82c81e520e56be94439d57c7dc3bb4e3d7b71a3a31bc06133161e1c158bb2d3","dependencies":["shared-89ca0b52749b","shared-98e37fe0f266","shared-e89a1c8e2b2d"],"moduleIds":["profiles/src/families/geography.js","profiles/src/generated-family-geography.js"],"entries":["verify:geography"],"rawBytes":15027,"gzipBytes":4393},{"id":"verify-graphs-772258308814","file":"chunks/verify-graphs-772258308814.js","hash":"e70cedeeb94c43de6489e408d1332f9e361a771cb1557fe12c5e38b4328394dc","dependencies":["shared-89ca0b52749b","shared-98e37fe0f266","shared-e89a1c8e2b2d"],"moduleIds":["profiles/src/families/graphs.js","profiles/src/generated-family-graphs.js"],"entries":["verify:graphs"],"rawBytes":214121,"gzipBytes":34610},{"id":"verify-surfaces-0dc5102a6fd9","file":"chunks/verify-surfaces-0dc5102a6fd9.js","hash":"f6ec30d4f276c1687ccc03cb16a319d301de53aa7d9e9f4ff5715c6add2a8a10","dependencies":["shared-89ca0b52749b","shared-98e37fe0f266","shared-e89a1c8e2b2d"],"moduleIds":["profiles/src/families/surfaces.js","profiles/src/generated-family-surfaces.js"],"entries":["verify:surfaces"],"rawBytes":125374,"gzipBytes":16422},{"id":"viewer-defe0ef52de3","file":"chunks/viewer-defe0ef52de3.js","hash":"19c2694753882f76000f39a6292db4e05abfa548e4c8ee27ecc8b3c148244d62","dependencies":["shared-1d7e2e746c2a","shared-e37dea31afcf"],"moduleIds":["standalone/src/modular-viewer-entry.js"],"entries":["viewer"],"rawBytes":1645,"gzipBytes":892},{"id":"worker-f621ec472de9","file":"chunks/worker-f621ec472de9.js","hash":"f79008172d50c608127ef92c62f9a17c26ba4850da530947665edb7a889446de","dependencies":["shared-e89a1c8e2b2d","shared-f98a38a4da4d"],"moduleIds":["execution/src/worker-entry.js","standalone/src/modular-worker.js"],"entries":["worker"],"rawBytes":4545,"gzipBytes":1836}],"totals":{"modules":141,"chunks":31,"rawBytes":3181468,"gzipBytes":652271}},15000);
