// Browser-local script files. Never interpret paths or execute file contents.
import {readSourceFile, saveSourceFile} from '../cdeadmin_ui/editors/scriptFiles';
export const readFirebirdScriptFile = readSourceFile;

export function saveFirebirdScriptFile(source) {
  return saveSourceFile(source, 'firebird-script.sql');
}
