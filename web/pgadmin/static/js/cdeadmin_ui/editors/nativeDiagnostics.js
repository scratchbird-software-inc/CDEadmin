// Providers report Unicode character offsets; CodeMirror uses UTF-16 offsets.
// Approximate native positions highlight the reported line rather than inventing
// a precise character position. Unknown grammar never produces an error mark.
export function diagnosticRanges(source, diagnostics) {
  const characters = Array.from(source);
  const offset = value => characters.slice(0, Math.max(0, Math.min(characters.length, value))).join('').length;
  return diagnostics.filter(item => item.severity === 'error').map(item => {
    let from = Number.isInteger(item.offset) ? offset(item.offset) : 0;
    let to = offset(Number.isInteger(item.offset_end) ? item.offset_end + 1 : (item.offset || 0) + 1);
    if (item.position_exact === false) {
      from = source.lastIndexOf('\n', Math.max(0, from - 1)) + 1;
      const end = source.indexOf('\n', from);
      to = end < 0 ? source.length : end;
    }
    if (from === source.length && from > 0) from--;
    return {from, to: Math.max(from, Math.min(source.length, to)), message: item.message};
  }).filter(item => item.to > item.from);
}
