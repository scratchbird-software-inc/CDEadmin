/*! DDN — Diagram Design Notation
 * Copyright (c) 2026 ScratchBird Software Inc. and DDN contributors.
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Free and open-source software. See LICENSE and NOTICE.md.
 * Sponsored by ScratchBird Software Inc. — https://scratchbird.ca
 * Public project: https://github.com/ScratchBird-Software-Inc/Diagram-Design-Notation
 */
(()=>{"use strict";const runtime=globalThis["DDN_MODULES"];if(!runtime)throw Error("Missing DDN module runtime");runtime.register({"id":"shared-98e37fe0f266","version":"ddn-next-1","releaseHash":"4f601dab202a346b52c70ff1ec6bfdfb7c17ab3fbd59854e38cda422320d3131","dependencies":["shared-89ca0b52749b"],"modules":[{"id":"profiles/src/analysis-profile.js","bytes":7506,"sha256":"2e02a6465751a7392a33d1f9efe9c3837bc71684e057cd5aac1ebf850ae84b8e","dependencies":["profiles/src/core.js","profiles/src/schema-core.js","profiles/src/analysis.js","profiles/src/semantic.js"]},{"id":"profiles/src/analysis.js","bytes":17986,"sha256":"7a00c18e387e248915f5cf372587210dde0fde4a4d6117254e23b2c3d7ea994a","dependencies":["profiles/src/schema-core.js"]},{"id":"profiles/src/projection-rules.js","bytes":49930,"sha256":"26aee5b29aa58a24b0a2ff011ddaec2c662ce0386d56e3a0642c665d5440f7e2","dependencies":["profiles/src/core.js","profiles/src/schema-core.js","profiles/src/semantic.js"]},{"id":"profiles/src/semantic.js","bytes":67094,"sha256":"7f02c00a05eb63e073a1002817d5c8e266b0a0680a9e6d26de138d04f876d264","dependencies":["profiles/src/core.js","profiles/src/schema-core.js","profiles/src/analysis.js","profiles/src/analysis-profile.js","profiles/src/projection-rules.js"]}],"hash":"ed76d8c00864af0e785d2e0879426fc905f2612e496d2e138e6875328c05d1a4"},{"profiles/src/analysis-profile.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.flatTraceAnalysis = flatTraceAnalysis;
exports.analyzeProfile = analyzeProfile;
const core_js_1 = require("profiles/src/core.js");
const schema_core_js_1 = require("profiles/src/schema-core.js");
const analysis_js_1 = require("profiles/src/analysis.js");
const semantic_js_1 = require("profiles/src/semantic.js");
const obj = (value) => (0, schema_core_js_1.isRecord)(value) ? value : {};
const arr = (value) => Array.isArray(value) ? value : [];
const str = (value) => typeof value === 'string' ? value : '';
const id = (item) => item.file + '\0' + item.ref.id;
const json = (value) => JSON.parse(JSON.stringify(value));
function flatTraceAnalysis(view, records) {
    const { nodes, links, resolve } = (0, semantic_js_1.profileSelection)(view, records), options = obj((0, schema_core_js_1.getPath)(view.record, 'projection.options'));
    const initial = nodes.find(node => node.record.role === 'state.initial'), domains = (0, semantic_js_1.decisionDomains)(view, records);
    const budget = typeof options.analysis_budget === 'number' ? options.analysis_budget : 4096;
    const transitions = links.map(link => { const data = obj((0, schema_core_js_1.getPath)(link.item.record, 'metadata.x_transition')); return { id: id(link.item), from: id(link.from), to: id(link.to), ...(typeof data.event === 'string' ? { event: data.event } : {}), ...(data.guard === undefined ? {} : { guard: data.guard }), ...(Array.isArray(data.actions) ? { actions: data.actions } : {}) }; });
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
        const data = obj((0, schema_core_js_1.getPath)(trace.record, 'metadata.x_record'));
        const rawEvents = trace.record.role === 'core::Trace' ? arr((0, schema_core_js_1.getPath)(trace.record, 'content.events')) : arr(data.events);
        const events = [];
        let valid = true;
        for (const raw of rawEvents) {
            const resolved = trace.record.role === 'core::Trace' ? resolve(raw, trace) : undefined;
            const value = resolved ? obj((0, schema_core_js_1.getPath)(resolved.record, 'content.payload')) : obj(raw);
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
        const result = (0, analysis_js_1.evaluateFlatTrace)(id(initial), transitions, events, budget, { domains, ...(expectedId === undefined ? {} : { expectedFinalState: expectedId }) });
        results.push(json({ trace: trace.ref, ...result }));
    }
    const outcomes = results.map(result => str(obj(result).outcome));
    return { kind: 'flat-state', outcome: outcomes.includes('budget_exceeded') ? 'budget_exceeded' : outcomes.includes('incomplete') ? 'incomplete' : outcomes.some(outcome => outcome !== 'valid') ? 'invalid' : 'valid', actionsExecuted: false, results };
}
function analyzeProfile(normalized, target, values) {
    const records = (0, core_js_1.indexRecords)(normalized), selected = (0, core_js_1.resolveRecord)(records, target.file, target);
    let view = selected?.owner === 'view_definition' ? selected : undefined;
    if (!view && selected) {
        const owners = new Set((0, core_js_1.enclosingDefinitions)(records, selected).map(id));
        const appearance = records.find(record => record.owner === 'appearance' && owners.has(id((0, core_js_1.resolveRecord)(records, record.file, record.record.target) ?? record)));
        if (appearance)
            view = (0, core_js_1.resolveRecord)(records, appearance.file, appearance.record.parent);
    }
    if (!view)
        return { kind: 'none', outcome: 'unavailable' };
    const profile = str(view.record.profile), options = obj((0, schema_core_js_1.getPath)(view.record, 'projection.options'));
    if (profile === 'decision.rules@1') {
        const domains = (0, semantic_js_1.decisionDomains)(view, records), rules = (0, semantic_js_1.decisionRules)(view, records), hitPolicy = str(options.hit_policy) || 'unique';
        const result = (0, analysis_js_1.analyzeDecision)(domains, rules, { hitPolicy, coverage: str(options.coverage) || 'report', budget: typeof options.analysis_budget === 'number' ? options.analysis_budget : 4096 });
        const outputErrors = (0, semantic_js_1.decisionOutputErrors)(view, records, rules);
        if (outputErrors.length) {
            result.outcome = 'invalid';
            result.errors = [...result.errors, ...outputErrors];
        }
        const inputErrors = values === undefined ? [] : (0, analysis_js_1.decisionInputErrors)(domains, values);
        const matching = values === undefined ? undefined : inputErrors.length || result.errors.length ? { outcome: inputErrors.length ? 'invalid-input' : 'invalid-contract', hitPolicy, policyEvaluated: false, matches: [], outputs: [], valid: false, errors: inputErrors.length ? inputErrors : result.errors } : (0, analysis_js_1.evaluateDecision)(rules, values, hitPolicy);
        return json({ kind: 'decision', ...result, hitPolicy, inputs: domains, ...(matching === undefined ? {} : { matching }) });
    }
    if (profile === 'state.flat@1')
        return flatTraceAnalysis(view, records);
    if (profile === 'pert.cpm@1') {
        const { nodes, links } = (0, semantic_js_1.profileSelection)(view, records), missing = nodes.filter(node => (0, schema_core_js_1.getPath)(node.record, 'metadata.x_estimate') === undefined);
        if (missing.length)
            return json({ kind: 'critical-path', outcome: 'incomplete', missing: missing.map(node => node.ref) });
        try {
            return json({ kind: 'critical-path', outcome: 'valid', ...(0, analysis_js_1.calculateCriticalPath)(nodes.map(node => ({ id: id(node), duration: (0, schema_core_js_1.getPath)(node.record, 'metadata.x_estimate') })), links.map(link => ({ id: id(link.item), from: id(link.from), to: id(link.to) }))) });
        }
        catch (error) {
            return { kind: 'critical-path', outcome: 'invalid', message: error instanceof Error ? error.message : String(error) };
        }
    }
    return { kind: 'none', outcome: 'not-applicable' };
}

},
"profiles/src/analysis.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.decisionInputErrors = decisionInputErrors;
exports.matchPredicate = matchPredicate;
exports.matchGuard = matchGuard;
exports.analyzeDecision = analyzeDecision;
exports.evaluateDecision = evaluateDecision;
exports.evaluateFlatTrace = evaluateFlatTrace;
exports.calculateCriticalPath = calculateCriticalPath;
const schema_core_js_1 = require("profiles/src/schema-core.js");
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const equal = (a, b) => a === undefined || b === undefined ? a === b : (0, schema_core_js_1.stableStringify)(a) === (0, schema_core_js_1.stableStringify)(b);
function decisionInputErrors(domains, values) {
    const errors = Object.keys(values).filter(name => !domains.some(domain => domain.name === name)).map(name => 'Undeclared input: ' + name);
    for (const domain of domains) {
        const value = values[domain.name];
        const valid = value === undefined ? domain.optional : value === null ? domain.nullable : domain.type === 'boolean' ? typeof value === 'boolean' : domain.type === 'number' ? finite(value) && value >= (domain.min ?? -Infinity) && value <= (domain.max ?? Infinity) : domain.values?.some(candidate => equal(candidate, value));
        if (!valid)
            errors.push('Input is missing or outside its declared domain: ' + domain.name);
    }
    return errors;
}
function matchPredicate(value, predicate) {
    if (predicate === undefined)
        return true;
    if (!(0, schema_core_js_1.isRecord)(predicate))
        return equal(value, predicate);
    const op = predicate.op;
    if (op === 'missing')
        return value === undefined;
    if (op === 'null')
        return value === null;
    if (op === 'eq')
        return equal(value, predicate.value);
    if (op === 'ne')
        return !equal(value, predicate.value);
    if (op === 'exists')
        return (value !== undefined) === (predicate.value ?? true);
    if (op === 'in')
        return Array.isArray(predicate.values ?? predicate.value) && (predicate.values ?? predicate.value).some(v => equal(v, value));
    if (op === 'interval')
        return finite(value) && (predicate.min === undefined || finite(predicate.min) && (predicate.include_min === false ? value > predicate.min : value >= predicate.min)) && (predicate.max === undefined || finite(predicate.max) && (predicate.include_max === false ? value < predicate.max : value <= predicate.max));
    if (!finite(value) || !finite(predicate.value))
        return false;
    return op === 'lt' ? value < predicate.value : op === 'lte' ? value <= predicate.value : op === 'gt' ? value > predicate.value : op === 'gte' ? value >= predicate.value : false;
}
function matchGuard(values, guard) {
    if (guard === undefined || guard === true)
        return true;
    if (guard === false || !(0, schema_core_js_1.isRecord)(guard))
        return false;
    if (Array.isArray(guard.all))
        return guard.all.every(g => matchGuard(values, g));
    if (Array.isArray(guard.any))
        return guard.any.some(g => matchGuard(values, g));
    if (guard.not !== undefined)
        return !matchGuard(values, guard.not);
    if (typeof guard.field === 'string')
        return matchPredicate(values[guard.field], guard);
    return Object.entries(guard).every(([key, predicate]) => matchPredicate(values[key], predicate));
}
function predicateError(p, domain) {
    const inDomain = (value) => value === undefined ? domain.optional : value === null ? domain.nullable : domain.type === 'boolean' ? typeof value === 'boolean' : domain.type === 'number' ? finite(value) && value >= (domain.min ?? -Infinity) && value <= (domain.max ?? Infinity) : domain.values?.some(v => equal(v, value));
    if (!(0, schema_core_js_1.isRecord)(p) && !inDomain(p))
        return 'Predicate value is outside its input domain';
    if ((0, schema_core_js_1.isRecord)(p)) {
        if (!['eq', 'ne', 'lt', 'lte', 'gt', 'gte', 'in', 'interval', 'null', 'missing', 'exists'].includes(String(p.op)))
            return 'Unknown predicate';
        if (p.op === 'interval' && (domain.type !== 'number' || p.min !== undefined && !finite(p.min) || p.max !== undefined && !finite(p.max) || finite(p.min) && finite(p.max) && p.min > p.max))
            return 'Invalid interval predicate';
        if (p.op === 'in' && (!Array.isArray(p.values ?? p.value) || !(p.values ?? p.value).every(inDomain)))
            return 'Invalid membership predicate';
        if (p.op === 'eq' && !inDomain(p.value))
            return 'Equality value is outside its input domain';
        if (p.op === 'null' && !domain.nullable || p.op === 'missing' && !domain.optional)
            return 'Predicate asks for an undeclared null/missing state';
        if (['lt', 'lte', 'gt', 'gte'].includes(String(p.op)) && (domain.type !== 'number' || !finite(p.value)))
            return 'Ordered predicates require a numeric domain';
    }
    return undefined;
}
function analyzeDecision(domains, rules, options = {}) {
    const errors = [], overlaps = [], uncovered = [];
    const firstHitUnknown = { outcome: options.hitPolicy === 'first' ? 'unknown' : 'not-applicable', shadowed: null };
    const matched = new Set(), firstSelected = new Set();
    const budget = options.budget ?? 4096;
    if (!Number.isInteger(budget) || budget < 1 || budget > 50000)
        errors.push('Analysis budget must be an integer from 1 through 50000');
    if (!domains.length || domains.length > 8 || new Set(domains.map(d => d.name)).size !== domains.length)
        errors.push('Decision requires 1..8 uniquely named input domains');
    const cells = domains.map(domain => {
        let values;
        if (domain.type === 'boolean')
            values = [false, true];
        else if (domain.type === 'enum') {
            values = [...domain.values ?? []];
            if (!values.length || values.length > 30 || values.some(v => v === null || typeof v === 'object' || v === undefined) || new Set(values.map(schema_core_js_1.stableStringify)).size !== values.length)
                errors.push('Enum domains require 1..30 unique nonnull scalar values');
        }
        else {
            if (!finite(domain.min) || !finite(domain.max) || domain.min > domain.max) {
                errors.push('Numeric domains require a finite closed increasing interval');
                return [];
            }
            const boundaries = [domain.min, domain.max];
            for (const rule of rules) {
                const p = rule.inputs[domain.name];
                const boundaryValues = [];
                const predicateValues = (predicate) => {
                    if (!(0, schema_core_js_1.isRecord)(predicate)) {
                        if (predicate !== undefined)
                            boundaryValues.push(predicate);
                        return;
                    }
                    for (const candidate of [predicate.value, predicate.min, predicate.max, ...(Array.isArray(predicate.values) ? predicate.values : [])])
                        if (candidate !== undefined)
                            boundaryValues.push(...Array.isArray(candidate) ? candidate : [candidate]);
                };
                const collect = (g, depth = 0) => {
                    if (!(0, schema_core_js_1.isRecord)(g) || depth > 32)
                        return;
                    if (g.field === domain.name)
                        predicateValues(g);
                    else if (g.field === undefined && Object.hasOwn(g, domain.name))
                        predicateValues(g[domain.name]);
                    for (const child of [...Array.isArray(g.all) ? g.all : [], ...Array.isArray(g.any) ? g.any : [], ...(g.not === undefined ? [] : [g.not])])
                        collect(child, depth + 1);
                };
                predicateValues(p);
                collect(rule.guard);
                for (const value of boundaryValues)
                    if (finite(value) && value >= domain.min && value <= domain.max)
                        boundaries.push(value);
            }
            const points = [...new Set(boundaries)].sort((a, b) => a - b);
            values = points.flatMap((v, i) => i + 1 < points.length ? [v, v / 2 + points[i + 1] / 2] : [v]);
        }
        if (domain.nullable)
            values.push(null);
        if (domain.optional)
            values.push(undefined);
        return values;
    });
    let outputNames;
    for (const rule of rules) {
        const keys = Object.keys(rule.outputs).sort();
        if (!keys.length || keys.length > 20 || Object.values(rule.outputs).some(v => v !== null && (typeof v === 'object' || typeof v === 'number' && !finite(v))))
            errors.push('Rules require 1..20 finite scalar outputs');
        if (outputNames && !equal(keys, outputNames))
            errors.push('Every rule must supply the same output keys');
        outputNames = keys;
        const checkGuard = (guard, depth = 0) => {
            if (guard === undefined || typeof guard === 'boolean')
                return;
            if (depth > 32 || !(0, schema_core_js_1.isRecord)(guard)) {
                errors.push('Guard must use bounded typed predicates');
                return;
            }
            if (Array.isArray(guard.all) || Array.isArray(guard.any) || guard.not !== undefined) {
                for (const g of [...Array.isArray(guard.all) ? guard.all : [], ...Array.isArray(guard.any) ? guard.any : [], ...(guard.not === undefined ? [] : [guard.not])])
                    checkGuard(g, depth + 1);
                return;
            }
            if (typeof guard.field === 'string') {
                const domain = domains.find(d => d.name === guard.field);
                if (!domain)
                    errors.push('Guard names undeclared input');
                else {
                    const error = predicateError(guard, domain);
                    if (error)
                        errors.push(error);
                }
            }
            else
                for (const [name, predicate] of Object.entries(guard)) {
                    const domain = domains.find(d => d.name === name);
                    if (!domain)
                        errors.push('Guard names undeclared input');
                    else {
                        const error = predicateError(predicate, domain);
                        if (error)
                            errors.push(error);
                    }
                }
        };
        checkGuard(rule.guard);
        for (const [name, predicate] of Object.entries(rule.inputs)) {
            const domain = domains.find(d => d.name === name);
            if (!domain)
                errors.push('Predicate names undeclared input ' + name);
            else {
                const error = predicateError(predicate, domain);
                if (error)
                    errors.push(error + ' on ' + name);
            }
        }
    }
    if (errors.length)
        return { outcome: 'invalid', tested: 0, overlaps, uncovered, errors, firstHit: firstHitUnknown };
    if (options.coverage === 'none' && options.hitPolicy !== 'unique')
        return { outcome: 'valid', tested: 0, overlaps, uncovered, errors, firstHit: firstHitUnknown };
    const costOfGuard = (guard, depth = 0) => !(0, schema_core_js_1.isRecord)(guard) ? 1 : depth > 32 ? 50001 : 1 + Object.values(guard).reduce((cost, v) => cost + (Array.isArray(v) ? v.reduce((sum, g) => sum + costOfGuard(g, depth + 1), 0) : (0, schema_core_js_1.isRecord)(v) ? costOfGuard(v, depth + 1) : 1), 0);
    const cellCost = Math.max(1, rules.reduce((sum, rule) => sum + Object.keys(rule.inputs).length + costOfGuard(rule.guard), 0));
    let tested = 0, work = 0, exhausted = false;
    const walk = (i, row) => {
        if (exhausted)
            return;
        if (i < domains.length) {
            for (const value of cells[i]) {
                if (value === undefined)
                    delete row[domains[i].name];
                else
                    row[domains[i].name] = value;
                walk(i + 1, row);
                if (exhausted)
                    break;
            }
            return;
        }
        if (work + cellCost > budget) {
            exhausted = true;
            return;
        }
        tested++;
        work += cellCost;
        const matches = rules.filter(rule => Object.entries(rule.inputs).every(([name, predicate]) => matchPredicate(row[name], predicate)) && matchGuard(row, rule.guard));
        if (options.hitPolicy === 'first') {
            for (const rule of matches)
                matched.add(rule.id);
            if (matches[0])
                firstSelected.add(matches[0].id);
        }
        if (!matches.length && uncovered.length < 100)
            uncovered.push({ ...row });
        if (matches.length > 1 && overlaps.length < 100)
            overlaps.push(matches.map(rule => rule.id));
    };
    walk(0, {});
    const firstHit = options.hitPolicy === 'first' && !exhausted ? { outcome: 'complete', shadowed: rules.filter(rule => matched.has(rule.id) && !firstSelected.has(rule.id)).map(rule => rule.id) } : firstHitUnknown;
    return { outcome: exhausted ? 'budget_exceeded' : options.hitPolicy === 'unique' && overlaps.length || ['error', 'complete'].includes(options.coverage ?? '') && uncovered.length ? 'invalid' : 'valid', tested, overlaps, uncovered, errors, firstHit };
}
function evaluateDecision(rules, values, hitPolicy = 'unique') {
    const matches = rules.filter(rule => Object.entries(rule.inputs).every(([name, predicate]) => matchPredicate(values[name], predicate)) && matchGuard(values, rule.guard));
    const supported = ['unique', 'first', 'collect'].includes(hitPolicy);
    return { outcome: !supported ? 'unsupported-policy' : hitPolicy === 'unique' && matches.length > 1 ? 'ambiguous' : 'valid', hitPolicy, policyEvaluated: supported, matches: matches.map(r => r.id), outputs: supported ? (hitPolicy === 'first' ? matches.slice(0, 1) : matches).map(r => r.outputs) : [], valid: supported && (hitPolicy !== 'unique' || matches.length <= 1), ...(!supported ? { annotation: 'This policy is retained for table presentation and ordered matching; it has no local executable semantics in the bounded DDN contract.' } : {}) };
}
function evaluateFlatTrace(initial, transitions, events, budget = 4096, options = {}) {
    let state = initial, work = 0;
    const steps = [];
    const finish = (outcome) => ({ outcome, state, steps, actionsExecuted: false, ...(options.expectedFinalState === undefined ? {} : { expectedFinalState: options.expectedFinalState, expectedMatched: state === options.expectedFinalState }) });
    if (events.length > 1000 || !Number.isInteger(budget) || budget < 1 || budget > 50000)
        return finish('limit-exceeded');
    const start = transitions.filter(t => t.from === initial && !t.event && t.guard === undefined && !t.actions?.length);
    if (start.length === 1) {
        state = start[0].to;
        steps.push({ transition: start[0].id, state, actions: [] });
    }
    for (const input of events) {
        const values = input.values ?? {};
        if (options.domains && decisionInputErrors(options.domains, values).length)
            return finish('invalid-input');
        work += transitions.length;
        if (work > budget)
            return finish('budget_exceeded');
        const matched = transitions.filter(t => t.from === state && t.event === input.event && matchGuard(values, t.guard));
        if (matched.length !== 1)
            return finish(matched.length ? 'ambiguous' : 'unmatched');
        const next = matched[0];
        state = next.to;
        steps.push({ transition: next.id, state, actions: next.actions ?? [] });
    }
    return finish(options.expectedFinalState !== undefined && state !== options.expectedFinalState ? 'unexpected-final-state' : 'valid');
}
function calculateCriticalPath(tasks, links) {
    const byId = new Map(tasks.map(t => [t.id, t])), incoming = new Map(tasks.map(t => [t.id, []])), outgoing = new Map(tasks.map(t => [t.id, []]));
    if (byId.size !== tasks.length || tasks.some(t => !finite(t.duration) || t.duration < 0) || links.some(l => !byId.has(l.from) || !byId.has(l.to)))
        throw new Error('CPM requires unique tasks, finite nonnegative durations and resolved precedence endpoints');
    for (const l of links) {
        incoming.get(l.to).push(l.from);
        outgoing.get(l.from).push(l.to);
    }
    const degrees = new Map(tasks.map(t => [t.id, incoming.get(t.id).length])), order = tasks.filter(t => !degrees.get(t.id)).map(t => t.id);
    for (let i = 0; i < order.length; i++)
        for (const next of outgoing.get(order[i])) {
            degrees.set(next, degrees.get(next) - 1);
            if (!degrees.get(next))
                order.push(next);
        }
    if (order.length !== tasks.length)
        throw new Error('CPM precedence must be acyclic');
    const results = new Map();
    for (const id of order) {
        const es = Math.max(0, ...incoming.get(id).map(p => results.get(p).ef)), duration = byId.get(id).duration;
        results.set(id, { id, duration, es, ef: es + duration, ls: 0, lf: 0, slack: 0, critical: false });
    }
    const duration = Math.max(0, ...[...results.values()].map(t => t.ef));
    for (const id of [...order].reverse()) {
        const t = results.get(id), successors = outgoing.get(id);
        t.lf = successors.length ? Math.min(...successors.map(n => results.get(n).ls)) : duration;
        t.ls = t.lf - t.duration;
        t.slack = t.ls - t.es;
        t.critical = Math.abs(t.slack) < 1e-10;
    }
    return { duration, tasks: tasks.map(t => results.get(t.id)), criticalEdges: links.filter(l => results.get(l.from).critical && results.get(l.to).critical && Math.abs(results.get(l.from).ef - results.get(l.to).es) < 1e-10).map(l => l.id) };
}

},
"profiles/src/projection-rules.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.chartOptionErrors = chartOptionErrors;
exports.projectionRows = projectionRows;
exports.projectionDiagnostics = projectionDiagnostics;
const core_js_1 = require("profiles/src/core.js");
const schema_core_js_1 = require("profiles/src/schema-core.js");
const semantic_js_1 = require("profiles/src/semantic.js");
const obj = (v) => (0, schema_core_js_1.isRecord)(v) ? v : {};
const arr = (v) => Array.isArray(v) ? v : [];
const str = (v) => typeof v === 'string' ? v : '';
const num = (v) => typeof v === 'number' && Number.isFinite(v);
const key = (r) => r.file + '\0' + r.ref.id;
const same = (a, b) => a === undefined || b === undefined ? a === b : (0, schema_core_js_1.stableStringify)(a) === (0, schema_core_js_1.stableStringify)(b);
function chartOptionErrors(profileId, authored) {
    const specialized = profileId.slice(6).split('@')[0], transform = str(authored.transform), operation = ['histogram', 'pareto', 'waterfall', 'boxplot'].includes(transform), mark = str(authored.mark) || (operation ? transform === 'boxplot' ? 'boxplot' : 'bar' : ['basic', 'quality'].includes(specialized) ? 'bar' : specialized), layers = arr(authored.layers).map(obj);
    const errors = [];
    const common = ['width', 'height', 'records', 'mark', 'x', 'y', 'x_type', 'unit', 'aggregate', 'filter', 'order', 'missing'];
    const specific = { bar: ['series', 'series_missing', 'arrangement', 'baseline', 'transform', 'layers', 'error'], line: ['series', 'series_missing', 'arrangement', 'transform', 'layers', 'error', 'trend'], area: ['series', 'series_missing', 'arrangement', 'baseline', 'transform', 'layers', 'error'], point: ['series', 'series_missing', 'transform', 'layers', 'size', 'error', 'trend'], pie: [], donut: ['inner_radius'], radar: ['series'], funnel: [], gauge: ['target'], candlestick: ['open', 'high', 'low', 'close'], histogram: ['bin_count', 'bins', 'normalize', 'outside', 'step'], density: [], qq: [], quantiledot: [], dotplot: [], beeswarm: [], boxplot: ['quartiles', 'whiskers'], violin: [], topk: ['k', 'others'], treemap: ['depth'], tidytree: ['depth'], radialtree: ['depth'], circlepack: ['depth'], sunburst: ['depth'], packedbubble: ['depth'], heatmap: ['series'], densityheatmap: ['bin_count'], calendar: ['iso'], parallelcoords: ['series'], wordcloud: [], sankey: ['target'], arc: ['target'], force: ['target'], edgebundle: ['target'] };
    const operationFields = { histogram: ['bins', 'normalize', 'outside'], pareto: [], waterfall: ['step', 'baseline'], boxplot: ['quartiles', 'whiskers'] };
    if (!Object.hasOwn(specific, mark))
        errors.push('No chart operation is registered for ' + mark);
    const extrudable = ['bar', 'area', 'pie', 'donut', 'treemap'].includes(mark);
    const allowed = new Set(operation ? [...common.filter(name => name !== 'aggregate'), 'transform', ...operationFields[transform]] : [...common, ...specific[mark] ?? [], ...(extrudable ? ['iso', 'depth'] : []), ...(layers.some(layer => layer.mark === 'point') ? ['size'] : []), ...(layers.some(layer => ['line', 'point'].includes(str(layer.mark))) ? ['trend'] : [])]);
    if (authored.iso === true && extrudable && authored.depth !== undefined && (typeof authored.depth === 'string' ? !authored.depth.trim() : !num(authored.depth) || authored.depth < 0 || authored.depth > 2000))
        errors.push('Chart extrusion depth must be a channel name or a finite number between 0 and 2000');
    for (const name of Object.keys(authored))
        if (!allowed.has(name))
            errors.push('Option ' + name + ' does not apply to ' + mark);
    if (!operation && mark === 'boxplot' && (authored.quartiles !== undefined && authored.quartiles !== 'linear' || authored.whiskers !== undefined && authored.whiskers !== 'iqr' && authored.whiskers !== 1.5))
        errors.push('Direct boxplots use linear R7 quartiles and Tukey 1.5-IQR whiskers');
    return errors;
}
function projectionRows(view, records) {
    const { resolve } = (0, semantic_js_1.profileSelection)(view, records), options = obj((0, schema_core_js_1.getPath)(view.record, 'projection.options'));
    const refs = options.records === undefined ? [] : Array.isArray(options.records) ? options.records : [options.records];
    const rows = [];
    for (const ref of refs) {
        const source = resolve(ref);
        if (!source)
            continue;
        const data = source.owner === 'data' ? source.record : source.record.data === undefined ? undefined : obj(source.record.data);
        if (data) {
            const columns = arr(data.columns).map(v => str(obj(v).id));
            for (const row of arr(data.rows))
                rows.push({ source: source.ref, values: Array.isArray(row) ? Object.fromEntries(columns.map((name, i) => [name, row[i] ?? null])) : obj(row) });
        }
        else
            rows.push({ source: source.ref, values: { ...source.record, ...obj((0, schema_core_js_1.getPath)(source.record, 'metadata.x_record')) } });
    }
    return rows.filter(row => arr(options.filter).every(filter => { const f = obj(filter), value = (0, schema_core_js_1.getPath)(row.values, str(f.key)); return f.op === 'in' ? arr(f.value).some(v => same(value, v)) : same(value, f.value); }));
}
function projectionDiagnostics(view, records, review) {
    const profile = (0, core_js_1.getProfile)(str(view.record.profile));
    if (!profile)
        return [];
    const result = [], options = {};
    for (const [path, value] of Object.entries(profile.defaults))
        if (path.startsWith('projection.options.') && value.kind === 'literal' && value.value !== undefined)
            options[path.slice(19)] = value.value;
    Object.assign(options, obj((0, schema_core_js_1.getPath)(view.record, 'projection.options')));
    const { resolve, nodes, edges, links, selected } = (0, semantic_js_1.profileSelection)(view, records);
    const issue = (code, message, target = view.ref, severity = 'error') => result.push({ code, severity, message, target, rule: 'ddn.profile.' + profile.id });
    const incomplete = (message) => {
        if (review)
            issue('DDN-PROJECTION-INCOMPLETE', message, view.ref, 'warning');
    };
    const binding = (row, name, fallback) => (0, schema_core_js_1.getPath)(row.values, str(options[name]) || fallback || name);
    const rows = projectionRows(view, records);
    const geoMark = str(options.mark) || (profile.id === 'geo.outline@1' ? 'outline' : profile.id === 'geo.symbols@1' ? 'symbol' : 'choropleth');
    if (['chart', 'timeline', 'geo'].includes(profile.projection)) {
        if (options.records === undefined && !(profile.projection === 'geo' && geoMark === 'outline'))
            incomplete('Projection needs an explicit records binding');
        const refs = options.records === undefined ? [] : Array.isArray(options.records) ? options.records : [options.records];
        for (const ref of refs)
            if (!resolve(ref))
                issue('DDN-PROJECTION-REFERENCE', 'Projection input does not resolve');
        if (refs.length && !rows.length && arr(options.filter).length && projectionRows({ ...view, record: { ...view.record, projection: { options: { ...options, filter: [] } } } }, records).length)
            issue('DDN-PROJECTION-FILTER', 'Filtering nonempty input to no records is not a completed projection');
    }
    if (profile.projection === 'chart') {
        if (options.iso === true && typeof options.depth === 'string')
            for (const row of rows) {
                const depth = (0, schema_core_js_1.getPath)(row.values, options.depth);
                if (!num(depth) || depth < 0 || depth > 2000)
                    issue('DDN-CHART-DEPTH', 'Every extrusion depth must be finite and between 0 and 2000', row.source);
            }
        for (const message of chartOptionErrors(profile.id, obj((0, schema_core_js_1.getPath)(view.record, 'projection.options'))))
            issue('DDN-CHART-OPTION', message);
        const operation = str(options.transform);
        if (['histogram', 'pareto', 'waterfall', 'boxplot'].includes(operation)) {
            const authored = obj((0, schema_core_js_1.getPath)(view.record, 'projection.options')), mark = str(authored.mark) || (operation === 'boxplot' ? 'boxplot' : 'bar');
            if (mark !== (operation === 'boxplot' ? 'boxplot' : 'bar'))
                issue('DDN-TRANSFORM-MARK', 'Transform ' + operation + ' requires ' + (operation === 'boxplot' ? 'boxplot' : 'bar') + ' marks');
            if (!str(options.y) || operation !== 'histogram' && !str(options.x)) {
                incomplete('Transform requires explicit measured y and applicable x channel bindings');
                return result;
            }
            const values = [];
            for (const row of rows) {
                const x = binding(row, 'x'), y = binding(row, 'y');
                if ((y === null || y === undefined || operation !== 'histogram' && (x === null || x === undefined)) && options.missing === 'skip')
                    continue;
                if (!num(y) || operation !== 'histogram' && typeof x !== 'string' && !num(x)) {
                    issue('DDN-TRANSFORM-DATA', 'Transform channels require finite measurements and scalar categories', row.source);
                    continue;
                }
                values.push({ x, y, row });
            }
            if (!values.length)
                incomplete('Transform requires nonempty measurements');
            if (operation === 'histogram') {
                const bounds = arr(options.bins);
                if (!bounds.length)
                    incomplete('Histogram transform requires explicit bin boundaries');
                else if (bounds.length < 2 || bounds.length > 101 || bounds.some((bound, index) => { const previous = bounds[index - 1]; return !num(bound) || index > 0 && num(previous) && bound <= previous; }))
                    issue('DDN-TRANSFORM-BINS', 'Histogram transform requires 2..101 strictly increasing finite boundaries');
                else {
                    const low = bounds[0], high = bounds.at(-1), outside = values.filter(value => value.y < low || value.y > high);
                    if ((options.outside ?? 'error') === 'error' && outside.length)
                        issue('DDN-HISTOGRAM-OUTSIDE', 'Samples lie outside the declared transform bins');
                    if (options.outside === 'drop' && outside.length === values.length && values.length)
                        issue('DDN-HISTOGRAM-EMPTY', 'Histogram bounds exclude every sample');
                }
            }
            if (operation === 'pareto' && values.length && (values.some(value => value.y < 0) || !num(values.reduce((sum, value) => sum + value.y, 0)) || values.reduce((sum, value) => sum + value.y, 0) <= 0))
                issue('DDN-PARETO-TOTAL', 'Pareto requires nonnegative measurements with a positive finite total');
            if (operation === 'waterfall') {
                if (!str(options.step))
                    incomplete('Waterfall requires a step field binding');
                let total = num(options.baseline) ? options.baseline : 0;
                for (const value of values) {
                    const step = (0, schema_core_js_1.getPath)(value.row.values, str(options.step));
                    if (step === 'delta')
                        total += value.y;
                    else if (step === 'subtotal' || step === 'total') {
                        if (Math.abs(value.y - total) > 1e-10 * Math.max(1, Math.abs(total), Math.abs(value.y)))
                            issue('DDN-WATERFALL-TOTAL', 'Declared subtotal/total does not match the running total', value.row.source);
                    }
                    else if (options.step !== undefined)
                        issue('DDN-WATERFALL-STEP', 'Step must be delta, subtotal or total', value.row.source);
                    if (!num(total))
                        issue('DDN-WATERFALL-RANGE', 'Running total exceeds the finite numeric range', value.row.source);
                }
            }
            if (operation === 'boxplot') {
                if (options.quartiles !== undefined && options.quartiles !== 'linear' || options.whiskers !== undefined && !['iqr', 'minmax'].includes(str(options.whiskers)) && options.whiskers !== 1.5)
                    issue('DDN-BOXPLOT-METHOD', 'Boxplot transform uses linear R7 quartiles and IQR or minmax whiskers');
                if (new Set(values.map(value => (0, schema_core_js_1.stableStringify)(value.x ?? null))).size > 40)
                    issue('DDN-CHART-CATEGORY-LIMIT', 'Boxplot transform permits at most 40 categories');
            }
            return result;
        }
        const mark = str(options.mark) || (profile.id === 'chart.basic@1' || profile.id === 'chart.quality@1' ? 'bar' : profile.id.slice(6).split('@')[0]);
        const samples = ['histogram', 'density', 'qq', 'quantiledot'].includes(mark), linksMark = ['sankey', 'arc', 'force', 'edgebundle'].includes(mark), hierarchy = ['treemap', 'tidytree', 'radialtree', 'circlepack', 'sunburst', 'packedbubble'].includes(mark);
        if (!rows.length && !['bar', 'line', 'area', 'point'].includes(mark) && options.records !== undefined)
            incomplete(mark + ' requires records');
        if (str(options.aggregate) && options.aggregate !== 'none' && !['bar', 'pie', 'donut', 'topk'].includes(mark))
            issue('DDN-CHART-AGGREGATE', 'Aggregation is not available for ' + mark);
        if (options.aggregate === 'count' && options.unit !== undefined)
            issue('DDN-CHART-COUNT-UNIT', 'Count has no physical unit');
        if (samples && (options.y !== undefined || options.series !== undefined))
            issue('DDN-CHART-SAMPLE-CHANNEL', 'Raw-sample marks do not accept y or series');
        if (mark === 'densityheatmap' && options.x_type !== 'number')
            issue('DDN-CHART-XTYPE', mark + ' requires numeric x');
        if (['bar', 'pie', 'donut', 'radar', 'funnel'].includes(mark) && options.x_type !== undefined && options.x_type !== 'category')
            issue('DDN-CHART-XTYPE', mark + ' requires categorical x');
        if (['bar', 'area'].includes(mark) && options.baseline !== undefined && options.baseline !== 0)
            issue('DDN-CHART-BASELINE', 'Area-encoded marks require a zero baseline');
        if (samples && rows.length < 2)
            incomplete(mark + ' requires at least two samples');
        if (mark === 'boxplot' && (options.quartiles !== undefined && options.quartiles !== 'linear' || options.whiskers !== undefined && options.whiskers !== 'iqr' && options.whiskers !== 1.5))
            issue('DDN-BOXPLOT-METHOD', 'Direct boxplots use linear R7 quartiles and Tukey 1.5-IQR whiskers');
        const nonnegative = ['pie', 'donut', 'radar', 'funnel', 'treemap', 'tidytree', 'radialtree', 'circlepack', 'sunburst', 'packedbubble'].includes(mark);
        const values = [], categories = new Set(), series = new Set(), pairs = new Set(), dates = new Set(), nodeNames = new Set();
        const groups = new Map(), graph = new Map();
        for (const row of rows) {
            const x = binding(row, 'x'), y = binding(row, samples ? 'x' : 'y'), s = binding(row, 'series');
            const missing = x === undefined || x === null || mark !== 'candlestick' && (y === undefined || y === null);
            if (missing) {
                if ((options.missing ?? 'error') === 'error')
                    issue('DDN-CHART-MISSING', 'Chart input has a missing channel value', row.source);
                else
                    continue;
            }
            if (mark !== 'candlestick' && !num(y))
                issue('DDN-CHART-NUMBER', 'Chart measurements must be finite numbers; strings are not coerced', row.source);
            if (num(y)) {
                values.push(y);
                if (nonnegative && y < 0 || (linksMark || mark === 'wordcloud') && y <= 0)
                    issue('DDN-CHART-RANGE', mark + ' has an out-of-range value', row.source);
            }
            if ((samples || options.x_type === 'number') && !num(x))
                issue('DDN-CHART-NUMBER', 'Numeric x must be finite', row.source);
            if (options.x_type === 'date' && (typeof x !== 'string' || !validDate(x)))
                issue('DDN-CHART-DATE', 'Date axes require ISO dates or zoned instants', row.source);
            if (options.unit !== undefined && row.values.unit !== undefined && options.unit !== row.values.unit)
                issue('DDN-CHART-UNIT', 'Record and projection units disagree', row.source);
            const category = (0, schema_core_js_1.stableStringify)(x ?? null), seriesName = (0, schema_core_js_1.stableStringify)(s ?? null), pair = category + '\0' + seriesName;
            categories.add(category);
            series.add(seriesName);
            if (['heatmap', 'parallelcoords'].includes(mark) && pairs.has(pair))
                issue('DDN-CHART-DUPLICATE', 'Each category/series pair requires one measurement', row.source);
            pairs.add(pair);
            const group = groups.get(category) ?? [];
            if (num(y))
                group.push(y);
            groups.set(category, group);
            if (mark === 'calendar') {
                const date = typeof x === 'string' && validDate(x) ? new Date(x).toISOString().slice(0, 10) : '';
                if (!date || dates.has(date))
                    issue('DDN-CALENDAR-DAY', 'Calendar requires one value per valid UTC day', row.source);
                dates.add(date);
            }
            if (mark === 'candlestick') {
                const [o, h, l, c] = ['open', 'high', 'low', 'close'].map(name => binding(row, name));
                if (![o, h, l, c].every(num) || o > h || o < l || c > h || c < l || h < l)
                    issue('DDN-CANDLESTICK-OHLC', 'OHLC must be finite with open/close inside low..high', row.source);
            }
            if (hierarchy && (typeof x !== 'string' || !x || x.split('.').some(part => !part)))
                issue('DDN-HIERARCHY-PATH', 'Hierarchy paths need nonempty dotted segments', row.source);
            if (linksMark) {
                const target = (0, schema_core_js_1.getPath)(row.values, str(options.target) || 'target');
                if (options.target !== undefined && typeof options.target !== 'string' || typeof x !== 'string' || !x || typeof target !== 'string' || !target || x === target)
                    issue('DDN-CHART-LINK', 'Links require distinct named endpoints and a text target field binding', row.source);
                else {
                    nodeNames.add(x);
                    nodeNames.add(target);
                    graph.set(x, [...graph.get(x) ?? [], target]);
                    if (mark === 'edgebundle' && Math.max(x.split('.').length, target.split('.').length) > 3)
                        issue('DDN-EDGEBUNDLE-DEPTH', 'Edge bundle paths permit at most three levels', row.source);
                }
            }
            if (options.transform === 'log' && num(y) && y <= 0 || options.transform === 'sqrt' && num(y) && y < 0)
                issue('DDN-CHART-TRANSFORM', 'Transform input is outside its numeric domain', row.source);
            if (options.error !== undefined) {
                const error = obj(options.error), low = (0, schema_core_js_1.getPath)(row.values, str(error.low)), high = (0, schema_core_js_1.getPath)(row.values, str(error.high));
                if (error.low !== undefined && (!num(low) || num(y) && low > y) || error.high !== undefined && (!num(high) || num(y) && high < y))
                    issue('DDN-CHART-ERROR-BOUNDS', 'Error interval must bracket its measured value', row.source);
            }
        }
        if (rows.length && ['pie', 'donut'].includes(mark) && values.reduce((a, b) => a + b, 0) <= 0)
            issue('DDN-CHART-TOTAL', 'Arc shares need a positive total');
        if (mark === 'gauge') {
            if (!rows.length)
                incomplete('Gauge requires one value');
            if (rows.length > 1 || values.some(v => v < 0 || v > 100) || options.target !== undefined && (!num(options.target) || options.target < 0 || options.target > 100))
                issue('DDN-GAUGE-RANGE', 'Gauge requires one value and optional target in 0..100');
        }
        if (mark === 'density' && values.length > 1 && new Set(values).size < 2)
            issue('DDN-DENSITY-UNKNOWN', 'Zero-variance data has no defined density estimate', view.ref, 'warning');
        if (['boxplot', 'violin'].includes(mark) && categories.size > 40)
            issue('DDN-CHART-CATEGORY-LIMIT', 'Distribution plots allow at most 40 categories');
        if (mark === 'violin' && [...groups.values()].some(v => v.length < 2 || new Set(v).size < 2))
            issue('DDN-VIOLIN-UNKNOWN', 'Each violin needs at least two nonidentical observations', view.ref, 'warning');
        if (mark === 'radar' && categories.size < 3)
            incomplete('Radar needs at least three categories');
        if (mark === 'funnel' && categories.size < 2)
            incomplete('Funnel requires at least two stages');
        if (mark === 'qq' && values.length > 1 && new Set(values).size < 2)
            issue('DDN-QQ-UNKNOWN', 'Zero-variance samples have no defined normal reference comparison', view.ref, 'warning');
        if (mark === 'densityheatmap' && rows.length && (categories.size < 2 || new Set(values).size < 2))
            issue('DDN-DENSITYHEATMAP-UNKNOWN', 'Density heatmap requires nonzero range on both axes', view.ref, 'warning');
        if (hierarchy) {
            const paths = rows.map(row => str(binding(row, 'x')));
            if (paths.some(path => path.split('.').length > 3))
                issue('DDN-HIERARCHY-DEPTH', 'Hierarchy paths permit at most three levels');
            if (new Set(paths).size !== paths.length || paths.some(path => paths.some(other => other.startsWith(path + '.'))))
                issue('DDN-HIERARCHY-LEAF', 'Hierarchy input requires unique leaf paths; an input leaf cannot also be a parent');
        }
        if (mark === 'parallelcoords' && ([...groups.values()].some(values => new Set(values).size < 2) || pairs.size < categories.size * series.size))
            issue('DDN-PARALLEL-UNKNOWN', 'Constant or missing axes are unknown and display at mid-height', view.ref, 'warning');
        if (options.series !== undefined && (mark === 'radar' || options.series_missing === 'error' || ['stack', 'percent'].includes(str(options.arrangement)) && options.series_missing !== 'zero') && pairs.size < categories.size * series.size)
            issue('DDN-CHART-SERIES-INCOMPLETE', 'Each series requires a measurement at every category or an explicitly supported zero fill');
        if (mark === 'heatmap' && (categories.size > 60 || series.size > 60))
            issue('DDN-HEATMAP-LIMIT', 'Heatmap is bounded to 60 by 60');
        if (mark === 'parallelcoords') {
            if (categories.size < 2)
                incomplete('Parallel coordinates require at least two axes');
            if (categories.size > 24)
                issue('DDN-PARALLEL-AXES', 'Parallel coordinates permit at most 24 axes');
        }
        if (mark === 'wordcloud' && (rows.length > 120 || categories.size !== rows.length))
            issue('DDN-WORDCLOUD-LIMIT', 'Word cloud permits at most 120 unique words');
        if (linksMark && (nodeNames.size > 200 || rows.length > (mark === 'edgebundle' ? 500 : 1000)))
            issue('DDN-LINK-CHART-LIMIT', 'Link chart exceeds its bounded nodes/links');
        if (mark === 'sankey') {
            const visited = new Set(), active = new Set();
            const visit = (n) => {
                if (active.has(n))
                    return false;
                if (visited.has(n))
                    return true;
                active.add(n);
                for (const child of graph.get(n) ?? [])
                    if (!visit(child))
                        return false;
                active.delete(n);
                visited.add(n);
                return true;
            };
            if ([...nodeNames].some(n => !visit(n)))
                issue('DDN-SANKEY-CYCLE', 'Sankey flows must form a DAG');
        }
        if (['histogram', 'densityheatmap'].includes(mark) && options.bin_count !== undefined && options.bin_count !== 'auto' && (!Number.isInteger(options.bin_count) || options.bin_count < 2 || options.bin_count > (mark === 'histogram' ? 100 : 60)))
            issue('DDN-CHART-BINS', 'Bin count is outside the mark-specific bound');
        if (mark === 'topk' && options.k !== undefined && (!Number.isInteger(options.k) || options.k < 1 || options.k > 100))
            issue('DDN-TOPK-BOUND', 'Top-k requires k in 1..100');
        if (profile.id === 'chart.quality@1' && (series.size > 20 || pairs.size > 200))
            issue('DDN-QUALITY-LIMIT', 'Quality chart is bounded to 20 series and 200 coordinates');
        if (options.arrangement === 'percent' && (values.some(v => v < 0) || [...groups.values()].some(v => v.reduce((a, b) => a + b, 0) <= 0)))
            issue('DDN-PERCENT-TOTAL', 'Percent arrangement requires nonnegative values and positive category totals');
        const layers = arr(options.layers).map(obj);
        if (layers.length && (options.transform !== undefined && options.transform !== 'identity' || layers.some(layer => !['bar', 'line', 'area', 'point'].includes(str(layer.mark) || mark))))
            issue('DDN-CHART-LAYERS', 'Layers require identity operation and ordinary cartesian marks');
        if (layers.length && options.series !== undefined && series.size && layers.length !== series.size)
            issue('DDN-CHART-LAYERS', 'Declare one layer per series in series order');
        for (const layer of layers)
            for (const row of rows) {
                const value = (0, schema_core_js_1.getPath)(row.values, str(layer.y) || str(options.y));
                if (!num(value))
                    issue('DDN-CHART-LAYER-DATA', 'Each layer measurement must be finite', row.source);
            }
        if (mark === 'histogram' && options.bins !== undefined) {
            const bins = obj(options.bins), count = bins.count ?? options.bin_count, min = bins.min, max = bins.max, step = bins.step;
            if (count !== undefined && count !== 'auto' && (!Number.isInteger(count) || count < 2 || count > 100) || min !== undefined && !num(min) || max !== undefined && !num(max) || num(min) && num(max) && min >= max || step !== undefined && (!num(step) || step <= 0))
                issue('DDN-HISTOGRAM-BINS', 'Histogram bins require increasing finite bounds, positive step, and 2..100 bins');
            if ((options.outside ?? 'error') === 'error' && values.some(value => num(min) && value < min || num(max) && value > max))
                issue('DDN-HISTOGRAM-OUTSIDE', 'Sample lies outside the explicitly declared histogram bounds');
        }
        if (mark === 'histogram') {
            if (Array.isArray(options.bins))
                issue('DDN-HISTOGRAM-BINS', 'Explicit boundary arrays require the histogram transform');
            const bins = obj(options.bins), step = options.step ?? bins.step, count = typeof options.bins === 'number' ? options.bins : bins.count ?? options.bin_count;
            if (typeof options.bins === 'number' && (!Number.isInteger(options.bins) || options.bins < 2 || options.bins > 100))
                issue('DDN-HISTOGRAM-BINS', 'Histogram bin count is bounded to 2..100');
            if (step !== undefined) {
                if (!num(step) || step <= 0)
                    issue('DDN-HISTOGRAM-BINS', 'Direct histogram step must be a positive number');
                else if (values.length) {
                    let low = num(bins.min) ? bins.min : Math.min(...values), high = num(bins.max) ? bins.max : Math.max(...values);
                    if (low === high && bins.min === undefined && bins.max === undefined) {
                        low -= .5;
                        high += .5;
                    }
                    const exact = high / step - low / step;
                    if (!num(exact) || Math.abs(exact - Math.round(exact)) > 1e-10 || exact < 2 || exact > 100 || num(count) && count !== Math.round(exact))
                        issue('DDN-HISTOGRAM-BINS', 'Step must divide the domain into 2..100 bins and agree with explicit count');
                }
            }
        }
    }
    if (profile.projection === 'matrix') {
        const rowRefs = arr(options.rows), columnRefs = arr(options.columns), rowItems = rowRefs.map(r => resolve(r)), columnItems = columnRefs.map(r => resolve(r));
        if (review && (!rowRefs.length || !columnRefs.length || !str(options.relation)))
            incomplete('Matrix needs explicit rows, columns and relation role');
        if (rowRefs.length * columnRefs.length > 5000 || columnRefs.length > 40)
            issue('DDN-MATRIX-SIZE', 'Matrix is bounded to 5000 cells and 40 columns');
        if (rowItems.some(r => !r) || columnItems.some(r => !r))
            issue('DDN-MATRIX-REFERENCE', 'Matrix axes must resolve');
        if (new Set(rowItems.filter((r) => !!r).map(key)).size !== rowRefs.length || new Set(columnItems.filter((r) => !!r).map(key)).size !== columnRefs.length)
            issue('DDN-MATRIX-AXIS', 'Matrix axes must be unique');
        const cells = new Map(), rowCodes = new Map(), stories = new Set();
        for (const link of links.filter(l => l.item.record.role === options.relation)) {
            if (!rowItems.includes(link.from) || !columnItems.includes(link.to))
                continue;
            const id = key(link.from) + '\0' + key(link.to), existing = cells.get(id) ?? [];
            cells.set(id, [...existing, link]);
            const value = options.value ? (0, schema_core_js_1.getPath)(link.item.record, str(options.value)) : (0, schema_core_js_1.getPath)(link.item.record, 'metadata.x_assignment.code');
            if (profile.id === 'matrix.raci@1' && !['R', 'A', 'C', 'I'].includes(str(value)))
                issue('DDN-RACI-CODE', 'RACI codes must be R, A, C or I', link.item.ref);
            if (profile.id === 'matrix.crud@1' && (!/^[CRUD]+$/.test(str(value)) || new Set(str(value)).size !== str(value).length))
                issue('DDN-CRUD-CODE', 'CRUD codes require unique C/R/U/D letters', link.item.ref);
            rowCodes.set(key(link.from), [...rowCodes.get(key(link.from)) ?? [], str(value)]);
            if (profile.id === 'matrix.storymap@1') {
                const task = resolve((0, schema_core_js_1.getPath)(link.item.record, 'metadata.x_story.task'), link.item);
                if (!task || task.record.role !== 'analysis.task' || !selected.has(key(task)))
                    issue('DDN-STORYMAP-TASK', 'Story cell must reference a selected task', link.item.ref);
                else if (stories.has(key(task)))
                    issue('DDN-STORYMAP-DUPLICATE', 'A story can appear in only one cell', link.item.ref);
                else
                    stories.add(key(task));
            }
        }
        for (const cell of cells.values())
            if (cell.length > 1 && (options.duplicates !== 'join' || ['matrix.raci@1', 'matrix.crud@1', 'matrix.heatmap@1'].includes(profile.id)))
                issue('DDN-MATRIX-DUPLICATE', 'Duplicate cell assignment is not allowed', cell[0].item.ref);
        if (profile.id === 'matrix.raci@1' && review)
            for (const row of rowItems)
                if (row) {
                    const codes = rowCodes.get(key(row)) ?? [];
                    if (codes.filter(c => c === 'A').length !== 1 || !codes.includes('R'))
                        issue('DDN-RACI-ACCOUNTABILITY', 'Every completed row requires exactly one A and at least one R', row.ref);
                }
        const axes = { 'matrix.bcg@1': ['growth', ['high', 'low'], 'share', ['high', 'low']], 'matrix.ansoff@1': ['market', ['existing', 'new'], 'product', ['existing', 'new']], 'matrix.tows@1': ['internal', ['strength', 'weakness'], 'external', ['opportunity', 'threat']] };
        if (axes[profile.id]) {
            const [ra, rv, ca, cv] = axes[profile.id];
            if (rowItems.length < 2 || columnItems.length < 2)
                incomplete('Strategy matrix requires two rows and two columns');
            if (rowItems.length > 2 || columnItems.length > 2)
                issue('DDN-STRATEGY-AXES', 'Strategy matrix permits only two rows and two columns');
            for (const [items, axis, values] of [[rowItems, ra, rv], [columnItems, ca, cv]]) {
                const levels = items.map(n => n && obj((0, schema_core_js_1.getPath)(n.record, 'metadata.x_category')));
                if (levels.some(v => !v || v.axis === undefined || v.level === undefined))
                    incomplete('Strategy matrix categories need axis and level');
                if (levels.some(v => v && (v.axis !== undefined && v.axis !== axis || v.level !== undefined && !values.includes(str(v.level)))) || levels.length === 2 && levels.every(v => v && v.level !== undefined) && new Set(levels.map(v => v && v.level)).size !== 2)
                    issue('DDN-STRATEGY-CATEGORY', 'Strategy matrix categories do not match its declared axes');
            }
        }
        if (profile.id === 'matrix.heatmap@1') {
            const encoding = obj(options.encoding), domain = obj(encoding.domain), range = obj(encoding.range), mode = str(encoding.mode) || 'numeric';
            const values = [...cells.values()].flatMap(cell => cell.map(link => options.value ? (0, schema_core_js_1.getPath)(link.item.record, str(options.value)) : (0, schema_core_js_1.getPath)(link.item.record, 'metadata.x_assignment.code'))).filter(value => value !== undefined && value !== null);
            if (!['numeric', 'categorical', 'threshold'].includes(mode))
                issue('DDN-MATRIX-ENCODING', 'Heatmap mode must be numeric, categorical or threshold');
            if (mode === 'numeric' || mode === 'threshold') {
                if (values.some(value => !num(value)))
                    issue('DDN-MATRIX-VALUE', 'Numeric heatmap values must be finite numbers');
                if (encoding.domain !== undefined && (!num(domain.min) || !num(domain.max) || domain.min >= domain.max))
                    issue('DDN-MATRIX-DOMAIN', 'Explicit numeric domains require finite increasing bounds');
                const minimum = domain.min, maximum = domain.max;
                if (num(minimum) && num(maximum) && values.some(value => num(value) && (value < minimum || value > maximum)))
                    issue('DDN-MATRIX-VALUE', 'Encoded values must fit the explicit numeric domain');
            }
            const labels = arr(encoding.labels), boundaries = arr(encoding.boundaries);
            if (encoding.scale !== undefined && !['blue', 'diverging', 'linear'].includes(str(encoding.scale)))
                issue('DDN-MATRIX-SCALE', 'Heatmap scale must be blue, diverging or linear');
            if (mode === 'categorical' && (values.some(value => typeof value === 'object') || new Set(values.map(value => (0, schema_core_js_1.stableStringify)(value))).size > 12 || labels.length && values.some(value => !labels.some(label => same(value, label)))))
                issue('DDN-MATRIX-CATEGORIES', 'Categorical heatmaps require 1..12 scalar labels and values within their declared domain');
            if (mode === 'threshold') {
                if (encoding.boundaries !== undefined) {
                    if (boundaries.length < 2 || boundaries.length > 13 || boundaries.some((value, index) => { const previous = boundaries[index - 1]; return !num(value) || index > 0 && num(previous) && value <= previous; }))
                        issue('DDN-MATRIX-THRESHOLD', 'Band boundaries must contain 2..13 strictly increasing finite values');
                    else {
                        const first = boundaries[0], last = boundaries.at(-1);
                        if (values.some(value => num(value) && (value < first || value > last)))
                            issue('DDN-MATRIX-VALUE', 'Band values must fit the explicit boundary domain');
                    }
                }
                else if (!num(range.min) || !num(range.max) || range.min >= range.max)
                    issue('DDN-MATRIX-THRESHOLD', 'Threshold heatmaps require increasing range bounds or explicit boundaries');
            }
        }
    }
    if (profile.projection === 'panels') {
        const columns = typeof options.columns === 'number' ? options.columns : 1, panels = arr(options.panels), occupied = new Set(), ids = new Set();
        if (!Number.isInteger(columns) || columns < 1 || columns > 12 || panels.length > 80)
            issue('DDN-PANELS-LIMIT', 'Panel grid permits 1..12 columns and at most 80 panels');
        if (!panels.length)
            incomplete('Panel view needs at least one panel');
        const layouts = [];
        for (const [index, raw] of panels.entries()) {
            const inclusion = obj(raw), target = resolve(inclusion.target);
            if (!target) {
                issue('DDN-PANEL-TARGET', 'Panel target must resolve');
                continue;
            }
            const data = obj((0, schema_core_js_1.getPath)(target.record, 'metadata.x_record')), placement = { ...data, ...obj(inclusion.layout) }, id = inclusion.kind === 'view' ? key(view) + ':panel:' + index : str(data.id) || str(target.record.name) || target.ref.id;
            const row = typeof placement.row === 'number' ? placement.row : Math.floor(index / columns), column = typeof placement.column === 'number' ? placement.column : index % columns, rowspan = typeof placement.rowspan === 'number' ? placement.rowspan : 1, colspan = typeof placement.colspan === 'number' ? placement.colspan : 1;
            layouts.push({ id, row, column, rowspan, colspan, data, inclusion });
            if (ids.has(id))
                issue('DDN-PANEL-ID', 'Panel IDs must be unique', target.ref);
            ids.add(id);
            if (![row, column, rowspan, colspan].every(Number.isInteger) || row < 0 || row > 100 || column < 0 || rowspan < 1 || colspan < 1 || column + colspan > columns || row + rowspan > 101) {
                issue('DDN-PANEL-BOUNDS', 'Panel spans must stay inside the grid', target.ref);
                continue;
            }
            for (let r = row; r < row + rowspan; r++)
                for (let c = column; c < column + colspan; c++) {
                    const cell = r + ':' + c;
                    if (occupied.has(cell))
                        issue('DDN-PANEL-OVERLAP', 'Panel cells cannot overlap', target.ref);
                    occupied.add(cell);
                }
            if (inclusion.kind === 'view' && arr(data.items).length)
                issue('DDN-PANEL-CONTENT', 'A panel holds either a view or item references', target.ref);
            if (inclusion.kind === 'view') {
                if (target === view)
                    issue('DDN-PANEL-RECURSION', 'Panel cannot embed its containing view', target.ref);
                if (arr((0, schema_core_js_1.getPath)(target.record, 'projection.options.panels')).some(v => obj(v).kind === 'view'))
                    issue('DDN-PANEL-DEPTH', 'Embedded panels support one child-view level', target.ref);
            }
        }
        const required = profile.standard_overrides['template.required_panel_ids'];
        if (Array.isArray(required) && review && required.some(id => !ids.has(str(id))))
            issue('DDN-CANVAS-PANELS', 'Canvas is missing required named blocks');
        if (profile.id === 'panels.pyramid@1') {
            if (panels.length < 3)
                incomplete('Pyramid requires at least three bands');
            if (columns !== 1 || panels.length > 5 || layouts.some((p, i) => p.row !== i || p.rowspan !== 1 || p.colspan !== 1))
                issue('DDN-PYRAMID-BANDS', 'Pyramid requires one column and at most five contiguous single-row bands');
        }
        if (profile.id === 'panels.venn@1') {
            if (panels.length < 2)
                incomplete('Venn requires at least two sets');
            if (panels.length > 3)
                issue('DDN-VENN-SETS', 'Venn supports at most three sets');
            const memberships = new Map();
            for (const panel of layouts)
                for (const reference of arr(panel.data.items)) {
                    const target = resolve(reference);
                    if (!target) {
                        issue('DDN-PANEL-ITEM', 'Panel member must resolve');
                        continue;
                    }
                    const membership = memberships.get(key(target)) ?? { target, sets: new Set() };
                    membership.sets.add(panel.id);
                    memberships.set(key(target), membership);
                }
            for (const { target, sets } of memberships.values()) {
                const declared = arr((0, schema_core_js_1.getPath)(target.record, 'metadata.x_sets'));
                if (!declared.length)
                    incomplete('Venn members require their exact declared set IDs');
                else if (declared.length !== sets.size || declared.some(id => !sets.has(str(id))))
                    issue('DDN-VENN-MEMBERSHIP', 'Venn member set IDs must exactly match panel membership', target.ref);
            }
        }
        if (profile.id === 'panels.journey@1' && layouts.length) {
            const phases = layouts.filter(panel => panel.id.startsWith('phase-')).sort((a, b) => a.column - b.column), slugs = phases.map(panel => panel.id.slice(6));
            if (phases.length < 2)
                incomplete('Journey requires at least two phases');
            if (phases.length > 8 || columns > 8)
                issue('DDN-JOURNEY-PHASES', 'Journey permits at most eight phase columns');
            if (phases.length !== columns)
                incomplete('Journey needs one phase for each declared column');
            const expected = new Map();
            slugs.forEach((slug, column) => ['phase', 'actions', 'touchpoints', 'opportunities'].forEach((prefix, row) => expected.set(prefix + '-' + slug, { row, column, colspan: 1 })));
            expected.set('emotions', { row: 4, column: 0, colspan: columns });
            if ([...expected.keys()].some(id => !ids.has(id)))
                incomplete('Journey requires phase, actions, touchpoints, opportunities and emotions panels');
            for (const panel of layouts) {
                const position = expected.get(panel.id);
                if (!position || panel.row !== position.row || panel.column !== position.column || panel.colspan !== position.colspan || panel.rowspan !== 1)
                    issue('DDN-JOURNEY-LAYOUT', 'Journey panel IDs and positions must match the declared phase grid');
            }
            const emotion = layouts.find(panel => panel.id === 'emotions'), seen = new Set();
            for (const reference of arr(emotion?.data.items)) {
                const target = resolve(reference), value = obj((0, schema_core_js_1.getPath)(target?.record, 'metadata.x_record')), phase = str(value.phase);
                if (!target || !slugs.includes(phase) || seen.has(phase) || !num(value.value) || value.value < 1 || value.value > 5)
                    issue('DDN-JOURNEY-EMOTION', 'Emotion records require a unique declared phase and a value from 1 through 5');
                seen.add(phase);
            }
        }
    }
    if (profile.projection === 'timeline') {
        const calendar = obj(view.record.calendar), holidays = arr(calendar.holidays);
        if (holidays.some(value => typeof value !== 'string' || value.length !== 10 || !validDate(value)) || new Set(holidays).size !== holidays.length)
            issue('DDN-TIMELINE-HOLIDAYS', 'Business holidays must be unique valid date-only values');
        for (const row of rows) {
            const start = binding(row, 'start'), end = binding(row, 'end');
            if (typeof start !== 'string' || !validDate(start) || end !== undefined && end !== null && (typeof end !== 'string' || !validDate(end)))
                issue('DDN-TIMELINE-DATE', 'Timeline requires ISO dates or explicitly zoned timestamps', row.source);
            else if (typeof end === 'string' && Date.parse(end) < Date.parse(start))
                issue('DDN-TIMELINE-ORDER', 'End cannot precede start', row.source);
        }
        const instants = rows.flatMap(row => [binding(row, 'start'), binding(row, 'end')]).filter((value) => typeof value === 'string' && validDate(value)).map(Date.parse);
        if (options.calendar === 'business' && instants.length && (Math.max(...instants) - Math.min(...instants)) / 86400000 > 366000)
            issue('DDN-TIMELINE-RANGE', 'Business counting is bounded to 366000 days');
        for (const reference of arr(options.dependencies)) {
            const dependency = resolve(reference);
            if (!dependency || dependency.record.category !== 'relation')
                issue('DDN-TIMELINE-DEPENDENCY', 'Timeline dependencies must resolve to relations');
            else
                for (const endpoint of arr(dependency.record.endpoints)) {
                    const target = resolve(obj(endpoint).definition, dependency);
                    if (!target || !rows.some(row => key(target) === row.source.file + '\0' + row.source.id))
                        issue('DDN-TIMELINE-DEPENDENCY', 'Dependency endpoints must be included timeline records', dependency.ref);
                }
        }
        if (options.timezone !== undefined)
            try {
                new Intl.DateTimeFormat('en', { timeZone: str(options.timezone) }).format(0);
            }
            catch {
                issue('DDN-TIMEZONE-UNKNOWN', 'Named timezone is unavailable in this host', view.ref, 'warning');
            }
        if (options.calendar !== undefined && !['gregorian', 'fiscal', 'business'].includes(str(options.calendar)))
            issue('DDN-TIMELINE-CALENDAR', 'Calendar must be gregorian, fiscal or business');
    }
    if (profile.projection === 'fishbone') {
        const effects = nodes.filter(n => n.record.role === 'quality.effect'), effect = options.effect ? resolve(options.effect) : effects[0];
        if (review && (effects.length !== 1 || !effect))
            issue('DDN-FISHBONE-EFFECT', 'Fishbone requires exactly one selected effect');
        if (effect) {
            const used = new Set(), active = new Set();
            let occurrences = 0;
            const visit = (n, depth) => {
                if (++occurrences > 250 || depth > 4) {
                    issue('DDN-FISHBONE-LIMIT', 'Fishbone exceeds four cause levels or 250 occurrences');
                    return;
                }
                if (active.has(key(n))) {
                    issue('DDN-FISHBONE-CYCLE', 'Fishbone cannot cycle');
                    return;
                }
                active.add(key(n));
                used.add(key(n));
                for (const l of links.filter(l => l.to === n && (!options.relation || l.item.record.role === options.relation)))
                    visit(l.from, depth + 1);
                active.delete(key(n));
            };
            visit(effect, 0);
            const categories = links.filter(l => l.to === effect);
            if (review && (categories.length < 1 || categories.length > 12 || categories.some(l => l.from.record.role !== 'quality.category')))
                issue('DDN-FISHBONE-CATEGORIES', 'Effect requires 1..12 first-level category ribs');
            if (links.some(l => !used.has(key(l.from)) || !used.has(key(l.to))))
                issue('DDN-FISHBONE-DISCONNECTED', 'Selected cause graph contains disconnected branches');
        }
    }
    if (profile.projection === 'geo') {
        if (!str(options.geography))
            incomplete('Geographic projection requires host-supplied geography');
        if (!['outline', 'symbol', 'choropleth'].includes(geoMark))
            issue('DDN-GEO-MARK', 'Geographic projections admit outline, symbol or choropleth marks');
        if (geoMark === 'symbol')
            for (const row of rows) {
                const longitude = binding(row, 'x'), latitude = binding(row, 'y');
                if (!num(longitude) || longitude < -180 || longitude > 180 || !num(latitude) || latitude < -90 || latitude > 90)
                    issue('DDN-GEO-COORDINATE', 'Geographic coordinates must be finite longitude/latitude in range', row.source);
                if (options.size !== undefined && (!num(binding(row, 'size')) || binding(row, 'size') < 0))
                    issue('DDN-GEO-SIZE', 'Symbol size must be finite and nonnegative', row.source);
            }
        if (geoMark === 'choropleth') {
            const seen = new Set();
            for (const row of rows) {
                const region = binding(row, 'x'), value = binding(row, 'value');
                const id = (0, schema_core_js_1.stableStringify)(region ?? null);
                if (region === undefined || seen.has(id))
                    issue('DDN-GEO-REGION', 'Choropleth region keys must be present and unique', row.source);
                seen.add(id);
                if (!num(value))
                    issue('DDN-GEO-VALUE', 'Choropleth measures must be finite numbers', row.source);
            }
        }
    }
    return result;
}
function validDate(value) {
    if (!/^\d{4}-\d\d-\d\d(?:T\d\d:\d\d(?::\d\d(?:\.\d+)?)?(?:Z|[+-]\d\d:\d\d))?$/.test(value) || !Number.isFinite(Date.parse(value)))
        return false;
    const date = value.slice(0, 10);
    return new Date(date).toISOString().slice(0, 10) === date;
}

},
"profiles/src/semantic.js":function(module,exports,require){
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.profileSelection = profileSelection;
exports.completeProfileDiagnostics = completeProfileDiagnostics;
exports.decisionDomains = decisionDomains;
exports.decisionRules = decisionRules;
exports.decisionOutputErrors = decisionOutputErrors;
const core_js_1 = require("profiles/src/core.js");
const schema_core_js_1 = require("profiles/src/schema-core.js");
const analysis_js_1 = require("profiles/src/analysis.js");
const analysis_profile_js_1 = require("profiles/src/analysis-profile.js");
const projection_rules_js_1 = require("profiles/src/projection-rules.js");
const object = (v) => (0, schema_core_js_1.isRecord)(v) ? v : {};
const array = (v) => Array.isArray(v) ? v : [];
const text = (v) => typeof v === 'string' ? v : '';
const key = (v) => v.file + '\0' + v.ref.id;
const role = (v) => text(v.record.role);
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const meta = (v, name) => (0, schema_core_js_1.getPath)(v.record, 'metadata.' + name);
function profileSelection(view, records) {
    const selected = new Map();
    const resolve = (ref, owner = view) => typeof ref === 'string' ? records.find(r => r.file === owner.file && (r.record.name === ref || r.ref.id === ref)) : (0, core_js_1.resolveRecord)(records, owner.file, ref);
    const add = (r) => {
        if (r?.owner === 'definition')
            selected.set(key(r), r);
    };
    for (const appearance of records.filter(r => r.owner === 'appearance'))
        if (resolve(appearance.record.parent, appearance) === view)
            add(resolve(appearance.record.target, appearance));
    for (const path of ['sources', 'selection.items', 'selection.include', 'projection.inputs'])
        for (const ref of array((0, schema_core_js_1.getPath)(view.record, path)))
            add(resolve(ref));
    for (const ref of array((0, schema_core_js_1.getPath)(view.record, 'selection.exclude'))) {
        const item = resolve(ref);
        if (item)
            selected.delete(key(item));
    }
    const nodes = [...selected.values()].filter(r => r.record.category !== 'relation'), edges = [...selected.values()].filter(r => r.record.category === 'relation');
    const links = [];
    for (const item of edges) {
        const ends = array(item.record.endpoints).filter(schema_core_js_1.isRecord), from = resolve(ends[0]?.definition, item), to = resolve(ends[1]?.definition, item);
        if (from && to)
            links.push({ item, from, to, ends });
    }
    return { nodes, edges, links, selected, resolve };
}
function topological(nodes, links) {
    const ids = new Set(nodes.map(key)), degree = new Map(nodes.map(n => [key(n), 0])), outgoing = new Map(nodes.map(n => [key(n), []]));
    for (const l of links)
        if (ids.has(key(l.from)) && ids.has(key(l.to))) {
            degree.set(key(l.to), degree.get(key(l.to)) + 1);
            outgoing.get(key(l.from)).push(key(l.to));
        }
    const queue = [...degree].filter(([, n]) => !n).map(([id]) => id);
    for (let i = 0; i < queue.length; i++)
        for (const next of outgoing.get(queue[i])) {
            degree.set(next, degree.get(next) - 1);
            if (!degree.get(next))
                queue.push(next);
        }
    return queue.length === nodes.length;
}
function completeProfileDiagnostics(view, records, review = false) {
    const profileId = text(view.record.profile), profile = (0, core_js_1.getProfile)(profileId);
    if (!profile)
        return [];
    const result = [];
    const issue = (code, message, target = view.ref, severity = 'error') => result.push({ code, severity, message, target, rule: 'ddn.profile.' + profileId });
    const incomplete = (message, target = view.ref) => {
        if (review)
            issue('DDN-PROFILE-INCOMPLETE', message, target, 'warning');
    };
    const { nodes, edges, links, selected, resolve } = profileSelection(view, records);
    const regions = array(view.record.regions).filter(schema_core_js_1.isRecord);
    const regionOf = (n) => regions.find(region => array(region.members).some(ref => resolve(ref) === n));
    const regionOwner = (n) => { const region = regionOf(n); return region ? resolve(region.scope) : resolve(object(meta(n, 'x_diagram')).owner, n); };
    const regionKey = (n) => text(regionOf(n)?.id) || text(object(meta(n, 'x_diagram')).owner);
    const regionIds = new Set();
    for (const region of regions) {
        const id = text(region.id);
        if (regionIds.has(id))
            issue('DDN-REGION-ID', 'Region IDs must be unique');
        regionIds.add(id);
        for (const member of array(region.members))
            if (!resolve(member) || !selected.has(key(resolve(member))))
                issue('DDN-REGION-MEMBER', 'Region member must resolve to a selected item');
        if (region.scope !== undefined && !resolve(region.scope))
            issue('DDN-REGION-SCOPE', 'Region scope must resolve');
    }
    for (const region of regions) {
        const seen = new Set();
        let current = region;
        while (current) {
            const id = text(current.id);
            if (seen.has(id)) {
                issue('DDN-REGION-CYCLE', 'Region nesting must be acyclic');
                break;
            }
            seen.add(id);
            const parent = current.parent;
            if (parent !== undefined && !regionIds.has(text(parent))) {
                issue('DDN-REGION-PARENT', 'Region parent must exist');
                break;
            }
            current = parent === undefined ? undefined : regions.find(r => r.id === parent);
        }
    }
    const incoming = (n, within = links) => within.filter(l => key(l.to) === key(n));
    const outgoing = (n, within = links) => within.filter(l => key(l.from) === key(n));
    const members = (n) => array(n.record.members).map(r => resolve(r, n)).filter((r) => !!r);
    const selectedRef = (reference, owner, roles) => { const target = resolve(reference, owner); return target && selected.has(key(target)) && (!roles || roles.includes(role(target))) ? target : undefined; };
    const unique = (values, code, description) => {
        const defined = values.filter((v) => !!v);
        if (new Set(defined).size !== defined.length)
            issue(code, description);
    };
    const cycle = (subset, code) => {
        if (!topological(nodes, subset))
            issue(code, 'The declared relationship graph must be acyclic');
    };
    for (const n of [...nodes, ...edges]) {
        const m = object(n.record.metadata), r = role(n);
        for (const [name, admitted] of Object.entries({ x_petri: ['petri.'], x_idef0: ['idef0.'], x_vsm: ['vsm.process'], x_contact: ['ladder.contact'], x_coil: ['ladder.coil'], x_gateway: ['flow.gateway'], x_event: ['flow.start', 'flow.end', 'flow.intermediate'], x_epc: ['epk.connector'], x_chen: ['entity', 'field', 'assoc', 'ref'], x_instance: ['object', 'record'], x_rack: ['network.rack', 'network.server', 'network.switch'], x_states: ['uml.', 'msc.', 'object', 'service', 'application'], x_gate: ['tree.gate'], x_activity: ['flow.process', 'flow.subprocess', 'flow.choreotask'], x_io: ['flow.datainput', 'flow.dataoutput'], x_bands: ['flow.choreotask'], x_sentry: ['cmmn.sentry'], x_boxed: ['dmn.decision', 'dmn.bkm'] })) {
            if (m[name] !== undefined && !admitted.some(a => a.endsWith('.') ? r.startsWith(a) : r === a))
                issue('DDN-METADATA-OWNER', name + ' is not legal on ' + r, n.ref);
        }
        if (m.x_petri !== undefined) {
            const p = object(m.x_petri);
            if (p.tokens !== undefined && r !== 'petri.place' || p.weight !== undefined && !['petri.arc', 'petri.testarc'].includes(r))
                issue('DDN-PETRI-OWNER', 'Tokens belong to places; weights belong to ordinary and test arcs', n.ref);
        }
        if (m.x_vsm !== undefined) {
            const v = object(m.x_vsm);
            if ((v.va !== undefined || v.nva !== undefined) && !text(v.unit))
                incomplete('VA/NVA durations require a declared unit', n.ref);
        }
        if (m.x_subdiagram !== undefined) {
            const child = resolve(object(m.x_subdiagram).view, n);
            if (!child || child.owner !== 'view_definition')
                issue('DDN-SUBDIAGRAM-TARGET', 'Subdiagram must reference a workspace view', n.ref);
            else if (key(child) === key(view))
                issue('DDN-SUBDIAGRAM-RECURSION', 'A view cannot embed itself', n.ref);
            else if (profileId === 'dmn.drd@1' && child.record.profile !== 'decision.rules@1')
                issue('DDN-DMN-DRILLDOWN', 'DMN decision drill-down must reference a decision table view', n.ref);
        }
        if (m.x_boxed !== undefined) {
            const boxed = object(m.x_boxed);
            if (['literal', 'invocation'].includes(text(boxed.form)) && !text(boxed.text) || ['context', 'relation'].includes(text(boxed.form)) && !array(boxed.entries).length)
                incomplete('Boxed expression requires text or entries for its declared presentation form', n.ref);
        }
        if (m.x_contract !== undefined) {
            const ref = object(m.x_contract).choreography;
            if (ref !== undefined) {
                const target = resolve(ref, n);
                if (!target || target.owner !== 'view_definition' || !['sequence', 'graph'].includes((0, core_js_1.getProfile)(text(target.record.profile))?.projection ?? '') || !/sequence|statemachine/.test(text(target.record.profile)))
                    issue('DDN-SERVICE-CHOREOGRAPHY', 'Service choreography must reference a sequence or state-machine view', n.ref);
            }
        }
        if (m.x_sdl !== undefined && profileId === 'sdl.process@1') {
            const sdl = object(m.x_sdl);
            if (['priority', 'spontaneous', 'continuous', 'active'].some(p => sdl[p] !== undefined) && r !== 'sdl.input')
                issue('DDN-SDL-MARKER-OWNER', 'Input markers belong only to SDL input nodes', n.ref);
            if ((sdl.timer !== undefined || sdl.duration !== undefined) && !['sdl.set', 'sdl.reset'].includes(r))
                issue('DDN-SDL-TIMER-OWNER', 'Timer references belong to set/reset nodes', n.ref);
        }
        if (m.x_sdl !== undefined)
            for (const ref of array(object(m.x_sdl).signals))
                if (role(resolve(ref, n) ?? n) !== 'sdl.signal')
                    issue('DDN-SDL-SIGNAL', 'Signal references must resolve to sdl.signal', n.ref);
        if (m.x_jump !== undefined && !selectedRef(object(m.x_jump).target, n, ['ladder.label']))
            issue('DDN-LADDER-JUMP', 'Jump target must be a selected ladder label', n.ref);
        if (m.x_derive !== undefined && r !== 'orm.facttype')
            issue('DDN-ORM-DERIVATION', 'Derivation text belongs to a fact type', n.ref);
        if (m.x_planning !== undefined && !['cmmn.stage', 'cmmn.humantask'].includes(r))
            issue('DDN-CMMN-PLANNING', 'Planning tables belong to a stage or human task', n.ref);
    }
    for (const owner of nodes)
        for (const member of members(owner))
            if (role(member) === 'core::Port') {
                const declared = resolve((0, schema_core_js_1.getPath)(member.record, 'content.owner'), member);
                if (declared && declared !== owner)
                    issue('DDN-PORT-OWNER', 'Port owner and containing member list must agree', member.ref);
                for (const [name, value] of Object.entries(object(member.record.metadata))) {
                    if (['x_fbd', 'x_icom', 'x_service', 'x_port', 'x_pin', 'x_interfaces'].includes(name)) {
                        for (const failure of (0, schema_core_js_1.validateSchema)('meta_' + name + '_port', value))
                            issue('DDN-PORT-METADATA', name + ': ' + failure.message, member.ref);
                    }
                }
                const service = object(meta(member, 'x_service'));
                const serviceOwner = ['soaml.participant', 'soaml.agent'].includes(role(owner)) || role(owner) === 'soaml.serviceinterface' && service.kind === 'service';
                if (service.kind !== undefined && !serviceOwner)
                    issue('DDN-SERVICE-PORT', 'Service/request ports belong to participants or agents; a service interface may declare its provided service port', member.ref);
                if (meta(member, 'x_fbd') !== undefined && !['fbd.block', 'fbd.variable'].includes(role(owner)))
                    issue('DDN-FBD-PORT', 'FBD pins belong to blocks or variables', member.ref);
                if (meta(member, 'x_icom') !== undefined && role(owner) !== 'idef0.activity')
                    issue('DDN-IDEF0-PORT', 'ICOM ports belong to IDEF0 functions', member.ref);
                if (meta(member, 'x_pin') !== undefined && !['flow.process', 'flow.subprocess', 'flow.sendsignal', 'flow.acceptsignal'].includes(role(owner)))
                    issue('DDN-ACTIVITY-PIN', 'Activity pins belong to supported action kinds', member.ref);
                if (role(owner) === 'sdl.agent')
                    issue('DDN-SDL-GATE', 'SDL gates belong to blocks', member.ref);
            }
    for (const link of links.filter(link => ['uml.assembly', 'uml.connector', 'uml.delegation'].includes(role(link.item)))) {
        const source = resolve(link.ends[0]?.member, link.item) ?? link.from, target = resolve(link.ends[1]?.member, link.item) ?? link.to;
        const assertions = (item, path) => array(object(meta(item, 'x_interfaces'))[path]).map(ref => resolve(ref, item)).filter((r) => !!r);
        const provided = assertions(source, 'provides'), required = assertions(target, 'requires');
        if (role(link.item) === 'uml.delegation' && role(source) !== 'core::Port')
            issue('DDN-DELEGATION-PORT', 'Delegation starts at a port', link.item.ref);
        const mode = text(object(meta(link.item, 'x_compatibility')).mode) || 'same';
        const compatible = (a, b) => {
            if (a === b)
                return true;
            if (mode === 'operation-coverage') {
                const signature = (field) => (0, schema_core_js_1.stableStringify)({ name: field.record.name ?? '', datatype: (0, schema_core_js_1.getPath)(field.record, 'content.datatype') ?? (0, schema_core_js_1.getPath)(field.record, 'properties.datatype') ?? null, domain: (0, schema_core_js_1.getPath)(field.record, 'content.domain') ?? (0, schema_core_js_1.getPath)(field.record, 'properties.domain') ?? null, parameters: (0, schema_core_js_1.getPath)(field.record, 'properties.parameters') ?? null });
                const signatures = new Set(members(a).filter(f => object(meta(f, 'x_member')).kind === 'operation').map(signature));
                return members(b).filter(f => object(meta(f, 'x_member')).kind === 'operation').every(f => signatures.has(signature(f)));
            }
            const roles = mode === 'specialization' ? ['uml.generalization'] : mode === 'realization' ? ['uml.realization', 'uml.generalization'] : [];
            const visited = new Set(), queue = [a];
            for (let i = 0; i < queue.length; i++) {
                const item = queue[i];
                if (item === b)
                    return true;
                if (visited.has(key(item)))
                    continue;
                visited.add(key(item));
                for (const edge of links)
                    if (edge.from === item && roles.includes(role(edge.item)))
                        queue.push(edge.to);
            }
            return false;
        };
        if (required.length && !required.every(r => provided.some(p => compatible(p, r))))
            issue('DDN-INTERFACE-COMPATIBILITY', 'Provided interfaces do not satisfy the declared required interface assertion', link.item.ref);
        const reverseRequired = assertions(source, 'requires'), reverseProvided = assertions(target, 'provides');
        if (reverseRequired.length && !reverseRequired.every(r => reverseProvided.some(p => compatible(p, r))))
            issue('DDN-INTERFACE-COMPATIBILITY', 'Reverse provided interfaces do not satisfy the declared required interface assertion', link.item.ref);
        if (profileId === 'soaml.services@1') {
            const service = object(meta(source, 'x_service')), request = object(meta(target, 'x_service'));
            const a = resolve((0, schema_core_js_1.getPath)(source.record, 'content.schema'), source), b = resolve((0, schema_core_js_1.getPath)(target.record, 'content.schema'), target);
            if (service.kind === 'service' && request.kind === 'request') {
                if (!a || !b)
                    incomplete('Service/request ports require interface types', link.item.ref);
                else if (!compatible(a, b))
                    issue('DDN-SERVICE-COMPATIBILITY', 'Service and request interface types are incompatible under the selected mode', link.item.ref);
            }
        }
    }
    const treeProfiles = ['org.tree@1', 'wbs.tree@1'];
    if (treeProfiles.includes(profileId)) {
        if (review && nodes.length && nodes.filter(n => !incoming(n).length).length !== 1)
            issue('DDN-TREE-ROOT', 'Exactly one decomposition root is required');
        if (nodes.some(n => incoming(n).length > 1))
            issue('DDN-TREE-PARENT', 'A child cannot have multiple parents');
        cycle(links, 'DDN-TREE-CYCLE');
    }
    if (profileId === 'family.tree@1') {
        const parents = links.filter(l => /parent/.test(role(l.item)));
        cycle(parents, 'DDN-FAMILY-CYCLE');
        for (const n of nodes)
            if (incoming(n, parents).length > 2)
                issue('DDN-FAMILY-PARENTS', 'At most two parents are supported', n.ref);
    }
    if (/^(flow\.|uml\.activity|sysml\.activity)/.test(profileId)) {
        const flow = links.filter(l => ['flow.next', 'flow.continues', 'uml.flow'].includes(role(l.item))), active = nodes.filter(n => !/annotation|note|data|lane|group/.test(role(n)));
        const starts = active.filter(n => /(?:^|\.)start$|initial$/.test(role(n))), ends = active.filter(n => /(?:^|\.)end$|final$|terminate$/.test(role(n)));
        if (review && active.length && (!starts.length || !ends.length))
            issue('DDN-FLOW-TERMINALS', 'Completed flow requires a start and an end');
        for (const n of starts)
            if (incoming(n, flow).length)
                issue('DDN-FLOW-START', 'Start cannot have incoming control flow', n.ref);
        for (const n of ends)
            if (outgoing(n, flow).length)
                issue('DDN-FLOW-END', 'End cannot have outgoing control flow', n.ref);
        for (const n of active) {
            const ins = incoming(n, flow), outs = outgoing(n, flow);
            if (/decision$/.test(role(n)) && review) {
                const labels = outs.map(l => text((0, schema_core_js_1.getPath)(l.item.record, 'metadata.x_diagram.branch')) || text(l.item.record.title));
                if (outs.length < 2 || labels.some(s => !s.trim()) || new Set(labels).size !== labels.length)
                    issue('DDN-FLOW-BRANCH', 'Decisions require at least two distinct nonempty branch labels', n.ref);
            }
            if (/forkjoin$/.test(role(n)) && review && !(ins.length === 1 && outs.length >= 2 || ins.length >= 2 && outs.length === 1))
                issue('DDN-ACTIVITY-FAN', 'Fork/join requires a valid split or join fan', n.ref);
            if (/merge$/.test(role(n)) && review && (ins.length < 2 || outs.length !== 1))
                issue('DDN-ACTIVITY-MERGE', 'Merge requires at least two incoming and exactly one outgoing flow', n.ref);
            if (/fork$/.test(role(n)) && review && (ins.length !== 1 || outs.length < 2) || /join$/.test(role(n)) && review && (ins.length < 2 || outs.length !== 1))
                issue('DDN-ACTIVITY-FAN', 'Fork and join fan counts are invalid', n.ref);
        }
        const reachable = (origins, reverse) => {
            const visited = new Set(origins.map(key)), queue = [...origins];
            for (let i = 0; i < queue.length; i++)
                for (const l of reverse ? incoming(queue[i], flow) : outgoing(queue[i], flow)) {
                    const next = reverse ? l.from : l.to;
                    if (!visited.has(key(next))) {
                        visited.add(key(next));
                        queue.push(next);
                    }
                }
            return visited;
        };
        if (review && starts.length && ends.length) {
            const from = reachable(starts, false), to = reachable(ends, true);
            for (const n of active)
                if (!from.has(key(n)) || !to.has(key(n)))
                    issue('DDN-FLOW-REACHABILITY', 'Every control node must be reachable from a start and able to reach an end', n.ref);
        }
        const continuations = nodes.filter(n => meta(n, 'x_continuation') !== undefined), groups = new Map();
        for (const n of continuations) {
            const k = text(object(meta(n, 'x_continuation')).key);
            groups.set(k, [...groups.get(k) ?? [], n]);
        }
        for (const [id, pair] of groups) {
            const source = pair.find(n => object(meta(n, 'x_continuation')).side === 'out'), target = pair.find(n => object(meta(n, 'x_continuation')).side === 'in');
            if (review && (pair.length !== 2 || !source || !target || !flow.some(l => role(l.item) === 'flow.continues' && l.from === source && l.to === target)))
                issue('DDN-FLOW-CONTINUATION', 'Continuation ' + id + ' requires one outgoing and one incoming connector joined by flow.continues');
        }
        const lanes = new Set([...nodes.filter(n => /lane$/.test(role(n))).flatMap(n => [n.ref.id, text(n.record.name)]), ...regions.flatMap(region => [text(region.id), text(region.name)])]);
        for (const n of nodes)
            if (meta(n, 'x_partition') !== undefined && !lanes.has(text(object(meta(n, 'x_partition')).lane)))
                issue('DDN-ACTIVITY-PARTITION', 'Partition must name a declared lane', n.ref);
    }
    if (profileId.startsWith('dfd.')) {
        const processes = nodes.filter(n => role(n) === 'dfd.process');
        unique(processes.map(n => text(object(meta(n, 'x_diagram')).number)), 'DDN-DFD-NUMBER', 'Process numbers must be unique');
        for (const n of processes)
            if (review && (!text(object(meta(n, 'x_diagram')).number) || !incoming(n).length || !outgoing(n).length))
                incomplete('Completed process needs a number and incoming/outgoing data flow', n.ref);
        for (const l of links)
            if (role(l.from) !== 'dfd.process' && role(l.to) !== 'dfd.process')
                issue('DDN-DFD-BYPASS', 'A data flow requires a process at one end', l.item.ref);
    }
    const composition = [];
    for (const link of links) {
        const sourceMark = (0, schema_core_js_1.getPath)(link.item.record, 'qualifiers.source.mark'), targetMark = (0, schema_core_js_1.getPath)(link.item.record, 'qualifiers.target.mark');
        const aggregates = ['diamond', 'filled-diamond'];
        if (aggregates.includes(text(sourceMark)) && aggregates.includes(text(targetMark)))
            issue('DDN-ASSOCIATION-AGGREGATION', 'Aggregation/composition may be declared at only one association end', link.item.ref);
        if (sourceMark === 'filled-diamond' || role(link.item) === 'sysml.composition')
            composition.push(link);
        else if (targetMark === 'filled-diamond')
            composition.push({ ...link, from: link.to, to: link.from });
        for (const side of ['source', 'target']) {
            const cardinality = object((0, schema_core_js_1.getPath)(link.item.record, 'qualifiers.' + side + '.cardinality'));
            if (finite(cardinality.min) && finite(cardinality.max) && cardinality.min > cardinality.max)
                issue('DDN-CARDINALITY-ORDER', 'Cardinality minimum cannot exceed maximum', link.item.ref);
        }
    }
    if (composition.length) {
        cycle(composition, 'DDN-COMPOSITION-CYCLE');
        for (const node of nodes)
            if (incoming(node, composition).length > 1)
                issue('DDN-COMPOSITION-OWNER', 'A composed part cannot have multiple composite owners', node.ref);
    }
    const generalizations = links.filter(l => /generaliz|\.extends$/.test(role(l.item)));
    if (generalizations.length) {
        cycle(generalizations, 'DDN-GENERALIZATION-CYCLE');
        for (const l of generalizations)
            if (role(l.from) !== role(l.to))
                issue('DDN-GENERALIZATION-KIND', 'Generalization endpoints must have the same classifier kind', l.item.ref);
    }
    if (/^uml\.|^sysml\.|^soaml\./.test(profileId)) {
        const sets = new Map();
        for (const link of links)
            if (meta(link.item, 'x_genset') !== undefined) {
                if (!generalizations.includes(link))
                    issue('DDN-GENERALIZATION-SET', 'Generalization sets belong only to generalization relations', link.item.ref);
                const name = text(object(meta(link.item, 'x_genset')).name);
                sets.set(name, [...sets.get(name) ?? [], link]);
            }
        for (const set of sets.values())
            if (set.some(link => link.to !== set[0].to || (0, schema_core_js_1.stableStringify)(meta(link.item, 'x_genset') ?? null) !== (0, schema_core_js_1.stableStringify)(meta(set[0].item, 'x_genset') ?? null)))
                issue('DDN-GENERALIZATION-SET', 'Members of a named generalization set must share a general classifier and flags', set[0].item.ref);
        for (const n of nodes) {
            if (meta(n, 'x_template') !== undefined && !['uml.class', 'uml.interface', 'uml.component', 'uml.enumeration', 'sysml.block', 'sysml.interfaceblock', 'sysml.valuetype'].includes(role(n)))
                issue('DDN-TEMPLATE-OWNER', 'Templates belong to classifiers', n.ref);
            for (const field of members(n)) {
                const kind = object(meta(field, 'x_member')).kind;
                if (kind === 'literal' && role(n) !== 'uml.enumeration' || role(n) === 'uml.enumeration' && kind !== undefined && kind !== 'literal')
                    issue('DDN-ENUMERATION-MEMBER', 'Enumeration members are literals and literal members belong to enumerations', field.ref);
                if (role(n) === 'uml.enumeration' && kind === undefined)
                    incomplete('Enumeration members require the literal member kind', field.ref);
                const part = object(meta(field, 'x_part'));
                if (part.classifier !== undefined) {
                    const classifier = resolve(part.classifier, field);
                    if (!classifier || !['uml.class', 'uml.interface', 'uml.component', 'uml.collaboration', 'sysml.block', 'sysml.interfaceblock', 'sysml.valuetype'].includes(role(classifier)))
                        issue('DDN-PART-CLASSIFIER', 'Composite part type must resolve to a classifier', field.ref);
                }
            }
        }
        const packageParent = (n) => resolve(object(meta(n, 'x_pack')).package, n);
        for (const n of nodes) {
            const seen = new Set([key(n)]);
            let parent = packageParent(n);
            while (parent) {
                if (seen.has(key(parent))) {
                    issue('DDN-PACKAGE-CYCLE', 'Package ownership cannot cycle', n.ref);
                    break;
                }
                seen.add(key(parent));
                parent = packageParent(parent);
            }
        }
        for (const l of links) {
            if (/import|access/.test(role(l.item)) && object(meta(l.to, 'x_pack')).visibility === 'private' && packageParent(l.from) !== packageParent(l.to))
                issue('DDN-PACKAGE-PRIVATE', 'Private package content cannot be imported from another package', l.item.ref);
            if (/merge/.test(role(l.item))) {
                let ancestor = l.from;
                const seen = new Set();
                while (ancestor && !seen.has(key(ancestor))) {
                    seen.add(key(ancestor));
                    if (ancestor === l.to) {
                        issue('DDN-PACKAGE-MERGE', 'A package cannot merge itself or an ancestor', l.item.ref);
                        break;
                    }
                    ancestor = packageParent(ancestor);
                }
            }
            if (meta(l.item, 'x_association_class') !== undefined && !selectedRef(object(meta(l.item, 'x_association_class')).class, l.item, ['uml.class', 'cls']))
                issue('DDN-ASSOCIATION-CLASS', 'Association class must resolve to a selected classifier', l.item.ref);
            if (/communication_path|communicationpath/.test(role(l.item)) && Object.values(object(meta(l.item, 'x_endlabels'))).some(v => object(v).qualifier !== undefined))
                issue('DDN-DEPLOYMENT-QUALIFIER', 'Communication paths cannot carry qualifiers', l.item.ref);
        }
    }
    if (/usecase/.test(profileId)) {
        cycle(links.filter(l => /include|generaliz/.test(role(l.item))), 'DDN-USECASE-CYCLE');
        if (!profileId.endsWith('@1') || profileId.startsWith('sysml.'))
            for (const l of links.filter(l => /include|extend/.test(role(l.item)))) {
                const subjects = (n) => array(object(meta(n, 'x_usecase')).subjects).map(ref => resolve(ref, n)).filter(Boolean);
                const a = subjects(l.from), b = subjects(l.to);
                if (review && (!a.length || !b.length))
                    incomplete('Use cases require declared subjects', l.item.ref);
                else if (a.length && !a.some(s => b.includes(s)))
                    issue('DDN-USECASE-SUBJECT', 'Include and extend endpoints must share a subject', l.item.ref);
                if (/extend/.test(role(l.item))) {
                    const detail = object(meta(l.item, 'x_usecase'));
                    if (detail.condition !== undefined && detail.condition_ref !== undefined)
                        issue('DDN-USECASE-CONDITION', 'Extend cannot have conflicting condition forms', l.item.ref);
                    if (!array(object(meta(l.to, 'x_usecase')).extension_points).includes(detail.extension_point ?? ''))
                        issue('DDN-USECASE-EXTENSION', 'Extend must target a declared extension point', l.item.ref);
                }
            }
    }
    if (profileId === 'requirements.basic@1' || profileId === 'sysml.requirements@1') {
        const requirements = nodes.filter(n => /requirement$/.test(role(n)));
        unique(requirements.map(n => text(object(meta(n, 'x_diagram')).code)), 'DDN-REQUIREMENT-CODE', 'Requirement codes must be unique');
        for (const n of requirements)
            if (review && (!text(object(meta(n, 'x_diagram')).code).trim() || !text(object(meta(n, 'x_diagram')).text).trim()))
                incomplete('A completed requirement needs nonempty code and text', n.ref);
    }
    if (profileId.startsWith('chen.')) {
        for (const l of links) {
            if (l.ends.some(e => e.member !== undefined))
                issue('DDN-CHEN-MEMBER', 'Chen relationships connect entities, not member endpoints', l.item.ref);
            const extras = array(object(meta(l.item, 'x_nary')).ends);
            if (extras.length && profileId !== 'chen.nary@3')
                issue('DDN-CHEN-NARY', 'N-ary associations require chen.nary@3', l.item.ref);
            if (extras.length) {
                const ends = [l.from, l.to, ...extras.map(v => selectedRef(object(v).element, l.item, ['entity']))];
                if (role(l.item) !== 'assoc' || ends.some(e => !e) || new Set(ends.filter((e) => !!e).map(key)).size !== ends.length)
                    issue('DDN-CHEN-NARY-ENDS', 'N-ary assoc ends must be distinct selected entities', l.item.ref);
            }
            if (profileId !== 'chen.basic@1' && review)
                for (const side of ['from', 'to']) {
                    const card = object(object(meta(l.item, 'x_chen'))[side]);
                    if (card.min === undefined || card.max === undefined)
                        incomplete('Chen participant ends require explicit min/max bounds', l.item.ref);
                }
        }
        const ownerLinks = [];
        for (const n of nodes) {
            const chen = object(meta(n, 'x_chen'));
            for (const field of members(n)) {
                const c = object(meta(field, 'x_chen'));
                if ((c.key || c.partial_key) && (c.derived || c.multivalued))
                    issue('DDN-CHEN-KEY', 'A key cannot be derived or multivalued', field.ref);
            }
            if (chen.weak) {
                const owner = selectedRef(chen.owner, n, ['entity']);
                if (!owner || owner === n)
                    issue('DDN-CHEN-OWNER', 'Weak entity requires a different selected entity owner', n.ref);
                else
                    ownerLinks.push({ from: owner, to: n, item: n, ends: [] });
                const identifying = links.filter(l => object(meta(l.item, 'x_chen')).identifying && [l.from, l.to].includes(n));
                if (review && (!members(n).some(f => object(meta(f, 'x_chen')).partial_key) || identifying.length !== 1))
                    incomplete('Weak entity requires a partial key and exactly one identifying relation', n.ref);
            }
        }
        cycle(ownerLinks, 'DDN-CHEN-OWNER-CYCLE');
    }
    if (profileId === 'erd.crowfoot@1')
        for (const l of links) {
            const ends = object(meta(l.item, 'x_endlabels'));
            for (const side of ['source', 'target']) {
                const card = object(object(meta(l.item, 'x_chen'))[side === 'source' ? 'from' : 'to']);
                const derived = card.min === 1 && card.max === 1 ? 'one' : card.min === 0 && card.max === 1 ? 'zeroone' : card.min === 1 && card.max === 'many' ? 'many' : card.min === 0 && card.max === 'many' ? 'zeromany' : undefined;
                const mark = (0, schema_core_js_1.getPath)(l.item.record, 'properties.' + (side === 'source' ? 'source_mark' : 'target_mark')) ?? object(ends[side]).multiplicity ?? derived;
                if (mark === undefined)
                    incomplete('Crows-foot connections require both endpoint marks', l.item.ref);
                else if (!['one', 'zeroone', 'many', 'zeromany'].includes(String(mark)))
                    issue('DDN-CROWFOOT-MARK', 'Unknown crows-foot endpoint mark', l.item.ref);
            }
        }
    if (profileId === 'uml.deployment@1' || profileId === 'c4.deployment@1')
        for (const region of regions) {
            if (region.scope !== undefined) {
                const scope = resolve(region.scope);
                if (!scope || !['uml.node', 'uml.device', 'uml.executionenv'].includes(role(scope)))
                    issue('DDN-DEPLOYMENT-SCOPE', 'Deployment regions must scope a node, device or execution environment');
            }
        }
    if (profileId.startsWith('c4.')) {
        for (const link of links)
            if (link.ends.some(end => end.member !== undefined))
                issue('DDN-C4-MEMBER', 'C4 relationships connect elements, not fields or ports', link.item.ref);
        if (['c4.container@1', 'c4.component@1'].includes(profileId)) {
            const scopeRole = profileId === 'c4.container@1' ? 'c4.system' : 'c4.container';
            const scoped = regions.filter(region => { const owner = resolve(region.scope); return owner && role(owner) === scopeRole; });
            if (review && scoped.length !== 1)
                incomplete('C4 subtype requires exactly one region scoped to its parent ' + scopeRole);
            if (scoped.length === 1) {
                const members = new Set(array(scoped[0].members).map(ref => resolve(ref)).filter((n) => !!n).map(key));
                const inside = profileId === 'c4.container@1' ? ['c4.container', 'c4.store', 'c4.queue'] : ['c4.component'];
                for (const n of nodes.filter(n => inside.includes(role(n))))
                    if (!members.has(key(n)))
                        issue('DDN-C4-SCOPE', 'Interior element must belong to the enclosing scope', n.ref);
            }
        }
    }
    if (profileId.startsWith('epc.')) {
        const flow = links.filter(l => /flow|next/.test(role(l.item)));
        for (const l of flow)
            if (role(l.from) === role(l.to) && ['epk.event', 'epk.function'].includes(role(l.from)))
                issue('DDN-EPC-ALTERNATION', 'Events and functions cannot connect directly to their own kind', l.item.ref);
        for (const n of nodes.filter(n => role(n) === 'epk.connector')) {
            if (!['and', 'or', 'xor'].includes(text(object(meta(n, 'x_epc')).operator)))
                incomplete('EPC connectors require and/or/xor operator', n.ref);
            if (profileId === 'epc.complete@1' && review && !(incoming(n, flow).length === 1 && outgoing(n, flow).length >= 2 || incoming(n, flow).length >= 2 && outgoing(n, flow).length === 1))
                issue('DDN-EPC-FAN', 'Connector must be a split or a join', n.ref);
        }
    }
    if (profileId.startsWith('bpmn.')) {
        const pool = (n) => {
            const region = regionOf(n);
            if (region) {
                let current = region;
                const seen = new Set();
                while (current.parent !== undefined && !seen.has(text(current.id))) {
                    seen.add(text(current.id));
                    const parent = regions.find(r => r.id === current.parent);
                    if (!parent)
                        break;
                    current = parent;
                }
                return text(current.id);
            }
            return text(object(meta(n, 'x_diagram')).owner) || text(object(meta(n, 'x_partition')).lane);
        };
        for (const l of links) {
            if (/message/.test(role(l.item)) && pool(l.from) && pool(l.from) === pool(l.to))
                issue('DDN-BPMN-MESSAGE-POOL', 'Message flow must cross pool boundaries', l.item.ref);
            if (['flow.next', 'uml.flow'].includes(role(l.item)) && pool(l.from) && pool(l.to) && pool(l.from) !== pool(l.to))
                issue('DDN-BPMN-SEQUENCE-POOL', 'Sequence flow cannot cross pool boundaries', l.item.ref);
        }
        for (const n of nodes) {
            if (/gateway/.test(role(n)) && meta(n, 'x_gateway') === undefined)
                incomplete('Gateway type must be explicit', n.ref);
            if (role(n) === 'flow.gateway' && profileId !== 'bpmn.basic@1') {
                const control = links.filter(link => ['flow.next', 'uml.flow'].includes(role(link.item))), ins = incoming(n, control).length, outs = outgoing(n, control).length, type = object(meta(n, 'x_gateway')).type;
                if (review && (!ins || !outs || ins + outs < 3))
                    incomplete('Gateway needs incoming/outgoing sequence flow and a split or join', n.ref);
                if (['event', 'event_exclusive'].includes(text(type)) && (ins > 1 || review && outs < 2))
                    issue('DDN-BPMN-GATEWAY', 'Event gateways require one incoming flow and at least two outgoing flows', n.ref);
            }
            const event = object(meta(n, 'x_event'));
            if (Object.keys(event).length) {
                const position = text(event.position) || (/start/.test(role(n)) ? 'start' : /end/.test(role(n)) ? 'end' : /boundary/.test(role(n)) ? 'boundary' : 'intermediate');
                if (position === 'start' && ['terminate', 'cancel', 'error', 'compensation'].includes(text(event.type)) || position === 'end' && ['timer', 'conditional', 'link', 'parallel_multiple'].includes(text(event.type)))
                    issue('DDN-BPMN-TRIGGER', 'Event trigger is not legal at its position', n.ref);
                if (position === 'boundary') {
                    const target = selectedRef(event.on, n);
                    if (!target || !/process|activity|task/.test(role(target)))
                        issue('DDN-BPMN-BOUNDARY', 'Boundary event must attach to a selected activity', n.ref);
                }
            }
            if (/choreotask/.test(role(n))) {
                const bands = array(meta(n, 'x_bands'));
                if (review && (bands.length < 2 || bands.length > 6 || new Set(bands).size !== bands.length))
                    issue('DDN-BPMN-BANDS', 'Choreography requires 2..6 distinct participants', n.ref);
            }
        }
    }
    if (/^state\.|statemachine|^sdl\.process/.test(profileId)) {
        const initials = nodes.filter(n => /initial$|sdl.start$/.test(role(n))), terminals = nodes.filter(n => /final$|terminate$|stop$/.test(role(n)) || object(meta(n, 'x_state')).terminal === true);
        if (profileId === 'state.flat@1') {
            if (review && initials.length !== 1)
                issue('DDN-STATE-INITIAL', 'Flat state machine requires exactly one initial marker');
            if (review && !terminals.length)
                incomplete('Flat state machine requires a terminal state');
            for (const n of nodes)
                if (members(n).length)
                    issue('DDN-STATE-NESTING', 'Flat states do not contain members or regions', n.ref);
        }
        else {
            const regions = new Map();
            for (const n of initials) {
                const region = regionKey(n);
                regions.set(region, (regions.get(region) ?? 0) + 1);
            }
            if ([...regions.values()].some(n => n > 1))
                issue('DDN-STATE-REGION', 'Each region permits at most one initial marker');
        }
        for (const n of nodes) {
            const ins = incoming(n), outs = outgoing(n);
            if (initials.includes(n) && (ins.length || review && outs.length !== 1))
                issue('DDN-STATE-INITIAL-FLOW', 'Initial requires no incoming and one outgoing transition', n.ref);
            if (terminals.includes(n) && outs.length)
                issue('DDN-STATE-TERMINAL', 'Terminal state cannot have outgoing transitions', n.ref);
            if (/choice$/.test(role(n)) && review && outs.length < 2 || /junction$/.test(role(n)) && review && (!ins.length || !outs.length))
                issue('DDN-STATE-FAN', 'Pseudostate fan count is invalid', n.ref);
            if (/history|entrypoint|exitpoint|entry_point|exit_point/.test(role(n)) && !regionKey(n))
                incomplete('History and entry/exit points require a composite region', n.ref);
            const state = object(meta(n, 'x_state'));
            if (role(n) !== 'state.state' && ['entry', 'exit', 'do', 'internal'].some(name => state[name] !== undefined))
                issue('DDN-STATE-COMPARTMENT', 'State behavior compartments belong only to state.state', n.ref);
            const sub = state.submachine;
            if (sub !== undefined && (!resolve(sub, n) || resolve(sub, n) === n || role(resolve(sub, n)) !== 'state.state'))
                issue('DDN-STATE-SUBMACHINE', 'Submachine must reference a different state', n.ref);
        }
        if (profileId === 'state.flat@1' && review && initials.length && terminals.length) {
            const reachable = (origins, reverse) => {
                const seen = new Set(origins.map(key)), queue = [...origins];
                for (let i = 0; i < queue.length; i++)
                    for (const edge of reverse ? incoming(queue[i]) : outgoing(queue[i])) {
                        const next = reverse ? edge.from : edge.to;
                        if (!seen.has(key(next))) {
                            seen.add(key(next));
                            queue.push(next);
                        }
                    }
                return seen;
            };
            const from = reachable(initials, false), to = reachable(terminals, true);
            for (const node of nodes)
                if (!from.has(key(node)) || !to.has(key(node)))
                    issue('DDN-STATE-REACHABILITY', 'Every state must be reachable and able to reach a terminal', node.ref);
        }
        if (profileId === 'state.flat@1') {
            const transitionGroups = new Map();
            for (const l of links) {
                const t = object(meta(l.item, 'x_transition'));
                if (initials.includes(l.from)) {
                    if (t.event || t.guard !== undefined || array(t.actions).length)
                        issue('DDN-STATE-INITIAL-EFFECT', 'Initial transition must be unconditional and action-free', l.item.ref);
                }
                else if (!text(t.event))
                    incomplete('Noninitial transition requires an event', l.item.ref);
                if (t.effect !== undefined || typeof t.guard === 'string')
                    issue('DDN-STATE-EXECUTABLE-TEXT', 'Flat state evaluation accepts typed guard data and referenced actions only', l.item.ref);
                for (const action of array(t.actions))
                    if (!resolve(action, l.item))
                        issue('DDN-STATE-ACTION', 'Flat transition actions must resolve as references', l.item.ref);
                if (t.guard !== undefined && typeof t.guard !== 'string') {
                    const domains = decisionDomains(view, records);
                    if (!domains.length)
                        incomplete('Typed transition guards require declared input domains', l.item.ref);
                    else {
                        const checked = (0, analysis_js_1.analyzeDecision)(domains, [{ id: l.item.ref.id, inputs: {}, guard: t.guard, outputs: { state: l.to.ref.id } }], { hitPolicy: 'first', coverage: 'none' });
                        if (checked.outcome === 'invalid')
                            issue('DDN-STATE-GUARD', checked.errors.join('; '), l.item.ref);
                    }
                }
                const group = key(l.from) + ':' + text(t.event);
                transitionGroups.set(group, [...transitionGroups.get(group) ?? [], l]);
            }
            for (const group of transitionGroups.values())
                if (group.length > 1) {
                    const domains = decisionDomains(view, records);
                    const rules = group.map(l => ({ id: l.item.ref.id, inputs: {}, guard: object(meta(l.item, 'x_transition')).guard, outputs: { state: l.to.ref.id } }));
                    const analysis = (0, analysis_js_1.analyzeDecision)(domains, rules, { hitPolicy: 'unique', coverage: 'none', budget: finite((0, schema_core_js_1.getPath)(view.record, 'projection.options.analysis_budget')) ? (0, schema_core_js_1.getPath)(view.record, 'projection.options.analysis_budget') : 4096 });
                    if (analysis.outcome === 'budget_exceeded')
                        issue('DDN-ANALYSIS-BUDGET', 'Transition disjointness exceeded its bounded analysis budget', view.ref, 'warning');
                    else if (analysis.outcome === 'invalid')
                        issue('DDN-STATE-AMBIGUITY', 'Same-state/event alternatives are not provably disjoint', view.ref);
                }
        }
        if (profileId === 'sdl.process@1') {
            if (review && nodes.filter(n => role(n) === 'state.initial').length !== 1)
                issue('DDN-SDL-START', 'SDL process requires exactly one start');
            for (const n of nodes) {
                if (/^sdl\.(input|output|task|save|create|set|reset)$/.test(role(n)) && review && !outgoing(n).length)
                    incomplete('SDL process step needs an outgoing transition', n.ref);
                const timer = object(meta(n, 'x_sdl')).timer;
                if (timer !== undefined && role(resolve(timer, n) ?? n) !== 'sdl.timer')
                    issue('DDN-SDL-TIMER', 'Timer reference must resolve to sdl.timer', n.ref);
            }
        }
    }
    if (profileId.startsWith('uml.object'))
        for (const n of nodes.filter(n => role(n) === 'object' || meta(n, 'x_instance') !== undefined)) {
            const instance = object(meta(n, 'x_instance')), classifier = resolve(instance.classifier, n);
            if (!classifier) {
                incomplete('Instance must name a classifier', n.ref);
                continue;
            }
            const fields = members(classifier);
            for (const [name, value] of Object.entries(object(instance.slots))) {
                const field = fields.find(f => f.record.name === name);
                if (fields.length && !field)
                    issue('DDN-INSTANCE-SLOT', 'Slot does not belong to its declared classifier: ' + name, n.ref);
                if (field && profileId.endsWith('@2')) {
                    const type = text((0, schema_core_js_1.getPath)(field.record, 'content.datatype'));
                    if (/^(int|integer|number|float|double|real)/i.test(type) && !finite(value) || /^(bool)/i.test(type) && typeof value !== 'boolean')
                        issue('DDN-INSTANCE-TYPE', 'Slot value does not match the declared bounded datatype', n.ref);
                }
            }
        }
    if (/communication|c4.dynamic/.test(profileId)) {
        const numbers = [];
        for (const edge of edges) {
            const number = text(object(meta(edge, 'x_message')).seq);
            if (!/^\d+(?:\.\d+)*(?:[a-z])?$/.test(number))
                incomplete('Communication message requires explicit dotted sequence numbering', edge.ref);
            else
                numbers.push(number);
            if (object(meta(edge, 'x_message')).sort === 'reply' && number && !edges.some(request => request !== edge && object(meta(request, 'x_message')).sort !== 'reply' && number.startsWith(text(object(meta(request, 'x_message')).seq) + '.')))
                issue('DDN-MESSAGE-REPLY', 'Reply numbering must be dotted beneath an existing request number', edge.ref);
        }
        unique(numbers, 'DDN-MESSAGE-SEQUENCE', 'Communication sequence numbers must be unique');
    }
    if (profile.projection === 'sequence' || profile.projection === 'timing' || /communication|c4.dynamic/.test(profileId)) {
        for (const l of links) {
            if (!selected.has(key(l.from)) || !selected.has(key(l.to)) || l.ends.some(e => e.member !== undefined))
                issue('DDN-INTERACTION-ENDPOINT', 'Interaction endpoints must be selected participants', l.item.ref);
            const message = object(meta(l.item, 'x_message'));
            if (message.sort === 'lost' && message.gate !== 'target' || message.sort === 'found' && message.gate !== 'source')
                issue('DDN-MESSAGE-GATE', 'Lost/found messages require their respective target/source gate', l.item.ref);
        }
        for (const n of nodes) {
            if (profile.projection === 'sequence' && !incoming(n).length && !outgoing(n).length)
                issue('DDN-SEQUENCE-UNUSED', 'Selected lifeline has no messages', n.ref, 'warning');
            if (profile.projection === 'timing') {
                const states = array(meta(n, 'x_states'));
                let last = -Infinity;
                if (!states.length)
                    incomplete('Timing participants require state entries', n.ref);
                for (const state of states) {
                    const entry = object(state), at = Array.isArray(state) ? state[0] : entry.at ?? entry.time;
                    if (!finite(at) || at <= last || !(Array.isArray(state) ? typeof state[1] === 'string' : typeof (entry.state ?? entry.value) === 'string'))
                        issue('DDN-TIMING-ORDER', 'Timing states require named states and strictly increasing numeric times', n.ref);
                    else
                        last = at;
                }
            }
            for (const activation of array(meta(n, 'x_activation'))) {
                const a = resolve(object(activation).from, n), b = resolve(object(activation).to, n);
                if (!a || !b || !edges.includes(a) || !edges.includes(b) || edges.indexOf(a) > edges.indexOf(b))
                    issue('DDN-SEQUENCE-ACTIVATION', 'Activation anchors must resolve in message order', n.ref);
            }
            for (const invariant of array(meta(n, 'x_invariant')))
                if (!edges.includes(resolve(object(invariant).after, n)))
                    issue('DDN-SEQUENCE-INVARIANT', 'Invariant anchor must resolve to a selected message', n.ref);
        }
        const fragments = (value, owner, depth = 0) => {
            if (value === undefined)
                return;
            if (depth > 16) {
                issue('DDN-FRAGMENT-DEPTH', 'Fragment nesting exceeds 16', owner.ref);
                return;
            }
            const fragment = object(value), used = new Set();
            for (const operand of array(fragment.operands)) {
                for (const ref of array(object(operand).messages)) {
                    const message = resolve(ref, owner);
                    if (!message || !edges.includes(message))
                        issue('DDN-FRAGMENT-MESSAGE', 'Fragment message must resolve to selected interaction', owner.ref);
                    else if (used.has(key(message)))
                        issue('DDN-FRAGMENT-OVERLAP', 'Message cannot belong to overlapping sibling operands', owner.ref);
                    else
                        used.add(key(message));
                }
                for (const child of array(object(operand).fragments))
                    fragments(child, owner, depth + 1);
            }
        };
        for (const edge of edges)
            fragments(meta(edge, 'x_fragment'), edge);
    }
    if (profileId.startsWith('cmmn.')) {
        if (profileId === 'cmmn.complete@1' && review && nodes.filter(n => role(n) === 'cmmn.caseplan').length !== 1)
            issue('DDN-CMMN-CASEPLAN', 'Completed CMMN view requires exactly one case plan');
        for (const n of nodes.filter(n => role(n) === 'cmmn.sentry')) {
            const sentry = object(meta(n, 'x_sentry'));
            if (!['entry', 'exit'].includes(text(sentry.on)))
                incomplete('Sentry must declare entry or exit', n.ref);
            if ((!regionOwner(n) || role(regionOwner(n)) !== 'cmmn.stage'))
                incomplete('Sentry must belong to a stage', n.ref);
            for (const p of ['attach', 'on_part'])
                if (sentry[p] !== undefined && !selectedRef(sentry[p], n))
                    issue('DDN-CMMN-SENTRY', 'Sentry references must resolve in the selected case', n.ref);
        }
    }
    if (profileId.startsWith('sysml.')) {
        for (const n of nodes)
            for (const member of members(n))
                if (role(member) === 'core::Port' && meta(member, 'x_pin') === undefined && !(profileId.endsWith('@2') ? /^sysml\.(block|interfaceblock|constraint|valuetype|flowspec)$/.test(role(n)) : role(n) === 'sysml.block'))
                    issue('DDN-SYSML-PORT-OWNER', 'Port owner is not admitted by this SysML version', member.ref);
        if (profileId.startsWith('sysml.parametric'))
            for (const n of nodes.filter(n => role(n) === 'sysml.constraint')) {
                const bindings = links.filter(l => l.from === n || l.to === n);
                if (profileId.endsWith('@1') && bindings.length > 2)
                    issue('DDN-PARAMETRIC-BINDINGS', 'Version-1 constraints admit exactly two incident bindings', n.ref);
                else if (profileId.endsWith('@1') ? bindings.length < 2 : bindings.length < 1)
                    incomplete('Constraint has the wrong binding count for this profile version', n.ref);
            }
    }
    if (profileId === 'archimate.basic@1') {
        const layer = (n) => /business/.test(role(n)) ? 2 : /application/.test(role(n)) ? 1 : /technology/.test(role(n)) ? 0 : -1;
        for (const l of links)
            if (layer(l.from) > layer(l.to))
                issue('DDN-ARCHIMATE-LAYER', 'Only same-layer or upward serving relations are supported', l.item.ref);
    }
    if (profileId === 'pert.cpm@1') {
        try {
            if (review || nodes.every(n => finite(meta(n, 'x_estimate'))))
                (0, analysis_js_1.calculateCriticalPath)(nodes.map(n => ({ id: key(n), duration: meta(n, 'x_estimate') })), links.map(l => ({ id: key(l.item), from: key(l.from), to: key(l.to) })));
        }
        catch (error) {
            issue('DDN-CPM', error instanceof Error ? error.message : String(error));
        }
    }
    if (profileId === 'fault.tree@1' || profileId === 'event.tree@1') {
        cycle(links, 'DDN-GATE-CYCLE');
        for (const n of nodes.filter(n => /gate$/.test(role(n))))
            if (review && (!['and', 'or'].includes(text(object(meta(n, 'x_gate')).type)) || incoming(n).length < 2))
                incomplete('Gate needs an and/or type and at least two inputs', n.ref);
    }
    if (profileId.startsWith('network.')) {
        for (const l of links.filter(l => /attach/.test(role(l.item))))
            if (!/bus$/.test(role(l.to)) && !/bus$/.test(role(l.from)) && l.ends.every(e => e.member === undefined))
                issue('DDN-NETWORK-ATTACHMENT', 'Attachment requires a bus or declared port', l.item.ref);
        const slots = new Map();
        for (const n of nodes) {
            const rack = object(meta(n, 'x_rack'));
            if (rack.unit !== undefined && (profileId === 'network.rack@1' || regionOwner(n))) {
                const owner = regionOwner(n), max = owner && object(meta(owner, 'x_rack')).units;
                if (!owner || !finite(max) || !finite(rack.unit) || rack.unit > max)
                    issue('DDN-RACK-SLOT', 'Rack slot must be inside its declared rack', n.ref);
                else {
                    const used = slots.get(key(owner)) ?? new Set();
                    if (used.has(rack.unit))
                        issue('DDN-RACK-DUPLICATE', 'Rack slots must be unique', n.ref);
                    used.add(rack.unit);
                    slots.set(key(owner), used);
                }
            }
        }
    }
    if (profileId === 'wireframe.ui@1')
        for (const n of nodes.filter(n => role(n) !== 'ui.frame'))
            if ((!regionOwner(n) || role(regionOwner(n)) !== 'ui.frame'))
                issue('DDN-UI-FRAME', 'Control is not assigned to a UI frame', n.ref, 'warning');
    if (profileId === 'idef0.basic@1') {
        unique(nodes.map(n => text(object(meta(n, 'x_idef0')).node)), 'DDN-IDEF0-NUMBER', 'IDEF0 node codes must be unique');
        for (const n of nodes)
            for (const member of members(n)) {
                const icom = text(object(meta(member, 'x_icom')).type), rawSide = (0, schema_core_js_1.getPath)(member.record, 'content.side') ?? (0, schema_core_js_1.getPath)(member.record, 'properties.side'), side = { west: 'left', east: 'right', north: 'top', south: 'bottom' }[String(rawSide)] ?? rawSide;
                if (icom && side !== undefined && side !== { input: 'left', control: 'top', output: 'right', mechanism: 'bottom' }[icom])
                    issue('DDN-IDEF0-SIDE', 'ICOM pin type does not match its declared side', member.ref);
            }
    }
    if (profileId === 'petri.basic@1')
        for (const l of links)
            if (role(l.from) === role(l.to))
                issue('DDN-PETRI-BIPARTITE', 'Petri arcs must connect a place and transition', l.item.ref);
    if (profileId === 'orm.basic@1') {
        for (const n of nodes.filter(n => role(n) === 'orm.facttype'))
            if (!members(n).some(member => role(member) === 'field'))
                incomplete('Fact type requires at least one role field', n.ref);
        for (const link of links.filter(link => role(link.item) === 'orm.plays')) {
            const field = resolve(link.ends[0]?.member, link.item);
            if (!field)
                incomplete('ORM role-player relation requires a fact role field endpoint', link.item.ref);
            else if (role(field) !== 'field' || !members(link.from).includes(field) || link.ends[1]?.member !== undefined)
                issue('DDN-ORM-ROLE-ENDPOINT', 'ORM player links run from a fact role field to an entity/value player', link.item.ref);
        }
    }
    if (profileId === 'fbd.basic@1')
        for (const l of links) {
            const a = resolve(l.ends[0]?.member, l.item), b = resolve(l.ends[1]?.member, l.item);
            if (!a || !b)
                incomplete('Function block wires require pin endpoints', l.item.ref);
            else {
                const type = (n) => text((0, schema_core_js_1.getPath)(n.record, 'metadata.x_fbd.type'));
                for (const pin of [a, b])
                    if ((0, schema_core_js_1.getPath)(pin.record, 'metadata.x_fbd.negated') === true && type(pin) !== 'BOOL')
                        issue('DDN-FBD-NEGATION', 'Only BOOL pins can be negated', pin.ref);
                if (type(a) !== type(b) || !['BOOL', 'INT', 'DINT', 'REAL', 'TIME', 'STRING', 'WORD'].includes(type(a)))
                    issue('DDN-FBD-TYPE', 'Wire pin datatypes must match the supported FBD types', l.item.ref);
            }
        }
    if (profileId === 'ladder.basic@1') {
        const layout = (0, schema_core_js_1.getPath)(view.record, 'layout.algorithm');
        if (layout !== undefined && layout !== 'ladder')
            issue('DDN-LADDER-LAYOUT', 'Ladder diagrams require ladder layout');
        const rungs = new Map();
        for (const n of nodes) {
            const rung = regionKey(n);
            rungs.set(rung, [...rungs.get(rung) ?? [], n]);
        }
        for (const rung of rungs.values())
            if (review && rung.filter(n => role(n) === 'ladder.coil').length !== 1)
                issue('DDN-LADDER-COIL', 'Each rung requires exactly one output coil');
        for (const l of links)
            if (/series/.test(role(l.item)) && regionKey(l.from) !== regionKey(l.to))
                issue('DDN-LADDER-RUNG', 'Series links must stay in one rung', l.item.ref);
    }
    if (profileId === 'state.flat@1' && array((0, schema_core_js_1.getPath)(view.record, 'projection.options.traces')).length) {
        const traceResult = object((0, analysis_profile_js_1.flatTraceAnalysis)(view, records));
        if (traceResult.outcome === 'budget_exceeded')
            issue('DDN-ANALYSIS-BUDGET', 'Flat trace evaluation exceeded its work budget', view.ref, 'warning');
        else if (traceResult.outcome === 'incomplete')
            incomplete('Trace requires a declared expected final state');
        else if (traceResult.outcome !== 'valid')
            issue('DDN-STATE-TRACE', 'Declared trace failed input, transition or expected final-state validation');
    }
    else if (profileId !== 'state.flat@1' && array((0, schema_core_js_1.getPath)(view.record, 'projection.options.traces')).length)
        issue('DDN-STATE-TRACE-PROFILE', 'Trace evaluation is available only for state.flat@1');
    if (profileId === 'decision.rules@1') {
        const rules = decisionRules(view, records);
        for (const message of decisionOutputErrors(view, records, rules))
            issue('DDN-DECISION-OUTPUTS', message);
        const options = object((0, schema_core_js_1.getPath)(view.record, 'projection.options')), domains = decisionDomains(view, records);
        if (review || domains.length) {
            const analysis = (0, analysis_js_1.analyzeDecision)(domains, rules, { hitPolicy: text(options.hit_policy) || 'unique', coverage: text(options.coverage) || 'report', budget: finite(options.analysis_budget) ? options.analysis_budget : 4096 });
            if (analysis.outcome === 'budget_exceeded')
                issue('DDN-ANALYSIS-BUDGET', 'Decision proof exceeded its analysis budget', view.ref, 'warning');
            else if (analysis.outcome === 'invalid')
                issue('DDN-DECISION-RULES', analysis.errors.join('; ') || 'Decision overlap or coverage obligation failed');
            else if (analysis.uncovered.length)
                issue('DDN-DECISION-GAPS', 'Decision table has uncovered input cells', view.ref, 'warning');
        }
    }
    result.push(...(0, projection_rules_js_1.projectionDiagnostics)(view, records, review));
    return result;
}
function decisionDomains(view, records) {
    const { resolve } = profileSelection(view, records);
    return array((0, schema_core_js_1.getPath)(view.record, 'projection.options.inputs')).flatMap((ref, index) => {
        const target = resolve(ref), raw = target && (0, schema_core_js_1.getPath)(target.record, 'content.allowed_values');
        const name = typeof ref === 'string' ? ref : target ? text(target.record.name) || target.ref.id : '';
        if (!name || raw === undefined)
            return [{ name: name || 'input' + index, type: 'enum', values: [] }];
        if (Array.isArray(raw))
            return [{ name, type: 'enum', values: raw }];
        const d = object(raw);
        if (!['enum', 'boolean', 'number'].includes(text(d.type)))
            return [{ name, type: 'enum', values: [] }];
        return [{ name, type: d.type, ...(Array.isArray(d.values) ? { values: d.values } : {}), ...(finite(d.min) ? { min: d.min } : {}), ...(finite(d.max) ? { max: d.max } : {}), nullable: d.nullable === true, optional: d.optional === true }];
    });
}
function decisionRules(view, records) {
    const { nodes } = profileSelection(view, records);
    if ((0, schema_core_js_1.getPath)(view.record, 'projection.options.records') !== undefined)
        return (0, projection_rules_js_1.projectionRows)(view, records).map((row, index) => {
            const source = records.find(record => record.file === row.source.file && record.ref.id === row.source.id);
            const values = source?.owner === 'data' || source?.record.data !== undefined ? row.values : object((0, schema_core_js_1.getPath)(source?.record, 'metadata.x_rule'));
            return { id: row.source.file + '\0' + row.source.id + '#' + index, inputs: object(values.inputs), outputs: object(values.outputs) };
        });
    return nodes.filter(n => role(n) === 'rule.row').map(n => ({ id: key(n), inputs: object(object(meta(n, 'x_rule')).inputs), outputs: object(object(meta(n, 'x_rule')).outputs) }));
}
function decisionOutputErrors(view, records, rules) {
    const declared = (0, schema_core_js_1.getPath)(view.record, 'projection.options.outputs');
    if (declared === undefined)
        return [];
    const { resolve } = profileSelection(view, records), names = array(declared).map(reference => typeof reference === 'string' ? reference : text(resolve(reference)?.record.name) || resolve(reference)?.ref.id || '');
    if (!names.length || names.length > 20 || names.some(name => !name) || new Set(names).size !== names.length)
        return ['Output declarations require 1..20 unique names or resolved references'];
    return rules.some(rule => Object.keys(rule.outputs).length !== names.length || names.some(name => !Object.hasOwn(rule.outputs, name))) ? ['Every rule must supply exactly the declared output keys'] : [];
}

}});})();
