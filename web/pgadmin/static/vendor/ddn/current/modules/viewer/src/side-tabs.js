import { uiIcon } from './ui-icons.js';
let serial = 0;
const CSS = `.ddn-panel-sections[hidden]{display:none!important}.ddn-panel-sections{display:grid;grid-template-columns:88px minmax(0,1fr);gap:8px;min-width:0}.ddn-side-tabs{display:flex;flex-direction:column;gap:3px;align-items:stretch;align-self:start;position:sticky;top:40px;min-width:0;border-right:1px solid var(--ddn-ui-border);padding-right:6px}.ddn-viewer .ddn-side-tabs[role=tablist] button,.ddn-side-tabs[role=tablist] button{display:flex;flex-direction:column;justify-content:center;align-items:center;gap:4px;margin:0;width:100%;padding:7px 4px;min-height:44px;border:1px solid transparent;border-radius:7px;background:transparent;color:var(--ddn-ui-muted);font:500 10px/1.3 system-ui,sans-serif;text-align:center;overflow-wrap:normal;word-break:normal;hyphens:none;cursor:pointer}.ddn-side-tabs[role=tablist] button[aria-selected=true]{color:var(--ddn-ui-accent);border-color:color-mix(in srgb,var(--ddn-ui-accent) 45%,transparent);background:color-mix(in srgb,var(--ddn-ui-accent) 12%,var(--ddn-ui-surface))}.ddn-side-tabs[role=tablist] button:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:-2px}.ddn-side-tabs small{font-size:9px;opacity:.8}.ddn-panel-section{min-width:0}.ddn-panel-section>[hidden],.ddn-panel-section[hidden]{display:none!important}.ddn-side-tabs svg{width:16px;height:16px}.ddn-side-tab-label{display:block;max-width:100%;white-space:normal;text-wrap:balance}.ddn-side-tabs svg{flex:none}`;
/** Accessible vertical navigation shared by palettes, inspector sections and navigator filters. */
export function sideTabs(container, label, tabs, selected, onSelect) {
    const document = container.ownerDocument;
    if (!document.querySelector('style[data-ddn-side-tabs]')) {
        const style = document.createElement('style');
        style.dataset.ddnSideTabs = '';
        style.textContent = CSS;
        document.head.append(style);
    }
    const element = document.createElement('div');
    element.className = 'ddn-side-tabs';
    element.setAttribute('role', 'tablist');
    element.setAttribute('aria-label', label);
    element.setAttribute('aria-orientation', 'vertical');
    const group = 'ddn-sections-' + (++serial), buttons = new Map();
    function choose(id, notify = true) { selected = id; for (const [key, button] of buttons) {
        button.setAttribute('aria-selected', String(key === id));
        button.tabIndex = key === id ? 0 : -1;
    } if (notify)
        onSelect(id); }
    for (const tab of tabs) {
        const button = document.createElement('button');
        button.type = 'button';
        button.id = group + '-' + tab.id.replace(/[^\w-]/g, '-');
        button.setAttribute('role', 'tab');
        button.setAttribute('aria-label', tab.label);
        button.title = tab.label + (tab.count === undefined ? '' : ` · ${tab.count} available`);
        const label = document.createElement('span');
        label.className = 'ddn-side-tab-label';
        label.textContent = tab.label;
        button.append(uiIcon(document, tab.icon ?? 'grid'), label);
        if (tab.count !== undefined) {
            const count = document.createElement('small');
            count.textContent = String(tab.count);
            button.append(count);
        }
        button.addEventListener('click', () => choose(tab.id));
        buttons.set(tab.id, button);
        element.append(button);
    }
    element.addEventListener('keydown', event => { if (!['ArrowUp', 'ArrowDown', 'Home', 'End'].includes(event.key))
        return; const keys = [...buttons.keys()], index = keys.indexOf(selected); event.preventDefault(); const next = event.key === 'Home' ? 0 : event.key === 'End' ? keys.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + keys.length) % keys.length; const id = keys[next]; if (id) {
        choose(id);
        buttons.get(id).focus();
    } });
    choose(selected, false);
    container.append(element);
    return { element, select: (id) => choose(id), connect(panel) { panel.setAttribute('role', 'tabpanel'); panel.id = group + '-panel'; for (const button of buttons.values())
            button.setAttribute('aria-controls', panel.id); panel.setAttribute('aria-labelledby', buttons.get(selected)?.id ?? ''); }, label(panel) { panel.setAttribute('aria-labelledby', buttons.get(selected)?.id ?? ''); } };
}
//# sourceMappingURL=side-tabs.js.map