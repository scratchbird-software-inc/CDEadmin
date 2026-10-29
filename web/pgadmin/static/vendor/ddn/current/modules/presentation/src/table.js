export function columnPercentages(columns) {
    if (!columns.length)
        return [];
    const values = columns.map(c => c.percentage === undefined ? null : c.percentage);
    if (values.some(v => v !== null && (!Number.isFinite(v) || v < 0)))
        throw new Error('Invalid column percentage');
    const widths = values.map(v => v ?? 0);
    let sum = widths.reduce((a, b) => a + b, 0);
    if (sum > 100) {
        let excess = sum - 100;
        while (excess > 1e-9) {
            const greatest = Math.max(...widths);
            const top = widths.map((n, i) => n === greatest ? i : -1).filter(i => i >= 0);
            const next = Math.max(0, ...widths.filter(n => n < greatest));
            const reduction = Math.min(excess / top.length, greatest - next);
            if (reduction <= 0)
                break;
            for (const index of top)
                widths[index] = (widths[index] ?? 0) - reduction;
            excess -= reduction * top.length;
        }
        sum = 100;
    }
    const auto = values.map((n, i) => n === null ? i : -1).filter(i => i >= 0);
    if (auto.length)
        for (const i of auto)
            widths[i] = (100 - sum) / auto.length;
    else if (sum < 100)
        widths[widths.length - 1] = (widths[widths.length - 1] ?? 0) + 100 - sum;
    return widths;
}
export function wrapCell(value, width, measure, maxLines = 6) {
    const text = value === null || value === undefined ? '' : typeof value === 'object' ? JSON.stringify(value) : String(value);
    const normalized = text.replace(/\r\n?|\n/g, ' ');
    const output = [];
    let line = '';
    for (const word of normalized.match(/\S+\s*|\s+/g) ?? ['']) {
        if (line && measure(line + word) > width) {
            output.push(line.trimEnd());
            line = '';
        }
        for (const char of word) {
            if (line && measure(line + char) > width) {
                output.push(line.trimEnd());
                line = '';
            }
            line += char;
        }
    }
    if (line || !output.length)
        output.push(line.trimEnd());
    const cap = Math.max(1, Math.floor(maxLines));
    const truncated = output.length > cap;
    const lines = output.slice(0, cap);
    if (truncated) {
        let last = lines[cap - 1] ?? '';
        while (last && measure(last + '…') > width)
            last = last.slice(0, -1);
        lines[cap - 1] = last + '…';
    }
    return { value: text, lines, truncated };
}
export function layoutTable(columns, rows, width, measure, options = {}) {
    const percentages = columnPercentages(columns);
    const widths = percentages.map(p => width * p / 100);
    const pad = 8;
    const lineHeight = options.lineHeight ?? 20;
    // Character units are the default font's zero advance, not a wide glyph.
    const characterWidth = measure('0');
    const fits = columns.length > 0 && columns.every((c, i) => (widths[i] ?? 0) >= characterWidth * Math.max(1, c.min_chars ?? options.minChars ?? 1) + pad * 2);
    if (!fits)
        return { fits: false, widths, percentages, rows: [], height: 32 };
    const source = options.header === false ? rows : [columns.map(c => c.label ?? c.id), ...rows];
    const laid = source.map(row => { const cells = columns.map((c, i) => wrapCell(row[i], Math.min((widths[i] ?? 0) - pad * 2, c.max_chars === undefined ? Infinity : characterWidth * c.max_chars), measure, c.max_lines ?? options.maxLines ?? 6)); return { cells, height: Math.max(...cells.map(c => c.lines.length), 1) * lineHeight + pad }; });
    return { fits, widths, percentages, rows: laid, height: laid.reduce((sum, row) => sum + row.height, 0) };
}
//# sourceMappingURL=table.js.map