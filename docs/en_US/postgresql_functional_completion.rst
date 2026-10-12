PostgreSQL functional completion
*******************************

Scope and layout direction
==========================

Owner direction, 2026-10-11: apply the Firebird completion standard to PostgreSQL,
preserving the complete native administration surface. Compare existing forms
before replacing them: PostgreSQL's tabbed property forms, privilege collections,
constraint editors, SQL preview and version-aware fields may provide better
layouts than the Firebird forms. Preserve those strengths and reuse them for
other engines where appropriate. Shared controls do not imply shared grammar,
transaction semantics, object hierarchies or capabilities.

The existing PostgreSQL driver qualification is recorded in
``postgresql_driver_development.rst``. This checklist is additional required
work, not a claim that the full feature set has been qualified. Persistent
monitoring history, a ScratchBird history backend and Windows/macOS qualification
remain deferred or assigned to the platform teams.

Acceptance obligations
======================

* PG-COMP-01: Preserve the native server/database/schema/object hierarchy and all
  existing PostgreSQL forms, including partitions, materialized views, extensions,
  foreign data wrappers, publications/subscriptions, event triggers, policies,
  roles, tablespaces, languages, types and full-text objects. Hide unavailable
  operations by server version and permissions; distinguish system objects.
* PG-COMP-02: Explorer authentication, SQL selection and disconnect agree. A
  selected database is bound by its server-scoped native OID. Do not use the
  maintenance database as a fallback when an explicit database is invalid,
  disconnected, dropped or inaccessible. Database selection does not mutate the
  server registration or other editors. Preserve independently owned sessions,
  drafts, cancellation, aborted transactions and uncertain outcomes.
* PG-COMP-03: Shared SQL editor with PostgreSQL syntax, native parameter binding,
  completion, script/file tools, history, result navigation, buffer row limit,
  autocommit checkbox and explicit commit/rollback. Preserve the existing Query
  Tool's richer native facilities until equivalent shared paths are qualified.
  Report timings with measurement scope; distinguish estimated EXPLAIN from
  executed EXPLAIN ANALYZE. Never execute statements just to obtain a plan without
  explicit authorization. Do not manufacture a plan from another execution.
* PG-COMP-04: Native object/database/server metadata search, dependency-aware
  metadata/data export, COPY/import, selected-row SQL, binary/large values and
  test-data recipes. Use PostgreSQL quoting/types and explicit transaction
  outcomes. Native pg_dump/pg_restore backups remain distinct from DDN export.
* PG-COMP-05: DDN discovery/display/design, native generation, semantic diff,
  review/apply and rediscovery at object/database/server scope, following
  ``ddn_database_roundtrip.rst``. Retain unsupported native details and report
  incompleteness rather than silently flattening them into a generic SQL model.
* PG-COMP-06: Display-only engine/server/database DDN dashboards using independent
  collector connections, configurable credentials/role, bounded samples, policy
  heartbeat and regularly completed read transactions. Preserve native metric
  scope and resets. Availability does not imply replication freshness. Dashboard
  editing belongs in the separate DDN editor. A pgAdmin polling chart alone does
  not qualify this collection/authorization contract.
* PG-COMP-07: Compact forms, stable form references, keyboard navigation,
  accessible labels, efficient checkbox/select choices and paged editable grids.
  Preserve good native layouts. Compare corresponding Firebird forms and record
  reusable improvements rather than mechanically replacing PostgreSQL forms.
* PG-COMP-08: Qualify with a real supported PostgreSQL instance, independent
  transaction observers, at least two databases and two SQL sessions, native
  permission failures, disconnect/reconnect, cancellation and connection loss.
  Test native forms as well as provider adapters. Record exact DDN provenance.

Database-bound shared workspace contract
=======================================

The shared PostgreSQL workspace identifies a selected database using
``postgresql-database:<oid>`` within the registered server endpoint. The backend
accepts only canonical positive PostgreSQL OIDs and resolves names through the
server's catalog. An explicit target requires an already connected Explorer
attachment. Server scope retains the explicitly configured initial database;
unknown targets never collapse to that scope. Target-specific cache/session
namespaces prevent cross-database result or metadata reuse. Registration forms
remain the existing native PostgreSQL forms; shared read-only descriptors do not
permit generic provider registration mutations.

While any shared PostgreSQL SQL session on the endpoint remains open, native
server/database disconnect and configuration replacement are refused. The user
must explicitly resolve work and close the query session first. This conservative
endpoint guard also protects sessions on other databases of that server; it does
not infer that cancellation, socket loss or attempted commit resolved a transaction.

Independent monitoring source contract
======================================

The PostgreSQL source uses an independently opened psycopg attachment named
``ScratchRobin monitoring``. It never accepts an existing user connection. Each
sample executes a bounded, read-only transaction and ends it before publishing a
successful refresh. Optional metric groups use savepoints so a permission failure
does not poison other groups. Native SQLSTATE identifies unavailable groups; SQL
text, credentials and connection exception messages are not placed in samples.
Failure to end a transaction makes that sample unavailable. Failed connection
release remains owned and must be retried before reconnecting.

Initial native metric groups are database cumulative counters, activity excluding
the collector, lock waits, table maintenance estimates, replication state,
cluster I/O and relevant settings. Server scope reads per-database counters and
cluster groups; database scope limits activity, locks and relation statistics to
the selected database. Server statistics and database-local relation statistics
are labelled separately. Query text is not collected. Restricted statistics
visibility is explicit; null/redacted values are not converted to zeros.
Settings describe the collector connection and use the configured metadata
sampling interval, retaining their actual observation timestamp. Cached settings
are discarded on release/reconnect; a failed refresh is reported as unavailable.

Counter rates require consecutive samples from the same database, postmaster
start and statistics-reset epoch. Reconnect, failure, reset, decreasing counters
or missing counters break the rate baseline. Exact integral/decimal measurements
are serialized as strings, retaining SQL NULL. Table estimates are not row
counts; PostgreSQL buffer hits are not operating-system cache hits. All samples
are process-local, bounded by the monitoring runtime's lease and retention policy.
Collector availability and a fresh completed transaction do not imply replication
freshness. PostgreSQL metrics must use PostgreSQL dashboard bindings; Firebird
``MON$`` bindings are not reused.

Native semantics reference:
https://www.postgresql.org/docs/18/monitoring-stats.html

Monitoring delegation and presentation
======================================

The host selects the monitoring engine; a browser cannot supply a source factory.
Sealed credential grants bind that engine along with the owner, target, route,
generation, account and policy. PostgreSQL requires an explicit connection
database even for server-wide statistics. A database-scoped grant also binds the
native database OID and checks it on each completed refresh, so recreating a
database under the same name cannot silently resume the old collector.

DDN publications use fixed native metric bindings. Names and observations are
quoted data, never executable DDN identifiers or SQL. Only the latest fresh,
successfully completed, matching-scope sample can populate current measurements.
Stopped, failed, stale and incomplete observations do not retain earlier values
as current. Missing values remain unavailable; numeric zero and boolean false
remain valid observations. Counter rate values require an available baseline.
Each bounded group reports scope, visibility and truncation. Table tuple counts
are estimates; replication positions and intervals retain their native meaning.
No aggregate silently sums server-wide metrics across database collectors.

The source and DDN adapter are independently qualified components. Their presence
does not complete PG-COMP-06: host routes, credential configuration, policy UI,
engine inventory, publication editing and live browser qualification must also
be integrated and verified.

Host admission uses the authenticated owner's already connected native PostgreSQL
18.3 attachment only to resolve its database and capture encrypted credentials;
sampling never borrows that attachment. Both server and database context menus
provide separate monitoring settings and display-only DDN viewer destinations.
Current credentials and a dedicated username/password/optional role are supported.
The worker rechecks persisted ownership, active account, endpoint generation and
registration configuration before and after sampling. Registration changes revoke
access to old samples and require stop/reconfigure; browser disconnection alone
does not stop a separately admitted policy. The native database OID is rechecked
by the dedicated collector. Settings accept only PostgreSQL policy fields.

This initial admission path requires a direct password connection. SSH tunnels,
libpq service registrations and Kerberos authentication are explicitly refused,
not silently converted to another transport. TLS/GSS options are preserved under
the collector's allowlist; unknown options are refused. Connection timeout must
be 1–30 seconds. Those unsupported admission paths remain qualification work,
not a claim of complete native transport parity. The application shares one
process-ownership lock across Firebird and PostgreSQL and releases it only after
both runtimes confirm attachment cleanup.

The PostgreSQL engine dashboard lists only the current owner's native PostgreSQL
registrations. Server registration inventory is distinct from configured volatile
database collectors and from the native database catalog. Viewing inventory never
starts a collector. Each server and database observation is reauthorized; revoked,
failed, stale or missing sources remain explicitly unavailable. Fleet output is
bounded to the latest sample per collector, with no credentials or SQL text.
Metrics from different scopes are not summed. Navigation selects a registered
server or an admitted database target; it does not change or start a policy.
