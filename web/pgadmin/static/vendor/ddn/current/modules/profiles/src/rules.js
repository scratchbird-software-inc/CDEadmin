import { indexRecords, resolveRecord, enclosingDefinitions, nativeProfileDiagnostics, nativeProfileIds } from './core.js';
import { isRecord } from './schema-core.js';
export function rulesFor(ids, additional) {
    return ids.map(id => ({
        id: (nativeProfileIds.includes(id) ? 'ddn.native.' : 'ddn.profile.') + id, version: id === 'mindmap.basic@1' ? '1.0.1' : '1.0.0', profiles: [id], levels: ['semantic', 'review', 'publication'], purposes: ['*'],
        readPaths: ['views', 'definitions', 'appearances', 'data'], globalScope: true,
        async evaluate(input, options, context) {
            const records = indexRecords(input.normalized);
            const target = options.scope.kind === 'workarea' ? undefined : resolveRecord(records, options.scope.target.file, options.scope.target);
            const key = (r) => r.file + '\0' + r.ref.id;
            const selectedViews = new Set();
            if (target?.owner === 'view_definition')
                selectedViews.add(key(target));
            // A document contains targeted-output inclusions, not its own diagram
            // profile. Apply profile rules to its included views at document scope.
            const documents = target?.owner === 'document' ? [target] : [];
            const seenDocuments = new Set(documents.map(key));
            for (let i = 0; i < documents.length; i++) {
                const document = documents[i], sections = document.record.sections;
                await context.checkpoint(Array.isArray(sections) ? sections.length + 1 : 1);
                for (const section of Array.isArray(sections) ? sections.filter(isRecord) : []) {
                    if (section.kind !== 'view')
                        continue;
                    const included = resolveRecord(records, document.file, section.target);
                    if (included?.owner === 'view_definition')
                        selectedViews.add(key(included));
                    else if (included?.owner === 'document' && !seenDocuments.has(key(included))) {
                        seenDocuments.add(key(included));
                        documents.push(included);
                    }
                }
            }
            if (target?.owner === 'appearance') {
                const view = resolveRecord(records, target.file, target.record.parent);
                if (view)
                    selectedViews.add(key(view));
            }
            if (target?.owner === 'definition') {
                const owners = new Set(enclosingDefinitions(records, target).map(key));
                for (const occurrence of records.filter(r => r.owner === 'appearance')) {
                    const definition = resolveRecord(records, occurrence.file, occurrence.record.target);
                    if (definition && owners.has(key(definition))) {
                        const view = resolveRecord(records, occurrence.file, occurrence.record.parent);
                        if (view)
                            selectedViews.add(key(view));
                    }
                }
            }
            const views = records.filter(r => r.owner === 'view_definition' && (r.record.profile ?? 'ddn@1') === id && (options.scope.kind === 'workarea' || selectedViews.has(key(r))));
            const diagnostics = [];
            for (const view of views) {
                await context.checkpoint(records.length);
                const review = options.level === 'review' || options.level === 'publication';
                diagnostics.push(...nativeProfileDiagnostics(input.normalized, view, records, review));
                if (additional && !nativeProfileIds.includes(id))
                    diagnostics.push(...additional(view, records, review));
                await context.checkpoint(1);
            }
            const unavailable = diagnostics.filter(d => d.code === 'DDN-TABLE-INCOMPLETE' || d.code.endsWith('-INCOMPLETE') || d.code.endsWith('-UNKNOWN') || d.code === 'DDN-ANALYSIS-BUDGET').map(d => d.message);
            return { outcome: diagnostics.some(d => d.severity === 'error') ? 'invalid' : unavailable.length ? 'incomplete' : 'valid', diagnostics, dependencies: views.map(r => ({ target: r.ref, path: '*', fingerprint: input.semanticFingerprint })), coverage: { scope: options.scope, complete: unavailable.length === 0, checked: views.map(r => r.ref), unavailable } };
        }
    }));
}
//# sourceMappingURL=rules.js.map