import { getViewerHandle } from '../../viewer/src/native.js';
import { fontFamily, listFonts, loadFontFile, ensureFontResources, getFontResources, installFontResources } from '../../viewer/src/fonts.js';
import { textureBackground } from '../../viewer/src/texture.js';
import { choiceField } from '../../viewer/src/choice-field.js';
import { flushLiveSettings, notifyLiveSettings } from './live-settings.js';
import { records, pathValue, str, object, refKey, titleOf } from '../../presentation/src/native.js';
import { runtimeState } from '../../runtime/src/runtime.js';
import { findNode } from '../../language/src/index.js';
import { colourField, numberField, syncNumberField } from './dialogs.js';
import { parsePresetPack, serializePresetPack, standardPresets, mergePresetPacks, readLocalPresets, writeLocalPresets, PRESET_PATHS } from './presets.js';
const sessionLibraries = new WeakMap();
const unsavedLibraries = new WeakSet();
const valueAt = (values, path, fallback) => values.get(path) ?? fallback;
function download(document, name, text) { const url = URL.createObjectURL(new Blob([text], { type: 'application/json' })), a = document.createElement('a'); a.href = url; a.download = name; a.click(); setTimeout(() => URL.revokeObjectURL(url), 1000); }
/** Live appearance editor; every valid change uses the authorized source command service. */
export function openAppearance(viewer, panel, commit) {
    const handle = getViewerHandle(viewer), document = handle.ownerDocument, snapshot = handle.runtime.snapshot();
    if (!snapshot)
        throw Error('Open a workarea first.');
    const all = records(snapshot), entry = handle.selectedEntry(), scopes = [];
    if (entry && entry.definition.owner === 'definition' && entry.definition.record.category !== 'relation') {
        const decoded = runtimeState(handle.runtime).decoded;
        if (entry.appearance && decoded && !findNode(decoded, entry.appearance.ref)?.implicit)
            scopes.push({ ref: entry.appearance.ref, label: 'This appearance', target: 'element', profile: str(entry.view.record.profile) });
        scopes.push({ ref: entry.definition.ref, label: 'Shared element', target: 'element', profile: str(entry.view.record.profile) });
    }
    if (entry) {
        const decoded = runtimeState(handle.runtime).decoded;
        if (entry.placement && decoded && !findNode(decoded, entry.placement.ref)?.implicit)
            scopes.push({ ref: entry.placement.ref, label: 'This view placement', target: 'view', profile: str(entry.view.record.profile) });
        scopes.push({ ref: entry.view.ref, label: 'View background and text', target: 'view', profile: str(entry.view.record.profile) });
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
            library = readLocalPresets(storage);
            sessionLibraries.set(document, library);
        }
    }
    catch { /* Local persistence can be disabled; retain the page's session library. */ }
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
        let changes = {}, values = new Map(), chosen = 0, tab = 'Background', loading = false, ticket = 0;
        const field = (container, name, value, type = 'text') => { const wrap = document.createElement('label'); wrap.textContent = name; const input = document.createElement('input'); input.setAttribute('aria-label', name); input.type = type; input.value = value; wrap.append(input); container.append(wrap); return input; };
        const select = (container, name, choices, value) => choiceField(container, name, choices, value);
        const effective = (path, fallback) => Object.hasOwn(changes, path) && changes[path] !== undefined ? changes[path] : valueAt(values, path, fallback);
        const changed = (path, value) => { changes[path] = value; notifyLiveSettings(body); };
        const inherit = (container, path) => { const button = document.createElement('button'); button.type = 'button'; button.textContent = 'Inherit'; button.setAttribute('aria-label', 'Inherit ' + path); button.addEventListener('click', () => { changed(path, undefined); message.textContent = 'Using the inherited setting.'; void flushLiveSettings(body).then(() => { if (body.isConnected)
            render(); }).catch(error => { message.textContent = error.message; }); }); container.append(button); };
        const preview = (container) => {
            const sample = document.createElement('div');
            sample.className = 'ddn-appearance-preview';
            sample.textContent = 'Aa · Design ideas\nReadable text on the selected background';
            sample.style.cssText = 'min-height:88px;padding:12px;border:1px solid var(--ddn-ui-border);border-radius:4px;white-space:pre-line;overflow:hidden';
            container.append(sample);
            return () => {
                const fill = String(effective('background.color', '#ffffff')), texture = textureBackground(effective('background.texture', null), fill);
                sample.style.backgroundColor = fill;
                sample.style.backgroundImage = texture?.image ?? 'none';
                sample.style.backgroundSize = texture?.size ?? '';
                sample.style.color = String(effective('text.color', '#243449'));
                sample.style.fontFamily = fontFamily(String(effective('style.font', 'sans')));
                sample.style.fontSize = String(effective('style.font_size', 16)) + 'px';
            };
        };
        const persist = (next) => { library = next; sessionLibraries.set(document, library); try {
            if (!storage)
                throw Error('Storage unavailable');
            writeLocalPresets(storage, library);
            unsavedLibraries.delete(document);
            message.textContent = 'Saved in this browser. Export the pack to share or back it up.';
        }
        catch {
            unsavedLibraries.add(document);
            message.textContent = 'Available for this session only. Export the pack to keep it.';
        } };
        const render = () => {
            const current = scopes[chosen];
            targetLabel.textContent = 'Editing: ' + titleOf(current.target === 'element' ? entry.definition.record : current.target === 'view' ? entry.view.record : workarea.record);
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
                const color = colourField(grid, 'Background colour', String(effective('background.color', '#ffffff')));
                color.addEventListener('input', () => { changed('background.color', color.value); update(); });
                inherit(grid, 'background.color');
                const initial = object(effective('background.texture', null)), kind = select(grid, 'Texture', ['none', 'paper', 'linen', 'grid', 'dots'], str(initial.kind, 'none'));
                const ink = colourField(grid, 'Texture colour', str(initial.color, '#725d43'));
                const opacity = numberField(grid, 'Texture opacity', Number(initial.opacity ?? .12), { min: 0, max: 1, step: .01 });
                const scale = numberField(grid, 'Texture scale', Number(initial.scale ?? 32), { min: 4, max: 128, step: 1 });
                for (const input of [opacity, scale]) {
                    input.step = 'any';
                    syncNumberField(input);
                }
                const seed = numberField(grid, 'Texture seed', String(initial.seed ?? 1), { min: 0, max: 1000, step: 1 });
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
                const names = [...new Set(['sans', 'serif', 'mono', 'handwriting', ...listFonts(document).map(f => f.family), String(effective('style.font', 'sans'))])];
                const family = select(grid, 'Font family', names, String(effective('style.font', 'sans'))), size = numberField(grid, 'Font size (pt)', Number(effective('style.font_size', 16)) * .75, { min: 6, max: 48, step: .5 });
                size.step = 'any';
                syncNumberField(size);
                family.addEventListener('change', () => { const key = family.value, scopeTicket = ticket; void ensureFontResources(document, [{ family: key }]).then(() => { if (body.isConnected && ticket === scopeTicket) {
                    changed('style.font', key);
                    update();
                } }).catch(error => { if (body.isConnected)
                    message.textContent = String(error.message); }); });
                size.addEventListener('input', () => { changed('style.font_size', size.valueAsNumber * 4 / 3); update(); });
                const ink = colourField(grid, 'Text colour', String(effective('text.color', '#243449')));
                ink.addEventListener('input', () => { changed('text.color', ink.value); update(); });
                inherit(grid, 'style.font');
                inherit(grid, 'style.font_size');
                inherit(grid, 'text.color');
                const fontFile = field(content, 'Load local font', '', 'file');
                fontFile.accept = '.woff2,.woff,.ttf,.otf';
                fontFile.addEventListener('change', () => { const file = fontFile.files?.[0], scopeTicket = ticket; if (!file)
                    return; void loadFontFile(document, file).then(async (font) => { if (!body.isConnected || ticket !== scopeTicket)
                    return; if (body.ownerDocument !== document)
                    await installFontResources(body.ownerDocument, getFontResources(document)); if (!body.isConnected || ticket !== scopeTicket)
                    return; changed('style.font', font.family); render(); message.textContent = 'Local font loaded for this page. Export its resources to keep it with your document.'; }).catch(error => { if (body.isConnected)
                    message.textContent = String(error.message); }); });
                const resources = field(content, 'Import font resources', '', 'file');
                resources.accept = '.json,application/json';
                resources.addEventListener('change', () => { const file = resources.files?.[0]; if (!file)
                    return; if (file.size > 32 * 1024 * 1024) {
                    message.textContent = 'Font resource packs are limited to 32 MiB.';
                    return;
                } void file.text().then(async (text) => { const pack = JSON.parse(text); if (pack?.format !== 'ddn-font-resources-1' || !Array.isArray(pack.resources))
                    throw Error('Expected a DDN font resource pack.'); await installFontResources(document, pack.resources); if (body.isConnected) {
                    if (body.ownerDocument !== document)
                        await installFontResources(body.ownerDocument, pack.resources);
                    render();
                    message.textContent = 'Local font resources loaded.';
                } }).catch(error => { if (body.isConnected)
                    message.textContent = error.message; }); });
                const exportFonts = document.createElement('button');
                exportFonts.type = 'button';
                exportFonts.textContent = 'Export font resources';
                exportFonts.addEventListener('click', () => download(document, 'ddn-font-resources.json', JSON.stringify({ format: 'ddn-font-resources-1', resources: getFontResources(document) }, null, 2)));
                content.append(exportFonts);
                const note = document.createElement('p');
                note.textContent = 'Bundled fonts work offline. Custom font files stay local; text uses a fallback when their resources are unavailable.';
                content.append(note);
                update();
            }
            else {
                const choices = [...standardPresets(current.target), ...library.filter(p => p.target === current.target && (!p.profile || p.profile === current.profile))];
                const selectedPreset = choices.find(p => Object.entries(p.properties).every(([path, value]) => JSON.stringify(effective(path, undefined)) === JSON.stringify(value)))?.id ?? '';
                const pick = choiceField(content, 'Appearance preset', choices.map(p => ({ value: p.id, label: p.name, description: (p.id.startsWith('standard-') ? 'Standard' : p.scope === 'company' ? 'Company' : 'User') + ' · ' + p.name, preview: (document) => {
                        const sample = document.createElement('span');
                        sample.className = 'ddn-choice-surface';
                        sample.textContent = 'Aa · Ideas';
                        const fill = String(p.properties['background.color'] ?? '#ffffff'), texture = textureBackground(p.properties['background.texture'], fill);
                        sample.style.backgroundColor = fill;
                        sample.style.color = String(p.properties['text.color'] ?? '#243449');
                        sample.style.fontFamily = fontFamily(String(p.properties['style.font'] ?? 'sans'));
                        if (texture) {
                            sample.style.backgroundImage = texture.image;
                            sample.style.backgroundSize = texture.size;
                        }
                        return sample;
                    } })), selectedPreset);
                pick.addEventListener('change', () => { const preset = choices.find(p => p.id === pick.value); if (preset) {
                    changes = { ...changes, ...structuredClone(preset.properties) };
                    notifyLiveSettings(body);
                    message.textContent = 'Preset applied to the selected scope.';
                } });
                const name = field(content, 'New user preset name', 'My appearance'), save = document.createElement('button');
                name.dataset.ddnLiveIgnore = '';
                save.type = 'button';
                save.textContent = 'Save user preset';
                save.addEventListener('click', () => {
                    try {
                        const properties = {};
                        for (const path of PRESET_PATHS) {
                            const value = effective(path, undefined);
                            if (value !== undefined)
                                properties[path] = value;
                        }
                        const preset = { id: 'user-' + (document.defaultView?.crypto.randomUUID?.() ?? Date.now().toString(36)), name: name.value, scope: 'user', target: current.target, ...(current.profile ? { profile: current.profile } : {}), properties };
                        const next = mergePresetPacks(library, parsePresetPack(serializePresetPack([preset])).presets);
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
                remove.addEventListener('click', () => { const p = library.find(p => p.id === pick.value); if (p?.scope === 'user') {
                    persist(library.filter(item => item.id !== p.id));
                    render();
                } });
                content.append(remove);
                const input = field(content, 'Import user/company preset pack', '', 'file');
                input.accept = '.json,application/json';
                input.addEventListener('change', () => { const file = input.files?.[0]; if (!file)
                    return; if (file.size > 262144) {
                    message.textContent = 'Preset files are limited to 256 KiB.';
                    return;
                } void file.text().then(text => { persist(mergePresetPacks(library, parsePresetPack(text).presets)); render(); }).catch(error => { message.textContent = error.message; }); });
                const exportButton = document.createElement('button');
                exportButton.type = 'button';
                exportButton.textContent = 'Export preset pack';
                exportButton.addEventListener('click', () => download(document, 'ddn-appearance-presets.json', serializePresetPack(library)));
                content.append(exportButton);
                const note = document.createElement('p');
                note.textContent = 'Company packs are imported, read-only library entries here. Applying a preset copies its settings into the chosen scope; company identity does not grant approval or enforce policy.';
                content.append(note);
            }
        };
        for (const name of ['Background', 'Font', 'Presets']) {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = name;
            button.setAttribute('role', 'tab');
            button.addEventListener('click', () => { tabs.inert = true; content.inert = true; void flushLiveSettings(body).then(() => { if (body.isConnected) {
                tab = name;
                render();
            } }).catch(error => { message.textContent = error.message; }).finally(() => { tabs.inert = false; content.inert = false; }); });
            tabs.append(button);
        }
        tabs.addEventListener('keydown', event => { if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key))
            return; const buttons = [...tabs.querySelectorAll('button:not(:disabled)')], index = buttons.findIndex(b => b === body.ownerDocument.activeElement); if (index < 0)
            return; event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (event.key === 'ArrowRight' ? 1 : -1) + buttons.length) % buttons.length; buttons[next].click(); buttons[next].focus(); });
        const readValues = async () => {
            const token = ticket, inspection = await viewer.inspect(scopes[chosen].ref);
            if (token !== ticket || !body.isConnected)
                return;
            values = new Map(inspection.properties.map(p => [p.path, p.effective]));
            // Inspection reports object leaves; preserve full records in saved presets.
            for (const parent of ['background.texture', 'shadow']) {
                const object = {};
                for (const [path, value] of values)
                    if (path.startsWith(parent + '.'))
                        object[path.slice(parent.length + 1)] = value;
                if (Object.keys(object).length)
                    values.set(parent, object);
            }
        };
        const refresh = async () => { ++ticket; loading = true; changes = {}; content.textContent = 'Loading appearance…'; await readValues(); loading = false; if (body.isConnected)
            render(); };
        scope.addEventListener('change', event => { event.stopPropagation(); const next = Number(scope.value); scope.value = String(chosen); scope.disabled = true; content.inert = true; void flushLiveSettings(body).then(async () => { if (!body.isConnected)
            return; chosen = next; scope.value = String(next); await refresh(); }).catch(e => { message.textContent = e.message; }).finally(() => { scope.disabled = false; content.inert = false; }); });
        void refresh().catch(e => { message.textContent = e.message; });
        return async () => { if (loading)
            throw Error('Wait for settings to load.'); for (const input of content.querySelectorAll('input[type=number]'))
            if (!input.checkValidity() || !Number.isFinite(input.valueAsNumber))
                throw Error('Enter a valid value for ' + input.parentElement?.firstChild?.textContent); if (Object.keys(changes).length) {
            const pending = { ...changes }, target = scopes[chosen].ref;
            await commit(target, pending);
            for (const [path, value] of Object.entries(pending))
                if (Object.hasOwn(changes, path) && JSON.stringify(changes[path]) === JSON.stringify(value))
                    delete changes[path];
            await readValues();
        } };
    });
}
//# sourceMappingURL=appearance.js.map