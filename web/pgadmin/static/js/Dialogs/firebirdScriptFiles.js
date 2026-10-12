// Browser-local script files. Never interpret paths or execute file contents.
import gettext from 'sources/gettext';
export async function readFirebirdScriptFile(file) {
  if (!file || file.size > 1024 * 1024) throw new Error(gettext('SQL script files must be at most 1 MiB.'));
  let source;
  try { source = new TextDecoder('utf-8', {fatal: true}).decode(await file.arrayBuffer()); }
  catch { throw new Error(gettext('SQL script files must contain valid UTF-8 text.')); }
  if (source.includes('\0')) throw new Error(gettext('SQL script files must not contain NUL.'));
  return source;
}

export function saveFirebirdScriptFile(source) {
  const url = URL.createObjectURL(new Blob([source], {type: 'text/plain;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url; link.download = 'firebird-script.sql';
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
