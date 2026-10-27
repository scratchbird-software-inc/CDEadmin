MySQL implementation priorities and MariaDB handoff
===================================================

Accepted by the owner: 2026-10-22.
Comparison baseline: source ``0c14f90a21c80c32074c574e7914e56dc487661d``;
MySQL 9.7.0 and Connector/Python 26.7.0.

This is the accepted implementation queue arising from the MySQL management-tool
comparison. All eleven accepted comparison workflows are implemented and Linux-qualified.
The independent native inventory remains a separate handoff gate. They supplement
:doc:`mysql_functional_completion` and :doc:`six_engine_remaining_work`; their
acceptance must follow :doc:`six_engine_completion`.

Completion scope and sequencing
-------------------------------

Finish the existing MySQL beta backlog and these eleven workflows, then stop
MySQL feature development and switch the active implementation focus to MariaDB.
The accepted spatial, deployment-automation and notebook items remain required
for this handoff even though they follow operational work in priority.

* **P0:** recovery/recoverability and production HA/Router/host lifecycle are
  Linux-qualified. Reconcile ``INV-MYSQL`` and the current
  continuity, archive, language/capability and diagnostic gaps against that work.
* **P1:** implement graphical native plans, workload analysis and database-wide
  content search, followed by controlled online DDL, replica drift verification
  and MySQL alerting. Graphical plans are the first bounded comparison feature.
* **P2:** spatial inspection, then versioned schema deployment automation.
* **P3:** SQL notebooks and shareable investigations. P3 sets the order; this
  accepted workflow is not deferred beyond the handoff.

``CMP-MY-01`` and ``CMP-MY-02`` overlap existing recovery/lifecycle requirements.
Each is one scope with linked acceptance, not another denominator for reporting
completion. Existing implementations remain credited. New competitive research
must not automatically add optional features to this queue. Applicable native
beta gaps discovered by the required inventory remain tracked under their owning
product requirements.

.. list-table:: Accepted queue
   :header-rows: 1
   :widths: 17 9 42 32

   * - ID
     - Priority
     - Workflow
     - Existing ownership
   * - ``CMP-MY-01``
     - P0
     - Complete recovery and recoverability
     - ``MY-CONTINUITY``, ``MY-ARCHIVES``
   * - ``CMP-MY-02``
     - P0
     - Complete production topology, Router and host lifecycle
     - ``MY-HA-LIFECYCLE``
   * - ``CMP-MY-04``
     - P1
     - Graphical native MySQL execution plans
     - ``MY-LANGUAGE-CAPABILITIES``
   * - ``CMP-MY-03``
     - P1
     - Workload performance analysis
     - ``MY-LANGUAGE-CAPABILITIES``, ``MY-DIAGNOSTICS``
   * - ``CMP-MY-07``
     - P1
     - Database-wide content search
     - ``MY-LANGUAGE-CAPABILITIES``
   * - ``CMP-MY-05``
     - P1
     - Controlled online schema change
     - ``MY-LANGUAGE-CAPABILITIES``, ``MY-HA-LIFECYCLE``
   * - ``CMP-MY-06``
     - P1
     - Replica and full-table data drift verification
     - ``MY-CONTINUITY``, ``MY-HA-LIFECYCLE``
   * - ``CMP-MY-08``
     - P1
     - MySQL alert policies and actionable monitoring findings
     - ``MY-DIAGNOSTICS``
   * - ``CMP-MY-09``
     - P2
     - Spatial data inspection
     - ``MY-LANGUAGE-CAPABILITIES``
   * - ``CMP-MY-10``
     - P2
     - Versioned schema deployment automation
     - ``MY-LANGUAGE-CAPABILITIES``
   * - ``CMP-MY-11``
     - P3
     - SQL notebooks and shareable investigations
     - Accepted application workflow

Workflow acceptance
-------------------

Each item needs the complete application workflow, applicable native failure and
interruption/recovery handling, and current native/UI evidence. An adapter,
command template or successful build alone does not close it. Qualification
records the engine and utility versions, execution host, privileges and platform.
MySQL and MariaDB are qualified separately.

CMP-MY-01: Complete recovery and recoverability
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P0**.

Qualify an admitted MySQL 9.7 physical backup backend; prepare and restore to
an isolated target; apply selected log recovery targets; independently compare
full data and native definitions after replay; complete dependency-aware
retention, interruption recovery and reviewed cutover. Add reviewed recurring
backup/drill scheduling after outcomes and dependencies are reliable.

The :doc:`mysql_physical_backups` workflow admits source-available XtraBackup
9.7.1-rc1 at revision ``b1c9c34183de95316d8889ea3d4cb31e31ffddc5`` with
explicit release-candidate consent. Its qualified native reader extends system,
undo and raw-file admission. Full/incremental capture, immutable redo-only and
final preparation, private copy-back, managed read-only or replay recovery,
process-bound editor connections, native selected log replay and independent
expected-checkpoint acceptance are implemented. TLS, native GPL file-keyring
rotation/retention, encrypted logs/data, external tablespaces, relative/circular
paths, raw system files and the admitted Community storage engines retain their
native identities. MEMORY row loss on native restart is disclosed.

Individual, age/count and recurring retention protect exact backup/log-chain
inputs. Reviewed recurring backups, startup drills and expected-checkpoint
checks use expiring encrypted delegation, independent occurrences and explicit
interruption release. Original utility/runtime/guardian outcomes, file adoption,
server-lock cleanup and unknown acknowledgements remain separate. Untracked old
processes without original identity retain conservative protection.

A stopped recovered instance can now be copied into a self-contained permanent
read-only systemd service with its UUID, final data, binary logs, private
keyring/TLS files and external namespace. Normal registration and reviewed host
controls support inspection/restart. Background activation requires matched
native data/definition acceptance, explicit scope acknowledgement, an inactive
and disabled original source service, and independent absence of any process
holding the original source dictionary. It repeats native acceptance under
locks, commits a one-time startup policy and sets native writable/event flags.
Cancellation ends before the policy claim. Missing replies remain unknown and
never repeat activation; independent observation and a separate reviewed restart
expose the committed policy.

Native qualification covers both connectors, actual manually started source
refusal, data/account/25 selected public system-table comparisons, encrypted
external-table recovery, restart durability and lost-policy replies. The built
desktop exercises the same review/confirmation and observation workflow.
``tools/cdeadmin_mysql_recovered_deployment_qualification.py`` supplements the
existing physical replay/retention/schedule qualifiers. These accepted workflow
receipts do not certify every optional installation or close ``INV-MYSQL``.
Windows/macOS qualification remains platform-owned; ScratchBird history testing
remains owner-deferred.

Comparison evidence: `XtraBackup MySQL 9.7 support and limitations <https://docs.percona.com/percona-xtrabackup/9.7/>`_;
`XtraBackup 9.7.1-rc1 release status <https://docs.percona.com/percona-xtrabackup/9.7/release-notes/9.7.1-rc1.html>`_;
`XtraBackup implementation at admitted revision <https://github.com/percona/percona-xtrabackup/blob/b1c9c34183de95316d8889ea3d4cb31e31ffddc5/storage/innobase/xtrabackup/src/xtrabackup.cc>`_.

CMP-MY-02: Complete production topology, Router and host lifecycle
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P0**.

Complete bootstrap/outage/failover/repair with independent unreachable-member,
replication and application-traffic evidence; complete native upgrades.
The :doc:`mysql_router_hosts` workspace now bootstraps native Community Router
on an independent Linux SSH host, installs a new systemd unit and separately
controls start/stop/restart and boot enablement. Original guardian receipts,
unknown acknowledgements and later native observations remain separate.
Three-member Cluster qualification covers TLS-routed exact data, actual primary
crash, native election, pending rollback, committed-data preservation, secondary
routing, SQL-independent Router controls and member rejoin. Live Cluster Router
metadata listing, selected option set/reset, stale-review refusal and removal
now have independent native acceptance, including the read/write-split route.
ReplicaSet and ClusterSet now also have native Linux failure/repair and live
Router acceptance. Their separately bootstrapped Routers carry TLS application
traffic before and after actual primary-server loss, native forced promotion,
original-primary rejoin and planned switchover. Independent observations cover
exact committed data, pending rollback and new-write catch-up on every target.
Native Router listing, selected option inspection/set/reset and independent
metadata comparisons cover each family. Native method replies retain their
separate meaning; these receipts do not establish every possible deployment.
Cluster complete-outage qualification now crashes all three servers, recovers
two with explicit native force while the third remains unreachable, and
incrementally rejoins the restarted third member. Independent native checks
cover committed exact data, pending rollback and new-write replication after
repair. Original topology guardian loss also retains the original process
identity for separate surviving server-work checks; acknowledgement waits for
positive member idleness and preserves unknown outcomes.
Reviewed Linux service upgrades now validate an installed 9.7 candidate, display
and recheck native Shell preflight, stop the bound original process, and select
native AUTO upgrade through a reviewed unit drop-in. Older sources use explicit
SSH/process/filesystem authority before normal 9.7 SQL admission. Native 8.4.8
upgrade, exact data preservation and original-dispatcher loss/recovery have
separate acceptance; manager replies, current processes, upgrade history and
SQL/data checks retain distinct meanings. Native three-member Cluster rolling
qualification also covers genuine 8.4 Shell metadata migration from 2.2 to 2.4,
secondary-first 8.4.8-to-9.7 upgrades, election when the old primary stops, and
reviewed promotion after every member runs 9.7. Original UUIDs, exact data and
fresh-write replication are checked independently after each step. Mixed-version
primary selection follows the native version restriction. Certificate-login and explicit owned-primary execution from a secondary seed
now have native acceptance for administrator and Router accounts on Cluster,
ClusterSet and ReplicaSet, through both connectors. Independent TLS login
succeeds with the selected native certificate and refuses password-only login.
The broader inventory remains independently tracked.
Native Linux service installation now creates
a reviewed systemd unit with separate start and boot controls. Native Linux initialization
now supports new registrations before SQL is available, with secure/insecure
native bootstrap, original-writer controls and separate outcome observations. Reviewed
native Linux option-file deployment now validates the proposed original-filename
view, binds old/new include graphs and atomically preserves file ownership and
permissions without a service restart; see :doc:`mysql_functional_completion`. Preserve existing sandbox and administrator account
workflows. Certificate-login and explicit primary-registration routing retain
separate native receipts from the earlier host and Router scenarios.

Comparison evidence: `Native MySQL Shell InnoDB Cluster administration <https://dev.mysql.com/doc/mysql-shell/26.7/en/mysql-innodb-cluster.html>`_.

CMP-MY-04: Graphical native MySQL execution plans
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P1**.

Native pure/C workspace and built desktop acceptance is recorded under
``Graphical native query plans`` in :doc:`mysql_functional_completion`.
Windows/macOS acceptance remains with platform teams.

Render admitted MySQL JSON/TREE/analyze plans as native operator graphs,
including estimates and actual measurements when present. Keep exact native
values and original output accessible; show estimate/actual distinctions; never
invent costs or reinterpret failure as successful completion. Actual execution
requires explicit user action. Reuse existing native plan commands and
presentation infrastructure.

Comparison evidence: `Current Workbench generation and shipped features <https://blogs.oracle.com/mysql/introducing-mysql-workbench-26>`_;
`Workbench open source repository <https://github.com/mysql/mysql-shell-plugins/tree/7332e92a5fb3f1422c3b083f339cd03c8788e876>`_.

CMP-MY-03: Workload performance analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P1**.

Native pure/C workspace and built desktop acceptance is recorded under
``Native workload performance analysis`` in :doc:`mysql_functional_completion`.
Windows/macOS acceptance remains with platform teams.

Provide statement-digest ranking by total/mean latency, execution count,
examined rows and temporary work; drill into waits, indexes and native plan
capture; support scoped slow-log analysis and explicit instrumentation
coverage/reset epochs. Use dedicated observers and existing DDN dashboard
displays. Private SQL text access and redaction remain explicit. Persistent
ScratchBird qualification stays owner-deferred.

Comparison evidence: `Current Workbench generation and shipped features <https://blogs.oracle.com/mysql/introducing-mysql-workbench-26>`_;
`PMM query analytics, monitoring and alerting <https://docs.percona.com/percona-monitoring-and-management/3/discover-pmm/features.html>`_;
`Percona query digest analysis <https://docs.percona.com/percona-toolkit/pt-query-digest.html>`_.

CMP-MY-07: Database-wide content search
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P1**.

Native pure/C workspace and built desktop acceptance is recorded under
``Native database content search`` in :doc:`mysql_functional_completion`.
Windows/macOS acceptance remains with platform teams.

Search values across selected authorized tables/columns with bounded results,
indexed-only option, explicit text/numeric/binary rules, cancellation and row
navigation. Bind exact source identities and distinguish denied or unsearched
tables. Catalog filtering and per-query result filtering do not close this
workflow.

Comparison evidence: `DBeaver database content search <https://dbeaver.com/docs/dbeaver/DB-Full-Text-Search/>`_;
`HeidiSQL table tools implementation <https://github.com/HeidiSQL/HeidiSQL/blob/118d55a6bbeaa9ba53663c512d91eb9b63358b48/source/tabletools.pas>`_;
`phpMyAdmin supported features <https://docs.phpmyadmin.net/en/latest/intro.html>`_.

CMP-MY-05: Controlled online schema change
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P1**.

The native DDN workflow now binds exact ALGORITHM/LOCK, deadlines and native
refusals, with independent execution, progress, cancellation and current-state
observation. Pinned Percona Toolkit 3.7.2 provides the admitted InnoDB copy
workflow, including registered asynchronous replica gates, source load limits,
explicit cutover and separate cleanup observations. Pure/C native and built
desktop evidence covers concurrent DML, foreign keys, existing triggers and
interrupted outcomes. See :doc:`mysql_functional_completion` for admitted
profiles, installation and qualification entry points. Wider topology, product
inventory and platform acceptance remain separate.

Expose native ALGORITHM/LOCK expectations and engine refusals first. For cases
needing an admitted source-available utility, bind its exact version, execution
host, table identity and plan; retain copy/lag/load/cutover and cleanup
observations; qualify foreign keys, triggers and interrupted outcomes on Oracle
MySQL 9.7. Keep implementation in the native DDN migration/apply workflow.

Comparison evidence: `Percona online schema change <https://docs.percona.com/percona-toolkit/pt-online-schema-change.html>`_;
`Skeema native and external online schema changes <https://www.skeema.io/docs/features/osc/>`_;
`Percona Toolkit guidance for MySQL 9.7 <https://docs.percona.com/percona-server/9.7/percona-toolkit-9.7-updates.html>`_.

CMP-MY-06: Replica and full-table data drift verification
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P1**.

Native full-table comparison now admits independent endpoint/table pairs with
recorded read-only snapshot or server-lock boundaries. Duplicate-aware SHA256
row multisets preserve full row counts and binary-protocol floating-point values.
Registered GTID replica alignment, explicit incomplete coverage, cancellation,
private spill-file cleanup, mismatch reporting/download and existing separately
reviewed data-editor repair paths are implemented. Linux pure/C and built desktop
receipts qualify the recorded scopes; see :doc:`mysql_functional_completion`.
Broader native inventory, recovery/lifecycle and platform acceptance stay open.

Compare independently admitted complete table scopes using native-consistent
chunking/keys and explicit transaction or replication positions. Present
mismatches and coverage; any repair needs a separate exact-target review. Do
not equate sampled retained-result differences with native data equality.
Qualify toolkit replication-format/topology restrictions before selecting it as
a backend.

Comparison evidence: `Percona replica checksum and limitations <https://docs.percona.com/percona-toolkit/pt-table-checksum.html>`_;
`Percona Toolkit guidance for MySQL 9.7 <https://docs.percona.com/percona-server/9.7/percona-toolkit-9.7-updates.html>`_.

CMP-MY-08: MySQL alert policies and actionable monitoring findings
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P1**.

Eleven native MySQL rules now evaluate thresholds and continuous durations on
dedicated collector connections. Pending/firing/resolved/unknown/silenced states
retain exact native evidence and diagnostic next steps. Counter resets, missing
or denied groups and stale sources stay explicit; scheduled failure backoff is
included in outage-duration continuity. Configured owner-authorized JSON SMTP
routes use authenticated TLS, bounded independent delivery and durable outcome
receipts without automatic retries. Rule/silence administration is in collection
policy; DDN dashboards display read-only findings with current binding checks.
See :doc:`mysql_alerts` for setup and process/lease limits.

MySQL 9.7.0 pure/C native/API and built-desktop acceptance covers actual SMTP
submission and lost acknowledgement, native lock waits and FLUSH STATUS gaps,
replication failures, registration revocation, transaction isolation, duration,
silence and resolution. Affected checks pass 206 Python tests plus five subtests
and 48 JavaScript tests. ScratchBird history qualification stays owner-deferred;
Windows/macOS acceptance remains with the platform teams.

Comparison evidence: `PMM query analytics, monitoring and alerting <https://docs.percona.com/percona-monitoring-and-management/3/discover-pmm/features.html>`_;
`phpMyAdmin supported features <https://docs.phpmyadmin.net/en/latest/intro.html>`_.

CMP-MY-09: Spatial data inspection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P2**.

The native workspace now inspects exact geometry/WKB bytes, SRID definitions,
WKT in SRS and X/Y order, and native GeoJSON. A bounded DDN map supports every
native geometry family, lines, collections and polygon holes, with explicit
native X/Y or native WGS84 transformation. Invalid, null, oversized and refused
values retain distinct fallback states. Deliberate original-byte download and
private-result clearing are included. No external tiles or network requests
are enabled. See :doc:`mysql_spatial_inspection` for scope and limits. Linux
pure/C native/API and built desktop evidence qualifies this workflow; platform
acceptance and owner-deferred history remain separate.

Add a bounded geometry map and WKT/GeoJSON inspection with correct SRID and
axis-order handling, null/invalid/binary fallbacks and explicit external tile
access. Preserve native bytes. Reuse current native spatial-reference catalog
and DDN adapters; catalog and data fidelity already implemented do not equal a
map viewer.

Comparison evidence: `DBeaver spatial data viewing <https://dbeaver.com/docs/dbeaver/Working-with-Spatial-GIS-data/>`_.

CMP-MY-10: Versioned schema deployment automation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P2**.

The supported local operator/CI CLI now captures exact native environments,
packages versioned DDN artifacts, plans and validates native changes, prepares
durable review tickets, applies an explicitly approved ticket and retrieves its
original receipt. Exact artifact/environment/native bindings prevent cross-target
reuse and relabelled-review authority. JSON reports and documented exit codes
retain drift, partial/unknown and committed-without-verification outcomes without
automatic retry. Existing native controlled ALTER and pinned online-copy execution
are reused; copy cutover requires explicit approval. See
:doc:`mysql_schema_deployment` for setup, contracts and limitations.

Linux qualification uses actual CLI subprocesses with independent MySQL 9.7.0
instances and both corrected connector interfaces. It covers native data and
transaction preservation, once-only receipts, process loss after the durable
claim, native algorithm refusal and Percona Toolkit 3.7.2 copy/cutover. Platform
acceptance remains with the Windows/macOS teams; history stays owner-deferred.


Qualify a headless invocation and CI-friendly report/exit contract over
existing DDN desired/live/baseline plans, explicit environment bindings and
reviewed apply. Support reusable exact artifacts without broadening deletion
authority. Existing APIs, DDN persistence and native diff/apply are
implementation inputs, not missing diff engines. Full automation parity remains
unverified.

Inspect the existing API and command surfaces before adding code. If the
required headless workflow already exists, close the item with its current
qualification rather than introducing another compiler or migration engine.

Comparison evidence: `Skeema declarative schema management <https://github.com/skeema/skeema>`_.

CMP-MY-11: SQL notebooks and shareable investigations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Status: **implemented and Linux-qualified**. Priority: **P3**.

Native MySQL SQL editors and Project Explorer now share versioned notebook
assets containing notes, SQL cells and deliberately retained/redacted bounded
result snapshots. Explicit binding selects an engine/endpoint/database target;
only a deliberate cell run uses the existing native session, transactions,
diagnostics and cancellation. Opening, importing, saving and sharing never
execute stored SQL. Portable exports remove local connection bindings and
exclude credentials, session handles, parameters and native result blobs.
Import requires explicit rebinding before execution. Project permissions,
optimistic revisions, historical drafts, exact SQL/result matching and sharing
review are enforced. See :doc:`mysql_sql_notebooks` for privacy limits and use.

Linux native pure/C/API qualification covers exact unsigned64/Unicode results,
redaction, revision conflicts, inert stored mutations and independent pending
transaction/savepoint preservation. The production desktop qualifies explicit
execution, retention, revision save, portable download, inert import and
rebinding. Windows/macOS acceptance remains with platform teams. ScratchBird
history qualification is owner-deferred and was not run. Recovery/lifecycle
priorities and the broader native product inventory remain open.

Comparison evidence: `Current Workbench generation and shipped features <https://blogs.oracle.com/mysql/introducing-mysql-workbench-26>`_;
`Workbench open source repository <https://github.com/mysql/mysql-shell-plugins/tree/7332e92a5fb3f1422c3b083f339cd03c8788e876>`_.

Preserve existing native support
--------------------------------

The current provider already has native JSON/analyze plan commands, predictive
completion and native grammar checks. The shared provider supplies MySQL semantic
query compilation; a missing MySQL override does not imply missing compilation.
Shared result exports and retained-result comparison also exist, with their
recorded policy/bounds. Preserve the native DDN capture/diff/apply workflows,
logical backup/load/acceptance, managed archive dependencies, scoped topology
operations, Router metadata/guidelines, local sandboxes and administrator setup.

Qualify ad hoc visual-query usability and reuse existing analysis, chart and
project-asset infrastructure before proposing another builder. DDN continues to
own ERD/dashboard rendering and editing; dashboard viewers remain display-only.
The native source-available utility may be integrated, but requiring users to
operate another administration application does not close a workflow.

MySQL implementation exit and MariaDB start
-------------------------------------------

The active implementation focus moves to MariaDB when all of the following are
recorded:

1. ``CMP-MY-01`` through ``CMP-MY-11`` meet their applicable native/application
   acceptance and have current evidence, including failure/recovery behavior.
2. ``INV-MYSQL``, ``MY-CONTINUITY``, ``MY-ARCHIVES``, ``MY-HA-LIFECYCLE``,
   ``MY-LANGUAGE-CAPABILITIES`` and ``MY-DIAGNOSTICS`` are reconciled and closed
   for the agreed beta implementation scope. A linked comparison item does not
   close an entire broader requirement automatically.
3. Remaining externally owned, owner-deferred and post-beta evidence is listed
   explicitly. The implementation handoff does not establish full cross-platform
   product acceptance or close the six-engine matrix.
4. Record the final source revision and concise current qualification, clean
   superseded task-owned builds/fixtures, and update the active workplan to
   MariaDB. Start with its native inventory and current ``MA-*`` backlog;
   MySQL receipts do not qualify MariaDB behavior.

After this checkpoint, stop MySQL feature development and continue MariaDB.
Record additional MySQL feature ideas for later prioritization.

Scope boundaries retained from the owner
----------------------------------------

* Human form validation remains with the human team.
* Native Windows/macOS implementation/acceptance remains with platform teams.
  Their remaining work does not hold up this implementation-focus handoff;
  their evidence is still required before cross-platform acceptance is claimed.
* ScratchBird driver/history wiring remains in scope, but native and unit
  history qualification remains deferred. Do not start/build ScratchBird or
  run those tests until the owner resumes qualification.
* Closed-source MySQL Enterprise masking and server MLE remain post beta.
  Competitor GUI integrations do not make their required implementations
  available. The comparison is a source/documentation review, not positive
  runtime evidence for a new native dependency.
* XtraBackup 9.7.1-rc1 is a source-available candidate identified by that review.
  Verify its current release/source/compatibility before adoption and qualify
  actual backup, prepare, recovery and interruption paths. It is not already an
  admitted production backend merely because this queue names it.
