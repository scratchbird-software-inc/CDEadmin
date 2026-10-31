/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-7ada2b877c52","version":"ddn-next-1","releaseHash":"a013ac52c7b3173ca4a5c5558fb8bac7b899854da330646dcd39702d0d86b778","dependencies":["shared-0e2e62c8ac26","shared-4dfa2129e2cc","shared-646a07aa4889","shared-86dfe18929a0","shared-8776885c04b2","shared-9019e1da906d","shared-a54850724181","shared-c435f270a427","shared-cca37dc67bcd"],"modules":[{"id":"designer/src/appearance.js","bytes":28216,"sha256":"2eb18c86c0cf7d9a975e151aa824d0bdbbc24d0a6549a24f683f39121a55bec8","dependencies":["viewer/src/native.js","viewer/src/fonts.js","viewer/src/texture.js","viewer/src/choice-field.js","designer/src/live-settings.js","presentation/src/native.js","runtime/src/runtime.js","language/src/index.js","designer/src/dialogs.js","designer/src/presets.js"]},{"id":"designer/src/clipboard.js","bytes":5227,"sha256":"9387bba21551b61f4d9b14945282a248cc74e2e27d6bb765fb92f1060815a7bf","dependencies":["language/src/index.js","model/src/index.js"]},{"id":"designer/src/dialogs.js","bytes":814,"sha256":"b960e10ed44876f8e7c50867b413ecba51f6a57536d0f24b79c8368e03d31a74","dependencies":["viewer/src/dialogs.js"]},{"id":"designer/src/element-preview.js","bytes":2780,"sha256":"a141c80ce15b85e8f0c8e3aef87c89dded8426945798754a90ef61c331f3e9d4","dependencies":["profiles/src/core.js","presentation/src/graph-glyphs.js","presentation/src/node-dimensions.js","presentation/src/native-render.js","presentation/src/model.js","viewer/src/core.js"]},{"id":"designer/src/index.js","bytes":205950,"sha256":"2fc3d437f9f0af7bf0fcf48434c9974312cdc442ffab37ed3e605e7b4642c2dc","dependencies":["designer/src/element-preview.js","viewer/src/drawer.js","viewer/src/side-tabs.js","designer/src/palette-groups.js","designer/src/dialogs.js","viewer/src/choice-field.js","designer/src/live-settings.js","designer/src/appearance.js","designer/src/symbol.js","viewer/src/ui-icons.js","designer/src/properties.js","designer/src/mindmap-actions.js","designer/src/resize-handles.js","designer/src/relation-menu.js","designer/src/mindmap-source.js","designer/src/view-picker.js","designer/src/new-diagram.js","designer/src/view-layout-picker.js","profiles/src/view-surfaces.js","designer/src/presets.js","runtime/src/commands.js","runtime/src/layout-edit.js","runtime/src/profile-loading.js","runtime/src/registry.js","profiles/src/schema-core.js","designer/src/schema-editor.js","runtime/src/runtime.js","runtime/src/save.js","language/src/index.js","viewer/src/ui-commands.js","viewer/src/grid.js","designer/src/clipboard.js","model/src/index.js","profiles/src/core.js","viewer/src/native.js","presentation/src/native.js"]},{"id":"designer/src/live-settings.js","bytes":6769,"sha256":"a0f861b6d09e59a02ec796df5b3705be87da7f32749fd002f395948ca1f496a5","dependencies":["runtime/src/commands.js","execution/src/index.js"]},{"id":"designer/src/mindmap-actions.js","bytes":6971,"sha256":"a0dc91f31169496e0cb6415fc220e75336bd40a9d00819995106ed54b2737144","dependencies":["viewer/src/ui-icons.js","presentation/src/native.js","profiles/src/mindmap.js"]},{"id":"designer/src/mindmap-source.js","bytes":10465,"sha256":"ca13e999101935ae6a33dde89e9760419addcf27587bc8fff4a111ee262901e6","dependencies":["language/src/index.js","model/src/index.js","runtime/src/runtime.js","execution/src/index.js"]},{"id":"designer/src/new-diagram.js","bytes":10661,"sha256":"83ac1ff9bd3c334e0e04aa66e5f236ae0392a41674aab576734dae630ddcc5ad","dependencies":["viewer/src/native.js","viewer/src/ui-icons.js","language/src/index.js","designer/src/dialogs.js","designer/src/view-picker.js","designer/src/view-layout-picker.js","profiles/src/view-surfaces.js","runtime/src/profile-loading.js","runtime/src/registry.js"]},{"id":"designer/src/palette-groups.js","bytes":2920,"sha256":"4877b878ecd8af5278dfed835e57106edaf2ed6fe7a1a0ef970468ae92dc9002","dependencies":["profiles/src/core.js"]},{"id":"designer/src/presets.js","bytes":4839,"sha256":"f25ff9f00a8659a55e65d555dae615db99a01a2022d6bfa286a42a211c1d5d64","dependencies":["defaults/src/index.js"]},{"id":"designer/src/properties.js","bytes":19708,"sha256":"ba0ac1cf85cc7c8a4a1ac9baf9728f0c46eb30e26621182a3f850431b4acf621","dependencies":["viewer/src/native.js","profiles/src/schema-core.js","profiles/src/core.js","presentation/src/native.js","runtime/src/runtime.js","language/src/index.js","designer/src/dialogs.js","viewer/src/choice-field.js","viewer/src/fonts.js","designer/src/live-settings.js","designer/src/schema-editor.js"]},{"id":"designer/src/relation-menu.js","bytes":1736,"sha256":"ca95cfebfd680c84203f8af79a7113a2bc6d17d6beb2372f97512f6d0621d8f2","dependencies":["presentation/src/native.js"]},{"id":"designer/src/resize-handles.js","bytes":8426,"sha256":"665517ca8263107166dbfe7a3079c4555c7e4879283d7112a644d49e70de6959","dependencies":["presentation/src/native.js"]},{"id":"designer/src/schema-editor.js","bytes":13462,"sha256":"740428e867de5130fbfcb9545cd5ed0908b3b5a3c4033bd559005354a1c55351","dependencies":["profiles/src/schema-core.js","designer/src/dialogs.js","viewer/src/choice-field.js","designer/src/live-settings.js"]},{"id":"designer/src/symbol.js","bytes":9676,"sha256":"112c1ad19c21bd1cb118f872b19233dfbe17125741e8020134d96f9a7dd187f8","dependencies":["viewer/src/native.js","presentation/src/native.js","runtime/src/runtime.js","language/src/index.js","designer/src/dialogs.js","viewer/src/choice-field.js","designer/src/live-settings.js"]},{"id":"designer/src/view-layout-picker.js","bytes":14037,"sha256":"1131d84c5c4baca8951ce3fface05792259fd020f20428b208a7bc20c7b60055","dependencies":["profiles/src/view-surfaces.js","designer/src/dialogs.js"]},{"id":"designer/src/view-picker.js","bytes":12646,"sha256":"21d4acb9a059f38e250849fe65a3ca2be76d431ff66f655cb75168088e400273","dependencies":["profiles/src/core.js","language/src/index.js","designer/src/view-previews.js"]},{"id":"designer/src/view-previews.js","bytes":54794,"sha256":"06deb7f06e2a0c0982181e392b7c209e7e3087f9e0b0070b4beab9031fdc7e10","dependencies":[]},{"id":"runtime/src/commands.js","bytes":56649,"sha256":"78a94404f7a3074fd39a6bd983f992ed9ede811f4e458e5b0f618aea05d9b78a","dependencies":["language/src/index.js","model/src/index.js","defaults/src/index.js","runtime/src/layout-edit.js","execution/src/index.js","runtime/src/runtime.js","runtime/src/registry.js","runtime/src/profile-loading.js","profiles/src/core.js","runtime/src/guards.js"]},{"id":"runtime/src/layout-edit.js","bytes":3537,"sha256":"82ba90f78718ad2964b21bfab8b94ed60a9afa0cc60d439bd9d7218e1bdd173b","dependencies":["language/src/index.js","model/src/index.js","defaults/src/index.js","profiles/src/core.js","runtime/src/runtime.js"]},{"id":"runtime/src/save.js","bytes":2687,"sha256":"ddefcdd0cb5f69187a18349daa5c674092d0c56940e24e37a20b7451207c6a9e","dependencies":["language/src/index.js","model/src/index.js","execution/src/index.js","runtime/src/runtime.js"]},{"id":"standalone/src/modular-designer-api.js","bytes":2523,"sha256":"def2b0d21b5b4fd54a4d9cd268e0acf66ac9aa7dbc2a568a05d0f86aabc2225f","dependencies":["designer/src/index.js","runtime/src/commands.js","standalone/src/modular-viewer.js","standalone/src/modular-runtime.js","standalone/src/modular-loading.js","standalone/src/modular-verifier.js","standalone/src/browser-options.js"]}],"hash":"ed696c947036d7ff1650c2d585cbb3f75a5bff490407ae67c073f2baa005f3b2"},{"designer/src/appearance.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.openAppearance = openAppearance;
const native_js_1 = require("viewer/src/native.js");
const fonts_js_1 = require("viewer/src/fonts.js");
const texture_js_1 = require("viewer/src/texture.js");
const choice_field_js_1 = require("viewer/src/choice-field.js");
const live_settings_js_1 = require("designer/src/live-settings.js");
const native_js_2 = require("presentation/src/native.js");
const runtime_js_1 = require("runtime/src/runtime.js");
const index_js_1 = require("language/src/index.js");
const dialogs_js_1 = require("designer/src/dialogs.js");
const presets_js_1 = require("designer/src/presets.js");
const sessionLibraries = new WeakMap();
const unsavedLibraries = new WeakSet();
const valueAt = (values, path, fallback) => values.get(path) ?? fallback;
function download(document, name, text) { const url = URL.createObjectURL(new Blob([text], { type: 'application/json' })), a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
function openAppearance(viewer, panel, commit, initialTab = 'Background') {
    const handle = (0, native_js_1.getViewerHandle)(viewer), document = handle.ownerDocument, snapshot = handle.runtime.snapshot();
    if (!snapshot)
        throw Error('Open a workarea first.');
    const all = (0, native_js_2.records)(snapshot), entry = handle.selectedEntry(), scopes = [];
    const activeViewRef = handle.viewport().activeView;
    const fallbackView = (activeViewRef ? handle.scene()?.views.find(v => (0, native_js_2.refKey)(v.ref) === (0, native_js_2.refKey)(activeViewRef)) : undefined) ?? entry?.view ?? handle.scene()?.views[0];
    const targetView = entry?.view ?? fallbackView;
    if (entry && entry.definition.owner === 'definition' && entry.definition.record.category !== 'relation') {
        const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded;
        if (entry.appearance && decoded && !(0, index_js_1.findNode)(decoded, entry.appearance.ref)?.implicit)
            scopes.push({ ref: entry.appearance.ref, label: 'This appearance', target: 'element', profile: (0, native_js_2.str)(entry.view.record.profile) });
        scopes.push({ ref: entry.definition.ref, label: 'Shared element', target: 'element', profile: (0, native_js_2.str)(entry.view.record.profile) });
    }
    if (targetView) {
        const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded;
        if (entry?.placement && decoded && !(0, index_js_1.findNode)(decoded, entry.placement.ref)?.implicit)
            scopes.push({ ref: entry.placement.ref, label: 'This view placement', target: 'view', profile: (0, native_js_2.str)(targetView.record.profile) });
        scopes.push({ ref: targetView.ref, label: 'View background and text', target: 'view', profile: (0, native_js_2.str)(targetView.record.profile) });
    }
    const workarea = all.find(r => r.owner === 'workarea' && r.file === snapshot.rootFile);
    if (workarea)
        scopes.push({ ref: workarea.ref, label: 'Workarea background', target: 'workarea' });
    if (!scopes.length)
        throw Error('Select an element or view first.');
    let library = sessionLibraries.get(document) ?? [], storage;
    try {
        storage = document.defaultView?.localStorage;
        if (storage && !unsavedLibraries.has(document)) {
            library = (0, presets_js_1.readLocalPresets)(storage);
            sessionLibraries.set(document, library);
        }
    }
    catch { }
    panel('Appearance & presets', body => {
        const label = document.createElement('label');
        label.textContent = 'Apply appearance to';
        const scope = document.createElement('select');
        scope.setAttribute('aria-label', 'Apply appearance to');
        scope.dataset.ddnLiveIgnore = '';
        scopes.forEach((s, i) => scope.add(new Option(s.label, String(i))));
        label.append(scope);
        body.append(label);
        const targetLabel = document.createElement('p');
        targetLabel.className = 'ddn-appearance-target';
        body.append(targetLabel);
        const tabs = document.createElement('div');
        tabs.className = 'ddn-appearance-tabs';
        tabs.setAttribute('role', 'tablist');
        tabs.setAttribute('aria-label', 'Appearance sections');
        body.append(tabs);
        const content = document.createElement('div');
        body.append(content);
        const message = document.createElement('p');
        message.className = 'ddn-appearance-message';
        message.setAttribute('role', 'status');
        body.append(message);
        let changes = {}, values = new Map(), chosen = 0, tab = initialTab, loading = false, ticket = 0;
        const field = (container, name, value, type = 'text') => { const wrap = document.createElement('label'); wrap.textContent = name; const input = document.createElement('input'); input.setAttribute('aria-label', name); input.type = type; input.value = value; wrap.append(input); container.append(wrap); return input; };
        const select = (container, name, choices, value) => (0, choice_field_js_1.choiceField)(container, name, choices, value);
        const effective = (path, fallback) => Object.hasOwn(changes, path) && changes[path] !== undefined ? changes[path] : valueAt(values, path, fallback);
        const changed = (path, value) => { changes[path] = value; (0, live_settings_js_1.notifyLiveSettings)(body); };
        const inherit = (container, path) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = 'Inherit';
            button.setAttribute('aria-label', 'Inherit ' + path);
            button.addEventListener('click', () => {
                changed(path, undefined);
                message.textContent = 'Using the inherited setting.';
                void (0, live_settings_js_1.flushLiveSettings)(body).then(() => {
                    if (body.isConnected)
                        render();
                }).catch(error => { message.textContent = error.message; });
            });
            container.append(button);
        };
        const preview = (container) => {
            const sample = document.createElement('div');
            sample.className = 'ddn-appearance-preview';
            sample.textContent = 'Aa · Design ideas\nReadable text on the selected background';
            sample.style.cssText = 'min-height:88px;padding:12px;border:1px solid var(--ddn-ui-border);border-radius:4px;white-space:pre-line;overflow:hidden';
            container.append(sample);
            return () => {
                const fill = String(effective('background.color', '#ffffff')), texture = (0, texture_js_1.textureBackground)(effective('background.texture', null), fill);
                sample.style.backgroundColor = fill;
                sample.style.backgroundImage = texture?.image ?? 'none';
                sample.style.backgroundSize = texture?.size ?? '';
                sample.style.color = String(effective('text.color', '#243449'));
                sample.style.fontFamily = (0, fonts_js_1.fontFamily)(String(effective('style.font', 'sans')));
                sample.style.fontSize = String(effective('style.font_size', 16)) + 'px';
            };
        };
        const persist = (next) => {
            library = next;
            sessionLibraries.set(document, library);
            try {
                if (!storage)
                    throw Error('Storage unavailable');
                (0, presets_js_1.writeLocalPresets)(storage, library);
                unsavedLibraries.delete(document);
                message.textContent = 'Saved in this browser. Export the pack to share or back it up.';
            }
            catch {
                unsavedLibraries.add(document);
                message.textContent = 'Available for this session only. Export the pack to keep it.';
            }
        };
        const render = () => {
            const current = scopes[chosen];
            targetLabel.textContent = 'Editing: ' + (0, native_js_2.titleOf)(current.target === 'element' ? entry.definition.record : current.target === 'view' ? targetView.record : workarea.record);
            if (current.target === 'workarea' && tab === 'Font')
                tab = 'Background';
            content.replaceChildren();
            for (const b of tabs.querySelectorAll('button')) {
                b.setAttribute('aria-selected', String(b.textContent === tab));
                b.tabIndex = b.textContent === tab ? 0 : -1;
                b.disabled = b.textContent === 'Font' && current.target === 'workarea';
            }
            if (tab === 'Background') {
                const update = preview(content), grid = document.createElement('div');
                grid.className = 'ddn-appearance-grid';
                content.append(grid);
                const color = (0, dialogs_js_1.colourField)(grid, 'Background colour', String(effective('background.color', '#ffffff')));
                color.addEventListener('input', () => { changed('background.color', color.value); update(); });
                inherit(grid, 'background.color');
                const initial = (0, native_js_2.object)(effective('background.texture', null)), kind = select(grid, 'Texture', ['none', 'paper', 'linen', 'grid', 'dots'], (0, native_js_2.str)(initial.kind, 'none'));
                const ink = (0, dialogs_js_1.colourField)(grid, 'Texture colour', (0, native_js_2.str)(initial.color, '#725d43'));
                const opacity = (0, dialogs_js_1.numberField)(grid, 'Texture opacity', Number(initial.opacity ?? .12), { min: 0, max: 1, step: .01 });
                const scale = (0, dialogs_js_1.numberField)(grid, 'Texture scale', Number(initial.scale ?? 32), { min: 4, max: 128, step: 1 });
                for (const input of [opacity, scale]) {
                    input.step = 'any';
                    (0, dialogs_js_1.syncNumberField)(input);
                }
                const seed = (0, dialogs_js_1.numberField)(grid, 'Texture seed', String(initial.seed ?? 1), { min: 0, max: 1000, step: 1 });
                seed.max = '2147483647';
                const changeTexture = () => { const texture = kind.value === 'none' ? null : { kind: kind.value, color: ink.value, opacity: opacity.valueAsNumber, scale: scale.valueAsNumber, seed: seed.valueAsNumber }; changed('background.texture', texture); update(); };
                for (const input of [kind, ink, opacity, scale, seed])
                    input.addEventListener('input', changeTexture);
                inherit(grid, 'background.texture');
                update();
            }
            else if (tab === 'Font') {
                const update = preview(content), grid = document.createElement('div');
                grid.className = 'ddn-appearance-grid';
                content.append(grid);
                const names = [...new Set(['sans', 'serif', 'mono', 'handwriting', ...(0, fonts_js_1.listFonts)(document).map(f => f.family), String(effective('style.font', 'sans'))])];
                const family = select(grid, 'Font family', names, String(effective('style.font', 'sans'))), size = (0, dialogs_js_1.numberField)(grid, 'Font size (pt)', Number(effective('style.font_size', 16)) * .75, { min: 6, max: 48, step: .5 });
                size.step = 'any';
                (0, dialogs_js_1.syncNumberField)(size);
                family.addEventListener('change', () => { changed('style.font', family.value); update(); });
                size.addEventListener('input', () => { changed('style.font_size', size.valueAsNumber * 4 / 3); update(); });
                const ink = (0, dialogs_js_1.colourField)(grid, 'Text colour', String(effective('text.color', '#243449')));
                ink.addEventListener('input', () => { changed('text.color', ink.value); update(); });
                inherit(grid, 'style.font');
                inherit(grid, 'style.font_size');
                inherit(grid, 'text.color');
                const fontFile = field(content, 'Load local font', '', 'file');
                fontFile.accept = '.woff2,.woff,.ttf,.otf';
                fontFile.addEventListener('change', () => {
                    const file = fontFile.files?.[0], scopeTicket = ticket;
                    if (!file)
                        return;
                    void (0, fonts_js_1.loadFontFile)(document, file).then(async (font) => {
                        if (!body.isConnected || ticket !== scopeTicket)
                            return;
                        if (body.ownerDocument !== document)
                            await (0, fonts_js_1.installFontResources)(body.ownerDocument, (0, fonts_js_1.getFontResources)(document));
                        if (!body.isConnected || ticket !== scopeTicket)
                            return;
                        changed('style.font', font.family);
                        render();
                        message.textContent = 'Local font loaded for this page. Export its resources to keep it with your document.';
                    }).catch(error => {
                        if (body.isConnected)
                            message.textContent = String(error.message);
                    });
                });
                const resources = field(content, 'Import font resources', '', 'file');
                resources.accept = '.json,application/json';
                resources.addEventListener('change', () => {
                    const file = resources.files?.[0];
                    if (!file)
                        return;
                    if (file.size > 32 * 1024 * 1024) {
                        message.textContent = 'Font resource packs are limited to 32 MiB.';
                        return;
                    }
                    void file.text().then(async (text) => {
                        const pack = JSON.parse(text);
                        if (pack?.format !== 'ddn-font-resources-1' || !Array.isArray(pack.resources))
                            throw Error('Expected a DDN font resource pack.');
                        await (0, fonts_js_1.installFontResources)(document, pack.resources);
                        if (body.isConnected) {
                            if (body.ownerDocument !== document)
                                await (0, fonts_js_1.installFontResources)(body.ownerDocument, pack.resources);
                            render();
                            message.textContent = 'Local font resources loaded.';
                        }
                    }).catch(error => {
                        if (body.isConnected)
                            message.textContent = error.message;
                    });
                });
                const exportFonts = document.createElement('button');
                exportFonts.type = 'button';
                exportFonts.textContent = 'Export font resources';
                exportFonts.addEventListener('click', () => download(document, 'ddn-font-resources.json', JSON.stringify({ format: 'ddn-font-resources-1', resources: (0, fonts_js_1.getFontResources)(document) }, null, 2)));
                content.append(exportFonts);
                const note = document.createElement('p');
                note.textContent = 'Bundled fonts work offline. Custom font files stay local; text uses a fallback when their resources are unavailable.';
                content.append(note);
                update();
            }
            else if (tab === 'Style') {
                const update = preview(content), grid = document.createElement('div');
                grid.className = 'ddn-appearance-grid';
                content.append(grid);
                const look = select(grid, 'Drawing style', ['classic', 'handdrawn', 'clean', 'neo'], String(effective('style.look', 'classic')));
                look.addEventListener('change', () => { changed('style.look', look.value); update(); });
                inherit(grid, 'style.look');
                const theme = select(grid, 'Colour theme', ['default', 'neutral', 'dark', 'night', 'blueprint', 'warm'], String(effective('style.theme', 'default')));
                theme.addEventListener('change', () => { changed('style.theme', theme.value); update(); });
                inherit(grid, 'style.theme');
                const roughness = (0, dialogs_js_1.numberField)(grid, 'Hand-drawn roughness', Number(effective('style.roughness', 1)), { min: 0, max: 4, step: .1 });
                roughness.step = 'any';
                (0, dialogs_js_1.syncNumberField)(roughness);
                roughness.addEventListener('input', () => { changed('style.roughness', roughness.valueAsNumber); });
                inherit(grid, 'style.roughness');
                const note = document.createElement('p');
                note.textContent = 'Setting a drawing style or theme on the workarea cascades to all views, documents and elements unless overridden.';
                content.append(note);
                update();
            }
            else if (tab === 'Border') {
                const update = preview(content), grid = document.createElement('div');
                grid.className = 'ddn-appearance-grid';
                content.append(grid);
                const style = select(grid, 'Border style', ['solid', 'dashed', 'dotted', 'none'], String(effective('border.style', 'solid')));
                style.addEventListener('change', () => { changed('border.style', style.value); });
                inherit(grid, 'border.style');
                const width = (0, dialogs_js_1.numberField)(grid, 'Border width', Number(effective('border.width', 1)), { min: 0, max: 16, step: .5 });
                width.step = 'any';
                (0, dialogs_js_1.syncNumberField)(width);
                width.addEventListener('input', () => { changed('border.width', width.valueAsNumber); });
                inherit(grid, 'border.width');
                const borderColor = (0, dialogs_js_1.colourField)(grid, 'Border colour', String(effective('border.color', '#94a3b8')));
                borderColor.addEventListener('input', () => { changed('border.color', borderColor.value); });
                inherit(grid, 'border.color');
                update();
            }
            else {
                const choices = [...(0, presets_js_1.standardPresets)(current.target), ...library.filter(p => p.target === current.target && (!p.profile || p.profile === current.profile))];
                const selectedPreset = choices.find(p => Object.entries(p.properties).every(([path, value]) => JSON.stringify(effective(path, undefined)) === JSON.stringify(value)))?.id ?? '';
                const pick = (0, choice_field_js_1.choiceField)(content, 'Appearance preset', choices.map(p => ({ value: p.id, label: p.name, description: (p.id.startsWith('standard-') ? 'Standard' : p.scope === 'company' ? 'Company' : 'User') + ' · ' + p.name, preview: (document) => {
                        const sample = document.createElement('span');
                        sample.className = 'ddn-choice-surface';
                        sample.textContent = 'Aa · Ideas';
                        const fill = String(p.properties['background.color'] ?? '#ffffff'), texture = (0, texture_js_1.textureBackground)(p.properties['background.texture'], fill);
                        sample.style.backgroundColor = fill;
                        sample.style.color = String(p.properties['text.color'] ?? '#243449');
                        sample.style.fontFamily = (0, fonts_js_1.fontFamily)(String(p.properties['style.font'] ?? 'sans'));
                        if (texture) {
                            sample.style.backgroundImage = texture.image;
                            sample.style.backgroundSize = texture.size;
                        }
                        return sample;
                    } })), selectedPreset);
                pick.addEventListener('change', () => {
                    const preset = choices.find(p => p.id === pick.value);
                    if (preset) {
                        changes = { ...changes, ...structuredClone(preset.properties) };
                        (0, live_settings_js_1.notifyLiveSettings)(body);
                        message.textContent = 'Preset applied to the selected scope.';
                    }
                });
                const name = field(content, 'New user preset name', 'My appearance'), save = document.createElement('button');
                name.dataset.ddnLiveIgnore = '';
                save.type = 'button';
                save.textContent = 'Save user preset';
                save.addEventListener('click', () => {
                    try {
                        const properties = {};
                        for (const path of presets_js_1.PRESET_PATHS) {
                            const value = effective(path, undefined);
                            if (value !== undefined)
                                properties[path] = value;
                        }
                        const preset = { id: 'user-' + (document.defaultView?.crypto.randomUUID?.() ?? Date.now().toString(36)), name: name.value, scope: 'user', target: current.target, ...(current.profile ? { profile: current.profile } : {}), properties };
                        const next = (0, presets_js_1.mergePresetPacks)(library, (0, presets_js_1.parsePresetPack)((0, presets_js_1.serializePresetPack)([preset])).presets);
                        persist(next);
                        render();
                    }
                    catch (error) {
                        message.textContent = error.message;
                    }
                });
                content.append(save);
                const remove = document.createElement('button');
                remove.type = 'button';
                remove.textContent = 'Delete user preset';
                const updateRemove = () => { const selected = library.find(p => p.id === pick.value); remove.disabled = !selected || selected.scope !== 'user'; };
                pick.addEventListener('change', updateRemove);
                updateRemove();
                remove.addEventListener('click', () => {
                    const p = library.find(p => p.id === pick.value);
                    if (p?.scope === 'user') {
                        persist(library.filter(item => item.id !== p.id));
                        render();
                    }
                });
                content.append(remove);
                const input = field(content, 'Import user/company preset pack', '', 'file');
                input.accept = '.json,application/json';
                input.addEventListener('change', () => {
                    const file = input.files?.[0];
                    if (!file)
                        return;
                    if (file.size > 262144) {
                        message.textContent = 'Preset files are limited to 256 KiB.';
                        return;
                    }
                    void file.text().then(text => { persist((0, presets_js_1.mergePresetPacks)(library, (0, presets_js_1.parsePresetPack)(text).presets)); render(); }).catch(error => { message.textContent = error.message; });
                });
                const exportButton = document.createElement('button');
                exportButton.type = 'button';
                exportButton.textContent = 'Export preset pack';
                exportButton.addEventListener('click', () => download(document, 'ddn-appearance-presets.json', (0, presets_js_1.serializePresetPack)(library)));
                content.append(exportButton);
                const note = document.createElement('p');
                note.textContent = 'Company packs are imported, read-only library entries here. Applying a preset copies its settings into the chosen scope; company identity does not grant approval or enforce policy.';
                content.append(note);
            }
        };
        for (const name of ['Background', 'Font', 'Style', 'Border', 'Presets']) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = name;
            button.setAttribute('role', 'tab');
            button.addEventListener('click', () => {
                tabs.inert = true;
                content.inert = true;
                void (0, live_settings_js_1.flushLiveSettings)(body).then(() => {
                    if (body.isConnected) {
                        tab = name;
                        render();
                    }
                }).catch(error => { message.textContent = error.message; }).finally(() => { tabs.inert = false; content.inert = false; });
            });
            tabs.append(button);
        }
        tabs.addEventListener('keydown', event => {
            if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key))
                return;
            const buttons = [...tabs.querySelectorAll('button:not(:disabled)')], index = buttons.findIndex(b => b === body.ownerDocument.activeElement);
            if (index < 0)
                return;
            event.preventDefault();
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length;
            buttons[next].click();
            buttons[next].focus();
        });
        const readValues = async () => {
            const token = ticket, inspection = await viewer.inspect(scopes[chosen].ref);
            if (token !== ticket || !body.isConnected)
                return;
            values = new Map(inspection.properties.map(p => [p.path, p.effective]));
            for (const parent of ['background.texture', 'shadow']) {
                const object = {};
                for (const [path, value] of values)
                    if (path.startsWith(parent + '.'))
                        object[path.slice(parent.length + 1)] = value;
                if (Object.keys(object).length)
                    values.set(parent, object);
            }
        };
        const refresh = async () => {
            ++ticket;
            loading = true;
            changes = {};
            content.textContent = 'Loading appearance…';
            await readValues();
            loading = false;
            if (body.isConnected)
                render();
        };
        scope.addEventListener('change', event => {
            event.stopPropagation();
            const next = Number(scope.value);
            scope.value = String(chosen);
            scope.disabled = true;
            content.inert = true;
            void (0, live_settings_js_1.flushLiveSettings)(body).then(async () => {
                if (!body.isConnected)
                    return;
                chosen = next;
                scope.value = String(next);
                await refresh();
            }).catch(e => { message.textContent = e.message; }).finally(() => { scope.disabled = false; content.inert = false; });
        });
        void refresh().catch(e => { message.textContent = e.message; });
        return async () => {
            if (loading)
                throw Error('Wait for settings to load.');
            for (const input of content.querySelectorAll('input[type=number]'))
                if (!input.checkValidity() || !Number.isFinite(input.valueAsNumber))
                    throw Error('Enter a valid value for ' + input.parentElement?.firstChild?.textContent);
            if (Object.keys(changes).length) {
                const pending = { ...changes }, target = scopes[chosen].ref;
                await commit(target, pending);
                for (const [path, value] of Object.entries(pending))
                    if (Object.hasOwn(changes, path) && JSON.stringify(changes[path]) === JSON.stringify(value))
                        delete changes[path];
                await readValues();
            }
        };
    });
}

},
"designer/src/clipboard.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.quoteText = void 0;
exports.clipRecord = clipRecord;
exports.clipboardText = clipboardText;
exports.parseClipboardText = parseClipboardText;
exports.uniqueName = uniqueName;
exports.pasteRecords = pasteRecords;
exports.parseCsv = parseCsv;
const index_js_1 = require("language/src/index.js");
Object.defineProperty(exports, "quoteText", { enumerable: true, get: function () { return index_js_1.quoteText; } });
const index_js_2 = require("model/src/index.js");
const NOT_COPIED = ['id', 'category', 'acceptance', 'acceptance_history', 'design'];
function clipRecord(record) {
    const copy = {};
    for (const [key, value] of Object.entries(record))
        if (!NOT_COPIED.includes(key) && value !== undefined)
            copy[key] = value;
    return copy;
}
function clipboardText(items) {
    return items.map(item => (0, index_js_1.encodeDefinition)({ ...item.record, ...(item.position ? { position: { x: item.position.x, y: item.position.y } } : {}) }).replace(/\n?$/, '\n')).join('');
}
function parseClipboardText(text) {
    const body = text.replace(/\r\n/g, '\n').replace(/^\n+|\n+$/g, '');
    if (!/^\s*element\b/.test(body))
        return [];
    const minimum = Math.min(...body.split('\n').filter(line => line.trim()).map(line => line.length - line.trimStart().length));
    const wrapped = 'view clipboard as "ddn@1"\n' + body.split('\n').map(line => '    ' + line.slice(minimum)).join('\n') + '\n';
    const decoded = (0, index_js_1.decodeSources)({ entry: 'clipboard.ddn', files: [{ id: 'clipboard.ddn', text: wrapped, revision: '0', encoding: 'utf-8', writable: true }] });
    if (decoded.diagnostics.some(d => d.severity === 'error'))
        return [];
    const all = (0, index_js_2.listRecords)(decoded.normalized);
    return all.filter(entry => entry.kind === 'definition' && entry.record.category !== 'relation' && !Array.isArray(entry.record.endpoints)).map(entry => {
        const appearance = all.find(other => other.kind === 'appearance' && other.record.target?.id === entry.ref.id);
        const position = appearance?.record.position;
        return { record: clipRecord(entry.record), ...(position && typeof position.x === 'number' && typeof position.y === 'number' ? { position: { x: position.x, y: position.y } } : {}) };
    });
}
function uniqueName(name, taken) {
    if (!taken.has(name))
        return name;
    const identifier = !/\s/.test(name) && /[._:]/.test(name), separator = identifier ? '_' : ' ';
    const base = name.replace(identifier ? /_\d+$/ : /\s+\d+$/, '');
    for (let index = 2;; index++)
        if (!taken.has(base + separator + index))
            return base + separator + index;
}
function pasteRecords(items, taken, offset) {
    return clipboardText(items.map(item => {
        const record = { ...item.record };
        if (typeof record.name === 'string') {
            record.name = uniqueName(record.name, taken);
            taken.add(record.name);
        }
        return { record, ...(item.position ? { position: { x: Math.max(0, item.position.x + offset.x), y: Math.max(0, item.position.y + offset.y) } } : {}) };
    }));
}
function parseCsv(text) {
    const rows = [];
    let row = [], field = '', quoted = false;
    for (let index = 0; index < text.length; index++) {
        const character = text[index];
        if (quoted) {
            if (character === '"' && text[index + 1] === '"') {
                field += '"';
                index++;
            }
            else if (character === '"')
                quoted = false;
            else
                field += character;
        }
        else if (character === '"')
            quoted = true;
        else if (character === ',') {
            row.push(field);
            field = '';
        }
        else if (character === '\n' || character === '\r') {
            if (character === '\r' && text[index + 1] === '\n')
                index++;
            row.push(field);
            field = '';
            if (row.some(cell => cell !== ''))
                rows.push(row);
            row = [];
        }
        else
            field += character;
    }
    row.push(field);
    if (row.some(cell => cell !== ''))
        rows.push(row);
    const [header = [], ...body] = rows;
    if (!header.length)
        throw Error('The CSV file has no header row.');
    const used = new Set();
    const columns = header.map((label, index) => {
        let id = label.trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'column_' + (index + 1);
        if (/^\d/.test(id))
            id = 'c_' + id;
        while (used.has(id))
            id += '_' + (index + 1);
        used.add(id);
        const numeric = body.length > 0 && body.every(cells => { const value = (cells[index] ?? '').trim(); return value === '' || Number.isFinite(Number(value)); });
        return { id, label: label.trim() || id, type: numeric ? 'number' : 'text' };
    });
    return { columns, rows: body.map(cells => columns.map((column, index) => { const value = (cells[index] ?? '').trim(); return value === '' ? null : column.type === 'number' ? Number(value) : value; })) };
}

},
"designer/src/dialogs.js":function(module,exports,require){
"use strict";
var __createBinding = (this && this.__createBinding) || (Object.create ? (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    var desc = Object.getOwnPropertyDescriptor(m, k);
    if (!desc || ("get" in desc ? !m.__esModule : desc.writable || desc.configurable)) {
      desc = { enumerable: true, get: function() { return m[k]; } };
    }
    Object.defineProperty(o, k2, desc);
}) : (function(o, m, k, k2) {
    if (k2 === undefined) k2 = k;
    o[k2] = m[k];
}));
var __exportStar = (this && this.__exportStar) || function(m, exports) {
    for (var p in m) if (p !== "default" && !Object.prototype.hasOwnProperty.call(exports, p)) __createBinding(exports, m, p);
};
Object.defineProperty(exports, "__esModule", { value: true });
__exportStar(require("viewer/src/dialogs.js"), exports);

},
"designer/src/element-preview.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.elementPreview = elementPreview;
const core_js_1 = require("profiles/src/core.js");
const graph_glyphs_js_1 = require("presentation/src/graph-glyphs.js");
const node_dimensions_js_1 = require("presentation/src/node-dimensions.js");
const native_render_js_1 = require("presentation/src/native-render.js");
const model_js_1 = require("presentation/src/model.js");
const core_js_2 = require("viewer/src/core.js");
function elementPreview(document, role, profile) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.dataset.role = role;
    svg.dataset.profile = profile;
    const render = (0, core_js_1.roleDescriptor)(role)?.render ?? {}, fill = (0, model_js_1.str)(render.fill, '#f8fafc'), stroke = (0, model_js_1.str)(render.colour, '#475569');
    const native = ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile);
    const centred = ['external_actor', 'uml.actor', 'uml.usecase', 'dfd.process', 'dfd.store'].includes(role) || role.startsWith('flow.') || role.startsWith('state.');
    const textOnly = role === 'ui.label';
    const bounds = textOnly ? { x: 0, y: 0, width: 40, height: 20 } : native ? { x: 0, y: 0, width: 180, height: 100 } : (0, node_dimensions_js_1.graphNodeDimensions)(role, profile, { x: 0, y: 0, width: 180, height: 90 });
    const primitives = native
        ? [...(0, native_render_js_1.nativeContour)(role, {}, bounds, fill, stroke, 1.5, 'classic', 1, 42), ...(centred ? [] : (0, native_render_js_1.nativeIcon)((0, model_js_1.str)(render.glyph, role), { x: 14, y: 16, width: 32, height: 32 }, stroke))]
        : (0, graph_glyphs_js_1.nodeGlyph)(role, {}, bounds, { profile, title: textOnly ? 'Text' : '', fill, stroke, width: 1.5 });
    const padding = 10;
    svg.setAttribute('viewBox', `${bounds.x - padding} ${bounds.y - padding} ${bounds.width + padding * 2} ${bounds.height + padding * 2}`);
    const sample = primitives.filter(p => p.kind !== 'text' || p.runs.some(run => run.text.trim())).map(p => textOnly && p.kind === 'text'
        ? { ...p, runs: p.runs.map(run => ({ ...run, style: { ...run.style, fill: 'currentColor' } })) } : p);
    svg.append((0, core_js_2.renderPreviewPrimitives)(document, sample, bounds));
    for (const shape of svg.querySelectorAll('path,rect,ellipse')) {
        shape.setAttribute('vector-effect', 'non-scaling-stroke');
        const weight = Number(shape.getAttribute('stroke-width') ?? 1.5);
        if (shape.getAttribute('stroke') !== 'none' && weight > 0)
            shape.setAttribute('stroke-width', String(Math.max(.75, weight * 1.25 / 1.5)));
    }
    return svg;
}

},
"designer/src/index.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.serializePresetPack = exports.parsePresetPack = exports.colourField = exports.createStandardDialog = void 0;
exports.createDesigner = createDesigner;
const element_preview_js_1 = require("designer/src/element-preview.js");
const drawer_js_1 = require("viewer/src/drawer.js");
const side_tabs_js_1 = require("viewer/src/side-tabs.js");
const palette_groups_js_1 = require("designer/src/palette-groups.js");
const dialogs_js_1 = require("designer/src/dialogs.js");
const choice_field_js_1 = require("viewer/src/choice-field.js");
const live_settings_js_1 = require("designer/src/live-settings.js");
const appearance_js_1 = require("designer/src/appearance.js");
const symbol_js_1 = require("designer/src/symbol.js");
const ui_icons_js_1 = require("viewer/src/ui-icons.js");
const properties_js_1 = require("designer/src/properties.js");
const live_settings_js_2 = require("designer/src/live-settings.js");
const mindmap_actions_js_1 = require("designer/src/mindmap-actions.js");
const resize_handles_js_1 = require("designer/src/resize-handles.js");
const relation_menu_js_1 = require("designer/src/relation-menu.js");
const mindmap_source_js_1 = require("designer/src/mindmap-source.js");
const view_picker_js_1 = require("designer/src/view-picker.js");
const new_diagram_js_1 = require("designer/src/new-diagram.js");
const view_layout_picker_js_1 = require("designer/src/view-layout-picker.js");
const view_surfaces_js_1 = require("profiles/src/view-surfaces.js");
var dialogs_js_2 = require("designer/src/dialogs.js");
Object.defineProperty(exports, "createStandardDialog", { enumerable: true, get: function () { return dialogs_js_2.createStandardDialog; } });
Object.defineProperty(exports, "colourField", { enumerable: true, get: function () { return dialogs_js_2.colourField; } });
var presets_js_1 = require("designer/src/presets.js");
Object.defineProperty(exports, "parsePresetPack", { enumerable: true, get: function () { return presets_js_1.parsePresetPack; } });
Object.defineProperty(exports, "serializePresetPack", { enumerable: true, get: function () { return presets_js_1.serializePresetPack; } });
const commands_js_1 = require("runtime/src/commands.js");
const layout_edit_js_1 = require("runtime/src/layout-edit.js");
const profile_loading_js_1 = require("runtime/src/profile-loading.js");
const registry_js_1 = require("runtime/src/registry.js");
const schema_core_js_1 = require("profiles/src/schema-core.js");
const schema_editor_js_1 = require("designer/src/schema-editor.js");
const runtime_js_1 = require("runtime/src/runtime.js");
const save_js_1 = require("runtime/src/save.js");
const index_js_1 = require("language/src/index.js");
const ui_commands_js_1 = require("viewer/src/ui-commands.js");
const grid_js_1 = require("viewer/src/grid.js");
const clipboard_js_1 = require("designer/src/clipboard.js");
let clipboard = [];
let clipboardWritten = '';
const DOCUMENT_OUTPUTS = ['pdf', 'html', 'dashboard', 'docx', 'odt', 'csv', 'json', 'markdown'];
const index_js_2 = require("model/src/index.js");
const core_js_1 = require("profiles/src/core.js");
const native_js_1 = require("viewer/src/native.js");
const native_js_2 = require("presentation/src/native.js");
const active = new WeakSet();
function jsonValue(value) { return value; }
function createDesigner(viewer, options) {
    if (active.has(viewer))
        throw new Error('This viewer already has a designer');
    const handle = (0, native_js_1.getViewerHandle)(viewer), document = handle.ownerDocument;
    const standalone = () => {
        const snapshot = handle.runtime.snapshot();
        return !!snapshot && (0, native_js_2.records)(snapshot).some(record => record.owner === 'workarea' && record.file === snapshot.rootFile && record.record.mode === 'standalone');
    };
    const commands = (0, commands_js_1.createCommandService)(handle.runtime, options.authority, options.history);
    active.add(viewer);
    const baseline = new Map(handle.runtime.sources()?.files.map(file => [file.id, file.text]) ?? []);
    let documentOpenGeneration = 0;
    let disposed = false, connectFrom, menu;
    const cleanups = [];
    const panels = new Set();
    const panelClosers = new Map();
    const toolbar = document.createElement('div');
    toolbar.className = 'ddn-viewer-toolbar ddn-designer-toolbar';
    toolbar.setAttribute('role', 'toolbar');
    toolbar.setAttribute('aria-label', 'Diagram editing');
    toolbar.dataset.ddnDesigner = '';
    handle.container.setAttribute('data-ddn-editing', '');
    const css = document.createElement('style');
    css.textContent = `.ddn-designer-toolbar{grid-row:2;row-gap:2px}.ddn-viewer .ddn-designer-toolbar .ddn-toolbar-group[hidden],.ddn-viewer .ddn-designer-toolbar button[hidden]{display:none}.ddn-viewer .ddn-designer-toolbar button[data-primary]{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:transparent;font-weight:650}.ddn-viewer .ddn-designer-toolbar button[data-primary]:hover{filter:brightness(1.08);color:var(--ddn-ui-accent-text)}.ddn-viewer .ddn-designer-toolbar button[data-primary][aria-pressed=true]{box-shadow:inset 0 0 0 2px color-mix(in srgb,var(--ddn-ui-accent-text) 55%,transparent)}.ddn-designer-toolbar button[aria-pressed=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 18%,var(--ddn-ui-surface));color:var(--ddn-ui-accent);border-color:color-mix(in srgb,var(--ddn-ui-accent) 50%,transparent)}.ddn-designer-toolbar .ddn-selection-name{font-size:11px;color:var(--ddn-ui-muted);padding:0 6px;max-width:220px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;line-height:32px}.ddn-designer-toolbar .ddn-toolbar-group[data-empty=true]{flex-basis:100%;border-right:0}.ddn-designer-toolbar .ddn-toolbar-group[data-empty=true] button{display:none}.ddn-designer-toolbar .ddn-toolbar-group[data-empty=true] .ddn-selection-name{max-width:none}.ddn-designer-toolbar .ddn-toolbar-group[data-empty=false]{flex-basis:100%;border-right:0}.ddn-designer-toolbar .ddn-toolbar-group[data-empty=false] .ddn-selection-name{color:var(--ddn-ui-text);font-weight:600}.ddn-viewer .ddn-designer-toolbar button[data-in-menu]{display:none}.ddn-designer-toolbar button:disabled{opacity:.4}
.ddn-viewer[data-ddn-dock-left] .ddn-viewer-outline{display:none}.ddn-viewer[data-ddn-dock-left]{grid-template-columns:320px minmax(0,1fr)}.ddn-viewer[data-ddn-dock-left] .ddn-designer-dock-left{grid-column:1;grid-row:3}.ddn-viewer[data-ddn-dock-right]{grid-template-columns:250px minmax(0,1fr) 320px}.ddn-viewer[data-ddn-dock-left][data-ddn-dock-right]{grid-template-columns:320px minmax(0,1fr) 320px}.ddn-viewer[data-ddn-dock-right] .ddn-designer-dock-right{grid-column:3;grid-row:3}.ddn-viewer[data-ddn-dock-right] .ddn-viewer-toolbar,.ddn-viewer[data-ddn-dock-right] .ddn-viewer-status{grid-column:1/-1}
.ddn-designer-dock{min-height:0;overflow:auto;background:color-mix(in srgb,var(--ddn-ui-surface) 70%,var(--ddn-ui-bg));font-size:12px;scrollbar-width:thin;scrollbar-color:var(--ddn-ui-border) transparent}.ddn-designer-dock-left{border-right:1px solid var(--ddn-ui-border)}.ddn-designer-dock-right{border-left:1px solid var(--ddn-ui-border)}.ddn-dock-head{position:sticky;top:0;z-index:2;display:flex;align-items:center;gap:6px;padding:8px 10px;background:var(--ddn-ui-surface);border-bottom:1px solid var(--ddn-ui-border);font-size:11px;font-weight:650;letter-spacing:.08em;text-transform:uppercase;color:var(--ddn-ui-muted)}.ddn-dock-head button{margin-left:auto;min-height:24px;padding:2px 6px;font-size:14px;line-height:1}.ddn-dock-body{padding:8px 10px}.ddn-dock-body label{display:block;margin:6px 0 8px;font-size:11px;color:var(--ddn-ui-muted)}.ddn-dock-body label>input:not([type=checkbox]),.ddn-dock-body label>select,.ddn-dock-body label>textarea{display:block;width:100%;margin-top:3px;min-height:30px;padding:4px 7px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-input);color:var(--ddn-ui-text);font:inherit}.ddn-dock-body textarea{min-height:56px;resize:vertical}.ddn-dock-body input[type=color]{width:100%;height:30px;padding:2px}.ddn-dock-body .ddn-dock-row{display:grid;grid-template-columns:1fr 1fr;gap:8px}.ddn-dock-row>.ddn-ui-number-field{grid-column:1/-1}.ddn-dock-body .ddn-dock-help{font-size:11px;color:var(--ddn-ui-muted);margin:0 0 8px;line-height:1.45}.ddn-dock-body .ddn-dock-actions{display:grid;gap:4px;margin-top:8px}.ddn-dock-body .ddn-dock-actions button{justify-content:flex-start;font-size:12px;padding:6px 8px;min-height:30px}.ddn-dock-body .ddn-dock-actions button[data-danger]{color:var(--ddn-ui-danger)}.ddn-dock-body .ddn-dock-kind{display:flex;align-items:center;gap:8px;padding:6px 0 2px;font-size:12px}.ddn-dock-body .ddn-dock-kind .ddn-dock-swatch{width:14px;height:14px;border-radius:4px;border:1px solid var(--ddn-ui-border);flex:none}.ddn-dock-body .ddn-dock-kind small{color:var(--ddn-ui-muted);font-size:10px}
.ddn-palette-search{display:flex;align-items:center;gap:6px;margin:0 0 8px;padding:0 8px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-input)}.ddn-palette-search[hidden]{display:none}.ddn-palette-search input{flex:1;min-width:0;border:0;background:transparent;color:var(--ddn-ui-text);padding:7px 0;font-size:12px;outline-offset:1px}.ddn-palette-group{margin:6px 0 2px;font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--ddn-ui-muted)}.ddn-palette-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:5px;margin-bottom:6px}.ddn-viewer .ddn-palette-grid button{min-width:0;display:grid;grid-template-rows:auto auto;justify-items:center;gap:3px;padding:7px 4px 6px;min-height:0;border:1px solid var(--ddn-ui-border);border-radius:9px;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);text-align:center;font-size:11px;line-height:1.25;cursor:grab}.ddn-viewer .ddn-palette-grid button:hover,.ddn-viewer .ddn-palette-grid button:focus-visible{border-color:var(--ddn-ui-accent);color:var(--ddn-ui-text)}.ddn-viewer .ddn-palette-grid button[aria-pressed=true]{border-color:var(--ddn-ui-accent);box-shadow:inset 0 0 0 1px var(--ddn-ui-accent)}.ddn-palette-grid svg{width:54px;height:34px;display:block}.ddn-palette-grid .ddn-palette-id{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:9.5px;color:var(--ddn-ui-muted);font-family:ui-monospace,monospace}.ddn-palette-empty{font-size:11px;color:var(--ddn-ui-muted);padding:6px 2px}
.ddn-port{fill:#ffffff;stroke:#2563eb;stroke-width:1.5;cursor:crosshair}.ddn-port:hover{fill:#2563eb}.ddn-connect-line{fill:none;stroke:#2563eb;stroke-width:2;stroke-dasharray:6 4;pointer-events:none}.ddn-connect-target{filter:drop-shadow(0 0 4px #2563eb)}.ddn-placing .ddn-viewer-stage>svg{cursor:crosshair}
.ddn-inline-rename{position:absolute;z-index:30;min-width:120px;padding:4px 8px;border:2px solid var(--ddn-ui-accent);border-radius:8px;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);font:600 14px Inter,system-ui,sans-serif;box-shadow:0 8px 24px color-mix(in srgb,var(--ddn-ui-shadow) 60%,transparent)}
.ddn-verb-list{display:grid;gap:4px;margin:4px 0 8px}.ddn-viewer .ddn-verb-list button,.ddn-ui-dialog .ddn-verb-list button{justify-content:flex-start;text-align:left;font-size:12px;padding:6px 9px}.ddn-verb-list button b{font-weight:650;color:var(--ddn-ui-accent)}.ddn-verb-list small{margin-left:auto;color:var(--ddn-ui-muted);font:10px ui-monospace,monospace}.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-outline,.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-stage{grid-row:3}.ddn-viewer:has(.ddn-designer-toolbar){grid-template-rows:auto auto minmax(200px,1fr) auto}.ddn-appearance-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px;align-items:end}.ddn-appearance-grid>label{min-width:0}.ddn-appearance-grid>.ddn-ui-number-field{grid-column:1/-1}.ddn-appearance-tabs{display:flex;flex-wrap:wrap;gap:4px;margin:10px 0}.ddn-appearance-tabs [aria-selected=true]{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text)}.ddn-appearance-message{font-size:12px;color:var(--ddn-ui-muted)}.ddn-designer-menu{position:absolute;z-index:25;display:grid;gap:3px;padding:6px;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);border:1px solid var(--ddn-ui-border);border-radius:6px;box-shadow:0 6px 20px #14243633}.ddn-designer-menu button{text-align:left}.ddn-designer-preview{fill:#3b82f622;stroke:#2563eb;stroke-width:2;stroke-dasharray:4 3;pointer-events:none}@media(max-width:480px){.ddn-appearance-grid{grid-template-columns:minmax(0,1fr)}}@media(max-width:760px){.ddn-viewer:has(.ddn-designer-toolbar){grid-template-rows:auto auto auto minmax(340px,1fr) auto}.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-outline{grid-row:3}.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-stage{grid-row:4}.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-status{grid-row:5}}`;
    css.textContent += `@media(max-width:760px){.ddn-viewer[data-ddn-dock-left],.ddn-viewer[data-ddn-dock-right],.ddn-viewer[data-ddn-dock-left][data-ddn-dock-right]{grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto auto minmax(340px,1fr) auto auto}.ddn-viewer[data-ddn-dock-left] .ddn-designer-dock-left{grid-column:1;grid-row:3;min-height:180px;max-height:240px}.ddn-viewer[data-ddn-dock-right] .ddn-designer-dock-right{grid-column:1;grid-row:5;min-height:200px;max-height:300px}.ddn-viewer[data-ddn-dock-left] .ddn-viewer-stage,.ddn-viewer[data-ddn-dock-right] .ddn-viewer-stage{grid-column:1;grid-row:4}.ddn-viewer[data-ddn-dock-left] .ddn-viewer-status,.ddn-viewer[data-ddn-dock-right] .ddn-viewer-status{grid-row:6}.ddn-designer-toolbar .ddn-toolbar-group{flex-wrap:wrap}}.ddn-designer-menu{max-height:calc(100% - 8px);overflow:auto}.ddn-designer-toolbar .ddn-toolbar-group{border-right:1px solid var(--ddn-ui-border);padding-right:8px}`;
    css.textContent += `@media(min-width:761px){.ddn-designer-dock-left{display:flex;flex-direction:column;overflow:hidden}.ddn-designer-dock-left>.ddn-dock-head{flex:none}.ddn-designer-dock-left>.ddn-dock-body{display:flex;flex-direction:column;flex:1;min-height:0}.ddn-designer-dock-left .ddn-panel-sections{flex:1;min-height:0;overflow:hidden}.ddn-designer-dock-left .ddn-side-tabs{position:static;max-height:100%;overflow:auto;scrollbar-width:thin}.ddn-designer-dock-left .ddn-panel-section{overflow:auto;min-height:0}.ddn-designer-dock-left .ddn-palette-search{flex:none}}`;
    handle.container.append(css);
    if (options.controls !== 'host')
        handle.container.insertBefore(toolbar, handle.container.children[2] ?? null);
    function on(target, event, listener) {
        const callback = listener;
        target.addEventListener(event, callback);
        cleanups.push(() => target.removeEventListener(event, callback));
    }
    const selected = () => handle.selectedEntry();
    const writable = (ref) => handle.runtime.sources()?.files.some(file => file.id === ref.file && file.writable) === true;
    const explicitEditable = (ref) => {
        const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded, node = decoded && (0, index_js_1.findNode)(decoded, ref);
        return !!node && !node.implicit && !node.generated && writable(ref);
    };
    const revision = () => JSON.stringify(handle.runtime.snapshot()?.revision);
    function requireCurrent(expected) {
        if (disposed || revision() !== expected)
            throw Error('The diagram changed while you were editing. Reopen the editor and try again.');
    }
    const semanticBounds = (entry) => entry.item.hitTargets.find(hit => (0, native_js_2.refKey)(hit.target) === (0, native_js_2.refKey)(entry.definition.ref))?.bounds ?? entry.item.hitTargets[0]?.bounds ?? entry.item.bounds;
    const logicalPoint = (entry, point) => {
        const m = entry?.surfaceTransform;
        if (!m)
            return point;
        const determinant = m[0] * m[3] - m[1] * m[2];
        return { x: (m[3] * (point.x - m[4]) - m[2] * (point.y - m[5])) / determinant,
            y: (-m[1] * (point.x - m[4]) + m[0] * (point.y - m[5])) / determinant };
    };
    const surfaceScale = (entry) => entry.definition.owner === 'view' ? 1 : entry.surfaceTransform?.[0] ?? 1;
    const requireSelection = () => {
        const entry = selected();
        if (!entry)
            throw new Error('Select an element first.');
        return entry;
    };
    const notifyError = (error) => handle.announce(error instanceof Error ? error.message : String(error));
    async function apply(intent) {
        const group = (0, commands_js_1.currentCommandHistoryGroup)(commands);
        if (disposed)
            throw new Error('Designer is destroyed');
        const prepared = await commands.prepare(intent, group ? { cancel: group.signal } : {});
        if (!prepared.ok)
            throw new Error(prepared.failure.diagnostics.map(d => d.message).join('\n') || prepared.failure.code);
        const committed = await (group ? group.commit(prepared.command.id) : commands.commit(prepared.command.id));
        if (!committed.ok) {
            commands.discard(prepared.command.id);
            throw new Error(committed.failure.diagnostics.map(d => d.message).join('\n') || committed.failure.code);
        }
        await handle.refresh();
        return committed.receipt;
    }
    function run(action) { void action().catch(notifyError); }
    function set(target, path, value) { return apply({ kind: 'set-property', target, path, value: jsonValue(value) }); }
    function nativeCommand(command, target, args, profile) { const entry = selected(); return apply({ kind: 'profile-command', profile: profile ?? (0, native_js_2.str)(entry?.view.record.profile, 'ddn@1'), command, target, arguments: jsonValue(args) }); }
    const toolbarGroups = new Map();
    function button(label, action) {
        const element = document.createElement('button');
        element.type = 'button';
        element.textContent = label;
        const icon = { 'Add view': 'plus', 'Add entity': 'plus', 'Add element': 'grid', 'Connect': 'link', 'Reflow': 'reflow', 'Style': 'pen', 'Font': 'type', 'Border': 'border', 'Shadow': 'shadow', 'Pin': 'pin', 'Paper & attachments': 'shadow', 'Appearance & presets': 'palette', 'Properties': 'settings', 'Rename': 'type', 'Undo': 'undo', 'Redo': 'redo', 'Delete': 'minus' }[label];
        if (icon)
            element.prepend((0, ui_icons_js_1.uiIcon)(document, icon));
        const groupName = ['Add element', 'Add existing element', 'Connect', 'Add view', 'Add entity', 'Workarea', 'Reflow'].includes(label) ? 'Create' : ['Undo', 'Redo'].includes(label) ? 'History' : ['Datasets', 'Source', 'Projection', 'Style', 'Font', 'Border', 'Shadow'].includes(label) ? 'Document' : 'Selection';
        let group = toolbarGroups.get(groupName);
        if (!group) {
            group = document.createElement('div');
            group.className = 'ddn-toolbar-group';
            group.setAttribute('role', 'group');
            group.setAttribute('aria-label', groupName);
            toolbarGroups.set(groupName, group);
            toolbar.append(group);
        }
        element.addEventListener('click', action);
        group.append(element);
        return element;
    }
    function field(container, label, value = '', multiline = false) { const wrapper = document.createElement('label'); wrapper.append(document.createTextNode(label)); const input = multiline ? document.createElement('textarea') : document.createElement('input'); input.value = value; wrapper.append(input); container.append(wrapper); return input; }
    function panel(title, build, applyLabel) {
        const openedRevision = JSON.stringify(handle.runtime.snapshot()?.revision);
        let submit;
        const existing = [...panels][0];
        if (existing) {
            if (existing.dataset.ddnLiveSettings !== undefined) {
                panelClosers.get(existing)?.();
            }
            else {
                existing.focus();
                handle.announce('Close the open editor before opening another settings form.');
                return existing;
            }
        }
        const live = ['Edit title', 'Draft body', 'Details shown (this appearance)', 'Details shown (entity default)', 'Edit table data', 'Comments', 'Constraints', 'Properties', 'Paper & attachments', 'Appearance & presets', 'Symbol & label', 'Projection settings', 'Element and relationship details', 'Datasets', 'Workarea settings', 'Edit topic name', 'Topic notes', 'Page setup', 'Header', 'Footer'].includes(title);
        let session;
        const dialog = (0, dialogs_js_1.createStandardDialog)(handle.overlays, { title, modal: !live, ...(applyLabel ? { applyLabel } : {}),
            ...(!live ? { async onApply() {
                    if (JSON.stringify(handle.runtime.snapshot()?.revision) !== openedRevision)
                        throw Error('The diagram changed while this editor was open. Copy your edits and reopen it to reconcile the current revision.');
                    await submit();
                } } : { async beforeClose() {
                    try {
                        await session?.finish();
                    }
                    catch (error) {
                        notifyError(error);
                    }
                } }),
            onClose() { panels.delete(dialog.element); panelClosers.delete(dialog.element); session?.dispose(); },
        });
        dialog.element.classList.add('ddn-designer-panel');
        if (dialog.applyButton)
            dialog.applyButton.dataset.ddnApply = '';
        panels.add(dialog.element);
        panelClosers.set(dialog.element, () => { session?.dispose(); dialog.close(); });
        try {
            submit = build(dialog.body, dialog.applyButton ?? document.createElement('button'));
            if (live) {
                dialog.element.dataset.ddnLiveSettings = '';
                const status = document.createElement('span');
                status.className = 'ddn-live-settings-status';
                status.setAttribute('role', 'status');
                status.style.cssText = 'font-size:11px;margin-right:auto;color:var(--ddn-ui-muted)';
                const revert = document.createElement('button');
                revert.type = 'button';
                revert.textContent = 'Revert changes';
                revert.title = 'Undo changes made in this editor and close it';
                dialog.footer.prepend(status);
                dialog.footer.append(revert);
                session = (0, live_settings_js_2.createLiveSettings)({ body: dialog.body, commands, submit, showError: dialog.showError,
                    onState(state) { status.textContent = state.busy ? 'Updating diagram…' : state.error ? 'Last valid settings retained.' : 'Changes update the diagram immediately.'; revert.disabled = !state.changed || !state.current; },
                    afterRevert: () => handle.refresh(),
                });
                revert.addEventListener('click', () => { void session.revert().then(() => dialog.close()).catch(dialog.showError); });
            }
        }
        catch (error) {
            dialog.close();
            throw error;
        }
        return dialog.element;
    }
    async function applyProperties(target, properties) {
        const current = (0, runtime_js_1.runtimeState)(handle.runtime), original = current.source;
        if (!original || !current.decoded)
            throw Error('Editable sources are unavailable.');
        let source = original, decoded = current.decoded;
        for (const [path, value] of Object.entries(properties)) {
            source = (0, index_js_1.applySourcePatches)(source, (0, index_js_1.patchProperty)(decoded, target, path, value));
            decoded = (0, index_js_1.decodeSources)(source, { previous: decoded });
            if (!decoded.syntaxValid)
                throw Error(decoded.diagnostics.map(d => d.message).join('\n'));
        }
        const patches = source.files.flatMap(file => { const before = original.files.find(candidate => candidate.id === file.id); return file.text === before.text ? [] : [{ file: file.id, base: before.revision, start: 0, end: before.text.length, text: file.text }]; });
        if (patches.length)
            await apply({ kind: 'edit-source', patches });
    }
    async function renameTitle(entry, value) {
        if ((0, mindmap_actions_js_1.mindmapSelection)(handle, entry)) {
            const draft = (0, mindmap_source_js_1.mindmapSource)(handle.runtime, entry.view.ref);
            if ((0, index_js_1.findNode)(draft.decoded, entry.definition.ref)?.generated)
                draft.materialize();
            draft.set(entry.definition.ref, 'title', value);
            await commitMindmap(draft);
        }
        else
            await set(entry.definition.ref, 'title', value);
    }
    function editTitle(entry = requireSelection()) {
        if ((0, mindmap_actions_js_1.mindmapSelection)(handle, entry)) {
            editTopicName(entry);
            return;
        }
        panel('Edit title', body => { const input = field(body, 'Display title', (0, native_js_2.str)(entry.definition.record.title) || (0, native_js_2.str)(entry.definition.record.name)); return async () => { await set(entry.definition.ref, 'title', input.value); }; });
    }
    function editDraft(entry = requireSelection()) { panel('Draft body', body => { const input = field(body, 'Free-form text', (0, native_js_2.str)((0, native_js_2.pathValue)(entry.definition.record, 'draft.text')), true); const note = document.createElement('p'); note.textContent = 'Free-form text shown inside the element. Use Columns to turn each line into a field later.'; body.append(note); return async () => { await nativeCommand('ddn.set-draft', entry.definition.ref, { text: input.value, format: (0, native_js_2.str)((0, native_js_2.pathValue)(entry.definition.record, 'draft.format'), 'text') }); }; }); }
    function convert(entry = requireSelection()) {
        panel('Convert draft to columns', body => {
            const label = document.createElement('label');
            label.textContent = 'Interpretation';
            const select = document.createElement('select');
            for (const [value, text] of [['field-list', 'Every line is a field (no header)'], ['header-table', 'First row defines table columns']]) {
                const option = document.createElement('option');
                option.value = value;
                option.textContent = text;
                select.append(option);
            }
            select.value = (0, native_js_2.pathValue)(entry.definition.record, 'draft.format') === 'table' ? 'header-table' : 'field-list';
            label.append(select);
            body.append(label);
            const pre = document.createElement('pre');
            pre.textContent = (0, native_js_2.str)((0, native_js_2.pathValue)(entry.definition.record, 'draft.text'));
            body.append(pre);
            return async () => { await apply({ kind: 'convert-body', target: entry.definition.ref, interpretation: select.value }); };
        });
    }
    function details(entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const data = (0, native_js_2.tableData)(snapshot, entry.definition);
        const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded;
        const explicit = entry.appearance && decoded && !(0, index_js_1.findNode)(decoded, entry.appearance.ref)?.implicit;
        const target = explicit ? entry.appearance.ref : entry.definition.ref;
        panel(explicit ? 'Details shown (this appearance)' : 'Details shown (entity default)', body => { const visibility = { ...(0, native_js_2.object)(entry.definition.record.column_visibility), ...(0, native_js_2.object)(entry.appearance?.record.column_visibility) }; const choices = data.columns.map(column => { const label = document.createElement('label'), checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = visibility[(0, native_js_2.str)(column.id)] === 'shown' || visibility[(0, native_js_2.str)(column.id)] !== 'hidden' && (0, native_js_2.str)(column.id) === 'field'; checkbox.dataset.column = (0, native_js_2.str)(column.id); label.append(checkbox, document.createTextNode((0, native_js_2.str)(column.label, (0, native_js_2.str)(column.id)))); body.append(label); return { id: (0, native_js_2.str)(column.id), checkbox }; }); return async () => { await set(target, 'column_visibility', Object.fromEntries(choices.map(({ id, checkbox }) => [id, checkbox.checked ? 'shown' : 'hidden']))); }; });
    }
    function editRows(entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const data = (0, native_js_2.tableData)(snapshot, entry.definition);
        panel('Edit table data', body => {
            const table = document.createElement('table'), head = document.createElement('tr');
            for (const column of data.columns) {
                const th = document.createElement('th');
                th.textContent = (0, native_js_2.str)(column.label, (0, native_js_2.str)(column.id));
                head.append(th);
            }
            table.append(head);
            const inputs = [];
            for (const row of data.rows) {
                const tr = document.createElement('tr');
                inputs.push(data.columns.map((column, i) => { const td = document.createElement('td'), input = document.createElement('input'); input.value = String(row[i] ?? ''); input.setAttribute('aria-label', `${(0, native_js_2.str)(column.id)} row ${inputs.length + 1}`); td.append(input); tr.append(td); return input; }));
                table.append(tr);
            }
            body.append(table);
            const add = document.createElement('button');
            add.textContent = 'Add row';
            add.addEventListener('click', () => { const tr = document.createElement('tr'); inputs.push(data.columns.map(column => { const td = document.createElement('td'), input = document.createElement('input'); input.setAttribute('aria-label', (0, native_js_2.str)(column.id)); td.append(input); tr.append(td); return input; })); table.append(tr); (0, live_settings_js_1.notifyLiveSettings)(body); });
            body.append(add);
            return async () => { const columns = data.columns; const rows = inputs.map((row, ri) => row.map((input, ci) => { const previous = data.rows[ri]?.[ci]; return input.value === '' ? previous === null || previous === undefined ? null : '' : typeof previous === 'number' && Number.isFinite(Number(input.value)) ? Number(input.value) : input.value; })); await nativeCommand('ddn.set-table', entry.definition.ref, { columns, rows }); };
        });
    }
    function notes(entry = requireSelection(), topic = false) {
        panel(topic ? 'Topic notes' : 'Comments', body => {
            const choice = document.createElement('select');
            choice.setAttribute('aria-label', topic ? 'Topic note' : 'Note');
            choice.dataset.ddnLiveIgnore = '';
            body.append(choice);
            const input = field(body, topic ? 'Markdown note' : 'Markdown notes', '', true);
            let selectedId = '', known = [];
            const currentNotes = () => (0, native_js_2.array)((0, native_js_2.records)(handle.runtime.snapshot()).find(record => (0, native_js_2.refKey)(record.ref) === (0, native_js_2.refKey)(entry.definition.ref))?.record.notes).map(index_js_2.asRecord);
            const refreshChoices = (pick, updateText) => {
                known = currentNotes();
                choice.replaceChildren();
                known.forEach((note, index) => choice.add(new Option((0, native_js_2.str)(note.title, (0, native_js_2.str)(note.name, 'Note ' + (index + 1))), (0, native_js_2.str)(note.id))));
                choice.add(new Option('New note', 'new'));
                selectedId = known.some(note => note.id === pick) ? pick : pick === '' && known[0] ? (0, native_js_2.str)(known[0].id) : 'new';
                choice.value = selectedId;
                if (updateText)
                    input.value = (0, native_js_2.str)(known.find(note => note.id === selectedId)?.text);
            };
            refreshChoices('', true);
            choice.addEventListener('change', event => { event.stopPropagation(); const next = choice.value; choice.value = selectedId; run(async () => { await (0, live_settings_js_1.flushLiveSettings)(body); refreshChoices(next, true); }); });
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.textContent = 'Delete selected note';
            if (topic)
                body.append(remove);
            remove.addEventListener('click', () => { input.value = ''; deleting = true; (0, live_settings_js_1.notifyLiveSettings)(body); });
            let deleting = false;
            return async () => {
                const selected = selectedId, text = input.value, deleteNote = deleting;
                deleting = false;
                if (deleteNote && selected === 'new' || selected === 'new' && !text)
                    return;
                const existing = currentNotes(), beforeIds = new Set(existing.map(note => (0, native_js_2.str)(note.id)));
                if (topic) {
                    const draft = (0, mindmap_source_js_1.mindmapSource)(handle.runtime, entry.view.ref);
                    if ((0, index_js_1.findNode)(draft.decoded, entry.definition.ref)?.generated)
                        draft.materialize();
                    const saveNotes = (values) => {
                        for (const note of existing) {
                            const ref = { file: entry.definition.file, id: (0, native_js_2.str)(note.id) };
                            if ((0, index_js_1.findNode)(draft.decoded, ref)?.kind === 'notes')
                                draft.apply((0, index_js_1.deleteDeclaration)(draft.decoded, ref));
                        }
                        draft.set(entry.definition.ref, 'notes', values);
                    };
                    const note = existing.find(note => note.id === selected);
                    if (note) {
                        const target = { file: entry.definition.file, id: selected }, node = (0, index_js_1.findNode)(draft.decoded, target);
                        if (node?.kind === 'notes')
                            draft.apply(deleteNote ? (0, index_js_1.deleteDeclaration)(draft.decoded, target) : (0, index_js_1.replaceNoteBody)(draft.decoded, target, text));
                        else
                            saveNotes(deleteNote ? existing.filter(note => note.id !== selected) : existing.map(note => note.id === selected ? { ...note, text } : note));
                    }
                    else
                        saveNotes([...existing, { id: draft.unique('mindmap-note', entry.definition.file), name: draft.unique('Note', entry.definition.file), title: 'Notes', text }]);
                    await commitMindmap(draft);
                }
                else if (selected === 'new')
                    await nativeCommand('ddn.add-note', entry.definition.ref, { text }, (0, native_js_2.str)(entry.view.record.profile));
                else {
                    const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded, target = { file: entry.definition.file, id: selected };
                    if (decoded && (0, index_js_1.findNode)(decoded, target))
                        await nativeCommand('ddn.set-note', target, { text }, (0, native_js_2.str)(entry.view.record.profile));
                    else
                        await applyProperties(entry.definition.ref, { notes: existing.map(note => note.id === selected ? { ...note, text } : note) });
                }
                const created = currentNotes().find(note => !beforeIds.has((0, native_js_2.str)(note.id)));
                refreshChoices(created ? (0, native_js_2.str)(created.id) : deleteNote ? 'new' : selected, false);
                remove.disabled = selectedId === 'new';
            };
        });
    }
    function constraints(entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        panel('Constraints', body => {
            const available = (0, native_js_2.records)(snapshot).filter(record => record.owner === 'definition' && record.record.role === 'constraint');
            const selected = new Set((0, native_js_2.array)(entry.definition.record.constraints).map(value => { const reference = (0, native_js_2.object)(value); return JSON.stringify([(0, native_js_2.str)(reference.file, entry.definition.file), (0, native_js_2.str)(reference.id)]); }));
            const note = document.createElement('p');
            note.textContent = 'Choose reusable constraints. Create a constraint from the element palette when a new one is needed.';
            body.append(note);
            const choices = available.map(record => { const label = document.createElement('label'), input = document.createElement('input'); input.type = 'checkbox'; input.checked = selected.has((0, native_js_2.refKey)(record.ref)); label.append(input, document.createTextNode((0, native_js_2.titleOf)(record.record) + ' (' + record.file + ')')); body.append(label); return { record, input }; });
            return async () => { await set(entry.definition.ref, 'constraints', choices.filter(choice => choice.input.checked).map(choice => choice.record.ref)); };
        });
    }
    function properties() { (0, properties_js_1.openProperties)(viewer, panel, applyProperties); }
    function paperAttachments(entry = selected()) {
        const viewFallback = !entry ? currentView() : undefined;
        const targetEntry = entry ?? (viewFallback ? handle.scene()?.entries.find(e => e.definition.owner === 'view' && (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(viewFallback.ref)) : undefined);
        if (!targetEntry || targetEntry.definition.record.category === 'relation' || !['definition', 'view'].includes(targetEntry.definition.owner))
            throw Error('Select an element or view for paper and attachment settings.');
        const state = (0, runtime_js_1.runtimeState)(handle.runtime);
        if (!state.decoded || !state.source)
            throw Error('Editable sources must be open.');
        const explicit = (record) => record && (0, index_js_1.findNode)(state.decoded, record.ref) && !(0, index_js_1.findNode)(state.decoded, record.ref).implicit;
        const scopes = targetEntry.definition.owner === 'view'
            ? [...(explicit(targetEntry.placement) ? [{ record: targetEntry.placement, label: 'This view placement' }] : []), { record: targetEntry.view, label: 'View definition' }]
            : [...(explicit(targetEntry.appearance) ? [{ record: targetEntry.appearance, label: 'This appearance' }] : []), { record: targetEntry.definition, label: 'Shared definition' }];
        const defaults = { 'style.paper': 'plain', 'shadow.kind': 'none', 'shadow.color': '#000000', 'shadow.opacity': .24, 'shadow.blur': 4, 'shadow.lift': 10, 'shadow.spread': 0 };
        const attachmentColors = { 'push-pin': '#df4545', 'round-pin': '#45a3da', 'paper-clip': '#5b83b4', 'binder-clip': '#3b414b', tape: '#e4c788' };
        panel('Paper & attachments', body => {
            const scope = document.createElement('select');
            scope.setAttribute('aria-label', 'Apply appearance settings to');
            scope.dataset.ddnLiveIgnore = '';
            scopes.forEach(({ label }, index) => { const option = document.createElement('option'); option.value = String(index); option.textContent = label; scope.append(option); });
            const targetLabel = document.createElement('p');
            targetLabel.textContent = 'Editing: ' + (0, native_js_2.titleOf)(targetEntry.definition.record);
            body.append(targetLabel);
            const instructions = document.createElement('p');
            instructions.textContent = 'Only changed settings are saved. Inherit removes the setting here so file defaults and CSS can supply it. Attachments are visual decorations; they do not change meaning or review status.';
            const controls = document.createElement('div');
            body.append(scope, instructions, controls);
            let chosen = 0, generation = 0, loading = true;
            const changes = new Map();
            const readers = new Map();
            const selectField = (container, title, choices, value) => (0, choice_field_js_1.choiceField)(container, title, choices.map(([value, label]) => ({ value, label })), value);
            const numericField = (container, title, value, min, max, step = 'any') => {
                const input = (0, dialogs_js_1.numberField)(container, title, value, { min: Math.max(min, -256), max: Math.min(max, 256), step: step === 'any' ? (max - min <= 1 ? .01 : .1) : Number(step) });
                input.type = 'number';
                input.min = String(min);
                input.max = String(max);
                input.step = step;
                input.required = true;
                (0, dialogs_js_1.syncNumberField)(input);
                return input;
            };
            const colorField = (container, title, value) => (0, dialogs_js_1.colourField)(container, title, value, { dialogHost: handle.overlays });
            const readNumber = (input, title) => {
                if (!input.checkValidity() || !Number.isFinite(input.valueAsNumber))
                    throw Error(`${title} must be a number from ${input.min} to ${input.max}.`);
                return input.valueAsNumber;
            };
            const refresh = async () => {
                const ticket = ++generation, target = scopes[chosen].record;
                loading = true;
                changes.clear();
                readers.clear();
                controls.textContent = 'Loading appearance settings…';
                const inspection = await viewer.inspect(target.ref);
                if (ticket !== generation || disposed || !body.isConnected)
                    return;
                controls.replaceChildren();
                const effective = new Map(inspection.properties.map(property => [property.path, property.effective]));
                const sourceValue = (path) => (0, native_js_2.pathValue)((0, native_js_2.records)(handle.runtime.snapshot()).find(item => (0, native_js_2.refKey)(item.ref) === (0, native_js_2.refKey)(target.ref))?.record ?? target.record, path);
                const resolvedValue = (path) => {
                    if (effective.has(path))
                        return effective.get(path);
                    const parts = path.split('.');
                    for (let length = parts.length - 1; length > 0; length--) {
                        const parent = effective.get(parts.slice(0, length).join('.'));
                        if (parent !== undefined)
                            return (0, native_js_2.pathValue)((0, native_js_2.object)(parent), parts.slice(length).join('.'));
                    }
                    return undefined;
                };
                const currentShadow = resolvedValue('shadow') ?? sourceValue('shadow') ?? ([...effective.keys()].some(path => path.startsWith('shadow.')) ? {} : undefined);
                const value = (path, fallback) => resolvedValue(path) ?? sourceValue(path) ?? (path === 'shadow.kind' && currentShadow && typeof currentShadow === 'object' ? 'offset' : defaults[path]) ?? fallback ?? '';
                const shadowOffsets = new Map();
                function updateShadowOffsets() {
                    for (const [path, input] of shadowOffsets)
                        if (!changes.has(path) && resolvedValue(path) === undefined && sourceValue(path) === undefined) {
                            input.value = String(shadow.value === 'offset' ? path === 'shadow.x' ? 6 : 8 : 0);
                            (0, dialogs_js_1.syncNumberField)(input);
                        }
                }
                const bind = (path, label, input, read) => {
                    const inherit = document.createElement('input'), wrapper = document.createElement('label');
                    inherit.type = 'checkbox';
                    inherit.checked = sourceValue(path) === undefined;
                    wrapper.append(inherit, document.createTextNode('Inherit ' + label.toLowerCase()));
                    controls.append(wrapper);
                    const edited = () => {
                        inherit.checked = false;
                        changes.set(path, null);
                        readers.set(path, read);
                        if (path.startsWith('shadow.') && path !== 'shadow.kind' && !currentShadow && !changes.has('shadow.kind')) {
                            shadow.value = 'offset';
                            (0, choice_field_js_1.syncChoiceField)(shadow);
                            updateShadowOffsets();
                        }
                    };
                    input.addEventListener('input', edited);
                    input.addEventListener('change', edited);
                    inherit.addEventListener('change', () => {
                        changes.set(path, undefined);
                        readers.delete(path);
                        if (!inherit.checked)
                            readers.set(path, read);
                    });
                };
                const paper = selectField(controls, 'Paper surface', [['plain', 'Plain'], ['note', 'Sticky note'], ['pad', 'Note pad']], String(value('style.paper')));
                bind('style.paper', 'Paper surface', paper, () => paper.value);
                const fillPath = 'background.color';
                const color = colorField(controls, 'Paper colour', String(value(fillPath, '#ffffff')));
                bind(fillPath, 'Paper colour', color, () => color.value);
                const shadow = selectField(controls, 'Shadow shape', [['none', 'None'], ['offset', 'Uniform offset'], ['centre', 'Centre raised'], ['corners', 'Lower corners raised'], ['corner', 'One corner raised']], String(value('shadow.kind')));
                bind('shadow.kind', 'Shadow shape', shadow, () => shadow.value);
                shadow.addEventListener('change', updateShadowOffsets);
                const shadowColor = colorField(controls, 'Shadow colour', String(value('shadow.color')));
                bind('shadow.color', 'Shadow colour', shadowColor, () => shadowColor.value);
                for (const [path, label, min, max] of [['shadow.opacity', 'Shadow opacity', 0, 1], ['shadow.blur', 'Shadow softness', 0, 128], ['shadow.lift', 'Paper lift', 0, 64], ['shadow.x', 'Shadow horizontal offset', -1e9, 1e9], ['shadow.y', 'Shadow vertical offset', -1e9, 1e9], ['shadow.spread', 'Shadow spread', 0, 128]]) {
                    const fallback = shadow.value === 'offset' ? path === 'shadow.x' ? 6 : path === 'shadow.y' ? 8 : undefined : 0;
                    const input = numericField(controls, label, Number(value(path, fallback)), min, max);
                    if (path === 'shadow.x' || path === 'shadow.y')
                        shadowOffsets.set(path, input);
                    bind(path, label, input, () => readNumber(input, label));
                }
                const heading = document.createElement('h4');
                heading.textContent = 'Attachments';
                controls.append(heading);
                const attachments = JSON.parse(JSON.stringify(effective.get('decorations') ?? sourceValue('decorations') ?? []));
                const inheritAttachments = document.createElement('input'), inheritLabel = document.createElement('label'), list = document.createElement('div'), add = document.createElement('button');
                inheritAttachments.type = 'checkbox';
                inheritAttachments.checked = sourceValue('decorations') === undefined;
                inheritLabel.append(inheritAttachments, document.createTextNode('Inherit attachments'));
                add.type = 'button';
                add.textContent = 'Add attachment';
                controls.append(inheritLabel, list, add);
                let attachmentReaders = [];
                const changedAttachments = () => {
                    inheritAttachments.checked = false;
                    changes.set('decorations', null);
                    readers.set('decorations', () => {
                        for (const read of attachmentReaders)
                            read();
                        return attachments;
                    });
                    (0, live_settings_js_1.notifyLiveSettings)(body);
                };
                const renderAttachments = () => {
                    list.replaceChildren();
                    attachmentReaders = [];
                    add.disabled = attachments.length >= 32;
                    attachments.forEach((item, index) => {
                        const group = document.createElement('fieldset'), legend = document.createElement('legend');
                        legend.textContent = 'Attachment ' + (index + 1);
                        group.append(legend);
                        list.append(group);
                        const kind = selectField(group, 'Attachment kind', [['push-pin', 'Push-pin'], ['round-pin', 'Round pin'], ['paper-clip', 'Paper-clip'], ['binder-clip', 'Binder clip'], ['tape', 'Tape']], (0, native_js_2.str)(item.kind, 'push-pin'));
                        const color = colorField(group, 'Attachment colour', (0, native_js_2.str)(item.color, attachmentColors[kind.value]));
                        kind.addEventListener('change', () => {
                            item.kind = kind.value;
                            if (item.color === undefined) {
                                color.value = attachmentColors[kind.value];
                                (0, dialogs_js_1.syncColourField)(color);
                            }
                            changedAttachments();
                        });
                        color.addEventListener('input', () => { item.color = color.value; changedAttachments(); });
                        const position = selectField(group, 'Attachment position', [['lt', 'Left top'], ['ct', 'Centre top'], ['rt', 'Right top'], ['lm', 'Left middle'], ['cm', 'Centre middle'], ['rm', 'Right middle'], ['lb', 'Left bottom'], ['cb', 'Centre bottom'], ['rb', 'Right bottom']], (0, native_js_2.str)(item.position, 'ct'));
                        position.addEventListener('change', () => { item.position = position.value; changedAttachments(); });
                        for (const [path, label, fallback, min, max] of [['size', 'Attachment size', 32, 8, 128], ['rotation', 'Attachment rotation', 0, -180, 180], ['opacity', 'Attachment opacity', 1, 0, 1], ['offset.x', 'Attachment horizontal offset', 0, -256, 256], ['offset.y', 'Attachment vertical offset', 0, -256, 256]]) {
                            const input = numericField(group, label, (0, native_js_2.num)((0, native_js_2.pathValue)(item, path), fallback), min, max);
                            let touched = false;
                            input.addEventListener('input', () => { touched = true; changedAttachments(); });
                            attachmentReaders.push(() => {
                                if (!touched)
                                    return;
                                const result = readNumber(input, label);
                                if (path.startsWith('offset.'))
                                    item.offset = jsonValue({ ...(0, native_js_2.object)(item.offset), [path.slice(7)]: result });
                                else
                                    item[path] = result;
                            });
                        }
                        const remove = document.createElement('button');
                        remove.type = 'button';
                        remove.textContent = 'Remove attachment';
                        remove.addEventListener('click', guarded(() => {
                            for (const read of attachmentReaders)
                                read();
                            attachments.splice(index, 1);
                            renderAttachments();
                            changedAttachments();
                        }));
                        group.append(remove);
                    });
                };
                add.addEventListener('click', guarded(() => {
                    if (attachments.length >= 32)
                        return;
                    for (const read of attachmentReaders)
                        read();
                    attachments.push({ kind: 'push-pin' });
                    renderAttachments();
                    changedAttachments();
                }));
                inheritAttachments.addEventListener('change', () => {
                    if (inheritAttachments.checked) {
                        changes.set('decorations', undefined);
                        readers.delete('decorations');
                    }
                    else
                        changedAttachments();
                });
                renderAttachments();
                loading = false;
            };
            scope.addEventListener('change', event => {
                event.stopPropagation();
                const next = Number(scope.value);
                scope.value = String(chosen);
                run(async () => { await (0, live_settings_js_1.flushLiveSettings)(body); chosen = next; scope.value = String(chosen); await refresh(); });
            });
            void refresh().catch(notifyError);
            return async () => {
                if (loading)
                    throw Error('Wait for appearance settings to load.');
                if (!changes.size)
                    return;
                const current = (0, runtime_js_1.runtimeState)(handle.runtime), original = current.source;
                if (!original || !current.decoded)
                    throw Error('Editable sources are unavailable.');
                let source = original, decoded = current.decoded;
                for (const [path, reset] of changes) {
                    const value = readers.has(path) ? readers.get(path)() : reset;
                    source = (0, index_js_1.applySourcePatches)(source, (0, index_js_1.patchProperty)(decoded, scopes[chosen].record.ref, path, value));
                    decoded = (0, index_js_1.decodeSources)(source, { previous: decoded });
                    if (!decoded.syntaxValid)
                        throw Error(decoded.diagnostics.map(d => d.message).join('\n'));
                }
                const patches = source.files.flatMap(file => {
                    const before = original.files.find(candidate => candidate.id === file.id);
                    return file.text === before.text ? [] : [{ file: file.id, base: before.revision, start: 0, end: before.text.length, text: file.text }];
                });
                if (patches.length)
                    await apply({ kind: 'edit-source', patches });
            };
        });
    }
    function profileEditor(projection = false, entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const references = (0, native_js_2.records)(snapshot).filter(r => !['appearance', 'placement'].includes(r.owner)).map(r => ({ ref: r.ref, label: `${(0, native_js_2.titleOf)(r.record)} (${r.owner}, ${r.file})` }));
        const profile = (0, core_js_1.getProfile)((0, native_js_2.str)(entry.view.record.profile));
        panel(projection ? 'Projection settings' : 'Element and relationship details', body => {
            if (projection) {
                if (!profile)
                    throw Error('Profile is unavailable');
                const note = document.createElement('p');
                note.textContent = profile.scope + ' Omitted settings use the versioned defaults.';
                body.append(note);
                const editor = (0, schema_editor_js_1.createFieldEditor)(body, schema_core_js_1.codex.roots[profile.projection_schema], jsonValue((0, native_js_2.pathValue)(entry.view.record, 'projection.options')), references, 'Projection');
                return async () => { await set(entry.view.ref, 'projection.options', editor.read()); };
            }
            const role = (0, core_js_1.roleDescriptor)((0, native_js_2.str)(entry.definition.record.role), (0, native_js_2.str)(entry.definition.record.category, 'element'));
            const core = schema_core_js_1.codex.coreTypes[(0, native_js_2.str)(entry.definition.record.role)];
            const sectionSchema = (key) => core && key === (core.category === 'relation' ? 'qualifiers' : 'content') ? core.schema : (0, schema_editor_js_1.childSchema)(role?.schema, key) ?? (0, schema_editor_js_1.childSchema)(schema_core_js_1.codex.roots.definition, key);
            const choices = document.createElement('select'), controls = document.createElement('div');
            choices.setAttribute('aria-label', 'Detail section');
            choices.dataset.ddnLiveIgnore = '';
            for (const key of ['metadata', 'properties', 'content', 'qualifiers', 'endpoints', 'members']) {
                if ((sectionSchema(key)) === undefined)
                    continue;
                const option = document.createElement('option');
                option.value = key;
                option.textContent = key;
                choices.append(option);
            }
            if (!choices.options.length)
                throw Error('Select an element or relationship to edit its details.');
            body.append(choices, controls);
            let editor = (0, schema_editor_js_1.createFieldEditor)(controls, sectionSchema(choices.value), jsonValue(entry.definition.record[choices.value]), references, choices.value);
            let section = choices.value;
            choices.addEventListener('change', event => {
                event.stopPropagation();
                const next = choices.value;
                choices.value = section;
                run(async () => { await (0, live_settings_js_1.flushLiveSettings)(body); section = next; choices.value = next; controls.replaceChildren(); const current = (0, native_js_2.records)(handle.runtime.snapshot()).find(record => (0, native_js_2.refKey)(record.ref) === (0, native_js_2.refKey)(entry.definition.ref)); editor = (0, schema_editor_js_1.createFieldEditor)(controls, sectionSchema(section), jsonValue(current?.record[section]), references, section); });
            });
            return async () => { await applyProperties(entry.definition.ref, { [section]: editor.read() }); };
        });
    }
    function datasets() {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const all = (0, native_js_2.records)(snapshot), data = all.filter(r => r.owner === 'data'), view = selected()?.view ?? handle.scene()?.views[0];
        const references = all.filter(r => !['appearance', 'placement'].includes(r.owner)).map(r => ({ ref: r.ref, label: `${(0, native_js_2.titleOf)(r.record)} (${r.owner}, ${r.file})` }));
        panel('Datasets', body => {
            const choice = document.createElement('select');
            choice.setAttribute('aria-label', 'Dataset');
            choice.dataset.ddnLiveIgnore = '';
            const available = () => (0, native_js_2.records)(handle.runtime.snapshot()).filter(record => record.owner === 'data');
            const updateChoices = (selected) => { choice.replaceChildren(new Option('New dataset', 'new')); available().forEach(record => choice.add(new Option((0, native_js_2.titleOf)(record.record), (0, native_js_2.refKey)(record.ref)))); choice.value = selected; };
            let selected = 'new', creating = false;
            updateChoices(selected);
            body.append(choice);
            const name = field(body, 'Dataset name', 'NewData'), area = document.createElement('div');
            body.append(area);
            const create = document.createElement('button');
            create.type = 'button';
            create.textContent = 'Create dataset';
            body.append(create);
            let columns, rows;
            const render = () => {
                area.replaceChildren();
                const record = available().find(record => (0, native_js_2.refKey)(record.ref) === selected);
                name.disabled = !!record;
                name.value = (0, native_js_2.str)(record?.record.name, 'NewData');
                create.hidden = !!record;
                const columnLabel = document.createElement('h4');
                columnLabel.textContent = 'Columns';
                area.append(columnLabel);
                columns = (0, schema_editor_js_1.createFieldEditor)(area, (0, schema_editor_js_1.childSchema)(schema_core_js_1.codex.roots.data_record, 'columns'), jsonValue(record?.record.columns ?? [{ id: 'label', type: 'text' }, { id: 'value', type: 'number' }]), references, 'Columns');
                const rowLabel = document.createElement('h4');
                rowLabel.textContent = 'Rows';
                area.append(rowLabel);
                rows = (0, schema_editor_js_1.createFieldEditor)(area, (0, schema_editor_js_1.childSchema)(schema_core_js_1.codex.roots.data_record, 'rows'), jsonValue(record?.record.rows ?? []), references, 'Rows');
            };
            choice.addEventListener('change', event => { event.stopPropagation(); const next = choice.value; choice.value = selected; run(async () => { await (0, live_settings_js_1.flushLiveSettings)(body); selected = next; choice.value = next; render(); }); });
            create.addEventListener('click', () => { creating = true; (0, live_settings_js_1.notifyLiveSettings)(body); });
            render();
            const note = document.createElement('p');
            note.textContent = 'Edits to existing data update its diagrams immediately. Create new data explicitly, then bind it using Projection settings. Provider-bound data remains read-only.';
            body.append(note);
            return async () => {
                const isNew = selected === 'new';
                if (isNew && !creating)
                    return;
                creating = false;
                const record = available().find(record => (0, native_js_2.refKey)(record.ref) === selected), label = name.value, profile = (0, native_js_2.str)(view?.record.profile, 'ddn@1');
                const target = isNew ? view?.ref ?? { file: snapshot.rootFile, id: '' } : record.ref;
                await nativeCommand(isNew ? 'ddn.add-dataset' : 'ddn.set-records', target, { ...(isNew ? { name: label } : {}), columns: columns.read(), rows: rows.read() }, profile);
                if (isNew) {
                    const created = available().find(record => record.record.name === label);
                    if (created) {
                        selected = (0, native_js_2.refKey)(created.ref);
                        updateChoices(selected);
                        name.disabled = true;
                        create.hidden = true;
                    }
                }
            };
        });
    }
    const canMove = (entry) => entry.definition.owner === 'view' || (0, core_js_1.getProfile)((0, native_js_2.str)(entry.view.record.profile))?.projection === 'graph';
    const geometryLocked = (entry, kind) => (0, native_js_2.pathValue)(entry.effective, 'locked.' + kind) === true;
    let resizeDecoded;
    const resizeSources = new Map();
    const canResize = (entry) => {
        const target = entry.appearance ?? entry.placement;
        if (!target || !writable(target.ref) || geometryLocked(entry, 'resize') || !canMove(entry) || entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints) || entry.definition.owner === 'view' && entry.surfaceTransform)
            return false;
        const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded;
        if (decoded !== resizeDecoded) {
            resizeDecoded = decoded;
            resizeSources.clear();
            if (decoded)
                for (const node of (0, index_js_1.allNodes)(decoded))
                    if (node.ref && !resizeSources.has((0, native_js_2.refKey)(node.ref)))
                        resizeSources.set((0, native_js_2.refKey)(node.ref), !node.generated);
        }
        const editable = resizeSources.get((0, native_js_2.refKey)(target.ref));
        return editable === true || editable === false && entry.view.record.profile === 'mindmap.basic@1';
    };
    async function resizeElement(entry, width, height, nextPos) {
        if (!canResize(entry))
            return;
        const target = (entry.appearance ?? entry.placement), size = { width: Math.max(40, snap(width)), height: Math.max(40, snap(height)) };
        const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded;
        if (entry.view.record.profile === 'mindmap.basic@1' && decoded && (0, index_js_1.findNode)(decoded, target.ref)?.generated) {
            const draft = (0, mindmap_source_js_1.mindmapSource)(handle.runtime, entry.view.ref);
            draft.materialize();
            draft.set(target.ref, 'size', size);
            if (nextPos)
                draft.set(target.ref, 'position', { x: snap(nextPos.x), y: snap(nextPos.y) });
            await commitMindmap(draft);
        }
        else {
            await nativeCommand('ddn.set-size', target.ref, size);
            if (nextPos)
                await nativeCommand('ddn.set-position', target.ref, { x: snap(nextPos.x), y: snap(nextPos.y) });
        }
    }
    async function statusChange(next, entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            throw new Error('No model');
        const from = (0, native_js_2.str)((0, native_js_2.pathValue)(entry.definition.record, 'design.state'), 'draft');
        const scope = { kind: entry.definition.owner === 'view' ? 'view' : 'item', target: entry.definition.ref };
        const report = next === 'in-review' || next === 'accepted' ? await handle.runtime.verifier.verifyModel(snapshot, { scope, purpose: 'review', level: 'review' }) : undefined;
        const authority = await options.authority.authorize(from === 'accepted' ? 'lifecycle.reopen' : next === 'accepted' ? 'lifecycle.accept' : next === 'in-review' ? 'lifecycle.review' : 'model.edit', [entry.definition.ref], snapshot.revision);
        if (!authority.allowed)
            throw new Error('Status change is not authorized.');
        const transition = { target: entry.definition.ref, from, to: next, grants: authority.grants, ...(report ? { report } : {}), ...(next === 'accepted' ? { acceptance: { user: authority.principal, timestamp: new Date().toISOString(), authorityContext: 'local' } } : {}) };
        await apply({ kind: 'status', transition });
    }
    function statusDialog(entry = requireSelection()) {
        panel('Design status', body => {
            const select = document.createElement('select');
            for (const state of ['in-progress', 'in-review', 'accepted']) {
                const option = document.createElement('option');
                option.value = state;
                option.textContent = state;
                select.append(option);
            }
            body.append(select);
            const explanation = document.createElement('p');
            explanation.textContent = 'In progress → in review → accepted. Moving to review runs the full verification first; accepting records who accepted it and when. A draft leaves the draft state once.';
            body.append(explanation);
            return async () => { await statusChange(select.value, entry); };
        });
    }
    function allowedViewProfiles() {
        const snapshot = handle.runtime.snapshot();
        const workarea = snapshot && (0, native_js_2.records)(snapshot).find(record => record.owner === 'workarea' && record.file === snapshot.rootFile)?.record;
        const rootMethod = (0, native_js_2.str)(workarea?.method, 'ddn'), foreign = workarea?.allow_foreign_views ?? rootMethod === 'ddn';
        const allowed = (0, native_js_2.array)(workarea?.allowed_profiles);
        const names = { MT01: 'ddn', MT02: 'uml', MT03: 'chen', MT04: 'flowchart', MT05: 'bpmn', MT06: 'cmmn', MT07: 'dmn', MT08: 'c4', MT09: 'dfd', MT10: 'sysml', MT11: 'archimate', MT12: 'epc', MT13: 'idef0', MT14: 'petri', MT15: 'orm', MT16: 'vsm', MT17: 'sdl', MT18: 'msc', MT19: 'soaml', MT20: 'uaf', MT21: 'electrical' };
        return ((0, profile_loading_js_1.profileLoadingHost)(handle.runtime)?.profiles ?? (0, registry_js_1.registrations)(handle.runtime.registry).profiles ?? []).filter(profile => (foreign || names[profile.method] === rootMethod) && (!allowed.length || allowed.includes(profile.id)));
    }
    function viewCanChooseType(view) {
        const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded, node = decoded && (0, index_js_1.findNode)(decoded, view.ref);
        return !!node && !node.generated && !node.implicit && view.record.kind !== 'document'
            && (0, core_js_1.getProfile)((0, native_js_2.str)(view.record.profile))?.projection === 'graph' && view.record.profile !== 'table.records@1'
            && !(0, native_js_2.array)((0, native_js_2.pathValue)(view.record, 'selection.include')).length
            && !handle.scene()?.entries.some(entry => entry.definition.owner !== 'view' && (0, native_js_2.refKey)(entry.view.ref) === (0, native_js_2.refKey)(view.ref))
            && node.children.every(child => child.implicit || child.kind === 'with');
    }
    async function activateView(view) {
        await viewer.navigate({ kind: 'focus', target: view.ref });
        const frame = handle.scene()?.entries.find(entry => entry.definition.owner === 'view' && (0, native_js_2.refKey)(entry.view.ref) === (0, native_js_2.refKey)(view.ref));
        if (frame)
            handle.select(view.ref, frame.item.occurrence);
        closePaletteDock();
        paletteSearchValue = '';
        openPaletteDock();
        handle.container.dispatchEvent(new CustomEvent('ddn:view-type-chosen', { detail: { view: view.ref } }));
    }
    async function createView(name, profile, layout = 'dynamic') {
        if (standalone() && handle.scene()?.views.length)
            throw Error('A standalone document contains one view.');
        const state = (0, runtime_js_1.runtimeState)(handle.runtime), source = state.source, decoded = state.decoded;
        if (!source || !decoded)
            throw Error('Editable sources are unavailable.');
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            throw Error('Open a document before creating a view.');
        await apply({ kind: 'edit-source', patches: (0, index_js_1.appendDeclaration)(decoded, snapshot.rootFile, (0, view_picker_js_1.diagramHeader)(name, profile) + '\n' + (0, view_layout_picker_js_1.viewLayoutSource)(layout)) });
        const created = handle.scene()?.views.find(view => view.record.name === name && view.file === snapshot.rootFile);
        if (created)
            await activateView(created);
        handle.announce(`View "${name}" added.`);
    }
    function addView(chooseType = false) {
        if (standalone() && handle.scene()?.views.length) {
            handle.announce('A standalone document contains one view.');
            return;
        }
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        if (!currentView() && !handle.runtime.sources()?.files.some(file => file.text.trim())) {
            chooseViewType();
            return;
        }
        const existing = [...panels][0];
        if (existing) {
            existing.focus();
            handle.announce('Close the open editor before adding a view.');
            return;
        }
        const profiles = allowedViewProfiles();
        let initialName = 'NewView', index = 2, layout = 'dynamic';
        const names = new Set((0, native_js_2.records)(snapshot).map(record => record.record.name));
        while (names.has(initialName))
            initialName = 'NewView' + index++;
        const chooseLayout = () => (0, view_layout_picker_js_1.viewLayoutDialog)(handle.overlays, { selected: layout, onContinue(preset) { layout = preset; chooseProfile(); } });
        const chooseProfile = () => {
            const existing = [...panels][0];
            if (existing) {
                existing.focus();
                handle.announce('Close the open editor before adding a view.');
                return;
            }
            let input;
            const form = panel(chooseType ? 'Choose diagram type' : 'Add view', (body, applyButton) => {
                const summary = document.createElement('p');
                summary.className = 'ddn-appearance-message';
                summary.textContent = 'View layout: ' + (0, view_surfaces_js_1.getViewSurfacePreset)(layout).label;
                body.append(summary);
                const type = (0, view_picker_js_1.viewTypePicker)(body, profiles, chooseType ? 'Diagram type' : 'View profile');
                const settings = viewTypeSettings(body, type, applyButton);
                const name = field(settings, chooseType ? 'View name' : 'Unique view name', initialName);
                input = name;
                const note = document.createElement('p');
                note.className = 'ddn-appearance-message';
                note.textContent = 'The chosen type supplies the view defaults, available elements and connection rules.';
                settings.append(note);
                return async () => {
                    if (!name.value.trim())
                        throw Error('Give the view a name.');
                    if (!allowedViewProfiles().some(profile => profile.id === type.value))
                        throw Error('Choose an available diagram type.');
                    await createView(name.value.trim(), type.value, layout);
                };
            }, chooseType ? 'Create view' : undefined);
            const back = document.createElement('button');
            back.type = 'button';
            back.textContent = 'Back';
            back.addEventListener('click', () => {
                if (form.getAttribute('aria-busy') === 'true')
                    return;
                initialName = input.value;
                panelClosers.get(form)?.();
                chooseLayout();
            });
            form.querySelector('footer')?.prepend(back);
        };
        chooseLayout();
    }
    function viewTypeSettings(body, type, applyButton) {
        const settings = document.createElement('div');
        settings.className = 'ddn-view-type-settings';
        body.append(settings);
        const update = () => {
            settings.hidden = !type.value;
            applyButton.disabled = !type.value;
            if (type.value) {
                const name = settings.querySelector('input');
                (name ?? applyButton).focus({ preventScroll: true });
                name?.select();
            }
        };
        type.onChange(update);
        update();
        return settings;
    }
    function chooseViewType() {
        const view = currentView();
        if (!view) {
            const sources = handle.runtime.sources();
            if (sources?.files.some(file => file.text.trim())) {
                addView(true);
                return;
            }
            (0, new_diagram_js_1.newDiagramDialog)(viewer, async (text) => {
                const snapshot = handle.runtime.snapshot(), source = handle.runtime.sources();
                const file = source?.files.find(file => file.id === snapshot?.rootFile);
                if (!file || !snapshot || source?.files.some(file => file.text.trim()))
                    throw Error('This document is no longer empty.');
                await apply({ kind: 'edit-source', patches: [{ file: file.id, base: file.revision, start: 0, end: file.text.length, text }] });
            });
            return;
        }
        if (!viewCanChooseType(view)) {
            handle.announce('This view already contains content. Add a new view to choose another diagram type.');
            return;
        }
        if (!writable(view.ref)) {
            handle.announce('This view is read-only.');
            return;
        }
        const profiles = allowedViewProfiles();
        panel('Choose diagram type', (body, applyButton) => {
            const type = (0, view_picker_js_1.viewTypePicker)(body, profiles, 'Diagram type', (0, native_js_2.str)(view.record.profile));
            const settings = viewTypeSettings(body, type, applyButton);
            const note = document.createElement('p');
            note.className = 'ddn-appearance-message';
            note.textContent = `Set the diagram type for "${(0, native_js_2.titleOf)(view.record)}". Explicit appearance settings are retained; omitted values use the chosen type’s defaults.`;
            settings.append(note);
            return async () => {
                if (!allowedViewProfiles().some(profile => profile.id === type.value))
                    throw Error('Choose an available diagram type.');
                const state = (0, runtime_js_1.runtimeState)(handle.runtime), original = state.source;
                if (!original || !state.decoded || !viewCanChooseType(view))
                    throw Error('This view is no longer empty and editable.');
                let source = original, decoded = state.decoded;
                for (const path of ['profile', 'subtype']) {
                    const removals = (0, index_js_1.patchProperty)(decoded, view.ref, path, undefined).map(patch => {
                        const file = source.files.find(file => file.id === patch.file);
                        const comments = file.text.slice(patch.start, patch.end).split(/(?<=\n)/).filter(line => line.trimStart().startsWith('//')).join('');
                        return { ...patch, text: comments };
                    });
                    source = (0, index_js_1.applySourcePatches)(source, removals);
                    decoded = (0, index_js_1.decodeSources)(source, { previous: decoded });
                }
                const node = (0, index_js_1.findNode)(decoded, view.ref), file = source.files.find(file => file.id === view.ref.file);
                const documentSource = decoded.documents.find(document => document.file.id === view.ref.file);
                if (!node || !file || !documentSource)
                    throw Error('View source is unavailable.');
                const title = node.titleStart !== undefined && typeof view.record.title === 'string' ? view.record.title : undefined;
                const header = (node.start === 0 && documentSource.bom ? '\ufeff' : '') + ' '.repeat(node.indent) + (0, view_picker_js_1.diagramHeader)((0, native_js_2.str)(view.record.name), type.value, title) + documentSource.newline;
                source = (0, index_js_1.applySourcePatches)(source, [{ file: file.id, base: file.revision, start: node.start, end: node.headerEnd, text: header }]);
                const patches = source.files.flatMap(file => {
                    const before = original.files.find(candidate => candidate.id === file.id);
                    return file.text === before.text ? [] : [{ file: file.id, base: before.revision, start: 0, end: before.text.length, text: file.text }];
                });
                if (patches.length)
                    await apply({ kind: 'edit-source', patches });
                const configured = handle.scene()?.views.find(candidate => (0, native_js_2.refKey)(candidate.ref) === (0, native_js_2.refKey)(view.ref));
                if (configured)
                    await activateView(configured);
            };
        });
    }
    let paletteSection = 'All elements';
    let paletteDock, paletteSearchValue = '', placing, recentRoles = [];
    let paletteDrag;
    let renderPalette;
    function palette() { openPaletteDock(); }
    function closePaletteDock() { paletteDrag = undefined; (0, drawer_js_1.drawerFor)(handle.container, 'palette')?.destroy(); paletteDock?.remove(); paletteDock = undefined; renderPalette = undefined; handle.container.removeAttribute('data-ddn-dock-left'); buttons['Add element']?.setAttribute('aria-pressed', 'false'); cancelPlacing(); }
    function currentView() { const activeView = handle.viewport().activeView; return (activeView ? handle.scene()?.views.find(v => (0, native_js_2.refKey)(v.ref) === (0, native_js_2.refKey)(activeView)) : undefined) ?? selected()?.view ?? handle.scene()?.views[0]; }
    function roleLabel(role, category = 'element') { const descriptor = (0, core_js_1.roleDescriptor)(role, category); return (0, native_js_2.str)(descriptor?.render?.text_label) || role.replace(/[._]/g, ' '); }
    function openPaletteDock(reuse) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const view = currentView();
        if (!view) {
            addView(true);
            return;
        }
        if (paletteDock && !reuse) {
            const drawer = (0, drawer_js_1.drawerFor)(handle.container, 'palette');
            if (drawer?.mode === 'hidden')
                drawer.setMode('docked');
            drawer?.detached?.focus();
            paletteDock.querySelector('input')?.focus();
            return;
        }
        const profile = (0, core_js_1.getProfile)((0, native_js_2.str)(view.record.profile));
        const dataBound = !!profile && (profile.projection !== 'graph' || view.record.profile === 'table.records@1');
        const roles = profile && !dataBound ? [...profile.primary_palette] : [];
        const dock = reuse ?? document.createElement('section');
        dock.replaceChildren();
        dock.className = 'ddn-designer-dock ddn-designer-dock-left';
        dock.setAttribute('aria-label', 'Element palette');
        const head = document.createElement('div');
        head.className = 'ddn-dock-head';
        head.append((0, ui_icons_js_1.uiIcon)(document, 'grid'), document.createTextNode(dataBound ? 'View data' : 'Add element'));
        const body = document.createElement('div');
        body.className = 'ddn-dock-body';
        const help = document.createElement('p');
        help.className = 'ddn-dock-help';
        help.textContent = dataBound ? 'Add or choose a dataset, then use projection settings to display it in this view.' : roles.length ? 'Drag an element onto the view, or click it then click where it goes. It stays there until connected. Double-click to place it in the middle.' : 'This view type has no element palette; its content comes from its data or projection settings.';
        const searchWrap = document.createElement('div');
        searchWrap.className = 'ddn-palette-search';
        const search = document.createElement('input');
        search.type = 'search';
        search.placeholder = 'Find an element type';
        search.setAttribute('aria-label', 'Find an element type');
        search.value = paletteSearchValue;
        searchWrap.append((0, ui_icons_js_1.uiIcon)(document, 'search'), search);
        const sections = document.createElement('div');
        sections.className = 'ddn-panel-sections';
        const list = document.createElement('div');
        list.className = 'ddn-panel-section';
        const allGroups = [...new Set(roles.map(palette_groups_js_1.paletteGroup))].sort((a, b) => (palette_groups_js_1.paletteGroupOrder.indexOf(a) < 0 ? palette_groups_js_1.paletteGroupOrder.length : palette_groups_js_1.paletteGroupOrder.indexOf(a)) - (palette_groups_js_1.paletteGroupOrder.indexOf(b) < 0 ? palette_groups_js_1.paletteGroupOrder.length : palette_groups_js_1.paletteGroupOrder.indexOf(b)));
        if (!['All elements', 'Recently used', ...allGroups].includes(paletteSection))
            paletteSection = 'All elements';
        const tabs = (0, side_tabs_js_1.sideTabs)(sections, 'Element types', [{ id: 'All elements', label: 'All elements', icon: 'grid', count: roles.length }, ...allGroups.map(group => ({ id: group, label: group, count: roles.filter(role => (0, palette_groups_js_1.paletteGroup)(role) === group).length, icon: group === 'SQL objects' ? 'table' : group === 'File types' ? 'folder' : group === 'Cluster objects' ? 'layers' : 'grid' }))], paletteSection, id => { paletteSection = id; render(); tabs.label(list); });
        tabs.connect(list);
        sections.append(list);
        body.append(help, searchWrap, sections);
        if (dataBound)
            sections.hidden = true;
        if (dataBound) {
            searchWrap.hidden = true;
            const actions = document.createElement('div');
            actions.className = 'ddn-dock-actions';
            for (const [label, run] of [['Data sources and datasets…', () => datasets()], ['Projection settings…', () => profileEditor(true)]]) {
                const button = document.createElement('button');
                button.type = 'button';
                button.textContent = label;
                button.disabled = !writable(view.ref);
                button.addEventListener('click', guarded(run));
                actions.append(button);
            }
            body.append(actions);
        }
        dock.append(head, body);
        const tile = (role) => {
            const item = document.createElement('button');
            item.type = 'button';
            item.disabled = !writable(view.ref);
            item.setAttribute('aria-pressed', String(placing?.role === role));
            const name = document.createElement('span');
            name.textContent = roleLabel(role);
            const id = document.createElement('span');
            id.className = 'ddn-palette-id';
            id.textContent = role;
            item.append((0, element_preview_js_1.elementPreview)(document, role, (0, native_js_2.str)(view.record.profile)), name, id);
            item.title = `${roleLabel(role)} (${role}) — drag onto the view, or click then place; double-click to add it in the middle`;
            item.draggable = !item.disabled;
            item.addEventListener('dragstart', event => {
                if (!writable(view.ref) || !event.dataTransfer) {
                    event.preventDefault();
                    return;
                }
                cancelPlacing();
                paletteDrag = { role, view, revision: revision() };
                event.dataTransfer.effectAllowed = 'copy';
                event.dataTransfer.setData('application/x-ddn-element', role);
                handle.announce(`Drop ${roleLabel(role)} on this view. It will join the automatic layout when connected.`);
            });
            item.addEventListener('dragend', () => { paletteDrag = undefined; });
            item.addEventListener('click', () => {
                startPlacing(role, view);
                for (const other of list.querySelectorAll('button'))
                    other.setAttribute('aria-pressed', String(other === item));
            });
            item.addEventListener('dblclick', () => { cancelPlacing(); run(() => createElementAt(view, role, visibleCentre(view))); });
            return item;
        };
        const render = () => {
            const q = search.value.trim().toLowerCase();
            paletteSearchValue = search.value;
            list.replaceChildren();
            if (dataBound)
                return;
            const matches = roles.filter(role => (q || paletteSection === 'All elements' || (0, palette_groups_js_1.paletteGroup)(role) === paletteSection) && (!q || role.includes(q) || roleLabel(role).toLowerCase().includes(q)));
            list.setAttribute('aria-label', q ? 'Search results across all element types' : paletteSection);
            if (!matches.length) {
                const empty = document.createElement('p');
                empty.className = 'ddn-palette-empty';
                empty.textContent = roles.length ? 'No element type matches.' : 'No element types available.';
                list.append(empty);
                return;
            }
            const groups = new Map();
            const recent = recentRoles.filter(role => matches.includes(role));
            if (recent.length && !q && paletteSection === 'All elements')
                groups.set('Recently used', recent);
            for (const role of matches) {
                const group = (0, palette_groups_js_1.paletteGroup)(role);
                if (!groups.has(group))
                    groups.set(group, []);
                groups.get(group).push(role);
            }
            for (const [group, members] of groups) {
                const heading = document.createElement('div');
                heading.className = 'ddn-palette-group';
                heading.textContent = `${group} · ${members.length}`;
                const grid = document.createElement('div');
                grid.className = 'ddn-palette-grid';
                for (const role of members)
                    grid.append(tile(role));
                list.append(heading, grid);
            }
        };
        renderPalette = render;
        search.addEventListener('input', render);
        search.addEventListener('keydown', event => {
            if (event.key === 'Escape') {
                event.stopPropagation();
                if (search.value) {
                    search.value = '';
                    render();
                }
                else
                    (0, drawer_js_1.drawerFor)(handle.container, 'palette')?.setMode('hidden');
            }
        });
        render();
        paletteDock = dock;
        paletteDock.dataset.viewKey = (0, native_js_2.refKey)(view.ref) + ':' + (0, native_js_2.str)(view.record.profile);
        if (!reuse)
            handle.container.append(dock);
        const existingDrawer = (0, drawer_js_1.drawerFor)(handle.container, 'palette');
        if (existingDrawer)
            existingDrawer.setHeader(head);
        else
            (0, drawer_js_1.createDrawer)(dock, { id: 'palette', title: 'Element palette', container: handle.container, header: head, closeLabel: 'Close the palette', width: 400,
                onMode(mode) { handle.container.toggleAttribute('data-ddn-dock-left', mode === 'docked'); buttons['Add element']?.setAttribute('aria-pressed', String(mode !== 'hidden')); },
                onHide() { paletteDrag = undefined; cancelPlacing(); },
                onBlocked() { handle.announce('The browser blocked the new window. The palette floats here; allow pop-ups to move it to another monitor.'); } });
        if (!reuse)
            search.focus();
    }
    function refreshPaletteForView() {
        if (!paletteDock)
            return;
        const view = currentView();
        if (!view) {
            closePaletteDock();
            return;
        }
        if (paletteDock.dataset.viewKey === (0, native_js_2.refKey)(view.ref) + ':' + (0, native_js_2.str)(view.record.profile))
            return;
        const owner = paletteDock.ownerDocument, activeDocument = owner.hasFocus() ? owner : document;
        const previousFocus = activeDocument.activeElement;
        const hadFocus = owner.hasFocus() && paletteDock.contains(previousFocus);
        cancelPlacing();
        openPaletteDock(paletteDock);
        if (hadFocus)
            paletteDock.querySelector('input')?.focus();
        else if (previousFocus?.isConnected)
            previousFocus.focus({ preventScroll: true });
    }
    function visibleCentre(view) {
        const vb = handle.viewport(), visible = { x: vb.bounds.x, y: vb.bounds.y, width: vb.bounds.width / vb.zoom, height: vb.bounds.height / vb.zoom };
        const frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(view.ref));
        const fb = frame ? semanticBounds(frame) : undefined;
        const cx = visible.x + visible.width / 2, cy = visible.y + visible.height / 2;
        if (!fb || (cx >= fb.x && cx <= fb.x + fb.width && cy >= fb.y && cy <= fb.y + fb.height))
            return { x: cx, y: cy };
        return { x: fb.x + fb.width / 2, y: fb.y + fb.height / 2 };
    }
    let placePreview;
    function startPlacing(role, view) {
        placing = { role, view };
        handle.container.classList.add('ddn-placing');
        handle.announce(`${roleLabel(role)}: click on the view where it should go (hold Shift to place several). Esc cancels.`);
    }
    function cancelPlacing() {
        placePreview?.remove();
        placePreview = undefined;
        if (!placing)
            return;
        placing = undefined;
        handle.container.classList.remove('ddn-placing');
        for (const other of paletteDock?.querySelectorAll('.ddn-palette-grid button') ?? [])
            other.setAttribute('aria-pressed', 'false');
    }
    async function createElementAt(view, role, point) {
        if (!writable(view.ref))
            throw Error('This view belongs to a read-only file.');
        const profile = (0, native_js_2.str)(view.record.profile);
        const frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(view.ref));
        const origin = frame ? semanticBounds(frame) : { x: 0, y: 0 };
        const local = logicalPoint(frame, point);
        const position = { x: Math.max(0, Math.round(local.x - origin.x)), y: Math.max(0, Math.round(local.y - origin.y)) };
        const before = new Set((handle.scene()?.entries ?? []).map(e => e.item.occurrence));
        const receipt = await apply({ kind: 'profile-command', profile, command: 'ddn.create-element', target: view.ref, arguments: jsonValue({ view: view.ref, role, position }) });
        recentRoles = [role, ...recentRoles.filter(r => r !== role)].slice(0, 6);
        renderPalette?.();
        const changed = new Set(receipt.changed.map(native_js_2.refKey));
        const created = handle.scene()?.entries.find(e => (0, native_js_2.refKey)(e.view.ref) === (0, native_js_2.refKey)(view.ref) && e.definition.owner === 'definition' && !before.has(e.item.occurrence) && changed.has((0, native_js_2.refKey)(e.definition.ref)));
        if (created) {
            handle.select(created.definition.ref, created.item.occurrence);
            inlineRename(created, true);
        }
        else
            handle.announce(`${roleLabel(role)} added.`);
        return created;
    }
    async function reflowView(view = currentView()) {
        if (!view || (0, core_js_1.getProfile)((0, native_js_2.str)(view.record.profile))?.projection !== 'graph')
            throw Error('Choose a diagram view to reflow.');
        if (!writable(view.ref))
            throw Error('This view belongs to a read-only file.');
        cancelPlacing();
        const frame = handle.scene()?.entries.find(entry => entry.definition.owner === 'view' && (0, native_js_2.refKey)(entry.definition.ref) === (0, native_js_2.refKey)(view.ref));
        const patches = (0, layout_edit_js_1.reflowViewPatches)(handle.runtime, view.ref, (0, native_js_2.str)((0, native_js_2.pathValue)(frame?.effective, 'layout.algorithm')) || undefined);
        if (patches.length)
            await apply({ kind: 'edit-source', patches });
        else
            await handle.refresh();
        handle.announce(`Reflowed ${(0, native_js_2.titleOf)(view.record)} using its diagram layout.${patches.length ? ' Fixed positions have been released. Undo restores the previous layout.' : ''}`);
    }
    function reuseItem() {
        const snapshot = handle.runtime.snapshot(), view = currentView();
        if (!snapshot || !view)
            return;
        const profile = (0, core_js_1.getProfile)((0, native_js_2.str)(view.record.profile));
        if (!profile)
            return;
        const eligible = new Set([...profile.primary_palette, ...profile.context_roles, ...profile.relation_roles]);
        const candidates = (0, native_js_2.records)(snapshot).filter(record => record.owner === 'definition' && eligible.has((0, native_js_2.str)(record.record.role)));
        panel('Reuse an existing item', body => {
            const select = document.createElement('select');
            select.setAttribute('aria-label', 'Shared item');
            candidates.forEach((record, index) => { const option = document.createElement('option'); option.value = String(index); option.textContent = `${(0, native_js_2.titleOf)(record.record)} (${(0, native_js_2.str)(record.record.role)}, ${record.file})`; select.append(option); });
            body.append(select);
            return async () => {
                const record = candidates[Number(select.value)];
                if (!record)
                    throw Error('No eligible existing item is available.');
                await apply({ kind: 'create-occurrence', view: view.ref, target: record.ref });
            };
        });
    }
    function workareaSettings() {
        if (standalone())
            return;
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const workarea = (0, native_js_2.records)(snapshot).find(record => record.owner === 'workarea' && record.file === snapshot.rootFile);
        if (!workarea)
            return;
        const references = (0, native_js_2.records)(snapshot).map(record => ({ ref: record.ref, label: `${(0, native_js_2.titleOf)(record.record)} (${record.owner})` }));
        panel('Workarea settings', body => {
            const choice = document.createElement('select');
            choice.setAttribute('aria-label', 'Workarea property');
            choice.dataset.ddnLiveIgnore = '';
            for (const key of ['background', 'grid', 'viewport', 'method', 'allowed_profiles', 'allow_foreign_views', 'style', 'size'])
                if ((0, schema_editor_js_1.childSchema)(schema_core_js_1.codex.roots.workarea, key) !== undefined) {
                    const option = document.createElement('option');
                    option.value = key;
                    option.textContent = key;
                    choice.append(option);
                }
            const controls = document.createElement('div');
            body.append(choice, controls);
            let editor = (0, schema_editor_js_1.createFieldEditor)(controls, (0, schema_editor_js_1.childSchema)(schema_core_js_1.codex.roots.workarea, choice.value), jsonValue(workarea.record[choice.value]), references, 'Workarea.' + choice.value);
            let section = choice.value;
            choice.addEventListener('change', event => {
                event.stopPropagation();
                const next = choice.value;
                choice.value = section;
                run(async () => { await (0, live_settings_js_1.flushLiveSettings)(body); section = next; choice.value = next; controls.replaceChildren(); const current = (0, native_js_2.records)(handle.runtime.snapshot()).find(record => (0, native_js_2.refKey)(record.ref) === (0, native_js_2.refKey)(workarea.ref)); editor = (0, schema_editor_js_1.createFieldEditor)(controls, (0, schema_editor_js_1.childSchema)(schema_core_js_1.codex.roots.workarea, section), jsonValue(current?.record[section]), references, 'Workarea.' + section); });
            });
            return async () => { await applyProperties(workarea.ref, { [section]: editor.read() }); };
        });
    }
    function newElement() {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const view = currentView();
        if (!view) {
            addView();
            return;
        }
        const profile = (0, native_js_2.str)(view.record.profile);
        const role = profile === 'mindmap.basic@1' || profile === 'concept.map@1' ? 'object' : profile === 'table.records@1' ? 'dataset' : profile === 'ddn@1' ? 'entity' : (0, core_js_1.getProfile)(profile)?.primary_palette[0];
        if (!role) {
            handle.announce('This view type has no element to add directly. Use its projection settings or dataset instead.');
            return;
        }
        run(() => createElementAt(view, role, visibleCentre(view)));
    }
    function isErdView(view = currentView()) { return !!view && (0, native_js_2.str)(view.record.profile) === 'ddn@1' && (0, native_js_2.array)(view.record.subtype).includes('erd'); }
    let renameBox, cancelRename = () => { };
    function inlineRename(entry = requireSelection(), isNew = false) {
        cancelRename();
        if (!writable(entry.definition.ref))
            throw Error('This element belongs to a read-only file.');
        const openedRevision = revision();
        const group = handle.surface.querySelector(`[data-occurrence="${CSS.escape(entry.item.occurrence)}"]`);
        const frame = group?.getBoundingClientRect(), host = handle.overlays.getBoundingClientRect();
        if (!group || !frame || frame.width === 0 || frame.right < host.left || frame.left > host.right || frame.bottom < host.top || frame.top > host.bottom) {
            guarded(() => editTitle(entry))();
            return;
        }
        const input = document.createElement('input');
        input.className = 'ddn-inline-rename';
        input.setAttribute('aria-label', 'Element name');
        const current = (0, native_js_2.str)(entry.definition.record.title) || (0, native_js_2.str)(entry.definition.record.name);
        input.value = isNew && /^<.*>$/.test(current) ? '' : current;
        input.placeholder = isNew ? roleLabel((0, native_js_2.str)(entry.definition.record.role, 'element')) : 'Name';
        input.style.left = `${Math.max(4, frame.left - host.left + 8)}px`;
        input.style.top = `${Math.max(4, frame.top - host.top + 8)}px`;
        input.style.width = `${Math.max(140, Math.min(frame.width - 16, host.width - 16))}px`;
        let done = false;
        const finish = (commit) => {
            if (done)
                return;
            done = true;
            const value = input.value.trim();
            input.remove();
            renameBox = undefined;
            handle.surface.focus({ preventScroll: true });
            if (commit && value && value !== current)
                run(async () => { requireCurrent(openedRevision); await renameTitle(entry, value); });
            else if (!commit && isNew)
                handle.announce('Kept the placeholder name — double-click the element to rename it later.');
        };
        input.addEventListener('keydown', event => {
            event.stopPropagation();
            if (event.key === 'Enter') {
                event.preventDefault();
                finish(true);
            }
            else if (event.key === 'Escape') {
                event.preventDefault();
                finish(false);
            }
        });
        input.addEventListener('blur', () => finish(true));
        cancelRename = () => finish(false);
        renameBox = input;
        handle.overlays.append(input);
        input.focus();
        input.select();
        handle.announce(isNew ? 'Type a name for the new element, then press Enter.' : 'Type the new name, then press Enter.');
    }
    function sourceEditor() {
        const toggleEvt = new CustomEvent('ddn:toggle-source', { bubbles: true, cancelable: true });
        if (!handle.container.dispatchEvent(toggleEvt))
            return;
        const input = handle.runtime.sources();
        if (!input)
            return;
        panel('DDN source', body => {
            const select = document.createElement('select');
            for (const file of input.files) {
                const option = document.createElement('option');
                option.value = file.id;
                option.textContent = file.id;
                select.append(option);
            }
            body.append(select);
            let file = input.files.find(f => f.id === input.entry) ?? input.files[0];
            select.value = file.id;
            const editor = field(body, 'Source', file.text, true);
            editor.style.minHeight = '300px';
            let changed = false;
            editor.addEventListener('input', () => { changed = true; });
            select.addEventListener('change', () => {
                if (changed) {
                    select.value = file.id;
                    handle.announce('Apply or cancel your current source edit before switching files.');
                    return;
                }
                file = input.files.find(f => f.id === select.value);
                editor.value = file.text;
            });
            return async () => { await apply({ kind: 'edit-source', patches: [{ file: file.id, base: file.revision, start: 0, end: file.text.length, text: editor.value }] }); };
        });
    }
    function deleteItem(entry = requireSelection()) {
        if ((0, mindmap_actions_js_1.mindmapSelection)(handle, entry)) {
            deleteTopic(entry);
            return;
        }
        const snapshot = handle.runtime.snapshot(), all = snapshot ? (0, native_js_2.records)(snapshot) : [];
        const key = (0, native_js_2.refKey)(entry.definition.ref);
        const isRelation = entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints);
        const connections = all.filter(record => record.owner === 'definition' && Array.isArray(record.record.endpoints) && record.record.endpoints.some(end => {
            const target = (0, native_js_2.resolveRecord)(all, (0, native_js_2.object)(end).definition, record.file);
            return target && (0, native_js_2.refKey)(target.ref) === key;
        })).length;
        const name = (0, native_js_2.titleOf)(entry.definition.record);
        return panel(isRelation ? 'Delete connection' : 'Delete element', body => {
            body.closest('.ddn-ui-dialog')?.querySelector('[data-ddn-apply]')?.replaceChildren('Delete');
            const text = document.createElement('p');
            text.textContent = isRelation ? `Delete the connection "${name}"?` : connections ? `Delete "${name}" and its ${connections} connection${connections === 1 ? '' : 's'}? It disappears from every view it appears in.` : `Delete "${name}"? It disappears from every view it appears in.`;
            const advanced = document.createElement('details'), summary = document.createElement('summary');
            summary.textContent = 'Advanced';
            const retain = document.createElement('input');
            retain.type = 'checkbox';
            const label = document.createElement('label');
            label.append(retain, document.createTextNode('Keep the dangling references and list them as problems instead of removing them'));
            advanced.append(summary, label);
            body.append(text, advanced);
            return async () => {
                await apply({ kind: 'remove', target: entry.definition.ref, references: retain.checked ? 'retain-diagnostic' : 'remove-dependents' });
                handle.announce(`Deleted ${name}. Ctrl+Z undoes it.`);
            };
        });
    }
    async function commitMindmap(draft) { await apply({ kind: 'edit-source', patches: draft.patches() }); }
    function editTopicName(entry) {
        panel('Edit topic name', body => {
            const input = field(body, 'Topic name', (0, native_js_2.titleOf)(entry.definition.record));
            return async () => {
                if (!input.value.trim())
                    throw Error('Enter a topic name.');
                const draft = (0, mindmap_source_js_1.mindmapSource)(handle.runtime, entry.view.ref);
                if ((0, index_js_1.findNode)(draft.decoded, entry.definition.ref)?.generated)
                    draft.materialize();
                draft.set(entry.definition.ref, 'title', input.value);
                await commitMindmap(draft);
            };
        });
    }
    async function addTopic(entry, side) {
        const topology = (0, mindmap_actions_js_1.mindmapSelection)(handle, entry);
        if (!topology || !topology[side])
            throw Error('New topics must continue away from the incoming relationship.');
        const draft = (0, mindmap_source_js_1.mindmapSource)(handle.runtime, entry.view.ref);
        draft.materialize();
        const name = draft.unique('New topic'), id = draft.unique('mindmap-topic'), relation = draft.unique('Branch');
        draft.append(entry.view.file, (0, index_js_1.encodeDefinition)({ id, name, role: 'object' }));
        draft.append(entry.view.file, `connect ${draft.reference(entry.definition.ref)} to ${(0, index_js_1.quoteText)(name)} as assoc named ${(0, index_js_1.quoteText)(relation)}`);
        draft.append(entry.view.file, `use ${(0, index_js_1.quoteText)(name)}\nuse ${(0, index_js_1.quoteText)(relation)}\n    with\n        route.source_side ${side === 'left' ? 'west' : 'east'}`, entry.view.ref);
        await commitMindmap(draft);
        const created = handle.scene()?.entries.find(item => item.definition.ref.id === id && item.definition.file === entry.view.file && (0, native_js_2.refKey)(item.view.ref) === (0, native_js_2.refKey)(entry.view.ref));
        if (created) {
            handle.select(created.definition.ref, created.item.occurrence);
            editTopicName(created);
        }
    }
    async function addSiblingTopic(entry) {
        const topology = (0, mindmap_actions_js_1.mindmapSelection)(handle, entry);
        if (!topology)
            return;
        const parentLink = topology.internal.find(link => (0, native_js_2.refKey)(link.to.ref) === (0, native_js_2.refKey)(entry.definition.ref));
        const parentEntry = parentLink ? handle.scene()?.entries.find(item => (0, native_js_2.refKey)(item.definition.ref) === (0, native_js_2.refKey)(parentLink.from.ref) && (0, native_js_2.refKey)(item.view.ref) === (0, native_js_2.refKey)(entry.view.ref)) : undefined;
        const target = parentEntry ?? entry;
        const targetTopology = (0, mindmap_actions_js_1.mindmapSelection)(handle, target);
        const side = targetTopology?.right ? 'right' : targetTopology?.left ? 'left' : 'right';
        await addTopic(target, side);
    }
    function topicNotes(entry) { notes(entry, true); }
    function deleteTopic(entry) {
        const topology = (0, mindmap_actions_js_1.mindmapSelection)(handle, entry);
        if (!topology)
            return;
        const descendants = new Set([(0, native_js_2.refKey)(entry.definition.ref)]);
        for (let changed = true; changed;) {
            changed = false;
            for (const link of topology.internal)
                if (descendants.has((0, native_js_2.refKey)(link.from.ref)) && !descendants.has((0, native_js_2.refKey)(link.to.ref))) {
                    descendants.add((0, native_js_2.refKey)(link.to.ref));
                    changed = true;
                }
        }
        panel('Delete topic', body => {
            const message = document.createElement('p');
            message.textContent = `Delete ${(0, native_js_2.titleOf)(entry.definition.record)} from every view where it is used, together with its linked relationships?`;
            body.append(message);
            const cascade = document.createElement('input');
            cascade.type = 'checkbox';
            if (descendants.size > 1) {
                const label = document.createElement('label');
                label.append(cascade, `Also delete its ${descendants.size - 1} descendant topic(s)`);
                body.append(label);
            }
            return async () => {
                if (descendants.size > 1 && !cascade.checked)
                    throw Error('This topic has children. Move them first or explicitly include its descendants.');
                const draft = (0, mindmap_source_js_1.mindmapSource)(handle.runtime, entry.view.ref);
                draft.materialize();
                const removed = new Set(cascade.checked ? descendants : [(0, native_js_2.refKey)(entry.definition.ref)]), all = (0, index_js_2.listRecords)(draft.decoded.normalized);
                const mentions = (value, file) => { const target = (0, index_js_2.resolveReference)(draft.decoded.normalized, file, value); return !!target && removed.has((0, native_js_2.refKey)(target.ref)); };
                for (const item of all)
                    if (item.kind === 'definition' && item.record.category === 'relation' && (0, index_js_2.asArray)(item.record.endpoints).some(end => mentions((0, index_js_2.asRecord)(end).definition, item.file)))
                        removed.add((0, native_js_2.refKey)(item.ref));
                for (const item of all)
                    if (item.kind === 'appearance' && mentions(item.record.target, item.file))
                        removed.add((0, native_js_2.refKey)(item.ref));
                for (const item of all.filter(item => item.kind === 'view')) {
                    for (const path of ['selection.include', 'selection.items', 'sources']) {
                        const value = (0, native_js_2.pathValue)(item.record, path);
                        if (Array.isArray(value) && value.some(ref => mentions(jsonValue(ref), item.file)))
                            draft.set(item.ref, path, value.filter(ref => !mentions(jsonValue(ref), item.file)));
                    }
                    if (mentions((0, index_js_2.asRecord)(item.record.layout).root, item.file))
                        draft.set(item.ref, 'layout.root', undefined);
                }
                const targets = all.filter(item => removed.has((0, native_js_2.refKey)(item.ref))).sort((a, b) => Number(b.kind === 'appearance') - Number(a.kind === 'appearance'));
                for (const item of targets) {
                    const node = (0, index_js_1.findNode)(draft.decoded, item.ref);
                    if (!node || node.implicit)
                        continue;
                    const hidden = (0, index_js_2.listRecords)(draft.decoded.normalized).find(other => {
                        if (removed.has((0, native_js_2.refKey)(other.ref)) || other.kind === 'note' || other.file !== item.file)
                            return false;
                        const nested = (0, index_js_1.findNode)(draft.decoded, other.ref);
                        return !!nested && nested.start >= node.start && nested.end <= node.end;
                    });
                    if (hidden)
                        throw Error('This source block contains other topics or a view that were not selected for deletion. Delete from its owning mind map or move those topics first.');
                }
                for (const item of targets) {
                    const node = (0, index_js_1.findNode)(draft.decoded, item.ref);
                    if (node && !node.implicit)
                        draft.apply((0, index_js_1.deleteDeclaration)(draft.decoded, item.ref));
                }
                await commitMindmap(draft);
            };
        });
    }
    const guarded = (fn) => () => {
        try {
            fn();
        }
        catch (error) {
            notifyError(error);
        }
    };
    const isPinned = (entry = selected()) => !!entry && typeof entry.appearance?.record.position === 'object' && entry.appearance?.record.pinned !== false;
    async function togglePin(entry = requireSelection()) {
        if (entry.definition.owner === 'view' || entry.definition.record.category === 'relation')
            return;
        const name = (0, native_js_2.titleOf)(entry.definition.record);
        if (isPinned(entry) && entry.appearance) {
            await applyProperties(entry.appearance.ref, { position: undefined, pinned: undefined });
            handle.announce(`Unpinned "${name}" — it now places dynamically and reroutes connections.`);
        }
        else {
            const frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(entry.view.ref));
            const origin = frame ? semanticBounds(frame) : { x: 0, y: 0 };
            const local = logicalPoint(entry, semanticBounds(entry));
            const pos = { x: Math.max(0, Math.round(local.x - origin.x)), y: Math.max(0, Math.round(local.y - origin.y)) };
            if (entry.appearance)
                await nativeCommand('ddn.set-position', entry.appearance.ref, pos);
            else
                await apply({ kind: 'create-occurrence', view: entry.view.ref, target: entry.definition.ref, properties: { position: pos } });
            handle.announce(`Pinned "${name}" at (${pos.x}, ${pos.y}).`);
        }
    }
    const tooltips = { 'Add element': 'Open the element palette — click a type, then click where it goes (A)', 'Add existing element': 'Show an element that already exists in another view here', 'Connect': 'Connect two elements: click the first, then the second — or drag from a selected element\'s handle (C)', 'Add view': 'Add another view (diagram) to this document', 'Add entity': 'Add an ERD entity to this view (ERD views only)', 'Workarea': 'Workarea settings — background, grid, allowed diagram types', 'Style': 'Set drawing style (hand-drawn, classic, clean, neo) and theme for workarea, view or element', 'Font': 'Set font family, size and text colour for workarea, view or element', 'Border': 'Set border style, width and colour for workarea, view or element', 'Shadow': 'Set shadow, paper surface and attachments for view or element', 'Pin': 'Pin or unpin the selected element in this view — unpinned elements place dynamically', 'Rename': 'Rename the selected element (F2, or double-click it)', 'Properties': 'Open the inspector for the selected element — name, description, colours, lock (P)', 'Draft': 'Free-form text inside the element', 'Columns': 'Turn the draft text into fields', 'Table': 'Edit the element\'s table rows', 'Details': 'Choose which details (columns) are shown', 'Paper & attachments': 'Paper surface, shadow, pins and tape for the selected element', 'Symbol & label': 'How the element is drawn: card, image symbol or bare text, and where its name sits', 'Appearance & presets': 'Colours, fonts, textures and saved presets', 'Profile details': 'Notation-specific details for this element', 'Projection': 'How this data-bound view is projected (chart, matrix, …)', 'Datasets': 'Datasets that feed data-bound views', 'Status': 'Design status: in progress, in review, accepted', 'Source': 'Edit the DDN source of a file in a dialog', 'Delete': 'Delete the selected element (Delete key)', 'Undo': 'Undo (Ctrl+Z)', 'Redo': 'Redo (Ctrl+Shift+Z)' };
    const buttons = {};
    tooltips['Add element'] = 'Open the element palette — drag a type onto the view, or click a type then its position (A)';
    tooltips.Reflow = 'Release fixed and pinned element positions in this view, then arrange it using its diagram type and connections (undoable)';
    const add = (label, action) => { const element = button(label, action); element.title = tooltips[label] ?? ''; buttons[label] = element; return element; };
    add('Add element', () => openPaletteDock()).dataset.primary = '';
    add('Add existing element', reuseItem);
    const connectButton = add('Connect', () => {
        if (connectFrom || connectArmed) {
            connectFrom = undefined;
            connectArmed = false;
            handle.announce('Connect cancelled.');
            updateToolbar();
            return;
        }
        const source = selected();
        const target = source && source.definition.owner !== 'view' && source.definition.record.category !== 'relation' ? source.definition.ref : undefined;
        if (!target) {
            handle.announce('Connect: click the first element, then the second. Drag from a selected element\'s handle to do it in one move.');
            connectArmed = true;
            updateToolbar();
            return;
        }
        connectFrom = target;
        handle.announce(`Connect from "${(0, native_js_2.titleOf)(selected().definition.record)}" — now click the target element. Esc cancels.`);
        updateToolbar();
    });
    add('Add view', () => addView());
    add('Add entity', newElement);
    add('Workarea', workareaSettings);
    add('Reflow', () => run(() => reflowView()));
    add('Rename', guarded(() => inlineRename()));
    add('Properties', guarded(() => openInspectorDock()));
    add('Pin', () => run(() => togglePin()));
    add('Draft', guarded(() => editDraft()));
    add('Columns', guarded(() => convert()));
    add('Table', guarded(() => editRows()));
    add('Details', guarded(() => details()));
    add('Paper & attachments', guarded(() => paperAttachments()));
    add('Symbol & label', guarded(() => (0, symbol_js_1.openSymbol)(viewer, panel, applyProperties)));
    add('Appearance & presets', guarded(() => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties)));
    add('Profile details', guarded(() => profileEditor()));
    add('Projection', guarded(() => profileEditor(true)));
    add('Status', guarded(() => statusDialog()));
    add('Delete', guarded(() => deleteItem()));
    add('Style', guarded(() => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties, 'Style')));
    add('Font', guarded(() => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties, 'Font')));
    add('Border', guarded(() => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties, 'Border')));
    add('Shadow', guarded(() => paperAttachments()));
    add('Datasets', datasets);
    add('Source', sourceEditor);
    add('Undo', () => run(async () => {
        const result = await commands.undo();
        if (!result.ok)
            throw new Error(result.failure.diagnostics.map(d => d.message).join('\n'));
        await handle.refresh();
    }));
    add('Redo', () => run(async () => {
        const result = await commands.redo();
        if (!result.ok)
            throw new Error(result.failure.diagnostics.map(d => d.message).join('\n'));
        await handle.refresh();
    }));
    const selectionName = document.createElement('span');
    selectionName.className = 'ddn-selection-name';
    toolbarGroups.get('Selection')?.prepend(selectionName);
    for (const name of ['Document', 'History', 'Selection'])
        if (toolbarGroups.get(name))
            toolbar.append(toolbarGroups.get(name));
    const moreLabels = ['Draft', 'Columns', 'Table', 'Details', 'Profile details', 'Status'];
    const moreButton = document.createElement('button');
    moreButton.type = 'button';
    moreButton.append(document.createTextNode('More'), (0, ui_icons_js_1.uiIcon)(document, 'chevron'));
    moreButton.title = 'Text, columns, table rows, details, notation specifics and design status';
    moreButton.setAttribute('aria-haspopup', 'menu');
    moreButton.setAttribute('aria-expanded', 'false');
    toolbarGroups.get('Selection')?.insertBefore(moreButton, buttons['Delete'] ?? null);
    moreButton.addEventListener('click', () => {
        if (menu) {
            menu.remove();
            menu = undefined;
            moreButton.setAttribute('aria-expanded', 'false');
            return;
        }
        menu = document.createElement('div');
        menu.className = 'ddn-designer-menu';
        menu.setAttribute('role', 'menu');
        for (const label of moreLabels) {
            const source = buttons[label];
            if (!source || source.hidden)
                continue;
            const item = document.createElement('button');
            item.textContent = label === 'Draft' ? 'Draft text' : label === 'Details' ? 'Details shown' : label === 'Table' ? 'Edit table' : label;
            item.setAttribute('role', 'menuitem');
            item.disabled = source.disabled;
            item.title = source.title;
            item.addEventListener('click', () => { menu?.remove(); menu = undefined; moreButton.setAttribute('aria-expanded', 'false'); source.click(); });
            menu.append(item);
        }
        handle.overlays.append(menu);
        const bounds = handle.overlays.getBoundingClientRect(), rect = moreButton.getBoundingClientRect();
        menu.style.left = `${Math.max(4, Math.min(rect.left - bounds.left, bounds.width - menu.getBoundingClientRect().width - 4))}px`;
        menu.style.top = '4px';
        moreButton.setAttribute('aria-expanded', 'true');
        menu.querySelector('button:not(:disabled)')?.focus();
    });
    let connectArmed = false;
    function updateToolbar() {
        const entry = selected();
        const isRelation = !!entry && (entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints));
        const isView = !!entry && entry.definition.owner === 'view';
        const view = currentView();
        const erd = isErdView(view);
        const profile = view ? (0, core_js_1.getProfile)((0, native_js_2.str)(view.record.profile)) : undefined;
        const dataBound = profile ? profile.projection !== 'graph' : false;
        const graphView = !!view && !dataBound;
        const has = (label) => buttons[label];
        has('Add entity').hidden = !erd;
        has('Add element').hidden = !!view && !profile?.primary_palette.length;
        has('Add existing element').hidden = !graphView;
        has('Connect').hidden = !graphView;
        for (const label of ['Add entity', 'Add existing element', 'Connect'])
            has(label).disabled = !!view && !writable(view.ref);
        has('Add element').disabled = !!view && !writable(view.ref);
        has('Workarea').hidden = standalone();
        has('Add view').hidden = standalone();
        has('Reflow').disabled = !graphView || !view || !writable(view.ref);
        has('Projection').hidden = !dataBound && !isView;
        has('Datasets').hidden = !dataBound;
        const selectionGroup = toolbarGroups.get('Selection');
        if (selectionGroup)
            selectionGroup.dataset.empty = String(!entry);
        selectionName.textContent = entry ? (isRelation ? 'Connection: ' : isView ? 'View: ' : '') + (0, native_js_2.titleOf)(entry.definition.record) : 'Click an element to edit it — or right-click it';
        const elementOnly = ['Draft', 'Columns', 'Table', 'Details', 'Symbol & label', 'Paper & attachments', 'Profile details'];
        for (const label of elementOnly)
            has(label).hidden = !entry || isRelation || isView;
        has('Pin').hidden = !entry || isRelation || isView || !graphView;
        has('Pin').disabled = !entry || !writable(entry.view.ref);
        has('Pin').setAttribute('aria-pressed', String(isPinned(entry)));
        for (const label of ['Style', 'Font', 'Border', 'Shadow'])
            has(label).disabled = !!view && !writable(view.ref);
        for (const label of moreLabels)
            has(label).dataset.inMenu = '';
        moreButton.hidden = !entry || isRelation || isView;
        has('Rename').hidden = !entry;
        has('Rename').disabled = !!entry && !writable(entry.definition.ref);
        has('Delete').disabled = !!entry && !writable(entry.definition.ref);
        has('Properties').hidden = !entry;
        has('Appearance & presets').hidden = !entry;
        has('Status').hidden = !entry || isRelation;
        has('Delete').hidden = !entry || isView;
        for (const label of ['Draft', 'Columns', 'Table', 'Details'])
            has(label).disabled = !entry || !writable(entry.definition.ref) || !(entry.definition.record.draft || entry.definition.record.data || entry.definition.record.content || label === 'Draft');
        has('Connect').setAttribute('aria-pressed', String(!!connectFrom || connectArmed));
        has('Connect').replaceChildren((0, ui_icons_js_1.uiIcon)(document, 'link'), document.createTextNode(connectFrom ? 'Click the target…' : connectArmed ? 'Click the first element…' : 'Connect'));
        has('Undo').disabled = false;
        has('Redo').disabled = false;
        updatePortHandles();
        (0, ui_commands_js_1.notifyUICommands)(handle.container);
    }
    cleanups.push(viewer.subscribe(event => {
        if (event.kind === 'ready' || event.kind === 'viewport' || event.kind === 'selection') {
            updateToolbar();
            refreshPaletteForView();
            if (inspectorDock && event.kind === 'ready')
                renderInspector();
        }
    }));
    on(handle.container, 'ddn:action', event => {
        const action = event.detail?.action;
        if (action === 'palette')
            openPaletteDock();
        else if (action === 'add-view')
            addView();
        else if (action === 'choose-view-type')
            guarded(chooseViewType)();
        else if (action === 'activate-view-tools') {
            const view = currentView();
            if (view)
                run(() => activateView(view));
        }
    });
    let inspectorDock, inspectorToken = 0;
    let inspectorLive, inspectorApplying = false, inspectorEntryKey = '', inspectorSection = 'all';
    function openInspectorDock() {
        if (!selected())
            throw new Error('Select an element first.');
        if (!inspectorDock) {
            inspectorDock = document.createElement('section');
            inspectorDock.className = 'ddn-designer-dock ddn-designer-dock-right';
            inspectorDock.setAttribute('aria-label', 'Inspector');
            handle.container.append(inspectorDock);
            handle.container.setAttribute('data-ddn-dock-right', '');
        }
        const drawer = (0, drawer_js_1.drawerFor)(handle.container, 'inspector');
        if (drawer?.mode === 'hidden')
            drawer.setMode('docked');
        drawer?.detached?.focus();
        renderInspector();
    }
    function closeInspectorDock() { inspectorLive?.dispose(); inspectorLive = undefined; inspectorToken++; (0, drawer_js_1.drawerFor)(handle.container, 'inspector')?.destroy(); inspectorDock?.remove(); inspectorDock = undefined; handle.container.removeAttribute('data-ddn-dock-right'); }
    async function renderInspector() {
        if (!inspectorDock)
            return;
        const entry = selected();
        const entryKey = entry ? (0, native_js_2.refKey)(entry.definition.ref) + '::' + (0, native_js_2.refKey)(entry.view.ref) + '::' + entry.item.occurrence : '';
        if (inspectorApplying && inspectorEntryKey === entryKey)
            return;
        inspectorLive?.dispose();
        inspectorLive = undefined;
        inspectorEntryKey = entryKey;
        const token = ++inspectorToken;
        const pendingEdits = new Map();
        const edit = (key, action) => {
            if (token !== inspectorToken)
                return;
            pendingEdits.set(key, action);
            inspectorLive?.request();
        };
        const dock = inspectorDock;
        dock.replaceChildren();
        const head = document.createElement('div');
        head.className = 'ddn-dock-head';
        head.append((0, ui_icons_js_1.uiIcon)(document, 'settings'), document.createTextNode('Inspector'));
        const body = document.createElement('div');
        body.className = 'ddn-dock-body';
        const sectionLayout = document.createElement('div');
        sectionLayout.className = 'ddn-panel-sections';
        const content = document.createElement('div');
        content.className = 'ddn-panel-section';
        const tabs = (0, side_tabs_js_1.sideTabs)(sectionLayout, 'Inspector sections', [{ id: 'all', label: 'All settings', icon: 'settings' }, { id: 'identity', label: 'Identity', icon: 'type' }, { id: 'appearance', label: 'Appearance', icon: 'palette' }, { id: 'actions', label: 'Actions', icon: 'layers' }], inspectorSection, id => { inspectorSection = id; filterSections(); });
        tabs.connect(content);
        sectionLayout.append(content);
        body.append(sectionLayout);
        dock.append(head, body);
        let drawer = (0, drawer_js_1.drawerFor)(handle.container, 'inspector');
        if (drawer)
            drawer.setHeader(head);
        else
            drawer = (0, drawer_js_1.createDrawer)(dock, { id: 'inspector', title: 'Inspector', container: handle.container, header: head, side: 'right', closeLabel: 'Close the inspector', width: 420,
                onMode(mode) { handle.container.toggleAttribute('data-ddn-dock-right', mode === 'docked'); },
                onHide() { void inspectorLive?.flush().catch(notifyError); },
                onBlocked() { handle.announce('The browser blocked the new window. The inspector floats here; allow pop-ups to move it to another monitor.'); } });
        function filterSections() {
            for (const child of content.children) {
                const section = child;
                section.hidden = inspectorSection !== 'all' && section.dataset.inspectorSection !== inspectorSection;
            }
            tabs.label(content);
        }
        if (!entry) {
            const empty = document.createElement('p');
            empty.className = 'ddn-dock-help';
            empty.textContent = 'Select an element, connection or view to see and change its properties here.';
            content.append(empty);
            return;
        }
        const isRelation = entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints);
        const isView = entry.definition.owner === 'view';
        const role = (0, native_js_2.str)(entry.definition.record.role);
        const descriptor = role ? (0, core_js_1.roleDescriptor)(role, isRelation ? 'relation' : 'element') : undefined;
        const kind = document.createElement('div');
        kind.className = 'ddn-dock-kind';
        const swatch = document.createElement('span');
        swatch.className = 'ddn-dock-swatch';
        swatch.style.background = (0, native_js_2.str)(descriptor?.render?.fill, (0, native_js_2.str)(descriptor?.render?.colour, 'transparent'));
        swatch.style.borderColor = (0, native_js_2.str)(descriptor?.render?.colour, '');
        const kindText = document.createElement('span');
        kindText.textContent = isView ? 'View · ' + (0, view_picker_js_1.profileDisplayName)((0, native_js_2.str)(entry.definition.record.profile, 'ddn@1')) : role ? roleLabel(role, isRelation ? 'relation' : 'element') : 'Element';
        const kindId = document.createElement('small');
        kindId.textContent = role ? ` ${role}` : '';
        kind.append(swatch, kindText, kindId);
        content.append(kind);
        if (!isRelation && !isView) {
            const state = (0, native_js_2.str)((0, native_js_2.pathValue)(entry.definition.record, 'design.state'), 'draft');
            const statusLine = document.createElement('p');
            statusLine.className = 'ddn-dock-help';
            statusLine.textContent = 'Design status: ' + ({ draft: 'draft — the amber dot on the element', 'in-progress': 'in progress — the blue dot on the element', 'in-review': 'in review — the purple dot on the element', accepted: 'accepted — the green dot on the element' }[state] ?? state) + '. Change it under Design status… below.';
            content.append(statusLine);
        }
        const fieldFor = (label, value, multiline = false) => { const wrap = document.createElement('label'); wrap.append(document.createTextNode(label)); const input = document.createElement(multiline ? 'textarea' : 'input'); input.value = value ?? ''; wrap.append(input); content.append(wrap); return input; };
        const name = fieldFor(isRelation ? 'Label' : 'Name', (0, native_js_2.str)(entry.definition.record.title) || (0, native_js_2.str)(entry.definition.record.name));
        name.disabled = !writable(entry.definition.ref);
        name.addEventListener('input', () => { const value = name.value.trim(); edit('title', () => renameTitle(entry, value)); });
        name.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                name.blur();
            }
        });
        if (isRelation) {
            const snapshot = handle.runtime.snapshot(), all = snapshot ? (0, native_js_2.records)(snapshot) : [];
            const ends = (0, native_js_2.array)(entry.definition.record.endpoints).map(end => { const record = (0, native_js_2.resolveRecord)(all, (0, native_js_2.object)(end).definition, entry.definition.file); return record ? (0, native_js_2.titleOf)(record.record) : '?'; });
            const info = document.createElement('p');
            info.className = 'ddn-dock-help';
            info.textContent = ends.length ? `${ends[0]} → ${ends.slice(1).join(', ')}` : '';
            content.append(info);
        }
        const description = fieldFor('Description', (0, native_js_2.str)(entry.definition.record.description), true);
        description.disabled = !explicitEditable(entry.definition.ref);
        description.addEventListener('input', () => { const value = description.value; edit('description', () => set(entry.definition.ref, 'description', value)); });
        const identityChildren = [...content.children];
        const scopes = [];
        if (entry.appearance && explicitEditable(entry.appearance.ref))
            scopes.push({ label: 'This appearance only', ref: entry.appearance.ref, help: 'Changes how this element looks in this view only.' });
        if (!isView && explicitEditable(entry.definition.ref))
            scopes.push({ label: isRelation ? 'This connection everywhere' : 'This element everywhere', ref: entry.definition.ref, help: 'Changes the shared element, so every view that shows it follows.' });
        if (isView && explicitEditable(entry.definition.ref))
            scopes.push({ label: 'This view', ref: entry.definition.ref, help: 'Changes the whole view.' });
        if (scopes.length) {
            const scopeWrap = document.createElement('label');
            scopeWrap.append(document.createTextNode('Apply appearance to'));
            const scope = document.createElement('select');
            scopes.forEach((item, index) => scope.add(new Option(item.label, String(index))));
            scopeWrap.append(scope);
            content.append(scopeWrap);
            const scopeHelp = document.createElement('p');
            scopeHelp.className = 'ddn-dock-help';
            scopeHelp.textContent = scopes[0].help;
            content.append(scopeHelp);
            scope.dataset.ddnLiveIgnore = '';
            let chosenScope = 0, scopeLoading = true;
            scope.addEventListener('change', () => {
                const next = Number(scope.value), live = inspectorLive;
                scopeLoading = true;
                row.inert = true;
                scope.disabled = true;
                void live?.flush().then(async () => {
                    if (token !== inspectorToken || !dock.isConnected)
                        return;
                    chosenScope = next;
                    scopeHelp.textContent = scopes[chosenScope].help;
                    await fill();
                }).catch(error => {
                    if (token === inspectorToken && dock.isConnected) {
                        scope.value = String(chosenScope);
                        scopeLoading = false;
                        row.inert = false;
                        scope.disabled = false;
                        notifyError(error);
                    }
                });
            });
            const row = document.createElement('div');
            row.className = 'ddn-dock-row';
            content.append(row);
            const colour = (label, path) => {
                const wrap = document.createElement('label');
                wrap.append(document.createTextNode(label));
                const input = document.createElement('input');
                input.type = 'color';
                wrap.append(input);
                row.append(wrap);
                input.addEventListener('input', () => {
                    if (scopeLoading)
                        return;
                    const target = scopes[chosenScope].ref, value = input.value;
                    edit(path, () => applyProperties(target, { [path]: value }));
                });
                return input;
            };
            const background = colour('Background', 'background.color'), text = colour('Text', 'text.color');
            const size = (0, dialogs_js_1.numberField)(row, 'Font size (pt)', 12, { min: 6, max: 48, step: .5 });
            size.step = 'any';
            size.addEventListener('input', () => {
                if (scopeLoading)
                    return;
                const value = size.valueAsNumber * 4 / 3, target = scopes[chosenScope].ref;
                if (size.checkValidity() && Number.isFinite(value))
                    edit('style.font_size', () => applyProperties(target, { 'style.font_size': value }));
            });
            const opacity = (0, dialogs_js_1.numberField)(row, 'Opacity (0–1)', 1, { min: 0, max: 1, step: .01 });
            opacity.step = 'any';
            opacity.addEventListener('input', () => {
                if (scopeLoading)
                    return;
                const value = opacity.valueAsNumber, target = scopes[chosenScope].ref;
                if (opacity.checkValidity() && Number.isFinite(value))
                    edit('opacity', () => applyProperties(target, { opacity: value }));
            });
            let fillToken = 0;
            const fill = async () => {
                const request = ++fillToken, target = scopes[chosenScope].ref;
                scopeLoading = true;
                row.inert = true;
                scope.disabled = true;
                try {
                    const inspected = await viewer.inspect(target);
                    if (request !== fillToken || token !== inspectorToken || !dock.isConnected)
                        return;
                    const get = (path) => inspected.properties.find(p => p.path === path)?.effective;
                    const supported = inspected.properties.some(p => p.path === 'opacity');
                    for (const input of opacity.closest('.ddn-ui-number-field').querySelectorAll('input')) {
                        input.disabled = !supported;
                        input.title = supported ? '' : 'Opacity is available on an explicit appearance or view.';
                    }
                    const toHex = (value) => typeof value === 'string' && /^#[0-9a-f]{6}$/i.test(value) ? value : typeof value === 'string' && /^#[0-9a-f]{3}$/i.test(value) ? '#' + value.slice(1).split('').map(c => c + c).join('') : undefined;
                    background.value = toHex(get('background.color')) ?? '#ffffff';
                    text.value = toHex(get('text.color')) ?? '#1f2933';
                    const fontSize = get('style.font_size');
                    size.value = typeof fontSize === 'number' ? String(fontSize * 3 / 4) : '12';
                    (0, dialogs_js_1.syncNumberField)(size);
                    const alpha = get('opacity');
                    opacity.value = typeof alpha === 'number' ? String(alpha) : '1';
                    (0, dialogs_js_1.syncNumberField)(opacity);
                }
                catch (error) {
                    if (request === fillToken && token === inspectorToken && dock.isConnected)
                        notifyError(error);
                }
                finally {
                    if (request === fillToken && token === inspectorToken && dock.isConnected) {
                        scopeLoading = false;
                        row.inert = false;
                        scope.disabled = false;
                    }
                }
            };
            void fill();
        }
        const movable = entry.appearance ?? entry.placement;
        if (movable && !isView && explicitEditable(movable.ref)) {
            for (const [kind, label] of [['move', 'Lock position (cannot be dragged)'], ['resize', 'Lock size (cannot be resized)']]) {
                const lockWrap = document.createElement('label'), lock = document.createElement('input');
                lock.type = 'checkbox';
                lock.checked = geometryLocked(entry, kind);
                lockWrap.append(lock, document.createTextNode(' ' + label));
                content.append(lockWrap);
                lock.addEventListener('change', () => { const value = lock.checked; edit('locked.' + kind, () => set(movable.ref, 'locked.' + kind, value)); });
            }
        }
        const appearanceChildren = [...content.children].filter(child => !identityChildren.includes(child));
        const actions = document.createElement('div');
        actions.className = 'ddn-dock-actions';
        const action = (label, fn, danger = false) => {
            const b = document.createElement('button');
            b.type = 'button';
            b.textContent = label;
            if (danger)
                b.dataset.danger = '';
            b.addEventListener('click', () => run(async () => {
                const live = inspectorLive;
                await live?.flush();
                if (token === inspectorToken && dock.isConnected)
                    guarded(fn)();
            }));
            actions.append(b);
        };
        action('All properties…', () => properties());
        action('Appearance & presets…', () => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties));
        if (!isRelation) {
            action('Paper & attachments…', () => paperAttachments());
            action('Design status…', () => statusDialog());
        }
        if (!isRelation && !isView) {
            action('Symbol & label…', () => (0, symbol_js_1.openSymbol)(viewer, panel, applyProperties));
            action('Comments…', () => notes());
        }
        if (!isView)
            action('Delete…', () => deleteItem(), true);
        content.append(actions);
        for (const child of identityChildren)
            child.dataset.inspectorSection = 'identity';
        for (const child of appearanceChildren)
            child.dataset.inspectorSection = 'appearance';
        actions.dataset.inspectorSection = 'actions';
        filterSections();
        const error = document.createElement('p');
        error.className = 'ddn-dock-help';
        error.setAttribute('role', 'status');
        body.append(error);
        inspectorLive = (0, live_settings_js_2.createLiveSettings)({ body, commands, async submit() {
                const jobs = [...pendingEdits.values()];
                pendingEdits.clear();
                for (const action of jobs) {
                    if (token !== inspectorToken)
                        return;
                    await inspectorLive.group.run(action);
                }
            }, showError(failure) { error.textContent = failure instanceof Error ? failure.message : failure ? String(failure) : ''; }, onState(state) {
                if (token === inspectorToken)
                    inspectorApplying = state.busy;
            } });
    }
    let portGroup, connectDrag;
    function updatePortHandles() {
        portGroup?.remove();
        portGroup = undefined;
        const entry = selected();
        if (!entry || entry.definition.owner === 'view' || entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints) || (0, mindmap_actions_js_1.mindmapSelection)(handle, entry) || !writable(entry.view.ref) || !canMove(entry))
            return;
        const view = entry.view, profile = (0, core_js_1.getProfile)((0, native_js_2.str)(view.record.profile));
        if (!profile || profile.projection !== 'graph' || !profile.relation_roles.length)
            return;
        const b = semanticBounds(entry), NS = 'http://www.w3.org/2000/svg';
        const vb = handle.viewport(), rect = handle.surface.getBoundingClientRect();
        const scale = rect.width > 0 && rect.height > 0 ? Math.min(rect.width / (vb.bounds.width / vb.zoom), rect.height / (vb.bounds.height / vb.zoom)) : 1;
        const r = Math.max(5, 7 / scale);
        portGroup = document.createElementNS(NS, 'g');
        portGroup.setAttribute('class', 'ddn-ports');
        portGroup.setAttribute('aria-hidden', 'true');
        for (const [px, py] of [[b.x + b.width, b.y + b.height / 2], [b.x + b.width / 2, b.y + b.height], [b.x, b.y + b.height / 2], [b.x + b.width / 2, b.y]]) {
            const port = document.createElementNS(NS, 'circle');
            port.setAttribute('class', 'ddn-port');
            port.setAttribute('cx', String(px));
            port.setAttribute('cy', String(py));
            port.setAttribute('r', String(r));
            port.setAttribute('vector-effect', 'non-scaling-stroke');
            const title = document.createElementNS(NS, 'title');
            title.textContent = 'Drag to connect to another element';
            port.append(title);
            port.addEventListener('pointerdown', event => {
                if (event.button !== 0 || pinching || connectDrag)
                    return;
                event.preventDefault();
                const line = document.createElementNS(NS, 'path');
                line.setAttribute('class', 'ddn-connect-line');
                handle.surface.append(line);
                connectDrag = { id: event.pointerId, from: entry, start: { x: px, y: py }, line, revision: JSON.stringify(handle.runtime.snapshot()?.revision) };
                try {
                    handle.surface.setPointerCapture(event.pointerId);
                }
                catch { }
                handle.announce(`Drag to the element "${(0, native_js_2.titleOf)(entry.definition.record)}" should connect to, then release.`);
            });
            portGroup.append(port);
        }
        handle.surface.append(portGroup);
    }
    on(handle.surface, 'pointermove', event => {
        if (!connectDrag || connectDrag.id !== event.pointerId)
            return;
        const point = handle.toWorld(event.clientX, event.clientY);
        connectDrag.line.setAttribute('d', `M${connectDrag.start.x},${connectDrag.start.y}L${point.x},${point.y}`);
        const over = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-occurrence]');
        for (const group of handle.surface.querySelectorAll('.ddn-connect-target'))
            group.classList.remove('ddn-connect-target');
        if (over && over.getAttribute('data-occurrence') !== connectDrag.from.item.occurrence)
            over.classList.add('ddn-connect-target');
    });
    const finishConnectDrag = (event, commit) => {
        if (!connectDrag || (event && connectDrag.id !== event.pointerId))
            return;
        const current = connectDrag;
        connectDrag = undefined;
        current.line.remove();
        if (handle.surface.hasPointerCapture(current.id))
            handle.surface.releasePointerCapture(current.id);
        for (const group of handle.surface.querySelectorAll('.ddn-connect-target'))
            group.classList.remove('ddn-connect-target');
        if (!commit || !event)
            return;
        if (current.revision !== revision()) {
            handle.announce('The diagram changed during the drag. Connect cancelled; try again.');
            return;
        }
        const target = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-occurrence]');
        const entry = target ? handle.scene()?.entries.find(e => e.item.occurrence === target.getAttribute('data-occurrence')) : undefined;
        if (!entry || entry.definition.owner === 'view' || entry.definition.record.category === 'relation' || entry.item.occurrence === current.from.item.occurrence || (0, native_js_2.refKey)(entry.view.ref) !== (0, native_js_2.refKey)(current.from.view.ref)) {
            handle.announce('Release the handle on another element to connect them.');
            return;
        }
        openVerbChooser(current.from.definition.ref, entry.definition.ref, current.from.view);
    };
    on(handle.surface, 'pointerup', event => finishConnectDrag(event, true));
    on(handle.surface, 'pointercancel', event => finishConnectDrag(event, false));
    const commonVerbs = ['assoc', 'flow', 'depends', 'uses', 'calls', 'publish', 'subscribe', 'contains', 'reads', 'writes', 'implements', 'extends', 'owns', 'ref', 'generates', 'delivers', 'triggers', 'queries', 'import', 'export'];
    function openVerbChooser(from, to, view) {
        const inView = handle.scene()?.entries.filter(entry => (0, native_js_2.refKey)(entry.view.ref) === (0, native_js_2.refKey)(view.ref)) ?? [];
        if (![from, to].every(ref => inView.some(entry => (0, native_js_2.refKey)(entry.definition.ref) === (0, native_js_2.refKey)(ref)))) {
            handle.announce('Choose two elements in the same view.');
            return;
        }
        const profile = (0, core_js_1.getProfile)((0, native_js_2.str)(view.record.profile));
        const all = handle.runtime.snapshot() ? (0, native_js_2.records)(handle.runtime.snapshot()) : [];
        const fromRecord = all.find(record => (0, native_js_2.refKey)(record.ref) === (0, native_js_2.refKey)(from)), toRecord = all.find(record => (0, native_js_2.refKey)(record.ref) === (0, native_js_2.refKey)(to));
        const fromRole = (0, native_js_2.str)(fromRecord?.record.role), toRole = (0, native_js_2.str)(toRecord?.record.role);
        const fromName = fromRecord ? (0, native_js_2.titleOf)(fromRecord.record) : 'A', toName = toRecord ? (0, native_js_2.titleOf)(toRecord.record) : 'B';
        const topicKeys = new Set(((0, mindmap_actions_js_1.mindmapSelection)(handle)?.topics ?? []).map(item => (0, native_js_2.refKey)(item.definition.ref)));
        const internalMindmap = view.record.profile === 'mindmap.basic@1' && topicKeys.has((0, native_js_2.refKey)(from)) && topicKeys.has((0, native_js_2.refKey)(to));
        const legal = new Set(profile?.relation_endpoint_contracts.filter(contract => (!internalMindmap || contract.role === 'assoc') && contract.source_roles.includes(fromRole) && contract.target_roles.includes(toRole) && ((0, native_js_2.refKey)(from) !== (0, native_js_2.refKey)(to) || contract.self_allowed)).map(contract => contract.role));
        const verbs = (profile?.relation_roles ?? []).filter(role => legal.has(role));
        if (!verbs.length) {
            handle.announce(`No connection type allows ${fromName} → ${toName} in this diagram type.`);
            return;
        }
        panel('Connect', body => {
            const intro = document.createElement('p');
            intro.className = 'ddn-appearance-message';
            intro.textContent = `${fromName} → ${toName}. Choose what the connection means.`;
            body.append(intro);
            let chosen = verbs.includes('assoc') ? 'assoc' : verbs[0];
            const list = document.createElement('div');
            list.className = 'ddn-verb-list';
            const common = commonVerbs.filter(v => verbs.includes(v)).slice(0, 8);
            const shown = (common.length ? common : verbs.slice(0, 8));
            queueMicrotask(() => {
                const applyButton = body.closest('.ddn-ui-dialog')?.querySelector('[data-ddn-apply]');
                if (applyButton)
                    applyButton.textContent = 'Connect';
            });
            const renderList = (items) => {
                list.replaceChildren();
                for (const verb of items) {
                    const b = document.createElement('button');
                    b.type = 'button';
                    b.setAttribute('aria-pressed', String(verb === chosen));
                    const strong = document.createElement('b');
                    strong.textContent = roleLabel(verb, 'relation');
                    const small = document.createElement('small');
                    small.textContent = verb;
                    b.append(document.createTextNode(fromName + ' '), strong, document.createTextNode(' ' + toName), small);
                    b.addEventListener('click', () => { chosen = verb; renderList(items); more.value = verb; });
                    b.addEventListener('dblclick', () => { chosen = verb; body.closest('.ddn-ui-dialog')?.querySelector('[data-ddn-apply]')?.click(); });
                    list.append(b);
                }
            };
            body.append(list);
            const moreWrap = document.createElement('label');
            moreWrap.append(document.createTextNode(`All ${verbs.length} connection types`));
            const more = document.createElement('select');
            for (const verb of verbs)
                more.add(new Option(`${roleLabel(verb, 'relation')} (${verb})`, verb));
            more.value = chosen;
            moreWrap.append(more);
            body.append(moreWrap);
            more.addEventListener('change', () => { chosen = more.value; renderList(shown.includes(chosen) ? shown : [chosen, ...shown]); });
            renderList(shown);
            const label = internalMindmap ? undefined : field(body, 'Label on the line (optional)');
            return async () => {
                await apply({ kind: 'connect', view: view.ref, from, to, relation: chosen, ...(label?.value ? { properties: { title: label.value } } : {}) });
                handle.announce(`Connected ${fromName} → ${toName} (${roleLabel(chosen, 'relation')}).`);
            };
        });
    }
    const acceptsPaletteDrop = (event) => {
        if (!paletteDrag)
            return false;
        const occurrence = event.target.closest('[data-occurrence]')?.getAttribute('data-occurrence');
        const entry = occurrence && handle.scene()?.entries.find(item => item.item.occurrence === occurrence);
        return !entry || (0, native_js_2.refKey)(entry.view.ref) === (0, native_js_2.refKey)(paletteDrag.view.ref);
    };
    on(handle.surface, 'dragover', event => {
        if (!acceptsPaletteDrop(event))
            return;
        event.preventDefault();
        event.stopPropagation();
        if (event.dataTransfer)
            event.dataTransfer.dropEffect = 'copy';
    });
    on(handle.surface, 'drop', event => {
        if (!acceptsPaletteDrop(event) || !paletteDrag)
            return;
        event.preventDefault();
        event.stopPropagation();
        const drop = paletteDrag;
        paletteDrag = undefined;
        const point = handle.toWorld(event.clientX, event.clientY);
        run(async () => { requireCurrent(drop.revision); await createElementAt(drop.view, drop.role, point); });
    });
    on(handle.surface, 'pointermove', event => {
        if (!placing) {
            placePreview?.remove();
            placePreview = undefined;
            return;
        }
        const point = handle.toWorld(event.clientX, event.clientY);
        if (!placePreview) {
            placePreview = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
            placePreview.setAttribute('class', 'ddn-designer-preview');
            placePreview.setAttribute('width', '140');
            placePreview.setAttribute('height', '64');
            placePreview.setAttribute('rx', '6');
            handle.surface.append(placePreview);
        }
        placePreview.setAttribute('x', String(snap(point.x - 70)));
        placePreview.setAttribute('y', String(snap(point.y - 32)));
    });
    on(handle.surface, 'click', event => {
        if (!placing)
            return;
        if (event.target.closest('.ddn-ports') || event.target.closest('.ddn-inline-rename'))
            return;
        const role = placing.role, view = placing.view;
        const point = handle.toWorld(event.clientX, event.clientY);
        if (!event.shiftKey)
            cancelPlacing();
        run(() => createElementAt(view, role, point));
    });
    updateToolbar();
    cleanups.push(handle.subscribeOpen(() => {
        documentOpenGeneration++;
        resizeDecoded = undefined;
        resizeSources.clear();
        finishGesture(false);
        for (const close of [...panelClosers.values()])
            close();
        closeInspectorDock();
        closePaletteDock();
        cancelRename();
        connectFrom = undefined;
        connectArmed = false;
        finishConnectDrag(undefined, false);
        baseline.clear();
        for (const file of handle.runtime.sources()?.files ?? [])
            baseline.set(file.id, file.text);
    }));
    cleanups.push(viewer.subscribe(event => {
        if (event.kind === 'disposed')
            designer.destroy();
    }));
    cleanups.push(handle.subscribeSelection(ref => {
        updateToolbar();
        if (inspectorDock)
            void renderInspector();
        const chosen = selected();
        const connectable = chosen && chosen.definition.owner !== 'view' && chosen.definition.record.category !== 'relation';
        if (connectArmed && ref && connectable) {
            connectArmed = false;
            connectFrom = ref;
            handle.announce(`Connect from "${(0, native_js_2.titleOf)(selected()?.definition.record ?? {})}" — now click the target element. Esc cancels.`);
            updateToolbar();
            return;
        }
        if (connectFrom && ref && connectable && (0, native_js_2.refKey)(connectFrom) !== (0, native_js_2.refKey)(ref)) {
            const from = connectFrom;
            connectFrom = undefined;
            updateToolbar();
            const view = selected()?.view;
            if (view) {
                openVerbChooser(from, ref, view);
                return;
            }
        }
    }));
    on(handle.surface, 'dblclick', event => {
        const target = event.target.closest('[data-ref]');
        if (!target)
            return;
        const ref = JSON.parse(target.getAttribute('data-ref') ?? 'null');
        handle.select(ref, target.getAttribute('data-occurrence') ?? undefined);
        guarded(() => inlineRename())();
    });
    function openContextMenu(clientX, clientY, target) {
        const entry = target ? handle.scene()?.entries.find(e => e.item.occurrence === target.getAttribute('data-occurrence')) : undefined;
        if (target)
            handle.select(JSON.parse(target.getAttribute('data-ref') ?? 'null'), target.getAttribute('data-occurrence') ?? undefined);
        menu?.remove();
        menu = document.createElement('div');
        menu.className = 'ddn-designer-menu';
        menu.setAttribute('role', 'menu');
        const isRelation = !!entry && (entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints));
        const isView = !!entry && entry.definition.owner === 'view';
        const expected = revision(), targetRef = entry?.appearance?.ref;
        const sourceNode = targetRef && (0, runtime_js_1.runtimeState)(handle.runtime).decoded && (0, index_js_1.findNode)((0, runtime_js_1.runtimeState)(handle.runtime).decoded, targetRef);
        const editableRelation = !!entry && (targetRef ? !!sourceNode && !sourceNode.generated && writable(targetRef)
            : explicitEditable(entry.view.ref) && (!!entry.definition.record.name || explicitEditable(entry.definition.ref)));
        const toggles = isRelation ? (0, relation_menu_js_1.relationMenuItems)(entry, handle.scene()?.entries.find(e => e.definition.owner === 'view' && (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(entry.view.ref))?.effective ?? entry.view.record, editableRelation, (path, value) => run(async () => {
            requireCurrent(expected);
            if (targetRef)
                await applyProperties(targetRef, { [path]: value });
            else
                await apply({ kind: 'create-occurrence', view: entry.view.ref, target: entry.definition.ref, properties: { [path]: value } });
        })) : [];
        const items = !entry ? [['Add element…', () => openPaletteDock()], ['Add existing element…', () => reuseItem()], ['Add view…', () => addView()], ['Appearance & presets', () => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties)], ['Paper & attachments', () => paperAttachments()], ['Fit all', () => void viewer.navigate({ kind: 'fit-workarea' })]]
            : isView ? [['Rename', () => inlineRename()], ['Properties', () => openInspectorDock()], ['Appearance & presets', () => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties)], ['Paper & attachments', () => paperAttachments()], ['Expand view', () => void viewer.navigate({ kind: 'expand-view', target: entry.definition.ref })]]
                : isRelation ? [...toggles, ['Rename label', () => inlineRename()], ['Properties', () => openInspectorDock()], ['Appearance & presets', () => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties)], ['Delete', () => deleteItem()]]
                    : [['Rename', () => inlineRename()], [isPinned(entry) ? 'Unpin position (auto-place)' : 'Pin position in view', () => run(() => togglePin(entry))], ['Connect from here', () => { connectFrom = entry.definition.ref; updateToolbar(); handle.announce(`Connect from "${(0, native_js_2.titleOf)(entry.definition.record)}" — click the target element.`); }], ['Properties', () => openInspectorDock()], ['Appearance & presets', () => (0, appearance_js_1.openAppearance)(viewer, panel, applyProperties)], ['Symbol & label', () => (0, symbol_js_1.openSymbol)(viewer, panel, applyProperties)], ['Paper & attachments', () => paperAttachments()], ['Draft text', () => editDraft()], ['Columns', () => convert()], ['Details shown', () => details()], ['Edit table', () => editRows()], ['Comments', () => notes()], ['Constraints', () => constraints()], ['Status', () => statusDialog()], ['Delete', () => deleteItem()]];
        for (const [label, action, toggle] of items) {
            if (standalone() && ['Add view…', 'Expand view'].includes(label))
                continue;
            const item = document.createElement('button');
            item.type = 'button';
            item.textContent = label;
            item.setAttribute('role', toggle ? 'menuitemcheckbox' : 'menuitem');
            if (toggle) {
                const check = document.createElement('span');
                check.textContent = toggle.checked ? '✓' : '○';
                check.setAttribute('aria-hidden', 'true');
                check.style.cssText = 'display:inline-block;min-width:1.5em';
                item.prepend(check);
                item.setAttribute('aria-label', toggle.name);
                item.setAttribute('aria-checked', String(toggle.checked));
                item.disabled = toggle.disabled;
                item.title = toggle.title;
            }
            item.addEventListener('click', () => { menu?.remove(); menu = undefined; guarded(action)(); });
            menu.append(item);
        }
        menu.addEventListener('keydown', event => {
            event.stopPropagation();
            if (event.key === 'Escape') {
                event.preventDefault();
                menu?.remove();
                menu = undefined;
                handle.surface.focus();
                return;
            }
            if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key))
                return;
            event.preventDefault();
            const buttons = [...menu.querySelectorAll('button:not(:disabled)')], index = buttons.indexOf(document.activeElement);
            const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowUp' ? -1 : 1) + buttons.length) % buttons.length;
            buttons[next]?.focus();
        });
        handle.overlays.append(menu);
        const bounds = handle.overlays.getBoundingClientRect(), size = menu.getBoundingClientRect();
        let left = clientX - bounds.left, top = clientY - bounds.top;
        if (left + size.width > bounds.width - 4)
            left = Math.max(4, clientX - bounds.left - size.width);
        if (top + size.height > bounds.height - 4)
            top = Math.max(4, Math.min(clientY - bounds.top - size.height, bounds.height - size.height - 4));
        menu.style.left = `${left}px`;
        menu.style.top = `${top}px`;
        menu.querySelector('button:not(:disabled)')?.focus();
    }
    on(handle.surface, 'contextmenu', event => {
        event.preventDefault();
        openContextMenu(event.clientX, event.clientY, event.target.closest('[data-ref]'));
    });
    on(handle.overlays, 'pointerdown', event => {
        if (menu && !menu.contains(event.target)) {
            menu.remove();
            menu = undefined;
        }
    });
    on(handle.surface, 'pointerdown', event => {
        if (menu && !menu.contains(event.target)) {
            menu.remove();
            menu = undefined;
        }
    });
    let longPress, pressOrigin, pinching = false;
    const cancelPress = () => { clearTimeout(longPress); longPress = undefined; pressOrigin = undefined; };
    on(handle.container, 'ddn:gesture', event => {
        const kind = event.detail?.gesture;
        if (kind === 'pinch-start') {
            pinching = true;
            cancelPress();
            finishGesture(false);
            finishConnectDrag(undefined, false);
            cancelPlacing();
        }
        else if (kind === 'pinch-end')
            pinching = false;
    });
    on(handle.surface, 'pointerdown', event => {
        if (pinching || event.button !== 0 || placing || connectDrag || event.target.closest('.ddn-element-resize,.ddn-element-resize-handles') || (event.pointerType !== 'touch' && event.pointerType !== 'pen'))
            return;
        cancelPress();
        const { clientX, clientY } = event, target = event.target.closest('[data-ref]');
        pressOrigin = { x: clientX, y: clientY };
        longPress = setTimeout(() => { cancelPress(); finishGesture(false); openContextMenu(clientX, clientY, target); }, 550);
    });
    for (const type of ['pointerup', 'pointercancel', 'pointermove'])
        on(handle.surface, type, event => {
            if (type !== 'pointermove' || (pressOrigin && Math.hypot(event.clientX - pressOrigin.x, event.clientY - pressOrigin.y) > 5))
                cancelPress();
        });
    on(document, 'keydown', event => {
        const target = event.target;
        if (document.querySelectorAll('[data-ddn-editing]').length !== 1 || !(target instanceof Element) || target.closest('.ddn-viewer') || handle.container.contains(target) || target.closest('input,textarea,select,[contenteditable=true],.ddn-ui-dialog') || document.querySelector('.ddn-ui-dialog'))
            return;
        if (event.ctrlKey || event.metaKey || event.altKey || event.shiftKey)
            return;
        if (event.key === 'a') {
            event.preventDefault();
            openPaletteDock();
        }
        else if (event.key === 'c') {
            event.preventDefault();
            buttons['Connect']?.click();
        }
        else if (event.key === 'p' && selected()) {
            event.preventDefault();
            guarded(() => openInspectorDock())();
        }
        else if (event.key === 'F2' && selected()) {
            event.preventDefault();
            guarded(() => inlineRename())();
        }
    });
    on(handle.container, 'keydown', event => {
        const key = event;
        const target = event.target;
        if (key.key === 'Escape') {
            menu?.remove();
            menu = undefined;
            if (connectFrom || connectArmed) {
                connectFrom = undefined;
                connectArmed = false;
                handle.announce('Connect cancelled.');
            }
            cancelPlacing();
            finishConnectDrag(undefined, false);
            updateToolbar();
        }
        if (target.closest('.ddn-ui-dialog') || target.matches('input,textarea,select') || target.isContentEditable)
            return;
        if (key.key === 'F2' && selected()) {
            key.preventDefault();
            guarded(() => inlineRename())();
        }
        if (!key.ctrlKey && !key.metaKey && !key.altKey && !key.shiftKey) {
            if (key.key === 'a') {
                key.preventDefault();
                openPaletteDock();
            }
            else if (key.key === 'c') {
                key.preventDefault();
                buttons['Connect']?.click();
            }
            else if (key.key === 'p' && selected()) {
                key.preventDefault();
                guarded(() => openInspectorDock())();
            }
        }
        if ((key.ctrlKey || key.metaKey) && (key.key.toLowerCase() === 'z' || key.key.toLowerCase() === 'y')) {
            key.preventDefault();
            const isRedo = key.key.toLowerCase() === 'y' || key.shiftKey;
            run(async () => {
                const result = await (isRedo ? commands.redo() : commands.undo());
                if (!result.ok)
                    throw new Error(result.failure.code);
                await handle.refresh();
            });
        }
        if ((key.key === 'Tab' || key.key === 'Insert' || key.key === 'Enter') && !key.ctrlKey && !key.metaKey && !key.altKey && selected()) {
            const mm = (0, mindmap_actions_js_1.mindmapSelection)(handle, selected());
            if (mm) {
                key.preventDefault();
                const entry = selected();
                if (key.key === 'Enter')
                    run(() => addSiblingTopic(entry));
                else
                    run(() => addTopic(entry, mm.right ? 'right' : mm.left ? 'left' : 'right'));
                return;
            }
        }
        if ((key.key === 'Delete' || key.key === 'Backspace') && selected() && selected().definition.owner !== 'view') {
            key.preventDefault();
            const entry = selected();
            if (key.shiftKey && !(0, mindmap_actions_js_1.mindmapSelection)(handle, entry) && writable(entry.definition.ref)) {
                const name = (0, native_js_2.titleOf)(entry.definition.record);
                run(async () => {
                    await apply({ kind: 'remove', target: entry.definition.ref, references: 'remove-dependents' });
                    handle.announce(`Deleted ${name}. Ctrl+Z undoes it.`);
                });
            }
            else {
                guarded(() => deleteItem())();
            }
        }
        if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(key.key)) {
            const entry = selected();
            const movable = entry?.appearance ?? entry?.placement;
            if (!entry || !movable || !writable(movable.ref) || !canMove(entry) || geometryLocked(entry, 'move'))
                return;
            key.preventDefault();
            const position = (0, native_js_2.object)(movable.record.position);
            const bounds = semanticBounds(entry), frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(entry.view.ref));
            const frameBounds = entry.appearance && frame ? semanticBounds(frame) : { x: 0, y: 0 };
            const local = entry.appearance ? logicalPoint(entry, bounds) : bounds;
            const snapping = snapStep(), amount = key.shiftKey && !snapping ? 1 : snapping || 16;
            const nextX = (0, native_js_2.num)(position.x, local.x - frameBounds.x) - Number(key.key === 'ArrowLeft') * amount + Number(key.key === 'ArrowRight') * amount, nextY = (0, native_js_2.num)(position.y, local.y - frameBounds.y) - Number(key.key === 'ArrowUp') * amount + Number(key.key === 'ArrowDown') * amount;
            run(() => nativeCommand('ddn.set-position', movable.ref, { x: snap(nextX), y: snap(nextY) }));
        }
    });
    let gesture;
    const finishGesture = (commit) => {
        if (!gesture)
            return;
        const current = gesture;
        gesture = undefined;
        if (handle.surface.hasPointerCapture(current.id))
            handle.surface.releasePointerCapture(current.id);
        const x = Number(current.rect.getAttribute('x')), y = Number(current.rect.getAttribute('y')), width = Number(current.rect.getAttribute('width')), height = Number(current.rect.getAttribute('height'));
        current.rect.remove();
        const movable = current.entry.appearance ?? current.entry.placement;
        if (!commit || !current.moved || !movable)
            return;
        if (JSON.stringify(handle.runtime.snapshot()?.revision) !== current.revision) {
            handle.announce('The diagram changed during the drag. Move cancelled; try again on the current revision.');
            return;
        }
        const frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && (0, native_js_2.refKey)(e.definition.ref) === (0, native_js_2.refKey)(current.entry.view.ref));
        const frameBounds = current.entry.appearance && frame ? semanticBounds(frame) : { x: 0, y: 0 };
        const initial = semanticBounds(current.entry), position = (0, native_js_2.object)(movable.record.position);
        const scale = surfaceScale(current.entry), local = current.entry.appearance ? logicalPoint(current.entry, initial) : initial;
        const nextPos = { x: snap((0, native_js_2.num)(position.x, local.x - frameBounds.x) + (x - initial.x) / scale), y: snap((0, native_js_2.num)(position.y, local.y - frameBounds.y) + (y - initial.y) / scale) };
        const posChanged = Math.abs(x - initial.x) > 0.5 || Math.abs(y - initial.y) > 0.5;
        run(() => current.resizing ? resizeElement(current.entry, width / scale, height / scale, posChanged ? nextPos : undefined) : nativeCommand('ddn.set-position', movable.ref, nextPos));
    };
    function snapStep() { return (0, grid_js_1.viewSetting)(handle.container, 'snap') === 'on' ? (0, grid_js_1.gridStep)(handle.runtime.snapshot()) : 0; }
    function snap(value) { const step = snapStep(); return step ? Math.round(value / step) * step : value; }
    function beginGesture(entry, pointer, resizing, direction = 'se') {
        handle.select(entry.definition.ref, entry.item.occurrence);
        const position = handle.toWorld(pointer.clientX, pointer.clientY);
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        for (const [key, value] of Object.entries(semanticBounds(entry)))
            rect.setAttribute(key, String(value));
        rect.setAttribute('class', 'ddn-designer-preview');
        gesture = { id: pointer.pointerId, start: position, entry, rect, resizing, direction, moved: false, revision: revision() };
        if (resizing && pointer.pointerType !== 'mouse')
            try {
                handle.surface.setPointerCapture(pointer.pointerId);
            }
            catch { }
    }
    on(handle.surface, 'pointerdown', event => {
        const pointer = event;
        if (pointer.button !== 0 || pinching || placing || connectDrag || pointer.target.closest('.ddn-ports,.ddn-element-resize,.ddn-element-resize-handles'))
            return;
        const group = pointer.target.closest('[data-occurrence]');
        if (!group)
            return;
        const entry = handle.scene()?.entries.find(e => e.item.occurrence === group.getAttribute('data-occurrence'));
        const movable = entry?.appearance ?? entry?.placement;
        if (!entry || !movable || !writable(movable.ref) || !canMove(entry))
            return;
        if (geometryLocked(entry, pointer.altKey ? 'resize' : 'move'))
            return;
        if (pointer.altKey && entry.definition.owner === 'view' && entry.surfaceTransform) {
            handle.announce('This view has a fixed layout size. Change its surface settings to resize it.');
            return;
        }
        if (pointer.altKey && !canResize(entry))
            return;
        beginGesture(entry, pointer, pointer.altKey);
    });
    on(handle.surface, 'pointermove', event => {
        const pointer = event;
        if (!gesture || gesture.id !== pointer.pointerId)
            return;
        const position = handle.toWorld(pointer.clientX, pointer.clientY), dx = position.x - gesture.start.x, dy = position.y - gesture.start.y, bounds = semanticBounds(gesture.entry);
        gesture.moved ||= Math.abs(dx) + Math.abs(dy) > 2;
        if (gesture.moved && !gesture.rect.isConnected) {
            handle.surface.append(gesture.rect);
            handle.surface.setPointerCapture(pointer.pointerId);
        }
        if (gesture.resizing) {
            const minimum = 40 * surfaceScale(gesture.entry);
            const dir = gesture.direction;
            let nextX = bounds.x, nextY = bounds.y, nextW = bounds.width, nextH = bounds.height;
            if (dir.includes('e'))
                nextW = Math.max(minimum, snap(bounds.width + dx));
            if (dir.includes('s'))
                nextH = Math.max(minimum, snap(bounds.height + dy));
            if (dir.includes('w')) {
                const maxDx = bounds.width - minimum;
                const clampedDx = Math.min(maxDx, dx);
                nextX = snap(bounds.x + clampedDx);
                nextW = Math.max(minimum, bounds.x + bounds.width - nextX);
            }
            if (dir.includes('n')) {
                const maxDy = bounds.height - minimum;
                const clampedDy = Math.min(maxDy, dy);
                nextY = snap(bounds.y + clampedDy);
                nextH = Math.max(minimum, bounds.y + bounds.height - nextY);
            }
            gesture.rect.setAttribute('x', String(nextX));
            gesture.rect.setAttribute('y', String(nextY));
            gesture.rect.setAttribute('width', String(nextW));
            gesture.rect.setAttribute('height', String(nextH));
        }
        else {
            gesture.rect.setAttribute('x', String(snap(bounds.x + dx)));
            gesture.rect.setAttribute('y', String(snap(bounds.y + dy)));
        }
    });
    on(handle.surface, 'pointerup', event => {
        if (gesture?.id === event.pointerId)
            finishGesture(true);
    });
    on(handle.surface, 'pointercancel', event => {
        if (gesture?.id === event.pointerId)
            finishGesture(false);
    });
    on(handle.surface, 'lostpointercapture', event => {
        if (gesture?.id === event.pointerId)
            finishGesture(false);
        if (connectDrag?.id === event.pointerId)
            finishConnectDrag(undefined, false);
    });
    on(handle.container, 'keydown', event => {
        if (event.key === 'Escape')
            finishGesture(false);
    });
    if (document.defaultView)
        on(document.defaultView, 'blur', () => { finishGesture(false); finishConnectDrag(undefined, false); cancelPress(); pinching = false; });
    cleanups.push((0, resize_handles_js_1.mountResizeHandles)(viewer, handle, { bounds: semanticBounds, allowed: canResize,
        start(entry, event, direction = 'se') {
            if (event.button !== 0 || pinching || placing || connectDrag || gesture || connectArmed || connectFrom)
                return;
            event.preventDefault();
            cancelPress();
            beginGesture(entry, event, true, direction);
            handle.surface.focus({ preventScroll: true });
        },
        step(entry, dx, dy) {
            const b = semanticBounds(entry), scale = surfaceScale(entry);
            run(async () => {
                await resizeElement(entry, b.width / scale + dx, b.height / scale + dy);
                if (document.activeElement === document.body || document.activeElement === handle.surface)
                    handle.surface.querySelector(`[data-occurrence="${CSS.escape(entry.item.occurrence)}"] > .ddn-element-resize`)?.focus();
            });
        },
    }));
    const copyable = (entry = selected()) => !!entry && entry.definition.owner === 'definition' && entry.definition.record.category !== 'relation' && !Array.isArray(entry.definition.record.endpoints) && !(0, mindmap_actions_js_1.mindmapSelection)(handle, entry);
    const pasteView = () => { const entry = selected(); return entry && entry.definition.owner === 'view' ? entry.view : entry?.view ?? currentView(); };
    const graphView = (view) => !!view && (0, native_js_2.str)(view.record.kind) !== 'document' && (0, core_js_1.getProfile)((0, native_js_2.str)(view.record.profile))?.projection === 'graph';
    let pasteSerial = 0;
    function copySelection() {
        const entry = requireSelection();
        if (!copyable(entry))
            throw Error('Copy works on elements. Views, connections and mind-map topics are not copied yet.');
        const position = (0, native_js_2.object)(entry.appearance?.record.position);
        const item = { record: (0, clipboard_js_1.clipRecord)(entry.definition.record), source: entry.definition.ref, ...(typeof position.x === 'number' && typeof position.y === 'number' ? { position: { x: position.x, y: position.y } } : {}) };
        clipboard = [item];
        pasteSerial = 0;
        clipboardWritten = (0, clipboard_js_1.clipboardText)(clipboard);
        void document.defaultView?.navigator.clipboard?.writeText(clipboardWritten).catch(() => { });
        handle.announce(`Copied "${(0, native_js_2.titleOf)(entry.definition.record)}".`);
        (0, ui_commands_js_1.notifyUICommands)(handle.container);
    }
    async function clipboardItems() {
        try {
            const text = await document.defaultView?.navigator.clipboard?.readText();
            if (text && text !== clipboardWritten) {
                const parsed = (0, clipboard_js_1.parseClipboardText)(text);
                if (parsed.length)
                    return parsed;
            }
        }
        catch { }
        return clipboard;
    }
    async function paste(inPlace, items) {
        const view = pasteView();
        if (!view)
            throw Error('Open or add a view first.');
        if (!graphView(view))
            throw Error('Paste into a diagram view. Data-bound views and documents take datasets and figures instead.');
        if (!writable(view.ref))
            throw Error('This view belongs to a read-only file.');
        const content = items ?? await clipboardItems();
        if (!content.length)
            throw Error('Nothing to paste. Copy an element first.');
        const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded;
        if (!decoded)
            throw Error('The document is not ready.');
        const taken = new Set((0, native_js_2.records)(handle.runtime.snapshot()).filter(r => r.file === view.ref.file).map(r => (0, native_js_2.str)(r.record.name)).filter(Boolean));
        const step = inPlace ? 0 : ++pasteSerial;
        const text = (0, clipboard_js_1.pasteRecords)(content, taken, inPlace ? { x: 0, y: 0 } : { x: 24 * step, y: 24 * step });
        const before = new Set((handle.scene()?.entries ?? []).map(e => e.item.occurrence));
        const receipt = await apply({ kind: 'edit-source', patches: (0, index_js_1.appendDeclaration)(decoded, view.ref.file, text, view.ref) });
        const changed = new Set(receipt.changed.map(native_js_2.refKey));
        const created = handle.scene()?.entries.find(e => (0, native_js_2.refKey)(e.view.ref) === (0, native_js_2.refKey)(view.ref) && e.definition.owner === 'definition' && !before.has(e.item.occurrence) && (changed.has((0, native_js_2.refKey)(e.definition.ref)) || !changed.size));
        if (created)
            handle.select(created.definition.ref, created.item.occurrence);
        handle.announce(`Pasted ${content.length === 1 ? 'one element' : content.length + ' elements'}.`);
    }
    async function pasteReference() {
        const view = pasteView(), source = clipboard[0]?.source;
        if (!view || !source)
            throw Error('Copy an element of this document first.');
        if (!(0, native_js_2.records)(handle.runtime.snapshot()).some(r => (0, native_js_2.refKey)(r.ref) === (0, native_js_2.refKey)(source)))
            throw Error('The copied element no longer exists in this document.');
        await apply({ kind: 'create-occurrence', view: view.ref, target: source });
        handle.announce('Placed the same element in this view.');
    }
    const activeDocument = () => { const view = currentView(); return view && (0, native_js_2.str)(view.record.kind) === 'document' ? view : undefined; };
    function newDocument() {
        if (standalone())
            throw Error('A standalone document contains one view.');
        const snapshot = handle.runtime.snapshot(), decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded;
        if (!snapshot || !decoded)
            throw Error('The document is not ready.');
        const source = currentView(), names = new Set((0, native_js_2.records)(snapshot).map(r => (0, native_js_2.str)(r.record.name)).filter(Boolean));
        panel('New document view', body => {
            const name = field(body, 'Document name', 'Report');
            const output = document.createElement('select');
            output.setAttribute('aria-label', 'Output');
            for (const format of DOCUMENT_OUTPUTS)
                output.add(new Option(format.toUpperCase(), format));
            for (const format of ['PPTX', 'Email']) {
                const option = new Option(format + ' — ScratchWeaver', '');
                option.disabled = true;
                output.add(option);
            }
            const outputLabel = document.createElement('label');
            outputLabel.append('Output', output);
            body.append(outputLabel);
            const pageLayout = document.createElement('select');
            pageLayout.setAttribute('aria-label', 'Page layout');
            for (const [val, text] of [['content', 'Content-sized (default)'], ['letter', 'Letter (8.5 × 11 in)'], ['legal', 'Legal (8.5 × 14 in)'], ['a4', 'A4 (210 × 297 mm)'], ['a3', 'A3 (297 × 420 mm)'], ['tabloid', 'Tabloid (11 × 17 in)']])
                pageLayout.add(new Option(text, val));
            for (const text of ['A1 (594 × 841 mm) — ScratchWeaver', 'A2 (420 × 594 mm) — ScratchWeaver', 'A5 (148 × 210 mm) — ScratchWeaver', 'Custom page — ScratchWeaver', 'Widescreen 16:9 Slide — ScratchWeaver', 'Standard 4:3 Slide — ScratchWeaver']) {
                const option = new Option(text, '');
                option.disabled = true;
                pageLayout.add(option);
            }
            const pageLayoutLabel = document.createElement('label');
            pageLayoutLabel.append('Page layout', pageLayout);
            body.append(pageLayoutLabel);
            const include = document.createElement('input');
            include.type = 'checkbox';
            include.checked = !!source && (0, native_js_2.str)(source.record.kind) !== 'document';
            const includeLabel = document.createElement('label');
            includeLabel.append(include, ` Include the current view${source ? ` (${(0, native_js_2.titleOf)(source.record)})` : ''} as a figure`);
            include.disabled = !source || (0, native_js_2.str)(source.record.kind) === 'document';
            body.append(includeLabel);
            const note = document.createElement('p');
            note.className = 'ddn-dock-help';
            note.textContent = 'A document is a view with output settings: page size, header and footer. Creating it does not render or send anything.';
            body.append(note);
            return async () => {
                const label = name.value.trim();
                if (!label)
                    throw Error('Name the document.');
                if (names.has(label))
                    throw Error('That name is already used in this workarea.');
                const useName = source && include.checked ? (0, native_js_2.str)(source.record.name) : '';
                const pageBlock = pageLayout.value && pageLayout.value !== 'content' ? `    with\n        page.size ${pageLayout.value}\n` : '';
                const text = `document ${(0, index_js_1.quoteText)(label)} as ${output.value}\n` + (useName ? `    use ${source.ref.file === snapshot.rootFile ? '' : (0, index_js_1.quoteText)(source.ref.file) + '::'}${(0, index_js_1.quoteText)(useName)}\n` : '') + pageBlock;
                await apply({ kind: 'edit-source', patches: (0, index_js_1.appendDeclaration)(decoded, snapshot.rootFile, text) });
                const created = handle.scene()?.views.find(v => (0, native_js_2.str)(v.record.name) === label);
                if (created)
                    await viewer.navigate({ kind: 'fit-view', target: created.ref });
            };
        });
    }
    function documentSettings(key) {
        const view = activeDocument();
        if (!view)
            throw Error('Show a document view first (Document › New document view, or pick one in the view list).');
        if (!writable(view.ref))
            throw Error('This document belongs to a read-only file.');
        const snapshot = handle.runtime.snapshot(), references = (0, native_js_2.records)(snapshot).map(record => ({ ref: record.ref, label: `${(0, native_js_2.titleOf)(record.record)} (${record.owner})` }));
        panel(key === 'page' ? 'Page setup' : key === 'header' ? 'Header' : 'Footer', body => {
            const help = document.createElement('p');
            help.className = 'ddn-dock-help';
            help.textContent = 'Leave a setting empty to use the output default. Only what differs is written to the document.';
            body.append(help);
            const editor = (0, schema_editor_js_1.createFieldEditor)(body, (0, schema_editor_js_1.childSchema)(schema_core_js_1.codex.roots.document, key), jsonValue(view.record[key]), references, key === 'page' ? 'Page' : key === 'header' ? 'Header' : 'Footer');
            return async () => { const value = editor.read(); await (value === undefined || value === null ? apply({ kind: 'reset-property', target: view.ref, path: key }) : set(view.ref, key, value)); };
        });
    }
    async function exportDocument() {
        const view = activeDocument();
        if (!view)
            throw Error('Show a document view first.');
        const format = (0, native_js_2.str)(view.record.format, 'pdf');
        const result = await viewer.capture({ scope: { kind: 'document', target: view.ref }, format, extent: 'content', includePreview: false, partial: 'reject', stale: 'reject' });
        if (!result.ok)
            throw Error(result.reason === 'unsupported' ? `No ${format.toUpperCase()} output adapter is installed in this build. Export the figure as SVG or PNG from File › Export, or use ScratchWeaver for managed output.` : result.diagnostics.map(d => d.message).join('; ') || result.reason);
        for (const artifact of result.artifacts) {
            const url = URL.createObjectURL(artifact.blob), link = document.createElement('a');
            link.href = url;
            link.download = artifact.name;
            link.click();
            setTimeout(() => URL.revokeObjectURL(url), 1000);
        }
        handle.announce('Document export requested.');
    }
    function importCsv() {
        const view = pasteView() ?? handle.scene()?.views[0], snapshot = handle.runtime.snapshot();
        if (!snapshot)
            throw Error('The document is not ready.');
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.csv,text/csv';
        input.addEventListener('change', () => run(async () => {
            const file = input.files?.[0];
            if (!file)
                return;
            const table = (0, clipboard_js_1.parseCsv)(await file.text());
            const taken = new Set((0, native_js_2.records)(snapshot).map(r => (0, native_js_2.str)(r.record.name)).filter(Boolean));
            let name = file.name.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'Imported';
            if (/^\d/.test(name))
                name = 'Data_' + name;
            for (let index = 2; taken.has(name); index++)
                name = name.replace(/_\d+$/, '') + '_' + index;
            await nativeCommand('ddn.add-dataset', view?.ref ?? { file: snapshot.rootFile, id: '' }, { name, columns: table.columns.map(column => ({ id: column.id, type: column.type, ...(column.label !== column.id ? { label: column.label } : {}) })), rows: table.rows }, (0, native_js_2.str)(view?.record.profile, 'ddn@1'));
            handle.announce(`Imported ${table.rows.length} rows as the dataset "${name}". Bind it to a view with Projection settings.`);
        }));
        input.click();
    }
    const has = (label) => buttons[label];
    const usable = (label) => { const button = has(label); return !!button && !button.hidden && !button.disabled; };
    const clickCommand = (id, label, title = label) => ({ id, label: title, run: () => has(label)?.click(), enabled: () => usable(label) });
    cleanups.push((0, ui_commands_js_1.registerUICommands)(handle.container, [
        { id: 'edit.undo', label: 'Undo', run: () => has('Undo')?.click() },
        { id: 'edit.redo', label: 'Redo', run: () => has('Redo')?.click() },
        { id: 'edit.cut', label: 'Cut', run: () => { copySelection(); guarded(() => deleteItem())(); }, enabled: () => copyable() && writable(selected().definition.ref) },
        { id: 'edit.copy', label: 'Copy', run: () => copySelection(), enabled: () => copyable() },
        { id: 'edit.paste', label: 'Paste', run: () => run(() => paste(false)), enabled: () => graphView(pasteView()) },
        { id: 'edit.paste-in-place', label: 'Paste in place', run: () => run(() => paste(true)), enabled: () => graphView(pasteView()) },
        { id: 'edit.paste-reference', label: 'Paste as reference', hint: 'Copy an element of this document first.', run: () => run(pasteReference), enabled: () => !!clipboard[0]?.source && graphView(pasteView()) },
        { id: 'edit.duplicate', label: 'Duplicate', run: () => {
                const entry = requireSelection();
                if (!copyable(entry))
                    throw Error('Duplicate works on elements.');
                const position = (0, native_js_2.object)(entry.appearance?.record.position);
                run(() => paste(false, [{ record: (0, clipboard_js_1.clipRecord)(entry.definition.record), ...(typeof position.x === 'number' && typeof position.y === 'number' ? { position: { x: position.x, y: position.y } } : {}) }]));
            }, enabled: () => copyable() && writable(selected().definition.ref) },
        clickCommand('edit.delete', 'Delete'),
        { id: 'edit.select-all', label: 'Select all in view', run: () => {
                const view = currentView();
                const entries = (handle.scene()?.entries ?? []).filter(e => e.definition.owner === 'definition' && (!view || (0, native_js_2.refKey)(e.view.ref) === (0, native_js_2.refKey)(view.ref)));
                if (entries.length) {
                    handle.select(entries[0].definition.ref, entries[0].item.occurrence);
                    for (let i = 1; i < entries.length; i++)
                        handle.select(entries[i].definition.ref, entries[i].item.occurrence, true);
                    handle.announce(`Selected ${entries.length} item${entries.length === 1 ? '' : 's'}.`);
                }
            }, enabled: () => !!(handle.scene()?.entries ?? []).some(e => e.definition.owner === 'definition') },
        { id: 'edit.deselect', label: 'Deselect', run: () => handle.clearSelection(), enabled: () => !!selected() },
        clickCommand('edit.rename', 'Rename'),
        clickCommand('edit.properties', 'Properties'),
        clickCommand('edit.appearance', 'Appearance & presets', 'Appearance & presets…'),
        { id: 'edit.status', label: 'Review status…', run: guarded(() => statusDialog()), enabled: () => usable('Status') },
        clickCommand('workarea.add-element', 'Add element', 'Add element…'),
        clickCommand('workarea.add-existing', 'Add existing element', 'Add existing element…'),
        clickCommand('workarea.connect', 'Connect'),
        clickCommand('workarea.reflow', 'Reflow', 'Reflow view'),
        clickCommand('workarea.add-entity', 'Add entity'),
        { id: 'workarea.add-view', label: 'Add view…', run: () => addView(), enabled: () => !standalone() },
        { id: 'workarea.settings', label: 'Workarea settings…', run: () => workareaSettings(), enabled: () => !standalone() },
        { id: 'workarea.datasets', label: 'Data sources and datasets…', run: () => datasets() },
        { id: 'workarea.import-csv', label: 'Import CSV as dataset…', run: guarded(importCsv) },
        clickCommand('workarea.projection', 'Projection', 'Projection settings…'),
        { id: 'document.new', label: 'New document view…', run: guarded(newDocument), enabled: () => !standalone() },
        { id: 'document.page-setup', label: 'Page setup…', hint: 'Show a document view first.', run: guarded(() => documentSettings('page')), enabled: () => !!activeDocument() },
        { id: 'document.header', label: 'Header…', hint: 'Show a document view first.', run: guarded(() => documentSettings('header')), enabled: () => !!activeDocument() },
        { id: 'document.footer', label: 'Footer…', hint: 'Show a document view first.', run: guarded(() => documentSettings('footer')), enabled: () => !!activeDocument() },
        { id: 'document.export', label: 'Export document…', hint: 'Show a document view first.', run: () => run(exportDocument), enabled: () => !!activeDocument() },
        { id: 'window.inspector', label: 'Inspector', hint: 'Select an element first.', run: value => value === false ? (0, drawer_js_1.drawerFor)(handle.container, 'inspector')?.setMode('hidden') : guarded(() => openInspectorDock())(), enabled: () => !!selected() || !!inspectorDock, checked: () => !!inspectorDock && (0, drawer_js_1.drawerFor)(handle.container, 'inspector')?.mode !== 'hidden' },
        { id: 'window.palette', label: 'Palette', run: value => value === false ? (0, drawer_js_1.drawerFor)(handle.container, 'palette')?.setMode('hidden') : openPaletteDock(), enabled: () => usable('Add element') || !!paletteDock, checked: () => !!paletteDock && (0, drawer_js_1.drawerFor)(handle.container, 'palette')?.mode !== 'hidden' },
    ]));
    cleanups.push((0, mindmap_actions_js_1.mountMindmapActions)(viewer, handle, semanticBounds, { add: addTopic, remove: deleteTopic, name: editTopicName, notes: topicNotes }));
    const designer = { commands, async save(task) {
            if (disposed)
                throw new Error('Designer is destroyed');
            if (task?.cancel?.aborted)
                throw new Error('Save cancelled');
            const opened = documentOpenGeneration, inspector = inspectorLive, editors = [...panels];
            const assertDocument = () => {
                if (disposed || opened !== documentOpenGeneration)
                    throw new Error('The document changed while saving; save the current document again');
                if (task?.cancel?.aborted)
                    throw new Error('Save cancelled');
            };
            const remaining = await (0, live_settings_js_1.waitForSettingsSave)(async () => {
                await inspector?.flush();
                assertDocument();
                for (const dialog of editors) {
                    const body = dialog.querySelector('.ddn-ui-dialog-body');
                    if (body)
                        await (0, live_settings_js_1.flushLiveSettings)(body);
                    assertDocument();
                }
            }, task);
            assertDocument();
            const source = await (0, save_js_1.sourcesForSave)(handle.runtime, remaining), snapshot = handle.runtime.snapshot();
            assertDocument();
            if (!source || !snapshot)
                return [];
            return source.files.map(file => ({ name: file.id, blob: new Blob([file.originalBytes && baseline.get(file.id) === file.text ? new Uint8Array(file.originalBytes).buffer : file.text], { type: 'text/plain;charset=utf-8' }), revision: snapshot.revision }));
        }, isDirty() { const source = handle.runtime.sources(); return !!source && (source.files.length !== baseline.size || source.files.some(file => baseline.get(file.id) !== file.text)); }, destroy() {
            if (disposed)
                return;
            disposed = true;
            resizeDecoded = undefined;
            resizeSources.clear();
            finishGesture(false);
            for (const cleanup of cleanups)
                cleanup();
            for (const dialog of panels)
                panelClosers.get(dialog)?.();
            menu?.remove();
            closePaletteDock();
            closeInspectorDock();
            finishConnectDrag(undefined, false);
            clearTimeout(longPress);
            portGroup?.remove();
            cancelRename();
            handle.container.removeAttribute('data-ddn-editing');
            toolbar.remove();
            css.remove();
            active.delete(viewer);
        } };
    return designer;
}

},
"designer/src/live-settings.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.LIVE_SETTINGS_CHANGE = void 0;
exports.notifyLiveSettings = notifyLiveSettings;
exports.flushLiveSettings = flushLiveSettings;
exports.waitForSettingsSave = waitForSettingsSave;
exports.createLiveSettings = createLiveSettings;
const commands_js_1 = require("runtime/src/commands.js");
const index_js_1 = require("execution/src/index.js");
exports.LIVE_SETTINGS_CHANGE = 'ddn-settings-change';
const sessions = new WeakMap();
function notifyLiveSettings(body) { body.dispatchEvent(new body.ownerDocument.defaultView.Event(exports.LIVE_SETTINGS_CHANGE, { bubbles: true })); }
async function flushLiveSettings(body) { await sessions.get(body)?.flush(); }
async function waitForSettingsSave(flush, task = {}) {
    const started = Date.now(), budget = task.budget;
    if (budget && Object.values(budget).some(value => !Number.isFinite(value) || value < 0))
        throw new RangeError('Invalid operation budget');
    const cancelled = () => new index_js_1.ComputationStopped('cancelled', 'Save cancelled');
    const exhausted = () => new index_js_1.ComputationStopped('budget-exceeded', 'Save time budget exhausted while waiting for live settings');
    if (task.cancel?.aborted)
        throw cancelled();
    await new Promise((resolve, reject) => {
        let finished = false, timer, unlisten;
        const finish = (success, error) => {
            if (finished)
                return;
            finished = true;
            clearTimeout(timer);
            unlisten?.();
            if (success)
                resolve();
            else
                reject(error);
        };
        const deadline = () => {
            if (!budget || finished)
                return;
            const remaining = budget.elapsedMs - (Date.now() - started);
            if (remaining < 0) {
                finish(false, exhausted());
                return;
            }
            timer = setTimeout(deadline, Math.min(remaining + 1, 2147483647));
        };
        unlisten = task.cancel?.onAbort(() => finish(false, cancelled()));
        if (finished) {
            unlisten?.();
            return;
        }
        if (task.cancel?.aborted) {
            finish(false, cancelled());
            return;
        }
        deadline();
        if (!finished)
            void Promise.resolve().then(() => {
                if (!finished)
                    return flush();
            }).then(() => finish(true), error => finish(false, error));
    });
    if (task.cancel?.aborted)
        throw cancelled();
    if (!budget)
        return task;
    const elapsedMs = budget.elapsedMs - (Date.now() - started);
    if (elapsedMs < 0)
        throw exhausted();
    return { ...task, budget: { ...budget, elapsedMs } };
}
function createLiveSettings(options) {
    const { body } = options, group = (0, commands_js_1.createCommandHistoryGroup)(options.commands);
    let pending = false, stopped = false, running, reverting, error;
    const state = () => options.onState?.({ busy: !!running || !!reverting || pending, changed: group.changed, current: group.current, ...(error ? { error } : {}) });
    const report = (value) => { error = value; options.showError(value); state(); };
    async function drain() {
        while (pending && !stopped) {
            pending = false;
            try {
                if (!group.current)
                    throw Error('The diagram changed outside this settings session. Close and reopen the editor to continue.');
                const invalid = [...body.querySelectorAll('input:invalid,textarea:invalid,select:invalid')].find(input => !input.disabled && !input.closest('[inert],[hidden],[data-ddn-live-ignore]') && input.getClientRects().length > 0);
                if (invalid)
                    throw Error('Enter a valid value for ' + (invalid.getAttribute('aria-label') ?? invalid.labels?.[0]?.textContent ?? 'this setting') + '.');
                await group.run(options.submit);
                if (!stopped)
                    report(undefined);
            }
            catch (failure) {
                if (!stopped)
                    report(failure);
            }
        }
    }
    function start() {
        if (!running && pending && !stopped) {
            running = Promise.resolve().then(drain).finally(() => {
                running = undefined;
                state();
                if (pending && !stopped)
                    void start();
            });
            state();
        }
        return running ?? Promise.resolve();
    }
    const session = {
        group,
        request() {
            if (stopped || reverting)
                return;
            pending = true;
            void start();
        },
        async flush() {
            if (reverting)
                await reverting;
            do {
                await start();
            } while (pending && !stopped);
            if (error)
                throw error;
        },
        revert() {
            if (reverting)
                return reverting;
            reverting = (async () => {
                pending = false;
                await running;
                if (!group.changed)
                    return;
                const result = await group.revert();
                if (!result.ok)
                    throw Error(result.failure.diagnostics.map(item => item.message).join('\n') || result.failure.code);
                error = undefined;
                options.showError(undefined);
                await options.afterRevert?.();
            })().finally(() => { reverting = undefined; state(); });
            state();
            return reverting;
        },
        async finish() {
            try {
                await session.flush();
            }
            finally {
                session.dispose();
            }
        },
        dispose() {
            if (stopped)
                return;
            stopped = true;
            pending = false;
            group.close();
            for (const event of ['input', 'change', exports.LIVE_SETTINGS_CHANGE])
                body.removeEventListener(event, changed);
            sessions.delete(body);
            state();
        },
    };
    function changed(event) {
        const target = event.target;
        if (target?.closest?.('[data-ddn-live-ignore]'))
            return;
        if (target?.closest?.('.ddn-ui-dialog') !== body.closest('.ddn-ui-dialog'))
            return;
        session.request();
    }
    for (const event of ['input', 'change', exports.LIVE_SETTINGS_CHANGE])
        body.addEventListener(event, changed);
    sessions.set(body, session);
    state();
    return session;
}

},
"designer/src/mindmap-actions.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.mindmapSelection = mindmapSelection;
exports.mountMindmapActions = mountMindmapActions;
const ui_icons_js_1 = require("viewer/src/ui-icons.js");
const native_js_1 = require("presentation/src/native.js");
const mindmap_js_1 = require("profiles/src/mindmap.js");
function mindmapSelection(handle, selected = handle.selectedEntry()) {
    if (!selected || selected.definition.owner !== 'definition' || selected.view.record.profile !== 'mindmap.basic@1' || !(0, mindmap_js_1.isMindmapTopic)(selected.definition.record) || selected.mindmapTopic === false)
        return;
    const entries = handle.scene()?.entries.filter(item => (0, native_js_1.refKey)(item.view.ref) === (0, native_js_1.refKey)(selected.view.ref)) ?? [];
    const topics = entries.filter(item => item.definition.owner === 'definition' && (0, mindmap_js_1.isMindmapTopic)(item.definition.record) && item.mindmapTopic !== false);
    const keys = new Set(topics.map(item => (0, native_js_1.refKey)(item.definition.ref))), all = handle.runtime.snapshot() ? (0, native_js_1.records)(handle.runtime.snapshot()) : [];
    const internal = entries.filter(item => item.definition.record.category === 'relation' && item.definition.record.role === 'assoc').flatMap(item => {
        const ends = (0, native_js_1.array)(item.definition.record.endpoints).map(native_js_1.object), from = (0, native_js_1.resolveRecord)(all, ends[0]?.definition, item.definition.file), to = (0, native_js_1.resolveRecord)(all, ends[1]?.definition, item.definition.file);
        return from && to && keys.has((0, native_js_1.refKey)(from.ref)) && keys.has((0, native_js_1.refKey)(to.ref)) ? [{ entry: item, from, to }] : [];
    });
    const incoming = internal.find(link => (0, native_js_1.refKey)(link.to.ref) === (0, native_js_1.refKey)(selected.definition.ref));
    const parent = incoming && topics.find(item => (0, native_js_1.refKey)(item.definition.ref) === (0, native_js_1.refKey)(incoming.from.ref));
    const parentRight = !!parent && parent.item.bounds.x + parent.item.bounds.width / 2 > selected.item.bounds.x + selected.item.bounds.width / 2;
    return { selected, topics, internal, incoming, left: !incoming || parentRight, right: !incoming || !parentRight };
}
function mountMindmapActions(viewer, handle, bounds, actions) {
    const document = handle.ownerDocument, bar = document.createElement('div'), css = document.createElement('style');
    bar.className = 'ddn-mindmap-actions';
    bar.setAttribute('role', 'toolbar');
    bar.setAttribute('aria-label', 'Mind map topic actions');
    bar.hidden = true;
    css.textContent = '.ddn-mindmap-actions{position:absolute;z-index:8;display:flex;justify-content:space-evenly;align-items:center;gap:4px;height:30px;pointer-events:none!important}.ddn-mindmap-actions[hidden]{display:none}.ddn-mindmap-actions>button{pointer-events:auto;flex:none;display:grid;place-items:center;min-width:26px;width:26px;height:26px;padding:0;border:1px solid var(--ddn-ui-border);border-radius:50%;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);font-size:15px;line-height:1;box-shadow:0 1px 4px #14243626}.ddn-mindmap-actions>button>svg{width:14px;height:14px}.ddn-mindmap-actions>button:hover{border-color:var(--ddn-ui-accent);background:var(--ddn-ui-surface-alt)}.ddn-mindmap-actions>button:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:2px}';
    handle.container.append(css);
    handle.overlays.append(bar);
    let signature = '', disposed = false;
    const stop = (event) => event.stopPropagation();
    for (const event of ['pointerdown', 'dblclick', 'keydown', 'keyup'])
        bar.addEventListener(event, stop);
    const update = () => {
        if (disposed)
            return;
        const selected = mindmapSelection(handle);
        if (!selected) {
            bar.hidden = true;
            signature = '';
            return;
        }
        const body = bounds(selected.selected), matrix = handle.surface.getScreenCTM(), overlay = handle.overlays.getBoundingClientRect();
        if (!matrix) {
            bar.hidden = true;
            return;
        }
        const point = handle.surface.createSVGPoint();
        point.x = body.x;
        point.y = body.y + body.height;
        const origin = point.matrixTransform(matrix);
        point.x += body.width;
        const end = point.matrixTransform(matrix);
        const width = Math.max(130, end.x - origin.x), center = (origin.x + end.x) / 2 - overlay.left, top = origin.y - overlay.top + 3;
        bar.hidden = top < 0 || top > overlay.height - 26 || center < 0 || center > overlay.width;
        bar.style.left = center - width / 2 + 'px';
        bar.style.top = top + 'px';
        bar.style.width = width + 'px';
        const next = selected.selected.item.occurrence + ':' + selected.left + ':' + selected.right;
        if (next === signature)
            return;
        signature = next;
        bar.replaceChildren();
        const button = (icon, actionName, name, action) => {
            const element = document.createElement('button');
            element.type = 'button';
            element.dataset.action = actionName;
            element.title = name;
            element.setAttribute('aria-label', name);
            element.append((0, ui_icons_js_1.uiIcon)(document, icon));
            element.addEventListener('click', event => {
                event.stopPropagation();
                try {
                    Promise.resolve(action()).catch(error => handle.announce(error instanceof Error ? error.message : String(error)));
                }
                catch (error) {
                    handle.announce(error instanceof Error ? error.message : String(error));
                }
            });
            bar.append(element);
        };
        if (selected.left)
            button('branch-left', 'add-left', 'Add linked topic to the left', () => actions.add(handle.selectedEntry(), 'left'));
        if (selected.right)
            button('branch-right', 'add-right', 'Add linked topic to the right', () => actions.add(handle.selectedEntry(), 'right'));
        button('trash', 'delete', 'Delete topic', () => actions.remove(handle.selectedEntry()));
        button('pen', 'rename', 'Edit topic name', () => actions.name(handle.selectedEntry()));
        button('notes', 'notes', 'Add, edit or delete topic notes', () => actions.notes(handle.selectedEntry()));
    };
    const unsubscribe = viewer.subscribe(event => {
        if (['ready', 'selection', 'viewport'].includes(event.kind))
            update();
    });
    const selection = handle.subscribeSelection(update), Resize = document.defaultView?.ResizeObserver, resize = Resize ? new Resize(update) : undefined;
    resize?.observe(handle.surface);
    update();
    return () => { disposed = true; resize?.disconnect(); unsubscribe(); selection(); bar.remove(); css.remove(); };
}

},
"designer/src/mindmap-source.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.mindmapSource = mindmapSource;
const index_js_1 = require("language/src/index.js");
const index_js_2 = require("model/src/index.js");
const runtime_js_1 = require("runtime/src/runtime.js");
const index_js_3 = require("execution/src/index.js");
const key = (ref) => ref.file + '\0' + ref.id;
const without = (value, keys) => Object.fromEntries(Object.entries(value).filter(([name]) => !keys.includes(name)));
const relativeFile = (from, target) => {
    const parent = from.split('/').slice(0, -1), parts = target.split('/');
    while (parent.length && parts.length && parent[0] === parts[0]) {
        parent.shift();
        parts.shift();
    }
    return [...parent.map(() => '..'), ...parts].join('/');
};
function mindmapSource(runtime, view) {
    const state = (0, runtime_js_1.runtimeState)(runtime), original = state.source;
    if (!original || !state.decoded)
        throw Error('Editable sources are unavailable.');
    let source = original, decoded = state.decoded;
    const used = new Map();
    for (const item of (0, index_js_2.listRecords)(decoded.normalized)) {
        const names = used.get(item.file) ?? new Set();
        names.add(item.ref.id);
        names.add((0, index_js_2.asString)(item.record.name));
        used.set(item.file, names);
    }
    const unique = (stem, file = view.file) => {
        const names = used.get(file) ?? new Set();
        let name = stem, serial = 2;
        while (names.has(name))
            name = stem + ' ' + serial++;
        names.add(name);
        used.set(file, names);
        return name;
    };
    const apply = (patches) => {
        source = (0, index_js_1.applySourcePatches)(source, patches);
        decoded = (0, index_js_1.decodeSources)(source, { previous: decoded });
        if (!decoded.syntaxValid)
            throw Error(decoded.diagnostics.map(item => item.message).join('\n'));
    };
    const record = (ref) => {
        const found = (0, index_js_2.listRecords)(decoded.normalized).find(item => key(item.ref) === key(ref));
        if (!found)
            throw Error('Mind-map source item is unavailable.');
        return found;
    };
    const append = (file, text, parent) => apply((0, index_js_1.appendDeclaration)(decoded, file, text, parent));
    const set = (ref, path, value) => apply((0, index_js_1.patchProperty)(decoded, ref, path, value));
    const reference = (ref) => { const found = record(ref); return (ref.file === view.file ? '' : (0, index_js_1.quoteText)(relativeFile(view.file, ref.file)) + '::') + (0, index_js_1.quoteText)((0, index_js_2.asString)(found.record.name, ref.id)); };
    const materialize = () => {
        const viewNode = (0, index_js_1.findNode)(decoded, view);
        if (!viewNode)
            throw Error('Mind-map view source is unavailable.');
        const nodes = (0, index_js_1.allNodes)(decoded), root = nodes.find(node => node.kind === 'mindmaproot' && node.file === view.file && node.start === viewNode.start);
        if (!root)
            return;
        const previous = decoded, file = source.files.find(item => item.id === view.file);
        const owned = (0, index_js_2.listRecords)(previous.normalized).filter(item => item.file === view.file && (() => {
            const node = (0, index_js_1.findNode)(previous, item.ref);
            return !!node && node.start >= viewNode.start && node.end <= viewNode.end;
        })());
        if (owned.some(item => !['view', 'placement', 'definition', 'appearance', 'note'].includes(item.kind)) || owned.some(item => {
            const node = (0, index_js_1.findNode)(previous, item.ref);
            return item.kind === 'definition' && node?.generated && !['mindmaproot', 'branch'].includes(node.kind);
        }))
            throw Error('This mind-map recipe contains generated data that cannot be safely expanded. Edit that data through its owning editor first.');
        const definitions = owned.filter(item => item.kind === 'definition');
        const names = new Map(definitions.map(item => [key(item.ref), (0, index_js_2.asString)(item.record.name) || unique(item.ref.id === root.ref?.id ? 'Central topic' : item.record.category === 'relation' ? 'Branch' : 'Topic')]));
        const sourceValue = (value) => {
            if (Array.isArray(value))
                return value.map(sourceValue);
            if (!value || typeof value !== 'object')
                return value;
            const object = value;
            if (typeof object.file === 'string' && typeof object.id === 'string') {
                const target = (0, index_js_2.listRecords)(previous.normalized).find(item => item.file === object.file && item.ref.id === object.id);
                const name = names.get(object.file + '\0' + object.id) ?? target?.record.name;
                if (typeof name === 'string')
                    return { ...without(object, ['id']), file: relativeFile(view.file, object.file), name };
                return { ...object, file: relativeFile(view.file, object.file) };
            }
            return Object.fromEntries(Object.entries(value).map(([name, item]) => [name, sourceValue(item)]));
        };
        const refText = (ref) => {
            const target = (0, index_js_2.listRecords)(previous.normalized).find(item => key(item.ref) === key(ref));
            if (!target)
                throw Error('A mind-map reference cannot be preserved.');
            return (ref.file === view.file ? '' : (0, index_js_1.quoteText)(relativeFile(view.file, ref.file)) + '::') + (0, index_js_1.quoteText)(names.get(key(ref)) ?? (0, index_js_2.asString)(target.record.name, ref.id));
        };
        const viewRecord = record(view).record, appearances = owned.filter(item => item.kind === 'appearance');
        const newline = previous.documents.find(doc => doc.file.id === view.file).newline;
        const comments = file.text.slice(viewNode.start, viewNode.end).split(/\r?\n/).filter(line => line.trimStart().startsWith('//')).map(line => line.trimStart());
        const chunks = [comments.join('\n'), `view ${(0, index_js_1.quoteText)((0, index_js_2.asString)(viewRecord.name))} as mindmap.basic@1\n    with\n${(0, index_js_1.serializeProperties)(sourceValue(without(viewRecord, ['name', 'profile'])), '        ')}`];
        for (const appearance of appearances) {
            const target = (0, index_js_2.resolveReference)(previous.normalized, appearance.file, appearance.record.target);
            if (!target)
                throw Error('A mind-map appearance cannot be preserved.');
            chunks.push('    use ' + refText(target.ref) + (appearance.record.name ? ' named ' + (0, index_js_1.quoteText)((0, index_js_2.asString)(appearance.record.name)) : '') + '\n        with\n' + (0, index_js_1.serializeProperties)(sourceValue(without(appearance.record, ['name', 'target', 'parent'])), '            '));
        }
        for (const item of definitions) {
            const value = sourceValue({ ...item.record, name: names.get(key(item.ref)) });
            chunks.push(item.record.category === 'relation'
                ? `relation ${(0, index_js_1.quoteText)((0, index_js_2.asString)(value.name))} as ${(0, index_js_1.quoteText)((0, index_js_2.asString)(value.role))}\n    with\n${(0, index_js_1.serializeProperties)(without(value, ['name', 'role', 'category']), '        ')}`
                : (0, index_js_1.encodeDefinition)(value));
        }
        const text = chunks.filter(Boolean).map(chunk => chunk.replace(/\n+$/, '')).join('\n') + '\n';
        apply([{ file: file.id, base: file.revision, start: viewNode.start, end: viewNode.end, text: text.replace(/\n/g, newline) }]);
        const normalize = (value, root = false) => {
            if (Array.isArray(value))
                return value.map(item => normalize(item));
            if (!value || typeof value !== 'object')
                return value;
            const entries = Object.entries(value);
            const reference = 'file' in value && 'id' in value;
            return Object.fromEntries(entries.filter(([name]) => name !== 'name' || !root && !reference).map(([name, item]) => [name, normalize(item)]));
        };
        const current = new Map((0, index_js_2.listRecords)(decoded.normalized).map(item => [key(item.ref), item]));
        for (const item of (0, index_js_2.listRecords)(previous.normalized)) {
            const next = current.get(key(item.ref));
            if (!next || (0, index_js_3.canonical)(normalize(item.record, true)) !== (0, index_js_3.canonical)(normalize(next.record, true)))
                throw Error('The compact mind map cannot be expanded without changing ' + (0, index_js_2.asString)(item.record.name, item.ref.id) + '. No changes were saved.');
        }
        const fresh = (0, index_js_1.decodeSources)(source), reloaded = new Map((0, index_js_2.listRecords)(fresh.normalized).map(item => [key(item.ref), item]));
        const persistent = new Set([...owned.filter(item => item.kind !== 'placement').map(item => key(item.ref)), ...previous.references.filter(site => site.spelling === 'id' && site.target).map(site => key(site.target))]);
        for (const item of (0, index_js_2.listRecords)(previous.normalized).filter(item => persistent.has(key(item.ref)))) {
            const next = reloaded.get(key(item.ref));
            if (!next || (0, index_js_3.canonical)(normalize(item.record, true)) !== (0, index_js_3.canonical)(normalize(next.record, true)))
                throw Error('An authored identity reference cannot be preserved when expanding this recipe. No changes were saved.');
        }
    };
    const patches = () => original.files.flatMap(file => {
        const next = source.files.find(item => item.id === file.id);
        if (file.text === next.text)
            return [];
        let start = 0, end = file.text.length, nextEnd = next.text.length;
        while (start < end && start < nextEnd && file.text[start] === next.text[start])
            start++;
        while (end > start && nextEnd > start && file.text[end - 1] === next.text[nextEnd - 1]) {
            end--;
            nextEnd--;
        }
        return [{ file: file.id, base: file.revision, start, end, text: next.text.slice(start, nextEnd) }];
    });
    return { get source() { return source; }, get decoded() { return decoded; }, record, unique, reference, append, set, apply, materialize, patches };
}

},
"designer/src/new-diagram.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.newDiagramDialog = newDiagramDialog;
const native_js_1 = require("viewer/src/native.js");
const ui_icons_js_1 = require("viewer/src/ui-icons.js");
const index_js_1 = require("language/src/index.js");
const dialogs_js_1 = require("designer/src/dialogs.js");
const view_picker_js_1 = require("designer/src/view-picker.js");
const view_layout_picker_js_1 = require("designer/src/view-layout-picker.js");
const view_surfaces_js_1 = require("profiles/src/view-surfaces.js");
const profile_loading_js_1 = require("runtime/src/profile-loading.js");
const registry_js_1 = require("runtime/src/registry.js");
const wizardStyle = `
.ddn-document-choices{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0 6px}
.ddn-ui-dialog .ddn-document-choice{display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:9px;min-width:0;padding:18px 12px;border-radius:12px;white-space:normal;text-align:center}
.ddn-document-choice>.ddn-ui-icon{width:36px;height:36px;color:var(--ddn-ui-accent)}
.ddn-document-choice strong{font-size:13px;line-height:1.35;overflow-wrap:anywhere}
.ddn-document-choice small{font-size:11px;line-height:1.4;color:var(--ddn-ui-muted)}
.ddn-workarea-options{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0 0}
.ddn-workarea-option{display:block;min-width:0;border-radius:10px}
.ddn-ui-dialog .ddn-workarea-option button{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:8px;width:100%;min-height:86px;padding:12px;pointer-events:none}
.ddn-workarea-option .ddn-ui-icon{width:28px;height:28px}
.ddn-workarea-option-hints{min-height:46px;padding-top:6px;font-size:11px;line-height:1.4;color:var(--ddn-ui-muted)}
.ddn-workarea-option-hints p[hidden]{display:none}
@media(max-width:340px){.ddn-document-choices{grid-template-columns:1fr}.ddn-ui-dialog .ddn-document-choice{padding:12px}.ddn-document-choice>.ddn-ui-icon{width:28px;height:28px}}
`;
let nextHint = 0;
function newDiagramDialog(viewer, create) {
    const handle = (0, native_js_1.getViewerHandle)(viewer), document = handle.ownerDocument;
    const profiles = (0, profile_loading_js_1.profileLoadingHost)(handle.runtime)?.profiles ?? (0, registry_js_1.registrations)(handle.runtime.registry).profiles ?? [];
    let workareaName = 'Untitled', viewName = 'NewView', mode = 'workarea', layout = 'dynamic';
    const field = (body, caption, value) => {
        const label = document.createElement('label'), input = document.createElement('input');
        input.type = 'text';
        input.value = value;
        input.autocomplete = 'off';
        label.append(document.createTextNode(caption), input);
        body.append(label);
        return input;
    };
    const style = (dialog) => {
        const sheet = document.createElement('style');
        sheet.textContent = wizardStyle;
        dialog.body.prepend(sheet);
        dialog.element.style.setProperty('--ddn-ui-dialog-width', '480px');
    };
    const readName = (input) => {
        if (!input.value.trim()) {
            input.focus();
            throw Error('Enter a workarea name.');
        }
        workareaName = input.value.trim();
    };
    const back = (dialog, label, next) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = label;
        button.addEventListener('click', () => {
            if (dialog.element.getAttribute('aria-busy') === 'true')
                return;
            dialog.close();
            next();
        });
        dialog.footer.prepend(button);
    };
    function chooseDocument() {
        const dialog = (0, dialogs_js_1.createStandardDialog)(handle.overlays, { title: 'New document', cancelLabel: 'Cancel' });
        style(dialog);
        const name = field(dialog.body, 'Workarea name', workareaName);
        const choices = document.createElement('div');
        choices.className = 'ddn-document-choices';
        for (const [value, caption, icon, description] of [
            ['workarea', 'Create WorkArea', 'layers', 'Arrange multiple views and documents in one workarea.'],
            ['standalone', 'Create Standalone View', 'fit', 'Create a single view with a workarea that fits its size.'],
        ]) {
            const button = document.createElement('button');
            button.type = 'button';
            button.className = 'ddn-document-choice';
            button.setAttribute('aria-label', caption);
            const title = document.createElement('strong');
            title.textContent = caption;
            const detail = document.createElement('small');
            detail.textContent = description;
            button.append((0, ui_icons_js_1.uiIcon)(document, icon), title, detail);
            button.addEventListener('click', () => {
                try {
                    readName(name);
                    mode = value;
                    dialog.close();
                    if (mode === 'workarea')
                        setupWorkarea();
                    else
                        chooseLayout();
                }
                catch (error) {
                    dialog.showError(error);
                }
            });
            choices.append(button);
        }
        dialog.body.append(choices);
    }
    function setupWorkarea() {
        const dialog = (0, dialogs_js_1.createStandardDialog)(handle.overlays, { title: 'Create WorkArea', applyLabel: 'Apply', onApply() {
                readName(name);
                dialog.close();
                chooseLayout();
            } });
        style(dialog);
        const name = field(dialog.body, 'Workarea name', workareaName);
        const options = document.createElement('div');
        options.className = 'ddn-workarea-options';
        const hints = document.createElement('div');
        hints.className = 'ddn-workarea-option-hints';
        for (const [caption, icon, text] of [
            ['Settings', 'settings', 'change defaults for the workarea or load a saved template'],
            ['Permissions', 'link', 'setup user permissions for sharing and concurrent editing'],
        ]) {
            const wrapper = document.createElement('span');
            wrapper.className = 'ddn-workarea-option';
            wrapper.tabIndex = 0;
            wrapper.title = text;
            wrapper.setAttribute('role', 'group');
            wrapper.setAttribute('aria-label', `${caption} — unavailable in the open-source designer`);
            const button = document.createElement('button');
            button.type = 'button';
            button.disabled = true;
            button.textContent = caption;
            button.title = text;
            button.prepend((0, ui_icons_js_1.uiIcon)(document, icon));
            const hint = document.createElement('p');
            hint.id = 'ddn-workarea-option-hint-' + (++nextHint);
            hint.setAttribute('role', 'tooltip');
            hint.textContent = text;
            hint.hidden = true;
            wrapper.setAttribute('aria-describedby', hint.id);
            button.setAttribute('aria-describedby', hint.id);
            const updateHint = () => { hint.hidden = !wrapper.matches(':hover') && document.activeElement !== wrapper; };
            for (const event of ['mouseenter', 'mouseleave', 'focus', 'blur'])
                wrapper.addEventListener(event, updateHint);
            wrapper.append(button);
            options.append(wrapper);
            hints.append(hint);
        }
        dialog.body.append(options, hints);
        back(dialog, 'Back', () => { workareaName = name.value; chooseDocument(); });
    }
    function chooseLayout() {
        (0, view_layout_picker_js_1.viewLayoutDialog)(handle.overlays, { selected: layout,
            onContinue(preset) { layout = preset; chooseView(); },
            onBack(preset) {
                layout = preset;
                if (mode === 'workarea')
                    setupWorkarea();
                else
                    chooseDocument();
            },
        });
    }
    function chooseView() {
        let type;
        const dialog = (0, dialogs_js_1.createStandardDialog)(handle.overlays, { title: 'Choose diagram type', applyLabel: 'Create view', lockWhileApplying: true, async onApply() {
                viewName = name.value.trim();
                if (!viewName) {
                    name.focus();
                    throw Error('Enter a view name.');
                }
                if (viewName === workareaName) {
                    name.focus();
                    throw Error('The view and workarea must have different names.');
                }
                if (!profiles.some(profile => profile.id === type.value))
                    throw Error('Choose an available diagram type.');
                const header = 'workarea ' + (0, index_js_1.quoteText)(workareaName) + '\n' + (mode === 'standalone' ? '    with\n        mode standalone\n' : '');
                await create(header + (0, view_picker_js_1.diagramHeader)(viewName, type.value) + '\n' + (0, view_layout_picker_js_1.viewLayoutSource)(layout));
                const view = handle.scene()?.entries.find(entry => entry.definition.owner === 'view');
                if (view) {
                    handle.select(view.definition.ref, view.item.occurrence);
                    handle.container.dispatchEvent(new CustomEvent('ddn:action', { detail: { action: 'activate-view-tools' } }));
                }
            } });
        const summary = document.createElement('p');
        summary.className = 'ddn-appearance-message';
        summary.textContent = 'View layout: ' + (0, view_surfaces_js_1.getViewSurfacePreset)(layout).label;
        dialog.body.append(summary);
        type = (0, view_picker_js_1.viewTypePicker)(dialog.body, profiles, 'Diagram type');
        const settings = document.createElement('div');
        settings.className = 'ddn-view-type-settings';
        const name = field(settings, 'View name', viewName === workareaName ? viewName + ' View' : viewName);
        dialog.body.append(settings);
        const update = () => {
            settings.hidden = !type.value;
            dialog.applyButton.disabled = !type.value;
            if (type.value) {
                name.focus({ preventScroll: true });
                name.select();
            }
        };
        type.onChange(update);
        update();
        back(dialog, 'Back', () => { viewName = name.value; chooseLayout(); });
    }
    chooseDocument();
}

},
"designer/src/palette-groups.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.paletteGroupOrder = void 0;
exports.paletteGroup = paletteGroup;
const core_js_1 = require("profiles/src/core.js");
const sections = [
    ['SQL objects', 'catalog database schema table foreign_table materialized_view view saved_view field index constraint sequence synonym function procedure trigger sql_type sql_domain extension qry query_operation write_operation'],
    ['Cluster objects', 'cluster shard partition partition_rule replica replica_set federation colocation placement router checkpoint recovery retention'],
    ['System infrastructure', 'host device network cloud cloud_account region zone site container environment security_zone namespace volume workspace registry service application gateway endpoint api'],
    ['File types', 'file file_set folder document archive backup blob bucket manifest export log snapshot model_artifact'],
    ['Data structures', 'aggregate array cache collection cube data_product dataset dimension enumeration fact feature graph graph_edge graph_node history key_value keyspace map metric rdf record search_index semantic_model set tensor time_series timeline variant vector wide_column window'],
    ['Messaging', 'binding bridge connector consumer_group message pub queue schema_registry sub subscription topic webhook'],
    ['Automation', 'activity command job manual_activity opr pipeline pkg run schedule test rule'],
    ['People & permissions', 'organization team role identity entl gpo pol prv dcl cls'],
    ['Concepts & notes', 'context decision domain entity object term note note.sticky observation issue change qlr rel unit sample fixture dct slo ext'],
];
exports.paletteGroupOrder = sections.map(([name]) => name);
const groupByRole = new Map(sections.flatMap(([group, roles]) => roles.split(' ').map(role => [role, group])));
const methodNames = { uml: 'UML elements', sysml: 'SysML elements', uaf: 'Architecture elements', flow: 'Flow elements', dfd: 'Data flow elements', chen: 'Chen elements', elec: 'Electrical symbols', electrical: 'Electrical symbols', c4: 'C4 elements', bpmn: 'BPMN elements', cmmn: 'Case elements', erd: 'ERD elements', archimate: 'ArchiMate elements', soaml: 'Service elements', req: 'Requirements', vsm: 'Value stream elements', epk: 'Event process elements' };
function paletteGroup(role) {
    const group = groupByRole.get(role);
    if (group)
        return group;
    const method = role.split('.')[0];
    if (methodNames[method])
        return methodNames[method];
    const shape = String((0, core_js_1.roleDescriptor)(role)?.render.shape ?? 'card').split('.')[0];
    return { frame: 'Containers', activity: 'Activities', decision: 'Decisions', note: 'Notes & evidence', document: 'Documents', cylinder: 'Storage', actor: 'People', port: 'Interfaces', sample: 'Samples', profile: 'Diagram symbols' }[shape] ?? 'Other elements';
}

},
"designer/src/presets.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.PRESET_PATHS = void 0;
exports.parsePresetPack = parsePresetPack;
exports.serializePresetPack = serializePresetPack;
exports.standardPresets = standardPresets;
exports.mergePresetPacks = mergePresetPacks;
exports.readLocalPresets = readLocalPresets;
exports.writeLocalPresets = writeLocalPresets;
const index_js_1 = require("defaults/src/index.js");
const owners = { workarea: 'workarea', element: 'appearance', view: 'view_definition' };
exports.PRESET_PATHS = ['background.color', 'background.texture', 'text.color', 'border.color', 'opacity', 'style.paper', 'style.font', 'style.font_size', 'style.look', 'shadow', 'decorations'];
const paths = new Set(exports.PRESET_PATHS);
const record = (value) => !!value && typeof value === 'object' && !Array.isArray(value);
const clone = (value) => JSON.parse(JSON.stringify(value));
function parsePresetPack(text) {
    if (text.length > 262144 || new TextEncoder().encode(text).byteLength > 262144)
        throw Error('Preset files are limited to 256 KiB.');
    const pack = JSON.parse(text);
    if (!record(pack) || pack.format !== 'ddn-appearance-presets' || pack.version !== 1 || !Array.isArray(pack.presets) || pack.presets.length > 100)
        throw Error('Expected a version 1 DDN appearance preset pack with at most 100 presets.');
    const seen = new Set();
    for (const preset of pack.presets) {
        if (!record(preset) || typeof preset.id !== 'string' || !/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,79}$/.test(preset.id) || seen.has(preset.id))
            throw Error('Preset IDs must be unique, short identifiers.');
        seen.add(preset.id);
        if (preset.id.startsWith('standard-'))
            throw Error('The standard- ID prefix is reserved for bundled presets.');
        if (typeof preset.name !== 'string' || !preset.name.trim() || preset.name.length > 80)
            throw Error('Each preset needs a name of at most 80 characters.');
        if (!['user', 'company'].includes(String(preset.scope)) || !Object.hasOwn(owners, String(preset.target)))
            throw Error('Preset scope or target is invalid.');
        if (preset.profile !== undefined && (typeof preset.profile !== 'string' || preset.profile.length > 100))
            throw Error('Preset profile must be a short profile ID.');
        if (!record(preset.properties) || !Object.keys(preset.properties).length)
            throw Error('A preset needs appearance properties.');
        for (const [path, value] of Object.entries(preset.properties)) {
            if (!paths.has(path))
                throw Error(`Preset property ${path} is not an appearance setting.`);
            const errors = (0, index_js_1.validateProperty)(owners[preset.target], path, value);
            if (errors.length)
                throw Error(errors.map(e => e.message).join('; '));
        }
        if (Object.keys(preset).some(key => !['id', 'name', 'scope', 'target', 'profile', 'properties'].includes(key)))
            throw Error('Unknown preset field.');
    }
    if (Object.keys(pack).some(key => !['format', 'version', 'presets'].includes(key)))
        throw Error('Unknown preset pack field.');
    return clone(pack);
}
function serializePresetPack(presets) {
    const text = JSON.stringify({ format: 'ddn-appearance-presets', version: 1, presets }, null, 2) + '\n';
    parsePresetPack(text);
    return text;
}
function standardPresets(target) {
    return [
        { id: 'light', name: 'Clean light', background: '#ffffff', ink: '#243449', texture: null },
        { id: 'dark', name: 'Dark slate', background: '#233144', ink: '#e8ecf2', texture: null },
        { id: 'warm', name: 'Warm paper', background: '#f5e9d4', ink: '#473f35', texture: { kind: 'paper', color: '#9b7952', opacity: 0.12, scale: 32, seed: 42 } },
    ].map(p => ({ id: 'standard-' + target + '-' + p.id, name: p.name, scope: 'user', target, properties: { 'background.color': p.background, 'background.texture': p.texture, ...(target === 'workarea' ? {} : { 'text.color': p.ink, 'style.font': 'sans', 'style.font_size': 16 }) } }));
}
function mergePresetPacks(existing, incoming) {
    const result = clone([...existing]);
    for (const preset of incoming) {
        const found = result.findIndex(p => p.id === preset.id);
        if (found >= 0)
            throw Error(`Preset ID ${preset.id} already exists; rename it before importing.`);
        result.push(clone(preset));
    }
    return parsePresetPack(serializePresetPack(result)).presets;
}
function readLocalPresets(storage) {
    const text = storage?.getItem('ddn.appearance-presets.v1');
    return text ? parsePresetPack(text).presets : [];
}
function writeLocalPresets(storage, presets) {
    storage.setItem('ddn.appearance-presets.v1', serializePresetPack(presets));
}

},
"designer/src/properties.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.openProperties = openProperties;
const native_js_1 = require("viewer/src/native.js");
const schema_core_js_1 = require("profiles/src/schema-core.js");
const core_js_1 = require("profiles/src/core.js");
const native_js_2 = require("presentation/src/native.js");
const runtime_js_1 = require("runtime/src/runtime.js");
const index_js_1 = require("language/src/index.js");
const dialogs_js_1 = require("designer/src/dialogs.js");
const choice_field_js_1 = require("viewer/src/choice-field.js");
const fonts_js_1 = require("viewer/src/fonts.js");
const live_settings_js_1 = require("designer/src/live-settings.js");
const schema_editor_js_1 = require("designer/src/schema-editor.js");
const labels = {
    title: 'Title', description: 'Description', opacity: 'Opacity',
    'background.color': 'Background colour', 'background.texture': 'Background texture',
    'border.color': 'Border colour', 'text.color': 'Text colour',
    'style.font': 'Font family', 'style.font_size': 'Font size',
    'style.look': 'Drawing style', 'style.paper': 'Paper style',
    'shadow.kind': 'Shadow style', 'shadow.opacity': 'Shadow opacity',
    'shadow.blur': 'Shadow softness', 'shadow.lift': 'Shadow lift',
    'shadow.spread': 'Shadow spread', 'shadow.color': 'Shadow colour',
    'text.line_height': 'Line height', 'text.align': 'Text alignment',
    'stroke.weight': 'Line thickness', decorations: 'Pins, clips and tape',
};
const preferred = ['title', 'background.color', 'opacity', 'style.font_size', 'text.color', 'style.font', 'style.look', 'style.paper', 'background.texture', 'shadow', 'decorations'];
const protectedPath = (path) => /^(?:id|name|category|role|profile|method|target|design|acceptance|acceptance_history|revision|access)(?:\.|$)/.test(path);
const ownerAliases = { view: 'view_definition', placement: 'view_placement' };
const ownerName = (owner) => ownerAliases[owner] ?? owner;
const clone = (value) => value === undefined ? value : JSON.parse(JSON.stringify(value));
function openProperties(viewer, panel, commit) {
    const handle = (0, native_js_1.getViewerHandle)(viewer), document = handle.ownerDocument;
    const snapshot = handle.runtime.snapshot(), decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded;
    if (!snapshot || !decoded)
        throw Error('Open an editable workarea first.');
    const all = (0, native_js_2.records)(snapshot), entry = handle.selectedEntry(), scopes = [];
    const addScope = (record, label) => {
        if (!record || scopes.some(s => (0, native_js_2.refKey)(s.record.ref) === (0, native_js_2.refKey)(record.ref)))
            return;
        const node = (0, index_js_1.findNode)(decoded, record.ref);
        if (!node || node.implicit)
            return;
        scopes.push({ record, label, owner: ownerName(record.owner) });
    };
    if (entry) {
        addScope(entry.appearance, 'This appearance');
        addScope(entry.definition, entry.definition.owner === 'view' ? 'This view' : 'Shared element');
        addScope(entry.placement, 'This view placement');
        addScope(entry.view, 'This view');
    }
    addScope(all.find(record => record.owner === 'workarea' && record.file === snapshot.rootFile), 'Workarea');
    if (!scopes.length)
        throw Error('Select an editable item or workarea.');
    const references = all.map(record => ({ ref: record.ref, label: (0, native_js_2.titleOf)(record.record) + ' (' + record.file + ')' }));
    const scopeTitle = (scope) => (0, native_js_2.titleOf)(scope.owner === 'appearance' && entry ? entry.definition.record : scope.owner === 'view_placement' && entry ? entry.view.record : scope.record.record);
    panel('Properties', body => {
        const editing = document.createElement('p');
        editing.textContent = 'Editing: ' + scopeTitle(scopes[0]);
        body.append(editing);
        const makeSelect = (label) => {
            const wrap = document.createElement('label'), select = document.createElement('select');
            wrap.textContent = label;
            select.setAttribute('aria-label', label);
            select.dataset.ddnLiveIgnore = '';
            wrap.append(select);
            body.append(wrap);
            return select;
        };
        const scope = makeSelect('Apply settings to');
        scopes.forEach((item, index) => scope.add(new Option(item.label, String(index))));
        const activeChips = document.createElement('div');
        activeChips.className = 'ddn-active-properties';
        activeChips.setAttribute('aria-label', 'Configured settings');
        activeChips.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;margin:2px 0';
        body.append(activeChips);
        const filterWrap = document.createElement('label'), filterInput = document.createElement('input');
        filterInput.type = 'search';
        filterInput.placeholder = 'Filter settings…';
        filterInput.setAttribute('aria-label', 'Filter settings');
        filterInput.dataset.ddnLiveIgnore = '';
        filterWrap.append('Filter settings', filterInput);
        body.append(filterWrap);
        const property = makeSelect('Setting'), editorArea = document.createElement('div');
        body.append(editorArea);
        const resetLabel = document.createElement('label'), reset = document.createElement('input');
        reset.type = 'checkbox';
        resetLabel.append(reset, 'Reset to inherited value (omit here)');
        body.append(resetLabel);
        const hint = document.createElement('p');
        hint.className = 'ddn-appearance-message';
        body.append(hint);
        const advanced = document.createElement('details'), summary = document.createElement('summary');
        summary.textContent = 'Advanced property';
        advanced.append(summary);
        body.append(advanced);
        const advancedField = (label, multiline = false) => {
            const wrap = document.createElement('label'), input = document.createElement(multiline ? 'textarea' : 'input');
            wrap.textContent = label;
            input.setAttribute('aria-label', label);
            wrap.append(input);
            advanced.append(wrap);
            return input;
        };
        const advancedPath = advancedField('Property path'), advancedValue = advancedField('Value (text, number, boolean, or structured JSON)', true);
        advancedPath.dataset.ddnLiveIgnore = '';
        const advancedResetLabel = document.createElement('label'), advancedReset = document.createElement('input');
        advancedReset.type = 'checkbox';
        advancedResetLabel.append(advancedReset, 'Reset advanced property to inherited');
        advanced.append(advancedResetLabel);
        const message = document.createElement('p');
        message.setAttribute('role', 'status');
        body.append(message);
        let chosen = 0, selectedPath = '', loading = true, token = 0, dirty = false, advancedDirty = false;
        let editor, initialValue;
        let values = {}, choices = [];
        let changes = {};
        const effective = (path) => {
            const combined = clone(values);
            for (const [key, value] of Object.entries(changes))
                if (value !== undefined)
                    (0, schema_core_js_1.setPath)(combined, key, clone(value));
            return (0, native_js_2.pathValue)(combined, path);
        };
        const stash = () => {
            if (!dirty || !selectedPath)
                return;
            const value = reset.checked ? undefined : editor?.read();
            if (reset.checked || JSON.stringify(value) !== JSON.stringify(initialValue)) {
                delete changes[selectedPath];
                changes[selectedPath] = value;
            }
            else
                delete changes[selectedPath];
            dirty = false;
        };
        const render = () => {
            selectedPath = property.value;
            editorArea.replaceChildren();
            editor = undefined;
            dirty = false;
            const definition = choices.find(item => item.path === selectedPath);
            if (!definition)
                return;
            const current = scopes[chosen], name = labels[selectedPath] ?? selectedPath;
            reset.checked = Object.hasOwn(changes, selectedPath) && changes[selectedPath] === undefined;
            const node = (0, schema_editor_js_1.schemaNode)(definition.schema);
            const authoredRecord = (0, native_js_2.records)(handle.runtime.snapshot()).find(record => (0, native_js_2.refKey)(record.ref) === (0, native_js_2.refKey)(current.record.ref))?.record ?? current.record.record;
            const authored = (0, native_js_2.pathValue)(authoredRecord, selectedPath);
            initialValue = clone(effective(selectedPath));
            let value = initialValue;
            if ((node.type === 'object' || node.type === 'array') && !Object.keys(changes).some(path => path === selectedPath || path.startsWith(selectedPath + '.')) && authored !== undefined)
                value = clone(authored);
            initialValue = clone(value);
            if (selectedPath === 'style.font') {
                const families = [...new Set(['sans', 'serif', 'mono', 'handwriting', ...(0, fonts_js_1.listFonts)(document).map(font => font.family), String(value ?? 'sans')])];
                const input = (0, choice_field_js_1.choiceField)(editorArea, name, families, String(value ?? 'sans'), { kind: 'font' });
                editor = { read: () => input.value };
            }
            else if (selectedPath === 'style.font_size') {
                const input = (0, dialogs_js_1.numberField)(editorArea, 'Font size (pt)', typeof value === 'number' ? value * .75 : 12, { min: 6, max: 48, step: .5 });
                input.step = 'any';
                editor = { read: () => {
                        if (!input.checkValidity() || !Number.isFinite(input.valueAsNumber))
                            throw Error('Enter a valid font size.');
                        return input.valueAsNumber * 4 / 3;
                    } };
            }
            else if (/(?:^|\.)color$/.test(selectedPath) && typeof value === 'string') {
                const input = (0, dialogs_js_1.colourField)(editorArea, name, value);
                editor = { read: () => input.value };
            }
            else {
                let schema = definition.schema;
                if (selectedPath === 'projection.options' && current.owner === 'view_definition') {
                    const profile = (0, core_js_1.getProfile)((0, native_js_2.str)(current.record.record.profile));
                    if (profile)
                        schema = schema_core_js_1.codex.roots[profile.projection_schema] ?? schema;
                }
                editor = (0, schema_editor_js_1.createFieldEditor)(editorArea, schema, value, references, name);
            }
            editorArea.inert = reset.checked;
            hint.textContent = 'Changes appear immediately. Unchanged defaults stay inherited.';
        };
        editorArea.addEventListener('input', () => { dirty = true; });
        editorArea.addEventListener('change', () => { dirty = true; });
        editorArea.addEventListener('click', event => {
            if (event.target.closest('button'))
                dirty = true;
        });
        reset.addEventListener('change', () => { dirty = true; editorArea.inert = reset.checked; });
        editorArea.addEventListener('ddn-settings-change', () => { dirty = true; });
        const selectProperty = (nextPath) => {
            if (!nextPath || nextPath === selectedPath)
                return;
            property.disabled = true;
            editorArea.inert = true;
            void (0, live_settings_js_1.flushLiveSettings)(body).then(() => {
                if (!body.isConnected)
                    return;
                if (![...property.options].some(o => o.value === nextPath)) {
                    const def = choices.find(c => c.path === nextPath);
                    if (def)
                        property.add(new Option(labels[def.path] ?? def.path, def.path));
                }
                property.value = nextPath;
                render();
                renderActiveChips();
                message.textContent = '';
            }).catch(error => { message.textContent = error.message; }).finally(() => { property.disabled = false; editorArea.inert = reset.checked; });
        };
        const renderActiveChips = () => {
            activeChips.replaceChildren();
            const current = scopes[chosen];
            if (!current || !handle.runtime.snapshot())
                return;
            const authoredRecord = (0, native_js_2.records)(handle.runtime.snapshot()).find(record => (0, native_js_2.refKey)(record.ref) === (0, native_js_2.refKey)(current.record.ref))?.record ?? current.record.record;
            for (const item of choices) {
                const authored = Object.hasOwn(changes, item.path) ? changes[item.path] : (0, native_js_2.pathValue)(authoredRecord, item.path);
                if (authored === undefined)
                    continue;
                const chip = document.createElement('button');
                chip.type = 'button';
                chip.className = 'ddn-active-property-chip';
                chip.dataset.propertyPath = item.path;
                chip.dataset.ddnLiveIgnore = '';
                const summaryVal = typeof authored === 'object' ? '…' : String(authored);
                chip.textContent = `${labels[item.path] ?? item.path}: ${summaryVal.length > 18 ? summaryVal.slice(0, 18) + '…' : summaryVal}`;
                chip.title = `Jump to ${labels[item.path] ?? item.path} (${item.path})`;
                chip.style.cssText = `font-size:11px;padding:2px 7px;border-radius:999px;border:1px solid ${item.path === selectedPath ? 'var(--ddn-ui-accent)' : 'var(--ddn-ui-border)'};background:${item.path === selectedPath ? 'color-mix(in srgb,var(--ddn-ui-accent) 14%,var(--ddn-ui-surface))' : 'var(--ddn-ui-surface)'}`;
                chip.addEventListener('click', event => { event.stopPropagation(); selectProperty(item.path); });
                activeChips.append(chip);
            }
            activeChips.hidden = activeChips.childElementCount === 0;
        };
        const populatePropertyOptions = () => {
            const q = filterInput.value.trim().toLowerCase();
            const filtered = q ? choices.filter(item => `${labels[item.path] ?? ''} ${item.path}`.toLowerCase().includes(q)) : choices;
            const list = filtered.length ? filtered : choices;
            property.replaceChildren();
            list.forEach(item => property.add(new Option(labels[item.path] ?? item.path, item.path)));
            property.value = list.some(item => item.path === selectedPath) ? selectedPath : list[0]?.path ?? '';
        };
        filterInput.addEventListener('input', event => {
            event.stopPropagation();
            const prev = selectedPath;
            populatePropertyOptions();
            if (property.value && property.value !== prev)
                selectProperty(property.value);
        });
        property.addEventListener('change', event => {
            event.stopPropagation();
            const next = property.value;
            property.value = selectedPath;
            selectProperty(next);
        });
        for (const input of [advancedValue, advancedReset])
            input.addEventListener('input', () => { advancedDirty = true; });
        const refresh = async () => {
            const request = ++token;
            loading = true;
            dirty = false;
            property.disabled = reset.disabled = true;
            editorArea.inert = true;
            editorArea.textContent = 'Loading settings…';
            const current = scopes[chosen], inspected = await viewer.inspect(current.record.ref);
            if (request !== token || !body.isConnected)
                return;
            editing.textContent = 'Editing: ' + scopeTitle(current);
            values = {};
            for (const item of inspected.properties)
                if (item.effective !== undefined)
                    (0, schema_core_js_1.setPath)(values, item.path, clone(item.effective));
            choices = schema_core_js_1.codex.properties.filter(item => item.owner === current.owner && item.settable && !protectedPath(item.path));
            choices.sort((a, b) => {
                const ai = preferred.indexOf(a.path), bi = preferred.indexOf(b.path);
                return (ai < 0 ? preferred.length : ai) - (bi < 0 ? preferred.length : bi) || a.path.localeCompare(b.path);
            });
            populatePropertyOptions();
            loading = false;
            property.disabled = reset.disabled = false;
            render();
            renderActiveChips();
        };
        scope.addEventListener('change', event => {
            event.stopPropagation();
            const next = Number(scope.value);
            scope.value = String(chosen);
            scope.disabled = true;
            editorArea.inert = true;
            void (0, live_settings_js_1.flushLiveSettings)(body).then(async () => {
                if (!body.isConnected)
                    return;
                chosen = next;
                scope.value = String(next);
                changes = {};
                advancedPath.value = advancedValue.value = '';
                advancedReset.checked = false;
                await refresh();
            }).catch(error => { message.textContent = error.message; }).finally(() => { scope.disabled = false; editorArea.inert = reset.checked; });
        });
        void refresh().catch(error => { message.textContent = error.message; });
        return async () => {
            if (loading)
                throw Error('Wait for settings to load.');
            stash();
            if (advancedDirty) {
                const path = advancedPath.value.trim();
                if (!path)
                    throw Error('Enter the advanced property path.');
                if (protectedPath(path))
                    throw Error('Use the dedicated identity or lifecycle commands for this property.');
                let value = advancedValue.value;
                if (advancedReset.checked)
                    value = undefined;
                else {
                    try {
                        value = JSON.parse(advancedValue.value);
                    }
                    catch { }
                }
                delete changes[path];
                changes[path] = value;
            }
            if (Object.keys(changes).length) {
                const pending = { ...changes }, target = scopes[chosen].record.ref, advancedAtCommit = advancedValue.value;
                await commit(target, pending);
                for (const [path, value] of Object.entries(pending))
                    if (Object.hasOwn(changes, path) && JSON.stringify(changes[path]) === JSON.stringify(value))
                        delete changes[path];
                if (advancedValue.value === advancedAtCommit)
                    advancedDirty = false;
                const inspected = await viewer.inspect(target);
                values = {};
                for (const item of inspected.properties)
                    if (item.effective !== undefined)
                        (0, schema_core_js_1.setPath)(values, item.path, clone(item.effective));
                initialValue = clone(effective(selectedPath));
                renderActiveChips();
            }
        };
    });
}

},
"designer/src/relation-menu.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.relationMenuItems = relationMenuItems;
const native_js_1 = require("presentation/src/native.js");
function relationMenuItems(entry, viewProperties, editable, change) {
    const state = (0, native_js_1.relationPresentation)(entry, viewProperties);
    const disabled = !state.allowed || !editable;
    const reason = !state.allowed ? 'Internal mind-map links have no labels, numbers or legend entries.'
        : !editable ? 'This relation has no editable appearance in this view.' : '';
    const legendHidden = (0, native_js_1.pathValue)(viewProperties, 'legend.placement') === 'none' || (0, native_js_1.pathValue)(viewProperties, 'chrome.legend') === 'off';
    const item = (name, caption, checked, path, value, help) => [caption, () => change(path, value), { name, checked, disabled, title: reason || help }];
    return [
        item('Label visible', `Label: ${state.visible ? 'Visible' : 'Invisible'}`, state.visible, 'label.visible', !state.visible, 'Show or hide this relation’s label. Legend membership is independent.'),
        item('Number instead of text', `Label format: ${state.mode === 'numbers' ? 'Number' : state.mode === 'tokens' ? 'Token' : 'Text'}`, state.mode === 'numbers', 'label.mode', state.mode === 'numbers' ? 'text' : 'numbers', 'Switch this label between its relation number and text. This does not change label visibility.'),
        item('Include in legend', `In legend: ${state.inLegend ? 'Included' : 'Excluded'}`, state.inLegend, 'legend.include', !state.inLegend, 'Include or exclude this relation in the view’s relationship legend.' + (legendHidden ? ' The view currently hides its legend.' : '')),
    ];
}

},
"designer/src/resize-handles.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.mountResizeHandles = mountResizeHandles;
const native_js_1 = require("presentation/src/native.js");
function mountResizeHandles(viewer, handle, options) {
    const document = handle.ownerDocument, NS = 'http://www.w3.org/2000/svg';
    let focusedOccurrence;
    const css = document.createElement('style');
    css.textContent = '.ddn-element-resize{cursor:nwse-resize;touch-action:none;opacity:.65;outline:none}.ddn-element-resize:hover,.ddn-element-resize:focus-visible,[data-selected=true]>.ddn-element-resize{opacity:1}.ddn-element-resize .ddn-resize-pad,.ddn-element-resize-handles .ddn-resize-handle{fill:#fff;fill-opacity:.85;stroke:#5278a1;stroke-opacity:.55}.ddn-element-resize-handles .ddn-resize-handle{touch-action:none}.ddn-element-resize-handles .ddn-resize-handle:hover{stroke:#2563eb;stroke-width:1.5;fill-opacity:1}.ddn-element-resize path{fill:none;stroke:#416b98;stroke-width:1.5;stroke-linecap:round;pointer-events:none}.ddn-element-resize:focus-visible .ddn-resize-pad{stroke:#2563eb;stroke-width:2}';
    handle.container.append(css);
    const stopClick = (event) => { event.preventDefault(); event.stopPropagation(); };
    const clearFocus = (event) => {
        const target = event.target;
        if (!target?.closest?.('.ddn-element-resize') || !handle.surface.contains(target))
            focusedOccurrence = undefined;
    };
    document.addEventListener('focusin', clearFocus);
    document.addEventListener('pointerdown', clearFocus, true);
    const extraDirs = [
        { dir: 'nw', cursor: 'nwse-resize' },
        { dir: 'n', cursor: 'ns-resize' },
        { dir: 'ne', cursor: 'nesw-resize' },
        { dir: 'e', cursor: 'ew-resize' },
        { dir: 's', cursor: 'ns-resize' },
        { dir: 'sw', cursor: 'nesw-resize' },
        { dir: 'w', cursor: 'ew-resize' },
    ];
    function update() {
        const entries = new Map(handle.scene()?.entries.map(entry => [entry.item.occurrence, entry]));
        const matrix = handle.surface.getScreenCTM(), scale = matrix ? Math.hypot(matrix.a, matrix.b) : 1;
        if (!(scale > 0))
            return;
        for (const group of [...handle.surface.children]) {
            const occurrence = group.getAttribute('data-occurrence');
            if (!occurrence)
                continue;
            const entry = entries.get(occurrence);
            let grip = group.querySelector(':scope > .ddn-element-resize');
            let extras = group.querySelector(':scope > .ddn-element-resize-handles');
            if (group.getAttribute('data-selected') !== 'true' || !entry || !options.allowed(entry) || handle.surface.dataset.lod === 'mini') {
                if (focusedOccurrence === occurrence)
                    focusedOccurrence = undefined;
                grip?.remove();
                extras?.remove();
                continue;
            }
            const current = () => handle.scene()?.entries.find(item => item.item.occurrence === occurrence);
            if (!extras) {
                extras = document.createElementNS(NS, 'g');
                extras.classList.add('ddn-element-resize-handles');
                for (const { dir, cursor } of extraDirs) {
                    const rect = document.createElementNS(NS, 'rect');
                    rect.setAttribute('class', 'ddn-resize-handle');
                    rect.dataset.handle = dir;
                    rect.style.cursor = cursor;
                    for (const [k, v] of Object.entries({ width: 10, height: 10, rx: 2.5 }))
                        rect.setAttribute(k, String(v));
                    rect.addEventListener('pointerdown', event => {
                        const target = current();
                        if (group.getAttribute('data-selected') === 'true' && target && options.allowed(target))
                            options.start(target, event, dir);
                    });
                    rect.addEventListener('click', stopClick);
                    rect.addEventListener('dblclick', stopClick);
                    extras.append(rect);
                }
                group.append(extras);
            }
            if (!grip) {
                grip = document.createElementNS(NS, 'g');
                grip.classList.add('ddn-element-resize', 'ddn-resize-handle');
                grip.dataset.handle = 'se';
                grip.setAttribute('role', 'button');
                grip.setAttribute('tabindex', '0');
                const title = document.createElementNS(NS, 'title');
                title.textContent = 'Drag to resize. Arrow keys resize; Shift uses smaller steps. Escape cancels a drag.';
                const pad = document.createElementNS(NS, 'rect');
                pad.setAttribute('class', 'ddn-resize-pad');
                for (const [key, value] of Object.entries({ width: 20, height: 20, rx: 3 }))
                    pad.setAttribute(key, String(value));
                const lines = document.createElementNS(NS, 'path');
                lines.setAttribute('d', 'M6 16L16 6M11 16L16 11M16 16L16 16');
                grip.append(title, pad, lines);
                grip.addEventListener('focus', () => { focusedOccurrence = occurrence; });
                grip.addEventListener('pointerdown', event => {
                    const target = current();
                    if (group.getAttribute('data-selected') === 'true' && target && options.allowed(target))
                        options.start(target, event, 'se');
                });
                grip.addEventListener('keydown', event => {
                    const target = current();
                    if (group.getAttribute('data-selected') !== 'true' || !target || !options.allowed(target))
                        return;
                    const amount = event.shiftKey ? 1 : 16;
                    const offsets = { ArrowLeft: [-amount, 0], ArrowRight: [amount, 0], ArrowUp: [0, -amount], ArrowDown: [0, amount] };
                    const offset = offsets[event.key];
                    if (offset) {
                        event.preventDefault();
                        event.stopPropagation();
                        options.step(target, ...offset);
                    }
                });
                grip.addEventListener('click', stopClick);
                grip.addEventListener('dblclick', stopClick);
                group.append(grip);
            }
            grip.setAttribute('aria-label', 'Resize ' + (0, native_js_1.titleOf)(entry.definition.record));
            const b = options.bounds(entry);
            const coords = {
                nw: [b.x, b.y],
                n: [b.x + b.width / 2, b.y],
                ne: [b.x + b.width, b.y],
                e: [b.x + b.width, b.y + b.height / 2],
                s: [b.x + b.width / 2, b.y + b.height],
                sw: [b.x, b.y + b.height],
                w: [b.x, b.y + b.height / 2],
            };
            for (const rect of extras.querySelectorAll('.ddn-resize-handle')) {
                const dir = rect.dataset.handle;
                const [hx, hy] = coords[dir];
                rect.setAttribute('transform', `translate(${hx - 5 / scale} ${hy - 5 / scale}) scale(${1 / scale})`);
            }
            grip.setAttribute('transform', `translate(${b.x + b.width - 20 / scale} ${b.y + b.height - 20 / scale}) scale(${1 / scale})`);
            if (focusedOccurrence === occurrence && (document.activeElement === document.body || document.activeElement === handle.surface))
                grip.focus({ preventScroll: true });
        }
    }
    const unsubscribe = viewer.subscribe(event => {
        if (['ready', 'viewport', 'selection'].includes(event.kind))
            update();
    });
    const unselect = handle.subscribeSelection(update), Resize = document.defaultView?.ResizeObserver;
    const unopen = handle.subscribeOpen(() => { focusedOccurrence = undefined; });
    const observer = Resize ? new Resize(update) : undefined;
    observer?.observe(handle.surface);
    update();
    return () => { unsubscribe(); unselect(); unopen(); observer?.disconnect(); document.removeEventListener('focusin', clearFocus); document.removeEventListener('pointerdown', clearFocus, true); css.remove(); handle.surface.querySelectorAll('.ddn-element-resize,.ddn-element-resize-handles').forEach(grip => grip.remove()); };
}

},
"designer/src/schema-editor.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.schemaNode = schemaNode;
exports.childSchema = childSchema;
exports.createFieldEditor = createFieldEditor;
const schema_core_js_1 = require("profiles/src/schema-core.js");
const dialogs_js_1 = require("designer/src/dialogs.js");
const choice_field_js_1 = require("viewer/src/choice-field.js");
const live_settings_js_1 = require("designer/src/live-settings.js");
function schemaNode(id) {
    const seen = new Set();
    while (id !== undefined && !seen.has(id)) {
        seen.add(id);
        const node = schema_core_js_1.codex.nodes[id];
        if (!node || typeof node === 'boolean')
            return {};
        if (node.ref === undefined)
            return node;
        id = node.ref;
    }
    return {};
}
function childSchema(id, field) {
    return schemaNode(id).properties?.[field];
}
const isObject = (v) => !!v && typeof v === 'object' && !Array.isArray(v);
const matches = (schema, value) => {
    if (schema.enum)
        return schema.enum.some(v => JSON.stringify(v) === JSON.stringify(value));
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    return types.some(t => t === undefined || t === 'array' && Array.isArray(value) || t === 'object' && isObject(value) || t === 'null' && value === null || t === 'integer' && typeof value === 'number' && Number.isInteger(value) || t === typeof value);
};
function createFieldEditor(parent, id, value, refs, label, depth = 0, forcedType) {
    if (id === undefined || Object.keys(schemaNode(id)).length === 0)
        id = schema_core_js_1.codex.roots.json_value;
    const document = parent.ownerDocument, schema = schemaNode(id);
    const button = (text, fn) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = text; b.addEventListener('click', () => { fn(); (0, live_settings_js_1.notifyLiveSettings)(parent); }); return b; };
    const input = (type, value) => { const e = document.createElement('input'); e.type = type; e.value = value; e.setAttribute('aria-label', label); parent.append(e); return e; };
    if (depth > 12) {
        const retained = document.createElement('p');
        retained.textContent = 'Deeply nested value retained. Use the DDN source editor to change this section.';
        parent.append(retained);
        return { read: () => value ?? null };
    }
    if (Array.isArray(schema.type) && !forcedType) {
        const types = schema.type, select = document.createElement('select'), body = document.createElement('div');
        select.setAttribute('aria-label', label + ' scalar type');
        for (const type of types) {
            const option = document.createElement('option');
            option.value = type;
            option.textContent = type;
            select.append(option);
        }
        select.value = types.find(type => matches({ type }, value)) ?? types[0];
        parent.append(select, body);
        let editor = createFieldEditor(body, id, value, refs, label, depth + 1, select.value);
        select.addEventListener('change', () => {
            let previous;
            try {
                previous = editor.read();
            }
            catch {
                previous = undefined;
            }
            body.replaceChildren();
            editor = createFieldEditor(body, id, matches({ type: select.value }, previous) ? previous : undefined, refs, label, depth + 1, select.value);
        });
        return { read: () => editor.read() };
    }
    if (schema.properties?.file !== undefined && schema.properties?.id !== undefined) {
        const select = document.createElement('select');
        select.setAttribute('aria-label', label + ' reference');
        const choices = [...refs];
        if (isObject(value) && typeof value.file === 'string' && typeof value.id === 'string' && !choices.some(c => c.ref.file === value.file && c.ref.id === value.id))
            choices.push({ ref: { file: value.file, id: value.id }, label: `${value.file} :: ${value.id} (unresolved)` });
        const empty = document.createElement('option');
        empty.value = '';
        empty.textContent = 'Choose a reference';
        select.append(empty);
        choices.forEach((choice, i) => { const option = document.createElement('option'); option.value = String(i); option.textContent = choice.label; select.append(option); });
        const found = choices.findIndex(c => isObject(value) && c.ref.file === value.file && c.ref.id === value.id);
        select.value = found < 0 ? '' : String(found);
        parent.append(select);
        return { read: () => {
                const choice = choices[Number(select.value)];
                if (select.value === '' || !choice)
                    throw Error('Choose a reference for ' + label);
                return { ...choice.ref };
            } };
    }
    const variants = schema.oneOf ?? schema.anyOf;
    if (variants?.length) {
        const select = document.createElement('select'), body = document.createElement('div');
        select.setAttribute('aria-label', label + ' value type');
        variants.forEach((variant, i) => { const node = schemaNode(variant), option = document.createElement('option'); option.value = String(i); option.textContent = node.enum ? node.enum.map(String).join(' / ') : Array.isArray(node.type) ? node.type.join(' / ') : node.type ?? 'value'; select.append(option); });
        const exact = value === undefined ? -1 : variants.findIndex(v => (0, schema_core_js_1.validateSchema)(v, value).length === 0);
        const selected = exact >= 0 ? exact : Math.max(0, variants.findIndex(v => matches(schemaNode(v), value)));
        select.value = String(selected);
        parent.append(select, body);
        let editor = createFieldEditor(body, variants[selected], value, refs, label, depth + 1);
        select.addEventListener('change', () => {
            let previous;
            try {
                previous = editor.read();
            }
            catch {
                previous = undefined;
            }
            body.replaceChildren();
            const next = variants[Number(select.value)];
            editor = createFieldEditor(body, next, matches(schemaNode(next), previous) ? previous : undefined, refs, label, depth + 1);
        });
        return { read: () => editor.read() };
    }
    if (schema.enum || Object.hasOwn(schema, 'const')) {
        const values = [...(schema.enum ?? [schema.const])];
        if (value !== undefined && !values.some(v => JSON.stringify(v) === JSON.stringify(value)))
            values.push(value);
        const index = values.findIndex(v => JSON.stringify(v) === JSON.stringify(value));
        const select = (0, choice_field_js_1.choiceField)(parent, label, values.map((v, i) => ({ value: String(i), label: String(v), preview: document => (0, choice_field_js_1.choicePreview)(document, String(v), label) })), String(Math.max(0, index)));
        return { read: () => values[Number(select.value)] };
    }
    const type = forcedType ?? (Array.isArray(schema.type) ? schema.type.find(t => matches({ type: t }, value)) ?? schema.type[0] : schema.type ?? (Array.isArray(value) ? 'array' : isObject(value) ? 'object' : typeof value === 'number' ? 'number' : typeof value === 'boolean' ? 'boolean' : 'string'));
    if (type === 'object') {
        const initial = isObject(value) ? value : {}, fields = new Map();
        const addField = (key, child, initialValue) => {
            const group = document.createElement('details'), summary = document.createElement('summary'), enabled = document.createElement('input'), body = document.createElement('div');
            enabled.type = 'checkbox';
            enabled.checked = initialValue !== undefined;
            enabled.setAttribute('aria-label', 'Set ' + label + '.' + key);
            summary.append(enabled, document.createTextNode(key + (schema.required?.includes(key) ? ' (required when complete)' : '')));
            group.append(summary, body);
            parent.append(group);
            const state = { enabled };
            fields.set(key, state);
            const render = () => {
                body.replaceChildren();
                if (enabled.checked) {
                    state.editor = createFieldEditor(body, child, initialValue, refs, label + '.' + key, depth + 1);
                    group.open = true;
                }
                else {
                    delete state.editor;
                    group.open = false;
                }
            };
            if (enabled.checked)
                state.editor = createFieldEditor(body, child, initialValue, refs, label + '.' + key, depth + 1);
            enabled.addEventListener('change', render);
        };
        for (const key of new Set([...Object.keys(schema.properties ?? {}), ...Object.keys(initial)]))
            addField(key, schema.properties?.[key] ?? (typeof schema.additionalProperties === 'number' ? schema.additionalProperties : undefined), initial[key]);
        if (schema.additionalProperties !== false) {
            const row = document.createElement('div'), name = document.createElement('input');
            name.placeholder = 'New field name';
            name.setAttribute('aria-label', label + ' new field name');
            row.append(name, button('Add field', () => {
                const key = name.value.trim();
                if (!key || fields.has(key) || ['__proto__', 'constructor', 'prototype'].includes(key))
                    return;
                addField(key, typeof schema.additionalProperties === 'number' ? schema.additionalProperties : undefined, '');
                name.value = '';
            }));
            parent.append(row);
        }
        return { read: () => {
                const result = {};
                for (const [key, state] of fields)
                    if (state.enabled.checked && state.editor)
                        result[key] = state.editor.read();
                return result;
            } };
    }
    if (type === 'array') {
        const list = document.createElement('div');
        parent.append(list);
        const rows = [];
        const add = (initial) => {
            const element = document.createElement('fieldset'), legend = document.createElement('legend'), body = document.createElement('div');
            legend.textContent = 'Item';
            element.append(legend, body);
            const row = { element, editor: createFieldEditor(body, schema.items, initial, refs, label + ' item', depth + 1) };
            const move = (offset) => {
                const index = rows.indexOf(row), next = index + offset;
                if (next < 0 || next >= rows.length)
                    return;
                rows.splice(index, 1);
                rows.splice(next, 0, row);
                list.replaceChildren(...rows.map(r => r.element));
            };
            element.append(button('Move up', () => move(-1)), button('Move down', () => move(1)), button('Remove item', () => { rows.splice(rows.indexOf(row), 1); element.remove(); }));
            rows.push(row);
            list.append(element);
        };
        if (Array.isArray(value))
            value.forEach(add);
        parent.append(button('Add item', () => add(undefined)));
        return { read: () => rows.map(row => row.editor.read()) };
    }
    if (type === 'boolean') {
        const e = input('checkbox', '');
        e.checked = value === true;
        return { read: () => e.checked };
    }
    if (type === 'null') {
        const text = document.createElement('span');
        text.textContent = 'Empty (null)';
        parent.append(text);
        return { read: () => null };
    }
    if (type === 'number' || type === 'integer') {
        const current = typeof value === 'number' && Number.isFinite(value) ? value : 0;
        const min = typeof schema.minimum === 'number' ? schema.minimum : Math.min(-100, current * 2);
        const max = typeof schema.maximum === 'number' ? schema.maximum : Math.max(100, current * 2);
        const span = max - min, step = type === 'integer' ? 1 : span <= 1 ? .01 : span <= 100 ? .1 : 1;
        const e = Number.isFinite(min) && Number.isFinite(max) && max > min
            ? (0, dialogs_js_1.numberField)(parent, label, typeof value === 'number' ? value : '', { min, max, step })
            : input('number', typeof value === 'number' ? String(value) : '');
        e.step = type === 'integer' ? '1' : 'any';
        if (schema.minimum !== undefined)
            e.min = String(schema.minimum);
        else
            e.removeAttribute('min');
        if (schema.maximum !== undefined)
            e.max = String(schema.maximum);
        else
            e.removeAttribute('max');
        (0, dialogs_js_1.syncNumberField)(e);
        return { read: () => {
                const n = Number(e.value);
                if (e.value.trim() === '' || !Number.isFinite(n) || !e.checkValidity() || type === 'integer' && !Number.isInteger(n))
                    throw Error(label + ' needs a finite ' + type);
                return n;
            } };
    }
    const e = document.createElement('textarea');
    e.value = value === undefined || value === null ? '' : String(value);
    e.rows = 2;
    e.style.minHeight = '3em';
    e.setAttribute('aria-label', label);
    parent.append(e);
    return { read: () => e.value };
}

},
"designer/src/symbol.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.openSymbol = openSymbol;
const native_js_1 = require("viewer/src/native.js");
const native_js_2 = require("presentation/src/native.js");
const runtime_js_1 = require("runtime/src/runtime.js");
const index_js_1 = require("language/src/index.js");
const dialogs_js_1 = require("designer/src/dialogs.js");
const choice_field_js_1 = require("viewer/src/choice-field.js");
const live_settings_js_1 = require("designer/src/live-settings.js");
const modes = ['auto', 'card', 'image', 'text'];
const labels = ['auto', 'none', 'inside', 'top', 'bottom', 'left', 'right', 'top-left', 'top-right', 'bottom-left', 'bottom-right'];
const owns = (record, path) => Object.prototype.hasOwnProperty.call(record, path);
function openSymbol(viewer, panel, commit) {
    const handle = (0, native_js_1.getViewerHandle)(viewer), document = handle.ownerDocument, snapshot = handle.runtime.snapshot();
    const decoded = (0, runtime_js_1.runtimeState)(handle.runtime).decoded, entry = handle.selectedEntry();
    if (!snapshot || !decoded || !entry || entry.definition.owner !== 'definition' || entry.definition.record.category === 'relation')
        throw Error('Select an element first.');
    const scopes = [];
    const appearanceNode = entry.appearance ? (0, index_js_1.findNode)(decoded, entry.appearance.ref) : undefined;
    if (entry.appearance && appearanceNode && !appearanceNode.implicit)
        scopes.push({ record: entry.appearance, label: 'This appearance' });
    scopes.push({ record: entry.definition, label: 'Shared element' });
    const assets = (0, native_js_2.records)(snapshot).filter(record => record.owner === 'asset' && (0, native_js_2.str)(record.record.media_type).startsWith('image/'));
    panel('Symbol & label', body => {
        const select = (container, name, options, value) => {
            if (name !== 'Apply symbol settings to')
                return (0, choice_field_js_1.choiceField)(container, name, options, value);
            const wrap = document.createElement('label');
            wrap.textContent = name;
            const control = document.createElement('select');
            control.setAttribute('aria-label', name);
            for (const option of options) {
                const item = document.createElement('option');
                item.value = option.value;
                item.textContent = option.label;
                control.append(item);
            }
            control.value = value;
            wrap.append(control);
            container.append(wrap);
            return control;
        };
        const scope = select(body, 'Apply symbol settings to', scopes.map((s, i) => ({ value: String(i), label: s.label })), '0');
        scope.dataset.ddnLiveIgnore = '';
        const title = document.createElement('p');
        title.textContent = (0, native_js_2.titleOf)(entry.definition.record);
        body.append(title);
        const guidance = document.createElement('p');
        guidance.className = 'ddn-appearance-message';
        guidance.textContent = 'Name position and gap apply to image symbols and unboxed text. Native / card keeps its profile labels.';
        body.append(guidance);
        const content = document.createElement('div');
        content.className = 'ddn-appearance-grid';
        body.append(content);
        const message = document.createElement('p');
        message.className = 'ddn-appearance-message';
        message.setAttribute('role', 'status');
        body.append(message);
        let chosen = 0, loading = true, ticket = 0, changes = {}, values = new Map(), origins = new Map();
        const effective = (path, fallback) => owns(changes, path) ? changes[path] ?? fallback : values.get(path) ?? fallback;
        const changed = (path, value) => { changes[path] = value; (0, live_settings_js_1.notifyLiveSettings)(body); message.textContent = value === undefined ? 'Using the inherited setting.' : 'Changes appear immediately.'; };
        const inherit = (name, path) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = 'Inherit';
            button.setAttribute('aria-label', 'Inherit ' + name);
            button.addEventListener('click', () => {
                changed(path, undefined);
                void (0, live_settings_js_1.flushLiveSettings)(body).then(() => {
                    if (body.isConnected)
                        render();
                }).catch(error => { message.textContent = error.message; });
            });
            content.append(button);
        };
        const render = () => {
            content.replaceChildren();
            const mode = select(content, 'Presentation', modes.map(value => ({ value, label: value === 'auto' ? 'Automatic' : value === 'card' ? 'Native / card' : value === 'image' ? 'Image symbol' : 'Unboxed text' })), String(effective('symbol.mode', 'auto')));
            mode.addEventListener('change', () => changed('symbol.mode', mode.value));
            inherit('presentation', 'symbol.mode');
            const imageValue = effective('symbol.image', null), imageRef = imageValue === null ? undefined : (0, native_js_2.object)(imageValue);
            const automatic = owns(changes, 'symbol.image') ? changes['symbol.image'] === undefined : !origins.has('symbol.image') || origins.get('symbol.image').startsWith('standard:');
            const imageKey = imageRef ? (0, native_js_2.refKey)({ file: (0, native_js_2.str)(imageRef.file, scopes[chosen].record.file), id: (0, native_js_2.str)(imageRef.id) }) : automatic ? 'inherit' : '';
            const options = [{ value: 'inherit', label: 'Automatic / inherited image' }, { value: '', label: 'None (disable inherited image)' }, ...assets.map(asset => ({ value: (0, native_js_2.refKey)(asset.ref), label: (0, native_js_2.titleOf)(asset.record) + ' · ' + asset.file }))];
            if (imageKey && !options.some(option => option.value === imageKey))
                options.push({ value: imageKey, label: 'Unavailable asset · ' + (0, native_js_2.str)(imageRef?.id) });
            const asset = select(content, 'Image asset', options, imageKey);
            asset.addEventListener('change', () => { const selected = assets.find(item => (0, native_js_2.refKey)(item.ref) === asset.value); changed('symbol.image', asset.value === 'inherit' ? undefined : selected ? { ...selected.ref } : null); });
            inherit('image asset', 'symbol.image');
            const position = select(content, 'Name position', labels.map(value => ({ value, label: value === 'auto' ? 'Automatic' : value === 'none' ? 'Hidden' : value.replaceAll('-', ' ') })), String(effective('symbol.label', 'auto')));
            position.addEventListener('change', () => changed('symbol.label', position.value));
            inherit('name position', 'symbol.label');
            const gap = (0, dialogs_js_1.numberField)(content, 'Label gap', String(effective('symbol.label_gap', 6)), { min: 0, max: 64, step: 1 });
            gap.removeAttribute('max');
            gap.step = 'any';
            (0, dialogs_js_1.syncNumberField)(gap);
            gap.addEventListener('input', () => changed('symbol.label_gap', gap.valueAsNumber));
            inherit('label gap', 'symbol.label_gap');
        };
        const readValues = async () => {
            const current = ticket, inspection = await viewer.inspect(scopes[chosen].record.ref);
            if (current !== ticket || !body.isConnected)
                return;
            values = new Map(inspection.properties.map(property => [property.path, property.effective]));
            origins = new Map(inspection.properties.map(property => [property.path, property.origin]));
        };
        const refresh = async () => {
            loading = true;
            ++ticket;
            content.replaceChildren();
            await readValues();
            loading = false;
            if (body.isConnected)
                render();
        };
        scope.addEventListener('change', event => {
            event.stopPropagation();
            const next = Number(scope.value);
            scope.value = String(chosen);
            scope.disabled = true;
            content.inert = true;
            void (0, live_settings_js_1.flushLiveSettings)(body).then(async () => {
                if (!body.isConnected)
                    return;
                chosen = next;
                scope.value = String(next);
                changes = {};
                await refresh();
            }).catch(error => { message.textContent = error.message; }).finally(() => { scope.disabled = false; content.inert = false; });
        });
        void refresh().catch(error => { message.textContent = error.message; });
        return async () => {
            if (loading)
                throw Error('Wait for the symbol settings to load.');
            for (const input of content.querySelectorAll('input[type=number]'))
                if (!input.checkValidity() || !Number.isFinite(input.valueAsNumber))
                    throw Error('Label gap must be a nonnegative number.');
            if (Object.keys(changes).length) {
                const pending = { ...changes }, target = scopes[chosen].record.ref;
                await commit(target, pending);
                for (const [path, value] of Object.entries(pending))
                    if (Object.hasOwn(changes, path) && JSON.stringify(changes[path]) === JSON.stringify(value))
                        delete changes[path];
                await readValues();
            }
        };
    });
}

},
"designer/src/view-layout-picker.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.EXTENDED_VIEW_LAYOUTS = void 0;
exports.viewLayoutLabel = viewLayoutLabel;
exports.viewLayoutDialog = viewLayoutDialog;
exports.viewLayoutSource = viewLayoutSource;
const view_surfaces_js_1 = require("profiles/src/view-surfaces.js");
const dialogs_js_1 = require("designer/src/dialogs.js");
const unavailable = ' Available in ScratchWeaver; unavailable in the open-source designer.';
const rawPageChoices = [
    { id: 'page-letter', label: 'Letter', detail: '8.5 × 11 in', hint: 'Letter paper · 8.5 × 11 inches (215.9 × 279.4 mm).', width: 816, height: 1056 },
    { id: 'page-legal', label: 'Legal', detail: '8.5 × 14 in', hint: 'Legal paper · 8.5 × 14 inches (215.9 × 355.6 mm).', width: 816, height: 1344 },
    { id: 'page-a1', label: 'A1', detail: '594 × 841 mm', hint: 'A1 paper · 594 × 841 mm.', width: 2245, height: 3179 },
    { id: 'page-a2', label: 'A2', detail: '420 × 594 mm', hint: 'A2 paper · 420 × 594 mm.', width: 1587, height: 2245 },
    { id: 'page-a3', label: 'A3', detail: '297 × 420 mm', hint: 'A3 paper · 297 × 420 mm.', width: 1123, height: 1587 },
    { id: 'page-a4', label: 'A4', detail: '210 × 297 mm', hint: 'A4 paper · 210 × 297 mm.', width: 794, height: 1123 },
    { id: 'page-a5', label: 'A5', detail: '148 × 210 mm', hint: 'A5 paper · 148 × 210 mm.', width: 559, height: 794 },
    { id: 'page-custom', label: 'Custom page', detail: 'Custom dimensions', hint: 'A physical page with a chosen width, height, units and orientation.', width: 816, height: 1056 },
];
const rawPresentationChoices = [
    { id: 'presentation-wide', label: 'Widescreen', detail: '16:9 · PPTX / ODP', hint: 'Widescreen presentation layout · 16:9 proportions for PPTX or ODP slides.', width: 1920, height: 1080 },
    { id: 'presentation-standard', label: 'Standard', detail: '4:3 · PPTX / ODP', hint: 'Standard presentation layout · 4:3 proportions for PPTX or ODP slides.', width: 1440, height: 1080 },
    { id: 'presentation-custom', label: 'Custom slide', detail: 'Custom proportions', hint: 'A presentation layout with chosen proportions for PPTX or ODP slides.', width: 1920, height: 1200 },
];
exports.EXTENDED_VIEW_LAYOUTS = Object.freeze([
    ...rawPageChoices.map(choice => Object.freeze({ ...choice, kind: 'page' })),
    ...rawPresentationChoices.map(choice => Object.freeze({ ...choice, kind: 'presentation' })),
]);
const pageChoices = rawPageChoices.map(choice => ({ ...choice, kind: 'page', unavailable: true, hint: choice.hint + unavailable }));
const presentationChoices = rawPresentationChoices.map(choice => ({ ...choice, kind: 'presentation', unavailable: true, hint: choice.hint + unavailable }));
const style = `
.ddn-ui-dialog.ddn-layout-dialog{max-height:min(780px,calc(100vh - 24px));max-height:min(780px,calc(100dvh - 24px))}
.ddn-layout-intro{margin:0 0 8px;font-size:12px;line-height:1.45;color:var(--ddn-ui-muted)}
.ddn-layout-group{margin-top:12px}.ddn-layout-group h4{margin:0 0 7px;font-size:12px;line-height:1.4;font-weight:650}.ddn-layout-group h4 small{font-weight:400;color:var(--ddn-ui-muted);margin-left:8px}
.ddn-layout-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(84px,1fr));gap:8px}
.ddn-ui-dialog .ddn-layout-card{position:relative;display:flex;flex-direction:column;align-items:center;justify-content:flex-start;gap:4px;min-width:0;min-height:100px;padding:8px 6px;border:1px solid var(--ddn-ui-border);border-radius:10px;background:var(--ddn-ui-input);color:var(--ddn-ui-text);text-align:center;white-space:normal}
.ddn-layout-card svg{display:block;width:100%;height:46px;color:var(--ddn-ui-accent);pointer-events:none}.ddn-layout-card strong{font-size:12px;line-height:1.3}.ddn-layout-card small{font-size:10px;line-height:1.3;color:var(--ddn-ui-muted);margin-top:auto}
.ddn-ui-dialog .ddn-layout-card:hover,.ddn-ui-dialog .ddn-layout-card:focus-visible{border-color:var(--ddn-ui-accent)}
.ddn-ui-dialog .ddn-layout-card:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:2px}
.ddn-ui-dialog .ddn-layout-card[aria-pressed=true]{border-color:var(--ddn-ui-accent);box-shadow:inset 0 0 0 1px var(--ddn-ui-accent);background:color-mix(in srgb,var(--ddn-ui-accent) 12%,var(--ddn-ui-input))}
.ddn-ui-dialog .ddn-layout-card[aria-disabled=true]{opacity:.48;cursor:not-allowed}.ddn-layout-card[aria-disabled=true] svg{color:var(--ddn-ui-muted)}
.ddn-layout-card[aria-pressed=true]::after{content:'✓';position:absolute;right:5px;top:3px;color:var(--ddn-ui-accent);font-size:13px;font-weight:700}
.ddn-layout-hint{position:sticky;top:0;z-index:2;margin:10px 0 0;min-height:42px;padding:8px 10px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-input);font-size:11px;line-height:1.45;color:var(--ddn-ui-muted)}
.ddn-layout-card{scroll-margin-top:140px;scroll-margin-bottom:8px}
@media(max-width:380px){.ddn-layout-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.ddn-ui-dialog .ddn-layout-card{min-height:94px;padding:6px}.ddn-layout-card svg{height:40px}}
@media(max-width:260px){.ddn-layout-grid{grid-template-columns:minmax(0,1fr)}}
`;
let nextHint = 0;
function preview(document, choice) {
    const NS = 'http://www.w3.org/2000/svg', svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 96 54');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    const el = (name, attrs) => {
        const node = document.createElementNS(NS, name);
        for (const [key, value] of Object.entries(attrs))
            node.setAttribute(key, String(value));
        svg.append(node);
        return node;
    };
    const paint = { fill: 'none', stroke: 'currentColor', 'stroke-width': 1.6, 'stroke-linecap': 'round', 'stroke-linejoin': 'round' };
    if (choice.kind === 'page') {
        el('path', { d: 'M33 3H55L65 13V51H33Z M55 3V13H65', ...paint });
        el('path', { d: 'M39 22H59 M39 29H59 M39 36H52', ...paint, opacity: .65 });
    }
    else if (choice.kind === 'dynamic') {
        el('rect', { x: 15, y: 5, width: 66, height: 44, rx: 3, ...paint, 'stroke-dasharray': '4 3' });
        el('rect', { x: 23, y: 14, width: 22, height: 13, rx: 2, ...paint });
        el('rect', { x: 52, y: 30, width: 22, height: 12, rx: 2, ...paint });
        el('path', { d: 'M45 21H63V30 M11 5H5V11 M85 43V49H91', ...paint });
    }
    else {
        const ratio = (choice.width ?? 16) / (choice.height ?? 9), h = 35, w = Math.min(75, h * ratio), x = (96 - w) / 2;
        el('rect', { x, y: 3, width: w, height: h, rx: choice.kind === 'monitor' ? 3 : 0, ...paint });
        el('path', { d: choice.kind === 'monitor' ? 'M48 39V46 M34 49H62' : 'M48 39V45 M48 45L37 51 M48 45L59 51', ...paint });
        el('path', { d: `M${x + 8} 11H${x + w - 8} M${x + 8} 17H${x + w / 2}`, ...paint, opacity: .65 });
        el('rect', { x: x + 8, y: 22, width: Math.max(9, w * .25), height: 9, rx: 1, ...paint, opacity: .55 });
        el('path', { d: `M${x + w * .56} 31V25H${x + w * .7}V20H${x + w - 8}`, ...paint });
    }
    return svg;
}
function viewLayoutLabel(preset) {
    return (0, view_surfaces_js_1.getViewSurfacePreset)(preset)?.label ?? exports.EXTENDED_VIEW_LAYOUTS.find(item => item.id === preset)?.label ?? 'Dynamic';
}
function viewLayoutDialog(host, options) {
    const document = host.ownerDocument;
    const extended = options.allowExtended === true;
    const isAdmitted = (id) => !!(0, view_surfaces_js_1.getViewSurfacePreset)(id) || (extended && exports.EXTENDED_VIEW_LAYOUTS.some(item => item.id === id));
    let selected = isAdmitted(options.selected) ? options.selected : 'dynamic';
    const dialog = (0, dialogs_js_1.createStandardDialog)(host, { title: 'Choose view layout', applyLabel: 'Continue', onApply() {
            if (!isAdmitted(selected))
                throw Error('Choose an available view layout.');
            dialog.close();
            options.onContinue(selected);
        } });
    dialog.element.classList.add('ddn-layout-dialog');
    dialog.element.style.setProperty('--ddn-ui-dialog-width', '760px');
    const css = document.createElement('style');
    css.textContent = style;
    const intro = document.createElement('p');
    intro.className = 'ddn-layout-intro';
    intro.textContent = 'Choose the size of the view. Next, choose the diagram or graph it displays.';
    const hint = document.createElement('p');
    hint.className = 'ddn-layout-hint';
    hint.id = 'ddn-layout-hint-' + (++nextHint);
    hint.setAttribute('role', 'tooltip');
    hint.setAttribute('aria-live', 'polite');
    dialog.body.append(css, intro, hint);
    const available = view_surfaces_js_1.VIEW_SURFACE_PRESETS.map(preset => ({
        id: preset.id, label: preset.label, kind: preset.id === 'dynamic' ? 'dynamic' : 'monitor',
        detail: preset.width && preset.height ? `${preset.width} × ${preset.height} px` : 'Fits its contents',
        hint: preset.description + (preset.id === 'dynamic' ? ' Uses the diagram type’s normal appearance defaults.' : ' Fixed size; content fits within the surface. Sans-serif text scales to the display, with dark text on a neutral white background. Customise colours, fonts and branding later.'),
        ...(preset.width && preset.height ? { width: preset.width, height: preset.height } : {}),
    }));
    const pages = extended ? exports.EXTENDED_VIEW_LAYOUTS.filter(item => item.kind === 'page') : pageChoices;
    const presentations = extended ? exports.EXTENDED_VIEW_LAYOUTS.filter(item => item.kind === 'presentation') : presentationChoices;
    const choicesById = new Map([...available, ...pages, ...presentations].map(choice => [choice.id, choice]));
    const defaultHint = () => {
        const focused = document.activeElement;
        return (focused && dialog.body.contains(focused) ? choicesById.get(focused.dataset.layout ?? '') : undefined)?.hint
            ?? choicesById.get(selected).hint;
    };
    hint.textContent = defaultHint();
    for (const [title, choices, closed] of [['Dynamic and TV dashboards', available, false], ['Physical pages', pages, !extended], ['Presentations', presentations, !extended]]) {
        const section = document.createElement('section');
        section.className = 'ddn-layout-group';
        const heading = document.createElement('h4');
        heading.textContent = title;
        if (closed) {
            const badge = document.createElement('small');
            badge.textContent = 'ScratchWeaver';
            heading.append(badge);
        }
        const grid = document.createElement('div');
        grid.className = 'ddn-layout-grid';
        grid.setAttribute('role', 'group');
        grid.setAttribute('aria-label', title);
        for (const choice of choices) {
            const tile = document.createElement('button');
            tile.type = 'button';
            tile.className = 'ddn-layout-card';
            tile.dataset.layout = choice.id;
            if (!choice.unavailable)
                tile.dataset.surfacePreset = choice.id;
            tile.setAttribute('aria-label', choice.label);
            tile.title = choice.hint;
            tile.setAttribute('aria-describedby', hint.id);
            if (choice.unavailable)
                tile.setAttribute('aria-disabled', 'true');
            else
                tile.setAttribute('aria-pressed', String(selected === choice.id));
            const label = document.createElement('strong');
            label.textContent = choice.label;
            const detail = document.createElement('small');
            detail.textContent = choice.detail;
            tile.append(preview(document, choice), label, detail);
            tile.addEventListener('click', () => {
                if (choice.unavailable)
                    return;
                selected = choice.id;
                for (const button of dialog.body.querySelectorAll('.ddn-layout-card[aria-pressed]'))
                    button.setAttribute('aria-pressed', String(button.dataset.layout === selected));
                hint.textContent = choice.hint;
            });
            tile.addEventListener('dblclick', () => {
                if (choice.unavailable)
                    return;
                selected = choice.id;
                for (const button of dialog.body.querySelectorAll('.ddn-layout-card[aria-pressed]'))
                    button.setAttribute('aria-pressed', String(button.dataset.layout === selected));
                dialog.applyButton?.click();
            });
            tile.addEventListener('mouseenter', () => { hint.textContent = choice.hint; });
            tile.addEventListener('focus', () => { hint.textContent = choice.hint; });
            tile.addEventListener('mouseleave', () => {
                if (document.activeElement !== tile)
                    hint.textContent = defaultHint();
            });
            tile.addEventListener('blur', () => {
                if (!tile.matches(':hover'))
                    hint.textContent = defaultHint();
            });
            grid.append(tile);
        }
        section.append(heading, grid);
        dialog.body.append(section);
    }
    if (options.onBack) {
        const back = document.createElement('button');
        back.type = 'button';
        back.textContent = 'Back';
        back.addEventListener('click', () => { dialog.close(); options.onBack(selected); });
        dialog.footer.prepend(back);
    }
    return dialog;
}
function viewLayoutSource(preset, allowExtended = false) {
    if ((0, view_surfaces_js_1.getViewSurfacePreset)(preset))
        return preset === 'dynamic' ? '' : `    with\n        surface.preset ${preset}\n`;
    const ext = allowExtended ? exports.EXTENDED_VIEW_LAYOUTS.find(item => item.id === preset) : undefined;
    if (ext && ext.width && ext.height)
        return `    with\n        surface.width ${ext.width}\n        surface.height ${ext.height}\n`;
    throw Error('Choose an available view layout.');
}

},
"designer/src/view-picker.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.profileDisplayName = profileDisplayName;
exports.viewTypePicker = viewTypePicker;
exports.diagramHeader = diagramHeader;
const core_js_1 = require("profiles/src/core.js");
const index_js_1 = require("language/src/index.js");
const view_previews_js_1 = require("designer/src/view-previews.js");
function profileDisplayName(id) {
    return `${(0, view_previews_js_1.profileLabel)(id)} (${id})`;
}
const pickerStyle = `
.ddn-ui-dialog.ddn-view-picker-dialog{max-height:min(760px,calc(100vh - 24px));max-height:min(760px,calc(100dvh - 24px))}
.ddn-view-type-settings[hidden]{display:none}
.ddn-view-picker{min-width:0;--ddn-picker-card:var(--ddn-ui-input)}
.ddn-view-picker-heading{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px;min-width:0}
.ddn-view-picker-heading h4{margin:0;font-size:14px;line-height:1.4;font-weight:650;overflow-wrap:anywhere}
.ddn-view-picker-step{color:var(--ddn-ui-muted);font-size:11px;white-space:nowrap}
.ddn-view-picker-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(128px,1fr));gap:9px;align-items:stretch;min-width:0}
.ddn-view-picker-grid[aria-label="Diagram types"]{max-height:min(320px,34dvh);overflow:auto;padding:3px;scrollbar-gutter:stable}
.ddn-ui-dialog .ddn-view-picker-card{position:relative;display:flex;flex-direction:column;align-items:stretch;justify-content:flex-start;gap:5px;min-width:0;min-height:118px;padding:8px;border:1px solid var(--ddn-ui-border);border-radius:10px;background:var(--ddn-picker-card);color:var(--ddn-ui-text);text-align:center;line-height:1.3;overflow-wrap:anywhere}
.ddn-ui-dialog .ddn-view-picker-card:hover{border-color:var(--ddn-ui-accent);background:color-mix(in srgb,var(--ddn-ui-accent) 9%,var(--ddn-picker-card));color:var(--ddn-ui-text)}
.ddn-ui-dialog .ddn-view-picker-card:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:2px}
.ddn-ui-dialog .ddn-view-picker-card[aria-pressed=true]{border-color:var(--ddn-ui-accent);box-shadow:inset 0 0 0 1px var(--ddn-ui-accent);background:color-mix(in srgb,var(--ddn-ui-accent) 12%,var(--ddn-picker-card))}
.ddn-view-picker-preview{display:block;aspect-ratio:5/3;height:76px;width:100%;color:var(--ddn-ui-accent);pointer-events:none}
.ddn-view-picker-preview svg{display:block;width:100%;height:100%}
.ddn-view-picker-name{font-size:12px;font-weight:600;line-height:1.3}
.ddn-view-picker-meta{font-size:10px;color:var(--ddn-ui-muted);margin-top:auto}
.ddn-view-picker-check{display:none;position:absolute;right:5px;top:5px;width:18px;height:18px;align-items:center;justify-content:center;border-radius:50%;background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);font-size:12px;font-weight:700}
.ddn-view-picker-card[aria-pressed=true]>.ddn-view-picker-check{display:flex}
.ddn-view-picker-tools{display:flex;align-items:center;gap:10px;flex-wrap:wrap;margin:0 0 10px}
.ddn-ui-dialog .ddn-view-picker-back{display:inline-flex;align-items:center;gap:6px;flex:none;font-size:12px}
.ddn-view-picker-tools label{flex:1;min-width:160px;margin:0}
.ddn-view-picker-tools label>input{margin-top:0}
.ddn-view-picker-result{font-size:11px;color:var(--ddn-ui-muted);min-height:16px;margin:8px 0}
.ddn-view-picker-empty{grid-column:1/-1;text-align:center;padding:28px 12px;color:var(--ddn-ui-muted);font-size:13px}
.ddn-view-picker-status{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:380px){.ddn-view-picker-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}.ddn-ui-dialog .ddn-view-picker-card{padding:6px;min-height:110px}.ddn-view-picker-preview{height:66px}}
@media(max-width:260px){.ddn-view-picker-grid{grid-template-columns:minmax(0,1fr)}}
`;
function viewTypePicker(body, profiles, label = 'View profile', selected) {
    const document = body.ownerDocument;
    const element = document.createElement('section');
    element.className = 'ddn-view-picker';
    element.setAttribute('aria-label', label);
    const style = document.createElement('style');
    style.textContent = pickerStyle;
    const content = document.createElement('div');
    const status = document.createElement('p');
    status.className = 'ddn-view-picker-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    element.append(style, content, status);
    body.append(element);
    const dialog = body.closest('.ddn-ui-dialog');
    dialog?.classList.add('ddn-view-picker-dialog');
    dialog?.style.setProperty('--ddn-ui-dialog-width', '760px');
    const available = [...new Map(profiles.map(profile => [profile.id, { id: profile.id, method: (0, core_js_1.knownProfile)(profile.id)?.method ?? profile.method }])).values()];
    const methods = [...new Set(available.map(profile => profile.method))];
    const current = available.find(profile => profile.id === selected);
    const listeners = new Set();
    let value = '';
    const choose = (next) => {
        value = next;
        for (const listener of [...listeners])
            listener(value);
    };
    const heading = (title, step) => {
        const row = document.createElement('div');
        row.className = 'ddn-view-picker-heading';
        const text = document.createElement('h4');
        text.textContent = title;
        const progress = document.createElement('span');
        progress.className = 'ddn-view-picker-step';
        progress.textContent = `Step ${step} of 2`;
        row.append(text, progress);
        return row;
    };
    const card = (name, preview, meta) => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'ddn-view-picker-card';
        button.setAttribute('aria-label', name);
        const image = document.createElement('span');
        image.className = 'ddn-view-picker-preview';
        preview.setAttribute('aria-hidden', 'true');
        preview.setAttribute('focusable', 'false');
        image.append(preview);
        const caption = document.createElement('span');
        caption.className = 'ddn-view-picker-name';
        caption.textContent = name;
        button.append(image, caption);
        if (meta) {
            const note = document.createElement('span');
            note.className = 'ddn-view-picker-meta';
            note.textContent = meta;
            button.append(note);
        }
        return button;
    };
    function showMethods(focus) {
        content.replaceChildren(heading('Choose a diagram method', 1));
        const grid = document.createElement('div');
        grid.className = 'ddn-view-picker-grid';
        grid.setAttribute('role', 'group');
        grid.setAttribute('aria-label', 'Diagram methods');
        for (const method of methods) {
            const count = available.filter(profile => profile.method === method).length;
            const tile = card((0, view_previews_js_1.methodLabel)(method), (0, view_previews_js_1.methodPreview)(document, method), `${count} diagram ${count === 1 ? 'type' : 'types'}${current?.method === method ? ' · Current' : ''}`);
            tile.dataset.method = method;
            tile.addEventListener('click', () => showTypes(method));
            grid.append(tile);
        }
        if (!methods.length) {
            const empty = document.createElement('p');
            empty.className = 'ddn-view-picker-empty';
            empty.textContent = 'No diagram methods are available in this workarea.';
            grid.append(empty);
        }
        content.append(grid);
        if (focus)
            [...grid.querySelectorAll('button')].find(button => button.dataset.method === focus)?.focus();
    }
    function showTypes(method) {
        choose('');
        const types = available.filter(profile => profile.method === method);
        content.replaceChildren(heading((0, view_previews_js_1.methodLabel)(method), 2));
        const tools = document.createElement('div');
        tools.className = 'ddn-view-picker-tools';
        const back = document.createElement('button');
        back.type = 'button';
        back.className = 'ddn-view-picker-back';
        back.setAttribute('aria-label', 'All diagram methods');
        back.textContent = '← All methods';
        back.addEventListener('click', () => { choose(''); status.textContent = 'Choose a diagram method.'; showMethods(method); });
        const searchField = document.createElement('label'), search = document.createElement('input');
        search.type = 'search';
        search.placeholder = 'Find a diagram type';
        search.setAttribute('aria-label', 'Find a diagram type');
        searchField.append(search);
        tools.append(back, searchField);
        const result = document.createElement('p');
        result.className = 'ddn-view-picker-result';
        const grid = document.createElement('div');
        grid.className = 'ddn-view-picker-grid';
        grid.setAttribute('role', 'group');
        grid.setAttribute('aria-label', 'Diagram types');
        content.append(tools, result, grid);
        const renderTypes = () => {
            const term = search.value.trim().toLocaleLowerCase();
            const matches = types.filter(profile => `${(0, view_previews_js_1.profileLabel)(profile.id)} ${profile.id}`.toLocaleLowerCase().includes(term));
            result.textContent = term ? `${matches.length} of ${types.length} diagram types` : `${types.length} diagram ${types.length === 1 ? 'type' : 'types'} — choose one to continue`;
            grid.replaceChildren();
            for (const profile of matches) {
                const tile = card((0, view_previews_js_1.profileLabel)(profile.id), (0, view_previews_js_1.profilePreview)(document, profile.id), current?.id === profile.id ? 'Current type' : undefined);
                tile.dataset.profile = profile.id;
                tile.title = (0, view_previews_js_1.profileLabel)(profile.id);
                tile.setAttribute('aria-pressed', String(value === profile.id));
                const check = document.createElement('span');
                check.className = 'ddn-view-picker-check';
                check.setAttribute('aria-hidden', 'true');
                check.textContent = '✓';
                tile.append(check);
                tile.addEventListener('click', () => {
                    choose(profile.id);
                    for (const button of grid.querySelectorAll('button[data-profile]'))
                        button.setAttribute('aria-pressed', String(button.dataset.profile === value));
                    status.textContent = `${(0, view_previews_js_1.profileLabel)(profile.id)} selected.`;
                });
                tile.addEventListener('dblclick', () => {
                    choose(profile.id);
                    for (const button of grid.querySelectorAll('button[data-profile]'))
                        button.setAttribute('aria-pressed', String(button.dataset.profile === value));
                    status.textContent = `${(0, view_previews_js_1.profileLabel)(profile.id)} selected.`;
                    const hostDialog = tile.closest('[role="dialog"]');
                    const primary = hostDialog?.querySelector('button[data-ddn-apply], .ddn-form-actions button:first-child');
                    if (primary && !primary.disabled)
                        primary.click();
                });
                grid.append(tile);
            }
            if (!matches.length) {
                const empty = document.createElement('p');
                empty.className = 'ddn-view-picker-empty';
                empty.textContent = 'No diagram types match your search.';
                grid.append(empty);
            }
        };
        search.addEventListener('input', () => { choose(''); renderTypes(); status.textContent = result.textContent; });
        renderTypes();
        back.focus();
        status.textContent = `${(0, view_previews_js_1.methodLabel)(method)}. Choose a diagram type.`;
    }
    showMethods();
    return { element, get value() { return value; }, onChange(listener) { listeners.add(listener); } };
}
function diagramHeader(name, profile, title) {
    const header = profile === 'ddn@1' ? 'erd ' + (0, index_js_1.quoteText)(name)
        : profile === 'mindmap.basic@1' ? 'mindmap ' + (0, index_js_1.quoteText)(name)
            : 'view ' + (0, index_js_1.quoteText)(name) + ' as ' + (0, index_js_1.quoteText)(profile);
    return header + (title === undefined ? '' : ' : ' + (0, index_js_1.quoteText)(title));
}

},
"designer/src/view-previews.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.profilePreview = exports.methodPreview = exports.profileLabel = exports.methodLabel = void 0;
const profiles = {
    'ddn@1': ['DDN / ERD', 'erd'],
    'flow.basic@1': ['Flowchart', 'flow'],
    'dfd.gane_sarson@1': ['Gane–Sarson data flow', 'dfd', 1],
    'dfd.yourdon@1': ['Yourdon data flow', 'dfd'],
    'uml.structure@1': ['Class diagram', 'class'],
    'uml.structure@2': ['Class diagram — detailed', 'class', 1],
    'uml.deployment@1': ['Deployment diagram', 'deployment'],
    'uml.composite@1': ['Composite structure', 'composite'],
    'uml.usecase@1': ['Use cases', 'usecase'],
    'requirements.basic@1': ['Requirements', 'requirements'],
    'chen.basic@1': ['Chen ERD', 'chen'],
    'matrix.raci@1': ['RACI responsibilities', 'matrix', 1],
    'matrix.crud@1': ['CRUD matrix', 'matrix', 2],
    'matrix.relations@1': ['Relationship matrix', 'matrix', 3],
    'panels.basic@1': ['Panels', 'panels'],
    'canvas.bmc@1': ['Business model canvas', 'canvas', 1],
    'canvas.lean@1': ['Lean canvas', 'canvas', 2],
    'canvas.pest@1': ['PEST analysis', 'quadrant', 1],
    'canvas.pestle@1': ['PESTLE analysis', 'canvas', 3],
    'canvas.porter5@1': ['Porter’s five forces', 'forces'],
    'canvas.empathy@1': ['Empathy map', 'empathy'],
    'canvas.scorecard@1': ['Balanced scorecard', 'scorecard'],
    'table.records@1': ['Table', 'table'],
    'chart.basic@1': ['Bar, line & area chart', 'chart'],
    'chart.radar@1': ['Radar chart', 'radar'],
    'chart.funnel@1': ['Funnel chart', 'funnel'],
    'timeline.basic@1': ['Timeline', 'timeline'],
    'fishbone.basic@1': ['Fishbone', 'fishbone'],
    'matrix.heatmap@1': ['Matrix heatmap', 'heatmap', 1],
    'chart.quality@1': ['Quality / control chart', 'quality'],
    'state.flat@1': ['State transitions', 'state'],
    'decision.rules@1': ['Decision table', 'table', 1],
    'panels.composed@1': ['Composed dashboard', 'panels', 1],
    'uml.usecase@2': ['Use cases — detailed', 'usecase', 1],
    'uml.usecase@3': ['Use cases — extended', 'usecase', 2],
    'chen.binary@2': ['Binary relationships', 'chen', 1],
    'chen.nary@3': ['N-ary relationships', 'chen', 2],
    'flow.documented@2': ['Documented flowchart', 'flow', 1],
    'chart.gauge@1': ['Gauge', 'gauge'],
    'chart.candlestick@1': ['Candlestick chart', 'candlestick'],
    'chart.treemap@1': ['Treemap', 'treemap'],
    'chart.sankey@1': ['Sankey diagram', 'sankey'],
    'c4.context@1': ['System context', 'c4'],
    'c4.container@1': ['Containers', 'c4', 1],
    'c4.component@1': ['Components', 'c4', 2],
    'org.tree@1': ['Organization chart', 'tree', 1],
    'wbs.tree@1': ['Work breakdown', 'tree', 2],
    'mindmap.basic@1': ['Mind map', 'mindmap'],
    'concept.map@1': ['Concept map', 'concept'],
    'epc.basic@1': ['Event-driven process', 'epc'],
    'matrix.bcg@1': ['BCG portfolio matrix', 'quadrant', 2],
    'matrix.ansoff@1': ['Ansoff growth matrix', 'quadrant', 3],
    'matrix.tows@1': ['TOWS strategy matrix', 'quadrant', 4],
    'panels.journey@1': ['Customer journey', 'journey'],
    'matrix.storymap@1': ['User story map', 'storymap'],
    'erd.crowfoot@1': ['Crow’s-foot ERD', 'erd', 1],
    'panels.pyramid@1': ['Pyramid', 'pyramid'],
    'panels.venn@1': ['Venn diagram', 'venn'],
    'uml.sequence@1': ['Sequence diagram', 'sequence'],
    'uml.sequence@2': ['Sequence diagram — detailed', 'sequence', 1],
    'uml.communication@1': ['Communication diagram', 'communication'],
    'uml.communication@2': ['Communication diagram — detailed', 'communication', 1],
    'uml.object@1': ['Object diagram', 'object'],
    'uml.object@2': ['Object diagram — detailed', 'object', 1],
    'state.composite@1': ['Nested states', 'state', 1],
    'uml.statemachine@1': ['State machine', 'state', 2],
    'uml.activity@1': ['Activity diagram', 'activity'],
    'uml.activity@2': ['Activity diagram — detailed', 'activity', 1],
    'bpmn.basic@1': ['Collaboration', 'bpmn'],
    'bpmn.process@1': ['Process', 'bpmn', 1],
    'bpmn.choreography@1': ['Choreography', 'bpmn', 2],
    'bpmn.conversation@1': ['Conversation', 'bpmn', 3],
    'uml.timing@1': ['Timing diagram', 'timing'],
    'uml.timing@2': ['Timing diagram — detailed', 'timing', 1],
    'uml.interaction_overview@1': ['Interaction overview', 'activity', 2],
    'uml.interaction_overview@2': ['Interaction overview — detailed', 'activity', 3],
    'uml.profile@1': ['UML profile', 'packages', 1],
    'cmmn.basic@1': ['Case management', 'case'],
    'cmmn.complete@1': ['Case management — detailed', 'case', 1],
    'sysml.bdd@1': ['Block definition', 'blocks'],
    'sysml.ibd@1': ['Internal blocks', 'composite', 1],
    'sysml.parametric@1': ['Parametric constraints', 'parametric'],
    'archimate.basic@1': ['Architecture layers', 'architecture'],
    'pert.cpm@1': ['PERT / critical path', 'pert'],
    'fault.tree@1': ['Fault tree', 'fault'],
    'event.tree@1': ['Event tree', 'eventtree'],
    'network.basic@1': ['Network diagram', 'network'],
    'network.rack@1': ['Rack layout', 'rack'],
    'wireframe.ui@1': ['Interface wireframe', 'wireframe'],
    'family.tree@1': ['Family tree', 'tree', 3],
    'chart.histogram@1': ['Histogram', 'histogram'],
    'chart.density@1': ['Density plot', 'density'],
    'chart.qq@1': ['Q–Q plot', 'qq'],
    'chart.quantiledot@1': ['Quantile dot plot', 'quantiledot'],
    'chart.dotplot@1': ['Dot plot', 'dotplot'],
    'chart.boxplot@1': ['Box plot', 'boxplot'],
    'chart.violin@1': ['Violin plot', 'violin'],
    'chart.beeswarm@1': ['Beeswarm plot', 'beeswarm'],
    'chart.topk@1': ['Ranked values', 'ranked'],
    'chart.tidytree@1': ['Tidy tree', 'tidytree'],
    'chart.radialtree@1': ['Radial tree', 'radialtree'],
    'chart.circlepack@1': ['Circle packing', 'circlepack'],
    'chart.sunburst@1': ['Sunburst', 'sunburst'],
    'chart.packedbubble@1': ['Packed bubbles', 'bubbles'],
    'chart.heatmap@1': ['Heatmap', 'heatmap'],
    'chart.densityheatmap@1': ['Density heatmap', 'heatmap', 2],
    'chart.calendar@1': ['Calendar heatmap', 'calendar'],
    'chart.parallelcoords@1': ['Parallel coordinates', 'parallel'],
    'chart.wordcloud@1': ['Word cloud', 'wordcloud'],
    'chart.arc@1': ['Arc diagram', 'arc'],
    'chart.force@1': ['Force-directed graph', 'force'],
    'chart.edgebundle@1': ['Bundled edges', 'bundle'],
    'geo.choropleth@1': ['Choropleth map', 'map', 1],
    'geo.symbols@1': ['Symbol map', 'map', 2],
    'geo.outline@1': ['Outline map', 'map'],
    'sysml.requirements@1': ['SysML requirements', 'requirements', 1],
    'sysml.bdd@2': ['Block definition — detailed', 'blocks', 1],
    'sysml.ibd@2': ['Internal blocks — detailed', 'composite', 2],
    'sysml.parametric@2': ['Parametric constraints — detailed', 'parametric', 1],
    'sysml.package@1': ['Package diagram', 'packages'],
    'sysml.usecase@1': ['SysML use cases', 'usecase', 1],
    'sysml.activity@1': ['SysML activities', 'activity', 1],
    'sysml.sequence@1': ['SysML sequence', 'sequence', 1],
    'sysml.statemachine@1': ['SysML state machine', 'state', 2],
    'dmn.drd@1': ['Decision requirements', 'decision'],
    'soaml.services@1': ['Service architecture', 'services'],
    'uaf.strategic@1': ['Strategic architecture', 'uaf', 0],
    'uaf.operational@1': ['Operational architecture', 'uaf', 1],
    'uaf.services@1': ['Service architecture', 'services', 1],
    'uaf.systems@1': ['Systems architecture', 'uaf', 2],
    'uaf.personnel@1': ['Personnel architecture', 'tree', 1],
    'uaf.resources@1': ['Resource architecture', 'uaf', 3],
    'uaf.security@1': ['Security architecture', 'uaf', 4],
    'uaf.projects@1': ['Project architecture', 'uaf', 5],
    'uaf.standards@1': ['Standards architecture', 'uaf', 6],
    'uaf.actualresources@1': ['Actual resources', 'rack', 1],
    'uaf.dictionary@1': ['Architecture dictionary', 'table', 2],
    'uaf.summary@1': ['Architecture summary', 'panels', 1],
    'flow.iso5807@1': ['ISO 5807 flowchart', 'flow', 2],
    'c4.deployment@1': ['Deployment', 'deployment', 1],
    'c4.dynamic@1': ['Dynamic interactions', 'communication', 1],
    'epc.complete@1': ['Event-driven process — detailed', 'epc', 1],
    'msc.basic@1': ['Message sequence chart', 'sequence', 2],
    'idef0.basic@1': ['Function model', 'idef'],
    'petri.basic@1': ['Petri net', 'petri'],
    'orm.basic@1': ['Object-role model', 'orm'],
    'vsm.basic@1': ['Value stream map', 'vsm'],
    'sdl.basic@1': ['Specification & description', 'sdl'],
    'sdl.process@1': ['SDL process', 'sdl', 1],
    'fbd.basic@1': ['Function block diagram', 'fbd'],
    'ladder.basic@1': ['Ladder logic', 'ladder'],
};
const methods = {
    MT01: ['DDN', 'erd'], MT02: ['UML', 'class'], MT03: ['Chen', 'chen'],
    MT04: ['Flowchart', 'flow'], MT05: ['BPMN', 'bpmn', 1], MT06: ['CMMN', 'case'],
    MT07: ['DMN', 'decision'], MT08: ['C4', 'c4', 1], MT09: ['DFD', 'dfd'],
    MT10: ['SysML', 'parametric'], MT11: ['ArchiMate', 'architecture'], MT12: ['EPC', 'epc'],
    MT13: ['IDEF0', 'idef'], MT14: ['Petri nets', 'petri'], MT15: ['ORM', 'orm'],
    MT16: ['Value stream', 'vsm'], MT17: ['SDL', 'sdl'], MT18: ['MSC', 'sequence', 2],
    MT19: ['SoaML', 'services'], MT20: ['UAF', 'uaf'], MT21: ['Electrical / control', 'circuit'],
};
const methodLabel = (id) => methods[id]?.[0] ?? id;
exports.methodLabel = methodLabel;
const profileLabel = (id) => profiles[id]?.[0] ?? id;
exports.profileLabel = profileLabel;
const NS = 'http://www.w3.org/2000/svg';
const ink = 'var(--ddn-ui-text, #334155)', muted = 'var(--ddn-ui-muted, #64748b)';
const colours = ['#639cea', '#38b5a1', '#bf8bea', '#dba34c'];
function preview(document, example) {
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 160 96');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    const add = (tag, attrs) => {
        const element = document.createElementNS(NS, tag);
        for (const [key, value] of Object.entries(attrs))
            element.setAttribute(key, String(value));
        svg.append(element);
        return element;
    };
    const path = (d, colour = ink, width = 1.8, fill = 'none', opacity = 1) => add('path', { d, stroke: colour, 'stroke-width': width, fill, opacity });
    const line = (x, y, x2, y2, colour = muted, width = 1.8) => path(`M${x},${y}L${x2},${y2}`, colour, width);
    const rect = (x, y, w, h, colour = colours[0], radius = 3, solid = false) => add('rect', { x, y, width: w, height: h, rx: radius, stroke: colour, 'stroke-width': 1.8, fill: colour, 'fill-opacity': solid ? .65 : .13 });
    const circle = (x, y, r, colour = colours[0], solid = false) => add('circle', { cx: x, cy: y, r, stroke: colour, 'stroke-width': 1.8, fill: colour, 'fill-opacity': solid ? .8 : .13 });
    const ellipse = (x, y, rx, ry, colour = colours[0]) => add('ellipse', { cx: x, cy: y, rx, ry, stroke: colour, 'stroke-width': 1.8, fill: colour, 'fill-opacity': .13 });
    const text = (x, y, value, size = 9, colour = ink) => { const e = add('text', { x, y, fill: colour, stroke: 'none', 'font-size': size, 'font-family': 'system-ui,sans-serif', 'font-weight': 600, 'text-anchor': 'middle' }); e.textContent = value; return e; };
    const arrow = (x, y, x2, y2, colour = muted) => {
        line(x, y, x2, y2, colour);
        const a = Math.atan2(y2 - y, x2 - x), r = 4;
        path(`M${x2 - r * Math.cos(a - .5)},${y2 - r * Math.sin(a - .5)}L${x2},${y2}L${x2 - r * Math.cos(a + .5)},${y2 - r * Math.sin(a + .5)}`, colour);
    };
    const diamond = (x, y, w = 13, h = 10, colour = colours[2]) => path(`M${x - w},${y}L${x},${y - h}L${x + w},${y}L${x},${y + h}Z`, colour, 1.8, colour, .8);
    const labelLines = (x, y, w, count = 2) => {
        for (let i = 0; i < count; i++)
            line(x, y + i * 6, x + w - (i % 2) * w * .2, y + i * 6, muted, 1);
    };
    const box = (x, y, w = 38, h = 30, colour = colours[0], rows = 2) => { rect(x, y, w, h, colour); line(x, y + 10, x + w, y + 10, colour, 1.2); labelLines(x + 6, y + 17, w - 12, rows); };
    const actor = (x, y, colour = ink) => { circle(x, y, 4, colour); path(`M${x},${y + 4}V${y + 18}M${x - 8},${y + 10}H${x + 8}M${x},${y + 18}L${x - 7},${y + 28}M${x},${y + 18}L${x + 7},${y + 28}`, colour, 1.5); };
    const axes = () => { path('M20,13V79H145', muted, 1.2); };
    const dash = (d, colour = muted) => { const p = path(d, colour, 1.2); p.setAttribute('stroke-dasharray', '4 4'); };
    const nodes = (points, edges, r = 5) => {
        for (const [a, b] of edges)
            line(...points[a], ...points[b]);
        points.forEach(([x, y], i) => circle(x, y, r, colours[i % 4], true));
    };
    const [name, kind, variant = 0] = example ?? ['Unavailable preview', 'unknown'];
    svg.dataset.preview = kind;
    switch (kind) {
        case 'erd': {
            box(8, 11, 43, 37);
            box(105, 48, 45, 37, colours[1], 3);
            box(70, 10, 34, 25, colours[2], 1);
            path('M51,31H69V64H105', muted);
            path('M87,35V48H128', muted);
            if (variant)
                path('M96,58L105,64L96,70M58,25V37M61,25V37', colours[1]);
            else {
                circle(69, 31, 2, colours[0], true);
                circle(69, 64, 2, colours[1], true);
            }
            break;
        }
        case 'class':
        case 'object':
        case 'blocks': {
            box(57, 7, 46, 31, colours[0], kind === 'object' ? 2 : 1);
            box(9, 58, 49, 31, colours[1], 2);
            box(102, 58, 49, 31, colours[2], 2);
            path('M34,58V48H126V58M80,48V38', muted);
            if (kind === 'class')
                path('M75,44L80,38L85,44Z', ink, 1.2, 'var(--ddn-ui-surface,#fff)');
            if (kind === 'blocks') {
                text(80, 16, '«block»', 7);
                rect(7, 67, 4, 6, colours[1], 0);
                rect(149, 67, 4, 6, colours[2], 0);
            }
            if (kind === 'object') {
                line(66, 14, 93, 14, colours[0], 1);
                line(18, 65, 47, 65, colours[1], 1);
            }
            if (variant) {
                dash('M58,75H102');
                text(80, 69, '1..*', 8);
            }
            break;
        }
        case 'chen': {
            rect(6, 39, 38, 24, colours[0], 0);
            rect(116, 39, 38, 24, colours[1], 0);
            line(44, 51, 66, 51);
            line(94, 51, 116, 51);
            diamond(80, 51, 14, 11);
            ellipse(22, 14, 17, 7);
            line(24, 21, 24, 39);
            ellipse(139, 14, 17, 7, colours[1]);
            line(138, 21, 138, 39);
            if (variant === 2) {
                rect(61, 76, 38, 15, colours[3], 0);
                line(80, 62, 80, 76);
            }
            else {
                ellipse(79, 17, 18, 8, colours[2]);
                line(80, 25, 80, 40);
            }
            if (variant === 1) {
                text(51, 45, '1', 8);
                text(108, 45, 'N', 8);
            }
            break;
        }
        case 'flow':
        case 'activity':
        case 'sdl': {
            circle(14, 21, 5, colours[0], true);
            arrow(19, 21, 39, 21);
            rect(39, 10, 37, 22, colours[0], kind === 'sdl' ? 0 : 7);
            arrow(76, 21, 99, 21);
            diamond(111, 21, 12, 11);
            path('M123,21H144V67H123M111,32V52', muted);
            rect(94, 52, 34, 28, colours[1], kind === 'sdl' ? 0 : 5);
            rect(20, 56, 42, 24, colours[2], 4);
            arrow(94, 68, 62, 68);
            if (kind === 'activity') {
                path('M79,53V82', ink, 4);
                if (variant > 1)
                    text(41, 71, 'ref', 10);
            }
            if (kind === 'sdl')
                path('M20,56H57L65,68L57,80H20Z', colours[2]);
            if (kind === 'flow' && variant) {
                path('M20,74Q31,66 41,74T62,74', colours[2]);
                if (variant === 2)
                    path('M39,10L34,32M47,10L42,32', colours[0]);
            }
            break;
        }
        case 'dfd': {
            rect(6, 13, 31, 21, colours[0], 0);
            line(37, 24, 55, 24);
            arrow(55, 24, 55, 42);
            if (variant)
                rect(37, 42, 39, 31, colours[1], 6);
            else
                circle(57, 56, 18, colours[1]);
            arrow(76, 56, 99, 56);
            if (variant)
                rect(100, 42, 36, 31, colours[2], 6);
            else
                circle(119, 56, 18, colours[2]);
            path('M119,38V21H140', muted);
            path('M102,8H150M102,27H150', colours[3]);
            arrow(56, 74, 56, 85);
            path('M13,80H42M13,91H42', colours[0]);
            break;
        }
        case 'usecase': {
            actor(17, 36);
            rect(46, 7, 106, 80, colours[0], 1);
            ellipse(99, 29, 30, 12, colours[1]);
            ellipse(99, 66, 30, 12, colours[2]);
            line(25, 48, 70, 29);
            line(25, 48, 69, 66);
            if (variant)
                dash('M99,42V54');
            if (variant === 2) {
                ellipse(139, 48, 9, 6, colours[3]);
                dash('M122,35L133,44');
            }
            break;
        }
        case 'requirements': {
            box(8, 14, 54, 40, colours[0], 3);
            box(99, 41, 52, 41, colours[1], 3);
            dash('M63,36H80V61H99');
            text(35, 23, variant ? '«requirement»' : 'REQ-01', 7);
            text(125, 50, 'REQ-02', 7);
            rect(99, 8, 45, 18, colours[2]);
            dash('M121,26V41');
            break;
        }
        case 'matrix':
        case 'table': {
            const w = kind === 'matrix' ? 24 : 29, cols = kind === 'matrix' ? 5 : 4;
            rect(15, 9, w * cols, 77, colours[0], 2);
            rect(15, 9, w * cols, 14, colours[0], 1, true);
            for (let x = 1; x < cols; x++)
                line(15 + x * w, 9, 15 + x * w, 86, muted, 1);
            for (let y = 1; y < 5; y++)
                line(15, 23 + y * 13, 15 + w * cols, 23 + y * 13, muted, 1);
            if (kind === 'matrix') {
                for (let y = 0; y < 4; y++)
                    for (let x = 1; x < 5; x++) {
                        if ((x + y) % 3 !== 0)
                            text(27 + x * w, 33 + y * 13, variant === 1 ? 'RACI'[(x + y) % 4] : variant === 2 ? 'CRUD'[(x + y) % 4] : '●', 8, colours[(x + y) % 4]);
                    }
            }
            else {
                for (let y = 0; y < 4; y++) {
                    labelLines(21, 31 + y * 13, 17, 1);
                    if (variant === 1) {
                        text(58, 34 + y * 13, y % 2 ? '≤' : '≥', 9);
                        text(119, 34 + y * 13, y % 2 ? 'Yes' : 'No', 8, colours[1]);
                    }
                    else
                        labelLines(52, 31 + y * 13, 65, 1);
                }
            }
            break;
        }
        case 'panels':
        case 'wireframe': {
            rect(7, 7, 146, 82, colours[0], 4);
            line(7, 21, 153, 21, colours[0]);
            circle(14, 14, 1.4, colours[0], true);
            circle(21, 14, 1.4, colours[1], true);
            circle(28, 14, 1.4, colours[2], true);
            if (kind === 'wireframe') {
                rect(14, 29, 29, 52, colours[2], 2);
                labelLines(20, 36, 15, 5);
                rect(51, 29, 94, 16, colours[1], 2);
                rect(51, 52, 43, 29, colours[0]);
                rect(102, 52, 43, 29, colours[3]);
                path('M56,76L69,60L78,69L87,58', colours[0]);
            }
            else {
                rect(15, 29, 56, 51, colours[1]);
                rect(80, 29, 64, 23, colours[2]);
                rect(80, 59, 64, 21, colours[3]);
                if (variant) {
                    path('M21,71L33,57L44,62L62,39', colours[1], 2);
                    for (let i = 0; i < 4; i++)
                        rect(87 + i * 12, 44 - i * 3, 7, 5 + i * 3, colours[2], 0, true);
                    path('M86,71H108L113,65L119,76L126,68H139', colours[3]);
                }
                else {
                    labelLines(24, 41, 36, 4);
                    labelLines(89, 39, 42, 1);
                    labelLines(89, 68, 42, 1);
                }
            }
            break;
        }
        case 'canvas': {
            rect(7, 9, 146, 78, colours[0], 2);
            if (variant === 3) {
                for (let x = 1; x < 3; x++)
                    line(7 + x * 146 / 3, 9, 7 + x * 146 / 3, 87, muted, 1);
                line(7, 48, 153, 48, muted, 1);
                for (let i = 0; i < 6; i++)
                    rect(15 + (i % 3) * 48, 18 + Math.floor(i / 3) * 39, 23, 12, colours[i % 4]);
            }
            else {
                for (const x of [36, 65, 95, 124])
                    line(x, 9, x, 66, muted, 1);
                line(7, 66, 153, 66, muted, 1);
                line(80, 66, 80, 87, muted, 1);
                line(36, 38, 65, 38, muted, 1);
                line(95, 38, 124, 38, muted, 1);
                for (const [x, y, c] of [[14, 18, 0], [42, 18, 1], [72, 31, 2], [102, 18, 1], [131, 18, 0], [41, 47, 3], [102, 47, 2], [25, 73, 1], [103, 73, 3]])
                    rect(x, y, 15, 8, colours[c], 1, variant === 2);
            }
            break;
        }
        case 'quadrant': {
            rect(19, 10, 122, 75, colours[0], 1);
            line(80, 10, 80, 85, muted, 1.5);
            line(19, 47, 141, 47, muted, 1.5);
            const words = variant === 1 ? ['P', 'E', 'S', 'T'] : variant === 2 ? ['★', '?', '●', '×'] : variant === 3 ? ['Market', 'Product', 'Develop', 'Diversify'] : ['SO', 'WO', 'ST', 'WT'];
            words.forEach((w, i) => { rect(24 + (i % 2) * 61, 15 + Math.floor(i / 2) * 37, 51, 27, colours[i], 2); text(49 + (i % 2) * 61, 33 + Math.floor(i / 2) * 37, w, w.length > 3 ? 8 : 14, colours[i]); });
            break;
        }
        case 'forces': {
            rect(58, 36, 44, 25, colours[0]);
            for (const [x, y] of [[56, 5], [6, 39], [113, 39], [56, 72]])
                rect(x, y, 42, 18, colours[1]);
            arrow(79, 23, 79, 36);
            arrow(48, 48, 58, 48);
            arrow(113, 48, 102, 48);
            arrow(79, 72, 79, 61);
            break;
        }
        case 'empathy': {
            path('M17,10H143V86H17ZM17,10L143,86M17,86L143,10', muted, 1.2);
            circle(80, 47, 15, colours[0]);
            circle(75, 43, 1, colours[0], true);
            circle(85, 43, 1, colours[0], true);
            path('M74,52Q80,58 86,52', colours[0]);
            text(80, 22, 'THINK', 8);
            text(80, 79, 'DO', 8);
            text(35, 49, 'SAY', 8);
            text(125, 49, 'FEEL', 8);
            break;
        }
        case 'scorecard': {
            for (let i = 0; i < 4; i++) {
                const y = 7 + i * 22;
                rect(9, y, 142, 16, colours[i]);
                text(24, y + 11, String(i + 1), 8, colours[i]);
                rect(42, y + 5, 68 - i * 12, 6, colours[i], 1, true);
                circle(137, y + 8, 3, colours[i], true);
            }
            break;
        }
        case 'chart':
        case 'histogram':
        case 'ranked': {
            axes();
            const heights = kind === 'histogram' ? [12, 25, 47, 61, 45, 29, 13] : [23, 47, 33, 59, 44];
            if (kind === 'ranked') {
                for (let i = 0; i < 5; i++)
                    rect(27, 17 + i * 12, 105 - i * 18, 7, colours[i % 4], 1, true);
            }
            else
                heights.forEach((h, i) => rect(27 + i * (kind === 'histogram' ? 16 : 23), 78 - h, kind === 'histogram' ? 15 : 14, h, colours[i % 2], 1, true));
            if (kind === 'chart')
                path('M27,63L48,51L71,59L94,30L126,21L140,29', colours[2], 2.6);
            break;
        }
        case 'radar': {
            const pts = (r) => Array.from({ length: 6 }, (_, i) => `${80 + Math.sin(i * Math.PI / 3) * r},${47 - Math.cos(i * Math.PI / 3) * r}`).join(' ');
            for (const r of [17, 34])
                add('polygon', { points: pts(r), stroke: muted, 'stroke-width': 1 });
            for (let i = 0; i < 6; i++)
                line(80, 47, 80 + Math.sin(i * Math.PI / 3) * 34, 47 - Math.cos(i * Math.PI / 3) * 34, muted, 1);
            path('M80,18L105,33L101,59L80,76L52,63L65,38Z', colours[0], 2, colours[0], .7);
            path('M80,30L97,37L109,64L80,63L65,55L57,34Z', colours[1], 2);
            break;
        }
        case 'funnel':
        case 'pyramid': {
            for (let i = 0; i < 4; i++) {
                const top = kind === 'pyramid' ? 16 + i * 29 : 136 - i * 29, bottom = kind === 'pyramid' ? top + 26 : top - 26, y = 8 + i * 21;
                path(`M${80 - top / 2},${y}H${80 + top / 2}L${80 + bottom / 2},${y + 17}H${80 - bottom / 2}Z`, colours[i], 1.5, colours[i], .65);
            }
            break;
        }
        case 'timeline': {
            line(12, 48, 148, 48, muted, 2);
            for (let i = 0; i < 5; i++) {
                const x = 22 + i * 29, y = i % 2 ? 67 : 19;
                circle(x, 48, 4, colours[i % 4], true);
                line(x, 48, x, y, colours[i % 4]);
                rect(x - 12, y - 8, 25, 16, colours[i % 4]);
            }
            break;
        }
        case 'fishbone': {
            arrow(9, 49, 135, 49);
            rect(135, 35, 21, 28, colours[0], 1);
            for (const x of [49, 86, 123]) {
                path(`M${x},49L${x - 20},12M${x},49L${x - 20},86`, colours[0]);
                for (const f of [.3, .65]) {
                    const dx = x - 20 * f;
                    line(dx, 49 - 37 * f, dx - 22, 49 - 37 * f, colours[1], 1.3);
                    line(dx, 49 + 37 * f, dx - 22, 49 + 37 * f, colours[2], 1.3);
                }
            }
            break;
        }
        case 'heatmap':
        case 'calendar': {
            const cols = kind === 'calendar' ? 12 : 7, rows = kind === 'calendar' ? 7 : 5, w = kind === 'calendar' ? 10 : 17, h = kind === 'calendar' ? 10 : 13;
            for (let y = 0; y < rows; y++)
                for (let x = 0; x < cols; x++) {
                    const level = variant === 2 ? Math.max(.1, 1 - Math.hypot(x - 3, y - 2) / 4) : .15 + ((x * 2 + y * 3) % 7) * .12;
                    const r = rect(18 + x * (w + 1), 12 + y * (h + 1), w, h, colours[variant === 1 ? 2 : 0], 1);
                    r.setAttribute('fill-opacity', String(level));
                    r.setAttribute('stroke', 'none');
                }
            break;
        }
        case 'quality': {
            axes();
            dash('M20,27H145', colours[2]);
            dash('M20,65H145', colours[2]);
            line(20, 46, 145, 46, colours[1], 1);
            path('M22,48L34,40L47,52L60,45L73,34L85,41L98,50L110,43L123,57L140,49', colours[0], 2);
            circle(123, 57, 3, colours[0], true);
            break;
        }
        case 'state': {
            if (variant) {
                rect(8, 8, 144, 80, colours[2], 8);
                text(30, 20, 'State', 8, colours[2]);
            }
            circle(20, 43, 4, ink, true);
            rect(41, 30, 36, 27, colours[0], 9);
            rect(108, 48, 36, 27, colours[1], 9);
            arrow(24, 43, 41, 43);
            path('M77,43H94V61H108', muted);
            path('M126,48V24H61V30', muted);
            circle(92, 79, 5, ink);
            circle(92, 79, 2, ink, true);
            arrow(108, 68, 97, 77);
            if (variant === 2)
                line(46, 41, 72, 41, colours[0], 1);
            break;
        }
        case 'gauge': {
            path('M30,73A50,50 0 0 1 130,73', muted, 12);
            path('M30,73A50,50 0 0 1 98,26', colours[1], 12);
            path('M80,73L108,35', ink, 3);
            circle(80, 73, 5, colours[0], true);
            text(80, 91, '68%', 12);
            break;
        }
        case 'candlestick': {
            axes();
            for (const [x, lo, hi, open, close] of [[34, 26, 69, 40, 57], [55, 19, 58, 26, 47], [76, 32, 72, 39, 62], [97, 13, 57, 21, 48], [118, 21, 68, 34, 52], [139, 10, 46, 17, 31]]) {
                const c = x % 3 ? colours[1] : colours[2];
                line(x, lo, x, hi, c);
                rect(x - 5, open, 10, close - open, c, 0, true);
            }
            break;
        }
        case 'treemap': {
            rect(10, 10, 140, 76, colours[0], 2);
            rect(14, 14, 60, 68, colours[0], 0, true);
            rect(78, 14, 68, 28, colours[1], 0, true);
            rect(78, 46, 30, 36, colours[2], 0, true);
            rect(112, 46, 34, 20, colours[3], 0, true);
            rect(112, 70, 34, 12, colours[1], 0, true);
            break;
        }
        case 'sankey': {
            path('M20,25C65,25 65,28 138,28', colours[0], 16, 'none', .6);
            path('M20,32C71,32 70,73 138,73', colours[1], 11, 'none', .6);
            path('M20,72C75,72 67,37 138,37', colours[2], 12, 'none', .6);
            rect(12, 15, 9, 26, colours[0], 1, true);
            rect(12, 62, 9, 21, colours[2], 1, true);
            rect(138, 15, 10, 32, colours[0], 1, true);
            rect(138, 64, 10, 18, colours[1], 1, true);
            break;
        }
        case 'c4': {
            actor(20, 35);
            rect(56, 20, 57, 53, colours[0], 3);
            arrow(28, 48, 56, 48);
            rect(130, 32, 24, 31, colours[2]);
            arrow(113, 48, 130, 48);
            if (variant) {
                const boundary = rect(48, 10, 73, 75, muted, 0);
                boundary.setAttribute('stroke-dasharray', '4 3');
                rect(62, 28, 44, 17, colours[1]);
                rect(62, 52, variant === 2 ? 18 : 44, 15, colours[3]);
                if (variant === 2)
                    rect(87, 52, 19, 15, colours[2]);
            }
            else
                text(84, 50, 'System', 9);
            break;
        }
        case 'tree': {
            path('M80,28V45H27V57M80,45H133V57M80,45V57', muted);
            if (variant === 3) {
                circle(67, 17, 9, colours[0]);
                rect(83, 8, 18, 18, colours[1], 0);
                line(76, 17, 83, 17);
                for (const x of [27, 80, 133])
                    circle(x, 69, 11, colours[2]);
            }
            else {
                box(61, 6, 38, 23, colours[0], 1);
                for (const [i, x] of [8, 61, 114].entries()) {
                    box(x, 57, 38, 26, colours[(i + 1) % 4], 1);
                    if (variant === 1) {
                        circle(x + 19, 64, 3, colours[(i + 1) % 4], true);
                    }
                    if (variant === 2)
                        text(x + 19, 66, '1.' + (i + 1), 7);
                }
            }
            break;
        }
        case 'mindmap': {
            rect(58, 36, 44, 24, colours[0], 7);
            for (const [x, y, c] of [[9, 14, 1], [8, 69, 2], [119, 12, 3], [118, 69, 1]]) {
                const left = x < 50, startX = left ? 58 : 102, startY = y < 48 ? 43 : 53;
                const endX = left ? x + 33 : x, endY = y + 9;
                path(`M${startX},${startY}C${left ? 47 : 113},${startY} ${left ? 52 : 108},${endY} ${endX},${endY}`, colours[c], 2);
                rect(x, y, 33, 18, colours[c], 5);
            }
            break;
        }
        case 'concept': {
            ellipse(79, 48, 25, 14);
            ellipse(25, 17, 20, 10, colours[1]);
            ellipse(133, 17, 20, 10, colours[2]);
            ellipse(28, 80, 22, 10, colours[2]);
            ellipse(133, 78, 22, 10, colours[1]);
            line(43, 25, 63, 38);
            line(98, 38, 117, 25);
            line(60, 57, 43, 71);
            line(99, 57, 115, 70);
            dash('M48,80H110');
            text(80, 25, 'relates', 7, muted);
            break;
        }
        case 'epc': {
            path('M20,8H45L52,20L45,32H20L13,20Z', colours[2], 1.8, colours[2], .6);
            rect(68, 8, 42, 24, colours[1]);
            arrow(52, 20, 68, 20);
            circle(130, 20, 8, colours[3]);
            text(130, 23, '×', 12);
            arrow(110, 20, 122, 20);
            path('M130,28V65H104', muted);
            rect(64, 53, 40, 24, colours[1]);
            path('M17,53H42L49,65L42,77H17L10,65Z', colours[2], 1.8, colours[2], .6);
            arrow(64, 65, 49, 65);
            if (variant) {
                ellipse(87, 90, 22, 5, colours[0]);
                dash('M87,77V85');
            }
            break;
        }
        case 'journey': {
            for (let i = 0; i < 4; i++) {
                rect(9 + i * 38, 8, 33, 18, colours[i]);
                for (let j = 0; j < 2; j++)
                    rect(12 + i * 38, 34 + j * 15, 27, 10, colours[i], 2);
            }
            path('M12,82Q35,58 57,77T98,69T149,76', colours[0], 2.5);
            break;
        }
        case 'storymap': {
            for (let i = 0; i < 4; i++) {
                rect(10 + i * 38, 8, 31, 18, colours[0]);
                for (let j = 0; j < 3 - (i % 2); j++)
                    rect(10 + i * 38, 34 + j * 17, 31, 12, colours[(j + 1) % 4]);
            }
            dash('M5,49H155');
            break;
        }
        case 'venn': {
            for (const [x, y, c] of [[63, 36, 0], [97, 36, 1], [80, 64, 2]]) {
                const p = circle(x, y, 27, colours[c]);
                p.setAttribute('fill-opacity', '.23');
            }
            break;
        }
        case 'sequence': {
            for (let i = 0; i < 3; i++) {
                const x = 27 + i * 54;
                rect(x - 16, 7, 32, 17, colours[i]);
                dash(`M${x},24V88`);
                rect(x - 3, 36 + i * 10, 6, 34 - i * 4, colours[i], 0);
            }
            arrow(29, 37, 78, 37, colours[0]);
            arrow(82, 51, 133, 51, colours[1]);
            dash('M132,66H80');
            path('M85,62L80,66L85,70', muted);
            if (variant === 1) {
                const f = rect(15, 30, 132, 48, muted, 0);
                f.setAttribute('stroke-dasharray', '3 3');
                text(24, 39, 'alt', 7);
            }
            if (variant === 2)
                path('M27,80H80L91,86H135', colours[2]);
            break;
        }
        case 'communication': {
            box(12, 12, 42, 29, colours[0], 1);
            box(105, 12, 42, 29, colours[1], 1);
            box(58, 61, 44, 29, colours[2], 1);
            arrow(54, 26, 105, 26);
            arrow(127, 41, 100, 65);
            arrow(60, 70, 34, 41);
            text(79, 19, '1', 9);
            text(126, 57, '2', 9);
            text(39, 64, '3', 9);
            if (variant)
                dash('M54,32H104');
            break;
        }
        case 'timing': {
            axes();
            path('M21,26H50V43H77V26H108V43H145', colours[0], 2);
            path('M21,63H36V52H91V68H124V52H145', colours[1], 2);
            for (let i = 0; i < 5; i++)
                dash(`M${35 + i * 24},16V79`);
            if (variant) {
                path('M24,88H77M24,85V91M77,85V91', colours[2]);
                text(50, 93, 'Δt', 7);
            }
            break;
        }
        case 'packages': {
            for (const [x, y, c] of [[10, 17, 0], [100, 54, 1]]) {
                rect(x, y, 46, 32, colours[c], 1);
                rect(x, y - 7, 22, 8, colours[c], 1);
            }
            dash('M56,33H79V70H100');
            if (variant)
                text(31, 37, '«profile»', 7);
            else
                labelLines(19, 32, 28, 2);
            break;
        }
        case 'case': {
            const p = rect(8, 10, 145, 76, colours[0], 1);
            p.setAttribute('stroke-dasharray', '5 3');
            path('M8,10L20,2H153V86', colours[0]);
            rect(21, 27, 49, 24, colours[1]);
            rect(88, 27, 49, 24, colours[2]);
            diamond(79, 70, 14, 6, colours[3]);
            dash('M47,51V70H65M114,51V70H93');
            if (variant) {
                text(45, 43, '+', 13);
                circle(140, 73, 6, colours[1]);
            }
            break;
        }
        case 'composite': {
            rect(10, 10, 140, 76, colours[0], 2);
            box(25, 29, 43, 34, colours[1], 2);
            box(92, 29, 43, 34, colours[2], 2);
            rect(8, 43, 5, 10, colours[0], 0);
            rect(147, 43, 5, 10, colours[0], 0);
            path('M13,48H25M68,48H92M135,48H147', muted);
            if (variant) {
                for (const x of [64, 91])
                    rect(x, 44, 6, 8, colours[3], 0);
            }
            if (variant === 2)
                text(80, 24, 'flow', 8);
            break;
        }
        case 'parametric': {
            rect(7, 10, 146, 76, colours[0], 2);
            rect(49, 30, 64, 36, colours[2], 4);
            text(81, 52, 'F = m × a', 11, colours[2]);
            for (const [x, y] of [[23, 28], [23, 65], [137, 47]]) {
                circle(x, y, 6, colours[1]);
                line(x < 80 ? x + 6 : x - 6, y, x < 80 ? 49 : 113, y < 40 ? 39 : 57, colours[1]);
            }
            if (variant)
                text(81, 22, '«constraint»', 7);
            break;
        }
        case 'architecture': {
            for (let i = 0; i < 3; i++) {
                rect(8, 7 + i * 29, 144, 24, colours[i], 1);
                for (let j = 0; j < 3; j++)
                    rect(17 + j * 46, 12 + i * 29, 34, 14, colours[i], 2);
            }
            arrow(35, 31, 35, 36);
            arrow(81, 60, 81, 65);
            break;
        }
        case 'pert': {
            nodes([[15, 48], [58, 20], [57, 76], [108, 20], [108, 76], [146, 48]], [[0, 1], [0, 2], [1, 3], [2, 4], [3, 5], [4, 5], [1, 4]], 7);
            path('M15,48L58,20H108L146,48', colours[2], 3);
            break;
        }
        case 'fault': {
            rect(60, 5, 40, 18, colours[2]);
            line(80, 23, 80, 36);
            path('M67,49V40A13,11 0 0 1 93,40V49Z', colours[0]);
            path('M67,49H93M80,49V60H31V73M80,60H129V73', muted);
            circle(31, 81, 8, colours[1]);
            circle(80, 81, 8, colours[3]);
            circle(129, 81, 8, colours[1]);
            line(80, 60, 80, 73);
            break;
        }
        case 'eventtree': {
            path('M10,48H48V21H91V9H144M91,21V35H144M48,48V73H91V59H144M91,73V88H144', colours[0]);
            for (const [x, y] of [[48, 21], [48, 73], [91, 9], [91, 35], [91, 59], [91, 88]])
                circle(x, y, 2.5, colours[1], true);
            text(25, 42, 'Event', 8);
            break;
        }
        case 'network': {
            circle(80, 45, 13, colours[0]);
            for (const [x, y] of [[18, 19], [142, 19], [19, 77], [141, 77]]) {
                line(80, 45, x, y, muted);
                rect(x - 11, y - 8, 22, 16, colours[1], 2);
                line(x - 5, y + 11, x + 5, y + 11, colours[1]);
            }
            circle(80, 45, 4, colours[0], true);
            break;
        }
        case 'rack': {
            for (let k = 0; k < 3; k++) {
                const x = 14 + k * 48;
                rect(x, 8, 36, 80, colours[k], 2);
                for (let y = 15; y < 78; y += 13) {
                    rect(x + 5, y, 26, 9, colours[k], 1);
                    circle(x + 25, y + 4.5, 1, colours[1], true);
                    labelLines(x + 9, y + 4.5, 9, 1);
                }
            }
            if (variant)
                path('M32,89V94H128V89', muted);
            break;
        }
        case 'density': {
            axes();
            path('M21,78C37,78 40,66 51,46C67,10 85,12 99,42C115,75 128,78 145,78', colours[0], 2.5, colours[0], .8);
            path('M21,78C59,78 67,62 88,41C110,18 116,69 145,78', colours[1], 2.2);
            break;
        }
        case 'qq': {
            axes();
            dash('M25,73L139,17', colours[2]);
            for (const [x, y] of [[29, 70], [43, 65], [55, 61], [66, 51], [79, 46], [90, 39], [103, 34], [118, 28], [135, 19]])
                circle(x, y, 3, colours[0], true);
            break;
        }
        case 'quantiledot': {
            axes();
            for (let i = 0; i < 11; i++) {
                const n = [1, 1, 2, 3, 5, 5, 4, 3, 2, 1, 1][i];
                for (let j = 0; j < n; j++)
                    circle(29 + i * 10, 73 - j * 11, 3.5, colours[i < 6 ? 0 : 1], true);
            }
            break;
        }
        case 'dotplot': {
            axes();
            for (let i = 0; i < 5; i++) {
                const y = 20 + i * 12;
                line(28, y, 137, y, muted, 1);
                circle([61, 95, 79, 126, 47][i], y, 4, colours[i % 4], true);
            }
            break;
        }
        case 'boxplot': {
            axes();
            for (const [i, row] of [[32, 55, 93, 124], [43, 72, 108, 141], [27, 40, 83, 114]].entries()) {
                const y = 25 + i * 22;
                line(row[0], y, row[3], y);
                path(`M${row[0]},${y - 5}V${y + 5}M${row[3]},${y - 5}V${y + 5}`, muted);
                rect(row[1], y - 7, row[2] - row[1], 14, colours[i], 0);
                line((row[1] + row[2]) / 2, y - 7, (row[1] + row[2]) / 2, y + 7, colours[i]);
            }
            break;
        }
        case 'violin': {
            axes();
            for (let i = 0; i < 3; i++) {
                const x = 47 + i * 38, w = [15, 10, 18][i];
                path(`M${x},14C${x - w},26 ${x - w},38 ${x - 4},49C${x - w},67 ${x - 10},74 ${x},78C${x + 10},74 ${x + w},67 ${x + 4},49C${x + w},38 ${x + w},26 ${x},14Z`, colours[i], 1.5, colours[i], .65);
                line(x, 27, x, 67, ink, 1);
                circle(x, 48, 2, ink, true);
            }
            break;
        }
        case 'beeswarm': {
            axes();
            for (let i = 0; i < 3; i++) {
                const x = 48 + i * 39;
                for (const [dx, y] of [[0, 22], [-4, 32], [5, 34], [-9, 43], [0, 43], [9, 45], [-5, 53], [4, 56], [0, 65], [3, 73]])
                    circle(x + dx, y + (i === 1 ? -7 : i === 2 ? 3 : 0), 2.7, colours[i], true);
            }
            break;
        }
        case 'tidytree': {
            path('M18,48H57V20H103V10H145M103,20V34H145M57,48V73H103V61H145M103,73V87H145', muted);
            for (const [x, y] of [[18, 48], [57, 20], [57, 73], [103, 10], [103, 34], [103, 61], [103, 87], [145, 10], [145, 34], [145, 61], [145, 87]])
                circle(x, y, 3, colours[x < 100 ? 0 : 1], true);
            break;
        }
        case 'radialtree': {
            circle(80, 48, 4, colours[0], true);
            for (let i = 0; i < 6; i++) {
                const a = i * Math.PI / 3, x = 80 + Math.cos(a) * 21, y = 48 + Math.sin(a) * 21;
                line(80, 48, x, y);
                circle(x, y, 3, colours[1], true);
                for (const offset of [-.19, .19]) {
                    const xx = 80 + Math.cos(a + offset) * 39, yy = 48 + Math.sin(a + offset) * 39;
                    line(x, y, xx, yy);
                    circle(xx, yy, 2.5, colours[2], true);
                }
            }
            break;
        }
        case 'circlepack': {
            circle(80, 48, 42, colours[0]);
            circle(62, 47, 23, colours[1]);
            circle(103, 47, 17, colours[2]);
            circle(86, 76, 10, colours[3]);
            for (const [x, y, r] of [[55, 39, 10], [67, 57, 9], [105, 42, 9], [98, 57, 5]])
                circle(x, y, r, colours[1], true);
            break;
        }
        case 'sunburst': {
            const arc = (r, start, end, c, w) => { const a = start * Math.PI / 180, b = end * Math.PI / 180; path(`M${80 + r * Math.cos(a)},${48 + r * Math.sin(a)}A${r},${r} 0 ${end - start > 180 ? 1 : 0} 1 ${80 + r * Math.cos(b)},${48 + r * Math.sin(b)}`, c, w); };
            circle(80, 48, 8, colours[0], true);
            for (let i = 0; i < 4; i++) {
                arc(20, i * 90 + 3, i * 90 + 87, colours[i], 12);
                for (let j = 0; j < 2; j++)
                    arc(36, i * 90 + j * 45 + 3, i * 90 + j * 45 + 42, colours[(i + j) % 4], 12);
            }
            break;
        }
        case 'bubbles': {
            for (const [x, y, r, c] of [[62, 52, 27, 0], [108, 39, 20, 1], [113, 73, 12, 2], [42, 15, 10, 3], [89, 15, 12, 2], [25, 54, 8, 1], [75, 86, 7, 3]])
                circle(x, y, r, colours[c], true);
            break;
        }
        case 'parallel': {
            for (const x of [25, 61, 97, 133]) {
                line(x, 12, x, 84, muted, 1.2);
                for (const y of [24, 48, 72])
                    line(x - 3, y, x + 3, y, muted, 1);
            }
            for (const [i, ys] of [[23, 58, 33, 69], [70, 27, 61, 30], [45, 75, 20, 48]].entries())
                path('M' + [25, 61, 97, 133].map((x, j) => `${x},${ys[j]}`).join('L'), colours[i], 2);
            break;
        }
        case 'wordcloud': {
            text(77, 45, 'IDEAS', 24, colours[0]);
            text(47, 65, 'design', 15, colours[1]);
            text(111, 64, 'DATA', 13, colours[2]);
            text(91, 22, 'people', 11, colours[3]);
            text(87, 81, 'connections', 10, muted);
            text(22, 29, 'maps', 9, colours[2]);
            break;
        }
        case 'arc': {
            line(12, 59, 149, 59, muted, 1);
            for (const [a, b, c] of [[18, 118, 0], [44, 145, 1], [18, 71, 2], [70, 118, 3]])
                path(`M${a},59A${(b - a) / 2},${(b - a) / 2 * .8} 0 0 1 ${b},59`, colours[c], 2.3);
            path('M44,59Q80,104 145,59', colours[2], 1.8);
            for (const x of [18, 44, 70, 94, 118, 145])
                circle(x, 59, 3.6, colours[0], true);
            break;
        }
        case 'force': {
            nodes([[23, 25], [68, 16], [110, 26], [143, 51], [109, 78], [65, 72], [20, 68], [79, 45]], [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 0], [0, 7], [2, 7], [4, 7], [5, 7], [1, 7]], 6);
            break;
        }
        case 'bundle': {
            for (let i = 0; i < 14; i++) {
                const a = i * Math.PI * 2 / 14, x = 80 + Math.cos(a) * 40, y = 48 + Math.sin(a) * 40;
                circle(x, y, 2.8, colours[i % 4], true);
                const b = (i + 5) % 14 * Math.PI * 2 / 14;
                path(`M${x},${y}Q80,48 ${80 + Math.cos(b) * 40},${48 + Math.sin(b) * 40}`, colours[i % 4], 1.2, 'none', .65);
            }
            break;
        }
        case 'map': {
            const regions = ['M15,27L35,14L55,19L63,34L47,45L27,43Z', 'M47,45L64,51L61,68L51,85L42,64Z', 'M78,24L94,16L109,22L106,37L89,42L77,34Z', 'M89,42L105,37L116,53L103,74L88,62Z', 'M109,22L137,17L151,32L138,46L116,43L106,37Z', 'M123,64L143,63L150,75L136,83L122,76Z'];
            regions.forEach((d, i) => path(d, muted, 1.2, variant === 1 ? colours[i % 4] : 'none', variant === 1 ? .8 : 1));
            if (variant === 2)
                for (const [x, y, r] of [[34, 30, 6], [55, 59, 4], [92, 29, 5], [102, 54, 7], [132, 30, 4], [137, 73, 5]])
                    circle(x, y, r, colours[0], true);
            break;
        }
        case 'deployment': {
            for (const [x, y, c] of [[8, 15, 0], [99, 48, 1]]) {
                path(`M${x},${y + 8}L${x + 9},${y}H${x + 51}V${y + 32}L${x + 42},${y + 40}H${x}ZM${x},${y + 8}H${x + 42}L${x + 51},${y}M${x + 42},${y + 8}V${y + 40}`, colours[c]);
                rect(x + 9, y + 18, 25, 13, colours[c], 1);
            }
            path('M59,39H79V72H99', muted);
            if (variant)
                rect(15, 40, 24, 9, colours[2]);
            break;
        }
        case 'bpmn': {
            if (variant === 3) {
                for (const [x, y] of [[39, 24], [121, 24], [80, 73]])
                    path(`M${x - 15},${y}L${x - 7},${y - 13}H${x + 7}L${x + 15},${y}L${x + 7},${y + 13}H${x - 7}Z`, colours[0], 1.6, colours[0], .6);
                line(54, 24, 106, 24);
                line(47, 37, 72, 60);
                line(113, 37, 88, 60);
                break;
            }
            if (variant === 0) {
                rect(5, 6, 150, 39, muted, 0);
                rect(5, 53, 150, 37, muted, 0);
                line(16, 6, 16, 45);
                line(16, 53, 16, 90);
                dash('M80,45V53');
            }
            circle(27, variant === 0 ? 26 : 47, 7, colours[1]);
            rect(50, variant === 0 ? 15 : 34, 45, 26, colours[0], 4);
            arrow(34, variant === 0 ? 26 : 47, 50, variant === 0 ? 26 : 47);
            diamond(118, variant === 0 ? 27 : 47, 11, 11);
            arrow(95, variant === 0 ? 27 : 47, 107, variant === 0 ? 27 : 47);
            if (variant === 0) {
                rect(64, 63, 43, 18, colours[2], 3);
                circle(136, 72, 7, colours[1]);
                arrow(107, 72, 129, 72);
            }
            else {
                circle(145, 47, 7, colours[1]);
                arrow(129, 47, 138, 47);
            }
            if (variant === 2) {
                line(50, 40, 95, 40, colours[0]);
                line(50, 54, 95, 54, colours[0]);
            }
            break;
        }
        case 'decision': {
            rect(56, 11, 48, 27, colours[0], 0);
            rect(14, 67, 41, 18, colours[1], 9);
            rect(105, 67, 41, 18, colours[1], 9);
            arrow(35, 67, 65, 38);
            arrow(125, 67, 96, 38);
            path('M66,51L75,45H102V59H66Z', colours[2]);
            dash('M84,45V38');
            break;
        }
        case 'services': {
            rect(57, 31, 47, 34, colours[0], 3);
            actor(17, 29);
            rect(127, 33, 24, 28, colours[1], 3);
            line(25, 43, 57, 43);
            line(104, 48, 127, 48);
            circle(48, 43, 4, colours[2]);
            path('M116,43A5,5 0 0 0 116,53', colours[2]);
            rect(59, 7, 44, 14, colours[3], 1);
            dash('M80,21V31');
            if (variant)
                rect(59, 76, 44, 14, colours[2], 1);
            break;
        }
        case 'uaf': {
            const col = colours[variant % 4];
            rect(13, 9, 134, 18, col);
            for (const [x, c] of [[19, 0], [99, 1]])
                box(x, 47, 42, 30, colours[c], 1);
            path('M80,27V38H40V47M80,38H120V47', muted);
            if (variant === 4) {
                path('M70,52L80,47L90,52V62Q90,72 80,78Q70,72 70,62Z', colours[2]);
            }
            else if (variant === 5) {
                path('M25,85H137', muted);
                for (const x of [40, 80, 120])
                    circle(x, 85, 3, colours[2], true);
            }
            else if (variant === 6) {
                text(81, 22, 'Standards', 8, col);
            }
            else {
                for (let i = 0; i < Math.min(variant + 1, 4); i++)
                    rect(29 + i * 26, 83, 19, 7, colours[i], 1, true);
            }
            break;
        }
        case 'idef': {
            rect(53, 29, 55, 39, colours[0], 0);
            text(81, 52, 'Function', 10);
            arrow(7, 48, 53, 48);
            arrow(108, 48, 154, 48);
            arrow(81, 5, 81, 29);
            arrow(81, 91, 81, 68);
            text(27, 41, 'Input', 7);
            text(133, 41, 'Output', 7);
            text(105, 15, 'Control', 7);
            break;
        }
        case 'petri': {
            circle(17, 48, 10, colours[0]);
            circle(76, 18, 10, colours[1]);
            circle(76, 78, 10, colours[1]);
            circle(144, 48, 10, colours[2]);
            rect(46, 35, 7, 26, ink, 0, true);
            rect(106, 35, 7, 26, ink, 0, true);
            arrow(27, 48, 46, 48);
            path('M53,44L68,26M53,52L68,70M84,26L106,44M84,70L106,52', muted);
            arrow(113, 48, 134, 48);
            circle(17, 48, 2, ink, true);
            circle(76, 18, 2, ink, true);
            break;
        }
        case 'orm': {
            ellipse(27, 25, 23, 13, colours[0]);
            ellipse(133, 25, 23, 13, colours[1]);
            rect(55, 49, 50, 20, colours[2], 0);
            line(80, 49, 80, 69, colours[2]);
            line(27, 38, 65, 49);
            line(133, 38, 95, 49);
            line(56, 44, 104, 44, ink, 2);
            ellipse(80, 86, 22, 7, colours[3]);
            line(80, 69, 80, 79);
            break;
        }
        case 'vsm': {
            rect(9, 9, 34, 23, colours[0], 0);
            rect(117, 9, 34, 23, colours[0], 0);
            path('M10,9V3L18,8L26,3L34,8', colours[0]);
            rect(57, 6, 46, 20, colours[2], 0);
            dash('M43,16H57M103,16H117');
            rect(12, 49, 38, 25, colours[1], 0);
            rect(110, 49, 38, 25, colours[1], 0);
            path('M72,49L85,73H59Z', colours[3]);
            text(72, 68, 'I', 10, colours[3]);
            arrow(50, 61, 59, 61);
            arrow(85, 61, 110, 61);
            path('M11,88H50V80H109V88H149', muted, 1.4);
            break;
        }
        case 'fbd': {
            rect(45, 17, 34, 60, colours[0], 1);
            rect(101, 35, 34, 42, colours[1], 1);
            text(62, 39, 'AND', 9);
            text(118, 57, 'OR', 9);
            path('M7,30H45M7,59H45M79,46H101M8,86H90V66H101M135,56H154', muted);
            for (const [x, y] of [[45, 30], [45, 59], [79, 46], [101, 46], [101, 66], [135, 56]])
                rect(x - 2, y - 2, 4, 4, colours[2], 0, true);
            break;
        }
        case 'ladder': {
            path('M12,8V88M148,8V88', ink, 2.5);
            for (const y of [27, 66]) {
                path(`M12,${y}H40M48,${y}H104M120,${y}H148M40,${y - 9}V${y + 9}M48,${y - 9}V${y + 9}M110,${y - 9}Q98,${y} 110,${y + 9}M114,${y - 9}Q126,${y} 114,${y + 9}`, colours[y === 27 ? 0 : 1]);
            }
            path('M37,77L51,55M72,66V47H128V66', colours[1]);
            break;
        }
        case 'circuit': {
            path('M15,48H38L43,40L50,56L57,40L64,56L71,40L76,48H109M109,23V74M116,23V74M116,48H145V85H15V57M15,39V9H145V48', colours[0], 2);
            line(7, 39, 23, 39, colours[1], 2);
            line(11, 57, 19, 57, colours[1], 2);
            circle(145, 48, 3, colours[1], true);
            circle(15, 85, 3, colours[1], true);
            break;
        }
        default: text(80, 57, '?', 32, muted);
    }
    const title = document.createElementNS(NS, 'title');
    title.textContent = name;
    svg.prepend(title);
    return svg;
}
const methodPreview = (document, id) => preview(document, methods[id]);
exports.methodPreview = methodPreview;
const profilePreview = (document, id) => preview(document, profiles[id]);
exports.profilePreview = profilePreview;

},
"runtime/src/commands.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createCommandHistoryGroup = createCommandHistoryGroup;
exports.currentCommandHistoryGroup = currentCommandHistoryGroup;
exports.createCommandService = createCommandService;
exports.createNativeCommandPack = createNativeCommandPack;
exports.createCompleteCommandPack = createCompleteCommandPack;
exports.createModularCommandPack = createModularCommandPack;
const index_js_1 = require("language/src/index.js");
const index_js_2 = require("model/src/index.js");
const index_js_3 = require("defaults/src/index.js");
const layout_edit_js_1 = require("runtime/src/layout-edit.js");
const index_js_4 = require("execution/src/index.js");
const runtime_js_1 = require("runtime/src/runtime.js");
const registry_js_1 = require("runtime/src/registry.js");
const profile_loading_js_1 = require("runtime/src/profile-loading.js");
const core_js_1 = require("profiles/src/core.js");
const guards_js_1 = require("runtime/src/guards.js");
const nativeProfiles = ['ddn@1', 'mindmap.basic@1', 'concept.map@1', 'table.records@1'];
const nativeIds = core_js_1.standardCommandIds;
const stringSchema = { type: 'string' }, numberSchema = { type: 'number' }, arraySchema = { type: 'array' }, referenceSchema = { type: 'object', required: ['file', 'id'], additionalProperties: false, properties: { file: stringSchema, id: stringSchema } };
const argumentDefinitions = {
    'ddn.add-dataset': { required: ['name', 'columns', 'rows'], properties: { name: stringSchema, columns: arraySchema, rows: arraySchema } },
    'ddn.set-records': { required: ['columns', 'rows'], properties: { columns: arraySchema, rows: arraySchema } },
    'ddn.add-view': { required: ['name', 'profile'], properties: { name: stringSchema, profile: { enum: core_js_1.completeProfileIds }, subtype: arraySchema } },
    'ddn.create-element': { required: ['role'], properties: { view: referenceSchema, role: stringSchema, name: stringSchema, position: { type: 'object', required: ['x', 'y'], additionalProperties: false, properties: { x: numberSchema, y: numberSchema } } } },
    'ddn.set-position': { required: ['x', 'y'], properties: { x: numberSchema, y: numberSchema } },
    'ddn.set-size': { required: ['width', 'height'], properties: { width: numberSchema, height: numberSchema } },
    'ddn.set-cell': { required: ['row', 'column', 'value'], properties: { row: { type: 'integer', minimum: 0 }, column: { type: ['integer', 'string'] }, value: {} } },
    'ddn.add-row': { required: [], properties: {} },
    'ddn.remove-row': { required: ['row'], properties: { row: { type: 'integer', minimum: 0 } } },
    'ddn.set-columns': { required: ['columns'], properties: { columns: arraySchema } },
    'ddn.add-note': { required: ['text'], properties: { text: stringSchema } },
    'ddn.set-note': { required: ['text'], properties: { text: stringSchema } },
    'ddn.set-draft': { required: ['text'], properties: { text: stringSchema, format: { enum: ['text', 'fields', 'table'] } } },
    'ddn.set-table': { required: ['columns', 'rows'], properties: { columns: arraySchema, rows: arraySchema } },
};
const argumentSchema = (id) => ({ type: 'object', additionalProperties: false, ...argumentDefinitions[id] });
function checkedArguments(command, value) {
    function check(schema, input, path) {
        const types = Array.isArray(schema.type) ? schema.type : typeof schema.type === 'string' ? [schema.type] : [];
        if (types.length && !types.some(type => type === 'array' ? Array.isArray(input) : type === 'object' ? (0, index_js_2.isRecord)(input) : type === 'integer' ? typeof input === 'number' && Number.isSafeInteger(input) : typeof input === type))
            throw Error('Invalid command argument ' + path);
        if (Array.isArray(schema.enum) && !schema.enum.some(item => (0, index_js_4.canonical)(item) === (0, index_js_4.canonical)(input)))
            throw Error('Invalid command choice ' + path);
        if (typeof schema.minimum === 'number' && typeof input === 'number' && input < schema.minimum)
            throw Error('Argument is below its minimum: ' + path);
        if ((0, index_js_2.isRecord)(input)) {
            const properties = (0, index_js_2.asRecord)(schema.properties);
            for (const name of (0, index_js_2.asArray)(schema.required))
                if (typeof name === 'string' && !(name in input))
                    throw Error('Missing command argument ' + path + '.' + name);
            for (const [name, item] of Object.entries(input)) {
                if (!(name in properties) && schema.additionalProperties === false)
                    throw Error('Unknown command argument ' + path + '.' + name);
                if ((0, index_js_2.isRecord)(properties[name]))
                    check(properties[name], item, path + '.' + name);
            }
        }
    }
    check((0, index_js_2.asRecord)(argumentSchema(command)), value, command);
    return (0, index_js_2.asRecord)(value);
}
const ownerOf = (entry) => ({ view: entry.record.kind === 'document' ? 'document' : 'view_definition', placement: 'view_placement', data: 'data', source: 'source', asset: 'asset', template: 'template', publication: 'publication', note: 'note', workarea: 'workarea', definition: 'definition', appearance: 'appearance' })[entry.kind];
const key = (ref) => ref.file + '\0' + ref.id;
const status = (record) => (0, index_js_2.asString)((0, index_js_2.asRecord)(record?.design).state, 'draft');
const ref = (value) => {
    if (!(0, index_js_2.isRecord)(value) || typeof value.file !== 'string' || typeof value.id !== 'string')
        throw Error('Expected a qualified reference');
    return { file: value.file, id: value.id };
};
const issue = (code, message, target) => ({ code, severity: 'error', message, ...(target ? { target } : {}) });
const failure = (code, diagnostics) => ({ ok: false, failure: { code, diagnostics } });
function sameSources(a, b) {
    return !!a && a.entry === b.entry && a.files.length === b.files.length && a.files.every(file => {
        const other = b.files.find(value => value.id === file.id);
        return !!other && file.text === other.text && file.revision === other.revision && file.writable === other.writable && file.encoding === other.encoding
            && (file.originalBytes === undefined ? other.originalBytes === undefined : !!other.originalBytes && file.originalBytes.length === other.originalBytes.length && file.originalBytes.every((byte, index) => byte === other.originalBytes[index]));
    });
}
function sourceQualifier(from, to) {
    if (from === to)
        return '';
    if (/^[a-z][a-z0-9+.-]*:/i.test(to))
        return (0, index_js_1.quoteText)(to) + '::';
    if (/^[a-z][a-z0-9+.-]*:/i.test(from) || from.startsWith('/') !== to.startsWith('/'))
        throw Error('The selected source namespaces do not have a representable relative reference');
    if (to.startsWith('/'))
        return (0, index_js_1.quoteText)(to) + '::';
    const parent = from.split('/').slice(0, -1), destination = to.split('/');
    while (parent.length && destination.length && parent[0] === destination[0]) {
        parent.shift();
        destination.shift();
    }
    return (0, index_js_1.quoteText)([...parent.map(() => '..'), ...destination].join('/')) + '::';
}
function difference(before, after) {
    return before.files.flatMap(file => {
        const next = after.files.find(f => f.id === file.id);
        if (!next)
            throw Error('Source files cannot disappear in an edit');
        if (next.text === file.text)
            return [];
        let start = 0;
        while (start < file.text.length && start < next.text.length && file.text[start] === next.text[start])
            start++;
        let end = file.text.length, nextEnd = next.text.length;
        while (end > start && nextEnd > start && file.text[end - 1] === next.text[nextEnd - 1]) {
            end--;
            nextEnd--;
        }
        return [{ file: file.id, base: file.revision, start, end, text: next.text.slice(start, nextEnd) }];
    });
}
function changedRecords(before, after) {
    const old = new Map((0, index_js_2.listRecords)(before.normalized).map(e => [key(e.ref), e])), current = new Map((0, index_js_2.listRecords)(after.normalized).map(e => [key(e.ref), e]));
    return [...new Set([...old.keys(), ...current.keys()])].sort().flatMap(k => (0, index_js_4.canonical)(old.get(k)?.record) === (0, index_js_4.canonical)(current.get(k)?.record) ? [] : [(current.get(k) ?? old.get(k)).ref]);
}
function liveRevision(runtime) {
    const state = (0, runtime_js_1.runtimeState)(runtime), snapshot = state.current;
    if (!snapshot)
        throw Error('No model is open');
    return { ...snapshot.revision, sources: Object.fromEntries(state.source?.files.map(f => [f.id, f.revision]) ?? Object.entries(snapshot.revision.sources)) };
}
const historyFactories = new WeakMap();
const activeHistoryGroups = new WeakMap();
function createCommandHistoryGroup(service) {
    const create = historyFactories.get(service);
    if (!create)
        throw Error('History grouping is unavailable for this command service.');
    return create();
}
function currentCommandHistoryGroup(service) { return activeHistoryGroups.get(service); }
function createCommandService(runtime, authority, limits = { maxCommands: 200, maxBytes: 32 * 1024 * 1024 }) {
    if (!Number.isSafeInteger(limits.maxCommands) || limits.maxCommands < 0 || !Number.isSafeInteger(limits.maxBytes) || limits.maxBytes < 0)
        throw Error('History limits must be nonnegative safe integers');
    limits = { ...limits };
    const pending = new Map(), undo = [], redo = [];
    let serial = 0, historyBytes = 0, expectedHistory = '';
    let historySources;
    let committing = false, travelling = false;
    function freshSource(source, before) { return { entry: source.entry, files: source.files.map(file => before.files.find(old => old.id === file.id)?.text === file.text ? file : ({ ...file, revision: 'source-' + (0, index_js_4.fingerprint)([file.id, file.text, ++serial]).slice(0, 24) })) }; }
    function find(decoded, target) {
        const entry = (0, index_js_2.listRecords)(decoded.normalized).find(e => key(e.ref) === key(target));
        if (!entry)
            throw Error('Target is unavailable: ' + target.id);
        return entry;
    }
    async function prepare(intentInput, task = {}) {
        try {
            (0, index_js_4.canonical)(intentInput);
            const intent = (0, index_js_4.freeze)((0, index_js_4.clone)(intentInput));
            task = { ...task, ...(task.budget ? { budget: (0, index_js_4.freeze)((0, index_js_4.clone)(task.budget)) } : {}) };
            const loadingStarted = Date.now();
            let loadingUnits = 0;
            if (intent.kind === 'profile-command') {
                const profiles = [intent.profile];
                if (intent.command === 'ddn.add-view') {
                    const selected = (0, index_js_2.asString)((0, index_js_2.asRecord)(intent.arguments).profile);
                    if (selected)
                        profiles.push(selected);
                }
                loadingUnits += profiles.length;
                await (0, profile_loading_js_1.prepareRuntimeProfiles)(runtime, profiles, task);
            }
            if (intent.kind === 'set-property' && intent.path === 'profile' && typeof intent.value === 'string')
                await (0, profile_loading_js_1.prepareRuntimeProfiles)(runtime, [intent.value], task);
            if (intent.kind === 'edit-source') {
                const current = runtime.sources();
                if (current) {
                    const proposed = (0, index_js_1.applySourcePatches)(current, intent.patches);
                    loadingUnits += proposed.files.reduce((sum, file) => sum + file.text.length, 0);
                    await (0, profile_loading_js_1.prepareRuntimeProfiles)(runtime, proposed, task);
                }
            }
            if (task.budget && (0, profile_loading_js_1.profileLoadingHost)(runtime)) {
                const elapsedMs = task.budget.elapsedMs - (Date.now() - loadingStarted);
                if (elapsedMs < 0)
                    throw new index_js_4.ComputationStopped('budget-exceeded', 'Profile loading exceeded the command budget');
                task = { ...task, budget: { ...task.budget, elapsedMs, workUnits: Math.max(0, task.budget.workUnits - loadingUnits) } };
            }
            const state = (0, runtime_js_1.runtimeState)(runtime), before = state.source, snapshot = state.current;
            const generation = state.generation;
            const registryFingerprint = (0, index_js_4.fingerprint)(runtime.registry.describe());
            if (!before || !snapshot || !state.decoded)
                return failure('unsupported', [issue('command.sources', 'Editable sources must be open before preparing a command')]);
            if (intent.kind !== 'edit-source' && state.decoded.documents.some(d => before.files.find(f => f.id === d.file.id)?.text !== d.file.text))
                return failure('invalid', [issue('command.source-pending', 'Finish the invalid source edit before visual editing')]);
            const context = (0, index_js_4.createContext)(snapshot.versions, task);
            context.accountMemory(before.files.reduce((n, f) => n + f.text.length * 2, 0));
            const base = (0, index_js_4.freeze)((0, index_js_4.clone)(liveRevision(runtime)));
            let source = (0, runtime_js_1.copySources)(before), decoded = state.decoded;
            let identityOrdinal = 0;
            const unique = (file) => {
                let id;
                do {
                    id = 'ddn-' + (0, index_js_4.fingerprint)([base, intent, file, ++identityOrdinal]).slice(0, 20);
                } while ((0, index_js_2.listRecords)(decoded.normalized).some(entry => entry.file === file && (entry.ref.id === id || entry.record.name === id)));
                return id;
            };
            const apply = (patches) => {
                if (patches.some(p => !source.files.some(f => f.id === p.file)))
                    throw Error('A source patch targets an unavailable file');
                source = (0, index_js_1.applySourcePatches)(source, patches);
                decoded = state.materialize((0, index_js_1.decodeSources)(source, { previous: decoded, ...task }));
                if (!decoded.syntaxValid)
                    throw Error(decoded.diagnostics.map(d => d.message).join('; '));
            };
            const set = (target, path, value) => {
                const entry = find(decoded, target);
                if (entry.kind === 'appearance' && ['position', 'size', 'route'].includes(path.split('.')[0])) {
                    const view = (0, index_js_2.resolveReference)(decoded.normalized, entry.file, entry.record.parent);
                    if ((0, core_js_1.getProfile)((0, index_js_2.asString)(view?.record.profile))?.projection !== 'graph')
                        throw Error('This profile derives item geometry from its projection settings');
                }
                if (['id', 'name', 'role', 'category', 'profile', 'design.state', 'acceptance', 'acceptance_history'].some(p => path === p || path.startsWith(p + '.')))
                    throw Error('Use the dedicated identity/lifecycle command for ' + path);
                if (value !== undefined) {
                    const errors = (0, index_js_3.validateProperty)(ownerOf(entry), path, value, { role: (0, index_js_2.asString)(entry.record.role), profile: (0, index_js_2.asString)(entry.record.profile), category: (0, index_js_2.asString)(entry.record.category, 'element') });
                    if (errors.some(e => e.severity === 'error'))
                        throw Error(errors.map(e => e.message).join('; '));
                }
                apply((0, index_js_1.patchProperty)(decoded, target, path, value));
            };
            const setInternal = (target, path, value) => apply((0, index_js_1.patchProperty)(decoded, target, path, value));
            const append = (file, text, parent) => apply((0, index_js_1.appendDeclaration)(decoded, file, text, parent));
            const appearance = (target) => (0, index_js_2.listRecords)(decoded.normalized).find(e => e.kind === 'appearance' && key((0, index_js_2.resolveReference)(decoded.normalized, e.file, e.record.target)?.ref ?? { file: '', id: '' }) === key(target))?.ref;
            const table = (target, columns, rows) => {
                if (!Array.isArray(columns) || !Array.isArray(rows) || columns.some(c => !(0, index_js_2.isRecord)(c) || typeof c.id !== 'string') || rows.some(r => !Array.isArray(r)))
                    throw Error('Table requires column descriptors and physical row arrays');
                const entry = find(decoded, target);
                if ((0, index_js_2.asRecord)(entry.record.data).source)
                    throw Error('Provider-bound data is read-only; change its provider or create an authored copy');
                const ds = { columns: columns, rows: rows };
                const domainIndex = ds.columns.findIndex(c => c.id === 'domain');
                if (domainIndex >= 0)
                    for (const row of ds.rows) {
                        const name = row[domainIndex];
                        if (typeof name === 'string' && name) {
                            const parts = (0, index_js_1.splitDelimited)(name, '::');
                            if (parts.length > 2)
                                throw Error('A domain reference has one file qualifier');
                            const file = parts.length === 2 ? (0, index_js_2.normalizeLocation)((0, index_js_1.decodeText)(parts[0]), target.file) : target.file;
                            const label = (0, index_js_1.decodeText)(parts.at(-1)).normalize('NFC');
                            const records = (0, index_js_2.listRecords)(decoded.normalized).filter(e => e.file === file);
                            const named = records.find(e => e.record.name === label) ?? records.find(e => e.ref.id === label);
                            if (named && named.record.role !== 'domain')
                                throw Error('Domain name belongs to another declaration: ' + name);
                            if (!named && parts.length === 2)
                                throw Error('Qualified domain is unavailable: ' + name);
                            if (!named)
                                append(target.file, (0, index_js_1.encodeDefinition)({ id: unique(target.file), name: label, role: 'domain' }));
                        }
                    }
                apply((0, index_js_1.replaceDataBody)(decoded, target, ds));
                const occurrence = appearance(target);
                if (occurrence)
                    setInternal(occurrence, 'body', 'columns');
            };
            const addElement = (view, role, name, position) => {
                const parent = find(decoded, view);
                if (parent.kind !== 'view')
                    throw Error('Creation requires a view');
                const profile = (0, core_js_1.getProfile)((0, index_js_2.asString)(parent.record.profile));
                if (!profile || !profile.primary_palette.includes(role))
                    throw Error('This role is not admitted by the selected profile: ' + role);
                const id = unique(view.file), record = { id, role, ...(name ? { name } : {}), ...(position && profile.projection === 'graph' ? { position, pinned: false } : {}) };
                append(view.file, (0, index_js_1.encodeDefinition)(record), view);
            };
            let action = 'model.edit';
            if (intent.kind === 'status')
                action = intent.transition.to === 'accepted' ? 'lifecycle.accept' : intent.transition.from === 'accepted' ? 'lifecycle.reopen' : intent.transition.to === 'in-review' ? 'lifecycle.review' : 'model.edit';
            let authorization;
            switch (intent.kind) {
                case 'create-definition': {
                    const properties = intent.properties ?? {};
                    if (Object.keys(properties).some(path => ['id', 'role', 'category', 'acceptance', 'acceptance_history', 'design'].some(p => path === p || path.startsWith(p + '.'))))
                        throw Error('Creation properties cannot override identity or lifecycle metadata');
                    append(intent.file, (0, index_js_1.encodeDefinition)({ ...properties, id: unique(intent.file), role: intent.role }));
                    break;
                }
                case 'create-occurrence': {
                    let target = find(decoded, intent.target);
                    if (!target.record.name) {
                        setInternal(target.ref, 'id', target.ref.id);
                        target = find(decoded, intent.target);
                    }
                    const name = unique(intent.view.file);
                    append(intent.view.file, 'use ' + sourceQualifier(intent.view.file, intent.target.file) + (0, index_js_1.quoteText)((0, index_js_2.asString)(target.record.name, target.ref.id)) + ' named ' + (0, index_js_1.quoteText)(name), intent.view);
                    const occurrence = (0, index_js_2.listRecords)(decoded.normalized).find(e => e.kind === 'appearance' && e.file === intent.view.file && e.record.name === name);
                    if (!occurrence)
                        throw Error('Created occurrence is unavailable');
                    for (const [path, value] of Object.entries(intent.properties ?? {}))
                        set(occurrence.ref, path, value);
                    break;
                }
                case 'rename':
                    apply((0, index_js_1.renameDeclaration)(decoded, intent.target, intent.name));
                    break;
                case 'set-property':
                    set(intent.target, intent.path, intent.value);
                    break;
                case 'reset-property':
                    set(intent.target, intent.path, undefined);
                    break;
                case 'edit-source':
                    apply(intent.patches);
                    break;
                case 'remove': {
                    if (!['retain-diagnostic', 'remove-dependents'].includes(intent.references))
                        throw Error('Choose an explicit reference-removal policy');
                    const selected = find(decoded, intent.target), selectedNode = (0, index_js_1.findNode)(decoded, intent.target);
                    if ((selected.kind === 'appearance' || selected.kind === 'placement') && selectedNode?.implicit)
                        throw Error('This occurrence is implicit; remove its inline declaration or author an explicit use before removing only this occurrence');
                    if (intent.references === 'remove-dependents') {
                        const removed = new Set([key(intent.target)]);
                        const dependencies = (0, guards_js_1.referenceGraph)(decoded.normalized);
                        const mentions = (value, file) => { const referenced = (0, index_js_2.resolveReference)(decoded.normalized, file, value); return !!referenced && removed.has(key(referenced.ref)); };
                        let grew = true;
                        while (grew) {
                            grew = false;
                            for (const entry of (0, index_js_2.listRecords)(decoded.normalized))
                                if (!removed.has(key(entry.ref)) && (entry.kind === 'appearance' || entry.kind === 'placement' || entry.kind === 'definition') && [...(dependencies.get(key(entry.ref)) ?? [])].some(id => removed.has(id))) {
                                    removed.add(key(entry.ref));
                                    grew = true;
                                }
                        }
                        for (const entry of (0, index_js_2.listRecords)(decoded.normalized).filter(e => e.kind === 'view'))
                            for (const path of ['selection.include', 'selection.items', 'sources']) {
                                const value = (0, index_js_2.getPath)(entry.record, path);
                                if (Array.isArray(value) && value.some(v => mentions(v, entry.file)))
                                    setInternal(entry.ref, path, value.filter(v => !mentions(v, entry.file)));
                            }
                        const deletions = (0, index_js_2.listRecords)(decoded.normalized).filter(e => removed.has(key(e.ref)) && key(e.ref) !== key(intent.target));
                        for (const entry of deletions) {
                            const node = (0, index_js_1.findNode)(decoded, entry.ref);
                            if (!node || node.implicit)
                                continue;
                            if (selectedNode && entry.file === selected.file && node.start >= selectedNode.start && node.end <= selectedNode.end)
                                continue;
                            apply((0, index_js_1.deleteDeclaration)(decoded, entry.ref));
                        }
                    }
                    apply((0, index_js_1.deleteDeclaration)(decoded, intent.target));
                    break;
                }
                case 'connect': {
                    for (const target of [intent.from, intent.to])
                        if (!find(decoded, target).record.name)
                            setInternal(target, 'id', target.id);
                    const from = find(decoded, intent.from), to = find(decoded, intent.to);
                    const reference = (entry) => sourceQualifier(intent.view.file, entry.file) + (0, index_js_1.quoteText)((0, index_js_2.asString)(entry.record.name, entry.ref.id));
                    const name = unique(intent.view.file);
                    append(intent.view.file, `connect ${reference(from)} to ${reference(to)}${intent.relation ? ' as ' + (0, index_js_1.quoteText)(intent.relation) : ''} named ${(0, index_js_1.quoteText)(name)}`, intent.view);
                    const relation = (0, index_js_2.listRecords)(decoded.normalized).find(e => e.file === intent.view.file && e.record.name === name);
                    if (relation)
                        for (const [path, value] of Object.entries(intent.properties ?? {}))
                            set(relation.ref, path, value);
                    let released = false;
                    for (const endpoint of [intent.from, intent.to]) {
                        const selected = find(decoded, endpoint);
                        const occurrence = selected.kind === 'appearance' ? selected : (0, index_js_2.listRecords)(decoded.normalized).find(entry => entry.kind === 'appearance' && key((0, index_js_2.resolveReference)(decoded.normalized, entry.file, entry.record.parent)?.ref ?? { file: '', id: '' }) === key(intent.view) &&
                            key((0, index_js_2.resolveReference)(decoded.normalized, entry.file, entry.record.target)?.ref ?? { file: '', id: '' }) === key(endpoint));
                        if (occurrence?.record.pinned === false && key((0, index_js_2.resolveReference)(decoded.normalized, occurrence.file, occurrence.record.parent)?.ref ?? { file: '', id: '' }) === key(intent.view)) {
                            set(occurrence.ref, 'position', undefined);
                            set(occurrence.ref, 'pinned', undefined);
                            released = true;
                        }
                    }
                    if (released && (0, index_js_2.getPath)((0, index_js_3.resolveProperties)(snapshot, intent.view).values, 'layout.algorithm') === 'manual')
                        set(intent.view, 'layout.algorithm', (0, layout_edit_js_1.automaticLayoutAlgorithm)((0, index_js_2.asString)(find(decoded, intent.view).record.profile)));
                    if (released)
                        decoded = state.materialize((0, index_js_1.decodeSources)(source, { previous: state.decoded, ...task }));
                    break;
                }
                case 'convert-body': {
                    if (!['field-list', 'header-table'].includes(intent.interpretation))
                        throw Error('Choose an explicit draft interpretation');
                    const entry = find(decoded, intent.target), draft = (0, index_js_2.asRecord)(entry.record.draft), text = (0, index_js_2.asString)(draft.text), lines = text.split(/\r?\n/).filter(line => line.trim());
                    if (intent.interpretation === 'field-list')
                        table(intent.target, ['field', 'type', 'domain', 'constraint', 'key', 'comment'].map(id => ({ id })), lines.map(line => [line, null, null, null, null, null]));
                    else {
                        const temporary = (0, index_js_1.decodeSources)({ entry: 'conversion.ddn', files: [{ id: 'conversion.ddn', text: 'data Body\n' + lines.map(l => '    ' + l).join('\n'), revision: '1', encoding: 'utf-8', writable: true }] });
                        if (!temporary.syntaxValid)
                            throw Error(temporary.diagnostics.map(d => d.message).join('; '));
                        const data = (0, index_js_2.listRecords)(temporary.normalized).find(e => e.kind === 'data');
                        if (!data)
                            throw Error('A table draft needs a header');
                        table(intent.target, data.record.columns ?? [], data.record.rows ?? []);
                    }
                    const remaining = (0, index_js_2.asArray)(find(decoded, intent.target).record.incomplete).filter(value => (0, index_js_2.asRecord)(value).path !== 'draft');
                    setInternal(intent.target, 'incomplete', remaining.length ? remaining : undefined);
                    break;
                }
                case 'status': {
                    const target = find(decoded, intent.transition.target);
                    authorization = await authority.authorize(action, [target.ref], base);
                    if (!authorization.allowed)
                        return failure('unauthorized', [issue('command.authority', 'Status change is not authorized')]);
                    const transition = { ...intent.transition, grants: authorization.grants };
                    if (transition.acceptance && transition.acceptance.user !== authorization.principal)
                        return failure('unauthorized', [issue('command.attribution', 'Acceptance must name the authorized principal')]);
                    const eligibility = await runtime.verifier.checkTransition(snapshot, transition, task);
                    if (!eligibility.allowed)
                        return failure('invalid', eligibility.diagnostics);
                    if (transition.from !== transition.to) {
                        if (target.record.acceptance) {
                            setInternal(target.ref, 'acceptance_history', [...(0, index_js_2.asArray)(target.record.acceptance_history), target.record.acceptance]);
                            setInternal(target.ref, 'acceptance', undefined);
                        }
                        setInternal(target.ref, 'design.state', transition.to);
                        if (transition.to === 'accepted' && transition.acceptance)
                            setInternal(target.ref, 'acceptance', { at: transition.acceptance.timestamp, by: transition.acceptance.user, semantic_digest: snapshot.semanticFingerprint });
                    }
                    break;
                }
                case 'profile-command': {
                    const descriptor = (0, registry_js_1.registrations)(runtime.registry).commands?.find(d => d.id === intent.command && d.profiles.includes(intent.profile));
                    if (!descriptor)
                        return failure('unsupported', [issue('command.unsupported', 'No registered command: ' + intent.command)]);
                    if (!nativeIds.includes(intent.command)) {
                        const prepared = await descriptor.prepare(snapshot, intent, context);
                        if (!prepared.ok)
                            return prepared;
                        apply(prepared.command.patches);
                        break;
                    }
                    if (!core_js_1.completeProfileIds.includes(intent.profile))
                        throw Error('Editing is unavailable for this profile');
                    const args = checkedArguments(intent.command, intent.arguments), target = ['ddn.add-view', 'ddn.add-dataset'].includes(intent.command) ? undefined : find(decoded, intent.target);
                    switch (intent.command) {
                        case 'ddn.add-dataset': {
                            if (!(0, index_js_2.asString)(args.name).trim())
                                throw Error('A dataset needs a unique name');
                            append(snapshot.rootFile, 'data ' + (0, index_js_1.quoteText)((0, index_js_2.asString)(args.name)) + '\n    with\n' + (0, index_js_1.serializeProperties)({ id: unique(snapshot.rootFile), columns: args.columns, rows: args.rows }, '        '));
                            break;
                        }
                        case 'ddn.set-records':
                            apply((0, index_js_1.replaceRecordData)(decoded, target.ref, args.columns, args.rows));
                            break;
                        case 'ddn.add-view': {
                            const profile = (0, index_js_2.asString)(args.profile);
                            if (!descriptor.profiles.includes(profile) || !(0, index_js_2.asString)(args.name).trim())
                                throw Error('Choose an installed profile and a unique view name');
                            if ((0, index_js_2.asArray)(args.subtype).some(value => value !== 'erd') || (0, index_js_2.asArray)(args.subtype).length > 1)
                                throw Error('Only the native ERD view subtype is registered for this command');
                            const text = profile === 'ddn@1' && (0, index_js_2.asArray)(args.subtype).includes('erd') ? 'erd ' + (0, index_js_1.quoteText)((0, index_js_2.asString)(args.name)) : 'view ' + (0, index_js_1.quoteText)((0, index_js_2.asString)(args.name)) + ' as ' + (0, index_js_1.quoteText)(profile);
                            append(snapshot.rootFile, text);
                            break;
                        }
                        case 'ddn.create-element':
                            addElement(ref(args.view ?? intent.target), (0, index_js_2.asString)(args.role), typeof args.name === 'string' ? args.name : undefined, args.position);
                            break;
                        case 'ddn.set-position':
                            set(target.ref, 'position', { x: args.x, y: args.y });
                            if (target.kind === 'appearance' && target.record.pinned !== false)
                                set(target.ref, 'pinned', true);
                            break;
                        case 'ddn.set-size':
                            set(target.ref, 'size', { width: args.width, height: args.height });
                            break;
                        case 'ddn.set-draft': {
                            apply((0, index_js_1.replaceDraftBody)(decoded, target.ref, (0, index_js_2.asString)(args.text), (0, index_js_2.asString)(args.format, 'text')));
                            const pending = (0, index_js_2.asArray)(find(decoded, target.ref).record.incomplete).filter(value => (0, index_js_2.asRecord)(value).path !== 'draft');
                            if ((0, index_js_2.asString)(args.text).trim())
                                pending.push({ path: 'draft', raw: '', reason: 'Draft editing is pending' });
                            setInternal(target.ref, 'incomplete', pending.length ? pending : undefined);
                            const occurrence = appearance(target.ref);
                            if (occurrence)
                                setInternal(occurrence, 'body', 'draft');
                            break;
                        }
                        case 'ddn.set-table':
                            table(target.ref, args.columns, args.rows);
                            break;
                        case 'ddn.set-columns':
                            table(target.ref, args.columns, (0, index_js_2.asRecord)(target.record.data).rows ?? []);
                            break;
                        case 'ddn.set-cell':
                        case 'ddn.add-row':
                        case 'ddn.remove-row': {
                            const data = (0, index_js_2.asRecord)(target.record.data), columns = (0, index_js_2.asArray)(data.columns), rows = (0, index_js_4.clone)((0, index_js_2.asArray)(data.rows));
                            if (intent.command === 'ddn.add-row')
                                rows.push(columns.map(() => null));
                            else {
                                const row = Number(args.row);
                                if (!Number.isInteger(row) || row < 0 || row >= rows.length)
                                    throw Error('Row is unavailable');
                                if (intent.command === 'ddn.remove-row')
                                    rows.splice(row, 1);
                                else {
                                    const column = typeof args.column === 'number' ? args.column : columns.findIndex(c => (0, index_js_2.asRecord)(c).id === args.column);
                                    if (!Number.isInteger(column) || column < 0 || column >= columns.length)
                                        throw Error('Column is unavailable');
                                    rows[row][column] = args.value ?? null;
                                }
                            }
                            table(target.ref, columns, rows);
                            break;
                        }
                        case 'ddn.add-note':
                            append(target.file, 'notes : Notes\n' + (0, index_js_2.asString)(args.text).split('\n').map(line => '    ' + line).join('\n'), target.ref);
                            break;
                        case 'ddn.set-note':
                            apply((0, index_js_1.replaceNoteBody)(decoded, target.ref, (0, index_js_2.asString)(args.text)));
                            break;
                    }
                    break;
                }
                default:
                    return failure('unsupported', [issue('command.unsupported', 'Unknown command intent')]);
            }
            await context.checkpoint((0, index_js_2.listRecords)(decoded.normalized).length);
            const writeSet = changedRecords(snapshot, decoded), protectedScopes = (0, guards_js_1.affectedProtected)(snapshot, decoded.normalized);
            if (intent.kind !== 'status' && protectedScopes.length)
                return failure('invalid', protectedScopes.map(target => issue('command.protected', 'Reopen this protected scope before semantic editing', target)));
            if (intent.kind !== 'status') {
                const lifecycle = (0, guards_js_1.checkLifecycleMutation)(snapshot.normalized, decoded.normalized);
                if (lifecycle.length)
                    return failure('invalid', lifecycle);
            }
            authorization = await authority.authorize(action, writeSet, base);
            if (!authorization.allowed)
                return failure('unauthorized', [issue('command.authority', 'The affected scope is not authorized')]);
            const candidate = { ...snapshot, normalized: decoded.normalized, semanticFingerprint: (0, index_js_4.fingerprint)(decoded.normalized), coverage: decoded.coverage };
            const report = await runtime.verifier.verifyModel(candidate, { scope: { kind: 'workarea' }, purpose: 'design', level: 'semantic', ...task });
            if (['invalid', 'cancelled', 'budget-exceeded', 'stale', 'unsupported'].includes(report.outcome))
                return failure(report.outcome === 'cancelled' ? 'cancelled' : report.outcome === 'budget-exceeded' ? 'budget-exceeded' : 'invalid', report.diagnostics);
            if (registryFingerprint !== (0, index_js_4.fingerprint)(runtime.registry.describe()))
                return failure('conflict', [issue('command.capabilities', 'Registered rules changed while preparing the command')]);
            context.check();
            if (generation !== state.generation || (0, index_js_4.canonical)(liveRevision(runtime)) !== (0, index_js_4.canonical)(base))
                return failure('conflict', [issue('command.conflict', 'Revision changed while preparing the command')]);
            const patches = difference(before, source), id = 'command-' + (++serial);
            const readSet = (0, index_js_2.listRecords)(snapshot.normalized).sort((a, b) => key(a.ref) < key(b.ref) ? -1 : key(a.ref) > key(b.ref) ? 1 : 0).map(entry => ({ target: entry.ref, path: '', fingerprint: (0, index_js_4.fingerprint)(entry.record) }));
            const prepared = (0, index_js_4.freeze)({ id, base, intent, readSet, writeSet, patches, modelDelta: writeSet.map(target => ({ target: target, before: ((0, index_js_2.findRecord)(snapshot.normalized, target) ?? null), after: ((0, index_js_2.findRecord)(decoded.normalized, target) ?? null) })), summary: [intent.kind === 'profile-command' ? intent.command : intent.kind, `${patches.length} source file(s), ${writeSet.length} record(s)`], diagnostics: [...decoded.diagnostics, ...report.diagnostics], protectedScopes, eligible: true });
            pending.set(id, { public: prepared, before: (0, runtime_js_1.copySources)(before), after: source, decoded, action, principal: authorization.principal, registryFingerprint, generation });
            return { ok: true, command: prepared };
        }
        catch (error) {
            const code = error instanceof index_js_4.ComputationStopped ? error.outcome === 'cancelled' ? 'cancelled' : 'budget-exceeded' : 'invalid';
            return failure(code, [issue('command.prepare', error instanceof Error ? error.message : 'Command preparation failed')]);
        }
    }
    async function commit(preparedId, task = {}, group, groupBefore, history) {
        if (committing || travelling && !history)
            return failure('conflict', [issue('command.busy', 'Another command or history operation is committing')]);
        const prepared = pending.get(preparedId);
        if (!prepared)
            return failure('invalid', [issue('command.missing', 'Prepared command is missing or discarded')]);
        committing = true;
        try {
            const state = (0, runtime_js_1.runtimeState)(runtime), before = liveRevision(runtime);
            task = { ...task, ...(task.budget ? { budget: (0, index_js_4.freeze)((0, index_js_4.clone)(task.budget)) } : {}) };
            const context = (0, index_js_4.createContext)(state.current.versions, task);
            if (group && prepared.public.intent.kind === 'status')
                return failure('invalid', [issue('history.group-lifecycle', 'Lifecycle changes must remain separate from live settings.')]);
            if (group && !group.current)
                return failure('conflict', [issue('history.group-conflict', 'The diagram changed outside this settings session. Reopen the editor to continue.')]);
            let rejected;
            const reject = (code, diagnostics) => { rejected = { code, diagnostics }; return diagnostics; };
            const unchanged = (publication) => {
                context.check();
                if (pending.get(preparedId) !== prepared)
                    return reject('cancelled', [issue('command.discarded', 'Prepared command was discarded')]);
                if (prepared.registryFingerprint !== (0, index_js_4.fingerprint)(runtime.registry.describe()))
                    return reject('conflict', [issue('command.capabilities', 'Registered rules changed; prepare again')]);
                if (state.generation !== prepared.generation + (publication ? 1 : 0) || !sameSources(state.source, prepared.before) || (0, index_js_4.canonical)(liveRevision(runtime)) !== (0, index_js_4.canonical)(prepared.public.base))
                    return reject('conflict', [issue('command.conflict', 'The source context or model/source/data revision changed; prepare again')]);
                return [];
            };
            const check = async (publication = false) => {
                const changed = unchanged(publication);
                if (changed.length)
                    return changed;
                const authorized = await authority.authorize(prepared.action, prepared.public.writeSet, before);
                if (!authorized.allowed || authorized.principal !== prepared.principal)
                    return reject('unauthorized', [issue('command.revoked', 'Authority or principal changed since preparation')]);
                if (prepared.public.intent.kind === 'status') {
                    const eligibility = await runtime.verifier.checkTransition(state.current, { ...prepared.public.intent.transition, grants: authorized.grants }, task);
                    if (!eligibility.allowed)
                        return reject('invalid', eligibility.diagnostics);
                    const latest = await authority.authorize(prepared.action, prepared.public.writeSet, before);
                    if (!latest.allowed || latest.principal !== authorized.principal || (0, index_js_4.canonical)(latest.grants) !== (0, index_js_4.canonical)(authorized.grants))
                        return reject('unauthorized', [issue('command.revoked', 'Authority changed while validating the transition')]);
                }
                return unchanged(publication);
            };
            if ((await check()).length)
                return { ok: false, failure: rejected };
            if (!prepared.public.patches.length) {
                pending.delete(preparedId);
                return { ok: true, receipt: { commandId: preparedId, before, after: before, changed: [] } };
            }
            const next = freshSource(prepared.after, prepared.before), baseline = groupBefore ?? prepared.before;
            const forward = difference(baseline, next), inverse = difference(next, baseline);
            const opened = await state.commitSources(next, task, (0, index_js_4.fingerprint)(prepared.decoded.normalized), { check: () => check(true), published(result) {
                    pending.delete(preparedId);
                    historySources = next;
                    if (history) {
                        const from = history.direction === 'undo' ? undo : redo, to = history.direction === 'undo' ? redo : undo;
                        from.pop();
                        to.push(history.entry);
                        expectedHistory = (0, index_js_4.canonical)(result.revision);
                    }
                    else if (prepared.public.intent.kind !== 'status') {
                        historyBytes -= redo.reduce((sum, entry) => sum + entry.bytes, 0);
                        redo.length = 0;
                        const previous = undo.at(-1);
                        if (group && previous?.group === group) {
                            undo.pop();
                            historyBytes -= previous.bytes;
                        }
                        const entry = { forward, inverse, bytes: [...forward, ...inverse].reduce((n, p) => n + p.text.length * 2, 0), expected: (0, index_js_4.canonical)(result.revision), ...(group ? { group } : {}) };
                        if (forward.length) {
                            undo.push(entry);
                            historyBytes += entry.bytes;
                        }
                        expectedHistory = entry.expected;
                        let trimmed = false;
                        while (undo.length > limits.maxCommands || historyBytes > limits.maxBytes) {
                            const removed = undo.shift();
                            if (!removed)
                                break;
                            historyBytes -= removed.bytes;
                            trimmed = true;
                        }
                        if (trimmed)
                            state.diagnostics = (0, index_js_4.freeze)([...state.diagnostics, { code: 'history.checkpoint', severity: 'info', message: 'Undo history reached its configured limit. Older edits are no longer undoable; current source is retained.' }]);
                    }
                    else {
                        undo.length = 0;
                        redo.length = 0;
                        historyBytes = 0;
                        expectedHistory = '';
                        historySources = undefined;
                    }
                } });
            if (!opened.committed)
                return rejected ? { ok: false, failure: rejected } : failure(opened.diagnostics.some(d => d.code === 'runtime.stale') ? 'conflict' : opened.diagnostics.some(d => d.code === 'runtime.cancelled') ? 'cancelled' : opened.diagnostics.some(d => d.code === 'runtime.budget-exceeded') ? 'budget-exceeded' : 'invalid', opened.diagnostics);
            return { ok: true, receipt: { commandId: preparedId, before, after: opened.revision, changed: prepared.public.writeSet } };
        }
        catch (error) {
            return failure(error instanceof index_js_4.ComputationStopped ? error.outcome : 'invalid', [issue('command.commit', error instanceof Error ? error.message : 'Commit failed')]);
        }
        finally {
            committing = false;
        }
    }
    async function travel(direction, task = {}) {
        if (committing || travelling)
            return failure('conflict', [issue('history.busy', 'Another command or history operation is committing')]);
        travelling = true;
        try {
            const from = direction === 'undo' ? undo : redo, entry = from.at(-1);
            if (!entry)
                return failure('invalid', [issue('history.empty', 'Nothing to ' + direction)]);
            if (!historySources || !sameSources(runtime.sources(), historySources) || (0, index_js_4.canonical)(liveRevision(runtime)) !== expectedHistory)
                return failure('conflict', [issue('history.conflict', 'External changes require a history checkpoint')]);
            const source = runtime.sources();
            const patches = (direction === 'undo' ? entry.inverse : entry.forward).map(p => ({ ...p, base: source.files.find(f => f.id === p.file).revision }));
            const prepared = await prepare({ kind: 'edit-source', patches }, task);
            if (!prepared.ok)
                return prepared;
            return await commit(prepared.command.id, task, undefined, undefined, { direction, entry });
        }
        catch (error) {
            return failure('invalid', [issue('history.failed', error instanceof Error ? error.message : 'History operation failed')]);
        }
        finally {
            travelling = false;
        }
    }
    const service = { prepare, commit, undo: task => travel('undo', task), redo: task => travel('redo', task), discard(id) { pending.delete(id); } };
    historyFactories.set(service, () => {
        const before = runtime.sources();
        if (!before)
            throw Error('Open editable sources before editing settings.');
        let baseline = (0, runtime_js_1.copySources)(before);
        const abort = new AbortController();
        let expected = (0, index_js_4.canonical)(liveRevision(runtime)), generation = (0, runtime_js_1.runtimeState)(runtime).generation, closed = false, changed = false;
        const group = {
            get current() { return !closed && !(0, runtime_js_1.runtimeState)(runtime).disposed && generation === (0, runtime_js_1.runtimeState)(runtime).generation && expected === (0, index_js_4.canonical)(liveRevision(runtime)); },
            get changed() { return changed; },
            signal: { get aborted() { return abort.signal.aborted; }, onAbort(handler) { abort.signal.addEventListener('abort', handler); return () => abort.signal.removeEventListener('abort', handler); } },
            run(action) {
                if (!group.current)
                    throw Error('The diagram changed outside this settings session. Reopen the editor to continue.');
                const previous = activeHistoryGroups.get(service);
                activeHistoryGroups.set(service, group);
                try {
                    return action();
                }
                finally {
                    if (previous)
                        activeHistoryGroups.set(service, previous);
                    else
                        activeHistoryGroups.delete(service);
                }
            },
            async commit(id, task = {}) {
                if (!baseline)
                    return failure('cancelled', [issue('history.group-closed', 'This settings session is closed.')]);
                const result = await commit(id, { ...task, cancel: group.signal }, group, baseline);
                if (result.ok) {
                    expected = (0, index_js_4.canonical)(result.receipt.after);
                    generation = (0, runtime_js_1.runtimeState)(runtime).generation;
                    changed = !!undo.find(entry => entry.group === group);
                }
                return result;
            },
            async revert() {
                if (!group.current || undo.at(-1)?.group !== group)
                    return failure('conflict', [issue('history.group-conflict', 'Only the latest settings session can be reverted. Use Undo to review later edits first.')]);
                const result = await travel('undo', { cancel: group.signal });
                if (result.ok) {
                    expected = (0, index_js_4.canonical)(result.receipt.after);
                    generation = (0, runtime_js_1.runtimeState)(runtime).generation;
                    changed = false;
                }
                return result;
            },
            close() { closed = true; baseline = undefined; abort.abort(); },
        };
        return group;
    });
    return service;
}
function createNativeCommandPack() { return commandPack(nativeProfiles, 'ddn-native'); }
function createCompleteCommandPack() { return commandPack(core_js_1.completeProfileIds, 'ddn-complete'); }
function createModularCommandPack() { return commandPack(core_js_1.completeProfileIds, 'ddn-native', 'ddn-modular-commands'); }
function commandPack(profiles, dependency, id = dependency + '-commands') {
    return { manifest: { id, version: '1.0.0', api: '1.0', hash: (0, index_js_4.fingerprint)([nativeIds, profiles]), languages: ['ddn-next-1'], defaults: ['ddn-next-1'], profiles, dependencies: [dependency], capabilities: ['native.edit'] }, registrations: {
            schemas: Object.fromEntries(nativeIds.map(id => [id + '.arguments', argumentSchema(id)])),
            commands: nativeIds.map(id => ({ id, profiles, argumentSchemaId: id + '.arguments', propertyPaths: id === 'ddn.set-position' ? ['position'] : id === 'ddn.set-size' ? ['size'] : id === 'ddn.set-draft' ? ['draft', 'body'] : ['data', 'definitions', 'appearances'], editor: 'specialized', async prepare(input, intent) {
                    if (intent.kind !== 'profile-command' || intent.command !== id || !(0, index_js_2.isRecord)(intent.arguments))
                        return failure('invalid', [issue('command.arguments', 'Invalid native command arguments')]);
                    try {
                        checkedArguments(id, intent.arguments);
                    }
                    catch (error) {
                        return failure('invalid', [issue('command.arguments', String(error))]);
                    }
                    return { ok: true, command: { id: 'native-plan-' + (0, index_js_4.fingerprint)(intent), base: input.revision, intent, readSet: [], writeSet: [intent.target], patches: [], modelDelta: { kind: 'native-intent', command: id, arguments: intent.arguments }, summary: [id], diagnostics: [], protectedScopes: [], eligible: true } };
                } })),
        } };
}

},
"runtime/src/layout-edit.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.automaticLayoutAlgorithm = automaticLayoutAlgorithm;
exports.reflowViewPatches = reflowViewPatches;
const index_js_1 = require("language/src/index.js");
const index_js_2 = require("model/src/index.js");
const index_js_3 = require("defaults/src/index.js");
const core_js_1 = require("profiles/src/core.js");
const runtime_js_1 = require("runtime/src/runtime.js");
const key = (ref) => ref.file + '\0' + ref.id;
function automaticLayoutAlgorithm(profile) {
    const standard = (0, index_js_2.asString)((0, index_js_2.getPath)((0, index_js_3.resolve)({}, 'view_definition', { profile }).values, 'layout.algorithm'), 'auto');
    return standard === 'manual' ? 'auto' : standard;
}
function reflowViewPatches(runtime, view, effectiveAlgorithm) {
    const state = (0, runtime_js_1.runtimeState)(runtime), before = state.source, snapshot = state.current;
    if (!before || !snapshot || !state.decoded)
        throw Error('Editable sources are unavailable.');
    if (!before.files.find(file => file.id === view.file)?.writable)
        throw Error('This view belongs to a read-only file.');
    if (state.decoded.documents.some(document => before.files.find(file => file.id === document.file.id)?.text !== document.file.text))
        throw Error('Finish the invalid source edit before reflowing.');
    const records = (0, index_js_2.listRecords)(state.decoded.normalized), target = records.find(record => key(record.ref) === key(view));
    if (target?.kind !== 'view')
        throw Error('Reflow requires a view.');
    const profile = (0, index_js_2.asString)(target.record.profile);
    if ((0, core_js_1.getProfile)(profile)?.projection !== 'graph')
        throw Error('This view derives its arrangement from its data and projection settings.');
    let source = (0, runtime_js_1.copySources)(before), decoded = state.decoded;
    const set = (ref, path, value) => {
        const patches = (0, index_js_1.patchProperty)(decoded, ref, path, value);
        if (!patches.length)
            return;
        source = (0, index_js_1.applySourcePatches)(source, patches);
        decoded = state.materialize((0, index_js_1.decodeSources)(source, { previous: decoded }));
        if (!decoded.syntaxValid)
            throw Error(decoded.diagnostics.map(diagnostic => diagnostic.message).join('; '));
    };
    for (const entry of records) {
        if (entry.kind !== 'appearance' || key((0, index_js_2.resolveReference)(state.decoded.normalized, entry.file, entry.record.parent)?.ref ?? { file: '', id: '' }) !== key(view))
            continue;
        if (entry.record.position !== undefined)
            set(entry.ref, 'position', undefined);
        if (entry.record.pinned !== undefined)
            set(entry.ref, 'pinned', undefined);
        if ((0, index_js_2.asRecord)(entry.record.route).via !== undefined)
            set(entry.ref, 'route.via', undefined);
    }
    const algorithm = effectiveAlgorithm ?? (0, index_js_2.asString)((0, index_js_2.getPath)((0, index_js_3.resolveProperties)(snapshot, view).values, 'layout.algorithm'));
    if (algorithm === 'manual') {
        set(view, 'layout.algorithm', automaticLayoutAlgorithm(profile));
    }
    return source.files.flatMap(file => {
        const previous = before.files.find(candidate => candidate.id === file.id);
        return file.text === previous.text ? [] : [{ file: file.id, base: previous.revision, start: 0, end: previous.text.length, text: file.text }];
    });
}

},
"runtime/src/save.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.sourcesForSave = sourcesForSave;
const index_js_1 = require("language/src/index.js");
const index_js_2 = require("model/src/index.js");
const index_js_3 = require("execution/src/index.js");
const runtime_js_1 = require("runtime/src/runtime.js");
async function sourcesForSave(runtime, task = {}) {
    const state = (0, runtime_js_1.runtimeState)(runtime);
    let source = runtime.sources(), decoded = state.decoded;
    if (!source || !decoded || !state.current)
        return source;
    if (decoded.documents.some(document => source.files.find(file => file.id === document.file.id)?.text !== document.file.text))
        return source;
    const sourceFingerprint = () => (0, index_js_3.canonical)(runtime.sources()?.files.map(file => [file.id, file.revision, file.text]));
    const sourceRevision = sourceFingerprint();
    const revision = (0, index_js_3.canonical)(state.current.revision);
    const context = (0, index_js_3.createContext)(state.current.versions, task);
    const capturedAt = new Date().toISOString();
    for (const entry of (0, index_js_2.listRecords)(state.current.normalized)) {
        const data = entry.kind === 'data' ? entry.record : entry.kind === 'definition' ? (0, index_js_2.asRecord)(entry.record.data) : undefined;
        if (!data || data.persist !== 'snapshot' || !data.source || !Array.isArray(data.columns) || !Array.isArray(data.rows) || typeof data.revision !== 'string')
            continue;
        await context.checkpoint(data.rows.length + 1);
        const previous = (0, index_js_2.asRecord)(data.snapshot);
        if (previous.revision === data.revision && (0, index_js_3.canonical)(previous.columns) === (0, index_js_3.canonical)(data.columns) && (0, index_js_3.canonical)(previous.rows) === (0, index_js_3.canonical)(data.rows))
            continue;
        const snapshot = { columns: data.columns, rows: data.rows, revision: data.revision, captured_at: capturedAt };
        source = (0, index_js_1.applySourcePatches)(source, (0, index_js_1.patchProperty)(decoded, entry.ref, entry.kind === 'data' ? 'snapshot' : 'data.snapshot', snapshot));
        decoded = (0, index_js_1.decodeSources)(source, { ...task, previous: decoded });
        if (!decoded.syntaxValid)
            throw new Error('Unable to preserve the source while saving a data snapshot');
    }
    context.check();
    if ((0, index_js_3.canonical)(runtime.snapshot()?.revision) !== revision || sourceFingerprint() !== sourceRevision)
        throw new Error('The document changed while preparing save artifacts; save the current revision again');
    return source;
}

},
"standalone/src/modular-designer-api.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createVerifier = exports.getViewerHandle = exports.createViewer = exports.createCommandService = exports.createModularRuntimeOptions = exports.createRuntime = exports.createDesigner = exports.createBrowserRuntimeOptions = void 0;
const index_js_1 = require("designer/src/index.js");
const commands_js_1 = require("runtime/src/commands.js");
Object.defineProperty(exports, "createCommandService", { enumerable: true, get: function () { return commands_js_1.createCommandService; } });
const modular_viewer_js_1 = require("standalone/src/modular-viewer.js");
Object.defineProperty(exports, "createViewer", { enumerable: true, get: function () { return modular_viewer_js_1.createViewer; } });
Object.defineProperty(exports, "getViewerHandle", { enumerable: true, get: function () { return modular_viewer_js_1.getViewerHandle; } });
const modular_runtime_js_1 = require("standalone/src/modular-runtime.js");
Object.defineProperty(exports, "createRuntime", { enumerable: true, get: function () { return modular_runtime_js_1.createModularRuntime; } });
const modular_loading_js_1 = require("standalone/src/modular-loading.js");
Object.defineProperty(exports, "createModularRuntimeOptions", { enumerable: true, get: function () { return modular_loading_js_1.createModularRuntimeOptions; } });
const modular_verifier_js_1 = require("standalone/src/modular-verifier.js");
Object.defineProperty(exports, "createVerifier", { enumerable: true, get: function () { return modular_verifier_js_1.createModularVerifier; } });
const browser_options_js_1 = require("standalone/src/browser-options.js");
const modular_loading_js_2 = require("standalone/src/modular-loading.js");
(0, modular_loading_js_2.installModularWorkerFactory)();
const createBrowserRuntimeOptions = () => { const options = (0, modular_loading_js_1.createModularRuntimeOptions)(); return (0, browser_options_js_1.withBrowserExecutor)({ ...options, packs: [...options.packs, (0, commands_js_1.createModularCommandPack)()] }); };
exports.createBrowserRuntimeOptions = createBrowserRuntimeOptions;
const createDesigner = (viewer, options) => {
    const runtime = (0, modular_viewer_js_1.getViewerHandle)(viewer).runtime;
    if (!runtime.registry.describe().some(pack => pack.id.endsWith('-commands')))
        runtime.registry.install((0, commands_js_1.createModularCommandPack)());
    return (0, index_js_1.createDesigner)(viewer, options);
};
exports.createDesigner = createDesigner;

}});})();
