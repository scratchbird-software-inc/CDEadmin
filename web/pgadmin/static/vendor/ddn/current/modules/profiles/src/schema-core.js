import { compiledCodex } from './generated-native.js';
export const codex = compiledCodex;
const own = (v, k) => Object.prototype.hasOwnProperty.call(v, k);
const conditionalBranches = new WeakMap();
/** Index only provably inert discriminator branches; all selected branches still run exact schemas. */
function applicableAllOf(node, value) {
    const children = node.allOf ?? [];
    if (!isRecord(value) || children.length < 8)
        return children;
    let index = conditionalBranches.get(node);
    if (!index) {
        index = { always: [], groups: new Map() };
        for (const id of children) {
            const branch = codex.nodes[id];
            if (typeof branch !== 'object' || branch.if === undefined || branch.then === undefined || Object.keys(branch).some(key => key !== 'if' && key !== 'then')) {
                index.always.push(id);
                continue;
            }
            const condition = codex.nodes[branch.if];
            if (typeof condition !== 'object') {
                index.always.push(id);
                continue;
            }
            const discriminator = Object.entries(condition.properties ?? {}).find(([name, child]) => {
                const schema = codex.nodes[child];
                return condition.required?.includes(name) && typeof schema === 'object' && own(schema, 'const');
            });
            if (!discriminator) {
                index.always.push(id);
                continue;
            }
            const [name, child] = discriminator, expected = stableStringify(codex.nodes[child].const);
            const group = index.groups.get(name) ?? new Map();
            group.set(expected, [...(group.get(expected) ?? []), id]);
            index.groups.set(name, group);
        }
        conditionalBranches.set(node, index);
    }
    const selected = [...index.always];
    for (const [name, group] of index.groups)
        if (own(value, name))
            selected.push(...(group.get(stableStringify(value[name])) ?? []));
    return selected;
}
export function isRecord(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
export function stableStringify(value) {
    if (Array.isArray(value))
        return '[' + value.map(stableStringify).join(',') + ']';
    if (isRecord(value))
        return '{' + Object.keys(value).sort().map(k => JSON.stringify(k) + ':' + stableStringify(value[k])).join(',') + '}';
    return JSON.stringify(value) ?? 'undefined';
}
function validDate(value, dateTime) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[Tt](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?([Zz]|[+-]\d{2}:\d{2}))?$/.exec(value);
    if (!m || (dateTime && !m[4]) || (!dateTime && m[4]))
        return false;
    const y = Number(m[1]), month = Number(m[2]), day = Number(m[3]);
    const days = [31, (y % 4 === 0 && (y % 100 !== 0 || y % 400 === 0)) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31];
    if (month < 1 || month > 12 || day < 1 || day > (days[month - 1] ?? 0))
        return false;
    if (m[4] && (Number(m[4]) > 23 || Number(m[5]) > 59 || Number(m[6]) > 59))
        return false;
    if (m[7] && !/^[Zz]$/.test(m[7]) && (Number(m[7].slice(1, 3)) > 23 || Number(m[7].slice(4)) > 59))
        return false;
    return true;
}
/** Interprets deduplicated build-time validation instructions; never evaluates source code. */
export function validateSchema(schema, value, options = {}) {
    const start = typeof schema === 'number' ? schema : codex.roots[schema];
    if (start === undefined)
        return [{ path: '', keyword: 'schema', message: `Unknown registered schema ${schema}` }];
    const issues = [];
    const max = options.maxIssues ?? 100;
    const report = (path, keyword, message) => {
        if (issues.length < max)
            issues.push({ path, keyword, message });
    };
    const seen = new Set();
    function check(id, v, path, depth, emit = true) {
        options.checkpoint?.(1);
        if (depth > 1024) {
            if (emit)
                report(path, 'depth', 'Maximum structured-value depth exceeded');
            return false;
        }
        const node = codex.nodes[id];
        if (node === true)
            return true;
        if (node === false || node === undefined) {
            if (emit)
                report(path, 'schema', 'Value is forbidden by its registered schema');
            return false;
        }
        let ok = true;
        const fail = (key, msg) => {
            ok = false;
            if (emit)
                report(path, key, msg);
        };
        if (node.ref !== undefined) {
            if (node.ref === codex.roots.reference && isRecord(v) && emit)
                options.reference?.(v, path);
            const target = node.ref;
            if (target === undefined) {
                fail('schema', `Missing registered schema ${node.ref}`);
                return false;
            }
            const recursion = id + ':' + path;
            if (seen.has(recursion)) {
                fail('cycle', 'Cyclic schema evaluation');
                return false;
            }
            seen.add(recursion);
            ok = check(target, v, path, depth + 1, emit) && ok;
            seen.delete(recursion);
        }
        if (node.type) {
            const types = Array.isArray(node.type) ? node.type : [node.type];
            const matches = types.some(t => t === 'object' ? isRecord(v) : t === 'array' ? Array.isArray(v) : t === 'null' ? v === null : t === 'integer' ? typeof v === 'number' && Number.isSafeInteger(v) : t === 'number' ? typeof v === 'number' && Number.isFinite(v) : typeof v === t);
            if (!matches) {
                fail('type', `Expected ${types.join(' or ')}`);
                return false;
            }
        }
        if (node.enum && !node.enum.some(x => stableStringify(x) === stableStringify(v)))
            fail('enum', 'Value is outside the registered choices');
        if (own(node, 'const') && stableStringify(node.const) !== stableStringify(v))
            fail('const', 'Value differs from the required constant');
        if (typeof v === 'number') {
            if (!Number.isFinite(v))
                fail('type', 'A finite number is required');
            if (node.minimum !== undefined && v < node.minimum)
                fail('minimum', `Minimum is ${node.minimum}`);
            if (node.maximum !== undefined && v > node.maximum)
                fail('maximum', `Maximum is ${node.maximum}`);
            if (node.exclusiveMinimum !== undefined && v <= node.exclusiveMinimum)
                fail('exclusiveMinimum', `Must exceed ${node.exclusiveMinimum}`);
            if (node.exclusiveMaximum !== undefined && v >= node.exclusiveMaximum)
                fail('exclusiveMaximum', `Must be below ${node.exclusiveMaximum}`);
        }
        if (typeof v === 'string') {
            const len = [...v].length;
            if (node.minLength !== undefined && len < node.minLength)
                fail('minLength', `Minimum length is ${node.minLength}`);
            if (node.maxLength !== undefined && len > node.maxLength)
                fail('maxLength', `Maximum length is ${node.maxLength}`);
            if (node.pattern && !new RegExp(node.pattern, 'u').test(v))
                fail('pattern', 'Value does not match the registered pattern');
            if (node.format && (node.format === 'date' || node.format === 'date-time') && !validDate(v, node.format === 'date-time'))
                fail('format', `Expected a valid ${node.format}`);
        }
        if (Array.isArray(v)) {
            if (node.minItems !== undefined && v.length < node.minItems)
                fail('minItems', `At least ${node.minItems} items required`);
            if (node.maxItems !== undefined && v.length > node.maxItems)
                fail('maxItems', `At most ${node.maxItems} items permitted`);
            if (node.uniqueItems && new Set(v.map(stableStringify)).size !== v.length)
                fail('uniqueItems', 'Items must be unique');
            if (node.items !== undefined)
                for (let i = 0; i < v.length; i++)
                    ok = check(node.items, v[i], path + '/' + i, depth + 1, emit) && ok;
        }
        if (isRecord(v)) {
            const keys = Object.keys(v);
            if (node.minProperties !== undefined && keys.length < node.minProperties)
                fail('minProperties', 'Too few properties');
            if (node.maxProperties !== undefined && keys.length > node.maxProperties)
                fail('maxProperties', 'Too many properties');
            for (const required of node.required ?? [])
                if (!own(v, required))
                    fail('required', `Missing required property ${required}`);
            if (node.properties || node.additionalProperties !== undefined)
                for (const key of keys) {
                    const child = node.properties?.[key];
                    const p = path + '/' + key.replaceAll('~', '~0').replaceAll('/', '~1');
                    if (child !== undefined)
                        ok = check(child, v[key], p, depth + 1, emit) && ok;
                    else if (node.additionalProperties === false) {
                        ok = false;
                        if (emit)
                            report(p, 'additionalProperties', 'Unregistered property');
                    }
                    else if (typeof node.additionalProperties === 'number')
                        ok = check(node.additionalProperties, v[key], p, depth + 1, emit) && ok;
                }
        }
        for (const child of applicableAllOf(node, v))
            ok = check(child, v, path, depth + 1, emit) && ok;
        for (const keyword of ['anyOf', 'oneOf']) {
            const alternatives = node[keyword];
            if (!alternatives)
                continue;
            const matches = alternatives.filter(child => check(child, v, path, depth + 1, false));
            if ((keyword === 'anyOf' && matches.length === 0) || (keyword === 'oneOf' && matches.length !== 1))
                fail(keyword, `Value does not satisfy ${keyword} alternatives`);
            else if (emit && matches[0] !== undefined)
                check(matches[0], v, path, depth + 1, true);
        }
        if (node.not !== undefined && check(node.not, v, path, depth + 1, false))
            fail('not', 'Forbidden property combination');
        if (node.if !== undefined) {
            const branch = check(node.if, v, path, depth + 1, false) ? node.then : node.else;
            if (branch !== undefined)
                ok = check(branch, v, path, depth + 1, emit) && ok;
        }
        return ok;
    }
    check(start, value, '', 0);
    return issues;
}
export function getPath(value, path) {
    let v = value;
    for (const key of path.split('.')) {
        if (!isRecord(v) || !own(v, key))
            return undefined;
        v = v[key];
    }
    return v;
}
export function setPath(value, path, next) {
    const parts = path.split('.');
    let node = value;
    for (const part of parts.slice(0, -1)) {
        if (['__proto__', 'prototype', 'constructor'].includes(part))
            throw new Error('Unsafe property path');
        const child = node[part];
        if (!isRecord(child))
            node[part] = {};
        node = node[part];
    }
    const key = parts.at(-1);
    if (!key || ['__proto__', 'prototype', 'constructor'].includes(key))
        throw new Error('Unsafe property path');
    node[key] = next;
}
const lexicalCache = new Map();
export function schemaShape(schema) {
    const id = typeof schema === 'number' ? schema : /^n\d+$/.test(schema) ? Number(schema.slice(1)) : codex.roots[schema];
    if (id === undefined)
        return undefined;
    const known = lexicalCache.get(id);
    if (known)
        return known;
    const node = codex.nodes[id];
    if (node === undefined || typeof node === 'boolean')
        return undefined;
    const shape = {};
    lexicalCache.set(id, shape);
    if (node.ref !== undefined) {
        const name = node.ref === codex.roots.base_font_size ? 'base_font_size' : node.ref === codex.roots.font_size ? 'font_size' : 'n' + node.ref;
        shape.$ref = '#/$defs/' + name;
    }
    if (node.type)
        shape.type = node.type;
    if (node.enum)
        shape.type = [...new Set(node.enum.map(v => v === null ? 'null' : typeof v))];
    if (Object.prototype.hasOwnProperty.call(node, 'const'))
        shape.type = node.const === null ? 'null' : typeof node.const;
    if (node.properties)
        shape.properties = Object.fromEntries(Object.entries(node.properties).map(([key, value]) => [key, schemaShape(value) ?? {}]));
    if (node.items !== undefined)
        shape.items = schemaShape(node.items) ?? {};
    if (node.additionalProperties !== undefined)
        shape.additionalProperties = typeof node.additionalProperties === 'boolean' ? node.additionalProperties : schemaShape(node.additionalProperties) ?? {};
    for (const key of ['anyOf', 'oneOf'])
        if (node[key])
            shape[key] = node[key].map(value => schemaShape(value) ?? {});
    return shape;
}
export const lexicalShapes = new Proxy(Object.create(null), {
    get(_target, key) { return typeof key === 'string' ? schemaShape(key) : undefined; },
    has(_target, key) { return typeof key === 'string' && schemaShape(key) !== undefined; },
    ownKeys() { return Object.keys(codex.roots); },
    getOwnPropertyDescriptor(_target, key) { return typeof key === 'string' && schemaShape(key) !== undefined ? { enumerable: true, configurable: true, value: schemaShape(key) } : undefined; }
});
/** Exact schema shape for descriptor-driven editors; numeric references remain immutable codex indexes. */
export function getSchema(schema) { return codex.nodes[typeof schema === "number" ? schema : codex.roots[schema] ?? -1]; }
//# sourceMappingURL=schema-core.js.map