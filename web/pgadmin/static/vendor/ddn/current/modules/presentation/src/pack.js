import { completeProfileIds, getProfile } from '../../profiles/src/index.js';
import { resolveProperties } from '../../defaults/src/index.js';
import { fingerprint } from '../../execution/src/index.js';
import { projectSnapshot } from './project.js';
import { records, object, refKey } from './model.js';
/** Portable projection registrations; the browser remains responsible for measurement. */
export function createCompletePresentationPack() {
    const projections = [...new Set(completeProfileIds.map(id => getProfile(id).projection))].map(id => ({
        id, profiles: completeProfileIds.filter(profile => getProfile(profile).projection === id),
        readPaths: ['views', 'definitions', 'appearances', 'placements', 'data', 'assets'],
        async measure(input, context) {
            const all = records(input.snapshot);
            await context.checkpoint(all.length);
            const requests = new Map();
            const measure = (text, size, fontKey) => {
                const key = metricId(text, size, fontKey);
                requests.set(key, { id: key, text, fontKey, constraints: { size } });
                return text.length * size * .58;
            };
            const scene = projectSnapshot(input.snapshot, {
                profiles: completeProfileIds.filter(profile => getProfile(profile).projection === id),
                resolve: (target, options) => resolveInput(input, target, options), measure,
                ...(input.scope.kind === 'view' ? { onlyView: input.scope.target } : {}),
            });
            for (const item of scene.items)
                for (const primitive of item.primitives)
                    if (primitive.kind === 'text')
                        for (const run of primitive.runs)
                            measure(run.text, Number(run.style['font-size']) || 16, run.fontKey);
            await context.checkpoint(requests.size);
            return [...requests.values()];
        },
        async project(input, metrics, context) {
            if (fingerprint(metrics.revision) !== fingerprint(input.snapshot.revision) || fingerprint(metrics.versions) !== fingerprint(input.snapshot.versions) || metrics.fingerprint !== input.snapshot.semanticFingerprint || metrics.fontGeneration !== input.fontGeneration)
                throw Error('Projection measurement evidence is stale or belongs to another model');
            await context.checkpoint(records(input.snapshot).length);
            const measurements = object(metrics.measurements);
            const projection = projectSnapshot(input.snapshot, {
                profiles: completeProfileIds.filter(profile => getProfile(profile).projection === id),
                resolve: (target, options) => resolveInput(input, target, options),
                measure(text, size, fontKey) {
                    const value = measurements[metricId(text, size, fontKey)];
                    const width = typeof value === 'number' ? value : object(value).width;
                    return typeof width === 'number' && Number.isFinite(width) && width >= 0 ? width : text.length * size * .58;
                },
                ...(input.scope.kind === 'view' ? { onlyView: input.scope.target } : {}),
            });
            const targets = new Set();
            if (input.scope.kind === 'item')
                targets.add(refKey(input.scope.target));
            const items = projection.items.filter(item => !targets.size || targets.has(refKey(item.target)));
            await context.checkpoint(items.reduce((total, item) => total + item.primitives.length, 0));
            const dependencyFingerprint = fingerprint([input.snapshot.semanticFingerprint, input.resolvedProperties, input.fontGeneration, input.styleGeneration, id]);
            const generation = fingerprint([dependencyFingerprint, items]);
            const next = new Set(items.map(item => item.occurrence));
            const checked = [...new Map(items.map(item => [refKey(item.target), item.target])).values()];
            return { baseGeneration: fingerprint(input.previous ?? []), generation, revision: input.snapshot.revision, dependencyFingerprint,
                versions: input.snapshot.versions, fontGeneration: input.fontGeneration, styleGeneration: input.styleGeneration,
                upsert: items, remove: (input.previous ?? []).filter(item => !next.has(item.occurrence)).map(item => item.occurrence),
                coverage: { ...projection.coverage, scope: input.scope, checked },
            };
        },
    }));
    return { manifest: { id: 'ddn-complete-presentation', version: '1.0.0', api: '1.0', hash: fingerprint(completeProfileIds), languages: ['ddn-next-1'], defaults: ['ddn-next-1'], profiles: completeProfileIds, dependencies: ['ddn-complete'], capabilities: ['projection.complete'] }, registrations: { projections } };
}
function metricId(text, size, fontKey) { return 'text:' + fingerprint([text, size, fontKey]); }
function resolveInput(input, target, options) {
    const resolved = resolveProperties(input.snapshot, target, options);
    const supplied = object(object(input.resolvedProperties)[refKey(target)]);
    return { ...resolved, values: { ...resolved.values, ...supplied } };
}
//# sourceMappingURL=pack.js.map