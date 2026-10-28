import { applySourcePatches, decodeSources, patchProperty } from '../../language/src/index.js';
import { asRecord, listRecords } from '../../model/src/index.js';
import { canonical, createContext } from '../../execution/src/index.js';
import { runtimeState } from './runtime.js';
/** Materialize explicitly requested data snapshots into save artifacts, never the live model. */
export async function sourcesForSave(runtime, task = {}) {
    const state = runtimeState(runtime);
    let source = runtime.sources(), decoded = state.decoded;
    if (!source || !decoded || !state.current)
        return source;
    // An invalid editing buffer is saved as entered. Old spans must never patch new text.
    if (decoded.documents.some(document => source.files.find(file => file.id === document.file.id)?.text !== document.file.text))
        return source;
    const sourceFingerprint = () => canonical(runtime.sources()?.files.map(file => [file.id, file.revision, file.text]));
    const sourceRevision = sourceFingerprint();
    const revision = canonical(state.current.revision);
    const context = createContext(state.current.versions, task);
    const capturedAt = new Date().toISOString();
    for (const entry of listRecords(state.current.normalized)) {
        const data = entry.kind === 'data' ? entry.record : entry.kind === 'definition' ? asRecord(entry.record.data) : undefined;
        if (!data || data.persist !== 'snapshot' || !data.source || !Array.isArray(data.columns) || !Array.isArray(data.rows) || typeof data.revision !== 'string')
            continue;
        await context.checkpoint(data.rows.length + 1);
        const previous = asRecord(data.snapshot);
        if (previous.revision === data.revision && canonical(previous.columns) === canonical(data.columns) && canonical(previous.rows) === canonical(data.rows))
            continue;
        const snapshot = { columns: data.columns, rows: data.rows, revision: data.revision, captured_at: capturedAt };
        source = applySourcePatches(source, patchProperty(decoded, entry.ref, entry.kind === 'data' ? 'snapshot' : 'data.snapshot', snapshot));
        decoded = decodeSources(source, { ...task, previous: decoded });
        if (!decoded.syntaxValid)
            throw new Error('Unable to preserve the source while saving a data snapshot');
    }
    context.check();
    if (canonical(runtime.snapshot()?.revision) !== revision || sourceFingerprint() !== sourceRevision)
        throw new Error('The document changed while preparing save artifacts; save the current revision again');
    return source;
}
//# sourceMappingURL=save.js.map