MySQL engine functional completion
==================================

Product-wide catalog, editor and complete native management acceptance is
defined in :doc:`six_engine_completion`. The scoped receipts below do not close
the open requirements recorded there.

The current target is native MySQL 9.7.0 with Connector/Python 26.7.0.
MariaDB is a separate engine and is not accepted as MySQL qualification.
This checklist governs completion alongside ``mysql_driver_development.rst``,
``ddn_database_roundtrip.rst`` and the shared navigation/form contracts.
Existing experimental provider receipts establish only their recorded scope.
Completion requires current source and live UI evidence for every item below.

Owner direction, 2026-10-22: the eleven comparison-derived workflows in
:doc:`mysql_implementation_priorities` are accepted implementation work alongside
the current MySQL beta backlog. That document defines their ordering, native
acceptance and the completion checkpoint for switching development to MariaDB.
Recording these requirements does not qualify or complete their implementation.

Current comparison checkpoint
------------------------------

All eleven accepted comparison workflows are implemented and Linux-qualified.
Permanent recovered-service staging and reviewed background activation now close
``CMP-MY-01`` alongside the previously qualified production topology/host scope.
``INV-MYSQL`` remains an independent gate; comparison completion does not declare
full native product or cross-platform acceptance. Later evidence sections retain
the qualification limits recorded at their original checkpoint.

Acceptance requirements
-----------------------

MYSQL-COMP-01: Native navigation and administration
  Discover server/database/schema objects and their native children. Preserve
  database/schema equivalence in MySQL rather than inventing an extra namespace.
  Cover tables, views, materialized views where admitted by the selected server,
  columns, constraints, indexes, partitions, triggers, routines, events,
  security, storage, plugins/components, replication and system configuration.
  Gate edition/version/privilege-dependent objects explicitly. Support native
  properties, creation, alteration, removal, dependencies and grants where
  supported. A missing privilege or failed discovery is not an empty catalog.

MYSQL-COMP-02: Connection ownership and credentials
  Explorer, active connection selector and SQL sessions agree on connected
  state and exact database. Support explicit connect/disconnect and independently
  owned sessions on two databases. Cover authentication, TLS, cancellation,
  pool lease retirement and uncertain outcomes without reconnect/replay.

MYSQL-COMP-03: Shared SQL editor and script tools
  Use the shared compact editor, engine-labelled connection selection, native
  language validation, completion, parameter binding, scripts and file tools.
  Provide bounded result pages, typed values, diagnostics, native JSON/analyze
  plans and honestly scoped timing. Observe native autocommit before enabling
  commit/rollback. Refuse a policy change with pending work. Preserve unknown
  outcomes. SQL history is optional, persistent and owner/server/database/native
  language scoped; loading text must never execute it. History failure cannot
  prevent or replay execution. Credentials, bound values and result rows are
  excluded; explicit sensitive-source suppression and bounded retention apply.

MYSQL-COMP-04: Data operations and maintenance
  Qualify native editing, commit/rollback, paging, exact values, LOBs, export,
  import and test data. Qualify database lifecycle, maintenance and native
  MySQL Shell backup/restore with rediscovery and independent verification.
  Describe implicit DDL commits and nontransactional engine effects accurately.

MYSQL-COMP-05: DDN roundtrip
  Capture selected objects, databases and server metadata/data on independent
  connections. Preserve native definitions, exact identifiers/types/options,
  dependencies, security and scope/permission observations. Expose DDN views
  through the sister project's tools. Generate native definitions and reviewed
  semantic diff/apply plans with target/digest/revalidation and rediscovery.
  View filtering never authorizes deletion. MySQL catalog reads do not imply
  an atomic DDL snapshot; partial observations cannot authorize destructive apply.

MYSQL-COMP-06: Monitoring and dashboards
  Provide engine/server/database display-only DDN dashboards and separately
  authorized dashboard editing. Collect on dedicated connections, using either
  registration credentials or configurable monitoring credentials. Configure
  heartbeat and sample/retention/lease policies. Refresh transaction scope for
  each sample; collection continues without an open viewer. Distinguish denied,
  unavailable and zero metrics; retain a bounded volatile sample window and
  opt-in persistent history in the native ScratchBird archive. Historical reads
  require current owner/registration authorization, not an active collector or
  browser credential grant. Preserve exact values, epochs, metadata revisions,
  retention, rollups and ingestion gaps.

MYSQL-COMP-07: Forms and routing
  Context menus must lead to engine-appropriate compact forms with stable form
  references. Share appropriate controls without exposing unsupported engine
  features. Use checkboxes/selectors/icon buttons and bounded navigable grids;
  keep destructive operations reviewed and exact-target scoped.

MYSQL-COMP-08: Qualification
  Run native and browser acceptance on the exact engine, including independent
  sessions/databases, restricted privileges, disconnect/cancel, native object
  lifecycle, backup/restore, DDN roundtrip/apply and collector credentials.
  Refresh consumed DDN before builds and commit qualification, preserve logs
  outside the repository and clean owned disposable fixtures. Unit tests or
  old activation gates alone do not establish full support.

Implementation and qualification
--------------------------------

Graphical native query plans
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The MySQL SQL toolbar provides JSON and TREE optimizer estimates, and separate
TREE and JSON execution-plan actions labelled **executes query**. Analysis runs
on the selected SQL session with its existing bindings and transaction policy.
The application does not switch native session settings to make a format work.
In particular, JSON analysis requires the native JSON version 2 setting; native
format or privilege refusals remain errors, not successful plan observations.

The Explain tab presents connected, selectable native plan nodes. JSON version
1 keeps its query-block hierarchy; version 2 keeps its access-path inputs. TREE
uses the native indentation and operator descriptions, including never-executed
branches. Selected facts retain native field names, exact numeric tokens, NULL
and zero distinctions. Costs are not converted to milliseconds or summed across
operators. The original EXPLAIN text remains available unchanged. Selecting or
collapsing nodes sends no SQL. Graph availability does not establish successful
execution, commit, rollback or cancellation; incomplete/error observations stay
separate from returned plan text.

Graphical admission requires one native EXPLAIN text cell and bounds the plan
to 4 MiB, 500 nodes and 64 nesting levels. Unsupported/malformed plans and
larger graphs retain the original result instead of inventing an operator tree.
Other engines keep their owning native plan presentations.

``tools/cdeadmin_mysql_query_plans_qualification.py`` qualifies MySQL 9.7.0 on
both pure and C connector paths through authenticated workspace requests and
the production graph parser. It covers JSON v1/v2, JSON/TREE analysis, native
join inputs, estimate versus explicit-analysis session effects, native errors,
subsequent explicit session use and a pending transaction/savepoint. Its built
desktop path checks all four toolbar actions and native operator inspection.
The recorded acceptance is Linux only; platform-team acceptance remains
separate. Refresh paired DDN before builds/tests and keep the output outside
the repository, for example::

   python tools/cdeadmin_mysql_query_plans_qualification.py \
     --output /absolute/work-area/mysql-query-plans \
     --browser-binary /absolute/path/to/chrome \
     --driver-binary /absolute/path/to/chromedriver

These receipts close ``CMP-MY-04`` in its accepted implementation scope. They
do not close the broader editor/capability inventory or the MySQL product matrix.

Native workload performance analysis
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The server's **Diagnostics and verification** menu opens **MySQL workload
analysis**. Its observations own separate,
autocommit connections and do not consume an interactive pool lease or change
the user's transaction, savepoints or SQL diagnostics. Statement digests can be
ranked by total/mean latency, executions, examined rows, temporary tables and
disk temporary tables. Native integer counters and picosecond timers remain
exact strings. The top-100 limit, permission failures, native NULL overflow
bucket, first/last-seen times and native quantiles remain explicit.

Instrumentation coverage includes native consumers, enabled/timed instrument
counts, digest capacity/length, lost digests, uptime and slow-log settings.
Empty rows do not establish an idle server or complete instrumentation. Native
summaries are cumulative. Collectors report observed first-seen changes and
counter decreases across matching digests. MySQL provides no authoritative
timestamp for every summary reset, so undetected resets remain possible; rates
and uninterrupted measurement windows are not inferred. Workload collection
uses the existing metadata cadence and continues under the separate policy
without an open viewer. MariaDB retains its own collector behavior.

The DDN display shows server waits and scoped native index activity. These
aggregates are not attributed to a selected digest. Digest drilldown separately
joins directly nested waits still present in both native long history rings;
disabled, denied, evicted and stage-nested events remain coverage gaps. Existing
dashboard publications use stable, admitted native workload bindings and strip
observed values when definitions are saved. Viewers remain display-only.

Private SQL samples require endpoint administration authority and explicit
inspection consent. They are absent from routine collector samples and SQL
history. Plan capture rechecks the displayed sample fingerprint, admits one
native EXPLAIN statement and reuses the native graphical-plan presentation.
It uses the observer's current settings, not the original execution session's
settings. It requests optimizer estimates; native optimizer expression effects
remain possible and explicit execution analysis stays in the SQL editor.
Private responses are not cached or persisted; clearing them removes the sample
and plan. Native server logging remains controlled by MySQL.

Slow-log analysis selects one schema and an explicit UTC window of at most
24 hours. TABLE input admits the latest 100 matching native log entries with a
native execution-time bound. File input admits at most 1 MiB / 500 complete UTF-8
long-format entries, requires native schema context and refuses ambiguous or
partial framing. Native ``STATEMENT_DIGEST`` and ``STATEMENT_DIGEST_TEXT``
normalize bound SQL data without executing it. Non-SQL administrator commands
and syntax rejected by the native digest parser are counted separately with
source-free native error codes. Raw SQL is not retained. Results disclose their
input window, bounds and normalization gaps; they do not claim complete server
workload coverage or inspect arbitrary server-host paths.

``tools/cdeadmin_mysql_workload_qualification.py`` exercises the real MySQL
9.7.0 pure and C connectors through authenticated workspace requests, native
slow-log sources, an independent transaction/diagnostic oracle and the built
desktop. Output belongs outside the repository. ScratchBird persistent-history
qualification remains owner-deferred; Windows/macOS acceptance remains with
the platform teams.

Linux pure/C native and built-desktop receipts close ``CMP-MY-03`` in its
accepted implementation scope. The broader MySQL product matrix remains open.

Native database content search
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The endpoint **Diagnostics and verification** menu opens **MySQL database
content search**. Explicit discovery lists native permission-filtered databases,
base tables and columns. A private search admits up to 64 selected tables and
256 columns, 500 matches and 60 seconds. Catalog pages disclose their scope;
invisible objects remain unknown. Views and session temporary tables are outside
this workflow.

Text equality, literal prefix/contains, exact numeric equality, binary
hex equality/contains and NULL comparisons have separate native rules. Text
preserves column collation and padding behavior; JSON and temporal text use
native conversion. Exact integer/decimal values remain exact native parameters;
FLOAT/DOUBLE use native approximate comparison. Inapplicable types or native
conversion warnings produce explicit unsearched scope. Indexed-only mode checks
the native EXPLAIN plan and skips table and full-index scans. It does not promise
that every admitted index lookup is inexpensive.

Each search owns independent authenticated worker and cancellation connections.
Each selected table is read under its own read-only transaction and metadata
lock after structural identity revalidation. The report distinguishes searched,
denied, skipped, timed-out and bounded scope; no database-wide snapshot is
claimed. Nontransactional engines retain their native visibility limitations.
Cancellation confirms the owned server/thread identity before KILL QUERY;
unconfirmed threads wait for bounded native/cooperative completion. Interactive
transactions, savepoints and diagnostics remain independent.

Matches contain bounded previews and exact source names/fingerprints. Opening a
row requires a fully readable, nonnullable native unique key, retains native key
types and revalidates the server/account/role and structure. It reads current
values; it is not a historical row version or immutable physical object ID.
Keyless or unreadable-key matches explicitly disable navigation. Row previews
admit 100 readable columns and always include the matched column.

Private criteria, previews and locators remain in process memory for at most
five minutes, with explicit clear and periodic expiry. They are not written to
SQL history, operation receipts or the persistent collector. Responses disable
caching. Native server logging still applies. Changing the registered target or
closing the workspace cancels active work and discards late browser responses.

``tools/cdeadmin_mysql_content_search_qualification.py`` exercises real MySQL
9.7.0 through authenticated workspace requests with the actual pure and C
connector classes. It checks Unicode/literal text, exact unsigned/decimal/binary
values, zero dates and extended times, native index plans, column grants, stale
DDL identities, bounds, cancellation and independent interactive diagnostics.
Its optional built-browser path opens the provider menu, searches, navigates,
checks escaped previews and clears private results. Evidence belongs outside
the repository; Windows/macOS acceptance remains with the platform teams.

Linux pure/C native and built-desktop receipts close ``CMP-MY-07`` in its
accepted implementation scope. The broader MySQL product matrix remains open.

Controlled DDN table changes
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The database **MySQL metadata and DDN diagrams** workspace retains its existing
baseline/desired/live comparison, native validation and durable review. Select
**Controlled native ALTER** to bind an explicit INSTANT, INPLACE or COPY algorithm,
LOCK expectation, metadata-lock wait and runtime budget to one existing table.
INSTANT requires LOCK=DEFAULT. Other combinations remain subject to native
refusal. PREPARE is grammar/semantic preparation, not proof that an algorithm can
execute online. The application never retries with weaker ALGORITHM/LOCK values.

Controlled jobs own independent worker/control connections and use a cooperating
advisory lock in place of a duration-long table WRITE lock. Prevent other DDL
throughout the operation; the advisory lock fences cooperating controlled jobs,
not every administration path. Exact native server UUID, target names and
structural baseline are rechecked. The volatile next AUTO_INCREMENT counter is
excluded from structural comparison without removing text inside literals.
Native ALGORITHM/LOCK governs concurrent DML; brief metadata locks still occur.
MySQL owns implicit commits and native DDL atomicity. Cancellation confirms the
owned server/thread identity before KILL QUERY and never implies rollback.

Jobs retain native stages/work counters when instrumentation supplies them,
explicit unavailable coverage, error codes/SQLSTATE, dispatch and acknowledgement
facts. A lost worker or reply remains uncertain and is not automatically
redispatched. Reading the receipt or observing the current native table does not
rewrite the original outcome. Closing a workspace leaves an admitted job running;
explicit cancellation and runtime limits remain separate actions.

**Percona online copy** integrates the pinned source-available
``pt-online-schema-change`` 3.7.2 script with the existing independent utility
supervisor. The application host requires native Perl, DBI and DBD::mysql.
Install the exact script and license with::

   python tools/install_mysql_online_schema_tool.py \
     --destination tools/reference_engine_demos/runtime/percona-toolkit

The default runtime path is the installed ``bin/pt-online-schema-change``.
``CDEADMIN_MYSQL_ONLINE_SCHEMA_TOOL``, ``CDEADMIN_MYSQL_ONLINE_PERL`` and optional
``CDEADMIN_MYSQL_ONLINE_PERL_INCLUDE`` select an application-host installation.
Review binds its exact script/hook hashes, source revision, Perl executable and
module versions. A private copy is checked again before execution. Arbitrary
scripts and flags are not accepted from the browser. Passwords use a private
option file whose cleanup belongs to the independent supervisor; they do not
enter command arguments, reviews or saved policy.

The admitted copy profile covers InnoDB under UTF-8 DDN statement context on a
standalone instance or an asynchronous source with explicitly registered replica
channels. Native incoming/group replication and unadmitted reported replicas
refuse this copy profile; native ALTER remains a separate workflow. Native
privileges, unique-key requirements and unsupported alterations remain tool/server
refusals. This is not blanket qualification of every upstream utility option or
topology. Preserve the separate broader topology and capability inventories.

Copy binds existing triggers and referencing foreign-key definitions, uses native
trigger preservation and ``rebuild_constraints``, and reports that foreign-key
names can change. It copies through native statements and synchronization
triggers, then waits for a separate **Allow reviewed copy cutover** action.
Native RENAME acknowledgement is retained even if later utility cleanup fails.
Process exit alone is not database finality. Native process output and independent
current table/trigger artifact observations remain available; no uncertain
artifact is automatically removed.

Registered replica observers use independent authenticated connections and
credentials, never utility discovery/delegation to unknown hosts. Source UUID,
replica UUID/account, channel and registration configuration are bound at review
and rechecked at start. Stopped, denied, unknown or excessive native lag pauses
between copy chunks. Cutover checks the channels again. The source's observed
replica list must be admitted; hidden/unreported topology remains unknown. Native
load policy pauses above 25 running threads and aborts above 50. Observer heartbeat
loss aborts the copy hook; the independent supervisor retains process completion
and credential cleanup evidence after application-worker loss.

Current qualification entry points are
``tools/cdeadmin_mysql_online_ddl_qualification.py --online-copy``, its
``--desktop-only --browser-binary ... --driver-binary ...`` path, and
``tools/cdeadmin_mysql_online_replica_qualification.py``. Record evidence outside
the repository. Linux pure/C native, source-utility and desktop scopes remain
separate from Windows/macOS platform-team acceptance and owner-deferred
ScratchBird history qualification.

Linux native pure/C, registered-replica and built-desktop receipts close
``CMP-MY-05`` for these admitted profiles. The independent native oracle verifies
post-cutover definitions/data. Interrupted copies retain their original unknown
outcome alongside observed process completion, credential cleanup and remaining
table/trigger artifacts. Broader MySQL inventory, recovery and lifecycle gates
remain open; complete-table drift and alert workflows have subsequent qualified sections below.

Native full-table and replica data drift
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The endpoint **Diagnostics and verification → MySQL full-table data comparison**
workspace independently admits both registered endpoints, databases and complete
base-table pairs. Observe each native table, add its exact identity and confirm
the read-lock/scan scope. Owner, registrations, native identities and complete
logical-column metadata are checked at execution. Catalog visibility is
permission filtered; unselected or invisible tables remain unknown.

**InnoDB native snapshots** acquires server-wide native read locks on both
endpoints, records GTID/binary-log positions, establishes read-only repeatable-read
consistent snapshots and pins every selected table with metadata locks. It
releases the global locks before scanning. Concurrent DML can continue; retained
snapshots can retain undo versions. **Hold server read locks through scans**
retains those locks for admitted local engines: InnoDB, MyISAM, MEMORY, CSV,
ARCHIVE, MRG_MYISAM and BLACKHOLE. External/distributed writers have no admitted
consistency profile. Native privileges, lock waits and unsupported profiles are
reported without fallback. The native account needs complete table reads,
server read-lock privileges and position inspection privileges.

Optional replica alignment binds the explicit registered target/channel to the
native source UUID, requires GTID mode ON and a running channel, waits for the
recorded source set while source writes are blocked, and rechecks the applied
set after acquiring the target lock. The target snapshot retains its recorded
local/other-channel transactions. Source GTID coverage does not prove those
transactions or replication filters are absent. The workflow compares the
admitted endpoint directly without credential delegation or discovery of other
members. Independent snapshots do not assert replication alignment.

All logical columns, including invisible/generated columns, and all rows are
scanned. Native SHA256 projections preserve binary text, exact decimal/temporal,
JSON, geometry and vector representations. ENUM/SET use native numeric indices;
binary prepared results preserve FLOAT/DOUBLE IEEE values. Logical column names,
order, types, generation and collations must match. Physical storage bytes,
index/constraint parity and CHAR storage padding are separate checks. Native
warnings prevent a completed table result.

Native unique keys order keyed scans and identify bounded private mismatch
examples. Keyless tables use complete duplicate-aware row multisets. Fixed-size
fetch batches, bounded external sorting and SHA256 row digests retain duplicate
multiplicity. Matching counts or sampled rows do not establish a match. Results
are cryptographic checksum comparisons, not collision-free mathematical proofs
of physical byte equality. Reports retain full scanned-row and source-only/
target-only row-version counts, key coverage, native positions and release
observations. Schema differences, changed identities, denied reads, cancellation,
deadlines and exhausted sort space remain incomplete or uncomparable.

Limits are 1–64 table pairs, 16384 total observed columns, 1–86400 execution
seconds, 1–4096 MiB private sort space and 0–200 mismatch examples across the job.
Four active comparisons and 32 retained reports are admitted per process.
Temporary runs are private and removed at completion; abandoned runs are removed
after process-identity validation at startup. Private reports/key examples expire
five minutes after completion, with explicit clearing and deliberate JSON
download. Native server logging remains native. No SQL/history persistence or
repair is dispatched. Repairs use the existing native table data editor with a
separate review against its exact current target.

Cancellation verifies owned native worker identities before KILL QUERY. Cleanup
retains unlock/rollback replies and session-disposal observations. Closing the
workspace requests cancellation; native runtime limits continue if delivery
fails. Qualification entry points are
``tools/cdeadmin_mysql_drift_qualification.py`` and
``tools/cdeadmin_mysql_drift_desktop_qualification.py``. Preserve evidence outside
the repository. Windows/macOS acceptance remains with the platform teams;
ScratchBird history qualification remains owner-deferred.

Linux pure/C native/API receipts qualify InnoDB snapshots and MyISAM locked
scans, all admitted native type projections, equal-count duplicate drift,
adjacent IEEE values, GTID alignment and stopped-channel refusal, changed
structures, concurrent committed DML, sort limits and native cancellation.
Independent user transactions, savepoints and warning areas remain intact.
Built-desktop receipts qualify matched/different reports, deliberate report
download, clearing and an independent native oracle confirming no repair writes.
These scopes close ``CMP-MY-06``. Broader native inventory, recovery/lifecycle and
platform acceptance remain open; notebook qualification is recorded below.

The pinned Percona Toolkit 3.7.2 checksum source requires statement-based logging
and has replication-format/topology restrictions. It is not selected as this
workflow's backend. See `Percona checksum limitations
<https://docs.percona.com/percona-toolkit/pt-table-checksum.html#limitations>`_.

Native MySQL alert policies
~~~~~~~~~~~~~~~~~~~~~~~~~~~

The MySQL collection policy screen now configures eleven native threshold and
duration metrics, severity, missing-observation behavior and fixed notification
routes. Independent collectors evaluate pending, firing, resolved, unknown and
silenced states without any open viewer. Native identity/counter resets, stale
or denied groups, missing denominators and missed collection windows break
continuity. Scheduled failure backoff remains valid outage-duration evidence.
Findings carry exact values, source/sample identities and diagnostic next steps;
no automatic remediation is dispatched.

Silence/unsilence controls are owner- and grant-authorized. DDN dashboards expose
current read-only alert bindings. A bounded independent delivery worker rechecks
the grant, scope, silence and admitted destination before authenticated TLS SMTP
submission. Existing durable idempotent report-delivery occurrences retain
successful, failed and outcome-unknown receipts; uncertain submission is not
retried automatically. Alert rules, state, silences and 100 recent transitions
belong to the collector process/lease. See :doc:`mysql_alerts` for admission,
privileges, setup and operational limits.

Linux MySQL 9.7.0 qualification on both native Connector/Python interfaces covers
actual SMTP JSON attachments and lost acknowledgement, native InnoDB contention,
status-counter reset, stopped/failed replication, denied measurements and live
registration revocation. Existing interactive transactions, savepoints and
warning areas remain intact. Built-desktop acceptance qualifies rule setup,
firing/delivery receipts, silence/unsilence, a read-only DDN findings display and
collector stop/release. These receipts close ``CMP-MY-08`` on Linux. Three accepted
comparison workflows and broader MySQL inventory/recovery/lifecycle gaps remain
open; owner-deferred history and platform-team acceptance remain separate.

Native spatial data inspection
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The server or registered database **Diagnostics and verification → MySQL spatial
data inspection** workspace now provides native geometry/WKB inspection and a
bounded DDN map. Native ST_GeomFromWKB, ST_AsText, ST_AsGeoJSON, ST_IsValid and
ST_Transform preserve SRID and axis-order semantics. Original source bytes stay
available for deliberate binary download; native errors and null, empty,
invalid, malformed and oversized values retain distinct coverage/fallback
states. No source data is modified, persisted or sent to an external tile host.
See :doc:`mysql_spatial_inspection` for selection, coordinate modes, snapshots,
bounds and the recorded consumed-dependency adjustment.

Linux MySQL 9.7.0 qualification with both corrected Connector/Python 26.7.0
interfaces covers all native geometry types, lines/collections/polygon holes,
asymmetric geographic axes, projected-to-WGS84 transformation, malformed and
big-endian WKB, unknown SRIDs, native privilege refusals, source fingerprints,
page/map bounds and independent transaction/savepoint/warning preservation.
The built desktop renders the paired DDN map, distinguishes native SRS and X/Y
text, downloads byte-identical internal geometry and clears private results.
Network evidence confirms no external map/tile requests. This closes
``CMP-MY-09`` on Linux; three accepted comparison workflows and broader native
inventory/recovery/lifecycle gaps remain open. Windows/macOS acceptance remains
with the platform teams, and ScratchBird history testing remains owner-deferred.

Versioned native schema deployment automation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``tools/cdeadmin_mysql_deploy.py`` now provides capture, versioned packaging,
headless plan/validation, durable review, explicitly approved apply and original
receipt lookup over the existing MySQL DDN services. Each environment retains
its own exact native baseline/desired pair and owner/registration/target/server
binding. Artifact and ticket hashes, native review matching and recompilation of
the artifact's intended operations prevent relabelled or cross-environment
review reuse. No schema/SQL/definer rewriting or deletion authority is inferred
from deployment selection. See :doc:`mysql_schema_deployment` for the supported
local operator boundary, private outputs, JSON/exit contracts and limits.

Linux qualification covers actual subprocess deployment on independent native
MySQL 9.7.0 environments using both corrected Connector/Python 26.7.0 interfaces.
Native rediscovery, original data, independent pending transactions, savepoints
and warning areas are checked. Wrong-environment tickets, altered fingerprints,
three-way drift, duplicate apply and original receipt retrieval are qualified.
Abrupt CLI loss after the durable claim retains uncertainty across restart and
never redispatches the original review. Controlled native INSTANT, an actual
INPLACE refusal and pinned Percona Toolkit 3.7.2 copy with explicitly approved
cutover also pass. These scopes close ``CMP-MY-10`` on Linux. One accepted
comparison workflow and broader native inventory/recovery/lifecycle gaps remain
open. Platform-team qualification and owner-deferred ScratchBird history stay
separate.

SQL notebooks and investigations
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Native MySQL SQL workspaces and Project Explorer share notes, SQL cells and
explicitly retained result snapshots through existing versioned project assets.
Connection binding and cell execution are deliberate actions; opening, saving,
importing or sharing never executes SQL. Native editor completion, diagnostics,
session transactions and cancellation remain available. Selected snapshot
columns can be omitted, redacted or retained, with bounded rows and exact
SQL/connection provenance. Portable exports strip local bindings and require
review of saved content; imports are unbound and inert. Concurrent revisions,
shared viewer permissions, dirty drafts and earlier-revision sharing are
handled explicitly. See :doc:`mysql_sql_notebooks` for workflow and privacy
limits, including retained older project revisions.

Native MySQL 9.7.0 pure/C/API and built desktop receipts close ``CMP-MY-11`` on
Linux. Ten of eleven accepted comparison workflows are now implemented and
Linux-qualified. ``CMP-MY-01`` and the broader native
inventory/recovery/lifecycle work remain open before the MariaDB handoff.
Platform qualification, human form validation and owner-deferred ScratchBird
history acceptance remain separately owned.

Native topology administration
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The server Availability menu opens ``MySQL native topologies``. Its native
MySQL Shell9.7 Python AdminAPI adapter exposes instance configuration and core
Cluster, ReplicaSet and ClusterSet inspections and operations. A method catalog
retains each native argument order and distinguishes connection dictionaries
from URI-only instance arguments. Registered instance references are resolved
and authenticated separately; credential values never enter the saved argument
JSON, review, generated script or command line. Host option-file deployment and
account-password configuration retain their separate workflows.

Native ``setup_admin_account`` and ``setup_router_account`` workflows use the
current writable primary registration for Cluster, ReplicaSet and ClusterSet.
User and host identifiers are separate strings; native Shell identifier quoting
and account splitting preserve their identity. Reviews bind native primary
roles, a server-side SHA256 fingerprint of the account row and visible native
grants. Authentication values are excluded from the captured row. Changing
account state requires a fresh review. Password preservation and password
setting are distinct selections; a supplied password travels only in the
dispatch credential lease and is excluded from reviews and generated scripts.
Native options retain update, dry-run, certificate and expiration behavior.
The original method outcome and subsequent account state observations remain
separate. Native setup grants its required privileges and does not remove
unrelated existing privileges. These workflows do not freeze external account
administrators or attest client login, replication catch-up or workload readiness.

Native ``execute`` methods retain Cluster, ReplicaSet and ClusterSet SQL fanout.
Select native contextual keywords or ordered registered-instance references and
native exclusion, dry-run and timeout options. MySQL Shell resolves the native
target set and executes independently on its member sessions. The original
method return and instance-specific SQL errors, warnings and results remain
separate; Shell formats result cells as text. Unknown replies require admitted
member ownership and independent native session observations before explicit
target acknowledgement. Original unknown outcomes remain unknown. Session and
clone observations do not verify application data or asynchronous effects of
arbitrary SQL, stored programs or scheduled events.
ClusterSet ``set_option`` retains its native ``replicationAllowedHost`` option;
Cluster tag options are unavailable in that context. Router tags use native
routing options. Argument templates and admission follow those distinct native
interfaces, including versions that silently accept an ineffective tag request.

The same workspace also exposes native Router metadata inspection, global and
selected-Router option changes, and routing guideline creation, selection,
inspection, editing, copying, renaming, removal and JSON import/export for
Cluster, ReplicaSet and ClusterSet contexts. Native expression and document
validation runs in MySQL Shell. The application supplies private job files to
the native file APIs; users upload/download JSON without selecting arbitrary
execution-host paths. Browser argument and file text retain exact integer
digits. Export downloads preserve native file text unless sensitive string
values require removal, in which case the view labels the redacted copy.
Guideline selection is independent of topology selection. Native result tables
retain column names and rows; returned native guideline objects receive a
separate JSON observation. Later observation failure does not rewrite the
original method outcome. Reviews bind visible guideline documents and Router
configuration, excluding changing Router heartbeat timestamps. Stale reviews
require a new review. This scope does not establish Router installation,
bootstrap, actual traffic routing or failure/cutover acceptance.

Read-only native inspections have their own durable receipts. Mutations require
an exact seed UUID, a reviewed native method and explicit dispatch confirmation.
Review and dispatch bind native instance/principal identities, registered route
configuration, visible metadata identities, utility identity and execution host.
Selected members and visible metadata members share native-UUID target fences
with restore/replay operations. Partial claim failure releases only the job's
own claims; unresolved operations retain protection. Native AdminAPI can change
members that the principal cannot discover; the recorded scope does not attest
an unseen member or exclude external administration.

Arguments and returned JSON remain text at the browser boundary, preserving
native integer digits. Integer arguments outside native signed/unsigned64 bounds
are refused before review instead of accepting Shell's implicit string coercion.
Shell9.7's native metadata JSON decoder uses a signed integer conversion and can
clamp stored unsigned64 tags on options reads. Separate SQL text observations
retain exact stored tag JSON and the view displays that limitation without
rewriting the original Shell reply. The native method reply is saved independently from
later object/status serialization and SQL observations. Native failure after
invocation can have partial effects. Cancellation and utility exit never imply
rollback, and uncertain mutations are never automatically repeated. Private
native utility supervision supports explicit cleanup observation after worker
loss. Current seed/metadata observations and an explicit uncertain-target
acknowledgement do not establish workload readiness or physical recovery.
Uncertain methods that can perform clone recovery cannot clear their target
fences using utility termination alone: copying can continue on the server.
Select every known registered member for recovery observations before review.
New jobs retain positively observed native handshake/thread identities and
instrumentation coverage before AdminAPI dispatch. Later reconciliation binds
the original utility PID to its independently supervised completion receipt,
checks current effective PROCESS visibility, unchanged instrumentation loss
counters, absence of its SQL sessions and idle native clone status on every
reviewed target. Explicit target acknowledgement can then release the job's
claims while its original unknown operation outcome remains unchanged.
Missing witnesses, unavailable members, changed identities, denied visibility,
instrumentation loss and active server work retain protection. Older jobs and
unobserved scopes still require their own recovery work; they are not inferred
from a free lock or client exit.

Operations that can select native clone recovery acquire conservative archive
holds for registered and visible native sources before dispatch, including
automatic recovery selection. Those holds survive missing replies and later
observer failures. Inspect and explicitly retire them in managed backup
protection. They do not attest the protocol donor, calculate a physical recovery
chain or remove native clone files.

Advertised member addresses must be reachable from the native utility's
execution host. ``tools/cdeadmin_mysql_topology_qualification.py`` accepts three
explicitly disposable peer routes and runs actual authenticated application
requests, native configuration, Cluster/ReplicaSet creation, clone membership,
primary switching, exact wide-integer options and independent replicated-data
observations. Docker Desktop qualification places the actual application and
native utility inside the owned fixture network; Docker is test infrastructure,
not a substituted production tool runner. Both connector implementations and
the built desktop require their own receipts.

These adapters and scoped receipts do not complete the independently enumerated
AdminAPI surface. Unreachable-member recovery, complete ClusterSet/failover/
repair qualification, Router deployment/bootstrap/traffic, host installation,
upgrades and broader lifecycle acceptance remain under
``MY-HA-LIFECYCLE`` and ``INV-MYSQL``.

Local testing sandboxes
~~~~~~~~~~~~~~~~~~~~~~

The dedicated **MySQL local testing sandboxes** workspace exposes native Shell
9.7 ``deploy_sandbox_instance``, ``start_sandbox_instance``,
``stop_sandbox_instance``, ``kill_sandbox_instance`` and
``delete_sandbox_instance``. It works through an owned MySQL registration without
opening that registration's SQL connection. These sandboxes run under the
ScratchRobin execution host's operating-system account. They are native local
testing instances, separate from remote service installation or production
deployment. Native platform qualification remains with the platform teams.

Configure ``CDEADMIN_MYSQLSH_BINARY`` and ``CDEADMIN_MYSQL_SERVER_BINARY`` on that
host. Deployment checks the installed native Shell/server version and executable
hashes. ``CDEADMIN_MYSQL_SANDBOX_ROOT`` chooses the managed base directory;
``CDEADMIN_MYSQL_SANDBOX_DIRECTORIES`` can explicitly admit existing additional
base directories. Native ``sandboxDir`` and ``mysqldPath`` are bound to these
operator-selected paths. Deployment retains native ``portx``, ``allowRootFrom``,
``ignoreSslError`` and ordered ``mysqldOptions``. Root passwords enter separately
at dispatch, including an explicitly selected empty password. Saved reviews
contain no password. Server mode additionally requires an Administrator role
and ``CDEADMIN_MYSQL_SANDBOX_ENABLED = True``; SQL endpoint ownership alone does
not grant local host control.

Reviews bind actual control files, the native SDK's interpreted configuration,
the native option-file graph, persisted configuration, data-directory and
``auto.cnf`` identities, and observed PID/executable/listening-port ownership.
No database UUID is invented before deployment. Stale controls and unconfirmed
or foreign processes/ports refuse dispatch. Delete requires a stopped instance.
Native kill uses its documented fixed PID-file location; a different configured
PID file is refused for that method. These observations are bounded reads,
not an atomic filesystem snapshot or protection against an independently
privileged concurrent operating-system administrator.

Before stop, a private native client authenticates the supplied root password
and checks the actual server UUID. TLS is preferred; the native RSA password
exchange is enabled when TLS is unavailable. The subsequent shutdown uses the
public native sandbox method. This admission also handles the pinned gadgets
helper's default ``ssl=False`` with a cold ``caching_sha2_password`` account.
Native errors and partially completed operations remain visible; for example,
native deployment with ``allowRootFrom: localhost`` can create the instance and
then fail because that root account already exists.

Jobs preserve native replies separately from subsequent process/filesystem
observations and SQL workload readiness. Durable execution-host port fences
span registration aliases and base directories. Lost replies retain their
original unknown outcome, require utility termination and an independent
qualified observation before explicit acknowledgement, and are never replayed
automatically. ``tools/cdeadmin_mysql_sandbox_qualification.py`` exercises actual
application requests, native methods, independent connector/data checks and the
built desktop. Its receipts qualify that recorded scope, not full host lifecycle
or full MySQL product completion.

Instance bootstrap administrators
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Native ``configure_instance`` and ``configure_replica_set_instance`` accept
``clusterAdmin`` in their native option object. Their dedicated password mode
supplies ``clusterAdminPassword`` privately at dispatch; inline passwords remain
refused. Native Shell parses the exact account name. Reviews bind account-row
fingerprints and visible grants on the selected instance. An omitted account
host uses the native ``%`` lookup and target identity. Bootstrap
administrators are configured on standalone instances; native MySQL rejects
``clusterAdmin`` on existing Cluster or ReplicaSet members.

The native method creates new accounts and validates existing ones. A supplied
bootstrap password is rejected for an existing account; preserving its password
does not add missing grants. Certificate issuer/subject and password expiration
options retain native behavior. Configuration/account changes can commit in
stages. Native errors, unknown replies, later account observations and independent
login/privilege checks remain separate. Host option-file deployment and broader
installation/upgrade/recovery acceptance remain open.

MyISAM table maintenance includes reviewed native ``CACHE INDEX`` and
``LOAD INDEX INTO CACHE`` operations, with all or selected exact index names,
default or configured named caches, and ``IGNORE LEAVES``. Native instance,
principal, table definition and index names are checked again before dispatch.
An independently owned connection keeps these implicit commits separate from
interactive transactions. Native status rows distinguish positive OK from notes
and errors; a returned SQL acknowledgement alone does not establish successful
preloading. For example, MySQL rejects ``IGNORE LEAVES`` when a table's indexes
have different block sizes, even with an index selection. Lost replies and later
observation failures retain separate dispatch/acknowledgement facts without
automatic retry. Cache contents and physical recovery are not inferred.
``tools/cdeadmin_mysql_key_cache_qualification.py --output <outside-repo>
--application`` exercises both connectors and the authenticated reviewed workflow.
The two generated-task receipts can be added to an existing contract with
``tools/reference_engine_demos/supplement_mysql_key_cache_contract.py --evidence
<native-summary.json>``; the supplement verifies actual connector classes,
completed native receipts and unchanged source fingerprints.

Server Maintenance commands also inspect a selected cache prefix, configure
each of its four native variables and release its buffer. Configuration accepts
exact unsigned decimal text or native DEFAULT and applies one setting per
review. The server owns bounds, allocation, rounding and warnings; receipts
preserve actual values as decimal strings, including values above JavaScript's
safe integer range. Named prefixes and variable identifiers are quoted
separately. Changed settings stop a reviewed mutation, while a fresh read-only
inspection reports current values. All connections belong to the operation.

Release uses native ``key_buffer_size=0``: MySQL moves assigned tables to the
default cache and retains the prefix's other parameters. The default cache is
protected by native error 1438. All-zero values for an unknown prefix do not
prove that a named cache exists. SHOW GLOBAL VARIABLES does not enumerate named
caches; selected-prefix inspection does not claim a complete cache catalog.
These runtime settings are not server configuration persistence. Native 9.7
deprecation and rounding warnings remain visible. Use
``tools/cdeadmin_mysql_key_cache_lifecycle_qualification.py --output
<outside-repo> --application`` for native pure/C and reviewed API evidence.
The pure connector's native warning handler is retained with a private text
warning port so application regex filters can process its Exception-derived
warning objects. Native warning rows, raise-on-warnings behavior and Python
warning policy remain intact; process-wide warning functions are unchanged.

SQL source checking can use MySQL Shell's versioned server grammar library
(``mysql_9.7.so`` or native Windows ``mysql_9.7.dll``). Its C ABI applies the
observed native SQL mode, independently of the original connection, and runs in
an isolated, bounded process. The original session supplies no metadata commands
when its independent observer is admitted. Syntax checks cover compound
procedures and references to future objects without executing them; catalog
binding, privileges and quoted external-language bodies remain separate.
Optimizer-hint diagnostics remain warnings when the SQL grammar is valid.

Set ``CDEADMIN_MYSQL_PARSER_LIBRARY`` to the exact native library, or install
MySQL Shell with its sibling ``lib/mysqlsh/yparser`` directory. The adapter also
locates that directory from the configured Shell executable. It verifies the
native library's reported 9.7.0 version and retains process/library fingerprints.
The separate Shell AST API is not substituted because it forces ANSI quoting.
Missing libraries retain the existing native PREPARE path; an explicitly selected
unavailable or mismatched library is not silently replaced. Script previews track
deterministic SQL-mode declarations, saved mode variables, numeric masks, aliases,
CONCAT and SESSION DEFAULT. Fixed bound settings on the private observer let the
native server canonicalize mode values; submitted statements are never executed
by validation and the private mode is restored afterward. Each retained statement
records its expected mode and is checked again before dispatch, allowing intended
transitions while stopping on unexpected context drift. Runtime-dependent values
leave subsequent framing unconfirmed; the ordinary native Run path still observes
the actual mode between commands. Saved variables are invalidated after opaque
calls or expressions that may change them. Catalog/privilege binding and
unavailable observer profiles remain separate. Windows/macOS requires the teams'
evidence. The owned native qualifier is
``tools/cdeadmin_mysql_parser_qualification.py --output <outside-repo>
--library <native-library>``, with ``--use-c`` run independently and optional
browser/driver paths for the built editor.

The source inventory separates native dispatch IDs, top-level grammar entries
and SQL type keyword spellings. It excludes C++ actions and comments and retains
the first alternative of each grammar rule. The current source has 168 dispatch
IDs (excluding the enum sentinel), 144 top-level grammar alternatives and 79 type
spellings/aliases. These source facts do not establish complete native feature
support. The original grammar-rule labels are not SQL commands or data types.

All 79 type spellings have native parser acceptance and actual generated table
declarations through both connectors, with native COLUMN_TYPE observations.
Private completion exposes their SQL tokens, including multiword aliases such
as DOUBLE PRECISION and NATIONAL CHARACTER VARYING. Builtin type choices do not
replace colliding catalog names or their quoted member paths. The qualifier is
``tools/cdeadmin_mysql_type_inventory_qualification.py --output <outside-repo>
--library <native-9.7-parser-library>``; optional browser/driver paths check real
completion insertion and nonexecuting source validation in the built editor.
The source-only refresh tool is
``tools/reference_engine_demos/reconcile_mysql_source_inventory.py --source
<native-9.7-source>``. It retains existing runtime facts and qualified task
receipts, records source hashes and avoids relabelling the original artifact.

Native system-variable discovery now reconciles ``global_variables``,
``persisted_variables`` and ``variables_metadata``. It retains native type,
GLOBAL/SESSION/SESSION_ONLY scope, bounds and documentation, including installed
component variables and definitions that have no global value. SESSION means
that the native definition supports both global and session scope. SESSION_ONLY
definitions offer inspection and any existing persisted-override cleanup at
server scope; global/persist assignments are refused. Metadata presence does
not imply a visible global value, mutability or a sensitivity classification.
Unloaded persisted values remain withheld.

Native editor metadata includes these definitions without fetching their
values. MySQL completion separates variables from catalog namespaces and
filters explicit GLOBAL/SESSION/LOCAL prefixes and SET GLOBAL/SESSION/PERSIST/
PERSIST_ONLY positions by the observed native scope. Dotted component names
are inserted as one quoted native identity. Quoted names, SQL modes, comments
and string-literal positions use the native token-boundary rules. The private
committed-catalog peer still marks source active-role/temporary-object overlays
unconfirmed; variable definitions do not make those session overlays complete.

Global/persistent variable forms now retain explicit NULL and DOUBLE inputs.
DOUBLE casts bounded decimal/scientific text in MySQL, with native rounding,
bounds and overflow handling. It does not pass through the application's
DECIMAL(65,30) conversion. NULL is distinct from empty text and native DEFAULT.
Runtime DDN NULL application uses an explicit native ``IS NULL`` observation;
Performance Schema string values cannot establish that distinction. Persisted
NULL identity is not inferred from those strings, and a native acknowledgement
remains separate from unconfirmed persisted-value identity.

``tools/cdeadmin_mysql_variable_metadata_qualification.py --output
<outside-repo>`` reconciles actual metadata/navigation/server DDN, typed native
assignments, persistence and runtime NULL rediscovery with both drivers. It
checks private completion in default and ANSI_QUOTES/NO_BACKSLASH_ESCAPES modes
using independently observed, nonzero native statement counters; source row
counts, error areas and pending savepoints must survive. Its generated fixture
is consumed by ``nativeCompletionScope.spec.js`` through
``CDEADMIN_MYSQL_VARIABLE_FIXTURE``. Optional ``--library``,
``--browser-binary`` and ``--driver-binary`` qualify insertion and native syntax
checks in the built desktop. This does not close the wider procedural/editor,
privacy/diagnostic or independent product-inventory work.

Recovery dependency protection
==============================

The managed backup protection panel includes a recovery dependency workflow.
Choose a completed consistent managed logical dump and an ordered selection of
completed MySQL Shell binary-log archives. Review computes prerequisites using
native ``GTID_SUBSET`` and ``GTID_SUBTRACT`` and verifies the retained input
manifests. Tagged GTIDs remain native identities. A missing prerequisite,
changed input, different source or no-longer-executed source GTID refuses the
review/application. Before/after targets retain the entire final archive;
native replay remains responsible for event order and stop semantics.

An explicitly confirmed active chain protects its exact archive jobs across
application restarts. New protection is serialized with removal, including
already-reviewed retention and scheduled policies. Backup holds also cover the
same owner's other registrations of the same source UUID. Pending/uncertain
holds continue retaining their entire original registration. An unreadable
owner protection store refuses removal. Cross-owner records are not disclosed.
The owner-wide hold list includes removed registrations; explicit retirement
binds the selected original registration and review, without needing that
registration to remain online or present in the connection tree.

Creating a chain never retires a broad backup hold. Its separate reviewed
retirement can release unselected archives while the active chain retains its
edges. Chain retirement has another review and confirmation; it leaves files
and receipts intact and does not dispatch SQL. Neither operation repeats a
backup or restore. All existing archive pins and other holds still apply.

GTID sets cannot attest that a reset/replacement has never reused identities.
Activation therefore records explicit operator source-lineage confirmation,
separately from native observations. It does not claim generation attestation,
data/definition equivalence, physical recovery or production cutover. Raw
archives, physical clone bases, external backups and offline replica references
remain separate work. ``tools/cdeadmin_mysql_recovery_chain_qualification.py
--output <outside-repo> --mysql-shell <native-9.7-mysqlsh>`` exercises the actual
managed dump, archive and protection APIs. ``--use-c`` selects the C connector;
optional browser/driver paths qualify the built graphical workflow.

Full-instance logical backups
=============================

The server Backup menu includes ``MySQL full-instance backups``. This runs the
pinned native MySQL Shell ``util.dumpInstance`` on the application execution
host. A reviewed, explicitly started job can include selected schemas, native
objects and data, and account/role/grant definitions. Native system-schema
exclusions remain in force. Schema/user inclusion and exclusion, consistency,
checksums, compression and the supported native dump options are exposed. The
application assigns a private output directory. Closed Enterprise data masking
is disabled; a client-side Shell option does not supply its server component.

Jobs have durable owner/registration-bound receipts, progress, cancellation,
offline inspection, paginated verified-file inventories and streamed downloads.
Account SQL can contain authentication material. Review binds source UUID,
authenticated principal/role, registration, utility and adapter identities.
Execution rechecks the native source before invoking the utility. Creating a
backup acquires an archive hold before native dispatch. Pins, explicit removal
and interrupted-removal reconciliation retain the receipt after file removal.

Native utility acknowledgement, file acceptance and restored-data acceptance
are separate facts. An acknowledged utility return survives later file
publication or bookkeeping failure. A stopped utility whose original reply was
lost can have its exact native output explicitly verified and adopted without
running the dump again or inventing an acknowledgement. Adoption checks native
completion metadata, source identity and byte manifests. Incomplete output is
refused. Private-script cleanup failure preserves the native outcome and offers
an explicit, identity-checked retry on the original execution host.

A verified consistent full-instance dump can be selected as a recovery-chain
base. The active chain retains both its exact managed backup files and selected
Shell archive files, even after the broad backup hold is separately retired.
Chain retirement and file removal remain separate actions. File verification
does not establish restored row values, definition equality, physical recovery
or production cutover. Independent recovery acceptance remains open under
``MY-CONTINUITY``.

``tools/cdeadmin_mysql_instance_backup_qualification.py --output <outside-repo>
--mysql-shell <native-9.7-mysqlsh>`` exercises actual instance dumps, schemas,
cross-schema views, procedures, accounts/roles, native refusal, cancellation,
lost replies, post-return publication failure, cleanup retry and chain/file
protection. ``--use-c`` selects the C connector. Optional browser/driver paths
exercise the built server context action, review, dispatch and file inspection.

Full-instance logical restore
=============================

The server Restore menu includes ``MySQL full-instance restores``. Select an
owned registration and retained verified instance backup, inspect a separate
native recovery target, confirm its UUID and review the native load options.
Explicit start stages and rechecks the exact input, source/target identity,
target GTID state and utility before native ``util.loadDump``. Private input and
progress paths are assigned on the application execution host. Trusted
``local_infile`` must already be configured on the recovery target. Account
loading, schema/object filters, DDL/data/index loading, existing-object handling,
native checksum and GTID installation options remain native decisions.

Restore and binary-log replay share durable target fencing and a native
connection lock. Known native replies survive later observer or receipt
failures. Native errors after invocation, cancellation and lost replies can
leave partial effects; they retain uncertainty and the target fence. Separate
observation never repeats the load. Releasing an uncertain target for another
recovery requires confirmed utility termination, a free native lock, the exact
current observation digest and explicit target UUID acknowledgement. The
original unknown outcome remains unknown. Restarted/interrupted utility process
termination that has not been observed still requires separate reconciliation.

``tools/cdeadmin_mysql_instance_restore_qualification.py --output <outside-repo>
--mysql-shell <native-9.7-mysqlsh>`` exercises two actual MySQL instances through
authenticated application routes. It covers schemas, cross-schema views,
procedures, accounts/roles, wide integers/Unicode/BLOBs, native GTID base
installation followed by application log replay, explicit cancellation,
privilege refusal and injected reply/bookkeeping failures. ``--use-c`` selects
the C connector; optional browser/driver paths exercise the built restore UI.
These receipts prove their selected restore and continuation cases. Physical
recovery, external dependencies and production cutover retain their own
acceptance. The separate dump acceptance workflow below checks the exported
base snapshot; it does not accept data after later log replay.

Independent instance-dump acceptance
====================================

The full-instance restore view includes ``Independent dump acceptance``. It
uses an explicitly selected retained instance backup and separately confirmed
native target. Review requires consent to the server-wide write pause. Start
acquires an instance backup lock and global read lock, observes full table
inventories and exact row counts, runs native Shell checksum verification with
all data/DDL/index/account loading disabled, and re-exports native definitions.
No GTID update or restore is issued. Source bytes, native identity, GTID state,
utility identity and exported coverage are checked independently of the earlier
restore receipt.

Data, selected-schema definitions and exported account/role/grant definitions
have separate results. An unexported surface stays unchecked. Full row counts
detect rows outside native checksum chunk boundaries. Definition comparison
preserves native SQL bodies exactly, omitting only the five validated native
tool/host/version header lines. Native routine bodies, comments, names, user
properties and grant statements are preserved. Source SQL filename coverage is
required. Reports expose file names and body hashes, without SQL text or
authentication definitions. Account comparison covers the exported identities;
additional target accounts outside that selection are not accepted by it.

The pinned native checksum mismatch code ``53031`` is an observed mismatch;
privilege, launch, cancellation and incomplete checks remain unconfirmed.
Comparison facts, utility completion and server-lock cleanup are recorded
separately. Unconfirmed private server-lock cleanup retains target protection.
New target observations do not rerun checks or rewrite an earlier result.

Before taking either acceptance lock, new jobs durably record their private
native thread, connection and a job-specific user-lock ownership marker. Native
instrumentation and handshake visibility must be positively observed for this
reconciliation path. A later ``Observe acceptance target`` checks both that the
original native thread is absent and that the ownership marker is free. A free
user lock alone cannot establish backup-lock teardown. These observations use
the pinned native connection cleanup lifecycle; surviving or reused thread IDs,
denied/disabled instrumentation and older jobs without admitted ownership remain
unconfirmed. The original unlock replies and comparison results are preserved.
Observed private-session cleanup can release a completed check's target fence.
An unknown job still requires separately confirmed utility termination, a free
native utility lock and explicit target acknowledgement. This observation does
not terminate an orphan utility or reissue any check, restore or SQL lock.

New managed instance backup, restore and acceptance utilities have an independent
application-host supervisor. Its private invocation reference is durably saved
before dispatch; it owns native output, cancellation, the bounded runtime and
credential-file cleanup even if the original application worker exits. A later
target observation can read the bound utility completion receipt and confirm
process cleanup. It leaves the original load/check outcome unchanged. An
uncertain restore still needs the explicit target acknowledgement, and an
acceptance job still needs its separate private SQL-session cleanup evidence.
Backup file reconciliation separately verifies complete native files; it does
not invent a missing original dump reply. Interrupted utilities can be cancelled
from their retained job views. There is no automatic native retry.

If an interrupted start claimed target protection before atomic worker
admission, explicitly cancelling its still-unstarted review releases that
claim. A paused start then observes the cancellation and cannot dispatch.
Admission, utility or private SQL-session ownership evidence prevents this
review-only cleanup; uncertain native work keeps its original reconciliation
requirements.

A missing, changed or incomplete supervisor receipt remains unconfirmed. A
dead application PID or free native SQL lock alone is insufficient. Older jobs
without an invocation reference and failure of the supervisor itself retain
their separate unresolved cleanup state. Windows/macOS native acceptance stays
with the platform teams.

Add ``--acceptance`` to the instance restore qualification command to exercise
actual same-count value changes, extra rows, routine definition changes and role
grant changes, followed by new independent acceptance after reverting the owned
fixture. Both connector implementations and the optional built browser workflow
retain their own receipts. These results cover the exported logical base
snapshot; physical recovery, changed post-replay data, production cutover and
unobserved utility termination after interruption remain separate work. The
qualification also exercises lost unlock replies, a live private native lock
owner, subsequent session teardown and independent utility-termination gates.

InnoDB page tracking
====================

Community InnoDB page tracking now has seven dedicated server maintenance
actions: inspect the active window, start/reset, stop, count page IDs, set the
native backup ID, export a native index and purge tracking archives. These call
the five implemented ``component_mysqlbackup`` UDFs and the native runtime-only
``mysqlbackup.backupid`` variable. Native component installation/uninstallation
uses the existing component administration. The interfaces do not require a
closed-source Backup utility; physical data copying and incremental recovery
orchestration remain separate work.

Review binds the native component, UUID/principal/roles, current first active
LSN, backup ID and database-host directory. Each action owns its connection and
rechecks the review inputs. Read-only inspections/counts report fresh facts.
Start resets an already active tracking window, and the native stop UDF first
starts/resets tracking before stopping it. Destructive changes require an
explicit coordinated backup window. Setting the native backup ID can interrupt
a transfer and delete the component's previous exported index, even if the ID
is unchanged. This is a separately confirmed action; export never changes that
ID. NULL and native DEFAULT remain distinct inputs from literal text.

An SQL reply is separate from a UDF result. The adapter retains exact signed
native results as decimal text, including negative count errors, positive
export error statuses and duplicate-file -1. The native purge LSN_MAX sentinel
does not establish a purged boundary. Zero range inputs use native current
window/checkpoint semantics. Native functions may expand a range without
returning adjusted endpoints, so the adapter does not assert an exact exported
range. The index is created under ``datadir/#meb`` on the database host; an SQL
reply does not attest file existence, a copied data file, a recovery chain or
recoverability. Returned native results survive a later observation failure;
missing replies are never automatically replayed.

``tools/cdeadmin_mysql_page_tracking_qualification.py --output <outside-repo>``
checks both native drivers against an owned Community server. Its independent
fixture verifies the exported file size/hash against the native page count,
duplicate refusal, positive/negative native failure statuses, backup-ID file
deletion, NULL/DEFAULT, changed-input refusal, post-acknowledgement observation
loss, stop/purge and preservation of an unrelated transaction/savepoint.
``--application`` adds authenticated reviewed API calls; optional
``--browser-binary`` and ``--driver-binary`` qualify built desktop controls.
This is native page-tracking qualification, not physical backup/recovery or
cross-platform release acceptance.

Installed native Rewriter rules now have dedicated server maintenance actions
for inspection, insertion, editing, deletion and explicit reload. The adapter
uses the native ``query_rewrite.rewrite_rules`` InnoDB table and installed
``query_rewrite.flush_rewrite_rules`` procedure. Pattern/replacement text is
bound as data; signed native rule IDs, native YES/NO and distinct NULL/empty
pattern databases are preserved. Inspection includes stored patterns, native
messages/digests/normalized patterns and the four native Rewriter status values.
The plugin does not enumerate its in-memory rule definitions; the table and
status observations do not assert which rule handled a client query.

Each action owns its connection. Review binds the server UUID/principal/roles,
plugin, reload-procedure definition hash and affected stored rules. Edits lock
and recheck the selected row, then commit only their owned transaction. Saving
does not invoke a reload; another administrator or native startup loading can
activate stored rules. Reload is a separately confirmed server-wide action.
The native procedure commits its own connection and may load valid rules even
when it reports rejected rules. Native error 1644/45000 and per-rule messages
remain visible through a later inspection. Missing replies are never replayed;
a committed edit remains acknowledged if its later observation fails.

``tools/cdeadmin_mysql_rewriter_qualification.py --output <outside-repo>``
uses the official installer shipped with the pinned MySQL image, checks both
native connector implementations and observes actual rewriting through a
separate unprivileged client. ``--application`` adds authenticated reviewed API
checks; ``--browser-binary`` and ``--driver-binary`` add built desktop checks.
These fixtures install the native plugin for qualification. Deployment of the
native installer onto an arbitrary database host remains under host lifecycle
work; these rule actions require an already installed native plugin/schema.
Native permission checks remain authoritative, and bounded review refuses
partial inventories above 1000 stored rules or 4 MiB.

Prepared XA inspection and explicit commit/rollback recovery workflows are
available under the native server Maintenance menu. They use separate owned
connections, ``XA RECOVER CONVERT XID`` and binary hexadecimal literals for both
XID parts, preserving embedded NULs, non-ASCII bytes and exact decimal format IDs.
Server catalog exchange includes prepared branch identities. Inspection requires
the native ``XA_RECOVER_ADMIN`` privilege; the primary RMERR and supplementary
access-denied condition are retained, and denied catalog access is unavailable
rather than an empty transaction list.

Resolution requires the exact server name and a transaction manager decision or
authorized recovery instruction. The reviewed instance, actor and prepared XID
are rechecked immediately before requesting native resolution. Acknowledgement
and subsequent recovery-list observations are separate. An absent XID does not
establish the global decision, and the recovery list cannot distinguish reuse of
the same XID from its original branch. Native attached-branch and concurrent
resolution errors remain engine decisions. Operations are never automatically
replayed or executed on a borrowed user attachment. Native qualification is
``tools/cdeadmin_mysql_xa_qualification.py --output <outside-repo> --application``;
the companion ``tools/cdeadmin_mysql_xa_ui_qualification.py`` checks the built
desktop workflow. These receipts do not close the wider product inventory.

For admitted independent-observer profiles, predictive editor metadata now reads
the committed native catalog on that same-instance authenticated peer. The
source's current database, SQL mode and client charset are observed privately;
completion sends no original-session command and preserves ROW_COUNT, warnings,
errors and pending work. Private context loss or denied observation refuses the
request without substituting an original-session query. Source active-role and
temporary-object overlays are explicitly unobserved, so the returned metadata is
marked incomplete. The peer's role is labelled separately and never presented
as the source's active role. Unadmitted legacy profiles remain separately
unqualified for diagnostic preservation.

The MySQL editor's Engine options accepts a JSON object of native per-query
attributes. Ordinary Run and retained scripts bind them separately from SQL
parameters; a retained script freezes its private attribute policy at preview
and requires another preview after edits. Public plans and execution summaries
exclude attribute values. Each command observes its current client charset,
including charset transitions within a script. Original client attributes are
restored after protocol drain, decoded error or cancellation; unconfirmed
restoration blocks session reuse without replaying SQL.

Connector/Python 26.7's pure COM_QUERY encoder omits NULL attribute metadata.
The adapter uses its ordinary binary value encoder and supplies correctly framed
names, types and NULL bitmap without preparing or changing the submitted SQL.
Negative TIME values use the native positive magnitude and the protocol sign
byte. Attribute names and string values follow the native source charset.
Explicit integer, decimal, base64, date, datetime and time envelopes preserve
typed inputs; ordinary strings remain strings. The native Community
``component_query_attributes`` supplies qualification of actual delivery, and
installed runtime UDFs appear in predictive metadata. The component's own string
UDF uses a bounded C string, so its NUL/truncation behavior is not a binary
roundtrip guarantee.

Native C query attributes require the source correction built by
``tools/cdeadmin_build_mysql_driver.py`` against the matching MySQL 9.7.0 SDK.
Linux development's ``python`` stage and demo ``--install-python`` now build and
install that correction automatically through
``tools.cdeadmin_install_mysql_driver``. It checks the installed native ABI,
connector/client versions and extension hash before accepting or reusing a
receipt. A temporary pinned SDK can be extracted on Linux x86_64/glibc2.39+;
another matching native SDK can be selected explicitly. No database server or
OS package is installed by this connector step. Build intermediates are removed,
with one bounded current failure log retained when compilation fails. Import
qualification remains separate from actual native query/functionality tests.
The corrected extension exposes an ABI marker and keeps TIME duration signs and
microseconds, unsigned 64-bit integers, source-charset names, float64 precision,
exact decimals and NULL values in the native C binding path. It clears native
binding pointers and releases owned names/values on result, non-result and error
returns. A stock extension is refused before attribute dispatch; ordinary C
queries remain available. Native development setup builds this extension from
the pinned official source and verifies its marker. Platform qualification
remains separately owned; the marker alone is not runtime evidence.
Run the owned qualifier independently with and without ``--use-c``:
``tools/cdeadmin_mysql_query_attributes_qualification.py --output <outside-repo>
--application``. Optional browser and driver paths qualify the built editor.

Native server Maintenance also exposes reviewed ``SHUTDOWN`` and ``RESTART``
requests, requiring exact server confirmation and consent to disconnect clients.
They use independently owned connections and recheck native instance, principal
and role identity. Native SHUTDOWN privilege and RESTART supervisor refusals are
preserved. RESTART's native implicit commit applies to its private attachment;
server-wide disconnection and rollback remain engine-owned effects. A returned
acknowledgement reports request acceptance only, with no automatic retry or
inferred termination, process generation or readiness. Native host initialization
and Linux systemd installation/controls have separate workflows below; native
upgrade acceptance remains outstanding.
The native qualifier uses unmanaged and supervised owned fixtures to observe
actual refusals, process changes, preserved committed data and native rollback of
pending transactions. Disposable retained fixtures remove their anonymous data
volumes on cleanup.

Native instance maintenance exposes all six Community ``ALTER INSTANCE``
actions through server Maintenance context commands and reviewed native plans:
InnoDB/binlog master-key rotation, TLS context reload, keyring reload and InnoDB
redo enable/disable. TLS selects the native main/admin channel and explicit
rollback-on-error behavior. Review binds the native server UUID, authenticated
actor, active roles and observed state; TLS also captures configured variable
values separately from the active context. Changed state refuses dispatch.
Disabling redo requires acknowledgement that the instance is dedicated to an
initial load; crash recovery remains unavailable until redo is re-enabled.
Native privileges and installed services own permission/capability decisions.

Each operation uses its own connection, records native warnings and separates
SQL acknowledgement from later observation failure. An acknowledged key
rotation is never replayed to resolve a lost observation. Redo receipts report
the observed ON/OFF postcondition; TLS acknowledgement does not attest certificate
file contents or reconnect existing clients. The native Community file-keyring
fixture qualifies real key-ID rotation, encrypted-table readability, redo state
transitions, changed configured TLS paths and native privilege refusals with
both connectors. Use ``tools/cdeadmin_mysql_instance_qualification.py --output
<outside-repo> --application``. Host startup, services, upgrades and complete
recovery remain separate work.

Database-host diagnostics now have an explicit SSH execution path. The
authenticated peer's hostname and native ``auto.cnf`` UUID must match the
independently observed MySQL host and data directory. An SSH bastion and the
application host are not substituted. The public SSH key is pinned before
authentication. Credentials remain transient and do not enter command arguments,
operation reviews or durable receipts. A private-key file can be loaded in the
dedicated desktop form.

The initial native action is ``mysqld --validate-config`` on MySQL9.7.0. Review
binds the selected native executable hash/version and configuration-file graph.
The graph records nested ``!include`` and ``!includedir`` inputs, eligible sorted
directory members, resolved paths, file hashes and native ignored/missing states.
It follows native case-sensitive directives/extensions, quote-aware ``#``
comments, literal include filenames, the ten-level include limit and POSIX
world-writable-file exclusion. Relative includes resolve from the native process
working directory; they do not resolve from each included file's parent.
For an explicit root file, the process working directory and ``HOME`` are the
root file's resolved parent directory, shown in the review. The private job
directory continues to hold temporary files and receipts.

The helper rechecks the graph before native execution, records its intent
before dispatch, and persists process exit, timeout and bounded native output
before returning the SSH reply. Duplicate job delivery reads the existing
receipt. Explicit reconciliation keeps the original SSH acknowledgement separate
from subsequently read native process facts. Closing a viewer never revokes an
admitted remote action. Native completion is persisted before the separate
post-process graph observation. Changed or unreadable later inputs do not erase
the native exit result. These file observations do not freeze concurrent writers
or establish an atomic snapshot of the native parser's file reads. Graph byte,
entry and filename bounds refuse admission rather than accept partial evidence.
Persisted ``mysqld-auto.cnf`` settings and service/startup arguments remain
separate inputs; this graph covers the selected option-file load.

The host requires Python3.9 or later; only the standard library and the shipped
ScratchRobin permission helper are transferred over SSH. POSIX and native
Windows PowerShell launches have separate argument framing. Linux native
qualification does not establish Windows/macOS acceptance, which remains with
the platform teams. Native configuration acceptance is separate from server readiness, initialize/start/
stop/service management, upgrades and physical backup/recovery; these broader
host workflows remain required.

The server Maintenance menu also opens database-host administration for native
Linux systemd start, stop and restart. Review binds the exact unit/aliases,
fragment/drop-in bytes, command digests and manager executables. Command values
are withheld from public facts. The observed MySQL PID file, executable hash,
process start/boot identity and native control-group membership establish that
the running instance belongs to the selected unit, including a manager wrapper
whose MainPID differs from mysqld. Another service is refused before dispatch.
Stop/restart require explicit all-client disconnect consent.

Offline SQL startup uses an explicitly selected prior verified service job for
the same owner, registration and pinned SSH host. Inspecting its receipt fills
the prior-job field; choose start and supply fresh SSH credentials. Its SQL actor
facts remain labelled previous observations. Native UUID/data-directory binding,
current executable and unit facts are independently read on the host. This is
host administration authority and does not substitute a live SQL privilege
check. Initial association requires observing the running MySQL instance.

The native service-manager client outcome is persisted before later unit/process
observations. A returned client, an active unit and SQL readiness remain distinct.
Timeouts do not revoke an already admitted manager job. Lost SSH replies stay
unknown; reconciliation reads the durable result and new unit/process facts
without resubmitting a service action or changing the original acknowledgement.
Changed reviewed inputs and native manager policy refusals are preserved.
Unit fragments/drop-ins and command identities do not freeze external scripts,
environment/credential files or a complete startup-input snapshot. Native
initialization, option-file deployment and service creation have separate
workflows below. Native upgrades, broader physical recovery and
the separate Windows/macOS manager implementations/acceptance remain open.

``tools/cdeadmin_mysql_service_qualification.py --fixture <owned-fixture.json>
--output <outside-repo>`` qualifies the actual pure and C application routes.
Its optional browser flags qualify the root menu, service controls and reopening
the host workspace for offline startup. ``tools/cdeadmin_mysql_service_fixture.py
prepare --directory <new-outside-directory>`` builds a private disposable
QEMU/KVM Ubuntu/MySQL9.7.0 host. Its pinned archive hashes are checked; it does
not install host OS packages or use existing databases. Supplied image/server
archives can avoid downloads. Use its ``stop`` action on the exact directory
before removing guest disks, keys, credentials and logs. These are scoped native
service receipts, not full host lifecycle or full product completion.

The owned qualification runs through authenticated workspace HTTP routes and
real SSH/native MySQL9.7 processes. It checks wrong-host/key refusal, changed
configuration admission, native error exits, separate lost-reply reconciliation,
password and encrypted-key authentication, registration isolation and offline
receipts. Use ``tools/cdeadmin_mysql_host_qualification.py --output <outside-repo>
--prepare-fixture`` to build its disposable OpenSSH/Python/MySQL fixture, or supply
``--fixture-image`` with ``--ssh-private-key`` for an existing owned fixture.
Run ``--use-c`` separately for Connector/Python's C interface. Optional
``--browser-binary`` and ``--driver-binary`` exercise the built desktop context
menu, review, confirmation and receipt reconciliation. Stop/remove its owned
fixture image, private key and output when no longer needed. These checks do not
qualify native Windows/macOS execution or the remaining lifecycle operations.

Group Replication recovery credentials retain MySQL's native distinction
between account characters and password bytes. Recovery usernames accept up
to 32 characters within the native 96-byte buffer; passwords retain their
32-byte bound. The native no-LF grammar permits carriage returns, quotes,
backslashes and BMP Unicode in these bound credential arguments. No account or
password is truncated. This does not qualify human form input of those values.

The three-member Group Replication qualifier independently selects pure and C
connectors, uses the full native Unicode account/password bounds, and exercises
primary election after pausing an owned primary. A new acknowledged write is
observed on both survivors; explicit native stop/start repairs the resumed
member and all three independently reread the original and failover data.
This qualifies the native compiler and member behavior, with separate broader
workspace, topology, server-host lifecycle and upgrade acceptance still required.

Managed graphical MySQL Shell backups now record durable protection intents
before native dump dispatch. A native completion preserves the exact source
UUID, database, manifest digest and native file/position/GTID boundary without
copying the manifest's system-variable or credential material into protection
receipts. Missing replies, changed metadata and local bookkeeping failures keep
the hold; they never cause another native dump or replace an acknowledged dump
with a restore/retry request.

Application archive retention, individual removal and interrupted-removal
reconciliation check these holds. Admission of a new backup intent and archive
file removal share one application lock. An intent added after a retention
review can stop its next removal; it never expands the accepted removal list.
Pending/unconfirmed records retain this owner's registration archives, and
confirmed source records retain its matching source archives. This is a
conservative source hold, not calculated recovery-chain coverage. External
backups, other registrations, offline replicas and native server log purging
retain separate requirements. Direct SDK backup calls outside the managed
workspace do not acquire a workspace protection scope.

The archive retention form lists managed backup protection and provides a
separate, expiring, exact-record retirement review. Retirement keeps backup
files and abandons the backup's archive protection and recovery-planning role;
it can explicitly abandon an unresolved dump. A late native completion never
reactivates a retired hold. A changed backup record invalidates retirement
authority. These receipts do not establish successful recovery, physical backup
acceptance or a native log generation epoch.

Native binary-log reset has a separate reviewed workflow for ``RESET BINARY
LOGS AND GTIDS`` and its optional native ``TO`` sequence. It deletes all native
binary logs, including the active file, and clears executed/purged GTID history;
it is not an archive retention action. The server default and native sequence
range are preserved. Reset is also available with native binary logging
disabled, where GTID history can still be cleared. Native privilege and Group
Replication refusals remain server decisions; read-only flags are not a guard
against this native operation.

Confirmation binds the exact registration, principal, source UUID, adapter,
log index/positions and GTID observation. A changed observation requires a new
review in an exclusive maintenance window. Purge and reset serialize through
the same application advisory lock and revalidate inside it. They do not lock
out external native administration. The private worker owns its connections;
guarded cancellation, durable acknowledgement and explicit unknown-outcome
reconciliation retain the same non-replay rules. Reused filenames and empty
GTID observations cannot establish the original acknowledgement or a native
generation epoch. Application archives are retained, with no automatic rebinding
to the new source generation or discovery of backup/offline-replica dependencies.

Native editor preparation also checks the qualified MySQL9.7 post-parse refusal
paths for resource groups, tablespaces (including undo/logfile groups), roles,
spatial reference systems, components, transaction/savepoint/XA control, table
locks, diagnostics, signals, dynamic statement commands, table import and clone.
This confirms SQL grammar only; it does not confirm installed capabilities,
catalog binding, authorization or a non-SQL body language. A native 1295 reply
and the exact qualified server revision are required. Header recognition alone
cannot accept source. Malformed variants are checked independently by the
native server, and other context refusals remain unconfirmed.

Script framing and parameter markers use the observed ANSI_QUOTES and
NO_BACKSLASH_ESCAPES modes. Backslashes do not escape backtick or ANSI-quoted
identifier delimiters. Native line comments end at LF; a bare CR cannot expose
commented-out SQL to header classification. On the qualified MySQL9.7 parser,
dollar-quoted routine/library text preserves native numeric/Unicode tags,
consumed delimiter mismatches, comments, semicolons and placeholder-like text.
Native formatting preserves these literal bytes, and SQL completion does not
offer SQL keywords inside an external-language body. This SQL check does not
validate JavaScript or other opaque external-language code. MariaDB retains its
own native quoting rules. MySQL's MLE JavaScript runtime and language validation
depend on an unavailable Enterprise implementation and are post beta under
``MY-POST-BETA-MLE`` in :doc:`six_engine_remaining_work`. Native community library
declarations and their DDN/catalog handling remain separate beta workflows.
The retained native qualification
checks both connector implementations while preserving pending data/savepoints,
and the workspace qualifier checks authenticated HTTP and visible source-check
results without executing submitted SQL. Reproduce these scoped checks with::

    python tools/cdeadmin_mysql_family_prepare_qualification.py --engine mysql --evidence /work/mysql-prepare
    python tools/cdeadmin_mysql_family_editor_workspace_qualification.py --engine mysql --evidence /work/mysql-editor --browser-binary /path/to/chrome --driver-binary /path/to/chromedriver

Interactive query execution uses the same native lexical parameter boundaries
as preflight. Placeholder-like text inside strings, identifiers, ordinary or
inactive comments and dollar bodies remains text. Active MySQL version comments
use the selected release. Named bindings preserve Unicode and punctuation keys.
The selected connector converts values into native literals; the application
does not quote values itself. A fixed metadata read observes current SQL mode
without changing native settings or deciding the caller's transaction.

Converted query bytes and unbound SQL containing DELIMITER text use the native command port with the existing driver's
result ownership. Its client script preprocessor cannot rewrite DELIMITER words
inside values. Actual client directives have native-mode-aware framing. Local
binding refusals identify whether prior commands ran and preserve a usable
session after confirmed native boundaries. Cancellation is checked again after
conversion and before dispatch.
Quoted multiline text and opaque library bodies remain intact when there are no
bindings. Native client command identities use ASCII case rules, and actual
unbound client-delimited routines retain their own framing and result ownership.
Native qualification covers both interfaces, pending data/savepoints, exact
values, multiple results, native refusals, cancellation and lost commit replies::

    python tools/cdeadmin_mysql_parameter_boundary_qualification.py --evidence /work/mysql-parameter-boundaries

Parameterized and explicit setting/call/client-delimited batches now consume
each command's results before observing its successor's native SQL mode and
character sets. Values, source literals and identifiers are
encoded with those observations, including changes made by preceding commands
and client-delimited stored procedures. Named and positional bindings retain
their own lexical markers; a later admission failure reports prior dispatch
without replay or an implicit transaction decision. Cancellation before a later
dispatch retains completed results and pending work. Undelimited compound native
programs retain their whole-command port; future-state source preflight and
wider procedural/contextual coverage retain separate acceptance.

Admitted retained-session observers now also support native syntax preparation
on their independently authenticated connection. The exact source UUID,
principal, version, native thread and handshake nonce bind the observation.
Performance Schema supplies the source's current SQL mode and selected database;
only the private peer receives settings, database selection, user variables,
PREPARE, deallocation and cleanup. The source's row count, warning/error areas,
transaction and connection remain untouched. Live USE changes preserve exact
Unicode/backtick database identities. Parser errors and catalog/permission
failures retain their separate native classifications. Original-session active
roles, temporary objects and catalog binding are not inferred from the private
peer, and future-state script preflight remains separate acceptance.

This path requires observation access to performance_schema.threads in addition
to the existing variables_by_thread and session_account_connect_attrs views.
Denied/lost private parser context never substitutes an original-session query;
authenticated renewal acquires only a new private peer. Lost original identity
blocks source reuse. Profiles without an admitted observer retain explicitly
unqualified diagnostic-preservation status. Other retained metadata/completion
consumers and disabled/denied observer admission remain open.

When the retained C client's escape-mode acknowledgement differs from the
independently observed native language, parameter conversion now borrows the
retained private connection's stock C converter. Only that peer receives the
observed client character set and SQL mode; its native acknowledgement is checked
before conversion. Values retain the selected C driver's types and literal
conversion. The application does not invent literals, reconnect the source,
change its settings or infer transaction finality. Failure to confirm the private
conversion context refuses the current command and renews only the private peer
on a later authenticated request. Native fault qualification covers stale escape
status in four modes and utf8mb4/latin1, with exact quote/backslash/newline/NUL/
non-ASCII values and preserved source row counts. The source's converter is
prohibited during these fault cases, and native logs confirm no hidden source
metadata/settings commands.

Both Connector/Python interfaces are natively qualified across the four live
ANSI_QUOTES/NO_BACKSLASH_ESCAPES combinations, quoted Unicode SQL, database
switches, denied context and private-peer renewal. Native general logs confirm
no hidden parser/settings or PING commands on the source. Independent catalogs
confirm that future procedure/event/library definitions and DROP preparation
never execute. Event and library declarations have qualified native post-parse
classification on MySQL9.7.0. Library bodies remain opaque: their SQL declaration
syntax does not establish JavaScript validity or MLE execution, which remains
post beta. Native MySQL rejects dollar-quoted general SELECT literals.

Pure-client text escaping now represents NUL as a native backslash escape when
that language mode permits it, preserving loadable stored SQL definitions.
NO_BACKSLASH_ESCAPES keeps its native behavior. On the selected MySQL9.7 server,
a routine containing a raw NUL can be created but its subsequent CALL fails with
native error 3512; independent stock C and pure clients reproduce that refusal
in NO_BACKSLASH_ESCAPES mode. The adapter does not silently change SQL mode or
replace literal values with expressions having different grammar/collation rules.

The October 16 implementation adds native server/security/storage DDN review
and application, typed relation-data DDN import, named durable test-data recipes
and MySQL persistent monitoring history. These complement the existing editor,
SQL history, database DDN and graphical design, backup/restore, maintenance,
dashboard/collector and connection ownership workflows.

Server DDN changes use explicit ``native.mysql_change`` instructions while the
captured facts remain immutable. The server UUID, registered endpoint, exact
native address, current section visibility and reviewed baseline are checked
before each statement. Missing selections never request deletion. Accounts,
role/default-role edges, global/database/table/column/routine grants, native
plugins/components, tablespaces, resource groups, selected system variables and
replication channels use engine-specific compilers. Authentication secrets are
excluded; new DDN accounts are locked and authentication is administered
separately. An unavailable account identity cannot authorize a privilege change.
Routine privileges use effective native ``SHOW GRANTS`` observations rather
than assuming private grant-table storage encoding identifies an account.

Server reviews expire after five minutes, persist each dispatched statement's
unknown state before I/O, retain the acknowledged prefix and stop on refusal,
unconfirmed replies or failed rediscovery. Native server operations are not an
atomic transaction; advisory locks coordinate ScratchRobin only. Recent receipts
can be reopened after restart. Repeated requests never dispatch again.

Data import reads the paired DDN public workspace contract and preserves native
column order, types, character sets, spatial SRIDs and invisible columns. It
retains explicit AUTO_INCREMENT values including zero, omits generated columns,
and binds exact integers, decimals, dates/times, JSON, opaque text, binary,
geometry and VECTOR data. VECTOR parameters explicitly use binary character
semantics without converting their float32 bytes. Import owns its transaction,
revalidates metadata while holding its metadata lock, commits explicitly and
independently rereads primary-key postimages. Native constraints/triggers remain
active. Nontransactional engines require an explicit acknowledgement and report
partial effects. Unknown COMMIT replies remain unknown. Imported rows disappear
from durable reviews before dispatch and never appear in public receipts.

Named test-data recipes use immutable project-asset revisions with owner,
endpoint and registered-database binding and optimistic version checks. Reading
a recipe, historical SQL or a DDN document never executes SQL. Human form
validation remains assigned to the UX team.

Reproducible gates (refresh DDN first; evidence belongs outside the repository)::

    python tools/cdeadmin_mysql_tasks_gate.py --output /work/mysql-tasks --ddn-work /work/ddn --mysqlsh /path/to/mysqlsh
    python tools/cdeadmin_mysql_catalog_completeness_gate.py --output /work/mysql-catalog
    python tools/cdeadmin_mysql_completion_gate.py --output /work/mysql-product
    python tools/cdeadmin_mysql_extended_gate.py --output /work/mysql-extended
    python tools/cdeadmin_monitoring_history_gate.py --config /etc/cdeadmin/history.json --engine mysql

The first four commands default to uniquely owned MySQL 9.7.0 Docker fixtures.
The product and extended gates also accept a credential-free ``--route`` JSON
and a ``--password-env`` variable for a disposable native estate. They qualify
both Connector/Python implementations. The native Windows/macOS fixture workflow
runs these portable consumers after the driver proof, retaining their separate
receipts. Native resource-group availability comes from the serving engine,
not the client operating system.

Managed physical clone admission now persists archive protection before native
SQL dispatch. Local clones protect their observed native source. Remote clone
holds cover both the reviewed donor registration and recipient registration;
their holds retain all registration archives because the clone protocol does
not attest its source UUID. Lost replies and interrupted observers retain
protection. Original SQL acknowledgement is persisted before later observation
or protection bookkeeping, and remains distinct from those outcomes. Clone
worker, observer and donor connections are owned independently of interactive
client shutdown. Current native roles are part of their reviewed identity.

The existing managed backup protection viewer inspects these physical clone
holds and supports explicit reviewed retirement without deleting clone files.
These conservative holds neither calculate recovery-chain dependencies nor
discover other registrations/external backups, attest native log epochs or
establish physical recovery acceptance. The native qualifier is
``tools/cdeadmin_mysql_clone_qualification.py --evidence <outside-repo>
--mysql-binlog <native-binary>``; run local/``--remote`` and default pure/
``--use-c`` interfaces separately. Optional browser/driver paths exercise clone
and protection review/retirement through the built desktop.

The physical clone workspace supports local and registered remote donors into a
new recipient-server directory. Remote reviews bind both native identities and
registrations, require explicit credential delegation, and preserve native TLS,
allowlist and privilege admission. Native completion, file verification and
independent recovery remain separate outcomes. Active-directory replacement,
production cutover and the wider physical continuity surface remain open.

Logical backup and restore use a private temporary JSON credential file for
native Shell authentication. Password newlines, carriage returns, quotes,
backslashes and Unicode retain their exact values; second/third factors retain
their registered positions. Credentials are absent from command arguments and
generated operation scripts. The registered native TLS/compression policy
applies to the utility connection. Script and credential files are released
after the utility call, including failures; a missing return never retries the
backup or restore. Native factor dispatch wiring and installed authentication
plugin acceptance retain their separate qualification scopes.

Database Restore includes a separate **Verify restored dump data** operation.
It compares the selected database with a completed checksummed MySQL Shell dump,
including a renamed target schema. The native utility runs with definition,
data, index and user loading disabled, no progress resume, no ANALYZE and no
GTID update. Its independent session must match the captured server UUID,
version, authenticated principal and active roles before checksum dispatch.
The provider review binds that native identity, utility identity, execution
host and complete artifact hashes. Changes before application require a new
review before any verification lock or setting change.
Native dump common preamble/postamble scripts still execute in private sessions;
the operation requires a trusted dump and restore administration authority.

The exact database confirmation also authorizes a native server read lock,
which pauses writes across all databases during acceptance. Independently read
base-table inventories and full row counts supplement native chunk checksums:
an extra row outside a checksum boundary cannot pass acceptance. Empty tables,
duplicate/NULL rows, Unicode and binary values retain native checksum semantics;
the application does not implement a replacement checksum algorithm. Complete
metadata and checksum coverage, stable artifact hashes, exact native identity,
and the checksum utility's successful return are all required. An explicitly
authorized temporary local_infile enablement is restored afterward. Lock and
connection cleanup also run after utility failure.

Verification creates its own provider operation result and never reruns a
restore or rewrites its outcome. Native checksum failure, row-count mismatch,
extra target tables and unavailable evidence are unsuccessful acceptance.
This verifies dumped table data during the recorded write pause; object
definition equality, physical recovery, later log replay and production cutover
have separate acceptance requirements.

The binary-log archive workspace integrates native MySQL Shell9.7
``util.dumpBinlogs`` on the explicitly recorded application host. It inspects
available logs and GTID lineage, reviews a native file/position or verified
previous archive, and records a durable claim before dispatch. New archives use
private owner/endpoint/job directories. Native none, gzip and Zstandard
compression, thread count and bounded or operator-permitted unbounded runtime
are exposed. The registered TLS policy and multi-factor credentials apply to
the utility's independent session; credentials travel in a private temporary
JSON file that preserves newline and Unicode passwords and is erased afterward.

Its separate **Native server log administration** section integrates native
``PURGE BINARY LOGS TO`` and ``PURGE BINARY LOGS BEFORE``. TO uses the server's
ordered log index and retains the selected boundary. BEFORE uses an explicit
UTC session and the native server's file-timestamp evaluation; the review lists
potential closed logs, without inventing file modification times in the
application. Both GTID-enabled and disabled native servers are supported.
Reviews bind the source UUID, principal/role, registration, adapter and observed
log index. Changed indices or observed native GTID lineage require a new review.

Explicitly confirmed purges have durable, owner/registration-bound receipts.
The native SQL acknowledgement is recorded before warning collection or
independent postcondition reads. A missing acknowledgement stays unknown through
reconciliation, even when files are now absent, and a duplicate start never
replays the command. Cancellation requests native KILL QUERY only for the
confirmed private native thread, connection, handshake and active purge command;
removed files are not rolled back. Unavailable cancellation authority is exposed.
Native warnings, errors and observed removed/retained filenames remain separate
facts. Admitted connections belong to the job and are independent of interactive
client shutdown; closing a viewer does not cancel authorized work. Status and
saved receipts are available offline.

This server administration action leaves application archive bytes and their
retention policies separate. Operators must check backup and replica requirements
in an exclusive administration window. The action does not discover recovery
dependencies, attest a native log-generation epoch, or establish recovery/cutover
acceptance. Those broader product requirements remain open.

Completed archives reconcile native completion metadata, source UUID, every
file's size/SHA256, streaming v4 event framing and CRC32 where the native log
contains checksums. Native checksum-disabled logs are identified explicitly.
Continuation stages an independent immutable input. A native no-op records no
new archive and never advances a continuation cursor. Restart/lost workers stay
unknown without replay; artifact verification does not assert process finality.
Receipts and paged file inventories remain available offline. Authenticated file
downloads verify retained bytes; explicit identity-confirmed removal keeps the
receipt. ``CDEADMIN_MYSQL_BINLOG_ROOT`` and
``CDEADMIN_MYSQL_BINLOG_MAX_RUNTIME_SECONDS`` are operator settings.

The separate raw archive workspace uses native mysqlbinlog9.7.0 for contiguous
closed-log ranges with GTIDs enabled or disabled. Native current-file observations
bracket catalog reads, and full file lengths are checked independently from
framing, CRC and native parser verification. MySQL's native v1 encryption header
is accounted for when the replication stream delivers decrypted bytes. These
private raw archives contain plaintext events even when the source files were
encrypted. The raw utility's single-password-factor limitation is explicit;
additional factor bindings are refused. It has its own format, verifier, durable
storage and authenticated file-delivery scope.

Native MySQL Shell replay is also integrated through the restore menu. It selects
a sealed Shell archive and a separately confirmed target UUID, checks native
GTID lineage and supports complete, stop-before and stop-after GTID boundaries.
Durable target fences, native locks and final GTID checks protect dispatch.
Missing acknowledgements retain unknown outcomes without automatic replay;
current target observations and exact acknowledgement have separate receipts.
Utility return, native GTID coverage and independent recovered-data verification
remain distinct. The source can be offline after the archive has been sealed.

These are scoped archive/replay workflows. A compatible restored base is required;
complete end-to-end PITR, physical continuity and production cutover retain
separate product acceptance. Complete stopped closed-log files
can be separately reviewed, checked against native source/file postimages and
adopted into ordinary verified archives. Active/incomplete files are refused;
the parent outcome and recovery acceptance remain independent. Clean stopped
receivers now support a separately reviewed restart from their exact retained
next-log checkpoint, with source and native-writer rechecks. Interrupted writers
have an explicit owned-process reconciliation which does not verify their
artifacts or authorize checkpoint restart of an unknown outcome. MySQL also
offers a separate, explicitly acknowledged full recollection from the original
native starting file. It requires stopped writers and a currently available
original file, rechecks source identity and GTID mode, and checks the prior GTID
baseline natively when GTIDs are enabled. A missing/purged original file, changed
source/mode, or lost GTID lineage refuses admission. It never uses an uncertain
next-file cursor, modifies the old receiver outcome, or replays SQL. Previously
published changes can be collected again into independent archives. Native GTID
admission is distinct from binary-log epoch proof and database recovery; neither
is inferred, including on GTID-disabled profiles. MariaDB's
distinct native archive workflow is documented in
:doc:`mariadb_functional_completion`.

Private receiver inputs also have reviewed offline cleanup, including a paged
inventory, exact file-postimage admission, a shared adoption/removal filesystem
claim and per-file removal acknowledgements. Unknown/partial outcomes remain
explicit and are never automatically repeated. Published archives and receipts
are retained. This is separate from scheduled or recovery-chain-aware archive
retention and native server log purging.

Interrupted MySQL private-input cleanup now has explicit offline reconciliation.
It rechecks the owner, endpoint, original native source, recorded application
host/filesystem grants, stopped writers and the shared file claim. Only the
single file covered by the persisted pending removal intent is eligible: an
unchanged reviewed file may be removed, or its existing absence observed.
Replaced files, links, changed review scope and live workers refuse
reconciliation. Files whose removal was never attempted remain for a new review.
The original progress and missing unlink acknowledgement remain unchanged;
newly acknowledged removal bytes and observed absence are separate results.
Repeating reconciliation only reads the completed receipt and cannot remove a
file that later reappears. Neither the parent receiver outcome nor any published
archive is rewritten. Process-restart and lost-reconciliation-acknowledgement
tests cover the same boundaries. Native API qualification injects a lost ACK
after removing a real receiver input, reconciles with the source stopped, checks
unattempted files and downloads the independently sealed archive unchanged. The
production browser also performs that explicit reconciliation offline.

MySQL Shell and raw archive workspaces now provide reviewed retention and
explicit protection of individual archives. Set an age threshold and a minimum
retained count for each exact native source/principal/role, inspect the oldest
100 eligible archives and their byte totals, then confirm that exact review.
The inventory scans all receipts and fails closed on unreadable receipts.
Protected, active, uncertain, unverified and already removed archives are
excluded; protection applies to ordinary single-archive removal as well.
Protect every archive required by a base backup or recovery target: age/count
rules do not infer a recoverable chain. No scheduled deletion or native server
log purge is implied.

Scheduled age/count retention is available separately for Shell and raw archives.
Inspect a retained verified archive to select its exact native source, principal
and role, review the age/minimum count, scan interval and policy lifetime, and
explicitly authorize future archive removal. The policy can include newly
published archives of that identity, expires within 365 days and can be disabled.
Scans run without an open viewer or database connection and restore from durable
policy markers when the application starts. Each occurrence freezes at most 100
candidates, verifies native sealed bytes and records its own ordinary retention
receipt before removal. Protections and the minimum retained count are rechecked
at every dispatch. Other native identities never enter the policy.

Owner deactivation, permission/registration changes, changed adapter or execution
host, expired authority, interrupted preparation and unresolved prior occurrences
suspend scheduling. An interrupted occurrence is never restarted automatically:
reconcile its recorded removal intents, then review a new policy. Disabling
revokes future dispatches and requests cancellation of its active occurrence;
an already admitted file removal can finish. Native API qualification covers both
Connector/Python interfaces, both archive formats, background removal with the
source paused, scheduler restart and later actual native publications under the
original policy. Independent source observations and retained archive bytes are
unchanged. The production browser reviews, enables, observes and disables a
policy while the source is paused. These are local retention workflows; backup
dependency discovery and recoverable-chain protection remain separate work.

Retention verifies sealed archive bytes before review and again before removal.
Receipt/protection changes invalidate removal; new archives never enter an
existing review. Removal persists an owner/endpoint/host-bound intent before
detaching a private directory, keeps operation receipts, and acknowledges the
final absence separately. Explicit reconciliation resumes only recorded intents
belonging to that retention job and reports unattempted archives and other
removal authorities separately. It does not run a new retention scan. Added or
changed entries, replaced directories, links/reparse points, and an unconfirmed
native process refuse removal. Single-archive cleanup has the same durable
intent and explicit reconciliation. These workflows remain available while the
source is offline.

Qualification covers native MySQL9.7.0 Shell and raw archives through both
Connector/Python interfaces, authenticated ownership/registration boundaries,
protection changed after review, interrupted detachment and explicit
reconciliation with the server paused. The production browser also performs
retention with the server paused; independent native observations verify
unchanged source GTIDs, logs and exact wide-integer/Unicode/binary data.
Fault tests separately cover partial deletion, lost acknowledgements, a new
application process, changed files/directories and bounded large inventories.
These receipts qualify archive retention. Native receiver qualification also
covers explicit full recollection through both client interfaces and GTID ON/OFF
profiles, including independent source-file comparison and preservation of the
unknown parent. The production browser reviews and dispatches a new collection,
observes its verified archive and cancels it independently.

Retained receiver archives now also provide a separately reviewed native
successor checkpoint after the original source file has been purged. Inspect the
receiver's paged archive index, select a retained verified publication, inspect
its native successor, acknowledge the boundary, and review a new receiver. The
successor comes from its terminal native rotation or from the native closed-log
catalog observation sealed with newly published archives. The latter preserves
shutdown/restart boundaries that have no rotation event. Older archives without
either observation cannot authorize a guessed successor. Source UUID/principal,
GTID mode and applicable native GTID baseline must still match, and the exact
successor must remain on the server.

Successor inspection is bounded and explicitly does not claim fresh full-file
verification. The new receiver worker verifies every sealed file hash, complete
native framing/CRC and the reviewed archive digest before dispatching the native
reader. Corrupted/removed archives, changed metadata, foreign producer receipts,
unconfirmed writers, changed source and purged successors are refused. Raw
retrieval/parser utilities must acknowledge process cleanup before publication;
a zero exit code alone is insufficient. The old receiver remains unchanged;
archive boundaries do not establish a binary-log generation ID, transaction
finality or complete backup/log recovery coverage.

Native API qualification covers both client interfaces and GTID ON/OFF profiles,
including actual source purging, body-corruption refusal before reader dispatch,
checksum NONE, native shutdown/STOP and same-instance restart, independent
comparison with server file bytes, and once-only dispatch. The production
browser inspects and selects the retained checkpoint, reviews and starts its
new reader, observes a sealed batch and cancels it. Complete backup/log recovery
and production cutover remain separate acceptance work; automatic discovery and
protection of backup/log-chain dependencies remains open.

Raw archives also have a native replay adapter in the restore workspace. It
uses mysqlbinlog9.7.0 to decode sealed logs and mysql9.7.0 to apply them to an
independently confirmed target. Select full replay or exact native transaction
group boundaries. Native file positions remain decimal strings, including values
above JavaScript's safe integer range. Event-header times are displayed separately
from commit-time recovery targets.

GTID-enabled replay checks the starting lineage and skips native GTIDs already
present. GTID-disabled recovery can resume at an explicitly reviewed group start;
the operator must independently verify the corresponding recovered base. Native
target log-file/position, UUID, principal, role and configuration are checked
again inside the applying client. Inspection needs SELECT on
``performance_schema.log_status`` and native ``BACKUP_ADMIN``. Replay requires
the native privileges for the archived operations. The mysql client has its own
version/hash admission through ``CDEADMIN_MYSQL_CLIENT_BINARY``; mysqlbinlog uses
``CDEADMIN_MYSQL_BINLOG_BINARY``. Both execute on the recorded application host.

Raw and Shell replay share durable target fences and the same native lock.
Native LOAD DATA fragments stay inside a private execution directory; the client
does not receive unrestricted local-file loading. Credentials use a private
native option file with their original factor positions. Lost replies remain
unknown, require fresh reconciliation before acknowledgement and never replay
automatically. Native utility return and GTID/log-position observations do not
verify recovered application data. Cross-platform utility provisioning and full
PITR/cutover acceptance remain separate.

The query editor's lexical parameter path and ordinary native cursors share
live character-set conversion. MySQL latin1 uses its native Windows-1252/C1
mapping, including the Euro sign; Python's narrower latin1 codec must not reject
or alter those parameters. Native qualification covers positional and named
values, source/result character-set differences, SQL-mode escaping, independent
Unicode code-point checks, pending transactions/savepoints and pooled reuse on
both Connector/Python implementations. This does not qualify changes of
character set or SQL mode within a parameterized multi-statement batch.

The existing consolidated administration receipt covers 105 declared tasks.
Three additional spatial-reference-system tasks have separate native
qualification; this does not expand the older receipt's recorded scope. Independent
catalog reconciliation compares 30 categories plus native DDN child facts for
privileged and restricted accounts and checks navigator reachability. These are
separate from broader product, browser and platform acceptance.

Native physical backup artifacts
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The server Backup menu exposes :doc:`mysql_physical_backups`: native
XtraBackup9.7.1-rc1 full backups, preparation of a separate copy and copy-back
into a new private data directory on the pinned database SSH host. Exact
release/source identity, executable fingerprints, native SQL account/roles,
UUID and file manifests bind reviewed execution. The supported artifact scope
is self-contained, uncompressed and unencrypted MySQL9.7.0 InnoDB/MyISAM/CSV
instances. Release-candidate use and database credential delegation require
separate explicit confirmations.

A detached host supervisor records native replies before subsequent hashing,
file publication and credential cleanup. The application accepts dependent
artifacts only after those facts are independently observed. Original lost
dispatch replies remain unknown and never trigger another launch. Prepare
preserves the base; copy-back cannot overwrite the live source. Later
observation and preparation do not need a surviving live source. A durable
source-wide archive hold precedes backup dispatch.

The native qualifier covers both Connector/Python interfaces, a Unicode default
role and a password containing line-feed, quotes, backslash and Unicode,
preserved independent pending transactions/savepoints/warnings, lost replies,
once-only admission, all three native artifact phases and independent
disposable MySQL recovery of InnoDB/MyISAM/CSV rows, unsigned64/Unicode/BLOB
values, a view and a routine. The production desktop runs the same phases.
These cases establish the recorded artifact scope. Managed native recovery
instances now use a separately reviewed private data copy, native configuration
geometry, a fresh target UUID, private Unix socket and native read-only startup.
Version/account/roles/paths/isolation SQL observations are retained independently
of current process presence. Credentials are removed after startup inspection.
Explicit process-descriptor shutdown and lifetime expiry target the original
native process birth. Shutdown after supervisor loss preserves unknown native
exit replies and separately observed termination; original copy-back bytes stay
intact. Pure/C/API and desktop native receipts qualify this bounded scope.
The recovered native editor/catalog now has a separate owner-scoped registered
connection over a pinned, process-bound SSH byte stream. A reviewed optional
loopback TCP listener preserves native MySQL authentication/TLS and the full
driver protocol. Native target UUID/version/data-path checks, independent
registration observation after reply loss, explicit restart reattachment and
a native connection lease guard protect detach/replacement lifecycle. Source
sessions remain separate. Separately reviewed writable startup now admits a
native server ID/private ROW binary logs; leased native mysqlbinlog/mysql raw
replay covers selected before/after/all boundaries and unknown native replies.
Original decoder/client guardians now retain separate immutable references,
hash-verified private stdin and cancellation after observer loss. Reconciliation
observes both utilities and cleanup before releasing the matching parked lease;
the database outcome remains unknown and target acknowledgement still requires
the exact UUID, current facts and a free native replay lock. Managed recovery
Shell replay now admits its extra native SQL connections and reconnects over
that same route on POSIX application hosts. Its guardian and native process
inherit the loopback listener reservation, preserving it after application
loss. A separate original Shell guardian reference supports interruption
inspection and cancellation without changing unknown database outcomes.
Original utility inspection/cancellation now works without a live SQL relay.
New replay reviews retain their exact owner/endpoint/recovery binding; only
confirmed original termination releases that job's parked reservation, allowing
a separately reviewed reattachment. Staged-input cleanup preserves the source
archive. Target acknowledgement still needs fresh SQL identity/lock facts after
reattachment, including native active-session checks for the original login;
a still-running Shell worker statement keeps acknowledgement blocked even if
its guard connection has closed. Legacy missing-binding receipts remain conservative.
Windows listener inheritance, missing/failed guardian reconciliation and wider lifecycle handling,
incremental/encrypted/external-path admission, physical retention,
selected replay and independent post-replay acceptance, production cutover and
the broader native inventory remain open. ``CMP-MY-01`` stays
open; ten of eleven comparison items are implemented and Linux-qualified.

Persistent-history integration is wired. The owner correction of October 16
defers ScratchBird history testing until explicitly resumed. The earlier native
startup attempt failed its durable agent catalog seed with ``SECURITY.CONTEXT.EXPIRED`` / ``CATALOG_MUTATE`` before
archive SQL. No fallback database or security bypass is used. Windows/macOS
evidence remains with the platform teams and must match the final source before
cross-platform completion is claimed. Signing/release approvals remain separate.

MySQL registration lifecycle admission
------------------------------------

MySQL now participates in the registry's configuration-change admission and
release hooks. Retained SQL sessions block profile/route/credential changes,
database-target removal, disconnect and registration removal even when idle:
temporary tables and prepared statements belong to that native session.
Dedicated catalog/collector connections, connections still being initialized,
uncertain sessions, active execution workers and synchronous native utility
operations also retain their ownership. Admission remains held through release
and local metadata persistence; a released client cannot open another session,
dedicated connection or credential-delegating native utility operation.
Operators explicitly finish pending work and close the sessions first. Failed
admission does not commit, roll back, cancel or replay native work.

Recovery transport admission additionally checks independent original utility
leases even when no SQL provider binding remains. Those leases prevent generic
registration mutation as well as transport detach/replacement. An admitted
disconnect/removal releases the idle process-bound recovery transport. MySQL's
server Disconnect action now uses endpoint lifecycle handling instead of the
PostgreSQL connection manager.
Legacy PostgreSQL-style update/delete routes refuse MySQL registrations and
direct the caller to the existing provider forms, preserving their lifecycle
admission and exact removal confirmation.

``tools/cdeadmin_mysql_registration_lifecycle_qualification.py --output
<external-directory>`` qualifies the actual workspace and server-disconnect
HTTP routes against owned MySQL 9.7.0 fixtures with both Connector/Python native
implementations. Eleven checks per implementation cover refused edits/removal,
transaction/savepoint/temporary/prepared-state preservation, explicit rollback
and session closure, stale-client rejection, fresh verification and successful
idle removal. Regression checks also cover concurrent connection admission,
native utility callbacks, release failure and independent recovery reservations.
This closes the recorded generic MySQL registration lifecycle follow-up, not
the wider host/recovery inventory. ``CMP-MY-01`` and ``INV-MYSQL``
remain open. Windows/macOS native acceptance remains with the platform teams;
ScratchBird history qualification remains owner-deferred.

Reviewed physical artifact retention
------------------------------------

``CMP-MY-01`` now includes native-host pin/review/removal/reconciliation for
individual physical backups, prepared copies, isolated copy-back and stopped
recovery data/private binary logs. Durable application and SSH-host admission
protect input dependencies, native process ownership and retained recovery
registrations. Interrupted cleanup resumes only its exact detached filesystem
intent. Unclaimed review invalidation fences late dispatch. Original native
outcomes and output are preserved; completed file inventories are compacted.
See ``mysql_physical_backups.rst`` for the workflow and limits.

``tools/cdeadmin_mysql_physical_replay_qualification.py --retention`` adds owned
native Python/C chain-retention and built desktop evidence to the physical and
replay qualification. This closes the individual-artifact cleanup gap. Reviewed
age/count batches now preserve the newest verified full-backup chains, their
descendants and all inputs of retained jobs. Each step checks current graph
admission and the host rehashes retained full backups under its admission lock.
The fixed deletion set supports pause, independent restart observation,
explicit interrupted-item resume and unused-review invalidation. Scheduled
physical retention now adds explicitly delegated, encrypted and expiring SSH
access, independently polled occurrences and revocation between steps. Changed
authority or interrupted occurrences suspend future work without automatic
retry. Public receipts omit encrypted credential material. Recurring full-backup
policies now add encrypted SQL delegation through dedicated connection owners,
optional native prepare/copy-back/read-only startup/stop pipelines, durable job
binding before dispatch and retention protection for unresolved occurrences.
SQL startup remains distinct from independent data/definition acceptance.
Managed recovery targets now support explicit expected-dump acceptance of full
counts, native checksums and exported SQL definitions, including after native
replay. Private-socket startup works without a TCP listener; trusted checksum
input is an explicit reviewed startup choice. Original utility leases and
independent termination observations preserve unknown checks after relay loss.
Recurring expected-checkpoint policies now start fresh private read-only
recoveries, compare them to a selected sealed native dump and independently stop
them. Durable input holds, encrypted SSH/SQL delegation and explicit interrupted
utility/server-generation release preserve original outcomes. Unexported/system
state, remaining physical backend admission and production cutover stay open. ``CMP-MY-01`` and ``INV-MYSQL`` still precede
the MariaDB implementation handoff; the comparison count is ten implemented items out of eleven.


Native physical incremental recovery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Reviewed native incremental jobs now retain their exact full-backup lineage and
LSN checkpoints. Separate redo-only copies apply a privately staged next delta,
then final native preparation performs undo before copy-back. Both original
inputs and their ancestry are retained by manual, batch and host-side dependency
gates. Unknown original dispatch replies remain unknown after independent native
publication; no utility is automatically repeated. Native recovery and selected
expected-dump data/definition acceptance qualify the restored checkpoint.
External path mappings, additional engines, unexported/system state,
production cutover and the wider lifecycle/inventory gates remain open.

Native physical TLS and additional storage engines
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Physical backup delegation now carries exact registered CA/client certificate/
private-key files privately over pinned SSH, preserving native certificate and
hostname verification, TLS versions and ciphers. Reviews expose fingerprints
and policy; private client files are removed after use. Isolated recovery can
stage separately reviewed host server TLS files on its own loopback listener,
supporting X.509-required accounts and the process-bound native editor route.
Expiring encrypted worker delegation carries TLS material for recurring backups
and native startup drills after interactive credentials are erased.

ARCHIVE, BLACKHOLE and self-contained MRG_MYISAM physical recovery join
InnoDB/MyISAM/CSV. Native MEMORY definitions survive with empty-after-restart
semantics; volatile source rows are disclosed. MERGE member metadata now uses
native final database/table identities, including absolute/escaping prefixes,
with complete MyISAM child payload and original metadata bytes retained. The native
qualification exercises both drivers, real hostname mismatch, policy tampering,
incremental recovery, live/restored MERGE separation, recurring worker restart
and the built desktop. The pinned XtraBackup backend exposes one password slot;
existing MySQL MFA driver support is preserved rather than emulated in that
utility. External mappings, remaining engine
inventory, unexported/system-state acceptance, interrupted legacy/guardian
resolution and production cutover remain open. These additions do not close
``CMP-MY-01`` or the broader MySQL product matrix.

Native encrypted physical recovery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Explicit native GPL file-keyring retention supports encrypted full/incremental
backups, source master-key rotation, private native redo/final preparation and
copy-back. Each chain retains opaque native keyring bytes and a private native
transition key. Managed read-only and replay recovery stage separate plugin,
dependency and keyring copies; native SQL readiness verifies the actual keyring
path and redo/undo/binlog encryption policy. Recovery-side key rotation preserves
the source and sealed inputs. Recurring backup/startup-drill delegation includes
this admission after worker restart. Durable keys follow physical dependency
retention; ephemeral credential files are cleaned separately. Native utility
failures and unknown original replies remain separate from verified artifacts.
This source-backed file-keyring workflow does not implement other keyring
providers or close the remaining external mapping, system-state, guardian and
cutover requirements. See :doc:`mysql_physical_backups`.

Native external InnoDB recovery isolation
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

External per-table InnoDB files and general tablespaces now use explicitly
reviewed native copy-back maps and private Linux mount namespaces. Native
datadir/data/undo aliases consistently select private copies; the rest of the
host view is read-only. Native encrypted incremental recovery, external DDL and
literal child path names preserve source bytes. Actual process namespace and
directory/mount facts gate editor admission; uncertain facts retain independent
original-process cancellation and unknown database outcomes. Recurring drills
and physical retention cover the same private external files. The backend
requires admitted Linux64 mount privileges. Missing original alias directories
now use complete private parent projections; absent top-level paths additionally
require a separately probed private root switch. No original host directories
are created. Native encrypted SQL recovery with the source server offline uses
the same directory aliases and private keyrings. The original process remains
observable and stoppable after executable pathname replacement because its
actual executing image and birth identify it.

Retained native storage metadata now binds system-file specifications, default
and user undo locations and configured empty scan directories to native backup
artifacts. Private prepare/copy-back destinations and separate runtime payloads
preserve original native path semantics without rewriting pages or dictionary
contents. Native encrypted incrementals, key rotation, literal system-file names,
recurring startup drills and source-offline recovery with missing parent/root
directories are qualified through both connectors. Native relative homes and
scan roots retain original settings and effective paths; system and undo
catalog names use their native data-home/datadir bases. Nested homes and leading
parent references feed the same encrypted recovery and source-offline workflows.
Circular paths now retain observed native filesystem resolution and original
catalog spellings, including symbolic links followed by parent traversal.
Private runtime paths and offline audit use the sealed canonical mapping;
encrypted incrementals, recurring drills and missing parent/root recovery are
qualified through both connectors. Native fixed/autoextended raw system files
and multiple system-file copy-back now use a source-qualified reader and private
file aliases. Qualification includes system-space payloads, native incremental
recovery and source-offline editors with missing device nodes. Remaining native version/layout
inventory and the broader recovery/inventory gates remain
open. Unmapped geometry refuses before native preparation or copy-back.
See :doc:`mysql_physical_backups`.

Original physical recovery reconciliation and MERGE identities
---------------------------------------------------------------

Native MERGE absolute/escaping metadata prefixes now retain MySQL dictionary
and table-cache child identities, with complete data/index payload. Full backup,
preparation, copy-back and recovered reads/inserts preserve original metadata
and keep the live source separate through both connectors.

Physical reconciliation/output/original-process stop use the original pinned
host after adapter or registration changes. A missing duplicated binding can
use matching retained original host facts without rewriting the review. Actual
preceding-adapter supervisors, supervisor loss, source SQL shutdown, changed
registration generations and rejected conflicting source UUIDs are exercised.
Original unknown outcomes remain unknown after independent process-end evidence.
Wider utility/guardian recovery, inventory/system-state and cutover remain open.


Independent original native utility cleanup
------------------------------------------

Linux instance dumps, loads, acceptance checks and Shell/raw replay clients now
request a kernel parent-death policy from their isolated guardian. A lost
guardian cannot leave those newly dispatched clients running indefinitely.
Independent observation checks the original boot, process namespace, admission
marker, guardian lock and original native session before confirming termination.
It removes only identity-checked private credentials and staged input. A missing
completion receipt remains missing: process cleanup never supplies a return code,
changes the original database outcome or retries a load/replay.

Native topology clients now use the same Linux guardian-death policy. After
independent termination, the original nonce-bound progress receipt preserves
the historical client PID and process birth even when the final utility receipt
is missing. Invalid or foreign progress cannot supply that identity. Recovery
uses it to inspect the original member connections separately from utility
termination. Both connectors qualify actual guardian loss during SQL fanout
blocked by native locks on all three Cluster members: acknowledgement remains
refused while server work survives, becomes available only after independent
member-session absence and clone idleness, and preserves the original unknown
outcome without replay. The native command is
``tools/cdeadmin_mysql_router_qualification.py --topology-faults-only`` with an
explicitly owned three-member fixture and native Shell executable.

Older managed client references can be reconciled after guardian loss when the
original living client can still be identified. Original command, executable,
process birth, user and session must match before a separate witness is saved.
Explicit cancellation uses that client's kernel process handle. Missing original
identity, changed files, extra session members or unavailable host facts retain
an unconfirmed result. Untracked jobs without those facts require separate
handling; there is no general force-release action.

Instance restore receipts expose original utility observation without a SQL
connection. Releasing a matching process reservation remains separate from fresh
SQL observations and explicit acknowledgement of an unknown target outcome.
Both native drivers qualify worker loss, guardian loss, a missing completion
receipt and a legacy managed orphan. The built desktop qualifies the independent
observation control. These receipts do not close inventory/system-state recovery,
production cutover, ``CMP-MY-02`` or ``INV-MYSQL``.


Independent native system-table recovery checks
-----------------------------------------------

Expected native instance dumps now optionally seal selected system-table
checkpoints under source backup/read locks. Independent acceptance compares
native definitions, column metadata, complete counts and row-multiset digests
without importing system tables. System differences remain separate from
exported data/definition/account results and fail the selected acceptance.
Physical recovery qualification covers all 25 admitted native system tables;
logical/API checks exercise a foreign-server difference and a lost source-unlock
reply with independent original-session cleanup observation. See
:doc:`mysql_physical_backups` for checkpoint selection and the remaining native
runtime, host-state and cutover boundaries. ``CMP-MY-01`` stays open.


Unavailable original utility evidence
-------------------------------------

Older receipts without an original durable utility reference now record an
explicit unavailable-evidence diagnostic. SQL-independent inspection neither
signals a guessed process nor confirms termination, changes the database outcome
or releases target protection. Backup, restore, replay and acceptance views show
that limitation. Existing positive native cleanup facts remain unchanged.
Original facts that were never retained cannot be reconstructed from current SQL
state; these receipts remain unknown when their required evidence is missing.

For multi-client raw replay, each original decoder/client observation is collected
even when another original reference is missing, changed or unreadable. Each
failed observation remains unconfirmed. Aggregate cleanup requires all admitted
original clients; one successful observation cannot clear a partially observed
operation. This completes the unavailable-evidence handling, without asserting
that a historical operation with missing facts has become recoverable.


Reviewed native host option-file deployment
--------------------------------------------

The native host workspace now installs an explicitly reviewed replacement for
an existing MySQL option file. Upload exact bytes or edit UTF-8 text inside the
workspace. The private job retains the bytes; public review fields contain their
digest and the prospective native include graph. Native file ownership, permissions and extended attributes (including native
POSIX ACLs) survive installation. A private original-file copy remains with the
host receipt. Option values can appear in native diagnostic output, which is
scoped to the job's authenticated owner.

The Linux adapter validates the proposed bytes with the pinned native mysqld in
a private child mount namespace at the original configuration filename. Relative,
home, directory, symlink and circular include semantics use the existing native
configuration observer. Validation does not substitute a differently named root
file. The SSH account needs native mount-namespace and file-replacement
authority. Native refusal leaves the selected option file unchanged.

Original and prospective include graphs bind review and dispatch. Changing an
included file requires a new review. After successful native validation, the
adapter rechecks the original file/parent identities and bytes, retains a private
original copy and atomically replaces the selected resolved file. It does not
restart the server or claim SQL readiness. Later configuration observations stay
separate from the original installation result. Concurrent installers lock the original file inode; external writers are
not frozen. Repeated dispatch and lost-reply reconciliation never reinstall the
file automatically; read-only reconciliation can use the recorded host request
after local adapter or registration configuration changes.

This implements the option-file deployment part of ``CMP-MY-02``. Production
native upgrades, Router deployment/traffic and the
remaining topology failure/repair and recovery cutover gates remain separate.
Windows/macOS implementation and qualification stay with the platform teams.


Native data-directory initialization before SQL registration
-------------------------------------------------------------

The native host workspace initializes a new or native-empty Linux MySQL data
directory through authenticated, pinned SSH. An unverified MySQL registration
can open this workflow without a working SQL connection. Review records host,
boot/process namespace, native executable and option-file graph, selected data
directory and parent identities, native user option and secure-password mode.
There is no invented pre-initialization server UUID. The successful native
initializer creates the UUID read from its new ``auto.cnf``; SQL readiness remains
a separate observation. Native hidden entries and ``lost+found`` remain intact;
existing engine data or changed reviewed inputs refuse before dispatch.

Both secure ``--initialize`` and explicit ``--initialize-insecure`` use the
pinned native MySQL9.7 executable. MySQL owns option precedence, filesystem
ownership, bootstrap errors and password expiration. Secure initialization
emits its temporary root password into the private owner-scoped native output.
No command string or application-generated system tables substitute for native
initialization. Partial files remain after failure, timeout or cancellation.

A detached guardian admits the initializer once and holds private output files
across SSH/application loss and native user changes. A canonical directory claim
prevents another workspace from dispatching a competing initializer. Explicit
cancellation addresses the original guardian; after guardian loss, cancellation
requires the original process birth, session and kernel process handle.
Independent reconciliation checks the original boot/namespace, admission marker,
guardian lock and original session. Releasing a directory claim requires observed
writer termination and explicit acknowledgement. Missing admission or process
facts retain protection. Native completion, original SSH acknowledgement and
later writer observations remain separate; a missing native result is not filled
in and initialization is never automatically retried.

This implements the initialization part of ``CMP-MY-02``. Service creation is
described below. Native upgrade acceptance, Router deployment/traffic, topology failure/repair
and production recovery cutover remain separate completion gates. Windows/macOS
implementation and qualification remain with the platform teams.


Reviewed native Linux service installation and boot controls
-------------------------------------------------------------

The database-host workspace installs a new native systemd unit for an observed
MySQL UUID/data directory and executable. An existing online source can supply
the binding, or a completed native initialization receipt can supply it before
a SQL endpoint exists. The latter is explicitly labelled a previous initializer
identity, checked again through authenticated SSH and the native ``auto.cnf``.
No current SQL principal or SQL readiness is invented. The selected mysqld
binary, systemd tools and operating-system user must already exist on that host.

Review binds the exact generated unit text, direct native executable/arguments,
user option, configuration/include graph, PID filename, systemd tool bytes and
installation directory identity. Unit working directory and HOME preserve the
selected native configuration context. MySQL retains its native user-option
precedence. Native ``mysqld --validate-config`` and ``systemd-analyze verify``
run before exclusive unit publication. An existing unit file, symlink or loaded
unit is refused. A competing file cannot be overwritten between validation and
publication. The installed unit is flushed before native ``daemon-reload``; that
manager command rereads all unit definitions, including concurrent external
changes. These observations do not freeze other host administrators.

Installation does not start or enable MySQL. Separate reviewed start/stop/restart
and enable/disable actions use the native service manager. Boot enablement is
reported from native ``UnitFileState``. The installed inactive association checks
actual D-Bus command identities and loaded unit bytes against the reviewed
definition, retaining the native data-directory UUID. Offline control rejects
changed original unit files or commands until the association can be rebound.
An accepted manager client or active unit does not establish SQL readiness.

A private phase receipt separates native configuration validation, unit
validation, exclusive file publication and daemon-reload outcome. Read-only
reconciliation reports that receipt, current file identity/digest, load state
and current association independently from the original SSH acknowledgement.
A missing daemon-reload result stays missing; observing installed bytes does not
supply its return code. Neither installation nor a service request is repeated
automatically after interruption.

This implements native Linux service creation and boot controls under
``CMP-MY-02``. Native upgrades, remaining topology
failure/repair, production recovery cutover and inventory reconciliation remain
separate gates. Windows/macOS implementation and qualification stay with the
platform teams.

Native Router deployment and service controls
----------------------------------------------

The owned server's Availability menu now exposes :doc:`mysql_router_hosts`.
Native Community Router bootstraps on a separately pinned Linux SSH host after
independent metadata-seed UUID/topology, actor, grants and TLS observations.
Private credential admission supports the background invocation without
reacquiring a request Vault principal. The native utility creates the Router
identity, accounts and private deployment; generated IDs and file hashes are
observed rather than supplied by the application. Existing directories and
unit files are preserved.

Separately reviewed systemd installation and start/stop/restart/enable/disable
use the original deployment/host authority and work without source SQL. Native
unit validation does not substitute for Router configuration acceptance at
startup or routed SQL readiness. Original independent guardian receipts and
native input cleanup survive observer loss; an unknown original reply stays
unknown after later process/unit observations. Explicit stop/restart requires
all-client disconnection consent.

Linux native qualification includes pure/C application routes, an independent
three-member Cluster and separate Router host, TLS-routed exact bigint/Unicode
data, actual primary crash/election, pending-transaction rollback, committed
data preservation, read-only secondary routing, SQL-independent service
controls and crashed-member rejoin. The built desktop qualifies the dedicated
context menu and native bootstrap/service reviews. This bounds the recorded
Cluster/deployment scope; other topology failure/repair, upgrades, cutover and
inventory remain under their owning requirements. Live Cluster Router metadata
listing, selected option set/reset, stale-review refusal and removal now have
native pure/C and desktop acceptance through the existing topology workspace;
see :doc:`mysql_router_hosts`. Its original single native Shell utility reference
is retained without depending on a binary-log replay input. History qualification
stays owner-deferred.

Native Cluster complete-outage repair
-------------------------------------

The existing reviewed ``instance.reboot_cluster`` and
``cluster.rejoin_instance`` workflows now have independent Linux qualification
for a real three-server crash. Two servers restart with Group Replication
disabled while the third stays independently unreachable. Explicit native
``force`` recovery restores the reachable partition; the third server is then
restarted and incrementally rejoined through the application. Independent
queries verify native UUIDs and member roles, committed exact bigint/Unicode/
binary values, rollback of pending work and replication of a new write after
repair. Native method replies remain separate from those observations and do
not mark workload readiness as verified. The command is
``tools/cdeadmin_mysql_router_qualification.py --cluster-outage-only`` with an
explicitly owned fixture and native Shell executable. Other topology families,
native upgrades and the broader lifecycle inventory retain their separate gates.

Native ReplicaSet and ClusterSet failover and repair
----------------------------------------------------

Native Linux qualification now includes both topology families with separately
bootstrapped Community Routers and systemd services. Each family lists its live
Router, inspects selected options, sets and resets a native routing option and
independently compares the stored metadata. TLS application traffic then writes
exact bigint, Unicode and binary data before the original primary is killed.
The reviewed native forced-promotion method runs from a surviving registration;
fresh Router connections independently reach the new primary and verify
committed data, pending rollback and replication of a new write.

The original server restarts with the same native UUID. Native ReplicaSet
incremental rejoin, or ClusterSet original-cluster reboot and rejoin, restores
three-target replication. A separately reviewed planned switchover then moves
Router writes to the third target and independently verifies their delivery.
Native return values do not set workload readiness to verified. Between owned
fixture scenarios, dissolution is followed by positive metadata/channel and
outgoing-replica-registration observations before server reuse.

Run ``tools/cdeadmin_mysql_router_qualification.py --repair-families-only`` with
an explicitly owned three-member fixture and native Shell executable. Receipts
qualify their installed Linux interfaces and scenarios. Native upgrades,
production recovery cutover and the broader product inventory remain open;
Windows/macOS acceptance remains with the platform teams.

Reviewed native Linux service upgrades
---------------------------------------

Database-host administration now reviews an installed MySQL 9.7 candidate for
a running 8.4 LTS or MySQL 9 innovation source. SSH authority, filesystem UUID,
open dictionary file, executable, PID birth, systemd group and unit definitions
bind the source before normal 9.7 SQL-profile admission. The old version is not
admitted to the ordinary editor/catalog profile.

Native Shell 9.7 runs its upgrade checker against an explicit local socket or
loopback connection. Its native report and warnings are shown in review and
rechecked before shutdown; errors prevent data-upgrade dispatch. Authentication
factors travel privately outside retained options and through native stdin.
Candidate configuration and unit validation precede the original service stop.
A reviewed unit drop-in selects the candidate and native ``--upgrade=AUTO``
startup. MySQL owns dictionary migration; no automatic downgrade or filesystem
rollback is provided.

Original manager results, process facts, native upgrade history and subsequent
SQL/data acceptance remain separate. Owner-scoped phase receipts and a
data-directory claim survive an uncertain reply. Linux manager clients use a
parent-death policy. Acknowledgement requires ended original execution and a
stable observed native unit. An active candidate also requires its completed
native upgrade history; pending stops and unfinished upgrades remain protected. A new reviewed
original-service start can recover a stopped pre-upgrade source. Original
unknown outcomes stay unknown and are never replayed.

``tools/cdeadmin_mysql_upgrade_qualification.py`` uses an explicitly owned
SSH/systemd fixture. Native pure/C acceptance covers 8.4.8-to-9.7.0 upgrade,
unchanged UUID and exact bigint/Unicode/binary data. ``--interrupt`` kills the
actual dispatcher and stopped native client during a delayed stop, verifies
pending-work protection and explicitly restarts the original service before a
new upgrade. Desktop invocation adds ``--browser-binary`` and
``--driver-binary``. These receipts qualify their recorded Linux scenarios;
Production recovery cutover and wider inventory remain separate gates.

Native Cluster rolling and metadata upgrades
--------------------------------------------

The host upgrade workflow and native topology workspace also support a
secondary-first Cluster upgrade. Review each member's host upgrade separately.
MySQL owns mixed-version admission, replication recovery and primary eligibility.
During the qualified 8.4.8-to-9.7 sequence, both secondaries upgrade and rejoin
before the old primary stops. Native Group Replication then elects an upgraded
member. Deliberate primary promotion follows after every member runs 9.7;
attempting to promote a newer member while the old primary remains is refused
by native MySQL.

Select ``instance.upgrade_metadata`` in the topology workspace to review native
Shell metadata migration. Qualification starts with a real three-member Cluster
created by native Shell 8.4.8, rather than synthesized metadata tables. The native
operation migrates schema version 2.2 to 2.4 and preserves the original Cluster
and instance identities. Separate native Cluster status, UUID, exact bigint,
Unicode and binary comparisons, and fresh writes replicated to every member
check each rolling step. Method replies do not establish workload readiness.

Run ``tools/cdeadmin_mysql_rolling_upgrade_qualification.py`` against an explicitly
owned three-member fixture. The application/native Shell execution host must
reach the members' advertised addresses. ``--use-c`` selects the native C driver;
the default uses the pure driver. These Linux scenarios supplement the existing
installed-host and desktop upgrade evidence. Production recovery cutover and
wider inventory remain separate completion gates.

Owned topology execution and certificate accounts
--------------------------------------------------

The native topology workspace can run from a separately selected owned member.
From a secondary seed, load registered topology instances and choose **Use
execution registration** for the current primary. Inspect that seed and review
its UUID before dispatch. New inspections/reviews and reviewed starts check that
the selected native UUID belongs to the browsing seed's visible topology.
The selected registration supplies its own authentication, TLS policy and
execution host. Account setup independently requires the current writable native
primary. A different member or primary requires a new review.

Jobs belong to the execution registration. Status, cancellation and previously
dispatched starts preserve that original scope without reconnecting the browsing
seed. The original review/outcome is retained. Changing execution registration
clears the desktop's seed, review and private password.

Native administrator and Router setup accept ``requireCertIssuer`` and
``requireCertSubject`` in their native options. Supply password factors only in
the separate dispatch input. Native Cluster, ClusterSet and ReplicaSet
qualification creates each account through the application from a secondary
origin with its owned primary selected, then independently authenticates with
the required X.509 certificate. Password-only login is refused. Public account
observations contain identities/grants and fingerprints rather than passwords or
authentication strings.

``tools/cdeadmin_mysql_topology_security_qualification.py`` covers these six
native account methods through pure/C connectors, unrelated-member refusal and
native topology transitions. Its standalone fixture-generation resets are
confined to the explicitly owned disposable servers. The built desktop gate is
``tools/mysql_topology_security_ui_qualification.py``; it checks secondary-origin
selection, primary review/confirmation, password clearing, actual certificate
login and original-job listing. This completes the accepted Linux
``CMP-MY-02`` scope alongside the existing host/Router/outage/repair and upgrade
receipts. Recovery/recoverability (``CMP-MY-01``) and the independent native
inventory remain open before the MariaDB implementation handoff.


Permanent recovered-service and cutover acceptance
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

A stopped native recovery now stages a new permanent read-only systemd service
with independent unit/process/dictionary/namespace observations and its retained
UUID, data, logs, native file-keyring and TLS material. Its embedded launcher and
private copies survive ordinary registered host restarts. Namespace-aware host
binding identifies the permanent dictionary through its owned deployment claim
instead of confusing original source paths with the recovered files.

Background writable activation binds a registered target to matched independent
expected-checkpoint acceptance and explicit coverage acknowledgement. Current
source-service inactivity/disablement plus original dictionary-holder absence
exclude a manually started original writer. Fresh native checks run under
instance/read locks before the one-time writable startup policy and native live
read-only/event changes. Cancellation is admitted before the durable policy
claim. Missing replies keep their unknown outcomes, never trigger replay and
remain independently observable across an explicit restart.

``tools/cdeadmin_mysql_recovered_deployment_qualification.py`` qualifies both
connectors with native MySQL9.7/systemd/SSH, original manual-writer refusal, full
selected data/definition/account and 25 public system-table acceptance, encrypted
external data, writable restart durability and lost-policy acknowledgement. Its
built desktop companion verifies owner-scoped review, confirmation and
observation with no console errors. This closes admitted Linux ``CMP-MY-01``;
all eleven comparison items are Linux-qualified. Independent inventory, optional
installation coverage and cross-platform acceptance are separate. ScratchBird
history qualification remains owner-deferred.

Native SDI table import
~~~~~~~~~~~~~~~~~~~~~~~~

The MySQL server maintenance menu now exposes **Import native table definitions
from SDI files**. It issues Community ``IMPORT TABLE FROM`` through an owned
connection after reviewing the server UUID/principal, visible native table
inventory, an explicit default database on the private connection, and trusted
absolute database-host file patterns. Native
``FILE`` privileges, ``secure_file_priv``, pattern expansion, dictionary loading
and storage-engine restrictions remain engine-owned. Source implementation is
present in MySQL9.7 ``sql/sql_import.cc``; this is beta work.

The selected SDI and corresponding engine files must already be staged on the
database host. The review records paths and host facts; it does not freeze or
hash those files, transfer application-host files or attest data recoverability.
Changed native table inventory refuses dispatch. Original SQL acknowledgement,
native warnings/errors and later observations remain separate, with no automatic
retry or application rollback claim.

``tools/cdeadmin_mysql_sdi_import_qualification.py`` imports real MyISAM files
through both native connector classes, independently verifies full rows and
definitions and a later write, and preserves missing-file native errors. It
also checks stale-review refusal and literal Unicode/apostrophe host filenames.
The qualification closes this dispatch-inventory adapter gap; ``INV-MYSQL``
continues to reconcile the remaining source/runtime installation boundaries.
Native table creation options
-----------------------------

The MySQL table creation form accepts native engine, character-set/collation,
storage, statistics and MERGE options in its MySQL table-options object.
Integer values use decimal strings to preserve unsigned 64-bit values through
the browser. Text and JSON attributes are native bound parameters; identifier
paths remain quoted identifiers. Unknown option names are refused rather than
silently discarded. Native MySQL decides which options a selected engine and
version accept.

For FEDERATED, select the native engine and supply a named foreign-server/table
reference or native connection in the sensitive connection field. The existing
foreign-server workflow manages the native server definition. Named references
avoid embedding account passwords in table definitions. Reads and writes use
the native remote handler; creating a definition does not copy remote data.
NDB Cluster remains a separate engine scope under the owner's clarification.

Editor observation admission
----------------------------

MySQL completion and native syntax checks use an independent authenticated
observer. If observer admission is denied or Performance Schema is disabled,
the editor reports the unavailable native dependency and sends no substitute
metadata or PREPARE commands on the user's SQL session. The API returns
``MYSQL_EDITOR_OBSERVER_UNAVAILABLE`` with fixed operator guidance and a
numeric native error when available. It does not return native exception text.

For denied admission, restore the registered account's native SELECT access
to ``performance_schema.variables_by_thread``,
``performance_schema.session_account_connect_attrs`` and
``performance_schema.threads``, then retry completion or syntax checking.
The private observer can be readmitted while the original connection and its
pending work remain in place. A disabled Performance Schema needs a reviewed
native configuration/restart and a fresh SQL session. These editor guarantees
are separate from qualification of unadmitted execution/conversion paths and
from the explicitly unconfirmed source active-role/temporary-object overlays.

Retained observation and persisted value boundaries
---------------------------------------------------

Denied/disabled private observation no longer authorizes original-session
metadata queries for parameter binding, client script framing, query attributes
or C text conversion. These paths refuse affected commands before dispatch,
retain native diagnostic state and pending work, and explain the required native
Performance Schema access. Restoring grants permits authenticated readmission
without replacing the original connection. Native version verification occurs
during admission; later checks bind that observation to the original connection
identity. Native pure/C and authenticated API evidence covers both admission
profiles, server general-log command counts, ROW_COUNT, warning/error areas and
pending savepoints. This does not claim executable support without the dependency.

The system-variable catalog now distinguishes persisted absence, redaction,
ordinary text and ambiguous NULL/empty text. MySQL9.7's
``performance_schema.persisted_variables`` carries string values and no
NULL-versus-empty discriminator. Native ``SET PERSIST`` / ``SET PERSIST_ONLY``
receipts retain acknowledgement and persisted presence while exposing
``persisted_value_identity_unconfirmed`` for that ambiguity. Neither an empty
string comparison nor DEFAULT acknowledgement proves the value's typed identity.
Runtime NULL can be observed separately using ``IS NULL``; RESET PERSIST removes
the persisted identity. Native qualification exercises actual NULL
(``innodb_tmpdir``) and empty text (``init_connect``), both connectors, both
persistence operations and server DDN rediscovery. Engine-owned ambiguity is
reported, not repaired through an application value substitution.

The unified View family descriptor now accompanies the existing native view
compiler, with every declared create/alter binding verified. Its legacy field
factory and dispatch branch were removed. It remains draft until the front-end
stream verifies rendering and round trips. Ordered scalar aliases and
cross-operation privilege edits remain Decision 9 gaps; user-key inspection/export follows the owner's metadata-only beta ruling in
Decision 10. Raw-key export is outside that scope. Native/API evidence does not establish unified UI acceptance.

Typed native index definitions
------------------------------

Index creation now accepts ordered typed column/expression records while
retaining the existing column-name list contract. Native prefix lengths, ASC/DESC
order, unique, FULLTEXT/SPATIAL kinds, BTREE/HASH methods, FULLTEXT parser choice,
comments, visibility, key block size, secondary-engine attribute metadata and
ALGORITHM/LOCK clauses have dedicated backend fields. Native MySQL/storage-engine
restrictions, warnings and errors remain authoritative; no PostgreSQL-style
CONCURRENTLY or partial-index predicate is introduced.

Review binds the native server/principal/roles, SQL mode, database and owning
table structure. Ordinary AUTO_INCREMENT advancement is excluded from structural
comparison; quoted literals and engine attributes are preserved. Changed schema
refuses the original review. Execution owns a separate connection, preserves
query-session transactions and never retries a missing reply or observation.
Native acknowledgement remains separate from later catalog reads. Public index
receipts carry scoped key facts and a structure hash, rather than unrelated
column defaults or table connection strings. External DDL is not fenced.

Navigation retains every ordered STATISTICS row, including expressions, prefixes
and sort direction. MySQL9.7 reports ``SPATIAL`` as INDEX_TYPE; the kind projection
uses that native value. The Index descriptor is draft and its legacy index-change
field branches are removed; visibility also has a typed Maintenance operation
descriptor. Shared rendering/round-trip acceptance and recorded value projections
remain pending. The native qualification command is
``tools/cdeadmin_mysql_indexes_qualification.py``.

The authenticated validation path admits these typed inputs from the descriptor,
without changing the frozen legacy UI catalog. It retains scalar column-name
lists for existing clients; the native compiler checks record identities and
incompatible clauses. Unknown options and malformed structured inputs are
refused before planning. Both connector classes qualify authenticated typed
plan/apply, independent native catalog effects and refusal of a consumed plan.

Primary engine attributes outside the beta profile
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

Primary table/column/index ENGINE_ATTRIBUTE hooks require the handlerton flag
``HTON_SUPPORTS_ENGINE_ATTRIBUTE``. The audited Community9.7 implementation
contains its declaration and admission checks but no primary-engine source
advertises it; the engine-attribute test explicitly simulates support in a debug
build. Release InnoDB, MyISAM and MEMORY refusals are checked separately. Core SQL
syntax and dictionary hooks are not evidence of a working engine implementation.
The primary-attribute controls were therefore removed from the Table/Index beta
descriptors. A separately available implementation and native qualification are
required before exposing them; closed-engine integration is post beta.

Secondary-engine attribute metadata uses a distinct available core path and is
qualified independently. Its metadata support does not establish execution of a
closed secondary engine. Tablespace attribute APIs are a separate native command
contract and are not reclassified by the table/index flag check.

Typed stored routines and scheduled variants
--------------------------------------------

Procedure creation now preserves ordered IN, OUT and INOUT parameter modes.
Stored functions use native input-only parameters and scalar return types.
Types retain native precision, length, unsignedness, ENUM/SET literals and
character-set/collation modifiers. Native MySQL9.7 has no stored-routine
parameter defaults. Create-time determinism, data access, SQL security,
LANGUAGE SQL, definer, comments and IF NOT EXISTS have typed inputs; available
Community SQL execution is not replaced with a simulated non-SQL runtime.

The independently owned review binds server/principal/roles, SQL mode, default
database and the selected routine's observed definition. It uses the registered
MySQL9.7 Shell grammar library in an isolated process to validate the whole
CREATE command, including compound bodies, without executing submitted SQL.
That native dependency must be available before review. Apply rechecks the
review, parser identity and native state, and never retries a mutation after a
missing reply. Native acknowledgement remains separate from later observation.
External DDL is not fenced. Catalog parameter records preserve native order,
mode, type and character settings; unavailable bodies/parameter catalogs remain
explicitly unavailable.

The Routine family has separate Procedure, Function and Scheduled Event
variant descriptors, selected by capability references. Native characteristic
ALTER never recreates a body or signature. Separate create/alter defaults keep
comment-only edits from resetting security, data access, event completion or
scheduler status. Event rename has a typed Maintenance entry. The migrated
legacy field factories were deleted. All variants remain draft until the shared
front-end renderer and round trips are accepted. Native qualification command:
``tools/cdeadmin_mysql_routines_qualification.py``. Decision10 now limits user-key results to metadata for beta; raw-key export is
owner-excluded. This routine work does not establish shared UI acceptance.

Native trigger definitions and ordering
---------------------------------------

The Trigger descriptor exposes native BEFORE/AFTER, one INSERT/UPDATE/DELETE
event, owning table, definer, IF NOT EXISTS and FOLLOWS/PRECEDES ordering.
Compound bodies are checked as complete definitions by the registered native
MySQL9.7 grammar before dispatch. MySQL does not acquire another engine's
INSTEAD OF, statement-level, active/disabled or numeric-position behavior.
Legacy one-element event lists and the old generic defaults remain accepted;
non-default unsupported flags are refused explicitly.

Review binds execution identity, SQL mode, table structure and the observed
native trigger chain. Apply rechecks those observations and owns a separate
connection. Acknowledgement remains visible if later observation fails, and
unknown mutations are never replayed automatically. Ordinary AUTO_INCREMENT
advancement is not a schema change; concurrent external DDL is not fenced.
The navigator retains full native trigger fields, including body, definer,
order and stored language context. Native MySQL owns execution, privileges and
ordering compatibility. Existing explicit DROP/CREATE and DDN workflows remain
separate from native ALTER, which MySQL does not provide.

The combined ``tools/cdeadmin_mysql_routines_qualification.py`` command covers
native pure/C row execution and ordering, transaction/savepoint preservation,
existing-definition preservation, stale reviews, native errors and observation
loss. Authenticated create and drop are independently checked against native
row effects. Trigger remains draft (11fields/1gap) until the shared renderer
and family round trips are accepted; its ordering fields use Engine as required
by the field matrix.

Native account policies and role identities
-------------------------------------------

User creation and alteration now bind native authentication plugins and supplied
password/authentication strings. Typed clauses cover dual-password retention and
discard, current-password replacement, expiry/history/reuse requirements,
failed-login locking, hourly/connection limits, TLS/certificate requirements,
comments, exact JSON attributes and create-time default roles. Omitted alter
policies stay unchanged. Authentication and policy enforcement remain native.
MySQL has no PostgreSQL administrator flag; use native privileges and roles.

The available GPL ``auth_socket`` implementation supports second and third
factors. Typed create/add/modify/drop inputs and real Unix-socket authentication
are qualified on MySQL9.7 through both connector classes; no plugin simulation
is used. The acquired Community production plugins/components contain no
registration-requiring implementation. Core registration hooks do not establish
available WebAuthn/Enterprise functionality. Generated passwords remain a beta
protected-result integration gap under Decision16, separate from closed implementations.

User and host are separate native identities. Rename/drop preserve literal
quotes, backticks, backslashes, Unicode and @ characters, independently of SQL
mode. Named-account role aliases expose membership actions; they do not claim
persisted CREATE ROLE origin. All accounts remain under Users, including those
used as roles. Native CREATE USER DEFAULT ROLE can grant the role implicitly.
CREATE ROLE and optional initial grants are separate native statements: later
grant failure retains the prior acknowledgement and created account.

Review and apply use an independent server-global connection, privately bind
credential-bearing state and expose only nonsecret observations. Secrets and
factor credentials are redacted from public validation/plan receipts. Changed
state refuses dispatch. Lost replies or post-acknowledgement observations never
cause automatic replay. ``tools/cdeadmin_mysql_accounts_qualification.py`` checks
native authentication and policy effects, original-session diagnostics/pending
savepoints, stale reviews, native errors, partial creation and authenticated
role/default-role/rename/drop operations for pure/C paths.

Role/User descriptors and Security operation entries accompany this backend
work. They remain draft pending shared rendering and round trips; the privilege
variant and Decision9 projections are recorded separately. This qualification
does not close the entire native inventory or cross-platform acceptance.

Native privilege scope and delegation
-------------------------------------

Typed native grant/revoke workflows now preserve separate user/host records,
multiple grantees, literal database/object/column identities, ordered column
privilege lists, static and installed dynamic privilege names, routine/library
scopes and proxy accounts. Library privilege metadata does not establish an
available closed execution runtime. Global GRANT AS supports NONE, DEFAULT,
ALL, selected and excluded native role sets. MySQL permits GRANT AS only for
global privileges; the compiler refuses it on narrower scopes.

REVOKE supports IF EXISTS, IGNORE UNKNOWN USER, explicit GRANT OPTION removal
and ALL PRIVILEGES, GRANT OPTION at account scope. Database-level revocation
under native partial_revokes preserves MySQL's restriction behavior rather than
emulating another engine's DENY. Scope validity, dynamic privilege availability,
wildcards, warnings and errors remain native. The runtime partial_revokes policy
and observed native grants are rechecked before an independently owned dispatch;
external writers are not fenced. Original query-session diagnostics and pending
savepoints are preserved. A successful acknowledgement followed by observation
loss is never automatically replayed.

The two Security operation descriptors and the privilege family variant ship
with this backend input contract. ``tools/cdeadmin_mysql_privileges_qualification.py``
checks native column allow/deny, dynamic/routine/proxy/delegated grants, partial
revokes, missing-user warnings, native errors, changed reviews, observation loss
and authenticated typed grant/revoke through both connectors. Legacy scalar
privilege lists and simple account strings remain accepted; literal identities
use the structured fields. Shared rendering and family privilege-diff dispatch
remain pending under Decision9; the descriptor is draft.

Owner-approved user-key beta scope
----------------------------------

On 2026-10-25 the owner selected metadata-only for user keys under UI design
Decision10. Inspection returns native key type and byte length; public plans,
receipts and downloads contain no raw key material. Native setup, supplied-key
storage, generation and removal remain implemented and in beta. Private native
fingerprints continue to protect reviewed changes. No new execution path or
protected download is introduced by this ruling.

Raw-key retrieval/export is outside the current beta by owner scope, rather than
an unresolved implementation gap or closed-source Enterprise dependency. This
resolves the user-key result decision only. Native RANDOM PASSWORD delivery and
shared renderer/round-trip acceptance retain their separate recorded status;
the ruling does not complete Group9 or the independent product inventory.

Database defaults and registration descriptors
-----------------------------------------------

The Database descriptor now owns the native name, IF NOT EXISTS, character set,
collation, default encryption and ALTER-only read-only fields. Endpoint and
visual-admin input contracts load these same fields rather than maintaining
MySQL field tuples in parallel. The native compiler and execution contract are
unchanged. Existing-table character sets and encryption are not rewritten by
changing database defaults; the native qualification verifies preserved Unicode
data separately.

Database navigation now retains the full SHOW CREATE DATABASE definition and
its read-only state. MySQL9.7 reports that flag in a trailing native comment,
not I_S.SCHEMATA. A successful read distinguishes ON/OFF; failed observation
reports unavailable and does not invent OFF. The shared record projection maps
native encryption YES/NO to Y/N. ``tools/cdeadmin_mysql_database_descriptor_qualification.py``
qualifies descriptor create/prefill/alter/drop, actual native read-only write
refusal, existing data and original-session diagnostic/savepoint preservation
through pure/C and authenticated APIs. The six-field descriptor is complete under the shared family-render suite and
native descriptor/draft round trip; human presentation and platform acceptance
remain separate. Security diff dispatch remains Decision9.

The Server descriptor lists41 typed registration inputs, including failover,
TLS lists and connection attributes. Each binding reaches the existing
registration input validator. Registration-action dispatch belongs to the
shared shell and is recorded as Decision11; no server DDL is invented. This
form remains draft/unsurfaced. Nested failover credentials/pools, optional
closed-server authentication runtimes and application registration metadata
retain explicit gaps. These scoped changes do not close Group9 or the broader
native inventory/diagnostics reconciliation.

Server maintenance descriptor cutover
------------------------------------

The current operations descriptor lists42 entries, including29 migrated server
and MyISAM cache operations. Seven legacy native-module form factories and
dispatches are retired; the catalog/input boundary loads the same declared
fields. Native compile/review/apply functions are unchanged. Exact numeric and
binary identities remain lossless text; SDI files and index lists use typed
scalar grids. Descriptor/native input tests cover all29 migrated operations.

These entries are draft. UI design Decision12 records the shared operation
dialog projection gap; the SDI and table cache grid workflows remain explicitly
unsurfaced until it is fixed. Backend projection/native API qualification is
not dialog acceptance. Navigator data covers33 native kinds but is also
draft/unsurfaced pending shared tree consumption (Decision13). Group9, native
inventory reconciliation, generated-password delivery, human presentation and
platform evidence retain their recorded scope; these counts close none of them.

Partition, CHECK and group descriptor cutover
--------------------------------------------

The operations descriptor now lists65 entries. Twenty-three additions cover
eleven partition/table maintenance actions, CHECK enforcement, ten Group
Replication actions and privilege inspection. Every field binds the existing
native compiler; compile/review/apply behavior is unchanged. Native numeric
bounds and exact credential/identifier values are retained. CHECK prefill keeps
the existing catalog metadata contract. The two Group/CHECK form factories and
dispatches are removed; the partition factory retains only Tier1 drop, whose
classification and confirmation contract are unchanged.

The native qualification tools can now consume projected descriptor drafts.
They verify real partition data effects, CHECK state and existing-row refusal
through both connectors, authenticated plan/apply and a three-member group
covering all ten group actions. The shared OperationDialog projection gap is
still Decision12: reorganize grids and hidden COUNT/DEFINITIONS inputs remain
explicitly unsurfaced until that bridge lands. Family partition-grid changes
remain Decision9. All operation entries stay draft. Twenty-two remaining beta
tier2/3 entries and the independent native inventory/diagnostics reconciliation
remain open, alongside the previously recorded shared UI/protected-result gaps.

Typed configuration and channel inputs
--------------------------------------

Eleven further operation descriptors bring the declared total to76. Variable
inputs preserve native text, boolean, safe-integer and exact numeric binding
semantics; existing AUTO and encoded-object API shapes remain supported. The
shared backend validator's former object/array-only handling of scalar values
is corrected through an explicit backend scalar contract. DEFAULT and NULL do
not validate or bind ignored values. Native numeric conversion and refusal
remain authoritative.

All native UNTIL and filter families have typed fields. Database/table and
rewrite records are accepted alongside pair arrays, generating identical SQL.
Selected empty filters clear that family; unselected filters remain unchanged.
Resource thread IDs, process targets and log positions retain their exact
identity and numeric representations. Native/API qualification covers both
connectors, actual persisted/runtime state, owned thread/query interruption,
replication delivery and independently preserved session state.

The retired server-operation factory and migrated channel/resource-group
branches are removed. Family/options formatting preserves parsed content and
all existing fields. The11 new entries remain draft/unsurfaced under Decision12,
rather than claiming projected native inputs establish a working dialog.
Database8 and row-workflow3 descriptor entries still remain, with independent
native inventory and the previously recorded shared UI/protected-result work.

Typed database maintenance and dump inputs
-----------------------------------------

Eight database operation entries bring the descriptor total to84. The legacy
portfolio forms are deleted; typed fields reach the existing native contracts,
permissions, plan previews and apply paths. Histogram attributes and bucket
records preserve exact integer endpoints, native string/temporal encodings and
native JSON numeric conversion. Shell include/exclude lists and per-table
partition/condition records distinguish omitted options from explicit empties.
Existing native array/map and encoded API inputs remain compatible.

All entries remain draft/unsurfaced under Decision12. Qualification of projected
native/API inputs does not establish a rendered operation dialog. Backup and
restore run through the registered tool workspace on the CDEadmin execution
host. Independent dump verification still requires native checksums and row
counts; schema restoration alone does not qualify data recovery. Three row
workflow descriptors (Decision14), independent native inventory/diagnostics reconciliation,
shared UI integration and protected credential results remain open; this is
progress toward Group9 rather than a completion claim.

Installed-interface metadata preservation
-----------------------------------------

Native plugin discovery now keeps all eleven PLUGINS fields in both the explorer
and server DDN exchange, retaining the established short metadata aliases.
Runtime loadable functions also enter the bounded server capture with their
native return/type/library and exact usage count. Built-in/service NULL libraries
are preserved. Counter changes do not become migration intent; observed runtime
registration does not authorize create/drop in the server migration planner.
Native denied access remains an explicit unavailable section. Metadata capture
uses independently owned connections and does not probe the user's session.

The owning qualification is ``tools/cdeadmin_mysql_installed_catalog_qualification.py``.
It compares native facts, explorer inspection and server DDN through both
connector implementations and authenticated workspace requests, including a
restricted native principal. This closes these metadata-loss gaps, not the full
``INV-MYSQL`` or ``MY-DIAGNOSTICS`` inventory. The recorded shared UI,
protected-result and externally owned acceptance scopes remain open.

Native relay position range
----------------------------

RELAY_LOG_POS now accepts exact unsigned 64-bit text at the input boundary.
Coordinates above 2^32-1 require a separately owned native review and dispatch
connection. The target's ``bulk_insert_buffer_size`` metadata exposes ULONG_MAX
from its native Sys_var_ulong declaration. The compiler's unsigned-long relay
position therefore follows the server ABI, independently of the application
host or a guessed OS name. A native 32-bit ceiling or unavailable/denied metadata
refuses the wide plan; small coordinates retain their existing path.

Review binds the exact compiled statement and parameter digest, server UUID,
ceiling and requested coordinate. Apply rechecks on the same owned connection
that dispatches the command. A changed target/ceiling refuses mutation. Native
errors, acknowledgement and post-acknowledgement cleanup loss stay distinct;
unknown commands are not replayed and no transactional staging is claimed.
The typed UNTIL relay-position field documents this requirement. Channel
create/alter legacy source-option forms remain a separate descriptor migration;
this range fix does not complete those forms or the shared dialog projection.

``tools/cdeadmin_mysql_relay_positions_qualification.py`` covers actual wide
CHANGE/UNTIL values, unchanged original diagnostics/savepoints, native errors,
replacement-instance refusal, limited native grants, disabled instrumentation and authenticated
plan/apply through both connectors. Existing source-to-replica delivery runs
remain part of that qualification. Native Windows/macOS acceptance stays with
the platform teams; modeled 32-bit metadata refusal does not establish it.

The native metadata table is world-readable in MySQL9.7. A replication operator
needs no added SELECT grant for this bound; injected denial handling remains
covered separately. This perpetual metadata table remains available with disabled
Performance Schema. That scope does not change retained SQL-editor admission.

Native retry-count range
--------------------------

SOURCE_RETRY_COUNT accepts exact unsigned decimal text through the target's
native unsigned-long ceiling, using the same owned review and dispatch guard
as wide relay positions. Port and connection retry seconds remain unsigned
32-bit fields. The native delay maximum is 2,147,483,647; compression level
validation remains native (1..22, with zero retaining the previous setting).
Those distinct types are not widened by the retry-count change.

For a request containing both wide relay and retry values, the largest value
must fit the observed ceiling. The exact statement and parameters, native
version, server UUID and ceiling are bound and rechecked before dispatch.
The public ``native_unsigned_long`` observation identifies the maximum requested
integer when retry count is supplied; relay-only receipts retain
``native_relay_position``. Neither observation promises that a retry sequence
has executed. Native errors and lost acknowledgements are never replayed.

The replication qualification checks exact retry counts through both connectors,
SHOW REPLICA STATUS, Performance Schema and the native repository, including
2^64-1 across a native restart. Authenticated plan/apply, single-use plans,
limited native grants and disabled instrumentation are also covered.
Channel create/alter source-option forms still use their legacy contract and
remain unsurfaced under the unified descriptor rules; this range fix does not
qualify that UI. Broader inventory, diagnostics and protected generated-password
delivery remain open.

Declared native tool menus
---------------------------

The existing diagnostic, dashboard, native job and host/service tool openers
are declared in ``ui_descriptors/mysql/tools.json`` and resolved through the
shared menu loader. Their handlers and native workflows are unchanged. Source
readers retain verified-endpoint and owner gates; retained native job and host
views retain owner access during a SQL outage. Database actions carry the
selected database target. Collection configuration and the DDN dashboard
editor remain independent of the display-only viewer.

This migration replaces 25 handwritten menu appenders, not any native operation
or editor family. Channel create/alter lifecycle forms remain unsurfaced under
Decision15 because the shared registry has no Engine-object editor. Native
option APIs and the typed start/stop/reset/filter operation descriptors remain
available at their previously qualified scope. Product inventory, retained
role/temporary-object diagnostics and protected password delivery stay open.

Native replication receiver catalog
-------------------------------------

Explorer discovery and server/DDN capture share an explicit projection of all
27 fields in MySQL9.7's replication_connection_configuration table. This adds
receiver identity, network binding/namespace, TLS paths and choices, compression,
retry/heartbeat settings, automatic failover and GTID-only state to the explorer;
server exchange no longer drops the fields omitted by its earlier11-column
projection. Fields retain native names and enum values. CONNECTION_RETRY_COUNT
is projected as exact decimal text so browser/DDN readers preserve unsigned
64-bit values. TLS_CIPHERSUITES preserves native NULL versus an empty string.
SSL_KEY is a file path; no key file, source password or credential store is read.

The native qualification covers both connectors, default and quoted Unicode
channel identities, all27 fields, DDN readback and generation-bound authenticated
inspection. Restricted native grants produce explicit partial coverage. The
native table is perpetual and remains observable when Performance Schema
instrumentation is disabled; that case is tested independently. Dedicated
capture connections preserve original warnings, ROW_COUNT and savepoints.
These receipts establish configuration observations, not receiver connectivity,
TLS handshakes, compression negotiation, failover execution or delivery.

No operation or form status changes. Channel create/alter remains unsurfaced
under Decision15; native installed-feature reconciliation, retained-session
overlays and protected generated-password delivery remain open.

Native replication applier observations
----------------------------------------

Channel inspection now retains all seven native applier-configuration fields:
delay, the server-rendered privilege-check account, row-format/primary-key
policies and anonymous-transaction GTID assignment. The account text is retained
as reported; no separate host field or account parser is fabricated. Applier
status retains all four native fields, with the unsigned retry counter as
exact decimal text. The existing receiver status projection now preserves its
error timestamp as native text, including zero timestamps and fractional digits.
This does not expand the receiver status field inventory.

Receiver configuration, applier configuration, receiver status and applier
status are queried independently. Receiver-only access preserves its known
fields when applier reads are denied. Applier-only or status-only access can
still discover the channel's native identity without inventing a host, port
or policy. Server/DDN capture merges these observations onto the canonical
channel object; it does not turn each native table into another object.
Applier configuration participates in configuration comparisons. Transient
status stays outside that comparison and cannot become a migration instruction.
The reads remain observational, with no atomic channel-generation claim.

Native pure/C and authenticated API qualification covers four channels,
nullable/quoted policy accounts, OFF/LOCAL/UUID assignment, primary-key policy
variants, stopped and active SQL-applier observations, independent native grants,
DDN exchange and disabled instrumentation. Warnings, ROW_COUNT and savepoints
on the separate original connection remain unchanged. Native worker/coordinator
and the wider receiver-status inventory remain separate follow-up work; this
qualification does not claim event delivery or full replication completion.
Shared channel lifecycle forms and protected generated-password delivery remain
open under their recorded decisions.

Current Group9 integration boundary
------------------------------------

This section records the earlier producer/private-peer boundary. The seven
concrete backend gaps identified subsequently are reconciled in
``Group9 backend completion`` below; shared presentation remains separate.

Receiver, coordinator and worker inspection now projects all20,15 and24 native
MySQL9.7 status fields, respectively. Wide IDs/counters and timestamps use text;
multiple workers retain their native identities and order. Each table remains
independently authorized. An observed empty worker list is distinct from a
failed read. Live inspection retains native diagnostic messages; schema/DDN
exchange replaces their contents with explicit redaction/null/empty facts.
Transient status does not become desired configuration or a migration command.
Native pure/C, authenticated inspection, mixed-grant discovery and disabled
instrumentation are qualified by the channel-catalog command.

Retained resource discovery/inspection now uses the admitted private metadata
peer under the source session lock. It cannot issue incidental catalog queries
on the original editor connection. The selected target remains explicit;
source database, diagnostic preservation and unobserved role/temporary scope
are reported separately. Native warnings, ROW_COUNT and pending savepoints
are qualified through both connectors. Unavailable observation fails without
an intrusive fallback. Exact source overlays remain open under Decision17.

Native account create/alter and factor clauses accept RANDOM PASSWORD. A trusted
protected receiver reserves capacity before DCL and consumes generated values
through zeroized SecretLease buffers. Only password reference IDs and native
factor numbers appear in the public receipt. Review binds the receiver; apply
rechecks it before connecting. No configured receiver, changed review or failed
reservation can dispatch DCL. A lost result or post-acknowledgement delivery
failure is never replayed. Native generated-password creation, rotation and
actual authentication are qualified through pure/C; callback/transport failures
and sanitized receipts have regression coverage. The authenticated application
refuses generation before DCL until the shared bridge is installed.
``tools/cdeadmin_mysql_protected_passwords_qualification.py`` is the native gate.

The User descriptor carries typed choices in the existing authentication fields.
This completes the native producer, not the application delivery workflow.
Decision16 records the trusted service and reveal/recovery integration owned by
the front-end stream. User-key type/length inspection and native setup/store/
generate/remove remain separate and implemented; raw-key export stays outside
beta by owner ruling. No shared UI, family schema or shell was changed.

Group9 remains open for the shared integration/round trips and Decision17;
independent INV-MYSQL reconciliation is still a separate implementation gate.
The shared handoff also retains Decisions9/11/12/13/14/15: family privilege/value
dispatch, registration, operation projection, navigator, typed Data row binding
and Engine-object lifecycle. Platform acceptance, human presentation, deferred
ScratchBird history and closed Enterprise runtimes retain their existing scope.

Native asynchronous failover candidates
----------------------------------------

Five native Community functions now have reviewed management workflows: add and
remove an unmanaged source, add and remove a managed GroupReplication group,
and reset failover configuration for every channel. The four scoped actions
belong to the selected asynchronous channel; reset belongs to the server and
requires an explicit all-channel acknowledgement. Each ships with typed fields
and a Replication menu descriptor. No Engine-object lifecycle form or shared
renderer is added. The89 operation descriptors retain their draft status.

Calls own independent connections, bind exact parameters and recheck the native
instance, principal, active roles and selected configuration before dispatch.
Source-only changes need only their source-table read grant; managed changes
and global reset also inspect the managed table. Native mutation grants remain
authoritative. Changed reviews refuse before dispatch. Missing replies and
post-acknowledgement observation failures never trigger automatic replay.

Discovery independently reads all six source fields and four managed fields,
including exact native identities, weights and configuration. A successful empty
list differs from a denied read; failover-only visibility can discover a channel
without inventing its connection options. DDN retains both collections on the
canonical channel and includes their known configuration in comparison guards.
Explicit native change instructions use the same compiler. Apply checks the
required section visibility and actual source/managed postconditions; an existing
channel row alone cannot establish success. A missing DDN selection is still
never deletion intent. Original query-session diagnostics and savepoints are
preserved by independent execution and capture.

MySQL9.7 ignores the deprecated namespace argument of these functions; calls
supply an empty value rather than presenting an ineffective option. Their native
argument charset is Latin1. Unrepresentable channel text retains native
error3854/HY000; ordinary channel SQL has a different native text contract.
Managed addition requires the native group UUID and port1..65535; removal keeps
the reported managed name and case. Unmanaged add/delete use native unsigned
32-bit port storage. Connection success is a separate observation; native
configuration inspection does not establish source election or data delivery.

``tools/cdeadmin_mysql_failover_qualification.py`` covers pure/C native effects,
independent read/mutation grants, DDN plan/apply, native conversion/refusal,
stale review, post-acknowledgement loss, restart durability and disabled
instrumentation. Its ``--application`` mode exercises authenticated typed
validate/plan/apply and single-use plans after native task admission.
``tools/cdeadmin_mysql_failover_delivery_qualification.py`` separately uses
three owned servers, shuts down the original source and checks the native
candidate switch, exact new rows and GTID catch-up. Application election or
SQL replay does not substitute for that engine behavior.

The fixed generated tasks are admitted only by source-matched native parser and
pure/C receipts through ``supplement_mysql_failover_contract.py``. Redundant
single-statement arrays/format annotations were removed from existing task
records; their SQL, bindings and proof references remain unchanged. This
reduces source overhead without changing the SDK or its evidence requirements.
Shared UI Decisions9/11–17, independent inventory and platform/history scope
remain as recorded above; these workflows do not establish full product
completion.

Group9 backend completion
-------------------------

The remaining seven identified backend items now have concrete contracts:

* Temporary table creation uses a boolean ``temporary`` create field and a
  reviewed retained session. ``table.drop_temporary`` emits DROP TEMPORARY TABLE,
  so a base table can never be the fallback target. Neither action commits or
  closes the caller's transaction. A pooled connection that managed temporary
  objects is physically discarded at session close, including when reset is
  disabled. An absent or changed retained-session binding refuses execution.
* Structured foreign keys preserve ``on_delete`` and ``on_update``; structured
  CHECK creation preserves boolean ``enforced``. Invalid action/enforcement
  values refuse review. Native storage-engine restrictions remain authoritative,
  including InnoDB's refusal of SET DEFAULT; no referential behavior is emulated.
* Explicit ``server.refresh_session_metadata`` captures active roles and selected
  temporary-table definitions, including shadows of committed tables. It requires
  diagnostic-replacement acknowledgement. The source is locked and its retained
  identity checked. Automatic completion reads the resulting snapshot without
  a source command until execution/administration invalidates it. Without one,
  automatic observation retains its existing private-peer path. Native MySQL
  cannot enumerate every user temporary table; selected-name coverage stays
  explicit, and ``complete=false`` does not assert an invented full enumeration.
* Production RANDOM PASSWORD delivery reserves durable space before account DCL,
  encrypts each factor with authenticated, scope-bound encryption, and returns
  references only. The store binds application owner, endpoint, plan, native
  account, factor and expiry. It uses the unlocked master-password authority or
  ``CDEADMIN_GENERATED_PASSWORD_KEYS`` plus
  ``CDEADMIN_GENERATED_PASSWORD_ACTIVE_KEY_ID``. The default lifetime is600seconds;
  ``CDEADMIN_GENERATED_PASSWORD_TTL`` permits60..86400seconds and
  ``CDEADMIN_GENERATED_PASSWORD_PATH`` selects private storage. A changed key
  generation invalidates delivery review. Recovery by plan ID survives a lost
  HTTP result or publication response; it never repeats account DCL. Expired
  values cannot resolve. Explicit authenticated reveal is no-store. Ordinary
  plans, receipts, endpoint configuration and logs never carry the password.
* Each connection failover target can select an endpoint-protected credential
  reference and its kind, plus its own provider-owned pool name/size/reset policy.
  Credentials are acquired only around native connection setup. Higher priorities
  are tried first; equals are randomized without replacement. Configuration or
  secret-resolution failures do not silently fall back. Native connection errors
  can advance to another target. No global Connector/Python pool is created.
  Selected target/principal/reference metadata binds retained-session peers;
  plaintext nested passwords are refused. New secret values retire old pool
  generations; live leases remain owned until release.
* Invalid plans return422 with allowlisted field/code errors; stale, replayed or
  changed-session plans return409. Permission refusals return403. Confirmation
  refusals remain explicit. These pre-dispatch envelopes carry no submitted
  values and never claim a mutation occurred. Execution failures retain their
  separate unknown-outcome/native-acknowledgement contract. All these responses
  are no-store.

``tools/cdeadmin_mysql_group9_completion_qualification.py`` exercises native9.7.0
through both connectors and authenticated workspace requests. Its native pass
covers savepoints, independent visibility, temporary shadowing, role snapshots,
FK effects, unenforced CHECKs, disabled instrumentation, physical pool cleanup,
per-target authentication and credential rotation. Its application pass checks
protected delivery/reveal, actual password authentication, recovery after a lost
publication response, one-shot plans, structured refusals and retained-session
plan/apply. ``supplement_mysql_group9_contract.py`` admits the two new generated
SQL tasks only after source-matched native/parser evidence. Task counts qualify
these statements, not full product completeness.

The corresponding Table/Server/User descriptors and91 operation entries remain
at their recorded draft status. New retained-session selection, explicit refresh
and protected reveal/recovery controls are **unsurfaced** pending the front-end
stream. Decisions9/11/12/13/14/15 and the presentation portion of16/17 are the
shared handoff. No shared renderer, schema, shell, menu JavaScript or family test
was changed. Raw user-key export remains owner-excluded, and unavailable closed
Enterprise implementations remain post beta.

The finite seven-item backend audit is closed by the evidence above. This does
not reclassify external archive references or optional deployments as tested,
close the entire six-engine matrix, qualify Windows/macOS, resume ScratchBird
history testing, or claim human presentation acceptance. The eleven adopted
comparison priorities retain their existing completed scope; this audit does
not add a new comparison queue.
