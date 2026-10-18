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

Current implementation matrix, 2026-10-17
=========================================

All six engines now have catalog-backed completion, native nonexecuting
preflight, engine-specific formatting and implemented native administration,
data and design workflows. The implementations and scoped receipts below
supersede the initial findings about absent wiring. Full product acceptance
remains open for every engine; a scoped workflow is not the full denominator.

.. list-table:: Current implementation and remaining acceptance
   :header-rows: 1
   :widths: 14 29 30 27

   * - Engine
     - Catalog and editor
     - Implemented workflow scope
     - Remaining full-product acceptance
   * - MySQL 9.7.0
     - Independent native category/DDN reconciliation; retained catalog and
       mode/role-aware completion; native PREPARE and qualified post-parse
       checking for stored programs, administrative and transaction commands;
       native quoted-identifier and dollar-body framing, formatting and
       shared preflight/execution parameter boundaries, with SQL suggestions
       suppressed inside opaque bodies. Shared native parameter conversion
       preserves live client character sets, including MySQL latin1's Euro
       mapping, through retained-session and pooled reuse. Parameterized batches
       reobserve SQL mode and character sets at each framed command boundary;
       later local refusals preserve completed results and report partial dispatch.
       Unbound explicit setting/call and client-delimited batches use the same
       observed command boundaries and preserve source-literal character sets.
     - Native administration, data/DDN work, local/registered remote clone,
       Shell/raw closed archives and reviewed native replay with GTIDs on/off,
       exact transaction boundaries and shared target fencing.
     - Complete base/PITR/cutover, continuous archive/retention,
       wider procedural scopes and complete installed-capability/lifecycle/HA
       workflows and evidence.
   * - MariaDB 12.2.2
     - Independent native category/DDN reconciliation; retained catalog and
       mode/role-aware completion; native normal/Oracle-mode preparation.
     - Native administration, data/DDN work and independently verified closed
       raw logs with native checksum, compressed-event and GTID-domain semantics;
       reviewed native archive replay with target fencing and GTID boundaries.
     - Complete PITR/physical continuity, active/continuous logs and
       retention, wider procedural/package scopes and full native operational
       and installed-capability acceptance.
   * - PostgreSQL 18.3
     - Independent server/retained-session catalog work; native completion,
       context/savepoint preservation and qualified SQL/SQL-body/PLpgSQL checks.
     - Typed imports and durable recipes; native large objects/whole-file
       transfer; physical/incremental/compressed reconstruction and WAL-target
       recovery drills; additional native statistics collectors.
     - Production restore/cutover, continuous archive/retention, remote-host
       lifecycle/upgrades and complete installed-extension/language/HA coverage.
   * - DuckDB 1.5.2
     - Native attached/session catalogs, functions/types/macros, retained
       completion, native parsing and nested/indexed/positional member binding,
       including grouped receivers and explicitly named CTE projection positions.
     - Native administration, typed data/DDN imports, durable recipes and
       qualified schema transformations and retained-session workflows.
     - Remaining native transformations, computed/contextual binding and full
       independent installed-extension/feature and platform reconciliation.
   * - SQLite 3.53.0
     - Native schema/function/collation/flag observations, compiled keyword
       roles, lazy builtin table-function columns/arguments, retained completion
       with native schema priority and guarded nonexecuting compilation.
     - Native file/data workflows, typed imports, durable recipes, coordinated
       rebuilds, view/index/trigger replacement and atomic creation of ordinary
       relations with their explicitly declared indexes and triggers; native
       table/column rename design generation, reference rewriting and native
       FTS/RTree/Geopoly table renames; native quoted module identities;
       reviewed approved-library loading into retained query sessions, native
       symbol refresh and explicit uncertain initialization outcomes; reviewed
       native FTS configuration changes with preserved content and durable receipts.
       Structured native virtual-table constructors and retained-session FTS
       maintenance preserve transaction ownership; partial module/metadata
       observations retain healthy editor completion and explicit coverage.
       Reviewed external-content FTS4/FTS5 public-column renames preserve
       ordinary dependent views, maintenance triggers and native index settings.
       FTS4 language-column and selected FTS hidden MATCH-column mappings
       preserve native language-specific searches and dependent code.
       FTS5 table-function dependencies use isolated native AST binding and
       transactional recreation, with reviewed utility identity and final
       native view/trigger checks. Ordinary and FTS rename dependencies follow
       native inferred projection labels through downstream views and view
       triggers; explicit output aliases remain stable.
       Ordinary-content row identity changes preserve native FTS document keys
       through FTS4 mapping views or FTS5 content_rowid rebinding.
       FTS content views retain their named document/field projections during
       base-column renames, including stars and nested source views.
       Offline native file recovery uses private WAL/journal images, exact
       typed transfer, reviewed new-file publication, durable outcomes and
       registration/activation of recovered copies.
     - Remaining attached/content-view alias shadowing, language identity and installed-module transformations and
       complete native extension/feature and platform reconciliation.
   * - Firebird 5.0.4
     - Independent network/embedded category/navigator work, native DSQL/PSQL
       preparation, exact dialect context and native catalog completion.
     - Existing native administration, data/DDN, diagnostic, collector/dashboard
       and desktop/lifecycle workflows retain their own acceptance scopes.
     - Complete independent native feature/installed-capability reconciliation
       and current platform/release evidence beyond the declared task receipts.

Persistent ScratchBird history clients and all six collector integrations remain
wired. History testing is owner-deferred. Human form validation and native
Windows/macOS qualification remain with their assigned teams. Those obligations
are distinct from remaining backend implementations and native qualification.

Navigator child requests are coalesced for the same parent and metadata state.
A refresh, parent replacement or route change during a pending read discards
the stale response and loads the current hierarchy. A detached empty parent
cannot hide the replacement's children or publish facts from its prior route.

Source audit baseline, 2026-10-16
=================================

The following findings describe source revision
``c312b5b473aa41d5054935f331df5c72af8603c4``. This is a source audit with references
to existing scoped receipts, not a new native qualification run. All six engines
have implemented administration, data and DDN work; none yet has evidence closing
all four product requirements above.

.. list-table:: Initial audit evidence and open product coverage
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

Initial work ledger
-------------------

These were the initial gaps and acceptance obligations. The current matrix and
subsequent implementation sections supersede statements about missing wiring
in this historical ledger. The complete native denominator still requires
independent reconciliation; further inventory may add work.

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

PostgreSQL whole-file large-object transfers
--------------------------------------------

The database context menu opens a dedicated client-file workspace. Imports stage
bounded, checksummed chunks in private application-host storage, validate retry
bytes, and prepare an exact whole-file checksum review. Confirmation creates a
new native large object in a separately owned PostgreSQL transaction, verifies
its complete native postimage, then commits. An existing explicit OID is refused
by PostgreSQL; this workflow does not replace an existing large object.

Exports read one repeatable-read native snapshot into a private application
artifact and independently verify that artifact. Authenticated form navigation
streams its binary HTTP response to the browser download manager without a
complete-file JavaScript Blob or a filesystem picker. Native metadata, effective
role, database identity, lengths, OIDs and SHA-256 values remain in owner,
endpoint and database scoped durable receipts. Application artifact storage is
under ``CDEADMIN_POSTGRESQL_LARGE_OBJECT_ROOT`` or the operation store's
``postgresql-large-object-files`` sibling directory.
Application files can be removed with an exact transfer-ID confirmation after
their writer stops. Durable receipts and committed PostgreSQL objects remain.

Cancellation requests apply to an owned native connection and report rollback
only after native acknowledgement. Lost commit replies remain unknown with no
automatic replay. Import reconciliation queries the retained native xid8 status;
export reconciliation can verify complete application bytes while retaining an
unknown read-only commit outcome. An artifact receipt does not certify that a
browser saved or independently verified the client file. Server-file LO import
and export remain separate database-server operations.

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
Wider procedural scopes retain separate acceptance.

DuckDB indexed collection members
---------------------------------

Native editor observations retain recursive LIST, ARRAY and MAP element types,
including array lengths and named STRUCT/UNION members. Container elements do
not become fictitious dot fields. Completion resolves native member types after
balanced indexing, repeated indexing and list/array slicing, with exact quoted
insertion names. Direct indexed projections with explicit aliases retain their
observed types in CTEs and derived tables. Unqualified columns require one
unambiguous source binding.

Type traversal has explicit node, depth and response-byte limits. A limited or
unbound type preserves its owning column and reports incomplete observation.
Type parsing continues to use the companion connection; pending editor work is
neither committed nor rolled back. Index expressions are not evaluated by
completion, and suggestions do not establish grammar/binding acceptance of an
arbitrary index expression. Computed-expression inference retains separate
acceptance.

When the native string type parser cannot represent an unnamed tuple, the
companion binds the observed quoted column/relation and reads its logical type
without fetching rows. That type must exactly match the retained catalog's
observed type. The editor preserves unnamed positions and resolves positive
literal ordinals followed by named members or further list/array indexing.
Ordinal access does not invent dot-field names. A session-local or changed type
that the companion cannot confirm remains explicitly unavailable. Dynamic and
computed tuple ordinals retain separate acceptance.

DuckDB completion also respects its native identifier keyword classes and
keyword column labels after a dot. An unqualified source column can shadow a
built-in function name; ambiguous source columns are not guessed. These rules
apply to retained member types and direct CTE/derived projections as well as
ordinary alias paths.

MySQL and MariaDB qualified keyword names
------------------------------------------

The editor follows the native MySQL-family lexer rule that an identifier
immediately following a qualifying dot is an identifier even when its spelling
is a keyword. Qualified table/column names retain native source bindings through
aliases, CTE stars and direct projections. Insertion quoting follows the observed
SQL mode. Native qualification includes MySQL pure/C clients and MariaDB normal
and Oracle modes; this does not close other procedural or mode-specific scopes.

PostgreSQL exact dialect and statistics contracts
=================================================

The PostgreSQL 18.3 activation descriptor now includes native SQL/PLpgSQL grammar,
keyword, diagnostic, type, function, operator and setting inventories. Its task
acceptance covers the 37 provider-generated SQL administration operations, with
native execution receipts bound to the exact compiler sources. Preserved HTTP
forms and full product/platform acceptance retain their separate obligations.

An independent reconciliation of the release's core statistics/diagnostic view
definitions with the running native catalog identifies 52 view families and 604
columns. Collector policy can select these additional families. Collection uses
an independently owned read-only attachment, per-family savepoints, native
privilege checks, a 200-row limit per source and a shared 512 KiB row-byte budget.
Denial, native visibility, scope and truncation are explicit. Query/credential
text and string setting values are redacted; native numeric values retain their
exact textual representation. Collector-session views describe that collector's
session rather than the user's editor connection.

The dashboard's additional-statistics display uses the DDN viewer with ten rows
per page. It retains all native columns and exposes coverage and permission
results. Family selection belongs to collector policy; viewing does not start
collection or alter policy. Optional extension views require their own inventory
and acceptance. ScratchBird history qualification remains owner-deferred.

MySQL native binary-log archives
================================

The server's backup menu exposes native MySQL Shell9.7 binary-log archives,
with independent source/GTID observation, explicit execution-host and filesystem
scope, reviewed file/position or retained-archive continuation, native
compression and runtime options. Jobs claim durable identities before dispatch,
never replay after restart, retain progress/cancellation observations and keep
unknown process finality explicit. A no-op does not create a fictional archive
or advance the continuation cursor.

Verification reconciles native completion sidecars, source UUID, complete file
inventories, streaming decoded lengths/event counts and native v4 CRC32 where
present. Every file retains size/SHA256. Reconciliation preserves a prior sealed
postimage; application file verification is distinct from replay/recovery.
Private temporary JSON credentials preserve native password characters and the
registered utility TLS policy. Authenticated downloads, paged file inventories,
offline receipts and explicitly confirmed application-artifact removal are
integrated into the workspace. Unknown writers cannot authorize removal or
continuation. Complete PITR, continuous
collection/retention remain open requirements.

MariaDB native closed binary-log archives
==========================================

MariaDB12.2.2 now has a separate raw closed-log archive adapter and native parser
verification, exposed through the server's backup menu. Selection preserves a
contiguous native catalog range. The native server UID, authenticated principal,
log closure/order and file-size observations are checked at admission and on an
owned observer after retrieval. MySQL and MariaDB retain distinct archive
formats and verifiers while sharing owner/endpoint durable job infrastructure.

The archive workspace supplies review/confirmation, progress, cancellation,
uncertain-worker handling, offline receipts, byte verification, authenticated
downloads and explicit artifact removal. Native checksums-disabled streams,
compressed row events and native GTID domains retain their own semantics.
Native utility dependencies use explicit application-host execution grants and
registered transport/credential policy. Both MySQL and MariaDB now flush file
data before atomic archive-name publication. Archive verification does not
establish successful replay/recovery. Active/continuous collection, retention,
complete PITR, physical continuity and production cutover remain separate
open requirements. Reviewed archive replay is described below.

SQLite native keyword-name completion
======================================

SQLite completion now observes its loaded runtime's compiled keyword list and
native identifier roles using nonexecuting constant SELECT plans. Native
fallback names, implicit-alias restrictions, qualifier restrictions, contextual
WINDOW/OVER/FILTER handling and quoted string names retain their own semantics.
Source binding preserves keyword table/alias names through CTEs, projections and
joins, and uses ASCII keyword folding. Metadata probes do not call overridden
user functions or settle pending work. Denied observations remain incomplete.

MySQL native binary-log replay
================================

The native MySQL server restore menu selects a retained verified archive from
an owned source registration and a separately confirmed target UUID. Review
captures target identity, principal/role, exact GTID state, sealed input identity,
native utility identity, execution host and runtime policy. Dispatch independently
verifies and stages the archive, rechecks the target, and uses MySQL Shell's
native loader with GTID-gap and version checks enabled. Full archive replay and
stop-before/stop-after one exact native GTID have separate native semantics.
The source can be offline once the sealed archive exists.

Durable owner/endpoint claims prevent automatic replay, and target UUID fences
coordinate registrations and application workers. A native named lock and GTID
comparison guard the final utility boundary. Cancellation cannot undo committed
transactions. A missing acknowledgement remains unknown, including when current
GTID observations show archived transactions. Reconciliation records current
facts separately; exact acknowledgement can release a fence only after the
owned worker stops and native process/lock termination is observed. It does not
change the original unknown outcome or dispatch that job again.

Receipts distinguish native utility return, process termination, native GTID
coverage and independent recovered-data verification. These workflows require a
compatible restored base. Native replay qualification on independently initialized
servers with equivalent empty user schemas and explicit GTID seeds does not
qualify physical base recovery, end-to-end PITR, production restore or cutover.
Application-host replay storage uses ``CDEADMIN_MYSQL_BINLOG_REPLAY_ROOT`` or the
operation store's ``mysql-binary-log-replays`` sibling directory. Operators can
limit utility runtime with ``CDEADMIN_MYSQL_BINLOG_REPLAY_MAX_RUNTIME_SECONDS``.

MySQL native raw closed-log archives
=====================================

The MySQL server backup menu also provides native raw closed-log archives using
mysqlbinlog9.7.0, including GTID-disabled sources. The native raw format and
verifier remain separate from MySQL Shell dumps and MariaDB archives. Each
review selects a contiguous native closed-log range, source UUID and principal,
native utility identity, registered transport policy and application-host scope.
MySQL and MariaDB closed-log discovery both retry rotating or inconsistent
catalog observations before classifying an active file as closed.

The workspace owns private credentials, asynchronous durable claims, native
progress/cancellation, sealed file/event/checksum verification, native parser
verification, authenticated downloads, offline receipts and explicitly confirmed
artifact removal. Native parser LOAD DATA fragments remain inside a private
disposable execution scope. Local login-path files cannot override the reviewed
native connection policy. The raw utility accepts a single password factor;
additional password-factor bindings are explicitly refused rather than dropped.

Complete native file lengths are checked separately from event framing. MySQL
accounts for its native v1 encryption header when the replication stream
delivers decrypted bytes. Raw archives contain plaintext events even when the
source files are encrypted; keep these private artifacts protected.

Raw archives do not establish successful replay, base recovery or PITR. The
restore workspace selects Shell or raw format with separate native adapters;
it does not treat a raw archive as the Shell dump format. Continuous collection,
retention and full base/PITR acceptance remain separate. Storage uses
``CDEADMIN_MYSQL_RAW_BINLOG_ROOT`` or the
operation store's ``mysql-raw-binary-log-archives`` sibling directory; native
runtime policy uses ``CDEADMIN_MYSQL_RAW_BINLOG_MAX_RUNTIME_SECONDS``.

MySQL-family procedural preflight and live binding mode
=======================================================

MySQL9.7 preflight recognizes qualified native post-parse refusals for routine,
trigger, view, database and transactional-table headers, including comments,
DEFINER clauses and applicable native version comments. The native server must
have returned the recorded preparation refusal; lexical header classification
alone never validates source. Binding/preparation stages and native statement
observations remain separate, and post-parse acceptance does not establish
catalog binding or permission to execute. Context or permission failures retain
null grammar/syntax results instead of a positive syntax flag.

The MySQL pure client now observes decoded native OK/EOF status for parameter
escaping after SQL changes NO_BACKSLASH_ESCAPES. It preserves the native
converter's types and charset, performs one initial fixed metadata read and
never changes session mode for conversion. C clients retain their native
escaping path. Typed quote, backslash, NUL, Unicode and binary values retain
their original representations across tested mode changes. Full character-set
switching, mixed-mode parameterized batches and additional parser/rewrite
components retain separate reconciliation and qualification.

MariaDB native closed-log replay
-------------------------------

MariaDB 12.2.2 now has a dedicated server Restore workflow for sealed native
closed-log archives. It uses the registered transport and delegated credential,
checks both native utility identities, and runs ``mariadb-binlog`` followed by
``mariadb`` on the explicitly recorded application execution host. Reviews bind
the owned archive digest, native target ``server_uid`` and principal, current
GTID state, options, executable hashes and runtime policy. The archive source
can be offline. A compatible restored base must already be independently
verified; native GTID admission does not prove that base's data contents.

Native GTID/GTID_LIST event headers preserve MariaDB domain/server/unsigned
64-bit sequence identities. Resume admission combines the observed binlog and
replication positions per domain. With preserved source server IDs, native
``gtid_current_pos`` alone can lag ``gtid_binlog_pos`` on a separate target.
All three native positions are guarded and retained separately; the derived
replay position never changes the server replication stores. The native decoder filters transactions already
present on the target. Stop-before/stop-after boundaries use complete native
transaction groups in the ordered archived files. An in-client target/GTID
guard and named lock precede archive execution; a changed target or held lock
stops the batch. Replaying keeps native GTID assignments and requires target
binary logging and GTID strict mode. Complete archive checksums, framing and
cross-file GTID state are checked before native execution.

Durable owner/endpoint receipts distinguish utility return, local process
termination, native domain-sequence observations and independent data recovery.
A missing acknowledgement keeps the result unknown and fences every registration
of that native target. Reconciliation does not convert an unknown result into
success. Releasing that fence requires confirmed local process termination, a
free native replay lock and acknowledgement of the exact current observations.
An old job never replays automatically. Cancellation cannot undo committed
transactions. SQL output and raw native diagnostics remain private.

This closes the application archived-log replay gap in its recorded native
scope. Physical base recovery, continuous collection/retention, production
cutover, remote execution hosts and platform-team qualification remain separate
acceptance work. Persistent history qualification remains owner-deferred.

MySQL text cursor charset reconciliation
---------------------------------------

Connector/Python 26.7 text cursors now reconcile SQL character-set changes for
native source encoding, typed binding, result names and per-column text. Pure
connections negotiate native session tracking and consume the native system-
variable observations in OK packets. C connections use the native client charset
and a fixed session-variable observation before text dispatch; that observation
reads settings and never sends a replacement ``SET NAMES``. Pending work,
autocommit, savepoints and the selected character-set settings remain native.

The native MySQL Latin1 mapping is distinct from Python Latin1. Input and result
names preserve its Windows-1252 code points and undefined C1 positions. Pure
catalog conversions and C field/row conversion preserve the observed result
charset separately from the source charset. Raw result cells retain per-column
charset identity, including ``character_set_results=NULL``. Binary prepared
cursors retain the native driver path; this text-cursor work does not qualify
all binary prepared-statement charset combinations.

The fixed C metadata read is an additional native statement. Preservation of
native diagnostic state across application metadata reads remains a separate
requirement. Session-tracking-disabled pure connections, mixed-charset/mixed-mode
multi-statement parameter batches, the complete native charset denominator and
all optional protocol/parser components retain separate acceptance work.

SQLite coordinated dependency retirement
---------------------------------------

Explicitly selected view, index and trigger removals can now share a reviewed
native DDN batch with supported table rebuilds, column mappings, additions and
replacements. Removing a view also binds the exact observed identities of its
native children. Filtered or missing DDN rows still never authorize deletion.
Table and virtual-table deletions retain their separate-review requirement.

The owned SQLite write transaction revalidates the original file and dependency
facts before dispatch, removes selected dependencies before rebuilding, and
checks final views, trigger bindings, foreign keys and native postimages before
commit. An invalid new binding or failed native constraint rolls back the
retirements and rebuild together. Stale dependencies refuse dispatch. Durable
receipts do not repeat a completed or refused migration.

This extends coordinated migration scope; complete native rename/generation and
installed-module reconciliation remain separate full-product requirements.

SQLite coordinated relation creation
-------------------------------------

New ordinary tables and views can share a native DDN creation batch with their
explicit indexes and triggers. Preview compiles child ownership and grammar in
a separate empty SQLite database with the desired owner; it does not create
objects or run trigger DML on the registered file. The applying transaction
rechecks every target and owner, creates relations before their children and
prepares final view and trigger bindings before committing. A late binding
failure rolls back the complete batch. Stale targets prevent dispatch and
durable receipts never replay the original review.

This closes the separate-review restriction for those new relation children.
It does not qualify arbitrary installed module/function/collation environments,
full native renames or the complete native transformation denominator.

SQLite native rename generation and application
------------------------------------------------

The catalog workspace generates table and column rename designs through the
loaded SQLite runtime in a separate empty schema. SQLite rewrites the native
table, column, foreign-key, view, index and trigger references. Generated DDN
contains the complete rewritten main schema; a visual rename is not interpreted
as deletion and creation. Sequential table/column renames can share one review.
The registered file is unchanged until the separately confirmed application.

The owned applying connection uses native modern rename mode and checks the
original file identity and complete schema inside its write transaction. It
compares the rewritten schema and native view/trigger bindings before commit,
then rediscovers the committed postimage. Data and AUTOINCREMENT sequence state
are not copied. Existing foreign-key violations are compared after mapping the
renamed table identities; an existing violation does not itself authorize data
repair or prevent a metadata-only rename. A failed preservation check rolls back
the rename. Writer contention refuses dispatch without settling another
connection's work. A lost commit acknowledgement remains unknown and never
replays the original review.

Current generation covers ordinary main-file schemas using the runtime's
available native grammar. Attached/virtual-table environments and additional
installed module/function/collation adapters retain separate coverage. These
are implementation gaps, not inapplicable native features. Native rename
reviews remain separate from rebuilds and other transformations.

SQLite native virtual-table modules
-------------------------------------

Catalog classification now obtains virtual-table module identifiers through
SQLite's nonexecuting native compiler and authorizer. Quoted FTS declarations
remain FTS objects, and each virtual table records its native module observation.
The independent catalog gate observes module identities separately and reconciles
quoted/single-quoted/bracket-quoted FTS and spatial declarations, their native
child facts and navigator destinations.

Native DDN creation checks the declared module, target and installed runtime
without imposing a fixed module-name whitelist. Native acceptance covers quoted
FTS3/4/5, RTree, Geopoly, fts3tokenize, dbstat, fts4aux and fts5vocab creation and
their corresponding native queries. Constructor grammar, installed availability
and execution-time module refusal remain separate observations.

The rename adapter also admits native FTS3/4/5, RTree, RTree_i32 and Geopoly table
renames. Their real data, FTS postings/spatial queries and shadow storage remain
owned by SQLite's native rename implementation; the application copies no rows.
Stale schema and lost commit replies preserve the established refusal/unknown
receipt behavior. The catalog workspace exposes these observed table kinds in
the native rename selector. Column rename remains an ordinary-table operation
because SQLite refuses column renames on virtual tables.

Renaming an external-content owner can leave an FTS constructor pointing at the
old table/column even when native ALTER TABLE succeeds. The separately selected
reconstruction adapter below covers owner names and qualified row identities. Other
module-specific operations, attached transformations and the complete installed
capability denominator retain separate acceptance.

SQLite external-content FTS reconstruction
-------------------------------------------

The rename workspace exposes exact external-content FTS4/FTS5 identities for
explicit reconstruction. Native owner table renames and FTS5 content-row identity
renames can rebuild the selected dependent index in the same owned write
transaction. The generated review includes its DROP/CREATE, constructor changes,
native settings, rebuild and native integrity check. Owner rows, row IDs and
AUTOINCREMENT state remain in the original table. Search indexes are rebuilt
from the current content rows; this deliberately repairs pre-existing index
drift rather than promising identical old index bytes.

Catalogs preserve native FTS5 stored configuration and FTS3/FTS4 auto-merge
settings. The exact3.53 native maintenance commands restore those settings;
native FTS5 index-format versions remain separately observed. Desired settings
must reproduce their proposed catalog values through native setters in an empty
private database. Creation also restores explicitly supplied FTS configuration.
Configuration changes after review prevent dispatch. Native denial and failures
after real DROP/CREATE roll back the complete operation; a lost reply after an
actual commit remains unknown and the original review never repeats.

FTS3's ``content=...`` spelling is a column declaration, not FTS4's external-
content option. It retains its native behavior. Renaming public FTS content
columns or FTS4 language/row mappings still needs coordinated column and
dependency rewriting; those remaining adapters are not claimed complete.

SQLite unavailable module and child observations
-------------------------------------------------

A native schema object remains discoverable when its virtual-table module is
not loaded in the inspecting connection or its column metadata is denied or
unavailable. The catalog preserves the exact definition and identity, records
the native error separately from an empty column list, and continues observing
healthy relations. Module declarations and actual session registration have
separate facts. Database observations, production catalog responses and DDN
carry explicit incomplete coverage and the affected native identities.

Native qualification creates a real virtual table through SQLite3.53's module
API, closes that owning process and inspects the valid database without the
module registered. Navigator reachability and production DDN roundtrip are
checked independently from native column refusal. Additional native cases cover
authorizer denial and damaged FTS configuration while another connection keeps
pending work and a savepoint. This does not install the missing component or
claim that the inspecting client exposes every extension-management API.

SQLite structured virtual-table creation
-----------------------------------------

The explorer now exposes native structured constructors for FTS3/4/5,
RTree/RTree_i32, Geopoly, FTS4aux, FTS5vocab, FTS3tokenize and dbstat.
Module-specific options are typed values, quoted through each native constructor
grammar. They include tokenizers, prefix indexes, FTS4 compression and language
mapping, FTS5 contentless/external-content modes and spatial auxiliary columns.
SQLite still decides installed availability and native constructor constraints.
Eponymous-only functions are not presented as creatable modules.

Independent connections own a write transaction; retained connections stage
creation inside a private savepoint and preserve caller transactions. TEMP and
attached targets require a retained session. A failed constructor or declaration
check rolls back this operation; a missing reply after native commit remains
unknown. Fresh post-state observations compare the recorded native definition
and columns. An external-content constructor does not populate or synchronize
the index. This scope does not close arbitrary extension constructors or the
remaining native maintenance/transformation workflows.

SQLite native FTS index maintenance
------------------------------------

FTS object workflows now provide reviewed native optimize, rebuild, integrity
checks, segment merge, delete-all and session flush. Native module/content modes
determine admission; FTS3/4 and FTS5 merge arguments remain distinct. The applying
transaction checks reviewed definitions/settings/file identity, preserves native
settings, runs native integrity checks and observes delete-all through an empty
native vocabulary. External content rows are retained. Session flush uses the
retained connection and keeps caller finality separate from an owned commit.

Native operation observations and cancellation use the provider's retained
operation identity. Receipts distinguish not-dispatched, rolled-back, staged,
committed and unknown outcomes. Native VM callbacks provide work observations,
not completion percentages. Timeout/cancellation restore native progress and
busy policies; a lost caller savepoint after native interruption blocks session
reuse. A lost commit reply remains unknown and never authorizes replay. These
controls cover the recorded FTS operations; they do not qualify unrelated
extension APIs or remaining schema transformations.

SQLite table-function row identifiers
---------------------------------------

Native table-function metadata now compiles the physical ``rowid``, ``_rowid_``
and ``oid`` aliases through the retained connection, with its original native
authorization. It does not run the result-producing virtual-table program or a
wrapped PRAGMA. Explicit same-named columns keep their native identity; physical
aliases are excluded from star expansion and remain available for explicit
selection. Denied observations retain the visible declared columns and mark
coverage partial. Native fixture queries qualify direct aliases, CTE projections,
explicit renaming and real relation masking separately from the parser's own
declarations. Direct result labels and CTE column names need not be identical;
the actual native CTE observations determine the completion expectation.

SQLite partial editor metadata
--------------------------------

Unavailable virtual-table modules, native metadata denial and ignored metadata
results retain healthy SQL-editor symbols with explicit incomplete coverage.
Authorized native table-list observations can supply identities when direct
schema queries are denied. Unconfirmed relation masking prevents a real table
from being relabeled as a builtin function. Empty or unavailable column results
do not authorize invented columns or row identifiers. Physical relation aliases
are checked with the native nonexecuting compiler and preserve the caller's
authorization and pending transaction. A real unloaded-module fixture qualifies
healthy completion and native checking separately from the unavailable object.

MySQL native dollar-quoted source
----------------------------------

The pinned MySQL9.7 SQL boundary now recognizes dollar-quoted routine/library
text with native numeric and Unicode tags and consumed delimiter mismatches.
Semicolons, comments, client directives and placeholder-like text inside those
literals remain body text. Script framing uses the observed native revision;
unconfirmed revisions do not inherit this admission. Existing explicit dollar
client delimiters remain separate from SQL literal delimiters.

Formatting treats each literal as one opaque token and restores its exact bytes
before comparing the complete native token sequence. Retained SQL completion
does not offer SQL keywords inside complete or incomplete opaque bodies. Native
qualification checks original and malformed source through MySQL's nonexecuting
parser in each recorded SQL mode and both connector implementations, while
pending work/savepoints and the absence of created routines/libraries are checked
independently. This scope confirms SQL boundaries and SQL grammar; external body
languages still require their own validation and installed-capability evidence.

MySQL lexical query parameters
--------------------------------

The retained editor now uses one lexical parameter inventory for checking and
query execution. Quoted placeholder text remains literal; active and inactive
native version comments retain different roles. Native connector conversion
preserves value types and SQL-mode escaping. Converted statement bytes use the
native command interface with the existing result cursor, preventing the client
script preprocessor from rewriting DELIMITER words inside parameter values.
Actual client directives have their own observed-mode-aware framing.

Local binding refusals report no user-query dispatch and preserve the retained
session and pending transaction. Cancellation is checked again after conversion.
Native qualification covers both client implementations, source/literal
boundaries, exact values, bound result batches, client-delimited programs,
native refusal, cancellation, pending savepoints and independent observations.
Parameterized execution now advances one framed native command at a time,
observing the successor's SQL mode and character sets after prior results are
consumed. Exact values survive native mode/charset changes, and a later local
refusal reports partial dispatch without replay. Undelimited compound programs
retain their native whole-command port. Future-state source preflight, wider
procedural scopes and broader native operational/product acceptance remain open.

Unbound MySQL setting-changing source
--------------------------------------

Unbound explicit SET/CALL and client-delimited source now advances through
observed native command contexts as well. Unicode source literals and identifiers
use the selected command's client charset, and native quoting uses its actual
SQL mode. Literal placeholder text remains unbound. Later source-encoding
refusals identify earlier dispatch while retaining a confirmed usable session.
Native qualification covers both connector implementations, independent pending
work, stored-procedure charset changes, client delimiters and HTTP/browser flow.
Wider computed/procedural contexts and future-state preflight retain separate
acceptance.

SQLite FTS5 table-function dependency reconstruction
---------------------------------------------------

Public content-column and coordinated table renames now preserve dependent
FTS5 function invocations, including aliases and explicit view output names.
The ordinary-relation rewrite path remains available. When that path cannot
bind the virtual function, the pinned SQLite 3.53.0 native rename helpers bind
the original empty schema in a separate safe CLI process. Only native-selected
identifier spans are replaced; independent original-identity probes compose
column/table chains without guessing names in SQL text. Unrelated CTE names,
literals and comments remain exact. Internal testing functions are never
enabled on a registered database or user connection.

The reviewed operation records executable/source identity and execution host.
Views and triggers are recreated within the owned rename transaction, then
native preparation checks every final dependency. Review reuse, stale settings,
refusals, rollback and lost commit replies retain the existing durable outcome
contract. Native utility setup includes the pinned shell on Windows/macOS;
those teams still own native platform qualification. Wider attached, derived
view, FTS4 row-identity and installed-module transforms remain open.

SQLite inferred view-column rename dependencies
-----------------------------------------------

Native table/column rename generation now follows inferred output names through
ordinary and FTS view chains. Each pass observes native projection ordinals and
labels, then uses the original empty schema's native AST to bind references in
downstream views and INSTEAD OF triggers. Star projections and expression labels
retain their native meaning; explicitly named view columns remain stable.
SQLite's lazy view-column cache is populated before requesting internal column
bindings. No identifier is inferred from SQL text.

These passes run in the independent schema probe. Reviewed stages recreate the
dependencies inside the existing owned write transaction and prepare final
views/triggers before commit. Invalid bindings, changed projection widths or
nonconvergent dependencies refuse generation. Application receipts retain
stale-review refusal, rollback and uncertain commit outcomes. Attached contexts,
FTS4 row-identity and installed-module transformations remain separate work.
Final dependency checks force fresh native EXPLAIN preparation, preventing a
cached pre-change program from accepting invalid post-change view/trigger SQL.

SQLite ordinary-content FTS row identity mappings
------------------------------------------------

Renaming a physical rowid column or introducing an alias that shadows an
implicit rowid now preserves the original document identity for ordinary FTS
content tables. The independent empty-schema probe compares native content
SELECT programs before and after the requested renames. Schema cookie and
generation counters are excluded; expression, cursor and result instructions
must agree. Candidate content expressions are accepted only when their native
program preserves the original binding, including generated columns.

FTS5 uses its native content_rowid option. FTS4 creates an explicitly named
content mapping view in the reviewed migration transaction, then reconstructs
and checks the selected index. Native settings and owner rows remain intact.
The reviewed SQL and mapping observations identify the new view. Harmless
INTEGER PRIMARY KEY alias renames require no FTS4 reconstruction. Names already
used or selected for renaming are reserved before generating mapping views.
Content-view row identity, unavailable native expressions and wider installed
module/attachment transformations retain separate acceptance.

SQLite FTS content-view projection contracts
--------------------------------------------

Renaming base-table document or text columns now preserves the named projection
contract of a retained FTS4/FTS5 content view. When native inference would rename
its output columns, generation adds an explicit original column list to that
view's admitted declaration. Its SELECT is still rewritten by the pinned native
AST binder. Star projections, nested source views, comments and quoted names
retain their native meaning. Existing index content and owner rows are not
copied or reconstructed for this view-only contract preservation.

The reviewed migration recreates views/triggers within the owned transaction
and prepares final dependencies before commit. Native maintenance triggers bind
to the renamed owner fields while the FTS view's public names remain stable.
New implicit-alias shadowing through content views, distinct document/language
bindings and wider attached/installed-module reconciliation remain separate
acceptance.
