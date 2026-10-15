MariaDB engine functional completion
====================================

The native qualification target is MariaDB 12.2.2 with the patched MariaDB
Connector/Python 1.1.14 described in ``mariadb_driver_development.rst``. MySQL
qualification is not MariaDB qualification. This contract supplements that
native driver contract, ``ddn_database_roundtrip.rst`` and shared navigation,
compact form, SQL editor and dashboard contracts. Existing driver receipts
establish their recorded scope only; completion requires current implementation
and native/browser acceptance of each requirement.

Acceptance requirements
-----------------------

MARIA-COMP-01: Native navigation and administration
  Discover server and database objects and their native children. Database and
  schema identify the same native namespace. Cover tables, views, sequences,
  columns, constraints, indexes, partitions, triggers, procedures, functions,
  packages and package bodies, events, accounts, roles, grants, storage engines,
  plugins, server links, server loadable functions, replication, system variables,
  sessions and logs.
  Preserve system-versioned tables, application-time periods, partitioning,
  generated columns, exact native types/options and SQL-mode-dependent syntax.
  Gate features against observed server version, installed engines, SQL mode,
  privilege and edition. Do not expose MySQL components, JavaScript libraries,
  MySQL Shell or MySQL materialized views as MariaDB features. Discovery failure
  or denied metadata must not appear as an empty successful catalog.
  An observed disabled binary log with native error 1381 is explicitly
  unavailable, rather than a failed visibility probe. Permission denial,
  contradictory enabled state and other failures remain incomplete coverage.

  Remote server definitions expose native CREATE/ALTER/DROP SERVER with explicit
  wrapper and selected HOST/DATABASE/USER/PASSWORD/PORT/SOCKET/OWNER options.
  Discovery never reads remote passwords or arbitrary confidential Options.
  Alteration changes only explicitly selected options; omitted options remain
  unchanged. Passwords are never returned in previews or saved metadata.
  Registration does not contact or qualify the remote server or storage engine.

  Server loadable functions are distinct from stored routines and built-in
  FUNCTION plugins. Discover mysql.func registrations and expose native scalar
  or aggregate CREATE FUNCTION ... SONAME and DROP FUNCTION. Keep native
  STRING/REAL/INTEGER/DECIMAL return types. Native library availability,
  privileges and dependencies decide execution. Use an owned attachment with
  no default database for global UDF lifecycle; a concurrent removal must never
  turn DROP FUNCTION into removal of a same-name database routine. Native DDL
  has independent commits; do not retry or promise user rollback.

  Native partition administration provides table partitioning/add/coalesce/remove
  and selected-partition analyze/check/optimize/repair/rebuild/truncate/drop,
  exchange, reorganize and conversion to a standalone table. Conversion from
  an existing table requires explicit native partition definition text. Bind
  every action to its exact owning database/table/partition and require review
  and confirmation. Preserve native RANGE/LIST/HASH/KEY, subpartition and
  SYSTEM_TIME grammar. The native server decides storage-engine, foreign-key,
  current/history-partition and row-placement eligibility; do not disable
  constraints or promise transactional rollback of partition DDL. Exchange and
  conversion expose native WITH/WITHOUT VALIDATION explicitly.

  Package discovery retains declaration and body observations separately on the
  package node, including both native SHOW CREATE results. A same-name body must
  never overwrite declaration metadata. In addition to combined create/replace,
  expose independent declaration creation/replacement and body creation,
  replacement and removal. Removing a body preserves its declaration; replacing
  a declaration can invalidate its body and dependent callers. Existing-object
  forms offer stored, current or Oracle SQL mode; stored mode requires observed
  native context and must not be guessed. DDL remains independently committed,
  with no retry or claim that a multi-statement operation is atomic.

MARIA-COMP-02: Connections and native ownership
  Explorer, active connection selection and SQL sessions agree on exact engine,
  endpoint and database. Provide explicit connect/disconnect, independently
  owned database sessions, native authentication and TLS, cancellation and pool
  generation retirement. Do not reconnect or replay established native work.
  Socket loss is not proof of commit or rollback. Preserve uncertain outcomes
  and require explicit reconciliation before issuing replacement work.

MARIA-COMP-03: Shared SQL editor and scripts
  Use the shared compact SQL editor with engine-labelled connections, native
  language/SQL-mode validation and completion, exact parameter binding, script
  boundaries, file tooling, bounded result pages and diagnostics. Expose native
  EXPLAIN and ANALYZE options and honestly scoped preparation/dispatch/fetch
  timing. Observe native autocommit and pending transaction state before policy
  changes; disable commit/rollback when native autocommit is on. Do not infer
  transactional rollback for implicit DDL commits or nontransactional tables.

  Native SQL diagnostics expose bounded MariaDB server message text alongside
  native error number and SQLSTATE to the owning SQL session. Connector/transport
  failures expose their classified code/type without route or credential text.

  SQL history is optional and persistent, isolated by owner, endpoint,
  registered database target, engine and ``mariadb-sql`` language. Capture is
  disabled by default, bounded by record count/retention and omits bound values,
  results, explicit sensitive source, credential URIs and native authentication
  clauses including IDENTIFIED VIA, WITH and BY. Loading history only changes
  editor text. Store failure never blocks or retries native execution. History
  request observations never assert native transaction finality.

MARIA-COMP-04: Data, lifecycle and native maintenance
  Qualify native row editing, commit/rollback, bounded navigation, exact values,
  large objects, import/export and test data. Qualify database lifecycle,
  maintenance and separately installed MariaDB backup/restore executables with
  review, exact target checks, rediscovery and independent verification. Native
  MariaDB dump/restore behavior must not be substituted by MySQL Shell behavior.

MARIA-COMP-05: Native DDN roundtrip
  Capture selected objects, databases, server metadata and selected data using
  independent connections. Preserve exact identifiers, definitions, SQL modes,
  character sets, native type details, temporal clauses, sequence/package
  identities, dependencies, security and incomplete/denied observations. Use the
  sister project's renderer/designer. Generate native metadata and explicit
  reviewed diff/apply plans with target/digest/baseline validation, bounded
  receipts and rediscovery. View filtering and incomplete discovery are never
  deletion intent. Do not claim catalog reads are an atomic DDL snapshot or
  translate MySQL-only grammar into a MariaDB deployment.

  Graphical relational edits retain native field UIDs and exact table clauses.
  Translate explicit datatype/nullability/comment edits, admitted new columns,
  column renames and foreign-key intents into a catalog review before execution.
  Native MariaDB UUID/INET4/INET6 types remain available. Preserve generated
  expressions, periods, indexes, comments and literals during column renames.
  Graphical omissions never remove columns or constraints. System-versioned
  graphical schema changes require explicit native KEEP-history acceptance.
  Retain the original native baseline when loading a saved design or preparing
  a graphical handoff; a fresh capture does not silently replace that baseline.

  Three-way table previews bind the baseline, desired and live catalog to the
  endpoint, registered database and native server_uid. Compile named CHECK removal
  using MariaDB DROP CONSTRAINT. Preserve generated-column and temporal clauses;
  omitted columns and application periods require exact mariadb_change.drop_columns
  and drop_periods intent. Omitted objects are selections, never deletion intent.
  Native PREPARE validation uses an independent UTF-8 connector connection and
  exact-lossless native conversion into the original statement character set.
  PREPARE never EXECUTEs during validation. Reviewed receipts are owner/target
  bound, expire before dispatch and persist uncertainty before native execution.
  Apply requires explicit change and exclusive-DDL-maintenance-window confirmation,
  rechecks native UID and exact live definition/absence, and rediscovers afterward.
  Lost acknowledgements remain unknown; batch receipts preserve each statement's
  independently committed prefix and never automatically replay it.
  Native MariaDB rejects many system-versioned schema changes under its default
  history-alter policy. Require explicit mariadb_change.temporal_history=KEEP
  before admitting such an alteration; set system_versioning_alter_history only
  on the dedicated lease. KEEP accepts MariaDB's native historical-row/schema
  interpretation and is not a promise to retain each older schema definition.
  System-time history removal and period-boundary replacement require separately
  reviewed native lifecycle operations. A lexical preview grants no execution.

  Catalog capture uses a dedicated idle native connection and records
  ``server_uid``, SQL mode and character context. Preserve exact SHOW CREATE
  text for databases, tables, views, sequences, routines, triggers, events,
  packages and package bodies. Retain native column, constraint, partition,
  parameter, PERIODS and KEY_PERIOD_USAGE facts. A privilege denial is an
  explicit coverage gap; unsupported MySQL catalogs are never queried. Captures
  are bounded observational documents, not atomic snapshots or permission to
  execute imported definitions. Sequence inspection must not advance values.

  Explicit relation data capture supports user tables and views, including
  current visible rows of system-versioned tables. The selected canonical
  relation identity and captured server_uid must both match before the native
  data read. It never advances a sequence
  or implicitly reads historical FOR SYSTEM_TIME versions. Own a separate
  read-only REPEATABLE READ transaction, refresh and finish it within the
  capture, and retain exact patched-connector temporal, numeric and binary
  values. Sample/full modes have explicit row, byte, column and elapsed-time
  budgets. A full capture exceeding a budget returns no partial download.
  InnoDB table snapshots are distinguished from observational views and
  nontransactional engines. All paths retire the owned attachment, without
  altering interactive work or retrying interrupted reads.

  Capture must neutralize SHOW CREATE presentation flags that suppress table,
  field or key options. On its disposable connection, remove NO_TABLE_OPTIONS,
  NO_FIELD_OPTIONS, NO_KEY_OPTIONS and compatibility macros that restore them,
  retaining the other expanded native SQL-mode flags. Record the original mode
  in observed identity and the actual retrieval/creation context with every
  native definition. Stored routine/package/event contexts take precedence over
  retrieval context. Oracle-mode connections must not silently omit native
  ENGINE, character set, row format, field comments or index options.

  Test-data recipes bind to the owner-authorized MariaDB endpoint/database
  and current native table/column identities. Reuse the compact recipe controls
  with a distinct MariaDB format and downloadable persistent recipe files. Generate bounded,
  deterministic native scripts only: no implicit transaction control, writes,
  constraint disabling or sequence advancement during generation. MariaDB JSON
  values use validated textual JSON (not unsupported CAST AS JSON); vectors use
  VEC_FromText, not MySQL STRING_TO_VECTOR. Preserve exact decimal/integer/binary
  values, generated columns, native AUTO_INCREMENT returned values and reviewed
  parent dependencies. Native execution and transaction outcomes belong to the
  shared Query Tool. Apply existing row, byte, generator and scope limits.

  Saved catalog and relational designs use the shared project-asset repository
  under a MariaDB-specific namespace. Scope includes owner, endpoint, registered
  database and design family. Preserve original native baseline, authored DDN,
  historical revisions and optimistic version checks. Saving or editing a DDN
  design does not execute native DDL. Use the sister DDN designer for relation
  layout and manual design; stale captures require an explicit reviewed merge.

  Reviewed object changes retain complete native definitions, stored creation
  context and event time zone. Views and events use native ALTER; replacing a
  routine, package declaration/body or trigger requires exact explicit replacement
  intent. Package declaration replacement can invalidate/discard its body and
  callers; no transaction rollback is promised. An existing package body must
  first be removed through a separate reviewed operation before replacing its
  declaration, then recreated against the new declaration. Replacements use
  mariadb_change action=replace and exact name confirmation; database/sequence
  settings use action=alter-options. Sequence restart additionally confirms its
  native name. Preserve trigger ownership and
  native sibling order. CREATE resolves the desired action_order against the
  live group; replacement preserves its recorded owner/timing/event/order.
  Record and recheck the complete visible sibling group before native dispatch.
  An unresolved ordering dependency blocks admission.
  Sequence option changes are explicit and separate from confirmed restart.
  SHOW CREATE SEQUENCE describes configuration, not the currently cached next value.
  Capture and export must not claim it is an exact continuation-state backup.

  Native SQL generation is export-only and preserves SHOW CREATE definitions,
  per-object SQL mode, character context and event time zone. It must preserve
  system-versioned/application-period tables, sequences and separate package
  declarations/bodies. Foreign keys are deferred until tables exist; package
  bodies follow declarations and multiple triggers preserve native action order.
  MariaDB has no VIEW_TABLE_USAGE catalog: FROM/JOIN and table-list references outside
  literals/comments are conservative ordering hints, with external/unresolved
  dependencies explicitly reported rather than presented as exact discovery.
  Missing context/definitions or ambiguous identities block a deployable export.
  Filtered object exports retain the observed database identity/context in
  provenance. Imported DDL remains unvalidated and never authorizes execution.

  Mixed-character-set definitions are encoded by MariaDB itself, with exact
  Unicode roundtrip checks, on a dedicated UTF-8 Connector/Python connection.
  Do not change character_set_client away from utf8mb4 on that connector.
  Validate native character-set names before constructing CONVERT. Validate
  collation names with the native session setter, then restore the owned
  connection context; UCA-1400 aliases can be absent from catalog inventories.
  Downloads target a fresh mariadb --binary-mode client session, including
  per-object time zone; conversion loss or wrong server UID prevents download.

  Server inventory reads explicitly named credential-free columns from native
  SCHEMATA, mysql.user, roles_mapping, USER_PRIVILEGES, PLUGINS, CHARACTER_SETS,
  COLLATIONS, ENGINES, INNODB_SYS_TABLESPACES, mysql.func and mysql.servers. Distinguish roles
  using native is_role. Plugin identity includes native name and plugin type;
  MariaDB uuid DATA TYPE and FUNCTION plugins are separate entries. Preserve
  the native name for commands. Do not read authentication_string, Password, global_priv
  JSON or arbitrary server-link Options. Omitted confidential link options are
  disclosed as a coverage limit. Native max_statement_time and lock_wait_timeout
  bound probes. Database expansion requires explicit owned registered targets;
  independently captured scopes must report the same native server_uid.

MARIA-COMP-06: Dashboards and dedicated monitoring
  Provide engine/server/database display-only DDN dashboards with separately
  authorized dashboard editing. Use dedicated collector connections, selectable
  registration credentials or dedicated monitoring username/password/role,
  optional heartbeat and sampling/retention/lease policies. Refresh transaction
  scope every sample and continue collection without a viewer. Distinguish
  unavailable, denied and zero measurements. Retain bounded volatile samples.

  Reopening an active policy shows the admitted sampling, retention, lease,
  heartbeat and dedicated-account/role settings, rather than editor defaults.
  Return only safe policy fields and account identity; never return a password.
  Active settings remain disabled until collection is stopped. MariaDB roles
  have no MySQL role-host suffix. Successful native reverification with the same
  runtime family/version/evidence does not revoke collection merely because its
  observation timestamp changed. Persisted route, target, credentials, generation,
  runtime identity or verification-state changes still invalidate admission.

  Native probes use MariaDB's ``server_uid`` identity, information_schema
  GLOBAL_STATUS, PROCESSLIST and SLAVE_STATUS, plus explicitly named native
  settings and selected-database TABLES storage estimates. Do not depend on
  MySQL's server_uuid, super_read_only, replication_connection_status or enabled
  performance_schema. Server-wide counters remain server scoped on database
  dashboards. Exact counter deltas require the same collector epoch and native
  server UID and valid uptime/reset observations; missing/reset counters are
  gaps. A sample completes only after verifying autocommit with no retained
  native transaction. Lost authorization or a failed probe cannot heartbeat.

MARIA-COMP-07: Contextual compact forms
  Route native tree items to engine-appropriate information/forms with stable
  form references. Share controls where appropriate without hiding supported
  MariaDB functionality or showing unsupported options. Use compact selectors,
  checkboxes, icon actions and navigable grids. Mutations require explicit
  review and exact selected-target authorization.

MARIA-COMP-08: Qualification and cleanup
  Qualify current source against native MariaDB, including independent
  sessions/databases, restricted privileges, cancellation/disconnection, native
  object lifecycle, backup/restore, DDN conversion/diff/apply and monitoring
  credentials. Refresh DDN before each build/commit qualification and run
  immutable captured inputs. Preserve evidence outside the source tree and
  remove owned disposable fixtures. MySQL receipts, static inventories, unit
  tests and old activation gates alone do not establish full MariaDB support.

Current-run exclusions
----------------------

Persistent monitoring history and its ScratchBird backend remain deferred.
Windows/macOS work and platform QA belong to the separate platform teams.
Persistent SQL history, dashboard definitions, recipes and native DDN conversion
are in scope. MariaDB completion does not authorize starting DuckDB.

Application-period boundary renames compile an explicit DROP PERIOD and ADD PERIOD
in the same native ALTER as the column rename, preserving its final period and
constraint. MariaDB does not automatically rename the period reference. System-time
boundary renames require separate temporal lifecycle review.

MariaDB administration reuses the compact native field grid and password
confirmation controls, without enabling Firebird privilege queues or Firebird
operations. Native package and partition forms have stable reusable reference
numbers SR-F-001412 and SR-F-001413. Remote server and loadable-function
forms use SR-F-001414 and SR-F-001415. Numeric partition counts use bounded integer
controls, and fragment editors span the grid with bounded vertical scrolling.

The exact dialect task inventory must track every executable provider operation.
Package/partition additions require native parser and live execution evidence
before admission. Keep the provider task-ID set and dialect coverage identical;
an inventory mismatch must continue to block generated DDL rather than bypass
the engine gate.
