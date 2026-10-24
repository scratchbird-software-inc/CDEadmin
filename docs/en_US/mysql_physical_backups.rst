Native MySQL physical backups and recovery instances
=====================================================

The server **Backup → MySQL physical backups** workspace manages native
XtraBackup full and incremental backups, preparation of a separate copy, and copy-back into a
new isolated data directory on the authenticated database host. It uses the
existing owner-scoped provider API, private application operation storage and
source archive protection. A separately reviewed managed recovery operation
starts and supervises a private data copy. Selected log recovery, independent
exported-data/definition acceptance, dependency-aware retention and scheduling
have separate reviewed workflows. Native GPL file-keyring recovery is described
below. External InnoDB table/tablespace isolation is also described below.
External system/undo/MERGE-path admission,
unexported/system-state acceptance and production cutover remain open under
``CMP-MY-01``.

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

Certificate-authenticated recovery
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

For a certificate-authenticated profile, enable **Provision recovery server TLS
from reviewed host files**, select a separate loopback TCP port, and provide
the database-host CA, server certificate and server key paths. The native host
binds their exact hashes during review, stages private copies, and uses them
with the native server. Readiness authentication uses native TLS through that
listener; the process-bound SSH editor connection preserves native TLS too.
Client files are removed after readiness; staged server TLS files remain
private until the native process ends, then are removed. Interrupted server
copies remain within reviewed retention until their original process is proven
ended. Original host files and immutable recovery inputs are preserved.

Recurring backup startup drills and expected-checkpoint checks also admit this
explicit server TLS configuration. Enabling a policy encrypts its scoped TLS
material together with SQL and SSH delegation; expiry/revocation still suspends
future work. Interactive credential erasure does not replace this explicit
worker authorization.

The database host needs the matching native utility and its dependencies,
MySQL 9.7.0's native ``mysql`` client, Python and an explicitly pinned SSH peer.
Native database privileges and OS file access remain required. Desktop clients
can use the SSH host independently of their operating system. This backend
requires a native Linux database host; Windows/macOS native acceptance belongs
to the platform teams.

The artifact workflow admits full/incremental, uncompressed, self-contained
backups of InnoDB, MyISAM, CSV, ARCHIVE, BLACKHOLE and MRG_MYISAM tables. Native
MERGE members must resolve inside the private artifact. MEMORY definitions are
preserved with native empty-after-restart semantics; their currently observed
volatile rows are disclosed in the review. Use the logical backup workflow
when retaining those rows is required.
Source inspection refuses unadmitted engines and encrypted tablespaces.
External tablespace/MERGE mappings and other archive formats remain refused
until their native path/key handling is implemented. Native encryption-key
provisioning, other utility versions and broader physical recovery remain gaps. They
are not closed-source Enterprise deferrals or declared inapplicable features.

Review, execution and observation
--------------------------------

Enter the SSH host, OS account, exact public key, private authentication,
native executable paths and a private workspace separate from the live data
directory and its ancestors. The public-key inspection is unauthenticated;
explicitly choose the key before authenticating. SSH secrets travel separately
from saved review facts and never enter public receipts.

For **Full backup**, select the source's SQL hostname or address as reachable on
that host. The native client independently checks the source UUID, data path,
authenticated account and active roles before backup. The application's native
MySQL connection and the host's source ``auto.cnf`` provide separate binding
checks. Database credential delegation also privately transfers the registered
CA, client certificate and private key. Native ``REQUIRED``, ``VERIFY_CA`` or
``VERIFY_IDENTITY`` policy, selected TLS versions and ciphers are preserved.
Public reviews bind only policy and exact file fingerprints. Private client
files are removed after native utility completion, including refused and
interrupted paths; changed delegation refuses before dispatch.
The pinned XtraBackup utility exposes one password option. It cannot consume
native MFA password slots; MySQL's existing MFA client support is separate.
Use a separately authorized registered backup account for this utility rather
than changing the authentication requirements of an MFA account.

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
Production service installation, unexported/system-state acceptance and cutover
remain open. Replay, exported expected-checkpoint acceptance and physical
retention have their own reviewed workflows below.

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
host lifecycle and cutover requirements remain open.
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
protection remain separate. Exported data/definition acceptance is available
through the independent workflows below; unexported/system state and production
cutover remain open.

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
from unattended startup-drill automation. Expected snapshots are never selected
implicitly. Scheduled checks use the separately reviewed
explicit checkpoint policy below. Unexported/system-state coverage, wider
physical backend admission and production cutover remain open.

Recurring expected-checkpoint recovery drills
---------------------------------------------

Select a retained verified copy-back with **Use copy-back for managed recovery**.
Choose read-only startup, TCP port0, trusted LOCAL INFILE checksum input and a
30–3600-second native lifetime. Under **Recurring physical recovery checks**,
load and select an expected full-instance backup from this source registration,
choose the interval and policy lifetime, then review the policy. Type its exact
UUID, confirm the future work and explicitly delegate SSH and the registered SQL
password encrypted before enabling it. The existing physical worker key authority
is required. These policies have a separate encrypted purpose from backups and
retention.

Every occurrence creates a fresh isolated native recovery from the same retained
copy-back, with a new UUID and private Unix socket. It compares full row counts,
native data checksums and exported definitions against the selected sealed dump,
then stops the original recovered server and independently confirms termination
and credential cleanup. The source may continue accepting writes. Its current
state is never substituted for the selected expected checkpoint. The dump must
include native checksum coverage and both data and definitions. Matching checks
verify those selected exported surfaces; unexported/system state and production
cutover remain separate. Existing recurring full-backup policies continue to
create new backups and optional startup drills; this separate policy tests a
specifically retained recovery point.

Both retained inputs and the physical input's ancestors remain protected while
the policy is enabled or its occurrence is unresolved. The same protection
applies to manual and scheduled retention and connection-profile removal. Worker
SQL connections have their own scoped resolver and never replace interactive
credentials or sessions. Idle worker restart can use the encrypted delegation
after an interactive password is forgotten. Credentials are erased on disabling,
expiry or suspension. Missed intervals are not backfilled.

A difference or interruption suspends future occurrences and preserves each
original job and acceptance receipt. No uncertain occurrence is automatically
repeated. Disable the policy before explicitly stopping or reconciling its
original native jobs. With fresh SSH authentication, **Reconcile native ends and
release workflow protection** requires the original acceptance utility to have
ended and the exact original recovered server generation to have stopped. The
server's confirmed end establishes that its private SQL locks are gone, even
when its SQL transport is unavailable. It releases only the matching original
utility reservation and target fence; it never changes an earlier unknown or
different comparison into a match. Resolve any outstanding occurrence and disable
the policy to release its two retained-input holds. Expired policies also retain
that explicit disable action. A fresh review is required for future work.

Native qualification is available through
``tools/cdeadmin_mysql_physical_replay_qualification.py --check-only``.

Native incremental chains and redo-only preparation
---------------------------------------------------

From a verified full or incremental backup, **Take incremental from this backup**
reviews a new native incremental against that exact immutable input. Confirm
registered SQL-password delegation separately before starting it. XtraBackup
owns the live backup, native locks, changed-page capture and checkpoint. Each
incremental retains its native metadata, byte manifest, original source/host and
ordered full-backup lineage. LSNs are decimal strings, preserving their full
native width. Broad binary-log protection is acquired before dispatch, as for a
full backup. Unknown dispatch replies are observed independently and never
replayed automatically.

To recover a chain:

1. Select the original full backup and **Use separate redo-only copy for
   incrementals**. Review and start initial redo-only preparation, leaving the
   additional incremental selection empty. This runs native preparation without
   undo on a new private copy; it preserves the original full backup.
2. From that verified redo-only copy, select **Use separate redo-only copy for
   incrementals**, load retained incremental inputs, and choose the exact next
   incremental. Review and start the apply. Both the base and delta are copied
   privately before the native utility runs. Repeat for each increment in order.
3. Select **Finalize redo-only copy for recovery**, review and start final native
   preparation with undo. Only the resulting prepared artifact can proceed to
   isolated copy-back and managed recovery.

The native checkpoint and ordered lineage must agree. Applying a delta from
another full backup, skipping or repeating an increment, using raw incremental
files as a complete data directory, or copying back a redo-only target is refused.
A chain supports up to128 retained increments; start a new full backup before
exceeding that bound. The last incremental's native ``xtrabackup_info`` is copied
by XtraBackup into merged targets and can retain ``incremental=Y``. The original
marker is preserved; ``log-applied`` versus ``full-prepared`` in the native
checkpoint determines preparation state, together with the recorded lineage.

Every apply records dependencies on both original inputs. Manual and batch
retention preserve both branches and all ancestors until dependent work is
removed or cancelled before dispatch. Native host-side dependency checks also
cover the additional delta input. Temporary delta copies are removed after the
native process ends; interrupted copies remain inside the original job's reviewed
retention scope. Final preparation and recovery create further immutable
checkpoints; the original full and incremental files remain reusable for another
explicit recovery branch.

Independent native expected-dump acceptance and recurring retained-checkpoint
drills can use copy-backs derived from a finalized incremental chain. Native file
publication, SQL startup, selected exported data/definition acceptance and
production cutover remain separate facts. Qualification is available through
``tools/cdeadmin_mysql_physical_replay_qualification.py --incremental-only`` and
covers two native increments, InnoDB/MyISAM/CSV changes, new and altered objects,
an independent pending source transaction, lost replies, immutable input hashes,
private recovery, data/definition acceptance and the built desktop.

Encrypted native backups and private file-keyring recovery
----------------------------------------------------------

Enable **Retain native file-keyring material for encrypted backup and isolated
recovery** and select the **Native XtraBackup keyring component directory** on
the pinned host. The admitted implementation is MySQL9.7.0's active GPL
``component_keyring_file`` with the matching native XtraBackup component.
Reviews capture the source's redo, undo and binary-log encryption settings,
the native component identity, and hashes of the host server/plugin libraries.
Encrypted tables or logs require explicit key-retention consent. Other keyring
implementations are not silently substituted.

Each sealed artifact retains an opaque copy of the native keyring and a private
native transition key. Incrementals reuse their exact original chain key and
retain the latest keyring snapshot, including source master-key rotations.
These are durable backup keys, distinct from the temporary database password
and TLS files. They follow the same protected dependency chain and reviewed
retention as the physical data. Public receipts expose hashes and policy, never
key contents. Preserve access to this material when retaining or moving backups.

Native preparation uses a separate working copy. Its private configuration
temporarily includes a secret native option file; both the include and option
file are removed after utility termination. Opaque keyring material is held
outside the native working datadir during incremental cleanup and restored
before sealing. Original inputs are rehashed and remain unchanged. A failed or
unknown dispatched backup retains its private transition key for recovery and
reviewed retention; it is never erased merely because a result is uncertain.

Managed recovery copies the native plugins and their packaged private libraries
into its own job, writes a private file-component configuration, and uses a
separate keyring inside its private data directory. It preserves a retained
local component manifest and the source redo/undo/binlog encryption settings.
Independent native SQL readiness verifies the component's actual keyring path
and encryption variables. Read-only and writable replay startup both use this
isolation; recovered master-key rotation changes neither the live source keys
nor the sealed backup keys. Recurring backup/startup-drill policies carry the
same explicit admission and encrypted worker delegation.

Qualification uses ``tools/cdeadmin_mysql_physical_keyring_qualification.py``.
The native engine and utility own encryption, preparation and key rotation;
ScratchRobin does not parse or regenerate native key records. Original utility
failures remain visible and are never automatically retried. External paths,
unexported/system-state acceptance, interrupted legacy/guardian resolution and
production cutover remain separate ``CMP-MY-01`` requirements.

External InnoDB tables and general tablespaces
----------------------------------------------

Enable **Isolate external InnoDB paths in a private Linux filesystem view**
before backing up external InnoDB tables or general tablespaces. The review
lists the source files. Full and incremental artifacts retain native external
tablespace metadata and exact byte manifests. Preparation preserves original
inputs. Copy-back stages another verified input copy and rewrites only its
native utility path map, directing every restored external file into the new
private artifact. Native catalogs and data pages are not rewritten by the app.

Managed recovery moves external payloads into a separate private runtime tree.
A separately admitted Linux mount namespace presents the original datadir and
external directory names as aliases of those private copies. Native MySQL sees
its original paths and matching data/undo homes, so native ``DATA DIRECTORY``
validation and create/insert/drop operations retain their semantics. Its host
filesystem view is read-only; the private workspace is writable. Native
``@@datadir`` therefore reports the original alias, while the receipt separately
identifies the actual private data directory and exact namespace bindings.
The fresh UUID, original native PID and pinned SSH connection identify the
recovered instance. No network fallback is permitted.

The selected Linux64 SSH account must possess mount-namespace and
``mount_setattr`` privileges. Recovery admission tests that capability in a
separate process; a refusal starts no recovery server. Original alias directories
remain separate from the private workspace. Missing original directories are
reconstructed inside the recovery process's private mount namespace. A complete
private parent projection preserves existing siblings and runtime paths before
the missing directory is created; no placeholder is created on the source host.
Top-level missing paths use a private root switch and require its separately
probed OS privilege. The independent observer verifies the native process's
actual namespace, directory identities
and host/workspace mount permissions before admitting an editor connection.
Uncertain filesystem evidence blocks connections while preserving cancellation
of the independently identified original native process. Lost native replies
remain unknown. Recurring backup/startup-drill policies use the same admission
and retained dependencies after worker restart.

Encrypted external tables use the separately retained GPL file-keyring workflow
above. Literal spaces, Unicode and semicolons in child directory names retain
their native filenames; a containing native scan directory avoids interpreting
a literal semicolon as a directory-list separator. Source data/key files and
immutable backup inputs remain unchanged. Manual, batch and scheduled retention
include private external runtime files and interrupted copy-back input copies.

This admission covers InnoDB per-table external data and general tablespaces.
External system/undo geometry, external MERGE members,
broader engine inventory, system-state acceptance, legacy/guardian
resolution and production cutover remain tracked recovery work. Unsupported
absolute system geometry refuses before native copy-back. It is not treated as
an ordinary table path or as a successful restore. Native qualification is
``tools/cdeadmin_mysql_physical_keyring_qualification.py --external``; use
``--desktop-only`` with browser/driver paths for the built desktop workflow.

Missing original directories
~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The native recovery worker can start from a retained copy-back after the source
SQL server has stopped and its original datadir, external directories and
keyring path have disappeared. A private parent projection preserves existing
sibling entries and makes only the reviewed original aliases writable. Both
the directory projection and the native process namespace are independently
observed before an editor connection is admitted. The actual executing file's
device, inode and hash supplement its boot/start identity, so replacing the
executable pathname cannot falsely prove that the original process ended.
Legacy process receipts still use their pinned executing image and birth facts.

``tools/cdeadmin_mysql_physical_missing_qualification.py --missing-paths parent``
and ``--missing-paths root`` exercise actual native encrypted recovery through
both connector interfaces with the source SQL server offline. Owned source
volumes remain mounted at separate hold paths for exact byte comparisons;
original base-namespace aliases remain absent through native editor reads,
writable external DDL, key rotation and independent process stop. The separate
``tools/cdeadmin_mysql_namespace_qualification.py`` checks existing, missing
parent, missing root and mixed missing roots using actual OS/process operations;
its receipts alone do not constitute SQL recovery evidence.
