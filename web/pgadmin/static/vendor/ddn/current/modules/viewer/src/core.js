import { createDrawer } from './drawer.js';
import { sideTabs } from './side-tabs.js';
import { sanitizeSvgAsset } from './svg-assets.js';
import { analyzePresentedProfile as analyzeProfile, isDataProfile } from '../../presentation/src/adapters.js';
import { registrations } from '../../runtime/src/registry.js';
import { createRuntime } from '../../runtime/src/native.js';
import { resolveProperties, validatePreview, parseStylesheet } from '../../defaults/src/index.js';
import { publicationScene, resolveRecord, projectSnapshot, availableProjectionProfiles, recordTableData, findRecord, refKey, titleOf, records, tableData, object, str, num, pathValue, unionBounds, inheritedPresentation } from '../../presentation/src/native.js';
import { installUITheme } from './ui-theme.js';
import { uiIcon } from './ui-icons.js';
import { createStandardDialog } from './dialogs.js';
import { fontFamily, installFontResources, fontCSS } from './fonts.js';
import { createTexturePattern } from './texture.js';
import { registerUICommands, notifyUICommands } from './ui-commands.js';
import { gridStep, viewSetting } from './grid.js';
import { installStatusHint, statusHint } from './status-hint.js';
import { constrainStandaloneViewport, sameBounds } from './standalone-viewport.js';
export { setUITheme, installUITheme, UI_THEME_NAMES, UI_THEME_TOKEN_NAMES } from './ui-theme.js';
export { installFontResources, listFonts, loadFontFile, getFontResources } from './fonts.js';
const NS = 'http://www.w3.org/2000/svg';
function displayTableData(snapshot, item) { return item.record.profile === 'table.records@1' ? recordTableData(snapshot, item) : tableData(snapshot, item); }
const handles = new WeakMap();
export function getViewerHandle(viewer) {
    const handle = handles.get(viewer);
    if (!handle)
        throw new Error('Viewer is not active');
    return handle;
}
function cssPaint(value) { const valueString = String(value); return /url\s*\(|expression\s*\(|[<>]/i.test(valueString) ? 'none' : valueString; }
function backgroundPrimitive(bounds, fill, texture) { return { kind: 'path', d: `M${bounds.x},${bounds.y}h${bounds.width}v${bounds.height}h${-bounds.width}Z`, paint: { fill: cssPaint(fill), ...(texture ? { 'ddn-texture': texture } : {}) } }; }
function svgElement(document, name, attrs = {}) {
    const element = document.createElementNS(NS, name);
    for (const [key, value] of Object.entries(attrs))
        element.setAttribute(key, String(value));
    return element;
}
function realize(document, primitive, assets, effect) {
    let result;
    if (primitive.kind === 'path')
        result = svgElement(document, 'path', { d: primitive.d });
    else if (primitive.kind === 'rect')
        result = svgElement(document, 'rect', { ...primitive.bounds, rx: 4 });
    else if (primitive.kind === 'ellipse') {
        const b = primitive.bounds;
        result = svgElement(document, 'ellipse', { cx: b.x + b.width / 2, cy: b.y + b.height / 2, rx: b.width / 2, ry: b.height / 2 });
    }
    else if (primitive.kind === 'text') {
        result = svgElement(document, 'text');
        for (const run of primitive.runs) {
            const span = svgElement(document, 'tspan', { x: run.x, y: run.y, 'font-family': fontFamily(run.fontKey) });
            span.textContent = run.text;
            for (const [key, value] of Object.entries(run.style))
                if (['font-size', 'font-weight', 'font-style', 'font-variant', 'text-decoration', 'text-anchor', 'fill', 'opacity'].includes(key))
                    span.setAttribute(key, cssPaint(value));
            result.append(span);
        }
        return result;
    }
    else if (primitive.kind === 'image' && assets.has(primitive.assetId)) {
        result = svgElement(document, 'image', { ...primitive.bounds, href: assets.get(primitive.assetId).dataURL, preserveAspectRatio: 'xMidYMid meet' });
        return result;
    }
    else {
        result = svgElement(document, 'g');
        result.append(svgElement(document, 'rect', { ...primitive.bounds, fill: '#e5e7eb', stroke: '#94a3b8' }));
        const title = svgElement(document, 'title');
        title.textContent = `Asset ${'assetId' in primitive ? primitive.assetId : 'unknown'} requires a supplied provider`;
        result.append(title);
        return result;
    }
    if ('paint' in primitive)
        for (const [key, value] of Object.entries(primitive.paint))
            if (['fill', 'fill-rule', 'stroke', 'stroke-width', 'stroke-dasharray', 'stroke-linecap', 'stroke-linejoin', 'opacity', 'fill-opacity', 'stroke-opacity', 'rx', 'ry'].includes(key))
                result.setAttribute(key, cssPaint(value));
    if ('paint' in primitive) {
        const state = primitive.paint['ddn-design-status'];
        if (typeof state === 'string') {
            const title = svgElement(document, 'title');
            title.textContent = statusHint(state);
            result.append(title);
            result.setAttribute('data-status-dot', state);
            result.setAttribute('aria-label', title.textContent);
            result.setAttribute('role', 'img');
        }
        const pattern = createTexturePattern(document, effect.id + '-texture', primitive.paint['ddn-texture'], cssPaint(primitive.paint.fill ?? 'transparent'));
        if (pattern) {
            const group = svgElement(document, 'g'), defs = svgElement(document, 'defs');
            defs.append(pattern);
            result.setAttribute('fill', `url(#${pattern.id})`);
            group.append(defs, result);
            return group;
        }
        const decoration = primitive.paint['ddn-decoration'];
        if (decoration === 'shadow' || decoration === 'attachment') {
            result.setAttribute('pointer-events', 'none');
            result.setAttribute('aria-hidden', 'true');
        }
        // The scene supplies a bounded numeric blur, never a CSS filter or URL.
        // A local filter is also serialized into SVG/PNG captures.
        const blur = primitive.paint.blur;
        if (typeof blur === 'number' && Number.isFinite(blur) && blur > 0 && blur <= 128) {
            const group = svgElement(document, 'g'), defs = svgElement(document, 'defs');
            const filter = svgElement(document, 'filter', { id: effect.id, filterUnits: 'userSpaceOnUse', ...effect.bounds, 'color-interpolation-filters': 'sRGB' });
            filter.append(svgElement(document, 'feGaussianBlur', { stdDeviation: blur }));
            defs.append(filter);
            result.setAttribute('filter', `url(#${effect.id})`);
            group.append(defs, result);
            return group;
        }
    }
    return result;
}
/** Small UI previews use the same SVG realization as the canvas, without assets
 * or a second viewer/runtime. Input consists of trusted local glyph primitives. */
export function renderPreviewPrimitives(document, primitives, bounds) {
    const group = svgElement(document, 'g');
    const assets = new Map();
    for (const primitive of primitives)
        group.append(realize(document, primitive, assets, { id: 'ddn-glyph-preview', bounds }));
    return group;
}
function serializeScene(document, items, bounds, assets = new Map(), background = 'transparent', texture) {
    const svg = svgElement(document, 'svg', { viewBox: `${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`, width: bounds.width, height: bounds.height, role: 'img' });
    const css = fontCSS(document, items.flatMap(item => item.primitives.flatMap(p => p.kind === 'text' ? p.runs.map(run => run.fontKey) : [])));
    if (css) {
        const style = svgElement(document, 'style');
        style.textContent = css;
        svg.append(style);
    }
    svg.append(texture
        ? realize(document, backgroundPrimitive(bounds, background, texture), assets, { id: 'ddn-export-background', bounds })
        : svgElement(document, 'rect', { ...bounds, fill: cssPaint(background) }));
    for (const item of items) {
        const group = svgElement(document, 'g', { 'data-occurrence': item.occurrence });
        const title = svgElement(document, 'title');
        title.textContent = item.accessible.label;
        group.append(title);
        appendItem(document, group, item, assets);
        svg.append(group);
    }
    const Serializer = document.defaultView?.XMLSerializer ?? XMLSerializer;
    return new Serializer().serializeToString(svg);
}
function appendItem(document, group, item, assets, clipPrefix = 'ddn-export') {
    const content = svgElement(document, 'g', { transform: `matrix(${item.transform.join(' ')})` });
    const hasBlur = item.primitives.some(p => 'paint' in p && typeof p.paint.blur === 'number' && p.paint.blur > 0);
    const encoded = item.clip || hasBlur || item.primitives.some(p => 'paint' in p && p.paint['ddn-texture']) ? Array.from(item.occurrence).map(c => c.codePointAt(0).toString(16)).join('-') : '';
    const localBounds = hasBlur ? localPaintBounds(item) : item.bounds;
    for (const [index, primitive] of item.primitives.entries())
        content.append(realize(document, primitive, assets, { id: `${clipPrefix}-blur-${encoded}-${index}`, bounds: localBounds }));
    if (item.clip) {
        const id = clipPrefix + '-clip-' + encoded;
        const defs = svgElement(document, 'defs'), clip = svgElement(document, 'clipPath', { id, clipPathUnits: 'userSpaceOnUse' });
        clip.append(svgElement(document, 'rect', { ...item.clip }));
        defs.append(clip);
        group.append(defs);
        const clipped = svgElement(document, 'g', { 'clip-path': `url(#${id})` });
        clipped.append(content);
        group.append(clipped);
    }
    else
        group.append(content);
}
function localPaintBounds(item) {
    const [a, b, c, d, tx, ty] = item.transform, determinant = a * d - b * c;
    if (!Number.isFinite(determinant) || Math.abs(determinant) < 1e-12)
        return item.bounds;
    const box = item.bounds;
    const points = [[box.x, box.y], [box.x + box.width, box.y], [box.x, box.y + box.height], [box.x + box.width, box.y + box.height]].map(([x, y]) => ({ x: (d * (x - tx) - c * (y - ty)) / determinant, y: (-b * (x - tx) + a * (y - ty)) / determinant }));
    const x = Math.min(...points.map(p => p.x)), y = Math.min(...points.map(p => p.y));
    return { x, y, width: Math.max(1, ...points.map(p => p.x - x)), height: Math.max(1, ...points.map(p => p.y - y)) };
}
function intersects(a, b) { return a.x <= b.x + b.width && a.x + a.width >= b.x && a.y <= b.y + b.height && a.y + a.height >= b.y; }
export function createViewer(element, options) {
    const document = element.ownerDocument, win = document.defaultView;
    if (!win)
        throw new Error('Viewer needs a browser document');
    const clipPrefix = 'ddn-viewer-' + (win.crypto?.randomUUID?.() ?? Date.now().toString(36) + Math.random().toString(36).slice(2));
    const ownsRuntime = !options.runtime;
    const runtime = options.runtime ?? createRuntime(options.runtimeOptions);
    let disposed = false, projection, currentSnapshot, selection, selectedOccurrence;
    const selectedOccurrences = new Set();
    let spaceHeld = false, announceHoldUntil = 0;
    let viewport = { bounds: { x: 0, y: 0, width: 1280, height: 800 }, zoom: 1 };
    let preview;
    let stale = false, diagnostics = [];
    let runtimeDiagnostics = [];
    let generation = 0;
    let styleGeneration = 0, fontGeneration = 0;
    let rendering = Promise.resolve();
    let workareaBackground = '#f2f4f7';
    let workareaTexture;
    const fontsReady = installFontResources(document);
    const assets = new Map();
    const assetSizes = () => new Map([...assets].flatMap(([id, asset]) => asset.intrinsicSize ? [[id, asset.intrinsicSize]] : []));
    const geography = new Map();
    const geographyHashes = new Map();
    const geographyVersions = new Map();
    const assetFailures = new Set();
    const openListeners = new Set();
    const listeners = new Set(), selectionListeners = new Set();
    const cleanups = [];
    const history = [];
    let historyIndex = -1;
    let restored;
    let drag;
    let expandedView;
    let standalone = false;
    let miniCards;
    const pointers = new Map();
    let pinch;
    let gestureStart;
    const LOD_SCALE = 0.32;
    const container = document.createElement('section');
    container.className = 'ddn-viewer';
    installUITheme(container);
    container.style.height = element.clientHeight > 0 ? '100%' : '600px';
    container.setAttribute('aria-label', 'DDN diagram viewer');
    container.tabIndex = -1;
    const style = document.createElement('style');
    style.textContent = `
.ddn-viewer{font:var(--ddn-ui-font-size) Inter,system-ui,sans-serif;color:var(--ddn-ui-text);display:grid;grid-template-columns:250px minmax(0,1fr);grid-template-rows:auto minmax(200px,1fr) auto;min-height:420px;position:relative;overflow:hidden;background:var(--ddn-ui-bg);border:1px solid var(--ddn-ui-border);border-radius:12px}
.ddn-viewer *{box-sizing:border-box}.ddn-viewer button,.ddn-viewer input,.ddn-viewer select,.ddn-viewer textarea{font:inherit}
.ddn-viewer :is(.ddn-viewer-toolbar,.ddn-viewer-outline,.ddn-designer-menu) button{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid transparent;border-radius:8px;background:transparent;color:inherit;padding:6px 8px;min-height:32px;cursor:pointer;font-size:12px;font-weight:500}
.ddn-viewer :is(.ddn-viewer-toolbar,.ddn-viewer-outline,.ddn-designer-menu) button:hover{background:color-mix(in srgb,var(--ddn-ui-accent) 10%,var(--ddn-ui-surface));color:var(--ddn-ui-accent)}.ddn-viewer :is(.ddn-viewer-toolbar,.ddn-viewer-outline,.ddn-designer-menu) button:disabled{opacity:.45;cursor:default}.ddn-viewer button:focus-visible,.ddn-viewer [tabindex]:focus-visible{outline:2px solid var(--ddn-ui-accent);outline-offset:2px}
.ddn-viewer-toolbar{grid-column:1/-1;display:flex;gap:4px;align-items:center;padding:8px 10px;background:var(--ddn-ui-surface);border-bottom:1px solid var(--ddn-ui-border);flex-wrap:wrap}
.ddn-viewer .ddn-viewer-toolbar button[hidden]{display:none}
.ddn-viewer .ddn-viewer-toolbar [data-primary]{background:color-mix(in srgb,var(--ddn-ui-accent) 15%,var(--ddn-ui-surface));color:var(--ddn-ui-accent);font-weight:650}
.ddn-toolbar-group{display:flex;align-items:center;flex-wrap:wrap;gap:3px;padding-right:7px;margin-right:3px;border-right:1px solid var(--ddn-ui-border)}.ddn-toolbar-group:last-child{border-right:0;margin-right:0;padding-right:0}
.ddn-viewer-outline{grid-column:1;overflow:auto;padding:14px 10px;border-right:1px solid var(--ddn-ui-border);background:color-mix(in srgb,var(--ddn-ui-surface) 70%,var(--ddn-ui-bg));scrollbar-width:thin;scrollbar-color:var(--ddn-ui-border) transparent}
.ddn-outline-heading{font-size:10px;font-weight:650;letter-spacing:.11em;text-transform:uppercase;color:var(--ddn-ui-muted);margin:0 0 12px 4px}.ddn-outline-search{display:flex;align-items:center;gap:6px;background:var(--ddn-ui-input);border:1px solid var(--ddn-ui-border);border-radius:8px;padding:0 8px;color:var(--ddn-ui-muted);margin-bottom:10px}
.ddn-viewer-outline input{min-width:0;width:100%;padding:8px 0;border:0;background:transparent;color:var(--ddn-ui-text);font-size:12px;outline-offset:1px}.ddn-viewer .ddn-viewer-outline .ddn-panel-section>button{display:block;text-align:left;width:100%;margin-top:4px;font-size:12px;overflow-wrap:anywhere;padding:8px 10px;line-height:1.4;color:var(--ddn-ui-muted)}.ddn-viewer-outline button[aria-current=true]{background:color-mix(in srgb,var(--ddn-ui-accent) 13%,var(--ddn-ui-surface));color:var(--ddn-ui-accent);font-weight:650}
.ddn-viewer-stage{grid-column:2;position:relative;min-width:0;min-height:300px;overflow:hidden;background:#ffffff}.ddn-viewer-stage>svg{display:block;width:100%;height:100%;min-height:300px;touch-action:none;user-select:none;-webkit-user-select:none;cursor:grab}.ddn-viewer-stage>svg.ddn-panning{cursor:grabbing}.ddn-viewer-stage>svg [data-ref]{cursor:pointer}.ddn-viewer:not([data-ddn-editing]) .ddn-viewer-stage>svg [data-view-frame=true]{cursor:grab}.ddn-viewer[data-ddn-editing] .ddn-viewer-stage>svg [data-ref][data-movable=true]{cursor:move}.ddn-viewer-stage [data-selected=true]{filter:drop-shadow(0 0 3px #2563eb)}.ddn-viewer-stage>svg .ddn-hit{fill:none;stroke:transparent;stroke-width:14;pointer-events:stroke}.ddn-viewer-stage>svg[data-expanded] g[data-occurrence]:not([data-in-expanded=true]){display:none}.ddn-viewer-stage>svg[data-lod=mini] g[data-occurrence]:not([data-view-frame=true]){display:none}.ddn-viewer-stage>svg[data-lod=mini] g[data-view-frame=true]>g{display:none}.ddn-mini-card{cursor:pointer}.ddn-mini-card .ddn-mini-paper{fill:#ffffff;stroke:#94a3b8;stroke-width:1}.ddn-mini-card[data-active=true] .ddn-mini-paper{stroke:#2563eb;stroke-width:2}.ddn-mini-card text{fill:#1f2933;font-family:Inter,system-ui,sans-serif;font-weight:600}.ddn-mini-card .ddn-mini-meta{fill:#64748b;font-weight:400}.ddn-toolbar-group[aria-label=Zoom]{flex-wrap:nowrap;flex:none}.ddn-zoom-readout{min-width:48px;font-variant-numeric:tabular-nums;color:var(--ddn-ui-muted);font-size:11px;justify-content:center}.ddn-viewer-hint{width:min(420px,calc(100% - 32px));position:absolute;left:50%;top:50%;transform:translate(-50%,-50%);max-width:min(420px,calc(100% - 32px));padding:16px 18px;border-radius:12px;background:color-mix(in srgb,var(--ddn-ui-surface) 94%,transparent);color:var(--ddn-ui-text);border:1px solid var(--ddn-ui-border);box-shadow:0 10px 30px color-mix(in srgb,var(--ddn-ui-shadow) 55%,transparent);font-size:13px;line-height:1.5;text-align:center;pointer-events:none}.ddn-viewer-hint button{pointer-events:auto}.ddn-placing .ddn-viewer-hint{width:min(420px,calc(100% - 32px));display:none}.ddn-viewer-hint p{margin:0 0 10px}.ddn-viewer-hint .ddn-hint-actions{display:flex;gap:8px;justify-content:center;flex-wrap:wrap}.ddn-viewer-hint button{border:1px solid var(--ddn-ui-border);background:var(--ddn-ui-input);color:var(--ddn-ui-text);border-radius:8px;padding:6px 12px;font-size:12px;cursor:pointer}.ddn-viewer-hint button[data-primary]{background:var(--ddn-ui-accent);color:var(--ddn-ui-accent-text);border-color:transparent;font-weight:650}.ddn-viewer-hint small{display:block;margin-top:8px;color:var(--ddn-ui-muted);font-size:11px}
.ddn-viewer-inspector{overflow-wrap:anywhere}.ddn-viewer-inspector>h3{margin:0 0 6px}.ddn-viewer-inspector details{margin-top:12px}.ddn-viewer-inspector summary{cursor:pointer;font-weight:600}.ddn-viewer-inspector dt{font-weight:600;margin-top:8px}.ddn-viewer-inspector dd{margin:2px 0 8px;font:12px 'JetBrains Mono',ui-monospace,monospace;white-space:pre-wrap;overflow-wrap:anywhere}
.ddn-viewer-status{grid-column:1/-1;padding:8px 12px;border-top:1px solid var(--ddn-ui-border);white-space:pre-wrap;font-size:11px;color:var(--ddn-ui-muted);background:var(--ddn-ui-surface)}.ddn-viewer-status[data-tone=error]{color:var(--ddn-ui-danger)}.ddn-viewer-status[data-tone=warning]{color:#d97706}.ddn-viewer-stage>svg.ddn-space-pan{cursor:grab}.ddn-viewer-stage>svg.ddn-space-pan.ddn-panning{cursor:grabbing}.ddn-viewer-overlays{position:absolute;inset:0;pointer-events:none}.ddn-viewer-overlays>*:not(.ddn-ui-layer):not(.ddn-viewer-hint){pointer-events:auto}
.ddn-viewer[data-controls=host]{grid-template-columns:1fr}.ddn-viewer[data-controls=host] .ddn-viewer-stage{grid-column:1}.ddn-viewer[data-controls=host]>.ddn-viewer-toolbar,.ddn-viewer[data-controls=host]>.ddn-viewer-outline{display:none}
.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left]){grid-template-columns:minmax(0,1fr)}.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])>.ddn-viewer-stage{grid-column:1}.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])[data-ddn-dock-right]{grid-template-columns:minmax(0,1fr) 320px}.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])[data-ddn-dock-right]>.ddn-designer-dock-right{grid-column:2}
@media(max-width:760px){.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])[data-ddn-dock-right]{grid-template-columns:minmax(0,1fr)}.ddn-viewer[data-ddn-navigator]:not([data-ddn-navigator=docked]):not([data-ddn-dock-left])[data-ddn-dock-right]>.ddn-designer-dock-right{grid-column:1}.ddn-viewer{grid-template-columns:minmax(0,1fr);grid-template-rows:auto auto minmax(340px,1fr) auto;overflow:auto}.ddn-viewer-outline{grid-column:1;grid-row:2;max-height:120px;padding:10px;border-right:0;border-bottom:1px solid var(--ddn-ui-border)}.ddn-outline-heading{display:none}.ddn-viewer-stage{grid-column:1;grid-row:3;min-height:340px}.ddn-viewer-status{grid-row:4}.ddn-viewer-toolbar{padding:6px;gap:3px;min-width:0;flex-wrap:nowrap;overflow-x:auto;scrollbar-width:thin}.ddn-viewer-toolbar button{white-space:nowrap;flex:none}.ddn-toolbar-group{padding-right:4px;margin-right:0;flex-wrap:nowrap;flex:none}}
`;
    const toolbar = document.createElement('div');
    toolbar.className = 'ddn-viewer-toolbar';
    toolbar.setAttribute('role', 'toolbar');
    toolbar.setAttribute('aria-label', 'Diagram navigation');
    const outline = document.createElement('nav');
    outline.className = 'ddn-viewer-outline';
    outline.setAttribute('aria-label', 'Semantic outline');
    const search = document.createElement('input');
    search.type = 'search';
    search.placeholder = 'Find a view or element';
    search.setAttribute('aria-label', 'Search diagram');
    const outlineList = document.createElement('div');
    const outlineHeading = document.createElement('div');
    outlineHeading.className = 'ddn-outline-heading';
    outlineHeading.textContent = 'Navigator';
    outlineHeading.style.cssText = 'display:flex;align-items:center;gap:4px;letter-spacing:normal';
    const searchGroup = document.createElement('div');
    searchGroup.className = 'ddn-outline-search';
    searchGroup.append(uiIcon(document, 'search'), search);
    const outlineSections = document.createElement('div');
    outlineSections.className = 'ddn-panel-sections';
    outlineList.className = 'ddn-panel-section';
    let outlineSection = 'all';
    const outlineTabs = sideTabs(outlineSections, 'Navigator sections', [{ id: 'all', label: 'All items', icon: 'layers' }, { id: 'views', label: 'Views', icon: 'grid' }, { id: 'elements', label: 'Elements', icon: 'table' }, { id: 'relations', label: 'Connections', icon: 'link' }], outlineSection, id => { outlineSection = id; outlineTabs.label(outlineList); renderOutline(); });
    outlineTabs.connect(outlineList);
    outlineSections.append(outlineList);
    outline.append(outlineHeading, searchGroup, outlineSections);
    const stage = document.createElement('div');
    stage.className = 'ddn-viewer-stage';
    const svg = svgElement(document, 'svg', { role: 'graphics-document', 'aria-label': 'Diagram workarea', tabindex: 0 });
    stage.append(svg);
    const overlays = document.createElement('div');
    overlays.className = 'ddn-viewer-overlays';
    stage.append(overlays);
    const statusTooltip = installStatusHint(svg, overlays, clipPrefix + '-status-hint');
    cleanups.push(statusTooltip.destroy);
    const inspector = document.createElement('section');
    let inspectionDialog;
    inspector.className = 'ddn-viewer-inspector';
    inspector.setAttribute('aria-label', 'Item inspection');
    const status = document.createElement('div');
    status.className = 'ddn-viewer-status';
    status.setAttribute('role', 'status');
    status.setAttribute('aria-live', 'polite');
    container.dataset.controls = options.controls ?? 'standard';
    container.append(style, toolbar, outline, stage, status);
    element.append(container);
    const navigatorDrawer = createDrawer(outline, { id: 'navigator', title: 'Navigator', container, header: outlineHeading, width: 380, onMode(mode) { container.dataset.ddnNavigator = mode; }, onBlocked() { announce('The browser blocked the new window. The navigator floats here; allow pop-ups to move it to another monitor.'); } });
    cleanups.push(() => navigatorDrawer.destroy());
    const emit = (event) => {
        for (const listener of [...listeners])
            listener(event);
    };
    const ensure = () => {
        if (disposed)
            throw new Error('Viewer is destroyed');
    };
    const on = (target, type, listener, settings) => { target.addEventListener(type, listener, settings); cleanups.push(() => target.removeEventListener(type, listener, settings)); };
    const setStatusText = (message, tone, holdMs = 0) => {
        status.textContent = message;
        if (tone)
            status.dataset.tone = tone;
        else if (/not authorized|denied|failed|error|invalid|cannot/i.test(message))
            status.dataset.tone = 'error';
        else if (/stale|partial|warning|last valid/i.test(message))
            status.dataset.tone = 'warning';
        else
            delete status.dataset.tone;
        if (holdMs > 0)
            announceHoldUntil = Date.now() + holdMs;
    };
    const announce = (message, tone) => {
        setStatusText(message, tone, tone === 'error' || tone === 'warning' ? 2000 : 900);
    };
    function viewBox() { return { x: viewport.bounds.x, y: viewport.bounds.y, width: viewport.bounds.width / viewport.zoom, height: viewport.bounds.height / viewport.zoom }; }
    function screenScale(view = viewport) {
        const rect = svg.getBoundingClientRect();
        return Math.min(rect.width / view.bounds.width, rect.height / view.bounds.height) * view.zoom || 1;
    }
    function toWorld(x, y) {
        const matrix = svg.getScreenCTM();
        if (matrix) {
            const point = svg.createSVGPoint();
            point.x = x;
            point.y = y;
            const local = point.matrixTransform(matrix.inverse());
            return { x: local.x, y: local.y };
        }
        const rect = svg.getBoundingClientRect(), visible = viewBox(), scale = screenScale();
        return { x: visible.x + visible.width / 2 + (x - rect.left - rect.width / 2) / scale, y: visible.y + visible.height / 2 + (y - rect.top - rect.height / 2) / scale };
    }
    function viewFrame(ref) {
        return projection?.entries.find(entry => entry.item.occurrence === `view:${refKey(ref)}`);
    }
    function updatePaper() {
        let paper = workareaBackground;
        if (expandedView && currentSnapshot) {
            const resolved = styledResolve(currentSnapshot, expandedView).values;
            const declared = str(pathValue(resolved, 'background.color'));
            const frame = viewFrame(expandedView);
            const painted = frame?.item.primitives.find(p => 'paint' in p && typeof p.paint.fill === 'string' && !['none', 'transparent'].includes(p.paint.fill));
            paper = declared && !['none', 'transparent'].includes(declared) ? declared : painted && 'paint' in painted ? str(painted.paint.fill, '#ffffff') : '#ffffff';
        }
        stage.style.backgroundColor = cssPaint(paper);
    }
    function draw() {
        statusTooltip.hide();
        if (disposed || !projection)
            return;
        const visible = viewBox();
        svg.setAttribute('viewBox', `${visible.x} ${visible.y} ${visible.width} ${visible.height}`);
        svg.querySelector('[data-ddn-background]')?.remove();
        updatePaper();
        if (workareaTexture && !expandedView) {
            const background = svgElement(document, 'g', { 'data-ddn-background': '', 'pointer-events': 'none', 'aria-hidden': 'true' });
            background.append(realize(document, backgroundPrimitive(visible, workareaBackground, workareaTexture), assets, { id: clipPrefix + '-background', bounds: visible }));
            svg.prepend(background);
        }
        const overscan = { x: visible.x - 200, y: visible.y - 200, width: visible.width + 400, height: visible.height + 400 };
        const existing = new Map(Array.from(svg.children).filter(child => child.hasAttribute('data-occurrence')).map(child => [child.getAttribute('data-occurrence'), child]));
        const entryOf = new Map(projection.entries.map(e => [e.item.occurrence, e]));
        const scale = screenScale();
        const expandedKey = expandedView ? refKey(expandedView) : undefined;
        // Hosts may pin the level of detail: "frames" always draws view cards, "full" never does.
        const lod = viewSetting(container, 'lod');
        const mini = !expandedKey && projection.views.length > 0 && lod !== 'full' && (lod === 'frames' || scale < LOD_SCALE);
        drawGrid(visible, scale);
        if (expandedKey)
            svg.setAttribute('data-expanded', expandedKey);
        else
            svg.removeAttribute('data-expanded');
        if (mini)
            svg.setAttribute('data-lod', 'mini');
        else
            svg.removeAttribute('data-lod');
        for (const item of projection.items) {
            if (!intersects(item.bounds, overscan))
                continue;
            let group = existing.get(item.occurrence);
            existing.delete(item.occurrence);
            if (!group) {
                group = svgElement(document, 'g', { 'data-occurrence': item.occurrence, tabindex: 0, role: item.accessible.role });
                svg.append(group);
            }
            const entry = entryOf.get(item.occurrence);
            group.setAttribute('data-ref', JSON.stringify(item.target));
            group.setAttribute('aria-label', item.accessible.label);
            group.setAttribute('data-selected', String(selectedOccurrences.has(item.occurrence) || item.occurrence === selectedOccurrence || !selectedOccurrence && !selectedOccurrences.size && !!selection && refKey(item.target) === refKey(selection)));
            group.setAttribute('data-view-frame', String(item.occurrence === `view:${refKey(item.view)}`));
            group.setAttribute('data-movable', String(!!(entry?.appearance ?? entry?.placement)));
            if (expandedKey)
                group.setAttribute('data-in-expanded', String(!!item.view && refKey(item.view) === expandedKey));
            else
                group.removeAttribute('data-in-expanded');
            group.replaceChildren();
            const title = svgElement(document, 'title');
            title.textContent = item.accessible.label + (item.accessible.description ? ` — ${item.accessible.description}` : '');
            group.append(title);
            appendItem(document, group, item, assets, clipPrefix);
            const record = entry?.definition.record;
            for (const dot of group.querySelectorAll('[data-status-dot]')) {
                dot.setAttribute('tabindex', '0');
                dot.style.cursor = 'help';
            }
            if (record && (record.category === 'relation' || Array.isArray(record.endpoints))) {
                const content = group.querySelector('g[transform]');
                if (content)
                    for (const path of Array.from(content.querySelectorAll('path'))) {
                        if (path.closest('defs'))
                            continue;
                        const hit = svgElement(document, 'path', { d: path.getAttribute('d') ?? '', class: 'ddn-hit', 'aria-hidden': 'true', 'vector-effect': 'non-scaling-stroke' });
                        path.parentElement?.append(hit);
                    }
            }
        }
        for (const child of existing.values())
            child.remove();
        drawMiniCards(mini, scale);
    }
    /** A session-only alignment grid; it is never part of captures or the source. */
    function drawGrid(visible, scale) {
        svg.querySelector('[data-ddn-grid-lines]')?.remove();
        if (viewSetting(container, 'grid') !== 'on')
            return;
        let step = gridStep(currentSnapshot);
        while (step * scale < 8)
            step *= 2;
        // The SVG letterboxes its viewBox; cover the whole stage, not only the viewBox.
        const rect = svg.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0) {
            const topLeft = toWorld(rect.left, rect.top), bottomRight = toWorld(rect.right, rect.bottom);
            visible = { x: topLeft.x, y: topLeft.y, width: bottomRight.x - topLeft.x, height: bottomRight.y - topLeft.y };
        }
        if (standalone && projection) {
            const bounds = projection.bounds;
            const x = Math.max(bounds.x, visible.x), y = Math.max(bounds.y, visible.y);
            visible = { x, y, width: Math.max(0, Math.min(bounds.x + bounds.width, visible.x + visible.width) - x), height: Math.max(0, Math.min(bounds.y + bounds.height, visible.y + visible.height) - y) };
        }
        const round = standalone ? Math.ceil : Math.floor;
        const x0 = round(visible.x / step) * step, y0 = round(visible.y / step) * step;
        let d = '';
        for (let x = x0; x <= visible.x + visible.width; x += step)
            d += `M${x} ${visible.y}V${visible.y + visible.height}`;
        for (let y = y0; y <= visible.y + visible.height; y += step)
            d += `M${visible.x} ${y}H${visible.x + visible.width}`;
        const group = svgElement(document, 'g', { 'data-ddn-grid-lines': '', 'pointer-events': 'none', 'aria-hidden': 'true' });
        group.append(svgElement(document, 'path', { d, fill: 'none', stroke: '#94a3b8', 'stroke-opacity': .35, 'stroke-width': 1, 'vector-effect': 'non-scaling-stroke' }));
        const background = svg.querySelector('[data-ddn-background]');
        if (background)
            background.after(group);
        else
            svg.prepend(group);
    }
    function drawMiniCards(mini, scale) {
        miniCards?.remove();
        miniCards = undefined;
        if (!mini || !projection)
            return;
        miniCards = svgElement(document, 'g', { 'data-ddn-mini': '' });
        const activeKey = viewport.activeView ? refKey(viewport.activeView) : undefined;
        for (const view of projection.views) {
            const frame = viewFrame(view.ref);
            const b = frame?.item.bounds;
            if (!b || !frame)
                continue;
            const count = projection.entries.filter(e => e.definition.owner !== 'view' && refKey(e.view.ref) === refKey(view.ref)).length;
            const card = svgElement(document, 'g', { class: 'ddn-mini-card', role: 'button', tabindex: 0, 'aria-label': `${titleOf(view.record)} — ${count} elements. Enter to expand view`, 'data-ref': JSON.stringify(view.ref), 'data-occurrence-ref': frame.item.occurrence, 'data-active': String(activeKey === refKey(view.ref)) });
            card.append(svgElement(document, 'rect', { x: b.x, y: b.y, width: b.width, height: b.height, rx: Math.min(24, 12 / scale), class: 'ddn-mini-paper' }));
            const size = Math.min(b.height / 10, b.width / 16, Math.max(14, 22 / scale)), glyph = Math.min(b.width / 3, size * 1.6);
            const gx = b.x + b.width / 2 - glyph / 2, gy = b.y + b.height * 0.22;
            const sw = Math.max(1.5, 2.5 / scale);
            card.append(svgElement(document, 'rect', { x: gx, y: gy, width: glyph, height: glyph * .8, rx: glyph * .06, fill: 'none', stroke: '#2563eb', 'stroke-width': sw }));
            card.append(svgElement(document, 'rect', { x: gx, y: gy, width: glyph, height: glyph * .18, rx: glyph * .06, fill: '#2563eb', stroke: 'none' }));
            card.append(svgElement(document, 'rect', { x: gx + glyph * .14, y: gy + glyph * .32, width: glyph * .32, height: glyph * .3, fill: 'none', stroke: '#2563eb', 'stroke-width': sw }));
            card.append(svgElement(document, 'rect', { x: gx + glyph * .54, y: gy + glyph * .32, width: glyph * .32, height: glyph * .3, fill: 'none', stroke: '#2563eb', 'stroke-width': sw }));
            card.append(svgElement(document, 'path', { d: `M${gx + glyph * .46},${gy + glyph * .47}H${gx + glyph * .54}`, fill: 'none', stroke: '#2563eb', 'stroke-width': sw }));
            const label = titleOf(view.record) || view.ref.id;
            const title = svgElement(document, 'text', { x: b.x + b.width / 2, y: gy + glyph * 1.3 + size * 1.2, 'text-anchor': 'middle', 'font-size': size });
            title.textContent = label.length > 28 ? label.slice(0, 27) + '…' : label;
            card.append(title);
            const meta = svgElement(document, 'text', { x: b.x + b.width / 2, y: gy + glyph * 1.3 + size * 2.4, 'text-anchor': 'middle', 'font-size': size * 0.7, class: 'ddn-mini-meta' });
            meta.textContent = `${count} element${count === 1 ? '' : 's'} · double-click to open`;
            card.append(meta);
            card.addEventListener('dblclick', () => { void viewer.navigate({ kind: 'expand-view', target: view.ref }); });
            card.addEventListener('keydown', event => { if (event.key === 'Enter' || event.key === ' ') {
                event.preventDefault();
                event.stopPropagation();
                void viewer.navigate({ kind: 'expand-view', target: view.ref });
            } });
            miniCards.append(card);
        }
        svg.append(miniCards);
    }
    function outlineLabel(entry) {
        const record = entry.definition.record;
        const own = str(record.title);
        if (own)
            return own;
        if (Array.isArray(record.endpoints) && currentSnapshot) {
            const all = records(currentSnapshot);
            const names = record.endpoints.map(end => {
                const target = object(end).target ?? object(end).definition ?? end;
                const found = resolveRecord(all, target, entry.definition.file);
                return found ? titleOf(found.record) : undefined;
            }).filter((name) => !!name);
            if (names.length >= 2)
                return `${names[0]} → ${names.slice(1).join(', ')}`;
        }
        const generic = titleOf(record);
        return /^ddn-[0-9a-f]{12,}$/.test(generic) ? `${str(record.role, 'connection')} (unnamed)` : generic;
    }
    function renderOutline() {
        const q = search.value.toLocaleLowerCase();
        outlineList.replaceChildren();
        const seen = new Set();
        for (const entry of projection?.entries ?? []) {
            const key = refKey(entry.definition.ref);
            if (seen.has(key))
                continue;
            seen.add(key);
            const category = entry.definition.owner === 'view' ? 'views' : entry.definition.record.category === 'relation' ? 'relations' : 'elements';
            if (!q && outlineSection !== 'all' && outlineSection !== category)
                continue;
            const label = outlineLabel(entry);
            if (q && !`${label} ${entry.definition.file}`.toLocaleLowerCase().includes(q))
                continue;
            const button = document.createElement('button');
            button.textContent = label;
            button.title = `${entry.definition.file} :: ${entry.definition.ref.id}`;
            button.dataset.ref = JSON.stringify(entry.definition.ref);
            if (selection && refKey(selection) === key)
                button.setAttribute('aria-current', 'true');
            button.addEventListener('click', () => { select(entry.definition.ref, entry.item.occurrence); void viewer.navigate({ kind: 'focus', target: entry.definition.ref }); });
            outlineList.append(button);
        }
    }
    function openInspection() {
        if (inspectionDialog) {
            inspectionDialog.element.focus();
            return;
        }
        inspectionDialog = createStandardDialog(overlays, { title: 'Item details', modal: false, onClose() { inspectionDialog = undefined; } });
        inspectionDialog.body.append(inspector);
        renderInspection();
    }
    function renderInspection() {
        if (!inspectionDialog)
            return;
        inspector.replaceChildren();
        if (!selection || !currentSnapshot) {
            inspector.textContent = 'Select an item to inspect its full values and inherited settings.';
            return;
        }
        const found = findRecord(currentSnapshot, selection);
        if (!found)
            return;
        const heading = document.createElement('h3');
        heading.textContent = titleOf(found.record);
        inspector.append(heading);
        const id = document.createElement('p');
        id.textContent = `${found.file} :: ${found.ref.id}`;
        const summary = document.createElement('p');
        summary.textContent = [str(found.record.type), str(pathValue(found.record, 'design.state')), str(found.record.profile)].filter(Boolean).join(' · ');
        inspector.append(summary);
        renderAnalysis(found.ref);
        const details = document.createElement('details'), detailsLabel = document.createElement('summary');
        detailsLabel.textContent = 'All properties and inheritance';
        details.append(detailsLabel, id);
        const list = document.createElement('dl');
        const resolved = styledResolve(currentSnapshot, selection);
        for (const property of resolved.properties) {
            const term = document.createElement('dt');
            term.textContent = property.path;
            const value = document.createElement('dd');
            value.textContent = `${typeof property.value === 'string' ? property.value : JSON.stringify(property.value)} (${property.origin})`;
            list.append(term, value);
        }
        if (found.record.data || found.record.draft || found.record.content || found.record.projection) {
            const term = document.createElement('dt');
            term.textContent = 'Complete content';
            const value = document.createElement('dd');
            value.textContent = JSON.stringify({ data: found.record.data, draft: found.record.draft, content: found.record.content, ...(found.record.profile === 'table.records@1' ? { projectedTable: recordTableData(currentSnapshot, found) } : {}) }, null, 2);
            list.append(term, value);
        }
        details.append(list);
        inspector.append(details);
    }
    function renderAnalysis(target) {
        if (!currentSnapshot)
            return;
        const analysis = object(analyzeProfile(currentSnapshot.normalized, target));
        if (analysis.kind === 'none')
            return;
        const section = document.createElement('section');
        section.setAttribute('aria-label', 'Profile analysis');
        const title = document.createElement('h4');
        title.textContent = analysis.kind === 'decision' ? 'Decision analysis' : analysis.kind === 'flat-state' ? 'Declared trace analysis' : 'Critical path';
        const result = document.createElement('pre');
        result.style.cssText = 'white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px';
        result.setAttribute('aria-live', 'polite');
        result.textContent = JSON.stringify(analysis, null, 2);
        section.append(title);
        if (analysis.kind === 'decision' && Array.isArray(analysis.inputs)) {
            const controls = [];
            for (const raw of analysis.inputs) {
                const domain = object(raw), name = str(domain.name);
                const label = document.createElement('label');
                label.style.display = 'block';
                const enabled = document.createElement('input');
                enabled.type = 'checkbox';
                enabled.checked = domain.optional !== true;
                enabled.setAttribute('aria-label', 'Supply ' + name);
                label.append(enabled, ' ' + name + ' ');
                const choices = domain.type === 'boolean' ? [false, true] : Array.isArray(domain.values) ? [...domain.values] : [];
                if (domain.nullable === true)
                    choices.push(null);
                let read;
                if (domain.type !== 'number') {
                    const input = document.createElement('select');
                    input.setAttribute('aria-label', 'Decision input ' + name);
                    for (const [index, value] of choices.entries()) {
                        const option = document.createElement('option');
                        option.value = String(index);
                        option.textContent = value === null ? 'null' : String(value);
                        input.append(option);
                    }
                    label.append(input);
                    read = () => choices[Number(input.value)];
                }
                else {
                    const input = document.createElement('input');
                    input.type = 'number';
                    input.step = 'any';
                    input.setAttribute('aria-label', 'Decision input ' + name);
                    if (typeof domain.min === 'number') {
                        input.min = String(domain.min);
                        input.value = String(domain.min);
                    }
                    if (typeof domain.max === 'number')
                        input.max = String(domain.max);
                    label.append(input);
                    const nullValue = document.createElement('input');
                    nullValue.type = 'checkbox';
                    nullValue.setAttribute('aria-label', 'Null ' + name);
                    if (domain.nullable === true)
                        label.append(nullValue, ' null');
                    read = () => nullValue.checked ? null : input.value !== '' && input.checkValidity() ? Number(input.value) : (() => { throw Error('Enter a number within the declared range for ' + name); })();
                }
                section.append(label);
                controls.push({ name, enabled, read });
            }
            const calculate = document.createElement('button');
            calculate.type = 'button';
            calculate.textContent = 'Match inputs';
            calculate.addEventListener('click', () => {
                try {
                    const values = {};
                    for (const control of controls)
                        if (control.enabled.checked)
                            values[control.name] = control.read();
                    result.textContent = JSON.stringify(analyzeProfile(currentSnapshot.normalized, target, values), null, 2);
                }
                catch (error) {
                    result.textContent = String(error);
                }
            });
            section.append(calculate);
        }
        section.append(result);
        inspector.append(section);
    }
    function select(ref, occurrence, additive = false) {
        if (!ref) {
            clearSelection();
            return;
        }
        if (standalone && !projection?.entries.some(entry => occurrence ? entry.item.occurrence === occurrence && refKey(entry.definition.ref) === refKey(ref) : refKey(entry.definition.ref) === refKey(ref)))
            return;
        if (additive && occurrence) {
            if (selectedOccurrences.has(occurrence) && selectedOccurrences.size > 1) {
                selectedOccurrences.delete(occurrence);
                if (selectedOccurrence === occurrence) {
                    const lastOcc = [...selectedOccurrences].at(-1);
                    const lastEntry = projection?.entries.find(e => e.item.occurrence === lastOcc);
                    selectedOccurrence = lastOcc;
                    selection = lastEntry?.definition.ref ?? ref;
                }
            }
            else {
                if (selectedOccurrence && !selectedOccurrences.size)
                    selectedOccurrences.add(selectedOccurrence);
                selectedOccurrences.add(occurrence);
                selection = ref;
                selectedOccurrence = occurrence;
            }
        }
        else {
            selectedOccurrences.clear();
            if (occurrence)
                selectedOccurrences.add(occurrence);
            selection = ref;
            selectedOccurrence = occurrence;
        }
        for (const group of Array.from(svg.children)) {
            const occ = group.getAttribute('data-occurrence');
            const selected = (occ && selectedOccurrences.has(occ)) || (occurrence ? occ === selectedOccurrence : group.getAttribute('data-ref') === JSON.stringify(selection));
            group.setAttribute('data-selected', String(!!selected));
        }
        for (const button of outlineList.querySelectorAll('button')) {
            if (button.dataset.ref && selection && refKey(JSON.parse(button.dataset.ref)) === refKey(selection))
                button.setAttribute('aria-current', 'true');
            else
                button.removeAttribute('aria-current');
        }
        renderInspection();
        for (const listener of [...selectionListeners])
            listener(selection);
        updateToolbarState();
        renderHint();
        emit({ kind: 'selection', ...(selection ? { target: selection } : {}), ...(currentSnapshot ? { revision: currentSnapshot.revision } : {}) });
    }
    function cameraState() { return { viewport, expandedView, restored }; }
    function rememberCamera(state) {
        history.splice(historyIndex + 1);
        history.push(state);
        historyIndex = history.length - 1;
    }
    function setCamera(next, remember = true, mode) {
        if (!Number.isFinite(next.zoom) || next.zoom <= 0 || Object.values(next.bounds).some(v => !Number.isFinite(v)) || next.bounds.width <= 0 || next.bounds.height <= 0)
            throw new Error('Invalid viewport');
        if (remember)
            rememberCamera(cameraState());
        if (mode) {
            expandedView = mode.expandedView;
            restored = mode.restored;
        }
        viewport = { ...next, bounds: { ...next.bounds }, zoom: Math.min(32, Math.max(.05, next.zoom)) };
        if (standalone && projection) {
            expandedView = projection.views[0]?.ref;
            restored = undefined;
            viewport = constrainStandaloneViewport(viewport, projection.bounds, expandedView);
        }
        draw();
        updateToolbarState();
        renderHint();
        emit({ kind: 'viewport', ...(viewport.activeView ? { target: viewport.activeView } : {}) });
    }
    function zoomAt(factor, clientX, clientY, remember = false) {
        const before = viewBox(), anchor = toWorld(clientX, clientY);
        const zoom = Math.min(32, Math.max(.05, viewport.zoom * factor));
        const ratio = viewport.zoom / zoom;
        const x = anchor.x - (anchor.x - before.x) * ratio, y = anchor.y - (anchor.y - before.y) * ratio;
        setCamera({ ...viewport, zoom, bounds: { x, y, width: viewport.bounds.width, height: viewport.bounds.height } }, remember);
    }
    function clearSelection() {
        if (!selection && !selectedOccurrence && !selectedOccurrences.size)
            return;
        selection = undefined;
        selectedOccurrence = undefined;
        selectedOccurrences.clear();
        for (const group of Array.from(svg.children))
            if (group.hasAttribute('data-selected'))
                group.setAttribute('data-selected', 'false');
        for (const button of outlineList.querySelectorAll('button'))
            button.removeAttribute('aria-current');
        renderInspection();
        for (const listener of [...selectionListeners])
            listener(undefined);
        emit({ kind: 'selection', ...(currentSnapshot ? { revision: currentSnapshot.revision } : {}) });
        updateToolbarState();
    }
    function fit(bounds, target, mode) { const pad = standalone ? 0 : 24; setCamera({ bounds: { x: bounds.x - pad, y: bounds.y - pad, width: bounds.width + pad * 2, height: bounds.height + pad * 2 }, zoom: 1, ...(target ? { activeView: target } : {}) }, true, mode); }
    const cssCache = new Map();
    function styledResolve(snapshot, target, context = {}) {
        const files = Array.isArray(object(snapshot.normalized).files) ? object(snapshot.normalized).files : [];
        const rootDocument = object(files.map(object).find(f => f.location === snapshot.rootFile)?.document);
        const ownDocument = object(files.map(object).find(f => f.location === target.file)?.document);
        const view = context.view ? findRecord(snapshot, context.view)?.record : findRecord(snapshot, target)?.owner === 'view' ? findRecord(snapshot, target)?.record : undefined;
        const sheets = [];
        for (const [owner, file] of [[rootDocument, snapshot.rootFile], [ownDocument, target.file], [view, context.view?.file ?? target.file]]) {
            const listed = pathValue(owner, 'style.sheets');
            if (Array.isArray(listed))
                for (const sheet of listed)
                    sheets.push([sheet, file]);
        }
        const seen = new Set();
        const rules = [];
        const problems = [];
        for (const [reference, file] of sheets) {
            const record = typeof reference === 'object' ? records(snapshot).find(r => r.owner === 'asset' && (r.ref.id === object(reference).id || r.record.name === object(reference).name) && r.file === str(object(reference).file, file)) : undefined;
            const name = typeof reference === 'string' ? reference : str(record?.record.path, str(object(reference).name, str(object(reference).id)));
            const parts = record ? [] : file.split('/').slice(0, -1);
            for (const part of name.split('/')) {
                if (part === '..')
                    parts.pop();
                else if (part && part !== '.')
                    parts.push(part);
            }
            const location = parts.join('/');
            if (seen.has(location))
                continue;
            seen.add(location);
            const source = runtime.sources()?.files.find(f => f.id === location);
            if (!source) {
                problems.push({ code: 'style-unavailable', severity: 'warning', message: `Selected stylesheet ${location} is unavailable.`, target });
                continue;
            }
            const key = source.id + '@' + source.revision;
            let parsed = cssCache.get(key);
            if (!parsed) {
                parsed = parseStylesheet(source.text);
                cssCache.set(key, parsed);
                if (cssCache.size > 128)
                    cssCache.delete(cssCache.keys().next().value);
            }
            rules.push(...parsed.rules);
            problems.push(...parsed.diagnostics);
        }
        const result = resolveProperties(snapshot, target, { ...context, styles: rules });
        return { ...result, diagnostics: [...problems, ...result.diagnostics] };
    }
    const canvas = document.createElement('canvas');
    const measure = (value, size, font) => {
        const context = canvas.getContext('2d');
        if (!context)
            return value.length * size * .58;
        context.font = `${size}px ${fontFamily(font)}`;
        return context.measureText(value).width;
    };
    async function loadAssets(scene) {
        let sizesChanged = false;
        const ids = [...new Set(scene.items.flatMap(item => item.primitives.filter((p) => p.kind === 'image').map(p => p.assetId)))];
        for (const id of ids) {
            if (assets.has(id) || assetFailures.has(id))
                continue;
            if (!options.assets) {
                assetFailures.add(id);
                diagnostics.push({ code: 'asset-unavailable', severity: 'warning', message: `Asset ${id} needs an explicit local asset provider.` });
                continue;
            }
            try {
                const result = await options.assets.read(id);
                if (result.bytes.byteLength > 16 * 1024 * 1024)
                    throw new Error('Asset exceeds the local image budget');
                let bytes = new Uint8Array(result.bytes).buffer;
                let mime = result.mime;
                let intrinsicSize;
                if (mime === 'image/svg+xml') {
                    const parser = new win.DOMParser();
                    const svgDocument = parser.parseFromString(new TextDecoder().decode(bytes), 'image/svg+xml');
                    if (svgDocument.querySelector('parsererror') || svgDocument.documentElement.localName !== 'svg')
                        throw new Error('Invalid SVG asset');
                    sanitizeSvgAsset(svgDocument, document);
                    const root = svgDocument.documentElement, dimension = (name) => {
                        const raw = root.getAttribute(name)?.trim() ?? '';
                        return /^(?:\d+(?:\.\d*)?|\.\d+)(?:px)?$/.test(raw) ? Number.parseFloat(raw) : NaN;
                    };
                    const width = dimension('width'), height = dimension('height'), viewBox = (root.getAttribute('viewBox') ?? '').trim().split(/[\s,]+/).map(Number);
                    if (width > 0 && height > 0 && Number.isFinite(width) && Number.isFinite(height))
                        intrinsicSize = { width, height };
                    else if (viewBox.length === 4 && viewBox.every(Number.isFinite) && viewBox[2] > 0 && viewBox[3] > 0)
                        intrinsicSize = { width: viewBox[2], height: viewBox[3] };
                    bytes = new TextEncoder().encode(new win.XMLSerializer().serializeToString(svgDocument.documentElement)).buffer;
                }
                else if (!['image/png', 'image/jpeg', 'image/webp', 'image/gif'].includes(mime))
                    throw new Error('Unsupported image media type');
                const blob = new Blob([bytes], { type: mime });
                const dataURL = await new Promise((resolve, reject) => { const reader = new win.FileReader(); reader.onload = () => resolve(String(reader.result)); reader.onerror = () => reject(new Error('Asset encoding failed')); reader.readAsDataURL(blob); });
                if (!intrinsicSize) {
                    const image = new win.Image();
                    image.src = dataURL;
                    await image.decode();
                    if (image.naturalWidth > 0 && image.naturalHeight > 0)
                        intrinsicSize = { width: image.naturalWidth, height: image.naturalHeight };
                }
                assets.set(id, { dataURL, hash: result.hash, ...(intrinsicSize ? { intrinsicSize } : {}) });
                sizesChanged ||= !!intrinsicSize;
            }
            catch (error) {
                assetFailures.add(id);
                diagnostics.push({ code: 'asset-unavailable', severity: 'warning', message: `Asset ${id}: ${String(error)}` });
            }
        }
        for (const id of assets.keys())
            if (!ids.includes(id))
                assets.delete(id);
        return sizesChanged;
    }
    async function loadGeography(snapshot) {
        const problems = [], all = records(snapshot);
        const requested = all.filter(r => r.owner === 'view' && str(r.record.profile).startsWith('geo.')).map(r => ({ view: r, name: str(pathValue(r.record, 'projection.options.geography')) }));
        for (const { view, name } of requested) {
            const separator = name.indexOf('::');
            const file = separator >= 0 ? name.slice(0, separator) : view.file;
            const localName = separator >= 0 ? name.slice(separator + 2) : name;
            const asset = all.find(r => r.owner === 'asset' && (refKey(r.ref) === name || r.file === file && [r.ref.id, r.record.name, r.record.path].includes(localName)));
            if (!asset || asset.record.bytes !== undefined || !options.assets)
                continue;
            const key = refKey(asset.ref), version = JSON.stringify(asset.record);
            if (geographyVersions.get(key) === version)
                continue;
            try {
                const result = await options.assets.read(key);
                if (result.bytes.byteLength > 16 * 1024 * 1024)
                    throw Error('Geography exceeds the local 16 MiB asset budget');
                if (!['application/json', 'application/geo+json', 'application/geojson', 'application/octet-stream', 'text/plain'].includes(result.mime))
                    throw Error('Geography asset must contain JSON');
                const value = JSON.parse(new TextDecoder('utf-8', { fatal: true }).decode(result.bytes));
                geography.set(key, value);
                for (const alias of [asset.ref.id, str(asset.record.name), str(asset.record.path)])
                    if (alias)
                        geography.set(asset.file + '::' + alias, value);
                geographyVersions.set(key, version);
                geographyHashes.set(key, result.hash);
                assetFailures.delete(key);
            }
            catch (error) {
                assetFailures.add(key);
                problems.push({ code: 'geography-unavailable', severity: 'warning', message: error instanceof Error ? error.message : 'Geography could not be loaded', target: view.ref });
            }
        }
        return problems;
    }
    async function refresh() {
        const ticket = ++generation;
        await fontsReady;
        const snapshot = runtime.snapshot();
        if (!snapshot || disposed)
            return;
        emit({ kind: 'pending', revision: snapshot.revision });
        const report = await runtime.verifier.verifyModel(snapshot, { scope: { kind: 'workarea' }, purpose: 'display', level: 'structural' });
        if (disposed || ticket !== generation)
            return;
        const all = records(snapshot);
        const workarea = all.find(r => r.owner === 'workarea' && r.file === snapshot.rootFile);
        const nextStandalone = workarea?.record.mode === 'standalone';
        const onlyView = nextStandalone ? all.find(r => r.owner === 'view')?.ref : undefined;
        if (workarea) {
            const resolved = styledResolve(snapshot, workarea.ref).values;
            workareaBackground = str(pathValue(resolved, 'background.color'), '#f2f4f7');
            workareaTexture = pathValue(resolved, 'background.texture');
            stage.style.backgroundColor = cssPaint(workareaBackground);
        }
        else {
            workareaBackground = '#f2f4f7';
            workareaTexture = undefined;
        }
        diagnostics = [...runtimeDiagnostics, ...report.diagnostics];
        diagnostics.push(...await loadGeography(snapshot));
        if (disposed || ticket !== generation)
            return;
        const project = () => projectSnapshot(snapshot, { ...(onlyView ? { onlyView } : {}), resolve: (target, context) => styledResolve(snapshot, target, context), measure, geography, assetSizes: assetSizes(), ...(preview ? { preview } : {}), supports: profile => availableProjectionProfiles.has(profile) && !!registrations(runtime.registry).profiles?.some(p => p.id === profile) });
        let nextProjection = project();
        const sizesChanged = await loadAssets(nextProjection);
        if (disposed || ticket !== generation)
            return;
        if (sizesChanged)
            nextProjection = project();
        diagnostics.push(...nextProjection.diagnostics);
        const modeChanged = standalone !== nextStandalone;
        const wasFitted = projection && sameBounds(viewBox(), projection.bounds);
        const viewChanged = nextStandalone && refKey(projection?.views[0]?.ref ?? { file: '', id: '' }) !== refKey(nextProjection.views[0]?.ref ?? { file: '', id: '' });
        currentSnapshot = snapshot;
        projection = nextProjection;
        standalone = nextStandalone;
        container.dataset.ddnDocumentMode = standalone ? 'standalone' : 'workarea';
        svg.setAttribute('aria-label', standalone ? 'Standalone diagram view' : 'Diagram workarea');
        if (modeChanged || viewChanged) {
            history.length = 0;
            historyIndex = -1;
            restored = undefined;
            expandedView = undefined;
        }
        if (standalone) {
            expandedView = projection.views[0]?.ref;
            restored = undefined;
            if (modeChanged || viewChanged || wasFitted)
                viewport = { bounds: { ...projection.bounds }, zoom: 1 };
            viewport = constrainStandaloneViewport(viewport, projection.bounds, expandedView);
            if (selection && !projection.entries.some(entry => refKey(entry.definition.ref) === refKey(selection)))
                clearSelection();
        }
        if (expandedView && !projection.views.some(v => refKey(v.ref) === refKey(expandedView)))
            expandedView = undefined;
        draw();
        renderOutline();
        renderInspection();
        renderHint();
        updateToolbarState();
        const messages = [stale ? 'Showing the last valid version; the source has an error.' : '', !projection.coverage.complete ? 'Partial display: ' + projection.coverage.unavailable.join(', ') : '', ...diagnostics.filter(d => d.severity !== 'info').slice(0, 5).map(d => d.message)].filter(Boolean);
        const elements = projection.entries.length - projection.views.length;
        if (messages.length || Date.now() >= announceHoldUntil || !status.textContent)
            setStatusText(messages.join('\n') || `${projection.views.length} view${projection.views.length === 1 ? '' : 's'} · ${elements} element${elements === 1 ? '' : 's'}`);
        emit({ kind: 'diagnostics', revision: snapshot.revision, diagnostics });
        emit({ kind: 'ready', revision: snapshot.revision });
    }
    let renderKey = '', queued = false, openGeneration = 0;
    const schedule = () => {
        const key = JSON.stringify([runtime.snapshot()?.revision, styleGeneration, fontGeneration, runtime.registry.describe(), runtimeDiagnostics]);
        if (key === renderKey)
            return;
        renderKey = key;
        if (queued)
            return;
        queued = true;
        rendering = Promise.resolve().then(async () => { queued = false; await refresh(); }).catch(error => { diagnostics.push({ code: 'render-failed', severity: 'error', message: String(error) }); announce(`Display failed: ${String(error)}`); emit({ kind: 'diagnostics', diagnostics }); });
    };
    const unsubscribe = runtime.subscribe(event => {
        if (event.kind === 'disposed') {
            announce('Runtime closed.');
            return;
        }
        if (event.kind === 'diagnostics') {
            runtimeDiagnostics = [...(event.diagnostics ?? [])];
            diagnostics = [...runtimeDiagnostics];
            stale = !event.revision && diagnostics.some(d => d.severity === 'error');
        }
        if (event.kind === 'revision' || event.kind === 'diagnostics' || event.kind === 'capabilities')
            schedule();
    });
    cleanups.push(unsubscribe);
    const toolbarGroup = (name) => { const group = document.createElement('div'); group.className = 'ddn-toolbar-group'; group.setAttribute('role', 'group'); group.setAttribute('aria-label', name); toolbar.append(group); return group; };
    const navGroups = { details: toolbarGroup('Details'), fit: toolbarGroup('Fit and expand'), history: toolbarGroup('Position history'), zoom: toolbarGroup('Zoom') };
    const button = (label, action, group, title) => {
        const item = document.createElement('button');
        item.textContent = label;
        const icon = { 'Item details': 'info', 'Fit all': 'fit', 'Fit view': 'fit', 'Expand view': 'expand', 'Shrink to workarea': 'layers', 'Back': 'arrow-left', 'Forward': 'arrow-right' }[label];
        if (icon)
            item.prepend(uiIcon(document, icon));
        item.type = 'button';
        if (title)
            item.title = title;
        item.addEventListener('click', action);
        (group ?? toolbar).append(item);
        return item;
    };
    const currentViewRef = () => selection ? projection?.entries.find(e => refKey(e.definition.ref) === refKey(selection))?.view.ref ?? viewport.activeView ?? projection?.views[0]?.ref : viewport.activeView ?? projection?.views[0]?.ref;
    const detailsButton = button('Item details', openInspection, navGroups.details, 'Show every property of the selected element, with where each value comes from');
    const fitAllButton = button('Fit all', () => void viewer.navigate({ kind: 'fit-workarea' }), navGroups.fit, 'Show the whole workarea — every view (0)');
    const fitViewButton = button('Fit view', () => {
        const ref = currentViewRef();
        if (ref)
            void viewer.navigate({ kind: 'fit-view', target: ref });
    }, navGroups.fit, 'Frame the current view inside the workarea');
    const expandButton = button('Expand view', () => {
        if (expandedView) {
            void viewer.navigate({ kind: 'restore' });
            return;
        }
        const ref = currentViewRef();
        if (ref)
            void viewer.navigate({ kind: 'expand-view', target: ref });
    }, navGroups.fit, 'Fill the viewing area with the current view and hide the workarea; press again to shrink back');
    const backButton = button('Back', () => void viewer.navigate({ kind: 'back' }), navGroups.history, 'Previous position and zoom');
    const forwardButton = button('Forward', () => void viewer.navigate({ kind: 'forward' }), navGroups.history, 'Next position and zoom');
    button('−', () => { const rect = svg.getBoundingClientRect(); zoomAt(1 / 1.2, rect.left + rect.width / 2, rect.top + rect.height / 2, true); }, navGroups.zoom, 'Zoom out (−). Mouse wheel zooms at the pointer; pinch on touch');
    const zoomReadout = document.createElement('button');
    zoomReadout.type = 'button';
    zoomReadout.className = 'ddn-zoom-readout';
    zoomReadout.title = 'Current zoom — click to fit all';
    zoomReadout.textContent = '100%';
    zoomReadout.addEventListener('click', () => void viewer.navigate({ kind: 'fit-workarea' }));
    navGroups.zoom.append(zoomReadout);
    button('+', () => { const rect = svg.getBoundingClientRect(); zoomAt(1.2, rect.left + rect.width / 2, rect.top + rect.height / 2, true); }, navGroups.zoom, 'Zoom in (+)');
    function updateToolbarState() {
        const views = projection?.views.length ?? 0;
        const percent = Math.round(screenScale() * 100);
        zoomReadout.textContent = percent + '%';
        fitAllButton.hidden = standalone;
        expandButton.hidden = standalone;
        fitAllButton.disabled = !projection || standalone;
        zoomReadout.title = standalone ? 'Current zoom — click to fit view' : 'Current zoom — click to fit all';
        fitAllButton.title = views ? `Show the whole workarea — ${views} view${views === 1 ? '' : 's'}` : 'Show the whole workarea';
        fitViewButton.disabled = !views || !!expandedView && !standalone;
        fitViewButton.title = standalone ? 'Frame the standalone view' : 'Frame the current view inside the workarea';
        expandButton.disabled = !views || standalone;
        expandButton.replaceChildren(uiIcon(document, expandedView ? 'layers' : 'expand'), document.createTextNode(expandedView ? 'Shrink to workarea' : 'Expand view'));
        expandButton.setAttribute('aria-pressed', String(!!expandedView));
        backButton.disabled = historyIndex < 0;
        forwardButton.disabled = !history[historyIndex + 2];
        detailsButton.disabled = !projection;
        notifyUICommands(container);
    }
    function toScreen(x, y) {
        const matrix = svg.getScreenCTM(), rect = svg.getBoundingClientRect();
        if (!matrix)
            return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        const point = svg.createSVGPoint();
        point.x = x;
        point.y = y;
        const screen = point.matrixTransform(matrix);
        return { x: screen.x, y: screen.y };
    }
    /** Keyboard and menu zoom keep the selection in place when there is one, otherwise the viewport centre. */
    function zoomAnchor() {
        const rect = svg.getBoundingClientRect(), centre = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
        const entry = selection ? projection?.entries.find(e => selectedOccurrence ? e.item.occurrence === selectedOccurrence : refKey(e.definition.ref) === refKey(selection)) : undefined;
        if (!entry)
            return centre;
        const b = entry.item.bounds, point = toScreen(b.x + b.width / 2, b.y + b.height / 2);
        return point.x >= rect.left && point.x <= rect.right && point.y >= rect.top && point.y <= rect.bottom ? point : centre;
    }
    const zoomBy = (factor) => { const anchor = zoomAnchor(); zoomAt(factor, anchor.x, anchor.y, true); };
    const zoomTo = (percent) => { if (Number.isFinite(percent) && percent > 0)
        zoomBy(percent / 100 / screenScale()); };
    const views = () => projection?.views.length ?? 0;
    cleanups.push(registerUICommands(container, [
        { id: 'view.details', label: 'Item details', run: openInspection, enabled: () => !!projection },
        { id: 'view.fit-workarea', label: 'Fit workarea', run: () => void viewer.navigate({ kind: 'fit-workarea' }), enabled: () => !!projection && !standalone },
        { id: 'view.fit-view', label: 'Fit current view', run: () => fitViewButton.click(), enabled: () => !!views() && (!expandedView || standalone) },
        { id: 'view.fit-selection', label: 'Fit selection', hint: 'Select an element first.', run: () => { if (selection)
                void viewer.navigate({ kind: 'focus', target: selection }); }, enabled: () => !!selection && !!projection },
        { id: 'view.expand', label: 'Expand view', run: () => expandButton.click(), enabled: () => !!views() && !standalone, checked: () => !!expandedView },
        { id: 'view.back', label: 'Back', run: () => void viewer.navigate({ kind: 'back' }), enabled: () => historyIndex >= 0 },
        { id: 'view.forward', label: 'Forward', run: () => void viewer.navigate({ kind: 'forward' }), enabled: () => !!history[historyIndex + 2] },
        { id: 'view.zoom-in', label: 'Zoom in', run: () => zoomBy(1.2), enabled: () => !!projection },
        { id: 'view.zoom-out', label: 'Zoom out', run: () => zoomBy(1 / 1.2), enabled: () => !!projection },
        { id: 'view.zoom', label: 'Zoom', run: value => zoomTo(Number(value)), enabled: () => !!projection, value: () => Math.round(screenScale() * 100) + '%' },
        { id: 'view.actual-size', label: 'Actual size', run: () => zoomTo(100), enabled: () => !!projection },
        { id: 'edit.find', label: 'Find…', run: () => { search.focus(); search.select(); }, enabled: () => !!projection },
        { id: 'view.selection', label: 'Selection', run: () => { }, enabled: () => !!selection, value: () => selection ? JSON.stringify(selection) : '' },
        // Hosts call this after changing session display settings (grid, level of detail).
        { id: 'view.redraw', label: 'Redraw', run: () => { draw(); updateToolbarState(); emit({ kind: 'viewport', ...(viewport.activeView ? { target: viewport.activeView } : {}) }); } },
    ]));
    let hintElement;
    const configuredEmptyViews = new Map();
    const viewTypeChosen = (event) => {
        const requested = object(object(event.detail).view);
        const view = projection?.views.find(candidate => candidate.ref.file === requested.file && candidate.ref.id === requested.id);
        if (view)
            configuredEmptyViews.set(refKey(view.ref), str(view.record.profile));
        renderHint();
    };
    container.addEventListener('ddn:view-type-chosen', viewTypeChosen);
    cleanups.push(() => container.removeEventListener('ddn:view-type-chosen', viewTypeChosen));
    function renderHint() {
        hintElement?.remove();
        hintElement = undefined;
        if (!projection || container.dataset.controls === 'host')
            return;
        const editing = container.hasAttribute('data-ddn-editing');
        const views = projection.views.length;
        const activeRef = currentViewRef();
        const active = activeRef ? projection.views.find(view => refKey(view.ref) === refKey(activeRef)) : undefined;
        if (editing && active && configuredEmptyViews.get(refKey(active.ref)) === str(active.record.profile))
            return;
        // Data views and documents render their content through view-owned records.
        if (active && (isDataProfile(str(active.record.profile)) || active.record.profile === 'table.records@1' || active.record.kind === 'document'))
            return;
        const elements = activeRef ? projection.entries.filter(e => e.definition.owner !== 'view' && refKey(e.view.ref) === refKey(activeRef)).length : 0;
        if (views > 0 && (elements > 0 || !expandedView && !viewport.activeView && projection.entries.some(entry => entry.definition.owner !== 'view')))
            return;
        hintElement = document.createElement('div');
        hintElement.className = 'ddn-viewer-hint';
        hintElement.setAttribute('role', 'note');
        const text = document.createElement('p');
        const actions = document.createElement('div');
        actions.className = 'ddn-hint-actions';
        const action = (label, detail, primary = false) => { const b = document.createElement('button'); b.type = 'button'; b.textContent = label; if (primary)
            b.dataset.primary = ''; b.addEventListener('click', () => container.dispatchEvent(new CustomEvent('ddn:action', { detail, bubbles: true }))); actions.append(b); return b; };
        if (editing) {
            const newDocument = !views && !runtime.sources()?.files.some(file => file.text.trim());
            text.textContent = newDocument ? 'Create a workarea or a standalone view.' : 'What kind of diagram or graph do you want this view to display?';
            action(newDocument ? 'New document…' : 'Choose diagram type…', { action: 'choose-view-type' }, true);
        }
        else {
            text.textContent = views ? 'This view has no elements.' : 'This document has no view to show.';
            action('Open a sample…', { action: 'open-sample' });
            action('Open files…', { action: 'open-files' });
        }
        const small = document.createElement('small');
        small.textContent = editing ? views ? 'Choose a diagram method and type to load its defaults and design tools.' : 'Choose how to organize your design, then pick a diagram method and type.' : 'You can also drop a .ddn file here.';
        hintElement.append(text, actions, small);
        overlays.append(hintElement);
    }
    container.addEventListener('ddn:action', event => {
        const detail = object(event.detail);
        if (detail.action === 'open-sample')
            document.dispatchEvent(new CustomEvent('ddn:open-sample'));
        else if (detail.action === 'open-files')
            document.dispatchEvent(new CustomEvent('ddn:open-files'));
    });
    const hintObserver = new MutationObserver(renderHint);
    hintObserver.observe(container, { attributes: true, attributeFilter: ['data-ddn-editing', 'data-controls'] });
    cleanups.push(() => hintObserver.disconnect());
    updateToolbarState();
    on(search, 'input', renderOutline);
    let dragMoved = false;
    const isEditableTarget = (target) => {
        const el = target;
        return !!el?.closest?.('input,textarea,select,[contenteditable="true"],button');
    };
    on(win, 'keydown', event => {
        if ((event.code === 'Space' || event.key === ' ') && !isEditableTarget(event.target)) {
            spaceHeld = true;
            svg.classList.add('ddn-space-pan');
        }
    });
    on(win, 'keyup', event => {
        if (event.code === 'Space' || event.key === ' ') {
            spaceHeld = false;
            svg.classList.remove('ddn-space-pan');
        }
    });
    on(svg, 'click', event => {
        if (dragMoved) {
            dragMoved = false;
            return;
        }
        const group = event.target.closest('[data-ref]');
        if (group) {
            const ref = JSON.parse(group.getAttribute('data-ref') ?? 'null');
            const occ = group.getAttribute('data-occurrence') ?? group.getAttribute('data-occurrence-ref') ?? undefined;
            select(ref, occ, event.shiftKey && group.getAttribute('data-view-frame') !== 'true');
        }
        else if (!event.shiftKey)
            clearSelection();
    });
    let wheelTimer;
    const finishWheel = () => { if (wheelTimer !== undefined)
        win.clearTimeout(wheelTimer); wheelTimer = undefined; updateToolbarState(); };
    cleanups.push(finishWheel);
    on(svg, 'wheel', event => {
        event.preventDefault();
        if (pinch || drag)
            return;
        if (wheelTimer === undefined)
            rememberCamera(cameraState());
        else
            win.clearTimeout(wheelTimer);
        const unit = event.deltaMode === 1 ? 16 : event.deltaMode === 2 ? svg.clientHeight : 1;
        const delta = event.deltaY * unit;
        // In pan mode the wheel scrolls the workarea; Ctrl/Cmd+wheel (and trackpad pinch, which reports Ctrl) zooms.
        if (viewSetting(container, 'wheel') === 'pan' && !event.ctrlKey && !event.metaKey) {
            const scale = screenScale(), dx = (event.shiftKey && !event.deltaX ? event.deltaY : event.deltaX) * unit, dy = event.shiftKey && !event.deltaX ? 0 : delta;
            setCamera({ ...viewport, bounds: { ...viewport.bounds, x: viewport.bounds.x + dx / scale, y: viewport.bounds.y + dy / scale } }, false);
        }
        else
            zoomAt(Math.exp(-delta * (event.ctrlKey ? .01 : .0015)), event.clientX, event.clientY, false);
        wheelTimer = win.setTimeout(finishWheel, 180);
    }, { passive: false });
    const pinchState = () => {
        const [a, b] = [...pointers.values()];
        return a && b ? { dist: Math.hypot(a.x - b.x, a.y - b.y) || 1, midX: (a.x + b.x) / 2, midY: (a.y + b.y) / 2 } : undefined;
    };
    on(svg, 'pointerdown', event => {
        if (event.button !== 1 && event.button !== 0)
            return;
        finishWheel();
        if (!pointers.size) {
            gestureStart = cameraState();
            dragMoved = false;
        }
        pointers.set(event.pointerId, { x: event.clientX, y: event.clientY, startX: event.clientX, startY: event.clientY });
        if (pointers.size === 2) {
            drag = undefined;
            dragMoved = true;
            svg.classList.remove('ddn-panning');
            const state = pinchState();
            if (!state)
                return;
            pinch = { ...state, view: viewport, anchor: toWorld(state.midX, state.midY), scale: screenScale() };
            for (const id of pointers.keys())
                try {
                    if (!svg.hasPointerCapture(id))
                        svg.setPointerCapture(id);
                }
                catch { /* Synthetic pointers have no capture. */ }
            container.dispatchEvent(new CustomEvent('ddn:gesture', { detail: { gesture: 'pinch-start' }, bubbles: true }));
            return;
        }
        if (event.target.closest('.ddn-ports'))
            return;
        const group = event.target.closest('[data-ref]');
        const readingPan = !container.hasAttribute('data-ddn-editing') && (event.pointerType === 'touch' || group?.getAttribute('data-view-frame') === 'true');
        if (pointers.size > 2 || group && !readingPan && event.button !== 1 && !spaceHeld)
            return;
        drag = { id: event.pointerId, x: event.clientX, y: event.clientY, view: viewport };
        if (!group || spaceHeld)
            try {
                svg.setPointerCapture(event.pointerId);
            }
            catch { /* Synthetic pointers have no capture. */ }
        svg.classList.add('ddn-panning');
    });
    on(svg, 'pointermove', event => {
        const tracked = pointers.get(event.pointerId);
        if (tracked) {
            tracked.x = event.clientX;
            tracked.y = event.clientY;
            // A designer drag also produces a click after pointer capture. Keep
            // that click from clearing the selection or selecting another item.
            if (Math.abs(tracked.x - tracked.startX) + Math.abs(tracked.y - tracked.startY) > 3)
                dragMoved = true;
        }
        if (pinch && pointers.size >= 2) {
            const state = pinchState();
            if (!state)
                return;
            const zoom = Math.min(32, Math.max(.05, pinch.view.zoom * state.dist / pinch.dist));
            const ratio = pinch.view.zoom / zoom, scale = pinch.scale / ratio;
            const x = pinch.anchor.x - (pinch.anchor.x - pinch.view.bounds.x) * ratio - (state.midX - pinch.midX) / scale;
            const y = pinch.anchor.y - (pinch.anchor.y - pinch.view.bounds.y) * ratio - (state.midY - pinch.midY) / scale;
            setCamera({ ...pinch.view, zoom, bounds: { ...pinch.view.bounds, x, y } }, false);
            return;
        }
        if (!drag || drag.id !== event.pointerId)
            return;
        if (Math.abs(event.clientX - drag.x) + Math.abs(event.clientY - drag.y) > 3) {
            dragMoved = true;
            try {
                if (!svg.hasPointerCapture(event.pointerId))
                    svg.setPointerCapture(event.pointerId);
            }
            catch { /* Synthetic pointers have no capture. */ }
        }
        const scale = screenScale(drag.view);
        setCamera({ ...drag.view, bounds: { ...drag.view.bounds, x: drag.view.bounds.x - (event.clientX - drag.x) / scale, y: drag.view.bounds.y - (event.clientY - drag.y) / scale } }, false);
    });
    const endDrag = (event) => {
        const ids = event ? [event.pointerId] : [...pointers.keys()];
        for (const id of ids) {
            pointers.delete(id);
            if (svg.hasPointerCapture(id))
                svg.releasePointerCapture(id);
        }
        if (pinch && pointers.size < 2) {
            pinch = undefined;
            container.dispatchEvent(new CustomEvent('ddn:gesture', { detail: { gesture: 'pinch-end' }, bubbles: true }));
        }
        if (drag && (!event || drag.id === event.pointerId)) {
            drag = undefined;
            svg.classList.remove('ddn-panning');
        }
        if (!pinch && !drag && gestureStart) {
            if (dragMoved && gestureStart.viewport !== viewport)
                rememberCamera(gestureStart);
            gestureStart = undefined;
            updateToolbarState();
        }
    };
    on(win, 'pointerup', endDrag);
    on(win, 'pointercancel', endDrag);
    on(svg, 'lostpointercapture', endDrag);
    on(win, 'blur', () => { spaceHeld = false; svg.classList.remove('ddn-space-pan'); endDrag(); });
    on(svg, 'keydown', event => {
        if (event.key === 'Escape') {
            const wasGesture = !!drag || !!pinch;
            endDrag();
            if (!wasGesture && !container.hasAttribute('data-ddn-editing'))
                clearSelection();
            return;
        }
        // Ctrl/Cmd combinations belong to the host (browser zoom, or a shell's zoom commands).
        if (['+', '=', '-', '0'].includes(event.key) && !event.ctrlKey && !event.metaKey && !event.altKey) {
            event.preventDefault();
            if (event.key === '0')
                void viewer.navigate({ kind: 'fit-workarea' });
            else {
                const rect = svg.getBoundingClientRect();
                zoomAt(event.key === '-' ? 1 / 1.2 : 1.2, rect.left + rect.width / 2, rect.top + rect.height / 2, true);
            }
        }
        if (event.key === 'Enter') {
            const group = event.target.closest('[data-ref]');
            if (group)
                select(JSON.parse(group.getAttribute('data-ref') ?? 'null'), group.getAttribute('data-occurrence') ?? undefined);
        }
    });
    if (typeof ResizeObserver !== 'undefined') {
        const observer = new ResizeObserver(() => { draw(); updateToolbarState(); });
        observer.observe(stage);
        cleanups.push(() => observer.disconnect());
    }
    const fonts = document.fonts;
    if (fonts) {
        const changed = () => { fontGeneration++; schedule(); };
        fonts.addEventListener('loadingdone', changed);
        cleanups.push(() => fonts.removeEventListener('loadingdone', changed));
    }
    const viewer = {
        async open(input, task) {
            ensure();
            inspectionDialog?.close();
            finishWheel();
            endDrag();
            const openTicket = ++openGeneration;
            emit({ kind: 'pending' });
            announce('Opening diagram…');
            generation++;
            renderKey = '';
            history.length = 0;
            historyIndex = -1;
            assets.clear();
            geography.clear();
            geographyHashes.clear();
            geographyVersions.clear();
            assetFailures.clear();
            cssCache.clear();
            selection = undefined;
            selectedOccurrence = undefined;
            selectedOccurrences.clear();
            announceHoldUntil = 0;
            restored = undefined;
            expandedView = undefined;
            configuredEmptyViews.clear();
            const result = await runtime.open(input, task);
            if (disposed || openTicket !== openGeneration)
                return result;
            for (const listener of [...openListeners])
                listener();
            runtimeDiagnostics = [...result.diagnostics];
            diagnostics = [...runtimeDiagnostics];
            stale = !!result.snapshot && result.coverage !== result.snapshot.coverage && result.diagnostics.some(d => d.severity === 'error');
            schedule();
            await rendering;
            if (projection && !stale)
                fit(projection.bounds);
            return result;
        },
        setViewport(next) { ensure(); setCamera(next); },
        async navigate(request) {
            ensure();
            finishWheel();
            await rendering;
            if (!projection)
                return;
            if (request.kind === 'fit-workarea')
                fit(projection.bounds, undefined, { expandedView: undefined, restored: undefined });
            else if (request.kind === 'restore') {
                if (restored)
                    setCamera(restored, true, { expandedView: undefined, restored: undefined });
                else
                    fit(projection.bounds, undefined, { expandedView: undefined, restored: undefined });
            }
            else if (request.kind === 'back') {
                const next = history[historyIndex];
                if (next) {
                    if (historyIndex === history.length - 1)
                        history.push(cameraState());
                    historyIndex--;
                    setCamera(next.viewport, false, next);
                }
            }
            else if (request.kind === 'forward') {
                const next = history[historyIndex + 2];
                if (next) {
                    historyIndex++;
                    setCamera(next.viewport, false, next);
                }
            }
            else if ('target' in request) {
                const entry = projection.entries.find(e => refKey(request.kind === 'focus' ? e.definition.ref : e.view.ref) === refKey(request.target));
                if (entry) {
                    const bounds = request.kind === 'focus' ? (entry.item.bounds.width > 0 && entry.item.bounds.height > 0 ? entry.item.bounds : viewFrame(entry.view.ref)?.item.bounds ?? projection.bounds) : standalone ? projection.bounds : viewFrame(entry.view.ref)?.item.bounds ?? entry.item.bounds;
                    if (request.kind === 'expand-view' || expandedView) {
                        const mode = { expandedView: entry.view.ref, restored: restored ?? viewport };
                        if (request.kind === 'focus')
                            fit(bounds, entry.view.ref, mode);
                        else
                            setCamera({ bounds: { ...bounds }, zoom: 1, activeView: entry.view.ref }, true, mode);
                    }
                    else
                        fit(bounds, entry.view.ref);
                }
            }
        },
        async inspect(target) {
            ensure();
            await rendering;
            const snapshot = runtime.snapshot();
            if (!snapshot)
                throw new Error('No workarea is open');
            const entry = findRecord(snapshot, target);
            if (!entry)
                throw new Error('Unknown inspection target');
            const resolved = styledResolve(snapshot, target);
            return { target, revision: snapshot.revision, properties: resolved.properties.map(p => { const explicit = pathValue(entry.record, p.path); return { path: p.path, effective: p.value, origin: p.origin, ...(explicit !== undefined ? { explicit: explicit } : {}) }; }), diagnostics: diagnostics.filter(d => !d.target || refKey(d.target) === refKey(target)) };
        },
        setPreview(properties) {
            ensure();
            const errors = validatePreview(properties ?? {});
            if (Array.isArray(errors) && errors.length)
                throw new Error(errors.map(d => d.message).join('; '));
            preview = properties ? { ...properties } : undefined;
            styleGeneration++;
            schedule();
        },
        async capture(request) {
            ensure();
            await rendering;
            if (request.cancel?.aborted)
                return { ok: false, reason: 'cancelled', diagnostics: [] };
            const snapshot = currentSnapshot;
            if (!snapshot || !projection)
                return { ok: false, reason: 'incomplete', diagnostics };
            if (stale && request.stale === 'reject')
                return { ok: false, reason: 'stale', diagnostics };
            if ((!projection.coverage.complete || assetFailures.size > 0) && request.partial === 'reject')
                return { ok: false, reason: 'incomplete', diagnostics };
            const scene = request.includePreview ? projection : projectSnapshot(snapshot, { ...(standalone && projection.views[0] ? { onlyView: projection.views[0].ref } : {}), resolve: (target, context) => styledResolve(snapshot, target, context), measure, geography, assetSizes: assetSizes(), supports: profile => availableProjectionProfiles.has(profile) && !!registrations(runtime.registry).profiles?.some(p => p.id === profile) });
            let items = [...scene.items];
            if (request.scope.kind !== 'workarea') {
                const scope = request.scope;
                items = items.filter(item => scope.kind === 'item' ? refKey(item.target) === refKey(scope.target) : refKey(item.view) === refKey(scope.target));
            }
            if (!items.length)
                return { ok: false, reason: 'incomplete', diagnostics: [{ code: 'capture-empty', severity: 'error', message: 'Requested capture scope is unavailable.' }] };
            if (items.every(item => item.bounds.width <= 0 || item.bounds.height <= 0))
                return { ok: false, reason: 'incomplete', diagnostics: [{ code: 'capture-empty', severity: 'error', message: 'Requested capture scope is clipped outside its fixed view surface.' }] };
            let bounds = typeof request.extent === 'object' ? request.extent : request.extent === 'viewport' ? viewBox() : unionBounds(items.map(i => i.bounds));
            if (standalone && typeof request.extent === 'object') {
                const extent = scene.bounds, x = Math.max(bounds.x, extent.x), y = Math.max(bounds.y, extent.y);
                bounds = { x, y, width: Math.min(bounds.x + bounds.width, extent.x + extent.width) - x, height: Math.min(bounds.y + bounds.height, extent.y + extent.height) - y };
                if (bounds.width <= 0 || bounds.height <= 0)
                    return { ok: false, reason: 'incomplete', diagnostics: [{ code: 'capture-empty', severity: 'error', message: 'Requested capture extent is outside the standalone view.' }] };
            }
            const warnings = [...diagnostics];
            if (request.scope.kind === 'view' || request.scope.kind === 'document') {
                const target = findRecord(snapshot, request.scope.target), publication = target ? resolveRecord(records(snapshot), target.record.publication, target.file) : undefined;
                if (publication && request.extent === 'content' && ['svg', 'png'].includes(request.format)) {
                    const resolvedPublication = styledResolve(snapshot, publication.ref);
                    const workareaRecord = records(snapshot).find(r => r.owner === 'workarea' && r.file === snapshot.rootFile);
                    const resolvedWorkarea = workareaRecord ? styledResolve(snapshot, workareaRecord.ref) : undefined;
                    const workareaOrigins = Object.fromEntries((resolvedWorkarea?.properties ?? []).map(p => [p.path, p.origin]));
                    const pubValues = resolvedWorkarea ? inheritedPresentation(resolvedPublication.values, resolvedPublication.properties, resolvedWorkarea.values, workareaOrigins, undefined, 'view') : resolvedPublication.values;
                    const published = publicationScene(items, bounds, { ...publication, record: pubValues }, titleOf(target.record), new Date().toISOString().slice(0, 10));
                    if (published.diagnostics.some(d => d.severity === 'error'))
                        return { ok: false, reason: 'invalid', diagnostics: published.diagnostics };
                    items = published.items;
                    bounds = published.bounds;
                    warnings.push(...published.diagnostics);
                }
            }
            if (stale)
                warnings.push({ code: 'capture-stale', severity: 'warning', message: 'Capture contains a prior valid revision.' });
            const manifest = { revision: snapshot.revision, versions: snapshot.versions, coverage: assetFailures.size ? { ...scene.coverage, complete: false, unavailable: [...scene.coverage.unavailable, ...[...assetFailures].map(id => 'asset:' + id)] } : scene.coverage, styleGeneration: String(styleGeneration), fontGeneration: String(fontGeneration), assets: Object.fromEntries([...geographyHashes, ...[...assets].map(([id, asset]) => [id, asset.hash])]), previewIncluded: request.includePreview, warnings };
            const adapter = options.outputs?.find(a => a.formats.includes(request.format));
            if (adapter)
                return adapter.capture({ snapshot, scene: items, manifest }, request);
            const output = (name, mime, content) => ({ ok: true, artifacts: [{ name, mime, blob: new Blob([content], { type: mime }) }], manifest });
            const viewBackground = standalone && scene.views[0] ? styledResolve(snapshot, scene.views[0].ref).values : undefined;
            const captureBackground = viewBackground ? str(pathValue(viewBackground, 'background.color'), 'transparent') : workareaBackground;
            const captureTexture = standalone ? undefined : workareaTexture;
            if (request.format === 'svg')
                return output('diagram.svg', 'image/svg+xml', serializeScene(document, items, bounds, assets, captureBackground, captureTexture));
            if (request.format === 'json')
                return output('diagram.json', 'application/json', JSON.stringify(snapshot.normalized, null, 2));
            const targets = new Map(items.map(item => [refKey(item.target), findRecord(snapshot, item.target)]));
            if (request.format === 'markdown' || request.format === 'md') {
                const chunks = [];
                for (const record of targets.values()) {
                    if (!record)
                        continue;
                    chunks.push(`## ${titleOf(record.record)}`);
                    const data = displayTableData(snapshot, record);
                    if (data.rows.length) {
                        const clean = (v) => String(v ?? '').replaceAll('|', '\\|').replace(/\r?\n/g, ' ');
                        chunks.push('| ' + data.columns.map(c => clean(c.label ?? c.id)).join(' | ') + ' |', '| ' + data.columns.map(() => '---').join(' | ') + ' |', ...data.rows.map(row => '| ' + row.map(clean).join(' | ') + ' |'));
                    }
                    const note = str(pathValue(record.record, 'draft.text')) || str(pathValue(record.record, 'content.text'));
                    if (note)
                        chunks.push(note);
                    chunks.push('');
                }
                return output('diagram.md', 'text/markdown', chunks.join('\n'));
            }
            if (request.format === 'csv') {
                const candidates = [...targets.values()].filter((r) => !!r && (r.owner === 'definition' || r.record.profile === 'table.records@1') && displayTableData(snapshot, r).rows.length > 0);
                if (candidates.length !== 1)
                    return { ok: false, reason: 'unsupported', diagnostics: [{ code: 'csv-scope', severity: 'error', message: 'CSV capture requires one selected table.' }] };
                const data = displayTableData(snapshot, candidates[0]);
                const cell = (v) => '"' + String(v ?? '').replaceAll('"', '""') + '"';
                return output('table.csv', 'text/csv', [data.columns.map(c => c.label ?? c.id), ...data.rows].map(row => row.map(cell).join(',')).join('\r\n'));
            }
            if (request.format === 'png') {
                if (bounds.width > 16384 || bounds.height > 16384 || bounds.width * bounds.height > 64000000)
                    return { ok: false, reason: 'budget-exceeded', diagnostics: [] };
                const url = URL.createObjectURL(new Blob([serializeScene(document, items, bounds, assets, captureBackground, captureTexture)], { type: 'image/svg+xml' }));
                try {
                    const image = new win.Image();
                    image.src = url;
                    await image.decode();
                    const outputCanvas = document.createElement('canvas');
                    outputCanvas.width = Math.ceil(bounds.width);
                    outputCanvas.height = Math.ceil(bounds.height);
                    const context = outputCanvas.getContext('2d');
                    if (!context)
                        throw new Error('Canvas unavailable');
                    context.drawImage(image, 0, 0);
                    const blob = await new Promise((resolve, reject) => outputCanvas.toBlob(value => value ? resolve(value) : reject(new Error('PNG encoding failed')), 'image/png'));
                    return { ok: true, artifacts: [{ name: 'diagram.png', mime: 'image/png', blob }], manifest };
                }
                catch (error) {
                    return { ok: false, reason: 'invalid', diagnostics: [{ code: 'capture-failed', severity: 'error', message: String(error) }] };
                }
                finally {
                    URL.revokeObjectURL(url);
                }
            }
            return { ok: false, reason: 'unsupported', diagnostics: [{ code: 'output-unavailable', severity: 'error', message: `Output adapter ${request.format} is not installed.` }] };
        },
        subscribe(listener) { ensure(); listeners.add(listener); return () => listeners.delete(listener); },
        destroy() {
            inspectionDialog?.close();
            if (disposed)
                return;
            disposed = true;
            generation++;
            endDrag();
            for (const cleanup of cleanups)
                cleanup();
            container.remove();
            emit({ kind: 'disposed' });
            listeners.clear();
            selectionListeners.clear();
            openListeners.clear();
            assets.clear();
            geography.clear();
            geographyHashes.clear();
            geographyVersions.clear();
            assetFailures.clear();
            cssCache.clear();
            handles.delete(viewer);
            if (ownsRuntime)
                runtime.destroy();
        },
    };
    handles.set(viewer, { runtime, element, surface: svg, container, overlays, ownerDocument: document, selectedOccurrences, scene: () => projection, viewport: () => viewport, selected: () => selection, clearSelection, expanded: () => expandedView, stage, subscribeOpen(listener) { openListeners.add(listener); return () => openListeners.delete(listener); }, selectedEntry: () => projection?.entries.find(e => selectedOccurrence ? e.item.occurrence === selectedOccurrence : !!selection && refKey(e.definition.ref) === refKey(selection)), select, subscribeSelection(listener) { selectionListeners.add(listener); return () => selectionListeners.delete(listener); }, refresh: async () => { schedule(); await rendering; }, whenRendered: () => rendering, diagnostics: () => diagnostics, toWorld, announce });
    if (runtime.snapshot())
        schedule();
    return viewer;
}
//# sourceMappingURL=core.js.map