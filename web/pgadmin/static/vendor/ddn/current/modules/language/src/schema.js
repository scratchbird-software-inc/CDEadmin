/** Lexical dispatch shares the verifier's compiled codex; defaults are never inserted here. */
import { codex, lexicalShapes } from '../../profiles/src/schema-core.js';
function unfold(shape) {
    const seen = new Set();
    while (shape?.$ref) {
        const key = shape.$ref.split('/').at(-1);
        if (seen.has(key))
            break;
        seen.add(key);
        shape = lexicalShapes[key];
    }
    return shape;
}
const genericOptions = unfold(unfold(lexicalShapes.view_definition)?.properties?.projection)?.properties?.options;
const aliases = { boolean: 'bool', timestamp: 'instant' };
export const shapes = new Proxy(lexicalShapes, {
    get(target, key) {
        if (typeof key !== 'string')
            return undefined;
        const value = target[aliases[key] ?? key];
        if (value)
            return value;
        // Non-native profiles remain parseable against the shared option vocabulary; their
        // specialized verification and rendering still require their registered packs.
        if (key.startsWith('profile_') && Object.hasOwn(codex.knownProfiles, key.slice(8)))
            return genericOptions;
        return undefined;
    },
});
const descriptor = (entry) => ({ category: entry.category, schema: 'n' + entry.schema, core: entry.core });
export const roleTypes = Object.fromEntries(Object.entries(codex.roles).map(([key, value]) => [key, descriptor(value)]));
export const coreTypes = Object.fromEntries(Object.entries(codex.coreTypes).map(([key, value]) => [key, descriptor(value)]));
export const profiles = Object.keys(codex.knownProfiles);
//# sourceMappingURL=schema.js.map