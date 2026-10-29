const enabledOf = (item) => { try {
    return item.enabled ? item.enabled() : true;
}
catch {
    return false;
} };
/** A one-level popup menu anchored to a control (for example the status-bar zoom level). */
export function openPopupMenu(anchor, items, label, onError) {
    const document = anchor.ownerDocument, view = document.defaultView;
    document.querySelector('.app-popup-menu')?.remove();
    const menu = document.createElement('div');
    menu.className = 'app-menu app-popup-menu';
    menu.setAttribute('role', 'menu');
    menu.setAttribute('aria-label', label);
    menu.style.position = 'fixed';
    const close = (focus = true) => { menu.remove(); document.removeEventListener('pointerdown', outside, true); anchor.setAttribute('aria-expanded', 'false'); if (focus)
        anchor.focus(); };
    const outside = (event) => { if (!(event.target instanceof Node) || !menu.contains(event.target) && event.target !== anchor)
        close(false); };
    for (const item of items) {
        if (item.kind === 'separator') {
            const rule = document.createElement('hr');
            rule.setAttribute('role', 'separator');
            menu.append(rule);
            continue;
        }
        if (item.kind === 'heading' || item.kind === 'submenu')
            continue;
        const button = document.createElement('button');
        button.type = 'button';
        button.tabIndex = -1;
        const checked = item.checked?.();
        button.setAttribute('role', checked === undefined ? 'menuitem' : 'menuitemradio');
        if (checked !== undefined)
            button.setAttribute('aria-checked', String(checked));
        button.setAttribute('aria-label', item.label);
        const mark = document.createElement('span');
        mark.className = 'app-menu-check';
        mark.textContent = checked ? '•' : '';
        const text = document.createElement('span');
        text.className = 'app-menu-label';
        text.textContent = item.label;
        button.append(mark, text);
        if (item.shortcut) {
            const kbd = document.createElement('kbd');
            kbd.textContent = item.shortcut;
            button.append(kbd);
        }
        if (!enabledOf(item))
            button.setAttribute('aria-disabled', 'true');
        button.addEventListener('click', () => { if (button.getAttribute('aria-disabled') === 'true')
            return; close(); if (item.run)
            Promise.resolve().then(item.run).catch(onError); });
        menu.append(button);
    }
    menu.addEventListener('keydown', event => {
        const buttons = [...menu.querySelectorAll('button')], index = buttons.indexOf(document.activeElement);
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            buttons[(index + (event.key === 'ArrowDown' ? 1 : -1) + buttons.length) % buttons.length]?.focus();
        }
        else if (event.key === 'Escape' || event.key === 'Tab') {
            event.preventDefault();
            close();
        }
    });
    document.body.append(menu);
    const a = anchor.getBoundingClientRect(), m = menu.getBoundingClientRect();
    menu.style.left = Math.max(4, Math.min(a.right - m.width, view.innerWidth - m.width - 4)) + 'px';
    menu.style.top = (a.top - m.height - 4 >= 4 ? a.top - m.height - 4 : Math.min(a.bottom + 4, view.innerHeight - m.height - 4)) + 'px';
    anchor.setAttribute('aria-expanded', 'true');
    document.addEventListener('pointerdown', outside, true);
    (menu.querySelector('[aria-checked=true]') ?? menu.querySelector('button'))?.focus();
}
export function createMenuBar(document, specs, options) {
    const bar = document.createElement('div');
    bar.className = 'app-menubar';
    bar.setAttribute('role', 'menubar');
    bar.setAttribute('aria-label', options.label);
    const tops = [];
    let openIndex = -1;
    const closeSubmenus = (panel) => {
        for (const sub of panel.querySelectorAll('.app-submenu'))
            sub.hidden = true;
        for (const trigger of panel.querySelectorAll('[aria-haspopup=menu]'))
            trigger.setAttribute('aria-expanded', 'false');
    };
    function close(focusTop = false) {
        if (openIndex < 0)
            return;
        const top = tops[openIndex];
        top.panel.hidden = true;
        closeSubmenus(top.panel);
        top.button.setAttribute('aria-expanded', 'false');
        if (focusTop)
            top.button.focus();
        openIndex = -1;
        bar.removeAttribute('data-open');
    }
    const itemsOf = (panel) => [...panel.children].flatMap(child => child.matches('[role^=menuitem]') ? [child] : child.classList.contains('app-submenu-host') ? [child.firstElementChild] : []);
    function run(action) { close(); if (action)
        Promise.resolve().then(action).catch(options.onError); }
    function render(panel, items) {
        panel.replaceChildren();
        for (const item of items) {
            if (item.kind === 'separator') {
                const rule = document.createElement('hr');
                rule.setAttribute('role', 'separator');
                panel.append(rule);
                continue;
            }
            if (item.kind === 'heading') {
                const head = document.createElement('div');
                head.className = 'app-menu-head';
                head.setAttribute('role', 'presentation');
                head.textContent = item.label;
                panel.append(head);
                continue;
            }
            const button = document.createElement('button');
            button.type = 'button';
            button.tabIndex = -1;
            button.setAttribute('aria-label', item.label);
            const enabled = enabledOf(item);
            if (!enabled) {
                button.setAttribute('aria-disabled', 'true');
                if (item.hint)
                    button.title = item.hint;
            }
            const mark = document.createElement('span');
            mark.className = 'app-menu-check';
            mark.setAttribute('aria-hidden', 'true');
            const text = document.createElement('span');
            text.className = 'app-menu-label';
            text.textContent = item.label;
            button.append(mark, text);
            if (item.kind === 'submenu') {
                button.setAttribute('role', 'menuitem');
                button.setAttribute('aria-haspopup', 'menu');
                button.setAttribute('aria-expanded', 'false');
                const arrow = document.createElement('span');
                arrow.className = 'app-menu-arrow';
                arrow.setAttribute('aria-hidden', 'true');
                arrow.textContent = '›';
                button.append(arrow);
                const host = document.createElement('div');
                host.className = 'app-submenu-host';
                const sub = document.createElement('div');
                sub.className = 'app-menu app-submenu';
                sub.setAttribute('role', 'menu');
                sub.setAttribute('aria-label', item.label);
                sub.hidden = true;
                host.append(button, sub);
                panel.append(host);
                const openSub = (focus) => {
                    if (!enabledOf(item))
                        return;
                    for (const other of panel.querySelectorAll(':scope > .app-submenu-host > .app-submenu'))
                        if (other !== sub) {
                            other.hidden = true;
                            other.previousElementSibling?.setAttribute('aria-expanded', 'false');
                        }
                    render(sub, item.items());
                    sub.hidden = false;
                    button.setAttribute('aria-expanded', 'true');
                    sub.removeAttribute('data-flip');
                    const bounds = sub.getBoundingClientRect(), view = document.defaultView;
                    if (bounds.right > view.innerWidth - 4)
                        sub.dataset.flip = '';
                    if (focus)
                        itemsOf(sub)[0]?.focus();
                };
                button.addEventListener('click', () => openSub(true));
                button.addEventListener('pointerenter', () => openSub(false));
                button.addEventListener('keydown', event => { if (event.key === 'ArrowRight' || event.key === 'Enter' || event.key === ' ') {
                    event.preventDefault();
                    event.stopPropagation();
                    openSub(true);
                } });
                continue;
            }
            const checked = item.checked?.();
            button.setAttribute('role', checked === undefined ? 'menuitem' : item.radio ? 'menuitemradio' : 'menuitemcheckbox');
            if (checked !== undefined) {
                button.setAttribute('aria-checked', String(checked));
                mark.textContent = checked ? (item.radio ? '•' : '✓') : '';
            }
            if (item.badge) {
                const badge = document.createElement('span');
                badge.className = 'app-menu-badge';
                badge.textContent = item.badge;
                button.append(badge);
            }
            if (item.shortcut) {
                const kbd = document.createElement('kbd');
                kbd.textContent = item.shortcut;
                button.append(kbd);
            }
            button.addEventListener('pointerenter', () => { for (const other of panel.querySelectorAll(':scope > .app-submenu-host > .app-submenu')) {
                other.hidden = true;
                other.previousElementSibling?.setAttribute('aria-expanded', 'false');
            } });
            button.addEventListener('click', () => { if (button.getAttribute('aria-disabled') !== 'true')
                run(item.run); });
            panel.append(button);
        }
    }
    function open(index, focusFirst) {
        if (openIndex !== index)
            close();
        const top = tops[index];
        if (!top)
            return;
        openIndex = index;
        render(top.panel, top.spec.items());
        top.panel.hidden = false;
        top.button.setAttribute('aria-expanded', 'true');
        bar.dataset.open = '';
        top.panel.style.left = '';
        const bounds = top.panel.getBoundingClientRect(), width = document.defaultView.innerWidth;
        if (bounds.right > width - 4)
            top.panel.style.left = Math.max(-bounds.left + 4, width - 4 - bounds.right) + 'px';
        if (focusFirst)
            itemsOf(top.panel)[0]?.focus();
        else
            top.button.focus();
    }
    specs.forEach((spec, index) => {
        const host = document.createElement('div');
        host.className = 'app-menu-host';
        const button = document.createElement('button');
        button.type = 'button';
        button.textContent = spec.label;
        button.tabIndex = index === 0 ? 0 : -1;
        button.setAttribute('role', 'menuitem');
        button.setAttribute('aria-haspopup', 'menu');
        button.setAttribute('aria-expanded', 'false');
        const panel = document.createElement('div');
        panel.className = 'app-menu';
        panel.setAttribute('role', 'menu');
        panel.setAttribute('aria-label', spec.label);
        panel.hidden = true;
        host.append(button, panel);
        bar.append(host);
        tops.push({ button, panel, spec });
        button.addEventListener('click', () => { if (openIndex === index)
            close();
        else
            open(index, false); });
        button.addEventListener('pointerenter', () => { if (openIndex >= 0 && openIndex !== index)
            open(index, false); });
        button.addEventListener('focus', () => { for (const other of tops)
            other.button.tabIndex = other.button === button ? 0 : -1; });
        button.addEventListener('keydown', event => {
            const move = (step) => { const next = (index + step + tops.length) % tops.length; if (openIndex >= 0)
                open(next, true);
            else
                tops[next].button.focus(); };
            if (event.key === 'ArrowRight') {
                event.preventDefault();
                move(1);
            }
            else if (event.key === 'ArrowLeft') {
                event.preventDefault();
                move(-1);
            }
            else if (event.key === 'ArrowDown' || event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                open(index, true);
            }
            else if (event.key === 'ArrowUp') {
                event.preventDefault();
                open(index, false);
                const items = itemsOf(panel);
                items.at(-1)?.focus();
            }
            else if (event.key === 'Escape' && openIndex >= 0) {
                event.preventDefault();
                close(true);
            }
        });
        panel.addEventListener('keydown', event => {
            const current = event.target.closest('[role^=menuitem]');
            const container = current?.closest('.app-menu');
            if (!current || !container)
                return;
            const items = itemsOf(container), position = items.indexOf(current);
            const isSub = container.classList.contains('app-submenu');
            if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
                event.preventDefault();
                event.stopPropagation();
                items[(position + (event.key === 'ArrowDown' ? 1 : -1) + items.length) % items.length]?.focus();
            }
            else if (event.key === 'Home' || event.key === 'End') {
                event.preventDefault();
                items[event.key === 'Home' ? 0 : items.length - 1]?.focus();
            }
            else if (event.key === 'ArrowLeft') {
                event.preventDefault();
                event.stopPropagation();
                if (isSub) {
                    container.hidden = true;
                    const trigger = container.previousElementSibling;
                    trigger?.setAttribute('aria-expanded', 'false');
                    trigger?.focus();
                }
                else
                    open((index - 1 + tops.length) % tops.length, true);
            }
            else if (event.key === 'ArrowRight' && current.getAttribute('aria-haspopup') !== 'menu') {
                event.preventDefault();
                event.stopPropagation();
                open((index + 1) % tops.length, true);
            }
            else if (event.key === 'Escape') {
                event.preventDefault();
                event.stopPropagation();
                if (isSub) {
                    container.hidden = true;
                    const trigger = container.previousElementSibling;
                    trigger?.setAttribute('aria-expanded', 'false');
                    trigger?.focus();
                }
                else
                    close(true);
            }
            else if (event.key === 'Tab')
                close();
            else if (event.key.length === 1 && /\S/.test(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
                const letter = event.key.toLowerCase(), order = [...items.slice(position + 1), ...items.slice(0, position + 1)];
                order.find(item => (item.getAttribute('aria-label') ?? '').toLowerCase().startsWith(letter))?.focus();
            }
        });
    });
    document.addEventListener('pointerdown', event => { if (openIndex >= 0 && !(event.target instanceof Node && bar.contains(event.target)))
        close(); });
    return {
        element: bar, close: () => close(), isOpen: () => openIndex >= 0,
        refresh() {
            if (openIndex < 0)
                return;
            const top = tops[openIndex];
            if (top.panel.querySelector('.app-submenu:not([hidden])'))
                return;
            const focused = itemsOf(top.panel).indexOf(document.activeElement);
            render(top.panel, top.spec.items());
            if (focused >= 0)
                itemsOf(top.panel)[focused]?.focus();
        },
    };
}
//# sourceMappingURL=menus.js.map