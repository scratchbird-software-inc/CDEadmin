// PostgreSQL owns completion semantics; the shared editor owns reply lifetime.
export function registerPostgresqlCompletion(editor, current) {
  editor.registerAutocomplete(async (context, available) => {
    const initial = {...current()};
    const source = context.state.doc.toString();
    const prefix = context.state.sliceDoc(0, context.pos);
    const word = context.matchBefore(/[\p{L}\p{N}_$]*/u);
    const applicable = () => {
      const latest = current();
      return latest.active && !latest.blocked && latest.scope === initial.scope && latest.post === initial.post &&
        !context.aborted && editor.state.doc.toString() === source &&
        editor.state.selection.main.head === context.pos;
    };
    try {
      if (!initial.active || initial.blocked || !word || context.aborted) return null;
      const session = await initial.ensureSession();
      if (!current().active || current().scope !== initial.scope || context.aborted) return null;
      const result = await initial.post({action: 'source_complete', session_id: session,
        source, source_before_cursor: prefix, database_target_id: initial.databaseTargetId});
      if (!applicable()) return null;
      if (result.editor_context) initial.onMetadata?.(result.editor_context);
      return {from: word.from, options: Object.entries(result.completions || result || {}).slice(0, 1000)
        .map(([label, details]) => ({label, type: details.object_type || 'text'}))};
    } catch (failure) {
      if (applicable()) initial.onError('Native PostgreSQL completion is unavailable: ' + failure.message);
      return null;
    } finally { available(); }
  });
}
