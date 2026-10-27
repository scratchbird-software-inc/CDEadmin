import {insertCompletionText} from '@codemirror/autocomplete';

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
      const entries = Object.entries(result.completions || result || {}).slice(0, 1000)
        .map(([label, details]) => ({label, details, from: Number.isInteger(details.replacement_start) &&
          details.replacement_start >= 0 && details.replacement_start <= context.pos ? details.replacement_start : word.from}));
      const from = Math.min(word.from, ...entries.map(item => item.from));
      return {from, options: entries.map(item => {
        const option = {label:item.label, type:item.details.object_type || 'text'};
        const insert = item.details.insert_text ?? item.label;
        if (item.from !== from) {
          const offset = item.from - from;
          option.apply = (view, _completion, start, end) => view.dispatch(
            insertCompletionText(view.state, insert, start + offset, end));
        } else if (insert !== item.label) option.apply = insert;
        return option;
      })};
    } catch (failure) {
      if (applicable()) initial.onError('Native PostgreSQL completion is unavailable: ' + failure.message);
      return null;
    } finally { available(); }
  });
}
