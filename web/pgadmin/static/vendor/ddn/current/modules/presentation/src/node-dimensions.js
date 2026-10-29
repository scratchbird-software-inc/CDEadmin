import { roleDescriptor } from '../../profiles/src/core.js';
import { array, object, str } from './model.js';
import { metadata } from './graph-glyphs.js';
/** Shared default proportions for canvas symbols and palette previews. */
export function graphNodeDimensions(role, profile, original, record = {}, fixedSize = false) {
    if (fixedSize)
        return original;
    const b = { ...original, width: Math.max(160, Math.min(280, original.width)), height: Math.max(72, original.height) };
    if (!profile.startsWith('bpmn') && !profile.startsWith('uml.activity') && ['flow.start', 'flow.end'].includes(role))
        return { ...b, width: 130, height: 52 };
    if (/^(state\.(initial|final|junction|entrypoint|exitpoint|terminate|history_deep|history_shallow)|flow\.(start|end|intermediate|flowfinal)|petri\.place|epk\.connector)$/.test(role))
        return { ...b, width: 54, height: 54 };
    if (/^(flow\.(decision|gateway|merge)|state\.choice|cmmn\.sentry)$/.test(role))
        return { ...b, width: 88, height: 80 };
    if (role === 'uml.actor' || role === 'c4.person' || roleDescriptor(role)?.render.silhouette === 'actor')
        return { ...b, width: 100, height: 116 };
    if (role === 'petri.transition')
        return { ...b, width: 80, height: 30 };
    if (role === 'family.union')
        return { ...b, width: 110, height: 110 };
    if (role === 'flow.forkjoin' || role === 'state.forkjoin')
        return { ...b, width: 160, height: 15 };
    if (role === 'network.rack' && profile === 'network.rack@1')
        return { ...b, width: 300, height: 560 };
    if (role === 'network.bus')
        return { ...b, width: 640, height: 30 };
    if (role.startsWith('ladder.'))
        return { ...b, width: 100, height: 55 };
    if (role === 'tree.event')
        return { ...b, width: 140, height: 140 };
    if (profile === 'dfd.yourdon@1' && role === 'dfd.process')
        return { ...b, width: 170, height: 170 };
    if (profile.startsWith('dfd.'))
        return { ...b, width: 170, height: role === 'dfd.process' ? 100 : 65 };
    if (role === 'flow.choreotask')
        return { ...b, height: Math.max(b.height, 88 + array(metadata(record, 'x_bands')).length * 18) };
    if (['inline', 'thumbnail'].includes(str(object(metadata(record, 'x_subdiagram')).display, profile === 'uml.interaction_overview@2' ? 'inline' : '')) && metadata(record, 'x_subdiagram'))
        return { ...b, width: 600, height: 400 };
    return b;
}
//# sourceMappingURL=node-dimensions.js.map