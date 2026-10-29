/** Small local interface glyphs. Diagram symbols and brand artwork stay separate. */
const paths = {
    eye: 'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Zm13 0a3 3 0 1 1-6 0 3 3 0 0 1 6 0',
    pen: 'm15 4 5 5M4 20l5-1L21 7a2 2 0 0 0-5-5L4 14l-1 7Z',
    check: 'm5 12 4 4L19 6',
    folder: 'M3 7V4h6l2 3h10v13H3Z',
    code: 'm8 5-7 7 7 7m8-14 7 7-7 7M14 3l-4 18',
    download: 'M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5',
    upload: 'M12 16V4m-5 5 5-5 5 5M4 16v5h16v-5',
    undo: 'M8 4 3 9l5 5M3 9h10a7 7 0 0 1 0 14',
    redo: 'm16 4 5 5-5 5m5-5H11a7 7 0 0 0 0 14',
    reflow: 'M19 8A8 8 0 0 0 5 6L2 9m0-5v5h5m-2 7a8 8 0 0 0 14 2l3-3m0 5v-5h-5M9 10h6v4H9Z',
    settings: 'M4 6h16M4 12h16M4 18h16M8 3v6m8 0v6m-6 0v6',
    chevron: 'm6 9 6 6 6-6',
    grid: 'M3 3h7v7H3ZM14 3h7v7h-7ZM3 14h7v7H3Zm11 0h7v7h-7Z',
    plus: 'M12 4v16M4 12h16',
    minus: 'M4 12h16',
    'arrow-left': 'm11 5-7 7 7 7M4 12h16',
    'arrow-right': 'm13 5 7 7-7 7M4 12h16',
    expand: 'M9 3H3v6m12-6h6v6M3 15v6h6m6 0h6v-6',
    fit: 'M3 8V3h5m8 0h5v5M3 16v5h5m8 0h5v-5M8 8h8v8H8Z',
    search: 'M16 10a6 6 0 1 1-12 0 6 6 0 0 1 12 0Zm-1 5 6 6',
    link: 'm10 8 3-3a4 4 0 0 1 6 6l-3 3m-2 2-3 3a4 4 0 0 1-6-6l3-3m1 5 6-6',
    type: 'M3 5V3h18v2M12 3v18m-4 0h8',
    table: 'M3 3h18v18H3Zm0 6h18M9 3v18',
    layers: 'm12 3 10 5-10 5L2 8Zm-10 9 10 5 10-5M2 16l10 5 10-5',
    info: 'M12 8h.01M11 11h1v6m-1 0h2M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0',
    palette: 'M12 3a9 9 0 1 0 0 18h1a2 2 0 0 0 1-4 2 2 0 0 1 1-4h3a3 3 0 0 0 3-3c0-4-4-7-9-7ZM7 9h.01M10 6h.01M15 6h.01M6 13h.01',
};
export function uiIcon(document, name) {
    const ns = 'http://www.w3.org/2000/svg', svg = document.createElementNS(ns, 'svg'), path = document.createElementNS(ns, 'path');
    svg.classList.add('ddn-ui-icon');
    svg.setAttribute('viewBox', '0 0 24 24');
    svg.setAttribute('width', '16');
    svg.setAttribute('height', '16');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.7');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    path.setAttribute('d', paths[name] ?? paths.settings);
    svg.append(path);
    return svg;
}
//# sourceMappingURL=ui-icons.js.map