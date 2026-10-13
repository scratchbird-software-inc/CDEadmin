DuckDB engine functional completion
==================================

The native target is DuckDB 1.5.2 and PyArrow 25.0.1. This contract supplements
``duckdb_driver_development.rst``, the shared SQL editor, compact forms, navigation
and DDN roundtrip contracts. Native driver qualification alone does not establish
completion of management workflows.

DUCK-COMP-01: Native catalog and administration
  Preserve database/catalog, schema and object identity, including attached
  catalogs, temporary objects, columns, constraints, indexes, sequences, native
  types, scalar/table macros, functions, extensions and secret descriptors.
  The registered primary file's schemas are direct children of its database
  tree node. Attached-catalog schemas retain their attached-database parent.
  Navigator ownership must make actual schema descendants reachable, including
  indexes, sequences, types and views; a catalog capture without tree routes
  does not qualify object management.
  Resource IDs encode native path segments unambiguously; punctuation in names
  is not an identity delimiter. Distinct native constraint indexes remain
  distinct even when their reported names coincide. IDs are opaque; refresh
  discovery after activation rather than reusing a cached older identity format.
  Do not silently overwrite same-name native function overloads. A function or
  macro group retains every observed overload, its native function type,
  parameter names/types, return type, definition, examples and stability.
  A group exposes common fields only when all overloads agree; selecting one
  group must never silently select an arbitrary overload as its definition.
  Attachments are session-owned native objects, not remote authenticated servers.
  Do not offer unsupported server accounts, roles, triggers, procedures,
  replication, savepoints, or MySQL-style administrative executables.
  Never expose secret values, encryption keys or confidential attachment options.
  Database options use an explicit safe metadata allowlist; foreign attachment
  connection strings are omitted. Disclose omitted metadata without returning it.

DUCK-COMP-02: Embedded connection and transaction ownership
  Bind explorer connections, editor sessions and target selectors to the exact
  registered file/root and native catalog. Retain original DuckDB connections;
  cursor() creates another session and cannot substitute for their transaction.
  Respect read-only routes, native file locking, attachment lifetimes and native
  multi-database write restrictions. Preserve unknown outcomes and never replay
  native work. A COMMIT of an aborted transaction is reported as native rollback.
  Autocommit controls must reflect actual admitted DuckDB session policy, not
  imitate another driver's behavior. Refresh transactions when policy permits;
  pending interactive work must never be committed by monitoring or discovery.

DUCK-COMP-03: Shared SQL editor and native language
  Use the shared compact editor with engine-labelled connections, native parse
  validation, contextual completion, parameters, retained script execution,
  files, persistent optional owner/target/language-scoped history, result paging,
  cancellation, transaction controls, diagnostics and physical/profiling plans.
  Preserve native Arrow exact and nested values, duplicate column identities and
  ordered result sets. The SQL result grid must display each returned value in
  its corresponding ordinal column, including rows encoded as arrays by the
  native driver; a nonempty buffered result must not render blank cells.
  Result admission binds positional driver values to unique native column keys,
  not display names, so repeated output names remain distinct.
  Report preparation, dispatch and fetch measurements only
  for the scope actually measured. EXPLAIN ANALYZE executes native work.
  Source checking on a retained DuckDB session uses the pinned 1.5.2 native
  parse-only API. It returns native statement boundaries and grammar status
  without executing SQL. Parse errors are scrubbed because native diagnostics
  may echo source literals. This check does not establish semantic validity,
  permissions or side-effect safety; those remain execution-time concerns.
  Query metrics report native parsing time, client dispatch/reader setup time,
  and local fetch/encode time with a buffered-row count. The displayed total
  execution interval starts at dispatch and ends after native iteration and
  local buffering; it can include consumer backpressure. No plan is inferred
  from an ordinary execution. An explicit EXPLAIN result is shown as result
  data, and EXPLAIN ANALYZE may perform the work being profiled.
  A normal Run request admits exactly one user-authored SQL statement,
  including explicit EXPLAIN requests. Empty requests or a second SQL
  statement after a native-tokenized semicolon fail before dispatch and have
  no SQL effects. Native IMPORT DATABASE may expand that one command into
  several internal statements; this is not a second user-authored command.
  Multi-statement work
  uses the retained script coordinator: it reviews native boundaries, sends
  one statement at a time on the same session, observes each terminal result,
  stops on error or unknown outcome, and never automatically replays a
  submitted statement. An error plus blocked session is an unknown outcome.
  Editor preparation of a selection, current statement or remaining source
  from the cursor uses those same native parser boundaries without execution.
  A prepared multi-statement result enters retained script review; it is not
  passed to the ordinary single-statement Run path.
  Visible native catalog resources supply qualified catalog/schema/relation and
  column completions in the shared editor. Identifier insertion quotes and
  escapes exact native names. This page-scoped completion never claims a
  truncated or inaccessible catalog is empty or complete.

DUCK-COMP-04: Data and file workflows
  Implement native row editing with qualified identity, paging, commit/rollback,
  exact values, import/export and reusable test-data recipes. Provide reviewed
  native COPY, EXPORT/IMPORT DATABASE, attachment, checkpoint and maintenance
  workflows. Do not claim EXPORT is a physical backup, or that SQL rollback
  removes files written externally. Validate registered filesystem ownership
  without claiming that authorized arbitrary SQL/extensions are sandboxed.
  The database administration form requires an absolute directory under the
  registered filesystem root for native EXPORT/IMPORT DATABASE. EXPORT offers
  PARQUET or CSV and requires a new or empty destination. IMPORT requires an
  existing export with schema.sql and load.sql and targets the active file;
  it does not replace that file. Refuse export control-file symlinks that
  escape the reviewed import directory. Checkpoint, force checkpoint, vacuum
  and analyze expose only their native supported options.
  Native test-data recipes are scoped to one registered file and fresh catalog
  capture, bounded to 32 tables, 5000 rows, a 4 MiB recipe and 1 MiB generated
  SQL. Generation validates 1.5.2 native statement boundaries and performs no
  writes. The shared Query Tool owns execution, transaction outcome and effects.
  Native table COPY planning is similarly nonexecuting. It captures the exact
  registered-file table identity, requires a contained regular source file for
  import or an absent destination under the registered root for export, quotes
  the full catalog/schema/table and path, and emits one parsed native CSV or
  PARQUET statement. Import is a database write; export creates an external
  file that SQL rollback cannot promise to remove. Execution remains in the
  shared Query Tool with its explicit transaction controls.
  ATTACH/DETACH planning is session-scoped and nonexecuting. An ATTACH script
  accepts only an existing DuckDB file under the registered root, an explicit
  alias and read-only choice; a read-only primary route cannot attach a
  writable file. DETACH targets an explicit nonprimary alias. The script must
  run on the chosen retained connection, since an independent connection
  cannot observe or change another session's attachments. Never advertise
  these aliases as separately authenticated remote servers.

DUCK-COMP-05: DDN catalog, data and design exchange
  Capture native catalog and selected data into DDN views using the sister
  project's public tools. Preserve catalog-qualified names, native types,
  defaults, expressions, constraints, indexes, sequences, macros and dependency
  evidence. Retain exact native DDL where available; explicitly report metadata
  which DuckDB cannot reconstruct. Read DDN for native creation and three-way
  baseline/desired/live diff, with explicit deletion intent, native nonexecuting
  validation and reviewed apply receipts. A view filter never authorizes drops.
  Distinguish temporary/session definitions from persisted file contents.
  Catalog capture uses its own connection and transaction, bounded to 20,000
  native/expanded facts, 8 MiB and 30 seconds. Overflow or interruption returns
  no partial successful capture. A known missing registered file is refused
  before connection creation. Independent capture of :memory: is refused.
  Selected relation data uses a separate registered-file connection and native
  read transaction, exact catalog/schema/table-or-view identity, 1–6,000 rows,
  a 4 MiB value budget and 30-second deadline. A full request exceeding its
  row budget fails; a sample records truncation. Attached session-only catalogs
  are not independently captured. Values use the driver's exact Arrow encoding,
  and no capture borrows or commits an interactive transaction.
  Separate native sequence observations from resumable sequence state; discovery
  must not call nextval. Preserve native file effects and uncertain apply state.
  Versioned DDN design drafts use the shared project asset repository, scoped to
  the owner, exact endpoint and registered file target. Keep the capture used as
  the design baseline with each revision, permit source merge through the paired
  public DDN workflow, and treat an edited design as documentary until native
  plan review and application are separately qualified.
  Three-way design preview compares a saved baseline and edited DDN with a
  fresh native capture. Only explicit, exactly qualified DuckDB CREATE objects,
  exact-name index CREATE on a qualified table, nullable native column ADD,
  explicit DROP intent, view replacement, isolated column alterations, native
  enum extension, single-overload scalar macro replacement and exact-identity
  table/view/column rename, explicit primary-key addition and isolated native
  object comments are previewed
  through the 1.5.2 native parser. A column addition requires an observed persistent
  parent table and a native type; unsupported column constraints block review.
  One-field column default or nullability alterations require explicit change
  intent and an otherwise unchanged baseline definition. An explicit column
  type alteration may change only native type-derived metadata, with an
  optional separately reviewed ``USING`` expression; it does not infer a
  conversion or alter constraints. After commit, rediscovery must verify the
  requested native type, even when its canonical spelling differs and review
  is consequently marked unverified. Combined edits remain blockers. Each
  alteration is one parsed native statement and one review.
  An enum extension requires an observed native ENUM, preserves every existing
  label in order and appends distinct new labels. It uses one reviewed native
  ``CREATE OR REPLACE TYPE``. DuckDB does not retarget columns that already
  reference the prior type definition; any such column conversion requires a
  separate reviewed column alteration. A macro replacement requires exactly
  one observed scalar overload, unchanged parameters and metadata, and an
  explicit new bounded definition. Table macros, overload groups and parameter
  edits remain blockers. Both operations verify their native postconditions
  after commit; an uncertain or mismatched observation is never replayed.
  A rename requires the baseline source resource ID, unchanged native
  definition, unchanged parent, an absent target identity and an explicit old
  name confirmation. The plan binds both source and destination IDs, dispatches
  one native ``ALTER`` and verifies that the source disappeared and the
  destination appeared. Child resource identities generated from a renamed
  parent path must be refreshed in the design before further native changes.
  Table, view, column, sequence, type, macro and index comments may be set or
  cleared through one parsed ``COMMENT ON`` statement when the only edited
  native field is the comment. DuckDB 1.5.2 cannot comment on schemas; those
  edits remain blocked. The resulting comment is verified by fresh discovery.
  A primary key may be added to an existing table only by explicit intent
  naming one or more distinct observed columns when the baseline has no
  primary key. No other table edit is bundled with this operation. DuckDB
  checks existing data and nullability during native execution; a failure
  rolls back the reviewed transaction. Fresh discovery must observe the key
  and the exact ordered key columns. Dropping or changing a primary key is
  unavailable through DuckDB 1.5.2 ``ALTER TABLE`` and remains blocked.
  An index's native identity includes its table, but DuckDB CREATE INDEX names
  the index without catalog qualification; DROP INDEX qualifies the index by
  catalog and schema. The reviewed target must match both forms exactly.
  Other native edits are blockers. Missing desired rows are
  ignored rather than treated as deletion. A bounded plan of up to 32 native
  statements may be reviewed together when their identities and dependencies
  are unambiguous. Create schemas before their tables and tables before their
  indexes; apply added columns before indexes on those columns. Drop children
  before their parents. A new table's columns belong in its one CREATE TABLE
  statement, and cannot also be added as separate operations. Rename remains
  a single-operation review until descendant identities are recaptured.
  Reject conflicting create/drop actions under one parent, unresolved targets
  and an aggregate source above 1 MiB. The durable owner/file-bound receipt
  binds the exact ordered statement list and affected baseline/desired rows.
  Application opens its own connection, begins one DuckDB transaction,
  verifies the registered file identity and rechecks the live baseline in that
  transaction, dispatches each native statement once in dependency order,
  commits once and rediscovers every target. A failed/uncertain commit is never
  replayed automatically. The limited admitted operation set does not complete
  the full native DDN adapter obligation.

DUCK-COMP-06: Native dashboards and monitoring
  Provide display-only DDN engine/embedded-instance/database dashboards with a
  separately authorized editor and published definitions. Use independently
  owned monitoring connections compatible with the native file's connection
  configuration. Observe loaded/installed extensions, attached file statistics,
  native memory/storage/configuration and availability without inventing remote
  server load, network authentication or global user-session metrics. Temporary
  objects and session settings on another connection are not globally visible.
  Configure sampling, bounded volatile retention, leases and optional heartbeat.
  A failed refresh cannot heartbeat. An independent :memory: connection is a
  different database; do not present it as monitoring the interactive instance.
  The collector is admitted only for a registered, existing file in its
  filesystem root. It has an independently owned connection and a scoped grant;
  neither a database password nor a current-user credential selector is used.
  The host requires single-process admission and a process lock. Each completed
  probe opens a native read transaction and rolls it back; failure retires that
  collector connection and cannot count as a heartbeat. The server dashboard
  aggregates registered file collectors, not a remote process. The engine
  dashboard lists owner-registered file targets and never deduplicates physical
  aliases. All metric bindings are validated against DuckDB-specific public DDN
  module and scope identifiers, with live values rebound after publication.
  Published definitions contain no sampled values. Trends expose only bounded
  volatile samples for the current process. Engine, server and database viewers
  remain display-only; dashboard editing is a separately authorized destination.

DUCK-COMP-07: Contextual compact forms
  Give native tree entries meaningful engine-specific destinations and stable
  reusable form references. Use compact selectors, checkboxes, icon actions and
  navigable data grids. Preserve supported native functionality without adding
  features from other engines. Require review and exact target authorization
  for mutations; display native capability or configuration limits explicitly.

DUCK-COMP-08: Qualification and cleanup
  Qualify native driver, catalog, structured administration, SQL, data, file,
  DDN and monitoring behavior with independent observations where applicable.
  Refresh DDN and qualify immutable captured inputs. Preserve failure inventory
  and evidence outside the repository. Clean up only owned disposable fixtures.
  Static forms and driver receipts alone do not prove full engine completion.

Current-run exclusions
----------------------

Persistent monitoring history and its ScratchBird backend remain deferred.
Windows/macOS development and platform UX qualification belong to their teams.
Persistent SQL history, design/dashboard definitions and recipes remain in scope.
