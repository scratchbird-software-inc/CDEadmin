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
  renames are also admitted. Generation for attached environments, external-
  content column rewriting and additional installed module/function/collation adapters
  remains open.

  Virtual-table catalog families and module identities are resolved with the
  native compiler/authorizer, including quoted module names. DDN creation checks
  actual installed module availability and native ownership rather than a fixed
  list of module spellings. Native creation/query acceptance includes FTS3/4/5,
  RTree, Geopoly, fts3tokenize, dbstat, fts4aux and fts5vocab. An external-content
  owner rename selects the exact FTS4/FTS5 indexes to reconstruct in the same
  transaction. Native settings survive the reconstruction and native integrity
  checks verify the rebuilt index against its content rows. FTS5 content-row
  identity changes have a corresponding constructor adapter. Public FTS content
  column and FTS4 row/language mappings retain separate acceptance. Native ALTER
  alone can leave an external-content search table unusable.

  Native FTS configuration controls generate normalized desired DDN through
  SQLite's public setting commands in an empty private module. Configuration-
  only application preserves the table definition and content, rechecks the
  original settings, verifies native results before commit and retains a durable
  once-only receipt. Existing keys are preserved; resetting a setting requires
  an explicit native value. Direct deletion of private config rows is not a
  reset workflow. FTS3/4 automerge and the installed FTS5 configuration commands
  retain their own native admission and normalization rules.

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
