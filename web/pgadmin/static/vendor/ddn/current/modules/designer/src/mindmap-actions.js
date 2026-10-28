import { array, object, refKey, records, resolveRecord } from '../../presentation/src/native.js';
import { isMindmapTopic } from '../../profiles/src/mindmap.js';
export function mindmapSelection(handle, selected = handle.selectedEntry()) {
    if (!selected || selected.definition.owner !== 'definition' || selected.view.record.profile !== 'mindmap.basic@1' || !isMindmapTopic(selected.definition.record) || selected.mindmapTopic === false)
        return;
    const entries = handle.scene()?.entries.filter(item => refKey(item.view.ref) === refKey(selected.view.ref)) ?? [];
    const topics = entries.filter(item => item.definition.owner === 'definition' && isMindmapTopic(item.definition.record) && item.mindmapTopic !== false);
    const keys = new Set(topics.map(item => refKey(item.definition.ref))), all = handle.runtime.snapshot() ? records(handle.runtime.snapshot()) : [];
    const internal = entries.filter(item => item.definition.record.category === 'relation' && item.definition.record.role === 'assoc').flatMap(item => {
        const ends = array(item.definition.record.endpoints).map(object), from = resolveRecord(all, ends[0]?.definition, item.definition.file), to = resolveRecord(all, ends[1]?.definition, item.definition.file);
        return from && to && keys.has(refKey(from.ref)) && keys.has(refKey(to.ref)) ? [{ entry: item, from, to }] : [];
    });
    const incoming = internal.find(link => refKey(link.to.ref) === refKey(selected.definition.ref));
    const parent = incoming && topics.find(item => refKey(item.definition.ref) === refKey(incoming.from.ref));
    const parentRight = !!parent && parent.item.bounds.x + parent.item.bounds.width / 2 > selected.item.bounds.x + selected.item.bounds.width / 2;
    return { selected, topics, internal, incoming, left: !incoming || parentRight, right: !incoming || !parentRight };
}
/** Screen-sized editing controls live outside the capture scene. */
export function mountMindmapActions(viewer, handle, bounds, actions) {
    const document = handle.ownerDocument, bar = document.createElement('div'), css = document.createElement('style');
    bar.className = 'ddn-mindmap-actions';
    bar.setAttribute('role', 'toolbar');
    bar.setAttribute('aria-label', 'Mind map topic actions');
    bar.hidden = true;
    css.textContent = '.ddn-mindmap-actions{position:absolute;z-index:8;display:flex;justify-content:space-evenly;align-items:center;gap:4px;height:30px;pointer-events:none!important}.ddn-mindmap-actions[hidden]{display:none}.ddn-mindmap-actions>button{pointer-events:auto;flex:none;display:grid;place-items:center;min-width:26px;width:26px;height:26px;padding:0;border:1px solid var(--ddn-ui-border);border-radius:50%;background:var(--ddn-ui-surface);color:var(--ddn-ui-text);font-size:15px;line-height:1;box-shadow:0 1px 4px #14243626}.ddn-mindmap-actions>button:hover{border-color:var(--ddn-ui-accent);background:var(--ddn-ui-surface-alt)}.ddn-mindmap-actions>button:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:2px}';
    handle.container.append(css);
    handle.overlays.append(bar);
    let signature = '', disposed = false;
    const stop = (event) => event.stopPropagation();
    for (const event of ['pointerdown', 'dblclick', 'keydown', 'keyup'])
        bar.addEventListener(event, stop);
    const update = () => {
        if (disposed)
            return;
        const selected = mindmapSelection(handle);
        if (!selected) {
            bar.hidden = true;
            signature = '';
            return;
        }
        const body = bounds(selected.selected), matrix = handle.surface.getScreenCTM(), overlay = handle.overlays.getBoundingClientRect();
        if (!matrix) {
            bar.hidden = true;
            return;
        }
        const point = handle.surface.createSVGPoint();
        point.x = body.x;
        point.y = body.y + body.height;
        const origin = point.matrixTransform(matrix);
        point.x += body.width;
        const end = point.matrixTransform(matrix);
        const width = Math.max(130, end.x - origin.x), center = (origin.x + end.x) / 2 - overlay.left, top = origin.y - overlay.top + 3;
        bar.hidden = top < 0 || top > overlay.height - 26 || center < 0 || center > overlay.width;
        bar.style.left = center - width / 2 + 'px';
        bar.style.top = top + 'px';
        bar.style.width = width + 'px';
        const next = selected.selected.item.occurrence + ':' + selected.left + ':' + selected.right;
        if (next === signature)
            return;
        signature = next;
        bar.replaceChildren();
        const button = (symbol, name, action) => {
            const element = document.createElement('button');
            element.type = 'button';
            element.textContent = symbol;
            element.title = name;
            element.setAttribute('aria-label', name);
            element.addEventListener('click', event => {
                event.stopPropagation();
                try {
                    Promise.resolve(action()).catch(error => handle.announce(error instanceof Error ? error.message : String(error)));
                }
                catch (error) {
                    handle.announce(error instanceof Error ? error.message : String(error));
                }
            });
            bar.append(element);
        };
        if (selected.left)
            button('⥆', 'Add linked topic to the left', () => actions.add(handle.selectedEntry(), 'left'));
        if (selected.right)
            button('⥅', 'Add linked topic to the right', () => actions.add(handle.selectedEntry(), 'right'));
        button('🗑️', 'Delete topic', () => actions.remove(handle.selectedEntry()));
        button('📝', 'Edit topic name', () => actions.name(handle.selectedEntry()));
        button('📓', 'Add, edit or delete topic notes', () => actions.notes(handle.selectedEntry()));
    };
    const unsubscribe = viewer.subscribe(event => { if (['ready', 'selection', 'viewport'].includes(event.kind))
        update(); });
    const selection = handle.subscribeSelection(update), Resize = document.defaultView?.ResizeObserver, resize = Resize ? new Resize(update) : undefined;
    resize?.observe(handle.surface);
    update();
    return () => { disposed = true; resize?.disconnect(); unsubscribe(); selection(); bar.remove(); css.remove(); };
}
//# sourceMappingURL=mindmap-actions.js.map