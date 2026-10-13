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
  ordered result sets. Report preparation, dispatch and fetch measurements only
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
  Native test-data recipes are scoped to one registered file and fresh catalog
  capture, bounded to 32 tables, 5000 rows, a 4 MiB recipe and 1 MiB generated
  SQL. Generation validates 1.5.2 native statement boundaries and performs no
  writes. The shared Query Tool owns execution, transaction outcome and effects.

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
  explicit DROP intent and view replacement are currently previewed through the
  1.5.2 native parser. Other native edits are blockers. Missing desired rows are
  ignored rather than treated as deletion. The preview is nonexecuting and does
  not grant an apply right; full native adapters and reviewed application remain
  required before this requirement is complete.

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
