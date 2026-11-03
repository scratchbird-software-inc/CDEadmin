/** Small, local schematic previews for the chooser, not rendered user data.
 * Every catalogue profile has an explicit label and representative drawing.
 * This module deliberately does not load a renderer or a catalogue family. */
import { profileLabel } from './view-labels.js';
export { profileLabel } from './view-labels.js';
const profiles = {
    'ddn@1': ['erd'],
    'flow.basic@1': ['flow'],
    'dfd.gane_sarson@1': ['dfd', 1],
    'dfd.yourdon@1': ['dfd'],
    'uml.structure@1': ['class'],
    'uml.structure@2': ['class', 1],
    'uml.deployment@1': ['deployment'],
    'uml.composite@1': ['composite'],
    'uml.usecase@1': ['usecase'],
    'requirements.basic@1': ['requirements'],
    'chen.basic@1': ['chen'],
    'matrix.raci@1': ['matrix', 1],
    'matrix.crud@1': ['matrix', 2],
    'matrix.relations@1': ['matrix', 3],
    'panels.basic@1': ['panels'],
    'canvas.bmc@1': ['canvas', 1],
    'canvas.lean@1': ['canvas', 2],
    'canvas.pest@1': ['quadrant', 1],
    'canvas.pestle@1': ['canvas', 3],
    'canvas.porter5@1': ['forces'],
    'canvas.empathy@1': ['empathy'],
    'canvas.scorecard@1': ['scorecard'],
    'table.records@1': ['table'],
    'chart.basic@1': ['chart'],
    'chart.radar@1': ['radar'],
    'chart.funnel@1': ['funnel'],
    'timeline.basic@1': ['timeline'],
    'fishbone.basic@1': ['fishbone'],
    'matrix.heatmap@1': ['heatmap', 1],
    'chart.quality@1': ['quality'],
    'state.flat@1': ['state'],
    'decision.rules@1': ['table', 1],
    'panels.composed@1': ['panels', 1],
    'uml.usecase@2': ['usecase', 1],
    'uml.usecase@3': ['usecase', 2],
    'chen.binary@2': ['chen', 1],
    'chen.nary@3': ['chen', 2],
    'chebotko.conceptual@1': ['chen', 1],
    'chebotko.logical@1': ['erd', 1],
    'flow.documented@2': ['flow', 1],
    'chart.gauge@1': ['gauge'],
    'chart.candlestick@1': ['candlestick'],
    'chart.treemap@1': ['treemap'],
    'chart.sankey@1': ['sankey'],
    'c4.context@1': ['c4'],
    'c4.container@1': ['c4', 1],
    'c4.component@1': ['c4', 2],
    'org.tree@1': ['tree', 1],
    'wbs.tree@1': ['tree', 2],
    'mindmap.basic@1': ['mindmap'],
    'concept.map@1': ['concept'],
    'epc.basic@1': ['epc'],
    'matrix.bcg@1': ['quadrant', 2],
    'matrix.ansoff@1': ['quadrant', 3],
    'matrix.tows@1': ['quadrant', 4],
    'panels.journey@1': ['journey'],
    'matrix.storymap@1': ['storymap'],
    'erd.crowfoot@1': ['erd', 1],
    'panels.pyramid@1': ['pyramid'],
    'panels.venn@1': ['venn'],
    'uml.sequence@1': ['sequence'],
    'uml.sequence@2': ['sequence', 1],
    'uml.communication@1': ['communication'],
    'uml.communication@2': ['communication', 1],
    'uml.object@1': ['object'],
    'uml.object@2': ['object', 1],
    'state.composite@1': ['state', 1],
    'uml.statemachine@1': ['state', 2],
    'uml.activity@1': ['activity'],
    'uml.activity@2': ['activity', 1],
    'bpmn.basic@1': ['bpmn'],
    'bpmn.process@1': ['bpmn', 1],
    'bpmn.choreography@1': ['bpmn', 2],
    'bpmn.conversation@1': ['bpmn', 3],
    'uml.timing@1': ['timing'],
    'uml.timing@2': ['timing', 1],
    'uml.interaction_overview@1': ['activity', 2],
    'uml.interaction_overview@2': ['activity', 3],
    'uml.profile@1': ['packages', 1],
    'cmmn.basic@1': ['case'],
    'cmmn.complete@1': ['case', 1],
    'sysml.bdd@1': ['blocks'],
    'sysml.ibd@1': ['composite', 1],
    'sysml.parametric@1': ['parametric'],
    'archimate.basic@1': ['architecture'],
    'pert.cpm@1': ['pert'],
    'fault.tree@1': ['fault'],
    'event.tree@1': ['eventtree'],
    'network.basic@1': ['network'],
    'network.rack@1': ['rack'],
    'wireframe.ui@1': ['wireframe'],
    'family.tree@1': ['tree', 3],
    'chart.histogram@1': ['histogram'],
    'chart.density@1': ['density'],
    'chart.qq@1': ['qq'],
    'chart.quantiledot@1': ['quantiledot'],
    'chart.dotplot@1': ['dotplot'],
    'chart.boxplot@1': ['boxplot'],
    'chart.violin@1': ['violin'],
    'chart.beeswarm@1': ['beeswarm'],
    'chart.topk@1': ['ranked'],
    'chart.tidytree@1': ['tidytree'],
    'chart.radialtree@1': ['radialtree'],
    'chart.circlepack@1': ['circlepack'],
    'chart.sunburst@1': ['sunburst'],
    'chart.packedbubble@1': ['bubbles'],
    'chart.heatmap@1': ['heatmap'],
    'chart.densityheatmap@1': ['heatmap', 2],
    'chart.calendar@1': ['calendar'],
    'chart.parallelcoords@1': ['parallel'],
    'chart.wordcloud@1': ['wordcloud'],
    'chart.arc@1': ['arc'],
    'chart.force@1': ['force'],
    'chart.edgebundle@1': ['bundle'],
    'geo.choropleth@1': ['map', 1],
    'geo.symbols@1': ['map', 2],
    'geo.outline@1': ['map'],
    'sysml.requirements@1': ['requirements', 1],
    'sysml.bdd@2': ['blocks', 1],
    'sysml.ibd@2': ['composite', 2],
    'sysml.parametric@2': ['parametric', 1],
    'sysml.package@1': ['packages'],
    'sysml.usecase@1': ['usecase', 1],
    'sysml.activity@1': ['activity', 1],
    'sysml.sequence@1': ['sequence', 1],
    'sysml.statemachine@1': ['state', 2],
    'dmn.drd@1': ['decision'],
    'soaml.services@1': ['services'],
    'uaf.strategic@1': ['uaf', 0],
    'uaf.operational@1': ['uaf', 1],
    'uaf.services@1': ['services', 1],
    'uaf.systems@1': ['uaf', 2],
    'uaf.personnel@1': ['tree', 1],
    'uaf.resources@1': ['uaf', 3],
    'uaf.security@1': ['uaf', 4],
    'uaf.projects@1': ['uaf', 5],
    'uaf.standards@1': ['uaf', 6],
    'uaf.actualresources@1': ['rack', 1],
    'uaf.dictionary@1': ['table', 2],
    'uaf.summary@1': ['panels', 1],
    'flow.iso5807@1': ['flow', 2],
    'c4.deployment@1': ['deployment', 1],
    'c4.dynamic@1': ['communication', 1],
    'epc.complete@1': ['epc', 1],
    'msc.basic@1': ['sequence', 2],
    'idef0.basic@1': ['idef'],
    'petri.basic@1': ['petri'],
    'orm.basic@1': ['orm'],
    'vsm.basic@1': ['vsm'],
    'sdl.basic@1': ['sdl'],
    'sdl.process@1': ['sdl', 1],
    'fbd.basic@1': ['fbd'],
    'ladder.basic@1': ['ladder'],
};
const methods = {
    MT01: ['DDN', 'erd'], MT02: ['UML', 'class'], MT03: ['Chen', 'chen'],
    MT04: ['Flowchart', 'flow'], MT05: ['BPMN', 'bpmn', 1], MT06: ['CMMN', 'case'],
    MT07: ['DMN', 'decision'], MT08: ['C4', 'c4', 1], MT09: ['DFD', 'dfd'],
    MT10: ['SysML', 'parametric'], MT11: ['ArchiMate', 'architecture'], MT12: ['EPC', 'epc'],
    MT13: ['IDEF0', 'idef'], MT14: ['Petri nets', 'petri'], MT15: ['ORM', 'orm'],
    MT16: ['Value stream', 'vsm'], MT17: ['SDL', 'sdl'], MT18: ['MSC', 'sequence', 2],
    MT19: ['SoaML', 'services'], MT20: ['UAF', 'uaf'], MT21: ['Electrical / control', 'circuit'],
};
export const methodLabel = (id) => methods[id]?.[0] ?? id;
const NS = 'http://www.w3.org/2000/svg';
const ink = 'var(--ddn-ui-text, #334155)', muted = 'var(--ddn-ui-muted, #64748b)';
const colours = ['#639cea', '#38b5a1', '#bf8bea', '#dba34c'];
function preview(document, example) {
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('viewBox', '0 0 160 96');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke-linecap', 'round');
    svg.setAttribute('stroke-linejoin', 'round');
    const add = (tag, attrs) => {
        const element = document.createElementNS(NS, tag);
        for (const [key, value] of Object.entries(attrs))
            element.setAttribute(key, String(value));
        svg.append(element);
        return element;
    };
    const path = (d, colour = ink, width = 1.8, fill = 'none', opacity = 1) => add('path', { d, stroke: colour, 'stroke-width': width, fill, opacity });
    const line = (x, y, x2, y2, colour = muted, width = 1.8) => path(`M${x},${y}L${x2},${y2}`, colour, width);
    const rect = (x, y, w, h, colour = colours[0], radius = 3, solid = false) => add('rect', { x, y, width: w, height: h, rx: radius, stroke: colour, 'stroke-width': 1.8, fill: colour, 'fill-opacity': solid ? .65 : .13 });
    const circle = (x, y, r, colour = colours[0], solid = false) => add('circle', { cx: x, cy: y, r, stroke: colour, 'stroke-width': 1.8, fill: colour, 'fill-opacity': solid ? .8 : .13 });
    const ellipse = (x, y, rx, ry, colour = colours[0]) => add('ellipse', { cx: x, cy: y, rx, ry, stroke: colour, 'stroke-width': 1.8, fill: colour, 'fill-opacity': .13 });
    const text = (x, y, value, size = 9, colour = ink) => { const e = add('text', { x, y, fill: colour, stroke: 'none', 'font-size': size, 'font-family': 'system-ui,sans-serif', 'font-weight': 600, 'text-anchor': 'middle' }); e.textContent = value; return e; };
    const arrow = (x, y, x2, y2, colour = muted) => {
        line(x, y, x2, y2, colour);
        const a = Math.atan2(y2 - y, x2 - x), r = 4;
        path(`M${x2 - r * Math.cos(a - .5)},${y2 - r * Math.sin(a - .5)}L${x2},${y2}L${x2 - r * Math.cos(a + .5)},${y2 - r * Math.sin(a + .5)}`, colour);
    };
    const diamond = (x, y, w = 13, h = 10, colour = colours[2]) => path(`M${x - w},${y}L${x},${y - h}L${x + w},${y}L${x},${y + h}Z`, colour, 1.8, colour, .8);
    const labelLines = (x, y, w, count = 2) => { for (let i = 0; i < count; i++)
        line(x, y + i * 6, x + w - (i % 2) * w * .2, y + i * 6, muted, 1); };
    const box = (x, y, w = 38, h = 30, colour = colours[0], rows = 2) => { rect(x, y, w, h, colour); line(x, y + 10, x + w, y + 10, colour, 1.2); labelLines(x + 6, y + 17, w - 12, rows); };
    const actor = (x, y, colour = ink) => { circle(x, y, 4, colour); path(`M${x},${y + 4}V${y + 18}M${x - 8},${y + 10}H${x + 8}M${x},${y + 18}L${x - 7},${y + 28}M${x},${y + 18}L${x + 7},${y + 28}`, colour, 1.5); };
    const axes = () => { path('M20,13V79H145', muted, 1.2); };
    const dash = (d, colour = muted) => { const p = path(d, colour, 1.2); p.setAttribute('stroke-dasharray', '4 4'); };
    const nodes = (points, edges, r = 5) => { for (const [a, b] of edges)
        line(...points[a], ...points[b]); points.forEach(([x, y], i) => circle(x, y, r, colours[i % 4], true)); };
    const [name, kind, variant = 0] = example ?? ['Unavailable preview', 'unknown'];
    svg.dataset.preview = kind;
    // All coordinates are authored examples, so previews do not disclose data.
    switch (kind) {
        case 'erd': {
            box(8, 11, 43, 37);
            box(105, 48, 45, 37, colours[1], 3);
            box(70, 10, 34, 25, colours[2], 1);
            path('M51,31H69V64H105', muted);
            path('M87,35V48H128', muted);
            if (variant)
                path('M96,58L105,64L96,70M58,25V37M61,25V37', colours[1]);
            else {
                circle(69, 31, 2, colours[0], true);
                circle(69, 64, 2, colours[1], true);
            }
            break;
        }
        case 'class':
        case 'object':
        case 'blocks': {
            box(57, 7, 46, 31, colours[0], kind === 'object' ? 2 : 1);
            box(9, 58, 49, 31, colours[1], 2);
            box(102, 58, 49, 31, colours[2], 2);
            path('M34,58V48H126V58M80,48V38', muted);
            if (kind === 'class')
                path('M75,44L80,38L85,44Z', ink, 1.2, 'var(--ddn-ui-surface,#fff)');
            if (kind === 'blocks') {
                text(80, 16, '«block»', 7);
                rect(7, 67, 4, 6, colours[1], 0);
                rect(149, 67, 4, 6, colours[2], 0);
            }
            if (kind === 'object') {
                line(66, 14, 93, 14, colours[0], 1);
                line(18, 65, 47, 65, colours[1], 1);
            }
            if (variant) {
                dash('M58,75H102');
                text(80, 69, '1..*', 8);
            }
            break;
        }
        case 'chen': {
            rect(6, 39, 38, 24, colours[0], 0);
            rect(116, 39, 38, 24, colours[1], 0);
            line(44, 51, 66, 51);
            line(94, 51, 116, 51);
            diamond(80, 51, 14, 11);
            ellipse(22, 14, 17, 7);
            line(24, 21, 24, 39);
            ellipse(139, 14, 17, 7, colours[1]);
            line(138, 21, 138, 39);
            if (variant === 2) {
                rect(61, 76, 38, 15, colours[3], 0);
                line(80, 62, 80, 76);
            }
            else {
                ellipse(79, 17, 18, 8, colours[2]);
                line(80, 25, 80, 40);
            }
            if (variant === 1) {
                text(51, 45, '1', 8);
                text(108, 45, 'N', 8);
            }
            break;
        }
        case 'flow':
        case 'activity':
        case 'sdl': {
            circle(14, 21, 5, colours[0], true);
            arrow(19, 21, 39, 21);
            rect(39, 10, 37, 22, colours[0], kind === 'sdl' ? 0 : 7);
            arrow(76, 21, 99, 21);
            diamond(111, 21, 12, 11);
            path('M123,21H144V67H123M111,32V52', muted);
            rect(94, 52, 34, 28, colours[1], kind === 'sdl' ? 0 : 5);
            rect(20, 56, 42, 24, colours[2], 4);
            arrow(94, 68, 62, 68);
            if (kind === 'activity') {
                path('M79,53V82', ink, 4);
                if (variant > 1)
                    text(41, 71, 'ref', 10);
            }
            if (kind === 'sdl')
                path('M20,56H57L65,68L57,80H20Z', colours[2]);
            if (kind === 'flow' && variant) {
                path('M20,74Q31,66 41,74T62,74', colours[2]);
                if (variant === 2)
                    path('M39,10L34,32M47,10L42,32', colours[0]);
            }
            break;
        }
        case 'dfd': {
            rect(6, 13, 31, 21, colours[0], 0);
            line(37, 24, 55, 24);
            arrow(55, 24, 55, 42);
            if (variant)
                rect(37, 42, 39, 31, colours[1], 6);
            else
                circle(57, 56, 18, colours[1]);
            arrow(76, 56, 99, 56);
            if (variant)
                rect(100, 42, 36, 31, colours[2], 6);
            else
                circle(119, 56, 18, colours[2]);
            path('M119,38V21H140', muted);
            path('M102,8H150M102,27H150', colours[3]);
            arrow(56, 74, 56, 85);
            path('M13,80H42M13,91H42', colours[0]);
            break;
        }
        case 'usecase': {
            actor(17, 36);
            rect(46, 7, 106, 80, colours[0], 1);
            ellipse(99, 29, 30, 12, colours[1]);
            ellipse(99, 66, 30, 12, colours[2]);
            line(25, 48, 70, 29);
            line(25, 48, 69, 66);
            if (variant)
                dash('M99,42V54');
            if (variant === 2) {
                ellipse(139, 48, 9, 6, colours[3]);
                dash('M122,35L133,44');
            }
            break;
        }
        case 'requirements': {
            box(8, 14, 54, 40, colours[0], 3);
            box(99, 41, 52, 41, colours[1], 3);
            dash('M63,36H80V61H99');
            text(35, 23, variant ? '«requirement»' : 'REQ-01', 7);
            text(125, 50, 'REQ-02', 7);
            rect(99, 8, 45, 18, colours[2]);
            dash('M121,26V41');
            break;
        }
        case 'matrix':
        case 'table': {
            const w = kind === 'matrix' ? 24 : 29, cols = kind === 'matrix' ? 5 : 4;
            rect(15, 9, w * cols, 77, colours[0], 2);
            rect(15, 9, w * cols, 14, colours[0], 1, true);
            for (let x = 1; x < cols; x++)
                line(15 + x * w, 9, 15 + x * w, 86, muted, 1);
            for (let y = 1; y < 5; y++)
                line(15, 23 + y * 13, 15 + w * cols, 23 + y * 13, muted, 1);
            if (kind === 'matrix') {
                for (let y = 0; y < 4; y++)
                    for (let x = 1; x < 5; x++) {
                        if ((x + y) % 3 !== 0)
                            text(27 + x * w, 33 + y * 13, variant === 1 ? 'RACI'[(x + y) % 4] : variant === 2 ? 'CRUD'[(x + y) % 4] : '●', 8, colours[(x + y) % 4]);
                    }
            }
            else {
                for (let y = 0; y < 4; y++) {
                    labelLines(21, 31 + y * 13, 17, 1);
                    if (variant === 1) {
                        text(58, 34 + y * 13, y % 2 ? '≤' : '≥', 9);
                        text(119, 34 + y * 13, y % 2 ? 'Yes' : 'No', 8, colours[1]);
                    }
                    else
                        labelLines(52, 31 + y * 13, 65, 1);
                }
            }
            break;
        }
        case 'panels':
        case 'wireframe': {
            rect(7, 7, 146, 82, colours[0], 4);
            line(7, 21, 153, 21, colours[0]);
            circle(14, 14, 1.4, colours[0], true);
            circle(21, 14, 1.4, colours[1], true);
            circle(28, 14, 1.4, colours[2], true);
            if (kind === 'wireframe') {
                rect(14, 29, 29, 52, colours[2], 2);
                labelLines(20, 36, 15, 5);
                rect(51, 29, 94, 16, colours[1], 2);
                rect(51, 52, 43, 29, colours[0]);
                rect(102, 52, 43, 29, colours[3]);
                path('M56,76L69,60L78,69L87,58', colours[0]);
            }
            else {
                rect(15, 29, 56, 51, colours[1]);
                rect(80, 29, 64, 23, colours[2]);
                rect(80, 59, 64, 21, colours[3]);
                if (variant) {
                    path('M21,71L33,57L44,62L62,39', colours[1], 2);
                    for (let i = 0; i < 4; i++)
                        rect(87 + i * 12, 44 - i * 3, 7, 5 + i * 3, colours[2], 0, true);
                    path('M86,71H108L113,65L119,76L126,68H139', colours[3]);
                }
                else {
                    labelLines(24, 41, 36, 4);
                    labelLines(89, 39, 42, 1);
                    labelLines(89, 68, 42, 1);
                }
            }
            break;
        }
        case 'canvas': {
            rect(7, 9, 146, 78, colours[0], 2);
            if (variant === 3) {
                for (let x = 1; x < 3; x++)
                    line(7 + x * 146 / 3, 9, 7 + x * 146 / 3, 87, muted, 1);
                line(7, 48, 153, 48, muted, 1);
                for (let i = 0; i < 6; i++)
                    rect(15 + (i % 3) * 48, 18 + Math.floor(i / 3) * 39, 23, 12, colours[i % 4]);
            }
            else {
                for (const x of [36, 65, 95, 124])
                    line(x, 9, x, 66, muted, 1);
                line(7, 66, 153, 66, muted, 1);
                line(80, 66, 80, 87, muted, 1);
                line(36, 38, 65, 38, muted, 1);
                line(95, 38, 124, 38, muted, 1);
                for (const [x, y, c] of [[14, 18, 0], [42, 18, 1], [72, 31, 2], [102, 18, 1], [131, 18, 0], [41, 47, 3], [102, 47, 2], [25, 73, 1], [103, 73, 3]])
                    rect(x, y, 15, 8, colours[c], 1, variant === 2);
            }
            break;
        }
        case 'quadrant': {
            rect(19, 10, 122, 75, colours[0], 1);
            line(80, 10, 80, 85, muted, 1.5);
            line(19, 47, 141, 47, muted, 1.5);
            const words = variant === 1 ? ['P', 'E', 'S', 'T'] : variant === 2 ? ['★', '?', '●', '×'] : variant === 3 ? ['Market', 'Product', 'Develop', 'Diversify'] : ['SO', 'WO', 'ST', 'WT'];
            words.forEach((w, i) => { rect(24 + (i % 2) * 61, 15 + Math.floor(i / 2) * 37, 51, 27, colours[i], 2); text(49 + (i % 2) * 61, 33 + Math.floor(i / 2) * 37, w, w.length > 3 ? 8 : 14, colours[i]); });
            break;
        }
        case 'forces': {
            rect(58, 36, 44, 25, colours[0]);
            for (const [x, y] of [[56, 5], [6, 39], [113, 39], [56, 72]])
                rect(x, y, 42, 18, colours[1]);
            arrow(79, 23, 79, 36);
            arrow(48, 48, 58, 48);
            arrow(113, 48, 102, 48);
            arrow(79, 72, 79, 61);
            break;
        }
        case 'empathy': {
            path('M17,10H143V86H17ZM17,10L143,86M17,86L143,10', muted, 1.2);
            circle(80, 47, 15, colours[0]);
            circle(75, 43, 1, colours[0], true);
            circle(85, 43, 1, colours[0], true);
            path('M74,52Q80,58 86,52', colours[0]);
            text(80, 22, 'THINK', 8);
            text(80, 79, 'DO', 8);
            text(35, 49, 'SAY', 8);
            text(125, 49, 'FEEL', 8);
            break;
        }
        case 'scorecard': {
            for (let i = 0; i < 4; i++) {
                const y = 7 + i * 22;
                rect(9, y, 142, 16, colours[i]);
                text(24, y + 11, String(i + 1), 8, colours[i]);
                rect(42, y + 5, 68 - i * 12, 6, colours[i], 1, true);
                circle(137, y + 8, 3, colours[i], true);
            }
            break;
        }
        case 'chart':
        case 'histogram':
        case 'ranked': {
            axes();
            const heights = kind === 'histogram' ? [12, 25, 47, 61, 45, 29, 13] : [23, 47, 33, 59, 44];
            if (kind === 'ranked') {
                for (let i = 0; i < 5; i++)
                    rect(27, 17 + i * 12, 105 - i * 18, 7, colours[i % 4], 1, true);
            }
            else
                heights.forEach((h, i) => rect(27 + i * (kind === 'histogram' ? 16 : 23), 78 - h, kind === 'histogram' ? 15 : 14, h, colours[i % 2], 1, true));
            if (kind === 'chart')
                path('M27,63L48,51L71,59L94,30L126,21L140,29', colours[2], 2.6);
            break;
        }
        case 'radar': {
            const pts = (r) => Array.from({ length: 6 }, (_, i) => `${80 + Math.sin(i * Math.PI / 3) * r},${47 - Math.cos(i * Math.PI / 3) * r}`).join(' ');
            for (const r of [17, 34])
                add('polygon', { points: pts(r), stroke: muted, 'stroke-width': 1 });
            for (let i = 0; i < 6; i++)
                line(80, 47, 80 + Math.sin(i * Math.PI / 3) * 34, 47 - Math.cos(i * Math.PI / 3) * 34, muted, 1);
            path('M80,18L105,33L101,59L80,76L52,63L65,38Z', colours[0], 2, colours[0], .7);
            path('M80,30L97,37L109,64L80,63L65,55L57,34Z', colours[1], 2);
            break;
        }
        case 'funnel':
        case 'pyramid': {
            for (let i = 0; i < 4; i++) {
                const top = kind === 'pyramid' ? 16 + i * 29 : 136 - i * 29, bottom = kind === 'pyramid' ? top + 26 : top - 26, y = 8 + i * 21;
                path(`M${80 - top / 2},${y}H${80 + top / 2}L${80 + bottom / 2},${y + 17}H${80 - bottom / 2}Z`, colours[i], 1.5, colours[i], .65);
            }
            break;
        }
        case 'timeline': {
            line(12, 48, 148, 48, muted, 2);
            for (let i = 0; i < 5; i++) {
                const x = 22 + i * 29, y = i % 2 ? 67 : 19;
                circle(x, 48, 4, colours[i % 4], true);
                line(x, 48, x, y, colours[i % 4]);
                rect(x - 12, y - 8, 25, 16, colours[i % 4]);
            }
            break;
        }
        case 'fishbone': {
            arrow(9, 49, 135, 49);
            rect(135, 35, 21, 28, colours[0], 1);
            for (const x of [49, 86, 123]) {
                path(`M${x},49L${x - 20},12M${x},49L${x - 20},86`, colours[0]);
                for (const f of [.3, .65]) {
                    const dx = x - 20 * f;
                    line(dx, 49 - 37 * f, dx - 22, 49 - 37 * f, colours[1], 1.3);
                    line(dx, 49 + 37 * f, dx - 22, 49 + 37 * f, colours[2], 1.3);
                }
            }
            break;
        }
        case 'heatmap':
        case 'calendar': {
            const cols = kind === 'calendar' ? 12 : 7, rows = kind === 'calendar' ? 7 : 5, w = kind === 'calendar' ? 10 : 17, h = kind === 'calendar' ? 10 : 13;
            for (let y = 0; y < rows; y++)
                for (let x = 0; x < cols; x++) {
                    const level = variant === 2 ? Math.max(.1, 1 - Math.hypot(x - 3, y - 2) / 4) : .15 + ((x * 2 + y * 3) % 7) * .12;
                    const r = rect(18 + x * (w + 1), 12 + y * (h + 1), w, h, colours[variant === 1 ? 2 : 0], 1);
                    r.setAttribute('fill-opacity', String(level));
                    r.setAttribute('stroke', 'none');
                }
            break;
        }
        case 'quality': {
            axes();
            dash('M20,27H145', colours[2]);
            dash('M20,65H145', colours[2]);
            line(20, 46, 145, 46, colours[1], 1);
            path('M22,48L34,40L47,52L60,45L73,34L85,41L98,50L110,43L123,57L140,49', colours[0], 2);
            circle(123, 57, 3, colours[0], true);
            break;
        }
        case 'state': {
            if (variant) {
                rect(8, 8, 144, 80, colours[2], 8);
                text(30, 20, 'State', 8, colours[2]);
            }
            circle(20, 43, 4, ink, true);
            rect(41, 30, 36, 27, colours[0], 9);
            rect(108, 48, 36, 27, colours[1], 9);
            arrow(24, 43, 41, 43);
            path('M77,43H94V61H108', muted);
            path('M126,48V24H61V30', muted);
            circle(92, 79, 5, ink);
            circle(92, 79, 2, ink, true);
            arrow(108, 68, 97, 77);
            if (variant === 2)
                line(46, 41, 72, 41, colours[0], 1);
            break;
        }
        case 'gauge': {
            path('M30,73A50,50 0 0 1 130,73', muted, 12);
            path('M30,73A50,50 0 0 1 98,26', colours[1], 12);
            path('M80,73L108,35', ink, 3);
            circle(80, 73, 5, colours[0], true);
            text(80, 91, '68%', 12);
            break;
        }
        case 'candlestick': {
            axes();
            for (const [x, lo, hi, open, close] of [[34, 26, 69, 40, 57], [55, 19, 58, 26, 47], [76, 32, 72, 39, 62], [97, 13, 57, 21, 48], [118, 21, 68, 34, 52], [139, 10, 46, 17, 31]]) {
                const c = x % 3 ? colours[1] : colours[2];
                line(x, lo, x, hi, c);
                rect(x - 5, open, 10, close - open, c, 0, true);
            }
            break;
        }
        case 'treemap': {
            rect(10, 10, 140, 76, colours[0], 2);
            rect(14, 14, 60, 68, colours[0], 0, true);
            rect(78, 14, 68, 28, colours[1], 0, true);
            rect(78, 46, 30, 36, colours[2], 0, true);
            rect(112, 46, 34, 20, colours[3], 0, true);
            rect(112, 70, 34, 12, colours[1], 0, true);
            break;
        }
        case 'sankey': {
            path('M20,25C65,25 65,28 138,28', colours[0], 16, 'none', .6);
            path('M20,32C71,32 70,73 138,73', colours[1], 11, 'none', .6);
            path('M20,72C75,72 67,37 138,37', colours[2], 12, 'none', .6);
            rect(12, 15, 9, 26, colours[0], 1, true);
            rect(12, 62, 9, 21, colours[2], 1, true);
            rect(138, 15, 10, 32, colours[0], 1, true);
            rect(138, 64, 10, 18, colours[1], 1, true);
            break;
        }
        case 'c4': {
            actor(20, 35);
            rect(56, 20, 57, 53, colours[0], 3);
            arrow(28, 48, 56, 48);
            rect(130, 32, 24, 31, colours[2]);
            arrow(113, 48, 130, 48);
            if (variant) {
                const boundary = rect(48, 10, 73, 75, muted, 0);
                boundary.setAttribute('stroke-dasharray', '4 3');
                rect(62, 28, 44, 17, colours[1]);
                rect(62, 52, variant === 2 ? 18 : 44, 15, colours[3]);
                if (variant === 2)
                    rect(87, 52, 19, 15, colours[2]);
            }
            else
                text(84, 50, 'System', 9);
            break;
        }
        case 'tree': {
            path('M80,28V45H27V57M80,45H133V57M80,45V57', muted);
            if (variant === 3) {
                circle(67, 17, 9, colours[0]);
                rect(83, 8, 18, 18, colours[1], 0);
                line(76, 17, 83, 17);
                for (const x of [27, 80, 133])
                    circle(x, 69, 11, colours[2]);
            }
            else {
                box(61, 6, 38, 23, colours[0], 1);
                for (const [i, x] of [8, 61, 114].entries()) {
                    box(x, 57, 38, 26, colours[(i + 1) % 4], 1);
                    if (variant === 1) {
                        circle(x + 19, 64, 3, colours[(i + 1) % 4], true);
                    }
                    if (variant === 2)
                        text(x + 19, 66, '1.' + (i + 1), 7);
                }
            }
            break;
        }
        case 'mindmap': {
            rect(58, 36, 44, 24, colours[0], 7);
            for (const [x, y, c] of [[9, 14, 1], [8, 69, 2], [119, 12, 3], [118, 69, 1]]) {
                const left = x < 50, startX = left ? 58 : 102, startY = y < 48 ? 43 : 53;
                const endX = left ? x + 33 : x, endY = y + 9;
                path(`M${startX},${startY}C${left ? 47 : 113},${startY} ${left ? 52 : 108},${endY} ${endX},${endY}`, colours[c], 2);
                rect(x, y, 33, 18, colours[c], 5);
            }
            break;
        }
        case 'concept': {
            ellipse(79, 48, 25, 14);
            ellipse(25, 17, 20, 10, colours[1]);
            ellipse(133, 17, 20, 10, colours[2]);
            ellipse(28, 80, 22, 10, colours[2]);
            ellipse(133, 78, 22, 10, colours[1]);
            line(43, 25, 63, 38);
            line(98, 38, 117, 25);
            line(60, 57, 43, 71);
            line(99, 57, 115, 70);
            dash('M48,80H110');
            text(80, 25, 'relates', 7, muted);
            break;
        }
        case 'epc': {
            path('M20,8H45L52,20L45,32H20L13,20Z', colours[2], 1.8, colours[2], .6);
            rect(68, 8, 42, 24, colours[1]);
            arrow(52, 20, 68, 20);
            circle(130, 20, 8, colours[3]);
            text(130, 23, '×', 12);
            arrow(110, 20, 122, 20);
            path('M130,28V65H104', muted);
            rect(64, 53, 40, 24, colours[1]);
            path('M17,53H42L49,65L42,77H17L10,65Z', colours[2], 1.8, colours[2], .6);
            arrow(64, 65, 49, 65);
            if (variant) {
                ellipse(87, 90, 22, 5, colours[0]);
                dash('M87,77V85');
            }
            break;
        }
        case 'journey': {
            for (let i = 0; i < 4; i++) {
                rect(9 + i * 38, 8, 33, 18, colours[i]);
                for (let j = 0; j < 2; j++)
                    rect(12 + i * 38, 34 + j * 15, 27, 10, colours[i], 2);
            }
            path('M12,82Q35,58 57,77T98,69T149,76', colours[0], 2.5);
            break;
        }
        case 'storymap': {
            for (let i = 0; i < 4; i++) {
                rect(10 + i * 38, 8, 31, 18, colours[0]);
                for (let j = 0; j < 3 - (i % 2); j++)
                    rect(10 + i * 38, 34 + j * 17, 31, 12, colours[(j + 1) % 4]);
            }
            dash('M5,49H155');
            break;
        }
        case 'venn': {
            for (const [x, y, c] of [[63, 36, 0], [97, 36, 1], [80, 64, 2]]) {
                const p = circle(x, y, 27, colours[c]);
                p.setAttribute('fill-opacity', '.23');
            }
            break;
        }
        case 'sequence': {
            for (let i = 0; i < 3; i++) {
                const x = 27 + i * 54;
                rect(x - 16, 7, 32, 17, colours[i]);
                dash(`M${x},24V88`);
                rect(x - 3, 36 + i * 10, 6, 34 - i * 4, colours[i], 0);
            }
            arrow(29, 37, 78, 37, colours[0]);
            arrow(82, 51, 133, 51, colours[1]);
            dash('M132,66H80');
            path('M85,62L80,66L85,70', muted);
            if (variant === 1) {
                const f = rect(15, 30, 132, 48, muted, 0);
                f.setAttribute('stroke-dasharray', '3 3');
                text(24, 39, 'alt', 7);
            }
            if (variant === 2)
                path('M27,80H80L91,86H135', colours[2]);
            break;
        }
        case 'communication': {
            box(12, 12, 42, 29, colours[0], 1);
            box(105, 12, 42, 29, colours[1], 1);
            box(58, 61, 44, 29, colours[2], 1);
            arrow(54, 26, 105, 26);
            arrow(127, 41, 100, 65);
            arrow(60, 70, 34, 41);
            text(79, 19, '1', 9);
            text(126, 57, '2', 9);
            text(39, 64, '3', 9);
            if (variant)
                dash('M54,32H104');
            break;
        }
        case 'timing': {
            axes();
            path('M21,26H50V43H77V26H108V43H145', colours[0], 2);
            path('M21,63H36V52H91V68H124V52H145', colours[1], 2);
            for (let i = 0; i < 5; i++)
                dash(`M${35 + i * 24},16V79`);
            if (variant) {
                path('M24,88H77M24,85V91M77,85V91', colours[2]);
                text(50, 93, 'Δt', 7);
            }
            break;
        }
        case 'packages': {
            for (const [x, y, c] of [[10, 17, 0], [100, 54, 1]]) {
                rect(x, y, 46, 32, colours[c], 1);
                rect(x, y - 7, 22, 8, colours[c], 1);
            }
            dash('M56,33H79V70H100');
            if (variant)
                text(31, 37, '«profile»', 7);
            else
                labelLines(19, 32, 28, 2);
            break;
        }
        case 'case': {
            const p = rect(8, 10, 145, 76, colours[0], 1);
            p.setAttribute('stroke-dasharray', '5 3');
            path('M8,10L20,2H153V86', colours[0]);
            rect(21, 27, 49, 24, colours[1]);
            rect(88, 27, 49, 24, colours[2]);
            diamond(79, 70, 14, 6, colours[3]);
            dash('M47,51V70H65M114,51V70H93');
            if (variant) {
                text(45, 43, '+', 13);
                circle(140, 73, 6, colours[1]);
            }
            break;
        }
        case 'composite': {
            rect(10, 10, 140, 76, colours[0], 2);
            box(25, 29, 43, 34, colours[1], 2);
            box(92, 29, 43, 34, colours[2], 2);
            rect(8, 43, 5, 10, colours[0], 0);
            rect(147, 43, 5, 10, colours[0], 0);
            path('M13,48H25M68,48H92M135,48H147', muted);
            if (variant) {
                for (const x of [64, 91])
                    rect(x, 44, 6, 8, colours[3], 0);
            }
            if (variant === 2)
                text(80, 24, 'flow', 8);
            break;
        }
        case 'parametric': {
            rect(7, 10, 146, 76, colours[0], 2);
            rect(49, 30, 64, 36, colours[2], 4);
            text(81, 52, 'F = m × a', 11, colours[2]);
            for (const [x, y] of [[23, 28], [23, 65], [137, 47]]) {
                circle(x, y, 6, colours[1]);
                line(x < 80 ? x + 6 : x - 6, y, x < 80 ? 49 : 113, y < 40 ? 39 : 57, colours[1]);
            }
            if (variant)
                text(81, 22, '«constraint»', 7);
            break;
        }
        case 'architecture': {
            for (let i = 0; i < 3; i++) {
                rect(8, 7 + i * 29, 144, 24, colours[i], 1);
                for (let j = 0; j < 3; j++)
                    rect(17 + j * 46, 12 + i * 29, 34, 14, colours[i], 2);
            }
            arrow(35, 31, 35, 36);
            arrow(81, 60, 81, 65);
            break;
        }
        case 'pert': {
            nodes([[15, 48], [58, 20], [57, 76], [108, 20], [108, 76], [146, 48]], [[0, 1], [0, 2], [1, 3], [2, 4], [3, 5], [4, 5], [1, 4]], 7);
            path('M15,48L58,20H108L146,48', colours[2], 3);
            break;
        }
        case 'fault': {
            rect(60, 5, 40, 18, colours[2]);
            line(80, 23, 80, 36);
            path('M67,49V40A13,11 0 0 1 93,40V49Z', colours[0]);
            path('M67,49H93M80,49V60H31V73M80,60H129V73', muted);
            circle(31, 81, 8, colours[1]);
            circle(80, 81, 8, colours[3]);
            circle(129, 81, 8, colours[1]);
            line(80, 60, 80, 73);
            break;
        }
        case 'eventtree': {
            path('M10,48H48V21H91V9H144M91,21V35H144M48,48V73H91V59H144M91,73V88H144', colours[0]);
            for (const [x, y] of [[48, 21], [48, 73], [91, 9], [91, 35], [91, 59], [91, 88]])
                circle(x, y, 2.5, colours[1], true);
            text(25, 42, 'Event', 8);
            break;
        }
        case 'network': {
            circle(80, 45, 13, colours[0]);
            for (const [x, y] of [[18, 19], [142, 19], [19, 77], [141, 77]]) {
                line(80, 45, x, y, muted);
                rect(x - 11, y - 8, 22, 16, colours[1], 2);
                line(x - 5, y + 11, x + 5, y + 11, colours[1]);
            }
            circle(80, 45, 4, colours[0], true);
            break;
        }
        case 'rack': {
            for (let k = 0; k < 3; k++) {
                const x = 14 + k * 48;
                rect(x, 8, 36, 80, colours[k], 2);
                for (let y = 15; y < 78; y += 13) {
                    rect(x + 5, y, 26, 9, colours[k], 1);
                    circle(x + 25, y + 4.5, 1, colours[1], true);
                    labelLines(x + 9, y + 4.5, 9, 1);
                }
            }
            if (variant)
                path('M32,89V94H128V89', muted);
            break;
        }
        case 'density': {
            axes();
            path('M21,78C37,78 40,66 51,46C67,10 85,12 99,42C115,75 128,78 145,78', colours[0], 2.5, colours[0], .8);
            path('M21,78C59,78 67,62 88,41C110,18 116,69 145,78', colours[1], 2.2);
            break;
        }
        case 'qq': {
            axes();
            dash('M25,73L139,17', colours[2]);
            for (const [x, y] of [[29, 70], [43, 65], [55, 61], [66, 51], [79, 46], [90, 39], [103, 34], [118, 28], [135, 19]])
                circle(x, y, 3, colours[0], true);
            break;
        }
        case 'quantiledot': {
            axes();
            for (let i = 0; i < 11; i++) {
                const n = [1, 1, 2, 3, 5, 5, 4, 3, 2, 1, 1][i];
                for (let j = 0; j < n; j++)
                    circle(29 + i * 10, 73 - j * 11, 3.5, colours[i < 6 ? 0 : 1], true);
            }
            break;
        }
        case 'dotplot': {
            axes();
            for (let i = 0; i < 5; i++) {
                const y = 20 + i * 12;
                line(28, y, 137, y, muted, 1);
                circle([61, 95, 79, 126, 47][i], y, 4, colours[i % 4], true);
            }
            break;
        }
        case 'boxplot': {
            axes();
            for (const [i, row] of [[32, 55, 93, 124], [43, 72, 108, 141], [27, 40, 83, 114]].entries()) {
                const y = 25 + i * 22;
                line(row[0], y, row[3], y);
                path(`M${row[0]},${y - 5}V${y + 5}M${row[3]},${y - 5}V${y + 5}`, muted);
                rect(row[1], y - 7, row[2] - row[1], 14, colours[i], 0);
                line((row[1] + row[2]) / 2, y - 7, (row[1] + row[2]) / 2, y + 7, colours[i]);
            }
            break;
        }
        case 'violin': {
            axes();
            for (let i = 0; i < 3; i++) {
                const x = 47 + i * 38, w = [15, 10, 18][i];
                path(`M${x},14C${x - w},26 ${x - w},38 ${x - 4},49C${x - w},67 ${x - 10},74 ${x},78C${x + 10},74 ${x + w},67 ${x + 4},49C${x + w},38 ${x + w},26 ${x},14Z`, colours[i], 1.5, colours[i], .65);
                line(x, 27, x, 67, ink, 1);
                circle(x, 48, 2, ink, true);
            }
            break;
        }
        case 'beeswarm': {
            axes();
            for (let i = 0; i < 3; i++) {
                const x = 48 + i * 39;
                for (const [dx, y] of [[0, 22], [-4, 32], [5, 34], [-9, 43], [0, 43], [9, 45], [-5, 53], [4, 56], [0, 65], [3, 73]])
                    circle(x + dx, y + (i === 1 ? -7 : i === 2 ? 3 : 0), 2.7, colours[i], true);
            }
            break;
        }
        case 'tidytree': {
            path('M18,48H57V20H103V10H145M103,20V34H145M57,48V73H103V61H145M103,73V87H145', muted);
            for (const [x, y] of [[18, 48], [57, 20], [57, 73], [103, 10], [103, 34], [103, 61], [103, 87], [145, 10], [145, 34], [145, 61], [145, 87]])
                circle(x, y, 3, colours[x < 100 ? 0 : 1], true);
            break;
        }
        case 'radialtree': {
            circle(80, 48, 4, colours[0], true);
            for (let i = 0; i < 6; i++) {
                const a = i * Math.PI / 3, x = 80 + Math.cos(a) * 21, y = 48 + Math.sin(a) * 21;
                line(80, 48, x, y);
                circle(x, y, 3, colours[1], true);
                for (const offset of [-.19, .19]) {
                    const xx = 80 + Math.cos(a + offset) * 39, yy = 48 + Math.sin(a + offset) * 39;
                    line(x, y, xx, yy);
                    circle(xx, yy, 2.5, colours[2], true);
                }
            }
            break;
        }
        case 'circlepack': {
            circle(80, 48, 42, colours[0]);
            circle(62, 47, 23, colours[1]);
            circle(103, 47, 17, colours[2]);
            circle(86, 76, 10, colours[3]);
            for (const [x, y, r] of [[55, 39, 10], [67, 57, 9], [105, 42, 9], [98, 57, 5]])
                circle(x, y, r, colours[1], true);
            break;
        }
        case 'sunburst': {
            const arc = (r, start, end, c, w) => { const a = start * Math.PI / 180, b = end * Math.PI / 180; path(`M${80 + r * Math.cos(a)},${48 + r * Math.sin(a)}A${r},${r} 0 ${end - start > 180 ? 1 : 0} 1 ${80 + r * Math.cos(b)},${48 + r * Math.sin(b)}`, c, w); };
            circle(80, 48, 8, colours[0], true);
            for (let i = 0; i < 4; i++) {
                arc(20, i * 90 + 3, i * 90 + 87, colours[i], 12);
                for (let j = 0; j < 2; j++)
                    arc(36, i * 90 + j * 45 + 3, i * 90 + j * 45 + 42, colours[(i + j) % 4], 12);
            }
            break;
        }
        case 'bubbles': {
            for (const [x, y, r, c] of [[62, 52, 27, 0], [108, 39, 20, 1], [113, 73, 12, 2], [42, 15, 10, 3], [89, 15, 12, 2], [25, 54, 8, 1], [75, 86, 7, 3]])
                circle(x, y, r, colours[c], true);
            break;
        }
        case 'parallel': {
            for (const x of [25, 61, 97, 133]) {
                line(x, 12, x, 84, muted, 1.2);
                for (const y of [24, 48, 72])
                    line(x - 3, y, x + 3, y, muted, 1);
            }
            for (const [i, ys] of [[23, 58, 33, 69], [70, 27, 61, 30], [45, 75, 20, 48]].entries())
                path('M' + [25, 61, 97, 133].map((x, j) => `${x},${ys[j]}`).join('L'), colours[i], 2);
            break;
        }
        case 'wordcloud': {
            text(77, 45, 'IDEAS', 24, colours[0]);
            text(47, 65, 'design', 15, colours[1]);
            text(111, 64, 'DATA', 13, colours[2]);
            text(91, 22, 'people', 11, colours[3]);
            text(87, 81, 'connections', 10, muted);
            text(22, 29, 'maps', 9, colours[2]);
            break;
        }
        case 'arc': {
            line(12, 59, 149, 59, muted, 1);
            for (const [a, b, c] of [[18, 118, 0], [44, 145, 1], [18, 71, 2], [70, 118, 3]])
                path(`M${a},59A${(b - a) / 2},${(b - a) / 2 * .8} 0 0 1 ${b},59`, colours[c], 2.3);
            path('M44,59Q80,104 145,59', colours[2], 1.8);
            for (const x of [18, 44, 70, 94, 118, 145])
                circle(x, 59, 3.6, colours[0], true);
            break;
        }
        case 'force': {
            nodes([[23, 25], [68, 16], [110, 26], [143, 51], [109, 78], [65, 72], [20, 68], [79, 45]], [[0, 1], [1, 2], [2, 3], [3, 4], [4, 5], [5, 6], [6, 0], [0, 7], [2, 7], [4, 7], [5, 7], [1, 7]], 6);
            break;
        }
        case 'bundle': {
            for (let i = 0; i < 14; i++) {
                const a = i * Math.PI * 2 / 14, x = 80 + Math.cos(a) * 40, y = 48 + Math.sin(a) * 40;
                circle(x, y, 2.8, colours[i % 4], true);
                const b = (i + 5) % 14 * Math.PI * 2 / 14;
                path(`M${x},${y}Q80,48 ${80 + Math.cos(b) * 40},${48 + Math.sin(b) * 40}`, colours[i % 4], 1.2, 'none', .65);
            }
            break;
        }
        case 'map': {
            const regions = ['M15,27L35,14L55,19L63,34L47,45L27,43Z', 'M47,45L64,51L61,68L51,85L42,64Z', 'M78,24L94,16L109,22L106,37L89,42L77,34Z', 'M89,42L105,37L116,53L103,74L88,62Z', 'M109,22L137,17L151,32L138,46L116,43L106,37Z', 'M123,64L143,63L150,75L136,83L122,76Z'];
            regions.forEach((d, i) => path(d, muted, 1.2, variant === 1 ? colours[i % 4] : 'none', variant === 1 ? .8 : 1));
            if (variant === 2)
                for (const [x, y, r] of [[34, 30, 6], [55, 59, 4], [92, 29, 5], [102, 54, 7], [132, 30, 4], [137, 73, 5]])
                    circle(x, y, r, colours[0], true);
            break;
        }
        case 'deployment': {
            for (const [x, y, c] of [[8, 15, 0], [99, 48, 1]]) {
                path(`M${x},${y + 8}L${x + 9},${y}H${x + 51}V${y + 32}L${x + 42},${y + 40}H${x}ZM${x},${y + 8}H${x + 42}L${x + 51},${y}M${x + 42},${y + 8}V${y + 40}`, colours[c]);
                rect(x + 9, y + 18, 25, 13, colours[c], 1);
            }
            path('M59,39H79V72H99', muted);
            if (variant)
                rect(15, 40, 24, 9, colours[2]);
            break;
        }
        case 'bpmn': {
            if (variant === 3) {
                for (const [x, y] of [[39, 24], [121, 24], [80, 73]])
                    path(`M${x - 15},${y}L${x - 7},${y - 13}H${x + 7}L${x + 15},${y}L${x + 7},${y + 13}H${x - 7}Z`, colours[0], 1.6, colours[0], .6);
                line(54, 24, 106, 24);
                line(47, 37, 72, 60);
                line(113, 37, 88, 60);
                break;
            }
            if (variant === 0) {
                rect(5, 6, 150, 39, muted, 0);
                rect(5, 53, 150, 37, muted, 0);
                line(16, 6, 16, 45);
                line(16, 53, 16, 90);
                dash('M80,45V53');
            }
            circle(27, variant === 0 ? 26 : 47, 7, colours[1]);
            rect(50, variant === 0 ? 15 : 34, 45, 26, colours[0], 4);
            arrow(34, variant === 0 ? 26 : 47, 50, variant === 0 ? 26 : 47);
            diamond(118, variant === 0 ? 27 : 47, 11, 11);
            arrow(95, variant === 0 ? 27 : 47, 107, variant === 0 ? 27 : 47);
            if (variant === 0) {
                rect(64, 63, 43, 18, colours[2], 3);
                circle(136, 72, 7, colours[1]);
                arrow(107, 72, 129, 72);
            }
            else {
                circle(145, 47, 7, colours[1]);
                arrow(129, 47, 138, 47);
            }
            if (variant === 2) {
                line(50, 40, 95, 40, colours[0]);
                line(50, 54, 95, 54, colours[0]);
            }
            break;
        }
        case 'decision': {
            rect(56, 11, 48, 27, colours[0], 0);
            rect(14, 67, 41, 18, colours[1], 9);
            rect(105, 67, 41, 18, colours[1], 9);
            arrow(35, 67, 65, 38);
            arrow(125, 67, 96, 38);
            path('M66,51L75,45H102V59H66Z', colours[2]);
            dash('M84,45V38');
            break;
        }
        case 'services': {
            rect(57, 31, 47, 34, colours[0], 3);
            actor(17, 29);
            rect(127, 33, 24, 28, colours[1], 3);
            line(25, 43, 57, 43);
            line(104, 48, 127, 48);
            circle(48, 43, 4, colours[2]);
            path('M116,43A5,5 0 0 0 116,53', colours[2]);
            rect(59, 7, 44, 14, colours[3], 1);
            dash('M80,21V31');
            if (variant)
                rect(59, 76, 44, 14, colours[2], 1);
            break;
        }
        case 'uaf': {
            const col = colours[variant % 4];
            rect(13, 9, 134, 18, col);
            for (const [x, c] of [[19, 0], [99, 1]])
                box(x, 47, 42, 30, colours[c], 1);
            path('M80,27V38H40V47M80,38H120V47', muted);
            if (variant === 4) {
                path('M70,52L80,47L90,52V62Q90,72 80,78Q70,72 70,62Z', colours[2]);
            }
            else if (variant === 5) {
                path('M25,85H137', muted);
                for (const x of [40, 80, 120])
                    circle(x, 85, 3, colours[2], true);
            }
            else if (variant === 6) {
                text(81, 22, 'Standards', 8, col);
            }
            else {
                for (let i = 0; i < Math.min(variant + 1, 4); i++)
                    rect(29 + i * 26, 83, 19, 7, colours[i], 1, true);
            }
            break;
        }
        case 'idef': {
            rect(53, 29, 55, 39, colours[0], 0);
            text(81, 52, 'Function', 10);
            arrow(7, 48, 53, 48);
            arrow(108, 48, 154, 48);
            arrow(81, 5, 81, 29);
            arrow(81, 91, 81, 68);
            text(27, 41, 'Input', 7);
            text(133, 41, 'Output', 7);
            text(105, 15, 'Control', 7);
            break;
        }
        case 'petri': {
            circle(17, 48, 10, colours[0]);
            circle(76, 18, 10, colours[1]);
            circle(76, 78, 10, colours[1]);
            circle(144, 48, 10, colours[2]);
            rect(46, 35, 7, 26, ink, 0, true);
            rect(106, 35, 7, 26, ink, 0, true);
            arrow(27, 48, 46, 48);
            path('M53,44L68,26M53,52L68,70M84,26L106,44M84,70L106,52', muted);
            arrow(113, 48, 134, 48);
            circle(17, 48, 2, ink, true);
            circle(76, 18, 2, ink, true);
            break;
        }
        case 'orm': {
            ellipse(27, 25, 23, 13, colours[0]);
            ellipse(133, 25, 23, 13, colours[1]);
            rect(55, 49, 50, 20, colours[2], 0);
            line(80, 49, 80, 69, colours[2]);
            line(27, 38, 65, 49);
            line(133, 38, 95, 49);
            line(56, 44, 104, 44, ink, 2);
            ellipse(80, 86, 22, 7, colours[3]);
            line(80, 69, 80, 79);
            break;
        }
        case 'vsm': {
            rect(9, 9, 34, 23, colours[0], 0);
            rect(117, 9, 34, 23, colours[0], 0);
            path('M10,9V3L18,8L26,3L34,8', colours[0]);
            rect(57, 6, 46, 20, colours[2], 0);
            dash('M43,16H57M103,16H117');
            rect(12, 49, 38, 25, colours[1], 0);
            rect(110, 49, 38, 25, colours[1], 0);
            path('M72,49L85,73H59Z', colours[3]);
            text(72, 68, 'I', 10, colours[3]);
            arrow(50, 61, 59, 61);
            arrow(85, 61, 110, 61);
            path('M11,88H50V80H109V88H149', muted, 1.4);
            break;
        }
        case 'fbd': {
            rect(45, 17, 34, 60, colours[0], 1);
            rect(101, 35, 34, 42, colours[1], 1);
            text(62, 39, 'AND', 9);
            text(118, 57, 'OR', 9);
            path('M7,30H45M7,59H45M79,46H101M8,86H90V66H101M135,56H154', muted);
            for (const [x, y] of [[45, 30], [45, 59], [79, 46], [101, 46], [101, 66], [135, 56]])
                rect(x - 2, y - 2, 4, 4, colours[2], 0, true);
            break;
        }
        case 'ladder': {
            path('M12,8V88M148,8V88', ink, 2.5);
            for (const y of [27, 66]) {
                path(`M12,${y}H40M48,${y}H104M120,${y}H148M40,${y - 9}V${y + 9}M48,${y - 9}V${y + 9}M110,${y - 9}Q98,${y} 110,${y + 9}M114,${y - 9}Q126,${y} 114,${y + 9}`, colours[y === 27 ? 0 : 1]);
            }
            path('M37,77L51,55M72,66V47H128V66', colours[1]);
            break;
        }
        case 'circuit': {
            path('M15,48H38L43,40L50,56L57,40L64,56L71,40L76,48H109M109,23V74M116,23V74M116,48H145V85H15V57M15,39V9H145V48', colours[0], 2);
            line(7, 39, 23, 39, colours[1], 2);
            line(11, 57, 19, 57, colours[1], 2);
            circle(145, 48, 3, colours[1], true);
            circle(15, 85, 3, colours[1], true);
            break;
        }
        default: text(80, 57, '?', 32, muted);
    }
    const title = document.createElementNS(NS, 'title');
    title.textContent = name;
    svg.prepend(title);
    return svg;
}
export const methodPreview = (document, id) => preview(document, methods[id]);
export const profilePreview = (document, id) => preview(document, profiles[id] ? [profileLabel(id), ...profiles[id]] : undefined);
//# sourceMappingURL=view-previews.js.map