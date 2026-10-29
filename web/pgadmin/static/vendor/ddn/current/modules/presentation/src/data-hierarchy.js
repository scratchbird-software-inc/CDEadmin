import { str, num } from './model.js';
import { DataScene, colors, finite, sum, unique, box, ellipse, path, label, arcPath, pointsPath, boundsOf, numberLabel } from './data-common.js';
export function hierarchy(records) {
    const root = { key: '', name: '', children: [], value: 0, records: [], depth: 0, slot: 0, radius: 0, x: 0, y: 0 };
    for (const record of records) {
        const name = str(record.values.label), value = record.values.value;
        if (!name || name.split('.').some(part => !part) || !finite(value) || value < 0)
            throw new Error('Hierarchy needs nonempty dotted paths and nonnegative finite leaf weights.');
        let node = root;
        const parts = name.split('.');
        if (parts.length > 3)
            throw new Error('Hierarchy depth exceeds three levels.');
        for (const part of parts) {
            if (node.records.length)
                throw new Error('A declared hierarchy leaf cannot also be a parent.');
            const key = node.key ? `${node.key}.${part}` : part;
            let next = node.children.find(child => child.key === key);
            if (!next) {
                next = { key, name: part, children: [], value: 0, records: [], depth: node.depth + 1, slot: 0, radius: 0, x: 0, y: 0 };
                node.children.push(next);
            }
            node = next;
        }
        if (node.children.length || node.records.length)
            throw new Error('Hierarchy paths must identify unique leaves.');
        node.records.push(record);
        node.value = value;
    }
    let leaf = 0;
    const calculate = (node) => {
        node.children.forEach(calculate);
        if (node.children.length) {
            node.value = sum(node.children.map(c => c.value));
            node.records = node.children.flatMap(c => c.records);
            node.slot = (node.children[0].slot + node.children.at(-1).slot) / 2;
        }
        else
            node.slot = leaf++;
    };
    calculate(root);
    return root;
}
export function drawHierarchy(scene, mark, data) {
    let root;
    try {
        root = hierarchy(data);
    }
    catch (error) {
        scene.issue(String(error));
        return;
    }
    if (!(root.value > 0) || !finite(root.value)) {
        scene.issue('The hierarchy needs a positive total weight.');
        return;
    }
    const displayDepth = scene.settings.iso === true ? 3 : num(scene.settings.depth, 3);
    if (!Number.isInteger(displayDepth) || displayDepth < 0 || displayDepth > 3) {
        scene.issue('Hierarchy display depth must be an integer in 0..3.');
        return;
    }
    if (displayDepth === 0) {
        scene.add(`Hierarchy summary: ${root.value}`, scene.bounds, [box(scene.bounds, '#eff6ff'), label(`Total ${root.value}`, scene.bounds.x + scene.bounds.width / 2, scene.bounds.y + scene.bounds.height / 2, 18, { 'text-anchor': 'middle' })], root.records[0].source, root.records.flatMap(record => record.contributors), 'Collapsed display at depth zero; all source contributors are retained.');
        return;
    }
    const collapse = (node) => {
        if (node.depth >= displayDepth)
            node.children = [];
        else
            node.children.forEach(collapse);
    };
    collapse(root);
    let nextSlot = 0;
    const slots = (node) => { node.children.forEach(slots); node.slot = node.children.length ? (node.children[0].slot + node.children.at(-1).slot) / 2 : nextSlot++; };
    slots(root);
    const bounds = { ...scene.bounds, x: scene.bounds.x + 24, y: scene.bounds.y + 24, width: Math.max(80, scene.bounds.width - 48), height: Math.max(80, scene.bounds.height - 88) }, all = [];
    const collect = (node) => { all.push(node); node.children.forEach(collect); };
    collect(root);
    const maximumDepth = Math.max(...all.map(n => n.depth));
    const sources = (node) => node.records.flatMap(r => r.contributors);
    const leaves = all.filter(node => !node.children.length), fill = (node) => colors[Math.max(0, node.children.length ? root.children.indexOf(node) : leaves.findIndex(leaf => leaf.key === node.key)) % colors.length];
    const valueLabel = (node) => `${numberLabel(node.value)}${scene.settings.unit ? ' ' + scene.settings.unit : ''}`;
    if (mark === 'treemap') {
        const draw = (node, b) => {
            if (node !== root) {
                const title = `${node.name}: ${valueLabel(node)}`;
                const lines = b.width >= 18 ? scene.wrap(title, b.width - 10, 11).slice(0, Math.max(0, Math.floor((b.height - 5) / 14))) : [];
                scene.add(`${node.key}: ${node.value}`, b, [box(b, node.children.length ? '#edf2f8' : fill(node), '#fff', { 'fill-opacity': node.children.length ? 1 : .8, 'stroke-width': 2 }), ...lines.map((line, i) => label(line, b.x + 5, b.y + 15 + i * 14, 11, { fill: node.children.length ? '#243449' : '#ffffff' }))], node.records[0].source, sources(node));
            }
            if (node !== root && node.children.length) {
                const header = Math.min(b.height, Math.max(24, scene.wrap(`${node.name}: ${valueLabel(node)}`, Math.max(8, b.width - 10), 11).length * 14 + 10));
                b = { ...b, y: b.y + header, height: Math.max(0, b.height - header) };
            }
            let offset = 0;
            const horizontal = node.depth % 2 === 0;
            for (const child of node.children) {
                const share = node.value ? child.value / node.value : 0, childBounds = horizontal ? { x: b.x + offset, y: b.y, width: b.width * share, height: b.height } : { x: b.x, y: b.y + offset, width: b.width, height: b.height * share };
                offset += horizontal ? childBounds.width : childBounds.height;
                if (share)
                    draw(child, childBounds);
            }
        };
        draw(root, bounds);
        scene.caption('Rectangle area encodes weight; header strips identify parent groups.');
        return;
    }
    if (mark === 'tidytree' || mark === 'radialtree') {
        const leaves = all.filter(n => !n.children.length).length, radius = Math.min(bounds.width, bounds.height) * .42;
        const position = (node) => mark === 'tidytree' ? [bounds.x + (node.slot + .5) * bounds.width / leaves, maximumDepth === 1 ? bounds.y + bounds.height / 2 : bounds.y + 12 + (node.depth - 1) * (bounds.height - 50) / (maximumDepth - 1)] : [bounds.x + bounds.width / 2 + Math.cos((node.slot + .5) / leaves * Math.PI * 2 - Math.PI / 2) * node.depth / maximumDepth * radius, bounds.y + bounds.height / 2 + Math.sin((node.slot + .5) / leaves * Math.PI * 2 - Math.PI / 2) * node.depth / maximumDepth * radius];
        for (const node of all.filter(node => node !== root)) {
            const p = position(node);
            for (const child of node.children) {
                const q = position(child);
                scene.add(`${node.key || 'root'} → ${child.key}`, boundsOf([p, q]), [path(pointsPath([p, q]), fill(child))], child.records[0].source, sources(child));
            }
            scene.add(node.key || 'root', { x: p[0] - 5, y: p[1] - 5, width: 10, height: 10 }, [ellipse(p[0], p[1], node.children.length ? 6 : 4, node.children.length ? '#1E2D43' : fill(node)), label(node.name, p[0], p[1] + 20, 11, { 'text-anchor': 'middle' })], node.records[0].source, sources(node));
        }
        scene.caption(`${mark === 'radialtree' ? 'Radial' : 'Tidy'} hierarchy; named roots remain separate; position encodes hierarchy, not weight.`);
        return;
    }
    if (mark === 'sunburst') {
        const cx = bounds.x + bounds.width / 2, cy = bounds.y + bounds.height / 2, ring = Math.min(bounds.width, bounds.height) / (2 * Math.max(1, maximumDepth));
        const draw = (node, start, end) => {
            if (node !== root && end > start)
                scene.add(`${node.key}: ${node.value}`, bounds, [path(arcPath(cx, cy, ring * node.depth, start, end, ring * (node.depth - 1)), '#fff', fill(node), { 'fill-opacity': .45 + .5 * node.depth / maximumDepth }), label(node.name, cx + Math.cos((start + end) / 2) * ring * (node.depth - .5), cy + Math.sin((start + end) / 2) * ring * (node.depth - .5) + 4, 11, { 'text-anchor': 'middle' })], node.records[0].source, sources(node));
            let angle = start;
            for (const child of node.children) {
                const next = angle + (end - start) * child.value / node.value;
                if (child.value)
                    draw(child, angle, next);
                angle = next;
            }
        };
        draw(root, -Math.PI / 2, Math.PI * 1.5);
        scene.caption('Sector angle encodes weight; concentric rings encode hierarchy depth.');
        return;
    }
    // Deterministic ring packing. A single global scale retains leaf area ratios.
    const pack = (node) => {
        node.children.forEach(pack);
        if (!node.children.length) {
            node.radius = Math.sqrt(node.value / Math.PI);
            return;
        }
        const children = [...node.children].sort((a, b) => b.radius - a.radius || (a.key < b.key ? -1 : 1));
        if (children.length === 1) {
            children[0].x = children[0].y = 0;
            node.radius = children[0].radius * 1.08;
            return;
        }
        const maximum = Math.max(...children.map(c => c.radius)), circumference = sum(children.map(c => 2 * c.radius + maximum * .1)), ring = Math.max(maximum * 1.05 / Math.sin(Math.PI / children.length), circumference / (2 * Math.PI));
        let angle = 0;
        for (const child of children) {
            const halfAngle = Math.asin(Math.min(1, (child.radius + maximum * .05) / ring));
            angle += halfAngle;
            child.x = ring * Math.cos(angle);
            child.y = ring * Math.sin(angle);
            angle += halfAngle;
        }
        node.radius = (ring + maximum) * 1.06;
    };
    if (mark === 'packedbubble' && data.some(datum => str(datum.values.label).includes('.'))) {
        const grouped = new Map();
        for (const datum of data) {
            const group = str(datum.values.label).split('.')[0];
            grouped.set(group, [...grouped.get(group) ?? [], datum]);
        }
        root.children = [...grouped].map(([name, rows], i) => ({ key: name, name, value: sum(rows.map(r => num(r.values.value))), records: rows, depth: 1, slot: i, radius: 0, x: 0, y: 0, children: rows.map((row, index) => ({ key: str(row.values.label), name: str(row.values.label).split('.').at(-1), value: num(row.values.value), records: [row], depth: 2, slot: index, radius: 0, x: 0, y: 0, children: [] })) }));
        collapse(root);
    }
    pack(root);
    // Lay out independent named groups beside one another with a shared area scale.
    const groupWidth = sum(root.children.map(child => 2 * child.radius)), gap = 24;
    const factor = Math.min((bounds.width - gap * Math.max(0, root.children.length - 1)) / Math.max(1, groupWidth), (bounds.height - 40) / Math.max(1, 2 * Math.max(...root.children.map(child => child.radius))));
    const draw = (node, x, y) => {
        if (node !== root && (mark === 'circlepack' || !node.children.length))
            scene.add(`${node.key}: ${node.value}`, { x: x - node.radius * factor, y: y - node.radius * factor, width: node.radius * factor * 2, height: node.radius * factor * 2 }, [ellipse(x, y, node.radius * factor, node.children.length ? '#ffffff' : fill(node), { 'fill-opacity': node.children.length ? 0 : .78, stroke: node.children.length ? '#C6D5E6' : '#ffffff' }), ...(!node.children.length ? [label(node.name, x, y + (mark === 'packedbubble' ? -3 : 4), 10, { 'text-anchor': 'middle' }), ...(mark === 'packedbubble' ? [label(valueLabel(node), x, y + 13, 10, { 'text-anchor': 'middle' })] : [])] : [])], node.records[0].source, sources(node), node.children.length ? 'Padded approximate container; area is not the sum of child areas.' : 'Leaf area encodes weight.');
        for (const child of node.children)
            draw(child, x + child.x * factor, y + child.y * factor);
    };
    let left = bounds.x + (bounds.width - groupWidth * factor - gap * (root.children.length - 1)) / 2;
    for (const child of root.children) {
        const x = left + child.radius * factor, y = bounds.y + bounds.height / 2;
        draw(child, x, y);
        if (child.children.length)
            scene.add(`${child.name} total`, { x: left, y: y - child.radius * factor - 25, width: child.radius * factor * 2, height: 20 }, [label(`${child.name}: ${valueLabel(child)}`, x, y - child.radius * factor - 10, 12, { 'text-anchor': 'middle' })]);
        left += 2 * child.radius * factor + gap;
    }
    scene.caption('Leaf circle area encodes weight; parent outlines group leaves and include packing space.');
}
export function forcePositions(names, links, width, height) {
    let seed = 0xB1024;
    const random = () => { seed = (seed + 0x6D2B79F5) | 0; let word = Math.imul(seed ^ seed >>> 15, seed | 1); word ^= word + Math.imul(word ^ word >>> 7, word | 61); return ((word ^ word >>> 14) >>> 0) / 4294967296; };
    const positions = names.map(() => [random() * 2 - 1, random() * 2 - 1]);
    const index = new Map(names.map((name, i) => [name, i])), k = Math.sqrt(4 / Math.max(1, names.length));
    for (let iteration = 0; iteration < 300; iteration++) {
        const displacement = names.map(() => [0, 0]);
        for (let a = 0; a < names.length; a++)
            for (let b = a + 1; b < names.length; b++) {
                const dx = positions[a][0] - positions[b][0], dy = positions[a][1] - positions[b][1], distance = Math.max(1e-6, Math.hypot(dx, dy)), force = k * k / distance;
                displacement[a][0] += dx / distance * force;
                displacement[a][1] += dy / distance * force;
                displacement[b][0] -= dx / distance * force;
                displacement[b][1] -= dy / distance * force;
            }
        for (const link of links) {
            const a = index.get(link.source), b = index.get(link.target), dx = positions[a][0] - positions[b][0], dy = positions[a][1] - positions[b][1], distance = Math.max(1e-6, Math.hypot(dx, dy)), force = distance * distance / k;
            displacement[a][0] -= dx / distance * force;
            displacement[a][1] -= dy / distance * force;
            displacement[b][0] += dx / distance * force;
            displacement[b][1] += dy / distance * force;
        }
        const temperature = .1 * (1 - iteration / 300);
        positions.forEach((point, i) => {
            const d = displacement[i], length = Math.max(1e-6, Math.hypot(d[0], d[1]));
            point[0] += d[0] / length * Math.min(length, temperature);
            point[1] += d[1] / length * Math.min(length, temperature);
        });
    }
    const xs = positions.map(point => point[0]), ys = positions.map(point => point[1]), lowX = Math.min(...xs), lowY = Math.min(...ys), spanX = Math.max(...xs) - lowX || 1, spanY = Math.max(...ys) - lowY || 1, padX = Math.min(70, width * .15), padY = Math.min(35, height * .15);
    return new Map(names.map((name, i) => [name, [padX + (positions[i][0] - lowX) / spanX * (width - 2 * padX), padY + (positions[i][1] - lowY) / spanY * (height - 2 * padY)]]));
}
export function drawLinks(scene, mark, data) {
    const links = data.map(datum => ({ datum, source: str(datum.values.source), target: str(datum.values.target), value: num(datum.values.value) }));
    if (links.some(link => !link.source || !link.target || link.source === link.target || !(link.value > 0))) {
        scene.issue('Weighted links require distinct nonempty endpoints and positive finite weights.');
        return;
    }
    const names = unique(links.flatMap(link => [link.source, link.target])), bound = mark === 'edgebundle' ? 500 : 1000;
    if (names.length > 200 || links.length > bound) {
        scene.issue(`Link projection exceeds 200 nodes or ${bound} links.`);
        return;
    }
    const b = { x: scene.bounds.x + 72, y: scene.bounds.y + 32, width: Math.max(80, scene.bounds.width - 144), height: Math.max(80, scene.bounds.height - 100) }, weights = new Map(names.map(name => [name, sum(links.filter(l => l.source === name || l.target === name).map(l => l.value))])), maximumWeight = Math.max(...weights.values(), 1), maximumLink = Math.max(...links.map(l => l.value), 1);
    if (mark === 'sankey') {
        const indegree = new Map(names.map(name => [name, links.filter(l => l.target === name).length])), depth = new Map(names.map(name => [name, 0])), queue = names.filter(name => indegree.get(name) === 0);
        let processed = 0;
        while (queue.length) {
            const name = queue.shift();
            processed++;
            for (const link of links.filter(l => l.source === name)) {
                depth.set(link.target, Math.max(depth.get(link.target), depth.get(name) + 1));
                indegree.set(link.target, indegree.get(link.target) - 1);
                if (indegree.get(link.target) === 0)
                    queue.push(link.target);
            }
        }
        if (processed !== names.length) {
            scene.issue('Sankey flows must form a directed acyclic graph.');
            return;
        }
        const columns = Math.max(...depth.values(), 0), heights = new Map(names.map(name => [name, Math.max(sum(links.filter(l => l.source === name).map(l => l.value)), sum(links.filter(l => l.target === name).map(l => l.value)))])), levels = Array.from({ length: columns + 1 }, (_, i) => names.filter(name => depth.get(name) === i)), gap = Math.min(16, b.height / (2 * Math.max(...levels.map(level => level.length), 1))), factor = Math.min(...levels.map(level => (b.height - Math.max(0, level.length - 1) * gap) / sum(level.map(name => heights.get(name))))), positions = new Map();
        for (const [index, level] of levels.entries()) {
            let y = b.y;
            for (const name of level) {
                const bounds = { x: b.x + index * (b.width - 18) / Math.max(1, columns), y, width: 18, height: heights.get(name) * factor };
                positions.set(name, bounds);
                y += bounds.height + gap;
            }
        }
        const out = new Map(names.map(name => [name, 0])), incoming = new Map(out);
        for (const link of links) {
            const a = positions.get(link.source), target = positions.get(link.target), thickness = link.value * factor, y1 = a.y + out.get(link.source) + thickness / 2, y2 = target.y + incoming.get(link.target) + thickness / 2, x1 = a.x + a.width, x2 = target.x;
            out.set(link.source, out.get(link.source) + thickness);
            incoming.set(link.target, incoming.get(link.target) + thickness);
            scene.add(`${link.source} → ${link.target}: ${link.value}`, boundsOf([[x1, y1], [x2, y2]], thickness / 2), [path(`M${x1},${y1}C${(x1 + x2) / 2},${y1} ${(x1 + x2) / 2},${y2} ${x2},${y2}`, colors[links.indexOf(link) % colors.length], 'none', { 'stroke-width': thickness, 'stroke-opacity': .45 })], link.datum.source, link.datum.contributors);
        }
        for (const name of names) {
            const bounds = positions.get(name);
            scene.add(name, bounds, [box(bounds, '#1E2D43', 'none'), label(`${name}: ${numberLabel(heights.get(name))}${scene.settings.unit ? ' ' + scene.settings.unit : ''}`, depth.get(name) === columns ? bounds.x - 8 : bounds.x + 26, bounds.y + bounds.height / 2 + 4, 11, { 'text-anchor': depth.get(name) === columns ? 'end' : 'start' })], links.find(l => l.source === name || l.target === name).datum.source, links.filter(l => l.source === name || l.target === name).flatMap(l => l.datum.contributors));
        }
        scene.caption('Ribbon thickness encodes flow; node totals are the greater of incoming and outgoing flow.');
        return;
    }
    let positions;
    let hierarchyPositions;
    if (mark === 'force')
        positions = new Map([...forcePositions(names, links, b.width, b.height)].map(([name, point]) => [name, [point[0] + b.x, point[1] + b.y]]));
    else if (mark === 'arc') {
        const ordered = [...names].sort((a, c) => weights.get(c) - weights.get(a) || (a < c ? -1 : a > c ? 1 : 0));
        const x = new Map(ordered.map((name, i) => [name, b.x + (i + .5) * b.width / ordered.length]));
        const upper = Math.max(0, ...links.filter(link => x.get(link.target) > x.get(link.source)).map(link => Math.abs(x.get(link.target) - x.get(link.source)) / 2));
        const lower = Math.max(0, ...links.filter(link => x.get(link.target) < x.get(link.source)).map(link => Math.abs(x.get(link.target) - x.get(link.source)) / 2));
        const baseline = b.y + upper + 12;
        b.height = upper + lower + 48;
        positions = new Map(ordered.map(name => [name, [x.get(name), baseline]]));
        scene.add('Arc node axis', b, [path(`M${b.x},${baseline}H${b.x + b.width}`, '#1E2D43', 'none', { 'stroke-width': 1 })]);
    }
    else {
        if (names.some(name => name.split('.').length > 3)) {
            scene.issue('Edge bundles are bounded to three hierarchy levels.');
            return;
        }
        hierarchyPositions = radialHierarchyPositions(names, b);
        positions = new Map(names.map(name => [name, hierarchyPositions.get(name)]));
    }
    for (const link of links) {
        const a = positions.get(link.source), target = positions.get(link.target), width = 1 + (mark === 'edgebundle' ? 2.5 : mark === 'arc' ? 5 : 4) * link.value / maximumLink;
        let d;
        if (mark === 'arc') {
            const radius = Math.abs(target[0] - a[0]) / 2;
            d = `M${a[0]},${a[1]}A${radius},${radius} 0 0 1 ${target[0]},${target[1]}`;
        }
        else if (mark === 'edgebundle') {
            const source = link.source.split('.'), dest = link.target.split('.');
            let common = 0;
            while (common < source.length && source[common] === dest[common])
                common++;
            const route = [];
            for (let depth = source.length; depth >= common; depth--)
                route.push(hierarchyPositions.get(source.slice(0, depth).join('.')));
            for (let depth = common + 1; depth <= dest.length; depth++)
                route.push(hierarchyPositions.get(dest.slice(0, depth).join('.')));
            d = `M${route[0][0]},${route[0][1]}`;
            for (let i = 1; i < route.length - 1; i++) {
                const current = route[i], next = route[i + 1];
                d += `Q${current[0]},${current[1]} ${(current[0] + next[0]) / 2},${(current[1] + next[1]) / 2}`;
            }
            d += `L${route.at(-1)[0]},${route.at(-1)[1]}`;
        }
        else
            d = pointsPath([a, target]);
        scene.add(`${link.source} → ${link.target}: ${link.value}`, b, [path(d, mark === 'force' ? '#CBD7E6' : colors[links.indexOf(link) % colors.length], 'none', { 'stroke-width': width, 'stroke-opacity': mark === 'force' ? 1 : .6 })], link.datum.source, link.datum.contributors);
    }
    names.forEach((name, i) => {
        const p = positions.get(name), r = mark === 'edgebundle' ? 3.5 : (mark === 'force' ? 5 : 4) + (mark === 'force' ? 12 : 10) * Math.sqrt(weights.get(name) / maximumWeight), rows = links.filter(l => l.source === name || l.target === name);
        const angle = Math.atan2(p[1] - b.y - b.height / 2, p[0] - b.x - b.width / 2), outsideX = p[0] + Math.cos(angle) * 12, outsideY = p[1] + Math.sin(angle) * 12;
        scene.add(name, { x: p[0] - r, y: p[1] - r, width: r * 2, height: r * 2 }, [ellipse(p[0], p[1], r, mark === 'force' ? colors[i % colors.length] : '#1E2D43'), label(mark === 'edgebundle' ? name.split('.').at(-1) : name, mark === 'edgebundle' ? outsideX : p[0], mark === 'edgebundle' ? outsideY + 4 : p[1] + r + 16, 11, { 'text-anchor': mark === 'edgebundle' ? Math.cos(angle) < 0 ? 'end' : 'start' : 'middle' })], rows[0].datum.source, rows.flatMap(l => l.datum.contributors), 'Position has no quantitative meaning.');
    });
    scene.caption(mark === 'arc' ? `${names.length} nodes · ${links.length} links · nodes ordered by total weight; arc thickness encodes value; arc height encodes distance only.` : mark === 'edgebundle' ? 'Links follow smooth paths through their lowest common ancestor; thickness encodes weight.' : 'Deterministic force layout (seed 0xB1024); node size and link width encode weight; position has no quantitative meaning.');
}
/** Radial tidy hierarchy; endpoints retain their declared hierarchy depth. */
export function radialHierarchyPositions(names, bounds) {
    const root = { name: '', children: [], depth: 0, slot: 0 }, byName = new Map([['', root]]);
    for (const name of names) {
        let parent = root;
        for (const segment of name.split('.')) {
            const prefix = parent.name ? parent.name + '.' + segment : segment;
            let node = byName.get(prefix);
            if (!node) {
                node = { name: prefix, children: [], depth: parent.depth + 1, slot: 0 };
                parent.children.push(node);
                byName.set(prefix, node);
            }
            parent = node;
        }
    }
    let leaves = 0;
    const place = (node) => { node.children.forEach(place); node.slot = node.children.length ? (node.children[0].slot + node.children.at(-1).slot) / 2 : leaves++; };
    place(root);
    const maximum = Math.max(...[...byName.values()].map(node => node.depth)), radius = Math.min(bounds.width, bounds.height) * .4;
    return new Map([...byName].map(([name, node]) => { const angle = (node.slot + .5) / Math.max(1, leaves) * Math.PI * 2 - Math.PI / 2, r = node.depth / Math.max(1, maximum) * radius; return [name, [bounds.x + bounds.width / 2 + Math.cos(angle) * r, bounds.y + bounds.height / 2 + Math.sin(angle) * r]]; }));
}
//# sourceMappingURL=data-hierarchy.js.map