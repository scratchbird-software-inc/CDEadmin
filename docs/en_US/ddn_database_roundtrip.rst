DDN database discovery, generation and metadata differences
***********************************************************

Owner requirements and scope
============================

Owner direction, 2026-10-10: DDN originated as an ERD/data-design tool, originally
named Data Designer Notation. Its wider diagramming capabilities do not narrow
ScratchRobin's required database-design use. This document owns the cross-engine
bidirectional contract; ``firebird_functional_completion.rst`` references it for
Firebird implementation. Requirements below are accepted product requirements,
not a declaration of implemented or qualified support.

The required paths are:

* Live object/database/server metadata and selected data -> DDN source workspace
  -> one or more linked diagrams, data views and dashboards.
* Authored or imported DDN source -> resolved native metadata model -> native
  creation statements, preview and optional explicit application.
* Desired DDN metadata compared with live or saved baseline metadata -> semantic
  differences -> ordered engine-native migration statements and execution plan.

DDN owns notation, model validation, display and visual editing. ScratchRobin
owns database discovery, engine/version mappings, data acquisition, permissions,
identity, native statement generation and application. Use the sister project's
public tools and APIs; do not build a competing visual editor.

Shared conversion boundary for every engine
===========================================

Owner clarification, 2026-10-11: every supported engine requires conversion for
both DDN display and manual design. Share the conversion orchestration, document
validation, design refresh, provenance and review lifecycle. Supply separate
engine/version/dialect adapters for discovery, native model interpretation,
semantic differences, statement generation, execution and rediscovery. Reusing
forms or DDN transport must not reduce native coverage to a common SQL subset or
advertise features absent from an engine. Adapter qualification is per engine;
Firebird evidence does not qualify another engine.

Perform metadata discovery, metadata/document conversion, native semantic
comparison and statement compilation on the server. The browser edits source,
displays DDN output and presents review results. The shared ``ddn_design_merge``
workspace action performs conservative three-way source reconciliation using the
paired public parser and validates every resulting view on the server. It is
available through authenticated, owner-authorized provider workspaces and does
not connect to a database or execute statements. A merge accepts three bounded
DDN source workspaces; conflicts leave all inputs unchanged. Resulting documentary
content still requires engine-specific, target-bound native review and explicit
application. Timeout, resource exhaustion, unsupported imports or invalid source
must return failure without replacing the draft.

DDNA/DDNN interpretation must use the corresponding sister-project public
contracts when admitted by an adapter. Do not treat a source file extension as
native execution authority, flatten automation or narrative content into SQL,
or claim format conversion solely because the DDN source renderer accepts a
workspace. Preserve format/version and declared semantics; report unsupported
conversion explicitly. The source-workspace refresh action admits DDN source,
not DDNA/DDNN execution.

Discovery and source generation
===============================

DDN-DB-001 — Scope and completeness
  Accept selected object, subtree, database, selected databases or entire server.
  A server identity includes endpoint and port, not just physical hostname.
  Respect actual engine namespaces: do not invent schemas in engines without
  them. Include server-level and database-level entities, system/user distinction,
  persistent SQL objects, subobjects, dependencies, grants, native storage and
  programming entities where supported and visible. Full-system coverage is not
  limited to tables and foreign keys. Report each category as complete, partial,
  inaccessible, unsupported or failed; never equate denied visibility with empty.

DDN-DB-002 — Consistent observations
  Record engine/version, endpoint/database identities, discovery time and scope,
  provider/dialect revision, completeness and available catalog revision tokens.
  Use a consistent read where the engine supports it. Report concurrent changes
  and retry or mark uncertainty when it does not. A multi-database/server scan
  must not claim a single atomic snapshot unless the engine actually provides it.

DDN-DB-003 — Lossless native metadata
  Retain exact names, qualification, case/quoting, types and their attributes,
  defaults versus computed expressions, identities/sequences, nullability,
  constraints, index details, routine signatures/bodies, trigger event/timing/
  order, comments, grants and engine-specific properties. Preserve supported
  UUID/native identities, including ScratchBird UUIDv7 identities; do not invent
  persistent native IDs for engines that lack them. Use stable adapter IDs and
  explicit provenance where necessary. Never reduce native types to generic
  diagram types for regeneration. Name normalization for labels is presentation
  only and cannot change generated SQL identifiers.

DDN-DB-004 — DDN source and mapping contracts
  Generate valid editable DDN scripts, with deterministic identifiers, ordering,
  source locations and references. Support multi-file workspaces and imports for
  large systems. DDN source is the exchange/editing artifact, not rendered SVG.
  Persist it through the existing versioned project asset infrastructure.
  Define and version an admitted mapping for every native property: public DDN
  construct or approved extension with round-trip preservation. Unsupported
  mappings produce explicit diagnostics and block claims of lossless generation.
  Do not silently discard properties or hide the only authoritative metadata in
  private side files inaccessible to DDN readers. Necessary DDN extensions must
  be agreed with its team before relying on invented syntax or internal fields.

DDN-DB-005 — Data acquisition and binding
  Support actual database data as well as metadata: selected tables/queries,
  samples, aggregates, relationships and dashboard measurements. Make metadata
  only, sample, aggregate, selected/full data and live-binding modes explicit.
  Obtain data through authorized native providers, preserving NULL, precision,
  time-zone, binary/LOB and other native types. Bound and stream large transfers;
  report selection, truncation and coverage. Do not automatically dump all rows
  when a user diagrams a server. Never embed passwords or connection secrets in
  scripts. Retain data separately or reference it only through supported DDN
  constructs with portable resolution rules; distinguish a static export from a
  live provider binding. Imported scripts do not authorize arbitrary data reads.

DDN-DB-006 — Multiple coordinated views
  Generate server overview, database/schema/object detail, ERD, dependencies,
  security/storage/programming views and data/dashboard views as appropriate.
  Views share underlying identities rather than duplicating physical objects.
  Support filters, grouping, drill-down and links back to native tree/form context.
  Keep system objects distinguishable. Preserve authored layout, annotations and
  views when refreshing native metadata; present conflicts instead of replacing
  user work. A filtered, hidden, collapsed or unloaded object remains in the
  underlying model and must never become a schema deletion instruction.

DDN input and native creation
============================

DDN-DB-007 — Resolve and validate
  Parse imported/generated/authored source through current public DDN APIs;
  resolve imports within the admitted workspace and retain coded diagnostics
  with source locations. Validate the native metadata mapping separately from
  visual syntax. Distinguish deployable physical metadata from conceptual/logical
  entities, inferred relationships, annotations and presentation-only elements.
  An illustrative relationship is not automatically an enforced foreign key.

DDN-DB-008 — Engine-native generation
  Select an exact target engine/version/dialect and deployment scope. Generate
  native creation metadata/statements using existing provider compilers where
  suitable. Account for dependency order, cycles, deferred definitions, engine
  capabilities, database creation outside database scope and statements needing
  service APIs. Emit a plan containing SQL and explicitly identified non-SQL
  operations where necessary; never fabricate SQL for a native service task.
  Show unsupported/lossy cross-engine conversions and require explicit choices.
  A source script that lacks a type, default or constraint cannot silently gain
  an invented native definition. System-managed entities are documentary unless
  the target engine exposes an admitted management operation.

Metadata differences and migration
=================================

DDN-DB-009 — Semantic differences
  Compare desired DDN metadata with live metadata or a saved qualified baseline;
  also support comparisons between DDN snapshots. Normalize semantically
  equivalent native forms without losing raw definitions. Compare all supported
  persistent object kinds and subobjects, not just tables/columns. Ignore layout,
  label, zoom and view changes for SQL generation. Match stable native identities
  and explicit rename mappings; do not guess that similarly named objects are a
  rename. Ambiguous rename versus drop/create requires a user decision.

DDN-DB-010 — Coverage and drift
  Treat absent, unknown, inaccessible, excluded and explicitly deleted as
  different states. Destructive differences require complete relevant coverage
  and explicit intent. Re-read live metadata before apply and compare its revision
  or semantic fingerprint with the planned baseline. Detect external changes and
  require replan/conflict resolution. Use baseline/live/desired three-way
  comparison when editing a discovered snapshot; preserve both authored and
  externally changed definitions rather than overwriting either silently.

DDN-DB-011 — Native diff statements and review
  Produce deterministic ordered CREATE/ALTER/DROP, rename, privilege, dependency
  and required data-conversion/rebuild operations as supported by the engine.
  Each change records native target identity, before/after metadata, source DDN
  location, reason, preconditions, dependencies, affected objects, expected
  outcome, required permissions and transactional/locking implications. Separate
  direct alterations from rebuild/copy/swap procedures. Never assume DDL is
  transactional or rollback is universally available. Generate downloadable
  scripts/plans without executing them and identify operations that cannot be
  represented by a standalone SQL script. No-op comparisons produce no changes.

DDN-DB-012 — Apply and outcome
  Apply only a reviewed explicit plan through native provider boundaries, with
  existing authorization/confirmation policies and exact target binding. Keep
  transaction semantics native; don't route engine changes through DDN. Surface
  progress, partial success, failed preconditions and uncertain outcomes. Do not
  automatically replay unknown-result or irreversible operations. Provide
  rollback/compensation only where valid, and state backup/recovery prerequisites
  for operations that need them. Re-discover changed metadata and compare it with
  the expected result; preserve the plan/result and refresh affected DDN views.
  Data read for visualization does not itself authorize inserting or changing
  those records when applying a metadata plan.

Acceptance and dependency obligations
=====================================

DDN-DB-013 — Round-trip qualification
  For each supported engine/version, qualify native metadata -> DDN -> native
  metadata equivalence; DDN -> isolated database -> discovery equivalence; no-op
  diff; create/alter/drop/rename/grants and dependency cycles; quoted/non-ASCII
  identifiers and exact native types; filtered/denied/partial catalogs; stale
  baselines and conflicting edits; large multi-file/multi-database workspaces;
  data sampling/precision and live bindings; and failed/partial/unknown apply
  outcomes. Demonstrate ERD/dashboard display AND editing with the refreshed DDN
  tools. Track mapping completeness by object kind and property. Passing diagram
  rendering tests does not qualify native schema generation or migration.

DDN-DB-014 — Current DDN intake and team coordination
  Refresh the consumed sister-project snapshot before every build and
  commit-validation test run, following AGENTS.md. Track exact source/artifact
  revisions and public APIs. Keep design-only display coverage, lossless metadata
  mapping, native statement generation and live qualification as separate states.
  Coordinate missing native metadata vocabulary, lossless public model access,
  authoring/serialization, refresh/merge identity and editable data bindings with
  the DDN team. Requirements recorded here are not proof of delivery or agreement
  by that team; do not edit its active source to imply acceptance.

Observed baseline, 2026-10-10
============================

Sister-project revision: de469bc62d660a5db6249e6a76db7e6b51c72f12.
Source inspection, not runtime qualification:

* ``notation/tests/fixtures/sql-ddl-export.sql`` explicitly labels its output
  "synthetic illustrative DDL, not a deployable schema" and uses TEXT columns.
  ``notation/runtime/ddn-export.js`` normalizes exported identifiers and only
  exports allowlisted tables/fields with restricted key/relationship handling.
  Reusing that output as exact Firebird or other engine DDL would lose metadata.
* ``notation/tests/sql-export.js`` tests those illustrative export restrictions;
  it is not evidence of engine-specific creation or migration qualification.
* ``field-guide/sources/diff-views.ddn`` demonstrates visual before/after unions
  matched by local source IDs. Visual change rendering is useful for review but
  does not provide native semantic differences, safe rename matching or ALTER SQL.
* At initial inspection ScratchRobin's asset contracts preserved multi-file DDN
  source, but its bundled runtime/Designer were older than the sister project.
  The current paired runtime intake, native adapters and planner described below
  supersede that implementation baseline.

These findings establish the implementation gap without limiting the owner's
required bidirectional functionality to the currently available DDN exporter.

Dashboard display versus editing
================================

Owner correction, 2026-10-10: dashboard instances are display-only. Layout and
binding changes occur in a separate DDN dashboard editor opened through an
engine/server/database context-menu item. This separation does not remove ERD
editing or the native metadata-plan requirements above. Dashboard collection
uses dedicated native connections independent of users; ScratchBird is the
intended historical observation store. ``firebird_dashboards.rst`` owns the
connection, scheduling, history and viewer/editor separation requirements.

Firebird catalog snapshot mapping v1
====================================

The metadata export form admits database or selected native-object branch scope
through the existing authorized resource service. It uses one generation-bound
catalog capture; endpoint route and registered database identity are resolved on
the host. It never accepts a browser-supplied catalog, SQL, hostname or password.
An explicit refresh first checks the caller's generation, invalidates that
catalog and captures its replacement. Other open views must reconcile the new
generation. An export without refresh is labelled a cached catalog observation.
Neither choice claims a new storage-level atomic snapshot or server-wide read.

The DDN workspace uses public data records and x_record fields. Each native
resource is one deterministic record with an endpoint-and-database-qualified
DDN uid, its exact resource ID, native kind,
display path, system flag and native_json string. native_json is canonical JSON
of the existing authorized provider metadata, preserving its integers as JSON
text inside a DDN string; a reader must not parse it through a lossy numeric
representation. It contains native definitions, dependencies and properties,
not rendered SVG. The mapping identifier is scratchrobin.firebird.catalog@1.
These records are documentary metadata, not deployable physical declarations.
They do not authorize executing embedded SQL or infer deletion intent.

A separate provenance record includes endpoint/registered target identity,
resource generation, export time, scope, inclusion policy, catalog observation
coverage and warnings. Successful visible observations are not proof of complete
privileged visibility. Denied or failed optional categories remain unknown.
The inventory is split into views of at most 100 objects, respecting DDN's
128-element live-view limit; all admitted objects remain in the DDN source. Export rejects catalogs above 20,000
resources or 8 MiB of UTF-8 DDN rather than silently truncating their source.
Transient service tasks and metric descriptors are omitted. Objects marked as system by the provider are
an explicit inclusion choice; missing classification is shown as unknown. Filtered scope is never deletion intent.

The form previews through the paired DDN viewer and downloads the exact DDN
source. This completes a catalog-to-document path only: native SQL export,
selected/full row data, ERD mapping, reverse generation, semantic diff and apply
require their own acceptance evidence and are not implied by this mapping.

Catalog document admission and comparison
-----------------------------------------

The export form also accepts a single UTF-8 catalog DDN document for read-only
comparison with the selected authorized database generation. The paired public
DDN parser reads the document; no imports, external assets or embedded SQL are
executed. Admission is bounded by the export limits, parser memory, concurrency
and timeout. Duplicate identities, invalid JSON, duplicate JSON properties,
non-finite numbers, inconsistent object counts and unsupported mapping versions
are refused. Native JSON is decoded on the host to preserve integer precision.

The provenance endpoint and registered database identity must match the host's
resolved selection. Provenance is untrusted documentary content, never proof of
authorization or completeness. Objects match by exact native resource identity;
renames are not guessed. Comparison reports equal, changed, document-only and
current-only records, including exact changed top-level native fields. Metadata
arrays retain order and values retain JSON types. Volatile catalog properties
are not silently discarded; this is a documentary comparison, not a semantic
migration planner. Missing objects, filtered views and incomplete observations
never authorize drops. The result contains no executable plan or apply action.

Structured Firebird change-plan admission
-----------------------------------------

A separate explicit preview accepts baseline and desired catalog DDN documents
and compares them with an authorized current capture. All three must identify
the same registered database. Native planning coverage includes standalone
sequences, exceptions, indexes, roles, BLOB filters, domains, tables, columns,
constraints, triggers, standalone procedures/functions, packages and views on
Firebird 5 / dialect 3, including the explicit identity, removal, domain-type and
column-domain lifecycles below, subject to
the per-kind contracts below. Coverage is reported in the
plan; it does not imply support for every catalog kind. Changed unsupported
objects, properties, ownership or grants block a downloadable migration script.
Raw embedded DDL/recreation statements and presentation labels are never used
as executable input. Names come from exact native paths, and SQL is regenerated
using native validation and quoting. Renames require their own explicit mapping;
changing a path under an existing identity is refused.

Sequence creation requires exact initial value and increment; alterations may
change increment and comment. Altering the stored initial value is not replaced
by RESTART, since those have different native semantics. Current sequence values
are not schema state and are never reset by this planner. Exception creation
and alteration preserve the message and comment. Creation does not claim to
restore ownership or grants; such requested changes require admitted handling.

Three-way comparison works per admitted property: unchanged desired properties
preserve current values; already-converged changes are no-ops; independent
changes may merge; competing changes produce conflicts. An object removed
from the desired document is not a drop request and blocks planning until the
document scope is reconciled. A live object absent from baseline is an external
addition, never an implicit create target. Target deletion and identity changes
require conflict resolution. Native metadata/layout observations are retained
separately from the admitted schema properties.

Plans include source digests, current generation, target/version/dialect,
property preconditions, ordered native statements and explicit blocked/no-op/
review-ready state. A downloadable script is available only with no blockers.
It is a review artifact, not authorization or an assertion of apply-time drift
protection. Application uses the separate reviewed-application contract below;
the pure planner itself never executes statements. No automatic retry, sequence
rewind or engine-outcome inference is introduced by planning.

The current host observation is compared directly as structured native metadata,
with canonical JSON and exact integer/decimal decoding. It need not be rendered
or reimported through DDN. Its digest format is explicitly reported as
scratchrobin.firebird.native-capture@1; imported document digests remain hashes
of their original UTF-8 DDN source. Host capture retains the 20,000-resource and
8 MiB native JSON bounds. Index namespace checks include system catalog objects.

The paired DDN 0.8 parser additionally limits each source file to 2,000,000
UTF-16 code units. Single-file export and import enforce that lower effective
limit alongside the UTF-8 byte bound, before emitting an unreadable document or
starting a parser process. Large catalogs are packaged as a ddn-workspace@1 JSON
document containing bounded DDN files, with one provenance record for the entire
capture. The download remains a plain .ddn file when the capture fits one file.
Every inventory view identifies its entry file, and preview page selection uses
that file. Files contain independent views; this mapping requires no imports or
external resolution. Native identities remain independent of file placement.

Import/comparison/planning accept either the original DDN source or the complete
workspace JSON download. All contained files are parsed through the paired DDN
API, and resource/UID uniqueness and object count are checked across all files.
Duplicate JSON properties, unsupported envelope fields, paths outside the flat
catalog filename set, unknown entry/view, imports and multiple provenance records
are rejected. Limits remain 20,000 resources and an 8 MiB downloaded artifact,
with at most 64 files and 2,000,000 UTF-16 units per file. Pages are bounded by
both 100 records and source size. A record or provenance block too large to fit
one admitted file is refused explicitly; it is never split or truncated. Source
locations retain the containing filename; document digests cover the exact
uploaded/downloaded UTF-8 artifact. This is not permission to bypass parser limits.

Standalone index planning
~~~~~~~~~~~~~~~~~~~~~~~~

The structured planner also admits creation of ordered-column indexes, including
unique/ascending/descending definitions and initial inactive state, and alteration
of standalone index active state/comments. Index identity includes its table;
the native name is nevertheless database-wide, so creation checks all visible
index names. The owner must be a currently observed user table and every selected
column must exist in its native column catalog. Index and constraint observations
must be available. Constraint backing indexes are never treated as independent
index lifecycle targets. Unknown/failed visibility blocks this planning path.

Segments retain exact identifiers and contiguous zero-based positions. Definition
changes to an existing index require an explicit rebuild contract and are blocked
here rather than emitted as unsupported ALTER clauses. Creation also admits
computed and partial indexes using native catalog source conventions:
expression_source is a parenthesized expression (without COMPUTED BY), and
condition_source is a WHERE clause. Computed and column-segment definitions are
mutually exclusive. The provider expression boundary validator checks balanced
delimiters, Firebird quoting/comments and absence of statement separators outside
quoted text; this is not native grammar/type/determinism validation. Original
source is preserved, with a terminating newline before subsequent SQL so a line
comment cannot consume provider syntax. Empty or malformed clauses block the
plan. Native prepare, privileges and index restrictions remain execution-time
checks. Existing expressions/predicates are retained for state/comment changes;
definition changes still require an explicit rebuild contract. Index statistics
and derived active-state summaries are observational, not desired schema changes.
Plans include the owning table as a dependency. The reviewed native application
workflow below performs apply-time revalidation and native prepare/permission
checks in its owned transaction.

Role definition planning
~~~~~~~~~~~~~~~~~~~~~~~~

Firebird 5 dialect 3 previews admit standalone user-role creation, replacement
or removal of the role's system-privilege set, and role comments. Privilege names
must belong to the native provider's exact versioned list; duplicates, absent
privilege metadata and unknown native privilege bits block a changed role.
The privilege set is canonicalized in native bitmap order. Order-only changes
are no-ops; competing changes to the set are conflicts, not an implicit union.
Independent live comments and memberships are preserved. Each role operation
reports privilege additions/removals for review and its native authorization
requirements. The planner never derives executable SQL from the supplied bitmap,
recreation statements or documentary DDL.

Creation requires an available role-catalog observation. RDB$ADMIN and
system-managed roles are not admitted by this lifecycle. Ownership is assigned
by Firebird to the creating user; authored ownership transfer, memberships,
grants and admin-mapping changes are not role-definition edits and block this
path. Existing ownership/membership changes observed live are preserved and
must not be overwritten. Native privileges and execution remain Firebird-owned;
review-ready status does not grant permission or provide an Apply action.

BLOB filter declaration planning
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Firebird 5 dialect 3 previews admit BLOB filter declarations and comment changes.
The model requires exact signed 16-bit input/output subtype numbers, installed
module name and exported entry point. External names use the native provider's
1–255 UTF-8 byte contract and literal quoting. Registered subtype mnemonics are
not inferred from numeric catalog metadata. Creation requires an available BLOB
filter catalog observation. Native ownership/security fields and grants cannot
be authored as declaration properties.

There is no ALTER FILTER. A desired change to subtype, module or entry point
blocks script generation until an explicit drop/redeclare lifecycle is admitted;
it must not silently drop an existing declaration or disrupt cached native code.
Comments use COMMENT ON FILTER. Firebird stores empty comment text as NULL;
the schema model normalizes empty strings to NULL for every supported kind,
so clearing a comment converges. Documentary metadata remains unmodified.
Independent live definition changes are retained for comment-only edits.

Plans carry the existing native BLOB-filter deployment warning: declaring a
filter neither installs nor qualifies the external library, changes UdfAccess,
invokes its entry point, unloads cached code nor proves ABI compatibility.
Successful declaration/discovery qualification is distinct from executing a
filter. Unknown or system-managed definitions are not silently recreated.

Existing domain property planning
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Firebird 5 dialect 3 previews admit changes to existing domain defaults,
nullability, CHECK constraints and comments. Native DEFAULT/CHECK source is
retained and validated with the provider's expression-boundary checks; malformed
clauses and unquoted statement separators block the plan. Default removal uses
DROP DEFAULT. CHECK replacement emits DROP CONSTRAINT followed by ADD CHECK;
it never silently recreates the domain. Nullability uses SET/DROP NOT NULL.
The entire ordered operation must use the eventual native transactional apply
contract; this preview does not grant execution or promise successful validation
against existing dependent data.

Type changes and renames require the explicit lifecycle contracts below;
collation reconstruction and array-layout changes cannot be inferred from a
property edit. Scalar creation follows the additional contract below. Exact
native type fields cannot be changed through an ordinary property edit. Independent live type
changes are preserved; native preparation/execution determines compatibility of
the requested properties with the live type and dependent columns. Availability
of the domain catalog is required. Missing desired objects never mean DROP.
Empty comments normalize to native NULL as for the other supported objects.

Clause boundaries are stricter than delimiter balance: a CHECK or computed-index
source must be one complete outer parenthesized expression, with only whitespace
or comments outside it. A DEFAULT payload must not introduce top-level ALTER
DOMAIN clauses (SET, DROP, ADD, TO or TYPE) or creation clauses
(NOT NULL, CHECK or COLLATE). Keywords inside quoted literals,
quoted identifiers, alternative-quoted strings or comments are not clauses.
These checks prevent property text from silently changing additional properties;
they do not replace native grammar/type validation.

Scalar domain creation
~~~~~~~~~~~~~~~~~~~~~~

Domain creation additionally admits lossless canonical scalar metadata through
the existing native type editor/compiler: integer, NUMERIC/DECIMAL, FLOAT/DOUBLE,
BOOLEAN, DATE/TIME/TIMESTAMP (including zones), DECFLOAT, CHAR/VARCHAR,
BINARY/VARBINARY and BLOB. Native field type/subtype/scale/precision, character
length and BLOB segment size drive structured rendering; no supplied DDL or
free-form type fragment is executed. Contradictory physical numeric encodings,
missing required type facts, legacy scaled doubles and unknown types are
rejected. Creation does not authorize existing type changes. Nonzero inapplicable
precision/character-length/segment-size fields and missing BLOB segment sizes
are refused rather than silently discarded. DECFLOAT native precision, when
present, must agree with the type code (16 or 34).

Character types and text BLOBs require an explicit observed character set.
A supplied collation must be observed for that same character set. If omitted,
the observed character-set default collation is fixed in the reviewed creation
descriptor and SQL. Missing catalog visibility blocks this resolution. Generated
plans retain charset/collation resource dependencies; catalog visibility and
native prepare remain required. Binary types use native OCTETS semantics.
Creation metadata records its canonical type descriptor; native discovery
qualification compares the same descriptor after executing generated statements.
Field storage length is documentary and is not interpreted as character length.
Defaults, nullability, CHECK and comments retain the property contracts above.

Array domain creation
~~~~~~~~~~~~~~~~~~~~~

Native domain capture includes ``array_dimensions`` with zero-based position,
lower_bound and upper_bound from RDB$FIELD_DIMENSIONS. Creation requires available
array-dimension catalog visibility, exactly the declared number of dimensions
(1 through 16), contiguous positions and signed 32-bit bounds with upper strictly
greater than lower (Firebird rejects equal endpoints). A scalar
cannot carry array bounds. BLOB elements are not supported by Firebird and are
rejected. Render bounds between the scalar type and CHARACTER SET clause;
collation retains the domain grammar position after property clauses. All bounds
are explicit, including negative, zero and non-default lower bounds. No bounds
are inferred from element counts or storage length. Native prepare/commit checks
remaining engine type and total-size constraints. Existing array-layout changes
remain outside this creation contract.

Reviewed native application
~~~~~~~~~~~~~~~~~~~~~~~~~~~

For admitted Firebird 5 dialect 3 operations, a separate Prepare application
request reauthorizes the registered target, refreshes metadata and verifies the
execution fingerprint of the displayed plan. A five-minute review binds the
owner, endpoint/target, route configuration, native database GUID/file identity,
engine version, exact operations and affected/dependent native properties.
Changed review inputs require a new preview. The review contains the generated
SQL and target for confirmation; Apply accepts only its ID, fingerprint and an
explicit confirmation, never browser-supplied executable SQL.

Linux hosts retain review/dispatch/result receipts in a separate private local
operation store, serialized across processes by an OS file lock. Claim-before-
mutation prevents duplicate execution of a review, including competing requests
and process restarts. Interrupted dispatch is an unknown outcome requiring
inspection, never automatic replay or inferred rollback. Stored documents are
reduced to the admitted changed objects; secrets from connection routes are
never stored in the receipt. A route binding is a digest. Reviews/receipts remain
owner-authorized on every read. Missing durable storage or locking support
prevents application while leaving preview/download available.

Application opens its own native attachment and a fresh SNAPSHOT, read-write,
non-autocommit transaction with bounded lock wait. It captures and replans on
that attachment before issuing any DDL, verifying the reviewed execution
fingerprint and database identity. Native catalog preparation, metadata locks,
privilege and commit-time dependency checks remain authoritative; this is not
an exclusive database-wide DDL maintenance lock against other tools. A detected
preflight change executes no statements. All admitted statements execute in
one transaction, followed by one native commit. Preparation/statement failures
request rollback; commit failure remains an unknown outcome even if subsequent
cleanup returns. No user session transaction is borrowed or refreshed.

Receipts distinguish not executed, native rollback returned, native commit
returned and unknown outcome. Statement completion is provisional until native
commit returns. Release and post-commit rediscovery failures are separate from
the observed commit result. Rediscovery uses a new transaction and reports
whether affected properties match; a mismatch is not an automatic retry or
compensating migration. Explorer cache invalidation is attempted after dispatch.
The form retains the receipt and supports fetching it again after a response
failure without re-executing the review. Windows/macOS locking adaptation remains
with the assigned platform teams.

Array-domain defaults are not admitted for creation or alteration. Firebird
rejects defaults on array domains, including DEFAULT NULL. Domain planning
reports this as a blocker before emitting executable statements; the presence
of a scalar element type does not make the array itself a scalar domain.

Firebird view definition planning
--------------------------------

The structured planner admits view query-definition and comment edits, preserving
ordered native output column names. CREATE uses an explicit column list; ALTER
preserves grants and triggers and never uses RECREATE. Native preparation owns
query grammar, dependency validity, output types and WITH CHECK OPTION semantics.
View query source is one native statement fragment, not an executable script.

The review compares exact catalog generations and native properties. Unknown
metadata changes, output column renames and absent desired objects are not implicit
permission to drop or rebuild. Output-type changes must pass native dependency
checks in the owned schema transaction. Review guards include the visible catalog
for view-definition changes because proposed SQL may introduce new dependencies.
Native failure rolls back the application; a lost commit response remains unknown.
Multiple new dependent views require explicit dependency ordering before their
combined plan is admitted; documentary dependencies alone cannot prove SQL meaning.

Relational diagram capture
--------------------------

Catalog export also provides a separate DDN relational workspace: native tables
and views retain exact resource identities, ordered columns and physical type
labels; foreign-key edges retain native constraint identity and ordered endpoint
column tuples. Composite constraints remain one constraint, not independent
single-column constraints. Diagram labels never become native identifiers.

Only visible objects in the selected scope are modeled. Missing referenced
objects, incomplete native type facts and relationships crossing a bounded view
are disclosed. Layout pagination does not imply database boundaries or deletion.
Native facts remain in the catalog document; the diagram workspace is a separate
presentation/design artifact. Diagram editing and download do not execute SQL.
Applying diagram-model edits requires the separately qualified native reconciliation
and explicit schema-application path; no raw DDN illustrative SQL is executable.

Column capture retains array bounds directly on each native column, including
anonymous RDB$ backing fields, so a table-only selection cannot accidentally
flatten an array into a scalar type. The column's own NULL flag and its backing
field/domain NULL flag remain distinct facts. The diagram marks a column
non-nullable when either native flag requires it; an unavailable flag is not
proof that NULL is allowed.

Structured table planning
-------------------------

Native table security, publication membership and comments participate in the
same three-way review as other objects. Relation kind and external filename are
immutable under ALTER. Table creation uses ordered native column descriptors,
including exact types, domains, array bounds, identity settings, computed source,
defaults, nullability and comments; it never executes documentary DDL. Native
preparation owns expression grammar and dependency permissions. External-file
creation requires a separate explicit filesystem-effect workflow and is not
admitted by a schema-plan import.

An absent child is not deletion intent. Until a child change is supported by its
own planner, changes to existing columns or constraints block the complete plan.
A newly authored table with keys/checks must retain those constraints; the
planner must refuse unsupported constraints rather than silently omit them.
Referenced domains, character sets and collations must be observed and guarded.
Creation and alteration use the existing owned-transaction schema application,
including durable receipts and uncertain-outcome handling. Rediscovery compares
normalized native properties and reports differences without claiming an
unobserved rollback or silently retrying a committed operation.

The array dimension count is read independently from ``RDB$FIELDS``. Missing
``RDB$FIELD_DIMENSIONS`` rows do not convert an array into a scalar: diagrams
show unavailable bounds and creation refuses incomplete bounds. Domain-derived
nullability remains visible on a column-only capture.

Table creation currently admits 1–1024 ordered columns and persistent or global
temporary relation kinds. Named constraints/indexes follow the child dependency
admission below; existing layout edits still require a separate plan. Computed plain
integer fields carry Firebird's derived physical precision (4/9/18/38); this is
not a NUMERIC declaration. Identity generator names are allocated by Firebird,
while generation mode, initial value and increment are preserved. SQL security
accepts native BOOLEAN or the provider's materialized BOOLEAN spelling, with
``False`` interpreted as INVOKER, never as a truthy DEFINER value.

New-table child dependency admission
------------------------------------

The next creation boundary admits explicitly named NOT NULL, CHECK, PRIMARY KEY,
UNIQUE and FOREIGN KEY constraints and their exact backing indexes within a new
table definition. Standalone column/computed/partial indexes follow CREATE TABLE
in the same owned transaction. Primary/unique definitions precede self-reference
foreign keys. Composite order, backing index name/direction, referential actions
and index comments remain native facts; expressions still require native prepare.

A referenced key must belong to the authored table, an observed existing
table, or an explicitly authored new table in the same dependency plan, with
its exact primary/unique constraint and ordered index columns.
The creation graph orders new domain references and index parents before
their consumers. Foreign keys referencing another newly authored table are
added in a final constraint phase after all object definitions. User triggers
require matching standalone definitions; existing child changes follow their
separate column, constraint, trigger and lifecycle contracts below. Contradictory child
facts, missing backing indexes or unsupported child properties block the plan.
No imported native DDL is executed. Existing ownership, system classification,
privilege and uncertain-outcome boundaries still apply.

Post-commit rediscovery identifies constraint-generated triggers through the
native ``RDB$CHECK_CONSTRAINTS``/``RDB$RELATION_CONSTRAINTS``/``RDB$TRIGGERS``
relationship, excluding NOT NULL rows (whose trigger-name column names a field).
It does not infer ownership from a trigger name prefix or source text. These
observed engine-generated children are consequences of their constraints,
not independent CREATE TRIGGER instructions. Authored trigger imports still
require routine dependency planning and cannot acquire execution authority by
claiming to be generated triggers.

Expanded domain nullability on a column must agree with the referenced domain.
Anonymous-domain nullability cannot be silently lost when emitting a scalar
column declaration. Identity generator/start/increment facts require an identity
column; orphan identity facts block creation instead of being discarded.

Creation dependency graph
-------------------------

New definitions may carry ``native_json.creation_dependencies``, an explicit
array of exact catalog resource identities. These are ordering instructions,
not native properties or executable SQL. Every reference must exist in the
observed catalog or the same admitted desired document. Duplicate, self,
unknown and cyclic explicit references block the whole plan. Native structured
domain and index-parent relationships add mandatory ordering edges.

Multiple new views require explicit dependency arrays, including an empty
array when independent. Native prepare still verifies their actual queries;
a supplied ordering declaration cannot authorize unknown SQL or bypass native
dependency/type checks. Broad metadata guards remain separate from ordering
edges. Read-only projected definitions resolve new domain types and referenced
keys during preview; they never become evidence that objects already exist.
The complete graph executes in the existing owned MGA transaction and is
rediscovered after commit. Mutating a referenced existing domain in the same
plan remains blocked until its expanded column facts can be reconciled against
the effective domain definition. Mutually referencing new tables are admitted:
all referenced primary/unique keys are created before the final foreign-key
phase. Each deferred ADD retains its exact named backing index and comments.
Both phases execute in one owned transaction, without intermediate commits or
constraint disabling. Native failure in either phase rolls back the entire
creation; uncertain commit outcomes remain uncertain. Standalone PSQL routine
cycles use the staged signature contract below; unresolved other ordering cycles
remain blocked. Self-referencing keys stay in CREATE TABLE.
The preview and downloaded script show both phases in execution order; the
review digest covers every deferred statement. Rediscovery compares the final
complete table definitions, not the intermediate unconstrained state.

A new table may include a standalone index both in its nested index metadata
and as a separately addressed catalog object. The definitions must agree
exactly; the table emits the index once, while its separate identity retains
its own drift guard and rediscovery check. Separately authored indexes absent
from the nested table definition are checked independently after creation.
Rediscovery recognizes native constraint-owned triggers on both sides of a
foreign key; this does not authorize importing user triggers as constraints.

Existing column property reconciliation
---------------------------------------

The structured planner admits existing user-table column defaults, column-level
nullability, identity generation mode, existing computed expressions and comments. It preserves the separate
backing-domain nullability, sequence allocation, column position and type facts.
Identity mode changes never restart or advance the identity generator. Adding or
removing identity status requires its own explicit lifecycle intent; changing a
mode is only valid for an existing identity column. Native constraints, computed
and array restrictions are revalidated using the live catalog before execution.

A column edit addresses its exact standalone column identity. A table's nested
column projection may remain the captured baseline or repeat exactly the same
property edits. A conflicting nested projection, a nested-only edit, a missing
column or a changed identity blocks the complete plan. The planner never treats
a missing column as DROP. The table and all observed constraint/index facts for
that table are drift guards; nullability is not inferred from labels or imported
editor hints. All admitted statements run through the existing owned native
transaction, explicit review and rediscovery workflow. Changing a stored column
to computed, or the reverse, requires explicit replacement intent. New default
or computed expressions guard the visible native schema and are prepared by
Firebird; imported dependency hints do not authorize them. Type, position and
column creation/removal are separate reconciliation operations;
an unadmitted change remains a visible blocker, never an ignored edit.

A new standalone column on an existing user table is also an explicit ADD intent.
Its native type, domain, array bounds, computed/identity facts and position must
be complete; creation uses the same structured definition compiler as CREATE
TABLE. Position is zero-based in the design and one-based in native ALTER SQL.
ADD and any position adjustment execute in one transaction. Existing column
identities and the parent layout are guarded. User-domain dependencies must be
observed. A required column that needs a named NOT NULL constraint is handled
with explicit constraint planning, not a synthesized untracked constraint.
Post-commit discovery compares the created definition and position, including
its type and identity settings; a successful COMMIT alone is insufficient.

Multiple new columns require distinct final positions. All ADD statements run
before the final position phase, which orders placements from low to high so
later insertions cannot displace a previously placed new field. Existing stored
values are preserved; a default declaration is not an explicit UPDATE/backfill
request. Native default behavior is verified for subsequent inserts.

A new table's standalone column records may repeat its nested column definitions.
Both representations must agree on native properties and position. The table
emits each definition and comment once; the separate column identity retains
its absent-object guard and post-commit property check. A mismatch blocks the
whole plan. A standalone column not present in that new table definition is not
silently added by a second CREATE/ALTER path.

Existing scalar column type changes use the native field type/subtype, scale,
precision and character length. The storage byte length is derived metadata;
it is not a separate user-editable datatype. Named-domain rebinding follows its
explicit lifecycle below. Array layout changes and ordinary BLOB type replacement
require separate reconstruction workflows. Charset/collation changes remain
explicit separate changes. Plain integer
computed-result precision is normalized as physical metadata, not NUMERIC.
The planner validates the complete resulting type against the observed catalog,
guards dependencies, and emits native TYPE (or TYPE ... COMPUTED BY) without
DROP/CREATE. Firebird owns conversion and dependency checks: data incompatibility
rolls back the whole application. Rediscovery compares semantic type facts.

Durable application reviews preserve admitted creation-order instructions along
with the executable object definitions. Removing documentary renderings during
receipt reduction must not remove planning instructions: a reopened receipt
must reconstruct the same reviewed dependency graph and execution fingerprint.
Qualification includes native application from the reduced stored receipt, not
only direct application of an in-memory preview.

Package header/body reconciliation
----------------------------------

Firebird package planning uses exact native header_source, body_source,
SQL SECURITY and comments. Header/body source is a structured native definition
submitted as one prepared statement, never a semicolon-split script or imported
DDL rendering. CREATE/ALTER PACKAGE owns the public member declarations;
packaged routines are not standalone ALTER targets. A changed header is an
explicit replacement of those declarations and may remove omitted members or
invalidate dependent code under Firebird's native checks.

All admitted package headers are created/altered before the final body phase.
An existing body is recreated after a header/security change even if its text
is unchanged. An explicit body_source change to NULL drops only the body.
Each header/body action and comment is shown in the review and covered by its
fingerprint. No intermediate commit separates header and body; failure rolls
back the whole application. Existing grants and native object identity are not
replaced using DROP PACKAGE or RECREATE PACKAGE. Full visible schema guards
protect new body references. Explicit dependency cycles still need an admitted
cycle plan. Downloaded schema scripts use a collision-free ISQL terminator;
provider execution uses the unchanged complete statement arrays.

Standalone procedure and function reconciliation
------------------------------------------------

Standalone routine plans use native parameters, metadata_source, external engine
and entrypoint, SQL SECURITY, function determinism and comments. Parameter names,
modes/positions, return identity, defaults, nullability, domain/TYPE OF references,
scalar type properties and comments are explicit. Generated backing-domain names
and physical storage lengths are not portable parameter identity. Character
parameters require explicit observed charset/collation facts. Referenced domain
or column metadata must agree with the expanded parameter type.

CREATE/ALTER is prepared as one native statement. No RECREATE or DROP routine is
used for signature/body changes; native dependency and conversion checks apply.
Parameter comments are restored after the declaration. Packaged members require
the package header/body workflow. Imported ddl/recreation_statements cannot
replace the structured definition. Explicit creation-order dependencies are
retained through saved reviews. PSQL and external-engine payloads are separate
forms of body source; an external clause cannot silently acquire SQL SECURITY.
Post-commit observation compares the exact normalized signature and body using
a fresh metadata transaction. Runtime verification uses a fresh attachment to
avoid treating retained prepared code as the committed replacement's behavior.

Trigger reconciliation
----------------------

Structured trigger plans preserve the exact native relation, event mask, active
state, position, SQL SECURITY, PSQL or external-engine definition and comment.
DML, all five database events and the native DDL event mask are separate families;
unknown or partial masks cannot be silently rendered as a smaller event set.
Constraint-owned and system triggers are changed through their owning objects.
CREATE binds a relation only for DML. ALTER preserves the relation and family;
Firebird permits event changes only for DML triggers. Database/DDL event changes
require an explicit lifecycle operation, not an implicit RECREATE. Clearing an
existing SQL SECURITY override emits DROP SQL SECURITY. Ordinary ALTER preserves
grants and native identity. Comments and full declarations are prepared in the
reviewed transaction, and native failure rolls back the complete application.
Trigger effects follow native transaction semantics, including any explicitly
written autonomous activity; rollback of the schema transaction does not promise
to erase independently committed effects. Reviews guard the visible schema,
retain explicit creation dependencies and rediscover the normalized definition.

Existing-table constraint reconciliation
----------------------------------------

Constraint definitions carry their exact owning table, native kind, CHECK source
or referenced key/rules, and the backing index definition where applicable.
The backing index remains a native owned object, not an independently recreated
standalone index. PRIMARY KEY, UNIQUE, FOREIGN KEY and CHECK creation uses ALTER
TABLE ADD. Firebird has no general ALTER CONSTRAINT definition: a changed
constraint is reviewed as DROP CONSTRAINT followed by ADD in the same transaction,
without CASCADE or intermediate commit. Permissions and dependent objects remain subject to native validation.
Native key creation checks existing data. Firebird CHECK creation/replacement
does not retroactively validate existing rows: this limitation must appear in
the review, and must not be described as full-table validation. A failed ADD restores the original
constraint through native rollback. The review identifies replacement explicitly.

Key names, column order, index direction and index comments are preserved.
Catalog-derived constraint triggers are not imported as user triggers. Standalone
and nested new-table constraints must agree and are emitted once. NOT NULL is
managed by the column nullability workflow for existing tables; authored native
constraint names must not be silently replaced by engine-generated names. An
absent desired constraint is not DROP intent. All schema dependencies and the
parent table layout are guarded before execution. Constraint SQL itself has no
COMMENT ON form; its backing index comment is separately addressable.

New-table user triggers are separate ordered definitions. A nested trigger must
match a standalone trigger object with the same database-wide identity, relation,
body and properties; the table emits no duplicate trigger statement. Trigger
creation follows the owning table and any explicitly declared source dependencies.
Post-commit table observation reconciles these separately created triggers, while
the trigger's own observation verifies its complete normalized definition.

Mutually dependent new standalone PSQL routines may be staged as complete native
signatures followed by their complete bodies, in one application transaction.
Only dependencies among admitted new PSQL routines are removed from the signature
phase; domain, TYPE OF COLUMN and nonroutine dependencies still constrain it.
No existing routine is replaced with an intermediate definition. External
modules are not staged as PSQL. Every intermediate signature is deliberately
non-callable: its body invokes RDB$SET_CONTEXT with an invalid namespace, which
Firebird 5 rejects before any user body runs. A same-transaction DDL trigger that
tries to call it therefore aborts rather than receiving fabricated results.
The signature/body phases, warning and exact statements belong to the immutable
review. A later body failure rolls back all new definitions. Native metadata
rediscovery and calls from fresh attachments qualify the final bodies.

Downloaded ISQL scripts disable AUTODDL before sending DDL and do not emit COMMIT
or ROLLBACK. The caller must review all errors and explicitly choose the outcome;
otherwise an ISQL default must not commit intermediate signatures or table stages.
This directive does not change the provider's native transaction configuration.

Explicit native identity transitions
------------------------------------

A desired Firebird column or domain may retain its original resource ID and
native facts and add ``native.lifecycle`` with exactly ``operation: "rename"``,
``confirmation`` equal to the original native name, and ``new_name`` equal to
the requested native identifier. Absence, a changed display label or a changed
resource path never implies a rename. The destination must be absent from the
current catalog and other authored objects, and two requests cannot claim the
same destination. Unrelated property changes require their own reviewed step.
Firebird does not provide equivalent native rename for arbitrary object kinds;
those require a separately specified reconstruction lifecycle.

The reviewed operation names both previous and resulting resource identities,
retains full visible schema guards and preserves the lifecycle instruction in
its durable review. Normal definitions and bodies execute before identity
transitions. Each native rename verifies unchanged native identity inside the
same owned transaction: relation/field IDs for columns, transient record key for
domains. Domain record keys are not retained or exposed. Native dependency and
permission checks remain authoritative; failure rolls back the owned change,
and uncertain commit responses retain the ordinary unknown-outcome rules.
Rediscovery verifies the old identity is absent and the new object's reviewed
properties are present. Existing data and ownership are never copied by a rename
workflow. Firebird 5 column renaming does not itself remap column privilege rows.
The review therefore includes exact native revocations before rename and grants
on the new name afterward, retaining grantees, grantors and grant options. The
complete observed column grant set is guarded and rediscovered; unavailable
privilege observations block preparation. Native grantor authority applies and
any failure rolls back the entire operation. Cross-object dependencies are not
rewritten by string edits.

Explicit removal intent
-----------------------

A desired row can retain its original identity and native facts and carry
``native.lifecycle: {operation: "drop", confirmation: "<exact native name>"}``.
This is distinct from omitting an object or filtering a view. Preparation requires
an unchanged observed baseline/current object and exposes native DROP statements,
full visible-schema guards and owned child identities removed with a parent.
Database/server/filesystem/security-user deletion remains in its specialized
management workflow. Constraint-owned indexes/triggers cannot be dropped as
independent objects, and NOT NULL constraint removal uses the column workflow.
User collations and standalone legacy external-function declarations also admit
explicit native removal; this does not load or execute their external modules.

Reviewed removals run after definitions and explicit renames, in reverse observed
dependency order. Each selected dependent is removed before its selected parent;
foreign-key references and relation children participate in ordering. An unresolved
cycle blocks this removal plan instead of guessing a cascade. Native dependency
checks also apply to unselected dependents. No CASCADE or automatic replay is
emitted. A native failure rolls back the owned transaction, while an uncertain
commit retains its unknown outcome. Successful rediscovery verifies absence of
the explicitly removed identity. This is destructive native removal, not archival,
backup, historical retention or a reversible application undo.

Lifecycle admission requires explicit user/system classification. Metadata
capture records the native user-object query predicate as ``system_object=false``
and inherits column/index/constraint classification from the observed owning
relation when their own query does not expose a flag. Explicit system flags
remain authoritative. Unknown classification is not authorization for a lifecycle
change; imported documents cannot override the current native observation.

Explicit domain type alteration
--------------------------------

A domain type edit carries ``native.lifecycle`` with ``operation: "type"`` and
``confirmation`` equal to its unchanged native name. Only native type properties
may differ from the baseline. The current object and visible dependencies must
still match the review guards. Compile ALTER DOMAIN TYPE using the canonical
native scalar descriptor; Firebird owns data conversion, dependent-field and
permission checks. Preserve defaults, checks, nullability, comments and identity;
never substitute DROP/CREATE or rebuild row data in the application.

Firebird 5 grammar accepts a non-array type and has no COLLATE clause in this
operation. Reject array source/target layouts. A character target must explicitly
request its observed character set's default collation; a former nondefault
collation is not silently preserved. Display this effect in the review and verify
actual type/collation after commit. Rebuilding a nondefault collation is a separate
reconstruction workflow, not an invented ALTER DOMAIN syntax. Domain-type reviews
are prepared separately from dependent definitions/property edits so those edits
can be based on refreshed native descriptors after conversion. Multiple explicitly
reviewed domain conversions can share one owned transaction; a later native
conversion failure rolls back earlier conversions.

Explicit column domain rebinding
--------------------------------

An ordinary stored scalar column may request ``native.lifecycle`` with
``operation: "bind_domain"`` and exact old-name ``confirmation`` while changing
``domain`` and its expanded type/domain-nullability facts to one existing observed
user domain. Validate those expanded facts against the target domain instead of
accepting contradictory native JSON. This request cannot combine a column rename,
comment/default/nullability edit, computed conversion or identity change. Array,
BLOB, computed and identity columns retain their specialized native constraints.

Compile native ALTER TABLE ALTER COLUMN TYPE with the quoted domain name, retain
full schema guards and verify the resulting binding and type through rediscovery.
Do not copy rows or replace the column. Native data conversion and dependency
checks own acceptance and rollback. Domain rebinding reviews are separate from
other definition/property edits so every requested binding uses a current observed
domain. Existing column defaults and constraints remain native facts; the review
must also expose the target domain's type and nullability. The column's native
relation/field identity is preserved and qualified alongside data and grants.

Constraint-owned index projections
----------------------------------

A desired constraint may also include its backing index as a standalone catalog
row. When the same plan creates or changes the owning constraint, an exactly
matching index row is a projection of that operation: emit native index creation
only through the constraint, order the projection after its owner, and rediscover
both identities after commit. Match the complete normalized index definition and
comment. Conflicting index/constraint definitions block the entire review.
Independent alteration of a constraint-owned index remains outside the standalone
index workflow; an unchanged captured projection need not be rewritten merely
because the explicitly edited owning constraint changes it.

Native collation definitions
---------------------------

Structured DDN review admits user collation creation from exact native character
set, external base name, attribute bits, specific-attribute text and comment.
The existing provider renderer quotes metadata as native identifiers/literals;
documentary DDL is never executed. The character set and complete collation
catalog observations are prerequisites. External collation implementations must
already be installed on the server; this operation does not install libraries.
Comments can be merged independently against the baseline/live definition.
Firebird has no ALTER COLLATION definition operation: changing comparison rules
requires explicit removal/recreation with dependency handling, never an implicit
replacement of a collation used by stored columns or indexes.

Native creation may append installed ICU-VERSION and COLL-VERSION attributes.
Post-commit rediscovery records those actual attributes in the receipt. The
comparison checks all requested settings and explicitly requested versions;
only those two additional engine version keys may appear without being authored.
Attribute comparison follows native escaping, last-wins and empty-removal rules.
Other added or changed comparison settings fail review matching.
New user collations may be created in the same reviewed migration as domains
and tables that use them. Type validation resolves these authored definitions
against the projected catalog, while native preconditions continue to record
their absence in the live catalog. Exact collation/domain prerequisites are
ordered before their consumers; projection is not evidence of native creation.
Malformed empty containers or Boolean values are not empty collation attributes.
Explicit compound removal reverses these type dependencies, including native
collation references on domains, columns and routine parameters. A collation
cannot be removed before a selected object that still uses its comparison rules.

Legacy external function declarations
--------------------------------------

Structured Firebird DDN reviews admit legacy external-function declarations,
entry-point/library binding changes and comments. Ordered native parameter
positions, physical types, character sets, mechanisms and return argument are
required. They are compiled through the provider's legacy UDF grammar; saved
documentary DDL is never execution input. The referenced native library must
already be installed and admitted by the server. Declaration or metadata
rediscovery does not prove that calling its ABI is safe or successful.

Signature changes on existing declarations require explicitly reviewed removal
and recreation, because ALTER EXTERNAL FUNCTION cannot change that signature.
Library and comment changes support independent three-way merges. No library
installation, ownership transfer, grant restoration, UDR conversion or implicit
signature replacement occurs. A supplied character collation must be the
observed default of its character set: legacy declarations have no COLLATE
clause. Missing catalog observations or unrenderable physical facts block the
review before application.

Catalog design handoff
----------------------

A captured catalog becomes the immutable baseline for the schema review form.
The separate DDN catalog designer edits a copy through the paired public tool.
Returning that copy to review populates the desired document only; it neither
previews nor applies SQL automatically. The user must request native comparison,
prepare its saved review and explicitly confirm application. Native facts are
edited in each record's native_json; visual labels, positions and view selection
are presentation, never native rename/drop instructions. The full catalog file
set accompanies the handoff regardless of the visible inventory page.

Invalid/unfinished DDN source, unsupported changes and stale native facts remain
subject to the existing parser/planner/application checks. A failed designer
snapshot leaves the editor open. Changing the baseline or database discards the
old design handoff and invalidates its review. Layout state stays in the designer
workspace and is excluded from the canonical native metadata input envelope.

Registered-server catalog capture
---------------------------------

The Firebird server catalog form selects one or more registered database targets,
including an explicit select-all option. Each capture resolves that registration
under the authenticated endpoint owner, obtains its own catalog generation and
uses the existing database exporter. It never changes the interactive active
database or interprets a database name from an imported file as a connection.
Catalog refresh is explicit. Independent database observations are not a single
server-wide atomic snapshot, and unregistered server files are not enumerated.

The result is a documentary ``scratchrobin.firebird.server-catalog@1`` bundle:
one DDN server overview and the unchanged complete DDN workspace/provenance for
each successful database. Failed, inaccessible and unattempted targets remain
visible entries, never empty successful catalogs. The form can stop after the
current database and bounds a batch to 256 targets and 64 MiB of UTF-8 bundle
content. Exceeding a bound reports incomplete coverage. Metadata capture never
automatically exports database rows. Individual database workspaces can be
downloaded for the existing target-bound native review flow; the server bundle
itself grants no cross-database deployment authority.

Versioned Firebird design assets
-------------------------------

Catalog and relational designs use the existing project-asset repository, scoped
to the authenticated owner, endpoint, registered database and design family.
Reading does not create a project. An explicit save records the complete DDN
workspace and its original baseline as one immutable asset revision. Saving
requires the last observed asset version; concurrent or stale saves fail instead
of overwriting another editor. Prior revisions remain available by version.
Loading an earlier revision does not roll back the repository's current version;
subsequent saving creates a new revision against the observed current version.

Loaded catalog designs retain their captured baseline for three-way native
review. A new native capture does not grant authority to replace that baseline
or silently discard authored source, annotations or layout. An asset reference
from another database is not accepted through this scope. Imported source remains
untrusted documentary content and can only affect native metadata through the
existing target-bound preview, reviewed plan and explicit application.

The host stores the original workspace in the asset content's
``firebirdDesign.baseline`` envelope field, outside the DDN source files. That
host-only field is removed before providing the workspace to DDN and is returned
separately to review callers; it is not an invented notation construct. Both
workspaces share the repository's overall asset size bound and immutable revision.

Refreshing a design is an explicit three-way operation over original native,
authored and newly captured DDN. Native data blocks changed on only one side
can be retained or refreshed; a block changed differently on both sides is a
conflict. Authored views, annotations and appearance source remain unchanged.
New native blocks and previously absent generated views may be added. Every
resulting view must validate through the paired DDN runtime before adopting the
candidate; unresolved references, removed blocks used by a view, overlapping
edits or incompatible workspace structure leave the entire authored draft and
baseline intact. Conflicts identify their file/block for manual reconciliation.
This deliberately conservative merge does not infer deletions or native SQL.

Explicit privilege differences
------------------------------

Native privilege records use the provider's complete grant identity: grantee,
object, column, privilege, grantor, grant/admin option, principal/object types and
default-role flag. They are not identified by their display label. A desired
record may carry ``grant_change`` with ``operation`` (``grant`` or ``revoke``),
exact grantee ``confirmation`` and Boolean ``allow_cascade``. Removal from a DDN
view or document is never a revoke. Changing a grant's identity or options is
an explicit revoke followed by a separately reviewed grant, not a label edit.

Planning requires an available native privilege catalog and resolves targets
against the selected database. Object/column, database, DDL-class and role
membership syntax uses the native compiler. Revocation of a grant/admin option
requires explicit cascade acknowledgement; native dependent grants may be
removed. The plan discloses this security effect, guards the observed privilege
catalog and rediscovery checks the exact requested grant identity. Privilege
reviews execute separately from structural DDL so ordering cannot silently
change security assumptions. No server-security-database user creation authority
is inferred from a database grant.

Relational design handoff
------------------------

An edited relational DDN workspace can prepare native review directly from its
``x_record.native_json`` definitions. The adapter compares its saved original
relational definitions with the edited definitions and a fresh catalog from the
selected registration. Matching requires the complete endpoint/database/object
UID. It builds baseline and desired catalog documents for the existing
three-way planner, retaining uncaptured objects unchanged. The original native
facts, not the latest capture, form the baseline for the selected definitions.

Diagram labels, field display types, view membership and edge geometry remain
presentation; native changes use the explicitly recorded native facts. Missing
or hidden relational elements do not imply deletion. New identities and missing
native objects require explicit catalog design reconciliation. Duplicate or
foreign UIDs, changed adapter-only foreign-key column labels and unsupported
definitions block the handoff. Preparing this handoff executes no metadata SQL;
normal preview, durable review, confirmation and drift checks remain mandatory.
