/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-4d0c8910f2dc","version":"ddn-next-1","releaseHash":"3a8a08e0de181224d2ea68fe4e723d8925be7c4165927abbf9a6d63554e103a8","dependencies":[],"modules":[{"id":"presentation/src/table.js","bytes":3740,"sha256":"01576f7de6152d47b9834e2ce548e454b51a47bcbbc60af13f7903e7ebe27980","dependencies":[]}],"hash":"809ccf349de2fc4f2a4047a89d8eedb19cb07ff5ae91bd4d7996686648cba683"},{"presentation/src/table.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.columnPercentages = columnPercentages;
exports.wrapCell = wrapCell;
exports.layoutTable = layoutTable;
function columnPercentages(columns) {
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
function wrapCell(value, width, measure, maxLines = 6) {
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
function layoutTable(columns, rows, width, measure, options = {}) {
    const percentages = columnPercentages(columns);
    const widths = percentages.map(p => width * p / 100);
    const pad = 8;
    const lineHeight = options.lineHeight ?? 20;
    const characterWidth = measure('0');
    const fits = columns.length > 0 && columns.every((c, i) => (widths[i] ?? 0) >= characterWidth * Math.max(1, c.min_chars ?? options.minChars ?? 1) + pad * 2);
    if (!fits)
        return { fits: false, widths, percentages, rows: [], height: 32 };
    const source = options.header === false ? rows : [columns.map(c => c.label ?? c.id), ...rows];
    const laid = source.map(row => { const cells = columns.map((c, i) => wrapCell(row[i], Math.min((widths[i] ?? 0) - pad * 2, c.max_chars === undefined ? Infinity : characterWidth * c.max_chars), measure, c.max_lines ?? options.maxLines ?? 6)); return { cells, height: Math.max(...cells.map(c => c.lines.length), 1) * lineHeight + pad }; });
    return { fits, widths, percentages, rows: laid, height: laid.reduce((sum, row) => sum + row.height, 0) };
}

}});})();
