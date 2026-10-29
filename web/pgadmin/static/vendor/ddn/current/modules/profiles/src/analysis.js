import { isRecord, stableStringify } from './schema-core.js';
const finite = (v) => typeof v === 'number' && Number.isFinite(v);
const equal = (a, b) => a === undefined || b === undefined ? a === b : stableStringify(a) === stableStringify(b);
export function decisionInputErrors(domains, values) {
    const errors = Object.keys(values).filter(name => !domains.some(domain => domain.name === name)).map(name => 'Undeclared input: ' + name);
    for (const domain of domains) {
        const value = values[domain.name];
        const valid = value === undefined ? domain.optional : value === null ? domain.nullable : domain.type === 'boolean' ? typeof value === 'boolean' : domain.type === 'number' ? finite(value) && value >= (domain.min ?? -Infinity) && value <= (domain.max ?? Infinity) : domain.values?.some(candidate => equal(candidate, value));
        if (!valid)
            errors.push('Input is missing or outside its declared domain: ' + domain.name);
    }
    return errors;
}
/** Predicates are data. No author text is evaluated as JavaScript or an expression language. */
export function matchPredicate(value, predicate) {
    if (predicate === undefined)
        return true;
    if (!isRecord(predicate))
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
export function matchGuard(values, guard) {
    if (guard === undefined || guard === true)
        return true;
    if (guard === false || !isRecord(guard))
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
    if (!isRecord(p) && !inDomain(p))
        return 'Predicate value is outside its input domain';
    if (isRecord(p)) {
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
export function analyzeDecision(domains, rules, options = {}) {
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
            if (!values.length || values.length > 30 || values.some(v => v === null || typeof v === 'object' || v === undefined) || new Set(values.map(stableStringify)).size !== values.length)
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
                // Guard predicates contribute the same numeric partition boundaries
                // as column predicates, including intervals and membership sets.
                const predicateValues = (predicate) => {
                    if (!isRecord(predicate)) {
                        if (predicate !== undefined)
                            boundaryValues.push(predicate);
                        return;
                    }
                    for (const candidate of [predicate.value, predicate.min, predicate.max, ...(Array.isArray(predicate.values) ? predicate.values : [])])
                        if (candidate !== undefined)
                            boundaryValues.push(...Array.isArray(candidate) ? candidate : [candidate]);
                };
                const collect = (g, depth = 0) => {
                    if (!isRecord(g) || depth > 32)
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
            if (depth > 32 || !isRecord(guard)) {
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
    const costOfGuard = (guard, depth = 0) => !isRecord(guard) ? 1 : depth > 32 ? 50001 : 1 + Object.values(guard).reduce((cost, v) => cost + (Array.isArray(v) ? v.reduce((sum, g) => sum + costOfGuard(g, depth + 1), 0) : isRecord(v) ? costOfGuard(v, depth + 1) : 1), 0);
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
    // A rule is shadowed only if it matches a declared input but is never
    // selected first. An incomplete partition walk cannot prove this absence.
    const firstHit = options.hitPolicy === 'first' && !exhausted ? { outcome: 'complete', shadowed: rules.filter(rule => matched.has(rule.id) && !firstSelected.has(rule.id)).map(rule => rule.id) } : firstHitUnknown;
    return { outcome: exhausted ? 'budget_exceeded' : options.hitPolicy === 'unique' && overlaps.length || ['error', 'complete'].includes(options.coverage ?? '') && uncovered.length ? 'invalid' : 'valid', tested, overlaps, uncovered, errors, firstHit };
}
export function evaluateDecision(rules, values, hitPolicy = 'unique') {
    const matches = rules.filter(rule => Object.entries(rule.inputs).every(([name, predicate]) => matchPredicate(values[name], predicate)) && matchGuard(values, rule.guard));
    const supported = ['unique', 'first', 'collect'].includes(hitPolicy);
    return { outcome: !supported ? 'unsupported-policy' : hitPolicy === 'unique' && matches.length > 1 ? 'ambiguous' : 'valid', hitPolicy, policyEvaluated: supported, matches: matches.map(r => r.id), outputs: supported ? (hitPolicy === 'first' ? matches.slice(0, 1) : matches).map(r => r.outputs) : [], valid: supported && (hitPolicy !== 'unique' || matches.length <= 1), ...(!supported ? { annotation: 'This policy is retained for table presentation and ordered matching; it has no local executable semantics in the bounded DDN contract.' } : {}) };
}
export function evaluateFlatTrace(initial, transitions, events, budget = 4096, options = {}) {
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
export function calculateCriticalPath(tasks, links) {
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
//# sourceMappingURL=analysis.js.map