import { wrapCell } from './table.js';
/** Separate type and name columns share geometry in sizing and painting. */
export function cardTextLayout(type, title, width, measure, typeSize, titleSize, padding = 12) {
    const available = Math.max(8, width - padding * 2);
    const typeWidth = type ? Math.min(Math.max(20, measure(type, typeSize)), Math.max(20, Math.min(96, available * .32))) : 0;
    const gap = type ? 12 : 0;
    const titleOffset = padding + typeWidth + gap;
    const titleWidth = Math.max(8, width - padding - titleOffset);
    const typeLines = type ? wrapCell(type, typeWidth, text => measure(text, typeSize), 64).lines : [];
    return { typeWidth, typeLines, titleOffset, titleWidth, titleLines: wrapCell(title, titleWidth, text => measure(text, titleSize), 64).lines };
}
//# sourceMappingURL=card-text.js.map