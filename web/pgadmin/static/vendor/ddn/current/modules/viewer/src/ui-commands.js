const registries = new WeakMap();
export const UI_COMMANDS_CHANGED = 'ddn:commands-changed';
/** Registers commands on a host element; returns a function that removes them. */
export function registerUICommands(host, commands) {
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
/** Finds a command registered on the host or on any registered descendant. */
export function findUICommand(root, id) {
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
export function listUICommands(root) {
    const result = new Map();
    for (const element of [root, ...root.querySelectorAll('[data-ddn-commands]')])
        for (const [id, command] of registries.get(element) ?? [])
            if (!result.has(id))
                result.set(id, command);
    return [...result.values()];
}
/** Tells hosts that enabled/checked/value states may have changed. */
export function notifyUICommands(host) {
    host.setAttribute('data-ddn-commands', '');
    host.dispatchEvent(new CustomEvent(UI_COMMANDS_CHANGED, { bubbles: true }));
}
export function commandEnabled(command) {
    if (!command)
        return false;
    try {
        return command.enabled ? command.enabled() : true;
    }
    catch {
        return false;
    }
}
//# sourceMappingURL=ui-commands.js.map