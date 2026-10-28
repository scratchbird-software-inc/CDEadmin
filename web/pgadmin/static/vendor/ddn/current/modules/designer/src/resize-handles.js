import { titleOf } from '../../presentation/src/native.js';
/** Screen-sized editing affordances; capture uses the scene, never these DOM controls. */
export function mountResizeHandles(viewer, handle, options) {
    const document = handle.ownerDocument, NS = 'http://www.w3.org/2000/svg';
    let focusedOccurrence;
    const css = document.createElement('style');
    css.textContent = '.ddn-element-resize{cursor:nwse-resize;touch-action:none;opacity:.65;outline:none}.ddn-element-resize:hover,.ddn-element-resize:focus-visible,[data-selected=true]>.ddn-element-resize{opacity:1}.ddn-element-resize .ddn-resize-pad{fill:#fff;fill-opacity:.85;stroke:#5278a1;stroke-opacity:.4}.ddn-element-resize path{fill:none;stroke:#416b98;stroke-width:1.5;stroke-linecap:round;pointer-events:none}.ddn-element-resize:focus-visible .ddn-resize-pad{stroke:#2563eb;stroke-width:2}';
    handle.container.append(css);
    const stopClick = (event) => { event.preventDefault(); event.stopPropagation(); };
    const clearFocus = (event) => {
        const target = event.target;
        if (!target?.closest?.('.ddn-element-resize') || !handle.surface.contains(target))
            focusedOccurrence = undefined;
    };
    document.addEventListener('focusin', clearFocus);
    document.addEventListener('pointerdown', clearFocus, true);
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
            if (group.getAttribute('data-selected') !== 'true' || !entry || !options.allowed(entry) || handle.surface.dataset.lod === 'mini') {
                if (focusedOccurrence === occurrence)
                    focusedOccurrence = undefined;
                grip?.remove();
                continue;
            }
            if (!grip) {
                grip = document.createElementNS(NS, 'g');
                grip.classList.add('ddn-element-resize');
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
                // Resolve by occurrence at event time: redraws may replace records.
                const current = () => handle.scene()?.entries.find(item => item.item.occurrence === occurrence);
                grip.addEventListener('focus', () => { focusedOccurrence = occurrence; });
                grip.addEventListener('pointerdown', event => { const target = current(); if (group.getAttribute('data-selected') === 'true' && target && options.allowed(target))
                    options.start(target, event); });
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
            grip.setAttribute('aria-label', 'Resize ' + titleOf(entry.definition.record));
            const b = options.bounds(entry);
            grip.setAttribute('transform', `translate(${b.x + b.width - 20 / scale} ${b.y + b.height - 20 / scale}) scale(${1 / scale})`);
            // The viewer rebuilds SVG children on zoom, font loads and redraws.
            // Preserve keyboard focus only when it was lost with that DOM node.
            if (focusedOccurrence === occurrence && (document.activeElement === document.body || document.activeElement === handle.surface))
                grip.focus({ preventScroll: true });
        }
    }
    const unsubscribe = viewer.subscribe(event => { if (['ready', 'viewport', 'selection'].includes(event.kind))
        update(); });
    const unselect = handle.subscribeSelection(update), Resize = document.defaultView?.ResizeObserver;
    const unopen = handle.subscribeOpen(() => { focusedOccurrence = undefined; });
    const observer = Resize ? new Resize(update) : undefined;
    observer?.observe(handle.surface);
    update();
    return () => { unsubscribe(); unselect(); unopen(); observer?.disconnect(); document.removeEventListener('focusin', clearFocus); document.removeEventListener('pointerdown', clearFocus, true); css.remove(); handle.surface.querySelectorAll('.ddn-element-resize').forEach(grip => grip.remove()); };
}
//# sourceMappingURL=resize-handles.js.map