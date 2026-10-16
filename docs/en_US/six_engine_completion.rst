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
  support; complete procedural-scope coverage still requires qualification.
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
  reconciliation checks privileged and restricted observations; session-local
  database catalogs and broader live topology qualification remain separate.
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
