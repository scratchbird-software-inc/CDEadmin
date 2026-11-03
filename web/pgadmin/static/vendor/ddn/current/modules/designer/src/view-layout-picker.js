import { VIEW_SURFACE_PRESETS, getViewSurfacePreset } from '../../profiles/src/view-surfaces.js';
import { createStandardDialog } from './dialogs.js';
const unavailable = ' Available in ScratchWeaver; unavailable in the open-source designer.';
const pageChoices = [
    { id: 'page-letter', label: 'Letter', detail: '8.5 × 11 in', hint: 'Letter paper · 8.5 × 11 inches (215.9 × 279.4 mm).' },
    { id: 'page-legal', label: 'Legal', detail: '8.5 × 14 in', hint: 'Legal paper · 8.5 × 14 inches (215.9 × 355.6 mm).' },
    { id: 'page-a1', label: 'A1', detail: '594 × 841 mm', hint: 'A1 paper · 594 × 841 mm.' },
    { id: 'page-a2', label: 'A2', detail: '420 × 594 mm', hint: 'A2 paper · 420 × 594 mm.' },
    { id: 'page-a3', label: 'A3', detail: '297 × 420 mm', hint: 'A3 paper · 297 × 420 mm.' },
    { id: 'page-a4', label: 'A4', detail: '210 × 297 mm', hint: 'A4 paper · 210 × 297 mm.' },
    { id: 'page-a5', label: 'A5', detail: '148 × 210 mm', hint: 'A5 paper · 148 × 210 mm.' },
    { id: 'page-custom', label: 'Custom page', detail: 'Custom dimensions', hint: 'A physical page with a chosen width, height, units and orientation.' },
].map(choice => ({ ...choice, kind: 'page', unavailable: true, hint: choice.hint + unavailable }));
const presentationChoices = [
    { id: 'presentation-wide', label: 'Widescreen', detail: '16:9 · PPTX / ODP', hint: 'Widescreen presentation layout · 16:9 proportions for PPTX or ODP slides.', width: 16, height: 9 },
    { id: 'presentation-standard', label: 'Standard', detail: '4:3 · PPTX / ODP', hint: 'Standard presentation layout · 4:3 proportions for PPTX or ODP slides.', width: 4, height: 3 },
    { id: 'presentation-custom', label: 'Custom slide', detail: 'Custom proportions', hint: 'A presentation layout with chosen proportions for PPTX or ODP slides.', width: 16, height: 10 },
].map(choice => ({ ...choice, kind: 'presentation', unavailable: true, hint: choice.hint + unavailable }));
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
/** Surface choice is independent of the later diagram method and profile. */
export function viewLayoutDialog(host, options) {
    const document = host.ownerDocument;
    let selected = getViewSurfacePreset(options.selected)?.id ?? 'dynamic';
    const dialog = createStandardDialog(host, { title: 'Choose view layout', applyLabel: 'Continue', onApply() {
            if (!getViewSurfacePreset(selected))
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
    const available = VIEW_SURFACE_PRESETS.map(preset => ({
        id: preset.id, label: preset.label, kind: preset.id === 'dynamic' ? 'dynamic' : 'monitor',
        detail: preset.width && preset.height ? `${preset.width} × ${preset.height} px` : 'Fits its contents',
        hint: preset.description + (preset.id === 'dynamic' ? ' Uses the diagram type’s normal appearance defaults.' : ' Fixed size; content fits within the surface. Sans-serif text scales to the display, with dark text on a neutral white background. Customise colours, fonts and branding later.'),
        ...(preset.width && preset.height ? { width: preset.width, height: preset.height } : {}),
    }));
    const choicesById = new Map([...available, ...pageChoices, ...presentationChoices].map(choice => [choice.id, choice]));
    const defaultHint = () => {
        const focused = document.activeElement;
        return (focused && dialog.body.contains(focused) ? choicesById.get(focused.dataset.layout ?? '') : undefined)?.hint
            ?? choicesById.get(selected).hint;
    };
    hint.textContent = defaultHint();
    for (const [title, choices, closed] of [['Dynamic and TV dashboards', available, false], ['Physical pages', pageChoices, true], ['Presentations', presentationChoices, true]]) {
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
            tile.addEventListener('mouseenter', () => { hint.textContent = choice.hint; });
            tile.addEventListener('focus', () => { hint.textContent = choice.hint; });
            tile.addEventListener('mouseleave', () => { if (document.activeElement !== tile)
                hint.textContent = defaultHint(); });
            tile.addEventListener('blur', () => { if (!tile.matches(':hover'))
                hint.textContent = defaultHint(); });
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
export { viewLayoutSource } from './layout-source.js';
//# sourceMappingURL=view-layout-picker.js.map