/** Deterministic client-side layouts. Every loop is bounded by model size or an
 * explicit relaxation count; authored pins always win over automatic placement. */
export function graphLayout(nodes, links, settings = {}) {
    const positions = new Map();
    if (!nodes.length)
        return positions;
    const n = nodes.length, index = new Map(nodes.map((node, i) => [node.id, i]));
    const outgoing = nodes.map(() => []), incoming = nodes.map(() => []);
    for (const link of links) {
        const a = index.get(link.from), b = index.get(link.to);
        if (a !== undefined && b !== undefined && a !== b && !outgoing[a].includes(b)) {
            outgoing[a].push(b);
            incoming[b].push(a);
        }
    }
    const gap = Math.max(8, settings.gap ?? 64), rowGap = Math.max(8, settings.row_gap ?? 64), width = Math.max(...nodes.map(node => node.bounds.width)), height = Math.max(...nodes.map(node => node.bounds.height));
    const stepX = width + gap, stepY = height + rowGap, algorithm = settings.algorithm ?? 'grid', columns = Math.max(1, Math.floor(settings.columns ?? 3));
    const direction = settings.direction ?? (algorithm === 'tree' ? 'down' : 'right');
    let intrinsic = false, preserveWorld = false;
    const xy = nodes.map((_, i) => ({ x: (i % columns) * stepX, y: Math.floor(i / columns) * stepY }));
    const roots = nodes.map((_, i) => i).filter(i => !incoming[i].length), declared = settings.root === undefined ? undefined : index.get(settings.root);
    if (declared !== undefined) {
        const at = roots.indexOf(declared);
        if (at >= 0)
            roots.splice(at, 1);
        roots.unshift(declared);
    }
    if (!roots.length)
        roots.push(0);
    const parents = new Map(), depths = new Map(), components = new Map();
    let component = 0;
    for (const root of [...roots, ...nodes.map((_, i) => i)]) {
        if (depths.has(root))
            continue;
        depths.set(root, 0);
        components.set(root, component++);
        const queue = [root];
        for (let i = 0; i < queue.length; i++)
            for (const child of outgoing[queue[i]])
                if (!depths.has(child)) {
                    parents.set(child, queue[i]);
                    depths.set(child, depths.get(queue[i]) + 1);
                    components.set(child, components.get(root));
                    queue.push(child);
                }
    }
    if (algorithm === 'fit_grid') {
        intrinsic = true;
        // A compact lattice grows around the most connected node (or authored
        // pins). Nearest-neighbour cost keeps connected clusters together;
        // balance prevents the first declaration from forcing a corner origin.
        const adjacent = nodes.map((_, i) => [...new Set([...outgoing[i], ...incoming[i]])]), pins = nodes.map((_, i) => i).filter(i => nodes[i].pinned), degree = (i) => adjacent[i].length;
        const seed = pins.length ? pins : [declared ?? nodes.map((_, i) => i).sort((a, b) => degree(b) - degree(a) || nodes[a].id.localeCompare(nodes[b].id))[0]], distance = new Map(), queue = [...seed];
        seed.forEach(i => distance.set(i, 0));
        for (let at = 0; at < queue.length; at++)
            for (const i of adjacent[queue[at]])
                if (!distance.has(i)) {
                    distance.set(i, distance.get(queue[at]) + 1);
                    queue.push(i);
                }
        const order = nodes.map((_, i) => i).filter(i => !nodes[i].pinned).sort((a, b) => (distance.get(a) ?? n) - (distance.get(b) ?? n) || degree(b) - degree(a) || nodes[a].id.localeCompare(nodes[b].id));
        const anchor = pins.length ? { x: (Math.min(...pins.map(i => nodes[i].bounds.x)) + Math.max(...pins.map(i => nodes[i].bounds.x + nodes[i].bounds.width))) / 2, y: (Math.min(...pins.map(i => nodes[i].bounds.y)) + Math.max(...pins.map(i => nodes[i].bounds.y + nodes[i].bounds.height))) / 2 } : { x: 0, y: 0 }, placed = new Set(pins);
        pins.forEach(i => xy[i] = { x: nodes[i].bounds.x, y: nodes[i].bounds.y });
        preserveWorld = !!pins.length;
        let sumX = 0, sumY = 0, count = 0;
        for (const i of order) {
            let best;
            const bounds = nodes[i].bounds;
            for (let ring = 0; ring <= n && !best; ring++)
                for (let col = -ring; col <= ring; col++)
                    for (let row = -ring; row <= ring; row++)
                        if (Math.max(Math.abs(col), Math.abs(row)) === ring) {
                            const cx = anchor.x + col * stepX, cy = anchor.y + row * stepY, x = cx - bounds.width / 2, y = cy - bounds.height / 2;
                            if ([...placed].some(j => x < nodes[j].bounds.width + xy[j].x + gap / 2 && x + bounds.width > xy[j].x - gap / 2 && y < nodes[j].bounds.height + xy[j].y + rowGap / 2 && y + bounds.height > xy[j].y - rowGap / 2))
                                continue;
                            const peers = adjacent[i].filter(j => placed.has(j)), links = peers.reduce((v, j) => v + Math.hypot(cx - xy[j].x - nodes[j].bounds.width / 2, cy - xy[j].y - nodes[j].bounds.height / 2), 0) / Math.max(1, peers.length), cost = Math.hypot(cx - anchor.x, cy - anchor.y) + .7 * Math.hypot(sumX + cx - anchor.x, sumY + cy - anchor.y) / (count + 1) + .12 * links;
                            if (!best || cost < best.cost - .001)
                                best = { x, y, cost };
                        }
            xy[i] = { x: best?.x ?? anchor.x + (n + 1) * stepX, y: best?.y ?? anchor.y + count * stepY };
            placed.add(i);
            sumX += xy[i].x + bounds.width / 2 - anchor.x;
            sumY += xy[i].y + bounds.height / 2 - anchor.y;
            count++;
        }
    }
    else if (algorithm === 'ladder') {
        xy.forEach((p, i) => { p.x = 0; p.y = i * stepY; });
    }
    else if (algorithm === 'layered') {
        intrinsic = true;
        // Condense feedback loops into strongly connected components. Ranking
        // the acyclic component graph keeps a feedback stage together instead
        // of flattening a cyclic workflow or placing its leaves at rank zero.
        const seen = new Set(), finished = [];
        for (let root = 0; root < n; root++)
            if (!seen.has(root)) {
                seen.add(root);
                const stack = [[root, 0]];
                while (stack.length) {
                    const top = stack.at(-1), i = top[0], next = top[1];
                    if (next >= outgoing[i].length) {
                        stack.pop();
                        finished.push(i);
                        continue;
                    }
                    top[1]++;
                    const child = outgoing[i][next];
                    if (!seen.has(child)) {
                        seen.add(child);
                        stack.push([child, 0]);
                    }
                }
            }
        const componentOf = new Map(), groups = [];
        for (const root of finished.reverse())
            if (!componentOf.has(root)) {
                const id = groups.length, members = [], stack = [root];
                componentOf.set(root, id);
                while (stack.length) {
                    const i = stack.pop();
                    members.push(i);
                    for (const parent of incoming[i])
                        if (!componentOf.has(parent)) {
                            componentOf.set(parent, id);
                            stack.push(parent);
                        }
                }
                groups.push(members.sort((a, b) => a - b));
            }
        const forward = groups.map(() => new Set()), backward = groups.map(() => new Set());
        for (let i = 0; i < n; i++)
            for (const child of outgoing[i]) {
                const a = componentOf.get(i), b = componentOf.get(child);
                if (a !== b) {
                    forward[a].add(b);
                    backward[b].add(a);
                }
            }
        const pending = backward.map(peers => peers.size), levels = groups.map(() => 0), queue = groups.map((_, i) => i).filter(i => !pending[i]).sort((a, b) => groups[a][0] - groups[b][0]);
        for (let at = 0; at < queue.length; at++) {
            const i = queue[at];
            for (const child of forward[i]) {
                levels[child] = Math.max(levels[child], levels[i] + 1);
                pending[child]--;
                if (!pending[child])
                    queue.push(child);
            }
        }
        const ranks = Array.from({ length: Math.max(...levels) + 1 }, () => []);
        groups.forEach((_, i) => ranks[levels[i]].push(i));
        ranks.forEach((rank, level) => rank.sort((a, b) => (level === 0 ? forward[a].size - forward[b].size : 0) || groups[a][0] - groups[b][0]));
        // Barycentric sweeps reduce crossings while retaining stable declaration
        // order for equal scores and keeping members of each cycle adjacent.
        const order = new Map();
        const refresh = () => ranks.forEach(rank => rank.forEach((id, i) => order.set(id, i)));
        refresh();
        for (let sweep = 0; sweep < 4; sweep++)
            for (const descending of [false, true]) {
                const visit = descending ? [...ranks].reverse() : ranks;
                for (const rank of visit) {
                    const neighbours = descending ? forward : backward, score = (id) => { const peers = [...neighbours[id]]; return peers.length ? peers.reduce((sum, k) => sum + (order.get(k) ?? 0), 0) / peers.length : order.get(id) ?? 0; };
                    rank.sort((a, b) => score(a) - score(b) || (order.get(a) ?? 0) - (order.get(b) ?? 0));
                    refresh();
                }
            }
        const vertical = ['down', 'up'].includes(direction), spacing = vertical ? gap : rowGap, dimension = (i) => vertical ? nodes[i].bounds.width : nodes[i].bounds.height;
        const members = ranks.map(rank => rank.flatMap(id => groups[id])), spans = members.map(rank => rank.reduce((sum, i) => sum + dimension(i), 0) + Math.max(0, rank.length - 1) * spacing), maxSpan = Math.max(...spans);
        members.forEach((rank, level) => { let cursor = (maxSpan - spans[level]) / 2; for (const i of rank) {
            xy[i] = vertical ? { x: cursor, y: level * stepY + (height - nodes[i].bounds.height) / 2 } : { x: level * stepX + (width - nodes[i].bounds.width) / 2, y: cursor };
            cursor += dimension(i) + spacing;
        } });
    }
    else if (['tree', 'spanning_tree', 'mindmap', 'radial'].includes(algorithm)) {
        const children = nodes.map(() => []);
        for (const [child, parent] of parents)
            children[parent].push(child);
        const breadth = new Map();
        let leaf = 0;
        // Postorder traversal keeps each subtree contiguous, then centres its
        // parent above the full child span. Declaration order breaks ties.
        for (const root of nodes.map((_, i) => i).filter(i => !parents.has(i))) {
            const stack = [[root, false]];
            while (stack.length) {
                const [i, done] = stack.pop();
                const kids = children[i];
                if (!done && kids.length) {
                    stack.push([i, true]);
                    for (const child of [...kids].reverse())
                        stack.push([child, false]);
                }
                else
                    breadth.set(i, kids.length ? (breadth.get(kids[0]) + breadth.get(kids.at(-1))) / 2 : leaf++);
            }
        }
        xy.forEach((p, i) => { p.x = (depths.get(i) ?? 0) * stepX; p.y = (breadth.get(i) ?? 0) * stepY; });
        if (algorithm === 'mindmap') {
            intrinsic = true;
            const root = roots[0], branches = children[root], spans = new Map();
            for (const i of nodes.map((_, i) => i).sort((a, b) => (depths.get(b) ?? 0) - (depths.get(a) ?? 0))) {
                const kids = children[i], childrenHeight = kids.reduce((sum, k) => sum + spans.get(k), 0) + Math.max(0, kids.length - 1) * rowGap;
                spans.set(i, Math.max(nodes[i].bounds.height, childrenHeight));
            }
            xy[root] = { x: (width - nodes[root].bounds.width) / 2, y: -nodes[root].bounds.height / 2 };
            const place = (branch, top, side) => {
                const stack = [[branch, top]];
                while (stack.length) {
                    const [i, start] = stack.pop(), span = spans.get(i), kids = children[i];
                    xy[i] = { x: (depths.get(i) ?? 0) * stepX * side + (width - nodes[i].bounds.width) / 2, y: start + (span - nodes[i].bounds.height) / 2 };
                    const childrenHeight = kids.reduce((sum, k) => sum + spans.get(k), 0) + Math.max(0, kids.length - 1) * rowGap;
                    let cursor = start + (span - childrenHeight) / 2;
                    for (const child of kids) {
                        stack.push([child, cursor]);
                        cursor += spans.get(child) + rowGap;
                    }
                }
            };
            const branchSides = new Map(branches.map((branch, i) => { const explicit = settings.mindmapProfile ? links.find(link => link.from === nodes[root].id && link.to === nodes[branch].id)?.side : undefined; return [branch, explicit === 'left' ? -1 : explicit === 'right' ? 1 : (i % 2 ? -1 : 1) * (settings.mindmapProfile && direction === 'left' ? -1 : 1)]; }));
            for (const side of [1, -1]) {
                const peers = branches.filter(branch => branchSides.get(branch) === side), total = peers.reduce((sum, i) => sum + spans.get(i), 0) + Math.max(0, peers.length - 1) * rowGap;
                let top = -total / 2;
                for (const branch of peers) {
                    place(branch, top, side);
                    top += spans.get(branch) + rowGap;
                }
            }
            let bottom = Math.max(...xy.map((p, i) => p.y + nodes[i].bounds.height)) + rowGap;
            for (const other of nodes.map((_, i) => i).filter(i => !parents.has(i) && i !== root)) {
                place(other, bottom, 1);
                bottom += spans.get(other) + rowGap;
            }
        }
        if (algorithm === 'radial') {
            const perDepth = new Map();
            nodes.forEach((_, i) => { const d = depths.get(i) ?? 0; const peers = perDepth.get(d) ?? []; peers.push(i); perDepth.set(d, peers); });
            for (const [depth, peers] of perDepth)
                peers.forEach((i, j) => { const radius = depth === 0 ? 0 : Math.max(depth * stepX, peers.length * stepX / (2 * Math.PI)), angle = j / peers.length * 2 * Math.PI - Math.PI / 2; xy[i] = { x: radius * Math.cos(angle), y: radius * Math.sin(angle) }; });
        }
    }
    else if (algorithm === 'circular') {
        const radius = Math.max(stepX, n * stepX / (2 * Math.PI));
        xy.forEach((p, i) => { const angle = i / n * 2 * Math.PI - Math.PI / 2; p.x = radius * Math.cos(angle); p.y = radius * Math.sin(angle); });
    }
    else if (algorithm === 'grouped') {
        const groups = new Map();
        nodes.forEach((node, i) => { const key = node.group ?? 'ungrouped', peers = groups.get(key) ?? []; peers.push(i); groups.set(key, peers); });
        let offset = 0;
        for (const peers of groups.values()) {
            const count = Math.min(columns, peers.length);
            peers.forEach((i, j) => { xy[i] = { x: offset + j % count * stepX, y: Math.floor(j / count) * stepY }; });
            offset += count * stepX + gap;
        }
    }
    else if (algorithm === 'organic') {
        const radius = Math.max(stepX, n * stepX / (2 * Math.PI));
        xy.forEach((p, i) => { const angle = i / n * 2 * Math.PI; p.x = radius * Math.cos(angle); p.y = radius * Math.sin(angle); });
        // Large models use bounded local repulsion rather than all-pairs work.
        const span = Math.min(128, n - 1);
        for (let iteration = 0; iteration < 48; iteration++) {
            const force = nodes.map(() => ({ x: 0, y: 0 }));
            for (let i = 0; i < n; i++)
                for (let offset = 1; offset <= span; offset++) {
                    const j = (i + offset) % n, dx = xy[i].x - xy[j].x, dy = xy[i].y - xy[j].y, length = Math.max(1, Math.hypot(dx, dy)), repel = stepX * stepY / (length * length);
                    force[i].x += dx / length * repel;
                    force[i].y += dy / length * repel;
                }
            for (const link of links) {
                const a = index.get(link.from), b = index.get(link.to);
                if (a === undefined || b === undefined)
                    continue;
                const dx = xy[b].x - xy[a].x, dy = xy[b].y - xy[a].y, length = Math.max(1, Math.hypot(dx, dy)), pull = (length - stepX) * .018;
                force[a].x += dx / length * pull;
                force[a].y += dy / length * pull;
                force[b].x -= dx / length * pull;
                force[b].y -= dy / length * pull;
            }
            xy.forEach((p, i) => { if (!nodes[i].pinned) {
                p.x += Math.max(-stepX / 10, Math.min(stepX / 10, force[i].x));
                p.y += Math.max(-stepY / 10, Math.min(stepY / 10, force[i].y));
            } });
        }
    }
    if (['tree', 'spanning_tree'].includes(algorithm) && ['down', 'up'].includes(direction))
        xy.forEach(p => { const x = p.x; p.x = p.y / stepY * stepX; p.y = x / stepX * stepY; });
    if (!intrinsic && ['layered', 'tree', 'spanning_tree', 'mindmap', 'radial', 'circular'].includes(algorithm))
        xy.forEach((p, i) => { p.x += (width - nodes[i].bounds.width) / 2; p.y += (height - nodes[i].bounds.height) / 2; });
    if (direction === 'left' && algorithm !== 'fit_grid' && !(algorithm === 'mindmap' && settings.mindmapProfile))
        xy.forEach((p, i) => p.x = -p.x - nodes[i].bounds.width);
    if (direction === 'up' && algorithm !== 'fit_grid' && !(algorithm === 'mindmap' && settings.mindmapProfile))
        xy.forEach((p, i) => p.y = -p.y - nodes[i].bounds.height);
    const minX = Math.min(...xy.map(p => p.x)), minY = Math.min(...xy.map(p => p.y));
    nodes.forEach((node, i) => positions.set(node.id, node.pinned ? node.bounds : { ...node.bounds, x: xy[i].x - (preserveWorld ? 0 : minX - 32), y: xy[i].y - (preserveWorld ? 0 : minY - 64) }));
    if (nodes.some(node => node.pinned) && algorithm !== 'fit_grid') {
        const occupied = nodes.filter(node => node.pinned).map(node => node.bounds), padding = Math.min(gap, rowGap) / 2, vertical = ['down', 'up'].includes(direction);
        const overlaps = (a, b) => a.x < b.x + b.width + padding && a.x + a.width > b.x - padding && a.y < b.y + b.height + padding && a.y + a.height > b.y - padding;
        for (const node of nodes.filter(node => !node.pinned)) {
            const initial = positions.get(node.id);
            let chosen = initial;
            for (let attempt = 0; attempt <= n * 2 && occupied.some(bounds => overlaps(chosen, bounds)); attempt++) {
                const offset = (Math.floor(attempt / 2) + 1) * (attempt % 2 ? -1 : 1);
                chosen = { ...initial, x: initial.x + (vertical ? offset * stepX : 0), y: initial.y + (vertical ? 0 : offset * stepY) };
            }
            positions.set(node.id, chosen);
            occupied.push(chosen);
        }
    }
    return positions;
}
//# sourceMappingURL=graph-layouts.js.map