MySQL Router host and service administration
=============================================

Open **Availability → MySQL Router host and service administration** on an
owned native MySQL registration. Router runs on an explicitly authenticated
Linux SSH host; that host need not contain a MySQL server or data directory.
The adapter admits native MySQL Router 9.7.0 Community (GPL), Connector/Python
26.7.0 and Python with psutil on that execution host. Windows/macOS native host
adapters and platform acceptance remain with their platform teams.

Bootstrap a new deployment
--------------------------

Select and pin the Router host's independently confirmed OpenSSH public key,
SSH account, native executable, new deployment directory and native operating
system user. Select the live Cluster, ClusterSet or ReplicaSet metadata seed,
bootstrap database account and native TLS policy. CA, certificate and private
key paths refer to files on the Router host. The application registration and
Router host independently observe the native seed UUID and topology identity.
Host-specific authenticated database accounts can differ; the Router host's
actual actor, role, grants and TLS observation bind the review.

Use the registered database credential or supply the separate bootstrap
account's password privately. A request-authorized short-lived private buffer
hands the credential to the background worker; no worker reacquires a request
Vault principal. SSH/database passwords are excluded from stored options,
command arguments and file manifests. Native keyring and certificate contents
remain on the host. Bootstrap accepts one private password input line; select a
compatible native bootstrap account when the registered account requires
multiple factors. Existing multi-factor MySQL client support is unchanged.

Review the exact request and explicitly authorize it. An independent original
guardian supervises native bootstrap and private input cleanup. The native
utility creates accounts, metadata and deployment files. ScratchRobin records
the generated native Router ID and exact file hashes, ownership and modes; it
does not invent a Router identity. Existing deployment directories are never
replaced. Concurrent bootstrap into the same canonical destination is claimed
exclusively. Additional native arguments cannot replace the reviewed identity,
directory, user, TLS or force-replacement fields. Private MRS global-secret
input is outside this adapter's current admission.

Native failure or cancellation can leave files and metadata. Inspect the
original invocation; do not repeat an uncertain bootstrap. Cancel controls the
original native process. A separate acknowledgement releases its deployment
claim only after original writer termination and cleanup are confirmed. It
does not remove partial deployment files or roll back native account/metadata
changes. A missing original receipt remains unknown.

Install and control the service
-------------------------------

Load a completed deployment receipt and select its original job. Select the
exact new systemd unit name and review **Install new Router service**. Native
systemd validates the unit. Exclusive publication preserves existing files,
symlinks and loaded definitions. Installation rereads systemd definitions but
does not start Router or enable boot startup. Router has no mysqld-style
``--validate-config`` mode: its native configuration acceptance occurs at
startup; unit validation does not establish Router configuration acceptance.

Enable, disable, start, stop and restart each require a separate review and
confirmation. Stop/restart require explicit disconnection of all routed clients.
The deployment directory identity, native Router executable/configuration,
generated Router IDs, exact unit/drop-in files and native command identities
bind controls. Active process association checks its native executable, PID
file and systemd control group. An inactive unit uses its original exact
association. Changed inputs require a new eligible association; controls do not
guess an unrelated service from its name.

These controls use the original deployment and current SSH authority without
requiring live SQL. They remain available during a database outage. Every native
command has its original independent guardian receipt. The original SSH reply,
native command result, later phase/file/unit/process observations and routed SQL
readiness remain distinct. Lost replies are never retried automatically; later
successful inspection does not rewrite an original unknown outcome. An
interrupted routed commit retains the native client's uncertain outcome.

Qualification and remaining scope
----------------------------------

``tools/cdeadmin_mysql_router_qualification.py`` qualifies the actual application
API with an explicitly owned three-member MySQL 9.7.0 Cluster and separate native
Router/systemd/SSH host. Pure and C driver runs cover independent seed binding,
private input cleanup, native IDs, once-only bootstrap, service installation and
controls, TLS-routed precise bigint/Unicode data, actual native primary crash,
group election, unfinished-transaction rollback, committed data preservation,
read-only routing, SQL-independent Router controls and crashed-member rejoin.
The built desktop uses the owner context menu and explicit native
bootstrap/service reviews; ``--browser-only-application`` selects its retained
owned qualification application and registration. Keep fixtures/evidence outside
the implementation repository. ScratchBird history tests are not run.

This bounds the deployment/service adapter and Cluster traffic qualification.
It does not close all ``CMP-MY-02`` topology families, native upgrades, production
cutover or ``INV-MYSQL``. ClusterSet/ReplicaSet bootstrap admission does not by
itself prove their production failure/repair acceptance. Router metadata/options,
routing-guideline and account workflows remain owned by the native topology
workspace. Human form validation, platform acceptance and closed Enterprise
features retain their separate ownership/scope.
