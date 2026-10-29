const topicRoles = new Set(['domain', 'entity', 'object', 'term']);
export function isMindmapTopic(record) {
    return record.category !== 'relation' && topicRoles.has(typeof record.role === 'string' ? record.role : 'object');
}
export function mindmapKey(record) {
    return record.file + '\0' + record.ref.id;
}
/** topicKeys contains only the selected topic definitions in this view. */
export function mindmapRelationKind(from, to, topicKeys) {
    if (!from || !to)
        return 'unresolved';
    const source = topicKeys.has(mindmapKey(from)), target = topicKeys.has(mindmapKey(to));
    return source && target ? 'internal' : source || target ? 'external' : 'unrelated';
}
//# sourceMappingURL=mindmap.js.map