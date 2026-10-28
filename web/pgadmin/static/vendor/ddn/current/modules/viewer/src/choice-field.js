import { fontFamily } from './fonts.js';
import { textureBackground } from './texture.js';
const synchronizers = new WeakMap();
const css = `.ddn-choice-field{display:block;min-width:0;margin:8px 0}.ddn-appearance-grid>.ddn-choice-field{grid-column:1/-1}.ddn-choice-title{display:block;margin-bottom:5px;font-size:12px;font-weight:600}.ddn-choice-options{display:grid;grid-template-columns:repeat(auto-fit,minmax(88px,1fr));gap:6px}.ddn-choice-options button.ddn-choice{display:flex;flex-direction:column;align-items:stretch;justify-content:center;gap:5px;min-width:0;min-height:64px;padding:7px;border:1px solid var(--ddn-ui-border,#8796aa);border-radius:7px;background:var(--ddn-ui-field,var(--ddn-ui-surface,#fff));color:var(--ddn-ui-text,#182637);font-size:11px;text-align:center;white-space:normal}.ddn-choice-options button.ddn-choice[aria-pressed=true]{border-color:var(--ddn-ui-accent,#7660dc);box-shadow:inset 0 0 0 1px var(--ddn-ui-accent,#7660dc);background:var(--ddn-ui-selected,var(--ddn-ui-surface,#fff))}.ddn-choice-options button.ddn-choice:focus-visible{outline:2px solid var(--ddn-ui-accent,#7660dc);outline-offset:2px}.ddn-choice-preview{display:flex;align-items:center;justify-content:center;height:38px;min-width:0;overflow:hidden;pointer-events:none}.ddn-choice-preview>svg{width:100%;height:38px}.ddn-choice-caption{overflow-wrap:anywhere;line-height:1.3}.ddn-choice-field[data-compact=true] .ddn-choice-options{grid-template-columns:repeat(auto-fit,minmax(66px,1fr))}.ddn-choice-field[data-compact=true] .ddn-choice{min-height:42px}.ddn-choice-native{display:none!important}.ddn-choice-surface{display:flex;align-items:center;justify-content:center;width:100%;height:100%;border-radius:3px;box-sizing:border-box;background:#fff;color:#283548;font-size:13px}.ddn-choice-field:has(select:disabled){opacity:.55}.ddn-choice-field:has(select:disabled) button{pointer-events:none}`;
function install(document) {
    if (document.querySelector('style[data-ddn-choices]'))
        return;
    const style = document.createElement('style');
    style.dataset.ddnChoices = '';
    style.textContent = css;
    document.head.append(style);
}
function svg(document, draw) {
    const ns = 'http://www.w3.org/2000/svg', root = document.createElementNS(ns, 'svg');
    root.setAttribute('viewBox', '0 0 88 38');
    root.setAttribute('aria-hidden', 'true');
    draw((tag, attributes, text) => { const node = document.createElementNS(ns, tag); for (const [name, value] of Object.entries(attributes))
        node.setAttribute(name, String(value)); if (text !== undefined)
        node.textContent = text; root.append(node); });
    return root;
}
/** Small examples use the same texture generator and font aliases as the viewer. */
export function choicePreview(document, value, kind) {
    const key = kind.toLowerCase(), v = value.toLowerCase();
    if (/^[lcr][tmb]$/.test(v))
        return svg(document, add => { add('rect', { x: 19, y: 5, width: 50, height: 28, rx: 2, fill: 'none', stroke: 'currentColor' }); add('circle', { cx: v[0] === 'l' ? 19 : v[0] === 'r' ? 69 : 44, cy: v[1] === 't' ? 5 : v[1] === 'b' ? 33 : 19, r: 3, fill: 'currentColor' }); });
    if (key.includes('texture') || ['paper', 'linen', 'grid', 'dots'].includes(v) && key === 'kind') {
        const sample = document.createElement('span');
        sample.className = 'ddn-choice-surface';
        sample.style.backgroundColor = '#f7efdc';
        const texture = textureBackground(v === 'none' ? null : { kind: v, color: '#705c40', opacity: .38, scale: v === 'dots' ? 12 : 24, seed: 3 }, '#f7efdc');
        if (texture) {
            sample.style.backgroundImage = texture.image;
            sample.style.backgroundSize = texture.size;
        }
        sample.textContent = 'Aa';
        return sample;
    }
    if (key.includes('font')) {
        const sample = document.createElement('span');
        sample.className = 'ddn-choice-surface';
        sample.textContent = 'Aa Bb 123';
        sample.style.fontFamily = fontFamily(value);
        sample.style.fontSize = '18px';
        return sample;
    }
    if (key.includes('position') || key.includes('symbol.label') || key === 'label')
        return svg(document, add => {
            add('rect', { x: 32, y: 11, width: 24, height: 16, rx: 2, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5 });
            if (v === 'none' || v === 'hidden') {
                add('path', { d: 'M28 31L60 7', stroke: 'currentColor' });
                return;
            }
            const x = v.includes('left') ? 16 : v.includes('right') ? 72 : 44, y = v.includes('top') ? 7 : v.includes('bottom') ? 36 : 22;
            add('text', { x, y, 'text-anchor': 'middle', 'font-size': 9, fill: 'currentColor' }, 'Aa');
        });
    if (key.includes('presentation') || key === 'symbol.mode')
        return svg(document, add => {
            if (v === 'card' || v === 'auto')
                add('rect', { x: 15, y: 3, width: 58, height: 32, rx: 3, fill: 'none', stroke: 'currentColor' });
            if (v !== 'text')
                add('path', { d: 'M31 23V12H56V23ZM37 27H50M44 23V27', fill: 'none', stroke: 'currentColor', 'stroke-width': 1.3 });
            if (v === 'text')
                add('text', { x: 44, y: 25, 'text-anchor': 'middle', 'font-size': 16, fill: 'currentColor' }, 'Name');
        });
    if (key.includes('shadow') || key.includes('paper') || key.includes('look') || key === 'drawing style')
        return svg(document, add => {
            if (key.includes('shadow') && v !== 'none') {
                const paths = { offset: 'M22 12H74V35H22Z', centre: 'M18 25H68V29Q44 42 18 29Z', corners: 'M18 25H68L74 36Q58 36 44 29Q29 36 12 36Z', corner: 'M18 8H68Q68 21 77 36Q54 32 18 29Z' };
                add('path', { d: paths[v] ?? paths.offset, fill: 'currentColor', opacity: .28 });
            }
            const fill = ['note', 'pad'].includes(v) || v.includes('post') || v.includes('sticky') ? '#fff0a6' : '#fcfaf4';
            add('path', { d: v.includes('hand') ? 'M17 7L69 8L68 29L18 30Z' : v.includes('fold') ? 'M17 7H61L69 15V29H17Z' : 'M17 7H69V29H17Z', fill, stroke: '#61718a' });
            if (v === 'note')
                add('path', { d: 'M17 7H69V12H17Z', fill: '#d9bc54', opacity: .3 });
            if (v.includes('pad'))
                for (const y of [31, 33])
                    add('path', { d: `M17 ${y}H69`, stroke: '#9c8d57' });
            add('text', { x: 43, y: 23, 'text-anchor': 'middle', 'font-size': 12, fill: '#334155' }, 'Aa');
        });
    if (key.includes('align') || ['start', 'center', 'end', 'justify', 'left', 'right'].includes(v))
        return svg(document, add => {
            for (const [i, width] of [52, 36, 44].entries()) {
                const x = ['right', 'end'].includes(v) ? 70 - width : ['center', 'middle'].includes(v) ? 44 - width / 2 : 18;
                add('path', { d: `M${x} ${10 + i * 8}h${v === 'justify' ? 52 : width}`, stroke: 'currentColor', 'stroke-width': 2 });
            }
        });
    if (key.includes('dash') || key.includes('line style') || key.includes('routing'))
        return svg(document, add => {
            add('path', { d: v.includes('curve') ? 'M9 30C28 30 58 7 79 7' : v.includes('ortho') ? 'M9 29H44V9H79' : 'M9 28L79 9', fill: 'none', stroke: 'currentColor', 'stroke-width': 2, ...(v === 'dashed' ? { 'stroke-dasharray': '6 4' } : v === 'dotted' ? { 'stroke-dasharray': '1 4', 'stroke-linecap': 'round' } : {}) });
        });
    if (key.includes('decoration') || key.includes('attachment') || ['push-pin', 'round-pin', 'paper-clip', 'binder-clip', 'tape'].includes(v))
        return svg(document, add => {
            if (v === 'push-pin') {
                add('path', { d: 'M42 19H46L44 35Z', fill: '#8491a0' });
                add('path', { d: 'M38 5H50L49 18L54 22H34L39 18Z', fill: '#dc5a5a', stroke: '#9c3535' });
                add('ellipse', { cx: 44, cy: 5, rx: 7, ry: 3, fill: '#f59191' });
            }
            else if (v === 'round-pin') {
                add('path', { d: 'M42 13H46L44 35Z', fill: '#8491a0' });
                add('circle', { cx: 44, cy: 11, r: 8, fill: '#459cd8' });
                add('circle', { cx: 41, cy: 8, r: 3, fill: '#b2e2ff' });
            }
            else if (v === 'paper-clip')
                add('path', { d: 'M46 27V9C46 3 37 3 37 9V28C37 37 51 37 51 28V8C51-1 33-1 33 8V24', fill: 'none', stroke: '#6c8bb4', 'stroke-width': 2.5, 'stroke-linecap': 'round' });
            else if (v === 'binder-clip') {
                add('path', { d: 'M38 14V7C38 0 50 0 50 7V14M38 25V31C38 38 50 38 50 31V25', fill: 'none', stroke: '#83909e', 'stroke-width': 2 });
                add('path', { d: 'M33 13H55L59 26H29Z', fill: '#39465b' });
            }
            else if (v === 'tape')
                add('path', { d: 'M13 10L18 7H73L70 12L75 17L70 22L73 28H15L18 22L13 17L18 12Z', fill: '#dec38b', stroke: '#b69b63' });
            else
                add('path', { d: 'M24 19H64', stroke: 'currentColor' });
        });
    const sample = document.createElement('span');
    sample.textContent = value === 'true' ? '✓' : value === 'false' ? '—' : value;
    sample.style.cssText = 'font-size:15px;line-height:1.2;overflow-wrap:anywhere';
    return sample;
}
export function syncChoiceField(select) { synchronizers.get(select)?.(); }
/** Buttons are the visible control. The hidden select keeps value/event integration simple. */
export function choiceField(container, label, choices, value, options = {}) {
    const document = container.ownerDocument;
    install(document);
    const wrapper = document.createElement('div');
    wrapper.className = 'ddn-choice-field';
    if (options.compact)
        wrapper.dataset.compact = 'true';
    const title = document.createElement('span');
    title.className = 'ddn-choice-title';
    title.textContent = label;
    const group = document.createElement('div');
    group.className = 'ddn-choice-options';
    group.setAttribute('role', 'group');
    group.setAttribute('aria-label', label);
    const select = document.createElement('select');
    select.className = 'ddn-choice-native';
    select.hidden = true;
    select.tabIndex = -1;
    select.setAttribute('aria-hidden', 'true');
    select.setAttribute('aria-label', label);
    const buttons = [];
    for (const source of choices) {
        const choice = typeof source === 'string' ? { value: source } : source, option = document.createElement('option');
        option.value = choice.value;
        option.textContent = choice.label ?? choice.value;
        select.append(option);
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'ddn-choice';
        button.dataset.choiceValue = choice.value;
        button.setAttribute('aria-label', choice.label ?? choice.value);
        button.title = choice.description ?? choice.label ?? choice.value;
        const preview = document.createElement('span');
        preview.className = 'ddn-choice-preview';
        preview.setAttribute('aria-hidden', 'true');
        preview.append(choice.preview?.(document) ?? choicePreview(document, choice.value, options.kind ?? label));
        const caption = document.createElement('span');
        caption.className = 'ddn-choice-caption';
        caption.textContent = choice.label ?? choice.value;
        button.append(preview, caption);
        group.append(button);
        buttons.push(button);
        button.addEventListener('click', () => { if (select.disabled || select.value === choice.value)
            return; select.value = choice.value; sync(); const view = select.ownerDocument.defaultView; select.dispatchEvent(new view.Event('input', { bubbles: true })); select.dispatchEvent(new view.Event('change', { bubbles: true })); });
    }
    const sync = () => buttons.forEach(button => { button.setAttribute('aria-pressed', String(button.dataset.choiceValue === select.value)); button.disabled = select.disabled; });
    select.value = value;
    sync();
    synchronizers.set(select, sync);
    select.addEventListener('input', sync);
    select.addEventListener('change', sync);
    group.addEventListener('keydown', event => { if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key))
        return; const index = buttons.indexOf(select.ownerDocument.activeElement); if (index < 0)
        return; event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? buttons.length - 1 : (index + (['ArrowRight', 'ArrowDown'].includes(event.key) ? 1 : -1) + buttons.length) % buttons.length; buttons[next]?.focus(); buttons[next]?.click(); });
    wrapper.append(title, select, group);
    container.append(wrapper);
    return select;
}
//# sourceMappingURL=choice-field.js.map