Native MySQL physical backups and recovery instances
=====================================================

The server **Backup → MySQL physical backups** workspace manages native
XtraBackup full backups, preparation of a separate copy, and copy-back into a
new isolated data directory on the authenticated database host. It uses the
existing owner-scoped provider API, private application operation storage and
source archive protection. A separately reviewed managed recovery operation
starts and supervises a private data copy. Selected log recovery, independent post-replay acceptance,
dependency-aware physical retention and production cutover remain separate
``CMP-MY-01`` requirements.

Admitted native backend
------------------------

The bounded Linux implementation uses Percona XtraBackup **9.7.1-rc1**, source
revision ``b1c9c34183de95316d8889ea3d4cb31e31ffddc5``. Its GPLv2 implementation
is source available. The native executable must report that release/revision;
its resolved path and SHA256 bind every review and dispatch. The upstream
release remains a release candidate. Each operation requires explicit consent
to that status; this does not relabel it as a generally available release.
See `the release source <https://github.com/percona/percona-xtrabackup/tree/b1c9c34183de95316d8889ea3d4cb31e31ffddc5>`_
and `upstream physical restore instructions <https://docs.percona.com/percona-xtrabackup/9.7/restore-a-backup.html>`_.

The database host needs the matching native utility and its dependencies,
MySQL 9.7.0's native ``mysql`` client, Python and an explicitly pinned SSH peer.
Native database privileges and OS file access remain required. Desktop clients
can use the SSH host independently of their operating system. This backend
requires a native Linux database host; Windows/macOS native acceptance belongs
to the platform teams.

This first artifact workflow admits full, uncompressed, self-contained native
backups of admitted InnoDB, MyISAM and CSV tables and their prepared copies.
Source inspection refuses other persistent engines and encrypted tablespaces.
It refuses external tablespace mappings and
unadmitted archive formats rather than writing original external paths during
restore. Native encryption-key provisioning, incremental chains, other utility
versions and broader physical recovery remain beta implementation gaps. They
are not closed-source Enterprise deferrals or declared inapplicable features.

Review, execution and observation
--------------------------------

Enter the SSH host, OS account, exact public key, private authentication,
native executable paths and a private workspace separate from the live data
directory and its ancestors. The public-key inspection is unauthenticated;
explicitly choose the key before authenticating. SSH secrets travel separately
from saved review facts and never enter public receipts.

For **Full backup**, select the source's loopback TCP address as reachable on
that host. The native client independently checks the source UUID, data path,
authenticated account and active roles before backup. The application's native
MySQL connection and the host's source ``auto.cnf`` provide separate binding
checks. Registered TLS verification is never lowered: profiles requiring
separately mapped verification files are refused by this initial host adapter.
Host SQL authentication uses required TLS and a private native option file.
Database credential delegation needs a separate explicit confirmation.
This host adapter admits single-factor database authentication; multifactor
delegation needs separate native provisioning.

Choose **Review native physical job**, inspect its facts and warnings, then
confirm and start that exact review. Stale registration, host, utility and
artifact observations refuse dispatch. The web application claims the review
once. An exclusive host directory prevents a second native launch even if
the first reply is lost. Before backup dispatch, a durable broad hold protects
the owner's known source archives, including registration aliases. Its
separate reviewed retirement leaves physical files in place.

A detached host supervisor owns the native process, timeout, cancellation
marker, private output and credential cleanup. It can finish after the viewer,
web worker or SSH transport disconnects. A lost original dispatch reply remains
unknown. **Observe remote physical job** reads the independent original host
receipt without repeating a command; fresh SSH authentication may be needed.
Native completion, process termination, credential cleanup and file verification
remain separate facts. An unconfirmed cleanup or changed source artifact
cannot be selected for a dependent operation. Original source SQL availability
and a surviving source data directory are not required for later artifact
inspection or preparation.

Preparation and isolated copy-back
----------------------------------

After verified backup completion, choose **Use backup for separate prepare**.
Review and start a new job. The host copies and hashes the selected base before
native preparation; the original backup stays intact. Native LSN, format and
file metadata are retained, with large numeric values represented as strings.
Every input is rechecked before use and after the operation. Unexpected links,
nonregular files, changed bytes or unsupported metadata refuse admission.

After verified preparation, choose **Use prepared artifact for isolated
copy-back**. Native copy-back writes a new private job directory only. Explicit
data/undo/redo paths keep this admitted self-contained operation separate from
the live source. Its result records copied-file hashes and the directory path.
It does not start a database, provision its OS ownership or service, verify
recovered SQL data, replay logs or authorize production cutover. Those remaining
management workflows are tracked under the recovery/lifecycle requirements.

Managed native recovery instance
--------------------------------

After verified copy-back, choose **Use copy-back for managed recovery**.
Select the exact native MySQL 9.7.0 ``mysqld`` executable, native GTID mode,
buffer memory and maximum instance lifetime. Review and explicitly confirm the
new operation and its separate database credential delegation. The recorded
OS account is the authenticated SSH account; it needs permission to read the
base and run the native server. Native startup uses that account without an
implicit ownership or service change.

The supervisor copies and hashes the selected base into a new private runtime
directory. It consumes admitted native geometry from the original prepared
``backup-my.cnf``, preserving its hash. External system-file mappings and
unadmitted options refuse startup. Native MySQL assigns a fresh target UUID.
The instance uses a private Unix socket, an optional explicitly reviewed
loopback TCP listener, disabled X Protocol listeners,
``super_read_only``, disabled events, asynchronous and Group Replication
autostart, the selected GTID
mode, disabled binary logging and ``upgrade=NONE``. Persisted global settings
from the base are excluded from this explicitly reviewed isolated startup.

The native client independently observes version, target UUID, account/roles,
data/socket paths and isolation settings. Credentials are removed after that
startup observation while supervision continues. The display retains the SQL
startup observation separately from fresh process presence. A live process
observation does not assert current SQL/data correctness. Full recovered-data
acceptance and replay connection integration retain their own gates.

Choose **Stop managed recovery instance** to request native shutdown. A native
Linux process descriptor binds signal delivery to the original process birth,
executable and OS account. A reused numeric PID cannot receive that request.
Stop requests and signal outcomes have separate durable receipts. Stop also
works after loss of the original supervisor. In that case independent process
termination observations preserve the missing native exit reply as unknown.
The normal supervisor records the native exit and checks that the original
copy-back bytes remain intact. Its reviewed lifetime also requests shutdown;
a required forced termination stays explicit in the receipt.
Native server error output is available through the same bounded output viewer.

Opening, observing or retrying an already claimed job never launches another
server. A new review from the preserved immutable base creates a new instance.
Production service installation, replay integration, full data/definition
and post-replay acceptance, physical retention and cutover remain open.

Native editor connection
------------------------

For editor access, start a new recovery instance with a separate loopback TCP
port. Port zero preserves Unix-socket-only startup. The host refuses an occupied
port and binds the reviewed TCP listener to ``127.0.0.1``. In the recovery
workspace, choose **Review recovery connection**, inspect the native instance
and registration facts, and confirm both the separate registration and database
credential use. **Attach reviewed recovery connection** creates a separate
owner-scoped MySQL registration in Data Explorer. Its selected query database
is copied from the current registration and verified on the recovered instance.
The registration uses the native MySQL driver, TLS/authentication, catalog,
predictive editor, native parameters and transaction/result protocols.

The application forwards native bytes through the explicitly pinned SSH host.
Each stream independently checks the original process birth/executable and its
loopback listening socket. Native SQL also checks the target UUID, version and
data path. The relay receives no database password outside the native protocol.
Its raw packets, SQL and result bytes are never retained. Native read-only
settings continue to enforce the instance's write policy.

The persistent registration stores a recovery binding rather than a usable
network destination. An absent transport, changed instance or ordinary network
fallback refuses connection. After application restart, open the target's
physical recovery workspace, choose **Load this registration’s recovery
instance**, and review a fresh attachment with private SSH authentication.
Lost original connection replies retain their unknown outcome; **Observe
recovery registration** reports the independently retained registration.
Source registrations and their pending sessions remain separate.

**Detach recovery transport** requires this registration's native SQL
connections to be explicitly closed before it releases this process's SSH
forwarding. Replacing a transport has the same admission rule. The native recovery instance
continues under its own supervisor/lifetime.

Writable startup and native raw replay
--------------------------------------

**Recovery startup mode** defaults to **Read-only inspection**. Choosing
**Replay (writable, binary logging)** requires an explicit native server ID and
loopback TCP port, invalidates earlier startup consent and requires a new
review. This starts another private data copy with a new native UUID,
``read_only``/``super_read_only`` off, private ROW binary logs and replica-update
logging enabled. Events, replication and Group Replication autostart remain
disabled. Native SQL independently checks the reviewed mode, server ID and log
paths before recording readiness. Earlier inspection instances stay read-only.

Attach the replay instance as a separate registration, then open its binary-log
recovery workspace and choose **MySQL raw closed logs**. The existing native
``mysqlbinlog``/``mysql`` workflow uses an application-host utility lease on the
original process-bound SSH stream. The lease retains the exact private route
and blocks detach/replacement during native execution. Database credentials
remain private and existing TLS options pass to the native client. The client
disables reconnect and checks native target identity/GTID/log position before
replay. A missing transport has no ordinary network fallback. MySQL owns log
application, commits, GTIDs and errors; stopping a client does not prove rollback.

Before/after/all transaction boundaries, original unknown replies and subsequent
native target observation retain the existing replay/fence rules. The decoder
and SQL client each have an independent guardian and immutable invocation
reference. The client reads a private, hash-verified stdin snapshot. After the
original observer exits, **Cancel replay** addresses those original utilities;
**Inspect current target facts** separately observes their termination and
input/credential cleanup. Only confirmed termination releases this job's parked
transport lease. The original database outcome remains unknown; releasing its
target fence still requires a free native replay lock and explicit confirmation
of the exact target UUID and current facts. Missing or failed guardian receipts
retain uncertainty and their reservation.
If observation is lost during decoding before SQL dispatch, the load remains
not dispatched while the decoder's separate process state stays observable and
cancellable; absence of SQL dispatch does not prove decoder termination.
Native **MySQL Shell archive** replay also admits this separately reviewed
writable registration on a POSIX application host. The Shell session, replay
worker connections and native reconnects use the same original process-bound
route. Every SSH stream rechecks the original native process and its listener.
The independent guardian and native Shell process inherit the loopback listener
reservation, so application loss cannot allow another service to reuse that port
while Shell is alive. Native authentication and TLS remain in effect.
Shell has its own immutable guardian reference, cancellation and termination
inspection. Lost replies retain the unknown database outcome and target fence;
current lock/identity checks and explicit acknowledgement remain required.
Windows listener inheritance remains separate platform-team implementation and
qualification. Missing/failed guardians and wider lifecycle reconciliation also
remain open.

If the recovery SSH relay is lost, open the replay receipt and use **Inspect
original replay utilities**. This reads the original execution-host receipts
without connecting to MySQL; **Cancel replay** also remains independent of the
SQL route. Once original utility termination is confirmed, the matching retained
recovery binding can release that job's parked lease. No other job or binding
is released. Its private staged input can then be removed while the original
archive stays intact. The unknown database outcome and target fence remain.
Reattach the same recovery instance using a fresh connection review and private
SSH authentication, then inspect current target facts before acknowledgement.
Managed replay acknowledgement also checks native session activity for the
original login, so a free Shell guard lock cannot hide a still-running worker
statement. Active connection IDs are retained; statement text is not retained.
Older receipts without a retained recovery binding keep their reservation until
the existing SQL-based reconciliation can establish the matching target.
Whole-product post-replay data/definition acceptance, retention and production
cutover also remain open; selected successful replay cases do not close them.

The job list and **Inspect native physical output** provide retained facts and
bounded output from the pinned host. Native errors and interrupted observations
stay visible; cancellation is a request to terminate native work and is not an
implicit transaction decision. Existing user SQL sessions are not borrowed for
these operations.

Qualification
-------------

``tools/cdeadmin_mysql_physical_qualification.py`` owns its disposable native
SSH/MySQL fixtures. Its pinned XtraBackup image is an execution dependency for
that qualification, not a Docker requirement for production SSH hosts. It
qualifies both corrected Connector/Python 26.7.0 interfaces, actual native
backup/prepare/copy-back, independent MySQL 9.7.0 recovery fixtures, selected
InnoDB/MyISAM/CSV data and native definitions, unknown original replies,
independent completion and credential cleanup. Optional browser/driver flags
qualify the production workspace. Managed native recovery qualification also
covers fresh target UUIDs, private-socket SQL/data/definition observations,
native write refusal, explicit shutdown, original-supervisor loss and process
descriptor control, all four exposed native GTID modes and reviewed lifetime
expiry. These receipts qualify the selected cases. Broader recovery,
incremental, lifecycle, retention and cutover requirements remain open.
ScratchBird history tests remain owner-deferred.

Reviewed physical artifact retention
------------------------------------

Use **Protect this physical artifact from retention** to pin an artifact, or
**Review physical artifact retention** on its original receipt to inspect the
exact host-side paths, file count, byte count and manifest fingerprint. Removal
requires its reviewed digest, explicit confirmation and the original physical
job UUID. Fresh private SSH authentication reaches the recorded host; source
SQL credentials are not delegated. The original physical result and native
output remain available after its data files are removed.

Remove dependent physical artifacts before their inputs. Cancel an unused
review explicitly. For a managed recovery instance, stop the original native
process, independently reconcile termination and credential cleanup, and remove
its recovery registrations first. Application admission serializes physical
reviews, dispatch and retention across workers. Host admission independently
serializes dispatch and removal, checks remote child receipts, and refuses
inputs that have entered retention. Pins, unknown native process presence,
unreleased registrations, changed file identities, symbolic links, mounted
artifacts and bind mounts prevent removal. Observed termination permits file
cleanup; it does not establish successful database recovery or a native exit
reply that was never observed.

Retention covers the selected job's ``artifact`` or ``runtime-data`` directory
and its private recovery binary logs. Its private manifest is bounded to
200,000 entries per tree and 30 MiB. It never traverses the source data directory
or another job's files. A durable intent precedes any rename. Exact files are
detached into that job's private removal namespace before deletion; interrupted
removal preserves that intent. **Inspect original physical removal** observes
completion without deleting or repeating anything. **Resume original physical
removal** validates the same detached identities and remaining entries; new or
changed files are preserved. **Invalidate an unclaimed removal review** prevents
late dispatch before releasing an unclaimed local intent. An unknown outcome or
missing intent alone never authorizes a fresh removal. Completed manifests are
compacted; private file inventories do not accumulate as retention history.

This workflow removes reviewed individual artifacts. Independent full post-replay acceptance
and production cutover remain under ``CMP-MY-01``. Binary-log archive protection
has its own reviewed retirement workflow and is not silently retired here.
Native qualification covers both Connector/Python interfaces, real pinned-host
backup/prepare/copy-back/recovery artifacts, dependency and pin refusal, private
recovery log cleanup, lost replies, interrupted file removal, explicit resume,
blocked source SQL authentication with a preserved independent transaction,
and the built desktop workflow. Windows/macOS acceptance remains separately
owned; ScratchBird history tests remain owner-deferred.

Reviewed age/count batch retention
----------------------------------

Select an original physical receipt and **Review physical retention policy**.
Choose retention days and the minimum number of newest verified full-backup
chains to keep. Zero days allows immediate cleanup after confirmed native end.
Age starts at the application's observation of completed native work, rather
than its earlier review or start time. Existing receipts without a completion
observation acquire a conservative age anchor when first inventoried.

Policies cover one owner, endpoint, original SQL identity, pinned SSH account,
host binding and workspace. The complete local dependency graph is inspected;
missing or cross-scope inputs, cycles and corrupt inventory prevent review.
The newest retained full backups and their descendants are protected. Pins,
retained recovery registrations, active/unknown native processes, other batch
reservations and outstanding individual reviews also protect their inputs.
If the verified full-backup count is below the requested floor, nothing is
eligible. This count establishes file retention, not recovery acceptance.

A review fixes at most 100 eligible jobs, children before their inputs. Each
item includes its native paths, file count and byte count. Additional jobs never
join this accepted batch. The host rehashes retained full backups at review and
before each removal while holding its admission lock; missing, changed or
unavailable retained files stop deletion. This may take time for large backups.
The application also rechecks eligibility, pins, registrations, the retained
floor, fingerprints and reservations before every step. Reserved inputs cannot
admit new derived jobs. Batch item tickets cannot bypass the parent workflow.

Type the exact batch UUID, confirm the review and select **Run reviewed physical
retention batch**. Each request removes one reviewed item. **Pause after current
physical removal** or closing the viewer stops future requests; work already
admitted by the SSH host may continue. No background scheduler is enabled.
Fresh SSH credentials are used only for the current request. Source SQL login
is unnecessary; independent user transactions and savepoints remain untouched.

Use **Load physical retention batches** after reconnecting or restarting the
application. Status and **Inspect current physical batch step** never delete
files. After a lost reply or interrupted worker, independent inspection and
renewed confirmation precede **Resume original physical batch step**. Resume
uses the same detached filesystem intent and never retries a native backup or
recovery operation. **Invalidate unused physical batch reviews** fences late
dispatch of unclaimed items. An already claimed removal keeps its original
intent; inspect and, if needed, explicitly finish only that item, then invalidate
the remaining reviews again. Cancellation never starts the next item.

Unused previews expire after ten minutes. Invalidate an expired batch and review
a fresh fixed set; there is no silent extension or added deletion intent.
Original physical results, unknown database outcomes, native output and archive
protection remain separate. Full data/definition recovery-drill acceptance,
full independent post-replay acceptance and production cutover remain open.

Scheduled physical retention
-----------------------------

Use **Review physical retention schedule** to review future age/count scans for
the selected original physical scope. Choose a scan interval from 60 seconds to
one year and a lifetime from 1 to 365 days. The preview does not reserve files or
store SSH credentials. Type the exact schedule UUID, confirm the policy and
explicitly select encrypted SSH delegation before **Enable reviewed physical
retention schedule**. Supply fresh SSH authentication for that enable request.

The application worker scans independently of the viewer. Each due occurrence
creates one fixed batch of at most 100 eligible jobs, including later jobs in
the same owner, endpoint, original source/principal/role, pinned SSH account and
workspace. Existing graph, registration, pin, process and native retained-file
checks still apply before each deletion. No source SQL password is delegated;
SQL login is unnecessary for retention. Backup/drill execution, data recovery
acceptance, binary-log protection retirement and cutover remain separate.

Application administrators configure ``CDEADMIN_MYSQL_PHYSICAL_WORKER_KEYS`` as
a mapping of key IDs to base64-encoded 32-byte keys, and select
``CDEADMIN_MYSQL_PHYSICAL_WORKER_ACTIVE_KEY_ID`` in private application
configuration. Use the same key authority across participating workers. Without
it, scheduled SSH delegation is unavailable; manual retention remains available.
Authenticated encryption binds the credential to this exact policy, owner,
endpoint, review and registration. Only ciphertext is persisted after explicit
enablement. Public receipts and exports omit the credential envelope. Workers
decrypt only while processing the admitted occurrence and do not delegate the
source SQL password.

For key rotation, first make the old and new keys available to all workers,
then select the new active key and use **Rotate physical retention SSH envelope**
on each enabled policy. Remove old keys only after their retained delegations
have been rotated. Losing a required key suspends the policy; review a new
policy with fresh SSH authentication. Changes to the registration, permissions,
original scope, adapter, application host or pinned execution host also suspend
future work. Expiry, disable and suspension clear the stored SSH delegation.

**Load physical retention schedules** and **Refresh physical retention schedule**
observe durable state without starting work. **Request due physical retention
scan** requests one due scan of an enabled policy; it cannot resume a suspended
one. **Disable physical retention schedule** stops future admissions, including
remaining steps of an active occurrence. A host request already admitted may
continue. Disable the owning policy before manually inspecting, resuming or
invalidating its batch intent. Its recorded occurrence remains accessible through
**Inspect scheduled physical occurrence**, with fresh SSH authentication for
host inspection. Original native and unknown database outcomes stay unchanged.

Idle application restart preserves enabled policies. An interrupted scan or
occurrence is never automatically retried: independent observation and explicit
handling of the original batch precede a new policy review. Disabling or
reconciling that batch never re-enables the old policy. While the application is
off, scans stop; restart evaluates a future due occurrence without backfilling
missed intervals. Native qualification is available through
``tools/cdeadmin_mysql_physical_replay_qualification.py --schedule-only``.

Recurring full backups and isolated startup drills
--------------------------------------------------

Select full-backup options in the physical workspace, then **Review recurring
physical backup policy**. Choose the interval, policy lifetime and optional
startup drill. The review admits the current source and native executable paths
without dispatching a backup or storing credentials. Type the exact policy UUID,
confirm it and explicitly delegate both SSH authentication and the registered
single-factor SQL password before **Enable reviewed recurring backup policy**.
The existing physical worker key authority encrypts both credentials, bound to
this separate policy purpose, owner, endpoint, review and registration.

Each due occurrence creates a new full backup. Source identity, principal/role,
storage engines and encryption admission are checked through dedicated SQL
connections with a private scoped resolver. The interactive client's credentials,
sessions, transactions and savepoints are not borrowed. Erasing a prompted
interactive password does not erase an enabled worker delegation; changing the
registered credential or other admitted configuration suspends future work.
Policies continue without a viewer and survive idle worker restart. Missed
intervals are not backfilled. One occurrence runs per policy, with the next due
time measured after completion.

An optional startup drill prepares a separate copy, copies it into another new
directory, then starts native MySQL with a fresh UUID, read-only enforcement and
a private Unix socket. Events, replication autostart, upgrades and binary logging
remain disabled. The worker independently observes SQL readiness, requests stop,
and confirms original process termination and credential cleanup. The reviewed
startup lifetime is bounded to 30–3600 seconds. Source data files and production
listeners are unchanged. ``startup_drill_outcome=passed`` means this specific
startup/stop sequence passed; ``database_recovery_verified`` and
``production_cutover_verified`` remain false. Full data/definition equality,
post-replay acceptance and production cutover retain separate gates.

Every occurrence and native job reference is durable before dispatch. Workflow
protection prevents manual or scheduled retention and unowned derivation of
in-progress files. Successful occurrences release that workflow protection only
after independent native-end observation. Backup artifacts and drill copies
remain available for their existing inspection, dependency and retention
workflows; source binary-log protection is retired separately.

**Disable recurring backup policy** stops future admissions and clears the
stored SSH/SQL delegation. Already admitted native work can continue under its
original supervisor and reviewed timeout. An interrupted occurrence is never
automatically repeated, including after application restart. Use **Load native
backup occurrences** and the original physical job receipts to inspect it.
Disable the policy before manual cancellation or reconciliation. With fresh SSH
authentication, **Reconcile native ends and release workflow protection** cancels
unused reviews and requires confirmed process end and credential cleanup for
every dispatched original job. It preserves unknown outcomes and the interrupted
occurrence state. A new policy review is required for future work.

Connection-profile removal refuses enabled physical policies and protected
backup work. Disable the policies and resolve/release their original jobs before
removal. Enabling policies and removing their registration share lifecycle
admission across application workers. Native qualification is available through
``tools/cdeadmin_mysql_physical_replay_qualification.py --backup-only`` and covers
both Connector/Python interfaces and the built desktop.

Independent expected-snapshot acceptance
----------------------------------------

A managed recovery registration can use the original private Unix socket through
pinned SSH, including when TCP is disabled. Each stream checks the original
native process birth/executable and its kernel listener ownership before and
after connection. The connected Unix peer must also report the original native
PID/UID, so replacing an unlinked socket pathname cannot redirect the stream.
TCP-enabled recoveries retain their original loopback checks.
A changed or stopped listener refuses access without a network fallback.

For data checksum checks, explicitly select **Enable trusted LOCAL INFILE for
native checksum acceptance on this recovery copy** before reviewing startup.
The option defaults off and the worker verifies the observed native setting.
It does not change the source server or silently enable a global setting later.
Only trusted managed dump inputs should be admitted to this recovery instance.

From the recovery target's **MySQL full-instance restores** workspace, inspect
the target, choose a retained expected full-instance backup from the original
physical source, confirm the target UUID, and open **Independent dump
acceptance**. Confirm the server-wide write pause, review the exact snapshot,
and start acceptance. The checks use a separate native connection, full row
counts, MySQL Shell checksums and exact exported native SQL bodies. No restore,
repair or GTID update is issued. Data, schema definitions and exported accounts
have separate matched/different/unconfirmed results. Unexported surfaces remain
unchecked. A post-replay check requires an explicitly selected expected snapshot
for that checkpoint; the current source is not implicitly treated as the
expected state of an older backup.

The receipt binds the original physical recovery, its immutable copy-back and
review, the expected dump's native boundary and its sealed artifact. Acceptance
utilities reserve their original process-bound route independently of SQL
sessions, including read-only targets. They cannot authorize raw or Shell
replay. A lost native reply leaves the original check unconfirmed and retains
its reservation. **Observe original acceptance utility without SQL connection**
and cancellation work without the relay. Confirming original utility termination
can release only its own reservation; fresh SSH attachment and native SQL-session
lock observations precede acknowledgement. Original comparison outcomes remain
unchanged and interrupted checks are never repeated automatically.

``tools/cdeadmin_mysql_physical_replay_qualification.py --acceptance-only``
qualifies native pure/C physical-base and post-replay data/definition acceptance,
actual differences, interrupted replies and the built desktop. This is separate
from unattended startup-drill automation. Automatically selecting/capturing an
expected snapshot for scheduled data checks, unexported/system-state coverage,
wider physical backend admission and production cutover remain open.
