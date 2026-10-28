/** Status explanations belong to the display, independently of editing tools. */
const descriptions = {
    draft: 'Draft — free-form design; information may be incomplete.',
    'in-progress': 'In progress — structured design; information may still be incomplete.',
    'in-review': 'In review — complete and verified, awaiting acceptance.',
    accepted: 'Accepted — accepted by an authorized user; acceptance details are recorded.',
};
export function statusHint(state) {
    return 'Design status: ' + (descriptions[state] ?? descriptions.draft);
}
export function installStatusHint(surface, overlays, id) {
    const document = surface.ownerDocument, tooltip = document.createElement('div');
    tooltip.id = id;
    tooltip.setAttribute('role', 'tooltip');
    tooltip.hidden = true;
    tooltip.style.cssText = 'position:absolute;z-index:20;pointer-events:none;max-width:min(300px,calc(100% - 16px));box-sizing:border-box;padding:8px 10px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);box-shadow:0 4px 14px #0003;font:12px/1.45 Inter,system-ui,sans-serif;overflow-wrap:anywhere';
    overlays.append(tooltip);
    let hovered, focused, described;
    const dot = (target) => target?.closest?.('[data-status-dot]') ?? undefined;
    const update = () => {
        described?.removeAttribute('aria-describedby');
        described = undefined;
        const active = hovered ?? focused;
        if (!active?.isConnected) {
            tooltip.hidden = true;
            return;
        }
        tooltip.textContent = statusHint(active.getAttribute('data-status-dot') ?? 'draft');
        tooltip.hidden = false;
        active.setAttribute('aria-describedby', id);
        described = active;
        const parent = overlays.getBoundingClientRect(), anchor = active.getBoundingClientRect(), size = tooltip.getBoundingClientRect();
        tooltip.style.left = Math.max(8, Math.min(anchor.left - parent.left + anchor.width / 2 - size.width / 2, parent.width - size.width - 8)) + 'px';
        const above = anchor.top - parent.top - size.height - 8;
        tooltip.style.top = Math.max(8, Math.min(above >= 8 ? above : anchor.bottom - parent.top + 8, parent.height - size.height - 8)) + 'px';
    };
    const hide = () => { hovered = focused = undefined; update(); };
    const over = (event) => { hovered = dot(event.target); update(); };
    const out = (event) => { hovered = dot(event.relatedTarget); update(); };
    const focus = (event) => { focused = dot(event.target); update(); };
    const blur = (event) => { focused = dot(event.relatedTarget); update(); };
    const key = (event) => { if (event.key === 'Escape')
        hide(); };
    surface.addEventListener('pointerover', over);
    surface.addEventListener('pointerout', out);
    surface.addEventListener('focusin', focus);
    surface.addEventListener('focusout', blur);
    surface.addEventListener('pointerdown', hide);
    surface.addEventListener('keydown', key);
    return { hide, destroy() {
            hide();
            tooltip.remove();
            surface.removeEventListener('pointerover', over);
            surface.removeEventListener('pointerout', out);
            surface.removeEventListener('focusin', focus);
            surface.removeEventListener('focusout', blur);
            surface.removeEventListener('pointerdown', hide);
            surface.removeEventListener('keydown', key);
        } };
}
//# sourceMappingURL=status-hint.js.map