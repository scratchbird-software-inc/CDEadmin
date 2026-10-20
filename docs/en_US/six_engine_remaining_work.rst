Six-engine remaining work
*************************

Status baseline: 2026-10-18, source ``ec52d652a``.

This is the consolidated known remaining backlog for :doc:`six_engine_completion`.
Every item below is open unless marked owner-deferred or externally owned.
Completed scoped workflows and their native evidence remain recorded in the
owning engine contracts. No engine has full product acceptance, and this list
is not an overall completion percentage. Independent inventory reconciliation
must expose additional missing native capabilities as explicit backlog items.

Owner scope correction, 2026-10-20: the beta denominator includes open source
and source available engine versions. Closed source Enterprise functionality is
post beta, with its dependency and reason recorded below. Source interfaces or
accepted syntax do not prove an available implementation. Missing adapters for
available native implementations remain beta gaps.

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

Native spatial-reference catalog, typed management and bounded selected-SRID
server DDN exchange/migration are implemented. Captured SRID scope is explicit;
large catalogs use separate selected batches under the existing byte bounds.
Full native column facts and reviewed column policy assignment/removal are
implemented and tested against community MySQL's native reference handling.
Those receipts do not qualify working masking. Global policy installation,
definition management and functioning masking depend on the closed source
Enterprise component and are deferred as ``MY-POST-BETA-MASKING`` below.
Foreign-server catalog, typed native
management and credential-free server DDN migration generation/application are
implemented. Server capture now includes every visible global variable and its native
provenance. Persisted-only settings for unloaded components now retain their
native identities and presence in navigation and server DDN, with withheld
values and verified exact-name RESET PERSIST. Arbitrary installed components'
runtime sensitivity classification and wider capability reconciliation remain
open.

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

Native BACKUP STAGE and table BACKUP LOCK/UNLOCK now have original-session
reviewed controls, native execution/cancellation and separate acknowledgement
receipts. Active transactions are refused before their native implicit commits;
backup connections are physically discarded on close even with pool reset
disabled. Physical file copying, verification and recovery-chain orchestration
remain separate continuity gaps. Asynchronous replication-channel controls do not establish the
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

Physical backup, WAL capture and known-name slot commands now offer explicit replication-only admission from the
saved registration without borrowing or opening a SQL session. Native
IDENTIFY_SYSTEM and SHOW bind the cluster, principal and WAL geometry; dispatch
reauthenticates the reviewed peer. Credentials are withheld from durable jobs.
Full and incremental backups stream native TAR files into private storage;
requested plain output is materialized and verified independently. Native
tablespace maps supply exact OIDs and source paths without opening those paths
or claiming SQL catalog names. Verified artifacts support reconstruction and
isolated recovery while the SQL registration remains disconnected. Native backup
acknowledgement, TAR/flat-file verification and recovery remain separate facts.
SQL role substitution is refused. Replication-only SSH now uses inspected or
operator-supplied public host keys, independent pinned worker tunnels and native
password/private-key authentication, including saved credentials. Remaining
temporary/logical protocol resources still require separate admission/workflow closure.
Permanent physical-slot creation and known-name physical/logical-slot removal
use the native utility without opening the SQL slot catalog. Prior existence,
type and current identity remain unobserved. Native utility acknowledgement is
saved before SSH release, separately from process cleanup and later catalog facts.

DuckDB
------

* DU-DESIGN: Close remaining native schema/dependency transformations and their
  complete DDN generation, reviewed application and postcondition workflows.
* DU-EDITOR: Close computed/contextual member and projection binding cases,
  preserving exact nested types, names and native positioned diagnostics.
* DU-CAPABILITIES: Close native installed-extension, file-format, storage,
  configuration and lifecycle findings from INV-DUCKDB.

Native object-comment editing is implemented for the pinned engine's supported
families; see :doc:`duckdb_driver_development`. Full native extension facts and
reviewed individual/all extension-file updates are also implemented. This does
not close remote attachment options or broader installed-capability
reconciliation. Original-session typed extension installation/loading includes
local signed files, credential-free installation URLs, repository/directory selection, versions and FORCE;
its read-only receipts now survive closing the original native instance and
application restart, without permitting replay or inferring commit. Standard
native file attachment mutation now has a reviewed original-session workflow,
including file creation, conflict modes and native rollback distinctions.
Database/schema comment syntax that the native runtime rejects
as unimplemented must not be presented as a supported management operation.
Reviewed attachments also expose native block/row-group sizes, storage version
and authorized in-memory compression, with observed storage facts and caller
transaction ownership. Native encrypted-file attachment uses privately bound,
expiring keys, explicit discard, observed encryption/cipher facts and existing
file-header semantics. Native database copy now has an original-session typed
review/apply workflow for schema, data and schema-and-data, background phase
receipts, cancellation, native partial/unknown outcomes and verified native
catalog/row aggregates. Independent qualification additionally checks exact
native data and committed file reopening. Attachment, extension and copy receipts
have owner/endpoint/target-scoped durable storage, separate native release
observations and read-only inspection without native admission. Extension-backed
foreign catalog copies, remote attachments and broader storage transformations
remain open. Native encrypt/decrypt/key-change-by-copy uses separately attached
stores, reviewed native encryption/cipher facts, caller-owned commit/rollback,
post-copy storage observations and independent correct/wrong-key file reopening.
The pinned implementation has no in-place SQL REKEY operation; do not invent one
or count it as an unmet native capability. Source replacement/cutover is not
implied by successful copy acknowledgement.
Native HTTP-secret source admission now records exact native selection and
effective version/platform URL, with secret-read authority and revalidation
before dispatch. Credentials stay inside DuckDB. Scope-specific HTTPS repository
qualification does not establish functioning direct HTTPS INSTALL on the pinned
build: ``DU-NATIVE-HTTPS-DIRECT`` records the independently reproduced native
local-filesystem refusal. HTTPFS's native HTTP-repository-to-HTTPS transport is
qualified separately. Wider secret-property, remote attachment and installed
capability reconciliation remains open.

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

Post beta: closed source Enterprise functionality
=================================================

MY-POST-BETA-MASKING: MySQL dynamic masking policies
---------------------------------------------------

* Status: owner-deferred to post beta; excluded from beta completion blockers.
* Native dependency: MySQL Enterprise ``object_policy`` component, its policy
  storage and ``column_masking_policy_management`` /
  ``column_masking_policy_retrieval`` service implementations.
* Source evidence: the pinned MySQL 9.7.0 community tree provides
  ``sql/sql_masking_policy.cc`` and
  ``include/mysql/components/services/object_policy_service.h`` for the core SQL
  hooks and service contracts. It contains no implementation of the required
  component. Its ``mysql-test/t/masking_policy.test`` explicitly expects
  component-unavailable errors for policy creation, deletion and lookup.
  Oracle documents the dependency in the `MySQL 9.7 Enterprise masking guide
  <https://dev.mysql.com/doc/refman/9.7/en/data-masking-dynamic-policies.html>`_.
* Reason: the required closed source Enterprise implementation is unavailable
  in the acquired source and falls outside the owner's beta edition scope.
  Parser acceptance and successful column-reference assignment/removal cannot
  establish working policy management or masked/unmasked query results.
* Deferred work: component installation/lifecycle, policy catalog and definition
  management, complete application workflows and positive native masking tests
  with real users/roles and independently observed results on a supported
  Enterprise installation after beta. Do not fabricate a replacement component
  or claim execution success from mocked services.

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
