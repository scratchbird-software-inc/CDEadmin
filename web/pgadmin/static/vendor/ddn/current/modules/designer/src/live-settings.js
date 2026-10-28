import { createCommandHistoryGroup } from '../../runtime/src/commands.js';
import { ComputationStopped } from '../../execution/src/index.js';
export const LIVE_SETTINGS_CHANGE = 'ddn-settings-change';
const sessions = new WeakMap();
/** Programmatic sample buttons use the same route as sliders and text controls. */
export function notifyLiveSettings(body) { body.dispatchEvent(new body.ownerDocument.defaultView.Event(LIVE_SETTINGS_CHANGE, { bubbles: true })); }
/** Editors flush before changing the meaning/target of their controls. */
export async function flushLiveSettings(body) { await sessions.get(body)?.flush(); }
/** Save may stop waiting without cancelling the user's independent live edit. */
export async function waitForSettingsSave(flush, task = {}) {
    const started = Date.now(), budget = task.budget;
    if (budget && Object.values(budget).some(value => !Number.isFinite(value) || value < 0))
        throw new RangeError('Invalid operation budget');
    const cancelled = () => new ComputationStopped('cancelled', 'Save cancelled');
    const exhausted = () => new ComputationStopped('budget-exceeded', 'Save time budget exhausted while waiting for live settings');
    if (task.cancel?.aborted)
        throw cancelled();
    await new Promise((resolve, reject) => {
        let finished = false, timer, unlisten;
        const finish = (success, error) => {
            if (finished)
                return;
            finished = true;
            clearTimeout(timer);
            unlisten?.();
            if (success)
                resolve();
            else
                reject(error);
        };
        const deadline = () => {
            if (!budget || finished)
                return;
            const remaining = budget.elapsedMs - (Date.now() - started);
            if (remaining < 0) {
                finish(false, exhausted());
                return;
            }
            timer = setTimeout(deadline, Math.min(remaining + 1, 2147483647));
        };
        unlisten = task.cancel?.onAbort(() => finish(false, cancelled()));
        if (finished) {
            unlisten?.();
            return;
        }
        if (task.cancel?.aborted) {
            finish(false, cancelled());
            return;
        }
        deadline();
        if (!finished)
            void Promise.resolve().then(() => { if (!finished)
                return flush(); }).then(() => finish(true), error => finish(false, error));
    });
    if (task.cancel?.aborted)
        throw cancelled();
    if (!budget)
        return task;
    const elapsedMs = budget.elapsedMs - (Date.now() - started);
    if (elapsedMs < 0)
        throw exhausted();
    return { ...task, budget: { ...budget, elapsedMs } };
}
/** A single bounded queue per editor. A slider replaces queued values, not undo history. */
export function createLiveSettings(options) {
    const { body } = options, group = createCommandHistoryGroup(options.commands);
    let pending = false, stopped = false, running, reverting, error;
    const state = () => options.onState?.({ busy: !!running || !!reverting || pending, changed: group.changed, current: group.current, ...(error ? { error } : {}) });
    const report = (value) => { error = value; options.showError(value); state(); };
    async function drain() {
        while (pending && !stopped) {
            pending = false;
            try {
                if (!group.current)
                    throw Error('The diagram changed outside this settings session. Close and reopen the editor to continue.');
                // Native invalid intermediate numbers (e.g. an empty field) stay local.
                const invalid = [...body.querySelectorAll('input:invalid,textarea:invalid,select:invalid')].find(input => !input.disabled && !input.closest('[inert],[hidden],[data-ddn-live-ignore]') && input.getClientRects().length > 0);
                if (invalid)
                    throw Error('Enter a valid value for ' + (invalid.getAttribute('aria-label') ?? invalid.labels?.[0]?.textContent ?? 'this setting') + '.');
                await group.run(options.submit);
                if (!stopped)
                    report(undefined);
            }
            catch (failure) {
                if (!stopped)
                    report(failure);
            }
        }
    }
    function start() {
        if (!running && pending && !stopped) {
            // One microtask lets sample-button and field handlers finish synchronously.
            running = Promise.resolve().then(drain).finally(() => { running = undefined; state(); if (pending && !stopped)
                void start(); });
            state();
        }
        return running ?? Promise.resolve();
    }
    const session = {
        group,
        request() { if (stopped || reverting)
            return; pending = true; void start(); },
        async flush() {
            if (reverting)
                await reverting;
            do {
                await start();
            } while (pending && !stopped);
            if (error)
                throw error;
        },
        revert() {
            if (reverting)
                return reverting;
            reverting = (async () => {
                // A rejected intermediate field must not prevent reverting valid edits.
                pending = false;
                await running;
                if (!group.changed)
                    return;
                const result = await group.revert();
                if (!result.ok)
                    throw Error(result.failure.diagnostics.map(item => item.message).join('\n') || result.failure.code);
                error = undefined;
                options.showError(undefined);
                await options.afterRevert?.();
            })().finally(() => { reverting = undefined; state(); });
            state();
            return reverting;
        },
        async finish() { try {
            await session.flush();
        }
        finally {
            session.dispose();
        } },
        dispose() {
            if (stopped)
                return;
            stopped = true;
            pending = false;
            group.close();
            for (const event of ['input', 'change', LIVE_SETTINGS_CHANGE])
                body.removeEventListener(event, changed);
            sessions.delete(body);
            state();
        },
    };
    function changed(event) {
        const target = event.target;
        if (target?.closest?.('[data-ddn-live-ignore]'))
            return;
        if (target?.closest?.('.ddn-ui-dialog') !== body.closest('.ddn-ui-dialog'))
            return;
        session.request();
    }
    for (const event of ['input', 'change', LIVE_SETTINGS_CHANGE])
        body.addEventListener(event, changed);
    sessions.set(body, session);
    state();
    return session;
}
//# sourceMappingURL=live-settings.js.map