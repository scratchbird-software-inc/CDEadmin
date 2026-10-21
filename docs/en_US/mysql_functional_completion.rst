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
