import { getViewerHandle } from '../../viewer/src/native.js';
import { codex, setPath } from '../../profiles/src/schema-core.js';
import { getProfile } from '../../profiles/src/core.js';
import { records, pathValue, titleOf, refKey, str } from '../../presentation/src/native.js';
import { runtimeState } from '../../runtime/src/runtime.js';
import { findNode } from '../../language/src/index.js';
import { colourField, numberField } from './dialogs.js';
import { choiceField } from '../../viewer/src/choice-field.js';
import { listFonts } from '../../viewer/src/fonts.js';
import { flushLiveSettings } from './live-settings.js';
import { createFieldEditor, schemaNode } from './schema-editor.js';
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
/** A typed settings form. Only changed values reach the authorized source service. */
export function openProperties(viewer, panel, commit) {
    const handle = getViewerHandle(viewer), document = handle.ownerDocument;
    const snapshot = handle.runtime.snapshot(), decoded = runtimeState(handle.runtime).decoded;
    if (!snapshot || !decoded)
        throw Error('Open an editable workarea first.');
    const all = records(snapshot), entry = handle.selectedEntry(), scopes = [];
    const addScope = (record, label) => {
        if (!record || scopes.some(s => refKey(s.record.ref) === refKey(record.ref)))
            return;
        const node = findNode(decoded, record.ref);
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
    const references = all.map(record => ({ ref: record.ref, label: titleOf(record.record) + ' (' + record.file + ')' }));
    const scopeTitle = (scope) => titleOf(scope.owner === 'appearance' && entry ? entry.definition.record : scope.owner === 'view_placement' && entry ? entry.view.record : scope.record.record);
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
                    setPath(combined, key, clone(value));
            return pathValue(combined, path);
        };
        const stash = () => {
            if (!dirty || !selectedPath)
                return;
            const value = reset.checked ? undefined : editor?.read();
            if (reset.checked || JSON.stringify(value) !== JSON.stringify(initialValue)) {
                // Preserve the explicit order when parent and child settings
                // are edited in the same form.
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
            const node = schemaNode(definition.schema);
            // Complex records preserve their authored omission choices. Scalar
            // controls show their effective value without writing it on open.
            const authoredRecord = records(handle.runtime.snapshot()).find(record => refKey(record.ref) === refKey(current.record.ref))?.record ?? current.record.record;
            const authored = pathValue(authoredRecord, selectedPath);
            initialValue = clone(effective(selectedPath));
            let value = initialValue;
            if ((node.type === 'object' || node.type === 'array') && !Object.keys(changes).some(path => path === selectedPath || path.startsWith(selectedPath + '.')) && authored !== undefined)
                value = clone(authored);
            initialValue = clone(value);
            if (selectedPath === 'style.font') {
                const families = [...new Set(['sans', 'serif', 'mono', 'handwriting', ...listFonts(document).map(font => font.family), String(value ?? 'sans')])];
                const input = choiceField(editorArea, name, families, String(value ?? 'sans'), { kind: 'font' });
                editor = { read: () => input.value };
            }
            else if (selectedPath === 'style.font_size') {
                const input = numberField(editorArea, 'Font size (pt)', typeof value === 'number' ? value * .75 : 12, { min: 6, max: 48, step: .5 });
                input.step = 'any';
                editor = { read: () => { if (!input.checkValidity() || !Number.isFinite(input.valueAsNumber))
                        throw Error('Enter a valid font size.'); return input.valueAsNumber * 4 / 3; } };
            }
            else if (/(?:^|\.)color$/.test(selectedPath) && typeof value === 'string') {
                const input = colourField(editorArea, name, value);
                editor = { read: () => input.value };
            }
            else {
                let schema = definition.schema;
                if (selectedPath === 'projection.options' && current.owner === 'view_definition') {
                    const profile = getProfile(str(current.record.record.profile));
                    if (profile)
                        schema = codex.roots[profile.projection_schema] ?? schema;
                }
                editor = createFieldEditor(editorArea, schema, value, references, name);
            }
            editorArea.inert = reset.checked;
            hint.textContent = 'Changes appear immediately. Unchanged defaults stay inherited.';
        };
        editorArea.addEventListener('input', () => { dirty = true; });
        editorArea.addEventListener('change', () => { dirty = true; });
        editorArea.addEventListener('click', event => { if (event.target.closest('button'))
            dirty = true; });
        reset.addEventListener('change', () => { dirty = true; editorArea.inert = reset.checked; });
        editorArea.addEventListener('ddn-settings-change', () => { dirty = true; });
        property.addEventListener('change', event => {
            event.stopPropagation();
            const next = property.value;
            property.value = selectedPath;
            property.disabled = true;
            editorArea.inert = true;
            void flushLiveSettings(body).then(() => { if (!body.isConnected)
                return; property.value = next; render(); message.textContent = ''; }).catch(error => { message.textContent = error.message; }).finally(() => { property.disabled = false; editorArea.inert = reset.checked; });
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
                    setPath(values, item.path, clone(item.effective));
            choices = codex.properties.filter(item => item.owner === current.owner && item.settable && !protectedPath(item.path));
            choices.sort((a, b) => {
                const ai = preferred.indexOf(a.path), bi = preferred.indexOf(b.path);
                return (ai < 0 ? preferred.length : ai) - (bi < 0 ? preferred.length : bi) || a.path.localeCompare(b.path);
            });
            property.replaceChildren();
            choices.forEach(item => property.add(new Option(labels[item.path] ?? item.path, item.path)));
            property.value = choices.some(item => item.path === selectedPath) ? selectedPath : choices[0]?.path ?? '';
            loading = false;
            property.disabled = reset.disabled = false;
            render();
        };
        scope.addEventListener('change', event => {
            event.stopPropagation();
            const next = Number(scope.value);
            scope.value = String(chosen);
            scope.disabled = true;
            editorArea.inert = true;
            void flushLiveSettings(body).then(async () => {
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
                    catch { /* Unquoted text remains text. */ }
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
                        setPath(values, item.path, clone(item.effective));
                initialValue = clone(effective(selectedPath));
            }
        };
    });
}
//# sourceMappingURL=properties.js.map