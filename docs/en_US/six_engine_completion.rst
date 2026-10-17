Six-engine product completion
*****************************

Owner acceptance requirements, 2026-10-16
=========================================

MySQL, MariaDB, PostgreSQL, DuckDB, SQLite and Firebird must each provide their
full native administration surface inside ScratchRobin. Firebird includes
network and embedded operation. Each engine must be catalog complete, feature
complete, provide predictive SQL completion and syntax checking, and support
management and maintenance without requiring a separate administration tool.
Shared infrastructure must preserve each engine's capabilities, native types,
language, identity, permissions and transaction behavior.

This contract adds product-wide acceptance to the existing engine checklists.
It does not certify that those requirements are currently met. A completed
driver gate, declared-task inventory, object editor or Linux workflow qualifies
its recorded scope only. An engine with an open requirement below is not product
complete. Human form validation remains assigned to the human team; backend
admission, authorization and native-operation validation remain required.
Windows/macOS qualification remains assigned to the platform teams and is
required for a cross-platform completion claim.

Owner correction, 2026-10-16: ScratchBird is under heavy development. Keep its
client-driver and archive integration wired, but do not run history tests until
the owner resumes qualification. History acceptance is deferred; it must not
hold up implementation of the other matrix items.

Version and installation identity
---------------------------------

The current application profiles target MySQL 9.7.0, MariaDB 12.2.2,
PostgreSQL 18.3, DuckDB 1.5.2, SQLite 3.53.0 and Firebird 5.0.4. These are the
profile versions under review, not a statement about the latest vendor release.
Record edition/build, interface, installed extensions/plugins/storage engines,
compile options, database configuration and session language modes separately.
Qualification of one installation does not cover another edition, extension,
compatibility mode or native interface automatically.

A native feature is not ``not applicable`` merely because its adapter is
missing. An unavailable privilege, uninstalled component or unsupported version
must be identified separately from an absent implementation. Features that the
engine does not have, such as SQLite server accounts or DuckDB stored procedures,
must not be fabricated. Installed optional capabilities require their own
catalog, operation and language coverage; a generic SQL/API passthrough does
not establish that coverage.

Workflow ownership
------------------

The user must be able to inspect, configure, review, run, observe and recover
each supported management operation in ScratchRobin. Handing the user a command
for another application, launching an external SQL client, or requiring hand-
written SQL does not close an explicitly required management workflow.

Native vendor utilities and libraries may be implementation dependencies. Their
versions, availability, execution host, credentials, progress, cancellation,
output and outcomes must be handled by the application. This interpretation
does not promise a reimplementation of vendor backup engines, or silently
exclude a workflow that needs one. Server-host filesystem/service operations
need an explicit authorized execution-host integration; the web server must not
be assumed to be the database host. Desktop and packaged environments need the
corresponding native binaries and libraries on each supported operating system.

Acceptance areas
================

PRODUCT-CAT-01: Catalog completeness
------------------------------------

Maintain an engine/version inventory independent of the provider's own resource
declarations. Reconcile raw native observations against discoverable objects,
properties, exact native definitions, child facts and navigator destinations.
Include database/server/session/attached-file scopes where they exist, system
and user objects, identities containing punctuation, overloads, dependencies,
comments, privileges, ownership and installed capability metadata. Redact secrets
without suppressing the existence or identity of the owning object.

Reconcile both privileged and restricted observations. Denied, unavailable,
truncated and session-local coverage must be explicit; none means an empty
catalog. Every object must be reachable and expose its native applicable
operations. A database DDN capture alone cannot close server catalog coverage.
Catalog observation, DDN preservation and native mutation are separate evidence.

PRODUCT-FEAT-01: Native feature coverage
----------------------------------------

Expand the inventory from native product documentation and the selected release
sources, rather than accepting the current task list as the complete denominator.
Every applicable feature needs a discoverable workflow, native operation adapter,
permission/version admission, progress/result handling and native acceptance.
An inspection-only object does not imply administration of that object.

The inventory must cover these areas for each engine:

.. list-table:: Required management areas
   :header-rows: 1
   :widths: 25 75

   * - Area
     - Required native scope
   * - Connections and lifecycle
     - Registration, native authentication/TLS, connection modes, database/file
       create/drop/clone/attach, server-host lifecycle, configuration and upgrades.
   * - Schema and code
     - All native relation, column, key, constraint, index, type, sequence,
       routine, package, trigger, event, view and other applicable object families;
       native options, dependencies, comments and ownership.
   * - Security
     - Users, roles, memberships, grants, default privileges, mappings, native
       authentication/encryption configuration and applicable row/security policy.
   * - Data
     - Browse/edit, stable row identities, exact types and LOBs, bulk import/export,
       native file formats, reusable recipes, search, scripts and cancellation.
   * - Design and migration
     - Metadata/data/server DDN capture, native generation, three-way diff,
       reviewed apply, explicit destructive intent and verified postconditions.
   * - Continuity
     - Logical and applicable physical/incremental backup, verification, restore,
       recovery targets, recovery drills and applicable log/archive management.
   * - Replication and availability
     - Native replication objects/topology, configuration, health, bootstrap,
       promotion/failover and repair where the selected product supports them.
   * - Maintenance and storage
     - Native consistency checks, optimization/statistics, index maintenance,
       partition/storage/tablespace administration, capacity and cleanup.
   * - Diagnostics
     - Native plans/profiling, sessions, locks, transactions, logs, slow operations,
       cancellation and engine-specific diagnostic facilities.
   * - Monitoring and durable assets
     - Independent collectors, display-only dashboards, persistent ScratchBird
       history, historical trends/gaps, SQL history, dashboard/design definitions
       and owner/target-scoped reusable recipe revisions.
   * - Extensions and automation
     - Installed extension/plugin/component/module administration, native jobs and
       events where applicable, schedules and operation receipts.

Engine-specific cases remain first-class: MySQL replication channels, components,
resource groups and Shell administration; MariaDB sequences, packages, temporal
tables, native replication/storage engines and Oracle compatibility mode;
PostgreSQL extensions, procedural languages, policies, FDWs, publications and
subscriptions; DuckDB attachments, macros, nested types, extensions, secrets and
native file formats; SQLite virtual tables, loaded modules/functions/collations,
PRAGMAs, compile options, online backup and file recovery; Firebird PSQL,
packages, generators, Services API, trace/profiling, events, authentication
mappings, backup chains and separate embedded limitations.

PRODUCT-EDIT-01: Predictive SQL completion
------------------------------------------

Completion must use the exact selected engine/version/mode and the authorized
catalog for the selected endpoint/database/session. Include keywords, functions
and overloads, operators, types, routines, relation/column names and native code
templates. Resolve qualification, aliases, CTEs, quoted identifiers and applicable
procedural scopes. Preserve exact insertion quoting and case. Refresh on catalog,
role, extension, connection, language and syntax-setting changes. Do not merge
same-named objects from different catalogs or treat a partial page as complete.

Qualify automatic suggestions during typing and explicit completion, incomplete
source, Unicode, native parameter forms and stale/asynchronous reply handling.
Keyword highlighting or a relation-name list alone does not close this item.

PRODUCT-EDIT-02: Syntax checking and script tools
-------------------------------------------------

Provide engine-native grammar checking for SQL and applicable procedural bodies,
with positioned diagnostics, incomplete-edit handling and clear distinction
between syntax, catalog binding, authorization and execution errors. Record the
parser revision and its relationship to the connected server. Use native parse-
only or independently qualified grammar paths; executing SQL and rolling it back
is not validation. Unsupported grammar remains unknown, never a false success.

Session settings and modes are part of the language identity, including MySQL
and MariaDB ``sql_mode``, MariaDB Oracle mode, PostgreSQL string settings,
SQLite compile/extension settings, DuckDB extensions and Firebird database/
attachment/statement dialect. Validate SQL, stored-program/package bodies and
client script boundaries separately. Formatting must preserve the selected
native language, comments, quoting, literals, parameters and body boundaries.
An unrelated engine's formatter cannot be used as a fallback.

Apply :doc:`native_dialect_tooling` to validation, framing, formatting and source
execution. Client directives, includes and streamed input need their own admitted
adapters. A refusal is honest behavior but leaves an applicable required workflow
open. Full native execution support does not close missing preflight checking.

PRODUCT-OPS-01: Complete workflows and native evidence
------------------------------------------------------

Qualify the complete user workflow on owned native fixtures: discover/review,
dispatch, progress, terminal result, independently observed effects and cleanup.
Exercise privilege denial, native refusal, cancellation, connection loss,
partial effects, unresolved outcomes and restart reconciliation where applicable.
Preserve native transaction ownership; never replay an uncertain mutation.
Verify backup/restore and recovery by restoring and checking actual data, and
replication/failover by observing independent native members.

Retain exact application source/artifact hashes, refreshed paired DDN provenance,
native engine/tool/interface identities and scope-specific receipts. Linux,
Windows, Intel Mac and Apple Silicon Mac evidence are separate. A top-level
``complete`` field or declared-task count cannot replace those observations.
Separate implementation, native qualification, platform qualification and human
form signoff in reports. Do not publish an overall completion percentage until
the complete native feature denominator has been reconciled.

Source audit baseline, 2026-10-16
=================================

The following findings describe source revision
``c312b5b473aa41d5054935f331df5c72af8603c4``. This is a source audit with references
to existing scoped receipts, not a new native qualification run. All six engines
have implemented administration, data and DDN work; none yet has evidence closing
all four product requirements above.

.. list-table:: Current evidence and open product coverage
   :header-rows: 1
   :widths: 14 28 28 30

   * - Engine
     - Catalog evidence
     - Editor implementation
     - Broader completion
   * - MySQL
     - Independent 30-category reconciliation and native DDN child facts;
       105/105 declared administration tasks have scoped native receipts.
     - Shared keyword display; catalog-backed completion is not wired. Source
       checking uses lexical analysis, not full MySQL grammar.
     - Open. Existing backup/restore and replication work does not qualify PITR
       or all native operational families. History native acceptance is blocked.
   * - MariaDB
     - Independent 30-category reconciliation and native DDN child facts;
       88/88 declared administration tasks have scoped native receipts.
     - Shared MySQL editor dialect; catalog-backed completion is not wired.
       Source checking is lexical; Oracle/package grammar is not fully checked.
     - Open. PITR/physical recovery and full native operational coverage need
       dedicated workflows/evidence. History native acceptance is blocked.
   * - PostgreSQL
     - Broad native database/child and separate server capture, plus inherited
       native forms. Complete independent catalog reconciliation is still needed.
     - Native catalog completion; pglast 8.5/PostgreSQL 18.6 SQL parser against
       server 18.3. Quoted procedural bodies are not checked.
     - Open. History integration, typed DDN data import, durable application
       recipe revisions and physical/PITR/upgrade workflows need completion.
   * - DuckDB
     - Native catalog/overload capture and navigator work. Complete independent
       installed-capability reconciliation is still needed.
     - Pinned native SQL parser; page-scoped relation/column completion. Full
       function/macro/type/context completion is not established.
     - Open. History integration, durable application recipe revisions and
       remaining native DDN transformations/import workflows need completion.
   * - SQLite
     - Native sqlite_schema and table/index/FK PRAGMA capture. Functions,
       collations and compile-option coverage need expansion/reconciliation.
     - SQLite keyword dialect; catalog-backed completion is not wired. Native
       EXPLAIN compilation leaves context/binding failures unconfirmed.
     - Open. History integration, durable application recipe revisions and
       remaining native DDN rebuild/import workflows need completion.
   * - Firebird
     - Independent supported-category reconciliation and navigator qualification
       for network/embedded. This does not certify all operations or platforms.
     - Native keyword/metadata suggestions and Firebird formatting. Shared source
       checking is lexical; full DSQL/PSQL preflight checking is missing.
     - Open. Existing FlameRobin parity receipts retain their scope. Native
       ScratchBird history acceptance and full platform/release acceptance remain.

Concrete open work
------------------

These are confirmed gaps or unclosed acceptance obligations, not an exhaustive
native feature denominator. Further inventory may add work.

* PRODUCT-GAP-01, MySQL/MariaDB/SQLite: implement catalog-backed predictive
  completion. ``LanguageSourceEditor.jsx`` binds the native completion callback
  only for PostgreSQL; the generic provider has no completion contribution.
  Firebird and DuckDB use separate bounded metadata configurations.
* PRODUCT-GAP-02, MySQL/MariaDB/Firebird: implement nonexecuting native/versioned
  grammar validation for SQL and procedural bodies. These providers have no
  ``validate_source_without_execution`` override; ``DataStudioService`` falls
  back to lexical ``language_tools.analyze`` with unknown grammar status.
* PRODUCT-GAP-03, PostgreSQL: qualify procedural-body checking, string-mode
  coverage and parser/server revision compatibility. ``providers/postgresql/language.py`` explicitly excludes quoted procedural bodies and admits only
  ``standard_conforming_strings=on``. Installed languages need distinct coverage.
* PRODUCT-GAP-04, DuckDB/SQLite and all editors: complete contextual symbols,
  overloads, aliases/CTEs and mode-aware invalidation; qualify incremental
  diagnostics and native error ranges. SQLite context/binding failures require
  an honest checking result rather than inference from an EXPLAIN error.
* PRODUCT-GAP-05, MySQL/MariaDB/DuckDB/SQLite: remove the PostgreSQL formatter
  fallback and supply native qualified formatting. ``ReactCodeMirror/index.jsx``
  hard-codes ``language: 'postgresql'``; the shared source editor supplies a
  formatting override only for Firebird.
* PRODUCT-GAP-06, PostgreSQL/DuckDB/SQLite: implement archive writers, engine
  identity/redaction/rollups, owner/target-authorized history routes and historic
  views. ``MonitoringHost`` currently enables history only for Firebird, MySQL
  and MariaDB. A shared archive class alone does not wire another collector.
* PRODUCT-GAP-07, all six: obtain a successful native ScratchBird history
  roundtrip and restart/retention/isolation evidence. The retained October 16
  native startup attempt failed before archive SQL with
  ``SECURITY.CONTEXT.EXPIRED`` / ``CATALOG_MUTATE``. This is an engine-team
  dependency, not permission to substitute another history database.
* PRODUCT-GAP-08, PostgreSQL/DuckDB/SQLite: add persistent owner/endpoint/database
  recipe revisions and optimistic concurrency. Current recipe UIs read/write
  downloadable JSON files; ``MySQLRecipeAssets`` admits only MySQL/MariaDB.
  File persistence is useful but does not provide the application revision store.
* PRODUCT-GAP-09, PostgreSQL/DuckDB/SQLite: close native DDN roundtrip operations
  individually, including typed data import and currently blocked applicable
  schema transformations. PostgreSQL's plan builder refuses additional changed
  native fields without generation adapters; SQLite rebuilds reject key/type
  changes; DuckDB documents bounded dependency/rebuild transformations. Do not
  replace required workflows with instructions to write SQL manually.
* PRODUCT-GAP-10, PostgreSQL/DuckDB/SQLite: add complete independent catalog/
  native child-fact and navigator reconciliation gates, including native symbols,
  temporary/attached-session coverage and installed capability differences.
  Preserve the existing MySQL/MariaDB/Firebird gates and extend their inventories
  when the native feature reconciliation identifies missing scope.
* PRODUCT-GAP-11, MySQL/MariaDB/PostgreSQL: implement and qualify dedicated PITR
  and applicable physical/incremental recovery workflows. Native dump/restore
  receipts do not close log replay or recovery-target handling. The operational
  workspace's generic PITR facet is a projection, not a recovery executor.
* PRODUCT-GAP-12, all six: reconcile full lifecycle/upgrade, replication/HA,
  security/configuration, extension and maintenance families against native
  product documentation. For example, staged MariaDB binlog tools and MySQL
  Shell backup calls do not establish complete recovery or cluster management.
* PRODUCT-GAP-13, all six: collect current-source native and browser workflow
  receipts for the expanded inventory, including supported operating systems and
  both Firebird modes. Preserve already-running platform qualification. A native
  development environment receipt alone does not close feature/platform parity.

Completion order
----------------

First reconcile the independent native feature/catalog denominator and repair
editor completion/validation/formatting boundaries. Then close monitoring and
durable asset gaps, DDN operations and engine-specific operational workflows.
Qualify each affected native scope as it is completed and aggregate platform
evidence only after the corresponding implementation is qualified. The blocked
ScratchBird archive acceptance can proceed when its native runtime serves; other
engine work need not wait for that dependency.

Implementation progress
=======================

The following additions supersede the corresponding source gaps in the audit
baseline. They do not certify full native product completion; the broader
transformation, recovery, operations and platform requirements remain open.

* Retained-session metadata completion is wired for MySQL, MariaDB, DuckDB,
  SQLite and Firebird, alongside PostgreSQL's native completion adapter.
  Suggestions include native functions/types and exact quoted relation/column
  paths. PostgreSQL refreshes its adapter for each request so dropped objects
  and earlier search paths are not retained indefinitely. Bounded or denied
  observations are explicitly partial. CTE projections and aliases have editor
  support. Native completion reparses the current source using newly observed
  modes before resolving scopes, decodes doubled identifier delimiters, preserves
  distinct quoted aliases and uses native MySQL/MariaDB table-name case settings.
  Firebird dialect 1 suggestions preserve its unquoted identifier rules. Complete
  procedural-scope coverage still requires qualification.
  SQLite source compilation preserves the existing authorizer and suppresses
  PRAGMA settings/VFS preparation effects through native ``SQLITE_IGNORE``.
  PRAGMA syntax is checked; its options are not executed or semantically applied.
* MySQL and MariaDB source checks use native ``PREPARE`` without ``EXECUTE``.
  Metadata lock waiting is bounded and the original session setting restored.
  Firebird checks use native DSQL/PSQL preparation in the selected statement
  dialect, including native-script framing. Idle checks own a separate read
  transaction; checks during interactive work preserve its transaction.
  Catalog/privilege failures leave grammar unconfirmed. Firebird execution
  continues through its dedicated client-setting-aware script workflow.
* PostgreSQL checks quoted SQL and PL/pgSQL bodies and observed string settings.
  A reproducible pglast 8.5 patch exposes native parse options and separate
  routine-body settings. Its exact library revision restores files omitted
  from the upstream source archive after verifying every overlapping file.
  Native bootstrap and Docker builds install this parser. PostgreSQL 18.6
  parser identity and the 18.3 server profile remain separate recorded facts;
  other installed procedural languages are explicitly unconfirmed.
* The shared editor selects the MySQL, MariaDB, PostgreSQL, DuckDB or SQLite
  formatter explicitly, with token preservation and native validation before
  replacing source. Firebird retains its native formatter. Incremental native
  diagnostics are opt-in through **Check while typing**; stale replies are
  discarded and Unicode character offsets translated for the editor.
* SQLite discovery now includes connection-local native function overloads,
  collations, compile options and supported PRAGMA names. Listing PRAGMA names
  does not execute those PRAGMAs. PostgreSQL catalog paths follow exact native
  ownership, including schema and table-owned objects; TOAST relations and
  large-object ownership/ACL metadata are discoverable. Large-object contents
  have native create, bounded read/write, truncate, owner/comment, privilege and
  drop workflows. Binary file chunks load into the review; downloads verify the
  returned length and checksum. Large-object operations own their transaction,
  preserving interactive sessions. Continuous whole-file transfers remain a
  separate workflow obligation.
* Independent raw catalog/child-fact/navigator reconciliation is available in
  ``tools/cdeadmin_native_catalog_gate.py`` for PostgreSQL, DuckDB and SQLite.
  PostgreSQL database/system catalogs, SQLite attachments/temporary objects and
  loaded capabilities, and DuckDB attachments/temporary objects and complete
  function overload groups have distinct observations. PostgreSQL server capture
  includes database properties, roles/authentication state, memberships,
  tablespaces, settings/configuration files, HBA/identity mappings, available
  extension versions and live replication/session/TLS/GSSAPI state. Secret
  values are redacted without hiding the owning object. Server-only inspection
  and DDN download do not require database expansion. Independent shared-catalog
  reconciliation checks privileged and restricted observations. Explicit
  retained-session inspection captures PostgreSQL temporary relations, types,
  constraints and native child facts, plus pending catalog changes. It preserves
  healthy user transactions and local settings; an aborted transaction is refused
  without implicit rollback. Session observations have separate DDN provenance
  and cannot enter an independent database migration. Broader live topology
  qualification remains separate.
* PostgreSQL, DuckDB and SQLite have durable owner/endpoint/database-scoped
  recipe revisions with optimistic concurrency. Reading a revision loads the
  editor; saving a revision does not execute the recipe.
* Typed data DDN import is wired for PostgreSQL, DuckDB and SQLite through
  separate preview, durable review and explicit one-time apply actions.
  Fresh native layouts guard dispatch. SQLite archives retain storage classes;
  DuckDB archives include an Arrow IPC representation, checked against displayed
  values by the installed native engine. PostgreSQL uses exact text-protocol
  values and native casts. Constraints and triggers remain active, generated
  columns are recomputed, and a lost commit reply is never replayed. Native
  qualification is recorded independently from implementation. Static data
  capture remains bounded to 6,000 rows and an 8 MiB workspace; review storage
  has a separate 4 MiB limit. A full capture exceeding a limit is refused.
* Explicit SQLite rebuilds support native type/affinity changes, generated
  columns, primary/unique/foreign-key constraints, STRICT and WITHOUT ROWID
  transitions and AUTOINCREMENT changes. The desired CREATE definition and
  complete column facts are reviewed. Row copying enforces the native desired
  constraints; generated values are recomputed. Retained views/triggers and
  foreign keys are checked before COMMIT. Dependency changes after review
  refuse dispatch. Failed preservation checks roll back the owned transaction.
  Exact independently declared index/trigger definitions remain preserved;
  changing those definitions and multi-table rebuild batches remain separate.
* PostgreSQL, DuckDB and SQLite collector archive writers, scoped history routes,
  identity/redaction/rollup mappings and historical viewers are wired to the
  shared ScratchBird client boundary. **No history qualification is claimed**;
  PRODUCT-GAP-07 is owner-deferred.
* Native utility execution supplies OS-specific process settings, isolates
  configuration and credentials, preserves virtual-environment launchers and
  records the application execution host separately from the database endpoint.
  Output capture is bounded while both streams drain; long-running tools expose
  numeric progress and explicit cancellation/timeout observations. Failed
  supervision retains its local process observation. Local exit and cleanup do
  not assert remote database finality. These facilities support continuity
  adapters; they do not close the outstanding recovery workspaces and drills.

PRODUCT-GAP-09 still includes remaining native schema transformations beyond the
typed imports. PRODUCT-GAP-11 still requires dedicated physical/incremental/PITR
workflows and recovery drills. PRODUCT-GAP-12 still requires the full native
feature denominator and outstanding lifecycle/upgrade, availability, security,
extension and maintenance adapters. PRODUCT-GAP-13 requires current-source
browser/native/platform evidence for that expanded scope. Existing passing
component receipts must not be promoted to those broader completion claims.

References
==========

The detailed owning engine requirements remain:

* :doc:`mysql_functional_completion`
* :doc:`mariadb_functional_completion`
* :doc:`postgresql_functional_completion`
* :doc:`duckdb_functional_completion`
* :doc:`sqlite_functional_completion`
* :doc:`firebird_functional_completion`
* :doc:`native_dialect_tooling`
* :doc:`ddn_database_roundtrip`

Native recovery requirements extend beyond SQL dumps. See the
`MySQL 9.7 backup and recovery manual
<https://dev.mysql.com/doc/refman/9.7/en/backup-and-recovery.html>`_,
`MariaDB backup and restore documentation
<https://mariadb.com/docs/server/server-usage/backup-and-restore>`_ and
`PostgreSQL 18 backup and restore manual
<https://www.postgresql.org/docs/18/backup.html>`_. Selected local release-source
packets provide catalog/grammar/tool inventories; their acquisition status is
separate from ScratchRobin native product qualification.

PostgreSQL physical continuity increment (2026-10-16)
==================================================

The server menu and Operations workspace now expose reviewed native physical
full/incremental backups, backup verification and ordered chain reconstruction.
The application supervises PostgreSQL 18 utilities on the **application host**;
this does not imply that the application host is the database server. Configure
``CDEADMIN_POSTGRESQL_CONTINUITY_BINARY_PATH`` (or the fixed/default ``pg-18``
binary directory) and ``CDEADMIN_POSTGRESQL_CONTINUITY_ROOT`` for that host.

Each owner/registration has durable, paged job receipts and protected artifacts.
Review records native replication cluster identity, timeline, authenticated
principal, tablespaces, WAL summarization, tool versions/hashes and exact options.
Start rechecks the target and registration before dispatch. Repeated starts
observe the same job. Private connection material is sealed for the worker and
released afterward; credentials are excluded from receipts and command arguments.
Native recovery-configuration output, when explicitly selected, can contain
credentials inside the protected backup, as PostgreSQL's utility specifies.

Plain backups relocate every observed tablespace into the managed artifact.
Reconstruction verifies each input and relocates the output tablespaces again.
Native PostgreSQL 18 verification supports plain and compressed TAR files; TAR
verification reports that WAL parsing was excluded. A native tool exit, verified
files and a successful independent recovery drill have separate meanings.
Cancellation retains its native process observation. A lost worker is reported
as unknown and is never automatically restarted. Verification of uncertain
artifacts requires observed writer termination. Receipt inspection and artifact
verification remain available when the source server is offline.

``tools/cdeadmin_postgresql_continuity_qualification.py`` exercises the
application's authenticated HTTP routes against a uniquely owned PostgreSQL
18.3 fixture. It independently restores the reconstructed chain, including
relocated tablespaces and exact bigint, Unicode and binary data, and verifies an
artifact after stopping the source server. Its tools' versions are recorded
separately from the exact server version. This Docker fixture is development
evidence; it is not native Windows/macOS qualification.

PRODUCT-GAP-11 remains open for application recovery drills, production restore,
PITR/WAL archive and retention workflows, standby bootstrap and registered remote
execution hosts, plus corresponding MySQL/MariaDB physical continuity work.
TAR input materialization for reconstruction, very large manifests and long
running backup limits also remain open. Standby recovery configuration using
non-environment libpq secrets (such as an encrypted TLS private-key password)
is refused until persistent standby credential provisioning can replace the
temporary service alias. These scoped workflows do not close the
full native utility option denominator or the complete six-engine matrix.
History testing remains explicitly deferred by the owner.

PostgreSQL manifest and runtime scaling increment
================================================

Native manifest file inventories are decoded incrementally. Their complete raw
bytes are hashed while reading; the complete ``Files`` array is not retained in
memory and there is no overall 128 MiB manifest cap. Individual native metadata
values retain a 1 MiB decoding bound. Numeric progress and cancellation cover
manifest inspection as well as native utility execution. Verification records
observed checksum algorithms and the number of manifest files with and without
checksums; requested backup options do not substitute for observed file facts.
An uncertain artifact lacking a prior manifest receipt is inspected by its
verification worker, rather than blocking the review request on a full scan.
Native ``pg_verifybackup`` remains the authority for content and WAL checks.

Every continuity utility accepts an explicit positive timeout or no deadline.
The editor retains a 3,600-second default; clearing it selects no deadline.
The SDK requires explicit trusted grant authority for an unbounded process, and
cancellation remains available. Operators can impose a per-utility ceiling with
``CDEADMIN_POSTGRESQL_CONTINUITY_MAX_RUNTIME_SECONDS``; unset/zero imposes none.
A policy or configured binary-path change invalidates an undispatched review.
Input verification and output verification use the reviewed timeout too.

These changes address manifest inventory scaling and the previous one-hour
hard limit. Production recovery, PITR, standby provisioning and remote execution
hosts remain separate implementation work. History testing remains deferred.

DuckDB and SQLite retained-session catalogs
==========================================

The editor's explicit Session catalog inspection now covers DuckDB and SQLite
alongside PostgreSQL. It uses the original provider handle, serializes access
against execution and retained scripts, and includes that session's temporary
objects, attached databases, loaded connection functions/collations and pending
catalog changes. DuckDB's temporary database and schema parents are included;
temporary objects are not mistaken for objects on another connection.

SQLite reads use a uniquely owned savepoint and restore the original transaction
state. An idle connection's ``defer_foreign_keys`` setting is preserved after the
owned read transaction, through the caller's unchanged native authorizer.
An unhealthy DuckDB transaction is refused without rollback. DuckDB observes its
existing native transaction context without asserting an independent snapshot or
running the separate macro-source export's ATTACH/COPY/EXPORT operations.
Native cleanup failures block session reuse; no caller transaction is repaired
implicitly.

Inspection distinguishes temporary, connection, attached-database and runtime
scope. Wide native integers are decimal text at the browser boundary with an
encoding descriptor; the DDN source retains the original exact metadata. Session
DDN documents carry explicit observation provenance and are refused by the
independent DuckDB/SQLite schema planners. Existing catalog/DDN size bounds remain
explicit; this increment does not assert whole-product catalog completeness or
close the broader independent catalog, native feature and platform inventories.

Native editor hidden-column projection
======================================

Retained editor metadata distinguishes queryable columns from a relation's
wildcard projection. MySQL/MariaDB invisible columns and SQLite virtual-table
hidden fields remain explicit completion candidates. SQLite generated columns
remain in ``SELECT *``; native rowid aliases are offered only on observed rowid
tables and are suppressed when a real column shadows them. DuckDB rowids are
offered on native DuckDB storage tables, including temporary tables, with real
column shadowing respected. Views and foreign extension storage do not acquire
invented DuckDB rowids. Firebird base-table ``RDB$DB_KEY`` is an explicit binary
record identifier suggestion. These identifiers are not durable application keys.

Wildcard expansion in CTEs and derived tables excludes explicit-only columns;
an explicitly selected hidden column becomes an ordinary projected column. The
native editor gate independently compares native cursor descriptions and direct
column queries on owned fixtures, preserving pending user work. This closes a
specific projection gap, not the complete editor/grammar or product inventory.
PostgreSQL completion also observes native negative attribute numbers on base
tables, partitioned tables and materialized views. System columns stay out of
star expansion, JOIN USING and INSERT/UPDATE/ALTER target lists; ordinary views
do not acquire system fields. Foreign tables are included, with universal
``tableoid`` completion; additional system columns specific to a loaded FDW
remain a separate capability inventory. PostgreSQL completion preserves native
insertion text and UTF-16 replacement starts at the shared editor boundary,
including expanded column lists and quoted identifier spans.

Windows qualification repairs
=============================

Native Windows evidence identified a PostgreSQL parser build failure caused by
including Python's CRT headers before PostgreSQL's internal Windows port
headers. The pinned parser patch now forces the PostgreSQL/Python include order
for the MSVC extension build. The native libpg_query library still uses its
separate native build, and the SQL/PLpgSQL string-context patch remains required.
The ScratchBird client installation follows this parser build; no ScratchBird
server or history tests are introduced by the repair.

DuckDB/SQLite typed data layouts encode registered file device/inode identities
as decimal strings. Windows can supply file IDs outside JavaScript's exact
integer range; treating them as numeric data made DDN imports reject otherwise
valid native captures. Review and dispatch compare the exact textual identities.
These repairs require a new native Windows receipt before platform completion
can be asserted; Linux simulation and parser build evidence have narrower scope.
The ``postgresql-parser`` native development stage builds and installs the
patched wheel into owned environments, then checks direct AST structure access,
Unicode and repeated SQL/PLpgSQL string-setting transitions. It runs through the
existing GitHub workflow's targeted stage selection and does not qualify the
full application environment or start any database server.

SQLite index and trigger replacement
===================================

Changed explicit indexes and triggers now produce an isolated reviewed native
replacement. Preview prepares a declaration under a uniquely owned probe name
without executing its CREATE VM. The write worker rechecks the original object
and native schema dependency fingerprints, then performs DROP/CREATE inside one
owned SQLite transaction. Native unique-index constraints, trigger bindings and
desired native catalog facts are checked before commit. Failure rolls back the
replacement; durable receipts never replay it. Fresh independent catalog
discovery verifies acknowledged commits.
Temporary names are derived from the exact plan inputs, so recomputing a table
rebuild or replacement during review preserves the displayed execution digest.

INSTEAD OF triggers on views are checked for their actual defining write events.
Changing a trigger event does not require unsupported INSERT/UPDATE/DELETE
operations on that view. Batches of up to 32 index/trigger replacements share
one native transaction. All baseline guards run before dispatch; dependency
binding and desired catalog verification use the final batch schema before
commit. A later failure rolls back every earlier replacement in that batch.
Retained children of a rebuilt table use the coordinated rebuild path described
below, including desired index/trigger sources for renamed columns. Human form validation and
ScratchBird history qualification retain their existing ownership/deferral.

Coordinated SQLite table transformations
======================================

The catalog workspace accepts up to 32 selected ordinary-table rebuilds in one
reviewed native transaction. Every original table, child definition, inbound
foreign key and retained dependency is checked before dispatch. Each table's
rows and applicable physical rowids/AUTOINCREMENT high-water mark are preserved
under its reviewed native conversion rules. Native foreign-key and retained
view/trigger binding checks run on the complete resulting schema before commit,
so coordinated parent/child key conversions can be reviewed together. Failure
in any copy or final constraint check rolls back the whole batch. Independent
rediscovery verifies every acknowledged table transformation.

Mixed batches can combine rebuilds with replacements on other objects and
admitted additions. The current rename editor maps columns on a
single selected table; broader coordinated dependency source rewriting remains
separate implementation work.

PostgreSQL server-file large-object workflows
============================================

Large-object forms expose native ``lo_import`` and ``lo_export`` on the database
server host, including native allocation or an explicitly selected import OID.
These native file operations are not limited to the editor's 1 MiB chunk size.
File paths preserve exact whitespace, quotes and backslashes, and input exceeding
PostgreSQL's native path buffer is refused rather than silently truncated.
The native function ACL, large-object ACL and server operating-system access
still govern each operation. Import allocates a transactional database object;
export can overwrite its selected server file and requires exact path confirmation.

Receipts identify the database-server filesystem separately from SQL transaction
finality. A lost export acknowledgement is unconfirmed and is not replayed;
SQL rollback cannot undo bytes already written by the server. Native SQL success
does not assert an independent file-content or filesystem durability check.
The owned platform fixture enables ``server_file_tests`` and removes its files
with the disposable cluster. External route qualifications leave those tests
disabled unless explicitly requested on a disposable estate with teardown.
Continuous browser/client whole-file streaming remains separate implementation
work; these native server paths are not application-host upload/download paths.

PostgreSQL application recovery drills
=====================================

The continuity workspace can review and run an offline recovery drill against a
verified full or reconstructed physical backup with locally collected WAL.
It verifies the input, copies file bytes and managed tablespaces into private
application-host storage, verifies that copy, and runs a supervised PostgreSQL
18 standalone backend. It opens no network listener or source connection. The
source backup is never started or modified, including hard-linked reconstructed
inputs. Configuration includes, auto-conf credentials, preload libraries,
archive/restore commands and standby routing are discarded on the copy.

A successful receipt requires confirmed native process termination and a fresh
SQL result matching the reviewed cluster and database. Up to 64 exact native
heap tables or materialized views can have row counts recorded or compared with
reviewed int64 decimal expectations. A zero exit with a SQL error, missing
result, wrong identity or mismatched count does not qualify recovery. Dispatch
is durable and never automatically replayed; cancellation retains its receipt.

This qualifies native WAL recovery and the selected counts on that execution
host. It does not qualify every database or extension in a cluster, production
restore, point-in-time recovery, archived-WAL retrieval or standby provisioning.
Source-build dependencies must exist on the execution host.
History testing remains deferred by owner direction.

SQLite mixed native migrations
==============================

A reviewed SQLite transaction may combine table rebuilds, replacements on other
retained indexes/triggers, and admitted schema additions. Every baseline,
dependency and native grammar guard runs before the first write. Row/identity
preservation applies to each rebuilt table; foreign keys and the complete final
view/trigger bindings are checked before commit, including newly created views
and changed trigger events. A later failure rolls back all preceding stages.
Acknowledged commits receive independent catalog rediscovery; durable receipts
never replay the migration.

Rebuilds also coordinate changed definitions for their retained explicit indexes
and triggers, including definitions using an explicitly renamed column. The
table's child facts and individual DDN records must agree with native compilation
of the desired table. Those children are recreated after copying rows; final
bindings and desired child metadata are checked before commit. Unique-index or
trigger-binding failure rolls back the entire batch. Rowids and AUTOINCREMENT
continuation retain their applicable preservation contracts.

The same rebuild can create new indexes/triggers and remove children selected by
exact explicit deletion identity. Native compilation must agree with every
desired child record; a filtered-out child is not deletion intent. Reviewed
warnings identify discarded child identities, and precommit checks verify their
absence. Deletions outside selected rebuilt tables remain separate reviews.
Retained views can be replaced in the same reviewed batch, including chains
depending on renamed table columns. CREATE VIEW column lists remain native
grammar. The defining view facts and individual column/trigger records must
agree. DROP VIEW's implicit trigger removal is handled by recreating observed
INSTEAD OF triggers before later admitted trigger changes. Native final-schema
binding, complete view-column metadata and trigger definitions are verified
before commit; a broken dependency rolls back every earlier stage. Other
dependent object rewrites remain subject to their applicable native adapters.

SQLite invalid-view discovery and repair
=======================================

Native view definitions, identities and trigger associations remain discoverable
when columns or query bindings cannot be observed. Separate native observations
record column availability and nonexecuting EXPLAIN binding, including native
error codes. The containing catalog identifies affected views; an unavailable
observation is never reported as an empty complete set of columns. File/transport
and other failures still propagate rather than being hidden as binding errors.

An invalid view can be selected for reviewed DDN replacement. The desired design
must provide complete native columns and child facts. Native final bindings and
metadata are verified before commit, with independent rediscovery afterward.
Existing INSTEAD OF triggers retain their definitions, and repeated requests
return their durable receipt without replaying the repair.

Editor metadata also retains other native symbols when a SQLite view's column
binding is invalid or denied, with an explicit unavailable observation. Its
retained transaction and native authorizer remain owned by the user session.
Native editor context revisions include the observed symbols and section
availability, so repairs, rollback and observed catalog changes invalidate the
previous completion context.

MySQL and MariaDB editor contexts retain the native authenticated principal and
active role, including each engine's representation of no active role. A role
change invalidates the previous context even when visible object names stay the
same. Metadata observation uses the retained native session without finishing
pending interactive work.

Firebird network and embedded editor contexts also observe CURRENT_USER and
CURRENT_ROLE from the retained attachment. Native role changes invalidate the
completion context. Metadata releases its own idle read transaction while
preserving an existing interactive transaction and its pending writes.

PostgreSQL observes the authenticated, session and effective principals, native
current/selected role, raw and resolved search path, encodings and SQL string
settings. These facts participate in the editor context revision. Observations
use an owned read transaction or an observation savepoint inside pending work;
cleanup restores the original transaction state. An aborted transaction is not
queried or implicitly repaired. Unavailable observations do not supply assumed
language settings; unconfirmed cleanup blocks reuse of the retained session.
The native PostgreSQL completion queries use the same transaction guards. A
failed catalog query cannot leave an enclosing user transaction aborted or be
reported as a complete suggestion set. Completion and its context observation
hold the retained-session lock together; role/settings changes cannot interleave
between those two parts of the reply.

DuckDB context revisions include the full native search path and installed/loaded
extension identities, versions and install modes. Changing a later search-path
entry invalidates context even if the default schema and visible symbols stay
the same. Installation paths and repository locations are not exported.
SQLite observes native connection flags through the client library, including
double-quoted string handling, trusted schema, defensive mode and foreign-key/
trigger enablement. Missing client bindings are explicit unavailable sections.
Flag changes invalidate context without replacing the retained connection or
finishing its pending work. These observations are read-only.

Native grammar/binding refusals remain visible and do not certify the full
SQLite migration denominator.

PostgreSQL compressed TAR recovery
=================================

Recovery drills materialize full directory TAR backups using uncompressed,
gzip, LZ4 or Zstandard archives. Base files, managed tablespaces and applicable
streamed WAL archives are copied into separate private plain-file storage.
Fetch-mode WAL is retained from the base archive. The source archives remain
unchanged. Decoding is bounded, reads concatenated compression frames and final
checksums, refuses unsafe paths/links/special entries and supports cancellation.

Native compressed-file verification precedes materialization. Native plain-file
and WAL verification then checks the materialized copy before PostgreSQL starts.
The recovery receipt retains both scopes; TAR file checks alone do not establish
WAL availability or recovery. Production restore remains separate work.

Reconstruction also accepts reviewed TAR and mixed TAR/plain chains. It verifies
each source in its native format, materializes each archive into a distinct
private input scope with that artifact's tablespaces, checks the copied manifest
identity, and verifies the plain files and applicable WAL before combining.
The native combine utility remains the authority for incremental ancestry and
chain order. The output receives its own native verification and can be selected
for a recovery drill. Receipts retain source-format and materialized-input
verification separately. Original archives are unchanged; intermediate copies
remain with the reconstruction job and need additional application-host space.
Native TAR tablespace maps retain source-host paths. Recovery preparation removes
or replaces that map on the independent copy before starting PostgreSQL; the
application recovery drill removes it and uses its managed relocated links.

MySQL native local physical clone
================================

The native MySQL server menu provides reviewed local cloning through the
installed clone plugin. It copies the plugin-supported InnoDB data and data
dictionary into a new database-server directory. Configuration, binary logs,
external encryption keys and other storage engines need their applicable
workflows. The server's native BACKUP_ADMIN and filesystem rules remain the
execution authority; a missing plugin is reported as unavailable.

Durable jobs own separate native worker and observer connections. Dispatch
rechecks server UUID, version, principal, plugin/settings and filesystem path
conversion. Native performance-schema status is correlated by clone ID,
connection ID, operation start time, source and destination. Local clone IDs
can be reused; the operation identity is frozen while its connection is owned.
Cancellation additionally checks the
current native PFS thread identity before KILL QUERY. Client timeout or lost
connection does not prove server termination or filesystem rollback. Unknown
jobs can inspect native state again without replaying the clone. Terminal
receipts remain available while the source is offline.

Native clone completion, independent file verification and a recovery drill
retain separate receipt fields. Server-host restore/provisioning,
the remaining native physical backup utilities, PITR and archive management
remain separate product requirements.

Registered remote MySQL cloning
-------------------------------

The same dialog can select an owned native MySQL donor registration and an
explicit TCP address reachable from the recipient. Review captures both native
SQL identities and registration fingerprints. Confirmation delegates the donor's
registered password under provider-tool authorization to an independently owned
recipient connection; a zeroizing lease is released after native execution.
Passwords are excluded from durable reviews, receipts and downloaded evidence.
Native CLONE's utf8mb3 system-string password grammar cannot preserve NUL or
supplementary Unicode characters; those credentials are refused before dispatch.
Only a new directory is supported; this workflow does not replace the recipient's
active data directory or restart it.

The recipient's native donor allowlist and CLONE_ADMIN privilege, and the donor's
BACKUP_ADMIN privilege, remain authoritative. Required TLS is the default.
Native CLONE uses recipient-side clone_ssl_ca/cert/key settings and cannot verify
the donor hostname; registrations requiring hostname verification are refused.
Registered CA verification requires recipient-side CA configuration and TLS.
The donor SQL UUID and the clone protocol's source address are distinct recorded
observations; the latter does not provide application-visible UUID attestation.
Remote status uses the exact native host:port source in addition to the frozen
worker/operation identity. Native refusal, cancellation, unknown outcomes and
independent recovery retain the same separate receipt semantics as local clones.

PostgreSQL native point-in-time recovery drills
===============================================

The physical recovery dialog selects native timestamp, transaction ID, WAL LSN,
named restore point or earliest-consistency targets, with native inclusion and
timeline policy. It selects completed WAL archives scoped to the current owner
and registered endpoint on the application host. Archive directories are under
``CDEADMIN_POSTGRESQL_WAL_ARCHIVE_ROOT/<owner>/<endpoint>/<archive>`` or, by
default, ``<continuity-root>/wal-archives/<owner>/<endpoint>/<archive>``.

The reviewed inventory contains native filenames, exact byte lengths and SHA256
hashes. Up to 100000 completed segment/history/backup-history files are admitted
per review. Partial files, other entries, links and reparse points are refused.
Dispatch checks the inventory and file content while staging into the independent
copy's private WAL directory. The original backup and archive are unchanged.

Native PostgreSQL validates WAL headers, cluster identity, record checksums,
timeline ancestry and the requested stop point. An unreachable target fails
before the standalone SQL receipt. Successful recovery promotes the independent
copy onto its own timeline without a network listener. The receipt separately
records reviewed archive matching, the selected target and recovered heap row
counts. Duplicate starts observe the durable job and do not replay recovery.
Production cutover, continuous archive collection/retention and remote execution
host integration remain separate obligations.

DuckDB native nested editor members
====================================

Editor metadata uses a separately owned native type-parser connection to expose
named STRUCT
and UNION members, including recursively nested structures and exact quoted
field names. UNION's internal unnamed tag is not a dot member. Named aliases
resolve through their native child paths. Direct CTE/derived-table projections,
renamed columns, explicit CTE column lists and STRUCT star projections retain
known native member types; computed expressions do not receive guessed types.
UNION members are not fabricated as a STRUCT star projection.

Native type binding that cannot represent an observed type, including unnamed
positional tuples, produces an explicit unavailable member observation while
retaining other symbols and pending interactive work.
The companion shares the native database installation and committed type
catalogs; it does not replace the retained catalog/session observation. Parsing
failures cannot abort the user's transaction. Session-local type resolution
that the companion cannot observe remains explicitly unavailable.
Indexed tuple/list expression completion and wider procedural scopes remain
separate obligations.
