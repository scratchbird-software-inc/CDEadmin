/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-646a07aa4889","version":"ddn-next-1","releaseHash":"a013ac52c7b3173ca4a5c5558fb8bac7b899854da330646dcd39702d0d86b778","dependencies":[],"modules":[{"id":"viewer/src/dialogs.js","bytes":25837,"sha256":"ed28cdaa48d5c91d9a22afda095dbb0462543827e190fc0225268d4191417728","dependencies":["viewer/src/ui-theme.js","viewer/src/popout.js","viewer/src/resize-grip.js"]},{"id":"viewer/src/drawer.js","bytes":7216,"sha256":"6586147163680130b240f098c9708353c65e2877902191f708863776340f509c","dependencies":["viewer/src/popout.js","viewer/src/ui-icons.js"]},{"id":"viewer/src/fonts.js","bytes":11501,"sha256":"9b6eac822cd0201609e40bd49994458e5494939ae6699fccf2b4646942f7a4ba","dependencies":[]},{"id":"viewer/src/popout.js","bytes":14544,"sha256":"c0252a7badad9fc90347214a336e18b3056bc683f851952681c1893e7673aa7d","dependencies":["viewer/src/fonts.js","viewer/src/ui-theme.js","viewer/src/resize-grip.js"]},{"id":"viewer/src/resize-grip.js","bytes":3906,"sha256":"57e6ec411f9c528273a804fc00b48892c5098b7814fea413bdfea47fbc8ea0d8","dependencies":[]},{"id":"viewer/src/texture.js","bytes":5449,"sha256":"98860f0894ae37bf73fac7c3fcdab47803f2458ad55d82c76137778d982cda91","dependencies":[]},{"id":"viewer/src/ui-commands.js","bytes":2000,"sha256":"a96a027c68d4261c6a7d2b1824e60cf33ba06e1a16385d7824b9724d642cbdca","dependencies":[]},{"id":"viewer/src/ui-icons.js","bytes":2742,"sha256":"b5246e3df9fea99b3e950a8b146003da397887a813fff448de7a7277e6d674cc","dependencies":[]},{"id":"viewer/src/ui-theme.js","bytes":9820,"sha256":"8b7cc6f7e3467857eec804cfec84a7879889cd4ca2d53d116c55c88b1d7a37af","dependencies":[]}],"hash":"be0fbb90196ccf976ce231543ded8c2c207c9918d85f12ad8df7a7008ab0c35a"},{"viewer/src/dialogs.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.createStandardDialog = createStandardDialog;
exports.syncNumberField = syncNumberField;
exports.numberField = numberField;
exports.syncColourField = syncColourField;
exports.colourField = colourField;
const ui_theme_js_1 = require("viewer/src/ui-theme.js");
const popout_js_1 = require("viewer/src/popout.js");
const resize_grip_js_1 = require("viewer/src/resize-grip.js");
const stacks = new WeakMap();
const dialogHosts = new WeakMap();
let nextId = 0;
function focusable(element) {
    return [...element.querySelectorAll('button,input,textarea,select,a[href],[tabindex]')]
        .filter(item => item.tabIndex >= 0 && !item.matches(':disabled') && !item.closest('[inert]') && item.getClientRects().length > 0 && item.ownerDocument.defaultView?.getComputedStyle(item).visibility !== 'hidden');
}
function createStandardDialog(host, options) {
    const document = host.ownerDocument, window = document.defaultView, modal = options.modal !== false;
    const stack = stacks.get(document) ?? [];
    stacks.set(document, stack);
    const containing = host.closest('.ddn-ui-dialog') ?? document.activeElement?.closest('.ddn-ui-dialog');
    const parent = stack.find(item => item.element === containing);
    host = host.closest('.ddn-ui-dialog') && containing && dialogHosts.get(containing) || host;
    (0, ui_theme_js_1.installUITheme)(host);
    const previousFocus = document.activeElement;
    const layer = document.createElement('div');
    layer.className = 'ddn-ui-layer';
    layer.dataset.modal = String(modal);
    const element = document.createElement('section');
    element.className = 'ddn-ui-dialog';
    element.tabIndex = -1;
    element.setAttribute('role', 'dialog');
    if (modal)
        element.setAttribute('aria-modal', 'true');
    const header = document.createElement('header'), heading = document.createElement('h3');
    header.className = 'ddn-ui-dialog-header';
    heading.id = `ddn-ui-dialog-${++nextId}`;
    element.setAttribute('aria-labelledby', heading.id);
    let move;
    if (options.movable !== false) {
        move = document.createElement('button');
        move.type = 'button';
        move.className = 'ddn-ui-dialog-move';
        const label = document.createElement('span');
        label.id = heading.id;
        label.textContent = options.title;
        heading.removeAttribute('id');
        move.append(label);
        move.setAttribute('aria-label', 'Move ' + options.title);
        move.title = 'Drag to move, or focus this title and use the arrow keys. Shift moves farther.';
        heading.append(move);
    }
    else
        heading.textContent = options.title;
    const dismiss = document.createElement('button');
    dismiss.type = 'button';
    dismiss.className = 'ddn-ui-dialog-dismiss';
    dismiss.textContent = '×';
    dismiss.setAttribute('aria-label', 'Close ' + options.title);
    let popped, detach;
    if (!modal) {
        detach = document.createElement('button');
        detach.type = 'button';
        detach.className = 'ddn-ui-dialog-popout';
        detach.textContent = '⧉';
        detach.setAttribute('aria-label', 'Pop out ' + options.title);
        detach.title = 'Open in its own window, for example on a second monitor';
        detach.addEventListener('click', () => {
            if (popped) {
                popped.dock();
                return;
            }
            popped = (0, popout_js_1.popOut)(element, { title: options.title, name: 'dialog-' + options.title, width: 460, height: 620, onKeydown: keydown, onReturn() {
                    popped = undefined;
                    detach.textContent = '⧉';
                    detach.setAttribute('aria-label', 'Pop out ' + options.title);
                    detach.title = 'Open in its own window, for example on a second monitor';
                    if (!closed) {
                        layer.hidden = false;
                        clamp();
                    }
                } });
            if (!popped) {
                showError('The browser blocked the new window. Allow pop-ups for this page to detach editors.');
                return;
            }
            layer.hidden = true;
            detach.textContent = '↩';
            detach.setAttribute('aria-label', 'Return ' + options.title + ' to the page');
            detach.title = 'Return this editor to the page';
        });
        header.append(heading, detach, dismiss);
    }
    else
        header.append(heading, dismiss);
    const body = document.createElement('div');
    body.className = 'ddn-ui-dialog-body';
    const error = document.createElement('div');
    error.className = 'ddn-ui-dialog-error';
    error.setAttribute('role', 'alert');
    error.hidden = true;
    const footer = document.createElement('footer');
    footer.className = 'ddn-ui-dialog-footer';
    const cancel = document.createElement('button');
    cancel.type = 'button';
    cancel.textContent = options.cancelLabel ?? (options.onApply ? 'Cancel' : 'Close');
    footer.append(cancel);
    let applying = false, closing = false;
    const requestClose = () => {
        if (closed || closing || applying && options.lockWhileApplying)
            return;
        if (!options.beforeClose) {
            close();
            return;
        }
        closing = true;
        cancel.disabled = dismiss.disabled = true;
        element.setAttribute('aria-busy', 'true');
        void Promise.resolve().then(options.beforeClose).then(close).catch(failure => {
            if (!closed)
                showError(failure);
        }).finally(() => {
            closing = false;
            if (!closed) {
                cancel.disabled = dismiss.disabled = false;
                element.removeAttribute('aria-busy');
            }
        });
    };
    let closed = false, positioned = false, drag;
    const activeModal = () => [...stack].reverse().find(item => item.modal);
    const focusInside = () => (focusable(body)[0] ?? focusable(element)[0] ?? element).focus({ preventScroll: true });
    function updateStack() {
        const active = activeModal();
        for (const [index, item] of stack.entries()) {
            item.layer.style.zIndex = String(1000 + index);
            item.element.inert = !!active && item !== active;
            if (item.element.inert)
                item.element.setAttribute('aria-hidden', 'true');
            else
                item.element.removeAttribute('aria-hidden');
        }
    }
    function bringForward() {
        if (activeModal() || stack.at(-1) === state)
            return;
        stack.splice(stack.indexOf(state), 1);
        stack.push(state);
        updateStack();
    }
    function showError(message) {
        error.textContent = message == null ? '' : message instanceof Error ? message.message : String(message);
        error.hidden = !error.textContent;
    }
    function position(left, top) {
        if (closed || popped)
            return;
        positioned = true;
        layer.dataset.positioned = '';
        const frame = layer.getBoundingClientRect(), bounds = element.getBoundingClientRect(), gap = parseFloat(window.getComputedStyle(layer).paddingLeft) || 0;
        element.style.left = Math.max(gap, Math.min(left, frame.width - bounds.width - gap)) + 'px';
        element.style.top = Math.max(gap, Math.min(top, frame.height - bounds.height - gap)) + 'px';
    }
    function clamp() {
        if (positioned)
            position(parseFloat(element.style.left), parseFloat(element.style.top));
    }
    function finishDrag() {
        if (drag && move?.hasPointerCapture(drag.id))
            move.releasePointerCapture(drag.id);
        drag = undefined;
        move?.classList.remove('ddn-ui-dragging');
    }
    function close() {
        if (closed)
            return;
        closed = true;
        popped?.dock();
        let heldFocus = element.contains(document.activeElement);
        for (const child of [...stack].reverse())
            if (child.parent === state)
                child.close();
        heldFocus ||= element.contains(document.activeElement);
        const index = stack.indexOf(state);
        if (index >= 0)
            stack.splice(index, 1);
        observer.disconnect();
        resizeObserver?.disconnect();
        window.removeEventListener('resize', clamp);
        document.removeEventListener('keydown', keydown, true);
        document.removeEventListener('focusin', focusin, true);
        finishDrag();
        grip.dispose();
        layer.remove();
        updateStack();
        const active = activeModal();
        if (modal || heldFocus) {
            if (previousFocus?.isConnected && !previousFocus.closest('[inert]') && (!active || active.element.contains(previousFocus)))
                previousFocus.focus({ preventScroll: true });
            else if (active)
                (focusable(active.element)[0] ?? active.element).focus({ preventScroll: true });
        }
        options.onClose?.();
    }
    const state = { element, host, layer, modal, ...(parent ? { parent } : {}), close };
    function keydown(event) {
        const active = activeModal();
        if (active ? active !== state : !element.contains(event.target))
            return;
        if (event.key === 'Escape') {
            event.preventDefault();
            event.stopImmediatePropagation();
            requestClose();
        }
        else if (event.key === 'Tab' && modal) {
            const controls = focusable(element), first = controls[0], last = controls.at(-1);
            if (!first) {
                event.preventDefault();
                element.focus();
            }
            else if (event.shiftKey && (document.activeElement === first || !element.contains(document.activeElement))) {
                event.preventDefault();
                last.focus();
            }
            else if (!event.shiftKey && (document.activeElement === last || !element.contains(document.activeElement))) {
                event.preventDefault();
                first.focus();
            }
        }
    }
    function focusin(event) {
        if (element.contains(event.target))
            bringForward();
        else if (activeModal() === state)
            focusInside();
    }
    element.addEventListener('pointerdown', bringForward);
    move?.addEventListener('pointerdown', event => {
        if (event.button !== 0)
            return;
        bringForward();
        const bounds = element.getBoundingClientRect(), frame = layer.getBoundingClientRect();
        drag = { id: event.pointerId, x: event.clientX, y: event.clientY, left: bounds.left - frame.left, top: bounds.top - frame.top };
        move.setPointerCapture(event.pointerId);
        move.classList.add('ddn-ui-dragging');
        event.preventDefault();
        move.focus({ preventScroll: true });
    });
    move?.addEventListener('pointermove', event => {
        if (drag?.id === event.pointerId)
            position(drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y);
    });
    move?.addEventListener('pointerup', finishDrag);
    move?.addEventListener('pointercancel', finishDrag);
    move?.addEventListener('lostpointercapture', finishDrag);
    move?.addEventListener('keydown', event => {
        const offsets = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }, offset = offsets[event.key];
        if (!offset)
            return;
        event.preventDefault();
        event.stopPropagation();
        const bounds = element.getBoundingClientRect(), frame = layer.getBoundingClientRect(), step = event.shiftKey ? 40 : 10;
        position(bounds.left - frame.left + offset[0] * step, bounds.top - frame.top + offset[1] * step);
    });
    cancel.addEventListener('click', requestClose);
    dismiss.addEventListener('click', requestClose);
    let applyButton;
    if (options.onApply) {
        applyButton = document.createElement('button');
        applyButton.type = 'button';
        applyButton.textContent = options.applyLabel ?? 'Apply';
        applyButton.dataset.ddnApply = '';
        applyButton.addEventListener('click', async () => {
            if (closed || applyButton.disabled)
                return;
            showError('');
            applying = true;
            applyButton.disabled = true;
            element.setAttribute('aria-busy', 'true');
            if (options.lockWhileApplying)
                cancel.disabled = dismiss.disabled = true;
            try {
                await options.onApply();
                close();
            }
            catch (failure) {
                if (!closed)
                    showError(failure);
            }
            finally {
                applying = false;
                applyButton.disabled = false;
                cancel.disabled = dismiss.disabled = false;
                element.removeAttribute('aria-busy');
            }
        });
        footer.append(applyButton);
    }
    stack.push(state);
    dialogHosts.set(element, host);
    element.append(header, body, error);
    const grip = (0, resize_grip_js_1.resizeGrip)(element, { label: options.title, size: () => element.getBoundingClientRect(), start() {
            bringForward();
            const bounds = element.getBoundingClientRect(), frame = layer.getBoundingClientRect();
            position(bounds.left - frame.left, bounds.top - frame.top);
        }, resize(width, height) {
            if (closed || popped)
                return;
            const frame = layer.getBoundingClientRect(), gap = parseFloat(window.getComputedStyle(layer).paddingLeft) || 0;
            const maxWidth = Math.max(0, frame.width - parseFloat(element.style.left) - gap), maxHeight = Math.max(0, frame.height - parseFloat(element.style.top) - gap);
            element.dataset.ddnResized = '';
            element.style.width = Math.min(maxWidth, Math.max(Math.min(280, maxWidth), width)) + 'px';
            const minHeight = Math.min(maxHeight, Math.max(180, header.getBoundingClientRect().height + footer.getBoundingClientRect().height + 80));
            element.style.height = Math.min(maxHeight, Math.max(minHeight, height)) + 'px';
            clamp();
        } });
    element.append(footer);
    layer.append(element);
    host.append(layer);
    updateStack();
    document.addEventListener('keydown', keydown, true);
    document.addEventListener('focusin', focusin, true);
    window.addEventListener('resize', clamp);
    const observer = new window.MutationObserver(() => {
        if (!element.isConnected)
            close();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    const resizeObserver = typeof window.ResizeObserver === 'function' ? new window.ResizeObserver(clamp) : undefined;
    resizeObserver?.observe(element);
    if (!modal) {
        const bounds = host.getBoundingClientRect(), frame = layer.getBoundingClientRect();
        position(bounds.right - frame.left - element.getBoundingClientRect().width - 12, bounds.top - frame.top + 12);
    }
    window.queueMicrotask(() => {
        if (!closed && !element.inert && element.isConnected)
            focusInside();
    });
    return { element, body, footer, ...(applyButton ? { applyButton } : {}), close, showError };
}
const numberSynchronizers = new WeakMap();
function syncNumberField(input) { numberSynchronizers.get(input)?.(); }
function numberField(container, label, value, options) {
    const { min, max, step = 1 } = options;
    if (!Number.isFinite(min) || !Number.isFinite(max) || min >= max || step !== 'any' && (!Number.isFinite(step) || step <= 0))
        throw Error('Numeric fields need finite increasing bounds and a positive step.');
    const document = container.ownerDocument, window = document.defaultView;
    (0, ui_theme_js_1.installUITheme)(container);
    const wrapper = document.createElement('div');
    wrapper.className = 'ddn-ui-number-field';
    const title = document.createElement('label');
    title.textContent = label;
    const row = document.createElement('div');
    row.className = 'ddn-ui-number-controls';
    const range = document.createElement('input');
    range.type = 'range';
    range.setAttribute('aria-label', label + ' slider');
    const input = document.createElement('input');
    input.type = 'number';
    input.setAttribute('aria-label', label);
    input.id = 'ddn-ui-number-' + (++nextId);
    title.htmlFor = input.id;
    for (const control of [range, input]) {
        control.min = String(min);
        control.max = String(max);
        control.step = String(step);
    }
    input.required = true;
    input.value = String(value);
    const sync = () => {
        if (Number.isFinite(input.valueAsNumber))
            range.value = input.value;
        input.setAttribute('aria-invalid', String(!input.checkValidity()));
    };
    numberSynchronizers.set(input, sync);
    sync();
    input.addEventListener('input', sync);
    input.addEventListener('change', sync);
    range.addEventListener('input', event => {
        event.stopPropagation();
        if (input.value === range.value)
            return;
        input.value = range.value;
        sync();
        input.dispatchEvent(new window.Event('input', { bubbles: true }));
    });
    row.append(range, input);
    wrapper.append(title, row);
    container.append(wrapper);
    return input;
}
function parseColour(value) {
    let hex = value.trim();
    if (hex.toLowerCase() === 'transparent')
        return { r: 0, g: 0, b: 0, a: 0 };
    if (/^#[\da-f]{3}$/i.test(hex))
        hex = '#' + [...hex.slice(1)].map(character => character.repeat(2)).join('');
    if (!/^#[\da-f]{6}(?:[\da-f]{2})?$/i.test(hex))
        return undefined;
    return { r: parseInt(hex.slice(1, 3), 16), g: parseInt(hex.slice(3, 5), 16), b: parseInt(hex.slice(5, 7), 16), a: hex.length === 9 ? parseInt(hex.slice(7, 9), 16) / 255 : 1 };
}
const byte = (value) => Math.round(value).toString(16).padStart(2, '0');
const hexColour = (colour) => '#' + byte(colour.r) + byte(colour.g) + byte(colour.b) + (colour.a < 1 ? byte(colour.a * 255) : '');
const synchronizers = new WeakMap();
function syncColourField(input) { synchronizers.get(input)?.(); }
function colourField(container, label, value, options = {}) {
    const document = container.ownerDocument, window = document.defaultView;
    (0, ui_theme_js_1.installUITheme)(container);
    const row = document.createElement('div');
    row.className = 'ddn-ui-colour-field';
    const wrapper = document.createElement('label');
    wrapper.append(document.createTextNode(label));
    const input = document.createElement('input');
    input.type = 'text';
    input.value = value;
    input.spellcheck = false;
    wrapper.append(input);
    const native = document.createElement('input');
    native.type = 'color';
    native.setAttribute('aria-label', label + ' picker');
    native.title = 'Choose RGB colour; use the palette or text field for transparency.';
    const palette = document.createElement('button');
    palette.type = 'button';
    palette.textContent = 'Palette';
    palette.setAttribute('aria-label', label + ' palette');
    const sync = () => { const colour = parseColour(input.value); native.value = colour ? '#' + byte(colour.r) + byte(colour.g) + byte(colour.b) : '#000000'; };
    const change = (text) => {
        if (input.value === text)
            return;
        input.value = text;
        sync();
        input.dispatchEvent(new window.Event('input', { bubbles: true }));
    };
    const chooseNative = () => { const text = input.value.trim(); change(native.value + (/^#[\da-f]{8}$/i.test(text) ? text.slice(7) : '')); };
    native.addEventListener('input', chooseNative);
    native.addEventListener('change', chooseNative);
    input.addEventListener('input', sync);
    input.addEventListener('change', sync);
    synchronizers.set(input, sync);
    sync();
    palette.addEventListener('click', () => {
        const initial = input.value;
        let draft = initial, colour = parseColour(initial) ?? { r: 0, g: 0, b: 0, a: 1 };
        const dialog = createStandardDialog(options.dialogHost ?? container, { title: label + ' palette', cancelLabel: 'Done' });
        const textField = (parent, title, type = 'text') => {
            const field = document.createElement('label');
            field.append(document.createTextNode(title));
            const control = document.createElement('input');
            control.type = type;
            field.append(control);
            parent.append(field);
            return control;
        };
        const hex = textField(dialog.body, 'Hex colour');
        hex.value = initial;
        hex.spellcheck = false;
        const picker = textField(dialog.body, 'RGB picker', 'color');
        const channels = document.createElement('div');
        channels.className = 'ddn-ui-colour-channels';
        dialog.body.append(channels);
        const red = numberField(channels, 'Red', colour.r, { min: 0, max: 255 }), green = numberField(channels, 'Green', colour.g, { min: 0, max: 255 }), blue = numberField(channels, 'Blue', colour.b, { min: 0, max: 255 }), alpha = numberField(channels, 'Alpha', colour.a, { min: 0, max: 1, step: .01 });
        alpha.step = 'any';
        const presets = document.createElement('div');
        presets.className = 'ddn-ui-colour-swatches';
        presets.setAttribute('role', 'group');
        presets.setAttribute('aria-label', 'Preset colours');
        const previews = document.createElement('div');
        previews.className = 'ddn-ui-colour-previews';
        function preview(title, value) {
            const block = document.createElement('div'), name = document.createElement('span');
            name.className = 'ddn-ui-colour-preview-label';
            name.textContent = title;
            const checkers = document.createElement('div');
            checkers.className = 'ddn-ui-colour-preview';
            const paint = document.createElement('span');
            paint.setAttribute('role', 'img');
            paint.setAttribute('aria-label', title + ' colour');
            paint.style.backgroundColor = parseColour(value) ? value : 'transparent';
            checkers.append(paint);
            block.append(name, checkers);
            previews.append(block);
            return paint;
        }
        preview('Current', initial);
        const proposed = preview('Preview', initial);
        function refresh(fromHex = false) {
            if (!fromHex) {
                draft = hexColour(colour);
                hex.value = draft;
            }
            red.value = String(colour.r);
            green.value = String(colour.g);
            blue.value = String(colour.b);
            alpha.value = String(colour.a);
            for (const channel of [red, green, blue, alpha])
                syncNumberField(channel);
            picker.value = '#' + byte(colour.r) + byte(colour.g) + byte(colour.b);
            proposed.style.backgroundColor = hexColour(colour);
            proposed.title = draft;
            hex.removeAttribute('aria-invalid');
            dialog.showError('');
        }
        hex.addEventListener('input', () => {
            draft = hex.value;
            const parsed = parseColour(draft);
            if (parsed) {
                colour = parsed;
                refresh(true);
                change(draft);
            }
            else {
                hex.setAttribute('aria-invalid', 'true');
                dialog.showError('Use #RGB, #RRGGBB, #RRGGBBAA or transparent.');
            }
        });
        for (const channel of [red, green, blue, alpha])
            channel.addEventListener('input', () => {
                if ([red, green, blue, alpha].some(control => control.value === '' || !control.checkValidity())) {
                    dialog.showError('RGB channels must be integers from 0 to 255; alpha must be from 0 to 1.');
                    return;
                }
                colour = { r: red.valueAsNumber, g: green.valueAsNumber, b: blue.valueAsNumber, a: alpha.valueAsNumber };
                refresh();
                change(draft);
            });
        picker.addEventListener('input', () => { colour = { ...parseColour(picker.value), a: colour.a }; refresh(); change(draft); });
        for (const value of ['#ffffff', '#000000', '#df4545', '#ef8f32', '#fff59d', '#54ab67', '#45a3da', '#955dcc', '#f6c4d2', '#b9e8dc', '#5b83b4', '#3b414b', '#e4c788', '#b4bac5', '#795548', 'transparent']) {
            const swatch = document.createElement('button');
            swatch.type = 'button';
            swatch.title = value;
            swatch.setAttribute('aria-label', 'Use ' + value);
            const paint = document.createElement('span');
            paint.style.backgroundColor = value;
            swatch.append(paint);
            swatch.addEventListener('click', () => { draft = value; hex.value = value; colour = parseColour(value); refresh(true); change(draft); });
            presets.append(swatch);
        }
        const reset = document.createElement('button');
        reset.type = 'button';
        reset.textContent = 'Reset colour';
        reset.addEventListener('click', () => { draft = initial; hex.value = initial; colour = parseColour(initial) ?? { r: 0, g: 0, b: 0, a: 1 }; refresh(true); change(initial); });
        dialog.footer.prepend(reset);
        dialog.body.append(presets, previews);
        refresh(true);
        if (!parseColour(initial))
            hex.setAttribute('aria-invalid', 'true');
    });
    row.append(wrapper, native, palette);
    container.append(row);
    return input;
}

},
"viewer/src/drawer.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.drawerFor = drawerFor;
exports.createDrawer = createDrawer;
const popout_js_1 = require("viewer/src/popout.js");
const ui_icons_js_1 = require("viewer/src/ui-icons.js");
let serial = 0;
const drawers = new WeakMap();
function drawerFor(container, id) { return container ? drawers.get(container)?.get(id) : undefined; }
const CSS = `.ddn-drawer-controls{display:inline-flex;gap:2px;margin-left:auto;align-items:center;flex:none}.ddn-viewer .ddn-drawer-controls button,.ddn-drawer-controls button{display:inline-flex!important;align-items:center;justify-content:center;width:25px!important;min-width:25px;min-height:26px;margin:0!important;padding:3px!important;border:1px solid transparent;border-radius:5px;color:var(--ddn-ui-muted);background:transparent;cursor:pointer}.ddn-drawer-controls button:hover{color:var(--ddn-ui-accent);background:color-mix(in srgb,var(--ddn-ui-accent) 12%,transparent)}.ddn-drawer-controls button:focus-visible,.ddn-drawer-rail button:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:1px}.ddn-drawer-controls button[hidden],.ddn-drawer-rail[hidden],[data-ddn-drawer][hidden]{display:none!important}.ddn-drawer-rail{position:absolute;z-index:8;top:112px;bottom:48px;left:0;pointer-events:none;display:flex;align-items:flex-start}.ddn-drawer-rail[data-side=right]{left:auto;right:0}.ddn-drawer-rail button{pointer-events:auto;writing-mode:vertical-rl;display:flex;align-items:center;gap:7px;border:1px solid var(--ddn-ui-border);border-radius:0 7px 7px 0;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);padding:10px 5px;font:600 11px system-ui,sans-serif;cursor:pointer;box-shadow:0 2px 6px #0002}.ddn-drawer-rail[data-side=right] button{border-radius:7px 0 0 7px}.ddn-drawer-rail[data-drawer=navigator]{top:245px}@media(max-width:760px){.ddn-drawer-rail{top:auto;bottom:36px}.ddn-drawer-rail[data-drawer=navigator]{top:auto;bottom:180px}}`;
function createDrawer(element, options) {
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
    reopen.append((0, ui_icons_js_1.uiIcon)(document, options.side === 'right' ? 'arrow-left' : 'arrow-right'), document.createTextNode(title));
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
        button.append((0, ui_icons_js_1.uiIcon)(document, icon));
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
            detached = next === 'popout' ? (0, popout_js_1.popOut)(element, detachOptions) : undefined;
            if (next === 'popout' && !detached) {
                mode = 'floating';
                options.onBlocked?.();
            }
            detached ??= (0, popout_js_1.floatPanel)(element, detachOptions);
        }
        if (next === 'hidden')
            options.onHide?.();
        announce();
    }
    reopen.addEventListener('click', () => { setMode('docked'); element.querySelector('input,button')?.focus(); });
    const observer = new window.MutationObserver(() => {
        if (!container.isConnected)
            drawer.destroy();
    });
    observer.observe(document.documentElement, { childList: true, subtree: true });
    const drawer = { element, get mode() { return mode; }, get detached() { return detached; }, setMode,
        setHeader(header) { header.append(controls); },
        destroy() {
            if (disposed)
                return;
            disposed = true;
            observer.disconnect();
            moving = true;
            detached?.dock();
            detached = undefined;
            rail.remove();
            controls.remove();
            entries?.delete(id);
            delete element.dataset.ddnDrawer;
            delete element.dataset.ddnDrawerMode;
        },
    };
    entries.set(id, drawer);
    drawer.setHeader(options.header);
    announce(false);
    return drawer;
}

},
"viewer/src/fonts.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.fontFamily = fontFamily;
exports.listFonts = listFonts;
exports.installFontResources = installFontResources;
exports.loadFontFile = loadFontFile;
exports.getFontResources = getFontResources;
exports.fontCSS = fontCSS;
const states = new WeakMap();
const MAX_FONT_BYTES = 16 * 1024 * 1024;
const MAX_FACES = 128;
const aliases = Object.freeze(Object.assign(Object.create(null), {
    sans: 'system-ui, sans-serif', serif: 'serif', mono: 'monospace', monospace: 'monospace', handwriting: 'cursive',
}));
const generics = new Set(['serif', 'sans-serif', 'monospace', 'cursive', 'fantasy', 'system-ui', 'ui-serif', 'ui-sans-serif', 'ui-monospace', 'ui-rounded', 'math']);
const standard = [
    { key: 'Inter', family: 'Inter', label: 'Inter', category: 'sans', source: 'standard', available: false, weights: ['100 900'], styles: ['normal', 'italic'] },
    { key: 'Source Serif 4', family: 'Source Serif 4', label: 'Source Serif 4', category: 'serif', source: 'standard', available: false, weights: ['200 900'], styles: ['normal', 'italic'] },
    { key: 'JetBrains Mono', family: 'JetBrains Mono', label: 'JetBrains Mono', category: 'monospace', source: 'standard', available: false, weights: ['100 800'], styles: ['normal', 'italic'] },
    { key: 'Caveat', family: 'Caveat', label: 'Caveat', category: 'handwriting', source: 'standard', available: false, weights: ['400 700'], styles: ['normal'] },
];
const system = [
    { key: 'sans', family: 'sans', label: 'System sans', category: 'sans', source: 'system', available: true, weights: ['400', '700'], styles: ['normal', 'italic'] },
    { key: 'serif', family: 'serif', label: 'System serif', category: 'serif', source: 'system', available: true, weights: ['400', '700'], styles: ['normal', 'italic'] },
    { key: 'mono', family: 'mono', label: 'System monospace', category: 'monospace', source: 'system', available: true, weights: ['400', '700'], styles: ['normal', 'italic'] },
    { key: 'handwriting', family: 'handwriting', label: 'System handwriting', category: 'handwriting', source: 'system', available: true, weights: ['400', '700'], styles: ['normal', 'italic'] },
];
function state(document) {
    let value = states.get(document);
    if (!value) {
        value = { installed: new Map(), pending: new Map() };
        states.set(document, value);
    }
    return value;
}
function quote(value) {
    return '"' + value.replace(/[\\"\x00-\x1f\x7f<>]/g, ch => '\\' + ch.codePointAt(0).toString(16) + ' ') + '"';
}
function names(key) {
    return key.split(',').map(name => name.trim().replace(/^(["'])(.*)\1$/, '$2')).filter(Boolean);
}
function fontFamily(key) {
    return aliases[key] ?? (names(key).map(name => generics.has(name) ? name : quote(name)).join(', ') || aliases.sans);
}
function familyName(value) {
    if (typeof value !== 'string' || !value.trim() || value.trim().length > 128 || /[\x00-\x1f\x7f,]/.test(value))
        throw new Error('Font family must contain 1–128 characters without controls or commas.');
    const name = value.trim();
    if (aliases[name.toLowerCase()] || generics.has(name.toLowerCase()))
        throw new Error('A local font cannot replace a generic font alias.');
    return name;
}
function fontWeight(value) {
    if (value === undefined || value === 'normal')
        return '400';
    if (value === 'bold')
        return '700';
    if (typeof value !== 'string' || !/^\d{1,4}(?: \d{1,4})?$/.test(value))
        throw new Error('Font weight must be a number or range from 1 to 1000.');
    const values = value.split(' ').map(Number);
    if (values.some(v => v < 1 || v > 1000) || (values.length === 2 && values[0] > values[1]))
        throw new Error('Font weight must be a number or ascending range from 1 to 1000.');
    return values.join(' ');
}
function format(bytes) {
    if (bytes.byteLength < 12 || bytes.byteLength > MAX_FONT_BYTES)
        throw new Error('Font files must be between 12 bytes and 16 MiB.');
    const magic = String.fromCharCode(...bytes.subarray(0, 4));
    if (magic === 'wOF2')
        return 'woff2';
    if (magic === 'wOFF')
        return 'woff';
    if (magic === 'OTTO')
        return 'otf';
    if (magic === '\x00\x01\x00\x00' || magic === 'true')
        return 'ttf';
    throw new Error('Select a WOFF2, WOFF, TTF or OTF font file.');
}
function decode(resource) {
    if (!resource || typeof resource !== 'object')
        throw new Error('Invalid font resource.');
    const family = familyName(resource.family), weight = fontWeight(resource.weight), style = resource.style ?? 'normal';
    if (!['normal', 'italic', 'oblique'].includes(style))
        throw new Error('Unsupported font style.');
    if (resource.category !== undefined && !['sans', 'serif', 'monospace', 'handwriting', 'custom'].includes(resource.category))
        throw new Error('Unsupported font category.');
    if (resource.source !== undefined && !['standard', 'custom'].includes(resource.source))
        throw new Error('Unsupported font source.');
    if (resource.license !== undefined && (typeof resource.license !== 'string' || resource.license.length > 65536 || /[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]/.test(resource.license)))
        throw new Error('Invalid font license notice.');
    if (typeof resource.dataURL !== 'string' || resource.dataURL.length > Math.ceil(MAX_FONT_BYTES / 3) * 4 + 40)
        throw new Error('Font resource exceeds 16 MiB.');
    const match = /^data:font\/(woff2|woff|ttf|otf);base64,([A-Za-z0-9+/]+={0,2})$/.exec(resource.dataURL);
    if (!match || match[2].length % 4 !== 0)
        throw new Error('Font resources must use a local base64 font data URL.');
    let binary;
    try {
        binary = atob(match[2]);
    }
    catch {
        throw new Error('Invalid font base64 data.');
    }
    const bytes = Uint8Array.from(binary, ch => ch.charCodeAt(0));
    if (format(bytes) !== match[1])
        throw new Error('Font MIME type does not match its binary format.');
    return { resource: Object.freeze({ family, dataURL: resource.dataURL, weight, style, category: resource.category ?? 'custom', source: resource.source ?? 'custom', ...(resource.license !== undefined ? { license: resource.license } : {}) }), bytes };
}
function slot(resource) { return JSON.stringify([resource.family.toLowerCase(), resource.weight, resource.style]); }
function copyOption(value) { return { ...value, weights: [...value.weights], styles: [...value.styles] }; }
function listFonts(document) {
    const options = [...system, ...standard].map(copyOption), byName = new Map(options.map(option => [option.family.toLowerCase(), option]));
    const installed = states.get(document)?.installed.values() ?? [];
    const resources = new Map();
    for (const { resource } of installed) {
        const key = resource.family.toLowerCase();
        resources.set(key, [...(resources.get(key) ?? []), resource]);
    }
    for (const [key, faces] of resources) {
        const first = faces[0], prior = byName.get(key);
        const option = { key: first.family, family: first.family, label: first.family, category: prior?.category ?? first.category ?? 'custom', source: first.source ?? 'custom', available: true,
            weights: [...new Set(faces.map(face => face.weight))], styles: [...new Set(faces.map(face => face.style))] };
        if (prior)
            options[options.indexOf(prior)] = option;
        else
            options.push(option);
    }
    return options;
}
async function installFontResources(document, resources) {
    const supplied = resources ?? document.defaultView?.DDN_FONT_RESOURCES ?? [];
    if (!Array.isArray(supplied) || supplied.length > MAX_FACES)
        throw new Error('A font pack may contain at most 128 faces.');
    if (!supplied.length)
        return listFonts(document);
    const FontFaceClass = document.defaultView?.FontFace;
    if (!FontFaceClass || !document.fonts?.add)
        throw new Error('This browser does not support local font loading.');
    const current = state(document), decoded = supplied.map(decode), unique = new Map();
    for (const entry of decoded) {
        const key = slot(entry.resource), previous = unique.get(key)?.resource ?? current.installed.get(key)?.resource ?? current.pending.get(key);
        if (previous && previous.dataURL !== entry.resource.dataURL)
            throw new Error('A different font is already registered for this family, weight and style.');
        unique.set(key, entry);
    }
    if (new Set([...current.installed.keys(), ...current.pending.keys(), ...unique.keys()]).size > MAX_FACES)
        throw new Error('A document may register at most 128 font faces.');
    await Promise.all([...unique].map(async ([key, entry]) => {
        if (current.installed.has(key))
            return;
        const pending = current.pending.get(key);
        if (pending)
            return pending.promise;
        const face = new FontFaceClass(entry.resource.family, entry.bytes.buffer, { weight: entry.resource.weight, style: entry.resource.style, display: 'swap' });
        const promise = face.load().then(loaded => {
            document.fonts.add(loaded);
            current.installed.set(key, { resource: entry.resource, face: loaded });
        }).finally(() => { current.pending.delete(key); });
        current.pending.set(key, { dataURL: entry.resource.dataURL, promise });
        return promise;
    }));
    document.dispatchEvent(new document.defaultView.Event('ddn:font-resources'));
    return listFonts(document);
}
async function loadFontFile(document, file, options = {}) {
    if (!file || !Number.isFinite(file.size) || file.size < 12 || file.size > MAX_FONT_BYTES)
        throw new Error('Font files must be between 12 bytes and 16 MiB.');
    const bytes = new Uint8Array(await file.arrayBuffer()), type = format(bytes);
    const family = familyName(options.family ?? file.name.replace(/\.(woff2?|ttf|otf)$/i, '').replace(/[_-]+/g, ' '));
    let binary = '';
    for (let offset = 0; offset < bytes.length; offset += 0x8000)
        binary += String.fromCharCode(...bytes.subarray(offset, offset + 0x8000));
    const resource = { family, dataURL: `data:font/${type};base64,${btoa(binary)}`, weight: options.weight ?? '400', style: options.style ?? 'normal', source: 'custom', category: 'custom' };
    await installFontResources(document, [resource]);
    return listFonts(document).find(option => option.family.toLowerCase() === family.toLowerCase());
}
function getFontResources(document, usedFontKeys) {
    const used = usedFontKeys === undefined ? undefined : new Set([...usedFontKeys].flatMap(key => names(aliases[key] ?? key)).map(name => name.toLowerCase()));
    return [...(states.get(document)?.installed.values() ?? [])].filter(({ resource }) => !used || used.has(resource.family.toLowerCase())).map(({ resource }) => ({ ...resource }));
}
function fontCSS(document, usedFontKeys) {
    const notices = new Set();
    return getFontResources(document, usedFontKeys).map(resource => {
        const notice = resource.license && !notices.has(resource.license) ? '/* ' + resource.license.replaceAll('*/', '* /') + ' */\n' : '';
        if (resource.license)
            notices.add(resource.license);
        return notice + `@font-face{font-family:${quote(resource.family)};src:url("${resource.dataURL}");font-weight:${resource.weight};font-style:${resource.style};font-display:block;}`;
    }).join('\n');
}

},
"viewer/src/popout.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.detachedPanels = detachedPanels;
exports.syncDetachedThemes = syncDetachedThemes;
exports.popOut = popOut;
exports.floatPanel = floatPanel;
const fonts_js_1 = require("viewer/src/fonts.js");
const ui_theme_js_1 = require("viewer/src/ui-theme.js");
const resize_grip_js_1 = require("viewer/src/resize-grip.js");
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
    catch { }
}
function copyTheme(from, toBody, bodyStyle = true) {
    const source = from.ownerDocument;
    for (const attribute of bodyStyle ? ['data-ddn-ui-theme', 'style'] : ['data-ddn-ui-theme'])
        if (source.body.hasAttribute(attribute))
            toBody.setAttribute(attribute, source.body.getAttribute(attribute));
    const computed = source.defaultView.getComputedStyle(from);
    for (const token of ui_theme_js_1.UI_THEME_TOKEN_NAMES) {
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
        document.defaultView?.addEventListener('pagehide', () => {
            for (const detached of [...(open.get(document) ?? [])])
                detached.dock();
        });
    }
    set.add(item);
}
function untrack(document, item) { open.get(document)?.delete(item); }
function detachedPanels(document) { return [...(open.get(document) ?? [])]; }
function syncDetachedThemes(document) {
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
function popOut(element, options) {
    const opener = element.ownerDocument, view = opener.defaultView;
    if (!view)
        return undefined;
    const place = remembered(options.name), width = Math.round(place.width ?? options.width ?? 420), height = Math.round(place.height ?? options.height ?? 640);
    const left = Math.round(place.left ?? (view.screenX + view.outerWidth - width - 24)), top = Math.round(place.top ?? (view.screenY + 80));
    let popup = null;
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
        catch { }
        return undefined;
    }
    target.title = options.title + ' — DDN';
    const copyFonts = () => { void (0, fonts_js_1.installFontResources)(target, (0, fonts_js_1.getFontResources)(opener)).catch(() => { }); };
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
    const save = () => {
        try {
            remember(options.name, { left: popup.screenX, top: popup.screenY, width: popup.outerWidth, height: popup.outerHeight });
        }
        catch { }
    };
    const grip = (0, resize_grip_js_1.resizeGrip)(target.body, { label: options.title + ' window', size: () => ({ width: popup.outerWidth, height: popup.outerHeight }), resize(width, height) {
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
    const observer = new popup.MutationObserver(() => {
        if (!host.contains(element)) {
            finish(false);
            try {
                popup.close();
            }
            catch { }
        }
    });
    observer.observe(host, { childList: true });
    popup.addEventListener('pagehide', () => { save(); finish(true); });
    popup.addEventListener('resize', save);
    if (options.onKeydown)
        target.addEventListener('keydown', options.onKeydown);
    const detached = {
        kind: 'window', element, window: popup,
        dock() {
            save();
            finish(true);
            try {
                popup.close();
            }
            catch { }
        },
        focus() {
            try {
                popup.focus();
            }
            catch { }
        },
    };
    track(opener, detached);
    popup.focus();
    return detached;
}
function floatPanel(element, options) {
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
    const grip = (0, resize_grip_js_1.resizeGrip)(frame, { label: options.title, size: () => frame.getBoundingClientRect(), resize(width, height) {
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
    move.addEventListener('pointermove', event => {
        if (drag?.id === event.pointerId)
            position(drag.left + event.clientX - drag.x, drag.top + event.clientY - drag.y);
    });
    const end = () => {
        if (drag) {
            drag = undefined;
            save();
        }
    };
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
    const observer = new view.MutationObserver(() => {
        if (!body.contains(element))
            finish(false);
    });
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

},
"viewer/src/resize-grip.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.resizeGrip = resizeGrip;
const CSS = `button.ddn-resize-grip{position:absolute!important;right:1px;bottom:1px;z-index:5;display:flex!important;align-items:center;justify-content:center;width:24px!important;height:24px!important;min-width:24px!important;min-height:24px!important;margin:0!important;padding:3px!important;border:0!important;border-radius:4px 0 7px 0!important;background:var(--ddn-ui-surface,#fff)!important;color:var(--ddn-ui-muted,#52647a)!important;cursor:nwse-resize!important;touch-action:none;user-select:none;box-sizing:border-box;flex:none}button.ddn-resize-grip:hover,button.ddn-resize-grip:focus-visible{color:var(--ddn-ui-accent,#2563eb)!important;background:var(--ddn-ui-input,#eef2f7)!important}button.ddn-resize-grip:focus-visible{outline:2px solid var(--ddn-ui-accent,#2563eb);outline-offset:-2px}.ddn-resize-grip svg{width:16px;height:16px;pointer-events:none}`;
function resizeGrip(container, options) {
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
        button.addEventListener(type, event => {
            if (drag?.id === event.pointerId)
                finish();
        });
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

},
"viewer/src/texture.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.normalizeTexture = normalizeTexture;
exports.createTexturePattern = createTexturePattern;
exports.textureBackground = textureBackground;
const ns = 'http://www.w3.org/2000/svg';
const color = (value, fallback) => typeof value === 'string' && /^(?:transparent|#[\da-f]{3}|#[\da-f]{6}|#[\da-f]{8})$/i.test(value) ? value : fallback;
const number = (value, fallback, low, high) => typeof value === 'number' && Number.isFinite(value) ? Math.min(high, Math.max(low, value)) : fallback;
const rounded = (value) => Number(value.toFixed(3));
function normalizeTexture(value) {
    if (!value || typeof value !== 'object' || Array.isArray(value))
        return;
    const source = value, kind = source.kind ?? 'paper';
    if (!['paper', 'linen', 'grid', 'dots'].includes(String(kind)))
        return;
    return { kind: kind, color: color(source.color, '#725d43'), opacity: number(source.opacity, .12, 0, 1), scale: number(source.scale, 32, 4, 128), seed: Math.floor(number(source.seed, 1, 0, 2147483647)) };
}
function shapes(settings, baseFill) {
    const result = [{ tag: 'rect', attributes: { width: 64, height: 64, fill: color(baseFill, 'transparent') } }];
    if (!settings.opacity || settings.color === 'transparent')
        return result;
    let state = settings.seed >>> 0;
    const random = () => { state = (Math.imul(state, 1664525) + 1013904223) >>> 0; return state / 4294967296; };
    const stroke = (d, width, opacity) => result.push({ tag: 'path', attributes: { d, fill: 'none', stroke: settings.color, 'stroke-width': width, 'stroke-linecap': 'round', opacity: rounded(settings.opacity * opacity) } });
    if (settings.kind === 'grid') {
        stroke('M.5 64V.5H64', 1, 1);
    }
    else if (settings.kind === 'dots') {
        result.push({ tag: 'circle', attributes: { cx: 32, cy: 32, r: 1.8, fill: settings.color, opacity: settings.opacity } });
    }
    else if (settings.kind === 'linen') {
        for (let direction = 0; direction < 2; direction++) {
            let threads = '', weave = '';
            for (let line = 0; line < 8; line++) {
                const position = rounded(line * 8 + 2 + random());
                threads += direction ? `M0 ${position}H64` : `M${position} 0V64`;
                for (let cross = 0; cross < 8; cross++)
                    if ((line + cross + direction) % 2 === 0) {
                        const start = cross * 8 + 1;
                        weave += direction ? `M${start} ${position}h5` : `M${position} ${start}v5`;
                    }
            }
            stroke(threads, 1.1, .52);
            stroke(weave, 1.9, .48);
        }
    }
    else {
        const grain = ['', '', ''], fibres = ['', '', ''];
        for (let index = 0; index < 84; index++) {
            const x = rounded(random() * 64), y = rounded(random() * 64);
            grain[index % 3] += `M${x} ${y}h.12`;
        }
        for (let index = 0; index < 18; index++) {
            const x = random() * 64, y = random() * 64, length = 3 + random() * 8, angle = random() * Math.PI * 2;
            const dx = Math.cos(angle) * length, dy = Math.sin(angle) * length, bend = (random() - .5) * 3;
            for (const ox of [-64, 0, 64])
                for (const oy of [-64, 0, 64]) {
                    const left = Math.min(x, x + dx, x + dx / 2 + bend) + ox, right = Math.max(x, x + dx, x + dx / 2 + bend) + ox;
                    const top = Math.min(y, y + dy, y + dy / 2 - bend) + oy, bottom = Math.max(y, y + dy, y + dy / 2 - bend) + oy;
                    if (right < 0 || left > 64 || bottom < 0 || top > 64)
                        continue;
                    fibres[index % 3] += `M${rounded(x + ox)} ${rounded(y + oy)}q${rounded(dx / 2 + bend)} ${rounded(dy / 2 - bend)} ${rounded(dx)} ${rounded(dy)}`;
                }
        }
        grain.forEach((d, index) => stroke(d, .45 + index * .3, .42 + index * .23));
        fibres.forEach((d, index) => stroke(d, .28 + index * .16, .4 + index * .2));
    }
    return result;
}
function createTexturePattern(document, id, value, baseFill = 'transparent') {
    const settings = normalizeTexture(value);
    if (!settings || !/^[A-Za-z_][\w.-]*$/.test(id))
        return;
    const pattern = document.createElementNS(ns, 'pattern');
    for (const [key, entry] of Object.entries({ id, patternUnits: 'userSpaceOnUse', width: settings.scale, height: settings.scale, viewBox: '0 0 64 64', preserveAspectRatio: 'none' }))
        pattern.setAttribute(key, String(entry));
    for (const shape of shapes(settings, baseFill)) {
        const node = document.createElementNS(ns, shape.tag);
        for (const [key, entry] of Object.entries(shape.attributes))
            node.setAttribute(key, String(entry));
        pattern.appendChild(node);
    }
    return pattern;
}
function textureBackground(value, baseFill = 'transparent') {
    const settings = normalizeTexture(value);
    if (!settings)
        return;
    const body = shapes(settings, baseFill).map(shape => `<${shape.tag} ${Object.entries(shape.attributes).map(([key, entry]) => `${key}="${entry}"`).join(' ')}/>`).join('');
    const svg = `<svg xmlns="${ns}" width="${settings.scale}" height="${settings.scale}" viewBox="0 0 64 64">${body}</svg>`;
    return { image: `url("data:image/svg+xml,${encodeURIComponent(svg)}")`, size: `${settings.scale}px ${settings.scale}px` };
}

},
"viewer/src/ui-commands.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.UI_COMMANDS_CHANGED = void 0;
exports.registerUICommands = registerUICommands;
exports.findUICommand = findUICommand;
exports.listUICommands = listUICommands;
exports.notifyUICommands = notifyUICommands;
exports.commandEnabled = commandEnabled;
const registries = new WeakMap();
exports.UI_COMMANDS_CHANGED = 'ddn:commands-changed';
function registerUICommands(host, commands) {
    let registry = registries.get(host);
    if (!registry) {
        registry = new Map();
        registries.set(host, registry);
    }
    for (const command of commands)
        registry.set(command.id, command);
    notifyUICommands(host);
    return () => {
        const current = registries.get(host);
        if (!current)
            return;
        for (const command of commands)
            if (current.get(command.id) === command)
                current.delete(command.id);
        notifyUICommands(host);
    };
}
function findUICommand(root, id) {
    const own = registries.get(root)?.get(id);
    if (own)
        return own;
    for (const element of root.querySelectorAll('[data-ddn-commands]')) {
        const found = registries.get(element)?.get(id);
        if (found)
            return found;
    }
    return undefined;
}
function listUICommands(root) {
    const result = new Map();
    for (const element of [root, ...root.querySelectorAll('[data-ddn-commands]')])
        for (const [id, command] of registries.get(element) ?? [])
            if (!result.has(id))
                result.set(id, command);
    return [...result.values()];
}
function notifyUICommands(host) {
    host.setAttribute('data-ddn-commands', '');
    host.dispatchEvent(new CustomEvent(exports.UI_COMMANDS_CHANGED, { bubbles: true }));
}
function commandEnabled(command) {
    if (!command)
        return false;
    try {
        return command.enabled ? command.enabled() : true;
    }
    catch {
        return false;
    }
}

},
"viewer/src/ui-icons.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.uiIcon = uiIcon;
const paths = {
    eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Zm13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
    pen: 'm15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14l-1 7Z',
    check: 'm5 12 4 4L19 6',
    folder: 'M3 7V4h6l2 3h10v13H3Z',
    code: 'm8 5-7 7 7 7m8-14 7 7-7 7M14 3l-4 18',
    download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
    upload: 'M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5',
    undo: 'M8 4 3 9l5 5M3 9h10a7 7 0 0 1 0 14',
    redo: 'm16 4 5 5-5 5m5-5H11a7 7 0 0 0 0 14',
    reflow: 'M19 8A8 8 0 0 0 5 6L2 9m0-5v5h5m-2 7a8 8 0 0 0 14 2l3-3m0 5v-5h-5M9 10h6v4H9Z',
    settings: 'M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6m-6 0v6',
    chevron: 'm6 9 6 6 6-6',
    grid: 'M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3Zm11 0h7v7h-7Z',
    plus: 'M12 4v16M4 12h16',
    minus: 'M4 12h16',
    'arrow-left': 'm11 5-7 7 7 7M4 12h16',
    'arrow-right': 'm13 5 7 7-7 7M4 12h16',
    expand: 'M9 3H3v6m12-6h6v6M3 15v6h6m6 0h6v-6',
    fit: 'M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5M8 8h8v8H8Z',
    search: 'M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0Zm-1 5 6 6',
    link: 'm10 8 3-3a4 4 0 0 1 6 6l-3 3m-2 2-3 3a4 4 0 0 1-6-6l3-3m1 5 6-6',
    type: 'M3 5V3h18v2M12 3v18m-4 0h8',
    table: 'M3 3h18v18H3Zm0 6h18M9 3v18',
    layers: 'm12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5',
    info: 'M12 8h.01M11 11h1v6m-1 0h2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
    palette: 'M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-4 2 2 0 0 1 1-4h3a3 3 0 0 0 3-3c0-4-4-7-9-7ZM7 9h.01M10 6h.01M15 6h.01M6 13h.01',
    trash: 'M3 6h18M8 6V4h8v2m-9 0 1 14h8l1-14M10 11v6m4-6v6',
    notes: 'M6 3h12a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm3 5h6m-6 4h6m-6 4h4',
    pin: 'M9 4v6l-2 4v2h10v-2l-2-4V4M12 16v5M8 4h8',
    border: 'M3 3h18v18H3Zm4 4h10v10H7Z',
    shadow: 'M4 4h13v13H4Zm3 16h13V7',
    'branch-left': 'M20 12H9m0 0 4-4m-4 4 4 4M5 6v12',
    'branch-right': 'M4 12h11m0 0-4-4m4 4-4 4M19 6v12',
};
function uiIcon(document, name) {
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg'), path = document.createElementNS(ns, 'path');
    svg.classList.add('ddn-ui-icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '16');
    svg.setAttribute('height', '16');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.7');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    path.setAttribute('d', paths[name] ?? paths.settings);
    svg.append(path);
    return svg;
}

},
"viewer/src/ui-theme.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.UI_THEME_TOKEN_NAMES = exports.UI_THEME_NAMES = void 0;
exports.installUITheme = installUITheme;
exports.setUITheme = setUITheme;
exports.UI_THEME_NAMES = ['light', 'dark', 'midnight', 'warm'];
const colourTokens = ['bg', 'surface', 'input', 'text', 'muted', 'border', 'accent', 'accent-text', 'danger', 'shadow'];
const metrics = {
    'font-size': [13, 11, 16], 'control-height': [32, 28, 40],
    radius: [12, 0, 16], 'dialog-width': [480, 280, 560],
};
exports.UI_THEME_TOKEN_NAMES = [...colourTokens, ...Object.keys(metrics)].map(name => `--ddn-ui-${name}`);
const themes = {
    light: ['#f3f6fc', '#ffffff', '#f8faff', '#18263d', '#55677f', '#d6dfed', '#3468db', '#ffffff', '#a71d3a', '#14243620'],
    dark: ['#0f172a', '#1b263b', '#111c30', '#f1f5fc', '#abbad0', '#35445e', '#80b3ff', '#10233d', '#ff9dad', '#02081780'],
    midnight: ['#070b16', '#11182b', '#0b1020', '#f1efff', '#b3b0cf', '#34344f', '#b4a2ff', '#1b1237', '#ff9dad', '#00000090'],
    warm: ['#f7f2e8', '#fffaf2', '#fdf8ef', '#44382d', '#79634c', '#dfd0ba', '#955023', '#ffffff', '#aa3140', '#49372120'],
};
const themeProperties = (name) => colourTokens.map((token, index) => `--ddn-ui-${token}:${themes[name][index]}`).join(';');
const css = `
:root{${themeProperties('light')};${Object.entries(metrics).map(([key, values]) => `--ddn-ui-${key}:${values[0]}px`).join(';')}}
${exports.UI_THEME_NAMES.map(name => `[data-ddn-ui-theme="${name}"]{${themeProperties(name)};color-scheme:${name === 'dark' || name === 'midnight' ? 'dark' : 'light'}}`).join('\n')}
.ddn-ui-layer{position:fixed;inset:0;display:grid;align-items:center;justify-items:center;padding:12px;box-sizing:border-box;pointer-events:auto;background:var(--ddn-ui-shadow);isolation:isolate}
.ddn-ui-layer[data-modal=false]{pointer-events:none;background:transparent}
.ddn-ui-layer[data-positioned]>.ddn-ui-dialog{position:absolute;width:min(var(--ddn-ui-dialog-width),calc(100% - 24px))}
.ddn-ui-dialog{position:relative;box-sizing:border-box;display:grid;grid-template-rows:auto minmax(0,1fr) auto auto;width:min(var(--ddn-ui-dialog-width),100%);max-height:min(640px,calc(100vh - 24px));max-height:min(640px,calc(100dvh - 24px));min-height:0;overflow:hidden;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);border:1px solid var(--ddn-ui-border);border-radius:var(--ddn-ui-radius);box-shadow:0 22px 64px var(--ddn-ui-shadow),0 2px 10px var(--ddn-ui-shadow);font:var(--ddn-ui-font-size)/1.4 Inter,system-ui,sans-serif;pointer-events:auto}
.ddn-ui-dialog[data-ddn-resized]{max-width:calc(100vw - 24px);max-height:calc(100dvh - 24px)}
.ddn-ui-dialog *,.ddn-ui-colour-field *{box-sizing:border-box}
.ddn-ui-icon{display:inline-block;width:16px;height:16px;min-height:0;flex:none;pointer-events:none;vertical-align:middle}
.ddn-ui-dialog-header{display:flex;align-items:center;gap:8px;padding:6px 10px;border-bottom:1px solid var(--ddn-ui-border)}
.ddn-ui-dialog-header h3{flex:1;min-width:0;margin:0;font-size:14px;line-height:1.4;font-weight:650;letter-spacing:-.015em;overflow-wrap:anywhere}
.ddn-ui-dialog-body{min-height:0;overflow:auto;overscroll-behavior:contain;padding:10px 12px}
.ddn-ui-dialog-footer{display:flex;flex-wrap:wrap;justify-content:flex-end;gap:6px;margin:0;padding:8px 34px 8px 12px;border-top:1px solid var(--ddn-ui-border);background:var(--ddn-ui-bg)}
.ddn-ui-dialog-error{color:var(--ddn-ui-danger);margin:0;padding:6px 12px;max-height:80px;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
.ddn-ui-dialog [hidden]{display:none!important}
.ddn-ui-dialog-error[hidden]{display:none}
.ddn-ui-dialog label{display:block;margin:6px 0}
.ddn-ui-dialog label>input,.ddn-ui-dialog label>select,.ddn-ui-dialog label>textarea{display:block;margin-top:3px}
.ddn-ui-dialog input:not([type=checkbox]):not([type=radio]),.ddn-ui-dialog select,.ddn-ui-dialog textarea,.ddn-ui-colour-field input{width:100%;min-width:0;min-height:var(--ddn-ui-control-height);padding:4px 7px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-input);color:var(--ddn-ui-text);font:inherit}
.ddn-ui-dialog input[type=checkbox],.ddn-ui-dialog input[type=radio]{display:inline-block;width:auto;margin:0 6px 0 0;accent-color:var(--ddn-ui-accent)}
.ddn-ui-dialog textarea{min-height:88px;resize:vertical;white-space:pre-wrap}
.ddn-ui-dialog button,.ddn-ui-colour-field button{min-height:var(--ddn-ui-control-height);padding:4px 10px;border:1px solid var(--ddn-ui-border);border-radius:8px;background:var(--ddn-ui-input);color:var(--ddn-ui-text);font:inherit;cursor:pointer}
.ddn-ui-dialog button[data-ddn-apply]{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:var(--ddn-ui-accent)}
.ddn-ui-dialog button:not(:disabled):hover{border-color:var(--ddn-ui-accent)}
.ddn-ui-dialog button:disabled{opacity:.55;cursor:default}
.ddn-ui-dialog .ddn-ui-dialog-move{width:100%;text-align:left;padding:3px 2px;border:0;background:transparent;font:inherit;cursor:grab;touch-action:none;user-select:none}
.ddn-ui-dialog .ddn-ui-dialog-move.ddn-ui-dragging{cursor:grabbing}
.ddn-ui-dialog .ddn-ui-dialog-dismiss{flex:0 0 28px;min-height:28px;padding:0;border:0;background:transparent;font-size:20px;line-height:1}
.ddn-ui-dialog .ddn-ui-dialog-popout{flex:0 0 28px;min-height:28px;padding:0;border:0;background:transparent;font-size:15px;line-height:1;color:var(--ddn-ui-muted)}
.ddn-ui-dialog .ddn-ui-dialog-popout:hover{color:var(--ddn-ui-accent)}
.ddn-ui-dialog :focus-visible,.ddn-ui-colour-field :focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:2px}
.ddn-ui-dialog input[aria-invalid=true]{border-color:var(--ddn-ui-danger)}
.ddn-ui-dialog fieldset{min-width:0;margin:8px 0;padding:10px;border:1px solid var(--ddn-ui-border);border-radius:10px}
.ddn-ui-dialog legend{padding:0 4px;color:var(--ddn-ui-muted)}
.ddn-ui-dialog p{margin:6px 0}
.ddn-ui-dialog pre{max-width:100%;overflow:auto;white-space:pre-wrap;overflow-wrap:anywhere}
.ddn-ui-dialog table{border-collapse:collapse;width:100%}
.ddn-ui-dialog th,.ddn-ui-dialog td{padding:4px;border:1px solid var(--ddn-ui-border)}
.ddn-ui-colour-field{display:flex;align-items:flex-end;gap:6px;margin:6px 0;font:var(--ddn-ui-font-size)/1.4 Inter,system-ui,sans-serif;color:var(--ddn-ui-text)}
.ddn-ui-colour-field>label{flex:1;min-width:0;margin:0}
.ddn-ui-colour-field>label>input{display:block;margin-top:3px}
.ddn-ui-colour-field input[type=color]{width:36px;height:var(--ddn-ui-control-height);flex:0 0 36px;padding:2px}
.ddn-ui-colour-field>button{flex:0 0 auto;padding:4px 7px}
.ddn-ui-colour-channels{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:6px}
.ddn-ui-colour-swatches{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:5px;margin:8px 0}
.ddn-ui-dialog .ddn-ui-colour-swatches button{padding:3px;min-width:0}
.ddn-ui-colour-swatches span{display:block;min-height:20px;border:1px solid var(--ddn-ui-border);border-radius:2px}
.ddn-ui-colour-previews{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin:8px 0}
.ddn-ui-colour-preview{background:repeating-conic-gradient(#ddd 0% 25%,#fff 0% 50%) 0/12px 12px;border:1px solid var(--ddn-ui-border);border-radius:4px;overflow:hidden}
.ddn-ui-colour-preview>span{display:block;height:48px}
.ddn-ui-colour-preview-label{display:block;margin-bottom:3px;color:var(--ddn-ui-muted)}
.ddn-ui-number-field{min-width:0;margin:6px 0}
.ddn-ui-number-field>label{margin:0 0 3px}
.ddn-ui-number-controls{display:grid;grid-template-columns:minmax(0,1fr) 80px;gap:10px;align-items:center}
.ddn-ui-dialog .ddn-ui-number-controls input[type=range]{padding:0;min-width:0;width:100%;border:0;box-shadow:none;background:transparent;accent-color:var(--ddn-ui-accent);cursor:pointer}
@media(max-width:380px){.ddn-ui-layer{padding:6px}.ddn-ui-dialog{max-height:calc(100dvh - 12px)}.ddn-ui-layer[data-positioned]>.ddn-ui-dialog{width:min(var(--ddn-ui-dialog-width),calc(100% - 12px))}.ddn-ui-dialog-header,.ddn-ui-dialog-body{padding:8px}.ddn-ui-dialog-footer{padding:6px 32px 6px 8px}.ddn-ui-colour-channels{grid-template-columns:repeat(2,minmax(0,1fr))}}
`;
function installUITheme(host) {
    const document = host.ownerDocument;
    if (!document.querySelector('style[data-ddn-ui-theme-styles]')) {
        const style = document.createElement('style');
        style.dataset.ddnUiThemeStyles = '';
        style.textContent = css;
        (document.head ?? document.documentElement).append(style);
    }
    host.classList.add('ddn-ui-theme');
}
function setUITheme(host, name, overrides = {}) {
    if (!exports.UI_THEME_NAMES.includes(name))
        throw new Error('Unknown DDN interface theme');
    const validated = [];
    for (const [key, value] of Object.entries(overrides)) {
        if (!exports.UI_THEME_TOKEN_NAMES.includes(key))
            throw new Error(`Unknown interface token: ${key}`);
        const token = key.slice('--ddn-ui-'.length);
        if (Object.hasOwn(metrics, token)) {
            const [, min, max] = metrics[token];
            if (typeof value !== 'number' || !Number.isFinite(value) || value < min || value > max)
                throw new Error(`${key} must be a number from ${min} to ${max}`);
            validated.push([key, `${value}px`]);
        }
        else {
            if (typeof value !== 'string' || !/^(?:#[\da-f]{3,4}|#[\da-f]{6}(?:[\da-f]{2})?|transparent)$/i.test(value))
                throw new Error(`${key} must be a hex colour or transparent`);
            validated.push([key, value]);
        }
    }
    installUITheme(host);
    host.dataset.ddnUiTheme = name;
    for (const key of exports.UI_THEME_TOKEN_NAMES)
        host.style.removeProperty(key);
    for (const [key, value] of validated)
        host.style.setProperty(key, value);
}

}});})();
