import { knownProfile } from '../../profiles/src/core.js';
import { quoteText } from '../../language/src/index.js';
import { methodLabel, profileLabel, methodPreview, profilePreview } from './view-previews.js';
export function profileDisplayName(id) {
    return `${profileLabel(id)} (${id})`;
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
/** Browse lightweight previews; selecting a type does not load its renderer pack. */
export function viewTypePicker(body, profiles, label = 'View profile', selected) {
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
    const available = [...new Map(profiles.map(profile => [profile.id, { id: profile.id, method: knownProfile(profile.id)?.method ?? profile.method }])).values()];
    const methods = [...new Set(available.map(profile => profile.method))];
    const current = available.find(profile => profile.id === selected);
    const listeners = new Set();
    let value = '';
    const choose = (next) => { value = next; for (const listener of [...listeners])
        listener(value); };
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
            const tile = card(methodLabel(method), methodPreview(document, method), `${count} diagram ${count === 1 ? 'type' : 'types'}${current?.method === method ? ' · Current' : ''}`);
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
        content.replaceChildren(heading(methodLabel(method), 2));
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
            const matches = types.filter(profile => `${profileLabel(profile.id)} ${profile.id}`.toLocaleLowerCase().includes(term));
            result.textContent = term ? `${matches.length} of ${types.length} diagram types` : `${types.length} diagram ${types.length === 1 ? 'type' : 'types'} — choose one to continue`;
            grid.replaceChildren();
            for (const profile of matches) {
                const tile = card(profileLabel(profile.id), profilePreview(document, profile.id), current?.id === profile.id ? 'Current type' : undefined);
                tile.dataset.profile = profile.id;
                tile.title = profileLabel(profile.id);
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
                    status.textContent = `${profileLabel(profile.id)} selected.`;
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
        status.textContent = `${methodLabel(method)}. Choose a diagram type.`;
    }
    showMethods();
    return { element, get value() { return value; }, onChange(listener) { listeners.add(listener); } };
}
/** A new mind map includes its central topic; other defaults remain implicit. */
export function diagramHeader(name, profile, title) {
    const header = profile === 'ddn@1' ? 'erd ' + quoteText(name)
        : profile === 'mindmap.basic@1' ? 'mindmap ' + quoteText(name)
            : 'view ' + quoteText(name) + ' as ' + quoteText(profile);
    return header + (title === undefined ? '' : ' : ' + quoteText(title));
}
//# sourceMappingURL=view-picker.js.map