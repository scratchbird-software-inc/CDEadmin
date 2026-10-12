Firebird functional completion
*****************************

Owner decision: 2026-10-10
==========================

Implementation scope reaffirmed, 2026-10-10
------------------------------------------

The owner requires implementation of all four recorded areas: bidirectional DDN,
the three dashboard scopes and independent collection, all FlameRobin parity
workflows, and compact native forms. Documentation, placeholders, adapter tests
or a successful application build do not close that scope. The requirements
below remain open until their end-to-end acceptance rules are satisfied.

All functionality identified by the FlameRobin source comparison is required
for ScratchRobin. A SQL editor capable of executing an equivalent statement is
not a substitute for an explicitly required management workflow. Reuse shared
forms and infrastructure where appropriate, exposing only operations supported
by the selected native engine and version.

This is an acceptance backlog, not a claim that the features are implemented.
The source comparison examined FlameRobin revision
97358ac6e429c8f49217e6c67fd22825daf303d3 and ScratchRobin revision
5aab659c8d29f1cd52b824617ddeba08a5eb849a plus ongoing Firebird navigation changes.
The retained source evidence is
/home/dcalford/SandBox/progress_reports/scratchrobin-flamerobin-comparison-20261010.txt.


Current-run scope correction, 2026-10-10
---------------------------------------

The owner defers persistent monitoring history and the ScratchBird connection
until a later run. Windows/macOS implementation qualification and QA belong to
the separate platform teams. These items remain future/cross-team obligations;
they are not blockers or acceptance requirements for this run, and must not be
reported as unfinished work assigned to this run.

Everything else remains in scope: published dashboard definitions and authorized
live bindings, standard metrics, trends and drill-downs using available samples,
metadata/data-to-DDN, DDN-to-native schema and semantic diff/apply, all remaining
FlameRobin parity workflows, compact native forms and end-to-end qualification
on the available local platform. A bounded volatile sample window must display
its gaps and retention limits; it must not imply durable historical coverage.

This deferral applies to monitoring observations, not to persistent searchable
SQL history (FB-COMP-05), saved dashboard definitions, DDN design assets or saved
test-data recipes. Those persistence requirements remain in this run. Completing
a draft editor alone does not complete dashboard publication or FB-COMP-18.

Required workflows
==================

* FB-COMP-01: Native SQL/PSQL profiling. Start/finish profiling in the admitted
  attachment context and display real PSQL/record-source measurements. Gate by
  server capability, package availability and permissions.
* FB-COMP-02: Query statistics. Show execution timing and native before/after
  counters with their actual attachment/statement scope clearly identified.
* FB-COMP-03: Metadata and data export. Support object, branch and database
  scopes, metadata/data/both selection, dependency-aware DDL, comments/grants,
  output download, and qualified import/round-trip behavior. Placeholders do
  not satisfy acceptance. Preserve distinctions from backup and result export.
* FB-COMP-04: Native language editor. Add syntax-aware display, metadata-aware
  completion, formatting, selected/current/from-cursor execution conveniences,
  and file handling while preserving native grammar authority and transactions.
* FB-COMP-05: Persistent searchable SQL history. Scope records by user, endpoint,
  database and dialect; support search, reload and previous/next navigation with
  explicit retention and sensitive-value handling.
* FB-COMP-06: Selected-row SQL generation. Generate INSERT, UPDATE, UPDATE OR
  INSERT and IN-list text using native quoting, typed values and explicit keys.
  Preview/copy must not execute mutations implicitly.
* FB-COMP-07: Test-data generation. Provide random/sequential/file-backed and
  existing-column sources, NULL rates, saved recipes, FK-aware ordering, cycle
  handling, preview, bounded execution and explicit cancellation outcomes.
* FB-COMP-08: Multi-database metadata search. Search names, kinds, descriptions,
  source/DDL and fields; report inaccessible/incomplete catalogs and navigate
  results to their native object identities.
* FB-COMP-09: ERD display/editing through DDN. Adapt native tables, columns,
  constraints and relationships to DDN and preserve object identity through
  selection and editing. Model edits require native change preview, validation
  and an explicit apply operation; editing a diagram never silently changes SQL.
* FB-COMP-10: Object-context code templates. Provide configurable SELECT/INSERT/
  UPDATE/DELETE, trigger, procedure/execute-block and extraction templates with
  native metadata substitution and editor handoff.
* FB-COMP-11: Whole-table column ordering. Provide ordering controls and a native
  preview/apply workflow using existing POSITION support; preserve stable object
  identities and refresh from the actual database after completion.
* FB-COMP-12: Dedicated BLOB viewing/editing. Reuse chunked transfer and typed
  values; provide text/binary viewing, file import/export, NULL-versus-empty
  handling and applicable text editing/line-ending controls.
* FB-COMP-13: Firebird Docker provisioning. Provide an end-user workflow with an
  explicit execution host, version, ports, storage and credential scope. Existing
  developer demo scripts are not a finished end-user feature.
* FB-COMP-14: External ISQL launch. Define desktop/local-agent execution and
  credentials explicitly; never launch on an unintended web-server host.
  Linux desktop admission uses the Electron host's local executable picker and
  a separate local terminal. The application server only returns a credential-
  free, owner-scoped TCP connection description; it never starts a process.
  The user supplies credentials for this independent ISQL attachment explicitly.
  Passwords are passed in the child's environment, never command arguments,
  saved preferences, receipts or logs. The executable must identify itself as
  Firebird 5 ISQL before launch. No shell command string is constructed.
  The form displays the execution host, exact database/role/charset/dialect and
  the fact that ISQL owns its own transactions. Process launch is not connection
  or transaction-success evidence. Browser-only clients cannot launch tools on
  the application server; they require the desktop host. Remote desktop targets
  use an explicit TCP endpoint; embedded/server-local paths cannot be silently
  reinterpreted on a different client machine. Windows/macOS host launch and QA
  remain owned by their platform teams.
* FB-COMP-15: Registration clone/move. Copy or relocate registration metadata
  with credential rules and collision handling. Distinguish it from physical
  database copying or migration.

  A registration has its own stable target ID; two named registrations may
  reference the same native filename on one server. Clone creates a new inactive
  registration; move preserves its ID and leaves it inactive under an explicitly
  chosen, same-owner Firebird server. Neither operation opens, creates, copies or
  drops a native database. Duplicate display names on the destination are refused
  rather than merged. Existing target IDs and files survive configuration upgrades.
  Both endpoint configuration guards must admit a cross-server move before any
  metadata changes; pending sessions are never committed, rolled back or rerouted.
  Configuration-generation comparisons serialize concurrent transfer writes;
  a changed generation refuses the transfer and requires a refreshed selection.

  The form explicitly chooses source registration credentials or destination
  endpoint credentials. Source credentials copy the saved encrypted password,
  username, role and character set into a registration-owned scope. A missing
  saved password remains missing and requires a prompt; process-only passwords
  are never silently persisted. A cloned saved credential does not change when
  the source credential later changes. The inherited option deliberately follows
  the destination endpoint's credential policy. Ciphertext and plaintext passwords
  are excluded from catalogs, form drafts, transfer previews and responses.
  Native verification after the local operation is a separate explicit action;
  relocation does not assert that the filename exists on the destination server.
  Registration passwords participate in master-key rotation/migration and
  owner credential reset. Clearing a server's saved credentials clears its
  registration passwords too, after pending-work admission. A password saved
  while verifying a registration-owned identity updates only that registration.
* FB-COMP-16: Recreate-empty shortcut. Reuse guarded native drop/create with
  explicit destructive confirmation and report partial failure accurately.
  The shortcut first opens the engine-owned drop form. Only a successful native
  drop receipt permits an explicit transition to the server-scoped create form,
  prefilled with the former database filename. Creation remains a separately
  reviewed and confirmed operation; it does not preserve schema, data or database
  identity. A failed or uncertain drop never starts creation or retries the drop.
  A failed local registration cleanup also blocks the transition pending repair.
  Closing the workflow after drop leaves the database absent. Creation failure
  must not suggest that the original database was restored. Existing drop/create
  form reference numbers identify both reused forms.
  The shortcut requires a configured server database-creation root before drop;
  an inferred root from a database registration is insufficient because that
  registration is removed after native drop. The workflow never silently expands
  the server's approved filesystem scope.
  Successful registration changes request a refresh of the owning server's
  navigator branch; the replacement registration receives its own new identity.
* FB-COMP-17: Native event monitor. Subscribe/unsubscribe, show event counts,
  manage disconnect/reconnect and cleanup using the supported native driver.
  FlameRobin's residual IBPP path is not current fb-cpp qualification evidence.
* FB-COMP-18: DDN dashboards. Use a display-only DDN viewer and a separate DDN
  editor reached from an authorized context-menu item. Collect real provider
  measurements through dedicated monitoring connections; use ScratchBird as the
  intended historical store. Persist versioned definitions/bindings separately
  from observations and handle stale/unavailable data and native capabilities.
  Simulated FlameRobin replication values must not become product telemetry.

* FB-COMP-19: Monitoring worker authentication. Configure a dedicated native
  username/password and optional role per server or database collection policy,
  independently of interactive credentials. Also permit explicit registration
  credential reuse. Seal credentials for the admitted background worker, show
  the active account without exposing passwords, and support stop/reconfigure/
  restart with confirmed old-worker release. Cover failed authentication, revoked
  scope, expiry, and collection without an interactive connection.

Shared acceptance rules
=======================

For each workflow demonstrate tree/menu -> scoped form -> provider/API -> native
result -> error/outcome handling -> refresh. Include reconnect and permission
cases where relevant. Keep stable form reference numbers. Existing drivers,
column operations, result exports and streaming paths should be reused.
Record actual implementation and qualification separately; mock or structural
checks do not prove live engine correctness.

Version-gated syntax described in FlameRobin's roadmap is not authority for
Firebird 5.0.4. Newer server support requires its own exact-version contract and
qualification. Do not expose unsupported CSV external-table or newer EXPLAIN
syntax solely because the reference UI contains a template.

DDN ownership and dependency intake
==================================

The owner-designated source is
/home/dcalford/Sandbox/Diagram-Design-Notation/.
DDN owns ERD/dashboard rendering and visual editing. ScratchRobin owns native
catalog adapters, authorized data bindings, persistence, identity mapping and
validated native operation execution. Use documented public APIs; do not fork
DDN internals or treat rendered SVG as authoritative database metadata.

Refresh the consumed DDN copy before every build and every commit-validation
test run, following the repository AGENTS.md intake procedure. Refresh runtime,
editor/tool and their assets as a coherent snapshot; preserve current licenses
and notices and record source revision plus artifact hashes. Reject unavailable,
inconsistent or incompatible intake rather than silently testing an old copy.
Build from an isolated source snapshot if current distributed artifacts are stale.

Original migration finding: ScratchRobin's library.js expected runtime
0.5.0-draft.2 and DDNDesigner 0.1.0-preview.1. The sister project is currently
0.8.0, with a unified shipping tool instead of the old separate Designer
bundle. Its current licensing/notices also differ from the old distribution.
A paired runtime/tool adapter migration and refreshed provenance were required;
changing version strings or replacing just the viewer would not qualify it.

The current implementation uses the 0.8.0 public runtime and unified tool.
``tools/refresh_ddn.py`` captures/rebuilds them together outside the sister
checkout and records source/artifact hashes. Webpack invokes that gate; direct
test runs still require explicit intake. The previous distribution is retired.
The passive viewer and separate editor reuse versioned project assets, preserve
source changes during saves, detect conflicts and block unapplied editor drafts.
Real-browser bridge checks and adapter/form tests cover this boundary. This does
not complete native metadata mapping, diff/apply, dashboards or the other
FB-COMP workflows.

Bidirectional DDN contract
==========================

``ddn_database_roundtrip.rst`` owns database/server discovery into DDN scripts,
multi-view metadata/data visualization, DDN-to-native metadata creation, and
semantic metadata differences with native migration statements. Firebird work
under FB-COMP-03, FB-COMP-09 and FB-COMP-18 must satisfy that contract. DDN is a
bidirectional design/exchange tool, not merely a viewer.

Form adaptation
===============

``firebird_form_parity.rst`` maps FlameRobin's individual dialogs and frames to
ScratchRobin equivalents, specifies control grouping and native bindings, and
separates presentation work from missing backend workflows.

Standard dashboards
===================

``firebird_dashboards.rst`` proposes engine/server/database widgets, exact native
sources, DDN presentation, collection/visibility rules and unavailable metrics
for FB-COMP-18. Numeric definitions alone are not live collector qualification.

Whole-table ordering contract (FB-COMP-11)
=========================================

The Firebird table context exposes Reorder columns with a fixed list populated
from the inspected native column order. Move-up/down controls change ordering
only; the list cannot add, remove or rename columns. The backend independently
requires an exact permutation of all observed column names and rejects system
and virtual relations. It compiles sequential POSITION moves needed
to transform the observed order into the selected order, using one-based native
POSITION values and engine identifier quoting. This does not recreate columns,
change their types or copy row data.

The native execution path rechecks the relation identity and complete current
name/position list before the first move. Add/drop/rename/reorder drift requires
refresh and a new preview. Existing provider plan confirmation, task savepoint,
owned-versus-borrowed transaction behavior and outcome contracts apply. The
whole operation is staged together; it never commits a borrowed user transaction.
Native rediscovery updates the explorer after an owned committed operation.

Persistent SQL history contract (FB-COMP-05)
==========================================

Firebird query history uses the existing application query_history table with a
reserved provider-history namespace, separate from PostgreSQL history and from
monitoring retention. Every access binds the authenticated owner, registered
server, database-target identity, Firebird language and client SQL dialect. The
policy defaults to source capture disabled. Enabling capture explains that SQL
literals may contain sensitive data; parameters, result rows and connection
credentials are never recorded. Credential-bearing source (PASSWORD/SECRET/TOKEN
keywords) is omitted conservatively, and a per-execution sensitive flag suppresses
source capture. Omitted text is not reconstructed from query results or logs.

Owners configure retention days (1–365) and record count (1–1000), search retained
source, load an entry into the editor without executing it, move previous/next
through the current result list and explicitly clear the selected scope. Expired
and excess records are removed on history access and capture; no background
monitoring-history service is implied. Source above 64 KiB is omitted as a whole,
never silently truncated into a different executable statement.

History distinguishes a submitted request, an accepted request and a request
error; these are not native transaction outcomes. Single-statement and legacy
script submissions are recorded at their host execution boundary. Retained
script preparation is separately labelled as preparation and never as execution.
History storage errors do not retry or cancel an already submitted native query;
the workspace displays the recording warning separately. The application store
uses transactions independent of the user's native Firebird transaction.

Native statement profiling contract (FB-COMP-01)
------------------------------------------------

The Firebird query workspace offers an explicit profiled single-statement run.
The user confirms that starting a native profiling session replaces any active
profile on the same attachment. Profiling is not enabled for prepare-only plans,
ISQL scripts or streaming runs. Normal parameter binding, dialect, row limits
and transaction behavior remain those of the original statement.

Before executing user SQL, require the native RDB$PROFILER package and start the
Default_Profiler on the existing user attachment. Native package execution and
plugin privileges remain engine-authorized. Use separate short control/read
transactions on that attachment; never commit, roll back or refresh the user's
main transaction. The plugin flushes its own data autonomously and may create
PLG$PROF objects. The user must consent to that persistent native diagnostic
storage and its native access rules; this is separate from application SQL
history and monitoring retention.

Finish and flush after the bounded query completes or fails, then read fresh
profile-scoped PSQL and record-source measurements, requests and statement
identities. Display counts, nanosecond units, profile identity and per-section
limits. Do not substitute invented timings for unavailable native measurements.
A start failure prevents user SQL dispatch. A finish/read failure preserves the
original SQL outcome, reports partial profiling, and never retries user SQL.
An uncertain profiler start/finish blocks reuse of that attachment until it is
closed. Connection loss does not confirm rollback or erase already flushed
native profiling data. Existing externally-issued profiler commands may affect
the same attachment; results identify the observed profile, not exclusive
ownership outside this application.

Query statistics contract (FB-COMP-02)
-------------------------------------

An optional statistics flag on single-statement execution captures current-
attachment MON$ I/O and record counters before dispatch and after bounded fetch
and cursor release. Each observation uses its own fresh read transaction;
observation never refreshes or finalizes the main transaction. Differences are
attachment-window measurements including monitoring overhead, not isolated
per-statement engine counters. Native database-info I/O counters are database-
instance statistics and must not be mislabeled as attachment counters.

Show both samples, nonnegative deltas and measured host elapsed nanoseconds.
Host elapsed spans native dispatch, execution, fetch and result cleanup; it is
not server CPU time. Missing observations, reset counters and read failures
remain explicit. Diagnostic failures do not suppress or repeat user SQL. These
samples are volatile result details, not persistent monitoring history.

Native array validation correction
-----------------------------------

Both domain creation and structured column creation require every array upper
bound to be strictly greater than its lower bound. Equal bounds are rejected by
Firebird 5.0.4 with an illegal-dimension error; a one-position array must not be
advertised as a native supported form. Signed bounds and up to sixteen
nonempty native dimensions remain available.

Firebird editor display and formatting contract (FB-COMP-04)
-----------------------------------------------------------

The query editor provides a native-token syntax view alongside its plain text
view. Firebird keyword hints come from the admitted Firebird lexical inventory;
metadata completion uses only discovered objects in the current workspace.
Quoted names preserve spelling and escaping. Completion coverage must identify
that unloaded or inaccessible metadata is absent rather than inventing objects.
SQL dialect 1 treats double quotes as strings; dialects 2/3 display quoted
identifiers. Alternate quoting and character-set introducers are recognized.
The editor's display parser is not native grammar validation.

Formatting changes whitespace only, preserving every non-whitespace token and
all literal/comment contents. It verifies this invariant before applying the
change. Unterminated quotes/comments cause refusal. Firebird formatting must
never invoke the shared editor's PostgreSQL formatter. Existing script UTF-8
file import/export and native script preview/execution remain available.

Firebird scoped execution conveniences (FB-COMP-04)
--------------------------------------------------

Selection, current-statement and from-cursor controls prepare an explicit source
preview. They do not execute on text selection or cursor movement. Current and
from-cursor modes start at the enclosing statement boundary; a cursor inside
PSQL must not dispatch a partial BEGIN/END block. Literals/comments and nested
CASE/BEGIN blocks protect internal delimiters. Explicit ISQL SET TERM changes
are honored. Incomplete quotes, comments or blocks are refused.

A single SQL fragment without inherited script settings uses ordinary native
statement execution and its parameter bindings. Multiple fragments or inherited
SET SQL DIALECT, SET AUTODDL and SET BAIL settings use the existing native script
runner. These inherited settings are included visibly in the prepared preview;
preceding SQL and transaction commands are never replayed. Script delimiters may
be normalized to a collision-free delimiter without changing SQL fragments.
A final explicit Run prepared source action uses the same pending-operation,
unknown-outcome, stop and transaction rules as existing execution. Editing the
original source invalidates its prepared execution preview.

Materialized grid BLOB editor contract
-------------------------------------

The dedicated Firebird BLOB form (SR-F-001360) edits an already materialized
text or binary value. Opening, cancelling, importing or downloading a value
never dispatches SQL. Apply stages the typed value in the existing row editor;
Save and the existing transaction controls retain their normal meaning.
NULL and an empty value are distinct. Text file import is strict UTF-8;
binary import preserves every byte. Text export is UTF-8, not a claim about
physical database character-set bytes. Unchanged text retains its original
line endings. Editing with preservation selected is refused when the original
contains CR characters: the user must explicitly choose LF or CRLF.

This form bounds editable/imported values to 1 MiB. Larger values continue to
use the existing chunked query-transfer workflow; the form must state this
limit and never silently truncate. Read-only columns permit viewing/export,
but not staging or importing changes. Custom BLOB subtypes without an admitted
typed codec are not treated as text or binary editors.

The existing bounded BLOB stream reader also offers hexadecimal/ASCII and
strict UTF-8 views of the current chunk. Displayed offsets remain exact.
A split UTF-8 character is reported rather than replaced or guessed; full-file
download remains the way to recover the complete value. Changing representation
performs no native fetch. Advancing the reader still obeys the existing exclusive
stream ownership and forward-only rules.

Registered-database metadata search contract
-------------------------------------------

SR-F-001361 searches an explicitly selected set of retained Firebird database
registrations on the current server. Each database uses its authorized native
catalog route independently of the user's SQL attachment or active database.
Search is a case-insensitive literal substring over selected name, kind,
description, native source/DDL and field metadata, with an optional exact kind
filter. It does not execute SQL supplied as search text or interpret regex.

The browser requests one database at a time, retains per-database successes and
failures and supports stopping before the next request. An in-flight catalog
request may finish; stopping is not a claim of native cancellation. Results
carry server registration, database target, native resource ID and generation.
Opening a result creates the corresponding scoped object workspace, which must
rediscover/inspect through its normal authorization and generation checks.

Catalog visibility is that of the registered attachment credentials. Report
native catalog observations and missing-DDL counts; absence of a match is never
proof of absence outside that visibility. Bound each database result to 500
matches and each matching snippet to 240 characters; explicitly mark truncation.
Names and resource identity are never inferred from text snippets. Failures
expose their type, not raw native messages that could reveal connection secrets.

Selected-row SQL preview contract
--------------------------------

SR-F-001362 selects rows from the currently fetched Firebird grid page, never
from unsaved editor drafts. It generates INSERT, UPDATE, UPDATE OR INSERT and
single-column IN predicates with exact quoted identifiers. Update/upsert require
explicit matching columns; metadata key flags supply defaults but do not prove
uniqueness of a user-chosen alternative. NULL IN-list values require an explicit
IS NULL alternative. Generated mutations are previews and carry no execution
permission, transaction outcome or automatic commit.

Bound-parameter output preserves the existing typed wire values (including
arrays, binary BLOBs and zoned values) alongside each independent statement.
An optional inline-literal mode supports admitted scalar representations;
values without an exact native literal are refused with instructions to use
parameters, never stringified approximately. Maximum selection is 100 rows and
output is bounded to 1 MiB. Each statement and its ordered parameter array can
be loaded into the same database's SQL editor without execution. Loading is
blocked while a query or retained script is active. The preview makes clear
that executing generated statements can duplicate or change existing data.

Native event subscription contract
----------------------------------

SR-F-001363 subscribes named Firebird events on a dedicated, authenticated
attachment for the selected registered database. Subscriptions are owned by the
application user, endpoint route and target. They never borrow, commit or roll
back the user's SQL transaction. Firebird delivers POST_EVENT notifications at
commit; the monitor reports observed cumulative native counts, not durable
message delivery or a recoverable event history.

The initial application policy permits 1–15 unique UTF-8 event names, each at
most 127 bytes, four active subscriptions per owner and 32 per process. A
subscription expires after 120 seconds without an authorized poll. The native
worker samples cumulative counters without flushing them (flush/read could lose
concurrent increments), performs a fresh short diagnostic read every ten seconds,
and closes its collector and attachment on stop, expiry or failure. Diagnostic
transactions are finalized immediately. A failed diagnostic or stopped native
event thread marks a delivery gap; counts already observed are retained.

Reconnect is explicit: stop/release the old subscription, then create a new
subscription with a new identity and zero-based observation interval. Missed
events cannot be replayed. Cleanup must report confirmed release or uncertainty;
a socket failure or cleanup timeout cannot imply successful native release.
Subscription state is process-local, so deployment requires request affinity.
An unknown subscription after restart or a request to another worker is reported
unavailable; no subscription is silently recreated. Closing the form requests
stop, with idle expiry as fallback. This is separate from dashboard collection.

Native retained-session identity correction
------------------------------------------

Firebird network and embedded Session/Execution DTO identity includes the exact
admitted manifest evidence reference, not the generic pilot evidence token.
The host continues comparing the complete provider identity on every retained
session operation. A manifest/profile mismatch fails closed. This correction
must be qualified through the actual host open/read/close path; direct driver
calls alone do not exercise that identity fence. An old incompatible retained
session is not silently relabelled as a new provider session.

Network event delivery requires Firebird's auxiliary event connection, in
addition to the normal database port. NAT/container deployments must expose a
reachable configured RemoteAuxPort; normal SQL connectivity alone does not prove
event delivery. ScratchRobin does not silently change server configuration.
A failed subscription reports the failure and its actual cleanup state. When
opening fails before handing back a handle, cleanup remains unconfirmed unless
separate native ownership evidence proves release.

Event names can be added/removed as individual lines and loaded/saved as bounded
UTF-8 files. The viewer keeps the latest 1000 observed count-increase entries
with subscription identity and observation timestamp, and exports JSON Lines.
Clearing that display does not flush native counters. Observation timestamps
are not transaction commit timestamps. These event observations are neither
persistent monitoring history nor a guaranteed message log.

Credential acquisition and native attachment authentication occur in the
initiating authorized request context. The event worker receives the already
opened dedicated attachment, not a copied HTTP session or stored plaintext
password. Native subscription setup, sampling, short diagnostic transactions and
release then belong to that worker. Reconnect obtains fresh route authorization
and credentials in a new request.

Object-context SQL templates
----------------------------

SR-F-001364 renders editable Firebird source templates against an authorized
native catalog object. Table/view templates include SELECT; ordinary user-table templates include
INSERT/UPDATE/DELETE and a PSQL trigger scaffold. External tables omit UPDATE
and DELETE; system objects omit generated mutations. View mutation templates
require native preparation evidence before they can be offered as defaults. General PSQL
procedure and execute-block scaffolds require an explicitly supplied new object
name where applicable. Definition extraction uses the provider's observed DDL
and reports when unavailable. Templates are previews, not native validation or
execution permission. UPDATE/DELETE defaults require the user to replace an
explicit FALSE key predicate, preventing an accidental all-row command.

Supported substitutions are exact quoted object/column/new-object identifiers,
ordered parameter markers, assignments and observed definition text. Unknown
substitutions fail; there is no expression evaluation. User-edited templates can
be saved/loaded as bounded UTF-8 JSON files and reused in another object context.
Loading a rendered statement into the same database editor never executes it.
Placeholder values remain explicit NULL parameters for the user to replace;
PSQL/multi-statement definitions must use the existing native script controls.

Bounded test-data recipe contract (FB-COMP-07)
--------------------------------------------

SR-F-001367 provides an explicit multi-table recipe and materialized preview.
Recipes use exact discovered table/column identities. Sources are omitted native
defaults, constant typed values, seeded random integer/choice, exact sequential
integers, file-imported JSON values, visible existing-column samples, or values
from another generated table. Exact integers use decimal strings, never rounded
JavaScript numbers. NULL percentages are explicit. Computed/noninsertable columns
are omitted. Native preparation remains the authority for type and permissions.

Preview is bounded to 32 tables, 1000 rows per table, 5000 rows total and 4 MiB
of materialized values. File/recipe input is strict UTF-8 JSON bounded to 1 MiB.
Existing sources identify their sampled database/table/column and limited page;
they never imply a full-table scan. Seeded output is repeatable for the same
recipe and samples, not cryptographic randomness or a uniqueness guarantee.
Generated-column sources preserve the row index across composite key columns.
Dependency ordering follows generated references and native foreign keys among
selected tables. Cycles are rejected before dispatch unless the user explicitly
chooses NULL or already-existing values to break the dependency; constraints
are never disabled. This does not infer that NULL is allowed by the engine.

Preview/download/save/load never mutate a database. Execution uses a separate
retained Firebird session and the existing validated native insert plans. Every
row must return evidence that it is staged in that session. No implicit commit
is allowed. Stop prevents the next row request; the in-flight row may complete.
Completed rows remain pending until explicit commit or rollback. Any lost/failed
row response stops dispatch, blocks retry and reports an uncertain pending
state. Native transaction controls and their receipts decide the actual outcome.
Closing the form requests session release; it never claims confirmed rollback
from a browser close. Recipes may contain sensitive sampled/file values; saving
is explicit and produces a user-controlled local JSON file, not monitoring
history. Preview is invalidated by recipe edits or database-scope changes.

Generator sessions use the admitted ``firebird-test-data`` session purpose.
The host preserves the selected route, credential and database identity but
sets SNAPSHOT, WRITE, bounded lock timeout, auto_commit=false, no_auto_undo=false
and ignore_limbo=false on this separate session only. User registration defaults
and interactive sessions are unchanged. Other engines and arbitrary purposes
are refused. This prevents a registered auto-commit TPB from committing generated
rows before the explicit finalization control.

Recipe constant/choice/file values reject fractional or unsafe JavaScript
numbers; exact decimal strings and admitted typed envelopes preserve native
values. Typed-value nesting is bounded to 32 levels. Materialization checks
output size as each row is generated, before accumulating an oversized batch.

Linux desktop Docker provisioning contract (FB-COMP-13)
------------------------------------------------------

SR-F-001368 is a Firebird connector-root workflow executed by the local Electron
host, never the web application server. The user selects the local Docker CLI
and an explicit Docker context. Review identifies that context's daemon endpoint
and daemon identity, exact resolved official Firebird image, published SQL and
optional event ports, named persistent data volume, database filename and
credential scope. The initial qualified version is Firebird 5.0.4; other image
versions require matching provider qualification before exposure.

Preparation may pull the requested official image and resolve its immutable
image ID; it must not create containers or storage. An explicit confirmation
applies the immutable review once. Recheck the daemon/context and image before
mutation, and recheck the daemon before each resource creation and start.
Context discovery returns names, endpoints and the current selection for explicit
review; it never silently substitutes an available daemon for an unavailable one.
Names, ports and database filenames are bounded values passed as
individual arguments, without shell composition. Publish to the chosen IPv4
bind address; remote contexts are explicitly displayed and never treated as the
local desktop. The Firebird auxiliary event port is configured and published
at the same port number when selected; SQL connectivity alone is not event proof.

A new named volume mounts at the qualified image's data directory
``/var/lib/firebird/data``. Existing volumes or containers are not overwritten.
User-selected names and an ownership label identify created resources. Errors,
timeouts, closing the form or lost responses do not authorize retry, container
delete or volume removal. Retain and display partial/uncertain outcomes and
exact names for reconciliation. A running container is not proof of native
server authentication, database readiness or successful registration.

The separately entered bootstrap SYSDBA password is passed through the child
environment, never shell text, process arguments, form persistence or receipts.
The Docker daemon retains that environment in container configuration, visible
to Docker administrators. The qualified image reapplies this bootstrap password
on restart; a later native password change alone does not update that value.
The form must make this concrete credential scope visible before confirmation.
Registration is a separate explicit handoff to the existing Firebird registration
form with host/port/database prefilled; its native verification and credential
choice remain authoritative. Browser-only clients cannot provision on the web
server. Windows/macOS launch and qualification remain with their platform teams.

A bind-directory alternative is admitted only for an explicitly selected empty
local directory and a Unix-socket Docker context. Preserve and recheck canonical
path, device/inode and emptiness before creation. Remote contexts cannot reinterpret
a desktop filesystem path. Do not chmod, delete or overwrite existing directory
contents; native directory permissions may prevent startup and must be reported.
The user can instead select a new managed Docker volume.

The desktop stores credential-free operation receipts under its application data
directory before each mutation phase. A consumed review cannot be applied again;
after restart it supports receipt inspection, not implicit replay. Retain known
container/volume identities and distinguish Docker command completion from
native Firebird verification. Receipt state is an observation of Docker commands,
not database transaction or recovery authority.

Native metadata script export contract (FB-COMP-03)
-------------------------------------------------

SQL output is a separate choice from the documentary DDN capture. It uses the
same authorized target, selected native identities and catalog generation.
Native statement arrays are indivisible: PSQL bodies and quoted semicolons must
never be split by a generic delimiter. ISQL output selects a terminator absent
from every statement and emits SET TERM around the script. It does not embed
credentials, CONNECT, CREATE DATABASE, COMMIT or rollback decisions.

Creation statements preserve native comments, grants, inactive index state and
owner execution requirements. Dependencies within the selected scope determine
creation order; prerequisites outside a branch are named explicitly. A cycle,
missing definition, ambiguous dependency or unsupported grant is reported against
the exact object and prevents presenting a partial script as a complete export.
Columns and constraints already included in their table, constraint-maintained
indexes/triggers and members included in their package are not created twice.
System and operational catalog observations are not user DDL. Server security
principals, external modules and filesystem paths are prerequisites, not portable
database objects. Catalog visibility and cached/refreshed provenance remain
visible. Metadata output alone does not satisfy the data/both or native replay
acceptance requirements of FB-COMP-03.

The capture includes the catalog owner for domains, routines, packages and
exceptions as well as relations, sequences, filters and roles. Native SQL
contains a machine-readable comment with capture provenance, prerequisites and
creating-user requirements; downloaded files retain these requirements outside
the viewer. Built-in NULL-grantor rows are engine initialization, and exact
owner-to-owner grant-option rows are restored by CREATE under that owner. They
are recorded separately from replayable explicit grants. This avoids generating
unsupported GRANT USAGE ON DOMAIN from Firebird's implicit owner metadata.

Native data transfer contract (FB-COMP-03)
----------------------------------------

Data capture owns a separate READ ONLY SNAPSHOT transaction with autocommit off.
It cannot reuse, refresh, commit or roll back an interactive user's transaction.
All admitted table pages in one capture share that snapshot. Success, cancellation
and failure release the cursor and end the owned snapshot; no idle export
transaction remains after preparing a download. A bounded export must fail with
an explicit limit instead of silently publishing a truncated database export.

Lossless transport retains exact numeric text, temporal precision, native time
zones, array bounds, binary envelopes, NULL and empty values. Computed outputs
may be observed but cannot be inserted. Identity values need explicit native
OVERRIDING SYSTEM VALUE on replay; an identity column must never simply be
omitted when recreating relationships. Database generators are independent from
MVCC row snapshots; an export must distinguish initial sequence definitions from
observed current values and concurrent allocation. External-table files and
attachment-local temporary rows do not have ordinary persistent MGA snapshot
semantics. Do not silently include those as durable database row contents.

Import is a reviewed, explicit operation against an independently selected
native destination and one owned write transaction. Decode typed values through
the existing native driver boundary, validate destination types and dependency
order, preserve data as bound values and do not execute arbitrary statements
supplied by a data document. Commit or rollback requires an explicit outcome;
a lost reply is uncertain and cannot trigger automatic replay.

Data import preview accepts only the versioned data archive, rejects duplicate
JSON keys and duplicate table/column identities, and matches every destination
by its exact native table/column name and type layout. It does not trust exported
resource IDs as destination authority. Native computed outputs are excluded from
INSERT values. Explicit identity preservation is surfaced only for Firebird
base-table INSERT and compiles OVERRIDING SYSTEM VALUE. Constraints stay enabled;
FK prerequisites outside the archive are reported, and unresolved cycles require
an explicit staging strategy rather than disabling integrity checks. Sequence
and identity allocation reconciliation remains a separate reviewed native action;
row import must not silently reset an independently advancing generator.

Package metadata export stages headers before bodies and member comments. Native
RDB$DEPENDENCIES records retain the dependent object's type as well as the
referenced type, distinguishing package-header dependencies from package-body
dependencies. Body-only cycles between package signatures do not become false
header cycles. Missing dependency provenance is treated conservatively; an
unresolved header cycle still blocks the complete script. External prerequisites
and creating-user requirements remain explicit in both phases.

Foreign-key SQL export staging preserves complete native statements. The provider
renders a separate primary table definition and final ALTER TABLE ADD actions
from native constraint metadata; export must not remove SQL fragments by splitting
or pattern matching source text. All selected tables and primary/unique keys are
created before foreign keys, including mutually referencing tables. External key
prerequisites remain explicit. Backing-index comments follow their actual creation
phase. The ordinary full CREATE rendering remains available for inspection.
Missing/incomplete staged renderings must block export instead of publishing an
incomplete restoration script. Native ISQL replay and enforced references qualify
this behavior; topological sorting alone is insufficient evidence.

SQL metadata export can stage mutually dependent standalone PSQL routine
signatures using the same non-callable signature contract as DDN application.
Complete bodies and their comments follow all signatures. External modules and
unresolved nonroutine cycles are not guessed. ISQL output disables AUTODDL and
leaves the final commit/rollback to its caller; intermediate signatures are
never represented as a successful restoration.

Explicit data-import row order
------------------------------

The import review accepts an optional complete ordered list of archive row
identities (exact table name and zero-based row offset). This permits self-
referencing and mutually referencing table layouts whose actual rows can be
inserted in an admissible order, or whose prerequisites already exist at the
destination. It never changes values or disables constraints. Every archived row
must occur exactly once; unknown, duplicate or omitted identities are rejected
before dispatch. The displayed preview and confirmation bind this order. Native
constraints and triggers remain final authority; a rejected row stops dispatch
and leaves the dedicated transaction for explicit commit/rollback. Structurally
cyclic data requiring intermediate NULL values is not silently rewritten by this
option. Such staging requires its own separately reviewed restoration workflow.

Allocation review after data import
----------------------------------

A completed import retains links to the imported identity columns and observed
user sequences. After the import transaction has returned its explicit decision,
these links open the existing native Alter form against a freshly inspected
object. Identity restart uses ALTER TABLE ALTER COLUMN; user sequences use ALTER
SEQUENCE. The system does not infer a safe next value from a snapshot maximum or
reset a generator automatically. The operator must coordinate concurrent writers
and other generator consumers, choose the next value, review native SQL and
confirm the separate operation. An unresolved import transaction cannot open this
handoff. Leaving the import form after a resolved decision releases its dedicated
session without repeating imported rows or the transaction decision.


Export branch discovery
-----------------------

The export form identifies when more native catalog pages remain and provides
an explicit Load more native branches action using the workspace's generation-
bound paging. A local name/path/kind filter only filters the loaded choices and
is labelled accordingly; it must not imply that unloaded objects do not exist.
Selecting a branch uses its native resource identity. Paging or filtering never
changes that selection or silently changes the export scope.
