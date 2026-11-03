/** Expand generated declarative tables; no source code is interpreted. */
export function decodeWire(encoded) {
    if (encoded[3] === 'compact-1') {
        const [shapes, strings, root] = encoded;
        function expand(value) {
            if (typeof value === 'number' && value < 0)
                return strings[-value - 1];
            if (!Array.isArray(value))
                return value;
            const tag = value[0];
            if (tag === null)
                return value[1];
            if (tag === 0)
                return value.slice(1).map(expand);
            return Object.fromEntries(shapes[tag - 1].map((key, index) => [key, expand(value[index + 1])]));
        }
        encoded = expand(root);
    }
    const pool = encoded[1];
    function unpack(value) {
        if (Array.isArray(value))
            return value.map(unpack);
        if (value !== null && typeof value === 'object') {
            const row = value;
            if (typeof row.$ === 'number') {
                const index = row.$;
                const result = unpack(pool[index]);
                pool[index] = result;
                return result;
            }
            for (const key of Object.keys(row))
                row[key] = unpack(row[key]);
        }
        return value;
    }
    return unpack(encoded[0]);
}
export function decodeCatalogue(encoded) {
    const data = decodeWire(encoded);
    const [owners, properties, order] = data.properties;
    data.properties = order.map(([owner, index]) => { const [path, schema, defaults, flags, cssName] = properties[index]; return { owner: owners[owner], path, schema, default: defaults, css: !!(flags & 1), settable: !!(flags & 2), defaultable: !!(flags & 4), ...(cssName ? { cssName } : {}) }; });
    const [bases, roleRows] = data.roles;
    data.roles = Object.fromEntries(roleRows.map(([key, core, schema, diff]) => { const category = key.startsWith('relation::') ? 'relation' : 'element'; return [key, { role: category === 'relation' ? key.slice(10) : key, category, core, schema, render: { ...bases[category], ...diff } }]; }));
    const indices = new Map();
    for (let i = 0; i < data.nodes.length; i++) {
        const value = data.nodes[i];
        if (value && typeof value === 'object')
            indices.set(value, i);
    }
    const pending = data.nodes.slice();
    function add(value) { if (typeof value === 'number')
        return value; if (value && typeof value === 'object') {
        const known = indices.get(value);
        if (known !== undefined)
            return known;
    } const index = data.nodes.length; data.nodes.push(value); pending.push(value); if (value && typeof value === 'object')
        indices.set(value, index); return index; }
    for (let i = 0; i < pending.length; i++) {
        const value = pending[i];
        if (!value || typeof value !== 'object')
            continue;
        const node = value;
        if (Array.isArray(node.$case)) {
            const [tag, match, then] = node.$case;
            const key = tag === 3 ? 'profile' : tag === 4 ? 'format' : 'role';
            const properties = { [key]: { const: match } };
            if (tag === 0 || tag === 1)
                properties.category = { const: tag === 0 ? 'element' : 'relation' };
            node.if = { properties, ...(tag === 4 ? {} : { required: tag === 1 ? ['role', 'category'] : [key] }) };
            node.then = then;
            delete node.$case;
        }
        if (node.properties) {
            const props = node.properties;
            for (const key of Object.keys(props))
                props[key] = add(props[key]);
        }
        for (const key of ['allOf', 'anyOf', 'oneOf'])
            if (Array.isArray(node[key]))
                node[key] = node[key].map(add);
        for (const key of ['items', 'not', 'if', 'then', 'else'])
            if (node[key] !== undefined)
                node[key] = add(node[key]);
        if (node.additionalProperties !== undefined && typeof node.additionalProperties !== 'boolean')
            node.additionalProperties = add(node.additionalProperties);
    }
    return data;
}
//# sourceMappingURL=generated-codec.js.map