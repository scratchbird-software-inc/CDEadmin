import { popOut, floatPanel } from './popout.js';
import { uiIcon } from './ui-icons.js';
let serial = 0;
const drawers = new WeakMap();
export function drawerFor(container, id) { return container ? drawers.get(container)?.get(id) : undefined; }
const CSS = `.ddn-drawer-controls{display:inline-flex;gap:2px;margin-left:auto;align-items:center;flex:none}.ddn-viewer .ddn-drawer-controls button,.ddn-drawer-controls button{display:inline-flex!important;align-items:center;justify-content:center;width:25px!important;min-width:25px;min-height:26px;margin:0!important;padding:3px!important;border:1px solid transparent;border-radius:5px;color:var(--ddn-ui-muted);background:transparent;cursor:pointer}.ddn-drawer-controls button:hover{color:var(--ddn-ui-accent);background:color-mix(in srgb,var(--ddn-ui-accent) 12%,transparent)}.ddn-drawer-controls button:focus-visible,.ddn-drawer-rail button:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:1px}.ddn-drawer-controls button[hidden],.ddn-drawer-rail[hidden],[data-ddn-drawer][hidden]{display:none!important}.ddn-drawer-rail{position:absolute;z-index:8;top:112px;bottom:48px;left:0;pointer-events:none;display:flex;align-items:flex-start}.ddn-drawer-rail[data-side=right]{left:auto;right:0}.ddn-drawer-rail button{pointer-events:auto;writing-mode:vertical-rl;display:flex;align-items:center;gap:7px;border:1px solid var(--ddn-ui-border);border-radius:0 7px 7px 0;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);padding:10px 5px;font:600 11px system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 6px #0002}.ddn-drawer-rail[data-side=right] button{border-radius:7px 0 0 7px}.ddn-drawer-rail[data-drawer=navigator]{top:245px}@media(max-width:760px){.ddn-drawer-rail{top:auto;bottom:36px}.ddn-drawer-rail[data-drawer=navigator]{top:auto;bottom:180px}}`;
/** One owner for embedded drawers and host menus; detach keeps the same DOM and runtime. */
export function createDrawer(element, options) {
    const { container, id, title } = options, document = container.ownerDocument, window = document.defaultView;
    if (!document.querySelector('style[data-ddn-drawers]')) {
        const style = document.createElement('style');
        style.dataset.ddnDrawers = '';
        style.textContent = CSS;
        document.head.append(style);
    }
    let entries = drawers.get(container);
    if (!entries) {
        entries = new Map();
        drawers.set(container, entries);
    }
    entries.get(id)?.destroy();
    const windowKey = id + '-' + (++serial);
    let mode = 'docked', detached, disposed = false, moving = false;
    element.dataset.ddnDrawer = id;
    const rail = document.createElement('div');
    rail.className = 'ddn-drawer-rail';
    rail.dataset.side = options.side ?? 'left';
    rail.dataset.drawer = id;
    rail.hidden = true;
    const reopen = document.createElement('button');
    reopen.type = 'button';
    reopen.setAttribute('aria-label', 'Show ' + title);
    reopen.title = 'Open the ' + title.toLowerCase() + ' drawer';
    reopen.setAttribute('aria-expanded', 'false');
    reopen.append(uiIcon(document, options.side === 'right' ? 'arrow-left' : 'arrow-right'), document.createTextNode(title));
    rail.append(reopen);
    container.append(rail);
    const controls = document.createElement('div');
    controls.className = 'ddn-drawer-controls';
    controls.setAttribute('role', 'group');
    controls.setAttribute('aria-label', title + ' panel controls');
    const buttons = new Map();
    for (const [value, label, icon, hint] of [
        ['floating', 'Float ' + title, 'layers', 'Float this panel over the page. Drag its title to move it.'],
        ['popout', 'Pop out ' + title, 'expand', 'Open this panel in its own window, which you can move to another monitor.'],
        ['docked', 'Dock ' + title, 'fit', 'Return this panel to its drawer.'],
        ['hidden', options.closeLabel ?? 'Close ' + title, 'minus', 'Close this drawer. Its edge tab opens it again.'],
    ]) {
        const button = document.createElement('button');
        button.type = 'button';
        button.setAttribute('aria-label', label);
        button.title = hint;
        button.append(uiIcon(document, icon));
        button.addEventListener('click', () => setMode(value));
        controls.append(button);
        buttons.set(value, button);
    }
    function announce(notify = true) {
        element.dataset.ddnDrawerMode = mode;
        rail.hidden = mode !== 'hidden';
        reopen.setAttribute('aria-expanded', String(mode !== 'hidden'));
        for (const [value, button] of buttons)
            button.hidden = value === mode;
        options.onMode?.(mode);
        if (notify)
            container.dispatchEvent(new window.CustomEvent('ddn:drawer-change', { bubbles: true, detail: { id, drawer } }));
    }
    function setMode(next) {
        if (disposed)
            return;
        if (mode === next) {
            detached?.focus();
            return;
        }
        moving = true;
        detached?.dock();
        detached = undefined;
        moving = false;
        mode = next;
        element.hidden = next === 'hidden';
        if (next === 'floating' || next === 'popout') {
            const detachOptions = { title, name: windowKey, width: options.width ?? 400, hostClass: options.hostClass ?? 'ddn-viewer', ...(options.onKeydown ? { onKeydown: options.onKeydown } : {}), onReturn() {
                    if (disposed || moving)
                        return;
                    detached = undefined;
                    mode = 'docked';
                    element.hidden = false;
                    announce();
                } };
            detached = next === 'popout' ? popOut(element, detachOptions) : undefined;
            if (next === 'popout' && !detached) {
                mode = 'floating';
                options.onBlocked?.();
            }
            detached ??= floatPanel(element, detachOptions);
        }
        if (next === 'hidden')
            options.onHide?.();
        announce();
    }
    reopen.addEventListener('click', () => { setMode('docked'); element.querySelector('input,button')?.focus(); });
    const observer = new window.MutationObserver(() => { if (!container.isConnected)
        drawer.destroy(); });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    const drawer = { element, get mode() { return mode; }, get detached() { return detached; }, setMode,
        setHeader(header) { header.append(controls); },
        destroy() { if (disposed)
            return; disposed = true; observer.disconnect(); moving = true; detached?.dock(); detached = undefined; rail.remove(); controls.remove(); entries?.delete(id); delete element.dataset.ddnDrawer; delete element.dataset.ddnDrawerMode; },
    };
    entries.set(id, drawer);
    drawer.setHeader(options.header);
    announce(false);
    return drawer;
}
//# sourceMappingURL=drawer.js.map