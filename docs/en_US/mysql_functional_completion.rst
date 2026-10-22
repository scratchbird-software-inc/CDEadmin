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
inferred termination, process generation or readiness. Full host initialization,
start/service control and upgrade workflows remain separate outstanding work.
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
environment/credential files or a complete startup-input snapshot. Initialization,
service installation/configuration deployment, upgrades, physical recovery and
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

Persistent-history integration is wired. The owner correction of October 16
defers ScratchBird history testing until explicitly resumed. The earlier native
startup attempt failed its durable agent catalog seed with ``SECURITY.CONTEXT.EXPIRED`` / ``CATALOG_MUTATE`` before
archive SQL. No fallback database or security bypass is used. Windows/macOS
evidence remains with the platform teams and must match the final source before
cross-platform completion is claimed. Signing/release approvals remain separate.
