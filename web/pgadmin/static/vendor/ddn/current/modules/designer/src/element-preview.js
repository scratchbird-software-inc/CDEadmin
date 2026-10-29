import { roleDescriptor } from '../../profiles/src/core.js';
import { nodeGlyph } from '../../presentation/src/graph-glyphs.js';
import { graphNodeDimensions } from '../../presentation/src/node-dimensions.js';
import { nativeContour, nativeIcon } from '../../presentation/src/native-render.js';
import { str } from '../../presentation/src/model.js';
import { renderPreviewPrimitives } from '../../viewer/src/core.js';
/** Draw the profile's actual symbol, omitting a user title and editing chrome. */
export function elementPreview(document, role, profile) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.dataset.role = role;
    svg.dataset.profile = profile;
    const render = roleDescriptor(role)?.render ?? {}, fill = str(render.fill, '#f8fafc'), stroke = str(render.colour, '#475569');
    const native = ['ddn@1', 'mindmap.basic@1', 'concept.map@1'].includes(profile);
    const centred = ['external_actor', 'uml.actor', 'uml.usecase', 'dfd.process', 'dfd.store'].includes(role) || role.startsWith('flow.') || role.startsWith('state.');
    const textOnly = role === 'ui.label';
    const bounds = textOnly ? { x: 0, y: 0, width: 40, height: 20 } : native ? { x: 0, y: 0, width: 180, height: 100 } : graphNodeDimensions(role, profile, { x: 0, y: 0, width: 180, height: 90 });
    const primitives = native
        ? [...nativeContour(role, {}, bounds, fill, stroke, 1.5, 'classic', 1, 42), ...(centred ? [] : nativeIcon(str(render.glyph, role), { x: 14, y: 16, width: 32, height: 32 }, stroke))]
        : nodeGlyph(role, {}, bounds, { profile, title: textOnly ? 'Text' : '', fill, stroke, width: 1.5 });
    const padding = 10;
    svg.setAttribute('viewBox', `${bounds.x - padding} ${bounds.y - padding} ${bounds.width + padding * 2} ${bounds.height + padding * 2}`);
    const sample = primitives.filter(p => p.kind !== 'text' || p.runs.some(run => run.text.trim())).map(p => textOnly && p.kind === 'text'
        ? { ...p, runs: p.runs.map(run => ({ ...run, style: { ...run.style, fill: 'currentColor' } })) } : p);
    svg.append(renderPreviewPrimitives(document, sample, bounds));
    // Keep contours legible at tile size without distorting a circle or diamond.
    for (const shape of svg.querySelectorAll('path,rect,ellipse')) {
        shape.setAttribute('vector-effect', 'non-scaling-stroke');
        const weight = Number(shape.getAttribute('stroke-width') ?? 1.5);
        if (shape.getAttribute('stroke') !== 'none' && weight > 0)
            shape.setAttribute('stroke-width', String(Math.max(.75, weight * 1.25 / 1.5)));
    }
    return svg;
}
//# sourceMappingURL=element-preview.js.map