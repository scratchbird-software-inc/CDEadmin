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
  Native EDS process-pool catalog facts and retained editor controls are now
  implemented; their owning workflow and qualification command are recorded in
  :doc:`firebird_functional_completion`. This closes that adapter gap only;
  the broader independent Firebird inventory remains open.

These six items reconcile the independent denominator. Existing category and
navigator gates provide evidence inputs; their own declarations do not define
that denominator.

Known implementation and qualification gaps
===========================================

MySQL
-----

* MY-CONTINUITY: Complete base-backup/log-chain recovery, selected recovery
  targets, physical/log recovery acceptance and reviewed production cutover.
  Separate logical-dump data acceptance now integrates native Shell checksums,
  independent full row counts and table inventories under an explicitly
  confirmed server read lock. It requires complete checksum coverage and stable
  artifact/native identities. It does not establish physical recovery, object
  definition equality, later log replay or production cutover.
* MY-ARCHIVES: Complete backup/log-dependency-aware archive protection and
  retention. Separate native source-log administration now exposes reviewed TO
  and BEFORE purges, independent observations, durable acknowledgement and
  explicit unknown-outcome reconciliation; it does not discover backup or
  offline-replica dependencies or attest log-generation epochs.
  A separate reviewed native binary-log/GTID reset now retains strict observed
  state binding, independent connections, native refusals and durable unknown
  outcomes. It requires an exclusive maintenance window and does not rebind old
  archive chains to reused native filenames or establish recovery coverage.
  Managed graphical dump intents now acquire durable application archive holds
  before dispatch, with conservative source protection, offline inspection and
  reviewed retirement. Missing replies retain protection. These scoped holds do
  not calculate native recovery-chain edges or discover external/other-registration
  backups, offline replicas or native log-generation epochs.
  Managed physical clones now acquire durable holds before dispatch, including
  conservative donor and recipient registration holds for remote clones whose
  native protocol does not attest a source UUID. Returned SQL acknowledgements
  remain separate from later observer/bookkeeping failures. These holds support
  explicit inspection/retirement and leave physical clone files intact; they do
  not close the remaining recovery-chain dependency calculation.
  Scheduled age/count policies for exact native source/principal/role
  are implemented with independent occurrence receipts, expiry, revocation,
  restart and unresolved-outcome suspension. They preserve explicit pins and
  do not discover base-backup dependencies or prove recoverability. Interrupted
  private-input cleanup now has explicit offline reconciliation of its single
  recorded pending removal; original lost acknowledgements remain visible and
  unattempted files require a new review. Recovery from independently sealed receiver archive
  checkpoints after the original native file is purged is implemented and
  native/API/browser qualified, including native shutdown boundaries without
  rotation events and checksum NONE. Explicit full recollection from an unresolved receiver's
  available original log is implemented, with stopped-writer admission, native
  source/GTID checks, a new receipt and no use of the uncertain cursor. Reviewed
  Shell/raw archive retention,
  explicit archive protection and durable interrupted-removal reconciliation
  are implemented and native/API/browser qualified. Age/count policies retain
  exact reviewed files and receipts; they do not infer backup/log recovery
  coverage or purge native server logs. Backup/log-chain-aware retention remains
  separate from the qualified age/count policies and operator-reviewed workflow.
* MY-HA-LIFECYCLE: Complete independently observed topology/bootstrap/failover/
  repair and authorized server-host configuration, lifecycle and upgrades.
  Pinned SSH host diagnostics now bind the actual MySQL host/data-directory UUID
  and expose reviewed native configuration validation with durable remote
  receipts. Complete included-configuration attestation, server initialize/start/
  stop/service control, upgrades and physical recovery remain separate work.
* MY-LANGUAGE-CAPABILITIES: Close remaining procedural/future-state editor
  checks and native operations for installed plugins/components/storage engines,
  security and maintenance features identified by INV-MYSQL.
  The versioned native server grammar library now checks UTF-8 editor text in
  an isolated process using the source-observed SQL mode, including compound
  procedures and names that do not yet exist. It performs no SQL execution or
  catalog/privilege binding, and separates optimizer-hint warnings from syntax
  errors. Script previews now follow deterministic mode declarations using native
  canonicalization on the private observer; retained execution rechecks each
  statement's expected mode and stops on drift. Runtime-dependent future context
  remains unconfirmed without executing submitted SQL. Remaining installed
  capability reconciliation and catalog/privilege semantics require their work.
  Native MyISAM index-cache assignment and preloading now have typed reviewed
  workflows, exact source/table/index rechecks and explicit native result-row
  outcomes. These additions do not close the wider installed feature inventory.
  Named-cache inspection, all four runtime settings and DEFAULT, and native
  buffer release are also implemented with exact decimal observations, native
  rounding/warnings, changed-state refusal and default-cache protection. Native
  MySQL has no SHOW GLOBAL VARIABLES enumeration of named prefixes; that absence
  is explicit, and all-zero observations do not assert native cache existence.
  Native per-query attributes now have editor inputs, scoped native execution,
  retained private script policies and installed runtime-UDF completion. The
  pure connector corrects NULL metadata and negative TIME framing. Connector26.7
  C still needs native fixes for TIME durations, unsigned attributes above
  signed 64-bit range and names whose current source bytes differ from UTF-8;
  these cases refuse dispatch rather than silently changing values or names.
  These are beta driver gaps, separate from closed-source Enterprise scope.
  All six Community ALTER INSTANCE actions now have reviewed owned-connection
  workflows, native key rotation and redo-state receipts, TLS main/admin and
  rollback options, changed-state refusal and explicit native ACK handling.
  Host lifecycle, file/configuration deployment and remaining installed native
  capabilities continue under their separate inventory and lifecycle work.
* MY-DIAGNOSTICS: Audit and complete diagnostic preservation for other retained
  editor/completion/catalog consumers and denied/disabled observer
  profiles. Admitted Performance Schema profiles now use a separately
  authenticated retained observer for current native language/charset facts in
  parameter binding, script framing and C charset adaptation. Identity discovery,
  cursor creation, decoded-error cleanup, empty script tails and automatic
  transaction observation also preserve diagnostic state in their qualified
  execution scope. Permission/connection loss refuses affected commands without
  intrusive fallback; authenticated observer renewal does not reconnect the
  original session or replay user SQL. Native C escape-mode acknowledgement
  mismatches now borrow the private peer's stock C converter with independently
  observed settings and verified private acknowledgement; unconfirmed private
  context still refuses dispatch. Admitted native syntax checks now prepare on the private
  same-instance peer using observed source mode/database context and preserve
  source diagnostic state. This includes live database switches and denied
  private parser context; original active-role/temporary-object binding remains
  unqualified. Committed-catalog completion now uses that private peer with
  source-observed database, mode and charset, preserving original diagnostic
  areas and pending work. It marks source role/temporary-object overlays
  incomplete and never substitutes an original read after private failure.
  Unadmitted profiles and wider retained catalog consumers remain open.
  See :doc:`mysql_driver_development` for the execution scope;
  these execution receipts do not close browser coverage or INV-MYSQL.

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
* PG-TEMP-PROTOCOL: Complete cross-registration and ordinary-SQL-principal
  exported-snapshot consumers, destination orchestration/cutover beyond selected
  native initial relation copies, and installed output-plugin qualification. Retained
  original-backend logical streaming and temporary physical/logical creation,
  export/no-export snapshot ownership and safe owned-slot removal now have a
  separate reviewed replication-only resource. Existing SQL temporary-slot
  controls and text/binary peek/get remain separate. A permanent-slot receiver
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
cross-registration and ordinary-SQL-principal snapshot-consumer workflows still
require separate admission/workflow closure.
Permanent physical-slot creation and known-name physical/logical-slot removal
use the native utility without opening the SQL slot catalog. Prior existence,
type and current identity remain unobserved. Native utility acknowledgement is
saved before SSH release, separately from process cleanup and later catalog facts.
Known-name logical stream capture also supports the registered database through
native logical replication without SQL admission. Native IDENTIFY_SYSTEM binds
the exact database and principal; the worker reauthenticates before dispatch.
The SQL slot catalog, plugin, temporary status, active consumer and flush
checkpoint remain unobserved. The native receiver governs refusal and feedback;
its returned result and independently sealed payload bytes are separate facts.
This path does not detect concurrent slot replacement/consumption or own another
backend's temporary slot. The SQL-admitted path retains its stronger native
catalog and checkpoint checks.

Permanent logical slot creation now also has a registered replication-only
workflow for native plugin, two-phase, failover and if-not-exists options.
Utility acknowledgement remains separate from catalog state and prior existence.
The native utility suppresses snapshot export. A separate retained native
replication resource now owns temporary slots and exported snapshots without
ordinary SQL admission. Status, review and acknowledgement pages do not send
commands that would invalidate the export. Another command requires explicit
invalidation confirmation. The original native database, backend and complete
provider isolation scope bind command admission. Historical creation cannot
authorize a drop after the name was released and reused elsewhere. Native error
ends this owner; acknowledgements and later local close remain separate from
unobserved catalog/health facts and no command automatically replays. This
resource also supports native logical COPY BOTH capture on its original backend,
reviewed bounds and optional fsynced-only flush feedback, exact frame delivery,
inspection and removal. Native completion, artifact publication and unknown
outcomes remain separate, with no automatic replay. Owned SNAPSHOT USE now starts
a native read-only repeatable-read transaction, creates its slot as the first
command, and supports explicit cancellable relation discovery/inspection and
typed binary/text/CSV COPY on that original backend. Declared domain identities
and their actual wire type/modifier remain separate. Native locks, current OID,
column facts, SELECT permission and RLS bind the selected output. Materialized
and foreign relations retain their native locking/snapshot rules. Native BEGIN,
slot creation, COPY return, byte publication and transaction end have separate
outcomes. Explicit commit/rollback retains session slots under native rules for
later streaming; failed/uncertain commands end this owner. Exact private delivery,
offline inspection and confirmed removal never replay a capture or promote an
unknown operation. Independent application consumers now import a server-derived
export on a separate same-registration native replication connection and
transport. Native exporter identity is checked before and after import; BEGIN,
import and verification retain separate acknowledgements. The imported read-only
transaction can discover, inspect and copy selected relations after exporter
release without acquiring its slot. Cross-registration and ordinary-SQL-principal
consumers, destination orchestration/cutover, installed plugin acceptance and the
independent PostgreSQL inventory remain open.

DuckDB
------

* DU-DESIGN: Close remaining native schema/dependency transformations and their
  complete DDN generation, reviewed application and postcondition workflows.
* DU-EDITOR: Close computed/contextual member and projection binding cases,
  preserving exact nested types, names and native positioned diagnostics.
  Observed unshadowed core aggregate result shapes now preserve exact members,
  container access, grouped FILTER/OVER results, DISTINCT/ALL arguments and
  explicit CTE/derived aliases. Wider computed arguments, function families,
  overloads and ordered aggregate arguments remain open; the native
  qualification scope is recorded in :doc:`duckdb_driver_development`.
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
qualified separately. Secret constants now retain native scalars, scope lists and
header maps, with private previews and a system-qualified map constructor.
Borrowed query connections retain caller transaction decisions on administration
refusal. Original-session secret management now distinguishes same-name storage
identities, observes exact DROP targets, supports native persistence/conflict
modes and default naming, and separately parses explicit private property
expressions without executing them during review. Native persistent file effects
can survive rollback and remain separate from current catalog state. Remote
attachment and installed-capability reconciliation remain open; this scoped
secret workflow does not establish independent INV-DUCKDB completeness.

SQLite
------

* SQ-TRANSIENT-DESIGN: Generate and apply native DDN migrations on the original
  authorized temporary/attached/uncommitted schema. Original-connection native
  creation/removal, view/index/trigger replacement and structured column append
  now have a separate reviewed workflow and durable receipts. Remaining
  preservation/rebuild transformations, qualified module
  transformations and large/partial-scope cases keep this item open. An
  independent file migration must continue refusing retained-session provenance.
  Native ordinary-table and column renames, column removal, named constraint
  removal, NOT NULL changes and CHECK additions now also have property-driven
  original-session DDN generation and reviewed native application. Native
  dependency rewriting and existing-data refusal retain the original caller
  transaction. External-content FTS identity/projection transformations still
  require their preservation adapter; native pinned-runtime refusals for quoted
  constraint lookup and TEMP-shadowed trigger renames remain explicit.
* SQ-DEPENDENCIES: Close remaining attached/content-view alias-shadowing and
  language-identity cases with preserved native FTS/document/row identities.
* SQ-MODULES: Close remaining installed-module transformations and native
  extension/function/collation/build-specific findings from INV-SQLITE.

TEMP triggers now retain an identity in their native TEMP namespace, independent
of a same-named table in another schema. Native nonexecuting declaration prepare
can identify a qualified owner in main, TEMP or an attached database, while
preserving the original connection's authorization policy. The owning relation
and navigator destination retain that observed database. An unqualified owner
with multiple visible candidates remains explicitly unavailable; a same-named
TEMP table never supplies an invented parent. This is declaration binding, not
proof that the existing trigger ran, and does not close retained DDN application.
Retained Data Studio operations also require the original complete provider
scope, including the selected registration target. A different target pointing
to the same file cannot inspect, execute, roll back or close that session.

Native catalog declaration generation now binds stored identifier
spellings to exact namespaces and owners without rewriting SQL bodies. The
independent registered-file path can consume those declarations. The separate
original-session workflow now preserves its caller transaction and exact
namespace/authorization scope for its admitted native stages; broader retained
transformations remain open.

Catalog-derived native main-file column additions now generate their own
reviewed stages, preserving untyped/generated columns and dependencies. Native
write-time checks distinguish empty and populated table capabilities; refusal
rolls back earlier stages and is retained without replay. This closes that
specific declaration-generation gap. It does not close original-session DDN
application, broader module transformations or the independent SQLite inventory.
Structured column-property controls now generate those DDN additions without
requiring hand-written CREATE/ALTER commands. Installed custom module/function/
collation preview adapters remain part of SQ-MODULES; unsupported reproduction
is explicit and does not suppress the native capability from the denominator.

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

MY-POST-BETA-MLE: MySQL JavaScript execution and language validation
------------------------------------------------------------------

* Status: owner-deferred to post beta under the beta edition/source rule.
* Native dependency: Enterprise ``file://component_mle`` and the implementations
  of ``external_program_execution``, ``external_library`` and
  ``external_library_ext``. Oracle identifies MLE as an Enterprise component in
  its `MySQL 9.7 MLE documentation
  <https://dev.mysql.com/doc/refman/9.7/en/mle-component.html>`_.
* Source evidence: the pinned community source contains the contracts in
  ``include/mysql/components/services/language_service.h`` and the consumers in
  ``sql/sp_head.cc`` and ``sql/sql_cmd_ddl.cc``. The acquired ``components`` and
  ``plugin`` implementation trees contain no provider of those services.
  ``sp_head::init_external_routine`` reports an unavailable language component
  when its execution service is absent.
* Reason: the JavaScript parser/runtime implementation is unavailable in the
  acquired source and is outside beta scope. Core SQL grammar acceptance,
  opaque-body framing, library catalog preservation and successful declaration
  management cannot establish JavaScript validity or functioning imports,
  execution or MLE runtime diagnostics and metrics.
* Beta scope retained: native community library catalog, CREATE, comment-only
  ALTER, DROP, exact text/binary DDN exchange, SQL framing/formatting and existing
  nonexecuting MySQL grammar checks. In this pinned source, library creation
  warns when its external-library services are absent and still stores the
  declaration; this does not prove the missing services work. Preserve those
  native warnings and distinguish a later engine build's behavior.
* Deferred work: MLE installation/lifecycle, JavaScript and imported-library
  validation/execution, language completion, native diagnostics and MLE metrics,
  with positive native Enterprise tests after beta. Do not supply an application
  JavaScript runtime as a replacement. Open source SQL stored routines and
  loadable-function implementations remain in the beta denominator.

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
