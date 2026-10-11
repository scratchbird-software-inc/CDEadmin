// Firebird virtual branches precede objects, independent of tree node class.
export function compareFirebirdNodes(a, b) {
  const left = a._metadata?.data;
  const right = b._metadata?.data;
  if (left?.cde_engine_id !== 'firebird' || right?.cde_engine_id !== 'firebird') return null;
  const virtual = (data) => data._type === 'cde_resource_group' || Boolean(data.cde_section);
  const groupOrder = Number(virtual(right)) - Number(virtual(left));
  return groupOrder || a.fileName.localeCompare(b.fileName, undefined, {sensitivity: 'base', numeric: true});
}
