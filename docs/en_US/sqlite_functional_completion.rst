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
  ``DROP TABLE``, ``DROP VIEW``, ``DROP INDEX`` and ``DROP TRIGGER`` operations
  are reviewed separately from additions. A missing DDN row never implies
  deletion. It compiles each statement under native ``EXPLAIN`` without
  executing it and checks SQLite authorizer facts for the exact object and
  owning table, then records a durable owner/file-bound review, claims that review
  before dispatch, applies the batch in one SQLite transaction and rediscovers
  the committed definitions or absence. An ordinary table with no views may
  be rebuilt to add or remove non-key columns while preserving native row IDs,
  retained column values, unchanged explicit and implicit indexes, owning triggers and
  unchanged inbound/outbound foreign keys; the desired DDN must carry matching
  table and column facts.
  The rebuild runs
  in one SQLite write transaction, checks row count and foreign keys before
  commit, restores the live ``AUTOINCREMENT`` high-water mark when applicable,
  and verifies the rewritten native definition afterward. The rebuild can
  retain non-key column data across a changed name when the user supplies
  an exact old-to-new mapping; an ambiguous same-type removal and addition
  without that mapping is refused. Rebuilds with unresolved dependencies,
  changed keys, type changes, and
  standalone column deletion remain blocked. Native ``fts3``, ``fts4``,
  ``fts5``, ``rtree``, ``rtree_i32``, ``geopoly`` and ``fts5vocab`` virtual
  tables admit exact reviewed creation and explicit ``DROP TABLE`` when the
  installed runtime provides their modules; other modules and rewrites need
  separate qualification. The rebuild follows SQLite's documented
  `generalized ALTER TABLE procedure <https://www.sqlite.org/lang_altertable.html#otheralter>`_
  within its admitted dependency scope. This bounded operation set is the
  current-run native DDN application contract. A blocked transformation can
  be authored as reviewed native SQL in the shared editor under its own
  transaction controls; a DDN preview never guesses a data conversion or
  treats a missing object as deletion intent.

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

Current-run exclusions
----------------------

Persistent monitoring history and its ScratchBird backend remain deferred.
Windows/macOS development and platform UX qualification belong to their teams.
Persistent SQL history, DDN design/dashboard definitions and recipes remain in
scope.
