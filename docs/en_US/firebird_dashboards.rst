Firebird standard dashboards: metric and presentation proposal
*************************************************************

Scope and evidence
==================

Proposal, 2026-10-10. This is the Firebird dashboard family in ScratchRobin:
engine-type root -> registered server endpoint -> database. Server means the
registered endpoint including port. DDN supplies read-only dashboard display and
a separate dashboard editor; ScratchRobin supplies scoped authorized data and
native object links. The viewer cannot change layout, bindings or displayed data.
A ScratchBird endpoint exposing Firebird compatibility may reuse these layouts
only after its own capability/semantic mapping is qualified; Firebird table
names alone do not prove equivalent ScratchBird measurements.

Reviewed exact Firebird 5.0.4 build 1812 source, admitted release archive SHA-256
5041b97b480c9fe241c92ad0adf89e36faad0a8f0e21f1371dfbcc96a6f38e12, and current
ScratchRobin provider code. Primary local evidence:

* /home/dcalford/Sandbox/donor_release_acquisition/firebird/5.0.4/source/doc/README.monitoring_tables
* Same source tree: src/jrd/relations.h, src/jrd/Monitoring.cpp,
  src/jrd/constants.h, src/jrd/svc.cpp and doc/README.replication.md.
* ScratchRobin web/pgadmin/cdeadmin/providers/firebird/
  firebird_metrics_5_0_4.json and provider.py; admitted firebird-driver core.py
  ServerInfoProvider properties and database information properties.

The existing exact-version inventory contains 146 native observations and 36
numeric metric definitions. These are not 36 working time-series collectors:
provider.py currently adds MON$ metric descriptors without sampling their live
values. It separately collects database information and service-manager values.
The initial proposal did not qualify live series. The dedicated monitoring
adapter and bounded process-local policy runtime now have the implementation
evidence described below. The single-process host and basic DDN dashboard bindings
are described below; durable history and the full dashboard family remain open.

Three dashboard layouts
=======================

Engine dashboard — Firebird fleet overview
------------------------------------------

Top row: registered endpoints, reachable/failed/unknown endpoints, monitored
versus known databases, visible user attachments, attention items. Show sample
age and coverage beside each aggregate. Under this row, use a wide sortable
server matrix; beneath it use small workload trend panels and an exceptions list.
Clicking any server/database opens its dashboard, not an unrelated generic form.

.. list-table:: Engine-root widgets
   :header-rows: 1
   :widths: 22 43 35

   * - ID / measure
     - Source and aggregation
     - DDN display
   * - E01 Endpoint reachability
     - Application connection/service observations; registered, reachable,
       failed, not checked and permission-limited are distinct states.
     - Count cards and server status matrix, last successful observation.
   * - E02 Version and architecture
     - Service manager version/engine_version/architecture and observed ODS.
     - Compact distribution bars; server matrix columns and version filters.
   * - E03 Inventory coverage
     - Registrations, service attached_databases, and explicitly monitored DBs.
       Attached databases are not every database file or configured alias.
     - Known/monitored/unreachable counts; coverage text such as 8 of 12 known.
   * - E04 Connections and workload
     - Database MON$ attachments and group-0 IO/record rates over comparable
       time windows; de-duplicate database registrations before aggregation.
     - Attachment sparkline, DML/read-rate trends and busiest DB ranking.
   * - E05 Database storage
     - Sum page_count * page_size per observed database instance, converting
       independently where page sizes differ. Unknown DBs remain unknown.
     - Known allocated-size card and ranked horizontal bars.
   * - E06 Attention queue
     - Fresh scoped findings: unreachable endpoint, old transaction, prolonged
       backup state, unexpected encryption/access state, new conflicts.
     - Severity-sorted table with reason, scope, age and drill-down.
   * - E07 Security coverage
     - Eligible user-attachment wire encryption plus database encryption state;
       retain unknown and non-wire/local categories separately.
     - Count/fraction cards with denominator and coverage, no opaque risk score.

Server dashboard — one endpoint
--------------------------------

Header: endpoint name/address/port, actual server version/architecture, service
manager availability and observation latency. Main area: database status table
and connection trends. Secondary tabs/panels: security, configuration, service
operations/logs. Show enabled versus unavailable collectors.

.. list-table:: Server widgets
   :header-rows: 1
   :widths: 22 43 35

   * - ID / measure
     - Native source and meaning
     - DDN display
   * - S01 Server identity/capabilities
     - Service manager version, engine_version, architecture, manager_version,
       capabilities; installation/lock/message/security DB locations as permitted.
     - Compact information panel; sensitive paths in authorized details.
   * - S02 Database attachments
     - Service connection_count: number of database attachments, not users,
       sockets or service-manager connections. Report server architecture scope.
     - Count and trend; compare with monitored DB coverage without asserting
       equality across independent samples.
   * - S03 Attached and registered DBs
     - Service attached_databases plus registrations; observe each authorized DB
       independently to obtain size/state/workload/oldest transaction details.
     - Database matrix: state, attachments, active requests, size, I/O, oldest
       transaction age, encryption/replica state and observation age.
   * - S04 Security database accounts
     - SEC$USERS: name + plugin, active/admin flags; SEC$DB_CREATORS and
       SEC$GLOBAL_AUTH_MAPPING for authorized privilege/mapping inventory.
     - Active/inactive/admin count cards and account/plugin table. Partition by
       actual security DB; deduplicate shared security DB observations.
   * - S05 Connected clients/security
     - Per-DB MON$ATTACHMENTS user/role/client version/protocol/auth method,
       wire encryption/compression/plugin, remote host/process where available.
     - Grouped connection table and distributions; count attachments separately
       from distinct users. Drill down with appropriate visibility permissions.
   * - S06 Observed workload
     - Group-0 measurements across covered DBs; never sum all statistic groups.
       Native DB memory is not necessarily whole-server RSS or host memory.
     - Per-DB stacked/ranked rates and scoped memory; coverage stays visible.
   * - S07 Service operation outcomes
     - ScratchRobin's actual backup/restore/maintenance receipts and service
       output; authorized Firebird server log retrieval on demand.
     - Recent operations table and bounded read-only log viewer. Task execution
       remains a separate context-menu destination.
       Absence of a local receipt does not prove nobody ran a backup elsewhere.
   * - S08 Configuration/overrides
     - Service identity/config observations and RDB$CONFIG values, defaults,
       is-set/source data from each database context where supported.
     - Searchable effective/default comparison table, source and DB context.
       Do not label database-specific effective settings as universal server values.

Database dashboard — operational overview plus drill-down
---------------------------------------------------------

Top row: database state, user attachments, active transactions/requests, allocated
size and oldest transaction age. Middle: activity, page I/O and transaction
horizon trends. Lower: longest-running activity and busiest tables. Tabs:
Overview, Activity, MGA/Transactions, Storage, Security, Schema, Protection.
Use sparklines/line plots for time series, bars for rankings and tables for
identities/diagnostics. Avoid circular gauges without a meaningful capacity limit.

.. list-table:: Database widgets
   :header-rows: 1
   :widths: 22 43 35

   * - ID / measure
     - Source / calculation
     - DDN display and interpretation
   * - D01 Identity/state
     - MON$DATABASE name, GUID, file ID, owner, ODS, page size, SQL dialect,
       creation time, shutdown mode, read-only and forced-writes flags.
     - Status strip plus property panel; native states remain explicit.
   * - D02 Attachment activity
     - MON$ATTACHMENTS: visible total/user/system and active/idle; timestamp
       for connection age. Separate the dashboard collector's own attachment.
     - Count cards, stacked trend and client/user/role detail table.
   * - D03 Transaction activity
     - MON$TRANSACTIONS: counts, timestamp age, state, isolation mode,
       read-only, lock timeout, auto-commit/undo; join attachment identity.
     - Oldest-first table and age trend. A transaction being open does not prove
       it is blocking another transaction or garbage collection by itself.
   * - D04 MGA horizons
     - MON$DATABASE OIT/OAT/OST/next transaction; differences next-OIT,
       next-OAT and next-OST, plus sweep interval and trend.
     - Three transaction-number-distance series and current values. These are
       not elapsed age, row-version counts or committed transactions per second.
   * - D05 Record activity
     - MON$RECORD_STATS, database statistic group: sequential/indexed reads,
       inserts, updates and deletes, using interval deltas.
     - Read and DML activity line plots. Operations are not committed business
       changes; rollback and internal work affect interpretation.
   * - D06 Page I/O/cache activity
     - MON$IO_STATS group 0: reads/writes/fetches/marks per second; convert
       page reads/writes to bytes/sec using this DB's page size.
     - Separate physical page I/O and logical cache-activity plots. This is
       Firebird page I/O, not host disk utilization or network bandwidth.
   * - D07 Cache estimate
     - Interval 100 * (1 - delta page reads / delta page fetches), when
       denominator and scope/reset checks permit a meaningful estimate.
     - Labelled interval cache-hit estimate with reads/fetches drill-down.
       No denominator means N/A; anomalous ratios are flagged, not hidden.
   * - D08 Record contention
     - MON$RECORD_WAITS, MON$RECORD_CONFLICTS and MON$RECORD_LOCKS deltas.
     - Wait/conflict-rate plot and per-table/attachment drill-down. Counts are
       not current lock counts, blocked-session counts or a wait-for graph.
   * - D09 Version cleanup work
     - MON$BACKVERSION_READS, RECORD_BACKOUTS/PURGES/EXPUNGES, RECORD_IMGC,
       FRAGMENT_READS and repeated reads, with same-scope interval rates.
     - Cleanup/version-read plot alongside horizons and oldest transactions.
       No fabricated dead-version percentage or predicted sweep duration.
   * - D10 Native memory/cache allocation
     - MON$MEMORY_USAGE group 0 used/allocated/high-water values; page buffers
       * page size is configured cache capacity, not actual resident usage.
     - Byte-valued lines, high-water marker, separate cache configuration card.
   * - D11 Active requests and PSQL
     - MON$STATEMENTS state/start/attachment/transaction/timeout and compiled
       ID; MON$CALL_STACK details on demand. SQL/plan BLOBs fetched only on drill.
     - Longest-first activity table, SQL preview, source location and plan.
       Distinguish active, idle and stalled execution; stalled can mean waiting
       for client fetching and must not be labelled a database lock wait.
   * - D12 Compiled statement inventory
     - MON$COMPILED_STATEMENTS count and source/object/plan details.
     - Count and searchable table; no inferred statement-cache hit/miss rate.
   * - D13 Busy tables
     - MON$TABLE_STATS -> MON$RECORD_STATS via record-stat ID within the
       selected native stat group; rank interval reads/writes/waits.
     - Top-N horizontal bars and expandable per-table metrics table. A table
       absent from an interval's activity is not necessarily unused historically.
   * - D14 Allocated size/growth
     - MON$PAGES * MON$PAGE_SIZE; native information pages-used/free when
       supported, with cost and scope stated; RDB$FILES file/shadow inventory.
     - Size/growth trend and storage details. Allocated pages are not logical
       data bytes, filesystem allocated blocks, host free disk or exact row counts.
   * - D15 Database security
     - RDB$ROLES, RDB$USER_PRIVILEGES, local/global auth mappings, owner,
       SQL-security defaults and visible wire/security observations.
     - Role/grant counts and scoped read-only matrices; links to object
       inspection. Grant changes remain separate context-menu actions. SEC$ user
       attributes stay opt-in detail, not automatically exposed dashboard data.
   * - D16 Schema inventory and conditions
     - RDB$RELATIONS/RELATION_FIELDS, indices/constraints/triggers, procedures,
       functions/packages, domains/generators, dependencies; system/user split.
     - Object-count bars, inactive-index/trigger and invalid-BLR detail lists.
       Counts are not health scores; inactive objects may be intentional.
   * - D17 Backup/protection
     - MON$BACKUP_STATE; RDB$BACKUP_HISTORY timestamps/levels/GUIDs/files
       for physical backup history; actual local task/restore-verification receipts.
     - Backup state/age cards and timeline. History does not prove backup files
       still exist or are restoreable; gbak history is not implied by this table.
   * - D18 Encryption and replication
     - MON$CRYPT_STATE/CRYPT_PAGE and native crypt identity; MON$REPLICA_MODE,
       RDB$PUBLICATIONS/PUBLICATION_TABLES and configuration observations.
     - State cards, publication coverage table and DDN relationship view.
       Crypt page is a progress marker, not a verified completion percentage;
       replica mode/publication membership is not replication health or lag.

Refresh, calculations and permissions
====================================

Proposed defaults (configurable, subject to cost qualification): database
activity collection every 5 seconds, server/fleet summaries every 15-30 seconds,
metadata/security/configuration every 60 seconds or after known change, and
expensive physical statistics/log/profiler/trace queries through explicit
separate diagnostics. Collection is scheduled independently of dashboard views.
Suspend rendering/subscriptions for hidden panels, not policy-enabled historical
collection. Coalesce collectors and back off on load/timeouts. Never run full
schema discovery or large SQL/plan BLOB fetches at the activity refresh interval.

Use dedicated collector connections, never user/editor connections or sessions.
Use one short independent monitoring transaction per database sample, sharing
its MON$ snapshot across queries, then finish it before the next sample. MON$
retains its first monitoring snapshot until that transaction ends regardless of
ordinary isolation mode. Reusing an open user-editor transaction would freeze
the dashboard and may prolong retained work. Collector lifecycle must follow
native transaction semantics and never commit or roll back the user's work.

Use backend elapsed time for rates, server timestamp semantics for ages, and
record collection start/end and skew. delta(C)/delta(t) is valid only for the
same native scope/identity and a continuous counter epoch. On restart, reset,
identity change, disappearing rows or decreasing counters, show a gap and
establish a new baseline. Do not show a negative rate or silently fabricate zero.
Preserve large counters as exact integers through transport before calculating.

Join statistic IDs with their group and owning observation, using the actual
engine's enum mapping. Database/attachment/transaction/statement/call statistics
are overlapping scopes: summing all of them double-counts. For fleet rates,
aggregate compatible fresh intervals; display coverage/skew and avoid summing
percentages. Compute aggregate cache estimates from summed eligible deltas.
Deduplicate aliases/registrations using verified database-instance identity, not
path spelling or a GUID alone (copies/restores may share identifiers). Preserve
uncertainty where endpoint aliases cannot be proven to identify the same instance.

Monitoring visibility depends on the authenticated principal and native
privileges. Firebird source uses MONITOR_ANY_ATTACHMENT through the locksmith
check; the older monitoring README's SYSDBA/owner description is not the full
modern privilege contract. Mark own-user/partial visibility explicitly. Account
inventory can vary by plugin and security database. Do not sum SEC$ account
counts once per application database that shares the same security database.
Authorization failure or absent capability means unavailable, not healthy/zero.

Every series carries scope/identity, source field, unit, counter/gauge/config
classification, collection interval, coverage, last-success time and reset epoch.
ScratchBird is the intended persistent history database, separate from monitored
source databases. Store authorized observations and catalog/configuration snapshots
with source identity, observation/ingestion times, scope, coverage and revision;
apply configurable retention/downsampling. History storage is future implementation
work, not an existing capability. DDN reads authorized current/historical records
through stable bindings and renders the selected published dashboard revision.
Saved definitions must not embed credentials, unrestricted context-variable
values or raw SQL text.

Not supplied by ordinary catalog/service snapshots
=================================================

Do not invent host CPU%, host RAM%, free disk, disk latency/IOPS saturation,
network throughput, authoritative server uptime, statement latency percentiles,
committed transaction TPS, failed-login history, complete blocking chains,
all-database enumeration, database row counts, verified restoreability or precise
replication lag. These need separately admitted sources: host agents, tracing,
profiling, application receipts, explicit table scans or replication telemetry.
Connection observation latency may be shown as client-observed round-trip time,
not labelled ping, CPU load or query execution time.

RDB$ index selectivity/statistics are optimizer metadata, not live usage rates.
SEC$USERS describes accounts, not sessions or login attempts. MON$CONTEXT_VARIABLES
may contain application secrets and should be a permission-scoped inspection
panel, not a default metric feed. Service-manager output/log retrieval may be
privileged, slow or textual; store source/type/time and parse known formats only.
Embedded endpoints omit server-service widgets that do not exist for that mode.

Alerts and interaction
======================

Thresholds belong to policy, not hard-coded assumptions. Example configurable
findings: oldest transaction age exceeds policy; horizon distance keeps growing;
new record conflicts; physical-backup state persists unusually long; observed
user connections do not meet required wire-encryption policy; known task failed;
required collector stale. Show observed value, duration, policy and evidence.
The dashboard presents findings without acknowledgment or mutation controls.
Cancel statement, disconnect, sweep, repair, change encryption/replica settings,
restore and any alert acknowledgment belong to separate authorized destinations,
not the dashboard viewer.

Implementation order
====================

1. Qualify the independent snapshot collector, visibility/counter-epoch model and
   DDN refresh/integration boundary. Keep descriptor inventory distinct from data.
2. Deliver E01-E03, S01-S03 and database D01-D06/D10/D14 with real drill-down.
3. Add record contention/cleanup, busy tables, query inspection, security,
   schema and protection panels with clear source/coverage semantics.
4. Add historical roll-ups, alerts and optional trace/profiler/host telemetry
   only after their data sources are admitted. Layout editing is available solely
   through the separate DDN dashboard-editor context-menu destination.

This proposal extends FB-COMP-18 and follows ddn_database_roundtrip.rst. It does
not claim the current project already collects or renders all proposed widgets.

Snapshot collector contract
===========================

The Firebird collector owns a provider client that is never shared with query
or administration work. It retains its dedicated attachment between samples,
but ends every monitoring transaction with rollback (no retaining). Each sample
therefore observes a fresh MON$ snapshot. Its read-only snapshot transaction,
no-wait locking, connection timeout and statement timeout override user defaults
only on that attachment. Collection contains a fixed allowlist of SELECTs;
it never accepts SQL or routes from a dashboard definition.

The initial source contract covers D01-D06/D10/D14 and service identity,
attachment count and attached-database inventory. User attachment and transaction
counts exclude the collector. The collector's IDs and overhead remain explicit.
Monitoring coverage is complete only when the native identity is SYSDBA, the
database owner or has MONITOR_ANY_ATTACHMENT. Otherwise counts are labelled
visible-to-collector; a failed privilege observation cannot imply full coverage.
SQL text, context variables and client process paths are not collected.

Native integers are decimal strings in samples, including IDs and derived byte
counts. Wall-clock UTC timestamps identify the observation window; rates use
backend monotonic elapsed time. Counters are not committed-row or transaction
counts. A new attachment, identity change, missing counter sample or decreasing
counter starts a new epoch with no rate for the first observation. Database
GUID/file identity is scoped to the registered endpoint, never globally deduped
without independent instance evidence. Optional unavailable groups have explicit
unavailable status, not zero. Exceptions expose types, not native error strings
that may contain credentials, SQL or sensitive paths.

On connection/query/transaction-end failure the collector attempts release and
retains ownership if cleanup is unconfirmed. It must release that old attachment
before reconnecting. A shutdown never touches any user's client or transaction.
This source adapter alone is not policy scheduling, dashboard publication or
durable history; those remain separate acceptance obligations.

The monitoring runtime coalesces an explicit owner/endpoint/target policy into
one job independently of viewers. Initial limits are 16 jobs per runtime,
5-300 second database intervals (15-300 for services), 1-720 retained samples
per job, and a maximum 24-hour collection lease. Defaults are 5 seconds,
120 samples and one hour for database policies. Sampling is serialized per job,
delayed from completion, with exponential outage backoff capped at five minutes.
There is no catch-up replay. Retention evicts the oldest observation and reports
the eviction count. This buffer is volatile, not the ScratchBird history store.

Configuration, collection and viewing are separately authorized. Collection
rechecks authorization before every sample; revocation or lease expiry stops
the job and releases its source. Re-enabling requires explicit policy admission.
Unconfirmed source release retains ownership and blocks replacement. Snapshot
reads never create or restart jobs. The runtime is process-local: web exposure
requires an admitted delegated-credential resolver and exclusive worker ownership
across application processes. Existing browser credentials must not be read by
impersonating a logged-in user. The single-process host below supplies scoped
delegation and dashboard destinations. Durable scheduling remains open.

MGA refresh and optional availability heartbeat
-----------------------------------------------

Owner clarification, 2026-10-10: MGA monitoring transactions must be refreshed
regularly. A policy may also use those refreshes as an availability heartbeat.
For Firebird, refresh means ending the previous monitoring transaction without
retaining and reading the next sample in a new read-only transaction. Do not
commit or roll back a user's transaction to achieve monitoring freshness. A
retained connection is permitted; a retained monitoring snapshot is not.

Heartbeat reporting is opt-in and distinct from metric freshness. A database
heartbeat requires a successful native monitoring read and confirmed completion
of its collector transaction. Optional unavailable metric groups do not erase
that availability observation. Cached identity, an open socket, a timer firing,
or an unsuccessful transaction end is not a heartbeat. Service scope requires
a fresh service query (attachment count or attached-database inventory), not a
cached version string. These are scoped availability observations, not proof
that every database or operation on a server is available.

The default overdue threshold is the greater of 15 seconds and three sampling
intervals; explicit thresholds range from one interval plus five seconds to
3600 seconds. Retain last successful wall-clock receipt and compute age with
the worker's monotonic clock. Expose disabled, unknown, observed, overdue and
stopped states independently of the latest probe status. Expiry/revocation/
shutdown stops heartbeat reporting. An overdue heartbeat is an observation gap,
not evidence of rollback, committed outcome, membership loss or permission to
fence a node. ScratchBird must implement its own qualified MGA refresh adapter
under this same lifecycle rule; Firebird SQL is not its native implementation.

Owner correction: connections, history and editor separation
===========================================================

Accepted 2026-10-10; this section supersedes any earlier suggestion of editing
layouts directly within dashboards.

* The collector owns dedicated native database attachments and service-manager
  sessions, credentials, transactions, timeouts and reconnection. They are
  separate from all user query/editing sessions. Closing a user session or
  dashboard does not stop policy-enabled collection. Collector failure cannot
  commit, roll back, cancel or reconnect a user's transaction.
* One admitted sampling job may serve multiple viewers; it must not create an
  independent source workload for each open dashboard. Distinguish collector
  attachments in measurements so their overhead is visible and can be excluded
  from user-activity totals. Separate connections do not imply unlimited source
  privileges; collection permissions and dashboard-view permissions are distinct.
* The eventual ScratchBird history writer uses its own destination connection
  and transaction. Source observation and history ingestion are not a distributed
  transaction. Retain source/time/provenance, stable sample IDs for deduplication,
  and explicit gaps/staleness. On destination outage, bounded buffering/retry and
  its overflow policy must be specified before implementation; never replay source
  queries and present later observations as the original missing samples.
* Collect metadata/configuration changes as versioned historical observations as
  well as metric samples. Do not interpret this requirement as automatic retention
  of all source business rows. Historical dashboards enforce current viewer
  authorization even if the collector could read broader data.
* Engine, server and database dashboards are display-only. No drag/reorder/resize,
  widget addition/removal, inline data editing, source editing, binding changes,
  save-layout controls or database administration controls are present. Disable
  editor capability in the mounted DDN viewer, not just visible toolbar buttons.
* Read-only inspection, drill-down, refresh and time-range/series selection may
  change the temporary view, but cannot modify the saved layout, stored samples,
  bindings or database state. A displayed historical value cannot be edited.
* Add a distinct **Edit dashboard...** context-menu item at the engine, server
  and database nodes for authorized dashboard designers. Pass dashboard identity,
  scope and definition revision to the separate DDN editor. Preserve the viewer
  and editor as separately referenced forms using the existing form-ID registry.
* Editor save/publish changes a versioned dashboard definition, never telemetry
  records or monitored database metadata. Validate bindings and capabilities;
  detect concurrent definition changes. Viewers render a coherent published
  revision and retain their read-only capability on refresh or version switch.
  Dashboard-edit rights do not grant collection-policy or database-write rights.
* Acceptance must prove separate native connection/session identities, collection
  continuing without viewers, no viewer mutation paths, authorized context-menu
  routing, concurrent editor conflict handling and correct current/historical
  scope and authorization. These are requirements, not completed implementation.

Qualified source/runtime increment
==================================

Worker credential delegation contract
--------------------------------------

An authenticated policy owner explicitly delegates the selected Firebird network
endpoint and database target (or service scope). Capture credentials through the
existing protected secret lease during admission, then seal them using the
existing authenticated worker-envelope implementation. A grant binds its owner,
complete sampling policy, endpoint generation, exact route fingerprint, secret
kind and unique grant/credential IDs as authenticated associated data. Never
retain a browser session or reuse the browser's resolver from a worker.

Every source open, reconnect and sample requires the host's current authorization
for that exact bound scope and generation. Recheck after sampling too: discard
observations if authorization was revoked while a native call ran. Collection
authorization does not grant viewing or policy changes. Grant expiry uses a
monotonic deadline and cannot exceed the policy lease. Explicit revocation clears
sealed credentials; the runtime must still finish/release an in-flight native
call before replacing its source. Native outcomes of user work remain unrelated.

The initial grant implementation is volatile and requires a supplied worker key
authority. Application restart loses grants and requires explicit re-admission;
it does not silently reconstruct authority from saved browser passwords. Durable
policy/grant storage and exclusive multi-process job ownership remain a separate
host integration obligation. Embedded attachments are not admitted by this
network credential contract.

The initial web host admits only ``CDEADMIN_MONITORING_PROCESS_MODE = 'single'``
with a supplied ``CDEADMIN_MONITORING_WORKER_KEYS`` key ring,
``CDEADMIN_MONITORING_WORKER_ACTIVE_KEY_ID`` and
``CDEADMIN_MONITORING_LOCK_PATH``. An OS-held exclusive lock prevents a second
process from admitting collectors against the same lock file; do not unlink the
lock file during service. This is a single-process deployment contract, not
multi-process request forwarding or a cluster-wide scheduler. Configuration is
disabled by default. Windows uses its native byte-range locking API; platform
QA is required before claiming Windows qualification.

The authenticated endpoint
``/cdeadmin/api/monitoring/firebird/<server-id>?target_id=<registered-target-id>``
provides GET for volatile observations, POST for explicit policy admission and
DELETE for revocation/release. Omit target_id for service scope. Only the current
endpoint owner can use it; server-side scope resolution determines routes and
credentials. POST accepts sampling, retention, lease and heartbeat policy fields
only. GET never schedules work. Expired collection grants do not independently
revoke a current owner's right to view retained samples; current endpoint scope
and verification are still checked. Changed routes/generations hide old samples
until explicit re-admission. DELETE remains possible after route changes.

Evidence
---------

``providers/firebird/monitoring.py`` supplies dedicated database/service
observations, exact counters and fresh read-only MGA transactions.
``workspace/monitoring.py`` supplies explicitly authorized process-local policies,
bounded volatile samples, independent workers and optional heartbeat reporting.
``tools/cdeadmin_firebird_monitoring_gate.py`` qualifies both against the native
engine using a disposable database and restricted user.

The 2026-10-10 gate passed on Firebird 5.0.4.1812: separate collector/user
attachment and transaction IDs; a changed transaction for the next MON$
snapshot; restricted-user visibility; uncommitted user work neither committed
nor rolled back; service-manager queries; repeated background collection without
viewers; policy heartbeat; authorization revocation and collector shutdown leaving
user work intact. The gate removed its temporary user and database. This is
source/runtime qualification. Subsequent host qualification covers explicit
volatile credential delegation. Multi-process scheduler ownership, dashboard
editor publishing and historical storage remain open.

The server and registered-database context menus now route to a passive DDN
dashboard (SR-F-001351) and a separate collection-policy form (SR-F-001352).
Dashboard reads cannot start/stop collection or alter layouts. The initial DDN
panels show exact textual observations and rates with coverage, source state and
units; integer counters are never converted to JavaScript floating-point numbers.
An unavailable latest sample does not display earlier successful values as
current. This initial display is not the complete engine fleet dashboard, trend
analysis, drill-down family or separate published-definition editor.

Engine overview admission and freshness
---------------------------------------

The initial engine overview reads only the current owner's registered native
Firebird endpoints and already admitted collector snapshots. GET never opens a
native connection, starts a policy, or probes an unmonitored registration. A
separate engine-root context action opens this passive DDN view. Embedded profiles
are excluded from the network service-manager inventory.

Each endpoint reports collection state, monotonic sample age, freshness, probe
result, visible version/architecture, registered database targets, monitored
registered targets, and service-visible attached files. Registered targets and
attached files are different inventories; neither is the complete server catalog.
Counts refer to registrations, not deduplicated physical database instances.
No workload or storage totals are inferred from these registration counts.

A sample becomes stale after max(15 seconds, three sampling intervals), regardless
of whether optional heartbeat is enabled. Stopped or expired collection is not
current reachability. A completed current service probe proves observed
reachability; explicitly denied permission, failed probes, unknown and stale
observations remain distinct. Source groups unavailable to a successful partial
probe remain unknown. Revoked or changed scope hides old native sample details.
Native failures are reported as observation failures, not proof of host failure.
The fleet read performs current scope authorization per admitted policy; it never
returns another owner's policies or credentials. Empty inventories are valid.

Scoped dashboard drafts
------------------------

Dashboard editing first persists an authored DDN draft through the existing
project-asset revision store. Draft identity binds the authenticated owner,
engine and endpoint registration UUID (plus registered target UUID for database
scope); a recreated registration must not inherit another endpoint's definition.
GET is read-only and creates neither projects nor assets nor source connections.
PUT creates the owner's dashboard-draft project on first save, checks scope and
expected asset version, and appends an immutable revision. Cross-owner and
cross-scope references are refused. Removed targets cannot be edited through an
old dashboard URL. The initial designer authority is the active registration
owner; project sharing alone grants no native monitoring rights.

The context action **Edit dashboard draft...** opens the separate DDN unified
editor with its static form reference. Standard templates have unavailable
metric values and never receive live telemetry. Saving a draft cannot change
collection policy, native metadata, or the dashboard currently being displayed.
The editor provides syntax/layout validation; the backend validates the bounded
DDN asset envelope and scope. A saved draft is explicitly not a semantically
qualified published definition. Binding admission, server-side publication
validation, published revision selection and viewer binding are a separate
unfinished step; do not silently display unqualified drafts as live dashboards.
Concurrent stale drafts receive an asset conflict; never silently overwrite.

Asset saves also use the existing version column as an ORM optimistic concurrency
predicate. A stale database UPDATE or DELETE rolls back its transaction and
returns an asset conflict, including when separate application workers loaded
the same version. The service continues assigning version numbers; no schema
migration or additional definition store is introduced.

Current-run scope correction, 2026-10-10
---------------------------------------

The owner defers persistent monitoring history and the ScratchBird connection
until a later run. Windows/macOS implementation qualification and QA belong to
the separate platform teams. These items remain future/cross-team obligations;
they are not blockers or acceptance requirements for this run, and must not be
reported as unfinished work assigned to this run.

Everything else remains in scope: published dashboard definitions and authorized
live bindings, standard metrics, trends and drill-downs using available samples,
metadata/data-to-DDN, DDN-to-native schema and semantic diff/apply, all remaining
FlameRobin parity workflows, compact native forms and end-to-end qualification
on the available local platform. A bounded volatile sample window must display
its gaps and retention limits; it must not imply durable historical coverage.

This deferral applies to monitoring observations, not to persistent searchable
SQL history (FB-COMP-05), saved dashboard definitions, DDN design assets or saved
test-data recipes. Those persistence requirements remain in this run. Completing
a draft editor alone does not complete dashboard publication or FB-COMP-18.


Qualified definition publication
---------------------------------

Publishing is a separate explicit operation from draft save. It names the saved
source version and expected current publication version. The server validates
that saved source with the paired DDN runtime, checks the selected view and every
other view, and admits only fixed observation bindings for its scope. The
published asset is a separate immutable DDN revision. Saving later drafts does
not change it. A stale publication version conflicts. Collection permissions,
policies and native state are unaffected by publication.

The initial binding contract is ``firebird-observations-v1``: one dashboard.ddn
file, one observations block, string-valued value/unit/rate records, no imports,
and only the known record identifiers for engine summaries, server metrics or
database metrics. Arbitrary queries, routes and new data blocks are not bindings.
Unbound source record values are replaced with unavailable placeholders before
publication. Live values come only from the authorized current snapshot, replace
records by stable key using DDN's public replaceData API, and never enter the
saved publication. Invalid layouts or refreshes show an error, not old telemetry.
Engine summary customization initially covers the fixed inventory/coverage
measures; per-endpoint detail layout customization remains separate work.

A host Node.js executable (configured with CDEADMIN_DDN_NODE, default node) runs
the shipped validator against the vendored paired DDN library. No browser-supplied
executable, command or script is executed. Validation is bounded to 512 KiB of
source, 128 MiB JavaScript heap, eight seconds and two simultaneous validators, with a bounded cache of
validated snapshots. Missing runtime or invalid DDN fails publication closed.
The live definition endpoint revalidates stored publication content, including
writes through generic project-asset APIs. Viewers fetch a coherent published
revision during refresh and remain passive; first-time scopes without a published
asset use the standard dashboard. Publication refusal never replaces the previous
published revision. Monitoring history remains outside this run.

Retained-sample inspection and scoped navigation
------------------------------------------------

Engine dashboards provide read-only navigation to registered server and database
dashboards. Server dashboards list their registered targets, and database views
can return to their server. Navigation passes registration/target identity, not
an attached-file path; an attached file alone is not a navigable registration.
Every destination reauthorizes its reads. Opening a destination does not admit
collection or change policy. This navigation is available with standard and
published layouts.

A separate read-only recent-observations surface uses the existing volatile
buffer. Users select an admitted metric and the last 30, 120 or up to 720 retained
samples; these controls change only the view. The host stamps accepted samples
with elapsed monotonic time within the collection revision; connection epochs
identify source reconnects. Samples are plotted as individual observations,
never interpolating across unavailable periods. Exact native decimal text,
receipt timestamp, coverage, epoch and gap reason remain available in a DDN
table. Large values outside JavaScript's safe numeric range stay in the table
and are explicitly excluded from approximate chart geometry. Counter rates use
the provider's comparable-epoch deltas, never differences recomputed by viewers.
No rate is plotted for a missing/reset epoch. Retention evictions and stopped or
stale collection are visible; old samples are explicitly past observations, not
current availability. The feature supplies no durable history or cross-endpoint
aggregate and introduces no ScratchBird connection.

Dedicated monitoring account configuration
-------------------------------------------

The separate collection-policy form offers registration credentials or a
dedicated monitoring username, password and optional role. Dedicated credentials
authenticate only the independent native collector; they never update the server
registration or the user's attachment. The admitted endpoint, database target,
transport and current owner authorization remain fixed by registration. A supplied
account cannot override host, port or database. Dedicated password authentication
disables inherited trusted authentication and does not inherit the user's role.

The current process-local policy accepts the password only on authenticated
start, seals it with the worker key, and returns only account/mode/role metadata.
It is not written to project assets, policy snapshots, or logs; the form clears
its password after submission, including failures. Deployment must protect
credential-bearing requests with HTTPS outside local development. Collection
continues without a browser or interactive attachment, subject to its lease and
authorization. Restart loses the grant and requires explicit credential admission.

Credential changes require Stop, confirmed release, then Start with the new
account. An existing worker cannot silently accept replacement credentials.
A failed native login is a failed collection observation, never a successful
availability heartbeat. No native account is created and no privilege is granted
implicitly. Insufficient visibility remains explicit in the measurements.

Bounded native activity inspection
----------------------------------

Each dedicated database sample includes up to 100 visible attachment, transaction
and statement identity rows from its fresh MON$ snapshot. The collector's own
attachment and its transactions/statements are excluded. Query ordering is stable
(oldest native timestamp first, then ID); a 101st row signals truncation. Each
category reports its own availability and limit. These lists are not a complete
inventory when truncated or permission-limited. They use the same snapshot and
coverage as the overview and do not execute additional queries when opened.

The passive DDN activity form selects a category and displays native IDs, states,
user/role, timing and transaction properties. State 2 for a statement is stalled,
not evidence of a lock wait. Native timestamps are shown as returned by Firebird,
without inventing timezone information. SQL text, plans, context variables and
SEC$ personal attributes are not collected by this list. Opening future SQL/plan
inspection requires a separate bounded, authorized detail operation. Source
freshness, collector identity and truncation remain visible.

The retained trend selector includes all admitted database I/O and record-counter
rates, memory gauges/high-water values, active/idle attachments, transaction
counts/oldest age, allocated/configured cache bytes, and the three MGA transaction
number distances. Gauges retain source-connection epochs; rates use counter
epochs. Underflowed nonzero decimals are omitted from numeric geometry while
their exact source values remain in the observation table.

On-demand native statement inspection
--------------------------------------

An explicit read-only activity action retrieves SQL text and explained plan for
one statement observed in the latest authorized sample. The request binds sample,
collector connection epoch, attachment, statement, compiled statement and native
timestamp. Reused, changed, disappeared or out-of-scope identities do not return
replacement statement text. Stop, lease expiry or revoked authorization during
the read prevents publication of the result. This action uses the existing
independent collector attachment under its serialization lock and ends its fresh
read-only MON$ transaction immediately. It never uses or refreshes user sessions.

Each text is bounded to 4096 native characters with explicit truncation. The
native server applies SUBSTRING and a bounded UTF-8 cast before transfer; the
client must not first materialize an unbounded BLOB. SQL text can contain values;
it is fetched only by this explicit authorized action, not included in periodic
samples, volatile trends, persistent history or logs. The passive activity form
shows the observed identity, inspection time, availability and truncation. It has
no execute, cancel-statement or connection-administration controls. Inspection
does not count as a scheduled availability heartbeat.

Passive DDN sections retain their rendered content height inside the dashboard's
scrolling container. Activity, statement inspection and the standard metrics
must remain separate, reachable sections when all are open; a fixed editor-sized
viewer must not overlap or obscure another section. The standalone interactive
diagram viewer keeps its own bounded viewport.

Bounded native inventory sampling
--------------------------------

The dedicated database collector samples compiled-statement identities, client
transport attributes and group-zero table counters without collecting SQL BLOBs.
Metadata inventories (schema health, security counts, physical backup history,
publications and secondary files) refresh every 60 seconds independently of the
activity cadence. Each inventory carries its own observation time; cached facts
are never presented as newly observed. Reconnecting invalidates this cache.
Every list has a 100-row display bound and an additional sentinel for truncation.
Optional native-query failures remain unavailable, including permission failures;
they are not converted to empty inventories. All queries share the collector's
fresh read-only transaction, which is rolled back after each sample.

Observed endpoint totals deduplicate registrations only when both native GUID and
file identity match within that endpoint. Cross-endpoint observations are not
asserted to be distinct physical databases: a copied database may retain its GUID
and multiple registered endpoints may reach the same host. Unknown identities
remain visible but do not contribute to these sums. Each metric carries its own
observed/identified database denominator. Stale, denied or failed samples supply
neither current identities nor current metric values. Integer and decimal totals
are serialized as exact strings. Database memory remains database memory, not
server RSS. These observations have independent sample times, not an atomic
server-wide snapshot.

Metadata sampling policy accepts 60 through 3600 seconds (default 60). Refresh
occurs on the next activity sample after that interval, not through another
transaction running between samples. Schema field counts include implicit native
field definitions; constraints/dependencies without their own system flag report
an unknown system classification rather than inventing a user/system split.

Native page-use information is sampled at the metadata cadence. Firebird may
inspect allocation pages to answer these requests; the result is an independent
attachment-info observation, not an atomic extension of the MON$ snapshot.
Used/free values count native allocated database pages, never host filesystem
free space. Protection details retain native crypt-page, crypt/backup/replica
flags and security-database classification without treating them as percentages,
replication lag or a unique security-file identity. Role/grant/local-mapping
matrices are bounded native-visible inventories, distinct from opt-in SEC$ user
personal attributes.

Compiled statement SQL/plan inspection uses the same explicit authorization and
bounded-text rules as request inspection. It binds the latest sample, collector
epoch, compiled ID, object/package identity and native statistics identity.
Disappearance or changed identity returns no replacement text. This includes
compiled objects visible to the monitoring account; it does not infer cache hit
rates or bypass native monitoring visibility. Compiled SQL/plan text is never
part of the periodic inventory or its retained trend buffer.

Firebird statistics IDs are snapshot-local join keys, not persistent object
identities. The native monitoring producer allocates them afresh while dumping
statistics (Firebird5 Monitoring.cpp). Do not use their equality across fresh
transactions as a continuity or object-reuse check. Compiled inspection uses the
native database-generated compiled ID plus object/package identity and collector
epoch; the submitted statistics ID is checked only against its referenced sample.
Table series use native relation ID/name within the collector epoch, while record
statistics IDs join the two MON$ sources only inside each individual snapshot.

Attention policy is explicit: the maximum transaction age and prolonged-backup
observation threshold are disabled at zero; expected encryption state is optional;
requiring encrypted wire attachments is separately enabled. Findings cite their
sample and threshold. Backup duration is only the continuously observed lower
bound within the current collector epoch, not the start time of an external
backup. A missing, failed or changed-epoch observation breaks that duration.
Conflicts report the interval's actual counter delta, not failed committed rows.
Unavailable/stale scope findings remain distinct from a healthy empty queue.

Explicit monitoring detail requests bind a recent sample from the current
collector epoch and active lease and reauthorize both before and after I/O. Server log inspection opens its
own service handle, reads at most 64 KiB/1000 lines with a five-second observation
budget, and releases it even when truncated or interrupted. This is a bounded
prefix of the native server log, not a tail, complete log or periodic history.
Server path inspection is an explicit authorized service-information operation.
Database account inspection explicitly returns up to100 visible SEC$ user rows;
personal name fields are read only for that request. Neither operation is a
heartbeat, user-session transaction, persistent log or automatic remediation.

Local operation receipt inspection reads the existing owner/endpoint-scoped
operation audit store, not a monitoring history store. It does not require a
running native collector. At most100 recent Firebird records are projected;
database views include only records with an exact observed database destination
matching that registration. Unattributed/server-wide receipts remain on the server
view. Native-returned, unknown-outcome, post-state-required and service-release
facts remain distinct; no receipt implies independent restore verification.
Absence or truncation of this local audit says nothing about external tools.

Ranked charts use only the bounded observations actually captured. Table rankings
must say when the native name-ordered capture was truncated; they cannot claim
to identify the busiest table outside that coverage. Sort exact decimal values
before choosing the top20, preserve exact values in the accompanying table, and
omit numeric geometry outside the renderer's safe range. The current paired DDN
chart renderer supplies its standard categorical bar orientation; ScratchRobin
uses that public projection rather than implementing a separate chart renderer.

Request SQL/plan inspection also reads at most100 MON$CALL_STACK entries for that
same verified statement in the same fresh monitoring snapshot. The read-only
panel shows caller identity, native object/package and source line/column.
An empty visible stack is not evidence that no PSQL executed earlier. Compiled
inventory inspection does not fabricate a running call stack.

An endpoint rate total is available only when contributing rate windows have
identical recorded observation times and elapsed durations. Independent collectors
normally have different windows; show their individual rates and window evidence
instead of silently summing noncomparable averages. Allocation and attachment
count totals remain explicitly independent observations with per-metric coverage.

Account/path/log drill requests accept one of the latest three retained samples
from the current source epoch. Collection may advance between viewer refresh and
click; a normal new sample must not invalidate this independent fresh read. A
reconnect, different epoch, ended lease or revoked grant still refuses the read.
Statement identity inspection retains its separate exact sampled-object checks.

The engine viewer includes registered-endpoint version/architecture distribution,
exact-ranked observed database allocation/workload, and an explicit database
selector for retained workload trends. The selector reads existing authorized
buffers only; it never starts a collector or mixes independent transaction
windows into a synthetic history. Publication detail includes a DDN relationship
view of captured native publication/table membership, with independent truncation
and unavailable-attribute indications. It does not invent replica endpoints.
