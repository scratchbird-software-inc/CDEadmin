import { getFontResources, installFontResources } from './fonts.js';
import { UI_THEME_TOKEN_NAMES } from './ui-theme.js';
import { resizeGrip } from './resize-grip.js';
const open = new Map();
const POPOUT_CSS = `html,body{margin:0;height:100%}body{background:var(--ddn-ui-bg);color:var(--ddn-ui-text);font:var(--ddn-ui-font-size,13px)/1.4 Inter,system-ui,sans-serif}
.ddn-popout-host{box-sizing:border-box;display:flex!important;flex-direction:column;height:100%!important;min-height:0!important;margin:0;border:0!important;border-radius:0!important;box-shadow:none!important;overflow:hidden;grid-template-columns:none!important;grid-template-rows:none!important}
.ddn-popout-host>*{flex:1 1 auto;min-height:0;max-height:none!important;height:auto!important;width:auto!important;max-width:none!important;position:static!important;border-radius:0!important;box-shadow:none!important;display:flex;flex-direction:column}
.ddn-popout-host>.ddn-designer-dock,.ddn-popout-host>.ddn-viewer-outline{display:block;overflow:auto}
.ddn-popout-host>.ddn-ui-dialog{display:grid;border:0}.ddn-popout-host .ddn-resize-grip{display:none!important}`;
const FLOAT_CSS = `.ddn-float{box-sizing:border-box;padding-bottom:24px;position:fixed;z-index:70;display:flex;flex-direction:column;min-width:min(240px,calc(100vw - 16px));min-height:min(160px,calc(100vh - 16px));max-width:calc(100vw - 16px);max-height:calc(100vh - 16px);overflow:hidden;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);border:1px solid var(--ddn-ui-border);border-radius:12px;box-shadow:0 18px 50px color-mix(in srgb,var(--ddn-ui-shadow) 80%,transparent);font:var(--ddn-ui-font-size,13px)/1.4 Inter,system-ui,sans-serif}
.ddn-float-head{display:flex;align-items:center;gap:6px;padding:4px 6px 4px 10px;border-bottom:1px solid var(--ddn-ui-border);background:var(--ddn-ui-bg);flex:none}
.ddn-float-head .ddn-float-move{flex:1;min-width:0;text-align:left;justify-content:flex-start;border:0;background:transparent;color:inherit;font:600 12px Inter,system-ui,sans-serif;cursor:grab;padding:4px 2px;touch-action:none}
.ddn-float-head button{min-height:26px;padding:2px 8px;font-size:11px}
.ddn-float-body{flex:1;min-height:0;display:flex;flex-direction:column;overflow:hidden}.ddn-float-body.ddn-viewer{display:flex;min-height:0;border:0;border-radius:0;grid-template-columns:none;grid-template-rows:none}
.ddn-float-body>*{flex:1 1 auto;min-height:0;height:auto!important;max-height:none!important;width:auto!important;position:static!important;border-radius:0!important;box-shadow:none!important;border:0!important}
.ddn-float-body>.ddn-designer-dock,.ddn-float-body>.ddn-viewer-outline{display:block;overflow:auto}`;
function remembered(name) {
    try {
        return JSON.parse(localStorage.getItem('ddn.detached.' + name) ?? '{}') ?? {};
    }
    catch {
        return {};
    }
}
function remember(name, value) {
    try {
        localStorage.setItem('ddn.detached.' + name, JSON.stringify(value));
    }
    catch { /* Preferences are optional. */ }
}
/** Copies interface theme tokens so the detached panel looks as it did in place. */
function copyTheme(from, toBody, bodyStyle = true) {
    const source = from.ownerDocument;
    for (const attribute of bodyStyle ? ['data-ddn-ui-theme', 'style'] : ['data-ddn-ui-theme'])
        if (source.body.hasAttribute(attribute))
            toBody.setAttribute(attribute, source.body.getAttribute(attribute));
    const computed = source.defaultView.getComputedStyle(from);
    for (const token of UI_THEME_TOKEN_NAMES) {
        const value = computed.getPropertyValue(token).trim();
        if (value)
            toBody.style.setProperty(token, value);
    }
}
function track(document, item) {
    let set = open.get(document);
    if (!set) {
        set = new Set();
        open.set(document, set);
        // Detached windows belong to this page: they close with it.
        document.defaultView?.addEventListener('pagehide', () => { for (const detached of [...(open.get(document) ?? [])])
            detached.dock(); });
    }
    set.add(item);
}
function untrack(document, item) { open.get(document)?.delete(item); }
/** Detached panels of a document (for a Window menu). */
export function detachedPanels(document) { return [...(open.get(document) ?? [])]; }
/** Re-applies theme tokens after an interface theme change. */
export function syncDetachedThemes(document) {
    for (const item of open.get(document) ?? []) {
        if (item.kind === 'window' && item.window && !item.window.closed)
            copyTheme(document.body, item.window.document.body);
        else if (item.kind === 'floating') {
            const frame = item.element.closest('.ddn-float');
            if (frame)
                copyTheme(document.body, frame, false);
        }
    }
}
/**
 * Opens a same-origin window and moves the element into it. Returns undefined
 * when the browser blocks the window (popup blockers, sandboxed frames); the
 * caller then falls back to a floating frame.
 */
export function popOut(element, options) {
    const opener = element.ownerDocument, view = opener.defaultView;
    if (!view)
        return undefined;
    const place = remembered(options.name), width = Math.round(place.width ?? options.width ?? 420), height = Math.round(place.height ?? options.height ?? 640);
    const left = Math.round(place.left ?? (view.screenX + view.outerWidth - width - 24)), top = Math.round(place.top ?? (view.screenY + 80));
    let popup = null;
    // A fresh browsing context is required even when two embedded tools use the same preference key.
    try {
        popup = view.open('', '_blank', `popup=yes,width=${width},height=${height},left=${left},top=${top}`);
    }
    catch {
        popup = null;
    }
    if (!popup)
        return undefined;
    let target;
    try {
        target = popup.document;
        target.open();
        target.write('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title></title></head><body></body></html>');
        target.close();
    }
    catch {
        try {
            popup.close();
        }
        catch { /* ignore */ }
        return undefined;
    }
    target.title = options.title + ' — DDN';
    const copyFonts = () => { void installFontResources(target, getFontResources(opener)).catch(() => { }); };
    copyFonts();
    opener.addEventListener('ddn:font-resources', copyFonts);
    for (const style of opener.querySelectorAll('style,link[rel=stylesheet]'))
        target.head.append(target.importNode(style, true));
    const extra = target.createElement('style');
    extra.textContent = POPOUT_CSS;
    target.head.append(extra);
    copyTheme(element.parentElement ?? opener.body, target.body);
    const host = target.createElement('div');
    host.className = 'ddn-popout-host ' + (options.hostClass ?? '');
    host.setAttribute('role', 'region');
    host.setAttribute('aria-label', options.title);
    target.body.append(host);
    host.style.paddingBottom = '24px';
    const marker = opener.createComment('ddn-detached:' + options.name);
    element.replaceWith(marker);
    host.append(element);
    let finished = false;
    const save = () => { try {
        remember(options.name, { left: popup.screenX, top: popup.screenY, width: popup.outerWidth, height: popup.outerHeight });
    }
    catch { /* closed */ } };
    const grip = resizeGrip(target.body, { label: options.title + ' window', size: () => ({ width: popup.outerWidth, height: popup.outerHeight }), resize(width, height) {
            if (finished || popup.closed)
                return;
            popup.resizeTo(Math.min(popup.screen.availWidth, Math.max(280, Math.round(width))), Math.min(popup.screen.availHeight, Math.max(220, Math.round(height))));
        }, end: save });
    const finish = (returnElement) => {
        if (finished)
            return;
        finished = true;
        observer.disconnect();
        grip.dispose();
        opener.removeEventListener('ddn:font-resources', copyFonts);
        untrack(opener, detached);
        if (returnElement && host.contains(element)) {
            if (marker.isConnected)
                marker.replaceWith(element);
            else
                element.remove();
        }
        marker.remove();
        options.onReturn?.();
    };
    // If the panel's owner removes it (for example, the inspector closes), the window closes too.
    const observer = new popup.MutationObserver(() => { if (!host.contains(element)) {
        finish(false);
        try {
            popup.close();
        }
        catch { /* ignore */ }
    } });
    observer.observe(host, { childList: true });
    popup.addEventListener('pagehide', () => { save(); finish(true); });
    popup.addEventListener('resize', save);
    if (options.onKeydown)
        target.addEventListener('keydown', options.onKeydown);
    const detached = {
        kind: 'window', element, window: popup,
        dock() { save(); finish(true); try {
            popup.close();
        }
        catch { /* ignore */ } },
        focus() { try {
            popup.focus();
        }
        catch { /* ignore */ } },
    };
    track(opener, detached);
    popup.focus();
    return detached;
}
/** An in-page floating frame with a keyboard Move control, clamped to the viewport. */
export function floatPanel(element, options) {
    const document = element.ownerDocument, view = document.defaultView;
    if (!document.querySelector('style[data-ddn-float]')) {
        const style = document.createElement('style');
        style.dataset.ddnFloat = '';
        style.textContent = FLOAT_CSS;
        document.head.append(style);
    }
    const frame = document.createElement('section');
    frame.className = 'ddn-float ddn-ui-theme';
    let stack = 70;
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
        const z = Number.parseInt(view.getComputedStyle(parent).zIndex, 10);
        if (Number.isFinite(z))
            stack = Math.max(stack, z + 1);
    }
    frame.style.zIndex = String(stack);
    frame.setAttribute('role', 'region');
    frame.setAttribute('aria-label', options.title);
    const head = document.createElement('div');
    head.className = 'ddn-float-head';
    const move = document.createElement('button');
    move.type = 'button';
    move.className = 'ddn-float-move';
    move.textContent = options.title;
    move.title = 'Drag to move, or focus and use the arrow keys (Shift moves farther)';
    move.setAttribute('aria-label', 'Move ' + options.title);
    head.append(move);
    for (const action of options.actions ?? []) {
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = action.label;
        button.title = action.title;
        button.addEventListener('click', action.run);
        head.append(button);
    }
    const body = document.createElement('div');
    body.className = 'ddn-float-body ' + (options.hostClass ?? '');
    frame.append(head, body);
    const place = remembered('float-' + options.name);
    const width = Math.min(place.width ?? options.width ?? 380, view.innerWidth - 16), height = Math.min(place.height ?? options.height ?? 480, view.innerHeight - 16);
    frame.style.width = width + 'px';
    frame.style.height = height + 'px';
    const position = (left, top) => {
        const bounds = frame.getBoundingClientRect();
        frame.style.left = Math.max(8, Math.min(left, view.innerWidth - bounds.width - 8)) + 'px';
        frame.style.top = Math.max(8, Math.min(top, view.innerHeight - bounds.height - 8)) + 'px';
    };
    copyTheme(element.parentElement ?? document.body, frame, false);
    const marker = document.createComment('ddn-floating:' + options.name);
    element.replaceWith(marker);
    body.append(element);
    document.body.append(frame);
    position(place.left ?? view.innerWidth - width - 24, place.top ?? 96);
    const save = () => { const b = frame.getBoundingClientRect(); remember('float-' + options.name, { left: b.left, top: b.top, width: b.width, height: b.height }); };
    const grip = resizeGrip(frame, { label: options.title, size: () => frame.getBoundingClientRect(), resize(width, height) {
            const bounds = frame.getBoundingClientRect(), maxWidth = Math.max(0, view.innerWidth - bounds.left - 8), maxHeight = Math.max(0, view.innerHeight - bounds.top - 8);
            frame.style.width = Math.min(maxWidth, Math.max(Math.min(240, maxWidth), width)) + 'px';
            frame.style.height = Math.min(maxHeight, Math.max(Math.min(160, maxHeight), height)) + 'px';
        }, end: save });
    let drag;
    move.addEventListener('pointerdown', event => {
        if (event.button !== 0)
            return;
        const b = frame.getBoundingClientRect();
        drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: b.left, top: b.top };
        move.setPointerCapture(event.pointerId);
        event.preventDefault();
    });
    move.addEventListener('pointermove', event => { if (drag?.id === event.pointerId)
        position(drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y); });
    const end = () => { if (drag) {
        drag = undefined;
        save();
    } };
    move.addEventListener('pointerup', end);
    move.addEventListener('pointercancel', end);
    move.addEventListener('keydown', event => {
        const step = event.shiftKey ? 40 : 10, offsets = { ArrowLeft: [-step, 0], ArrowRight: [step, 0], ArrowUp: [0, -step], ArrowDown: [0, step] }, offset = offsets[event.key];
        if (!offset)
            return;
        event.preventDefault();
        const b = frame.getBoundingClientRect();
        position(b.left + offset[0], b.top + offset[1]);
        save();
    });
    const clamp = () => { const b = frame.getBoundingClientRect(); position(b.left, b.top); };
    view.addEventListener('resize', clamp);
    const resize = new view.ResizeObserver(() => save());
    resize.observe(frame);
    let finished = false;
    const observer = new view.MutationObserver(() => { if (!body.contains(element))
        finish(false); });
    observer.observe(body, { childList: true });
    function finish(returnElement) {
        if (finished)
            return;
        finished = true;
        observer.disconnect();
        resize.disconnect();
        grip.dispose();
        view.removeEventListener('resize', clamp);
        untrack(document, detached);
        if (returnElement && body.contains(element) && marker.isConnected)
            marker.replaceWith(element);
        marker.remove();
        frame.remove();
        options.onReturn?.();
    }
    const detached = { kind: 'floating', element, dock: () => finish(true), focus: () => move.focus() };
    track(document, detached);
    return detached;
}
//# sourceMappingURL=popout.js.map