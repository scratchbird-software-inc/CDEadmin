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
retain uncertainty and their reservation. Native Shell replay, which manages
additional/reconnecting connections, requires separate transport admission.
If observation is lost during decoding before SQL dispatch, the load remains
not dispatched while the decoder's separate process state stays observable and
cancellable; absence of SQL dispatch does not prove decoder termination.
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
