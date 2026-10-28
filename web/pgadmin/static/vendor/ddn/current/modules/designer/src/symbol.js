import { getViewerHandle } from '../../viewer/src/native.js';
import { records, object, refKey, str, titleOf } from '../../presentation/src/native.js';
import { runtimeState } from '../../runtime/src/runtime.js';
import { findNode } from '../../language/src/index.js';
import { numberField, syncNumberField } from './dialogs.js';
import { choiceField } from '../../viewer/src/choice-field.js';
import { flushLiveSettings, notifyLiveSettings } from './live-settings.js';
const modes = ['auto', 'card', 'image', 'text'];
const labels = ['auto', 'none', 'inside', 'top', 'bottom', 'left', 'right', 'top-left', 'top-right', 'bottom-left', 'bottom-right'];
const owns = (record, path) => Object.prototype.hasOwnProperty.call(record, path);
/** Live symbol presentation uses the same authorized transaction as other appearance editors. */
export function openSymbol(viewer, panel, commit) {
    const handle = getViewerHandle(viewer), document = handle.ownerDocument, snapshot = handle.runtime.snapshot();
    const decoded = runtimeState(handle.runtime).decoded, entry = handle.selectedEntry();
    if (!snapshot || !decoded || !entry || entry.definition.owner !== 'definition' || entry.definition.record.category === 'relation')
        throw Error('Select an element first.');
    const scopes = [];
    const appearanceNode = entry.appearance ? findNode(decoded, entry.appearance.ref) : undefined;
    if (entry.appearance && appearanceNode && !appearanceNode.implicit)
        scopes.push({ record: entry.appearance, label: 'This appearance' });
    scopes.push({ record: entry.definition, label: 'Shared element' });
    const assets = records(snapshot).filter(record => record.owner === 'asset' && str(record.record.media_type).startsWith('image/'));
    panel('Symbol & label', body => {
        const select = (container, name, options, value) => {
            if (name !== 'Apply symbol settings to')
                return choiceField(container, name, options, value);
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
        title.textContent = titleOf(entry.definition.record);
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
        const changed = (path, value) => { changes[path] = value; notifyLiveSettings(body); message.textContent = value === undefined ? 'Using the inherited setting.' : 'Changes appear immediately.'; };
        const inherit = (name, path) => {
            const button = document.createElement('button');
            button.type = 'button';
            button.textContent = 'Inherit';
            button.setAttribute('aria-label', 'Inherit ' + name);
            button.addEventListener('click', () => { changed(path, undefined); void flushLiveSettings(body).then(() => { if (body.isConnected)
                render(); }).catch(error => { message.textContent = error.message; }); });
            content.append(button);
        };
        const render = () => {
            content.replaceChildren();
            const mode = select(content, 'Presentation', modes.map(value => ({ value, label: value === 'auto' ? 'Automatic' : value === 'card' ? 'Native / card' : value === 'image' ? 'Image symbol' : 'Unboxed text' })), String(effective('symbol.mode', 'auto')));
            mode.addEventListener('change', () => changed('symbol.mode', mode.value));
            inherit('presentation', 'symbol.mode');
            const imageValue = effective('symbol.image', null), imageRef = imageValue === null ? undefined : object(imageValue);
            const automatic = owns(changes, 'symbol.image') ? changes['symbol.image'] === undefined : !origins.has('symbol.image') || origins.get('symbol.image').startsWith('standard:');
            const imageKey = imageRef ? refKey({ file: str(imageRef.file, scopes[chosen].record.file), id: str(imageRef.id) }) : automatic ? 'inherit' : '';
            const options = [{ value: 'inherit', label: 'Automatic / inherited image' }, { value: '', label: 'None (disable inherited image)' }, ...assets.map(asset => ({ value: refKey(asset.ref), label: titleOf(asset.record) + ' · ' + asset.file }))];
            if (imageKey && !options.some(option => option.value === imageKey))
                options.push({ value: imageKey, label: 'Unavailable asset · ' + str(imageRef?.id) });
            const asset = select(content, 'Image asset', options, imageKey);
            asset.addEventListener('change', () => { const selected = assets.find(item => refKey(item.ref) === asset.value); changed('symbol.image', asset.value === 'inherit' ? undefined : selected ? { ...selected.ref } : null); });
            inherit('image asset', 'symbol.image');
            const position = select(content, 'Name position', labels.map(value => ({ value, label: value === 'auto' ? 'Automatic' : value === 'none' ? 'Hidden' : value.replaceAll('-', ' ') })), String(effective('symbol.label', 'auto')));
            position.addEventListener('change', () => changed('symbol.label', position.value));
            inherit('name position', 'symbol.label');
            const gap = numberField(content, 'Label gap', String(effective('symbol.label_gap', 6)), { min: 0, max: 64, step: 1 });
            gap.removeAttribute('max');
            gap.step = 'any';
            syncNumberField(gap);
            gap.addEventListener('input', () => changed('symbol.label_gap', gap.valueAsNumber));
            inherit('label gap', 'symbol.label_gap');
        };
        const readValues = async () => { const current = ticket, inspection = await viewer.inspect(scopes[chosen].record.ref); if (current !== ticket || !body.isConnected)
            return; values = new Map(inspection.properties.map(property => [property.path, property.effective])); origins = new Map(inspection.properties.map(property => [property.path, property.origin])); };
        const refresh = async () => { loading = true; ++ticket; content.replaceChildren(); await readValues(); loading = false; if (body.isConnected)
            render(); };
        scope.addEventListener('change', event => { event.stopPropagation(); const next = Number(scope.value); scope.value = String(chosen); scope.disabled = true; content.inert = true; void flushLiveSettings(body).then(async () => { if (!body.isConnected)
            return; chosen = next; scope.value = String(next); changes = {}; await refresh(); }).catch(error => { message.textContent = error.message; }).finally(() => { scope.disabled = false; content.inert = false; }); });
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
//# sourceMappingURL=symbol.js.map