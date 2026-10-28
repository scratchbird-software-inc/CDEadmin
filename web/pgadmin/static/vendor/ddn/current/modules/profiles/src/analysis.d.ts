import type { Json } from '../../types/src/core.js';
export interface DecisionDomain {
    name: string;
    type: 'enum' | 'boolean' | 'number';
    values?: readonly Json[];
    min?: number;
    max?: number;
    nullable?: boolean;
    optional?: boolean;
}
export interface DecisionRule {
    id: string;
    inputs: Readonly<Record<string, Json>>;
    outputs: Readonly<Record<string, Json>>;
    guard?: Json | undefined;
}
export interface DecisionAnalysis {
    outcome: 'valid' | 'invalid' | 'budget_exceeded';
    tested: number;
    overlaps: readonly string[][];
    uncovered: readonly Record<string, Json>[];
    errors: readonly string[];
    firstHit: {
        outcome: 'complete' | 'unknown' | 'not-applicable';
        shadowed: readonly string[] | null;
    };
}
export declare function decisionInputErrors(domains: readonly DecisionDomain[], values: Readonly<Record<string, Json>>): string[];
/** Predicates are data. No author text is evaluated as JavaScript or an expression language. */
export declare function matchPredicate(value: Json | undefined, predicate: Json | undefined): boolean;
export declare function matchGuard(values: Readonly<Record<string, Json>>, guard: Json | undefined): boolean;
export declare function analyzeDecision(domains: readonly DecisionDomain[], rules: readonly DecisionRule[], options?: {
    hitPolicy?: string;
    coverage?: string;
    budget?: number;
}): DecisionAnalysis;
export declare function evaluateDecision(rules: readonly DecisionRule[], values: Readonly<Record<string, Json>>, hitPolicy?: string): {
    annotation?: string;
    outcome: "valid" | "unsupported-policy" | "ambiguous";
    hitPolicy: string;
    policyEvaluated: boolean;
    matches: string[];
    outputs: Readonly<Record<string, Json>>[];
    valid: boolean;
};
export interface FlatTransition {
    id: string;
    from: string;
    to: string;
    event?: string;
    guard?: Json;
    actions?: readonly Json[];
}
export declare function evaluateFlatTrace(initial: string, transitions: readonly FlatTransition[], events: readonly {
    event: string;
    values?: Readonly<Record<string, Json>>;
}[], budget?: number, options?: {
    domains?: readonly DecisionDomain[];
    expectedFinalState?: string;
}): {
    expectedFinalState?: string;
    expectedMatched?: boolean;
    outcome: "valid" | "budget_exceeded" | "ambiguous" | "unmatched" | "invalid-input" | "unexpected-final-state" | "limit-exceeded";
    state: string;
    steps: {
        transition: string;
        state: string;
        actions: readonly Json[];
    }[];
    actionsExecuted: false;
};
export declare function calculateCriticalPath(tasks: readonly {
    id: string;
    duration: number;
}[], links: readonly {
    id: string;
    from: string;
    to: string;
}[]): {
    duration: number;
    tasks: {
        id: string;
        duration: number;
        es: number;
        ef: number;
        ls: number;
        lf: number;
        slack: number;
        critical: boolean;
    }[];
    criticalEdges: string[];
};
