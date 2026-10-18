SQLite engine functional completion
===================================

The native target is SQLite 3.53.0 through the application's Python SQLite
binding. This contract supplements ``sqlite_driver_development.rst``, the
shared SQL editor, compact forms, navigation and DDN roundtrip contracts.
Driver qualification alone does not establish management-workflow completion.

SQLITE-COMP-01: File and catalog identity
  An endpoint represents registered database files, not a remote server.
  Opening a registered file must verify its route and SQLite runtime before
  exposing database internals. Display attached schemas by their native names
  under the owning file or connection; an attachment is session-scoped and is
  not another authenticated endpoint. Preserve table, view, virtual table,
  index, trigger, column and constraint identity, including punctuation in
  names. Keep SQLite's internal objects and virtual-table shadow tables out of
  ordinary user-object groups while allowing explicit inspection. Capture
  exact ``sqlite_schema`` SQL where available, native table/index/foreign-key
  PRAGMA facts, generated/hidden columns, and native limitations. Do not imply
  that a PRAGMA value is a persisted schema object.

  An unloaded virtual-table module or unavailable column/binding observation
  does not erase its native object or block the healthy catalog. Keep the exact
  definition and navigator destination, report native refusal and incomplete
  capture explicitly, and preserve those facts in DDN. Module declaration and
  registration in the inspecting session are separate observations. Native
  module installation/loading remains a separate management requirement.

SQLITE-COMP-02: Native connection and transaction ownership
  Keep each SQLite handle on its owning worker. Explorer, editor, monitoring
  and design capture use independently owned connections and must never
  commit or roll back an interactive user's transaction. Honor route file
  containment, read-only mode, busy decisions, journal mode, active
  transactions and unknown I/O outcomes. A busy COMMIT may leave the native
  transaction open for an explicit retry; do not replay it automatically.
  Monitoring refreshes its own read transaction and may heartbeat only after
  a completed sample. An independent ``:memory:`` connection is a different
  database and cannot claim to observe the user's in-memory session.

SQLITE-COMP-03: Shared SQL editor
  Use the same compact SQL editor as other relational engines with an
  engine-labelled active-file connection selector, SQLite syntax checking,
  native parameters, scripts, saved files, optional owner/target/language
  scoped history, bounded result paging, cancellation, transaction controls,
  actual row-buffer and timing metrics, and SQLite EXPLAIN/EXPLAIN QUERY PLAN.
  Source checking must never execute the submitted SQL. Shell dot commands
  are separate from SQL. SQLite's native statement parser, not a semicolon
  split, defines trigger bodies and multi-statement script boundaries.
  Autocommit state and enabled Commit/Rollback controls must reflect the live
  connection, including explicit BEGIN in an autocommit route. A result with
  repeated column labels must retain distinct ordinal identities and values.
  The Python binding does not expose a separate native prepare timer. Report
  preparation as unavailable, measure dispatch through ``execute`` and local
  fetch/encoding separately, and label the total as dispatch through final
  buffering, including possible consumer backpressure. A normal statement
  has no inferred execution plan; only explicit EXPLAIN output supplies one.
  When a retained SQLite session is idle, source checking compiles framed
  statements under native ``EXPLAIN`` on that session without running the
  submitted statement. Syntax errors are distinct from schema-context and
  unbound-parameter cases, for which grammar remains unconfirmed. A lexical
  result alone is not reported as a successful native parse.

  Native table-valued functions include the lazily registered JSON/JSONB,
  compiled array/storage functions and result-producing PRAGMA wrappers.
  Their native columns and hidden arguments are observed without executing
  the result-producing function or wrapped PRAGMA. Catalog and DDN retain
  those observations and denied scopes. Completion resolves function aliases
  and projected columns, with hidden arguments excluded from star projections.
  Native temp/main/attachment lookup and real-table name masking are distinct
  from module registration. An engine version/source observation does not call
  user-replaced functions on the retained connection.

SQLITE-COMP-04: Data and file workflows
  Provide native table/view data browsing with bounded pages and exact values.
  Enable row edits only when a stable row identity is proved, preserving
  WITHOUT ROWID and composite-key semantics; a guessed rowid is insufficient.
  Ordinary rowid-table primary-key columns can contain NULL; rows with a NULL
  key do not receive mutation identities even when other rows in that table
  can be edited.
  Offer import/export and reusable test-data recipes through reviewed native
  SQL or contained files. Backup and restore use the qualified online backup
  contract, not a blind copy of an open database. Expose integrity check,
  foreign-key check, ANALYZE, REINDEX, OPTIMIZE, VACUUM and applicable
  checkpoint options with native prerequisites and effects. Review operations
  that cannot run in a transaction before dispatch.

  Native test-data recipes are bound to one endpoint and registered file. They
  generate bounded SQLite ``INSERT`` SQL without executing it; exact signed
  64-bit integers and BLOBs use explicit envelopes. Generated SQL is reviewed
  and executed only through the shared Query Tool, which owns its transaction.
  Registered-file endpoint DDN export captures selected files independently;
  an unavailable file is reported without substituting another registration.
  A user table can also be exported as a bounded native ``INSERT`` script on
  an independent read handle. The exporter retains signed 64-bit integers,
  finite REAL values, BLOBs and UTF-8 text including embedded NUL; it refuses
  unrepresentable native TEXT bytes and oversized tables rather than silently
  changing their storage class. Import remains a reviewed script execution in
  the shared Query Tool, under that tool's transaction controls.

  The registration/file recovery workspace uses SQLite's public recovery API
  in an isolated worker on private main/WAL/journal images. It is available
  without a successful SQL attachment and keeps endpoint/file authorization.
  Exact native values are transferred without shell SQL serialization. Reviews
  bind source/file identities, output directory, runtime/source provenance and
  options. Durable claims precede dispatch; progress, cancellation, timeout,
  exclusive new-file publication and lost-reply reconciliation are separate
  observations. Native integrity does not establish complete application-data
  recovery. Recovered copies can be registered and activated through normal
  native verification; staged-image removal retains the published file and
  receipt. Original files and interactive transactions are not modified.
  See ``tools/development/NATIVE.md`` for the native dependency and host policy.

SQLITE-COMP-05: DDN design exchange
  Capture one selected registered file's visible catalog and selected data in
  public DDN views, with exact endpoint/file provenance and capture bounds.
  Separately captured files form a bundle, not an atomic server snapshot.
  Preserve native SQL, types, defaults, generated expressions, constraints,
  indexes, triggers, virtual-table definitions and dependency evidence.
  Explicitly report facts SQLite cannot reconstruct. Read edited DDN into a
  native model, compare saved baseline, desired and freshly captured live
  metadata, and produce reviewed SQLite migration statements only for qualified
  operations. A view filter or absent object never authorizes deletion. Apply
  reviewed statements once in an owned transaction where SQLite supports it,
  retain unknown outcomes and verify postconditions by fresh discovery.
  Complex table rebuilds require explicit preservation of rows, indexes,
  triggers, foreign keys and native SQL; refuse unsafe transformations.

  The native application adapter admits additive ``CREATE TABLE``,
  ``CREATE VIEW``, ``CREATE INDEX``, ``CREATE TRIGGER`` and ``ALTER TABLE ADD
  COLUMN`` for exact main-file identities. Explicit, individually selected
  ``DROP TABLE`` operations are reviewed separately from additions; selected
  view/index/trigger removals can share an admitted atomic migration. A missing
  DDN row never implies deletion. New ordinary tables and views can be created
  with their explicit indexes and triggers in the same review. Child grammar
  and ownership are compiled in a separate empty native database containing the
  desired owner; preview executes no CREATE or DML on the registered file.
  Native ``EXPLAIN`` and authorizer facts bind statements to the exact object
  and owner. The application records a durable owner/file-bound review, claims that review
  before dispatch, applies the batch in one SQLite transaction and rediscovers
  the committed definitions or absence. Ordinary-table rebuilds support admitted
  column/type/key changes and coordinated index/trigger definitions. The desired
  DDN must carry matching table, column and child facts and explicit child-removal
  intent. Native constraints, retained views/trigger bindings and unchanged
  inbound/outbound foreign keys are checked before commit. Row IDs are preserved
  when the native key and storage identity permit that preservation.
  The rebuild runs
  in one SQLite write transaction, checks row count and foreign keys before
  commit, restores the live ``AUTOINCREMENT`` high-water mark when applicable,
  and verifies the rewritten native definition afterward. The rebuild can
  retain non-key column data across a changed name when the user supplies
  an exact old-to-new mapping; an ambiguous same-type removal and addition
  without that mapping is refused. Unresolved dependencies and unsupported
  standalone transformations remain blocked. Native ``fts3``, ``fts4``,
  ``fts5``, ``rtree``, ``rtree_i32``, ``geopoly`` and ``fts5vocab`` virtual
  tables admit exact reviewed creation and explicit ``DROP TABLE`` when the
  installed runtime provides their modules; other modules and rewrites need
  separate qualification. The rebuild follows SQLite's documented
  `generalized ALTER TABLE procedure <https://www.sqlite.org/lang_altertable.html#otheralter>`_
  within its admitted dependency scope. This bounded operation set is the
  current native DDN application contract. Unsupported transformations remain
  implementation gaps; a DDN preview never guesses a data conversion or treats
  a missing object as deletion intent.

  The native rename controls generate desired table/column names and rewritten
  references through SQLite itself in an independent empty schema. The generated
  DDN is then previewed and reviewed before applying modern native ALTER TABLE
  statements on the registered file. Complete original and resulting schema
  facts, native bindings, file identity and mapped foreign-key violations are
  verified. The operation copies no rows and preserves native row IDs and
  AUTOINCREMENT state. Contention refuses dispatch; a missing commit reply stays
  unknown without replay. Native FTS3/4/5, RTree/RTree_i32 and Geopoly table
  renames are also admitted. Generation for attached environments and
  additional installed module/function/collation adapters
  remains open.

  Virtual-table catalog families and module identities are resolved with the
  native compiler/authorizer, including quoted module names. DDN creation checks
  actual installed module availability and native ownership rather than a fixed
  list of module spellings. Native creation/query acceptance includes FTS3/4/5,
  RTree, Geopoly, fts3tokenize, dbstat, fts4aux and fts5vocab. An external-content
  owner rename selects the exact FTS4/FTS5 indexes to reconstruct in the same
  transaction. Native settings survive the reconstruction and native integrity
  checks verify the rebuilt index against its content rows. FTS5 content-row
  identity changes have a corresponding constructor adapter. Public FTS4/FTS5
  content-column changes reconstruct selected indexes and use native schema
  rewriting for dependent ordinary views and maintenance triggers. Quoted
  column names and native UNINDEXED/notindexed settings survive the change.
  FTS4 language-column changes preserve language-specific searches and rewrite
  dependent views and maintenance triggers. Explicitly selected reconstruction
  also rewrites the hidden MATCH/control column when the FTS table is renamed.
  FTS5 table-function views use the pinned native AST binder when an ordinary
  rewrite relation cannot preserve their function syntax. Native bindings select
  exact identifier spans, preserving CTE shadows, aliases, literals, comments
  and explicit view column names. The adapter recreates views/triggers within
  the same transaction and checks their final bindings before commit. Its
  application-host utility identity is part of the reviewed operation; a missing
  or changed runtime refuses dispatch. Native rename dependencies also follow
  inferred ordinary/FTS view column labels through downstream views and INSTEAD
  OF triggers, including star and expression projections. Explicit output names
  remain stable. Ordinary-content row identity changes use native expression
  observations, FTS4 content mapping views and FTS5 content_rowid rebinding.
  Generated row identifiers and new alias shadowing preserve document keys;
  harmless primary-key aliases avoid unnecessary FTS4 reconstruction. Content
  views retain their named row/document projections during base-column renames,
  including stars and nested views, without reconstructing the retained index.
  Implicit alias shadowing through views, unavailable native identities and
  attached environments retain separate adapter acceptance. Native ALTER alone can leave an external-content search table
  unusable.

  The explorer's virtual-table creation form provides structured native
  constructors for FTS3/4/5, RTree/RTree integer, Geopoly, FTS4 auxiliary,
  FTS5 vocabulary, FTS3 tokenizer and dbstat tables. Module options preserve
  tokenizer arguments, FTS4 compression callbacks and language/content mapping,
  FTS5 contentless and external-content settings, vocabulary modes and spatial
  auxiliary columns. The connected SQLite library admits installed modules and
  native constraints. Eponymous-only modules are not offered as creatable tables.
  Owned creation uses a native transaction; retained-session creation uses a
  private savepoint without committing caller work. TEMP/attached creation
  requires that retained session. Receipts distinguish staged and committed
  definitions; fresh post-state checks compare native definitions and columns.
  External-content population and synchronization remain explicit operations.

  Native FTS configuration controls generate normalized desired DDN through
  SQLite's public setting commands in an empty private module. Configuration-
  only application preserves the table definition and content, rechecks the
  original settings, verifies native results before commit and retains a durable
  once-only receipt. Existing keys are preserved; resetting a setting requires
  an explicit native value. Direct deletion of private config rows is not a
  reset workflow. FTS3/4 automerge and the installed FTS5 configuration commands
  retain their own native admission and normalization rules.

  FTS object menus also expose native optimize, rebuild, integrity-check,
  segment merge, delete-all and retained-session flush. Native FTS3/4 merge
  arguments, FTS5 signed merge budgets and external-content integrity comparison
  retain separate admission. Delete-all is limited to contentless/external-
  content FTS5; contentless FTS5 cannot be rebuilt. Reviews bind the original
  definition, settings and file identity. Native work preserves observed
  settings, restores FTS3/4 automerge after rebuild and checks index integrity
  before commit. Delete-all also checks the empty native vocabulary without
  deleting external content rows. Operation observations expose VM callback
  counts, timeout/cancellation and explicit native outcomes, with no percentage
  inference or mutation replay. Caller authorization/progress/busy policies are
  retained. SQLite interruption can roll back an entire caller write
  transaction; a lost private savepoint blocks reuse and reports uncertainty.

  The SQL editor also provides native extension inventory, review, confirmed
  load and receipt retrieval on its retained connection. The application
  operator supplies approved host library identities, SHA-256 values and
  optional native entry points. Verified private staging prevents source-file
  replacement from substituting different bytes at dispatch. Host dependencies
  are separately operator-managed. Pending work blocks loading; native code is
  never automatically retried or loaded on reconnect. SQL ``load_extension()``
  remains disabled during initialization. Failed native initialization can
  leave partial effects, blocks session reuse and reports an unknown outcome.
  A receipt remains readable before closing the session. Registered functions
  become visible to retained-session catalog, completion and native compilation.
  Native library initialization cannot be safely force-cancelled in this
  process. Optional library-specific administration remains separate coverage.
  See ``tools/development/NATIVE.md`` for the operator manifest and CPython
  build prerequisite; Windows/macOS qualification remains platform-team work.

SQLITE-COMP-06: Monitoring and dashboards
  Provide display-only DDN engine, registered-file aggregate and database
  dashboards with a separately authorized dashboard editor. An independently
  owned collector reads native PRAGMA and status values for one registered
  file, with sampling interval, bounded volatile retention, lease and optional
  completed-refresh heartbeat. File size, page/free-list counts, journal mode,
  integrity and availability are SQLite observations; do not invent remote
  CPU, server-session or network metrics. ``:memory:`` cannot be monitored
  from a second connection. Published layouts contain no sampled values;
  the viewer cannot edit them.

SQLITE-COMP-07: Contextual forms and qualification
  The explorer exposes only native applicable resources and operations, with
  stable reusable form references, compact selectors and navigable grids.
  Qualified native forms must link from their exact file/object context and
  make unsupported operations visibly unavailable. Validate the driver,
  catalog/tree, SQL, transactions, row/file workflows, DDN capture/diff/apply,
  monitoring and forms on an immutable refreshed DDN snapshot. Preserve
  independent observations and failure evidence. Static forms or a driver
  receipt alone cannot close this contract.

Remaining completion and ownership
----------------------------------

The owner's October 14/16 scope includes persistent monitoring history and its
ScratchBird backend. SQLite archive integration is wired. The owner
correction of October 16 defers ScratchBird history testing until explicitly
resumed; the remaining product work continues independently. Windows/macOS development and platform UX
qualification belong to their teams, and their evidence is required for a
cross-platform completion claim. Persistent SQL history, DDN design/dashboard
definitions and recipes remain in scope. The additional catalog, language and
complete management-workflow requirements and current gaps are recorded in
:doc:`six_engine_completion`.

Native keyword identifiers
---------------------------

Editor metadata enumerates keywords through the loaded SQLite runtime's public
keyword API and records its source identity. Constant SELECT binding probes use
``EXPLAIN`` to distinguish native name, implicit-alias, qualifier, bare-column
and window-lookahead roles. They never execute user functions or finish pending
interactive work. Denied/unavailable probes remain explicit incomplete
observations. Compiled-out keywords are not silently advertised as active syntax.

Completion preserves SQLite's Lemon fallback and ``nm``/``ids`` differences,
contextual WINDOW/OVER/FILTER token rules, quoted string names in native name
positions, native CTE/projection aliases and ASCII keyword folding. Keyword-named
tables or aliases do not accidentally terminate FROM/JOIN discovery. Native
CURRENT_DATE/TIME/TIMESTAMP expression literals are distinct from quoted columns
and valid qualifiers. SQLite's blob/string prefixes retain their native rules.
Insertion and binding qualification uses exact SQLite3.53.0 observations and the
real CodeMirror completion context; wider computed/procedural scopes retain
their separate acceptance.

Native connection captures and exports
---------------------------------------

The SQL editor's Engine options expose connection-local native session captures.
The application uses SQLite 3.53.0's public session APIs through a separately
packaged bridge admitted against the actual connection library and source ID.
Opening a capture, attaching exact tables or all current/future tables, native
enable/indirect switches, size estimates, rowid tracking and explicit capture
discard preserve the user's SQL transaction. Native object-configuration errors
remain visible. Session memory ends with its owning query connection.

Changeset and patchset exports have reviewed, target/owner-bound durable jobs.
The native streaming API writes to private application-host files; cancellation
interrupts that stream without settling SQL work. Native return acknowledgement,
iterator validation, checksums and publication have separate receipts. Repeated
start requests return the consumed receipt. Verified artifacts can be inspected
and downloaded after the SQL connection closes. The browser download manager
receives streamed file responses without a whole-file JavaScript buffer.

Lost publication can be reconciled against an existing seal. Unsealed output
can instead be inspected and downloaded as a diagnostic. A complete native
iterator pass over current bytes does not establish that an interrupted export
finished or bind those bytes to an unsealed original dispatch. Such inspections
retain the uncertain/failed/cancelled outcome and never enable automatic replay.
Explicit file removal retains the operation receipt.

Native qualification applies both exported formats through the independent
public C API to separate databases and compares exact 64-bit identifiers, large
Unicode text and binary values with the pinned SQLite CLI. Pending source work,
cross-target refusal and offline delivery are checked separately. Changeset
per-row conflict decisions, standalone
preupdate/carray support and broader installed-module coverage remain open.
These captures do not represent schema changes, virtual-table changes, a
database backup or proven recovery. Independent preupdate hooks cannot share a
connection with native sessions. Windows/macOS qualification remains with the
platform teams; ScratchBird/history testing remains deferred.

Reviewed native changeset application
--------------------------------------

The SQL editor can apply verified capture exports to another registered file
within the same owned endpoint. Source selectors enumerate registered files
and paged export receipts. Reviews bind exact source checksums, target file and
schema identity, execution host, native helper revision and apply options.
Writes use a separate owned connection and transaction. The retained user
query connection and its pending work remain independent.

Native v3 streaming apply supports changesets and patchsets, optional exact
table filtering, changeset inversion, IGNORENOOP, FKNOACTION, foreign-key and
recursive-trigger settings. Every native conflict kind has an explicit reviewed
ABORT/OMIT response; DATA and CONFLICT additionally support native REPLACE.
FOREIGN KEY OMIT retains changes including violations. Optional native rebase
output is retained separately. Selected changes skipped by native table
compatibility cause the owned transaction to roll back instead of receiving a
success receipt.

Apply return, commit admission, commit acknowledgement and output publication
have separate durable facts. Cancellation before commit rolls back the owned
work. A confirmed busy-commit rollback retains its own outcome. Lost commit
acknowledgements stay uncertain and cannot repeat the operation. Reconciliation
can verify/download sealed output independently while preserving that uncertain
database outcome. Existing query transactions are never committed by this
workflow. Native qualification includes exact typed rows, conflict kinds,
inversion, rowid patchsets, rebase output, schema-review refusal, cancellation,
busy commit, lost acknowledgements and authenticated cross-file delivery.

Per-row interactive conflict decisions,
standalone preupdate/carray workflows remain
separate work. Changeset apply is not a database recovery verification.

External native changeset and patchset files
-------------------------------------------

The apply editor also accepts external native files. Private intake receipts
bind the selected registration, owner, exact decimal length, client filename,
native helper and validation policy. The browser transfers bounded 256 KiB
chunks with SHA256 acknowledgements. Paused/retried uploads refresh durable
progress and revalidate the original file's acknowledged prefix before
appending. Missing, overlapping, changed or oversized chunks cannot advance
the recorded upload. An optional expected producer SHA256 binds the whole file.

Completed intake streams through hashing and SQLite's native iterator before
becoming an eligible apply source. Header format detection is followed by full
native parsing; it does not replace parsing. Empty native streams retain their
zero-record result. Validation has cancellation/deadline observation and uses an
independent in-memory helper connection. It never modifies a registered file.
Native return, seal and publication remain separate. Lost publication can be
reconciled against the seal; unsealed input remains diagnostic. Download and
explicit cleanup preserve the operation receipt and its owner/target scope.

Validated uploads appear alongside captured exports in native apply selectors.
Applying them requires the existing independent review and commit confirmation,
with source checksums, target schema identity, native conflict policies and
uncertain-outcome handling. Native qualification transfers independently
CLI-produced changesets and patchsets, checks repeated chunk acknowledgements,
downloads exact bytes, applies them and compares large text, Unicode, binary
values and wide integer keys through the pinned CLI. The browser exercises file
selection, bounded upload, native validation and reviewed application. Native
structure and checksums do not establish application-data completeness or a
database backup. Per-row decisions and standalone
preupdate/carray remain open; history testing remains deferred.

Native changeset transformation tools
-------------------------------------

The editor now creates new native artifacts through streaming inversion,
ordered concatenation, changegroup merging and local changeset rebasing.
Inputs can be captured exports, validated uploads or earlier transformed files.
Rebase buffers are selected from retained native apply output with a separate
commit acknowledgement. Input order, file checksums, execution host, helper
revision and native options belong to the review. Unsupported native format
combinations retain native errors rather than invented old values.

Schema-aware merging uses a separate read-only connection to the selected
registered file and its configured attachments. Review and execution compare
native schema identity, and an owned read transaction keeps the selected schema
consistent during transformation. Native changegroup schema handling fills
compatible trailing defaults and preserves primary-key positions. Transient or
uncommitted query-session schema remains separate work. Existing query
transactions are never committed or rolled back by these file tools.

Native return, stream parsing, seal and publication have separate receipts.
Cancellation/deadline observation, source-file postimages and output checksums
precede eligibility. Lost publication can be reconciled against a seal;
unsealed output remains diagnostic. Outputs can be downloaded, explicitly
removed while retaining receipts, selected as later transform inputs or sent
to the separate reviewed database-apply workflow.

Native qualification covers inversion, concatenation, schema-aware default
filling, patchsets, acknowledged conflict-resolution buffers and rebasing.
Zero-record streams may retain native table headers. Rebased bytes are compared
with the independent public rebaser API. Browser qualification transforms an
uploaded native file and applies the result, with independent database-row
verification. This scope does not close per-row conflict decisions, standalone
preupdate/carray or the broader product matrix. History tests remain deferred.


Connection-owned typed native arrays
-----------------------------------

The SQLite query workspace now creates, inspects and releases native CARRAY
parameters for int32, int64, double, TEXT and BLOB arrays. Queries use ordinary
``carray(:items)`` SQL with an opaque ``encoding: carray`` parameter envelope.
Bindings belong to the exact retained query connection and become invalid when
the array or connection closes. Array lifecycle actions refuse active query
workers and leave pending user transactions untouched.

The separately provisioned CARRAY bridge uses public ``sqlite3_carray_bind_v2``
and protected value APIs. It admits the exact connection library, SQLite source
identity and compiled CARRAY capability; it accesses no private CPython layouts.
The controlled extension loader closes before returning. Internal control tokens
and array payloads are omitted from query tracing. Native values and ownership
remain inside the application host. Windows/macOS provisioning builds the bridge
against the same native SQLite core; platform qualification remains with those
teams.

Element counts and measured native data bytes are decimal strings at the browser
boundary. Integer envelopes/decimal strings retain signed 64-bit values. TEXT
and BLOB arrays preserve NULL versus empty values; BLOBs support base64 input,
and invalid UTF-8 TEXT has an explicit byte envelope. Native CARRAY TEXT uses
terminated strings and cannot represent embedded zero bytes. Doubles retain
native floating-point behavior, including SQLite's NaN-to-NULL conversion.
``CDEADMIN_SQLITE_ARRAY_LIBRARY`` selects the operator-provisioned bridge;
``CDEADMIN_SQLITE_ARRAY_MAX_BYTES`` optionally limits aggregate native data on
one connection (zero/unset means no application limit). This measures array data,
not total process memory or SQLite object overhead.

Native qualification checks all five types, exact values, empty arrays, native
parameter slots, repeated names, quoted text/comments, ownership, explicit
release and pending-transaction preservation. Authenticated HTTP and browser
checks exercise the workspace-to-native binding path. This closes the scoped
typed array workflow; standalone preupdate, interactive changeset decisions and
broader installed-module/product coverage remain open. History tests remain
deferred by owner direction.

Standalone native preupdate diagnostics
--------------------------------------

The retained SQLite editor now starts, stops, inspects and clears standalone
native preupdate observations. Public callbacks record INSERT, UPDATE and DELETE,
old/new typed column values, native trigger depth and incremental BLOB-write
column metadata. Integer values remain decimal strings; TEXT includes embedded
zero bytes and invalid UTF-8 through explicit byte envelopes. BLOB NULL/empty
values remain distinct. Raw native rowid fields retain their documented limits:
WITHOUT ROWID tables, INSERT's old rowid and DELETE's new rowid are undefined.
These fields never authorize row mutations.

Callbacks occur before changes and can survive statement/transaction rollback.
They do not establish commit, and schema, virtual-table and system-table changes
have separate diagnostics. Per-run event/JSON retention limits and explicit loss
counters identify dropped observations. Limits count retained JSON data rather
than all native allocation overhead. Pages and reset/stop actions bind the exact
observation generation. Reset is confirmed; closing the connection stops the hook
and releases retained observations. Query-worker ownership guards all controls.

Native sessions and this independent hook use SQLite's single preupdate slot.
Cooperating bridges refuse replacement in both directions. Closing the last
session capture allows preupdate; stopping preupdate allows a session capture.
Older session helpers require a reconnect with the current bridge before hook
switching. Operator-approved third-party extensions remain responsible for their
own hook usage; these controls do not claim to chain arbitrary native callbacks.
The standalone bridge is selected by ``CDEADMIN_SQLITE_PREUPDATE_LIBRARY`` and
uses the exact connection library/source identity and closed controlled loader.
Platform provisioning includes its native build; platform teams still own their
Windows/macOS qualification.

Native checks cover typed callbacks, triggers, WITHOUT ROWID tables, blob writes,
rollback observations, limits/loss, paging, reset generations, loader/control
privacy and mutual exclusion. Authenticated HTTP and browser workflows exercise
start, observed changes, typed event inspection, stop and explicit reset.
This scoped workflow leaves interactive changeset decisions, remaining module
coverage and the broader product matrix open. History testing remains deferred.

Native capture comparisons and automatic table filters
-----------------------------------------------------

The capture panel now compares an exact table in an attached source database
against the capture database using native session diff. The operation adds
changes to capture memory and implicitly attaches the table; it leaves both
source/destination data and pending transactions intact. Native incompatibilities
remain errors. The database selector comes from the retained connection's
``PRAGMA database_list``; refresh inventory after changing attachments.

Automatic table filtering uses SQLite's native case-sensitive GLOB matching,
with include/exclude predicates scoped to one capture. The native filter API
enables automatic attachment of eligible future table names. Already attached
tables keep being tracked after filter changes; explicit attachments also remain
eligible. Clearing the predicate tracks all future eligible tables and does not
detach or discard anything. Recorded attachment names identify explicit attach
and successful diff requests; the public SQLite API does not enumerate its
internal automatic attachment list, and the response states this limitation.

Native checks inspect exported changeset selections to verify case/Unicode,
future tables, sticky attachments, explicit attachment, predicate changes,
exclusion and independent captures. Diff checks preserve both databases and a
pending transaction. Authenticated HTTP/browser workflows exercise filters and
attached-source comparison. These tools do not close interactive changeset
inspection/decisions, remaining module coverage or the broader product matrix.
History tests remain deferred.

Typed native changeset inspection and value extraction
------------------------------------------------------

Verified capture, upload and transform files can now be inspected before
application. The workspace shows native record operations, direct/indirect
flags, primary-key positions and typed old/new values. Values omitted by the
native format are explicitly undefined, distinct from SQL NULL and absent
old/new vectors. Native files contain positions and key masks rather than
original column names or declared SQL types; those facts are not invented.

The pinned public streaming iterator supplies bounded record pages and exact
cell byte ranges. Integer/record/offset identities remain decimal strings.
TEXT previews preserve bytes even when a range splits UTF-8 or contains invalid
UTF-8; decoded text is shown only for a valid prefix. Large TEXT/BLOB values can
be extracted completely into a separately checksummed downloadable file without
joining preview ranges. TEXT extraction uses the public API's UTF-8 value bytes.
Numeric/null/undefined values are not presented as raw binary files.

Inspection uses an independent in-memory helper connection and never changes a
registered database or interactive transaction. Owner/endpoint/target checks,
source-file seals and exact program identity bind each job. Source checksum
verification and native input/output work have cancellation/deadline checks.
Native return, file synchronization, sealing and publication remain separate.
Lost publication can reconcile a sealed output without repeating native work;
unsealed JSON/byte output remains diagnostic even when its current syntax or
length appears valid. Retained receipts and files support offline inspection,
verified downloads and confirmed cleanup. Inspection output is not an eligible
changeset/apply input.

UI requests preserve exact row/column/source identities, including when a
retained inspection belongs to a different source from the current apply
selection. Source changes discard stale asynchronous results. Native checks cover
changesets/patchsets, missing versus NULL values, signed int64 data, split UTF-8,
large byte ranges/full extraction, cancellation, sealed/unsealed recovery and
pending SQL preservation. Authenticated HTTP and browser checks inspect records
and download full native value bytes with independent comparisons.

This scope leaves interactive per-row conflict decisions, transient schema
bases, managed long-running session-diff progress/cancellation, remaining native
module transformations and the broader product matrix open. History testing is
still deferred; platform teams own Windows/macOS qualification.

Live native per-conflict decisions
---------------------------------

Reviewed apply can now pause in SQLite's native conflict callback for an
owner-authorized response. DATA, NOTFOUND, CONFLICT, CONSTRAINT and aggregate
FOREIGN KEY conflicts retain their different native semantics. Replacement is
available only for DATA and CONFLICT. The workspace shows effective incoming
values (including the reviewed inversion flag), available current target values,
key masks, exact integer values and native undefined/NULL distinctions. Apply
change sequence is explicitly separate from a source-file record ordinal.

Complete incoming/current TEXT and BLOB values are copied while the protected
callback values remain valid. The browser can download those exact byte ranges
with individual checksums. No native iterator or protected value escapes its
callback. A random callback challenge binds each durable response; a stale or
different admitted response is refused. Responses may apply to the current
conflict or, explicitly, later conflicts of the same kind. Native consumption is
acknowledged separately from response admission and database commit.

The apply transaction remains owned by its independent connection while waiting.
Its locks persist until response, cancellation or the reviewed timeout. Closing
the viewer does not cancel the job. Cancellation aborts native staging and rolls
back the owned transaction; pending interactive user sessions remain separate.
The operation is not previewed and replayed on the target to obtain conflicts.
FOREIGN KEY OMIT retains the native possibility of committing violations.

The owner-process channel bridges durable responses from HTTP workers to private
native pipes. Observer/stream failures prevent commit. Event/value output is
sealed separately, retained for owner-scoped inspection and removable with the
operation's output. Native return/response acknowledgements never replace the
existing commit-admission, commit-return and unknown-outcome rules. An uncertain
operation is never replayed automatically.

Native checks cover all conflict kinds, permitted/refused choices, scoped
responses, cancellation while waiting, remembered choices, complete byte values,
durable job admission and separate commit observation. Authenticated HTTP and
browser qualification downloads current native bytes, resolves a live conflict
and independently checks committed rows. Remaining transient schema bases,
managed session-diff progress/cancellation, installed-module workflows and broader
product coverage stay open. History tests remain deferred; platform evidence
remains with the Windows/macOS teams.

Retained schema bases for native changegroups
-------------------------------------------

Native changegroup merging can select its schema basis from the current query
session. Main, temporary and attached schemas include in-memory and uncommitted
objects. SQLite reads the original connection's schema and native default values;
ScratchRobin does not recreate DDL on another connection. Registered read-only
file schema bases remain available independently.

The review binds the exact query session, native connection generation,
attachments, schema contents/version and transaction-open state. These are
checked again at admission and under an exclusive connection reservation before
dispatch. Another target, closed connection, active execution or changed schema
is refused. Native file cancellation uses a private cancellation pipe and never
interrupts, commits or rolls back the borrowed query connection. Pending data and
savepoints remain owned by the user. Cancellation and completion release the
connection reservation; sealed artifacts remain usable after the session closes.

Native checks merge changesets with fewer columns using actual temporary,
uncommitted-main and attached-memory schema defaults, then independently apply
the output and compare values. Authenticated HTTP checks cover target/schema
refusal, preserved savepoints and offline artifact verification; browser controls
select a retained basis, merge, download and independently apply its output.
Separate transient DDN coverage, managed long-running diff controls and remaining
installed-module/product workflows stay open. History testing is deferred and
platform qualification remains with the Windows/macOS teams.

Managed native table differences
--------------------------------

Retained query sessions can compare a selected table against an attached source
through a reviewed, durable job. A disposable native session capture produces a
changeset or patchset; existing user captures stay separate. The operation uses
the original connection's main/temp/attached schema, current SQL visibility and
native defaults. Pending data, transactions and savepoints remain owned by the
user. A comparison does not settle SQL or establish a backup/recovered database.

The worker reserves the connection and rechecks both schemas, attachment and
connection identities. Native VM progress callbacks support cancellation and a
reviewed deadline; their count is not rows or a percentage. A pre-existing
progress-handler owner is refused and preserved. Native diff can leave partial
capture memory on error: this workflow closes its private capture and never
adds that partial state to an existing user capture. Unconfirmed capture cleanup
blocks further connection use until the user closes it.

Comparison return, export return, capture closure, output verification and
publication have separate durable facts. Retained files support typed inspection,
transforms, reviewed independent apply, downloads, verification after connection
closure and confirmed removal. Unsealed output is diagnostic and an uncertain
job is never automatically repeated. The original immediate diff-into-capture
control retains its separate native semantics.

Native checks cover changesets/patchsets, main/temp/attached schemas, exact
independent application, cancellation during comparison, preserved capture bytes,
SQL/savepoint ownership, stale source schema and cleanup failures. Authenticated
HTTP/browser qualification exercises comparison/export/download, native typed
inspection and independently verified apply. Transient DDN, installed-module and
other product gaps remain open. History tests stay deferred and platform teams
retain Windows/macOS qualification.
