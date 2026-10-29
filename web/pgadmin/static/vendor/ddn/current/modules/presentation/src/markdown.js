export function safeURL(value) {
    try {
        const url = new URL(value);
        return ['https:', 'http:', 'mailto:'].includes(url.protocol) ? url.href : undefined;
    }
    catch {
        return undefined;
    }
}
export function inlineMarkdown(text, depth = 0) {
    if (depth > 8)
        return [{ text }];
    const runs = [];
    let start = 0;
    const matcher = /(\*\*|__|\+\+|\*|_|`)(.+?)\1|\[([^\]]+)\]\(([^)]+)\)/g;
    let match;
    while ((match = matcher.exec(text))) {
        if (match.index > start)
            runs.push({ text: text.slice(start, match.index) });
        if (match[3] !== undefined) {
            const href = safeURL(match[4] ?? '');
            runs.push(href ? { text: match[3], href } : { text: match[3] });
        }
        else {
            const marker = match[1];
            const children = marker === '`' ? [{ text: match[2] ?? '' }] : inlineMarkdown(match[2] ?? '', depth + 1);
            for (const run of children)
                runs.push({ ...run, ...(marker === '**' || marker === '__' ? { bold: true } : marker === '++' ? { underline: true } : marker === '`' ? { code: true } : { italic: true }) });
        }
        start = matcher.lastIndex;
    }
    if (start < text.length || !runs.length)
        runs.push({ text: text.slice(start) });
    return runs;
}
export function markdownBlocks(text, formatted = true) {
    if (!formatted)
        return text.split(/\r?\n/).map(line => ({ runs: [{ text: line }], heading: 0, list: false, quote: false, code: false }));
    const blocks = [];
    let paragraph = [];
    let code = false;
    const flush = () => {
        if (paragraph.length) {
            blocks.push({ runs: inlineMarkdown(paragraph.join(' ')), heading: 0, list: false, quote: false, code: false });
            paragraph = [];
        }
    };
    for (const line of text.replace(/\r\n?/g, '\n').split('\n')) {
        if (/^\s*```/.test(line)) {
            flush();
            code = !code;
            continue;
        }
        if (code) {
            blocks.push({ runs: [{ text: line, code: true }], heading: 0, list: false, quote: false, code: true });
            continue;
        }
        if (!line.trim()) {
            flush();
            blocks.push({ runs: [{ text: '' }], heading: 0, list: false, quote: false, code: false });
            continue;
        }
        const heading = /^(#{1,6})\s*(.*)$/.exec(line);
        const list = /^\s*(?:[-*+] |\d+\. )(.*)$/.exec(line);
        const quote = /^\s*>\s?(.*)$/.exec(line);
        if (heading || list || quote) {
            flush();
            blocks.push({ runs: inlineMarkdown(heading?.[2] ?? list?.[1] ?? quote?.[1] ?? ''), heading: heading?.[1]?.length ?? 0, list: !!list, quote: !!quote, code: false });
        }
        else
            paragraph.push(line.trim());
    }
    flush();
    return blocks;
}
//# sourceMappingURL=markdown.js.map