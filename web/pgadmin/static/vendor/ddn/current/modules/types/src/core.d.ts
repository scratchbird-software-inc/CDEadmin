import type { SceneItem, ScenePatch } from './scene.js';
/** DDN utility ABI candidate 1.0; declarations only, no implementation.
 * Normalized records and property paths MUST conform to ddn-next-1/ddn.schema.json.
 * This API transport declaration is not a second language schema. */
export type Json = null | boolean | number | string | readonly Json[] | { readonly [key: string]: Json };
export type FileId = string;
export type EntityId = string;
export type ProfileId = string;
export type Revision = string;
export type Fingerprint = string;
export interface Ref { readonly file: FileId; readonly id: EntityId }
export interface Span { readonly file: FileId; readonly revision: Revision; readonly start: number; readonly end: number }
/** UTF-16 code-unit offsets into decoded text. Byte encoding/BOM/newlines are preserved separately. */
export interface SourceFile {
  readonly id: FileId; readonly text: string; readonly revision: Revision;
  readonly originalBytes?: Uint8Array; readonly encoding: 'utf-8'; readonly writable: boolean;
}
export interface SourceSet { readonly entry: FileId; readonly files: readonly SourceFile[] }
export type Scope = { readonly kind: 'workarea' } | { readonly kind: 'item' | 'view' | 'document'; readonly target: Ref };
export interface RevisionVector {
  readonly model: Revision;
  readonly sources: Readonly<Record<FileId, Revision>>;
  readonly data: Readonly<Record<string, Revision>>;
}
export interface VersionSet {
  readonly api: '1.0'; readonly language: string; readonly defaults: string;
  readonly packs: Readonly<Record<string, string>>;
}
/** Opaque validated normalized envelope; exact payload definition is the property-codex schema. */
export interface ModelSnapshot {
  readonly contract: 'ddn-next-1'; readonly rootFile: FileId;
  readonly revision: RevisionVector; readonly versions: VersionSet;
  readonly semanticFingerprint: Fingerprint; readonly normalized: Json;
  readonly coverage: Coverage;
}
export interface Coverage {
  readonly scope: Scope; readonly complete: boolean;
  readonly checked: readonly Ref[]; readonly unavailable: readonly string[];
}
export interface CancelToken { readonly aborted: boolean; onAbort(handler: () => void): () => void }
export interface Budget { readonly elapsedMs: number; readonly workUnits: number; readonly memoryBytes: number }
export interface TaskOptions { readonly cancel?: CancelToken; readonly budget?: Budget }
export interface Diagnostic {
  readonly code: string; readonly severity: 'info' | 'warning' | 'error'; readonly message: string;
  readonly source?: Span; readonly target?: Ref; readonly occurrences?: readonly string[];
  readonly rule?: string; readonly related?: readonly Span[];
}
export type Outcome = 'valid' | 'invalid' | 'incomplete' | 'unsupported' | 'budget-exceeded' | 'cancelled' | 'stale';
export type CheckLevel = 'decode' | 'structural' | 'semantic' | 'review' | 'publication';
export interface MeasurementEvidence {
  readonly fingerprint: Fingerprint; readonly versions: VersionSet;
  readonly revision: RevisionVector; readonly fontGeneration: string;
  readonly coverage: Coverage; readonly measurements: Json;
}
export interface VerifyOptions extends TaskOptions {
  readonly scope: Scope; readonly purpose: string; readonly level: CheckLevel;
  readonly measurement?: MeasurementEvidence;
}
export interface VerificationReport {
  readonly requestId: string; readonly outcome: Outcome;
  readonly revision: RevisionVector; readonly versions: VersionSet;
  readonly dependencyFingerprint: Fingerprint; readonly scope: Scope;
  readonly purpose: string; readonly level: CheckLevel; readonly coverage: Coverage;
  readonly diagnostics: readonly Diagnostic[]; readonly missing: readonly string[];
  readonly ruleVersions: Readonly<Record<string, string>>; readonly reviewEligible: boolean;
  readonly stats: { readonly elapsedMs: number; readonly workUnits: number; readonly cacheHits: number };
}
export type Status = 'draft' | 'in-progress' | 'in-review' | 'accepted';
export interface AcceptanceEvent { readonly user: string; readonly timestamp: string; readonly authorityContext: string }
export interface TransitionRequest {
  readonly target: Ref; readonly from: Status; readonly to: Status;
  readonly report?: VerificationReport; readonly acceptance?: AcceptanceEvent;
  readonly grants: readonly string[];
}
export interface Eligibility { readonly allowed: boolean; readonly diagnostics: readonly Diagnostic[] }
export interface Verifier {
  verifySources(input: SourceSet, options: VerifyOptions): Promise<VerificationReport>;
  verifyModel(input: ModelSnapshot, options: VerifyOptions): Promise<VerificationReport>;
  checkTransition(input: ModelSnapshot, transition: TransitionRequest, options?: TaskOptions): Promise<Eligibility>;
  destroy(): void;
}
export interface PackManifest {
  readonly id: string; readonly version: string; readonly api: '1.0'; readonly hash: string;
  readonly languages: readonly string[]; readonly defaults: readonly string[];
  readonly profiles: readonly ProfileId[]; readonly dependencies: readonly string[];
  readonly capabilities: readonly string[];
}
/** Trusted host-supplied code, never executable payload from a DDN source. */
export interface Pack { readonly manifest: PackManifest; readonly registrations: PackRegistrations }
export interface Registry {
  install(pack: Pack): void;
  describe(): readonly PackManifest[];
  supports(capability: string, profile?: ProfileId): boolean;
}
export interface Executor {
  run(job: ComputeRequest, options?: TaskOptions): Promise<ComputeResult>;
  destroy(): void;
}
export interface ComputeRequest {
  readonly protocol: 1; readonly sessionId: string; readonly jobId: string;
  readonly kind: 'decode' | 'verify' | 'project' | 'layout' | 'route' | 'capture';
  readonly revision: RevisionVector; readonly versions: VersionSet;
  readonly dependencyFingerprint: Fingerprint; readonly fontGeneration: string; readonly styleGeneration: string;
  readonly payload: Json;
}
export interface ComputeResult {
  readonly request: Omit<ComputeRequest, 'payload'>; readonly outcome: Outcome;
  readonly coverage: Coverage; readonly diagnostics: readonly Diagnostic[]; readonly payload: Json;
}
export interface RuntimeOptions {
  readonly versions: VersionSet; readonly packs: readonly Pack[]; readonly executor?: Executor;
  readonly limits?: Budget;
}
export interface OpenResult {
  readonly revision: RevisionVector; readonly snapshot?: ModelSnapshot;
  readonly diagnostics: readonly Diagnostic[]; readonly coverage: Coverage;
}
export type DataChange =
  | { readonly kind: 'replace'; readonly source: string; readonly next: Revision; readonly schema: Json; readonly rows: readonly Json[] }
  | { readonly kind: 'keyed'; readonly source: string; readonly base: Revision; readonly next: Revision;
      readonly operations: readonly ({ readonly op: 'upsert'; readonly key: string; readonly row: Json } | { readonly op: 'delete'; readonly key: string })[] };
export interface ExternalUpdate {
  readonly base: RevisionVector; readonly origin: string;
  readonly sources?: readonly SourceFile[]; readonly data?: readonly DataChange[];
}
export interface RuntimeEvent { readonly kind: 'revision' | 'diagnostics' | 'capabilities' | 'disposed'; readonly revision?: RevisionVector; readonly diagnostics?: readonly Diagnostic[] }
export interface Runtime {
  readonly registry: Registry; readonly verifier: Verifier;
  open(input: SourceSet | ModelSnapshot, options?: TaskOptions): Promise<OpenResult>;
  snapshot(): ModelSnapshot | undefined;
  sources(): SourceSet | undefined;
  /** Host/provider route; not exposed as a viewer editing action. Enforces base/lifecycle policy. */
  ingest(update: ExternalUpdate, options?: TaskOptions): Promise<OpenResult>;
  subscribe(listener: (event: RuntimeEvent) => void): () => void;
  destroy(): void;
}
export declare function createRuntime(options: RuntimeOptions): Runtime;
export declare function createVerifier(options: RuntimeOptions): Verifier;

export interface SourcePatch { readonly file: FileId; readonly base: Revision; readonly start: number; readonly end: number; readonly text: string }
export interface DependencyRead { readonly target: Ref; readonly path: string; readonly fingerprint: Fingerprint }
export type CommandIntent =
  | { readonly kind: 'create-definition'; readonly file: FileId; readonly role: string; readonly properties?: Readonly<Record<string, Json>> }
  | { readonly kind: 'create-occurrence'; readonly view: Ref; readonly target: Ref; readonly properties?: Readonly<Record<string, Json>> }
  | { readonly kind: 'remove'; readonly target: Ref; readonly references: 'retain-diagnostic' | 'remove-dependents' }
  | { readonly kind: 'rename'; readonly target: Ref; readonly name: string }
  | { readonly kind: 'set-property'; readonly target: Ref; readonly path: string; readonly value: Json }
  | { readonly kind: 'reset-property'; readonly target: Ref; readonly path: string }
  | { readonly kind: 'edit-source'; readonly patches: readonly SourcePatch[] }
  | { readonly kind: 'convert-body'; readonly target: Ref; readonly interpretation: 'field-list' | 'header-table' }
  | { readonly kind: 'connect'; readonly view: Ref; readonly from: Ref; readonly to: Ref; readonly relation?: string; readonly properties?: Readonly<Record<string, Json>> }
  | { readonly kind: 'status'; readonly transition: TransitionRequest }
  | { readonly kind: 'profile-command'; readonly profile: ProfileId; readonly command: string; readonly target: Ref; readonly arguments: Json };
/** Profile-command IDs and argument schemas are mandatory registered descriptors;
 * they cover row/column edits, reconnect, placements, layout, documents and data bindings. */
export interface PreparedCommand {
  readonly id: string; readonly base: RevisionVector; readonly intent: CommandIntent;
  readonly readSet: readonly DependencyRead[]; readonly writeSet: readonly Ref[];
  readonly patches: readonly SourcePatch[]; readonly modelDelta: Json;
  readonly summary: readonly string[]; readonly diagnostics: readonly Diagnostic[];
  readonly protectedScopes: readonly Ref[]; readonly eligible: boolean;
}
export interface CommitReceipt { readonly commandId: string; readonly before: RevisionVector; readonly after: RevisionVector; readonly changed: readonly Ref[] }
export interface CommandFailure { readonly code: 'invalid' | 'conflict' | 'unauthorized' | 'cancelled' | 'unsupported' | 'budget-exceeded'; readonly diagnostics: readonly Diagnostic[] }
export type PrepareResult = { readonly ok: true; readonly command: PreparedCommand } | { readonly ok: false; readonly failure: CommandFailure };
export type CommitResult = { readonly ok: true; readonly receipt: CommitReceipt } | { readonly ok: false; readonly failure: CommandFailure };
export interface CommandService {
  prepare(intent: CommandIntent, options?: TaskOptions): Promise<PrepareResult>;
  commit(preparedId: string, options?: TaskOptions): Promise<CommitResult>;
  undo(options?: TaskOptions): Promise<CommitResult>;
  redo(options?: TaskOptions): Promise<CommitResult>;
  discard(preparedId: string): void;
}
export interface AuthorityProvider { authorize(action: string, scope: readonly Ref[], revision: RevisionVector): Promise<{ readonly allowed: boolean; readonly principal: string; readonly grants: readonly string[] }> }

/** All callback-bearing definitions below are trusted installed code. The worker
 * gets the installed module ID plus cloneable inputs, never these functions. */
export interface ComputationContext {
  readonly task: TaskOptions; readonly versions: VersionSet;
  /** Accounts work, checks cancellation/budgets, and yields to a task when needed. */
  checkpoint(workUnits: number): Promise<void>;
}
export interface RuleResult {
  readonly outcome: Outcome; readonly diagnostics: readonly Diagnostic[];
  readonly dependencies: readonly DependencyRead[]; readonly coverage: Coverage;
}
export interface RuleDefinition {
  readonly id: string; readonly version: string; readonly profiles: readonly ProfileId[];
  readonly levels: readonly CheckLevel[]; readonly purposes: readonly string[];
  readonly readPaths: readonly string[]; readonly globalScope: boolean;
  evaluate(input: ModelSnapshot, options: VerifyOptions, context: ComputationContext): Promise<RuleResult>;
}
export interface ProfileDescriptor {
  readonly id: ProfileId; readonly method: string; readonly inherits?: ProfileId;
  readonly roles: readonly string[]; readonly relations: readonly string[];
  readonly ruleIds: readonly string[]; readonly projectionId: string;
  readonly commandIds: readonly string[]; readonly schemaIds: readonly string[];
  readonly codexHash: string; readonly boundedScope: string; readonly exclusions: readonly string[];
}
export interface CommandDescriptor {
  readonly id: string; readonly profiles: readonly ProfileId[];
  readonly argumentSchemaId: string; readonly propertyPaths: readonly string[];
  readonly editor: 'property' | 'text' | 'table' | 'relation' | 'geometry' | 'specialized';
  readonly adapterId?: string;
  /** Pure preparation; registry never grants permission to commit directly. */
  prepare(input: ModelSnapshot, intent: CommandIntent, context: ComputationContext): Promise<PrepareResult>;
}
export interface MetricRequest { readonly id: string; readonly text: string; readonly fontKey: string; readonly constraints: Json }
export interface ProjectionInput {
  readonly snapshot: ModelSnapshot; readonly scope: Scope; readonly resolvedProperties: Json;
  readonly fontGeneration: string; readonly styleGeneration: string;
  readonly previous?: readonly SceneItem[];
}
export interface ProjectionDefinition {
  readonly id: string; readonly profiles: readonly ProfileId[]; readonly readPaths: readonly string[];
  measure(input: ProjectionInput, context: ComputationContext): Promise<readonly MetricRequest[]>;
  project(input: ProjectionInput, metrics: MeasurementEvidence, context: ComputationContext): Promise<ScenePatch>;
}
export interface PackRegistrations {
  readonly profiles?: readonly ProfileDescriptor[];
  readonly rules?: readonly RuleDefinition[];
  readonly commands?: readonly CommandDescriptor[];
  readonly projections?: readonly ProjectionDefinition[];
  readonly schemas?: Readonly<Record<string, Json>>;
}
