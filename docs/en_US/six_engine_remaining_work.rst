Six-engine remaining work
*************************

Status baseline: 2026-10-18, source ``ec52d652a``.

This is the consolidated known remaining backlog for :doc:`six_engine_completion`.
Every item below is open unless marked owner-deferred or externally owned.
Completed scoped workflows and their native evidence remain recorded in the
owning engine contracts. No engine has full product acceptance, and this list
is not an overall completion percentage. Independent inventory reconciliation
must expose additional missing native capabilities as explicit backlog items.

Work order and closure rules
============================

1. Reconcile the native feature denominator for all six pinned profiles before
   selecting further implementation work. Include native source/documentation,
   actual build/edition, interfaces and installed components. Map each applicable
   feature to its catalog destination, editor coverage, operation adapter,
   complete application workflow and native receipt. Distinguish missing code,
   missing qualification, denied privilege and uninstalled components.
2. Close recovery, replication and lifecycle workflows against that inventory.
   Keep review, dispatch, native acknowledgement, partial effects, cancellation,
   unknown outcomes, restart reconciliation and independently observed effects
   separate. Never recover an uncertain mutation by replaying it.
3. Close remaining design/editor/capability cases, then reconcile all native
   evidence against the final source. Platform and human-team signoffs retain
   their separate owners. ScratchBird history testing remains deferred.

A work item closes only when the native capability is discoverable, admitted,
usable and observable in ScratchRobin, including its applicable failure and
recovery paths. A generic SQL runner, declared task count or successful build
cannot close a missing management workflow. Evidence qualifies its recorded
installation and scope; it does not automatically cover another installed
component, language mode, interface or operating system.

Independent inventory
=====================

* INV-MYSQL: Reconcile MySQL 9.7.0 core, installed plugins/components/storage
  engines and native/Shell interfaces against the full product contract.
* INV-MARIADB: Reconcile MariaDB 12.2.2 core, storage engines/plugins, normal and
  Oracle modes, native utilities and optional physical-continuity components.
* INV-POSTGRESQL: Reconcile PostgreSQL 18.3 core, server/database/session scopes,
  utilities, installed extensions/languages and SQL/replication interfaces.
* INV-DUCKDB: Reconcile DuckDB 1.5.2 core, retained/attached catalogs, installed
  extensions, types, macros/functions, native file formats and runtime options.
* INV-SQLITE: Reconcile SQLite 3.53.0 core/build flags and retained main/temp/
  attached scopes, loaded modules/functions/collations and native public APIs.
* INV-FIREBIRD: Reconcile Firebird 5.0.4 network and embedded independently,
  including native catalog, PSQL, Services API, trace/profiling, events,
  authentication and backup-chain capabilities beyond the parity checklist.

These six items reconcile the independent denominator. Existing category and
navigator gates provide evidence inputs; their own declarations do not define
that denominator.

Known implementation and qualification gaps
===========================================

MySQL
-----

* MY-CONTINUITY: Complete base-backup/log-chain recovery, selected recovery
  targets, independent restore verification and reviewed production cutover.
* MY-ARCHIVES: Complete unresolved receiver/checkpoint recovery, archive
  retention and cleanup/restart reconciliation beyond the published receiver
  restart and stopped-tail adoption workflows.
* MY-HA-LIFECYCLE: Complete independently observed topology/bootstrap/failover/
  repair and authorized server-host configuration, lifecycle and upgrades.
* MY-LANGUAGE-CAPABILITIES: Close remaining procedural/future-state editor
  checks and native operations for installed plugins/components/storage engines,
  security and maintenance features identified by INV-MYSQL.

Native spatial-reference catalog and typed management operations are implemented;
their wider server DDN integration remains open. The first native source
comparison also identifies foreign-server definitions and component-backed
masking policies as explicit adapter obligations. Masking-policy installation and its native
management privilege require separate admission. Server-variable discovery must
also be reconciled beyond the current curated selection; that selection cannot
establish catalog completeness.

MariaDB
-------

* MA-CONTINUITY: Complete native physical/incremental/PITR chains, recovery
  targets, independent restored-data verification and production cutover.
* MA-ARCHIVES: Complete unresolved receiver/checkpoint recovery, retention and
  cleanup beyond published restart and stopped-tail adoption workflows.
* MA-HA-LIFECYCLE: Complete topology/bootstrap/failover/repair, server-host
  configuration/lifecycle and upgrades using independent native members.
* MA-LANGUAGE-CAPABILITIES: Close wider procedural/Oracle-package scopes and
  installed engines/plugins, security and maintenance findings from INV-MARIADB.

Include native backup stages/locks and their connection lifetime in continuity
reconciliation. Asynchronous replication-channel controls do not establish the
Galera topology/bootstrap/repair workflows for installations that provide them.

PostgreSQL
----------

* PG-RESTORE: Complete production restore/cutover and acceptance beyond the
  implemented independent native recovery drills and recovery targets.
* PG-ARCHIVES: Complete retention, interrupted-stream restart and log/archive
  management beyond the qualified physical WAL and logical receiver captures.
* PG-TEMP-PROTOCOL: Implement retained temporary replication-protocol resources
  and streams. Existing independently retained SQL temporary-slot controls and
  SQL text/binary peek/get are implemented; the permanent-slot native receiver
  does not own another backend's temporary slot.
* PG-REPLICATION-ADMISSION: Support applicable replication-only registrations
  without requiring SQL admission and preserve the exact native principal.
* PG-HA-LIFECYCLE: Complete standby synchronization, topology/bootstrap,
  promotion/failover/repair, remote-host lifecycle/configuration and upgrades.
* PG-LANGUAGE-CAPABILITIES: Close installed procedural-language/extension and
  other native security/maintenance findings. Arbitrarily encoded catalog
  identities remain separate from the qualified lossless SQL_ASCII payloads.

DuckDB
------

* DU-DESIGN: Close remaining native schema/dependency transformations and their
  complete DDN generation, reviewed application and postcondition workflows.
* DU-EDITOR: Close computed/contextual member and projection binding cases,
  preserving exact nested types, names and native positioned diagnostics.
* DU-CAPABILITIES: Close native installed-extension, file-format, storage,
  configuration and lifecycle findings from INV-DUCKDB.

Native object-comment editing is implemented for the pinned engine's supported
families; see :doc:`duckdb_driver_development`. This does not close attachment
mutation, extension-update, copy-database or broader installed-capability
reconciliation. Database/schema comment syntax that the native runtime rejects
as unimplemented must not be presented as a supported management operation.

SQLite
------

* SQ-TRANSIENT-DESIGN: Generate and apply native DDN migrations on the original
  authorized temporary/attached/uncommitted schema. Retained catalog capture
  and native changegroup schema bases are already implemented. An independent
  registered-file migration must continue refusing retained-session provenance.
* SQ-DEPENDENCIES: Close remaining attached/content-view alias-shadowing and
  language-identity cases with preserved native FTS/document/row identities.
* SQ-MODULES: Close remaining installed-module transformations and native
  extension/function/collation/build-specific findings from INV-SQLITE.

Firebird network and embedded
-----------------------------

* FB-NATIVE: Implement and qualify findings from INV-FIREBIRD independently for
  network and embedded modes. Preserve completed native administration, DDN,
  data, diagnostics, collector/dashboard and desktop/lifecycle workflows.
* FB-EVIDENCE: Reconcile the expanded native capability evidence with current
  source. Existing FlameRobin parity/driver receipts retain their own scope.

Shared acceptance
=================

* ALL-EVIDENCE: Reconcile current-source catalog, editor and complete operational
  workflow receipts for the expanded native inventories. Record exact source,
  refreshed paired DDN artifacts, engine/tool identities and platform scope.
* HISTORY-QUALIFICATION: Owner-deferred. ScratchBird drivers and history
  integrations remain wired. Do not run history tests or start/build ScratchBird
  for history acceptance until the owner resumes qualification.
* HUMAN-FORMS: Externally owned by the human form-validation team.
* NATIVE-PLATFORMS: Externally owned by the Windows/macOS platform teams.
  Their evidence is required for a cross-platform completion claim.
