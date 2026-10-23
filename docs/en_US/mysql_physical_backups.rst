Native MySQL physical artifacts
===============================

The server **Backup → MySQL physical backups** workspace manages native
XtraBackup full backups, preparation of a separate copy, and copy-back into a
new isolated data directory on the authenticated database host. It uses the
existing owner-scoped provider API, private application operation storage and
source archive protection. These are physical artifact operations; starting a
recovered instance, selected log recovery, independent post-replay acceptance,
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
qualify the production workspace. Fixture recovery confirms those selected
cases; it does not close broader recovery, incremental, lifecycle, retention or
cutover requirements. ScratchBird history tests remain owner-deferred.
