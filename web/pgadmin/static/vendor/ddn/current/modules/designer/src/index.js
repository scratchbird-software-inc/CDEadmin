import { elementPreview } from './element-preview.js';
import { createDrawer, drawerFor } from '../../viewer/src/drawer.js';
import { sideTabs } from '../../viewer/src/side-tabs.js';
import { paletteGroup, paletteGroupOrder } from './palette-groups.js';
import { createStandardDialog, colourField, syncColourField, numberField, syncNumberField } from './dialogs.js';
import { choiceField, syncChoiceField } from '../../viewer/src/choice-field.js';
import { flushLiveSettings, notifyLiveSettings, waitForSettingsSave } from './live-settings.js';
import { openAppearance } from './appearance.js';
import { openSymbol } from './symbol.js';
import { uiIcon } from '../../viewer/src/ui-icons.js';
import { openProperties } from './properties.js';
import { createLiveSettings } from './live-settings.js';
import { mountMindmapActions, mindmapSelection } from './mindmap-actions.js';
import { mountResizeHandles } from './resize-handles.js';
import { relationMenuItems } from './relation-menu.js';
import { mindmapSource } from './mindmap-source.js';
import { viewTypePicker, profileDisplayName, diagramHeader } from './view-picker.js';
import { newDiagramDialog } from './new-diagram.js';
import { viewLayoutDialog, viewLayoutSource } from './view-layout-picker.js';
import { getViewSurfacePreset } from '../../profiles/src/view-surfaces.js';
export { createStandardDialog, colourField } from './dialogs.js';
export { parsePresetPack, serializePresetPack } from './presets.js';
import { createCommandService, currentCommandHistoryGroup } from '../../runtime/src/commands.js';
import { reflowViewPatches } from '../../runtime/src/layout-edit.js';
import { profileLoadingHost } from '../../runtime/src/profile-loading.js';
import { registrations } from '../../runtime/src/registry.js';
import { codex } from '../../profiles/src/schema-core.js';
import { createFieldEditor, childSchema } from './schema-editor.js';
import { runtimeState } from '../../runtime/src/runtime.js';
import { sourcesForSave } from '../../runtime/src/save.js';
import { allNodes, findNode, patchProperty, applySourcePatches, decodeSources, encodeDefinition, quoteText, deleteDeclaration, replaceNoteBody, appendDeclaration } from '../../language/src/index.js';
import { registerUICommands, notifyUICommands } from '../../viewer/src/ui-commands.js';
import { gridStep, viewSetting } from '../../viewer/src/grid.js';
import { parseCsv, clipboardText, clipRecord, parseClipboardText, pasteRecords } from './clipboard.js';
/** Shared by every designer on the page, so a copy survives New/Open and pop-out windows. */
let clipboard = [];
let clipboardWritten = '';
const DOCUMENT_OUTPUTS = ['pdf', 'html', 'dashboard', 'docx', 'odt', 'csv', 'json', 'markdown'];
import { listRecords, resolveReference, asString, asArray, asRecord } from '../../model/src/index.js';
import { getProfile, roleDescriptor } from '../../profiles/src/core.js';
import { getViewerHandle } from '../../viewer/src/native.js';
import { records, object, array, str, num, pathValue, tableData, titleOf, refKey, resolveRecord } from '../../presentation/src/native.js';
const active = new WeakSet();
function jsonValue(value) { return value; }
export function createDesigner(viewer, options) {
    if (active.has(viewer))
        throw new Error('This viewer already has a designer');
    const handle = getViewerHandle(viewer), document = handle.ownerDocument;
    const standalone = () => {
        const snapshot = handle.runtime.snapshot();
        return !!snapshot && records(snapshot).some(record => record.owner === 'workarea' && record.file === snapshot.rootFile && record.record.mode === 'standalone');
    };
    const commands = createCommandService(handle.runtime, options.authority, options.history);
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
.ddn-verb-list{display:grid;gap:4px;margin:4px 0 8px}.ddn-viewer .ddn-verb-list button,.ddn-ui-dialog .ddn-verb-list button{justify-content:flex-start;text-align:left;font-size:12px;padding:6px 9px}.ddn-verb-list button b{font-weight:650;color:var(--ddn-ui-accent)}.ddn-verb-list small{margin-left:auto;color:var(--ddn-ui-muted);font:10px ui-monospace,monospace}.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-outline,.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-stage{grid-row:3}.ddn-viewer:has(.ddn-designer-toolbar){grid-template-rows:auto auto minmax(200px,1fr) auto}.ddn-appearance-grid{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1fr);gap:8px;align-items:end}.ddn-appearance-grid>label{min-width:0}.ddn-appearance-grid>.ddn-ui-number-field{grid-column:1/-1}.ddn-appearance-tabs{display:flex;gap:4px;margin:10px 0}.ddn-appearance-tabs [aria-selected=true]{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text)}.ddn-appearance-message{font-size:12px;color:var(--ddn-ui-muted)}.ddn-designer-menu{position:absolute;z-index:25;display:grid;gap:3px;padding:6px;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);border:1px solid var(--ddn-ui-border);border-radius:6px;box-shadow:0 6px 20px #14243633}.ddn-designer-menu button{text-align:left}.ddn-designer-preview{fill:#3b82f622;stroke:#2563eb;stroke-width:2;stroke-dasharray:4 3;pointer-events:none}@media(max-width:480px){.ddn-appearance-grid{grid-template-columns:minmax(0,1fr)}}@media(max-width:760px){.ddn-viewer:has(.ddn-designer-toolbar){grid-template-rows:auto auto auto minmax(340px,1fr) auto}.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-outline{grid-row:3}.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-stage{grid-row:4}.ddn-viewer:has(.ddn-designer-toolbar) .ddn-viewer-status{grid-row:5}}`;
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
        const decoded = runtimeState(handle.runtime).decoded, node = decoded && findNode(decoded, ref);
        return !!node && !node.implicit && !node.generated && writable(ref);
    };
    const revision = () => JSON.stringify(handle.runtime.snapshot()?.revision);
    function requireCurrent(expected) {
        if (disposed || revision() !== expected)
            throw Error('The diagram changed while you were editing. Reopen the editor and try again.');
    }
    // Paint may extend beyond the logical object (shadows, pins, clips). Editing
    // always operates on the semantic body, whose hit bounds do not include it.
    const semanticBounds = (entry) => entry.item.hitTargets.find(hit => refKey(hit.target) === refKey(entry.definition.ref))?.bounds ?? entry.item.hitTargets[0]?.bounds ?? entry.item.bounds;
    // Fixed surfaces scale presentation; source positions stay in local diagram units.
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
        const group = currentCommandHistoryGroup(commands);
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
    function nativeCommand(command, target, args, profile) { const entry = selected(); return apply({ kind: 'profile-command', profile: profile ?? str(entry?.view.record.profile, 'ddn@1'), command, target, arguments: jsonValue(args) }); }
    const toolbarGroups = new Map();
    function button(label, action) {
        const element = document.createElement('button');
        element.type = 'button';
        element.textContent = label;
        const icon = { 'Add view': 'plus', 'Add entity': 'plus', 'Add element': 'grid', 'Connect': 'link', 'Reflow': 'reflow', 'Appearance & presets': 'palette', 'Properties': 'settings', 'Rename': 'type', 'Undo': 'undo', 'Redo': 'redo', 'Delete': 'minus' }[label];
        if (icon)
            element.prepend(uiIcon(document, icon));
        const groupName = ['Add element', 'Add existing element', 'Connect', 'Add view', 'Add entity', 'Workarea', 'Reflow'].includes(label) ? 'Create' : ['Undo', 'Redo'].includes(label) ? 'History' : ['Datasets', 'Source', 'Projection'].includes(label) ? 'Document' : 'Selection';
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
            existing.focus();
            handle.announce('Close the open editor before opening another settings form.');
            return existing;
        }
        const live = ['Edit title', 'Draft body', 'Details shown (this appearance)', 'Details shown (entity default)', 'Edit table data', 'Comments', 'Constraints', 'Properties', 'Paper & attachments', 'Appearance & presets', 'Symbol & label', 'Projection settings', 'Element and relationship details', 'Datasets', 'Workarea settings', 'Edit topic name', 'Topic notes', 'Page setup', 'Header', 'Footer'].includes(title);
        let session;
        const dialog = createStandardDialog(handle.overlays, { title, modal: !live, ...(applyLabel ? { applyLabel } : {}),
            ...(!live ? { async onApply() {
                    if (JSON.stringify(handle.runtime.snapshot()?.revision) !== openedRevision)
                        throw Error('The diagram changed while this editor was open. Copy your edits and reopen it to reconcile the current revision.');
                    await submit();
                } } : { async beforeClose() { try {
                    await session?.finish();
                }
                catch (error) {
                    notifyError(error);
                } } }),
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
                session = createLiveSettings({ body: dialog.body, commands, submit, showError: dialog.showError,
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
        const current = runtimeState(handle.runtime), original = current.source;
        if (!original || !current.decoded)
            throw Error('Editable sources are unavailable.');
        let source = original, decoded = current.decoded;
        for (const [path, value] of Object.entries(properties)) {
            source = applySourcePatches(source, patchProperty(decoded, target, path, value));
            decoded = decodeSources(source, { previous: decoded });
            if (!decoded.syntaxValid)
                throw Error(decoded.diagnostics.map(d => d.message).join('\n'));
        }
        const patches = source.files.flatMap(file => { const before = original.files.find(candidate => candidate.id === file.id); return file.text === before.text ? [] : [{ file: file.id, base: before.revision, start: 0, end: before.text.length, text: file.text }]; });
        if (patches.length)
            await apply({ kind: 'edit-source', patches });
    }
    async function renameTitle(entry, value) {
        if (mindmapSelection(handle, entry)) {
            const draft = mindmapSource(handle.runtime, entry.view.ref);
            if (findNode(draft.decoded, entry.definition.ref)?.generated)
                draft.materialize();
            draft.set(entry.definition.ref, 'title', value);
            await commitMindmap(draft);
        }
        else
            await set(entry.definition.ref, 'title', value);
    }
    function editTitle(entry = requireSelection()) {
        if (mindmapSelection(handle, entry)) {
            editTopicName(entry);
            return;
        }
        panel('Edit title', body => { const input = field(body, 'Display title', str(entry.definition.record.title) || str(entry.definition.record.name)); return async () => { await set(entry.definition.ref, 'title', input.value); }; });
    }
    function editDraft(entry = requireSelection()) { panel('Draft body', body => { const input = field(body, 'Free-form text', str(pathValue(entry.definition.record, 'draft.text')), true); const note = document.createElement('p'); note.textContent = 'Free-form text shown inside the element. Use Columns to turn each line into a field later.'; body.append(note); return async () => { await nativeCommand('ddn.set-draft', entry.definition.ref, { text: input.value, format: str(pathValue(entry.definition.record, 'draft.format'), 'text') }); }; }); }
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
            select.value = pathValue(entry.definition.record, 'draft.format') === 'table' ? 'header-table' : 'field-list';
            label.append(select);
            body.append(label);
            const pre = document.createElement('pre');
            pre.textContent = str(pathValue(entry.definition.record, 'draft.text'));
            body.append(pre);
            return async () => { await apply({ kind: 'convert-body', target: entry.definition.ref, interpretation: select.value }); };
        });
    }
    function details(entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const data = tableData(snapshot, entry.definition);
        const decoded = runtimeState(handle.runtime).decoded;
        const explicit = entry.appearance && decoded && !findNode(decoded, entry.appearance.ref)?.implicit;
        const target = explicit ? entry.appearance.ref : entry.definition.ref;
        panel(explicit ? 'Details shown (this appearance)' : 'Details shown (entity default)', body => { const visibility = { ...object(entry.definition.record.column_visibility), ...object(entry.appearance?.record.column_visibility) }; const choices = data.columns.map(column => { const label = document.createElement('label'), checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.checked = visibility[str(column.id)] === 'shown' || visibility[str(column.id)] !== 'hidden' && str(column.id) === 'field'; checkbox.dataset.column = str(column.id); label.append(checkbox, document.createTextNode(str(column.label, str(column.id)))); body.append(label); return { id: str(column.id), checkbox }; }); return async () => { await set(target, 'column_visibility', Object.fromEntries(choices.map(({ id, checkbox }) => [id, checkbox.checked ? 'shown' : 'hidden']))); }; });
    }
    function editRows(entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const data = tableData(snapshot, entry.definition);
        panel('Edit table data', body => {
            const table = document.createElement('table'), head = document.createElement('tr');
            for (const column of data.columns) {
                const th = document.createElement('th');
                th.textContent = str(column.label, str(column.id));
                head.append(th);
            }
            table.append(head);
            const inputs = [];
            for (const row of data.rows) {
                const tr = document.createElement('tr');
                inputs.push(data.columns.map((column, i) => { const td = document.createElement('td'), input = document.createElement('input'); input.value = String(row[i] ?? ''); input.setAttribute('aria-label', `${str(column.id)} row ${inputs.length + 1}`); td.append(input); tr.append(td); return input; }));
                table.append(tr);
            }
            body.append(table);
            const add = document.createElement('button');
            add.textContent = 'Add row';
            add.addEventListener('click', () => { const tr = document.createElement('tr'); inputs.push(data.columns.map(column => { const td = document.createElement('td'), input = document.createElement('input'); input.setAttribute('aria-label', str(column.id)); td.append(input); tr.append(td); return input; })); table.append(tr); notifyLiveSettings(body); });
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
            const currentNotes = () => array(records(handle.runtime.snapshot()).find(record => refKey(record.ref) === refKey(entry.definition.ref))?.record.notes).map(asRecord);
            const refreshChoices = (pick, updateText) => {
                known = currentNotes();
                choice.replaceChildren();
                known.forEach((note, index) => choice.add(new Option(str(note.title, str(note.name, 'Note ' + (index + 1))), str(note.id))));
                choice.add(new Option('New note', 'new'));
                selectedId = known.some(note => note.id === pick) ? pick : pick === '' && known[0] ? str(known[0].id) : 'new';
                choice.value = selectedId;
                if (updateText)
                    input.value = str(known.find(note => note.id === selectedId)?.text);
            };
            refreshChoices('', true);
            choice.addEventListener('change', event => { event.stopPropagation(); const next = choice.value; choice.value = selectedId; run(async () => { await flushLiveSettings(body); refreshChoices(next, true); }); });
            const remove = document.createElement('button');
            remove.type = 'button';
            remove.textContent = 'Delete selected note';
            if (topic)
                body.append(remove);
            remove.addEventListener('click', () => { input.value = ''; deleting = true; notifyLiveSettings(body); });
            let deleting = false;
            return async () => {
                const selected = selectedId, text = input.value, deleteNote = deleting;
                deleting = false;
                if (deleteNote && selected === 'new' || selected === 'new' && !text)
                    return;
                const existing = currentNotes(), beforeIds = new Set(existing.map(note => str(note.id)));
                if (topic) {
                    const draft = mindmapSource(handle.runtime, entry.view.ref);
                    if (findNode(draft.decoded, entry.definition.ref)?.generated)
                        draft.materialize();
                    const saveNotes = (values) => {
                        for (const note of existing) {
                            const ref = { file: entry.definition.file, id: str(note.id) };
                            if (findNode(draft.decoded, ref)?.kind === 'notes')
                                draft.apply(deleteDeclaration(draft.decoded, ref));
                        }
                        draft.set(entry.definition.ref, 'notes', values);
                    };
                    const note = existing.find(note => note.id === selected);
                    if (note) {
                        const target = { file: entry.definition.file, id: selected }, node = findNode(draft.decoded, target);
                        if (node?.kind === 'notes')
                            draft.apply(deleteNote ? deleteDeclaration(draft.decoded, target) : replaceNoteBody(draft.decoded, target, text));
                        else
                            saveNotes(deleteNote ? existing.filter(note => note.id !== selected) : existing.map(note => note.id === selected ? { ...note, text } : note));
                    }
                    else
                        saveNotes([...existing, { id: draft.unique('mindmap-note', entry.definition.file), name: draft.unique('Note', entry.definition.file), title: 'Notes', text }]);
                    await commitMindmap(draft);
                }
                else if (selected === 'new')
                    await nativeCommand('ddn.add-note', entry.definition.ref, { text }, str(entry.view.record.profile));
                else {
                    const decoded = runtimeState(handle.runtime).decoded, target = { file: entry.definition.file, id: selected };
                    if (decoded && findNode(decoded, target))
                        await nativeCommand('ddn.set-note', target, { text }, str(entry.view.record.profile));
                    else
                        await applyProperties(entry.definition.ref, { notes: existing.map(note => note.id === selected ? { ...note, text } : note) });
                }
                const created = currentNotes().find(note => !beforeIds.has(str(note.id)));
                // Keep the text field untouched while typing continues during a render.
                refreshChoices(created ? str(created.id) : deleteNote ? 'new' : selected, false);
                remove.disabled = selectedId === 'new';
            };
        });
    }
    function constraints(entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        panel('Constraints', body => {
            const available = records(snapshot).filter(record => record.owner === 'definition' && record.record.role === 'constraint');
            const selected = new Set(array(entry.definition.record.constraints).map(value => { const reference = object(value); return JSON.stringify([str(reference.file, entry.definition.file), str(reference.id)]); }));
            const note = document.createElement('p');
            note.textContent = 'Choose reusable constraints. Create a constraint from the element palette when a new one is needed.';
            body.append(note);
            const choices = available.map(record => { const label = document.createElement('label'), input = document.createElement('input'); input.type = 'checkbox'; input.checked = selected.has(refKey(record.ref)); label.append(input, document.createTextNode(titleOf(record.record) + ' (' + record.file + ')')); body.append(label); return { record, input }; });
            return async () => { await set(entry.definition.ref, 'constraints', choices.filter(choice => choice.input.checked).map(choice => choice.record.ref)); };
        });
    }
    function properties() { openProperties(viewer, panel, applyProperties); }
    function paperAttachments(entry = requireSelection()) {
        if (entry.definition.record.category === 'relation' || !['definition', 'view'].includes(entry.definition.owner))
            throw Error('Select an element or view for paper and attachment settings.');
        const state = runtimeState(handle.runtime);
        if (!state.decoded || !state.source)
            throw Error('Editable sources must be open.');
        const explicit = (record) => record && findNode(state.decoded, record.ref) && !findNode(state.decoded, record.ref).implicit;
        const scopes = entry.definition.owner === 'view'
            ? [...(explicit(entry.placement) ? [{ record: entry.placement, label: 'This view placement' }] : []), { record: entry.view, label: 'View definition' }]
            : [...(explicit(entry.appearance) ? [{ record: entry.appearance, label: 'This appearance' }] : []), { record: entry.definition, label: 'Shared definition' }];
        const defaults = { 'style.paper': 'plain', 'shadow.kind': 'none', 'shadow.color': '#000000', 'shadow.opacity': .24, 'shadow.blur': 4, 'shadow.lift': 10, 'shadow.spread': 0 };
        const attachmentColors = { 'push-pin': '#df4545', 'round-pin': '#45a3da', 'paper-clip': '#5b83b4', 'binder-clip': '#3b414b', tape: '#e4c788' };
        panel('Paper & attachments', body => {
            const scope = document.createElement('select');
            scope.setAttribute('aria-label', 'Apply appearance settings to');
            scope.dataset.ddnLiveIgnore = '';
            scopes.forEach(({ label }, index) => { const option = document.createElement('option'); option.value = String(index); option.textContent = label; scope.append(option); });
            const targetLabel = document.createElement('p');
            targetLabel.textContent = 'Editing: ' + titleOf(entry.definition.record);
            body.append(targetLabel);
            const instructions = document.createElement('p');
            instructions.textContent = 'Only changed settings are saved. Inherit removes the setting here so file defaults and CSS can supply it. Attachments are visual decorations; they do not change meaning or review status.';
            const controls = document.createElement('div');
            body.append(scope, instructions, controls);
            let chosen = 0, generation = 0, loading = true;
            const changes = new Map();
            const readers = new Map();
            const selectField = (container, title, choices, value) => choiceField(container, title, choices.map(([value, label]) => ({ value, label })), value);
            const numericField = (container, title, value, min, max, step = 'any') => {
                const input = numberField(container, title, value, { min: Math.max(min, -256), max: Math.min(max, 256), step: step === 'any' ? (max - min <= 1 ? .01 : .1) : Number(step) });
                input.type = 'number';
                input.min = String(min);
                input.max = String(max);
                input.step = step;
                input.required = true;
                syncNumberField(input);
                return input;
            };
            const colorField = (container, title, value) => colourField(container, title, value, { dialogHost: handle.overlays });
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
                const sourceValue = (path) => pathValue(records(handle.runtime.snapshot()).find(item => refKey(item.ref) === refKey(target.ref))?.record ?? target.record, path);
                const resolvedValue = (path) => {
                    if (effective.has(path))
                        return effective.get(path);
                    const parts = path.split('.');
                    for (let length = parts.length - 1; length > 0; length--) {
                        const parent = effective.get(parts.slice(0, length).join('.'));
                        if (parent !== undefined)
                            return pathValue(object(parent), parts.slice(length).join('.'));
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
                            syncNumberField(input);
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
                        // A newly supplied shadow object uses the contract's
                        // offset shape unless the user chose another shape.
                        if (path.startsWith('shadow.') && path !== 'shadow.kind' && !currentShadow && !changes.has('shadow.kind')) {
                            shadow.value = 'offset';
                            syncChoiceField(shadow);
                            updateShadowOffsets();
                        }
                    };
                    input.addEventListener('input', edited);
                    input.addEventListener('change', edited);
                    inherit.addEventListener('change', () => { changes.set(path, undefined); readers.delete(path); if (!inherit.checked)
                        readers.set(path, read); });
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
                    readers.set('decorations', () => { for (const read of attachmentReaders)
                        read(); return attachments; });
                    notifyLiveSettings(body);
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
                        const kind = selectField(group, 'Attachment kind', [['push-pin', 'Push-pin'], ['round-pin', 'Round pin'], ['paper-clip', 'Paper-clip'], ['binder-clip', 'Binder clip'], ['tape', 'Tape']], str(item.kind, 'push-pin'));
                        const color = colorField(group, 'Attachment colour', str(item.color, attachmentColors[kind.value]));
                        kind.addEventListener('change', () => { item.kind = kind.value; if (item.color === undefined) {
                            color.value = attachmentColors[kind.value];
                            syncColourField(color);
                        } changedAttachments(); });
                        color.addEventListener('input', () => { item.color = color.value; changedAttachments(); });
                        const position = selectField(group, 'Attachment position', [['lt', 'Left top'], ['ct', 'Centre top'], ['rt', 'Right top'], ['lm', 'Left middle'], ['cm', 'Centre middle'], ['rm', 'Right middle'], ['lb', 'Left bottom'], ['cb', 'Centre bottom'], ['rb', 'Right bottom']], str(item.position, 'ct'));
                        position.addEventListener('change', () => { item.position = position.value; changedAttachments(); });
                        for (const [path, label, fallback, min, max] of [['size', 'Attachment size', 32, 8, 128], ['rotation', 'Attachment rotation', 0, -180, 180], ['opacity', 'Attachment opacity', 1, 0, 1], ['offset.x', 'Attachment horizontal offset', 0, -256, 256], ['offset.y', 'Attachment vertical offset', 0, -256, 256]]) {
                            const input = numericField(group, label, num(pathValue(item, path), fallback), min, max);
                            let touched = false;
                            input.addEventListener('input', () => { touched = true; changedAttachments(); });
                            attachmentReaders.push(() => {
                                if (!touched)
                                    return;
                                const result = readNumber(input, label);
                                if (path.startsWith('offset.'))
                                    item.offset = jsonValue({ ...object(item.offset), [path.slice(7)]: result });
                                else
                                    item[path] = result;
                            });
                        }
                        const remove = document.createElement('button');
                        remove.type = 'button';
                        remove.textContent = 'Remove attachment';
                        remove.addEventListener('click', guarded(() => { for (const read of attachmentReaders)
                            read(); attachments.splice(index, 1); renderAttachments(); changedAttachments(); }));
                        group.append(remove);
                    });
                };
                add.addEventListener('click', guarded(() => { if (attachments.length >= 32)
                    return; for (const read of attachmentReaders)
                    read(); attachments.push({ kind: 'push-pin' }); renderAttachments(); changedAttachments(); }));
                inheritAttachments.addEventListener('change', () => { if (inheritAttachments.checked) {
                    changes.set('decorations', undefined);
                    readers.delete('decorations');
                }
                else
                    changedAttachments(); });
                renderAttachments();
                loading = false;
            };
            scope.addEventListener('change', event => {
                event.stopPropagation();
                const next = Number(scope.value);
                scope.value = String(chosen);
                run(async () => { await flushLiveSettings(body); chosen = next; scope.value = String(chosen); await refresh(); });
            });
            void refresh().catch(notifyError);
            return async () => {
                if (loading)
                    throw Error('Wait for appearance settings to load.');
                if (!changes.size)
                    return;
                const current = runtimeState(handle.runtime), original = current.source;
                if (!original || !current.decoded)
                    throw Error('Editable sources are unavailable.');
                let source = original, decoded = current.decoded;
                for (const [path, reset] of changes) {
                    const value = readers.has(path) ? readers.get(path)() : reset;
                    source = applySourcePatches(source, patchProperty(decoded, scopes[chosen].record.ref, path, value));
                    decoded = decodeSources(source, { previous: decoded });
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
        const references = records(snapshot).filter(r => !['appearance', 'placement'].includes(r.owner)).map(r => ({ ref: r.ref, label: `${titleOf(r.record)} (${r.owner}, ${r.file})` }));
        const profile = getProfile(str(entry.view.record.profile));
        panel(projection ? 'Projection settings' : 'Element and relationship details', body => {
            if (projection) {
                if (!profile)
                    throw Error('Profile is unavailable');
                const note = document.createElement('p');
                note.textContent = profile.scope + ' Omitted settings use the versioned defaults.';
                body.append(note);
                const editor = createFieldEditor(body, codex.roots[profile.projection_schema], jsonValue(pathValue(entry.view.record, 'projection.options')), references, 'Projection');
                return async () => { await set(entry.view.ref, 'projection.options', editor.read()); };
            }
            const role = roleDescriptor(str(entry.definition.record.role), str(entry.definition.record.category, 'element'));
            const core = codex.coreTypes[str(entry.definition.record.role)];
            const sectionSchema = (key) => core && key === (core.category === 'relation' ? 'qualifiers' : 'content') ? core.schema : childSchema(role?.schema, key) ?? childSchema(codex.roots.definition, key);
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
            let editor = createFieldEditor(controls, sectionSchema(choices.value), jsonValue(entry.definition.record[choices.value]), references, choices.value);
            let section = choices.value;
            choices.addEventListener('change', event => {
                event.stopPropagation();
                const next = choices.value;
                choices.value = section;
                run(async () => { await flushLiveSettings(body); section = next; choices.value = next; controls.replaceChildren(); const current = records(handle.runtime.snapshot()).find(record => refKey(record.ref) === refKey(entry.definition.ref)); editor = createFieldEditor(controls, sectionSchema(section), jsonValue(current?.record[section]), references, section); });
            });
            return async () => { await applyProperties(entry.definition.ref, { [section]: editor.read() }); };
        });
    }
    function datasets() {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            return;
        const all = records(snapshot), data = all.filter(r => r.owner === 'data'), view = selected()?.view ?? handle.scene()?.views[0];
        const references = all.filter(r => !['appearance', 'placement'].includes(r.owner)).map(r => ({ ref: r.ref, label: `${titleOf(r.record)} (${r.owner}, ${r.file})` }));
        panel('Datasets', body => {
            const choice = document.createElement('select');
            choice.setAttribute('aria-label', 'Dataset');
            choice.dataset.ddnLiveIgnore = '';
            const available = () => records(handle.runtime.snapshot()).filter(record => record.owner === 'data');
            const updateChoices = (selected) => { choice.replaceChildren(new Option('New dataset', 'new')); available().forEach(record => choice.add(new Option(titleOf(record.record), refKey(record.ref)))); choice.value = selected; };
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
                const record = available().find(record => refKey(record.ref) === selected);
                name.disabled = !!record;
                name.value = str(record?.record.name, 'NewData');
                create.hidden = !!record;
                const columnLabel = document.createElement('h4');
                columnLabel.textContent = 'Columns';
                area.append(columnLabel);
                columns = createFieldEditor(area, childSchema(codex.roots.data_record, 'columns'), jsonValue(record?.record.columns ?? [{ id: 'label', type: 'text' }, { id: 'value', type: 'number' }]), references, 'Columns');
                const rowLabel = document.createElement('h4');
                rowLabel.textContent = 'Rows';
                area.append(rowLabel);
                rows = createFieldEditor(area, childSchema(codex.roots.data_record, 'rows'), jsonValue(record?.record.rows ?? []), references, 'Rows');
            };
            choice.addEventListener('change', event => { event.stopPropagation(); const next = choice.value; choice.value = selected; run(async () => { await flushLiveSettings(body); selected = next; choice.value = next; render(); }); });
            create.addEventListener('click', () => { creating = true; notifyLiveSettings(body); });
            render();
            const note = document.createElement('p');
            note.textContent = 'Edits to existing data update its diagrams immediately. Create new data explicitly, then bind it using Projection settings. Provider-bound data remains read-only.';
            body.append(note);
            return async () => {
                const isNew = selected === 'new';
                if (isNew && !creating)
                    return;
                creating = false;
                const record = available().find(record => refKey(record.ref) === selected), label = name.value, profile = str(view?.record.profile, 'ddn@1');
                const target = isNew ? view?.ref ?? { file: snapshot.rootFile, id: '' } : record.ref;
                await nativeCommand(isNew ? 'ddn.add-dataset' : 'ddn.set-records', target, { ...(isNew ? { name: label } : {}), columns: columns.read(), rows: rows.read() }, profile);
                if (isNew) {
                    const created = available().find(record => record.record.name === label);
                    if (created) {
                        selected = refKey(created.ref);
                        updateChoices(selected);
                        name.disabled = true;
                        create.hidden = true;
                    }
                }
            };
        });
    }
    const canMove = (entry) => entry.definition.owner === 'view' || getProfile(str(entry.view.record.profile))?.projection === 'graph';
    const geometryLocked = (entry, kind) => pathValue(entry.effective, 'locked.' + kind) === true;
    let resizeDecoded;
    const resizeSources = new Map();
    const canResize = (entry) => {
        const target = entry.appearance ?? entry.placement;
        if (!target || !writable(target.ref) || geometryLocked(entry, 'resize') || !canMove(entry) || entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints) || entry.definition.owner === 'view' && entry.surfaceTransform)
            return false;
        const decoded = runtimeState(handle.runtime).decoded;
        if (decoded !== resizeDecoded) {
            resizeDecoded = decoded;
            resizeSources.clear();
            if (decoded)
                for (const node of allNodes(decoded))
                    if (node.ref && !resizeSources.has(refKey(node.ref)))
                        resizeSources.set(refKey(node.ref), !node.generated);
        }
        const editable = resizeSources.get(refKey(target.ref));
        return editable === true || editable === false && entry.view.record.profile === 'mindmap.basic@1';
    };
    async function resizeElement(entry, width, height) {
        if (!canResize(entry))
            return;
        const target = (entry.appearance ?? entry.placement), size = { width: Math.max(40, snap(width)), height: Math.max(40, snap(height)) };
        const decoded = runtimeState(handle.runtime).decoded;
        if (entry.view.record.profile === 'mindmap.basic@1' && decoded && findNode(decoded, target.ref)?.generated) {
            const draft = mindmapSource(handle.runtime, entry.view.ref);
            draft.materialize();
            draft.set(target.ref, 'size', size);
            await commitMindmap(draft);
        }
        else
            await nativeCommand('ddn.set-size', target.ref, size);
    }
    async function statusChange(next, entry = requireSelection()) {
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            throw new Error('No model');
        const from = str(pathValue(entry.definition.record, 'design.state'), 'draft');
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
        const workarea = snapshot && records(snapshot).find(record => record.owner === 'workarea' && record.file === snapshot.rootFile)?.record;
        const rootMethod = str(workarea?.method, 'ddn'), foreign = workarea?.allow_foreign_views ?? rootMethod === 'ddn';
        const allowed = array(workarea?.allowed_profiles);
        const names = { MT01: 'ddn', MT02: 'uml', MT03: 'chen', MT04: 'flowchart', MT05: 'bpmn', MT06: 'cmmn', MT07: 'dmn', MT08: 'c4', MT09: 'dfd', MT10: 'sysml', MT11: 'archimate', MT12: 'epc', MT13: 'idef0', MT14: 'petri', MT15: 'orm', MT16: 'vsm', MT17: 'sdl', MT18: 'msc', MT19: 'soaml', MT20: 'uaf', MT21: 'electrical' };
        return (profileLoadingHost(handle.runtime)?.profiles ?? registrations(handle.runtime.registry).profiles ?? []).filter(profile => (foreign || names[profile.method] === rootMethod) && (!allowed.length || allowed.includes(profile.id)));
    }
    function viewCanChooseType(view) {
        const decoded = runtimeState(handle.runtime).decoded, node = decoded && findNode(decoded, view.ref);
        return !!node && !node.generated && !node.implicit && view.record.kind !== 'document'
            && getProfile(str(view.record.profile))?.projection === 'graph' && view.record.profile !== 'table.records@1'
            && !array(pathValue(view.record, 'selection.include')).length
            && !handle.scene()?.entries.some(entry => entry.definition.owner !== 'view' && refKey(entry.view.ref) === refKey(view.ref))
            && node.children.every(child => child.implicit || child.kind === 'with');
    }
    async function activateView(view) {
        await viewer.navigate({ kind: 'focus', target: view.ref });
        const frame = handle.scene()?.entries.find(entry => entry.definition.owner === 'view' && refKey(entry.view.ref) === refKey(view.ref));
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
        const state = runtimeState(handle.runtime), source = state.source, decoded = state.decoded;
        if (!source || !decoded)
            throw Error('Editable sources are unavailable.');
        const snapshot = handle.runtime.snapshot();
        if (!snapshot)
            throw Error('Open a document before creating a view.');
        await apply({ kind: 'edit-source', patches: appendDeclaration(decoded, snapshot.rootFile, diagramHeader(name, profile) + '\n' + viewLayoutSource(layout)) });
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
        const names = new Set(records(snapshot).map(record => record.record.name));
        while (names.has(initialName))
            initialName = 'NewView' + index++;
        const chooseLayout = () => viewLayoutDialog(handle.overlays, { selected: layout, onContinue(preset) { layout = preset; chooseProfile(); } });
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
                summary.textContent = 'View layout: ' + getViewSurfacePreset(layout).label;
                body.append(summary);
                const type = viewTypePicker(body, profiles, chooseType ? 'Diagram type' : 'View profile');
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
            // An existing, deliberately empty workarea only needs its first view.
            if (sources?.files.some(file => file.text.trim())) {
                addView(true);
                return;
            }
            newDiagramDialog(viewer, async (text) => {
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
            const type = viewTypePicker(body, profiles, 'Diagram type', str(view.record.profile));
            const settings = viewTypeSettings(body, type, applyButton);
            const note = document.createElement('p');
            note.className = 'ddn-appearance-message';
            note.textContent = `Set the diagram type for "${titleOf(view.record)}". Explicit appearance settings are retained; omitted values use the chosen type’s defaults.`;
            settings.append(note);
            return async () => {
                if (!allowedViewProfiles().some(profile => profile.id === type.value))
                    throw Error('Choose an available diagram type.');
                const state = runtimeState(handle.runtime), original = state.source;
                if (!original || !state.decoded || !viewCanChooseType(view))
                    throw Error('This view is no longer empty and editable.');
                let source = original, decoded = state.decoded;
                // Header identity controls the profile/recipe. Remove overrides
                // of just those fields, retaining all other authored settings.
                for (const path of ['profile', 'subtype']) {
                    const removals = patchProperty(decoded, view.ref, path, undefined).map(patch => {
                        const file = source.files.find(file => file.id === patch.file);
                        const comments = file.text.slice(patch.start, patch.end).split(/(?<=\n)/).filter(line => line.trimStart().startsWith('//')).join('');
                        return { ...patch, text: comments };
                    });
                    source = applySourcePatches(source, removals);
                    decoded = decodeSources(source, { previous: decoded });
                }
                const node = findNode(decoded, view.ref), file = source.files.find(file => file.id === view.ref.file);
                const documentSource = decoded.documents.find(document => document.file.id === view.ref.file);
                if (!node || !file || !documentSource)
                    throw Error('View source is unavailable.');
                const title = node.titleStart !== undefined && typeof view.record.title === 'string' ? view.record.title : undefined;
                const header = (node.start === 0 && documentSource.bom ? '\ufeff' : '') + ' '.repeat(node.indent) + diagramHeader(str(view.record.name), type.value, title) + documentSource.newline;
                source = applySourcePatches(source, [{ file: file.id, base: file.revision, start: node.start, end: node.headerEnd, text: header }]);
                const patches = source.files.flatMap(file => {
                    const before = original.files.find(candidate => candidate.id === file.id);
                    return file.text === before.text ? [] : [{ file: file.id, base: before.revision, start: 0, end: before.text.length, text: file.text }];
                });
                if (patches.length)
                    await apply({ kind: 'edit-source', patches });
                const configured = handle.scene()?.views.find(candidate => refKey(candidate.ref) === refKey(view.ref));
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
    function closePaletteDock() { paletteDrag = undefined; drawerFor(handle.container, 'palette')?.destroy(); paletteDock?.remove(); paletteDock = undefined; renderPalette = undefined; handle.container.removeAttribute('data-ddn-dock-left'); buttons['Add element']?.setAttribute('aria-pressed', 'false'); cancelPlacing(); }
    function currentView() { const activeView = handle.viewport().activeView; return (activeView ? handle.scene()?.views.find(v => refKey(v.ref) === refKey(activeView)) : undefined) ?? selected()?.view ?? handle.scene()?.views[0]; }
    function roleLabel(role, category = 'element') { const descriptor = roleDescriptor(role, category); return str(descriptor?.render?.text_label) || role.replace(/[._]/g, ' '); }
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
            const drawer = drawerFor(handle.container, 'palette');
            if (drawer?.mode === 'hidden')
                drawer.setMode('docked');
            drawer?.detached?.focus();
            paletteDock.querySelector('input')?.focus();
            return;
        }
        const profile = getProfile(str(view.record.profile));
        const dataBound = !!profile && (profile.projection !== 'graph' || view.record.profile === 'table.records@1');
        const roles = profile && !dataBound ? [...profile.primary_palette] : [];
        const dock = reuse ?? document.createElement('section');
        dock.replaceChildren();
        dock.className = 'ddn-designer-dock ddn-designer-dock-left';
        dock.setAttribute('aria-label', 'Element palette');
        const head = document.createElement('div');
        head.className = 'ddn-dock-head';
        head.append(uiIcon(document, 'grid'), document.createTextNode(dataBound ? 'View data' : 'Add element'));
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
        searchWrap.append(uiIcon(document, 'search'), search);
        const sections = document.createElement('div');
        sections.className = 'ddn-panel-sections';
        const list = document.createElement('div');
        list.className = 'ddn-panel-section';
        const allGroups = [...new Set(roles.map(paletteGroup))].sort((a, b) => (paletteGroupOrder.indexOf(a) < 0 ? paletteGroupOrder.length : paletteGroupOrder.indexOf(a)) - (paletteGroupOrder.indexOf(b) < 0 ? paletteGroupOrder.length : paletteGroupOrder.indexOf(b)));
        if (!['All elements', 'Recently used', ...allGroups].includes(paletteSection))
            paletteSection = 'All elements';
        const tabs = sideTabs(sections, 'Element types', [{ id: 'All elements', label: 'All elements', icon: 'grid', count: roles.length }, ...allGroups.map(group => ({ id: group, label: group, count: roles.filter(role => paletteGroup(role) === group).length, icon: group === 'SQL objects' ? 'table' : group === 'File types' ? 'folder' : group === 'Cluster objects' ? 'layers' : 'grid' }))], paletteSection, id => { paletteSection = id; render(); tabs.label(list); });
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
            item.append(elementPreview(document, role, str(view.record.profile)), name, id);
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
            item.addEventListener('click', () => { startPlacing(role, view); for (const other of list.querySelectorAll('button'))
                other.setAttribute('aria-pressed', String(other === item)); });
            item.addEventListener('dblclick', () => { cancelPlacing(); run(() => createElementAt(view, role, visibleCentre(view))); });
            return item;
        };
        const render = () => {
            const q = search.value.trim().toLowerCase();
            paletteSearchValue = search.value;
            list.replaceChildren();
            if (dataBound)
                return;
            const matches = roles.filter(role => (q || paletteSection === 'All elements' || paletteGroup(role) === paletteSection) && (!q || role.includes(q) || roleLabel(role).toLowerCase().includes(q)));
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
                const group = paletteGroup(role);
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
        search.addEventListener('keydown', event => { if (event.key === 'Escape') {
            event.stopPropagation();
            if (search.value) {
                search.value = '';
                render();
            }
            else
                drawerFor(handle.container, 'palette')?.setMode('hidden');
        } });
        render();
        paletteDock = dock;
        paletteDock.dataset.viewKey = refKey(view.ref) + ':' + str(view.record.profile);
        if (!reuse)
            handle.container.append(dock);
        const existingDrawer = drawerFor(handle.container, 'palette');
        if (existingDrawer)
            existingDrawer.setHeader(head);
        else
            createDrawer(dock, { id: 'palette', title: 'Element palette', container: handle.container, header: head, closeLabel: 'Close the palette', width: 400,
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
        if (paletteDock.dataset.viewKey === refKey(view.ref) + ':' + str(view.record.profile))
            return;
        const owner = paletteDock.ownerDocument, activeDocument = owner.hasFocus() ? owner : document;
        const previousFocus = activeDocument.activeElement;
        const hadFocus = owner.hasFocus() && paletteDock.contains(previousFocus);
        cancelPlacing();
        // Keep the drawer and its window; only the profile-bound contents change.
        openPaletteDock(paletteDock);
        if (hadFocus)
            paletteDock.querySelector('input')?.focus();
        else if (previousFocus?.isConnected)
            previousFocus.focus({ preventScroll: true });
    }
    function visibleCentre(view) {
        const vb = handle.viewport(), visible = { x: vb.bounds.x, y: vb.bounds.y, width: vb.bounds.width / vb.zoom, height: vb.bounds.height / vb.zoom };
        const frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && refKey(e.definition.ref) === refKey(view.ref));
        const fb = frame ? semanticBounds(frame) : undefined;
        const cx = visible.x + visible.width / 2, cy = visible.y + visible.height / 2;
        if (!fb || (cx >= fb.x && cx <= fb.x + fb.width && cy >= fb.y && cy <= fb.y + fb.height))
            return { x: cx, y: cy };
        return { x: fb.x + fb.width / 2, y: fb.y + fb.height / 2 };
    }
    function startPlacing(role, view) {
        placing = { role, view };
        handle.container.classList.add('ddn-placing');
        handle.announce(`${roleLabel(role)}: click on the view where it should go. Esc cancels.`);
    }
    function cancelPlacing() {
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
        const profile = str(view.record.profile);
        const frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && refKey(e.definition.ref) === refKey(view.ref));
        const origin = frame ? semanticBounds(frame) : { x: 0, y: 0 };
        const local = logicalPoint(frame, point);
        const position = { x: Math.max(0, Math.round(local.x - origin.x)), y: Math.max(0, Math.round(local.y - origin.y)) };
        const before = new Set((handle.scene()?.entries ?? []).map(e => e.item.occurrence));
        // Creation and placement share one authorized command and one undo entry.
        const receipt = await apply({ kind: 'profile-command', profile, command: 'ddn.create-element', target: view.ref, arguments: jsonValue({ view: view.ref, role, position }) });
        recentRoles = [role, ...recentRoles.filter(r => r !== role)].slice(0, 6);
        renderPalette?.();
        const changed = new Set(receipt.changed.map(refKey));
        const created = handle.scene()?.entries.find(e => refKey(e.view.ref) === refKey(view.ref) && e.definition.owner === 'definition' && !before.has(e.item.occurrence) && changed.has(refKey(e.definition.ref)));
        if (created) {
            handle.select(created.definition.ref, created.item.occurrence);
            inlineRename(created, true);
        }
        else
            handle.announce(`${roleLabel(role)} added.`);
        return created;
    }
    async function reflowView(view = currentView()) {
        if (!view || getProfile(str(view.record.profile))?.projection !== 'graph')
            throw Error('Choose a diagram view to reflow.');
        if (!writable(view.ref))
            throw Error('This view belongs to a read-only file.');
        cancelPlacing();
        const frame = handle.scene()?.entries.find(entry => entry.definition.owner === 'view' && refKey(entry.definition.ref) === refKey(view.ref));
        const patches = reflowViewPatches(handle.runtime, view.ref, str(pathValue(frame?.effective, 'layout.algorithm')) || undefined);
        if (patches.length)
            await apply({ kind: 'edit-source', patches });
        else
            await handle.refresh();
        handle.announce(`Reflowed ${titleOf(view.record)} using its diagram layout.${patches.length ? ' Fixed positions have been released. Undo restores the previous layout.' : ''}`);
    }
    function reuseItem() {
        const snapshot = handle.runtime.snapshot(), view = currentView();
        if (!snapshot || !view)
            return;
        const profile = getProfile(str(view.record.profile));
        if (!profile)
            return;
        const eligible = new Set([...profile.primary_palette, ...profile.context_roles, ...profile.relation_roles]);
        const candidates = records(snapshot).filter(record => record.owner === 'definition' && eligible.has(str(record.record.role)));
        panel('Reuse an existing item', body => {
            const select = document.createElement('select');
            select.setAttribute('aria-label', 'Shared item');
            candidates.forEach((record, index) => { const option = document.createElement('option'); option.value = String(index); option.textContent = `${titleOf(record.record)} (${str(record.record.role)}, ${record.file})`; select.append(option); });
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
        const workarea = records(snapshot).find(record => record.owner === 'workarea' && record.file === snapshot.rootFile);
        if (!workarea)
            return;
        const references = records(snapshot).map(record => ({ ref: record.ref, label: `${titleOf(record.record)} (${record.owner})` }));
        panel('Workarea settings', body => {
            const choice = document.createElement('select');
            choice.setAttribute('aria-label', 'Workarea property');
            choice.dataset.ddnLiveIgnore = '';
            for (const key of ['background', 'grid', 'viewport', 'method', 'allowed_profiles', 'allow_foreign_views', 'style', 'size'])
                if (childSchema(codex.roots.workarea, key) !== undefined) {
                    const option = document.createElement('option');
                    option.value = key;
                    option.textContent = key;
                    choice.append(option);
                }
            const controls = document.createElement('div');
            body.append(choice, controls);
            let editor = createFieldEditor(controls, childSchema(codex.roots.workarea, choice.value), jsonValue(workarea.record[choice.value]), references, 'Workarea.' + choice.value);
            let section = choice.value;
            choice.addEventListener('change', event => {
                event.stopPropagation();
                const next = choice.value;
                choice.value = section;
                run(async () => { await flushLiveSettings(body); section = next; choice.value = next; controls.replaceChildren(); const current = records(handle.runtime.snapshot()).find(record => refKey(record.ref) === refKey(workarea.ref)); editor = createFieldEditor(controls, childSchema(codex.roots.workarea, section), jsonValue(current?.record[section]), references, 'Workarea.' + section); });
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
        const profile = str(view.record.profile);
        const role = profile === 'mindmap.basic@1' || profile === 'concept.map@1' ? 'object' : profile === 'table.records@1' ? 'dataset' : profile === 'ddn@1' ? 'entity' : getProfile(profile)?.primary_palette[0];
        if (!role) {
            handle.announce('This view type has no element to add directly. Use its projection settings or dataset instead.');
            return;
        }
        run(() => createElementAt(view, role, visibleCentre(view)));
    }
    function isErdView(view = currentView()) { return !!view && str(view.record.profile) === 'ddn@1' && array(view.record.subtype).includes('erd'); }
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
        const current = str(entry.definition.record.title) || str(entry.definition.record.name);
        input.value = isNew && /^<.*>$/.test(current) ? '' : current;
        input.placeholder = isNew ? roleLabel(str(entry.definition.record.role, 'element')) : 'Name';
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
        if (mindmapSelection(handle, entry)) {
            deleteTopic(entry);
            return;
        }
        const snapshot = handle.runtime.snapshot(), all = snapshot ? records(snapshot) : [];
        const key = refKey(entry.definition.ref);
        const isRelation = entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints);
        const connections = all.filter(record => record.owner === 'definition' && Array.isArray(record.record.endpoints) && record.record.endpoints.some(end => {
            const target = resolveRecord(all, object(end).definition, record.file);
            return target && refKey(target.ref) === key;
        })).length;
        const name = titleOf(entry.definition.record);
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
            const input = field(body, 'Topic name', titleOf(entry.definition.record));
            return async () => {
                if (!input.value.trim())
                    throw Error('Enter a topic name.');
                const draft = mindmapSource(handle.runtime, entry.view.ref);
                if (findNode(draft.decoded, entry.definition.ref)?.generated)
                    draft.materialize();
                draft.set(entry.definition.ref, 'title', input.value);
                await commitMindmap(draft);
            };
        });
    }
    async function addTopic(entry, side) {
        const topology = mindmapSelection(handle, entry);
        if (!topology || !topology[side])
            throw Error('New topics must continue away from the incoming relationship.');
        const draft = mindmapSource(handle.runtime, entry.view.ref);
        draft.materialize();
        const name = draft.unique('New topic'), id = draft.unique('mindmap-topic'), relation = draft.unique('Branch');
        draft.append(entry.view.file, encodeDefinition({ id, name, role: 'object' }));
        draft.append(entry.view.file, `connect ${draft.reference(entry.definition.ref)} to ${quoteText(name)} as assoc named ${quoteText(relation)}`);
        draft.append(entry.view.file, `use ${quoteText(name)}\nuse ${quoteText(relation)}\n    with\n        route.source_side ${side === 'left' ? 'west' : 'east'}`, entry.view.ref);
        await commitMindmap(draft);
        const created = handle.scene()?.entries.find(item => item.definition.ref.id === id && item.definition.file === entry.view.file && refKey(item.view.ref) === refKey(entry.view.ref));
        if (created) {
            handle.select(created.definition.ref, created.item.occurrence);
            editTopicName(created);
        }
    }
    function topicNotes(entry) { notes(entry, true); }
    function deleteTopic(entry) {
        const topology = mindmapSelection(handle, entry);
        if (!topology)
            return;
        const descendants = new Set([refKey(entry.definition.ref)]);
        for (let changed = true; changed;) {
            changed = false;
            for (const link of topology.internal)
                if (descendants.has(refKey(link.from.ref)) && !descendants.has(refKey(link.to.ref))) {
                    descendants.add(refKey(link.to.ref));
                    changed = true;
                }
        }
        panel('Delete topic', body => {
            const message = document.createElement('p');
            message.textContent = `Delete ${titleOf(entry.definition.record)} from every view where it is used, together with its linked relationships?`;
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
                const draft = mindmapSource(handle.runtime, entry.view.ref);
                draft.materialize();
                const removed = new Set(cascade.checked ? descendants : [refKey(entry.definition.ref)]), all = listRecords(draft.decoded.normalized);
                const mentions = (value, file) => { const target = resolveReference(draft.decoded.normalized, file, value); return !!target && removed.has(refKey(target.ref)); };
                for (const item of all)
                    if (item.kind === 'definition' && item.record.category === 'relation' && asArray(item.record.endpoints).some(end => mentions(asRecord(end).definition, item.file)))
                        removed.add(refKey(item.ref));
                for (const item of all)
                    if (item.kind === 'appearance' && mentions(item.record.target, item.file))
                        removed.add(refKey(item.ref));
                for (const item of all.filter(item => item.kind === 'view')) {
                    for (const path of ['selection.include', 'selection.items', 'sources']) {
                        const value = pathValue(item.record, path);
                        if (Array.isArray(value) && value.some(ref => mentions(jsonValue(ref), item.file)))
                            draft.set(item.ref, path, value.filter(ref => !mentions(jsonValue(ref), item.file)));
                    }
                    if (mentions(asRecord(item.record.layout).root, item.file))
                        draft.set(item.ref, 'layout.root', undefined);
                }
                const targets = all.filter(item => removed.has(refKey(item.ref))).sort((a, b) => Number(b.kind === 'appearance') - Number(a.kind === 'appearance'));
                for (const item of targets) {
                    const node = findNode(draft.decoded, item.ref);
                    if (!node || node.implicit)
                        continue;
                    const hidden = listRecords(draft.decoded.normalized).find(other => {
                        if (removed.has(refKey(other.ref)) || other.kind === 'note' || other.file !== item.file)
                            return false;
                        const nested = findNode(draft.decoded, other.ref);
                        return !!nested && nested.start >= node.start && nested.end <= node.end;
                    });
                    if (hidden)
                        throw Error('This source block contains other topics or a view that were not selected for deletion. Delete from its owning mind map or move those topics first.');
                }
                for (const item of targets) {
                    const node = findNode(draft.decoded, item.ref);
                    if (node && !node.implicit)
                        draft.apply(deleteDeclaration(draft.decoded, item.ref));
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
    const tooltips = { 'Add element': 'Open the element palette — click a type, then click where it goes (A)', 'Add existing element': 'Show an element that already exists in another view here', 'Connect': 'Connect two elements: click the first, then the second — or drag from a selected element\'s handle (C)', 'Add view': 'Add another view (diagram) to this document', 'Add entity': 'Add an ERD entity to this view (ERD views only)', 'Workarea': 'Workarea settings — background, grid, allowed diagram types', 'Rename': 'Rename the selected element (F2, or double-click it)', 'Properties': 'Open the inspector for the selected element — name, description, colours, lock (P)', 'Draft': 'Free-form text inside the element', 'Columns': 'Turn the draft text into fields', 'Table': 'Edit the element\'s table rows', 'Details': 'Choose which details (columns) are shown', 'Paper & attachments': 'Paper surface, shadow, pins and tape for the selected element', 'Symbol & label': 'How the element is drawn: card, image symbol or bare text, and where its name sits', 'Appearance & presets': 'Colours, fonts, textures and saved presets', 'Profile details': 'Notation-specific details for this element', 'Projection': 'How this data-bound view is projected (chart, matrix, …)', 'Datasets': 'Datasets that feed data-bound views', 'Status': 'Design status: in progress, in review, accepted', 'Source': 'Edit the DDN source of a file in a dialog', 'Delete': 'Delete the selected element (Delete key)', 'Undo': 'Undo (Ctrl+Z)', 'Redo': 'Redo (Ctrl+Shift+Z)' };
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
        handle.announce(`Connect from "${titleOf(selected().definition.record)}" — now click the target element. Esc cancels.`);
        updateToolbar();
    });
    add('Add view', () => addView());
    add('Add entity', newElement);
    add('Workarea', workareaSettings);
    add('Reflow', () => run(() => reflowView()));
    add('Rename', guarded(() => inlineRename()));
    add('Properties', guarded(() => openInspectorDock()));
    add('Draft', guarded(() => editDraft()));
    add('Columns', guarded(() => convert()));
    add('Table', guarded(() => editRows()));
    add('Details', guarded(() => details()));
    add('Paper & attachments', guarded(() => paperAttachments()));
    add('Symbol & label', guarded(() => openSymbol(viewer, panel, applyProperties)));
    add('Appearance & presets', guarded(() => openAppearance(viewer, panel, applyProperties)));
    add('Profile details', guarded(() => profileEditor()));
    add('Projection', guarded(() => profileEditor(true)));
    add('Status', guarded(() => statusDialog()));
    add('Delete', guarded(() => deleteItem()));
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
    // Row 1: create · document · history. Row 2: the selection's own actions.
    for (const name of ['Document', 'History', 'Selection'])
        if (toolbarGroups.get(name))
            toolbar.append(toolbarGroups.get(name));
    const moreLabels = ['Draft', 'Columns', 'Table', 'Details', 'Profile details', 'Status'];
    const moreButton = document.createElement('button');
    moreButton.type = 'button';
    moreButton.append(document.createTextNode('More'), uiIcon(document, 'chevron'));
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
        const profile = view ? getProfile(str(view.record.profile)) : undefined;
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
        selectionName.textContent = entry ? (isRelation ? 'Connection: ' : isView ? 'View: ' : '') + titleOf(entry.definition.record) : 'Click an element to edit it — or right-click it';
        const elementOnly = ['Draft', 'Columns', 'Table', 'Details', 'Symbol & label', 'Paper & attachments', 'Profile details'];
        for (const label of elementOnly)
            has(label).hidden = !entry || isRelation || isView;
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
        has('Connect').replaceChildren(uiIcon(document, 'link'), document.createTextNode(connectFrom ? 'Click the target…' : connectArmed ? 'Click the first element…' : 'Connect'));
        // The public command service does not expose stack availability.
        has('Undo').disabled = false;
        has('Redo').disabled = false;
        updatePortHandles();
        notifyUICommands(handle.container);
    }
    cleanups.push(viewer.subscribe(event => { if (event.kind === 'ready' || event.kind === 'viewport' || event.kind === 'selection') {
        updateToolbar();
        refreshPaletteForView();
        if (inspectorDock && event.kind === 'ready')
            renderInspector();
    } }));
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
    // ---- Inspector dock: the common properties of the selection on one panel ----
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
        const drawer = drawerFor(handle.container, 'inspector');
        if (drawer?.mode === 'hidden')
            drawer.setMode('docked');
        drawer?.detached?.focus();
        renderInspector();
    }
    function closeInspectorDock() { inspectorLive?.dispose(); inspectorLive = undefined; inspectorToken++; drawerFor(handle.container, 'inspector')?.destroy(); inspectorDock?.remove(); inspectorDock = undefined; handle.container.removeAttribute('data-ddn-dock-right'); }
    async function renderInspector() {
        if (!inspectorDock)
            return;
        const entry = selected();
        const entryKey = entry ? refKey(entry.definition.ref) + '::' + refKey(entry.view.ref) + '::' + entry.item.occurrence : '';
        if (inspectorApplying && inspectorEntryKey === entryKey)
            return;
        inspectorLive?.dispose();
        inspectorLive = undefined;
        inspectorEntryKey = entryKey;
        const token = ++inspectorToken;
        const pendingEdits = new Map();
        const edit = (key, action) => { if (token !== inspectorToken)
            return; pendingEdits.set(key, action); inspectorLive?.request(); };
        const dock = inspectorDock;
        dock.replaceChildren();
        const head = document.createElement('div');
        head.className = 'ddn-dock-head';
        head.append(uiIcon(document, 'settings'), document.createTextNode('Inspector'));
        const body = document.createElement('div');
        body.className = 'ddn-dock-body';
        const sectionLayout = document.createElement('div');
        sectionLayout.className = 'ddn-panel-sections';
        const content = document.createElement('div');
        content.className = 'ddn-panel-section';
        const tabs = sideTabs(sectionLayout, 'Inspector sections', [{ id: 'all', label: 'All settings', icon: 'settings' }, { id: 'identity', label: 'Identity', icon: 'type' }, { id: 'appearance', label: 'Appearance', icon: 'palette' }, { id: 'actions', label: 'Actions', icon: 'layers' }], inspectorSection, id => { inspectorSection = id; filterSections(); });
        tabs.connect(content);
        sectionLayout.append(content);
        body.append(sectionLayout);
        dock.append(head, body);
        let drawer = drawerFor(handle.container, 'inspector');
        if (drawer)
            drawer.setHeader(head);
        else
            drawer = createDrawer(dock, { id: 'inspector', title: 'Inspector', container: handle.container, header: head, side: 'right', closeLabel: 'Close the inspector', width: 420,
                onMode(mode) { handle.container.toggleAttribute('data-ddn-dock-right', mode === 'docked'); },
                onHide() { void inspectorLive?.flush().catch(notifyError); },
                onBlocked() { handle.announce('The browser blocked the new window. The inspector floats here; allow pop-ups to move it to another monitor.'); } });
        function filterSections() { for (const child of content.children) {
            const section = child;
            section.hidden = inspectorSection !== 'all' && section.dataset.inspectorSection !== inspectorSection;
        } tabs.label(content); }
        if (!entry) {
            const empty = document.createElement('p');
            empty.className = 'ddn-dock-help';
            empty.textContent = 'Select an element, connection or view to see and change its properties here.';
            content.append(empty);
            return;
        }
        const isRelation = entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints);
        const isView = entry.definition.owner === 'view';
        const role = str(entry.definition.record.role);
        const descriptor = role ? roleDescriptor(role, isRelation ? 'relation' : 'element') : undefined;
        const kind = document.createElement('div');
        kind.className = 'ddn-dock-kind';
        const swatch = document.createElement('span');
        swatch.className = 'ddn-dock-swatch';
        swatch.style.background = str(descriptor?.render?.fill, str(descriptor?.render?.colour, 'transparent'));
        swatch.style.borderColor = str(descriptor?.render?.colour, '');
        const kindText = document.createElement('span');
        kindText.textContent = isView ? 'View · ' + profileDisplayName(str(entry.definition.record.profile, 'ddn@1')) : role ? roleLabel(role, isRelation ? 'relation' : 'element') : 'Element';
        const kindId = document.createElement('small');
        kindId.textContent = role ? ` ${role}` : '';
        kind.append(swatch, kindText, kindId);
        content.append(kind);
        if (!isRelation && !isView) {
            const state = str(pathValue(entry.definition.record, 'design.state'), 'draft');
            const statusLine = document.createElement('p');
            statusLine.className = 'ddn-dock-help';
            statusLine.textContent = 'Design status: ' + ({ draft: 'draft — the amber dot on the element', 'in-progress': 'in progress — the blue dot on the element', 'in-review': 'in review — the purple dot on the element', accepted: 'accepted — the green dot on the element' }[state] ?? state) + '. Change it under Design status… below.';
            content.append(statusLine);
        }
        const fieldFor = (label, value, multiline = false) => { const wrap = document.createElement('label'); wrap.append(document.createTextNode(label)); const input = document.createElement(multiline ? 'textarea' : 'input'); input.value = value ?? ''; wrap.append(input); content.append(wrap); return input; };
        const name = fieldFor(isRelation ? 'Label' : 'Name', str(entry.definition.record.title) || str(entry.definition.record.name));
        name.disabled = !writable(entry.definition.ref);
        name.addEventListener('input', () => { const value = name.value.trim(); edit('title', () => renameTitle(entry, value)); });
        name.addEventListener('keydown', event => { if (event.key === 'Enter') {
            event.preventDefault();
            name.blur();
        } });
        if (isRelation) {
            const snapshot = handle.runtime.snapshot(), all = snapshot ? records(snapshot) : [];
            const ends = array(entry.definition.record.endpoints).map(end => { const record = resolveRecord(all, object(end).definition, entry.definition.file); return record ? titleOf(record.record) : '?'; });
            const info = document.createElement('p');
            info.className = 'ddn-dock-help';
            info.textContent = ends.length ? `${ends[0]} → ${ends.slice(1).join(', ')}` : '';
            content.append(info);
        }
        const description = fieldFor('Description', str(entry.definition.record.description), true);
        description.disabled = !explicitEditable(entry.definition.ref);
        description.addEventListener('input', () => { const value = description.value; edit('description', () => set(entry.definition.ref, 'description', value)); });
        const identityChildren = [...content.children];
        // Appearance quick settings with an explained scope.
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
                }).catch(error => { if (token === inspectorToken && dock.isConnected) {
                    scope.value = String(chosenScope);
                    scopeLoading = false;
                    row.inert = false;
                    scope.disabled = false;
                    notifyError(error);
                } });
            });
            const row = document.createElement('div');
            row.className = 'ddn-dock-row';
            content.append(row);
            const colour = (label, path) => { const wrap = document.createElement('label'); wrap.append(document.createTextNode(label)); const input = document.createElement('input'); input.type = 'color'; wrap.append(input); row.append(wrap); input.addEventListener('input', () => { if (scopeLoading)
                return; const target = scopes[chosenScope].ref, value = input.value; edit(path, () => applyProperties(target, { [path]: value })); }); return input; };
            const background = colour('Background', 'background.color'), text = colour('Text', 'text.color');
            const size = numberField(row, 'Font size (pt)', 12, { min: 6, max: 48, step: .5 });
            size.step = 'any';
            size.addEventListener('input', () => { if (scopeLoading)
                return; const value = size.valueAsNumber * 4 / 3, target = scopes[chosenScope].ref; if (size.checkValidity() && Number.isFinite(value))
                edit('style.font_size', () => applyProperties(target, { 'style.font_size': value })); });
            const opacity = numberField(row, 'Opacity (0–1)', 1, { min: 0, max: 1, step: .01 });
            opacity.step = 'any';
            opacity.addEventListener('input', () => { if (scopeLoading)
                return; const value = opacity.valueAsNumber, target = scopes[chosenScope].ref; if (opacity.checkValidity() && Number.isFinite(value))
                edit('opacity', () => applyProperties(target, { opacity: value })); });
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
                    syncNumberField(size);
                    const alpha = get('opacity');
                    opacity.value = typeof alpha === 'number' ? String(alpha) : '1';
                    syncNumberField(opacity);
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
        const action = (label, fn, danger = false) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = label; if (danger)
            b.dataset.danger = ''; b.addEventListener('click', () => run(async () => { const live = inspectorLive; await live?.flush(); if (token === inspectorToken && dock.isConnected)
            guarded(fn)(); })); actions.append(b); };
        action('All properties…', () => properties());
        action('Appearance & presets…', () => openAppearance(viewer, panel, applyProperties));
        if (!isRelation) {
            action('Paper & attachments…', () => paperAttachments());
            action('Design status…', () => statusDialog());
        }
        if (!isRelation && !isView) {
            action('Symbol & label…', () => openSymbol(viewer, panel, applyProperties));
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
        inspectorLive = createLiveSettings({ body, commands, async submit() { const jobs = [...pendingEdits.values()]; pendingEdits.clear(); for (const action of jobs) {
                if (token !== inspectorToken)
                    return;
                await inspectorLive.group.run(action);
            } }, showError(failure) { error.textContent = failure instanceof Error ? failure.message : failure ? String(failure) : ''; }, onState(state) { if (token === inspectorToken)
                inspectorApplying = state.busy; } });
    }
    // ---- Port handles: drag from a selected element to connect it ----
    let portGroup, connectDrag;
    function updatePortHandles() {
        portGroup?.remove();
        portGroup = undefined;
        const entry = selected();
        if (!entry || entry.definition.owner === 'view' || entry.definition.record.category === 'relation' || Array.isArray(entry.definition.record.endpoints) || mindmapSelection(handle, entry) || !writable(entry.view.ref) || !canMove(entry))
            return;
        const view = entry.view, profile = getProfile(str(view.record.profile));
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
                // Bubble so the viewer tracks this pointer and a second touch can start a pinch.
                event.preventDefault();
                const line = document.createElementNS(NS, 'path');
                line.setAttribute('class', 'ddn-connect-line');
                handle.surface.append(line);
                connectDrag = { id: event.pointerId, from: entry, start: { x: px, y: py }, line, revision: JSON.stringify(handle.runtime.snapshot()?.revision) };
                try {
                    handle.surface.setPointerCapture(event.pointerId);
                }
                catch { /* synthetic pointers have no capture */ }
                handle.announce(`Drag to the element "${titleOf(entry.definition.record)}" should connect to, then release.`);
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
        if (!entry || entry.definition.owner === 'view' || entry.definition.record.category === 'relation' || entry.item.occurrence === current.from.item.occurrence || refKey(entry.view.ref) !== refKey(current.from.view.ref)) {
            handle.announce('Release the handle on another element to connect them.');
            return;
        }
        openVerbChooser(current.from.definition.ref, entry.definition.ref, current.from.view);
    };
    on(handle.surface, 'pointerup', event => finishConnectDrag(event, true));
    on(handle.surface, 'pointercancel', event => finishConnectDrag(event, false));
    const commonVerbs = ['assoc', 'flow', 'depends', 'uses', 'calls', 'publish', 'subscribe', 'contains', 'reads', 'writes', 'implements', 'extends', 'owns', 'ref', 'generates', 'delivers', 'triggers', 'queries', 'import', 'export'];
    function openVerbChooser(from, to, view) {
        const inView = handle.scene()?.entries.filter(entry => refKey(entry.view.ref) === refKey(view.ref)) ?? [];
        if (![from, to].every(ref => inView.some(entry => refKey(entry.definition.ref) === refKey(ref)))) {
            handle.announce('Choose two elements in the same view.');
            return;
        }
        const profile = getProfile(str(view.record.profile));
        const all = handle.runtime.snapshot() ? records(handle.runtime.snapshot()) : [];
        const fromRecord = all.find(record => refKey(record.ref) === refKey(from)), toRecord = all.find(record => refKey(record.ref) === refKey(to));
        const fromRole = str(fromRecord?.record.role), toRole = str(toRecord?.record.role);
        const fromName = fromRecord ? titleOf(fromRecord.record) : 'A', toName = toRecord ? titleOf(toRecord.record) : 'B';
        const topicKeys = new Set((mindmapSelection(handle)?.topics ?? []).map(item => refKey(item.definition.ref)));
        const internalMindmap = view.record.profile === 'mindmap.basic@1' && topicKeys.has(refKey(from)) && topicKeys.has(refKey(to));
        const legal = new Set(profile?.relation_endpoint_contracts.filter(contract => (!internalMindmap || contract.role === 'assoc') && contract.source_roles.includes(fromRole) && contract.target_roles.includes(toRole) && (refKey(from) !== refKey(to) || contract.self_allowed)).map(contract => contract.role));
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
            queueMicrotask(() => { const applyButton = body.closest('.ddn-ui-dialog')?.querySelector('[data-ddn-apply]'); if (applyButton)
                applyButton.textContent = 'Connect'; });
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
        return !entry || refKey(entry.view.ref) === refKey(paletteDrag.view.ref);
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
    on(handle.surface, 'click', event => {
        if (!placing)
            return;
        if (event.target.closest('.ddn-ports') || event.target.closest('.ddn-inline-rename'))
            return;
        const role = placing.role, view = placing.view;
        const point = handle.toWorld(event.clientX, event.clientY);
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
            handle.announce(`Connect from "${titleOf(selected()?.definition.record ?? {})}" — now click the target element. Esc cancels.`);
            updateToolbar();
            return;
        }
        if (connectFrom && ref && connectable && refKey(connectFrom) !== refKey(ref)) {
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
        const sourceNode = targetRef && runtimeState(handle.runtime).decoded && findNode(runtimeState(handle.runtime).decoded, targetRef);
        const editableRelation = !!entry && (targetRef ? !!sourceNode && !sourceNode.generated && writable(targetRef)
            : explicitEditable(entry.view.ref) && (!!entry.definition.record.name || explicitEditable(entry.definition.ref)));
        const toggles = isRelation ? relationMenuItems(entry, handle.scene()?.entries.find(e => e.definition.owner === 'view' && refKey(e.definition.ref) === refKey(entry.view.ref))?.effective ?? entry.view.record, editableRelation, (path, value) => run(async () => {
            requireCurrent(expected);
            if (targetRef)
                await applyProperties(targetRef, { [path]: value });
            else
                await apply({ kind: 'create-occurrence', view: entry.view.ref, target: entry.definition.ref, properties: { [path]: value } });
        })) : [];
        const items = !entry ? [['Add element…', () => openPaletteDock()], ['Add existing element…', () => reuseItem()], ['Add view…', () => addView()], ['Fit all', () => void viewer.navigate({ kind: 'fit-workarea' })]]
            : isView ? [['Rename', () => inlineRename()], ['Properties', () => openInspectorDock()], ['Appearance & presets', () => openAppearance(viewer, panel, applyProperties)], ['Expand view', () => void viewer.navigate({ kind: 'expand-view', target: entry.definition.ref })]]
                : isRelation ? [...toggles, ['Rename label', () => inlineRename()], ['Properties', () => openInspectorDock()], ['Appearance & presets', () => openAppearance(viewer, panel, applyProperties)], ['Delete', () => deleteItem()]]
                    : [['Rename', () => inlineRename()], ['Connect from here', () => { connectFrom = entry.definition.ref; updateToolbar(); handle.announce(`Connect from "${titleOf(entry.definition.record)}" — click the target element.`); }], ['Properties', () => openInspectorDock()], ['Appearance & presets', () => openAppearance(viewer, panel, applyProperties)], ['Symbol & label', () => openSymbol(viewer, panel, applyProperties)], ['Paper & attachments', () => paperAttachments()], ['Draft text', () => editDraft()], ['Columns', () => convert()], ['Details shown', () => details()], ['Edit table', () => editRows()], ['Comments', () => notes()], ['Constraints', () => constraints()], ['Status', () => statusDialog()], ['Delete', () => deleteItem()]];
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
    on(handle.overlays, 'pointerdown', event => { if (menu && !menu.contains(event.target)) {
        menu.remove();
        menu = undefined;
    } });
    on(handle.surface, 'pointerdown', event => { if (menu && !menu.contains(event.target)) {
        menu.remove();
        menu = undefined;
    } });
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
        if (pinching || event.button !== 0 || placing || connectDrag || event.target.closest('.ddn-element-resize') || (event.pointerType !== 'touch' && event.pointerType !== 'pen'))
            return;
        cancelPress();
        const { clientX, clientY } = event, target = event.target.closest('[data-ref]');
        pressOrigin = { x: clientX, y: clientY };
        longPress = setTimeout(() => { cancelPress(); finishGesture(false); openContextMenu(clientX, clientY, target); }, 550);
    });
    for (const type of ['pointerup', 'pointercancel', 'pointermove'])
        on(handle.surface, type, event => { if (type !== 'pointermove' || (pressOrigin && Math.hypot(event.clientX - pressOrigin.x, event.clientY - pressOrigin.y) > 5))
            cancelPress(); });
    // Single-key shortcuts also work when nothing in the diagram has focus (e.g. right after the page loads).
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
        if ((key.ctrlKey || key.metaKey) && key.key.toLowerCase() === 'z') {
            key.preventDefault();
            run(async () => {
                const result = await (key.shiftKey ? commands.redo() : commands.undo());
                if (!result.ok)
                    throw new Error(result.failure.code);
                await handle.refresh();
            });
        }
        if (key.key === 'Delete' && selected() && selected().definition.owner !== 'view') {
            key.preventDefault();
            guarded(() => deleteItem())();
        }
        if (['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(key.key)) {
            const entry = selected();
            const movable = entry?.appearance ?? entry?.placement;
            if (!entry || !movable || !writable(movable.ref) || !canMove(entry) || geometryLocked(entry, 'move'))
                return;
            key.preventDefault();
            const position = object(movable.record.position);
            const bounds = semanticBounds(entry), frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && refKey(e.definition.ref) === refKey(entry.view.ref));
            const frameBounds = entry.appearance && frame ? semanticBounds(frame) : { x: 0, y: 0 };
            const local = entry.appearance ? logicalPoint(entry, bounds) : bounds;
            const snapping = snapStep(), amount = key.shiftKey && !snapping ? 1 : snapping || 16;
            const nextX = num(position.x, local.x - frameBounds.x) - Number(key.key === 'ArrowLeft') * amount + Number(key.key === 'ArrowRight') * amount, nextY = num(position.y, local.y - frameBounds.y) - Number(key.key === 'ArrowUp') * amount + Number(key.key === 'ArrowDown') * amount;
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
        const frame = handle.scene()?.entries.find(e => e.definition.owner === 'view' && refKey(e.definition.ref) === refKey(current.entry.view.ref));
        const frameBounds = current.entry.appearance && frame ? semanticBounds(frame) : { x: 0, y: 0 };
        const initial = semanticBounds(current.entry), position = object(movable.record.position);
        const scale = surfaceScale(current.entry), local = current.entry.appearance ? logicalPoint(current.entry, initial) : initial;
        // Retain authored coordinates when chrome/paper shifts the displayed
        // content origin. A drag is a delta, not a new page-space coordinate.
        run(() => current.resizing ? resizeElement(current.entry, width / scale, height / scale) : nativeCommand('ddn.set-position', movable.ref, { x: snap(num(position.x, local.x - frameBounds.x) + (x - initial.x) / scale), y: snap(num(position.y, local.y - frameBounds.y) + (y - initial.y) / scale) }));
    };
    /** Snap applies only while the host's View › Snap to grid is on; the step is the workarea grid. */
    function snapStep() { return viewSetting(handle.container, 'snap') === 'on' ? gridStep(handle.runtime.snapshot()) : 0; }
    function snap(value) { const step = snapStep(); return step ? Math.round(value / step) * step : value; }
    function beginGesture(entry, pointer, resizing) {
        handle.select(entry.definition.ref, entry.item.occurrence);
        const position = handle.toWorld(pointer.clientX, pointer.clientY);
        const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
        for (const [key, value] of Object.entries(semanticBounds(entry)))
            rect.setAttribute(key, String(value));
        rect.setAttribute('class', 'ddn-designer-preview');
        gesture = { id: pointer.pointerId, start: position, entry, rect, resizing, moved: false, revision: revision() };
        if (resizing && pointer.pointerType !== 'mouse')
            try {
                handle.surface.setPointerCapture(pointer.pointerId);
            }
            catch { /* Synthetic pointers have no capture. */ }
    }
    on(handle.surface, 'pointerdown', event => {
        const pointer = event;
        if (pointer.button !== 0 || pinching || placing || connectDrag || pointer.target.closest('.ddn-ports,.ddn-element-resize'))
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
            gesture.rect.setAttribute('width', String(Math.max(minimum, bounds.width + dx)));
            gesture.rect.setAttribute('height', String(Math.max(minimum, bounds.height + dy)));
        }
        else {
            gesture.rect.setAttribute('x', String(bounds.x + dx));
            gesture.rect.setAttribute('y', String(bounds.y + dy));
        }
    });
    on(handle.surface, 'pointerup', event => { if (gesture?.id === event.pointerId)
        finishGesture(true); });
    on(handle.surface, 'pointercancel', event => { if (gesture?.id === event.pointerId)
        finishGesture(false); });
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
    cleanups.push(mountResizeHandles(viewer, handle, { bounds: semanticBounds, allowed: canResize,
        start(entry, event) {
            if (event.button !== 0 || pinching || placing || connectDrag || gesture || connectArmed || connectFrom)
                return;
            event.preventDefault();
            cancelPress();
            beginGesture(entry, event, true);
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
    // ---- Clipboard: copies carry authored definitions, never identity or lifecycle ----
    const copyable = (entry = selected()) => !!entry && entry.definition.owner === 'definition' && entry.definition.record.category !== 'relation' && !Array.isArray(entry.definition.record.endpoints) && !mindmapSelection(handle, entry);
    const pasteView = () => { const entry = selected(); return entry && entry.definition.owner === 'view' ? entry.view : entry?.view ?? currentView(); };
    const graphView = (view) => !!view && str(view.record.kind) !== 'document' && getProfile(str(view.record.profile))?.projection === 'graph';
    function copySelection() {
        const entry = requireSelection();
        if (!copyable(entry))
            throw Error('Copy works on elements. Views, connections and mind-map topics are not copied yet.');
        const position = object(entry.appearance?.record.position);
        const item = { record: clipRecord(entry.definition.record), source: entry.definition.ref, ...(typeof position.x === 'number' && typeof position.y === 'number' ? { position: { x: position.x, y: position.y } } : {}) };
        clipboard = [item];
        clipboardWritten = clipboardText(clipboard);
        void document.defaultView?.navigator.clipboard?.writeText(clipboardWritten).catch(() => { });
        handle.announce(`Copied "${titleOf(entry.definition.record)}".`);
        notifyUICommands(handle.container);
    }
    async function clipboardItems() {
        // Text copied elsewhere (another tab, a file) wins when it differs from what this page copied.
        try {
            const text = await document.defaultView?.navigator.clipboard?.readText();
            if (text && text !== clipboardWritten) {
                const parsed = parseClipboardText(text);
                if (parsed.length)
                    return parsed;
            }
        }
        catch { /* Reading the system clipboard needs permission; fall back to this page's copy. */ }
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
        const decoded = runtimeState(handle.runtime).decoded;
        if (!decoded)
            throw Error('The document is not ready.');
        const taken = new Set(records(handle.runtime.snapshot()).filter(r => r.file === view.ref.file).map(r => str(r.record.name)).filter(Boolean));
        const text = pasteRecords(content, taken, inPlace ? { x: 0, y: 0 } : { x: 24, y: 24 });
        const before = new Set((handle.scene()?.entries ?? []).map(e => e.item.occurrence));
        const receipt = await apply({ kind: 'edit-source', patches: appendDeclaration(decoded, view.ref.file, text, view.ref) });
        const changed = new Set(receipt.changed.map(refKey));
        const created = handle.scene()?.entries.find(e => refKey(e.view.ref) === refKey(view.ref) && e.definition.owner === 'definition' && !before.has(e.item.occurrence) && (changed.has(refKey(e.definition.ref)) || !changed.size));
        if (created)
            handle.select(created.definition.ref, created.item.occurrence);
        handle.announce(`Pasted ${content.length === 1 ? 'one element' : content.length + ' elements'}.`);
    }
    async function pasteReference() {
        const view = pasteView(), source = clipboard[0]?.source;
        if (!view || !source)
            throw Error('Copy an element of this document first.');
        if (!records(handle.runtime.snapshot()).some(r => refKey(r.ref) === refKey(source)))
            throw Error('The copied element no longer exists in this document.');
        await apply({ kind: 'create-occurrence', view: view.ref, target: source });
        handle.announce('Placed the same element in this view.');
    }
    // ---- Documents: output-oriented views with page settings ----
    const activeDocument = () => { const view = currentView(); return view && str(view.record.kind) === 'document' ? view : undefined; };
    function newDocument() {
        if (standalone())
            throw Error('A standalone document contains one view.');
        const snapshot = handle.runtime.snapshot(), decoded = runtimeState(handle.runtime).decoded;
        if (!snapshot || !decoded)
            throw Error('The document is not ready.');
        const source = currentView(), names = new Set(records(snapshot).map(r => str(r.record.name)).filter(Boolean));
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
            const include = document.createElement('input');
            include.type = 'checkbox';
            include.checked = !!source && str(source.record.kind) !== 'document';
            const includeLabel = document.createElement('label');
            includeLabel.append(include, ` Include the current view${source ? ` (${titleOf(source.record)})` : ''} as a figure`);
            include.disabled = !source || str(source.record.kind) === 'document';
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
                const useName = source && include.checked ? str(source.record.name) : '';
                const text = `document ${quoteText(label)} as ${output.value}\n` + (useName ? `    use ${source.ref.file === snapshot.rootFile ? '' : quoteText(source.ref.file) + '::'}${quoteText(useName)}\n` : '');
                await apply({ kind: 'edit-source', patches: appendDeclaration(decoded, snapshot.rootFile, text) });
                const created = handle.scene()?.views.find(v => str(v.record.name) === label);
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
        const snapshot = handle.runtime.snapshot(), references = records(snapshot).map(record => ({ ref: record.ref, label: `${titleOf(record.record)} (${record.owner})` }));
        panel(key === 'page' ? 'Page setup' : key === 'header' ? 'Header' : 'Footer', body => {
            const help = document.createElement('p');
            help.className = 'ddn-dock-help';
            help.textContent = 'Leave a setting empty to use the output default. Only what differs is written to the document.';
            body.append(help);
            const editor = createFieldEditor(body, childSchema(codex.roots.document, key), jsonValue(view.record[key]), references, key === 'page' ? 'Page' : key === 'header' ? 'Header' : 'Footer');
            return async () => { const value = editor.read(); await (value === undefined || value === null ? apply({ kind: 'reset-property', target: view.ref, path: key }) : set(view.ref, key, value)); };
        });
    }
    async function exportDocument() {
        const view = activeDocument();
        if (!view)
            throw Error('Show a document view first.');
        const format = str(view.record.format, 'pdf');
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
            const table = parseCsv(await file.text());
            const taken = new Set(records(snapshot).map(r => str(r.record.name)).filter(Boolean));
            let name = file.name.replace(/\.[^.]+$/, '').replace(/[^A-Za-z0-9_]+/g, '_').replace(/^_+|_+$/g, '') || 'Imported';
            if (/^\d/.test(name))
                name = 'Data_' + name;
            for (let index = 2; taken.has(name); index++)
                name = name.replace(/_\d+$/, '') + '_' + index;
            await nativeCommand('ddn.add-dataset', view?.ref ?? { file: snapshot.rootFile, id: '' }, { name, columns: table.columns.map(column => ({ id: column.id, type: column.type, ...(column.label !== column.id ? { label: column.label } : {}) })), rows: table.rows }, str(view?.record.profile, 'ddn@1'));
            handle.announce(`Imported ${table.rows.length} rows as the dataset "${name}". Bind it to a view with Projection settings.`);
        }));
        input.click();
    }
    const has = (label) => buttons[label];
    const usable = (label) => { const button = has(label); return !!button && !button.hidden && !button.disabled; };
    const clickCommand = (id, label, title = label) => ({ id, label: title, run: () => has(label)?.click(), enabled: () => usable(label) });
    cleanups.push(registerUICommands(handle.container, [
        { id: 'edit.undo', label: 'Undo', run: () => has('Undo')?.click() },
        { id: 'edit.redo', label: 'Redo', run: () => has('Redo')?.click() },
        { id: 'edit.cut', label: 'Cut', run: () => { copySelection(); guarded(() => deleteItem())(); }, enabled: () => copyable() && writable(selected().definition.ref) },
        { id: 'edit.copy', label: 'Copy', run: () => copySelection(), enabled: () => copyable() },
        { id: 'edit.paste', label: 'Paste', run: () => run(() => paste(false)), enabled: () => graphView(pasteView()) },
        { id: 'edit.paste-in-place', label: 'Paste in place', run: () => run(() => paste(true)), enabled: () => graphView(pasteView()) },
        { id: 'edit.paste-reference', label: 'Paste as reference', hint: 'Copy an element of this document first.', run: () => run(pasteReference), enabled: () => !!clipboard[0]?.source && graphView(pasteView()) },
        { id: 'edit.duplicate', label: 'Duplicate', run: () => { const entry = requireSelection(); if (!copyable(entry))
                throw Error('Duplicate works on elements.'); const position = object(entry.appearance?.record.position); run(() => paste(false, [{ record: clipRecord(entry.definition.record), ...(typeof position.x === 'number' && typeof position.y === 'number' ? { position: { x: position.x, y: position.y } } : {}) }])); }, enabled: () => copyable() && writable(selected().definition.ref) },
        clickCommand('edit.delete', 'Delete'),
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
        { id: 'window.inspector', label: 'Inspector', hint: 'Select an element first.', run: value => value === false ? drawerFor(handle.container, 'inspector')?.setMode('hidden') : guarded(() => openInspectorDock())(), enabled: () => !!selected() || !!inspectorDock, checked: () => !!inspectorDock && drawerFor(handle.container, 'inspector')?.mode !== 'hidden' },
        { id: 'window.palette', label: 'Palette', run: value => value === false ? drawerFor(handle.container, 'palette')?.setMode('hidden') : openPaletteDock(), enabled: () => usable('Add element') || !!paletteDock, checked: () => !!paletteDock && drawerFor(handle.container, 'palette')?.mode !== 'hidden' },
    ]));
    cleanups.push(mountMindmapActions(viewer, handle, semanticBounds, { add: addTopic, remove: deleteTopic, name: editTopicName, notes: topicNotes }));
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
            const remaining = await waitForSettingsSave(async () => {
                await inspector?.flush();
                assertDocument();
                for (const dialog of editors) {
                    const body = dialog.querySelector('.ddn-ui-dialog-body');
                    if (body)
                        await flushLiveSettings(body);
                    assertDocument();
                }
            }, task);
            assertDocument();
            const source = await sourcesForSave(handle.runtime, remaining), snapshot = handle.runtime.snapshot();
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
//# sourceMappingURL=index.js.map