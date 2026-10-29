const CSS = `button.ddn-resize-grip{position:absolute!important;right:1px;bottom:1px;z-index:5;display:flex!important;align-items:center;justify-content:center;width:24px!important;height:24px!important;min-width:24px!important;min-height:24px!important;margin:0!important;padding:3px!important;border:0!important;border-radius:4px 0 7px 0!important;background:var(--ddn-ui-surface,#fff)!important;color:var(--ddn-ui-muted,#52647a)!important;cursor:nwse-resize!important;touch-action:none;user-select:none;box-sizing:border-box;flex:none}button.ddn-resize-grip:hover,button.ddn-resize-grip:focus-visible{color:var(--ddn-ui-accent,#2563eb)!important;background:var(--ddn-ui-input,#eef2f7)!important}button.ddn-resize-grip:focus-visible{outline:2px solid var(--ddn-ui-accent,#2563eb);outline-offset:-2px}.ddn-resize-grip svg{width:16px;height:16px;pointer-events:none}`;
/** A visible pointer/touch and keyboard grip; the owner supplies its geometry rules. */
export function resizeGrip(container, options) {
    const document = container.ownerDocument;
    if (!document.querySelector('style[data-ddn-resize-grip]')) {
        const style = document.createElement('style');
        style.dataset.ddnResizeGrip = '';
        style.textContent = CSS;
        document.head.append(style);
    }
    const button = document.createElement('button');
    button.type = 'button';
    button.className = 'ddn-resize-grip';
    button.setAttribute('aria-label', 'Resize ' + options.label);
    button.title = 'Drag to resize, or use arrow keys while focused. Shift resizes farther.';
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('viewBox', '0 0 16 16');
    svg.setAttribute('aria-hidden', 'true');
    const lines = document.createElementNS(svg.namespaceURI, 'path');
    lines.setAttribute('d', 'M3 13L13 3M7 13L13 7M11 13L13 11');
    lines.setAttribute('fill', 'none');
    lines.setAttribute('stroke', 'currentColor');
    lines.setAttribute('stroke-width', '1.5');
    lines.setAttribute('stroke-linecap', 'round');
    svg.append(lines);
    button.append(svg);
    let drag;
    const finish = () => {
        const previous = drag;
        drag = undefined;
        if (previous && button.hasPointerCapture(previous.id))
            button.releasePointerCapture(previous.id);
        if (previous)
            options.end?.();
    };
    button.addEventListener('pointerdown', event => {
        if (event.button !== 0 || drag)
            return;
        event.preventDefault();
        event.stopPropagation();
        options.start?.();
        drag = { id: event.pointerId, x: event.clientX, y: event.clientY, size: options.size() };
        button.setPointerCapture(event.pointerId);
        button.focus({ preventScroll: true });
    });
    button.addEventListener('pointermove', event => {
        if (drag?.id !== event.pointerId)
            return;
        event.preventDefault();
        event.stopPropagation();
        options.resize(drag.size.width + event.clientX - drag.x, drag.size.height + event.clientY - drag.y);
    });
    for (const type of ['pointerup', 'pointercancel', 'lostpointercapture'])
        button.addEventListener(type, event => { if (drag?.id === event.pointerId)
            finish(); });
    button.addEventListener('keydown', event => {
        const offset = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key];
        if (!offset)
            return;
        event.preventDefault();
        event.stopPropagation();
        options.start?.();
        const size = options.size(), step = event.shiftKey ? 40 : 10;
        options.resize(size.width + offset[0] * step, size.height + offset[1] * step);
        options.end?.();
    });
    container.append(button);
    return { button, dispose() { finish(); button.remove(); } };
}
//# sourceMappingURL=resize-grip.js.map