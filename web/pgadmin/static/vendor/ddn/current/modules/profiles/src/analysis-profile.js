import { indexRecords, resolveRecord, enclosingDefinitions } from './core.js';
import { getPath, isRecord } from './schema-core.js';
import { analyzeDecision, evaluateDecision, evaluateFlatTrace, calculateCriticalPath, decisionInputErrors } from './analysis.js';
import { profileSelection, decisionDomains, decisionRules, decisionOutputErrors } from './semantic.js';
const obj = (value) => isRecord(value) ? value : {};
const arr = (value) => Array.isArray(value) ? value : [];
const str = (value) => typeof value === 'string' ? value : '';
const id = (item) => item.file + '\0' + item.ref.id;
const json = (value) => JSON.parse(JSON.stringify(value));
export function flatTraceAnalysis(view, records) {
    const { nodes, links, resolve } = profileSelection(view, records), options = obj(getPath(view.record, 'projection.options'));
    const initial = nodes.find(node => node.record.role === 'state.initial'), domains = decisionDomains(view, records);
    const budget = typeof options.analysis_budget === 'number' ? options.analysis_budget : 4096;
    const transitions = links.map(link => { const data = obj(getPath(link.item.record, 'metadata.x_transition')); return { id: id(link.item), from: id(link.from), to: id(link.to), ...(typeof data.event === 'string' ? { event: data.event } : {}), ...(data.guard === undefined ? {} : { guard: data.guard }), ...(Array.isArray(data.actions) ? { actions: data.actions } : {}) }; });
    const traces = arr(options.traces);
    if (traces.length > 100)
        return { kind: 'flat-state', outcome: 'limit-exceeded', actionsExecuted: false, message: 'At most 100 traces are supported', results: [] };
    if (!initial)
        return { kind: 'flat-state', outcome: 'incomplete', actionsExecuted: false, message: 'An initial state is required', results: [] };
    const results = [];
    for (const reference of traces) {
        const trace = resolve(reference);
        if (!trace) {
            results.push({ outcome: 'invalid-input', message: 'Trace reference does not resolve', actionsExecuted: false });
            continue;
        }
        const data = obj(getPath(trace.record, 'metadata.x_record'));
        const rawEvents = trace.record.role === 'core::Trace' ? arr(getPath(trace.record, 'content.events')) : arr(data.events);
        const events = [];
        let valid = true;
        for (const raw of rawEvents) {
            const resolved = trace.record.role === 'core::Trace' ? resolve(raw, trace) : undefined;
            const value = resolved ? obj(getPath(resolved.record, 'content.payload')) : obj(raw);
            const event = typeof raw === 'string' && trace.record.role !== 'core::Trace' ? raw : str(value.event) || str(resolved?.record.name);
            if (!event) {
                valid = false;
                break;
            }
            events.push({ event, values: obj(value.values) });
        }
        const expected = resolve(data.expected, trace), expectedId = expected ? id(expected) : undefined;
        if (!valid || data.expected !== undefined && !expected) {
            results.push(json({ trace: trace.ref, outcome: 'invalid-input', message: 'Trace event or expected state is unresolved', actionsExecuted: false }));
            continue;
        }
        if (data.expected === undefined) {
            results.push(json({ trace: trace.ref, outcome: 'incomplete', message: 'Trace requires an explicit expected final state', actionsExecuted: false }));
            continue;
        }
        const result = evaluateFlatTrace(id(initial), transitions, events, budget, { domains, ...(expectedId === undefined ? {} : { expectedFinalState: expectedId }) });
        results.push(json({ trace: trace.ref, ...result }));
    }
    const outcomes = results.map(result => str(obj(result).outcome));
    return { kind: 'flat-state', outcome: outcomes.includes('budget_exceeded') ? 'budget_exceeded' : outcomes.includes('incomplete') ? 'incomplete' : outcomes.some(outcome => outcome !== 'valid') ? 'invalid' : 'valid', actionsExecuted: false, results };
}
/** Read-only bounded calculations for inspector output, with no action execution. */
export function analyzeProfile(normalized, target, values) {
    const records = indexRecords(normalized), selected = resolveRecord(records, target.file, target);
    let view = selected?.owner === 'view_definition' ? selected : undefined;
    if (!view && selected) {
        const owners = new Set(enclosingDefinitions(records, selected).map(id));
        const appearance = records.find(record => record.owner === 'appearance' && owners.has(id(resolveRecord(records, record.file, record.record.target) ?? record)));
        if (appearance)
            view = resolveRecord(records, appearance.file, appearance.record.parent);
    }
    if (!view)
        return { kind: 'none', outcome: 'unavailable' };
    const profile = str(view.record.profile), options = obj(getPath(view.record, 'projection.options'));
    if (profile === 'decision.rules@1') {
        const domains = decisionDomains(view, records), rules = decisionRules(view, records), hitPolicy = str(options.hit_policy) || 'unique';
        const result = analyzeDecision(domains, rules, { hitPolicy, coverage: str(options.coverage) || 'report', budget: typeof options.analysis_budget === 'number' ? options.analysis_budget : 4096 });
        const outputErrors = decisionOutputErrors(view, records, rules);
        if (outputErrors.length) {
            result.outcome = 'invalid';
            result.errors = [...result.errors, ...outputErrors];
        }
        const inputErrors = values === undefined ? [] : decisionInputErrors(domains, values);
        const matching = values === undefined ? undefined : inputErrors.length || result.errors.length ? { outcome: inputErrors.length ? 'invalid-input' : 'invalid-contract', hitPolicy, policyEvaluated: false, matches: [], outputs: [], valid: false, errors: inputErrors.length ? inputErrors : result.errors } : evaluateDecision(rules, values, hitPolicy);
        return json({ kind: 'decision', ...result, hitPolicy, inputs: domains, ...(matching === undefined ? {} : { matching }) });
    }
    if (profile === 'state.flat@1')
        return flatTraceAnalysis(view, records);
    if (profile === 'pert.cpm@1') {
        const { nodes, links } = profileSelection(view, records), missing = nodes.filter(node => getPath(node.record, 'metadata.x_estimate') === undefined);
        if (missing.length)
            return json({ kind: 'critical-path', outcome: 'incomplete', missing: missing.map(node => node.ref) });
        try {
            return json({ kind: 'critical-path', outcome: 'valid', ...calculateCriticalPath(nodes.map(node => ({ id: id(node), duration: getPath(node.record, 'metadata.x_estimate') })), links.map(link => ({ id: id(link.item), from: id(link.from), to: id(link.to) }))) });
        }
        catch (error) {
            return { kind: 'critical-path', outcome: 'invalid', message: error instanceof Error ? error.message : String(error) };
        }
    }
    return { kind: 'none', outcome: 'not-applicable' };
}
//# sourceMappingURL=analysis-profile.js.map