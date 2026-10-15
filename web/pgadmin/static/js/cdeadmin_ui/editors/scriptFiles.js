// Browser-local source only. File contents never change a connection or execute.
import gettext from 'sources/gettext';

const LIMIT = 1024 * 1024;
export async function readSourceFile(file) {
  if (!file || file.size > LIMIT) throw new Error(gettext('SQL script files must be at most 1 MiB.'));
  let source;
  try {
    const bytes = await file.arrayBuffer();
    if (bytes.byteLength > LIMIT) throw new Error();
    source = new TextDecoder('utf-8', {fatal: true}).decode(bytes);
  } catch { throw new Error(gettext('SQL script files must contain valid UTF-8 text of at most 1 MiB.')); }
  if (source.includes('\0')) throw new Error(gettext('SQL script files must not contain NUL.'));
  return source;
}

export function saveSourceFile(source, filename='query-script.sql') {
  if (new TextEncoder().encode(source).length > LIMIT) throw new Error(gettext('SQL script files must be at most 1 MiB.'));
  const url = URL.createObjectURL(new Blob([source], {type: 'text/plain;charset=utf-8'}));
  const link = document.createElement('a');
  link.href = url; link.download = filename;
  document.body.appendChild(link); link.click(); link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
