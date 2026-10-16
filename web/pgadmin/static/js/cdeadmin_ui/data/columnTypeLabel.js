// Compact display labels; provider types, binding and DDL keep their full names.
export function columnTypeLabel(type) {
  return String(type ?? '').replace(
    /^(\[PK\]\s*)?(character|integer)(?=\s|\(|\[|$)/i,
    (_match, key, name) => (key || '') +
      (name.toLowerCase() === 'character' ? 'char' : 'int')
  );
}
